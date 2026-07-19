import json
import sys
from pathlib import Path

# Nuitka --onefile: sys.argv[0] = 실제 .exe 경로
# 개발 중:          sys.argv[0] = main.py 경로
BASE_DIR     = Path(sys.argv[0]).resolve().parent
CONFIG_PATH  = BASE_DIR / "config.json"
SESSIONS_DIR = BASE_DIR / "sessions"
MODELS_DIR   = BASE_DIR / "models"
LOG_DIR      = BASE_DIR / "Log"

# Provider별 하드코딩 모델 목록
PROVIDER_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini-3.5-flash",       # GA, 최신 고성능 Flash
        "gemini-3.1-flash-lite",  # GA, 빠른 경량 Flash
        "gemini-2.5-pro",         # 고성능 Pro (1M 컨텍스트)
        "gemini-2.5-flash",       # 안정 Flash
        "gemini-2.0-flash",       # 검증된 안정 버전
        "gemini-2.0-flash-lite",  # 경량
    ],
    "openai": [
        "gpt-5.5",        # 최신 프론티어
        "gpt-4.1",        # 최신 안정
        "gpt-4.1-mini",   # 저비용 고속
        "gpt-4o",         # 안정
        "gpt-4o-mini",    # 경량
        "gpt-4-turbo",    # 구세대 안정
    ],
    "anthropic": [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "ollama": [],   # 런타임에 서버 쿼리로 채움
    "cli":    [],   # 모델 선택 없음
}

DEFAULT_CONFIG: dict = {
    # AI 연결
    "provider":  "gemini",
    "model":     "gemini-2.0-flash",
    "api_key":   "",
    "cli_cmd":   "claude",
    # 면접 설정
    "system_prompt": "",
    "resume_paths":  [],   # list[str]
    # 음성 설정
    "whisper_model":      "base",
    "max_record_seconds": 120,    # 0 = 무제한
    # AI 응답 설정
    "max_tokens": 4096,           # Anthropic 전용 (다른 provider는 무시)
    # 필수 Flag
    "flag_ai_verified":  False,
    "flag_prompt_ready": False,
    # 프리셋 (항상 마지막으로 저장)
    "presets": {},   # {name: {"system_prompt": str, "resume_paths": list[str]}}
}



def _ensure_dirs() -> None:
    for d in (SESSIONS_DIR, MODELS_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    """config.json 읽기. 없거나 손상되면 DEFAULT_CONFIG 반환.
    새 키가 DEFAULT에 추가돼도 기존 파일과 merge해 누락을 방지한다."""
    _ensure_dirs()
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            stored = json.load(f)

        return {**DEFAULT_CONFIG, **stored}
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def save(cfg: dict) -> None:
    """cfg를 config.json에 저장."""
    _ensure_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def reset_ai_flag(cfg: dict) -> dict:
    """Provider 또는 Model 변경 시 연결 확인 Flag를 리셋한다."""
    cfg["flag_ai_verified"] = False
    return cfg


def is_prompt_ready(cfg: dict) -> bool:
    """사용자 프롬프트 또는 번들 기본 프롬프트 존재 여부를 런타임에 확인."""
    if cfg.get("system_prompt", "").strip():
        return True
    return (BASE_DIR / "prompts" / "default.txt").exists()


def all_flags_ready(cfg: dict) -> list[str]:
    """미충족 필수 Flag 이름 목록을 반환. 비어 있으면 면접 시작 가능."""
    missing = []
    if not cfg.get("flag_ai_verified"):
        missing.append("flag_ai_verified")
    if not is_prompt_ready(cfg):
        missing.append("flag_prompt_ready")
    return missing
