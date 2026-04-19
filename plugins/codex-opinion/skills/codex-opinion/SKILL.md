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

- **The context window must neither rot nor starve.** Include every material fact Codex needs to catch wrong/missing/incomplete assumptions (tried paths, current hypotheses, constraints, specific errors, the actual user text). Cut only the procedural fluff around those facts. A summary-only briefing is worse than a dump — Codex can't challenge what it can't see.
- **Unexpected state, errors, and disagreements are not emergencies.** Find root causes before any destructive or expensive move.
- **No shortcuts that trade correctness for a quick answer.** No silently suppressing inconvenient findings.
- **Never claim findings you didn't verify, successes you didn't observe, or confidence you don't have.** Uncertainty is honest; false certainty corrodes reconciliation.
- **A thoughtful second opinion beats a fast one.** Codex running long is fine; Codex answering shallowly is not.
- **Default agreement across human, Claude, and Codex is three parties pretending to be one.** Surface disagreement with evidence, not politeness.
- **No party has priority.** Human, Claude, and Codex reconcile on facts, evidence, and context — not on whose suggestion it is. Prior user decisions override stylistic defaults; direct observation overrides inferred claims.
- **Wrong, incomplete, and missing assumptions are the origin of errors and misalignments.** Reconciliation's main job is to surface them — in Claude's briefing, Codex's reply, the user's framing, or prior memory and decisions.

Include a brief marker of this philosophy in your first briefing per project so Codex's framing inherits it. Restate it if any participant drifts (sycophancy creep, hand-wavy certainty, rushed conclusions, unverified claims).

## Invocation

Pure transport. Whatever you pipe to stdin is exactly what Codex sees — no default framing, no templates.

Codex runs can take minutes to hours. The default invocation makes its progress visible to the human live; the silent fallback exists only for trivial or debugging calls.

Three invocation shapes, picked by expected run length:

**Short runs, in-Monitor (< 1h): `CODEX_OPINION_STREAM=monitor`.**

Synchronous. Claude Code's Monitor tool streams compact progress lines (`>> tool: …`, `>> tool done: …`, `>> agent message ready`, `>> turn done: …`) as notifications while Codex works. Errors and stale-session recoveries surface as `>> error: …` / `>> warning: …`. Final message via sidecar at `$STATE_DIR/lastmsg/{pid}.txt`; `Read` it after Monitor completes.

```
Monitor({
  command:     "bash -lc '<your briefing> | CODEX_OPINION_STREAM=monitor python3 \"$CLAUDE_PLUGIN_ROOT/skills/codex-opinion/scripts/ask_codex.py\"'",
  description: "Codex: <short task label>",
  timeout_ms:  3600000,
  persistent:  true,
})
```

`CODEX_OPINION_STREAM=monitor` must sit on the python3 command (right of the pipe), not left — otherwise it applies to the briefing-producing command and the script falls through to silent default mode.

Monitor's `timeout_ms` caps at 3600000ms (1h); Codex continues running up to that ceiling and dies with the subprocess when Monitor expires. Use the detach shape below for anything that might exceed an hour.

**Long runs (hours to weeks): detach + watch + collect.**

The script has no time limit. For runs that may outlive any Claude Code tool invocation, use three calls:

1. `CODEX_OPINION_STREAM=detach` spawns Codex fully detached — its own session, stdin/stdout/stderr redirected to files under `$STATE_DIR/jobs/<job-id>/`. The script exits immediately with `>> job-id: <id>`, `>> job-dir: …`, `>> pid: …`, `>> log: …`, `>> sidecar: …`. Codex keeps running after Claude Code's tool call ends; it survives Monitor expiry, Claude Code session close, even laptop sleep if the OS keeps the process alive.

   ```
   bash -lc '<your briefing> | CODEX_OPINION_STREAM=detach python3 "$CLAUDE_PLUGIN_ROOT/skills/codex-opinion/scripts/ask_codex.py"'
   ```

   Capture the `>> job-id:` value from stdout and record it in the conversation so you can pass it to `watch` / `collect` later (possibly in a future Claude Code session).

2. `CODEX_OPINION_STREAM=watch` + `CODEX_OPINION_JOB_ID=<id>` tails the job's log and emits compact progress lines. Re-invocable across Monitor expiries — watch runs as a separate process from Codex, so killing watch doesn't affect Codex. When the job ends, watch emits `>> final-message: <path>`.

   ```
   Monitor({
     command:     "bash -lc 'CODEX_OPINION_STREAM=watch CODEX_OPINION_JOB_ID=<id> python3 \"$CLAUDE_PLUGIN_ROOT/skills/codex-opinion/scripts/ask_codex.py\"'",
     description: "Watch Codex job <id>",
     timeout_ms:  3600000,
     persistent:  true,
   })
   ```

3. `CODEX_OPINION_STREAM=collect` + `CODEX_OPINION_JOB_ID=<id>` prints the job's final agent_message on stdout. Use this once watch has reported `>> final-message:` (or directly, if you're willing to poll).

   ```bash
   CODEX_OPINION_STREAM=collect CODEX_OPINION_JOB_ID=<id> python3 "$CLAUDE_PLUGIN_ROOT/skills/codex-opinion/scripts/ask_codex.py"
   ```

Detached jobs do not touch the project's session state — each detach is a fresh Codex thread regardless of what's in the project session file. `CODEX_OPINION_SESSION_KEY` is recorded in the job's manifest for debugging only; it does not cause detach to resume any prior thread. Cross-job continuity (chained multi-turn reconciliation across separate detaches) is not implemented. Detach is for fire-and-forget long single runs; use `off` or `monitor` mode when you need continuity.

Progress lines are the progress, not the answer. Reconcile using the final-message file, never any intermediate `>> agent message ready` notification.

**Shortest path — Bash foreground (silent until completion):**

For known-short calls or debugging where live visibility isn't needed. Returns the final agent_message on stdout; the human sees nothing during the run.

```bash
<your briefing> | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

First call per project establishes Codex's framing; later calls resume the same thread, so Codex keeps accumulated project knowledge. **Reframe explicitly when the task shifts** — prior framing biases later answers if left unchecked. If the thread has drifted beyond what a reframe can steer, delete the state file (details in Session state).

## Briefing and reconciliation

Use this as a lens, not a form — don't mechanically fill headings; include only what's material for this moment, and omit empty parts entirely (no `N/A` padding): objective; the output Codex should produce; your current read, or that you don't have one yet; observed evidence (exact user text, errors, diffs, outputs); negative evidence (hypotheses already ruled out, and why); constraints and prior decisions (don't relitigate); where Codex should look (paths, commands, stuff, branches and diffs, artifacts, or specific evidence); the exact question; known non-goals (Codex may challenge them if they conflict with the objective).

When the material is in the current project, prefer pointing Codex at paths or commands over pasting bulk content — unless the exact text, error, or diff *is* the evidence. If uncommitted changes are material, inline `git diff HEAD` so Codex starts from a shared view of the working state.

When Codex replies, reconcile rather than relay. Agreements build confidence; disagreements need verification in code, docs, or commands. Fold in points Codex surfaced that you missed; correct assumptions Codex made that you know are wrong (e.g., from prior user decisions captured in memory) rather than silently accept them; surface points where the user needs to decide between your take and Codex's, don't paper over. Hand the user the reconciled output, not a summary from one of the three.

Show the reasoning path when handing the reconciled output to the user. Surface the material why: which Codex points you accepted or challenged, where you had a counter-view you deferred on and what moved you, what evidence or verification shifted the answer, why an audit was or was not needed, and where the user's framing constrained the decision. If uncertainty remains, say so.

### Audit your draft before finalizing

Prioritize single-round. Audit is the exception, and a closing check only follows when the audit materially changes the answer. Before finalizing, check whether your reconciliation added material judgment or synthesis Codex never saw: a recommendation, priority, severity call, go/no-go decision, bridging claim, changed confidence level, invented path, or resolved concern. If it did, use an audit call to test that added material for wrong, missing, incomplete, or unverified assumptions. If it did not, one round is enough.

Because this decision is self-judged, treat uncertainty about whether you added material judgment as a reason to audit, especially when turning Codex's findings into a recommendation, priority, severity, confidence change, or go/no-go answer.

An audit call should include the draft itself, name the specific new or changed claims, and keep the ask narrow.

If the audit finds something and you materially revise in response, a closing check lets Codex see the revision before you finalize. Include the revised answer, the audit findings and how you handled them, and what changed. Ask Codex to look only for blockers introduced by the revision itself: new material claims, lost uncertainty, or misapplied audit findings that would make the answer misleading, unsupported, or materially incomplete.

Keep the cycle bounded: initial briefing, audit when the draft adds material new judgment or synthesis, closing check when the audit materially changes the answer. This is not iterate-to-agreement. If the closing check surfaces a blocker, do not quietly resolve it and present the answer as stabilized; surface the blocker to the human or ask a concrete question.

## Session state

*Applies to `off` and `monitor` (sync) modes.* Detach jobs have separate per-job manifests under `$STATE_DIR/jobs/<job-id>/` and do not share the per-project thread.

One Codex thread per project at `$XDG_STATE_HOME/codex-opinion/{hash}.json` (default `~/.local/state/codex-opinion/`). Known stale-session errors (`no rollout found`, `thread not found`, `session expired`, and variants) trigger an automatic fresh start. Other failures — auth, network, config, or a clean exit with no agent message — exit non-zero with diagnostics. The script does not silently re-run; Codex has full filesystem access and prompts may be non-idempotent.

Set `CODEX_OPINION_SESSION_KEY` before launching Claude Code to isolate a session: the state file becomes `{project-hash}-{session-hash}.json` and that session gets its own Codex thread. Unset or empty keeps the project-wide thread. Use a non-secret label (e.g. a branch name or short task ID) — the raw value is written into the state file for debugging.

Different projects use different Codex threads. The same project shares one thread unless `CODEX_OPINION_SESSION_KEY` is set; concurrent same-project calls may mix context, so run them one at a time when continuity matters or isolate each session with a different key.

To delete the state file for this project (start clean), the matching file has a `project_path` field equal to the project root:

```bash
grep -l "$(git rev-parse --show-toplevel)" "${XDG_STATE_HOME:-$HOME/.local/state}/codex-opinion/"*.json
```
