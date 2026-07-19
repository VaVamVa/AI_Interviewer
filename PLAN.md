# AI 음성 모의 면접 앱 — 구현 플랜

## 프로젝트 개요

지인 배포용 음성 대화형 모의 면접 애플리케이션.

**고정 로직:**
- 음성 대화 (마이크 → STT → AI → TTS → 스피커)
- 대화 내용 텍스트 로그 자동 저장

**핵심 설계 원칙:**
- Setup이 진입점이 되어선 안 됨. 모든 설정은 앱 내부에서 언제든 변경 가능
- 면접 시작 직전 설정을 한 번 더 확인/수정하는 흐름
- API Key 등 민감 정보는 소스에 포함되지 않고 설치 경로 하위 폴더에 외부화
- Nuitka로 네이티브 exe 빌드 → 소스코드 역공학 사실상 불가

---

## 기술 스택

| 역할 | 도구 | 비고 |
|------|------|------|
| UI | PyQt6 | QThread로 블로킹 작업 분리 |
| STT | faster-whisper | 로컬 무료, base 모델 (~145MB) 첫 실행 시 자동 다운로드 |
| TTS | edge-tts | Microsoft Edge 엔진 무료 |
| AI — API 모드 | google-generativeai | Gemini 2.0 Flash, AI Studio 무료 티어 |
| AI — CLI 모드 | subprocess | claude / gemini 등 구독 CLI 도구 |
| 오디오 캡처 | sounddevice + scipy | WAV 저장 후 STT 전달 |
| 패키징 | Nuitka `--onefile` | 네이티브 exe, C 컴파일 |
| 인스톨러 | Inno Setup | 바탕화면 바로가기, 제거 지원 |

---

## 디렉토리 구조

```
AI_Interviewer/
├── main.py                    # 진입점 — QApplication 초기화, MainWindow 실행
├── requirements.txt           # 의존성 목록
├── build.py                   # Nuitka 빌드 스크립트
├── installer.iss              # Inno Setup 인스톨러 스크립트
│
├── app/
│   ├── states.py              # AppState Enum (INITIALIZING / SPEAKING / ... / ENDING)
│   ├── config.py              # <설치 경로>\config.json 읽기/쓰기, BASE_DIR 제공
│   ├── session.py             # 면접 세션 저장/불러오기 (자동저장 포함)
│   │
│   ├── core/
│   │   ├── voice.py           # STT (faster-whisper) + TTS (edge-tts) + 오디오 캡처
│   │   ├── agent.py           # API 모드 / CLI 모드 단일 인터페이스로 추상화
│   │   └── prompt_manager.py  # 프롬프트 파일 로드, _MASTER_PROMPT 하드코딩
│   │
│   └── ui/
│       ├── main_window.py     # IDLE 화면 (새 면접 시작, 세션 목록 진입)
│       ├── config_dialog.py   # 설정 다이얼로그 ([⚙] 버튼으로만 진입)
│       ├── interview_window.py # 면접 진행 화면 (녹음/STT/TTS/AI 상태 머신)
│       ├── session_list_dialog.py # 세션 목록·삭제·이어하기 다이얼로그
│       └── workers.py         # QThread 워커 모음
│
├── prompts/                   # exe에 번들되는 기본 프롬프트 템플릿
│   ├── default.txt
│   ├── guide_api.md           # IDLE 토글 — 무료 API Key 발급 안내
│   └── guide_cli.md           # IDLE 토글 — CLI 도구 설치 안내
│
└── assets/
    └── icon.ico
```

---

## 앱 상태 머신

```
IDLE
  │  [새 면접 시작하기] 클릭
  ▼
CONFIG_PANEL
  │  config.json 존재 시 pre-fill, 없으면 기본값
  │  사용자가 AI 모드 / API Key / 프롬프트 / 이력서 경로 확인·수정
  │  [면접 시작] 클릭
  ▼
INITIALIZING
  │  프롬프트 로드, AI 페르소나 확립, 첫 질문 생성
  ▼
SPEAKING         ← TTS 재생 중. 버튼 전체 비활성
  │  TTS 완료
  ▼
LISTENING        ← [🎤 녹음 시작] 활성화
  │  버튼 클릭
  ▼
RECORDING        ← 마이크 캡처 중. 버튼 [■ 답변 완료]로 변경
  │  버튼 클릭
  ▼
PROCESSING       ← STT → AI 호출 → TTS 준비. 버튼 비활성
  │  완료
  ▼
SPEAKING         ← 반복
  │
  │  [■ 종료] 클릭 또는 창 닫기
  ▼
ENDING           ← 세션 저장, 오디오 리소스 해제
  ▼
IDLE
```

---

### 필수 Flag 정의

면접 시작 전 충족되어야 하는 조건. `config.json`에 저장되며 앱 진입 시 로드.

| Flag | 의미 | 충족 조건 |
|------|------|----------|
| `flag_ai_verified` | AI 연결 확인 완료 | 테스트 호출 성공 또는 CLI 감지 성공 |
| `flag_prompt_ready` | 시스템 프롬프트 준비됨 | 직접 입력 **또는** `prompts/default.txt` 파일 존재 (런타임 체크) |

`is_prompt_ready(cfg)` 함수가 런타임에 판단. `flag_prompt_ready` 값을 config에 저장하지 않음.

> 이력서 경로는 선택 사항 — 없어도 면접 시작 가능

---

### IDLE

**진입 조건:** 앱 최초 실행 또는 ENDING 완료 후

**동작:**
- `config.load()` → 필수 Flag 상태 확인 후 UI에 반영
  - 각 Flag ✅ / ❌ 상태를 메인 화면에 표시
- [새 면접 시작하기] + [📋 세션 목록] 버튼 표시
- 우상단 [⚙] 버튼: `ConfigDialog` 독립 실행 (면접 시작과 무관)
- 하단 고정: **[📖 시작하기 전에]** 토글 (접기/펼치기)
  - 펼치면 아래 두 섹션을 인앱으로 표시 (외부 브라우저 열지 않음):
    1. **무료 API Key 발급 방법** — Google AI Studio 발급 절차 안내
    2. **CLI 도구 설치 방법** — claude / gemini CLI 설치 절차 안내
  - 안내 문서는 `prompts/guide_api.md`, `prompts/guide_cli.md`로 관리
    → 배포 후 내용 수정이 필요하면 해당 파일만 교체하면 됨
  - 기본 상태: 접혀 있음 (Flag 모두 ✅이면 자동으로 접힌 상태 유지)

**[새 면접 시작하기] 클릭 시:**
```
필수 Flag 전체 충족?
  YES → INITIALIZING 진입
  NO  → 미충족 Flag 항목 하이라이트 + "설정을 완료해 주세요" 안내
        ConfigDialog 자동으로 열리지 않음 (사용자가 [⚙]로 직접 진입)
```

**전환:**
- [새 면접 시작하기] + 모든 Flag ✅ → INITIALIZING
- [📋 세션 목록] → `SessionListDialog` (이어하기 선택 시 INITIALIZING)
- [⚙] → CONFIG_PANEL (독립 실행)

---

### CONFIG_PANEL

**진입 조건:** [⚙] 버튼 클릭 (면접 시작 흐름과 독립적)

**구성 — Flag 방식 (순서 자유, 단 AI 연결 섹션 내부는 Step 방식)**

#### 섹션 1: AI 연결 설정 `flag_ai_verified`

내부는 선후관계가 있으므로 Step 방식으로 진행:

```
Step 1. Provider 선택
        [ Gemini | OpenAI | Anthropic | Ollama | CLI ]

        ⚠️ Provider 선택 시 아래 주의사항을 인라인으로 표시:
        - CLI 선택 시:
          "CLI 모드는 구독 계정의 대화 기록을 소모하며,
           히스토리 전체를 매 요청마다 전송하므로 응답 속도가
           느리고 토큰 사용량이 많을 수 있습니다."
        - API Key 방식 (Gemini / OpenAI / Anthropic) 선택 시:
          "API 사용량에 따라 추가 비용이 발생할 수 있습니다.
           무료 티어 한도를 초과하지 않도록 주의하세요."
        - Ollama 선택 시: 주의사항 없음 (로컬 무료)

Step 2. Model 선택
        Provider에 따라 목록 변경
        - Gemini / OpenAI / Anthropic: 하드코딩 목록 드롭다운
        - Ollama: localhost:11434 쿼리로 설치된 모델 동적 로드
        - CLI: 명령어 입력란 + shutil.which() 감지 표시

Step 3. API Key 입력
        - Ollama / CLI: 이 Step 스킵
        - 나머지: Key 입력란 표시

Step 4. [연결 확인] 버튼
        - 테스트 호출 실행 (비용 최소 호출)
        - 성공: flag_ai_verified = True, ✅ 표시
        - 실패: 오류 메시지 표시, Step 3으로 포커스
```

Provider / Model 변경 시 `flag_ai_verified = False`로 리셋.

#### 섹션 2: 면접 설정 `flag_prompt_ready`

순서 자유, 각 항목 독립적:

- **시스템 프롬프트**: 직접 편집 or `prompts/` 기본 파일 선택
  - 어느 쪽이든 내용이 존재하면 `flag_prompt_ready = True`
- **회사 선택** _(선택)_: 드롭다운, 기본 프롬프트 파일과 연동
- **이력서 경로** _(선택)_: 파일 탐색기로 선택

**하단 공통:**
- Flag 상태 요약 표시: `✅ AI 연결됨  ✅ 프롬프트 준비됨`
- [저장]: `config.save()` 후 다이얼로그 유지
- [×] 닫기: 미저장 변경사항 있을 시 경고, IDLE 유지

---

### INITIALIZING

**진입 조건:** CONFIG_PANEL에서 [면접 시작] 클릭

**동작 (순서):**
1. `prompt_manager.build_system_prompt(cfg)` — 시스템 프롬프트 + 이력서 컨텍스트 조합
2. Whisper 모델 존재 확인 (`%APPDATA%\AI_Interviewer\models\`)
   - 없으면 `ModelDownloadWorker` 실행, 진행률 표시 후 대기 (`<설치 경로>\models\`에 저장)
3. 새 세션 객체 생성 (`session_id`, `company`, `status: "interrupted"`, `turns: []`)
4. `AIWorker` 실행: 시스템 프롬프트 전달, 빈 히스토리로 첫 질문 생성 요청
5. AI 응답 수신 → 세션 turns에 추가 → `session.autosave()`
6. `TTSWorker` 실행 준비

**전환:**
- AIWorker 응답 수신 완료 → SPEAKING
- 오류 발생 (API 실패, CLI 실패) → 오류 다이얼로그 표시 후 IDLE
- 오류 발생에 대한 Log 메시지 `<설치 경로>\Log\` 폴더에 저장

---

### SPEAKING

**진입 조건:** INITIALIZING 완료 또는 PROCESSING 완료 후 AI 응답 준비됨

**동작:**
- `TTSWorker` 실행: AI 응답 텍스트 → edge-tts mp3 생성 → pygame 재생
- 대화 로그에 면접관 발화 추가 (TTS 시작 시점에 즉시 표시)
- 녹음 버튼 비활성화, [❌ 종료] 버튼만 활성
- 상태 레이블: "🔊 면접관 답변 중..."

**전환:**
- `TTSWorker.finished` signal → LISTENING
- [❌ 종료] 클릭 → `TTSWorker` 즉시 중단 (`pygame.mixer.stop()`) → ENDING

---

### LISTENING

**진입 조건:** SPEAKING 완료 (TTSWorker.finished signal)

**동작:**
- [🎤 녹음 시작] 버튼 활성화
- [📖 대화 로그 펼치기/접기] 버튼 활성화
- 상태 레이블: "⏳ 답변을 말씀해 주세요"
- 대기 (사용자 입력 없이 아무것도 하지 않음)

**전환:**
- [🎤 녹음 시작] 클릭 → RECORDING
- [❌ 종료] 클릭 → ENDING

---

### RECORDING

**진입 조건:** LISTENING에서 [🎤 녹음 시작] 클릭

**동작:**
- `sounddevice.InputStream` 시작, numpy 배열로 오디오 청크 누적
- 버튼 텍스트 [🎤 녹음 시작] → [■ 답변 완료]로 변경
- 상태 레이블: "🔴 녹음 중... (0:08)" — 경과 시간 1초마다 갱신 (QTimer)
- 오디오 청크를 메모리에 누적 (파일 저장은 완료 시, 다만 너무 길어질 경우 별도로 chunk 단위를 저장할 방법도 생각해 보아야 함.)
  - 만약 너무 길어질 경우 자동 종료 (Config에서 설정 가능)

**전환:**
- [■ 답변 완료] 클릭:
  1. `sounddevice.InputStream` 종료
  2. 누적 배열 → WAV 파일 저장 (임시 경로)
  3. 버튼 비활성화
  4. → PROCESSING
- [❌ 종료] 클릭:
  1. `sounddevice.InputStream` 즉시 종료 (현재 턴 버림)
  2. → ENDING

---

### PROCESSING

**진입 조건:** RECORDING에서 [■ 답변 완료] 클릭 후 WAV 저장 완료

**동작 (순서, 모두 QThread로 실행):**
1. `STTWorker` 실행: WAV → 텍스트 변환
   - 완료 시 대화 로그에 지원자 발화 즉시 표시
   - 세션 turns에 추가 → `session.autosave()`
2. `AIWorker` 실행: STT 결과 + 전체 history → AI 응답 생성
   - api 모드: `chat.send_message(text)` (history 자동 누적)
   - cli 모드: `build_turn_prompt(history, text)` → subprocess 호출
   - 완료 시 대화 로그에 면접관 응답 즉시 표시
   - 세션 turns에 추가 → `session.autosave()`
3. 임시 WAV 파일 삭제
- 상태 레이블: "⚙ 처리 중..."
- 버튼 전체 비활성

**전환:**
- AIWorker 응답 수신 완료 → SPEAKING
- 오류 발생 (STT 실패, AI 실패) → 오류 다이얼로그 표시 후 LISTENING (재시도 가능)
- [❌ 종료] 클릭: 워커에 quit 시그널 → 응답 대기 없이 즉시 → ENDING

---

### ENDING

**진입 조건:** 어느 상태에서든 [❌ 종료] 클릭 또는 창 닫기 (`closeEvent`)

**동작 (순서 엄수):**
1. 실행 중인 모든 QThread에 `quit()` + `wait()` (블로킹 대기)
2. `pygame.mixer.stop()` (TTS 재생 중단)
3. `sounddevice` 스트림 열려 있으면 종료
4. `session["elapsed_seconds"]` 업데이트 후 `session.autosave()` (마지막 상태 저장)
   - status 구분 없음 (모든 세션은 이어하기 가능)
6. 임시 파일 정리 (WAV 등)
7. UI → IDLE 화면으로 전환 (`closeEvent`면 `event.accept()`)

**주의:** RECORDING 또는 PROCESSING 중 종료 시, 현재 미완료 턴의 데이터는 저장하지 않음. 직전 `autosave()` 시점까지만 보존.

---

## 구현 단계

### Phase 1 — 프로젝트 기반

**`requirements.txt`**
```
PyQt6
faster-whisper
edge-tts
sounddevice
scipy
google-generativeai
pygame
nuitka
```

**`app/states.py`**
```python
from enum import Enum, auto

class AppState(Enum):
    IDLE         = auto()
    CONFIG_PANEL = auto()
    INITIALIZING = auto()
    SPEAKING     = auto()
    LISTENING    = auto()
    RECORDING    = auto()
    PROCESSING   = auto()
    ENDING       = auto()
```

**`app/config.py`**
```python
# Nuitka --onefile: sys.argv[0] = 실제 .exe 경로 (임시 추출 경로 아님)
# 개발 중:         sys.argv[0] = main.py 경로
BASE_DIR = Path(sys.argv[0]).parent

CONFIG_PATH  = BASE_DIR / "config.json"
SESSIONS_DIR = BASE_DIR / "sessions"
MODELS_DIR   = BASE_DIR / "models"
LOG_DIR      = BASE_DIR / "Log"

DEFAULT_CONFIG = {
    # AI 연결
    "provider": "gemini",        # "gemini" | "openai" | "anthropic" | "ollama" | "cli"
    "model": "gemini-2.0-flash",
    "api_key": "",
    "cli_cmd": "claude",
    # 면접 설정
    "system_prompt": "",
    "resume_paths": [],          # list[str] — 다중 파일
    # 음성 설정
    "whisper_model": "base",
    "max_record_seconds": 120,   # RECORDING 자동 종료 시간 (0 = 무제한)
    # AI 응답 설정
    "max_tokens": 4096,          # Anthropic 전용 (다른 provider는 무시)
    # 필수 Flag
    "flag_ai_verified": False,
    # flag_prompt_ready는 저장 없이 is_prompt_ready(cfg) 런타임 체크로 대체
    "presets": {},               # {name: {"system_prompt": str, "resume_paths": list}}
}

def load() -> dict:   # 없으면 DEFAULT 반환, 새 키 누락 방지 위해 merge
def save(cfg: dict):  # BASE_DIR 하위 폴더 없으면 자동 생성
```

---

### Phase 2 — Core 로직

**`app/core/voice.py`**

| 함수 | 역할 |
|------|------|
| `record_audio() -> np.ndarray` | sounddevice로 마이크 캡처, 무음 감지 없이 버튼으로 시작/종료 |
| `save_wav(data, path)` | numpy 배열 → WAV 파일 |
| `transcribe(wav_path, model) -> str` | faster-whisper STT |
| `speak(text)` | edge-tts → 임시 mp3 → pygame 재생 |
| `ensure_model(model_name, progress_cb)` | 첫 실행 시 Whisper 모델 다운로드 |

**`app/core/agent.py`**

```python
def ask(user_text: str, history: list[dict], cfg: dict) -> str:
    if cfg["mode"] == "api":
        return _ask_api(user_text, history, cfg)
    else:
        return _ask_cli(user_text, history, cfg)

# API 모드: google.generativeai.GenerativeModel.start_chat() 세션 유지
# CLI 모드: subprocess.run([cli_cmd, "-p", prompt]) — history를 프롬프트에 직접 포함
```

**`app/core/prompt_manager.py`**

```python
def build_system_prompt(cfg: dict) -> str:
    # 1. cfg["system_prompt"] 있으면 사용
    # 2. 없으면 prompts/{company}.txt 로드 (번들 또는 AppData 경로)
    # 3. cfg["resume_path"] 파일 내용을 컨텍스트로 추가

def build_turn_prompt(history: list, user_text: str) -> str:
    # CLI 모드용 — history를 [면접관]/[지원자] 형식으로 직렬화
```

**`app/session.py`**

```python
# 세션 파일 구조
{
    "session_id": "2026-05-25_14-30",
    "started_at": "2026-05-25_14-30",
    "elapsed_seconds": 342,          # 경과 시간 (이어하기 시 복원)
    "snapshot": {
        "system_prompt": "...",      # 세션 시작 시점의 프롬프트 동결
        "resume_paths": [...]        # 세션 시작 시점의 파일 목록 동결
    },
    "turns": [
        {"role": "interviewer", "text": "...", "timestamp": "14:30:12"},
        {"role": "candidate",   "text": "...", "timestamp": "14:31:05"}
    ]
}
# status 필드 없음 — completed/interrupted 구분 제거

def autosave(session: dict): # 매 턴 완료 시 덮어쓰기 → 크래시 복구 가능
def load_latest_session() -> dict | None:  # 가장 최근 세션 반환 (status 필터 없음)
def list_sessions() -> list[dict]:
```

---

### Phase 3 — UI

**`app/ui/workers.py`** — QThread 워커

| 워커 | 입력 | Signal |
|------|------|--------|
| `STTWorker` | wav_path, model | `transcribed(str)`, `error(str)` |
| `AIWorker` | user_text, history, cfg | `response(str)`, `error(str)` |
| `TTSWorker` | text | `started()`, `finished()` |
| `ModelDownloadWorker` | model_name | `progress(int)`, `finished()` |

**`app/ui/main_window.py`** — IDLE 화면

- 이전 미완료 세션 감지 시: [이어하기] + [새 면접 시작하기]
- 이전 세션 없으면: [새 면접 시작하기]만 표시
- 우상단 [⚙] 버튼: config_dialog를 독립 실행 (면접 없이 설정만 변경 가능)
- [새 면접 시작하기] 클릭 → config_dialog 열기

**`app/ui/config_dialog.py`** — 설정 다이얼로그

- 열릴 때 `config.load()` → 각 필드 pre-fill
- AI 모드 라디오 버튼 전환 시 관련 필드 동적 표시/숨김
- CLI 도구 설치 감지: `shutil.which(cli_cmd)` → ✅ / ❌ 표시
- [이 설정 저장]: `config.save()`, 다이얼로그 유지
- [면접 시작]: `config.save()` 후 interview_window로 전환
- [×] 닫기: 저장 없이 닫기

**`app/ui/interview_window.py`** — 면접 화면

- 상단: 경과 시간 타이머, [■ 종료] 버튼
- 중앙: 대화 로그 QTextEdit (읽기 전용, 자동 스크롤)
- 하단: 상태 레이블 + 녹음 버튼
  - SPEAKING: 버튼 비활성
  - LISTENING: [🎤 녹음 시작] 활성
  - RECORDING: [■ 답변 완료] 표시 (클릭 시 STT → AI 파이프라인 시작)
  - PROCESSING: 버튼 비활성
- 대화 로그는 STT 결과 수신 즉시 표시, AI 응답도 수신 즉시 추가

---

### Phase 4 — 강제 종료 처리

```python
# interview_window.py
def closeEvent(self, event):
    if self.state in (RECORDING, SPEAKING, PROCESSING):
        reply = QMessageBox.question("면접을 종료할까요?\n지금까지 내용은 저장됩니다.")
        if reply != QMessageBox.Yes:
            event.ignore()
            return
    self._stop_all_workers()  # 각 QThread에 quit() + wait()
    self.session["status"] = "interrupted"
    session.autosave(self.session)
    audio.release()
    event.accept()
```

- 녹음 중 종료: 녹음 스레드 즉시 중단, 현재 미완료 턴은 저장 안 함
- TTS 중 종료: pygame.mixer.stop()
- PROCESSING 중 종료: 워커 스레드에 quit 시그널

---

### Phase 5 — Nuitka 빌드

**`build.py`**

```python
import subprocess, sys

cmd = [
    sys.executable, "-m", "nuitka",
    "--onefile",
    "--mingw64",                      # MSVC heap 오류 방지
    "--assume-yes-for-downloads",     # 자동 승인
    "--windows-console-mode=disable",
    "--windows-icon-from-ico=assets/icon.ico",
    "--plugin-enable=pyqt6",
    "--include-data-dir=prompts=prompts",
    "--include-data-dir=assets=assets",
    "--output-filename=AI_Interviewer.exe",
    "--output-dir=dist",
    "main.py",
]
subprocess.run(cmd, check=False)
```

| 항목 | 처리 |
|------|------|
| `prompts/` | exe에 번들 (`--include-data-dir`) |
| `assets/` | exe에 번들 |
| `config.json` | 번들 제외 — 런타임에 `<설치 경로>\`에 생성 |
| `sessions/` | 번들 제외 — 런타임에 `<설치 경로>\sessions\`에 생성 |
| `Log/` | 번들 제외 — 런타임에 `<설치 경로>\Log\`에 생성 |
| Whisper 모델 | 번들 제외 — 첫 실행 시 `<설치 경로>\models\`에 다운로드 |

**`installer.iss`** — Inno Setup

```ini
[Setup]
AppName=AI 모의 면접
; 기본 설치 경로: %LOCALAPPDATA%\Programs\AI_Interviewer (UAC 불필요)
; 사용자가 설치 중 경로 변경 가능
DefaultDirName={localappdata}\Programs\AI_Interviewer
PrivilegesRequired=lowest
OutputBaseFilename=AI_Interviewer_Setup

[Files]
Source: "dist\AI_Interviewer.exe"; DestDir: "{app}"

[Icons]
Name: "{autodesktop}\AI 모의 면접"; Filename: "{app}\AI_Interviewer.exe"
Name: "{autoprograms}\AI 모의 면접"; Filename: "{app}\AI_Interviewer.exe"

[Dirs]
; 설치 시 데이터 폴더 미리 생성
Name: "{app}\sessions"
Name: "{app}\models"
Name: "{app}\Log"
```

---

## 데이터 저장 위치 전체 요약

모든 런타임 데이터는 **설치 경로(`BASE_DIR`) 하위**에 저장된다.
기본 설치 경로: `%LOCALAPPDATA%\Programs\AI_Interviewer\`

| 데이터 | 저장 위치 | 변경 방법 |
|--------|----------|----------|
| API Key, 모드, 모델 | `<설치 경로>\config.json` | 앱 내 설정 UI |
| 시스템 프롬프트 | config.json 내 필드 또는 참조 파일 경로 | 앱 내 텍스트 에디터 |
| 기본 프롬프트 템플릿 | `prompts/*.txt` (exe 번들) | 변경 불가 (배포자 제공) |
| 면접 세션 로그 | `<설치 경로>\sessions\` | 자동 저장 |
| 오류 로그 | `<설치 경로>\Log\` | 자동 저장 |
| Whisper 모델 | `<설치 경로>\models\` | 첫 실행 자동 다운로드 |
| 임시 WAV | `<설치 경로>\` (턴 처리 후 즉시 삭제) | — |

---

## 개발 환경 설정

```powershell
# 최초 1회
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 검증 방법

1. `.venv\Scripts\python.exe -X utf8 main.py` — 개발 중 실행, UI 및 상태 전환 확인
2. API 모드: Gemini API Key 입력 → 면접 진행 → `sessions/` 파일 생성 확인
3. CLI 모드: claude CLI 설치 환경에서 subprocess 호출 확인
4. 강제 종료: 녹음 중 창 닫기 → `sessions/` 파일에 `"status": "interrupted"` 확인
5. `.venv\Scripts\python.exe -X utf8 build.py` → `dist/AI_Interviewer.exe` 실행
6. Python 미설치 환경에 exe 복사 후 실행 확인
