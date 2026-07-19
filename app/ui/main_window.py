"""메인 화면 — IDLE 상태."""

import os
from pathlib import Path

from PyQt6.QtCore    import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox,
)

import app.config as config
from app.ui.config_dialog       import ConfigDialog
from app.ui.interview_window    import InterviewWindow
from app.ui.session_list_dialog import SessionListDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI 모의 면접")
        self.setMinimumSize(480, 400)

        self._cfg                          = config.load()
        self._guide_visible                = False
        self._interview_win: InterviewWindow | None = None
        self._resume_target: dict | None   = None  # 세션 목록에서 선택된 세션

        central = QWidget()
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setSpacing(14)
        self._root.setContentsMargins(24, 24, 24, 16)

        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # 상단 — 타이틀 + 설정 버튼
        top = QHBoxLayout()
        title = QLabel("AI 모의 면접")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        self._settings_btn = QPushButton("⚙ 설정")
        self._settings_btn.setFixedWidth(80)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self._settings_btn)
        self._root.addLayout(top)

        # Flag 상태 표시
        self._flag_label = QLabel()
        self._flag_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._flag_label.setStyleSheet("font-size: 13px; color: #555; padding: 4px;")
        self._root.addWidget(self._flag_label)

        # 버튼 영역
        btn_lay = QVBoxLayout()
        btn_lay.setSpacing(8)
        self._start_btn    = QPushButton("새 면접 시작하기")
        self._start_btn.setFixedHeight(42)
        self._start_btn.setStyleSheet("font-size: 15px;")
        self._sessions_btn = QPushButton("📋 세션 목록")
        self._sessions_btn.setFixedHeight(36)
        self._sessions_btn.setStyleSheet("font-size: 12px; color: #444;")
        btn_lay.addWidget(self._start_btn)
        btn_lay.addWidget(self._sessions_btn)
        self._root.addLayout(btn_lay)

        self._root.addStretch()

        # 하단 — 안내 토글
        self._guide_toggle_btn = QPushButton("📖 시작하기 전에 ▼")
        self._guide_toggle_btn.setFlat(True)
        self._guide_toggle_btn.setStyleSheet("font-size: 12px; color: #666;")

        self._open_guide_btn = QPushButton("📂 Guide 문서 확인하기")
        self._open_guide_btn.setStyleSheet("font-size: 12px;")
        self._open_guide_btn.hide()

        self._root.addWidget(self._guide_toggle_btn)
        self._root.addWidget(self._open_guide_btn)

        # 시그널
        self._settings_btn.clicked.connect(self._open_settings)
        self._start_btn.clicked.connect(self._on_start)
        self._sessions_btn.clicked.connect(self._open_session_list)
        self._guide_toggle_btn.clicked.connect(self._toggle_guide)
        self._open_guide_btn.clicked.connect(self._open_guide_folder)

        self._refresh_ui()

    # ── UI 갱신 ──────────────────────────────────────────────────────────

    def _refresh_ui(self) -> None:
        self._cfg = config.load()

        ai = "✅ AI 연결됨"    if self._cfg.get("flag_ai_verified") else "❌ AI 미연결"
        pr = "✅ 프롬프트 준비됨" if config.is_prompt_ready(self._cfg) else "❌ 프롬프트 없음"
        self._flag_label.setText(f"{ai}     {pr}")

        if not config.all_flags_ready(self._cfg) and self._guide_visible:
            self._toggle_guide()

    # ── 이벤트 핸들러 ────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        dlg = ConfigDialog(self)
        dlg.exec()
        self._refresh_ui()

    def _open_session_list(self) -> None:
        dlg = SessionListDialog(self)
        dlg.exec()
        if dlg.resume_session:
            self._resume_target = dlg.resume_session
            self._on_resume()
        else:
            self._refresh_ui()

    def _on_start(self) -> None:
        self._cfg = config.load()
        missing   = config.all_flags_ready(self._cfg)
        if missing:
            labels = {
                "flag_ai_verified":  "AI 연결 확인",
                "flag_prompt_ready": "시스템 프롬프트",
            }
            names = "  /  ".join(labels[k] for k in missing)
            QMessageBox.warning(
                self, "설정 미완료",
                f"다음 항목을 먼저 설정해 주세요:\n\n{names}\n\n[⚙ 설정] 버튼을 눌러 설정을 완료하세요.",
            )
            return
        self._launch_interview(resume_session=None)

    def _on_resume(self) -> None:
        s            = self._resume_target
        resume_paths = s.get("snapshot", {}).get("resume_paths", [])
        missing      = [p for p in resume_paths if not Path(p).exists()]
        if missing:
            names = "\n".join(f"  • {Path(p).name}" for p in missing)
            reply = QMessageBox.warning(
                self, "파일 없음",
                f"이전 세션에 사용된 파일을 찾을 수 없습니다:\n\n{names}\n\n"
                "해당 파일 없이 이어하기를 진행할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._launch_interview(resume_session=s)

    def _launch_interview(self, resume_session: dict | None) -> None:
        self._interview_win = InterviewWindow(self._cfg, resume_session)
        self._interview_win.interview_closed.connect(self._on_interview_closed)
        self.hide()
        self._interview_win.show()

    def _on_interview_closed(self) -> None:
        self._interview_win = None
        self._refresh_ui()
        self.show()

    def _toggle_guide(self) -> None:
        self._guide_visible = not self._guide_visible
        self._open_guide_btn.setVisible(self._guide_visible)
        arrow = "▲" if self._guide_visible else "▼"
        self._guide_toggle_btn.setText(f"📖 시작하기 전에 {arrow}")

    def _open_guide_folder(self) -> None:
        prompts_dir = config.BASE_DIR / "prompts"
        if prompts_dir.exists():
            os.startfile(str(prompts_dir))
        else:
            QMessageBox.information(
                self, "폴더 없음",
                f"Guide 폴더를 찾을 수 없습니다.\n\n{prompts_dir}",
            )
