# /wg-sync — Pull Feedback Into This Session

## Usage
```
/wg-sync [channel] [thread-ts]
```

Syncs feedback for a plan thread. Targets are resolved in this order:
1. `channel` + `thread-ts` arguments → explicit, works for any thread
2. `channel` argument alone → looks up threads in the global registry owned by you; auto-selects if exactly one, otherwise lists and asks for `thread-ts`
3. No arguments → falls back to `.claude/wg_session.json` in the project directory

Works from **any Claude session** — no project-local session file required.

## What to do

1. **Resolve the target thread:**

   a. If the user provided `channel` (and optionally `thread-ts`):
      ```bash
      ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py sync \
        --channel <channel> [--thread-ts <ts>]
      ```

   b. If no arguments and a session file exists in `$PWD`:
      ```bash
      ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py sync --session-dir "$PWD"
      ```

   c. If neither works, run `/wg-status <channel>` to list available threads,
      then ask the user which to target and re-run with `--channel` + `--thread-ts`.

2. **Check whether the plan is multi-section:**

   Run the overview mode to detect sections:
   ```bash
   ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py sync \
     --overview --channel <channel> [--thread-ts <ts>]
   ```

   - If the output says "This plan has no sections", skip to step 3 (single-message flow).
   - If sections are listed, proceed to step 2a (multi-section parallel sync).

   **2a. Multi-section parallel sync:**

   The overview output lists each section's heading, timestamp (`ts:`),
   feedback count, and approval state (✅ if approved). For every section that
   has feedback (`[N feedback items]`):

   Use the Task tool to spawn **one subagent per section** in parallel (all in
   a single message, using multiple Task tool calls). Each subagent should:

   ```
   subagent_type: Bash
   prompt: |
     Run this command and return the full output:
     ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py sync \
       --section-ts <section_ts> --channel <channel> [--thread-ts <thread_ts>]
     Then synthesise the feedback in 2-3 sentences covering: key concerns raised,
     any blocking issues, and overall sentiment. Return: HEADING + SYNTHESIS.
   ```

   Wait for all subagents to complete, then collect their syntheses and present
   a unified summary to the user (one section per block).

3. **Single-message plan — read output carefully.** It contains:
   - Channel and thread metadata
   - Approval status
   - The current plan version text (for reference)
   - Each feedback item: author, timestamp, text

4. **If no feedback yet (any mode):** Tell the user "No feedback received yet on your
   plan. Check back later or ask collaborators to respond in Slack."

5. **If feedback exists (any mode):** Synthesise and present to the user:
   - For multi-section: one synthesis block per section (from subagents)
   - For single-message: summarise all feedback, areas of agreement/disagreement,
     blocking concerns, suggested revisions

6. **Ask the user:** "Would you like to revise the plan based on this feedback?
   If so, let's work on the next version and I'll post it as a reply."

7. **If the user wants to revise:**
   - Work through the plan revision together
   - Ask: "Which files will this revised plan modify? (Comma-separated paths, or enter to keep the same.)"
   - Write the revised plan to `/tmp/wg_plan.md`
   - Post the revision (use `--channel` to avoid session-file dependency):
     ```bash
     ~/.claude/wg/venv/bin/python ~/.claude/wg/cli.py reply \
       --plan-file /tmp/wg_plan.md \
       --channel <channel> [--thread-ts <ts>]
     ```
     Add `--files "path/to/file.py"` if files changed.
   - Confirm: "Plan v<N> posted. Waiting for further feedback."

8. **If the plan is already approved (✅):**
   - Congratulate the user
   - Suggest running `/wg-close <channel>` if all plans in the channel are done

## Notes
- The global registry lives in `~/.claude/wg/channels/` and is maintained by
  the daemon independently of any working directory or Claude session.
- `--channel` alone is sufficient when you own exactly one thread in that channel.
- When you own multiple threads in the same channel, `--thread-ts` is required
  to disambiguate (the CLI will list your threads and prompt you).
- The session file (`.claude/wg_session.json`) is a convenience cache — it is
  written when you create or post a plan, but is never required if you pass
  `--channel`.
