"""Tests for state.py — config and file I/O helpers."""

__authors__ = ["Dominik Dahlem"]
__status__ = "Development"

import re

import state

# ── is_wg_channel ─────────────────────────────────────────────────────────────

def test_is_wg_channel_matches():
    assert state.is_wg_channel("wg_feature")
    assert state.is_wg_channel("wg_auth-refactor")
    assert state.is_wg_channel("wg_")


def test_is_wg_channel_no_match():
    assert not state.is_wg_channel("feature")
    assert not state.is_wg_channel("")
    assert not state.is_wg_channel("WG_feature")
    assert not state.is_wg_channel("wgfeature")


# ── now_iso ───────────────────────────────────────────────────────────────────

def test_now_iso_format():
    result = state.now_iso()
    assert "T" in result
    assert result.endswith("+00:00")
    # Rough ISO 8601 shape: YYYY-MM-DDTHH:MM:SS...
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", result)


# ── session file ──────────────────────────────────────────────────────────────

def test_get_session_file_explicit(tmp_path):
    path = state.get_session_file(str(tmp_path))
    assert path == tmp_path / ".claude" / "wg_session.json"


def test_save_load_session_roundtrip(tmp_path):
    state.save_session("wg_test", "111.111", str(tmp_path))
    loaded = state.load_session(str(tmp_path))
    assert loaded is not None
    assert loaded["channel"] == "wg_test"
    assert loaded["thread_ts"] == "111.111"
    assert "linked_at" in loaded


def test_load_session_missing(tmp_path):
    assert state.load_session(str(tmp_path)) is None


def test_save_session_creates_parent_dir(tmp_path):
    nested = tmp_path / "deep" / "project"
    state.save_session("wg_test", "111.0", str(nested))
    assert (nested / ".claude" / "wg_session.json").exists()


# ── channel state ─────────────────────────────────────────────────────────────

def test_save_load_channel_state_roundtrip(tmp_path, monkeypatch, sample_state):
    channels = tmp_path / "channels"
    channels.mkdir()
    monkeypatch.setattr(state, "get_state_dir", lambda: channels)

    state.save_channel_state("wg_test", sample_state)
    loaded = state.load_channel_state("wg_test")
    assert loaded == sample_state


def test_load_channel_state_missing(tmp_path, monkeypatch):
    channels = tmp_path / "channels"
    channels.mkdir()
    monkeypatch.setattr(state, "get_state_dir", lambda: channels)

    assert state.load_channel_state("wg_nonexistent") is None


def test_save_channel_state_creates_dir(tmp_path, monkeypatch):
    channels = tmp_path / "channels"
    # Don't pre-create — save_channel_state should handle it
    monkeypatch.setattr(state, "get_state_dir", lambda: channels)

    state.save_channel_state("wg_test", {"channel_name": "wg_test"})
    assert (channels / "wg_test.json").exists()
