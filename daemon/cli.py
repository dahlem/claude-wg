#!/usr/bin/env python3
"""
claude-wg CLI — used by Claude Code skills to interact with Slack and local state.

Commands:
  create     Create a wg_* channel, invite collaborators, post the initial plan
  plan       Post a new plan thread to an existing channel
  reply      Post a revision to an existing plan thread
  sync       Print pending feedback for the current session's thread
  link       Link a Claude session (PWD) to a channel thread
  status     Show channel overview
  close      Archive the channel
  bootstrap  Populate local state from Slack history (for new collaborators)
  approve    Mark the current session's plan as approved
  list       List all working group channels
"""

__authors__ = ["Dominik Dahlem"]
__status__ = "Development"

import argparse
import json
import re
import sys
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

sys.path.insert(0, str(Path(__file__).parent))
from state import (
    get_state_dir,
    load_channel_state,
    load_config,
    load_session,
    now_iso,
    save_channel_state,
    save_session,
)

cfg = load_config()
client = WebClient(token=cfg["slack_bot_token"])


MY_USER_ID: str = cfg["my_slack_user_id"]

ONBOARDING_DM = """\
Hi! You've been invited to collaborate on *#{channel}* via *claude-wg*.

*Slack-only mode (no setup needed):*
Just reply in threads in the channel. Your feedback is automatically routed \
back to the plan owner's Claude Code session.

*Daemon mode (full Claude Code integration):*
Install claude-wg to get bidirectional Claude ↔ Slack collaboration:
  https://github.com/yourorg/claude-wg — see ONBOARDING.md

*Jump straight in:*
Desktop app: {deep_link}
Web: {web_link}

The channel is private and only visible to invited collaborators.
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def slack(method: str, **kwargs):
    """Call a Slack API method and return the response, raising on error.

    Retries once on transient connection errors (stale keep-alive, connection
    reset) before giving up.  This is needed because the urllib-based SDK
    client occasionally reuses a keep-alive connection after the server has
    closed it, causing an spurious ConnectionRefusedError / URLError.
    """
    import time
    from urllib.error import URLError

    fn = getattr(client, method)
    for attempt in range(2):
        try:
            return fn(**kwargs)
        except SlackApiError as e:
            print(f"Slack API error ({method}): {e.response['error']}", file=sys.stderr)
            sys.exit(1)
        except (URLError, OSError) as e:
            if attempt == 0:
                # Likely a stale keep-alive connection; pause briefly and retry
                time.sleep(0.5)
                continue
            print(f"Slack connection error ({method}): {e}", file=sys.stderr)
            sys.exit(1)


def read_plan(plan_file: str | None, plan_text: str | None) -> str:
    if plan_text:
        return plan_text
    if plan_file:
        return Path(plan_file).read_text()
    print("Provide --plan-text or --plan-file", file=sys.stderr)
    sys.exit(1)


def md_to_mrkdwn(text: str) -> str:
    """Convert standard Markdown to Slack mrkdwn format.

    Handles headings, bold, italic, unordered bullets, links, and horizontal
    rules. Code blocks (``` fences) and inline code are passed through verbatim.
    """
    result = []
    in_code_block = False

    for line in text.split("\n"):
        # Preserve fenced code blocks verbatim
        if line.startswith("```"):
            in_code_block = not in_code_block
            result.append(line)
            continue
        if in_code_block:
            result.append(line)
            continue

        # Headings (any level) → *bold line*
        heading = re.match(r"^#{1,6}\s+(.*)", line)
        if heading:
            result.append(f"*{heading.group(1)}*")
            continue

        # Horizontal rules → thin separator
        if re.match(r"^[-*_]{3,}\s*$", line):
            result.append("───────────────────")
            continue

        # Stash inline code spans so their contents are never transformed.
        # Replace `...` with a placeholder keyed by index.
        code_spans: list[str] = []
        def stash_code(m: re.Match) -> str:
            code_spans.append(m.group(0))
            return f"\x01CODE{len(code_spans) - 1}\x01"
        line = re.sub(r"`[^`]+`", stash_code, line)

        # Unordered bullets: - item / * item → • item (preserve indent)
        line = re.sub(r"^(\s*)[-*]\s+", r"\1• ", line)

        # Bold: **text** / __text__ → *text*
        # Use null-byte placeholder so bold markers don't get picked up by
        # the italic pass below.
        line = re.sub(r"\*\*(.+?)\*\*", "\x00\\1\x00", line)
        line = re.sub(r"__(.+?)__", "\x00\\1\x00", line)

        # Italic: *text* → _text_ (Slack italic)
        line = re.sub(r"\*(.+?)\*", r"_\1_", line)
        # _text_ is already correct; nothing to do for underscore italic.

        # Restore bold placeholders → *text*
        line = re.sub(r"\x00(.+?)\x00", r"*\1*", line)

        # Links: [text](url) → <url|text>
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", line)

        # Restore inline code spans verbatim
        for i, span in enumerate(code_spans):
            line = line.replace(f"\x01CODE{i}\x01", span)

        result.append(line)

    return "\n".join(result)


def format_plan_message(plan: str, version: int, channel_name: str) -> str:
    return f"*Plan v{version}* · `#{channel_name}`\n\n{md_to_mrkdwn(plan)}"


def parse_sections(plan: str) -> list[tuple[str, str]]:
    """Split a Markdown plan into (heading_line, body) pairs.

    Splits on any h1–h3 heading (``# …``, ``## …``, ``### …``).  Content
    before the first heading is attached to an empty-string heading.  If the
    plan has no headings at all, returns a single ``("", plan)`` pair, which
    signals callers to use single-message (backwards-compatible) behaviour.

    Returns a list of ``(heading_line, body)`` tuples where *heading_line* is
    the raw Markdown heading (e.g. ``## Section 1: Foo``) and *body* is the
    content that follows it up to the next heading, stripped of leading /
    trailing blank lines.
    """
    sections: list[tuple[str, str]] = []
    current_heading: str = ""
    current_body: list[str] = []

    for line in plan.split("\n"):
        if re.match(r"^#{1,3}\s+", line):
            if current_heading or current_body:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line
            current_body = []
        else:
            current_body.append(line)

    if current_heading or current_body:
        sections.append((current_heading, "\n".join(current_body).strip()))

    return sections if sections else [("", plan)]


def format_section_message(heading: str, body: str) -> str:
    """Format a single plan section as a Slack message."""
    parts: list[str] = []
    if heading:
        parts.append(md_to_mrkdwn(heading))
    if body:
        parts.append(md_to_mrkdwn(body))
    return "\n\n".join(parts)


def format_plan_anchor_message(version: int, channel_name: str,
                                sections: list[tuple[str, str]]) -> str:
    """Format the overview/anchor message for a multi-section plan."""
    lines = [f"*Plan v{version}* · `#{channel_name}`", ""]
    lines.append("*Sections:*")
    for i, (heading, _) in enumerate(sections, 1):
        m = re.match(r"^#{1,6}\s+(.*)", heading)
        heading_text = m.group(1) if m else heading or f"Section {i}"
        lines.append(f"  {i}. {heading_text}")
    lines.extend(["", "_Reply in each section below with your feedback._"])
    return "\n".join(lines)


def _post_plan(channel_id: str, plan: str, version: int,
               channel_name: str, files: list[str]) -> tuple[str, dict]:
    """Post a plan (possibly multi-section) and return (anchor_ts, thread_entry).

    If the plan contains h1–h3 headings, each section is posted as a separate
    top-level Slack message preceded by an anchor overview message.  Otherwise
    the whole plan is posted as a single message (backwards-compatible).
    """
    sections = parse_sections(plan)

    if len(sections) > 1:
        # Multi-section mode: anchor + one top-level message per section
        anchor_msg = format_plan_anchor_message(version, channel_name, sections)
        res = slack("chat_postMessage", channel=channel_id, text=anchor_msg, mrkdwn=True)
        anchor_ts: str = res["ts"]

        section_states: list[dict] = []
        section_index: dict[str, int] = {}
        for i, (heading, body) in enumerate(sections):
            sec_msg = format_section_message(heading, body)
            sec_res = slack("chat_postMessage", channel=channel_id, text=sec_msg, mrkdwn=True)
            section_ts: str = sec_res["ts"]
            section_states.append({
                "heading": heading,
                "body": body,
                "ts": section_ts,
                "feedback": [],
                "approved": False,
                "approved_by": None,
            })
            section_index[section_ts] = i

        thread_entry: dict = {
            "owner": MY_USER_ID,
            "ts": anchor_ts,
            "version": version,
            "status": "awaiting_feedback",
            "approved": False,
            "approved_by": None,
            "files": files,
            "plan_versions": [{"version": version, "text": plan, "posted_at": now_iso()}],
            "feedback": [],
            "sections": section_states,
            "section_index": section_index,
        }
        print(f"Plan posted as {len(sections)} sections. anchor_ts={anchor_ts}")
        return anchor_ts, thread_entry

    # Single-message mode (no h1–h3 headings)
    msg = format_plan_message(plan, version, channel_name)
    single_res = slack("chat_postMessage", channel=channel_id, text=msg, mrkdwn=True)
    single_ts: str = single_res["ts"]
    single_entry: dict = {
        "owner": MY_USER_ID,
        "ts": single_ts,
        "version": version,
        "status": "awaiting_feedback",
        "approved": False,
        "approved_by": None,
        "files": files,
        "plan_versions": [{"version": version, "text": plan, "posted_at": now_iso()}],
        "feedback": [],
    }
    print(f"Plan posted. thread_ts={single_ts}")
    return single_ts, single_entry


def parse_files(files_str: str | None) -> list[str]:
    """Parse comma-separated file paths into a list."""
    if not files_str:
        return []
    return [f.strip() for f in files_str.split(",") if f.strip()]


def resolve_user_ids(identifiers: list[str]) -> list[str]:
    """Resolve a list of Slack user IDs or usernames to user IDs.

    Identifiers that already look like Slack IDs (start with U or W, all
    uppercase alphanumeric) are passed through unchanged.  Anything else is
    treated as a display name / username and looked up via users.list.
    """
    id_pattern = re.compile(r"^[UW][A-Z0-9]+$")

    to_resolve = [i for i in identifiers if not id_pattern.match(i)]
    already_ids = {i for i in identifiers if id_pattern.match(i)}

    if not to_resolve:
        return identifiers

    # Fetch all workspace users once (paginated)
    name_to_id: dict[str, str] = {}
    cursor = None
    while True:
        kwargs: dict = {"limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        res = slack("users_list", **kwargs)
        for member in res.get("members", []):
            if member.get("deleted") or member.get("is_bot"):
                continue
            uid = member["id"]
            # Index by all name fields, lowercased
            for field in [
                member.get("name", ""),
                member.get("real_name", ""),
                (member.get("profile") or {}).get("display_name", ""),
                (member.get("profile") or {}).get("real_name", ""),
            ]:
                if field:
                    name_to_id[field.lower()] = uid
        next_cursor = res.get("response_metadata", {}).get("next_cursor", "")
        if not next_cursor:
            break
        cursor = next_cursor

    resolved: list[str] = list(already_ids)
    for name in to_resolve:
        uid = name_to_id.get(name.lower().lstrip("@"))
        if uid:
            resolved.append(uid)
            print(f"Resolved {name!r} → {uid}")
        else:
            print(f"Warning: could not resolve user {name!r} — skipping", file=sys.stderr)

    return resolved


def find_conflicts(state: dict) -> list[tuple]:
    """Find file conflicts between open (non-approved) threads.

    Returns list of (ts_a, ts_b, [conflicting_files]).
    """
    conflicts = []
    threads = state.get("threads", {})
    open_threads = [(ts, t) for ts, t in threads.items() if not t.get("approved")]
    for i, (ts_a, t_a) in enumerate(open_threads):
        for ts_b, t_b in open_threads[i + 1:]:
            files_a = set(t_a.get("files", []))
            files_b = set(t_b.get("files", []))
            overlap = files_a & files_b
            if overlap:
                conflicts.append((ts_a, ts_b, sorted(overlap)))
    return conflicts


def print_conflicts(conflicts: list) -> None:
    for ts_a, ts_b, files in conflicts:
        print(f"  ⚠️  Conflict between thread {ts_a} and {ts_b}: {', '.join(files)}")


# ── Commands ──────────────────────────────────────────────────────────────────

def _resolve_thread(channel_name: str, thread_ts: str | None) -> tuple[str, str, dict]:
    """Resolve channel + optional thread_ts to (channel_name, thread_ts, state).

    If thread_ts is omitted, infers the thread from MY_USER_ID ownership.
    Exits with a helpful message if resolution is ambiguous or impossible.
    """
    channel_name = channel_name if channel_name.startswith("wg_") else f"wg_{channel_name}"
    state = load_channel_state(channel_name)
    if not state:
        print(f"No local state for {channel_name}. Run /wg-join to bootstrap it.", file=sys.stderr)
        sys.exit(1)

    if thread_ts:
        if thread_ts not in state["threads"]:
            print(f"Thread {thread_ts} not found in {channel_name}.", file=sys.stderr)
            sys.exit(1)
        return channel_name, thread_ts, state

    # Infer by ownership
    owned = [(ts, t) for ts, t in state["threads"].items() if t.get("owner") == MY_USER_ID]
    if not owned:
        print(f"No threads owned by {MY_USER_ID} in #{channel_name}.", file=sys.stderr)
        sys.exit(1)
    if len(owned) == 1:
        return channel_name, owned[0][0], state

    # Multiple owned threads — list them and ask for disambiguation
    print(f"Multiple threads owned by {MY_USER_ID} in #{channel_name}:", file=sys.stderr)
    for ts, t in sorted(owned, key=lambda x: float(x[0])):
        print(f"  {ts}  v{t.get('version', 1)}  status={t.get('status')}", file=sys.stderr)
    print("Re-run with --thread-ts <ts> to select one.", file=sys.stderr)
    sys.exit(1)

def cmd_create(args) -> None:
    channel_name = f"wg_{args.channel}"

    # Create private channel
    res = slack("conversations_create", name=channel_name, is_private=True)
    channel_id = res["channel"]["id"]
    print(f"Created #{channel_name} ({channel_id})")

    # Resolve any usernames to user IDs, then always include MY_USER_ID.
    collaborator_ids = resolve_user_ids(args.collaborators or [])
    to_invite = list({MY_USER_ID, *collaborator_ids})
    slack("conversations_invite", channel=channel_id, users=",".join(to_invite))
    collaborators_display = [u for u in to_invite if u != MY_USER_ID]
    print(f"Invited self ({MY_USER_ID})" + (
        f" + collaborators: {', '.join(collaborators_display)}" if collaborators_display else ""
    ))

    # Get team info for deep-link
    try:
        auth_res = slack("auth_test")
        team_id = auth_res.get("team_id", "")
        deep_link = f"slack://channel?team={team_id}&id={channel_id}"
        web_link = f"https://app.slack.com/client/{team_id}/{channel_id}"
    except Exception:
        deep_link = ""
        web_link = ""

    plan = read_plan(args.plan_file, args.plan_text)
    files = parse_files(getattr(args, "files", None))
    thread_ts, thread_entry = _post_plan(channel_id, plan, 1, channel_name, files)

    # Initialise state
    state = {
        "channel_id": channel_id,
        "channel_name": channel_name,
        "created_by": MY_USER_ID,
        "collaborators": args.collaborators or [],
        "threads": {thread_ts: thread_entry},
    }
    save_channel_state(channel_name, state)

    # Link session
    save_session(channel_name, thread_ts, args.session_dir or None)
    print(f"Session linked: {args.session_dir or Path.cwd()} → {channel_name}:{thread_ts}")

    # DM collaborators with onboarding instructions
    for uid in (args.collaborators or []):
        try:
            dm = slack("conversations_open", users=uid)
            dm_id = dm["channel"]["id"]
            slack("chat_postMessage",
                  channel=dm_id,
                  text=ONBOARDING_DM.format(
                      channel=channel_name,
                      deep_link=deep_link,
                      web_link=web_link,
                  ),
                  mrkdwn=True)
        except Exception:
            pass  # Non-fatal if DM fails


def cmd_plan(args) -> None:
    """Post a new top-level plan thread in an existing channel."""
    channel_name = args.channel if args.channel.startswith("wg_") else f"wg_{args.channel}"
    state = load_channel_state(channel_name)
    if not state:
        print(f"No state for {channel_name}. Run /wg first.", file=sys.stderr)
        sys.exit(1)

    channel_id = state["channel_id"]
    plan = read_plan(args.plan_file, args.plan_text)
    files = parse_files(getattr(args, "files", None))
    thread_ts, thread_entry = _post_plan(channel_id, plan, 1, channel_name, files)

    state["threads"][thread_ts] = thread_entry
    save_channel_state(channel_name, state)
    save_session(channel_name, thread_ts, args.session_dir or None)
    print(f"Session linked to {channel_name}:{thread_ts}")


def cmd_reply(args) -> None:
    """Post a revised plan as a reply in the current session's thread."""
    if getattr(args, "channel", None):
        channel_name, thread_ts, state = _resolve_thread(args.channel, getattr(args, "thread_ts", None))
    else:
        session = load_session(args.session_dir or None)
        if not session:
            print(
                "No active session found. Pass --channel <name> to target a thread "
                "from the global registry, or run /wg or /wg-plan to create one.",
                file=sys.stderr,
            )
            sys.exit(1)
        channel_name = session["channel"]
        thread_ts = session["thread_ts"]
        _state = load_channel_state(channel_name)
        if not _state:
            print(f"No state for {channel_name}.", file=sys.stderr)
            sys.exit(1)
        state = _state

    thread = state["threads"].get(thread_ts, {})
    version = thread.get("version", 1) + 1
    plan = read_plan(args.plan_file, args.plan_text)
    msg = format_plan_message(plan, version, channel_name)

    channel_id = state["channel_id"]
    res = slack("chat_postMessage",
                channel=channel_id,
                text=msg,
                thread_ts=thread_ts,
                mrkdwn=True)
    reply_ts = res["ts"]

    # Update files if provided
    files = parse_files(getattr(args, "files", None))
    if files:
        thread["files"] = files

    # Append to plan_versions
    plan_versions = thread.get("plan_versions", [])
    plan_versions.append({"version": version, "text": plan, "posted_at": now_iso(), "ts": reply_ts})
    thread["plan_versions"] = plan_versions

    thread["version"] = version
    thread["latest_reply_ts"] = reply_ts
    thread["status"] = "awaiting_feedback"
    state["threads"][thread_ts] = thread
    save_channel_state(channel_name, state)

    print(f"Plan v{version} posted to thread {thread_ts}")


def cmd_sync(args) -> None:
    """Print pending feedback for the current session's thread."""
    if getattr(args, "channel", None):
        channel_name, thread_ts, state = _resolve_thread(args.channel, getattr(args, "thread_ts", None))
    else:
        session = load_session(args.session_dir or None)
        if not session:
            print(
                "No active session found. Pass --channel <name> to target a thread "
                "from the global registry, or run /wg or /wg-plan to create one.",
                file=sys.stderr,
            )
            sys.exit(1)
        channel_name = session["channel"]
        thread_ts = session["thread_ts"]
        _state = load_channel_state(channel_name)
        if not _state:
            print(f"No state found for {channel_name}.", file=sys.stderr)
            sys.exit(1)
        state = _state
        if state.get("status") == "closed":
            print(
                f"#{channel_name} is archived. Pass --channel <name> to target "
                "an active channel from the global registry.",
                file=sys.stderr,
            )
            sys.exit(1)

    thread = state["threads"].get(thread_ts)
    if not thread:
        print("Thread not found in state.", file=sys.stderr)
        sys.exit(1)

    # ── Overview mode: compact section list ───────────────────────────────────
    if getattr(args, "overview", False):
        sections = thread.get("sections")
        if not sections:
            print("This plan has no sections. Use sync without --overview for full feedback.")
            return
        print(f"# Plan Overview — #{channel_name}")
        print(f"Thread: {thread_ts}  |  Plan v{thread.get('version', 1)}")
        print(f"Status: {thread.get('status', 'open')}")
        if thread.get("approved"):
            print(f"✅ Approved by <@{thread['approved_by']}>")
        print()
        print("Sections:")
        for i, section in enumerate(sections, 1):
            heading = section.get("heading", "")
            m = re.match(r"^#{1,6}\s+(.*)", heading)
            heading_text = m.group(1) if m else heading or f"Section {i}"
            fb_count = len(section.get("feedback", []))
            sec_ts = section.get("ts", "")
            approved_str = " ✅" if section.get("approved") else ""
            feedback_note = f"  [{fb_count} feedback item{'s' if fb_count != 1 else ''}]" if fb_count else "  [no feedback]"
            print(f"  {i}.{approved_str} {heading_text}{feedback_note}")
            print(f"     ts: {sec_ts}")
        return

    # ── Section-feedback mode: one section's full thread ─────────────────────
    section_ts = getattr(args, "section_ts", None)
    if section_ts:
        sections = thread.get("sections", [])
        section_index = thread.get("section_index", {})
        idx = section_index.get(section_ts)
        if idx is None:
            print(f"Section ts {section_ts!r} not found in this plan.", file=sys.stderr)
            sys.exit(1)
        section = sections[idx]
        heading = section.get("heading", "")
        m = re.match(r"^#{1,6}\s+(.*)", heading)
        heading_text = m.group(1) if m else heading or f"Section {idx + 1}"
        print(f"# Section Feedback — {heading_text}")
        print(f"Channel: #{channel_name}  |  Section ts: {section_ts}")
        print()
        section_fb = section.get("feedback", [])
        if not section_fb:
            print("No feedback for this section yet.")
            return
        for i, entry in enumerate(section_fb, 1):
            print(f"## Feedback {i} — <@{entry['user']}> ({entry.get('received_at', '')[:19]})")
            print(entry["text"])
            print()
        return

    # ── Default: full feedback view (single-message plans) ────────────────────
    feedback = [f for f in thread.get("feedback", []) if f.get("type") == "feedback"]

    print(f"# Working Group Feedback — #{channel_name}")
    print(f"Thread: {thread_ts}  |  Plan version: {thread.get('version', 1)}")
    print(f"Status: {thread.get('status', 'open')}")
    if thread.get("approved"):
        print(f"✅ Approved by <@{thread['approved_by']}>")
    print()

    # Show current plan version text for reference
    plan_versions = thread.get("plan_versions", [])
    if plan_versions:
        latest = plan_versions[-1]
        print(f"## Current Plan (v{latest['version']})")
        print(latest["text"])
        print()

    if not feedback:
        print("No feedback yet.")
        return

    for i, entry in enumerate(feedback, 1):
        print(f"## Feedback {i} — <@{entry['user']}> ({entry.get('received_at', '')[:19]})")
        print(entry["text"])
        print()


def cmd_link(args) -> None:
    """Link the current session directory to a channel thread."""
    channel_name = args.channel if args.channel.startswith("wg_") else f"wg_{args.channel}"
    save_session(channel_name, args.thread_ts, args.session_dir or None)
    print(f"Linked session to {channel_name}:{args.thread_ts}")


def cmd_status(args) -> None:
    """Show an overview of a channel's plans and their status."""
    channel_name = args.channel if args.channel.startswith("wg_") else f"wg_{args.channel}"
    state = load_channel_state(channel_name)
    if not state:
        print(f"No state for {channel_name}.")
        return

    print(f"# #{channel_name}")
    print(f"Collaborators: {', '.join(state.get('collaborators', []))}")
    print(f"Active plans: {len(state.get('threads', {}))}")
    print()
    for ts, thread in state.get("threads", {}).items():
        approved = "✅" if thread.get("approved") else "⏳"
        fb_count = len([f for f in thread.get("feedback", []) if f.get("type") == "feedback"])
        files = thread.get("files", [])
        files_str = f" files=[{', '.join(files)}]" if files else ""
        print(f"  {approved} [{ts}] owner={thread.get('owner')} v{thread.get('version',1)} "
              f"feedback={fb_count} status={thread.get('status')}{files_str}")

    conflicts = find_conflicts(state)
    if conflicts:
        print()
        print("Conflicts:")
        print_conflicts(conflicts)


def cmd_close(args) -> None:
    """Archive the channel and clean up the local session file."""
    channel_name = args.channel if args.channel.startswith("wg_") else f"wg_{args.channel}"
    state = load_channel_state(channel_name)
    if not state:
        print(f"No state for {channel_name}.")
        sys.exit(1)

    slack("conversations_archive", channel=state["channel_id"])
    state["status"] = "closed"
    save_channel_state(channel_name, state)
    print(f"#{channel_name} archived.")

    # Clean up session file if it points to this channel (Gap 2)
    session_dir = Path(args.session_dir) if args.session_dir else Path.cwd()
    session_file = session_dir / ".claude" / "wg_session.json"
    if session_file.exists():
        try:
            with open(session_file) as f:
                session_data = json.load(f)
            if session_data.get("channel") == channel_name:
                session_file.unlink()
                print("Session file cleared.")
            else:
                print(
                    f"Session file points to a different channel "
                    f"({session_data.get('channel')}); not removed."
                )
        except Exception as e:
            print(f"Could not read/remove session file: {e}", file=sys.stderr)
    else:
        print("No session file found for this directory.")


def cmd_bootstrap(args) -> None:
    """Populate local state from Slack history for a new collaborator."""
    channel_name = args.channel if args.channel.startswith("wg_") else f"wg_{args.channel}"

    # Find channel by name via pagination
    channel_id = None
    cursor = None
    while True:
        kwargs = {"types": "private_channel", "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        res = slack("conversations_list", **kwargs)
        for ch in res.get("channels", []):
            if ch["name"] == channel_name:
                channel_id = ch["id"]
                break
        if channel_id:
            break
        next_cursor = res.get("response_metadata", {}).get("next_cursor", "")
        if not next_cursor:
            break
        cursor = next_cursor

    if not channel_id:
        print(
            f"Channel #{channel_name} not found (not a member or doesn't exist).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found #{channel_name} ({channel_id})")

    # Load existing state or create new (merge, don't overwrite)
    state = load_channel_state(channel_name)
    if state is None:
        state = {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "created_by": None,
            "collaborators": [],
            "threads": {},
        }

    # Fetch all top-level messages
    all_messages = []
    cursor = None
    while True:
        kwargs = {"channel": channel_id, "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        res = slack("conversations_history", **kwargs)
        all_messages.extend(res.get("messages", []))
        next_cursor = res.get("response_metadata", {}).get("next_cursor", "")
        if not next_cursor:
            break
        cursor = next_cursor

    thread_count = 0
    feedback_count = 0

    for msg in all_messages:
        ts = msg.get("ts", "")
        user = msg.get("user", "")
        text = msg.get("text", "")

        if ts in state["threads"]:
            # Already have this thread — skip to avoid overwriting local data
            continue

        # Create thread entry for top-level message
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
        thread_count += 1

        # Fetch replies for this thread
        thread_messages = []
        reply_cursor = None
        first_page = True
        while True:
            kwargs = {"channel": channel_id, "ts": ts, "limit": 200}
            if reply_cursor:
                kwargs["cursor"] = reply_cursor
            res = slack("conversations_replies", **kwargs)
            msgs = res.get("messages", [])
            # First message on the first page is the parent itself — skip it
            thread_messages.extend(msgs[1:] if first_page else msgs)
            first_page = False
            next_cursor = res.get("response_metadata", {}).get("next_cursor", "")
            if not next_cursor:
                break
            reply_cursor = next_cursor

        thread = state["threads"][ts]
        for reply in thread_messages:
            reply_user = reply.get("user", "")
            reply_ts = reply.get("ts", "")
            reply_text = reply.get("text", "")
            entry = {
                "user": reply_user,
                "ts": reply_ts,
                "text": reply_text,
                "received_at": now_iso(),
            }
            if reply_user == user:
                # Owner replying = revision
                new_version = thread["version"] + 1
                thread["version"] = new_version
                entry["type"] = "revision"
                thread["plan_versions"].append(
                    {"version": new_version, "text": reply_text, "posted_at": now_iso()}
                )
            else:
                entry["type"] = "feedback"
                feedback_count += 1
            thread["feedback"].append(entry)

    save_channel_state(channel_name, state)
    print(
        f"Bootstrapped #{channel_name}: {thread_count} threads, "
        f"{feedback_count} feedback entries"
    )


def cmd_approve(args) -> None:
    """Mark the current session's plan as approved and add ✅ reaction in Slack."""
    if getattr(args, "channel", None):
        channel_name, thread_ts, state = _resolve_thread(args.channel, getattr(args, "thread_ts", None))
    else:
        session = load_session(args.session_dir or None)
        if not session:
            print(
                "No active session found. Pass --channel <name> to target a thread "
                "from the global registry, or run /wg or /wg-plan to create one.",
                file=sys.stderr,
            )
            sys.exit(1)
        channel_name = session["channel"]
        thread_ts = session["thread_ts"]
        _state = load_channel_state(channel_name)
        if not _state:
            print(f"No state for {channel_name}.", file=sys.stderr)
            sys.exit(1)
        state = _state
        if state.get("status") == "closed":
            print(
                f"#{channel_name} is archived. Pass --channel <name> to target "
                "an active channel from the global registry.",
                file=sys.stderr,
            )
            sys.exit(1)

    thread = state["threads"].get(thread_ts)
    if not thread:
        print(f"No thread owned by {MY_USER_ID} found in #{channel_name}.", file=sys.stderr)
        sys.exit(1)

    # ── Per-section approval ──────────────────────────────────────────────────
    section_ts_arg = getattr(args, "section_ts", None)
    if section_ts_arg:
        sections = thread.get("sections", [])
        section_index = thread.get("section_index", {})
        idx = section_index.get(section_ts_arg)
        if idx is None:
            print(f"Section ts {section_ts_arg!r} not found in this plan.", file=sys.stderr)
            sys.exit(1)
        section = sections[idx]
        section["approved"] = True
        section["approved_by"] = MY_USER_ID
        state["threads"][thread_ts] = thread
        save_channel_state(channel_name, state)
        try:
            slack("reactions_add",
                  channel=state["channel_id"],
                  name="white_check_mark",
                  timestamp=section_ts_arg)
        except Exception as e:
            print(f"Warning: could not add reaction: {e}", file=sys.stderr)
        heading = section.get("heading", "")
        hm = re.match(r"^#{1,6}\s+(.*)", heading)
        heading_text = hm.group(1) if hm else heading or f"Section {idx + 1}"
        print(f"Section '{heading_text}' approved. ✅ reaction added in Slack.")
        return

    # ── Whole-plan approval ───────────────────────────────────────────────────
    thread["approved"] = True
    thread["approved_by"] = MY_USER_ID
    thread["status"] = "approved"
    state["threads"][thread_ts] = thread
    save_channel_state(channel_name, state)

    # Add ✅ reaction to the latest reply (or top-level if no replies yet)
    reaction_ts = thread.get("latest_reply_ts", thread_ts)
    try:
        slack("reactions_add",
              channel=state["channel_id"],
              name="white_check_mark",
              timestamp=reaction_ts)
    except Exception as e:
        print(f"Warning: could not add reaction: {e}", file=sys.stderr)

    version = thread.get("version", 1)
    print(f"Plan v{version} marked as approved. ✅ reaction added in Slack.")


def cmd_list(args) -> None:
    """List all working group channels."""
    from datetime import datetime, timezone

    channels_dir = get_state_dir()
    if not channels_dir.exists():
        print("No working group channels found.")
        return

    channel_files = list(channels_dir.glob("*.json"))
    if not channel_files:
        print("No working group channels found.")
        return

    summaries = []
    for cf in channel_files:
        try:
            with open(cf) as f:
                state = json.load(f)
        except Exception:
            continue

        channel_name = state.get("channel_name", cf.stem)
        threads = state.get("threads", {})
        total = len(threads)
        open_count = sum(1 for t in threads.values() if not t.get("approved"))
        approved_count = total - open_count

        # Last activity: most recent message/feedback timestamp
        last_ts: float | None = None
        for t in threads.values():
            for candidate in [t.get("ts", "")]:
                try:
                    val = float(candidate)
                    if last_ts is None or val > last_ts:
                        last_ts = val
                except (ValueError, TypeError):
                    pass
            for fb in t.get("feedback", []):
                try:
                    val = float(fb.get("ts", ""))
                    if last_ts is None or val > last_ts:
                        last_ts = val
                except (ValueError, TypeError):
                    pass

        if last_ts is not None:
            now = datetime.now(timezone.utc).timestamp()
            diff = now - last_ts
            if diff < 60:
                last_str = f"{int(diff)}s ago"
            elif diff < 3600:
                last_str = f"{int(diff / 60)}m ago"
            elif diff < 86400:
                last_str = f"{int(diff / 3600)}h ago"
            else:
                last_str = f"{int(diff / 86400)}d ago"
        else:
            last_str = "unknown"

        if args.open_only and open_count == 0:
            continue

        conflicts = find_conflicts(state)
        conflict_str = "  ⚠️ conflict" if conflicts else ""

        summaries.append(
            (last_ts or 0, channel_name, total, open_count, approved_count, last_str, conflict_str)
        )

    # Sort by last activity, most recent first
    summaries.sort(key=lambda x: x[0], reverse=True)

    for _, channel_name, total, open_count, approved_count, last_str, conflict_str in summaries:
        plan_word = "plan" if total == 1 else "plans"
        print(
            f"#{channel_name:<30} {total} {plan_word} "
            f"({open_count} open, {approved_count} approved)"
            f"  last: {last_str}{conflict_str}"
        )


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wg_cli", description="claude-wg CLI")
    sub = p.add_subparsers(dest="command", required=True)

    # create
    c = sub.add_parser("create", help="Create channel, invite collaborators, post plan")
    c.add_argument("--channel", required=True, help="Channel name without wg_ prefix")
    c.add_argument("--collaborators", nargs="*", help="Slack user IDs to invite")
    c.add_argument("--plan-file", help="Path to file containing plan markdown")
    c.add_argument("--plan-text", help="Plan text inline")
    c.add_argument("--session-dir", help="Project directory (defaults to CWD)")
    c.add_argument("--files", help="Comma-separated file paths this plan will modify")

    # plan
    c = sub.add_parser("plan", help="Post a new plan thread in an existing channel")
    c.add_argument("--channel", required=True)
    c.add_argument("--plan-file")
    c.add_argument("--plan-text")
    c.add_argument("--session-dir")
    c.add_argument("--files", help="Comma-separated file paths this plan will modify")

    # reply
    c = sub.add_parser("reply", help="Post a revised plan to the current session's thread")
    c.add_argument("--plan-file")
    c.add_argument("--plan-text")
    c.add_argument("--session-dir")
    c.add_argument("--files", help="Comma-separated file paths this plan will modify")
    c.add_argument("--channel", help="Channel name (bypasses session file; infers thread by ownership)")
    c.add_argument("--thread-ts", help="Thread timestamp (required when you own multiple threads in the channel)")

    # sync
    c = sub.add_parser("sync", help="Print feedback for the current session's thread")
    c.add_argument("--session-dir")
    c.add_argument("--channel", help="Channel name (bypasses session file when used with --thread-ts)")
    c.add_argument("--thread-ts", help="Thread timestamp (bypasses session file when used with --channel)")
    c.add_argument("--overview", action="store_true",
                   help="Print compact section list with feedback counts (multi-section plans)")
    c.add_argument("--section-ts",
                   help="Print feedback for a specific section identified by its Slack timestamp")

    # link
    c = sub.add_parser("link", help="Link session directory to a channel thread")
    c.add_argument("--channel", required=True)
    c.add_argument("--thread-ts", required=True)
    c.add_argument("--session-dir")

    # status
    c = sub.add_parser("status", help="Show channel plan overview")
    c.add_argument("--channel", required=True)

    # close
    c = sub.add_parser("close", help="Archive the channel")
    c.add_argument("--channel", required=True)
    c.add_argument("--session-dir", help="Project directory (defaults to CWD)")

    # bootstrap
    c = sub.add_parser("bootstrap", help="Populate local state from Slack history")
    c.add_argument("--channel", required=True)
    c.add_argument("--session-dir")

    # approve
    c = sub.add_parser("approve", help="Mark the current session's plan as approved")
    c.add_argument("--channel", help="Channel name (bypasses session file; infers thread by ownership)")
    c.add_argument("--thread-ts", help="Thread timestamp (required when you own multiple threads in the channel)")
    c.add_argument("--section-ts", help="Approve a specific section by its Slack timestamp (multi-section plans)")
    c.add_argument("--session-dir")

    # list
    c = sub.add_parser("list", help="List all working group channels")
    c.add_argument("--open-only", action="store_true", help="Only show channels with open plans")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    commands = {
        "create": cmd_create,
        "plan": cmd_plan,
        "reply": cmd_reply,
        "sync": cmd_sync,
        "link": cmd_link,
        "status": cmd_status,
        "close": cmd_close,
        "bootstrap": cmd_bootstrap,
        "approve": cmd_approve,
        "list": cmd_list,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
