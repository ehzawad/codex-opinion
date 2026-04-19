#!/usr/bin/env python3
"""Route a prompt to Codex CLI (asyncio event-loop architecture).

Pure transport: whatever is piped in on stdin is sent verbatim to
`codex exec` (or `codex exec resume` when a prior session exists for
this project). The caller — typically Claude Code via the skill — is
responsible for constructing a complete, self-framed prompt.

Non-blocking by design: the subprocess driver is asyncio-native with
concurrent stdin-feed, stdout-drain, and stderr-drain tasks gathered
in a single event loop. No threads. No polling sleeps. No per-stream
timeouts (codex exec can legitimately run for an hour or more; the
wrapper never imposes its own time ceiling).

An optional positional argument is prepended to the stdin body with a
blank-line separator, as a convenience for direct CLI use. Most Claude
Code invocations should leave it empty and bake any framing into stdin.

Two output modes:

- Default (unset / CODEX_OPINION_STREAM=off): silent during the run;
  prints the final agent_message text to stdout when codex finishes.
  Matches the pre-streaming contract.

- Streaming (CODEX_OPINION_STREAM=monitor): emits compact progress
  lines (`>> turn started`, `>> tool done: exit=0 ...`, etc.) to stdout
  as Codex events arrive. The final agent_message text is written to a
  sidecar file under $STATE_DIR/lastmsg/{pid}.txt and its path is
  emitted as `>> final-message: <path>` so Claude Code's Monitor tool
  can pick both up. Intended for long Codex runs where the human
  should see progress live instead of silence.

Set CODEX_OPINION_SESSION_KEY to isolate a session's Codex thread from
the project-wide thread. Unset or empty keeps one-thread-per-project.

Set CODEX_OPINION_LOG=1 to mirror raw JSONL events to
$STATE_DIR/logs/{project-hash}-{timestamp}.jsonl for debugging.

Usage:
    echo "<prompt>" | python3 ask_codex.py
    CODEX_OPINION_STREAM=monitor echo "<prompt>" | python3 ask_codex.py
"""

import asyncio
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from functools import lru_cache

STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "codex-opinion",
)
SIDECAR_DIR = os.path.join(STATE_DIR, "lastmsg")
LOG_DIR = os.path.join(STATE_DIR, "logs")
SIDECAR_MAX_AGE_SECS = 24 * 3600

# Lowercased stderr substrings from `codex exec resume` that indicate the
# stored session can no longer be resumed (stale/expired/missing). On match
# we start fresh; any other non-zero exit is reported with Codex's stderr
# plus an exit-code tag, and the script exits non-zero.
# Add new variants here as Codex CLI evolves its wording.
STALE_RESUME_MARKERS = (
    "no rollout found",
    "thread not found",
    "session not found",
    "session expired",
    "thread expired",
)


@lru_cache(maxsize=1)
def _project_root():
    """Return the git repo root for the current dir, falling back to cwd.

    Cached because the script is one-shot and the result is referenced
    transitively from _project_key/_state_path/load_session/save_session/
    _open_log; without caching the sync `git rev-parse` runs 4-5 times per
    invocation.
    """
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        ).stdout.strip()
    except OSError:
        root = ""
    return root or os.getcwd()


def _session_key():
    """Optional caller-provided key for isolating Codex state within a project."""
    return os.environ.get("CODEX_OPINION_SESSION_KEY", "").strip()


def _project_key():
    """Stable state key for this project, optionally scoped by session key."""
    base = hashlib.sha256(_project_root().encode()).hexdigest()[:16]
    session_key = _session_key()
    if session_key:
        suffix = hashlib.sha256(session_key.encode()).hexdigest()[:16]
        return f"{base}-{suffix}"
    return base


def _state_path():
    """Per-project session state file path."""
    return os.path.join(STATE_DIR, f"{_project_key()}.json")


def _stream_mode():
    """Return 'monitor' if CODEX_OPINION_STREAM=monitor, else 'off'."""
    if os.environ.get("CODEX_OPINION_STREAM", "").strip().lower() == "monitor":
        return "monitor"
    return "off"


def _sidecar_path_for_pid(pid):
    return os.path.join(SIDECAR_DIR, f"{pid}.txt")


def _log_path_for_project(project_key):
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return os.path.join(LOG_DIR, f"{project_key}-{ts}.jsonl")


def _gc_old_sidecars():
    """Remove sidecar files older than SIDECAR_MAX_AGE_SECS. Best-effort."""
    try:
        now = time.time()
        for name in os.listdir(SIDECAR_DIR):
            path = os.path.join(SIDECAR_DIR, name)
            try:
                if os.path.isfile(path) and (now - os.path.getmtime(path)) > SIDECAR_MAX_AGE_SECS:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def load_session():
    """Load stored session metadata. Returns (session_id, meta) or (None, None)."""
    try:
        with open(_state_path()) as f:
            meta = json.load(f)
            sid = meta.get("session_id")
            if sid:
                return sid, meta
    except (OSError, json.JSONDecodeError):
        pass
    return None, None


def save_session(session_id):
    """Persist session metadata atomically (unique tempfile + os.replace)."""
    os.makedirs(STATE_DIR, exist_ok=True)
    meta = {
        "session_id": session_id,
        "project_path": _project_root(),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    session_key = _session_key()
    if session_key:
        meta["session_key"] = session_key
    path = _state_path()
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp.", dir=STATE_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def clear_session():
    """Remove stale session state."""
    try:
        os.remove(_state_path())
    except OSError:
        pass


def extract_session_id(jsonl_output):
    """Pull session ID from codex --json output."""
    for line in jsonl_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "thread.started" and "thread_id" in event:
                return event["thread_id"]
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def extract_final_message(jsonl_output):
    """Pull the last agent message from codex --json output."""
    last_message = None
    for line in jsonl_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message" and "text" in item:
                    last_message = item["text"]
        except (json.JSONDecodeError, KeyError):
            continue
    return last_message


def _is_stale_resume_error(stderr_text):
    """Return True if stderr indicates the stored session can't be resumed."""
    lowered = stderr_text.lower()
    return any(marker in lowered for marker in STALE_RESUME_MARKERS)


def _mirror_to_monitor(level, message, stream_mode):
    """Mirror a critical diagnostic to stdout as a `>> level: ...` line.

    Claude Code's Monitor tool only surfaces stdout notifications live;
    stderr-only diagnostics stay invisible to the human until the
    subprocess exits. In monitor mode we emit a compact stdout line so
    stale-session notices, non-zero exits, and missing-agent-message
    conditions are visible in the conversation as they happen. In
    non-monitor mode this is a no-op — callers also print the full
    diagnostic to stderr.
    """
    if stream_mode != "monitor":
        return
    short = message.strip().replace("\n", " ")[:200]
    print(f">> {level}: {short}", flush=True)


def _event_to_progress_line(event):
    """Translate a JSONL event dict into a compact `>> ...` progress line.

    Returns None if the event carries no user-visible progress signal.
    Keeps lines short so Monitor notifications stay readable under
    long sessions with many tool calls.
    """
    ty = event.get("type")
    if ty == "thread.started":
        tid = event.get("thread_id", "?")
        short = tid[:8] + "…" if len(tid) > 8 else tid
        return f">> thread: {short}"
    if ty == "turn.started":
        return ">> turn started"
    if ty == "turn.completed":
        usage = event.get("usage") or {}
        inp = usage.get("input_tokens", 0)
        cached = usage.get("cached_input_tokens", 0)
        out = usage.get("output_tokens", 0)
        return f">> turn done: in={inp} cached={cached} out={out}"
    if ty == "item.started":
        item = event.get("item") or {}
        it = item.get("type")
        if it == "command_execution":
            cmd = item.get("command", "")
            if len(cmd) > 80:
                cmd = cmd[:77] + "..."
            return f">> tool: {cmd}"
        return f">> item started: {it}"
    if ty == "item.completed":
        item = event.get("item") or {}
        it = item.get("type")
        if it == "command_execution":
            exit_code = item.get("exit_code", "?")
            output = item.get("aggregated_output") or ""
            return f">> tool done: exit={exit_code} output={len(output)} bytes"
        if it == "agent_message":
            text_len = len(item.get("text") or "")
            return f">> agent message ready ({text_len} chars)"
        return f">> item done: {it}"
    return None


class StreamResult:
    """Lightweight container carrying the fields run_codex consumes."""

    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


async def _terminate_async(proc):
    """SIGTERM → SIGKILL escalation on the child process group."""
    if proc.returncode is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    except ProcessLookupError:
        pass


async def _feed_stdin(proc, prompt):
    """Write the prompt to the child's stdin and close it; tolerate broken pipe."""
    try:
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass


async def _drain_stderr(proc, sink):
    """Accumulate the child's stderr into `sink` line-by-line."""
    async for raw in proc.stderr:
        sink.append(raw.decode("utf-8", errors="replace"))


async def _drain_stdout(proc, sink, stream_mode, log_fh):
    """Accumulate stdout; in monitor mode, emit compact progress lines live."""
    async for raw in proc.stdout:
        decoded = raw.decode("utf-8", errors="replace")
        sink.append(decoded)
        if log_fh is not None:
            try:
                log_fh.write(decoded)
                log_fh.flush()
            except OSError:
                pass
        if stream_mode != "monitor":
            continue
        stripped = decoded.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        progress = _event_to_progress_line(event)
        if progress:
            print(progress, flush=True)


async def _run_codex_stream_async(cmd, prompt, stream_mode="off", log_fh=None):
    """asyncio.subprocess driver: runs codex, streams events, returns StreamResult.

    Concurrent stdin/stdout/stderr tasks gathered in the current event
    loop. The script still owns all parsing authority — callers use
    StreamResult.stdout for session-id and final-message extraction.

    Intentionally has no timeout: codex exec sessions can run without a
    hard time limit. Real failures surface via non-zero exit or a clean
    exit with no agent_message, both handled by the caller.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # Own process group so SIGINT/SIGTERM propagation is explicit.
        # start_new_session=True is equivalent to preexec_fn=os.setsid
        # but avoids the fork/async-safety hazards of preexec_fn.
        start_new_session=True,
    )

    stdout_sink = []
    stderr_sink = []

    stdin_task = asyncio.create_task(_feed_stdin(proc, prompt))
    stdout_task = asyncio.create_task(
        _drain_stdout(proc, stdout_sink, stream_mode, log_fh)
    )
    stderr_task = asyncio.create_task(_drain_stderr(proc, stderr_sink))

    try:
        await asyncio.gather(stdin_task, stdout_task, stderr_task)
    except BaseException:
        for task in (stdin_task, stdout_task, stderr_task):
            if not task.done():
                task.cancel()
        await _terminate_async(proc)
        raise

    returncode = await proc.wait()
    return StreamResult(
        returncode=returncode,
        stdout="".join(stdout_sink),
        stderr="".join(stderr_sink),
    )


def _run_codex_stream(cmd, prompt, stream_mode="off", log_fh=None):
    """Sync entry point backed by the async driver.

    Preserved so callers and tests with synchronous expectations still
    work. Internally runs the async driver to completion on the current
    thread. If an event loop is already running, we schedule on it;
    otherwise we create one via asyncio.run.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            _run_codex_stream_async(cmd, prompt, stream_mode=stream_mode, log_fh=log_fh)
        )
    # Running inside an existing loop — expose the coroutine directly.
    # The caller must `await` it. This branch exists for embedding use.
    return _run_codex_stream_async(cmd, prompt, stream_mode=stream_mode, log_fh=log_fh)


def _open_log():
    """Open a JSONL log file if CODEX_OPINION_LOG=1; else return None."""
    if os.environ.get("CODEX_OPINION_LOG", "").strip() != "1":
        return None
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        return open(_log_path_for_project(_project_key()), "w")
    except OSError:
        return None


def _finalize(msg, stream_mode, sidecar_path):
    """Handoff after a successful run.

    In monitor mode, write the final message to the sidecar file and
    emit a final `>> final-message: <path>` progress line for Claude
    Code's Monitor tool to pick up; return "" so main() prints nothing
    further to stdout (progress already streamed). Otherwise return
    `msg` for main() to print, matching the pre-streaming contract.
    """
    if stream_mode == "monitor" and sidecar_path:
        try:
            os.makedirs(SIDECAR_DIR, exist_ok=True)
            with open(sidecar_path, "w") as f:
                f.write(msg)
        except OSError:
            # Fall back to inline: print the message directly.
            print(">> final-message: (sidecar write failed; message below)", flush=True)
            return msg
        print(f">> final-message: {sidecar_path}", flush=True)
        return ""
    return msg


async def run_codex_async(prompt):
    """Send `prompt` to codex exec, resuming the prior session if present."""

    _gc_old_sidecars()
    root = _project_root()
    session_id, meta = load_session()
    stream_mode = _stream_mode()
    sidecar_path = _sidecar_path_for_pid(os.getpid()) if stream_mode == "monitor" else None
    log_fh = _open_log()

    try:
        if session_id:
            # `-C` is a parent option of `codex exec`; placing it after `resume`
            # is rejected as an unknown argument by the CLI parser.
            cmd = [
                "codex", "exec", "-C", root, "resume", session_id,
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--json", "-",
            ]
            result = await _run_codex_stream_async(
                cmd, prompt, stream_mode=stream_mode, log_fh=log_fh,
            )
            stderr = result.stderr.strip()

            if result.returncode == 0:
                msg = extract_final_message(result.stdout)
                if msg:
                    save_session(session_id)
                    return _finalize(msg, stream_mode, sidecar_path)
                # Clean exit but no agent message — do NOT silently retry,
                # because the prompt may have non-idempotent side effects.
                no_msg = "[codex-opinion] Codex exited cleanly but produced no agent message."
                print(no_msg, file=sys.stderr)
                _mirror_to_monitor("error", no_msg, stream_mode)
                if stderr:
                    print(stderr, file=sys.stderr)
                sys.exit(1)

            if not _is_stale_resume_error(stderr):
                if stderr:
                    print(stderr, file=sys.stderr)
                exit_msg = f"[codex resume exited {result.returncode}]"
                print(exit_msg, file=sys.stderr)
                _mirror_to_monitor("error", f"resume failed ({result.returncode}): {stderr or 'no stderr'}", stream_mode)
                sys.exit(1)

            updated = (meta or {}).get("updated_at", "unknown")
            stale_msg = (
                f"[codex-opinion] Session {session_id} (last used {updated}) is stale "
                f"({stderr}) — starting fresh."
            )
            print(stale_msg, file=sys.stderr)
            _mirror_to_monitor("warning", f"stale session, starting fresh: {session_id}", stream_mode)
            # Re-check before clearing: a concurrent invocation may have already
            # replaced the stale ID with a fresh one. Best-effort — still a tiny
            # TOCTOU window without flock, which is intentionally rejected here.
            current_id, _ = load_session()
            if current_id == session_id:
                clear_session()

        # Fresh session
        cmd = [
            "codex", "exec", "-C", root,
            "--dangerously-bypass-approvals-and-sandbox",
            "--json", "--skip-git-repo-check", "-",
        ]
        result = await _run_codex_stream_async(
            cmd, prompt, stream_mode=stream_mode, log_fh=log_fh,
        )
        stderr = result.stderr.strip()

        if result.returncode != 0:
            if stderr:
                print(stderr, file=sys.stderr)
            exit_msg = f"[codex exited {result.returncode}]"
            print(exit_msg, file=sys.stderr)
            _mirror_to_monitor("error", f"codex failed ({result.returncode}): {stderr or 'no stderr'}", stream_mode)
            sys.exit(1)

        msg = extract_final_message(result.stdout)
        new_id = extract_session_id(result.stdout)

        if msg and new_id:
            save_session(new_id)

        if not msg:
            # Mirror the resume-path diagnostic; do NOT persist a thread that
            # produced no answer so the next call won't resume it.
            no_msg = "[codex-opinion] Codex exited cleanly but produced no agent message."
            print(no_msg, file=sys.stderr)
            _mirror_to_monitor("error", no_msg, stream_mode)
            if stderr:
                print(stderr, file=sys.stderr)
            sys.exit(1)

        return _finalize(msg, stream_mode, sidecar_path)
    finally:
        if log_fh is not None:
            try:
                log_fh.close()
            except OSError:
                pass


def run_codex(prompt):
    """Sync entry: runs the async pipeline to completion and returns the payload.

    Kept for tests and scripts that want a synchronous call shape.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_codex_async(prompt))
    # If a loop is already running, return the coroutine for the caller
    # to await (embedding use).
    return run_codex_async(prompt)


async def main_async():
    if not shutil.which("codex"):
        print("Codex CLI not found — install with: npm i -g @openai/codex", file=sys.stderr)
        sys.exit(1)

    if sys.stdin.isatty():
        print("No input piped. Usage: echo 'prompt' | python3 ask_codex.py", file=sys.stderr)
        sys.exit(1)

    # Read stdin off the event-loop so we don't block other tasks once
    # the script grows. For a single-subprocess script this is cosmetic
    # but keeps the pipeline uniformly non-blocking.
    loop = asyncio.get_running_loop()
    stdin_content = await loop.run_in_executor(None, sys.stdin.read)

    if not stdin_content.strip():
        print("Empty input — pipe a complete prompt instead.", file=sys.stderr)
        sys.exit(1)

    # Optional positional prefix — prepended to stdin with a blank-line
    # separator. Usually empty; Claude Code bakes framing into stdin.
    prefix = " ".join(sys.argv[1:]).strip()
    prompt = f"{prefix}\n\n{stdin_content}" if prefix else stdin_content

    result = await run_codex_async(prompt)
    if result:
        print(result)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
