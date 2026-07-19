import json
from datetime import datetime
from pathlib import Path

from app.config import SESSIONS_DIR


def _path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def new_session(cfg: dict) -> dict:
    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return {
        "session_id": session_id,
        "started_at": session_id,
        "elapsed_seconds": 0,
        "snapshot": {
            "system_prompt": cfg.get("system_prompt", ""),
            "resume_paths":  list(cfg.get("resume_paths", [])),
        },
        "turns": [],
    }


def add_turn(session: dict, role: str, text: str) -> None:
    """role: "interviewer" | "candidate" """
    session["turns"].append({
        "role":      role,
        "text":      text,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })


def autosave(session: dict) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(_path(session["session_id"]), "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def load(session_id: str) -> dict | None:
    p = _path(session_id)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_latest_session() -> dict | None:
    """가장 최근 세션을 반환. 없으면 None."""
    if not SESSIONS_DIR.exists():
        return None
    files = sorted(SESSIONS_DIR.glob("*.json"), reverse=True)
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                s = json.load(fp)
            if s.get("turns"):
                return s
        except (json.JSONDecodeError, OSError):
            continue
    return None


def list_sessions() -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    result = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            with open(f, encoding="utf-8") as fp:
                result.append(json.load(fp))
        except (json.JSONDecodeError, OSError):
            continue
    return result
