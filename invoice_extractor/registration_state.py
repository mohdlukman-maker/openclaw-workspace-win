"""Persistent registration state storage."""
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REGISTRATION_STATE_DIR = Path(__file__).resolve().parent / "data" / "registration_state"


def _state_path(chat_id: str) -> Path:
    REGISTRATION_STATE_DIR.mkdir(parents=True, exist_ok=True)
    return REGISTRATION_STATE_DIR / f"{chat_id}.json"


def save_registration_state(chat_id: str, state: dict[str, Any]) -> None:
    """Save registration state to disk."""
    try:
        # Convert Path objects to strings for JSON serialization
        serializable = _make_serializable(state)
        path = _state_path(chat_id)
        path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save registration state for chat %s: %s", chat_id, exc)


def load_registration_state(chat_id: str) -> dict[str, Any] | None:
    """Load registration state from disk."""
    path = _state_path(chat_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Convert string paths back to Path objects
        return _restore_paths(data)
    except Exception as exc:
        logger.warning("Failed to load registration state for chat %s: %s", chat_id, exc)
        return None


def clear_registration_state(chat_id: str) -> None:
    """Delete registration state from disk."""
    path = _state_path(chat_id)
    if path.exists():
        try:
            path.unlink()
        except Exception as exc:
            logger.warning("Failed to clear registration state for chat %s: %s", chat_id, exc)


def _make_serializable(obj: Any) -> Any:
    """Convert Path objects to strings for JSON serialization."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    return obj


def _restore_paths(obj: Any) -> Any:
    """Restore Path objects from strings."""
    if isinstance(obj, str):
        # Only restore if it looks like a file path
        if "\\" in obj or "/" in obj:
            return Path(obj)
        return obj
    if isinstance(obj, dict):
        return {k: _restore_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_restore_paths(v) for v in obj]
    return obj