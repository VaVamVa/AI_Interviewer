# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 목적

지인 배포용 **음성 대화형 모의 면접 앱** (Windows 데스크탑).

## 개발 환경 설정 (최초 1회)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 개발 명령어

```powershell
# 개발 중 실행 (-X utf8 필수 — Windows cp949 로케일 인코딩 오류 방지)
.venv\Scripts\python.exe -X utf8 main.py

# 배포용 빌드 (Nuitka → dist/AI_Interviewer.exe)
.venv\Scripts\python.exe -X utf8 build.py
```

`-X utf8` 없이 실행하면 Windows 한국어 환경에서 `UnicodeDecodeError: 'cp949'` 오류가 발생한다.
venv를 사용해야 Nuitka가 필요한 패키지만 포함하여 빌드한다.

## 아키텍처 핵심

### 상태 머신 (`app/states.py`)

면접 창(InterviewWindow) 내부 상태. 메인 창(MainWindow)은 별도 창으로 면접 시작 시 숨기고 종료 시 다시 표시한다.

```
INITIALIZING → SPEAKING ↔ LISTENING → RECORDING → PROCESSING → SPEAKING (반복)
                                                ↘ (종료 시) ENDING
```

- **SPEAKING/PROCESSING/INITIALIZING**: 녹음 버튼 비활성
- **RECORDING**: 사용자가 직접 [답변 완료]를 눌러야만 종료 (VAD 없음)

### 비동기 처리 (`app/ui/workers.py`)

모든 블로킹 작업은 `QThread` 워커로 분리하고 `pyqtSignal`로 UI에 결과를 전달한다.

```
STTWorker             → transcribed(str)
AIWorker              → response(str)
TTSWorker             → started_tts(), finished_tts()
ModelDownloadWorker   → progress(int), finished()
VerifyWorker          → success(), error(str)
OllamaModelListWorker → fetched(list)
```

### AI Provider 분기 (`app/core/agent.py`)

`ask(user_text, history, system_prompt, cfg)` 단일 함수로 5개 provider를 추상화:

| Provider | 방식 | 이력서 처리 |
|----------|------|------------|
| `gemini` | `google-genai` Client + Chat (stateful) | `files.upload()` → chat history에 주입 |
| `openai` | `openai` SDK, stateless | `pypdf`로 텍스트 추출 → system 메시지에 삽입 |
| `anthropic` | `anthropic` SDK, stateless | PDF → base64 document 블록 |
| `ollama` | `ollama` SDK, stateless | `pypdf`로 텍스트 추출 → system 메시지에 삽입 |
| `cli` | `subprocess` + PowerShell pipe | 파일 경로를 프롬프트에 명시 |

Gemini는 `init_session(system_prompt, cfg, history)`에서 Chat 객체를 생성하고 이력서 파일 업로드 + 이전 세션 턴을 모두 chat history에 주입한다. 나머지 provider는 stateless이므로 매 호출마다 `history`를 프롬프트에 직렬화한다.

CLI는 `build_turn_prompt()`로 전체 대화 히스토리를 하나의 문자열로 직렬화하며, `_CLI_MAX_HIST_TURNS = 6`(최근 6턴)·`_CLI_MAX_CHARS = 6_000`(문자 수) 두 가지 제한을 순차 적용한다.

### 마스터 프롬프트 (`app/core/prompt_manager.py`)

`_MASTER_PROMPT` (영어, 하드코딩)가 사용자 프롬프트 앞에 항상 삽입된다. 사용자는 접근·수정 불가. 규칙: 질문 1개 제한, 면접 형식 유지, 인젝션 방지, 마크다운 금지, 한국어 진행.

`build_system_prompt(cfg)` → `_MASTER_PROMPT + 사용자 프롬프트` 반환. 이력서는 포함하지 않으며 provider별로 `agent.py`에서 별도 처리한다.

### 면접 시작 Flag 시스템

- `flag_ai_verified`: AI 연결 테스트 성공 여부 — config.json에 저장
- `flag_prompt_ready`: `is_prompt_ready(cfg)` 런타임 함수로 판단 — config에 저장 안 함
  - `cfg["system_prompt"].strip()` 비어 있지 않으면 True
  - 또는 `BASE_DIR / "prompts" / "default.txt"` 존재하면 True
  - → 기본 프롬프트 파일만 있어도 면접 시작 가능, 별도 설정 불필요

Flag 미충족 시 [새 면접 시작하기]를 눌러도 경고만 표시. ConfigDialog는 [⚙] 버튼으로만 진입하며 면접 시작 흐름과 독립적이다. `flag_ai_verified`는 provider/model 변경 시 자동 리셋.

### Config 흐름 (`app/config.py`)

```python
BASE_DIR    = Path(sys.argv[0]).resolve().parent   # exe 또는 main.py 위치
CONFIG_PATH = BASE_DIR / "config.json"
```

`DEFAULT_CONFIG` 주요 키:

```python
{
    "provider": "gemini",        # gemini | openai | anthropic | ollama | cli
    "model": "gemini-2.0-flash",
    "api_key": "",
    "cli_cmd": "claude",
    "system_prompt": "",
    "resume_paths": [],          # list[str] — 여러 파일 지원
    "whisper_model": "base",
    "max_record_seconds": 120,
    "max_tokens": 4096,          # Anthropic 전용 (_ask_anthropic에서 사용)
    "flag_ai_verified": False,
    "presets": {},               # {name: {"system_prompt": str, "resume_paths": list}}
}
```

`flag_prompt_ready`는 DEFAULT_CONFIG에 없음 — `is_prompt_ready(cfg)` 함수로 런타임 판단.

### 설정 다이얼로그 (`app/ui/config_dialog.py`)

- **프리셋**: `system_prompt` + `resume_paths` 조합을 이름으로 저장·불러오기·삭제. `config.json`의 `presets` 키에 저장.
- **이력서**: `QListWidget`으로 다중 파일 관리. 파일명 표시, 전체 경로는 tooltip.
- **STT 설정** (면접 설정 섹션):
  - Whisper 모델 드롭다운: `tiny / base / small / medium / large-v3`
  - 저장 시 해당 모델이 `MODELS_DIR`에 없으면 다운로드 여부 확인 → `ModelDownloadWorker` 실행
  - 최대 녹음 시간 스핀박스: 0–600초, 0 = 무제한 (`specialValueText`)

### 면접 화면 주요 동작 (`app/ui/interview_window.py`)

- **"다른 주제로" 버튼** (`_topic_btn`): LISTENING 상태에서만 활성. 클릭 시 `QInputDialog`로 키워드 입력창 표시. 키워드 입력 시 `_NEXT_TOPIC_KEYWORD_MSG`(키워드 포함), 빈 칸이면 `_NEXT_TOPIC_MSG`를 AI에 전송. 취소하면 상태 변경 없이 복귀. 세션 히스토리(`self._history`, `session.turns`)에는 기록하지 않음.
- **`_end_interview()`**: `self._state = AppState.ENDING` 설정 후 `self.close()` 호출. `closeEvent`가 ENDING 상태를 확인해 재진입을 방지함.
- **강제 종료 보호**: RECORDING/PROCESSING/SPEAKING 중 창 닫기 시 확인 다이얼로그 표시 (ENDING/INITIALIZING 상태면 즉시 닫힘).

### 세션 자동저장 (`app/session.py`)

```python
{
    "session_id": "YYYY-MM-DD_HH-MM-SS",
    "started_at": "YYYY-MM-DD_HH-MM-SS",
    "elapsed_seconds": 342,       # 경과 시간 누적 (이어하기 시 복원)
    "snapshot": {
        "system_prompt": "...",   # 세션 시작 시점의 프롬프트 동결
        "resume_paths": [...]     # 세션 시작 시점의 파일 목록 동결
    },
    "turns": [{"role": "interviewer"|"candidate", "text": "...", "timestamp": "..."}]
}
```

`status` 필드 없음 — completed/interrupted 구분 제거. 모든 세션은 이어하기 가능.

`load_latest_session()` (구 `load_latest_incomplete()`): 가장 최근 세션 반환, status 필터 없음.

매 턴 완료 시 `autosave()` 덮어쓰기 → 크래시 복구 가능.

### 세션 이어하기 흐름

1. MainWindow [📋 세션 목록] → `SessionListDialog`: 전체 세션 테이블 (날짜·턴 수·경과 시간)
2. 세션 선택 → [▶ 이어하기] 클릭 → `dlg.resume_session` 설정 후 `accept()`
3. `snapshot.resume_paths` 파일 존재 검사 → 없으면 경고 다이얼로그 (강행 또는 취소)
4. InterviewWindow 생성: `snapshot.system_prompt` + `snapshot.resume_paths` 사용, provider/model/api_key는 현재 config
5. `_interview_secs` = `resume_session["elapsed_seconds"]` 로 타이머 복원
6. `init_session(history=이전턴들)` 호출 → Gemini는 chat history에 턴 주입
7. `_RESUME_CONTEXT_MSG` 전송 → AI 응답 대기 → [▶ 면접 재개] 버튼 표시
8. 재개 클릭 → 마지막 턴이 면접관이면 LISTENING, 지원자면 AI 호출 후 SPEAKING

### Nuitka 번들 규칙

- **번들 포함**: `prompts/`, `assets/` (`--include-data-dir`)
- **번들 제외**: `config.json`, `sessions/`, Whisper 모델 — 런타임에 BASE_DIR 하위 생성/다운로드

## 주요 설계 제약

- **Setup은 진입점이 아님**: 설정 없이도 앱이 열린다. ConfigDialog는 [⚙]로만 진입.
- **답변 종료는 버튼**: VAD 없음. 사용자가 [답변 완료]를 직접 누른다.
- **모든 블로킹 작업은 QThread**: STT, TTS, AI 호출, 모델 다운로드 모두 워커로 분리.
- **강제 종료 대비**: `closeEvent`에서 ENDING 상태 체크 → 워커 종료 → 세션 저장 → 오디오 해제 순서 유지.
- **중복 면접 방지**: 면접 시작 시 MainWindow를 `hide()`, 종료 시 `interview_closed` 시그널로 복귀.
- **세션 관리는 SessionListDialog**: IDLE에 이어하기 버튼 없음. 세션 목록에서 이어하기·삭제·미리보기.
- **세션에 status 없음**: 모든 세션은 이어하기 가능. 완료/미완료 구분하지 않음.
