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

Sessions are scoped per-project and stored at `~/.local/state/codex-opinion/`. Each git repo gets its own session file keyed by a hash of the repo root, so switching between projects won't cross-contaminate Codex threads.

Follow-up calls resume the prior session so Codex builds on its earlier analysis.

```mermaid
flowchart TD
    A[Invoke /codex-opinion:codex-opinion] --> B{Session file exists<br/>for this project?}
    B -- Yes --> C[codex exec resume session_id]
    C --> D{Resume succeeded?}
    D -- Yes --> E[Extract response]
    D -- No --> F["Log notice to stderr:<br/>[codex-opinion] Session ... could not be resumed"]
    F --> G[Clear stale session file]
    G --> H[codex exec — fresh session]
    B -- No --> H
    H --> I[Save session metadata]
    I --> E
    E --> J[Return to Claude]
```

```mermaid
graph LR
    subgraph "~/.local/state/codex-opinion/"
        A["a1b2c3d4e5f6g7h8.json<br/><i>project-A</i>"]
        B["978c37f23779ed84.json<br/><i>project-B</i>"]
        C["f9e8d7c6b5a4f3e2.json<br/><i>project-C</i>"]
    end

    subgraph "Session metadata"
        D["session_id: UUID<br/>project_path: /path/to/repo<br/>created_at: ISO timestamp"]
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

## Configuration

The script uses your Codex CLI defaults — model, reasoning effort, and other settings come from `~/.codex/config.toml`. No model is hardcoded.

## License

MIT
