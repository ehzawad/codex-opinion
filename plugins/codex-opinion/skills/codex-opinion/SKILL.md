---
name: codex-opinion
description: Three-way collaboration with OpenAI Codex (human + Claude + Codex) that adapts in the moment to whatever you're doing. Claude reconciles Codex's take with the work at hand. Invoke /codex-opinion:codex-opinion, or naturally via phrases like "ask codex," "second opinion," "another perspective," "codex weigh in," "reconcile with codex."
argument-hint: [usually empty — compose the briefing into stdin]
---

# Three-way collaboration with Codex

Codex runs in its own process with full filesystem access. Its working root is the current project — resolved at each invocation from the cwd's git root (or the cwd itself if not in a repo), which is whatever project the user is working in right now. This plugin is not tied to any specific codebase; it works inside any Claude Code project.

Each invocation is a three-way collaboration — human, Claude, Codex. Your job is to brief Codex on the current moment, get its take, and reconcile — not forward and relay.

Codex cannot see Claude-only state: this conversation's history, transient command output, browser/tool state, external docs, user constraints you inferred from memory. If it's material, brief it. Files in the current project and anything Codex can produce by running commands — leave for Codex to fetch directly.

## Philosophy

These principles hold across every invocation regardless of task. Human, Claude, Codex — same floor for all three. The briefing adapts to the moment; the floor does not.

- **Keep the context window useful.** Include every material fact Codex needs to catch wrong/missing/incomplete assumptions (tried paths, current hypotheses, constraints, specific errors, the actual user text). Cut only the procedural fluff around those facts. A summary-only briefing is worse than a dump — Codex can't challenge what it can't see.
- **Unexpected state, errors, and disagreements are not emergencies.** Find root causes before any destructive or expensive move.
- **No shortcuts that trade correctness for a quick answer.** No silently suppressing inconvenient findings.
- **Never claim findings you didn't verify, successes you didn't observe, or confidence you don't have.** Uncertainty is honest; false certainty corrodes reconciliation.
- **A thoughtful second opinion beats a fast one.** Codex running long is fine; Codex answering shallowly is not.
- **Default agreement across human, Claude, and Codex is not evidence by itself.** Surface disagreement with evidence, not politeness.
- **Wrong, incomplete, and missing assumptions are the origin of errors and misalignments.** Reconciliation's main job is to surface them — in Claude's briefing, Codex's reply, the user's framing, or prior memory and decisions.

Include a brief marker of this philosophy in your first briefing per project so Codex's framing inherits it. Restate it if any participant drifts (sycophancy creep, hand-wavy certainty, rushed conclusions, unverified claims).

## Script

Pure transport. Whatever you pipe to stdin is exactly what Codex sees — no default framing, no templates. Call it with your composed briefing on stdin:

```bash
<your briefing> | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

First call per project establishes Codex's framing; later calls resume the same thread, so Codex keeps accumulated project knowledge. **Reframe explicitly when the task shifts** — prior framing biases later answers if left unchecked. If the thread has drifted beyond what a reframe can steer, delete the state file (details in Session state).

## Briefing and reconciliation

Use this as a lens, not a form — don't mechanically fill headings; include only what's material for this moment, and omit empty parts entirely (no `N/A` padding): objective; the output Codex should produce; your current read, or that you don't have one yet; observed evidence (exact user text, errors, diffs, outputs); negative evidence (hypotheses already ruled out, and why); constraints and prior decisions (don't relitigate); where Codex should look (paths, commands, stuff, branches and diffs, artifacts, or specific evidence); the exact question; known non-goals (Codex may challenge them if they conflict with the objective).

When the material is in the current project, prefer pointing Codex at paths or commands over pasting bulk content — unless the exact text, error, or diff *is* the evidence. If uncommitted changes are material, inline `git diff HEAD` so Codex starts from a shared view of the working state.

When Codex replies, reconcile rather than relay. Agreements build confidence; disagreements need verification in code, docs, or commands. Fold in points Codex surfaced that you missed; correct assumptions Codex made that you know are wrong (e.g., from prior user decisions captured in memory) rather than silently accept them; surface points where the user needs to decide between your take and Codex's, don't paper over. Hand the user the reconciled output, not a summary from one of the three.

Show the reasoning path when handing the reconciled output to the user. Surface the material why: which Codex points you accepted or challenged, what evidence or verification shifted the answer, why an audit was or was not needed, and where the user's framing constrained the decision. If uncertainty remains, say so.

### Audit your draft before finalizing

codex-opinion is single-round by default. Before finalizing, check whether your reconciliation added material judgment or synthesis Codex never saw: a recommendation, priority, severity call, go/no-go decision, bridging claim, changed confidence level, invented path, or resolved concern. If it did, use an audit call to test that added material for wrong, missing, incomplete, or unverified assumptions. If it did not, one round is enough.

Because this decision is self-judged, treat uncertainty about whether you added material judgment as a reason to audit, especially when turning Codex's findings into a recommendation, priority, severity, confidence change, or go/no-go answer.

An audit call should include the draft itself, name the specific new or changed claims, and keep the ask narrow.

If the audit finds something and you materially revise in response, a closing check lets Codex see the revision before you finalize. Include the revised answer, the audit findings and how you handled them, and what changed. Ask Codex to look only for blockers introduced by the revision itself: new material claims, lost uncertainty, or misapplied audit findings that would make the answer misleading, unsupported, or materially incomplete.

Keep the cycle bounded: initial briefing, audit when the draft adds material new judgment or synthesis, closing check when the audit materially changes the answer. This is not iterate-to-agreement. If the closing check surfaces a blocker, do not quietly resolve it and present the answer as stabilized; surface the blocker to the human or ask a concrete question.

## Session state

One Codex thread per project at `$XDG_STATE_HOME/codex-opinion/{hash}.json` (default `~/.local/state/codex-opinion/`). Known stale-session errors (`no rollout found`, `thread not found`, `session expired`, and variants) trigger an automatic fresh start. Other failures — auth, network, config, or a clean exit with no agent message — exit non-zero with diagnostics. The script does not silently re-run; Codex has full filesystem access and prompts may be non-idempotent.

Different projects use different Codex threads. The same project shares one thread; concurrent same-project calls may mix context, so run them one at a time when continuity matters.

To delete the state file for this project (start clean), the matching file has a `project_path` field equal to the project root:

```bash
grep -l "$(git rev-parse --show-toplevel)" "${XDG_STATE_HOME:-$HOME/.local/state}/codex-opinion/"*.json
```
