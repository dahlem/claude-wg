# /wg-close — Close a Working Group

## Usage
```
/wg-close <channel-name>
```

Archives the Slack channel, marks the working group as complete, and deletes
the local session file for this project directory.

## What to do

1. **Check status first:**
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py status --channel <channel-name>
   ```

2. **Verify with the user:** Show them any plans that are not yet approved (⏳).
   Ask: "The following plans are not yet approved: [list]. Are you sure you
   want to close the working group?"

3. **If confirmed, archive the channel:**
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py close \
     --channel <channel-name> \
     --session-dir "$PWD"
   ```

4. **Confirm:** "Working group #wg_<name> has been archived and your session
   file has been cleared. The state file remains at
   ~/.claude/wg/channels/wg_<name>.json for reference."

## Notes
- Archiving is reversible in Slack (workspace admins can unarchive)
- State files are kept locally — you can always review past feedback
- The `--session-dir` flag tells the CLI which project's `.claude/wg_session.json`
  to remove; if you're closing from a different directory, adjust accordingly
