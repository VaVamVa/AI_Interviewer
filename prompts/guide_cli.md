# CLI 도구 설치 방법

CLI 모드는 별도 AI 구독(Claude Pro, Gemini Advanced 등)이 있을 때 API Key 없이 사용하는 방식입니다.
설치 후 앱 설정에서 Provider를 **CLI**로 선택하고 명령어를 입력하세요.

> **주의**: CLI 모드는 매 요청마다 대화 히스토리 전체를 전송하므로, API 모드에 비해 응답이 느리고 평소보다 많은 Token을 소모합니다.

---

## Claude CLI (명령어: `claude`)

Anthropic Claude 구독(Pro 이상)이 필요합니다.

### 설치 방법

**방법 1 — 공식 설치 파일 (권장)**

1. **https://claude.ai/download** 접속
2. **Claude Code** 다운로드 → 설치 실행
3. 설치 완료 후 터미널에서 로그인:
   ```
   claude
   ```
4. 브라우저가 열리면 Anthropic 계정으로 인증

**방법 2 — npm**

Node.js(v18 이상)가 설치된 경우:
```
npm install -g @anthropic-ai/claude-code
```

### 설치 확인
```
claude --version
```

---

## Antigravity CLI (명령어: `agy`)

Google Antigravity 계정이 필요합니다.

### 실행 및 인증

터미널에서 `agy`를 실행하여 최초 인증을 진행합니다:

```
agy
```
화면의 안내에 따라 인증을 완료합니다.

### 설치 확인
```
agy --version
```

---

## 앱에서 CLI 설정하기

1. 앱 우상단 **[⚙ 설정]** 클릭
2. **Provider** → **CLI** 선택
3. **CLI 명령어** 입력란에 사용할 명령어 입력 (예: `agy` 또는 `claude`)
4. 설치 감지 상태가 ✅로 표시되면 **[연결 확인]** 클릭
