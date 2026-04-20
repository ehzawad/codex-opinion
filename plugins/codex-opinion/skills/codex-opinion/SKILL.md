---
name: codex-opinion
description: Three-way collaboration with OpenAI Codex (human + Claude + Codex). Claude reconciles Codex's take with the work at hand. Invoke /codex-opinion:codex-opinion, or naturally via phrases like "ask codex," "second opinion," "another perspective," "codex weigh in," "reconcile with codex."
argument-hint: [usually empty — compose the context into stdin]
---

# Three-way collaboration with Codex

Codex runs in its own process with full filesystem access. Its working root is the current project — resolved at each invocation from the cwd's git root (or the cwd itself if not in a repo), which is whatever project the user is working in right now. This plugin is not tied to any specific codebase; it works inside any Claude Code project.

Each invocation is a three-way collaboration — human, Claude, Codex. Your job is to give Codex the current context, get its take, and reconcile — not forward and relay.

Codex cannot see Claude-only state: this conversation's history, transient command output, browser/tool state, external docs, user constraints you inferred from memory. If it matters, put it in the context. Files in the current project and anything Codex can produce by running commands — leave for Codex to fetch directly.

## Philosophy

These principles hold across every invocation regardless of task. Human, Claude, Codex — same floor for all three. The context adapts to the moment; the floor does not.

- **The context window must neither rot nor starve.** Include every material fact Codex needs to catch wrong/missing/incomplete assumptions (tried paths, current hypotheses, constraints, specific errors, the actual user text). Cut only the procedural fluff around those facts. A summary-only context is worse than a dump — Codex can't challenge what it can't see.
- **Unexpected state, errors, and disagreements are not emergencies.** Find root causes before any destructive or expensive move.
- **No shortcuts that trade correctness for a quick answer.** No silently suppressing inconvenient findings.
- **Never claim findings you didn't verify, successes you didn't observe, or confidence you don't have.** Uncertainty is honest; false certainty corrodes reconciliation.
- **A thoughtful second opinion beats a fast one.** Codex running long is fine; Codex answering shallowly is not.
- **Default agreement across human, Claude, and Codex is three parties pretending to be one.** Surface disagreement with evidence, not politeness.
- **No party has priority.** Human, Claude, and Codex reconcile on facts, evidence, and context — not on whose suggestion it is. Prior user decisions override stylistic defaults; direct observation overrides inferred claims.
- **Wrong, incomplete, and missing assumptions are the origin of errors and misalignments.** Reconciliation's main job is to surface them — in Claude's context, Codex's reply, the user's framing, or prior memory and decisions.

Carry the floor through the context itself — comprehensive context, honest uncertainty, evidence-based reconciliation — instead of labeling prompts with a fixed header. Restate it explicitly only when starting fresh or when a participant drifts (sycophancy creep, hand-wavy certainty, rushed conclusions, unverified claims).

## Script

The script bookends the stdin body with a short review-directive instruction (`DEFAULT_INSTRUCTION` in `ask_codex.py`), then pipes the combined prompt to `codex exec`. The stdin body passes through verbatim between the instruction copies — Codex sees your full composed context. Call it with your context on stdin:

```bash
cat <<'EOF' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
<full context for Codex>
EOF
```

Override the default instruction by passing a positional argument, which replaces `DEFAULT_INSTRUCTION` and is also bookended:

```bash
cat <<'EOF' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py "custom directive for this task"
<full context for Codex>
EOF
```

For exact stdin passthrough with no default or custom wrapper:

```bash
cat <<'EOF' | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py --no-default-instruction
<full context for Codex>
EOF
```

A Codex call takes as long as the work takes; use Bash `run_in_background: true` and wait for Claude Code's completion notification instead of sleep-polling.

Direct-CLI context-building patterns (git diff, untracked files with binary/size guards, passthrough mode) are in [`reference.md`](reference.md).

First call per project establishes Codex's framing; later calls resume the same thread, so Codex keeps accumulated project knowledge. **Reframe explicitly when the task shifts** — prior framing biases later answers if left unchecked. If the thread has drifted beyond what a reframe can steer, delete the state file (details in Session state). For per-session isolation instead of project-wide continuity, set `CODEX_OPINION_SESSION_KEY` before launching Claude Code — see Session state.

## Context and reconciliation

Provide comprehensive context and tailor it to the moment — use this as a lens, not a form. When unsure, include more context rather than less: undershooting rots reconciliation, and Codex can't challenge what it can't see. Include the user's exact text verbatim, not just a paraphrase; the current chat-interaction state Codex cannot see (what was decided, what is pending, what changed in recent turns); the output Codex should produce; your current read, or that you don't have one yet; observed evidence inlined when the exact text is the evidence (errors, diffs, outputs); negative evidence (hypotheses already ruled out and why); constraints and prior decisions that still bind; where Codex should look (paths, commands, stuff, branches and diffs, artifacts, or specific evidence); the exact question; known non-goals (Codex may challenge them if they conflict with the objective).

When the material is in the current project, point Codex at paths or commands for bulk content it can fetch itself. When the evidence is the exact text, error, output, or diff, inline it rather than paraphrase. For codework with uncommitted changes, default to inlining `git diff HEAD` so Codex starts from the actual working state, not stale HEAD. For mid-session interaction state Codex cannot see (recent user instructions, current plan, decisions, failed attempts, tool output you saw), inline that too.

For review-shaped asks (code review, design review, plan review — anything framed as "check this"), explicitly include the artifact being reviewed, what motivated the review (observed failures, concerns, goals), and the review criteria Codex should apply. Weak task framing produces weak second opinions.

### Context-building templates

Pick a template when a user's task intent clearly matches one — otherwise compose context without a template. Templates are starting shapes, not forms. See [`assets/templates.md`](assets/templates.md) for the 20 templates covering general technical review, LLM/agentic/ML/DL/MLOps, data engineering, frontend, backend, databases, testing, QA, performance, deployment, DevSecOps, and research-paper work.

When Codex replies, reconcile rather than relay. Agreements build confidence; disagreements need verification in code, docs, or commands. Fold in points Codex surfaced that you missed; correct assumptions Codex made that you know are wrong (e.g., from prior user decisions captured in memory) rather than silently accept them; surface points where the user needs to decide between your take and Codex's, don't paper over. Hand the user the reconciled output, not a summary from one of the three.

Show the reasoning path when handing the reconciled output to the user. Surface the material why: which Codex points you accepted or challenged, where you had a counter-view you deferred on and what moved you, what evidence or verification shifted the answer, why an audit was or was not needed, and where the user's framing constrained the decision. If uncertainty remains, say so.

### Audit your draft before finalizing

Prioritize single-round. Audit is the exception, and a closing check only follows when the audit materially changes the answer. Before finalizing, check whether your reconciliation added material judgment or synthesis Codex never saw: a recommendation, priority, severity call, go/no-go decision, bridging claim, changed confidence level, invented path, or resolved concern. If it did, use an audit call to test that added material for wrong, missing, incomplete, or unverified assumptions. If it did not, one round is enough.

Because this decision is self-judged, treat uncertainty about whether you added material judgment as a reason to audit, especially when turning Codex's findings into a recommendation, priority, severity, confidence change, or go/no-go answer.

An audit call should include the draft itself, name the specific new or changed claims, and keep the ask narrow.

If the audit finds something and you materially revise in response, a closing check lets Codex see the revision before you finalize. Include the revised answer, the audit findings and how you handled them, and what changed. Ask Codex to look only for blockers introduced by the revision itself: new material claims, lost uncertainty, or misapplied audit findings that would make the answer misleading, unsupported, or materially incomplete.

Keep the cycle bounded: initial round, audit when the draft adds material new judgment or synthesis, closing check when the audit materially changes the answer. This is not iterate-to-agreement. If the closing check surfaces a blocker, do not quietly resolve it and present the answer as stabilized; surface the blocker to the human or ask a concrete question.

## Session state

One Codex thread per project at `$XDG_STATE_HOME/codex-opinion/{hash}.json` (default `~/.local/state/codex-opinion/`). Known stale-session errors (`no rollout found`, `thread not found`, `session expired`, and variants) trigger an automatic fresh start. Other failures — auth, network, config, or a clean exit with no agent message — exit non-zero with diagnostics. The script does not silently re-run; Codex has full filesystem access and prompts may be non-idempotent.

Set `CODEX_OPINION_SESSION_KEY` before launching Claude Code to isolate a session: the state file becomes `{project-hash}-{session-hash}.json` and that session gets its own Codex thread. Unset or empty keeps the project-wide thread. Use a non-secret label (e.g. a branch name or short task ID) — the raw value is written into the state file for debugging.

Different projects use different Codex threads. The same project shares one thread unless `CODEX_OPINION_SESSION_KEY` is set; concurrent same-project calls may mix context, so run them one at a time when continuity matters or isolate each session with a different key.

To delete the state file for this project (start clean), the matching file has a `project_path` field equal to the project root:

```bash
grep -l "$(git rev-parse --show-toplevel)" "${XDG_STATE_HOME:-$HOME/.local/state}/codex-opinion/"*.json
```
