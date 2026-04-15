---
name: codex-opinion
description: Pipe your plan or diff to Codex for a second opinion. Invoke with /codex-opinion.
---

# Codex Second Opinion

Get a second opinion from OpenAI Codex on your current work. Codex runs at full capability.

## How to call

Run the script in the **foreground** so you can read stdout. Pipe context in one Bash call.

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

The script auto-resumes Codex's exact prior session by stored session ID.

## After Codex responds

Tell the user what Codex found.
