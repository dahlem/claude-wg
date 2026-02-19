"""Tests for CLI command functions that read/write state (no real Slack calls)."""

__authors__ = ["Dominik Dahlem"]
__status__ = "Development"

import argparse
import json

import cli
import pytest


def make_args(**kwargs) -> argparse.Namespace:
    defaults: dict = {"session_dir": None, "channel": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ── cmd_status ────────────────────────────────────────────────────────────────

def test_cmd_status_no_state(capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_channel_state", lambda name: None)
    cli.cmd_status(make_args(channel="wg_test"))
    assert "No state" in capsys.readouterr().out


def test_cmd_status_shows_thread_info(capsys, monkeypatch, sample_state):
    monkeypatch.setattr(cli, "load_channel_state", lambda name: sample_state)
    cli.cmd_status(make_args(channel="wg_test"))
    out = capsys.readouterr().out
    assert "#wg_test" in out
    assert "U_ME" in out
    assert "v1" in out


def test_cmd_status_unapproved_flag(capsys, monkeypatch, sample_state):
    monkeypatch.setattr(cli, "load_channel_state", lambda name: sample_state)
    cli.cmd_status(make_args(channel="wg_test"))
    assert "⏳" in capsys.readouterr().out


def test_cmd_status_approved_flag(capsys, monkeypatch, sample_state):
    sample_state["threads"]["111.111"]["approved"] = True
    monkeypatch.setattr(cli, "load_channel_state", lambda name: sample_state)
    cli.cmd_status(make_args(channel="wg_test"))
    assert "✅" in capsys.readouterr().out


def test_cmd_status_shows_files(capsys, monkeypatch, sample_state):
    monkeypatch.setattr(cli, "load_channel_state", lambda name: sample_state)
    cli.cmd_status(make_args(channel="wg_test"))
    assert "auth/middleware.py" in capsys.readouterr().out


def test_cmd_status_shows_conflict(capsys, monkeypatch):
    state = {
        "channel_name": "wg_test",
        "collaborators": [],
        "threads": {
            "1": {"approved": False, "owner": "U_A", "version": 1,
                  "status": "open", "feedback": [], "files": ["shared.py"]},
            "2": {"approved": False, "owner": "U_B", "version": 1,
                  "status": "open", "feedback": [], "files": ["shared.py"]},
        },
    }
    monkeypatch.setattr(cli, "load_channel_state", lambda name: state)
    cli.cmd_status(make_args(channel="wg_test"))
    assert "⚠️" in capsys.readouterr().out


def test_cmd_status_normalises_channel_name(monkeypatch):
    """Both 'test' and 'wg_test' should load the same state."""
    loaded = []
    monkeypatch.setattr(cli, "load_channel_state", lambda name: loaded.append(name) or None)
    cli.cmd_status(make_args(channel="test"))
    assert loaded[0] == "wg_test"


# ── cmd_list ──────────────────────────────────────────────────────────────────

def test_cmd_list_missing_dir(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "get_state_dir", lambda: tmp_path / "nonexistent")
    cli.cmd_list(make_args(open_only=False))
    assert "No working group channels found" in capsys.readouterr().out


def test_cmd_list_empty_dir(capsys, monkeypatch, tmp_path):
    channels = tmp_path / "channels"
    channels.mkdir()
    monkeypatch.setattr(cli, "get_state_dir", lambda: channels)
    cli.cmd_list(make_args(open_only=False))
    assert "No working group channels found" in capsys.readouterr().out


def test_cmd_list_shows_channel(capsys, monkeypatch, tmp_path, sample_state):
    channels = tmp_path / "channels"
    channels.mkdir()
    (channels / "wg_test.json").write_text(json.dumps(sample_state))
    monkeypatch.setattr(cli, "get_state_dir", lambda: channels)
    cli.cmd_list(make_args(open_only=False))
    out = capsys.readouterr().out
    assert "wg_test" in out
    assert "1 plan" in out
    assert "1 open" in out


def test_cmd_list_open_only_hides_fully_approved(capsys, monkeypatch, tmp_path, sample_state):
    sample_state["threads"]["111.111"]["approved"] = True
    channels = tmp_path / "channels"
    channels.mkdir()
    (channels / "wg_test.json").write_text(json.dumps(sample_state))
    monkeypatch.setattr(cli, "get_state_dir", lambda: channels)
    cli.cmd_list(make_args(open_only=True))
    assert "wg_test" not in capsys.readouterr().out


def test_cmd_list_open_only_keeps_partial(capsys, monkeypatch, tmp_path, sample_state):
    # Add a second thread that is open
    sample_state["threads"]["222.0"] = {
        "approved": False, "owner": "U_BOB", "ts": "222.0",
        "version": 1, "status": "open", "files": [], "plan_versions": [], "feedback": [],
    }
    sample_state["threads"]["111.111"]["approved"] = True
    channels = tmp_path / "channels"
    channels.mkdir()
    (channels / "wg_test.json").write_text(json.dumps(sample_state))
    monkeypatch.setattr(cli, "get_state_dir", lambda: channels)
    cli.cmd_list(make_args(open_only=True))
    assert "wg_test" in capsys.readouterr().out


def test_cmd_list_shows_conflict(capsys, monkeypatch, tmp_path):
    state = {
        "channel_name": "wg_conflict",
        "threads": {
            "1": {"approved": False, "owner": "U_A", "ts": "1.0",
                  "version": 1, "status": "open", "files": ["shared.py"],
                  "plan_versions": [], "feedback": []},
            "2": {"approved": False, "owner": "U_B", "ts": "2.0",
                  "version": 1, "status": "open", "files": ["shared.py"],
                  "plan_versions": [], "feedback": []},
        },
    }
    channels = tmp_path / "channels"
    channels.mkdir()
    (channels / "wg_conflict.json").write_text(json.dumps(state))
    monkeypatch.setattr(cli, "get_state_dir", lambda: channels)
    cli.cmd_list(make_args(open_only=False))
    assert "⚠️" in capsys.readouterr().out


# ── cmd_sync ──────────────────────────────────────────────────────────────────

def test_cmd_sync_no_session(monkeypatch):
    monkeypatch.setattr(cli, "load_session", lambda d: None)
    with pytest.raises(SystemExit):
        cli.cmd_sync(make_args(session_dir="/tmp"))


def test_cmd_sync_no_feedback(capsys, monkeypatch, sample_state):
    monkeypatch.setattr(cli, "load_session",
                        lambda d: {"channel": "wg_test", "thread_ts": "111.111"})
    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    cli.cmd_sync(make_args(session_dir="/tmp"))
    out = capsys.readouterr().out
    assert "No feedback yet" in out


def test_cmd_sync_shows_current_plan(capsys, monkeypatch, sample_state):
    monkeypatch.setattr(cli, "load_session",
                        lambda d: {"channel": "wg_test", "thread_ts": "111.111"})
    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    cli.cmd_sync(make_args(session_dir="/tmp"))
    assert "Initial plan" in capsys.readouterr().out


def test_cmd_sync_with_feedback(capsys, monkeypatch, sample_state):
    sample_state["threads"]["111.111"]["feedback"] = [
        {"user": "U_BOB", "type": "feedback", "text": "Looks good",
         "received_at": "2026-01-01T00:00:00Z", "ts": "222.0"},
    ]
    monkeypatch.setattr(cli, "load_session",
                        lambda d: {"channel": "wg_test", "thread_ts": "111.111"})
    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    cli.cmd_sync(make_args(session_dir="/tmp"))
    out = capsys.readouterr().out
    assert "Looks good" in out
    assert "U_BOB" in out


def test_cmd_sync_shows_approval(capsys, monkeypatch, sample_state):
    sample_state["threads"]["111.111"]["approved"] = True
    sample_state["threads"]["111.111"]["approved_by"] = "U_BOB"
    monkeypatch.setattr(cli, "load_session",
                        lambda d: {"channel": "wg_test", "thread_ts": "111.111"})
    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    cli.cmd_sync(make_args(session_dir="/tmp"))
    out = capsys.readouterr().out
    assert "✅" in out
    assert "U_BOB" in out


def test_cmd_sync_filters_revisions_from_feedback(capsys, monkeypatch, sample_state):
    """Revisions posted by the owner should not appear as feedback items."""
    sample_state["threads"]["111.111"]["feedback"] = [
        {"user": "U_ME", "type": "revision", "text": "My revision",
         "received_at": "2026-01-01T00:00:00Z", "ts": "222.0"},
    ]
    monkeypatch.setattr(cli, "load_session",
                        lambda d: {"channel": "wg_test", "thread_ts": "111.111"})
    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    cli.cmd_sync(make_args(session_dir="/tmp"))
    out = capsys.readouterr().out
    assert "My revision" not in out
    assert "No feedback yet" in out


# ── cmd_close ─────────────────────────────────────────────────────────────────

def test_cmd_close_clears_matching_session_file(tmp_path, monkeypatch, sample_state):
    session_dir = tmp_path / "project"
    session_file = session_dir / ".claude" / "wg_session.json"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(json.dumps(
        {"channel": "wg_test", "thread_ts": "111.111"}
    ))

    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(cli, "save_channel_state", lambda n, s: None)
    monkeypatch.setattr(cli, "slack", lambda method, **kw: {})

    cli.cmd_close(make_args(channel="wg_test", session_dir=str(session_dir)))
    assert not session_file.exists()


def test_cmd_close_leaves_other_channel_session(tmp_path, monkeypatch, sample_state):
    session_dir = tmp_path / "project"
    session_file = session_dir / ".claude" / "wg_session.json"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(json.dumps(
        {"channel": "wg_other", "thread_ts": "999.0"}
    ))

    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(cli, "save_channel_state", lambda n, s: None)
    monkeypatch.setattr(cli, "slack", lambda method, **kw: {})

    cli.cmd_close(make_args(channel="wg_test", session_dir=str(session_dir)))
    assert session_file.exists()


def test_cmd_close_no_session_file(tmp_path, monkeypatch, sample_state, capsys):
    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(cli, "save_channel_state", lambda n, s: None)
    monkeypatch.setattr(cli, "slack", lambda method, **kw: {})

    cli.cmd_close(make_args(channel="wg_test", session_dir=str(tmp_path)))
    assert "No session file" in capsys.readouterr().out


def test_cmd_close_archives_channel(monkeypatch, sample_state, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "load_channel_state", lambda n: sample_state)
    monkeypatch.setattr(cli, "save_channel_state", lambda n, s: None)
    monkeypatch.setattr(cli, "slack", lambda method, **kw: calls.append(method) or {})

    cli.cmd_close(make_args(channel="wg_test", session_dir=str(tmp_path)))
    assert "conversations_archive" in calls
