"""세션 목록 / 관리 다이얼로그."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QTableWidget, QTableWidgetItem,
    QTextEdit, QPushButton, QMessageBox, QHeaderView,
)

import app.session as session
from app.config import SESSIONS_DIR


def _fmt_elapsed(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class SessionListDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("세션 목록")
        self.setMinimumSize(580, 500)
        self.setModal(True)

        self.resume_session: dict | None = None   # 이어하기 선택 시 설정

        self._sessions: list[dict] = []
        self._build_ui()
        self._load_sessions()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # 세션 테이블
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["날짜 / 시간", "턴 수", "경과 시간"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 70)
        self._table.setColumnWidth(2, 90)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table)

        # 대화 미리보기
        root.addWidget(QLabel("대화 미리보기"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(160)
        root.addWidget(self._preview)

        # 버튼 영역
        btn_lay = QHBoxLayout()
        self._resume_btn = QPushButton("▶ 이어하기")
        self._resume_btn.setEnabled(False)
        self._delete_btn = QPushButton("🗑 삭제")
        self._delete_btn.setEnabled(False)
        self._close_btn  = QPushButton("닫기")
        btn_lay.addWidget(self._resume_btn)
        btn_lay.addWidget(self._delete_btn)
        btn_lay.addStretch()
        btn_lay.addWidget(self._close_btn)
        root.addLayout(btn_lay)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._resume_btn.clicked.connect(self._on_resume)
        self._delete_btn.clicked.connect(self._on_delete)
        self._close_btn.clicked.connect(self.close)

    # ── 세션 로드 ─────────────────────────────────────────────────────────

    def _load_sessions(self) -> None:
        self._sessions = session.list_sessions()
        self._table.setRowCount(len(self._sessions))
        for row, s in enumerate(self._sessions):
            sid     = s.get("session_id", "")
            turns   = len(s.get("turns", []))
            elapsed = _fmt_elapsed(s.get("elapsed_seconds", 0))

            self._table.setItem(row, 0, QTableWidgetItem(sid))

            turn_item = QTableWidgetItem(f"{turns} 턴")
            turn_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, turn_item)

            elapsed_item = QTableWidgetItem(elapsed)
            elapsed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, elapsed_item)

    # ── 이벤트 핸들러 ────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        row = self._table.currentRow()
        if row < 0 or not self._table.selectedItems():
            self._preview.clear()
            self._resume_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            return

        s = self._sessions[row]
        self._resume_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)

        # 대화 미리보기 — 최대 20턴
        turns = s.get("turns", [])
        lines = []
        for turn in turns[:20]:
            prefix = "[면접관]" if turn["role"] == "interviewer" else "[지원자]"
            ts     = turn.get("timestamp", "")
            lines.append(f"{prefix} ({ts})\n{turn['text']}")
        if len(turns) > 20:
            lines.append(f"... 이하 {len(turns) - 20}턴 생략")
        self._preview.setPlainText("\n\n".join(lines))

    def _on_resume(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self.resume_session = self._sessions[row]
        self.accept()

    def _on_delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        s   = self._sessions[row]
        sid = s.get("session_id", "")
        reply = QMessageBox.question(
            self, "세션 삭제",
            f"'{sid}' 세션을 삭제할까요?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        (SESSIONS_DIR / f"{sid}.json").unlink(missing_ok=True)
        self._load_sessions()
        self._preview.clear()
        self._resume_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
