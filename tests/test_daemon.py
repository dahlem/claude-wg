"""Tests for daemon.py event-handler logic (no real Slack calls)."""

__authors__ = ["Dominik Dahlem"]
__status__ = "Development"

import sys
from unittest.mock import MagicMock, patch

import pytest  # noqa: F401 — used via fixtures
import state

# ── Fake slack_bolt so daemon.py can be imported without a Slack connection ──

class _PassThroughApp:
    """slack_bolt.App stand-in: decorators pass through so handlers stay callable."""

    def __init__(self, **kwargs):
        pass

    def event(self, *args, **kwargs):
        return lambda fn: fn


_bolt_mock = MagicMock()
_bolt_mock.App = _PassThroughApp
sys.modules.setdefault("slack_bolt", _bolt_mock)
sys.modules.setdefault("slack_bolt.adapter.socket_mode", MagicMock())

_FAKE_CFG = {
    "slack_bot_token": "xoxb-fake",
    "my_slack_user_id": "U_ME",
    "notify_macos": False,
}

with patch.object(state, "load_config", return_value=_FAKE_CFG):
    import daemon  # noqa: E402  — must come after mocking


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_client(channel_name: str = "wg_test") -> MagicMock:
    client = MagicMock()
    client.conversations_info.return_value = {"channel": {"name": channel_name}}
    return client


def _make_event(**kwargs) -> dict:
    defaults: dict = {
        "channel": "C123",
        "ts": "200.0",
        "user": "U_BOB",
        "text": "Some message",
    }
    defaults.update(kwargs)
    return defaults


# ── ensure_channel_state ──────────────────────────────────────────────────────

def test_ensure_channel_state_creates_new(monkeypatch):
    monkeypatch.setattr(daemon, "load_channel_state", lambda name: None)
    result = daemon.ensure_channel_state("wg_test", "C123")
    assert result["channel_name"] == "wg_test"
    assert result["channel_id"] == "C123"
    assert result["threads"] == {}
    assert result["collaborators"] == []


def test_ensure_channel_state_returns_existing(monkeypatch, sample_state):
    monkeypatch.setattr(daemon, "load_channel_state", lambda name: sample_state)
    result = daemon.ensure_channel_state("wg_test", "C999")
    assert result is sample_state


# ── handle_message — top-level (new plan) ────────────────────────────────────

def test_handle_message_new_top_level_creates_thread(monkeypatch, sample_state):
    sample_state["threads"].clear()
    saved = {}
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "ensure_channel_state", lambda n, i: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.update({"s": s}))
    monkeypatch.setattr(daemon, "notify", lambda t, b: None)

    event = _make_event(ts="300.0", user="U_BOB", text="Brand new plan")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())

    assert "300.0" in sample_state["threads"]
    thread = sample_state["threads"]["300.0"]
    assert thread["owner"] == "U_BOB"
    assert thread["version"] == 1
    assert thread["approved"] is False
    assert thread["plan_versions"][0]["text"] == "Brand new plan"
    assert saved


def test_handle_message_notifies_when_others_post(monkeypatch, sample_state):
    sample_state["threads"].clear()
    notified = []
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "ensure_channel_state", lambda n, i: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: None)
    monkeypatch.setattr(daemon, "notify", lambda t, b: notified.append(t))

    event = _make_event(ts="300.0", user="U_BOB", text="Plan")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())
    assert notified


def test_handle_message_no_notify_for_own_plan(monkeypatch, sample_state):
    sample_state["threads"].clear()
    notified = []
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "ensure_channel_state", lambda n, i: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: None)
    monkeypatch.setattr(daemon, "notify", lambda t, b: notified.append(t))

    event = _make_event(ts="300.0", user="U_ME", text="My own plan")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())
    assert not notified


def test_handle_message_ignores_bot_messages(monkeypatch):
    saved = []
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.append(s))

    event = _make_event(bot_id="B_BOT", ts="400.0")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())
    assert not saved


def test_handle_message_ignores_message_subtypes(monkeypatch):
    saved = []
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.append(s))

    event = _make_event(subtype="message_changed", ts="400.0")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())
    assert not saved


def test_handle_message_ignores_non_wg_channels(monkeypatch):
    saved = []
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "general")
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.append(s))

    event = _make_event(ts="400.0")
    daemon.handle_message(event=event, client=_fake_client("general"), logger=MagicMock())
    assert not saved


# ── handle_message — replies ──────────────────────────────────────────────────

def test_handle_message_reply_from_other_is_feedback(monkeypatch, sample_state):
    saved = {}
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "ensure_channel_state", lambda n, i: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.update({"s": s}))
    monkeypatch.setattr(daemon, "notify", lambda t, b: None)

    event = _make_event(ts="200.0", user="U_BOB", text="Looks good", thread_ts="111.111")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())

    thread = sample_state["threads"]["111.111"]
    assert len(thread["feedback"]) == 1
    entry = thread["feedback"][0]
    assert entry["type"] == "feedback"
    assert entry["text"] == "Looks good"
    assert entry["user"] == "U_BOB"
    assert saved


def test_handle_message_owner_reply_increments_version(monkeypatch, sample_state):
    saved = {}
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "ensure_channel_state", lambda n, i: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.update({"s": s}))
    monkeypatch.setattr(daemon, "notify", lambda t, b: None)

    event = _make_event(ts="200.0", user="U_ME", text="Updated plan", thread_ts="111.111")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())

    thread = sample_state["threads"]["111.111"]
    assert thread["version"] == 2
    assert len(thread["plan_versions"]) == 2
    assert thread["plan_versions"][1]["text"] == "Updated plan"
    assert thread["feedback"][0]["type"] == "revision"


def test_handle_message_reply_notifies_thread_owner(monkeypatch, sample_state):
    notified = []
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "ensure_channel_state", lambda n, i: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: None)
    monkeypatch.setattr(daemon, "notify", lambda t, b: notified.append(t))

    # U_BOB replies to U_ME's thread → notification
    event = _make_event(ts="200.0", user="U_BOB", text="Nice!", thread_ts="111.111")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())
    assert notified


def test_handle_message_unknown_thread_creates_placeholder(monkeypatch, sample_state):
    saved = {}
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "ensure_channel_state", lambda n, i: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.update({"s": s}))
    monkeypatch.setattr(daemon, "notify", lambda t, b: None)

    # Reply to a thread_ts we haven't seen before
    event = _make_event(ts="200.0", user="U_BOB", text="Comment", thread_ts="999.0")
    daemon.handle_message(event=event, client=_fake_client(), logger=MagicMock())

    assert "999.0" in sample_state["threads"]
    placeholder = sample_state["threads"]["999.0"]
    assert placeholder["owner"] is None
    assert placeholder["plan_versions"] == []


# ── handle_reaction ───────────────────────────────────────────────────────────

def test_handle_reaction_approves_my_thread(monkeypatch, sample_state):
    saved = {}
    notified = []
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.update({"s": s}))
    monkeypatch.setattr(daemon, "notify", lambda t, b: notified.append(t))

    event = {
        "reaction": "white_check_mark",
        "user": "U_BOB",
        "item": {"channel": "C123", "ts": "111.111"},
    }
    daemon.handle_reaction(event=event, client=_fake_client(), logger=MagicMock())

    thread = sample_state["threads"]["111.111"]
    assert thread["approved"] is True
    assert thread["approved_by"] == "U_BOB"
    assert thread["status"] == "approved"
    assert saved
    assert notified


def test_handle_reaction_ignores_other_reactions(monkeypatch, sample_state):
    saved = []
    monkeypatch.setattr(daemon, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.append(s))

    event = {
        "reaction": "thumbsup",
        "user": "U_BOB",
        "item": {"channel": "C123", "ts": "111.111"},
    }
    daemon.handle_reaction(event=event, client=_fake_client(), logger=MagicMock())
    assert not saved


def test_handle_reaction_ignores_non_wg_channel(monkeypatch, sample_state):
    saved = []
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "general")
    monkeypatch.setattr(daemon, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.append(s))

    event = {
        "reaction": "white_check_mark",
        "user": "U_BOB",
        "item": {"channel": "C123", "ts": "111.111"},
    }
    daemon.handle_reaction(event=event, client=_fake_client("general"), logger=MagicMock())
    assert not saved


def test_handle_reaction_ignores_other_thread_owner(monkeypatch, sample_state):
    """Reaction on a thread owned by someone else should not trigger approval."""
    sample_state["threads"]["111.111"]["owner"] = "U_OTHER"
    saved = []
    monkeypatch.setattr(daemon, "resolve_channel_name", lambda c, ch: "wg_test")
    monkeypatch.setattr(daemon, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(daemon, "save_channel_state", lambda n, s: saved.append(s))
    monkeypatch.setattr(daemon, "notify", lambda t, b: None)

    event = {
        "reaction": "white_check_mark",
        "user": "U_BOB",
        "item": {"channel": "C123", "ts": "111.111"},
    }
    daemon.handle_reaction(event=event, client=_fake_client(), logger=MagicMock())
    assert not saved
