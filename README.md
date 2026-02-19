# claude-wg — Working Group Collaboration for Claude Code

**claude-wg** turns Slack into a real-time coordination layer between Claude Code
sessions. When a non-trivial change needs input from teammates, you open a private
working group channel, post your plan, and invite collaborators. Feedback flows
back into your Claude session automatically. Plans iterate in parallel, ownership
is explicit, approval is tracked — all without leaving your terminal.

---

## Contents

1. [How It Works](#how-it-works)
2. [Architecture](#architecture)
3. [Setup](#setup)
   - [Slack App Setup](#1-slack-app-setup)
   - [Install](#2-install)
   - [Verify](#3-verify)
4. [User Experience Flows](#user-experience-flows)
   - [Solo Self-Test](#solo-self-test)
   - [Plan Owner Flow](#plan-owner-flow)
   - [Multi-Section Plan Flow](#multi-section-plan-flow)
   - [Collaborator: Slack-Only](#collaborator-slack-only-mode)
   - [Collaborator: Daemon Mode](#collaborator-daemon-mode)
   - [Full Team Flow](#full-team-multi-plan-flow)
5. [Skills Reference](#skills-reference)
6. [CLI Reference](#cli-reference)
7. [State and Files](#state-and-files)
8. [Troubleshooting](#troubleshooting)

---

## How It Works

You are working in a Claude Code session. You have a plan that touches shared
infrastructure, or you want architectural feedback before you write a line of
code. You type `/wg my-feature U456 U789`.

Claude creates a private Slack channel `#wg_my-feature`, posts your plan, invites
your teammates, and sends them each a DM with a direct link to the channel. Your
daemon starts watching the channel.

**Single-section plans** (no Markdown headings) are posted as one top-level
Slack message. Your teammate replies in that thread. The reply appears in Claude
when you run `/wg-sync`. You revise. You post the revision. You get approval.
You close.

**Multi-section plans** (any plan with `#`, `##`, or `###` headings) are posted
differently: an anchor overview message lists the sections, then each section
appears as its own top-level Slack message with its own thread. Collaborators
reply section-by-section, giving targeted feedback. When you run `/wg-sync`,
Claude spawns one parallel subagent per section that has new feedback, collects
compact syntheses, and presents a unified view — without pulling every raw reply
into your session's context.

**Two participation tiers:**

| Mode | Requirements | What you do |
|------|-------------|-------------|
| **Slack-only** | Just a Slack invite | Reply in threads and react ✅ |
| **Daemon mode** | Daemon + skills installed | Full Claude ↔ Slack ↔ Claude loop |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Your machine                                                       │
│                                                                     │
│  Terminal A (auth-middleware session)                               │
│  └─ /wg feature-auth → posts plan → #wg_feature-auth               │
│  └─ /wg-sync ← pulls feedback when daemon notifies                 │
│  └─ /wg-approve → ✅ reaction added in Slack                        │
│                                                                     │
│  Terminal B (session-store session)                                 │
│  └─ /wg-plan → posts second plan to same channel                   │
│  └─ /wg-sync ← independent feedback stream                         │
│                                                                     │
│  daemon.py (launchd, always-on)                                     │
│  └─ Socket Mode: watches all wg_* channels                         │
│  └─ reply in thread:111 → ~/.claude/wg/channels/wg_feature-auth.json
│  └─ ✅ reaction on thread:111 → sets approved=true, notifies        │
│  └─ macOS notification → you run /wg-sync in Terminal A            │
└─────────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
   #wg_feature-auth              collaborator machine
   ┌──────────────────┐          (daemon mode optional)
   │ [Plan v1] :111   │◄──────── /wg-plan posts plan :333
   │  ├─ feedback     │
   │  └─ [Plan v2]   │◄──────── /wg-sync + revision
   │                  │
   │ [Plan v1] :222   │
   │  └─ ✅ approved  │
   └──────────────────┘
```

**Key design points:**

- **State lives locally.** Each person's daemon writes to `~/.claude/wg/` on
  their own machine. The Slack channel is the shared medium; local JSON files
  route events to the right Claude session.
- **Global registry, session file optional.** All channel and thread state
  lives in `~/.claude/wg/channels/` and is maintained by the daemon
  independently of any project directory or Claude session. `/wg-sync`,
  `/wg-approve`, and `/wg-reply` all accept `--channel [--thread-ts]` and
  work from any Claude session without a project-local session file.
  The session file (`.claude/wg_session.json`) is written as a convenience
  when you create or post a plan, but is never required.
- **Ownership inference.** When you pass `--channel` alone, the CLI looks up
  threads owned by your user ID in the global registry. If you own exactly
  one thread in that channel, it is selected automatically. If you own
  multiple, the CLI lists them and asks for `--thread-ts` to disambiguate.
- **One thread = one plan.** If you need a second parallel plan in the same
  channel, run `/wg-plan` from any Claude session.
- **Per-section posting.** If your plan contains h1–h3 Markdown headings, each
  section is posted as a separate top-level Slack message, preceded by an
  anchor overview listing all sections. This lets collaborators give focused
  per-section feedback in dedicated threads. `/wg-sync` automatically detects
  sections and spawns one parallel subagent per section that has feedback,
  returning a unified synthesis without saturating the main session's context.

---

## Setup

### 1. Slack App Setup

You need **one** Slack app for the whole team. One person creates it and shares
the two tokens with everyone who installs claude-wg. If your team already has
an app set up, skip to [Install](#2-install).

> **Who can do this?** Any workspace member can create a Slack app. You do not
> need to be a workspace admin. You do need permission to install apps, which
> is enabled by default in most workspaces. If app installation is restricted,
> ask your Slack admin to approve it.

---

#### Step 1 — Create the app

1. Open [api.slack.com/apps](https://api.slack.com/apps) and sign in to your
   workspace if prompted.

2. Click **Create New App** (top-right).

3. Choose **From scratch** (not "From a manifest").

4. Fill in:
   - **App Name:** `Claude Code WG` (or any name your team prefers)
   - **Pick a workspace:** select your team's workspace

5. Click **Create App**.

You are now on the app's configuration page. Keep this tab open — you will
return to it several times.

---

#### Step 2 — Enable Socket Mode and get the app-level token

Socket Mode lets the daemon receive events over a persistent WebSocket
connection without exposing a public URL.

1. In the left sidebar, click **Settings → Socket Mode**.

2. Toggle **Enable Socket Mode** to ON.

3. A dialog appears asking you to create an app-level token. In the
   **Token Name** field, enter `daemon` (or any label).

4. Click **Add Scope** and select `connections:write`.

5. Click **Generate**.

6. Copy the token that starts with `xapp-`. Save it somewhere safe — this is
   your **app-level token**. You can always regenerate it from this page if
   you lose it.

---

#### Step 3 — Set bot token scopes

The bot token controls what the daemon and CLI are allowed to do in Slack.

1. In the left sidebar, click **Features → OAuth & Permissions**.

2. Scroll down to **Bot Token Scopes**.

3. Click **Add an OAuth Scope** and add each of the following:

   | Scope | Why it's needed |
   |-------|----------------|
   | `groups:write` | Create private `wg_*` channels, invite members, archive when done |
   | `groups:read` | Look up a channel's ID by name (used by bootstrap and status) |
   | `groups:history` | Read message history and thread replies (used by bootstrap) |
   | `chat:write` | Post plan messages to channels and DMs to collaborators |
   | `im:write` | Open a DM conversation with a collaborator before messaging them |
   | `reactions:read` | Receive ✅ reaction events (collaborator approvals) |
   | `reactions:write` | Add a ✅ reaction on behalf of the bot (owner self-approval) |

   After adding all seven scopes the list should look like:
   ```
   groups:write  groups:read  groups:history
   chat:write    im:write
   reactions:read  reactions:write
   ```

---

#### Step 4 — Subscribe to events

This tells Slack which events to forward to the daemon.

1. In the left sidebar, click **Features → Event Subscriptions**.

2. Toggle **Enable Events** to ON.

3. Scroll to **Subscribe to bot events** and click **Add Bot User Event**.
   Add both of:
   - `message.groups` — fires when any message is posted in a private channel
     the bot is in
   - `reaction_added` — fires when any emoji reaction is added to a message

4. Click **Save Changes** at the bottom of the page.

> **Note:** You do not need to set a Request URL. Socket Mode replaces the
> HTTP endpoint — leave the URL field empty.

---

#### Step 5 — Install the app to your workspace

1. In the left sidebar, click **Settings → Install App**.

2. Click **Install to Workspace**.

3. Review the permissions and click **Allow**.

4. You are returned to the Install App page. Copy the **Bot User OAuth Token**
   — it starts with `xoxb-`. This is your **bot token**.

> If you see a banner saying "This app is pending approval from your workspace
> admin", contact your admin. In most workspaces, app installation by members
> is allowed by default.

---

#### Step 6 — Find your Slack user ID

The installer asks for your personal Slack user ID (not the bot's ID). This is
how the daemon knows which plan threads belong to you.

**In the Slack desktop app:**
- Click your name in the top-left corner
- Click **Profile**
- Click the **⋯** (three-dot) menu at the top of the profile panel
- Click **Copy member ID**

**In Slack web:**
- Click your avatar → **Profile**
- Click **⋯ → Copy member ID**

The ID looks like `U0XXXXXXX` or `U01XXXXXXXX` (9–11 characters starting with `U`).

---

#### Checklist before running install.sh

| Item | Where to find it |
|------|-----------------|
| `xapp-...` app-level token | Settings → Socket Mode |
| `xoxb-...` bot token | Settings → Install App |
| `U...` your Slack user ID | Your Slack profile (must be the `U0XXXXXXX` ID, not a display name) |
| Socket Mode enabled | Settings → Socket Mode → ON |
| All 7 bot scopes added | Features → OAuth & Permissions |
| `message.groups` event subscribed | Features → Event Subscriptions |
| `reaction_added` event subscribed | Features → Event Subscriptions |
| App installed to workspace | Settings → Install App |

---

#### Sharing the app with teammates

Your teammates do **not** create their own apps. They reuse the same app and
tokens. Share with them:

- The `xoxb-...` bot token
- The `xapp-...` app-level token
- A link to [ONBOARDING.md](ONBOARDING.md)

Keep the tokens out of chat — use a shared password manager or secrets store.

---

### 2. Install

```bash
git clone https://github.com/yourorg/claude-wg
cd claude-wg
./install.sh
```

The installer:
- Creates `~/.claude/wg/` with a Python virtualenv and all dependencies
- Copies daemon files (`daemon.py`, `cli.py`, `state.py`) to `~/.claude/wg/`
- Copies all skills to `~/.claude/commands/`
- Prompts for your bot token, app token, and Slack user ID
- Writes `~/.claude/wg/config.json` (chmod 600)
- Registers `com.claude.wg` as a launchd service (auto-starts on login)

---

### 3. Verify

```bash
# Daemon is running
launchctl list | grep claude.wg

# Live logs
tail -f ~/.claude/wg/daemon.log
```

If the daemon is not listed, check `~/.claude/wg/daemon.err` for errors.

---

## User Experience Flows

### Solo Self-Test

The fastest way to verify everything works — no teammates needed.

```
/wg my-test
```

Claude will:
1. Ask you to describe a plan
2. Create `#wg_my-test` and invite you (the human account) to it
3. Post the plan, link the session

Then go to Slack, open `#wg_my-test`, and add a ✅ reaction to the plan message.

Within seconds, a macOS notification fires: "Plan approved in #wg_my-test".

Back in Claude:
```
/wg-sync
```
→ Shows "✅ Approved by <@you>"

Then clean up:
```
/wg-close my-test
```
→ Channel archived, session file deleted.

---

### Plan Owner Flow

**Step 1 — Open a working group**

```
/wg auth-refactor U456 U789
```

Claude captures the plan you've been discussing, asks which files it touches,
creates `#wg_auth-refactor`, invites U456 and U789, posts the plan, and sends
each collaborator a DM with a direct Slack link to the channel.

The session in your current project directory is now linked to that plan thread.

**Step 2 — Wait for feedback**

The daemon watches the channel. When a collaborator replies in the Slack thread
your macOS notification fires with a preview of their message.

**Step 3 — Sync feedback into Claude**

```
/wg-sync
```

Claude fetches the stored feedback, shows you the current plan version for
context, then presents a synthesis of all collaborator comments: points of
agreement, blocking concerns, suggested revisions.

**Step 4 — Revise and post**

Work through the revision with Claude. It writes the updated plan and posts it
as a reply in the same Slack thread, incrementing the version number.

**Step 5 — Approve**

When you're satisfied with the plan:

```
/wg-approve
```

Claude shows the current plan and asks for confirmation. On approval, a ✅
reaction is added to your plan's Slack message — visible to all collaborators —
and the local state is marked approved.

Alternatively, collaborators can approve your plan by adding a ✅ reaction
themselves in Slack; the daemon picks this up automatically.

**Step 6 — Check status across the channel**

```
/wg-status
```

Shows every plan thread: owner, version, feedback count, approval state, and
any file conflicts between open plans (⚠️ if two plans touch the same files).

**Step 7 — Close**

When all plans in the channel are done:

```
/wg-close auth-refactor
```

Archives the Slack channel and deletes `.claude/wg_session.json` from your
project directory. The state file at `~/.claude/wg/channels/wg_auth-refactor.json`
is kept for reference.

---

### Multi-Section Plan Flow

When a plan has Markdown headings, claude-wg posts it as a set of separate
Slack messages rather than one long thread. This section walks through the
complete lifecycle — what the owner sees, what collaborators see, and how
feedback flows back.

#### What appears in Slack

For a plan with five sections (About the Role, What You Will Do, Requirements,
Balance, Offer), the channel looks like this immediately after posting:

```
#wg_research-scientist
├── [Anchor] Plan v1 · #wg_research-scientist          ← overview + section list
├── [Section 1] About the Role                         ← own thread
├── [Section 2] What You Will Do                       ← own thread
├── [Section 3] What We Are Looking For                ← own thread
├── [Section 4] How We Think About the Balance         ← own thread
└── [Section 5] What We Offer                          ← own thread
```

The anchor message reads something like:

```
*Plan v1* · `#wg_research-scientist`

*Sections:*
  1. About the Role
  2. What You Will Do
  3. What We Are Looking For
  4. How We Think About the Balance
  5. What We Offer

_Reply in each section below with your feedback._
```

#### What collaborators do in Slack

Collaborators reply directly in the thread of the section they want to comment
on. There is no special syntax — just reply as you would in any Slack thread.

```
#wg_research-scientist
└── [Section 3] What We Are Looking For
    ├── owner: "First or co-first author on at least two accepted papers..."
    ├── alice: "Should we require at least one paper as sole first author,
    │          or is co-first author at a top venue sufficient?"
    └── bob:   "Production engineering bullet is great — suggest adding
                'experience with model serving infra' to preferred list."
```

Each section thread is independent. Alice can comment on Requirements while Bob
comments on What We Offer at the same time, without their replies colliding in a
single thread.

**Approving a section:** If a collaborator is happy with a specific section,
they react ✅ on that section's message. The daemon routes the reaction to that
section's approval state without marking the whole plan approved.

**Approving the whole plan:** A ✅ reaction on the anchor message (or any plan
revision posted in the anchor thread) marks the entire plan approved.

#### What the owner sees: parallel sync

When the owner runs `/wg-sync`:

1. Claude calls `sync --overview` to fetch the compact section list:
   ```
   Sections:
     1.   About the Role            [no feedback]
     2.   What You Will Do          [no feedback]
     3. ✅ What We Are Looking For  [2 feedback items]
          ts: 1771538032.123456
     4.   How We Think...           [1 feedback item]
          ts: 1771538033.456789
     5.   What We Offer             [no feedback]
   ```

2. Claude spawns **one subagent per section** that has new feedback — in
   parallel. Each subagent calls `sync --section-ts <ts>` and synthesises the
   replies into 2–3 sentences.

3. Claude collects the syntheses and presents a unified view:

   ```
   ## Section 3 — What We Are Looking For
   Alice asks whether co-first authorship at a top venue is sufficient or
   whether sole first authorship should be required. Bob suggests adding
   model serving infrastructure experience to the preferred list.
   → Suggested revision: clarify co-first policy; add serving infra bullet.

   ## Section 4 — How We Think About the Balance
   Carol notes the section reads as slightly defensive — she suggests
   reframing it as a positive signal ("owners of the full stack") rather
   than a clarification of what the role is not.
   → Suggested revision: reframe opening sentence positively.
   ```

   Sections with no feedback are omitted from the synthesis. The owner only
   sees what changed.

#### Ideal collaboration pattern

The multi-section model works best when:

- **Sections map to distinct concerns.** Each heading covers one topic, so
  reviewers know exactly where to put feedback. Headings like "Requirements",
  "Responsibilities", and "What We Offer" are cleaner boundaries than
  "Thoughts" or "Misc".

- **Collaborators pick their lane.** A hiring manager might focus on
  Requirements; a senior engineer might focus on What You Will Do. Parallel
  section threads make this natural — there is no need to prefix every message
  with "re: the third bullet in section 4".

- **Approvals are granular.** A collaborator can react ✅ on sections they are
  satisfied with while leaving sections they are still thinking about open. The
  owner can see at a glance which sections are settled and which need more
  iteration.

- **Revisions are targeted.** Because feedback is attributed to specific
  sections, the owner can revise section by section rather than re-reading
  the entire plan for every comment.

#### Section-level approval from the owner side

Once the owner has incorporated feedback and is ready to sign off on individual
sections:

```
/wg-sync research-scientist --overview
```

This shows which sections are approved (✅) and which are still open. To approve
a specific section:

```
/wg-approve research-scientist --section-ts 1771538032.123456
```

A ✅ reaction appears on that section's Slack message. When all sections are
approved (or when the owner is satisfied with the whole plan):

```
/wg-approve research-scientist
```

This approves the plan as a whole and adds ✅ to the latest plan revision.

---

### Collaborator: Slack-Only Mode

No installation needed. Just reply in Slack.

- For **single-section plans**: one top-level message per plan — reply in its thread
- For **multi-section plans**: an anchor overview message plus one top-level message per section — reply in whichever section thread is relevant to your feedback
- React ✅ (`white_check_mark`) on a section message to approve that section, or on the anchor / any plan reply to approve the whole plan

That's it. The plan owner's Claude session receives your feedback automatically — no setup, no daemon, no Claude Code required.

---

### Collaborator: Daemon Mode

**Step 1 — Accept the Slack invite**

When you receive the DM from the bot with a channel invite, click the direct
link to open `#wg_<name>` in Slack.

**Step 2 — Join via Claude Code**

In your project directory:

```
/wg-join <channel-name>
```

Claude bootstraps your local state from Slack history (fetching all existing
plans and feedback), then asks whether you want to contribute a plan or give
feedback on existing ones.

**Contributing a plan:**

Claude walks you through formulating a plan for your piece of the work, then
posts it as a new top-level thread in the channel. Your session is now linked
to that thread. You can iterate with `/wg-sync` and `/wg-approve` just like
the channel owner.

**Giving feedback on an existing plan:**

Claude shows you the existing plans (from `/wg-status`). You can link your
session to a specific thread and draft a response, or reply directly in Slack.

---

### Full Team Multi-Plan Flow

Three engineers working on related parts of the same feature:

```
Alice (auth-middleware)          Bob (session-store)             Carol (API gateway)
│                                │                               │
│ /wg feature-auth U_Bob U_Carol │                               │
│ → creates #wg_feature-auth     │                               │
│ → posts Plan v1 :111           │                               │
│                                │ /wg-join feature-auth         │
│                                │ → bootstraps local state      │
│                                │ → /wg-plan                    │
│                                │ → posts Plan v1 :222          │
│                                │                               │ /wg-join feature-auth
│                                │                               │ → bootstraps local state
│                                │                               │ → /wg-plan
│                                │                               │ → posts Plan v1 :333
│                                │                               │
│ 🔔 feedback on :111 from Carol │ 🔔 feedback on :222 from Alice│
│ /wg-sync → revise → v2        │ /wg-sync → revise → v2       │
│                                │                               │
│                          /wg-status feature-auth               │
│                          → :111 ⏳ v2  :222 ⏳ v2  :333 ✅ v1 │
│                          → ⚠️ :111 and :222 both touch auth/   │
│                                │                               │
│ /wg-approve → ✅ on :111       │ /wg-approve → ✅ on :222     │
│                                │                               │
│                          /wg-list → #wg_feature-auth  3 plans (all approved)
│                                │                               │
│ /wg-close feature-auth → archived                             │
```

At any point, `/wg-list` gives an overview of all your working group channels:

```
#wg_feature-auth      3 plans (2 open, 1 approved)  last: 5m ago  ⚠️ conflict
#wg_api-redesign      1 plan  (1 open)               last: 2h ago
#wg_perf-q1           2 plans (0 open, 2 approved)   last: 1d ago
```

---

## Skills Reference

All skills are invoked inside a Claude Code session by typing the skill name.

| Skill | When to use |
|-------|-------------|
| `/wg <name> [U... U...]` | **Start a working group.** Create the channel, post your first plan, invite collaborators. Collaborators optional for solo testing. |
| `/wg-plan [channel]` | **Post a new plan thread** in an existing channel. Works from any Claude session. |
| `/wg-sync [channel] [thread-ts]` | **Pull feedback** on your plan into the current session. Pass `channel` to target any thread from the global registry without a session file. Prompts you to revise if feedback exists. |
| `/wg-approve [channel] [thread-ts]` | **Approve your own plan.** Marks the latest version as final and adds a ✅ reaction to the most recent plan post in Slack. |
| `/wg-status [channel]` | **Overview of a channel**: every plan's owner, version, feedback count, approval state, and any file conflicts. Suggests next actions. |
| `/wg-list` | **Overview of all channels** you're tracking locally. Sorted by last activity. Shows conflict warnings and approved counts. |
| `/wg-join <channel>` | **Collaborator entrypoint.** Bootstraps local state from Slack history, then guides you to contribute a plan or give feedback. |
| `/wg-close <channel>` | **Wrap up.** Archives the Slack channel and clears the local session file. Warns about unapproved plans first. |

---

## CLI Reference

The underlying CLI at `~/.claude/wg/cli.py` (invoked via
`~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py`) supports these subcommands.
Skills call these for you; you rarely need to invoke them directly.

| Subcommand | Key arguments | What it does |
|------------|--------------|-------------|
| `create` | `--channel`, `--collaborators`, `--plan-file/--plan-text`, `--files`, `--session-dir` | Create channel, invite users, post plan, save state |
| `plan` | `--channel`, `--plan-file/--plan-text`, `--files`, `--session-dir` | Post a new plan thread in an existing channel |
| `reply` | `--plan-file/--plan-text`, `--files`, `--channel` (opt), `--thread-ts` (opt), `--session-dir` | Post a revision. Pass `--channel` to bypass session file; `--thread-ts` to disambiguate when you own multiple threads. |
| `sync` | `--channel` (opt), `--thread-ts` (opt), `--overview`, `--section-ts`, `--session-dir` | Print feedback + current plan text. `--overview` lists sections with feedback counts. `--section-ts <ts>` shows one section's feedback. Pass `--channel` to target any thread from the global registry without a session file. |
| `approve` | `--channel` (opt), `--thread-ts` (opt), `--section-ts` (opt), `--session-dir` | Mark plan approved, add ✅ reaction to the latest reply. Pass `--section-ts` to approve a single section of a multi-section plan. |
| `status` | `--channel` | Print all threads with feedback counts and conflict warnings |
| `list` | `--open-only` | List all tracked channels sorted by last activity |
| `link` | `--channel`, `--thread-ts`, `--session-dir` | Manually link a session to a thread |
| `bootstrap` | `--channel` | Fetch Slack history and populate local state (for new collaborators) |
| `close` | `--channel`, `--session-dir` | Archive the channel and delete the session file |

---

## State and Files

### File layout

```
~/.claude/
├── wg/
│   ├── config.json          # Slack tokens + user ID (chmod 600)
│   ├── daemon.py            # Slack Socket Mode listener
│   ├── cli.py               # CLI used by skills
│   ├── state.py             # Shared state helpers
│   ├── daemon.log           # Daemon stdout
│   ├── daemon.err           # Daemon stderr
│   ├── venv/                # Python virtualenv
│   └── channels/
│       ├── wg_feature-auth.json
│       └── wg_api-redesign.json
└── commands/                # Claude Code custom slash commands
    ├── wg.md
    ├── wg-plan.md
    ├── wg-sync.md
    ├── wg-approve.md
    ├── wg-status.md
    ├── wg-list.md
    ├── wg-join.md
    └── wg-close.md

<project_dir>/
└── .claude/
    └── wg_session.json      # Links this session to a channel:thread_ts
```

### Channel state schema

`~/.claude/wg/channels/<channel_name>.json`

```json
{
  "channel_id": "C08XXXXXX",
  "channel_name": "wg_feature-auth",
  "created_by": "U123",
  "collaborators": ["U456", "U789"],
  "threads": {
    "1234567890.111111": {
      "owner": "U123",
      "ts": "1234567890.111111",
      "version": 2,
      "status": "awaiting_feedback",
      "approved": false,
      "approved_by": null,
      "files": ["auth/middleware.py", "auth/tokens.py"],
      "latest_reply_ts": "1234567890.333333",
      "plan_versions": [
        {
          "version": 1,
          "text": "## Plan v1\n\nProposed approach...",
          "posted_at": "2026-02-19T10:00:00Z"
        },
        {
          "version": 2,
          "text": "## Plan v2\n\nRevised approach...",
          "posted_at": "2026-02-19T10:45:00Z",
          "ts": "1234567890.333333"
        }
      ],
      "feedback": [
        {
          "user": "U456",
          "ts": "1234567890.222222",
          "text": "Consider the token refresh edge case",
          "type": "feedback",
          "received_at": "2026-02-19T10:32:00Z"
        },
        {
          "user": "U123",
          "ts": "1234567890.333333",
          "text": "Plan v2 — added token refresh handling",
          "type": "revision",
          "received_at": "2026-02-19T10:44:00Z"
        }
      ],

      // ── Multi-section plans only ──────────────────────────────────────────
      // Present when the plan contains h1–h3 headings. Each section is a
      // separate top-level Slack message; section_index maps section ts → index.
      "sections": [
        {
          "heading": "## Section 1: Approach",
          "body": "We will...",
          "ts": "1234567890.444444",
          "feedback": [
            {
              "user": "U456",
              "ts": "1234567890.555555",
              "text": "Looks good",
              "type": "feedback",
              "received_at": "2026-02-19T11:00:00Z"
            }
          ]
        }
      ],
      "section_index": {
        "1234567890.444444": 0
      }
    }
  }
}
```

### Session file schema

`<project_dir>/.claude/wg_session.json`

```json
{
  "channel": "wg_feature-auth",
  "thread_ts": "1234567890.111111",
  "linked_at": "2026-02-19T10:00:00Z"
}
```

This file is written by `create`, `plan`, and `link`, and deleted by `close`.

---

## Troubleshooting

**Daemon not running:**
```bash
launchctl load ~/Library/LaunchAgents/com.claude.wg.plist
tail -f ~/.claude/wg/daemon.err
```

**"No state for wg_X" after being invited:**
Run the bootstrap command to pull Slack history into local state:
```bash
~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py bootstrap --channel <name>
```
Or use `/wg-join <name>` which does this automatically.

**Reactions not received:**
Ensure `reaction_added` is listed under Bot Events in your Slack app's
Event Subscriptions. The bot must be a member of the channel (it is, since
it creates all `wg_*` channels).

**"Channel not found" in bootstrap:**
The bot must be a member of the channel. Only channels created via `/wg` or
`/wg-plan` (which use the bot token) will be visible. Verify with:
```bash
~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py list
```

**Skill not found:**
Verify skills are in `~/.claude/commands/`:
```bash
ls ~/.claude/commands/wg*.md
```
If any are missing, re-run `./install.sh` (it will ask before overwriting the config).

**"/wg-sync" reports the wrong channel or "is archived":**
The session file in your project directory (`.claude/wg_session.json`) still
points to an old or archived channel. Pass `--channel` explicitly to target
any active thread from the global registry:
```
/wg-sync <channel-name>
```
The session file is a convenience cache — it is never required.

**`my_slack_user_id` must be a real Slack user ID:**
The value in `~/.claude/wg/config.json` must be your Slack user ID in
`U0XXXXXXX` format (not a display name). To find it: Slack → Profile → ⋯ →
Copy member ID. Ownership inference (used by `sync`, `reply`, `approve` when
`--thread-ts` is omitted) compares this value against the `owner` field stored
in each thread.

**Conflict warning ⚠️:**
Two open plans in the same channel declare overlapping files in `--files`.
Coordinate with the other plan's owner. Once one plan is approved or the
file lists are corrected, the warning clears.
