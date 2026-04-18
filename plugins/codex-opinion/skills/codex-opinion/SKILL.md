---
name: codex-opinion
description: Three-brain collaboration with OpenAI Codex (human + Claude + Codex) on any task. Claude briefs Codex; they reconcile to catch wrong/missing assumptions. Invoke /codex-opinion:codex-opinion, or naturally via phrases like "ask codex," "second opinion," "another perspective," "sanity-check this," "codex weigh in," "reconcile with codex."
argument-hint: [usually empty — compose the briefing into stdin]
---

# Codex three-brain collaboration

Codex runs in its own process with full filesystem access; its working root is this repo. Each invocation is a three-way collaboration — human, Claude, Codex. Codex is not only an after-the-fact reviewer; use it as a collaborator, critic, or reviewer depending on the task. All three brains watch for wrong assumptions, missing cases, and incomplete thinking. Your job is to brief Codex on the current moment, get its take, and reconcile — not forward and relay.

Codex cannot see Claude-only state: this conversation's history, transient command output, browser/tool state, external docs, user constraints you inferred from memory. If it's material, brief it. Repo files, git state, and anything Codex can produce by running commands — leave for Codex to fetch directly.

## Philosophy — baked in, not adaptive

These principles hold across every invocation regardless of task. Human, Claude, Codex — same floor for all three. The briefing adapts to the moment; the floor does not.

- **Don't rot the context window — and don't starve it either.** Include every material fact Codex needs to catch wrong/missing/incomplete assumptions (tried paths, current hypotheses, constraints, specific errors, the actual user text). Cut only the procedural fluff around those facts. Distillation preserves substance; summarization strips it. A summary-only briefing is worse than a dump — Codex can't challenge what it can't see.
- **Don't panic.** Unexpected state, errors, and disagreements are not emergencies. Find root causes before any destructive or expensive move.
- **Don't cheat.** No shortcuts that trade correctness for a quick answer. No silently suppressing inconvenient findings.
- **Don't lie.** Never claim findings you didn't verify, successes you didn't observe, or confidence you don't have. Uncertainty is honest; false certainty corrodes reconciliation.
- **Don't rush.** A thoughtful second opinion beats a fast one. Codex running long is fine; Codex answering shallowly is not.
- **Don't be sycophantic.** Three brains agreeing by default is three brains pretending to be one. Surface disagreement with evidence, not politeness.
- **Wrong, incomplete, and missing assumptions are the origin of bugs and misalignments.** Reconciliation's main job is to surface them — in Claude's briefing, in Codex's reply, in the user's framing, in prior memory or decisions.

Include a brief marker of this philosophy in your first briefing per project so Codex's role-setting inherits it. On follow-up calls, restate it if you detect any brain drifting (sycophancy creep, hand-wavy certainty, rushed conclusions, unverified claims).

## Script contract

Pure transport. Whatever you pipe to stdin is exactly what Codex sees. No default framing, no auto-bundling, no templates. You own the prompt every call.

First call per project establishes Codex's role; later calls resume the same thread, so Codex keeps accumulated codebase knowledge. **Reframe explicitly when the task shifts** (debug → plan → design → review → ...). Prior framing biases later answers if left unchecked. If the thread has drifted beyond what a reframe can steer, delete the state file to start clean: state lives under `$XDG_STATE_HOME/codex-opinion/` (default `~/.local/state/codex-opinion/`) as `{hash}.json`; the matching file for this project has a `project_path` field equal to the repo root, so `grep -l "$(git rev-parse --show-toplevel)" "${XDG_STATE_HOME:-$HOME/.local/state}/codex-opinion/"*.json` finds it.

## How to call

Foreground (Bash) — when you need Codex's answer before proceeding:

```bash
echo "<briefing>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

For multi-line briefings, use a brace-group or heredoc to produce the text on the left of the pipe. The shell mechanism doesn't matter; what lands on stdin is what Codex sees.

Background (Monitor) — run the **same command** directly via Monitor. Not TaskCreate, not file-polling. Set Monitor timeout ≥ 600s; Codex can legitimately take several minutes. The script enforces no timeout of its own.

Never pipe empty input — the script rejects it.

## Composing the briefing

No template, no recipe. Each call is adaptive to the moment — include what's material, skip what isn't.

**Diff is a default include.** When the task touches uncommitted changes, inline `git diff HEAD` in the briefing as belt-and-suspenders — Codex may or may not run the command itself, and inlining the diff guarantees a shared view. Skip it when the task doesn't touch uncommitted work.

**Other repo content is not.** Codex has full filesystem access and its own bash; don't bulk-pipe files, directory dumps, or whole-tree content unless there's a specific reason Codex can't fetch it (transient output, scratch content outside the repo, etc.). Tell Codex where to look, not what's there.

Things to weigh — use what applies, skip what doesn't. Do not pad the briefing to cover every axis; a short briefing with the right uncertainty beats a complete-looking checklist.

- **Where we are now.** Phase of work (exploring / planning / stuck / implementing / reviewing) and enough distilled context from the recent conversation for Codex to land in the same moment you and the human are in. How much is "enough" is a judgment call each time — adapt; you and Codex are both good at this.
- **What the user asked**, plus your reading of what they really want — not just the literal words.
- **Your current interpretation, assumptions, and what you've already tried** — concise, explicit enough that Codex can challenge specifics. Not a raw reasoning dump.
- **The uncertainty or decision point** — where you expect Codex's input to carry weight.
- **Specific ask and output shape** — bullets, counter-proposal, terse verdict, deep dive, plan. Codex calibrates to this.
- **Context boundaries** — what Codex should NOT chase (settled prior decisions, out-of-scope areas). Keeps Codex out of rabbit holes.

**Reframe on task shift** — if the last turn was "review a diff" and this one is "plan a refactor," say so explicitly. Don't assume the accumulated thread adapts on its own.

## Reconciliation — the actual point

When Codex responds, the work isn't done. Reconcile:

- **Agreements** → increased confidence; say so.
- **Disagreements on specifics** → verify in code/docs; one of you is wrong, figure out which.
- **Things Codex surfaced that you missed** → update your model.
- **Assumptions Codex made that you know are wrong** (e.g., from prior user decisions in memory or history) → correct, don't silently accept.
- **Points where the user needs to decide** between your take and Codex's → surface explicitly, don't paper over.

Report the reconciled output to the user, not a relay of Codex's reply. The user invoked three brains; hand them the reconciled output, not a summary of one.

## Session management

One Codex session per project at `$XDG_STATE_HOME/codex-opinion/{project-hash}.json`. Known stale-session errors (`no rollout found`, `thread not found`, `session expired`, and variants) trigger an automatic fresh start. Other failures — auth, network, config, or clean exit with no agent message — exit non-zero with diagnostics. The script does NOT silently re-run; Codex has full filesystem access and prompts may be non-idempotent.

Concurrent invocations across different projects are isolated. Concurrent invocations on the same project share the thread and may interleave — possibly confused opinion, never lost work. Intentional.
