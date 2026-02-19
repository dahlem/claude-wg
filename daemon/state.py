"""Shared state management for claude-wg."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast


def get_config_path() -> Path:
    return Path.home() / ".claude" / "wg" / "config.json"


def get_state_dir() -> Path:
    cfg = load_config()
    return Path(cfg.get("state_dir", "~/.claude/wg")).expanduser() / "channels"


def load_config() -> dict:
    path = get_config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Run install.sh first."
        )
    with open(path) as f:
        return cast(dict, json.load(f))


def get_channel_state_path(channel_name: str) -> Path:
    return get_state_dir() / f"{channel_name}.json"


def load_channel_state(channel_name: str) -> dict | None:
    path = get_channel_state_path(channel_name)
    if not path.exists():
        return None
    with open(path) as f:
        return cast(dict, json.load(f))


def save_channel_state(channel_name: str, state: dict) -> None:
    path = get_channel_state_path(channel_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def get_session_file(project_dir: str | None = None) -> Path:
    """Return the session file for the given (or current) project directory."""
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".claude" / "wg_session.json"


def load_session(project_dir: str | None = None) -> dict | None:
    path = get_session_file(project_dir)
    if not path.exists():
        return None
    with open(path) as f:
        return cast(dict, json.load(f))


def save_session(channel_name: str, thread_ts: str, project_dir: str | None = None) -> None:
    path = get_session_file(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "channel": channel_name,
            "thread_ts": thread_ts,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_wg_channel(channel_name: str) -> bool:
    return bool(channel_name and channel_name.startswith("wg_"))
