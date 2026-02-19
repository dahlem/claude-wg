# /wg — Create a Working Group Channel

## Usage
```
/wg <channel-name> [SlackUserID1 SlackUserID2 ...]
```

Examples:
- `/wg auth-refactor` — solo test (just you)
- `/wg auth-refactor U2H8K3P U9QRST4` — with collaborators

## What to do

When the user invokes `/wg`, follow these steps:

1. **Parse arguments** from the user's invocation:
   - `channel_name`: the first argument (e.g. `auth-refactor` → will become `wg_auth-refactor`)
   - `collaborators`: remaining arguments as Slack user IDs (e.g. `U2H8K3P U9QRST4`)

2. **Capture the current plan.** Ask the user: "Please describe the plan you want to share with the working group, or type 'use current' to use the plan we just discussed." Format the plan as clear markdown.

3. **Ask about affected files.** After capturing the plan, ask:
   "Which files will this plan modify? (List relative paths separated by commas, or press enter to skip.)"
   Save the answer for use in step 4.

4. **Create the channel and post the plan** by running:
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py create \
     --channel auth-refactor \
     --collaborators U2H8K3P U9QRST4 \
     --plan-file /tmp/wg_plan.md \
     --files "auth/middleware.py,auth/tokens.py"
   ```
   First write the plan markdown to `/tmp/wg_plan.md`, then run the command.
   - Omit `--collaborators` entirely if testing solo (no other users).
   - Omit `--files` if no files were provided.

5. **Record the session link.** The CLI outputs a `thread_ts`. The `create` command
   automatically links the session, so no separate `link` call is needed.

6. **Confirm to the user:**
   - Channel created: `#wg_<name>`
   - Collaborators invited: list their IDs
   - Plan posted as thread `<thread_ts>`
   - Collaborators have been sent a DM with a direct Slack link to the channel
   - "Run `/wg-sync` when you're ready to incorporate feedback."
   - "Run `/wg-plan` to post additional parallel plans to this channel."

## Notes
- Channel is private; only invited users and the bot can see it.
- The bot sends each collaborator a DM with onboarding instructions and a direct link to the channel.
- One session = one thread. If you need a second plan, open a new Claude session and run `/wg-plan`.
