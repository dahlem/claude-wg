# /wg-join — Join a Working Group Channel (Collaborator)

## Usage
```
/wg-join <channel-name>
```

Used by collaborators who have been invited to a `wg_*` channel and want to
link their Claude Code session so they can post plans and receive feedback.

## What to do

1. **Bootstrap local state if needed.** If the daemon may not have seen this
   channel yet (e.g. you were just invited, or you're on a new machine), run:
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py bootstrap --channel <channel-name>
   ```
   This fetches all existing plans and feedback from Slack history and populates
   your local state. Skip this step if you already see state for this channel.

2. **Verify the channel exists** and that the user has been invited:
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py status --channel <channel-name>
   ```
   If this returns "No state for..." after bootstrapping, ask the user to check
   they were invited in Slack.

3. **Ask the user:** "Do you have a plan to contribute to this working group,
   or are you joining to provide feedback on existing plans?"

4. **If they have a plan to contribute:**
   - Discuss and formulate the plan together
   - Then run `/wg-plan <channel-name>` to post it
   - This links their session to their new thread

5. **If they are joining to provide feedback only:**
   - Show them the existing plans using the status output from step 2
   - Explain that they can reply directly in Slack threads (Slack-only mode)
     OR ask them to specify which thread they want to engage with
   - If they want to engage via Claude: link their session to the relevant thread:
     ```bash
     ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py link \
       --channel <channel-name> \
       --thread-ts <thread_ts> \
       --session-dir "$PWD"
     ```
   - Then work with them to draft a thoughtful response and post it:
     ```bash
     ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py reply \
       --plan-text "<feedback text>" \
       --session-dir "$PWD"
     ```

## Notes
- Daemon mode requires the daemon to be running (`launchctl list | grep claude.wg`)
- Slack-only collaborators don't need to run this skill at all — they just
  reply in Slack threads directly
- The bootstrap command is safe to re-run; it merges with existing state without
  overwriting locally-tracked threads
