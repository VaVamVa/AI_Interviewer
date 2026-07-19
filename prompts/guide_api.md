# API Key 발급 방법

API Key를 발급받으면 설정 화면의 [AI 연결 설정] → Provider 선택 → API Key 입력 → [연결 확인]으로 등록합니다.

---

## Gemini (추천 — 과금량 적음)
(실행 test 확인됨)

Google AI Studio에서 발급하며, 결제 수단을 등록하여 Tier 1을 이용해야 외부 앱을 이용 가능합니다.

1. **https://aistudio.google.com** 접속
2. Google 계정으로 로그인
3. 좌측 메뉴 또는 우상단 **[Get API key]** 클릭
4. **[Create API key]** → 프로젝트 선택 또는 새 프로젝트 생성
5. 결제 수단 연결
   - (선택사항) 종량제 한도 설정
6. 생성된 키를 복사하여 앱에 입력


---

## OpenAI

1. **https://platform.openai.com** 접속 → 로그인 또는 회원가입
2. 우상단 프로필 아이콘 → **[API keys]**
3. **[+ Create new secret key]** 클릭
4. 키 이름 입력 후 생성 → 복사 (이후 재확인 불가)
5. 앱에 입력

> 신규 계정에 소액 무료 크레딧이 제공될 수 있으나, 기본적으로 유료입니다. 결제 수단 등록 필요.

---

## Anthropic (Claude)
(실행 test 확인됨)

1. **https://console.anthropic.com** 접속 → 로그인 또는 회원가입
2. 좌측 메뉴 **[API Keys]**
3. **[Create Key]** 클릭 → 키 이름 입력 후 생성
4. 생성된 키 복사 (이후 재확인 불가)
5. **(!중요)** Claude Console 사이트에서 크레딧 충전 (Claude Code에서 충전한 크레딧과는 호환 불가)
6. 복사한 키를 앱에 입력

> 유료 서비스입니다. 결제 수단 등록 및 크레딧 충전 후 사용 가능합니다.

---

## Ollama (로컬 — API Key 불필요)

Ollama는 인터넷 연결 없이 내 PC에서 AI 모델을 실행하는 방식입니다. API Key가 필요 없습니다.

1. **https://ollama.com** 접속 → **[Download]**
2. Windows 설치 파일 실행
3. 설치 완료 후 터미널에서 모델 다운로드:
   ```
   ollama pull llama3.2
   ```
4. 앱 설정에서 Provider를 **Ollama**로 선택하면 자동으로 설치된 모델 목록을 불러옵니다.

> 모델 크기에 따라 수 GB의 저장 공간이 필요합니다. llama3.2 기준 약 2GB.
