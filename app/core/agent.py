"""AI provider 추상화 레이어.

ask()    : 단일 인터페이스 — provider에 무관하게 동일하게 호출
verify() : 연결 확인용 최소 테스트 호출 (flag_ai_verified 설정에 사용)
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from app.core.prompt_manager import build_turn_prompt

_log = logging.getLogger(__name__)

# ── 선택적 import (패키지 미설치 환경에서도 앱이 기동되도록) ──────────────
try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GEMINI_OK = True
except ImportError:
    _GEMINI_OK = False

try:
    import openai as _openai_mod
    _OPENAI_OK = True
except ImportError:
    _OPENAI_OK = False

try:
    import anthropic as _anthropic_mod
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False

try:
    import ollama as _ollama_mod
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False

PROVIDER_AVAILABLE = {
    "gemini":    _GEMINI_OK,
    "openai":    _OPENAI_OK,
    "anthropic": _ANTHROPIC_OK,
    "ollama":    _OLLAMA_OK,
    "cli":       True,
}

# 연결 확인 시 허용하는 AI CLI 명령어 목록
_KNOWN_AI_CMDS = {"claude", "gemini", "codex"}

# ── 세션 객체 캐시 (API 모드에서 multi-turn 유지) ───────────────────────────
_gemini_client       = None
_gemini_chat         = None
_gemini_resume_files: list = []   # files.upload() 결과 캐시


def _get_resume_paths(cfg: dict) -> list[str]:
    """resume_paths 목록에서 실제 존재하는 경로만 반환."""
    return [p for p in cfg.get("resume_paths", []) if p and Path(p).exists()]


def init_session(system_prompt: str, cfg: dict,
                 history: list[dict] | None = None) -> None:
    """면접 시작 시 AI 세션 초기화.
    history: 이어하기 시 이전 턴 목록 — Gemini chat history에 주입한다."""
    global _gemini_client, _gemini_chat, _gemini_resume_files
    provider = cfg.get("provider", "gemini")

    if provider == "gemini" and _GEMINI_OK:
        _gemini_client = _genai.Client(
            api_key=cfg["api_key"],
            http_options={"timeout": 60_000},   # 60초 (단위: ms)
        )

        chat_history: list = []
        _gemini_resume_files = []

        # 이력서 파일 업로드 → 히스토리 첫머리에 추가
        resume_paths = _get_resume_paths(cfg)
        if resume_paths:
            file_parts = []
            for rp in resume_paths:
                try:
                    f = _gemini_client.files.upload(path=rp)
                    _gemini_resume_files.append(f)
                    file_parts.append(
                        _genai_types.Part(
                            file_data=_genai_types.FileData(
                                file_uri=f.uri,
                                mime_type=f.mime_type,
                            )
                        )
                    )
                except Exception:
                    _log.warning("Gemini 파일 업로드 실패: %s", rp)

            if file_parts:
                file_parts.append(
                    _genai_types.Part(text="이 문서들은 지원자의 이력서/포트폴리오입니다. 면접 중 참고해 주세요.")
                )
                chat_history.extend([
                    _genai_types.Content(role="user", parts=file_parts),
                    _genai_types.Content(
                        role="model",
                        parts=[_genai_types.Part(text="자료를 확인했습니다. 면접을 진행하겠습니다.")],
                    ),
                ])

        # 이전 세션 턴을 히스토리에 주입 (이어하기)
        if history:
            for turn in history:
                role = "model" if turn["role"] == "interviewer" else "user"
                chat_history.append(
                    _genai_types.Content(
                        role=role,
                        parts=[_genai_types.Part(text=turn["text"])],
                    )
                )

        _gemini_chat = _gemini_client.chats.create(
            model=cfg["model"],
            config=_genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
            history=chat_history,
        )


def ask(user_text: str, history: list[dict], system_prompt: str, cfg: dict) -> str:
    """사용자 발화 → AI 응답 텍스트 반환."""
    provider = cfg.get("provider", "gemini")
    try:
        if provider == "gemini":
            return _ask_gemini(user_text)
        if provider == "openai":
            return _ask_openai(user_text, history, system_prompt, cfg)
        if provider == "anthropic":
            return _ask_anthropic(user_text, history, system_prompt, cfg)
        if provider == "ollama":
            return _ask_ollama(user_text, history, system_prompt, cfg)
        if provider == "cli":
            return _ask_cli(user_text, history, system_prompt, cfg)
        raise ValueError(f"Unknown provider: {provider}")
    except Exception:
        _log.exception("AI 호출 실패 (provider=%s)", provider)
        raise


def verify(system_prompt: str, cfg: dict) -> tuple[bool, str]:
    """연결 확인용 테스트 호출. (성공 여부, 오류 메시지) 반환."""
    provider = cfg.get("provider", "gemini")
    try:
        if provider == "gemini":
            _verify_gemini(cfg)
        elif provider == "openai":
            _verify_openai(cfg)
        elif provider == "anthropic":
            _verify_anthropic(cfg)
        elif provider == "ollama":
            _verify_ollama(cfg)
        elif provider == "cli":
            _verify_cli(cfg)
        return True, ""
    except Exception as e:
        _log.warning("연결 확인 실패 (provider=%s): %s", provider, e)
        return False, str(e)


def fetch_ollama_models() -> list[str]:
    """로컬 Ollama 서버에서 설치된 모델 목록을 가져온다."""
    if not _OLLAMA_OK:
        return []
    try:
        models = _ollama_mod.list()
        return [m.model for m in models.models]
    except Exception:
        _log.warning("Ollama 모델 목록 가져오기 실패")
        return []


# ── Provider별 내부 구현 ──────────────────────────────────────────────────

def _ask_gemini(user_text: str) -> str:
    if not _GEMINI_OK or _gemini_chat is None:
        raise RuntimeError("Gemini 세션이 초기화되지 않았습니다.")
    response = _gemini_chat.send_message(user_text)
    return response.text


def _ask_openai(user_text: str, history: list[dict], system_prompt: str, cfg: dict) -> str:
    from app.core.prompt_manager import extract_resume_text
    client = _openai_mod.OpenAI(api_key=cfg["api_key"])

    # 이력서 텍스트를 시스템 메시지에 포함 (OpenAI는 파일 첨부 미지원)
    effective_system = system_prompt
    texts = []
    for rp in _get_resume_paths(cfg):
        t = extract_resume_text(rp)
        if t:
            texts.append(f"[파일: {Path(rp).name}]\n{t}")
    if texts:
        effective_system += "\n\n[지원자 이력서/컨텍스트]\n" + "\n\n".join(texts)

    messages = [{"role": "system", "content": effective_system}]
    for t in history:
        role = "assistant" if t["role"] == "interviewer" else "user"
        messages.append({"role": role, "content": t["text"]})
    messages.append({"role": "user", "content": user_text})
    resp = client.chat.completions.create(model=cfg["model"], messages=messages)
    return resp.choices[0].message.content


def _ask_anthropic(user_text: str, history: list[dict], system_prompt: str, cfg: dict) -> str:
    import base64 as _base64
    from app.core.prompt_manager import extract_resume_text
    client = _anthropic_mod.Anthropic(api_key=cfg["api_key"])
    messages = []

    # 이력서/포트폴리오를 document 블록으로 준비
    doc_blocks: list[dict] = []
    for rp in _get_resume_paths(cfg):
        p = Path(rp)
        if p.suffix.lower() == ".pdf":
            try:
                data = _base64.standard_b64encode(p.read_bytes()).decode("utf-8")
                doc_blocks.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                })
            except Exception:
                _log.warning("Anthropic PDF 읽기 실패: %s", rp)
        else:
            t = extract_resume_text(rp)
            if t:
                doc_blocks.append({"type": "text", "text": f"[파일: {p.name}]\n{t}"})

    # 이력서 블록이 있으면 대화 앞에 컨텍스트 교환을 삽입
    if doc_blocks:
        doc_blocks.append({"type": "text", "text": "이 문서들은 지원자의 이력서/포트폴리오입니다. 면접 중 참고해 주세요."})
        messages.append({"role": "user", "content": doc_blocks})
        messages.append({"role": "assistant", "content": "자료를 확인했습니다. 면접을 진행하겠습니다."})

    for t in history:
        role = "assistant" if t["role"] == "interviewer" else "user"
        messages.append({"role": role, "content": t["text"]})
    messages.append({"role": "user", "content": user_text})

    resp = client.messages.create(
        model=cfg["model"],
        max_tokens=cfg.get("max_tokens", 4096),
        system=system_prompt,
        messages=messages,
    )
    return resp.content[0].text


def _ask_ollama(user_text: str, history: list[dict], system_prompt: str, cfg: dict) -> str:
    from app.core.prompt_manager import extract_resume_text

    # 이력서 텍스트를 시스템 메시지에 포함 (Ollama는 파일 첨부 미지원)
    effective_system = system_prompt
    texts = []
    for rp in _get_resume_paths(cfg):
        t = extract_resume_text(rp)
        if t:
            texts.append(f"[파일: {Path(rp).name}]\n{t}")
    if texts:
        effective_system += "\n\n[지원자 이력서/컨텍스트]\n" + "\n\n".join(texts)

    messages = [{"role": "system", "content": effective_system}]
    for t in history:
        role = "assistant" if t["role"] == "interviewer" else "user"
        messages.append({"role": role, "content": t["text"]})
    messages.append({"role": "user", "content": user_text})
    resp = _ollama_mod.chat(model=cfg["model"], messages=messages)
    return resp.message.content


_CLI_MAX_CHARS        = 6_000   # CLI 안전 프롬프트 상한 (chars)
_CLI_MAX_HIST_TURNS   = 6       # 최대 유지 히스토리 턴 수 (면접관+지원자 각 3회)


def _build_cli_prompt(system_prompt: str, history: list[dict], user_text: str, cfg: dict) -> str:
    """CLI 컨텍스트 제한에 맞게 히스토리·시스템 프롬프트를 조정."""
    # 이력서 파일 경로 목록을 시스템 프롬프트에 참조로 추가 (CLI는 로컬 파일 직접 읽기 가능)
    effective_system = system_prompt
    resume_paths = _get_resume_paths(cfg)
    if resume_paths:
        paths_str = "\n".join(f"- {rp}" for rp in resume_paths)
        effective_system += (
            f"\n\n[지원자 이력서/포트폴리오 파일 목록]\n{paths_str}\n"
            "위 파일들을 직접 읽어 지원자 이력서/포트폴리오로 참고하십시오."
        )

    # 1단계: 히스토리를 최근 N턴으로 제한
    trimmed_hist = history[-_CLI_MAX_HIST_TURNS:] if len(history) > _CLI_MAX_HIST_TURNS else history
    suffix = "\n[이전 대화 일부 생략]" if len(trimmed_hist) < len(history) else ""
    prompt = build_turn_prompt(effective_system + suffix, trimmed_hist, user_text)

    # 2단계: 여전히 초과하면 시스템 프롬프트를 잘라냄
    if len(prompt) > _CLI_MAX_CHARS:
        max_sys = _CLI_MAX_CHARS // 2
        short_sys = effective_system[:max_sys] + "\n...(시스템 프롬프트 일부 생략)"
        prompt = build_turn_prompt(short_sys, trimmed_hist, user_text)

    _log.debug("CLI 프롬프트 길이: %d chars (히스토리 %d→%d턴)",
               len(prompt), len(history), len(trimmed_hist))
    return prompt


def _ask_cli(user_text: str, history: list[dict], system_prompt: str, cfg: dict) -> str:
    import tempfile as _tempfile

    prompt = _build_cli_prompt(system_prompt, history, user_text, cfg)
    cmd = cfg.get("cli_cmd", "claude")

    full_path = shutil.which(cmd)
    if full_path is None:
        raise RuntimeError(f"'{cmd}' CLI를 찾을 수 없습니다. PATH를 확인해 주세요.")

    base_name = Path(full_path).stem.lower()

    # CLI별 플래그 (stdin 파이프 수신 시)
    # --dangerously-skip-permissions: Claude Code가 비대화형 환경에서 권한 확인을 건너뜀
    # (stdin이 없는 subprocess이므로 권한 프롬프트에 응답할 수 없어 필수)
    _CLI_FLAGS: dict[str, list[str]] = {
        "claude": ["-p", "--dangerously-skip-permissions"],
        "gemini": [],       # gemini    : 플래그 없이 stdin 읽음 (-p는 project ID 플래그)
        "codex":  [],
    }
    flags = _CLI_FLAGS.get(base_name, ["-p"])
    flags_str = (" " + " ".join(flags)) if flags else ""

    # 프롬프트를 임시 파일에 저장 (WinError 206 커맨드라인 길이 제한 우회)
    tmp = _tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(prompt)
        tmp.flush()
        tmp.close()

        if sys.platform == "win32":
            # $OutputEncoding: PowerShell이 파이프로 전달하는 바이트 인코딩
            # [Console]::OutputEncoding: 자식 프로세스 출력을 캡처할 때 사용하는 인코딩
            # -Encoding UTF8: Get-Content가 파일을 UTF-8로 읽도록 명시 (시스템 기본값 우회)
            ps_cmd = (
                "$OutputEncoding = [System.Text.Encoding]::UTF8; "
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                f"Get-Content -Encoding UTF8 -Raw -Path '{tmp.name}'"
                f" | & '{full_path}'{flags_str}"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,   # Node.js CLI cold start 포함해 최대 3분
            )
        else:
            with open(tmp.name, encoding="utf-8") as stdin_f:
                result = subprocess.run(
                    [full_path] + flags,
                    stdin=stdin_f,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=180,
                )
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    _log.debug(
        "CLI [%s] returncode=%d | stdout=%r | stderr=%r",
        base_name, result.returncode,
        result.stdout[:400], result.stderr[:400],
    )

    if result.returncode != 0:
        # stderr 없으면 stdout도 확인 (CLI가 에러를 stdout에 출력하는 경우)
        err = result.stderr.strip() or result.stdout.strip() or f"CLI 호출 실패 (code={result.returncode})"
        raise RuntimeError(err)

    if not result.stdout.strip():
        raise RuntimeError("CLI가 빈 응답을 반환했습니다. 로그 파일을 확인해 주세요.")

    return result.stdout.strip()


# ── 연결 확인 ─────────────────────────────────────────────────────────────

def _verify_gemini(cfg: dict) -> None:
    client = _genai.Client(
        api_key=cfg["api_key"],
        http_options={"timeout": 30_000},   # 30초 (단위: ms)
    )
    client.models.generate_content(model=cfg["model"], contents="hi")


def _verify_openai(cfg: dict) -> None:
    _openai_mod.OpenAI(api_key=cfg["api_key"]).models.list()


def _verify_anthropic(cfg: dict) -> None:
    _anthropic_mod.Anthropic(api_key=cfg["api_key"]).messages.create(
        model=cfg["model"],
        max_tokens=1,   # 연결 확인용 최소값
        messages=[{"role": "user", "content": "hi"}],
    )


def _verify_ollama(cfg: dict) -> None:
    import urllib.request
    urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)


def _verify_cli(cfg: dict) -> None:
    cmd = cfg.get("cli_cmd", "claude")
    if shutil.which(cmd) is None:
        raise RuntimeError(f"'{cmd}' CLI를 찾을 수 없습니다. PATH를 확인해 주세요.")
    base_name = Path(cmd).stem.lower()
    if base_name not in _KNOWN_AI_CMDS:
        known_str = ", ".join(sorted(_KNOWN_AI_CMDS))
        raise RuntimeError(
            f"'{cmd}'은 알려진 AI CLI가 아닙니다.\n지원하는 AI CLI: {known_str}"
        )
