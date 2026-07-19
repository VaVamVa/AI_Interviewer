"""QThread 워커 모음.

모든 블로킹 작업(STT, TTS, AI 호출, 모델 다운로드)은 여기서 실행하고
Signal로 결과를 메인 스레드(UI)에 전달한다.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

_log = logging.getLogger(__name__)


class STTWorker(QThread):
    transcribed = pyqtSignal(str)
    error       = pyqtSignal(str)

    def __init__(self, wav_path: Path, model_name: str) -> None:
        super().__init__()
        self._wav_path   = wav_path
        self._model_name = model_name

    def run(self) -> None:
        try:
            from app.core.voice import transcribe
            text = transcribe(self._wav_path, self._model_name)
            self.transcribed.emit(text)
        except Exception as e:
            _log.exception("STT 실패")
            self.error.emit(str(e))


class AIWorker(QThread):
    response = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, user_text: str, history: list[dict],
                 system_prompt: str, cfg: dict) -> None:
        super().__init__()
        self._user_text     = user_text
        self._history       = history
        self._system_prompt = system_prompt
        self._cfg           = cfg

    def run(self) -> None:
        try:
            from app.core.agent import ask
            text = ask(self._user_text, self._history, self._system_prompt, self._cfg)
            self.response.emit(text)
        except Exception as e:
            _log.exception("AI 호출 워커 실패")
            self.error.emit(str(e))


class TTSWorker(QThread):
    started_tts  = pyqtSignal()
    finished_tts = pyqtSignal()
    error        = pyqtSignal(str)

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def run(self) -> None:
        try:
            from app.core.voice import speak
            self.started_tts.emit()
            speak(self._text)
            self.finished_tts.emit()
        except Exception as e:
            _log.exception("TTS 실패")
            self.error.emit(str(e))


class ModelDownloadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model_name = model_name

    def run(self) -> None:
        try:
            from app.core.voice import ensure_whisper_model
            ensure_whisper_model(self._model_name, self.progress.emit)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class VerifyWorker(QThread):
    """AI 연결 확인 테스트 호출."""
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, system_prompt: str, cfg: dict) -> None:
        super().__init__()
        self._system_prompt = system_prompt
        self._cfg           = cfg

    def run(self) -> None:
        from app.core.agent import verify
        ok, msg = verify(self._system_prompt, self._cfg)
        if ok:
            self.success.emit()
        else:
            self.error.emit(msg)


class OllamaModelListWorker(QThread):
    """Ollama 서버에서 설치된 모델 목록을 비동기로 가져온다."""
    fetched = pyqtSignal(list)

    def run(self) -> None:
        from app.core.agent import fetch_ollama_models
        self.fetched.emit(fetch_ollama_models())
