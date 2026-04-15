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

With a custom instruction:

```
/codex-opinion:codex-opinion focus on security vulnerabilities
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

Sessions are scoped per **Claude Code session** and per **project**. The script detects the parent Claude Code process (via grandparent PID) and uses it as part of the session key. This means:

- Two Claude Code sessions on the same project get **independent** Codex sessions
- Follow-up calls within the same Claude Code session **resume** the prior Codex thread
- When a Claude Code session ends, its state files are cleaned up on the next invocation

State files are stored at `~/.local/state/codex-opinion/`.

```mermaid
flowchart TD
    A[Invoke /codex-opinion:codex-opinion] --> B[Detect Claude Code PID<br/>via grandparent process]
    B --> C[Clean up state files from<br/>dead Claude Code sessions]
    C --> D{Session file exists for<br/>this project + Claude PID?}
    D -- Yes --> E[codex exec resume session_id]
    E --> F{Resume succeeded?}
    F -- Yes --> G[Extract response]
    F -- No --> H["Log notice to stderr"]
    H --> I[Clear stale session file]
    I --> J[codex exec — fresh session]
    D -- No --> J
    J --> K[Save session metadata]
    K --> G
    G --> L[Return to Claude]
```

```mermaid
graph LR
    subgraph "~/.local/state/codex-opinion/"
        A["a1b2c3d4e5f6a7b8_39837.json<br/><i>project-A, Claude PID 39837</i>"]
        B["a1b2c3d4e5f6a7b8_41502.json<br/><i>project-A, Claude PID 41502</i>"]
        C["978c37f23779ed84_39837.json<br/><i>project-B, Claude PID 39837</i>"]
    end

    subgraph "Session metadata"
        D["session_id: UUID<br/>project_path: /path/to/repo<br/>claude_pid: 39837<br/>created_at: ISO timestamp"]
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
