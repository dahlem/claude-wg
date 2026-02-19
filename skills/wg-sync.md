# /wg-sync — Pull Feedback Into This Session

## Usage
```
/wg-sync
```

No arguments. Operates on the plan thread linked to the current session
(stored in `.claude/wg_session.json` in the project directory).

## What to do

1. **Retrieve feedback:**
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py sync --session-dir "$PWD"
   ```

2. **Read the output carefully.** It contains:
   - Channel and thread metadata
   - Approval status
   - The current plan version text (for reference)
   - Each feedback item: author, timestamp, text

3. **If no feedback yet:** Tell the user "No feedback received yet on your
   plan. Check back later or ask collaborators to respond in Slack."

4. **If feedback exists:** Synthesise the feedback and present it to the user:
   - Show the current plan version so the user has context
   - Summarise the key points raised by each collaborator
   - Identify areas of agreement vs. disagreement
   - Highlight any blocking concerns
   - Suggest how the plan might be revised

5. **Ask the user:** "Would you like to revise the plan based on this feedback?
   If so, let's work on the next version and I'll post it as a reply."

6. **If the user wants to revise:**
   - Work through the plan revision together
   - Ask: "Which files will this revised plan modify? (Comma-separated paths, or enter to keep the same.)"
   - Write the revised plan to `/tmp/wg_plan.md`
   - Post the revision:
     ```bash
     ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py reply \
       --plan-file /tmp/wg_plan.md \
       --session-dir "$PWD"
     ```
     Add `--files "path/to/file.py"` if files changed.
   - Confirm: "Plan v<N> posted. Waiting for further feedback."

7. **If the plan is already approved (✅):**
   - Congratulate the user
   - Suggest running `/wg-close <channel>` if all plans in the channel are done

## Notes
- Feedback is stored locally by the daemon. No network call needed to read it.
- You can run `/wg-sync` as many times as you like — it always shows the
  current cumulative feedback.
- Only feedback on YOUR thread (the one linked to this session) is shown.
