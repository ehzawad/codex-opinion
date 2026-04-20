# Context-building patterns

Direct-CLI patterns for `ask_codex.py`. Claude Code's normal path composes context into a heredoc; these are for direct shell use, or when the raw diff/file content *is* the evidence.

## Uncommitted changes

```bash
git diff HEAD | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

## Uncommitted + untracked, with binary/size guards

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

## Clean tree, composed context

```bash
cat <<'EOF' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
<what, why, constraints, evidence, exact question for Codex>
EOF
```

## Custom instruction overrides the default

```bash
echo "<context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py "focus on migration risks"
```

The positional arg replaces `DEFAULT_INSTRUCTION` and is also bookended around stdin.

## Exact stdin passthrough, no wrapper

```bash
echo "<pre-composed context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py --no-default-instruction
```

## Guardrails

- Empty stdin → script exits non-zero with a clear error. Never pipe from a command that might produce nothing (e.g., `git diff HEAD` on a clean tree).
- For codework, inlining `git diff HEAD` beats path references when the diff is the evidence Codex needs to see.
- Binary files and files >32 KB are skipped in the untracked-files snippet to avoid polluting context with bytes Codex can't use.
