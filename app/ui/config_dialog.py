"""ConfigDialog — AI 연결 설정 + 면접 설정.

[⚙] 버튼으로만 진입. 면접 시작 흐름과 독립적.
"""

import shutil
import sys
from pathlib import Path

from PyQt6.QtCore    import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QRadioButton, QButtonGroup,
    QPushButton, QTextEdit, QFileDialog, QMessageBox,
    QProgressBar, QSpinBox, QWidget, QStackedWidget, QListWidget, QListWidgetItem,
)

import app.config as config
from app.config import PROVIDER_MODELS
from app.ui.workers import VerifyWorker, OllamaModelListWorker, ModelDownloadWorker

_PROVIDER_LABELS = {
    "gemini":    "Gemini (Google)",
    "openai":    "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "ollama":    "Ollama (로컬)",
    "cli":       "CLI Agent",
}

_PROVIDER_WARNINGS = {
    "gemini":    "⚠️ API 사용량에 따라 추가 비용이 발생할 수 있습니다. 무료 티어 한도를 초과하지 않도록 주의하세요.",
    "openai":    "⚠️ API 사용량에 따라 추가 비용이 발생할 수 있습니다. 무료 티어 한도를 초과하지 않도록 주의하세요.",
    "anthropic": "⚠️ API 사용량에 따라 추가 비용이 발생할 수 있습니다. 무료 티어 한도를 초과하지 않도록 주의하세요.",
    "ollama":    "",
    "cli":       "⚠️ CLI 모드는 구독 계정의 대화 기록을 소모하며, 히스토리 전체를 매 요청마다 전송하므로 응답 속도가 느리고 토큰 사용량이 많을 수 있습니다.",
}


class ConfigDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(560)
        self.setModal(True)

        self._cfg = config.load()
        self._dirty = False        # 미저장 변경사항 여부
        self._verify_worker:   VerifyWorker          | None = None
        self._ollama_worker:   OllamaModelListWorker | None = None
        self._download_worker: ModelDownloadWorker   | None = None

        self._build_ui()
        self._load_values()

    # ── UI 구성 ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        root.addWidget(self._build_ai_section())
        root.addWidget(self._build_interview_section())
        root.addWidget(self._build_flag_summary())
        root.addLayout(self._build_buttons())

    def _build_ai_section(self) -> QGroupBox:
        box = QGroupBox("AI 연결 설정")
        lay = QVBoxLayout(box)

        # Step 1 — Provider
        lay.addWidget(QLabel("Step 1. Provider 선택"))
        self._provider_group = QButtonGroup(self)
        provider_row = QHBoxLayout()
        self._provider_radios: dict[str, QRadioButton] = {}
        for key, label in _PROVIDER_LABELS.items():
            rb = QRadioButton(label)
            self._provider_radios[key] = rb
            self._provider_group.addButton(rb)
            provider_row.addWidget(rb)
        lay.addLayout(provider_row)

        self._warning_label = QLabel()
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #e07000; font-size: 11px;")
        lay.addWidget(self._warning_label)

        # Step 2 — Model / CLI
        self._step2_label = QLabel("Step 2. 모델 선택")
        lay.addWidget(self._step2_label)
        model_row = QHBoxLayout()
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(240)
        self._cli_cmd_edit = QLineEdit()
        self._cli_cmd_edit.setPlaceholderText("CLI 명령어 (예: claude)")
        self._cli_detect_label = QLabel()
        model_row.addWidget(self._model_combo)
        model_row.addWidget(self._cli_cmd_edit)
        model_row.addWidget(self._cli_detect_label)
        model_row.addStretch()
        lay.addLayout(model_row)

        # Step 3 — API Key
        self._key_widget = QWidget()
        key_lay = QVBoxLayout(self._key_widget)
        key_lay.setContentsMargins(0, 0, 0, 0)
        key_lay.addWidget(QLabel("Step 3. API Key"))
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("API Key 입력")
        key_lay.addWidget(self._api_key_edit)
        lay.addWidget(self._key_widget)

        # Step 4 — 연결 확인
        verify_row = QHBoxLayout()
        self._verify_btn   = QPushButton("연결 확인")
        self._verify_label = QLabel()
        self._verify_progress = QProgressBar()
        self._verify_progress.setRange(0, 0)
        self._verify_progress.hide()
        verify_row.addWidget(self._verify_btn)
        verify_row.addWidget(self._verify_progress)
        verify_row.addWidget(self._verify_label)
        verify_row.addStretch()
        lay.addLayout(verify_row)

        # 시그널 연결
        for rb in self._provider_radios.values():
            rb.toggled.connect(self._on_provider_changed)
        self._cli_cmd_edit.textChanged.connect(self._on_cli_cmd_changed)
        self._api_key_edit.textChanged.connect(lambda _: self._mark_dirty())
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        self._verify_btn.clicked.connect(self._on_verify)

        return box

    def _build_interview_section(self) -> QGroupBox:
        box = QGroupBox("면접 설정")
        lay = QVBoxLayout(box)

        # 시스템 프롬프트
        lay.addWidget(QLabel("시스템 프롬프트:"))
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlaceholderText(
            "면접관 역할과 질문 스타일을 입력하세요. 비워두면 기본 프롬프트를 사용합니다."
        )
        self._prompt_edit.setMaximumHeight(120)
        lay.addWidget(self._prompt_edit)

        # 프리셋 불러오기 / 삭제
        load_row = QHBoxLayout()
        load_row.addWidget(QLabel("프리셋:"))
        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(160)
        self._preset_load_btn = QPushButton("불러오기")
        self._preset_del_btn  = QPushButton("삭제")
        load_row.addWidget(self._preset_combo)
        load_row.addWidget(self._preset_load_btn)
        load_row.addWidget(self._preset_del_btn)
        load_row.addStretch()
        lay.addLayout(load_row)

        # 프리셋 저장
        save_row = QHBoxLayout()
        self._preset_name_edit = QLineEdit()
        self._preset_name_edit.setPlaceholderText("프리셋 이름 입력")
        self._preset_save_btn = QPushButton("프리셋 저장")
        self._preset_saved_label = QLabel("✅ 저장됨")
        self._preset_saved_label.setStyleSheet("color: green;")
        self._preset_saved_label.hide()
        save_row.addWidget(self._preset_name_edit)
        save_row.addWidget(self._preset_save_btn)
        save_row.addWidget(self._preset_saved_label)
        lay.addLayout(save_row)

        # 이력서/컨텍스트 파일 목록
        lay.addWidget(QLabel("이력서/컨텍스트 파일 (선택):"))
        resume_row = QHBoxLayout()

        self._resume_list = QListWidget()
        self._resume_list.setFixedHeight(80)
        self._resume_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._resume_list.setToolTip("파일명 위에 마우스를 올리면 전체 경로가 표시됩니다.")

        btn_col = QVBoxLayout()
        self._resume_add_btn = QPushButton("파일 추가")
        self._resume_del_btn = QPushButton("제거")
        btn_col.addWidget(self._resume_add_btn)
        btn_col.addWidget(self._resume_del_btn)
        btn_col.addStretch()

        resume_row.addWidget(self._resume_list)
        resume_row.addLayout(btn_col)
        lay.addLayout(resume_row)

        format_hint = QLabel("지원 형식: pdf, txt, md, html, mhtml")
        format_hint.setStyleSheet("font-size: 11px; color: #888;")
        lay.addWidget(format_hint)

        # STT 설정
        stt_row = QHBoxLayout()
        stt_row.addWidget(QLabel("STT 모델:"))
        self._whisper_combo = QComboBox()
        self._whisper_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self._whisper_combo.setToolTip(
            "tiny: 빠름 (~75 MB)\n"
            "base: 기본 (~145 MB)\n"
            "small: 균형 (~460 MB)\n"
            "medium: 고정확 (~1.5 GB)\n"
            "large-v3: 최고정확 (~3 GB)"
        )
        stt_row.addWidget(self._whisper_combo)
        stt_row.addSpacing(20)
        stt_row.addWidget(QLabel("최대 녹음:"))
        self._max_rec_spin = QSpinBox()
        self._max_rec_spin.setRange(0, 600)
        self._max_rec_spin.setSuffix(" 초")
        self._max_rec_spin.setSpecialValueText("무제한")
        self._max_rec_spin.setFixedWidth(120)
        stt_row.addWidget(self._max_rec_spin)
        stt_row.addStretch()
        lay.addLayout(stt_row)

        # 저장됨 자동 숨김 타이머
        self._preset_saved_timer = QTimer(self)
        self._preset_saved_timer.setSingleShot(True)
        self._preset_saved_timer.timeout.connect(self._preset_saved_label.hide)

        # 시그널 연결
        self._prompt_edit.textChanged.connect(self._on_prompt_changed)
        self._resume_add_btn.clicked.connect(self._browse_resume)
        self._resume_del_btn.clicked.connect(self._on_remove_resume)
        self._preset_load_btn.clicked.connect(self._on_load_preset)
        self._preset_del_btn.clicked.connect(self._on_delete_preset)
        self._preset_save_btn.clicked.connect(self._on_save_preset)

        return box

    def _build_flag_summary(self) -> QLabel:
        self._flag_label = QLabel()
        self._flag_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._flag_label.setStyleSheet("font-size: 13px; padding: 4px;")
        return self._flag_label

    def _build_buttons(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        self._save_done_label = QLabel("✅ 저장됨")
        self._save_done_label.setStyleSheet("color: green;")
        self._save_done_label.hide()
        self._save_done_timer = QTimer(self)
        self._save_done_timer.setSingleShot(True)
        self._save_done_timer.timeout.connect(self._save_done_label.hide)

        self._save_btn  = QPushButton("저장")
        self._close_btn = QPushButton("닫기")
        lay.addWidget(self._save_done_label)
        lay.addStretch()
        lay.addWidget(self._save_btn)
        lay.addWidget(self._close_btn)
        self._save_btn.clicked.connect(self._on_save)
        self._close_btn.clicked.connect(self._on_close)
        return lay

    # ── 값 로드 ──────────────────────────────────────────────────────────

    def _load_values(self) -> None:
        provider = self._cfg.get("provider", "gemini")
        if provider in self._provider_radios:
            self._provider_radios[provider].setChecked(True)
        self._api_key_edit.setText(self._cfg.get("api_key", ""))
        self._cli_cmd_edit.setText(self._cfg.get("cli_cmd", "claude"))
        self._prompt_edit.setPlainText(self._cfg.get("system_prompt", ""))
        self._resume_list.clear()
        for path in self._cfg.get("resume_paths", []):
            self._add_resume_item(path)
        self._whisper_combo.setCurrentText(self._cfg.get("whisper_model", "base"))
        self._max_rec_spin.setValue(self._cfg.get("max_record_seconds", 120))
        self._refresh_preset_combo()
        self._refresh_flag_summary()
        self._dirty = False

    # ── 이벤트 핸들러 ────────────────────────────────────────────────────

    def _on_provider_changed(self) -> None:
        provider = self._current_provider()
        self._warning_label.setText(_PROVIDER_WARNINGS.get(provider, ""))

        is_cli    = provider == "cli"
        is_ollama = provider == "ollama"
        no_key    = is_cli or is_ollama

        self._step2_label.setText(
            "Step 2. CLI 시작 명령어 입력" if is_cli else "Step 2. 모델 선택"
        )
        self._model_combo.setVisible(not is_cli)
        self._cli_cmd_edit.setVisible(is_cli)
        self._cli_detect_label.setVisible(is_cli)
        self._key_widget.setVisible(not no_key)

        if not is_cli:
            self._refresh_model_list(provider)

        config.reset_ai_flag(self._cfg)
        self._refresh_flag_summary()
        self._mark_dirty()

    def _on_model_changed(self, _: str) -> None:
        config.reset_ai_flag(self._cfg)
        self._refresh_flag_summary()
        self._mark_dirty()

    def _on_cli_cmd_changed(self, text: str) -> None:
        cmd = text.strip()
        found = shutil.which(cmd) if cmd else None
        base_name = Path(cmd).stem.lower() if cmd else ""
        known = base_name in {"claude", "gemini", "codex"}

        if not found:
            self._cli_detect_label.setText("❌ 미감지")
            self._cli_detect_label.setStyleSheet("color: red;")
        elif known:
            self._cli_detect_label.setText("✅ 감지됨")
            self._cli_detect_label.setStyleSheet("color: green;")
        else:
            self._cli_detect_label.setText("⚠️ AI CLI 아님  (지원: claude, gemini, codex)")
            self._cli_detect_label.setStyleSheet("color: #e07000;")
        config.reset_ai_flag(self._cfg)
        self._refresh_flag_summary()
        self._mark_dirty()

    def _on_prompt_changed(self) -> None:
        has_prompt = bool(self._prompt_edit.toPlainText().strip())
        bundle_default = Path(sys.argv[0]).resolve().parent / "prompts" / "default.txt"
        self._cfg["flag_prompt_ready"] = has_prompt or bundle_default.exists()
        self._refresh_flag_summary()
        self._mark_dirty()

    def _on_verify(self) -> None:
        self._collect_to_cfg()
        self._verify_btn.setEnabled(False)
        self._verify_label.setText("확인 중...")
        self._verify_progress.show()

        self._verify_worker = VerifyWorker(
            system_prompt="",
            cfg=self._cfg,
        )
        self._verify_worker.success.connect(self._on_verify_success)
        self._verify_worker.error.connect(self._on_verify_error)
        self._verify_worker.start()

    def _on_verify_success(self) -> None:
        self._cfg["flag_ai_verified"] = True
        self._verify_label.setText("✅ 연결 성공")
        self._verify_label.setStyleSheet("color: green;")
        self._verify_progress.hide()
        self._verify_btn.setEnabled(True)
        self._refresh_flag_summary()
        self._on_save()

    def _on_verify_error(self, msg: str) -> None:
        self._cfg["flag_ai_verified"] = False
        self._verify_label.setText(f"❌ 실패: {msg}")
        self._verify_label.setStyleSheet("color: red;")
        self._verify_progress.hide()
        self._verify_btn.setEnabled(True)
        self._refresh_flag_summary()

    def _on_save(self) -> None:
        self._collect_to_cfg()
        config.save(self._cfg)
        self._dirty = False
        self._save_done_label.show()
        self._save_done_timer.start(2000)
        self._check_whisper_model()

    def _check_whisper_model(self) -> None:
        from app.config import MODELS_DIR
        model = self._cfg.get("whisper_model", "base")
        # HF 캐시 디렉토리에 모델명이 포함된 항목이 있으면 설치된 것으로 간주
        try:
            cached = MODELS_DIR.exists() and any(
                model in item.name for item in MODELS_DIR.iterdir()
            )
        except OSError:
            cached = False
        if cached:
            return
        reply = QMessageBox.question(
            self, "STT 모델 미설치",
            f"'{model}' Whisper 모델이 설치되지 않았습니다.\n"
            "지금 다운로드할까요?\n(최초 녹음 시 자동으로 다운로드되기도 합니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._save_btn.setEnabled(False)
        self._close_btn.setEnabled(False)
        self._verify_progress.show()
        self._verify_label.setText(f"'{model}' 다운로드 중...")
        self._verify_label.setStyleSheet("color: #444;")
        self._download_worker = ModelDownloadWorker(model)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_download_finished(self) -> None:
        self._verify_progress.hide()
        self._verify_label.setText("✅ 다운로드 완료")
        self._verify_label.setStyleSheet("color: green;")
        self._save_btn.setEnabled(True)
        self._close_btn.setEnabled(True)

    def _on_download_error(self, msg: str) -> None:
        self._verify_progress.hide()
        self._verify_label.setText(f"❌ 다운로드 실패: {msg}")
        self._verify_label.setStyleSheet("color: red;")
        self._save_btn.setEnabled(True)
        self._close_btn.setEnabled(True)

    def _on_close(self) -> None:
        self.close()  # closeEvent로 위임 (dirty 체크 + 워커 정리 일원화)

    def closeEvent(self, event) -> None:
        if self._dirty:
            reply = QMessageBox.question(
                self, "닫기 확인",
                "저장하지 않은 변경사항이 있습니다. 저장 없이 닫을까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._cleanup_workers()
        super().closeEvent(event)

    def _cleanup_workers(self) -> None:
        for w in (self._verify_worker, self._ollama_worker, self._download_worker):
            if w is not None and w.isRunning():
                w.quit()
                w.wait(2000)

    def _add_resume_item(self, path: str) -> None:
        item = QListWidgetItem(Path(path).name)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self._resume_list.addItem(item)

    def _browse_resume(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "이력서/컨텍스트 파일 선택", "",
            "지원 형식 (*.pdf *.txt *.md *.html *.htm *.mhtml *.mht);;모든 파일 (*)",
        )
        existing = {
            self._resume_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._resume_list.count())
        }
        for path in paths:
            if path not in existing:
                self._add_resume_item(path)
                existing.add(path)
        if paths:
            self._mark_dirty()

    def _on_remove_resume(self) -> None:
        for item in self._resume_list.selectedItems():
            self._resume_list.takeItem(self._resume_list.row(item))
        self._mark_dirty()

    def _refresh_preset_combo(self, select: str = "") -> None:
        presets = self._cfg.get("presets", {})
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        for name in sorted(presets.keys()):
            self._preset_combo.addItem(name)
        if select:
            idx = self._preset_combo.findText(select)
            if idx >= 0:
                self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.blockSignals(False)

    def _on_load_preset(self) -> None:
        name = self._preset_combo.currentText()
        if not name:
            return
        p = self._cfg.get("presets", {}).get(name, {})
        self._prompt_edit.setPlainText(p.get("system_prompt", ""))
        self._resume_list.clear()
        for path in p.get("resume_paths", []):
            self._add_resume_item(path)
        self._preset_name_edit.setText(name)

    def _on_delete_preset(self) -> None:
        name = self._preset_combo.currentText()
        if not name:
            return
        reply = QMessageBox.question(
            self, "프리셋 삭제",
            f"'{name}' 프리셋을 삭제할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._cfg.get("presets", {}).pop(name, None)
        config.save(self._cfg)
        self._refresh_preset_combo()

    def _on_save_preset(self) -> None:
        name = self._preset_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "프리셋", "프리셋 이름을 입력해 주세요.")
            return
        presets = self._cfg.setdefault("presets", {})
        presets[name] = {
            "system_prompt": self._prompt_edit.toPlainText().strip(),
            "resume_paths":  [
                self._resume_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._resume_list.count())
            ],
        }
        config.save(self._cfg)
        self._refresh_preset_combo(select=name)
        self._preset_saved_label.show()
        self._preset_saved_timer.start(2000)
        self._dirty = False

    # ── 내부 유틸 ────────────────────────────────────────────────────────

    def _current_provider(self) -> str:
        for key, rb in self._provider_radios.items():
            if rb.isChecked():
                return key
        return "gemini"

    def _refresh_model_list(self, provider: str) -> None:
        # 기존 Ollama 워커가 실행 중이면 먼저 중단
        if self._ollama_worker and self._ollama_worker.isRunning():
            self._ollama_worker.quit()
            self._ollama_worker.wait(1000)

        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if provider == "ollama":
            self._model_combo.addItem("목록 불러오는 중...")
            self._ollama_worker = OllamaModelListWorker()
            self._ollama_worker.fetched.connect(self._on_ollama_models_fetched)
            self._ollama_worker.start()
        else:
            self._model_combo.addItems(PROVIDER_MODELS.get(provider, []))
            saved = self._cfg.get("model", "")
            idx   = self._model_combo.findText(saved)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
        self._model_combo.blockSignals(False)

    def _on_ollama_models_fetched(self, models: list) -> None:
        self._model_combo.clear()
        if models:
            self._model_combo.addItems(models)
        else:
            self._model_combo.addItem("(서버에 연결할 수 없음)")

    def _collect_to_cfg(self) -> None:
        provider = self._current_provider()
        self._cfg["provider"]       = provider
        self._cfg["model"]          = self._model_combo.currentText() if provider != "cli" else ""
        self._cfg["api_key"]        = self._api_key_edit.text().strip()
        self._cfg["cli_cmd"]        = self._cli_cmd_edit.text().strip()
        self._cfg["system_prompt"]  = self._prompt_edit.toPlainText().strip()
        self._cfg["resume_paths"]   = [
            self._resume_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._resume_list.count())
        ]
        self._cfg["whisper_model"]      = self._whisper_combo.currentText()
        self._cfg["max_record_seconds"] = self._max_rec_spin.value()

        has_direct = bool(self._cfg["system_prompt"])
        bundle_default = Path(sys.argv[0]).resolve().parent / "prompts" / "default.txt"
        self._cfg["flag_prompt_ready"] = has_direct or bundle_default.exists()

    def _refresh_flag_summary(self) -> None:
        ai  = "✅ AI 연결됨"    if self._cfg.get("flag_ai_verified") else "❌ AI 미연결"
        pr  = "✅ 프롬프트 준비됨" if config.is_prompt_ready(self._cfg) else "❌ 프롬프트 없음"
        self._flag_label.setText(f"{ai}     {pr}")

    def _mark_dirty(self) -> None:
        self._dirty = True
