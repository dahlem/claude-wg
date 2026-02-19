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


# ── md_to_mrkdwn ──────────────────────────────────────────────────────────────

def test_md_h1():
    assert cli.md_to_mrkdwn("# Hello") == "*Hello*"

def test_md_h2():
    assert cli.md_to_mrkdwn("## Section") == "*Section*"

def test_md_h3():
    assert cli.md_to_mrkdwn("### Sub") == "*Sub*"

def test_md_bold_double_asterisk():
    assert cli.md_to_mrkdwn("**bold**") == "*bold*"

def test_md_bold_double_underscore():
    assert cli.md_to_mrkdwn("__bold__") == "*bold*"

def test_md_italic_asterisk():
    assert cli.md_to_mrkdwn("*italic*") == "_italic_"

def test_md_italic_underscore_passthrough():
    # _text_ is already valid Slack mrkdwn — should pass through unchanged
    assert cli.md_to_mrkdwn("_italic_") == "_italic_"

def test_md_bold_and_italic_coexist():
    result = cli.md_to_mrkdwn("**bold** and *italic*")
    assert "*bold*" in result
    assert "_italic_" in result

def test_md_unordered_dash():
    assert cli.md_to_mrkdwn("- item") == "• item"

def test_md_unordered_asterisk():
    assert cli.md_to_mrkdwn("* item") == "• item"

def test_md_bullet_preserves_indent():
    assert cli.md_to_mrkdwn("  - nested") == "  • nested"

def test_md_link():
    assert cli.md_to_mrkdwn("[click here](https://example.com)") == "<https://example.com|click here>"

def test_md_horizontal_rule():
    result = cli.md_to_mrkdwn("---")
    assert result != "---"
    assert len(result) > 0

def test_md_code_block_preserved():
    text = "```\n**not bold**\n# not heading\n```"
    result = cli.md_to_mrkdwn(text)
    assert "**not bold**" in result
    assert "# not heading" in result

def test_md_inline_code_preserved():
    # Inline code passes through — no transformation inside backticks expected
    result = cli.md_to_mrkdwn("use `**raw**` here")
    # The inline backtick content is not specially handled (no fence),
    # but the surrounding text is transformed
    assert "`**raw**`" in result

def test_md_multiline():
    text = "# Title\n\n- item one\n- item two\n\n**done**"
    result = cli.md_to_mrkdwn(text)
    assert "*Title*" in result
    assert "• item one" in result
    assert "• item two" in result
    assert "*done*" in result

def test_md_plain_text_unchanged():
    assert cli.md_to_mrkdwn("just plain text") == "just plain text"

def test_md_empty_string():
    assert cli.md_to_mrkdwn("") == ""


# ── parse_sections ────────────────────────────────────────────────────────────

def test_parse_sections_no_headings():
    """Plans without headings produce a single ("", plan) pair."""
    plan = "Just some plain text\nwith no headings."
    result = cli.parse_sections(plan)
    assert result == [("", plan)]


def test_parse_sections_empty():
    result = cli.parse_sections("")
    assert result == [("", "")]


def test_parse_sections_single_h1():
    plan = "# Title\n\nBody text here."
    result = cli.parse_sections(plan)
    assert len(result) == 1
    heading, body = result[0]
    assert heading == "# Title"
    assert body == "Body text here."


def test_parse_sections_multiple():
    plan = "# Section 1\n\nBody 1.\n\n## Section 2\n\nBody 2."
    result = cli.parse_sections(plan)
    assert len(result) == 2
    assert result[0][0] == "# Section 1"
    assert "Body 1." in result[0][1]
    assert result[1][0] == "## Section 2"
    assert "Body 2." in result[1][1]


def test_parse_sections_h4_not_split():
    """h4 and deeper headings are treated as body content, not section boundaries."""
    plan = "# Top\n\n#### Deep heading\n\nContent."
    result = cli.parse_sections(plan)
    assert len(result) == 1
    assert "#### Deep heading" in result[0][1]


def test_parse_sections_body_stripped():
    """Leading/trailing blank lines in section bodies are stripped."""
    plan = "# Title\n\n\nBody\n\n"
    result = cli.parse_sections(plan)
    assert result[0][1] == "Body"


def test_parse_sections_content_before_first_heading():
    """Content before the first heading becomes a section with an empty heading."""
    plan = "Preamble\n\n# Section 1\n\nBody."
    result = cli.parse_sections(plan)
    assert len(result) == 2
    assert result[0][0] == ""
    assert "Preamble" in result[0][1]
    assert result[1][0] == "# Section 1"


def test_parse_sections_three_sections():
    plan = "# A\n\naa\n\n## B\n\nbb\n\n### C\n\ncc"
    result = cli.parse_sections(plan)
    assert len(result) == 3
    headings = [h for h, _ in result]
    assert headings == ["# A", "## B", "### C"]
