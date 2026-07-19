# TODO

## 버그 / 검증 필요

- [x] **Gemini SDK 타입 런타임 검증**
  Gemini API 면접 시작 및 이어하기 실사용 중 오류 없음. 검증 완료로 간주.

- [x] **세션 이어하기 전 provider 테스트**
  Gemini API → Gemini CLI 전환 이어하기 확인 완료. Anthropic 면접 시작 → Gemini CLI 이어하기 확인 완료.

- [x] **Anthropic `max_tokens` config 키로 관리**
  DEFAULT_CONFIG에 `max_tokens: 4096` 추가. `_ask_anthropic()`에서 `cfg.get("max_tokens", 4096)` 사용.

---

## 기능 추가

- [x] **세션 목록 / 관리 UI**
  메인 화면 "📋 세션 목록" 버튼. 날짜·턴 수·경과 시간 테이블, 대화 미리보기, 삭제, 이어하기.
  (`SessionListDialog` 신규 파일. 모든 세션 이어하기 가능.)

- [x] **세션 상태(status) 구분 제거**
  completed/interrupted 구분이 불필요하다고 판단. `status` 필드 삭제. 세션 목록은 전체를 이어하기 대상으로 표시.

- [x] **flag_prompt_ready 런타임 판단으로 전환**
  `is_prompt_ready(cfg)` 함수 추가. 시스템 프롬프트 직접 입력 또는 `prompts/default.txt` 파일 존재 시 True.
  기본 프롬프트 파일만 있어도 면접 시작 가능.

- [x] **메인 화면 이어하기 버튼 제거**
  세션 목록 다이얼로그가 이어하기 기능을 더 넓게 대체. IDLE 화면은 "새 면접 시작하기" + "📋 세션 목록"으로 단순화.

- [x] **녹음 최대 시간 설정 UI + STT 모델 선택 UI**
  ConfigDialog에 Whisper 모델 드롭다운(tiny/base/small/medium/large-v3) 및 최대 녹음 시간 스핀박스 추가.
  모델 저장 시 미설치 여부 확인 → 다운로드 제안.

- [x] **이어하기 타이머 복원**
  session.json에 `elapsed_seconds` 저장. 이어하기 시 이전 경과 시간 복원.

- [x] **"다른 주제로" 버튼**
  LISTENING 상태에서 활성화. 클릭 시 주제 전환 요청을 AI에 전송 (세션 히스토리 비기록).

---

## 빌드 / 배포

- [x] **Nuitka 빌드 성공**
  `--clang` (Python 3.13 + MSVC heap 오류 대응), `--assume-yes-for-downloads` 추가.
  PNG를 .ico로 재변환(Pillow) 후 빌드 완료. `dist/AI_Interviewer.exe` 생성 확인.

- [ ] **exe 단독 동작 검증**
  Python 미설치 환경(또는 별도 폴더)에서 exe 실행 후 면접 전 과정 확인.

- [ ] **`installer.iss` 작성 (Inno Setup)**
  바탕화면·시작 메뉴 바로가기, 제거 지원.
