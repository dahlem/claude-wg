# /wg-approve — Approve Your Plan

## Usage
```
/wg-approve
```

Marks the current session's plan as final and signals approval to collaborators
in Slack via a ✅ reaction.

## When to use

Use this when **you** (the plan owner) are satisfied with the current version
of your plan and want to signal to collaborators that the iteration is complete.

This is distinct from collaborators approving your plan (which they do by
reacting ✅ in Slack). `/wg-approve` is the owner's explicit sign-off from
within Claude Code.

## What to do

1. **Show current state** so the user can make an informed decision. Run:
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py sync --session-dir "$PWD"
   ```
   Present the current plan version and a summary of any feedback received.

2. **Confirm intent.** Ask the user:
   "Are you satisfied with this plan? Approving will signal to all collaborators
   in Slack that this plan is final (a ✅ reaction will be added to your plan
   post). You can still edit the plan later, but this marks the current version
   as your preferred outcome."

3. **If yes, approve:**
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py approve \
     --session-dir "$PWD"
   ```

4. **Confirm to the user:**
   "Plan approved. Your collaborators can see ✅ on the plan in Slack."

5. **Suggest next steps:**
   "Run `/wg-list` to see if other plans in this channel also need closing, or
   run `/wg-close <channel>` when all plans in the channel are done."

## Notes
- The `approve` command adds a ✅ (`white_check_mark`) reaction to the plan's
  top-level Slack message, making approval visible to all channel members.
- If you want to approve a specific channel rather than the current session's
  channel, you can pass `--channel <name>` directly to the CLI.
- Approval state is also stored in the local state file and will appear in
  `/wg-status` and `/wg-list` output.
