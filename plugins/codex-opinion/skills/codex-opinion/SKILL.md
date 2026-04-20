---
name: codex-opinion
description: Second opinion from OpenAI Codex — you, Claude, and Codex in the loop. Invoke /codex-opinion:codex-opinion, or naturally via phrases like "ask codex," "second opinion," "another perspective," "codex weigh in," "reconcile with codex."
---

# Codex Second Opinion

Get a second opinion from OpenAI Codex on your current work. Codex uses your configured model and settings.

## How to call

Call with your context on stdin. Codex can take several minutes; use Bash `run_in_background: true` and wait for Claude Code's completion notification instead of sleep-polling.

```bash
echo "<gathered context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

The script bookends stdin with a short default review directive. Pass a positional arg to override it, or `--no-default-instruction` to skip the wrapper entirely.

## Building the context

If there are uncommitted changes:

```bash
git diff HEAD | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

If there are also untracked files that matter, include them (with binary/size guards):

```bash
{ git diff HEAD
  git ls-files --others --exclude-standard | while IFS= read -r f; do
      file --mime "$f" | grep -q 'charset=binary' && continue
      [ $(wc -c <"$f") -gt 32768 ] && continue
      printf '\n=== %s ===\n' "$f"
      cat "$f"
  done
} | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
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

One Codex session per project, persisted across Claude Code sessions. Follow-up calls resume the prior Codex thread so it keeps its accumulated codebase knowledge. If the session has expired server-side, the script logs a notice and starts fresh.

Set `CODEX_OPINION_SESSION_KEY` before launching Claude Code to isolate a session from the project-wide thread.

## After Codex responds

Tell the user what Codex found.
