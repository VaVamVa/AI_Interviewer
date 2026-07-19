[Setup]
AppName=AI 모의 면접
AppVersion=1.0.0
AppPublisher=VaVamVa
; UAC 불필요 — 사용자 로컬 경로에 설치
DefaultDirName={localappdata}\Programs\AI_Interviewer
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputBaseFilename=AI_Interviewer_Setup
OutputDir=dist
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\AI_Interviewer.exe
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
; 실행 파일
Source: "dist\AI_Interviewer.exe"; DestDir: "{app}"; Flags: ignoreversion

; 가이드 및 기본 프롬프트 — exe와 같은 위치에 있어야 런타임에 경로를 찾음
Source: "dist\prompts\*"; DestDir: "{app}\prompts"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; 런타임에 자동 생성되지만 설치 시 미리 만들어 둠
Name: "{app}\sessions"
Name: "{app}\models"
Name: "{app}\Log"

[Icons]
Name: "{autodesktop}\AI 모의 면접";  Filename: "{app}\AI_Interviewer.exe"
Name: "{autoprograms}\AI 모의 면접"; Filename: "{app}\AI_Interviewer.exe"

[Run]
Filename: "{app}\AI_Interviewer.exe"; \
  Description: "AI 모의 면접 시작"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; config.json, sessions/, Log/ 는 사용자 데이터이므로 자동 삭제하지 않음
; 설치 폴더 자체는 제거 시 Inno Setup이 등록된 파일만 정리함
