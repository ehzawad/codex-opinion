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

Explicit:

```
/codex-opinion:codex-opinion
```

With a custom instruction:

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

Sessions are scoped per **Claude Code session** and per **project**, with continuity across sequential sessions. The script walks up the process tree to find the Claude Code process and uses its PID as part of the session key. This means:

- **Same Claude Code session**: follow-up calls resume the same Codex thread
- **New Claude Code session, same project**: adopts the Codex thread from the previous session — Codex keeps its accumulated codebase knowledge
- **Two concurrent Claude Code sessions**: each gets an independent Codex thread — no interference
- **Stale Codex sessions**: if the adopted Codex thread has expired server-side, logs a notice and starts fresh

State files are stored at `~/.local/state/codex-opinion/`.

```mermaid
flowchart TD
    A[Invoke /codex-opinion:codex-opinion] --> B[Walk process tree<br/>to find Claude Code PID]
    B --> C[Clean up dead session files<br/>from other closed sessions]
    C --> D{State file exists for<br/>this project + our PID?}
    D -- Yes --> E[codex exec resume session_id]
    D -- No --> F{Dead session file exists<br/>from a previous Claude session?}
    F -- Yes --> G["Adopt most recent session<br/>(atomic rename)"]
    G --> E
    F -- No --> H[codex exec — fresh session]
    E --> I{Resume succeeded?}
    I -- Yes --> J[Extract response]
    I -- No --> K["Log notice to stderr"]
    K --> L[Clear stale session file]
    L --> H
    H --> M[Save session metadata]
    M --> J
    J --> N[Return to Claude]
```

```mermaid
graph LR
    subgraph "~/.local/state/codex-opinion/"
        A["a1b2c3d4e5f6a7b8_39837.json<br/><i>project-A, Claude PID 39837</i>"]
        B["a1b2c3d4e5f6a7b8_41502.json<br/><i>project-A, Claude PID 41502<br/>(concurrent session)</i>"]
        C["978c37f23779ed84_39837.json<br/><i>project-B, Claude PID 39837</i>"]
    end

    subgraph "Session metadata"
        D["session_id: UUID<br/>project_path: /path/to/repo<br/>claude_pid: 39837<br/>updated_at: ISO timestamp"]
    end

    A --> D
    B --> D
    C --> D
```

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
