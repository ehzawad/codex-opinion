---
name: codex-opinion
description: Pipe a Claude-authored prompt to Codex for a second opinion. Invoke with /codex-opinion:codex-opinion. Triggers on natural-language requests for a Codex review or second opinion too.
argument-hint: [usually empty — bake framing into stdin instead]
---

# Codex Second Opinion

Get a second opinion from OpenAI Codex. Codex uses your configured model and settings.

**Core idea:** the script is a pure transport. You (Claude) craft a complete, self-framed prompt in stdin. There is no default framing inside the script — whatever you pipe in is exactly what Codex sees. On the first call for a project, your framing establishes the role; follow-up calls resume the same Codex thread, so Codex remembers the framing and you only need to send new context.

## How to call

Two options — pick whichever fits:

### Option A: Foreground (Bash)

Use when you need Codex's response before proceeding.

```bash
echo "<full prompt>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

### Option B: Background (Monitor)

Use when you want to keep working while Codex analyzes. Run the **same command** directly via Monitor — do NOT use TaskCreate, do NOT monitor a file, do NOT sleep+cat.

```bash
echo "<full prompt>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

Set Monitor timeout to at least **600** seconds. Codex can take several minutes. The script itself does not enforce any timeout on Codex — outer layers like Monitor are the cap.

## Authoring the prompt

The prompt you pipe in should have three things, in order:

1. **Framing** — who Codex is and what you want (e.g., "Give me a second opinion on the diff below. Flag correctness bugs, risky assumptions, and anything I might have missed.").
2. **User focus** (optional) — anything specific the user asked you to direct Codex's attention toward.
3. **Context** — the diff, files, plan, or question body.

You don't need framing on every turn. The **first** call for a project establishes the role; Codex remembers it across resume. On follow-up turns, a one-line pointer ("New diff — your thoughts?") plus the new context is enough.

### First-call templates

Second opinion on a diff:

```bash
{
  echo "Give me a second opinion on the diff below. Flag correctness bugs, risky assumptions, incomplete handling, and design trade-offs. If nothing material stands out, say so."
  echo
  git diff HEAD
} | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

Focused review (user asked for security / perf / etc.):

```bash
{
  echo "Review the diff below with specific focus on security vulnerabilities. Still flag anything else material, but prioritize security."
  echo
  git diff HEAD
} | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

Design / approach feedback (no diff yet):

```bash
{
  echo "I'm planning an implementation. Here's my approach — tell me what could go wrong, what I'm missing, and whether there's a better path."
  echo
  echo "<plan text>"
} | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

Bug hunt on a clean tree:

```bash
{
  echo "Read the codebase at this path and hunt for correctness bugs, race conditions, and unhandled edge cases. Prioritize actionable findings."
  echo
  echo "Start from: <key file path>"
} | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

### Follow-up-call templates

When the session is resumed, Codex already knows the project and the role — keep it short:

```bash
{
  echo "New diff adding <feature>. Same framing as before — what do you think?"
  echo
  git diff HEAD
} | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

```bash
echo "Re-check the repo now that I've fixed the issues you flagged last turn." \
  | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

## Gathering context

If there are uncommitted changes:

```bash
git diff HEAD
```

If there are also **untracked files** that matter, include them with a NUL-safe loop that skips binaries:

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
}
```

Combine with your framing by piping through a grouped block as shown in the templates above.

**Never pipe an empty string.** Always include at least a framing line.

## CLI positional argument

The script accepts an optional positional argument that gets prepended to stdin with a blank-line separator. It exists for direct CLI convenience:

```bash
echo "<context>" | ask_codex.py "Review this for bugs."
```

When invoking through this skill, **leave it empty** and bake everything into stdin instead. That keeps the prompt structure visible in the Bash command and avoids splitting framing between two places.

## Session continuity

One Codex session per project, persisted across Claude Code sessions. Follow-up calls resume the prior Codex thread so it keeps its accumulated codebase knowledge and framing.

If the resume fails with a known stale-session error (the stored thread is missing or expired server-side — matched against a case-insensitive list of markers like `no rollout found`, `thread not found`, `session expired`), the script logs a notice and starts fresh. Any other resume failure — auth, network, config, or a clean exit with no agent message — is reported with its stderr (and a short diagnostic for the no-message case), and the script exits non-zero. It does NOT silently re-run, because the prompt may have non-idempotent side effects under Codex's full filesystem access.

Concurrent invocations across different projects are fully isolated — each project keys to its own state file and Codex thread. Concurrent invocations on the same project share a thread once a session exists, so parallel turns can interleave and muddle the review output. State writes are atomic (the JSON file never corrupts); the worst case is a wasted re-learning round or a momentarily confused opinion, never lost work.

## After Codex responds

Tell the user what Codex found.
