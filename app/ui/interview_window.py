"""면접 진행 화면 — SPEAKING / LISTENING / RECORDING / PROCESSING / ENDING."""

from pathlib import Path

from PyQt6.QtCore    import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QMessageBox, QInputDialog,
)

import app.config  as config
import app.session as session
from app.states import AppState

_NEXT_TOPIC_MSG = "이 주제는 충분히 다루었습니다. 다음 새로운 질문으로 넘어가 주세요."
_NEXT_TOPIC_KEYWORD_MSG = (
    "이 주제는 충분히 다루었습니다. "
    "다음은 '{keyword}' 관련 주제로 새로운 질문을 해주세요."
)

_RESUME_CONTEXT_MSG = (
    "This is a session resume operation. "
    "You have been provided with the previous conversation history above. "
    "Review the context and your role, then respond briefly to confirm you are ready. "
    "Do not ask any new questions until the next instruction."
)
from app.core.voice   import AudioRecorder, stop_speaking
from app.core.agent   import init_session
from app.core.prompt_manager import build_system_prompt
from app.ui.workers   import STTWorker, AIWorker, TTSWorker


class InterviewWindow(QWidget):
    interview_closed = pyqtSignal()

    def __init__(self, cfg: dict, resume_session: dict | None = None) -> None:
        super().__init__()
        self.setWindowTitle("AI 모의 면접 — 진행 중")
        self.setMinimumSize(700, 520)

        self._state           = AppState.INITIALIZING
        self._recorder        = AudioRecorder()
        self._wav_path: Path | None = None
        self._elapsed         = 0   # 녹음 경과 초
        self._workers: list   = []  # 실행 중인 QThread 참조
        self._first_question: str | None = None  # 시작 전 AI 첫 질문 임시 저장

        # 세션 초기화 — 재개 시 snapshot의 system_prompt/resume_paths를 사용,
        # provider/model/api_key 등 연결 설정은 현재 cfg 유지
        if resume_session:
            snapshot = resume_session.get("snapshot", {})
            self._cfg = {
                **cfg,
                "system_prompt": snapshot.get("system_prompt", cfg.get("system_prompt", "")),
                "resume_paths":  snapshot.get("resume_paths",  cfg.get("resume_paths", [])),
            }
            self._session = resume_session
            self._history = list(resume_session.get("turns", []))
        else:
            self._cfg = cfg
            self._session = session.new_session(cfg)
            self._history = []

        self._system_prompt = build_system_prompt(self._cfg)

        self._build_ui()
        if resume_session:
            self._interview_secs = resume_session.get("elapsed_seconds", 0)
        self._start_interview()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 상단 — 타이머 + 종료 버튼
        top = QHBoxLayout()
        self._timer_label = QLabel("00:00:00")
        self._timer_label.setStyleSheet("font-size: 14px;")
        self._end_btn = QPushButton("❌ 종료")
        self._end_btn.setFixedWidth(90)
        top.addWidget(self._timer_label)
        top.addStretch()
        top.addWidget(self._end_btn)
        root.addLayout(top)

        # 중앙 — 대화 로그 + 접기/펼치기
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("대화 로그"))
        self._toggle_log_btn = QPushButton("펼치기")
        self._toggle_log_btn.setFixedWidth(60)
        log_header.addStretch()
        log_header.addWidget(self._toggle_log_btn)
        root.addLayout(log_header)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.hide()
        root.addWidget(self._log_edit)

        # 하단 — 상태 레이블 + 녹음 버튼
        self._status_label = QLabel("준비 중...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("font-size: 14px; padding: 6px;")
        root.addWidget(self._status_label)

        # "▶ 면접 시작" 버튼 — 첫 질문 준비 완료 시에만 표시
        self._ready_btn = QPushButton("▶ 면접 시작")
        self._ready_btn.setFixedHeight(44)
        self._ready_btn.setStyleSheet("font-size: 15px; font-weight: bold;")
        self._ready_btn.hide()
        root.addWidget(self._ready_btn)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._record_btn = QPushButton("🎤 녹음 시작")
        self._record_btn.setFixedHeight(44)
        self._record_btn.setEnabled(False)
        self._topic_btn = QPushButton("🔄 다른 주제로")
        self._topic_btn.setFixedHeight(44)
        self._topic_btn.setEnabled(False)
        btn_row.addWidget(self._record_btn)
        btn_row.addWidget(self._topic_btn)
        root.addLayout(btn_row)

        # 타이머
        self._interview_timer = QTimer()
        self._interview_timer.timeout.connect(self._tick_interview)
        self._interview_secs  = 0
        self._interview_timer.start(1000)

        self._record_timer = QTimer()
        self._record_timer.timeout.connect(self._tick_record)

        # 시그널
        self._end_btn.clicked.connect(self._on_end)
        self._ready_btn.clicked.connect(self._on_ready_start)
        self._record_btn.clicked.connect(self._on_record_btn)
        self._topic_btn.clicked.connect(self._on_topic_btn)
        self._toggle_log_btn.clicked.connect(self._toggle_log)

    # ── 면접 시작 ────────────────────────────────────────────────────────

    def _start_interview(self) -> None:
        init_session(self._system_prompt, self._cfg, self._history or None)
        self._set_state(AppState.INITIALIZING)

        if self._history:
            # 이어하기: 히스토리 로그 복원 후 AI에 컨텍스트 로드 요청
            for turn in self._history:
                self._append_log(turn["role"], turn["text"])
            self._status_label.setText("🔄 면접 준비 중... 이전 내용을 불러오고 있습니다")
            worker = AIWorker(_RESUME_CONTEXT_MSG, self._history, self._system_prompt, self._cfg)
            worker.response.connect(self._on_context_loaded)
            worker.error.connect(self._on_error)
            self._run_worker(worker)
            return

        # 새 면접: 첫 질문 생성 — 준비되면 _on_first_question에서 버튼 표시
        worker = AIWorker("면접을 시작해주세요.", [], self._system_prompt, self._cfg)
        worker.response.connect(self._on_first_question)
        worker.error.connect(self._on_error)
        self._run_worker(worker)

    # ── 상태 전환 ────────────────────────────────────────────────────────

    def _set_state(self, state: AppState) -> None:
        self._state = state
        is_listening  = state == AppState.LISTENING
        is_recording  = state == AppState.RECORDING
        is_busy       = state in (AppState.SPEAKING, AppState.PROCESSING, AppState.INITIALIZING)

        self._record_btn.setEnabled(is_listening or is_recording)
        self._topic_btn.setEnabled(is_listening)
        if state == AppState.INITIALIZING:
            self._status_label.setText("🔄 AI에 연결 중... 잠시만 기다려 주세요")
        elif is_listening:
            self._record_btn.setText("🎤 녹음 시작")
            self._status_label.setText("⏳ 답변을 말씀해 주세요")
        elif is_recording:
            self._record_btn.setText("■ 답변 완료")
            self._status_label.setText("🔴 녹음 중... (0:00)")
        elif state == AppState.SPEAKING:
            self._status_label.setText("🔊 면접관 답변 중...")
        elif state == AppState.PROCESSING:
            self._status_label.setText("⚙ 처리 중...")

    # ── 워커 실행 ────────────────────────────────────────────────────────

    def _run_worker(self, worker) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        worker.start()

    def _stop_all_workers(self) -> None:
        for w in list(self._workers):
            w.quit()
            w.wait(3000)
        self._workers.clear()

    # ── 이벤트 핸들러 ────────────────────────────────────────────────────

    def _on_first_question(self, text: str) -> None:
        """첫 질문 준비 완료 — 사용자가 버튼을 눌러 면접을 시작하도록 대기."""
        self._first_question = text
        self._status_label.setText("✅ 준비 완료 — 버튼을 눌러 면접을 시작하세요")
        self._ready_btn.setText("▶ 면접 시작")
        self._ready_btn.show()

    def _on_context_loaded(self, _: str) -> None:
        """이어하기 — AI 컨텍스트 로드 완료. 면접 재개 버튼 표시."""
        self._status_label.setText("✅ 준비 완료 — 버튼을 눌러 면접을 재개하세요")
        self._ready_btn.setText("▶ 면접 재개")
        self._ready_btn.clicked.disconnect(self._on_ready_start)
        self._ready_btn.clicked.connect(self._on_resume_start)
        self._ready_btn.show()

    def _on_resume_start(self) -> None:
        """▶ 면접 재개 버튼 클릭 — 마지막 턴 기준으로 상태 결정."""
        self._ready_btn.hide()
        self._ready_btn.clicked.disconnect(self._on_resume_start)
        self._ready_btn.clicked.connect(self._on_ready_start)

        last_role = self._history[-1]["role"] if self._history else "interviewer"

        if last_role == "interviewer":
            # 면접관이 마지막으로 발화 → 지원자가 답변할 차례
            self._set_state(AppState.LISTENING)
        else:
            # 지원자가 마지막으로 발화 → AI가 다음 질문을 해야 함
            self._set_state(AppState.PROCESSING)
            last_candidate_text = self._history[-1]["text"]
            worker = AIWorker(
                last_candidate_text, self._history[:-1],
                self._system_prompt, self._cfg,
            )
            worker.response.connect(self._on_ai_response)
            worker.error.connect(self._on_error)
            self._run_worker(worker)

    def _on_ready_start(self) -> None:
        """▶ 면접 시작 버튼 클릭 — 첫 질문 TTS 재생 후 LISTENING으로."""
        text = self._first_question
        self._first_question = None
        self._ready_btn.hide()

        self._append_log("interviewer", text)
        session.add_turn(self._session, "interviewer", text)
        self._session["elapsed_seconds"] = self._interview_secs
        session.autosave(self._session)
        self._history.append({"role": "interviewer", "text": text})

        self._set_state(AppState.SPEAKING)
        worker = TTSWorker(text)
        worker.finished_tts.connect(lambda: self._set_state(AppState.LISTENING))
        worker.error.connect(lambda _: self._set_state(AppState.LISTENING))
        self._run_worker(worker)

    def _on_record_btn(self) -> None:
        if self._state == AppState.LISTENING:
            self._recorder.start()
            self._elapsed = 0
            self._record_timer.start(1000)
            self._set_state(AppState.RECORDING)

        elif self._state == AppState.RECORDING:
            self._record_timer.stop()
            self._wav_path = self._recorder.stop()
            self._set_state(AppState.PROCESSING)
            self._run_stt()

    def _run_stt(self) -> None:
        worker = STTWorker(self._wav_path, self._cfg.get("whisper_model", "base"))
        worker.transcribed.connect(self._on_stt_done)
        worker.error.connect(self._on_stt_error)
        self._run_worker(worker)

    def _on_stt_done(self, text: str) -> None:
        self._append_log("candidate", text)
        session.add_turn(self._session, "candidate", text)
        self._session["elapsed_seconds"] = self._interview_secs
        session.autosave(self._session)
        self._history.append({"role": "candidate", "text": text})

        if self._wav_path:
            self._wav_path.unlink(missing_ok=True)
            self._wav_path = None

        worker = AIWorker(text, self._history[:-1], self._system_prompt, self._cfg)
        worker.response.connect(self._on_ai_response)
        worker.error.connect(self._on_error)
        self._run_worker(worker)

    def _on_stt_error(self, msg: str) -> None:
        self._append_log("system", f"[STT 오류] {msg} — 다시 시도해 주세요.")
        self._set_state(AppState.LISTENING)

    def _on_ai_response(self, text: str) -> None:
        self._append_log("interviewer", text)
        session.add_turn(self._session, "interviewer", text)
        self._session["elapsed_seconds"] = self._interview_secs
        session.autosave(self._session)
        self._history.append({"role": "interviewer", "text": text})

        self._set_state(AppState.SPEAKING)
        worker = TTSWorker(text)
        worker.finished_tts.connect(lambda: self._set_state(AppState.LISTENING))
        worker.error.connect(lambda msg: self._set_state(AppState.LISTENING))
        self._run_worker(worker)

    def _on_topic_btn(self) -> None:
        """🔄 다른 주제로 — 키워드 입력 후 주제 전환 요청. 세션 히스토리에는 기록하지 않음."""
        keyword, ok = QInputDialog.getText(
            self,
            "다른 주제로",
            "원하는 방향의 키워드를 입력하세요.\n비워두면 AI가 자동으로 다른 주제를 선택합니다.",
        )
        if not ok:
            return

        msg = (
            _NEXT_TOPIC_KEYWORD_MSG.format(keyword=keyword.strip())
            if keyword.strip()
            else _NEXT_TOPIC_MSG
        )

        self._set_state(AppState.PROCESSING)
        worker = AIWorker(msg, self._history, self._system_prompt, self._cfg)
        worker.response.connect(self._on_ai_response)
        worker.error.connect(self._on_error)
        self._run_worker(worker)

    def _on_error(self, msg: str) -> None:
        QMessageBox.warning(self, "오류", msg)

        # INITIALIZING 단계(첫 질문 생성)에서 실패하면 LISTENING으로 전환하지 않음.
        # 질문이 없는 상태에서 녹음 버튼이 활성화되면 계속 에러가 반복되기 때문.
        if self._state == AppState.INITIALIZING:
            self._status_label.setText(
                "⚠ AI 연결에 실패했습니다. 재시도하거나 종료 후 설정을 확인하세요."
            )
            self._ready_btn.setText("🔄 재시도")
            try:
                self._ready_btn.clicked.disconnect()
            except TypeError:
                pass
            self._ready_btn.clicked.connect(self._on_retry_start)
            self._ready_btn.show()
            return

        self._set_state(AppState.LISTENING)

    def _on_retry_start(self) -> None:
        """초기화 오류 후 재시도 — 첫 질문을 다시 요청한다."""
        self._ready_btn.hide()
        try:
            self._ready_btn.clicked.disconnect()
        except TypeError:
            pass
        self._ready_btn.clicked.connect(self._on_ready_start)
        self._start_interview()

    def _on_end(self) -> None:
        if self._state in (AppState.SPEAKING, AppState.RECORDING, AppState.PROCESSING):
            reply = QMessageBox.question(
                self, "면접 종료",
                "면접을 종료할까요?\n지금까지 내용은 저장됩니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._end_interview()

    def _toggle_log(self) -> None:
        visible = self._log_edit.isVisible()
        self._log_edit.setVisible(not visible)
        self._toggle_log_btn.setText("펼치기" if visible else "접기")

    # ── 종료 처리 ────────────────────────────────────────────────────────

    def _end_interview(self) -> None:
        self._interview_timer.stop()
        self._record_timer.stop()
        self._stop_all_workers()
        stop_speaking()
        self._recorder.release()

        if self._wav_path:
            self._wav_path.unlink(missing_ok=True)

        self._session["elapsed_seconds"] = self._interview_secs
        session.autosave(self._session)
        self._state = AppState.ENDING   # closeEvent 재진입 방지
        self.close()

    def closeEvent(self, event) -> None:
        if self._state not in (AppState.IDLE, AppState.ENDING):
            self._end_interview()
        self.interview_closed.emit()
        event.accept()

    # ── 타이머 ───────────────────────────────────────────────────────────

    def _tick_interview(self) -> None:
        if self._state in (AppState.SPEAKING, AppState.RECORDING):
            self._interview_secs += 1
        h = self._interview_secs // 3600
        m = (self._interview_secs % 3600) // 60
        s = self._interview_secs % 60
        self._timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _tick_record(self) -> None:
        self._elapsed += 1
        self._status_label.setText(f"🔴 녹음 중... ({self._elapsed // 60:01d}:{self._elapsed % 60:02d})")

        max_sec = self._cfg.get("max_record_seconds", 120)
        if max_sec > 0 and self._elapsed >= max_sec:
            self._on_record_btn()   # 자동 종료

    # ── 로그 출력 ────────────────────────────────────────────────────────

    def _append_log(self, role: str, text: str) -> None:
        prefix = {
            "interviewer": "[면접관]",
            "candidate":   "[지원자]",
            "system":      "[시스템]",
        }.get(role, "[?]")
        self._log_edit.append(f"{prefix} {text}\n")
        self._log_edit.ensureCursorVisible()
