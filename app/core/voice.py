"""STT (faster-whisper) + TTS (edge-tts) + 오디오 캡처 (sounddevice).

모든 함수는 블로킹이므로 반드시 QThread 워커 안에서 호출해야 한다.
"""

import asyncio
import re
import tempfile
import threading
from pathlib import Path
from typing import Callable

import numpy as np
import pygame
import sounddevice as sd
from scipy.io import wavfile

from app.config import MODELS_DIR

_SAMPLE_RATE = 16000   # Whisper 권장 샘플레이트
_CHANNELS    = 1

# ── 녹음 ──────────────────────────────────────────────────────────────────

class AudioRecorder:
    """RECORDING 상태에서 사용. start() → stop() → get_wav_path()."""

    def __init__(self) -> None:
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock   = threading.Lock()

    def start(self) -> None:
        self._chunks.clear()
        self._stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        with self._lock:
            self._chunks.append(indata.copy())

    def stop(self) -> Path:
        """녹음 중단 후 임시 WAV 파일 경로를 반환."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            data = np.concatenate(self._chunks, axis=0) if self._chunks else np.zeros((0, 1), dtype="int16")
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wavfile.write(tmp.name, _SAMPLE_RATE, data)
        return Path(tmp.name)

    def release(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None


# ── STT ───────────────────────────────────────────────────────────────────

def ensure_whisper_model(model_name: str, progress_cb: Callable[[int], None] | None = None) -> None:
    """모델이 없으면 다운로드. progress_cb(percent) 로 진행률 전달."""
    from faster_whisper import WhisperModel
    model_path = MODELS_DIR / model_name
    if model_path.exists():
        return
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    # faster-whisper는 HuggingFace Hub에서 자동 다운로드
    # download_root를 지정해 설치 경로에 저장
    if progress_cb:
        progress_cb(0)
    WhisperModel(model_name, device="cpu", compute_type="int8", download_root=str(MODELS_DIR))
    if progress_cb:
        progress_cb(100)


def transcribe(wav_path: Path, model_name: str = "base") -> str:
    """WAV 파일 → 한국어 텍스트 변환."""
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=str(MODELS_DIR))
    segments, _ = model.transcribe(str(wav_path), language="ko")
    return " ".join(seg.text.strip() for seg in segments).strip()


# ── TTS ───────────────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """TTS 전 마크다운 서식 기호 제거 — 별표·백틱 등이 그대로 읽히는 문제 방지."""
    # 코드 블록 (내용 포함 제거 — 코드를 읽어주면 어색함)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # 굵게/기울임: ***text***, **text**, *text* → text
    text = re.sub(r'\*{1,3}([^*\n]*?)\*{1,3}', r'\1', text)
    # 남은 단독 별표 모두 제거
    text = re.sub(r'\*+', '', text)
    # 밑줄: __text__, _text_ → text
    text = re.sub(r'_{1,2}([^_\n]*?)_{1,2}', r'\1', text)
    # 인라인 코드: `code` → code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = text.replace('`', '')
    # 헤더: # ## ### → 텍스트만 유지
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 링크: [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 이미지 제거: ![alt](url)
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    # 수평선 제거: ---, ***, ___
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # 인용 블록 마커 제거: > text → text
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # 불릿 리스트 마커 제거: - item, * item, + item → item
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
    # 연속 빈 줄 정리
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def speak(text: str) -> None:
    """edge-tts로 음성 합성 후 pygame으로 재생. 재생 완료까지 블로킹."""
    import edge_tts

    text = _strip_markdown(text)
    if not text:
        return

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    out_path = tmp.name

    async def _synthesize() -> None:
        communicate = edge_tts.Communicate(text, voice="ko-KR-SunHiNeural")
        await communicate.save(out_path)

    asyncio.run(_synthesize())

    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(out_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(50)

    # unload()로 파일 핸들을 먼저 해제해야 Windows에서 삭제 가능 (pygame 2.0+)
    pygame.mixer.music.stop()
    try:
        pygame.mixer.music.unload()
    except AttributeError:
        pass  # pygame < 2.0 fallback
    Path(out_path).unlink(missing_ok=True)


def stop_speaking() -> None:
    """TTS 재생 즉시 중단."""
    if pygame.mixer.get_init():
        pygame.mixer.music.stop()
