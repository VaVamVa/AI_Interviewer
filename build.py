"""Nuitka 빌드 스크립트.

실행: .venv\Scripts\python.exe build.py
결과: dist\AI_Interviewer.exe  +  dist\prompts\
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# VS 번들 clang-cl 대신 독립 설치 LLVM을 사용하도록 PATH 앞에 삽입
_LLVM_BIN = r"C:\Program Files\LLVM\bin"
if Path(_LLVM_BIN).exists():
    os.environ["PATH"] = _LLVM_BIN + os.pathsep + os.environ.get("PATH", "")

cmd = [
    sys.executable, "-m", "nuitka",
    "--onefile",
    "--clang",                            # MSVC 대신 Clang 사용 (대형 파일 heap 오류 방지, Python 3.13 지원)
    "--assume-yes-for-downloads",         # Dependency Walker 등 자동 승인
    "--windows-console-mode=disable",
    "--windows-icon-from-ico=assets/icon.ico",
    "--plugin-enable=pyqt6",
    # prompts/는 onefile 내부 번들 대신 exe 옆에 복사 (sys.argv[0] 기반 경로 탐색과 일치)
    "--output-filename=AI_Interviewer.exe",
    "--output-dir=dist",
    "main.py",
]

print("빌드 시작... (첫 실행 시 C 컴파일러 다운로드로 5~10분 소요)")
result = subprocess.run(cmd, check=False)
if result.returncode != 0:
    print("\n빌드 실패. 위 오류 메시지를 확인하세요.")
    sys.exit(1)

# prompts/ 를 dist/ 에 복사 — exe와 같은 위치에 있어야 런타임에 경로를 찾음
dist_prompts = Path("dist/prompts")
if dist_prompts.exists():
    shutil.rmtree(dist_prompts)
shutil.copytree("prompts", dist_prompts)
print("프롬프트 복사 완료: dist/prompts/")

print("\n빌드 완료: dist/AI_Interviewer.exe")
print("배포 시 dist/ 폴더 전체를 함께 전달하세요.")
