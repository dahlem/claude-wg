# /wg-plan — Post a New Plan Thread

## Usage
```
/wg-plan [channel-name]
```

If `channel-name` is omitted, uses the channel from the current session's
`.claude/wg_session.json` (if one exists). If neither is available, ask the
user which channel to post to.

## What to do

1. **Capture the current plan.** Format the plan we have been discussing as
   clear markdown. Include:
   - Objective / problem statement
   - Proposed approach (bullet points or numbered steps)
   - Files/modules affected
   - Open questions or assumptions
   - What feedback you are specifically requesting

2. **Ask about affected files.** After capturing the plan, ask:
   "Which files will this plan modify? (List relative paths separated by commas, or press enter to skip.)"
   Save the answer for use in step 4.

3. **Write the plan to a temp file:**
   ```bash
   cat > /tmp/wg_plan.md << 'PLAN'
   <plan content here>
   PLAN
   ```

4. **Post it:**
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py plan \
     --channel <channel-name> \
     --plan-file /tmp/wg_plan.md \
     --session-dir "$PWD" \
     --files "path/to/file1.py,path/to/file2.py"
   ```
   If no files were provided, omit the `--files` flag.

5. **Confirm to the user:**
   - Plan posted as a new thread in `#wg_<name>`
   - thread_ts recorded for this session
   - "Run `/wg-sync` when you're ready to incorporate feedback."

## Notes
- One session = one plan thread. This session will only ever sync feedback
  from the thread just created.
- If you need another plan in the same channel, open a new Claude Code session
  and run `/wg-plan` there.
- Collaborators in Slack-only mode will see the plan immediately and can reply.
- Collaborators in daemon mode will get a macOS notification.
