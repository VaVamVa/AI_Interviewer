# AI 모의 면접 (AI Interviewer)

마이크에 대고 답하면, AI가 진짜 면접관처럼 다음 질문을 이어갑니다.
Windows에서 설치 파일 하나로 실행되는 **음성 대화형 AI 모의 면접 앱**입니다.

---

## 왜 만들었나

기존 모의 면접 서비스는 대부분 텍스트 기반이라 실전처럼 "말하며" 연습할 환경이 없었습니다.
이 앱은 마이크로 답하고 스피커로 다음 질문을 듣는 흐름으로 실제 면접에 가장 가까운 연습 경험을 제공합니다.

- 텍스트가 아니라 **음성**으로 질문을 듣고 답합니다
- 이미 쓰고 있는 AI 서비스(Gemini/OpenAI/Anthropic/Ollama/CLI) 중 원하는 것을 그대로 씁니다
- Python이 설치되어 있지 않아도 **설치 파일 하나로 바로 실행**됩니다

---

## 핵심 기능

| 기능 | 설명 |
|---|---|
| 🎙️ 음성 대화 | STT(faster-whisper) → AI → TTS(edge-tts) 파이프라인. AI 질문을 듣고 마이크로 답변 |
| 🔀 AI 멀티 프로바이더 | Gemini / OpenAI / Anthropic / Ollama / CLI 5종 중 자유 선택 |
| 📄 이력서 첨부 | PDF·TXT·HTML 등 다중 파일 첨부 — AI가 이력서를 참고해 질문 |
| 💾 세션 자동저장 | 답변마다 자동 저장, 강제 종료돼도 복구, 다른 Provider로 이어하기도 가능 |
| 📦 원클릭 배포 | Python 없이 Setup 파일 하나로 설치·실행 (Nuitka 단일 exe) |

---

## 시작하기

### 1. 설치

1. [Releases](../../releases)에서 `AI_Interviewer_Setup.exe`를 내려받아 실행합니다.
   관리자 권한이 필요 없고, `%LocalAppData%`에 설치됩니다.
2. 앱을 실행하면 바로 메인 화면이 뜹니다 — 첫 실행에 별도 설정 화면을 거치지 않습니다.

### 2. 필수 설정 2가지

메인 화면에서 아래 두 항목이 모두 ✅가 되어야 면접을 시작할 수 있습니다.

**① AI 연결** — 우상단 **[⚙ 설정]** → AI 연결 설정
1. Provider 선택 (아래 [AI Provider 고르기](#ai-provider-고르기) 참고)
2. 모델 선택
3. API Key 입력 (Ollama·CLI는 생략)
4. **[연결 확인]** 클릭

**② 시스템 프롬프트** — 비워두면 범용 면접관 프롬프트가 자동 적용되어 별도 설정 없이도 시작할 수 있습니다.
지원 직군·회사·난이도를 지정하고 싶다면 직접 입력하세요.

```
당신은 AAA 콘솔 게임 개발사의 클라이언트 프로그래머 채용 면접관입니다.
지원자는 C++17, Unreal Engine 5, DirectX 12 경험이 있는 신입 지원자입니다.
렌더링 최적화, 메모리 관리, 멀티스레딩 역량을 중점적으로 평가해주세요.
```

### 3. 면접 시작

**[새 면접 시작하기]** 클릭 → AI가 첫 질문을 음성으로 읽어줍니다 → **[🎤 녹음 시작]**으로 답변 → 답변이 끝나면 **[■ 답변 완료]** → AI가 다음 질문으로 이어갑니다.

> 녹음은 자동으로 끊기지 않습니다. 답변을 마치면 직접 [■ 답변 완료]를 눌러야 합니다 (무음 자동 감지 없음).

---

## AI Provider 고르기

| Provider | 방식 | 비용 | 비고 |
|---|---|---|---|
| **Gemini** | API Key | 무료 티어 존재 (추천) | Google AI Studio에서 발급 |
| **OpenAI** | API Key | 유료 | |
| **Anthropic (Claude)** | API Key | 유료 | Claude Console에서 별도 크레딧 충전 필요 |
| **Ollama** | 로컬 실행 | 완전 무료 | 인터넷 연결 불필요, PC에 수 GB 저장공간 필요 |
| **CLI** (Claude Code / Antigravity CLI) | 구독 계정 재사용 | 구독료만 | API Key 불필요하지만 응답이 느리고 토큰 소모가 큼 |

발급·설치 방법은 앱 안 **[📖 시작하기 전에]** 토글(`prompts/guide_api.md`, `prompts/guide_cli.md`)에 상세히 정리되어 있습니다.

---

## 더 알아두면 좋은 기능

- **다른 주제로** — 답변 후 대기 상태(LISTENING)에서 클릭하면 키워드를 입력해 원하는 방향으로 질문을 유도하거나, 비워두고 AI에게 새 주제를 맡길 수 있습니다. 대화 로그에는 남지 않습니다.
- **세션 이어하기** — **[📋 세션 목록]**에서 지난 면접을 골라 이어할 수 있습니다. 이때 Provider를 바꿔도(Gemini → Claude CLI 등) 맥락은 그대로 유지됩니다.
- **프리셋** — 자주 쓰는 프롬프트 + 이력서 조합을 이름으로 저장해두고 회사별로 빠르게 전환할 수 있습니다.
- **STT 모델 선택** — `tiny`(75MB, 빠름) ~ `large-v3`(3GB, 고정확도) 중 PC 사양에 맞게 선택합니다. GPU 없이 CPU에서도 동작합니다.

---

## 개발자용 — 로컬 실행

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 개발 중 실행 (-X utf8 필수 — Windows 한국어 로케일 인코딩 오류 방지)
.venv\Scripts\python.exe -X utf8 main.py
```

### 배포용 exe 빌드

```powershell
# 1) Nuitka로 단일 exe 빌드 → dist/AI_Interviewer.exe
.venv\Scripts\python.exe -X utf8 build.py

# 2) Inno Setup으로 installer.iss 컴파일 → dist/AI_Interviewer_Setup.exe
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| UI | PyQt6 (QThread 기반 비동기 처리) |
| STT | faster-whisper (CTranslate2, CPU int8 추론) |
| TTS | edge-tts |
| 오디오 | sounddevice |
| AI SDK | google-genai · openai · anthropic · ollama |
| 빌드 | Nuitka `--onefile` |
| 배포 | Inno Setup |

---

## 프로젝트 구조

```
main.py                    # 진입점
app/
  config.py                # 설정 읽기/쓰기
  session.py                # 세션 저장·불러오기
  states.py                 # 상태 머신 정의
  core/
    agent.py                # 5-provider AI 추상화
    voice.py                 # STT + TTS + 오디오 캡처
    prompt_manager.py        # 시스템 프롬프트 조립
  ui/
    main_window.py / interview_window.py / config_dialog.py / session_list_dialog.py / workers.py
prompts/                    # 기본 프롬프트 + 인앱 가이드 문서
```

---

## 제작자

**박원서** ([@VaVamVa](https://github.com/VaVamVa)) — 기획부터 설계·구현·배포까지 1인 개발.
