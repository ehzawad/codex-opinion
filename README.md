# codex-opinion

A Claude Code plugin that gets a second opinion from OpenAI's Codex CLI on your work.

## Prerequisites

- [Claude Code](https://claude.ai/code) — authenticated (`claude` in terminal)
- [OpenAI Codex CLI](https://developers.openai.com/codex/cli) — authenticated (`codex` in terminal)

Both must be logged in and working in your terminal before using this plugin.

## Install

```bash
claude plugins marketplace add ehzawad/codex-opinion
claude plugins install codex-opinion@codex-opinion
```

Persists across sessions — no flags needed.

### For development

```bash
git clone https://github.com/ehzawad/codex-opinion.git
claude --plugin-dir ./codex-opinion/plugins/codex-opinion
```

## Usage

```
/codex-opinion:codex-opinion
```

With a focus directive (appended to the default thorough-review prompt — does not replace it):

```
/codex-opinion:codex-opinion focus on security vulnerabilities
```

Claude Code also triggers the skill automatically when you ask for a second opinion in natural language — no slash command needed:

```
ask codex what it thinks about this diff
get a second opinion on my changes
```

## How it works

When invoked, Claude gathers your diff, plan, or context and pipes it to `codex exec`. Codex uses your configured model and settings from `~/.codex/config.toml`, reads the codebase, runs commands, and does deep analysis. Claude reads the response and reports back.

```mermaid
sequenceDiagram
    participant U as User
    participant C as Claude Code
    participant S as ask_codex.py
    participant X as Codex CLI

    U->>C: /codex-opinion:codex-opinion
    C->>C: Gather diff / plan / context
    C->>S: Pipe context via stdin
    S->>X: codex exec --json
    X-->>S: JSONL events
    S->>S: Extract final message
    S-->>C: Codex's analysis via stdout
    C-->>U: Reports findings
```

## Session management

One Codex session per project, stored at `~/.local/state/codex-opinion/{project-hash}.json`. Follow-up calls resume the prior Codex thread so it builds on its accumulated codebase knowledge — across Claude Code sessions, not just within one.

Resume failures are handled conservatively. Only known stale-session errors (the stored thread is missing/expired server-side) trigger a fresh restart. Other failures — auth, network, config, or a clean exit with no agent message — are surfaced verbatim and the script exits non-zero. This avoids silently re-running prompts that may have non-idempotent side effects under Codex's full filesystem access.

```mermaid
flowchart TD
    A[Invoke /codex-opinion:codex-opinion] --> B{Session file exists<br/>for this project?}
    B -- Yes --> C[codex exec resume session_id]
    C --> D{Resume result?}
    D -- Success + msg --> E[Extract response]
    D -- Stale-session error --> F["Log notice + start fresh"]
    D -- Other failure --> X["Surface stderr<br/>exit non-zero"]
    F --> G[Start fresh session]
    B -- No --> G
    G --> H[Save session metadata]
    H --> E
    E --> I[Return to Claude]
```

Concurrent invocations on the same project are allowed by design — independent Claude Code sessions can each run an opinion in parallel. State writes are atomic, so the JSON file never corrupts. Trade-off: a parallel first-time call may create a duplicate fresh thread, and rare clear/save races may orphan a thread. Net cost is at most a wasted re-learning round, never lost work.

## JSONL protocol

The script communicates with `codex exec --json` via JSONL events on stdout:

```mermaid
sequenceDiagram
    participant S as ask_codex.py
    participant X as Codex CLI

    X->>S: {"type": "thread.started", "thread_id": "UUID"}
    Note over S: Captures session ID
    X->>S: {"type": "turn.started"}
    X->>S: {"type": "item.completed", "item": {"type": "agent_message", "text": "..."}}
    Note over S: Captures last agent message
    X->>S: {"type": "turn.completed", "usage": {...}}
    Note over S: Returns final message to Claude
```

## Security

Codex runs with `--dangerously-bypass-approvals-and-sandbox` — no approval prompts, no filesystem sandbox. This gives Codex full read/write access to your machine so it can thoroughly inspect and analyze the codebase. Do not use this plugin on untrusted repositories or with untrusted input.

## Configuration

The script uses your Codex CLI defaults — model, reasoning effort, and other settings come from `~/.codex/config.toml`. No model is hardcoded. Sandbox and approval settings are overridden by the plugin (see Security above).

## License

MIT
