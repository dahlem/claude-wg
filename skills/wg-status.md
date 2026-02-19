# /wg-status — Show Working Group Status

## Usage
```
/wg-status [channel-name]
```

If `channel-name` is omitted, reads the channel from `.claude/wg_session.json`
in the current project directory.

## What to do

1. **Resolve the channel name:**
   - If provided as an argument, use it directly.
   - If omitted, read `.claude/wg_session.json` in `$PWD` to get the channel.
   - If neither is available, ask the user which channel to check.

2. **Fetch status:**
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py status --channel <channel-name>
   ```

3. **Parse and present the output** clearly to the user:
   - For each plan thread, show:
     - Owner (highlight if it belongs to the current user's session)
     - Plan version number
     - Number of feedback items
     - Approval state (✅ approved / ⏳ awaiting)
     - Files this plan affects (if any)
   - If any ⚠️ conflict warnings appear in the output, call them out prominently:
     "⚠️ **Conflict detected**: threads [A] and [B] both touch [file]. Coordinate
     with collaborators before merging."

4. **Suggest next actions based on state:**
   - If the user's plan is **approved** (✅): "Your plan is approved! Run
     `/wg-close <channel>` when all plans in this channel are done."
   - If there is **pending feedback**: "Run `/wg-sync` to pull in feedback
     and iterate on your plan."
   - If there are **unapproved plans from others**: mention them so the user
     can review in Slack and add a ✅ reaction if satisfied.

## Notes
- Status reads from local state; no Slack API call is made.
- To refresh state with the latest Slack activity, the daemon must be running.
  If the daemon is not running, remind the user: "Daemon may be offline — run
  `launchctl start claude.wg` to restart it."
