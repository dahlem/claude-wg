"""Tests for pure (no I/O, no Slack) functions in cli.py."""

__authors__ = ["Dominik Dahlem"]
__status__ = "Development"

import cli

# ── parse_files ───────────────────────────────────────────────────────────────

def test_parse_files_none():
    assert cli.parse_files(None) == []


def test_parse_files_empty_string():
    assert cli.parse_files("") == []


def test_parse_files_single():
    assert cli.parse_files("auth/middleware.py") == ["auth/middleware.py"]


def test_parse_files_multiple():
    assert cli.parse_files("a.py,b.py,c.py") == ["a.py", "b.py", "c.py"]


def test_parse_files_strips_whitespace():
    assert cli.parse_files(" a.py , b.py ") == ["a.py", "b.py"]


def test_parse_files_skips_empty_segments():
    assert cli.parse_files(",a.py,,b.py,") == ["a.py", "b.py"]


# ── format_plan_message ───────────────────────────────────────────────────────

def test_format_plan_message_contains_version():
    msg = cli.format_plan_message("My plan", 2, "wg_test")
    assert "*Plan v2*" in msg


def test_format_plan_message_contains_channel():
    msg = cli.format_plan_message("My plan", 1, "wg_test")
    assert "`#wg_test`" in msg


def test_format_plan_message_contains_body():
    msg = cli.format_plan_message("My plan", 1, "wg_test")
    assert "My plan" in msg


# ── find_conflicts ────────────────────────────────────────────────────────────

def test_find_conflicts_empty_threads():
    assert cli.find_conflicts({"threads": {}}) == []


def test_find_conflicts_no_files():
    state = {
        "threads": {
            "1": {"approved": False, "files": []},
            "2": {"approved": False, "files": []},
        }
    }
    assert cli.find_conflicts(state) == []


def test_find_conflicts_no_overlap():
    state = {
        "threads": {
            "1": {"approved": False, "files": ["auth/a.py"]},
            "2": {"approved": False, "files": ["api/b.py"]},
        }
    }
    assert cli.find_conflicts(state) == []


def test_find_conflicts_overlap():
    state = {
        "threads": {
            "1": {"approved": False, "files": ["auth/a.py", "shared.py"]},
            "2": {"approved": False, "files": ["api/b.py", "shared.py"]},
        }
    }
    conflicts = cli.find_conflicts(state)
    assert len(conflicts) == 1
    _ts_a, _ts_b, files = conflicts[0]
    assert files == ["shared.py"]


def test_find_conflicts_approved_thread_excluded():
    state = {
        "threads": {
            "1": {"approved": True, "files": ["shared.py"]},
            "2": {"approved": False, "files": ["shared.py"]},
        }
    }
    assert cli.find_conflicts(state) == []


def test_find_conflicts_three_way():
    state = {
        "threads": {
            "1": {"approved": False, "files": ["a.py", "b.py"]},
            "2": {"approved": False, "files": ["b.py", "c.py"]},
            "3": {"approved": False, "files": ["a.py", "c.py"]},
        }
    }
    conflicts = cli.find_conflicts(state)
    # (1,2) share b.py, (1,3) share a.py, (2,3) share c.py
    assert len(conflicts) == 3


def test_find_conflicts_conflict_files_sorted():
    state = {
        "threads": {
            "1": {"approved": False, "files": ["z.py", "a.py"]},
            "2": {"approved": False, "files": ["a.py", "z.py"]},
        }
    }
    _ts_a, _ts_b, files = cli.find_conflicts(state)[0]
    assert files == ["a.py", "z.py"]


# ── resolve_user_ids — ID pass-through ────────────────────────────────────────

def test_resolve_user_ids_passthrough_u_prefix(monkeypatch):
    monkeypatch.setattr(cli, "slack", lambda m, **kw: (_ for _ in ()).throw(AssertionError("slack called")))
    result = cli.resolve_user_ids(["U123ABC", "UABCDEF"])
    assert set(result) == {"U123ABC", "UABCDEF"}


def test_resolve_user_ids_passthrough_w_prefix(monkeypatch):
    monkeypatch.setattr(cli, "slack", lambda m, **kw: (_ for _ in ()).throw(AssertionError("slack called")))
    result = cli.resolve_user_ids(["W123ABC"])
    assert result == ["W123ABC"]


def test_resolve_user_ids_empty():
    result = cli.resolve_user_ids([])
    assert result == []


# ── resolve_user_ids — name resolution ───────────────────────────────────────

def _fake_users_list(*members):
    """Return a fake users.list response with the given member dicts."""
    def handler(method, **kwargs):
        assert method == "users_list"
        return {
            "members": list(members),
            "response_metadata": {"next_cursor": ""},
        }
    return handler


def test_resolve_user_ids_by_username(monkeypatch):
    monkeypatch.setattr(cli, "slack", _fake_users_list(
        {"id": "U_BOB", "deleted": False, "is_bot": False,
         "name": "bob.smith", "real_name": "Bob Smith",
         "profile": {"display_name": "Bob", "real_name": "Bob Smith"}},
    ))
    assert cli.resolve_user_ids(["bob.smith"]) == ["U_BOB"]


def test_resolve_user_ids_by_display_name(monkeypatch):
    monkeypatch.setattr(cli, "slack", _fake_users_list(
        {"id": "U_ALICE", "deleted": False, "is_bot": False,
         "name": "alice_h", "real_name": "Alice Huang",
         "profile": {"display_name": "Alice", "real_name": "Alice Huang"}},
    ))
    assert cli.resolve_user_ids(["Alice"]) == ["U_ALICE"]


def test_resolve_user_ids_at_prefix_stripped(monkeypatch):
    monkeypatch.setattr(cli, "slack", _fake_users_list(
        {"id": "U_CAROL", "deleted": False, "is_bot": False,
         "name": "carol", "real_name": "Carol",
         "profile": {"display_name": "Carol", "real_name": "Carol"}},
    ))
    assert cli.resolve_user_ids(["@carol"]) == ["U_CAROL"]


def test_resolve_user_ids_case_insensitive(monkeypatch):
    monkeypatch.setattr(cli, "slack", _fake_users_list(
        {"id": "U_DAN", "deleted": False, "is_bot": False,
         "name": "dan", "real_name": "Dan",
         "profile": {"display_name": "Dan", "real_name": "Dan"}},
    ))
    assert cli.resolve_user_ids(["DAN"]) == ["U_DAN"]


def test_resolve_user_ids_skips_deleted(monkeypatch):
    monkeypatch.setattr(cli, "slack", _fake_users_list(
        {"id": "U_OLD", "deleted": True, "is_bot": False,
         "name": "old.user", "real_name": "Old User",
         "profile": {"display_name": "Old", "real_name": "Old User"}},
    ))
    result = cli.resolve_user_ids(["old.user"])
    assert result == []


def test_resolve_user_ids_unknown_warns(monkeypatch, capsys):
    monkeypatch.setattr(cli, "slack", _fake_users_list())
    result = cli.resolve_user_ids(["nobody"])
    assert result == []
    assert "Warning" in capsys.readouterr().err


def test_resolve_user_ids_mixed(monkeypatch):
    monkeypatch.setattr(cli, "slack", _fake_users_list(
        {"id": "U_EVE", "deleted": False, "is_bot": False,
         "name": "eve", "real_name": "Eve",
         "profile": {"display_name": "Eve", "real_name": "Eve"}},
    ))
    result = cli.resolve_user_ids(["U123DIRECT", "eve"])
    assert "U123DIRECT" in result
    assert "U_EVE" in result
