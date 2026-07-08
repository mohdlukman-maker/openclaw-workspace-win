import json
import logging
from pathlib import Path
from typing import Any


def pending_path(data_dir: Path, chat_id: Any) -> Path:
    safe_chat_id = "".join(character for character in str(chat_id or "unknown") if character.isalnum() or character in {"_", "-"})
    return data_dir / "pending" / f"{safe_chat_id or 'unknown'}.json"


def save_pending(data_dir: Path, chat_id: Any, pending: dict[str, Any]) -> None:
    path = pending_path(data_dir, chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")


def load_pending(data_dir: Path, chat_id: Any) -> dict[str, Any] | None:
    path = pending_path(data_dir, chat_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logging.exception("Could not load pending review state: %s", path)
        return None
    return data if isinstance(data, dict) else None


def clear_pending(data_dir: Path, chat_id: Any) -> None:
    path = pending_path(data_dir, chat_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return
