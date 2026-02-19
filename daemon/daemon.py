"""
claude-wg daemon — Slack Socket Mode listener.

Listens to all wg_* private channels, routes feedback to local state files,
and fires macOS notifications when relevant activity arrives.
"""

__authors__ = ["Dominik Dahlem"]
__status__ = "Development"

import logging
import subprocess
import sys
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Allow running from repo or from installed location
sys.path.insert(0, str(Path(__file__).parent))
from state import (
    is_wg_channel,
    load_channel_state,
    load_config,
    now_iso,
    save_channel_state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("claude-wg")


def notify(title: str, body: str) -> None:
    cfg = load_config()
    if not cfg.get("notify_macos", True):
        return
    script = f'display notification "{body}" with title "{title}"'
    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception as e:
        log.warning("macOS notification failed: %s", e)


def resolve_channel_name(client, channel_id: str) -> str | None:
    try:
        info = client.conversations_info(channel=channel_id)
        return str(info["channel"]["name"])
    except Exception as e:
        log.error("Could not resolve channel %s: %s", channel_id, e)
        return None


def ensure_channel_state(channel_name: str, channel_id: str) -> dict:
    state = load_channel_state(channel_name)
    if state is None:
        state = {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "created_by": None,
            "collaborators": [],
            "threads": {},
        }
    return state


# ── App setup ────────────────────────────────────────────────────────────────

cfg = load_config()
app = App(token=cfg["slack_bot_token"])
MY_USER_ID: str = cfg["my_slack_user_id"]


# ── Event handlers ────────────────────────────────────────────────────────────

@app.event("message")
def handle_message(event: dict, client, logger) -> None:
    # Ignore bot messages and message edits/deletes
    if event.get("bot_id") or event.get("subtype"):
        return

    channel_id = event.get("channel", "")
    thread_ts = event.get("thread_ts")   # None → top-level message
    ts = event.get("ts", "")
    user = event.get("user", "")
    text = event.get("text", "")

    channel_name = resolve_channel_name(client, channel_id)
    if not channel_name or not is_wg_channel(channel_name):
        return

    state = ensure_channel_state(channel_name, channel_id)

    if thread_ts is None:
        # ── New plan posted (top-level message) ──────────────────────────────
        state["threads"][ts] = {
            "owner": user,
            "ts": ts,
            "version": 1,
            "status": "open",
            "approved": False,
            "approved_by": None,
            "files": [],
            "plan_versions": [
                {"version": 1, "text": text, "posted_at": now_iso()}
            ],
            "feedback": [],
        }
        save_channel_state(channel_name, state)

        if user != MY_USER_ID:
            notify(
                f"New plan in #{channel_name}",
                f"<@{user}> posted a new plan — run /wg-sync to review",
            )
        log.info("New plan thread %s in #%s by %s", ts, channel_name, user)

    else:
        # ── Reply in an existing thread (feedback or iteration) ──────────────
        thread = state["threads"].get(thread_ts)
        if thread is None:
            # Thread we haven't seen — create a placeholder
            thread = {
                "owner": None,
                "ts": thread_ts,
                "version": 1,
                "status": "open",
                "approved": False,
                "approved_by": None,
                "files": [],
                "plan_versions": [],
                "feedback": [],
            }
            state["threads"][thread_ts] = thread

        entry = {
            "user": user,
            "ts": ts,
            "text": text,
            "received_at": now_iso(),
        }

        # Distinguish plan iterations (owner replying) from feedback (others)
        if user == thread.get("owner"):
            new_version = thread.get("version", 1) + 1
            thread["version"] = new_version
            entry["type"] = "revision"
            plan_versions = thread.get("plan_versions", [])
            plan_versions.append(
                {"version": new_version, "text": text, "posted_at": now_iso()}
            )
            thread["plan_versions"] = plan_versions
        else:
            entry["type"] = "feedback"

        thread["feedback"].append(entry)
        save_channel_state(channel_name, state)

        # Notify if someone gave feedback on MY thread
        if thread.get("owner") == MY_USER_ID and user != MY_USER_ID:
            preview = text[:80] + ("…" if len(text) > 80 else "")
            notify(
                f"Feedback in #{channel_name}",
                f"<@{user}>: {preview}",
            )
            log.info(
                "Feedback on thread %s from %s in #%s",
                thread_ts, user, channel_name,
            )


@app.event("reaction_added")
def handle_reaction(event: dict, client, logger) -> None:
    if event.get("reaction") != "white_check_mark":
        return

    item = event.get("item", {})
    channel_id = item.get("channel", "")
    item_ts = item.get("ts", "")
    reactor = event.get("user", "")

    channel_name = resolve_channel_name(client, channel_id)
    if not channel_name or not is_wg_channel(channel_name):
        return

    state = load_channel_state(channel_name)
    if not state:
        return

    # Find the thread this reaction was on (could be top-level or a reply)
    for thread_key, thread in state["threads"].items():
        if thread_key == item_ts or any(f["ts"] == item_ts for f in thread.get("feedback", [])):
            if thread.get("owner") == MY_USER_ID:
                thread["approved"] = True
                thread["approved_by"] = reactor
                thread["status"] = "approved"
                save_channel_state(channel_name, state)
                notify(
                    f"Plan approved in #{channel_name}",
                    f"<@{reactor}> approved your plan ✅",
                )
                log.info(
                    "Thread %s approved by %s in #%s",
                    thread_key, reactor, channel_name,
                )
            break


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("claude-wg daemon starting (user: %s)", MY_USER_ID)
    handler = SocketModeHandler(app, cfg["slack_app_token"])
    handler.start()
