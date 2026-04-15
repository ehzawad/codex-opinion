---
name: codex-opinion
description: Pipe your plan or diff to Codex for a read-only second opinion. Invoke manually with /codex-opinion.
---

# Codex Second Opinion

Get a second opinion from OpenAI Codex on your current work.

## Execution rules (for Claude, not Codex)

1. Run the Bash call in the **foreground** (not run_in_background) so you can read stdout.
2. Set Bash timeout to **600000** (10 min). Codex may run commands, spawn subagents, or do heavy analysis — let it finish.
3. Construct context and pipe it in **one** Bash call.

## How to call

Always use `echo` or command substitution to build context, then pipe to the script in ONE foreground Bash call.

If there are uncommitted changes:

```bash
git diff HEAD | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

If the tree is clean or the user wants a general review, gather context yourself and pipe it:

```bash
echo "Review this codebase for issues. Key files: ..." | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

With a custom instruction (from user text after `/codex-opinion`):

```bash
echo "<gathered context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py "user's custom instruction here"
```

**Never pipe an empty string.** If `git diff HEAD` would be empty, use echo with gathered context instead.

The script auto-resumes Codex's prior session so it maintains context across calls.

## Rules

- **Max 2 calls** to the script per prompt.
- **Skip trivial changes** — typos, formatting, single-line fixes don't need a second opinion.
- **Fix what Codex catches** before responding to the user.
- **Summarize** what Codex found for the user. Don't dump raw output.
