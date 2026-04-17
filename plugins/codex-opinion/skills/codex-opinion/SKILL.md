---
name: codex-opinion
description: Pipe your plan or diff to Codex for a second opinion. Invoke with /codex-opinion:codex-opinion. Triggers on natural-language requests for a Codex review or second opinion too.
argument-hint: [optional focus directive, e.g. "focus on security"]
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

If there are also **untracked files** that matter, include them. Use a NUL-delimited loop to handle filenames with spaces, newlines, or other special characters, and skip likely-binary files:

```bash
{
  git diff HEAD
  echo "--- Untracked files ---"
  git ls-files -z --others --exclude-standard | while IFS= read -r -d '' f; do
    if file --mime "$f" 2>/dev/null | grep -q 'charset=binary'; then
      echo "=== $f (binary, skipped) ==="
      continue
    fi
    echo "=== $f ==="
    cat "$f"
  done
} | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

If the tree is clean, gather context yourself:

```bash
echo "Review this codebase. Key files: ..." | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

**Never pipe an empty string.** If `git diff HEAD` would be empty, use echo with gathered context instead.

## Routing user intent to args

The script's optional CLI arg is a **focus directive** that gets appended to the default thorough-review prompt. It augments, never replaces. So passing a generic phrase doesn't hurt — but passing nothing keeps the prompt tight.

Decision table:

| User said | Pass arg? | Arg value |
|---|---|---|
| `/codex-opinion:codex-opinion` | no | — |
| `/codex-opinion:codex-opinion focus on security` | yes | `focus on security` |
| `/codex-opinion:codex-opinion check perf regressions` | yes | `check perf regressions` |
| `/codex-opinion:codex-opinion what do you think?` | no | — (it's just phrasing) |
| `/codex-opinion:codex-opinion second opinion?` | no | — |
| `read this and /codex-opinion:codex-opinion what is your opinion` | no | — (mid-sentence wrapper, not focus) |
| `ask codex what it thinks about this diff` | no | — |
| `ask codex to focus on the migration safety` | yes | `focus on the migration safety` |
| `get a second opinion on the auth refactor` | yes | `the auth refactor` |

Rule of thumb: if you can paraphrase the user as *"please specifically look at X"*, pass `X` as the arg. If you can only paraphrase as *"please run a review"*, omit the arg.

When in doubt: omit. The default prompt already covers correctness, bugs, regressions, risky assumptions, and trade-offs.

### Calling with a focus directive

```bash
echo "<context>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py "focus on security"
```

The script will send Codex: the default review prompt + a final line `Additional user focus: focus on security` + the piped context.

## Session continuity

One Codex session per project, persisted across Claude Code sessions. Follow-up calls resume the prior Codex thread so it keeps its accumulated codebase knowledge.

If the resume fails because the session is stale (server-side rollout missing), the script logs a notice and starts fresh. Other resume failures (auth, network, config) are surfaced verbatim and the script exits non-zero — it does NOT silently re-run, because the prompt may have non-idempotent side effects.

Concurrent invocations on the same project are allowed (independent Claude Code sessions can each run an opinion). The trade-off: a parallel first-time call may create a duplicate fresh thread. State writes are atomic, so the JSON file never corrupts.

## After Codex responds

Tell the user what Codex found.
