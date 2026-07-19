"""앱 로그 설정 — LOG_DIR에 날짜별 .log 파일로 기록."""

import logging
import warnings
from datetime import datetime

from app.config import LOG_DIR


def setup() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(fmt)
    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)

    # 외부 라이브러리 디버그 노이즈 억제
    for noisy in ("httpcore", "httpx", "google_genai", "urllib3",
                  "huggingface_hub", "filelock", "fsspec"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    # HuggingFace Hub 미인증 요청 경고 억제 (로컬 Whisper 모델 사용 시 무해)
    warnings.filterwarnings("ignore", message=".*HF_TOKEN.*")
    warnings.filterwarnings("ignore", message=".*huggingface.*", category=UserWarning)

    # ctranslate2: CPU에서 float16→float32 자동 변환 경고 억제 (정상 동작, 노이즈만 제거)
    try:
        import ctranslate2
        ctranslate2.set_log_level(4)  # 4 = ERROR (WARNING=3 미만 출력 차단)
    except Exception:
        pass
