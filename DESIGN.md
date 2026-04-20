# codex-opinion internals

Implementation details for contributors and maintainers. User-facing docs live in [README.md](README.md).

## Protocol vs transport boundary

The skill layer (how to call Codex, how to build context, session continuity) lives in [`SKILL.md`](plugins/codex-opinion/skills/codex-opinion/SKILL.md); runtime reconciliation is Claude's judgment. [`ask_codex.py`](plugins/codex-opinion/skills/codex-opinion/scripts/ask_codex.py) remains a transport shim: it bookends stdin with a generic, overridable review directive, calls Codex, returns the reply, and saves per-project session state atomically. Pass `--no-default-instruction` for exact stdin passthrough. When `CODEX_OPINION_SESSION_KEY` is set in the environment, the state key includes a hash of that value, giving that caller a separate Codex thread for the same project.

The script parses Codex's JSONL output only for what transport needs — `thread.started` to capture the session id, `item.completed` → `agent_message.text` for the final reply — and does not count rounds, detect cycle boundaries, or interpret Codex's reply semantically for protocol decisions. Adding protocol state to the script would mix transport with judgment and create edge cases around idempotency, concurrent invocations, and what counts as "stable."

If you want protocol enforcement in Python rather than skill-level discipline, that is a different project shape than this repo — a protocol engine, not a transport shim.

## Session management flowchart

```mermaid
flowchart TD
    A[Invoke /codex-opinion:codex-opinion] --> B{Session file exists<br/>for this project?}
    B -- Yes --> C[codex exec resume session_id]
    C --> D{Resume result?}
    D -- Success + msg --> E[Return response]
    D -- Success, no msg --> X["Diagnostic + exit non-zero"]
    D -- Stale-session error --> F["Log notice + start fresh"]
    D -- Other failure --> X
    F --> G[codex exec fresh]
    B -- No --> G
    G --> H{Fresh result?}
    H -- Success + msg --> I[Save session metadata]
    H -- Success, no msg --> X
    H -- Failure --> X
    I --> E
```

## JSONL protocol

`ask_codex.py` communicates with `codex exec --json` via JSONL events on stdout:

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

`extract_session_id` parses `thread.started` events; `extract_final_message` captures the last `agent_message` from any `item.completed` event. If the Codex CLI JSONL format changes (new event shapes, renamed keys), update those two functions in [`plugins/codex-opinion/skills/codex-opinion/scripts/ask_codex.py`](plugins/codex-opinion/skills/codex-opinion/scripts/ask_codex.py).
