---
name: codex-opinion
description: Pipe your plan or diff to Codex for a second opinion. Invoke with /codex-opinion:codex-opinion.
---

# Codex Second Opinion

Get a second opinion from OpenAI Codex on your current work. Codex uses your configured model and settings.

## How to call

Two options — pick whichever fits:

### Option A: Foreground (Bash)

Use when you need Codex's response before proceeding.

```bash
echo "<gathered context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

### Option B: Background (Monitor)

Use when you want to keep working while Codex analyzes. Run the **same command** directly via Monitor — do NOT use TaskCreate, do NOT monitor a file, do NOT sleep+cat. Monitor runs the command itself and notifies you when output arrives.

```bash
echo "<gathered context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

Set Monitor timeout to at least **600** seconds. Codex can take several minutes.

## Building the context

If there are uncommitted changes:

```bash
git diff HEAD | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

If there are also **untracked files** that matter, include them:

```bash
{ git diff HEAD; echo "--- Untracked files ---"; git ls-files --others --exclude-standard | while read f; do echo "=== $f ==="; cat "$f"; done; } | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

If the tree is clean, gather context yourself:

```bash
echo "Review this codebase. Key files: ..." | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

With a custom instruction (from user text after `/codex-opinion:codex-opinion`):

```bash
echo "<context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py "user's instruction"
```

**Never pipe an empty string.** If `git diff HEAD` would be empty, use echo with gathered context instead.

## Session continuity

Sessions are scoped per Claude Code session and per project. Follow-up calls resume the prior Codex thread. When a new Claude Code session starts on the same project, it adopts the Codex thread from the previous session — Codex keeps its accumulated codebase knowledge. Concurrent Claude Code sessions on the same project get independent threads. If an adopted session has expired server-side, the script logs a notice and starts fresh.

## After Codex responds

Tell the user what Codex found.
