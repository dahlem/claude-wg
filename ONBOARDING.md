# Onboarding — claude-wg Collaborator Guide

You've been invited to a `wg_*` working group channel. This document explains
how to participate, from zero setup to full Claude Code integration.

---

## Option A — Slack Only (no setup required)

You don't need to install anything. Just reply in Slack:

- Each top-level message in the channel is a **plan** posted by a teammate's
  Claude session.
- **Reply in the thread** to give feedback — the plan owner's daemon picks it
  up automatically and routes it into their Claude Code session.
- **React ✅** (`white_check_mark`) on any message in a thread to signal
  approval of that plan.

---

## Option B — Daemon Mode (full Claude Code integration)

With daemon mode your Claude Code session can post its own plans, receive
feedback, and iterate — all without leaving your terminal.

### Prerequisites

- Python 3.10+
- Claude Code installed
- Member of the shared Slack workspace with the same bot installed

### Install

```bash
git clone https://github.com/yourorg/claude-wg
cd claude-wg
./install.sh
```

The installer will prompt for:
- Your Slack bot token (`xoxb-...`) — get this from whoever created the app
- Your Slack app-level token (`xapp-...`)
- Your Slack user ID

> **Getting your Slack user ID:** In the Slack desktop app, click your name →
> **Profile** → three-dot menu → **Copy member ID**. It looks like `U0XXXXXXX`.

### Verify the daemon is running

```bash
launchctl list | grep claude.wg
tail -f ~/.claude/wg/daemon.log
```

### Join a working group

In any Claude Code session in your project directory:

```
/wg-join <channel-name>
```

Claude bootstraps your local state from Slack history (so you see all existing
plans and feedback), then asks whether you want to contribute a plan or engage
with existing ones.

---

## Workflow at a Glance

```
Receive Slack invite to #wg_feature-auth
         │
         ├── Slack-only:
         │     Reply in threads
         │     React ✅ to approve
         │
         └── Daemon mode:
               /wg-join feature-auth
                    │
                    ├── Have a plan? → /wg-plan
                    │     Posts your plan as a new thread
                    │     /wg-sync ← pulls feedback when notified
                    │     /wg-approve → signals approval in Slack
                    │
                    └── Giving feedback?
                          /wg-status → see all plans + conflicts
                          Reply via Claude or directly in Slack
```

---

## Skills Reference (Daemon Mode)

| Skill | What it does |
|-------|-------------|
| `/wg-join <name>` | Connect to a channel; bootstraps local state from Slack history |
| `/wg-plan [name]` | Post your plan as a new thread in the channel |
| `/wg-sync` | Pull feedback on your plan into this session, with current plan text for context |
| `/wg-approve` | Mark your plan as final; adds ✅ reaction in Slack |
| `/wg-status [name]` | Show all plans in a channel with approval state and conflict warnings |
| `/wg-list` | Overview of all working group channels you're tracking |
| `/wg-close <name>` | Archive the channel (typically the channel creator does this) |

---

## Privacy

Working group channels are **private**. Only explicitly invited members and the
bot can see them. Plans, feedback, and state files stay within your team's
workspace and machines.
