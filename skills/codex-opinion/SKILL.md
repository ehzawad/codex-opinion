---
name: codex-opinion
description: Pipe your plan or diff to Codex for a second opinion. Invoke with /codex-opinion.
---

# Codex Second Opinion

Get a second opinion from OpenAI Codex on your current work. Codex runs at full capability.

## How to call

Pipe context to the script. You can run it **foreground** (Bash) or **background** (Monitor) — pick whichever fits.

- **Foreground**: use when you need Codex's response before proceeding.
- **Monitor**: use when you want to keep working while Codex analyzes. Claude gets notified when the response arrives.

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
