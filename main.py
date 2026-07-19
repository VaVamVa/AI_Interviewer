# -*- coding: utf-8 -*-
"""진입점 — Windows cp949 환경에서의 UTF-8 강제 설정을 가장 먼저 수행."""

import os
import sys

# Windows 한국어 로케일(cp949) 환경에서 UTF-8 모드 강제
# 다른 모듈 import 전에 실행해야 효과가 있음
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app import logger as _app_logger
_app_logger.setup()

from PyQt6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AI 모의 면접")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
