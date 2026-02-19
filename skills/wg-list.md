# /wg-list — List All Working Group Channels

## Usage
```
/wg-list
```

Lists all `wg_*` channels tracked locally, with counts and last-activity times.

## What to do

1. **Fetch the channel list:**
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py list
   ```
   To show only channels with open (unapproved) plans:
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py list --open-only
   ```

2. **Present the table** to the user. Each row shows:
   - Channel name
   - Total plans, broken down by open vs. approved
   - Time since last activity
   - ⚠️ conflict flag if two plans in that channel touch the same files

3. **For any channel with ⚠️ conflicts:**
   "Run `/wg-status <channel>` to see which plans conflict and which files
   are affected."

4. **For any channel with approved plans:**
   "If all plans in #wg_<name> are done, run `/wg-close <name>` to archive it."

5. **If the list is empty:**
   "No working group channels found. Run `/wg <name> <collaborators>` to create one."

## Notes
- The list is built from local state files in `~/.claude/wg/channels/`.
  It reflects what the daemon has observed; channels the daemon hasn't seen
  yet will not appear until bootstrapped (see `/wg-join`).
- Channels are sorted by most recent activity (message or feedback timestamp).
