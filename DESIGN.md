# codex-opinion internals

Implementation details for contributors and maintainers. User-facing docs live in [README.md](README.md).

## Protocol vs transport boundary

Reconciliation protocol (when to call Codex, how to frame the briefing, when to audit the reconciled draft, when to run a closing revision check) lives in [`SKILL.md`](plugins/codex-opinion/skills/codex-opinion/SKILL.md) and Claude's judgment at runtime. [`ask_codex.py`](plugins/codex-opinion/skills/codex-opinion/scripts/ask_codex.py) intentionally remains prompt transport only: stdin in, Codex call, reply out, per-project session state saved atomically. When `CODEX_OPINION_SESSION_KEY` is set in the environment, the state key includes a hash of that value, giving that caller a separate Codex thread for the same project.

Multi-round behavior — initial briefing, audit call, closing revision check — is produced by Claude invoking the same script multiple times on the resumed Codex thread with explicit per-call briefings. The script does not count rounds, detect cycle boundaries, or parse Codex's response. Adding protocol state to the script would mix transport with judgment and create edge cases around idempotency, concurrent invocations, and what counts as "stable."

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
    X->>S: {"type": "item.started", "item": {"type": "command_execution", ...}}
    Note over S: In monitor mode, emits >> tool: ...
    X->>S: {"type": "item.completed", "item": {"type": "command_execution", ...}}
    Note over S: In monitor mode, emits >> tool done: ...
    X->>S: {"type": "item.completed", "item": {"type": "agent_message", "text": "..."}}
    Note over S: Captures last agent message
    X->>S: {"type": "turn.completed", "usage": {...}}
    Note over S: Writes final message to sidecar (monitor) or returns via stdout (default)
```

`extract_session_id` parses `thread.started` events; `extract_final_message` captures the last `agent_message` from any `item.completed` event. `_event_to_progress_line` translates events into compact `>> …` lines for monitor mode. If the Codex CLI JSONL format changes (new event shapes, renamed keys), update those three functions in [`plugins/codex-opinion/skills/codex-opinion/scripts/ask_codex.py`](plugins/codex-opinion/skills/codex-opinion/scripts/ask_codex.py).

## Streaming architecture

`_run_codex_stream_async` is the asyncio event-loop driver. It spawns `codex exec --json` via `asyncio.create_subprocess_exec` with the child in its own session (`os.setsid`) so SIGTERM/SIGKILL escalation targets the whole process group, and concurrently gathers three tasks:

- `_feed_stdin` writes the prompt and closes stdin without blocking the loop.
- `_drain_stdout` iterates the child's stdout line-by-line; in streaming mode each decoded line is parsed as JSON and, if it carries a progress signal, a compact `>> …` string is printed immediately to this script's own stdout (where Claude Code's `Monitor` tool picks it up).
- `_drain_stderr` accumulates stderr so no buffer ever fills and deadlocks the child.

```mermaid
sequenceDiagram
    participant C as Claude Code (Monitor)
    participant S as ask_codex.py (async)
    participant L as event loop
    participant X as codex exec

    C->>S: bash -lc 'CODEX_OPINION_STREAM=monitor … | ask_codex.py'
    S->>L: asyncio.run(run_codex_async)
    L->>X: create_subprocess_exec (own session)
    par stdin
        L->>X: prompt bytes
    and stdout drain
        X-->>L: JSONL event
        L-->>S: _event_to_progress_line
        S-->>C: >> ... (live notification)
    and stderr drain
        X-->>L: stderr chunk
        L->>S: accumulate
    end
    Note over S: JSONL parsing and session save happen in the script; Claude Code never arbitrates transport correctness.
    S-->>C: >> final-message: <sidecar path>
```

No timeout is enforced on the subprocess. No threads are used — concurrency is entirely `asyncio.gather`. Keyboard interrupts and exceptions cancel all in-flight tasks and escalate termination through `SIGTERM` → `SIGKILL` on the process group.
