#!/usr/bin/env python3
"""Route a prompt to Codex CLI.

Pure transport: whatever is piped in on stdin is sent verbatim to
`codex exec` (or `codex exec resume` when a prior session exists for
this project). The caller — typically Claude Code via the skill — is
responsible for constructing a complete, self-framed prompt.

An optional positional argument is prepended to the stdin body with a
blank-line separator, as a convenience for direct CLI use. Most Claude
Code invocations should leave it empty and bake any framing into stdin.

Set CODEX_OPINION_SESSION_KEY in the environment to isolate a session's
Codex thread from the project-wide thread. Unset or empty falls back to
the default one-thread-per-project behavior.

Usage:
    echo "<full prompt with framing>" | python3 ask_codex.py
    echo "<context>" | python3 ask_codex.py "Optional prefix line"
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from functools import lru_cache

STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "codex-opinion",
)

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
    transitively from _project_key, _state_path, save_session, and
    run_codex. Without caching the sync `git rev-parse` runs 4-5 times
    per invocation.
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


def _run_codex_proc(cmd, prompt):
    """Invoke a codex subprocess and capture its output.

    Intentionally has no timeout: codex exec sessions can run without a
    hard time limit. Real failures surface via non-zero exit or a clean
    exit with no agent_message, both handled by the caller.
    """
    return subprocess.run(
        cmd, input=prompt, capture_output=True, text=True,
    )


def run_codex(prompt):
    """Send `prompt` to codex exec, resuming the prior session if present."""

    root = _project_root()
    session_id, meta = load_session()

    if session_id:
        # `-C` is a parent option of `codex exec`; placing it after `resume`
        # is rejected as an unknown argument by the CLI parser.
        cmd = [
            "codex", "exec", "-C", root, "resume", session_id,
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json", "-",
        ]
        proc = _run_codex_proc(cmd, prompt)
        stderr = proc.stderr.strip()

        if proc.returncode == 0:
            msg = extract_final_message(proc.stdout)
            if msg:
                save_session(session_id)
                return msg
            # Clean exit but no agent message — do NOT silently retry,
            # because the prompt may have non-idempotent side effects.
            print(
                "[codex-opinion] Codex exited cleanly but produced no agent message.",
                file=sys.stderr,
            )
            if stderr:
                print(stderr, file=sys.stderr)
            sys.exit(1)

        if not _is_stale_resume_error(stderr):
            if stderr:
                print(stderr, file=sys.stderr)
            print(f"[codex resume exited {proc.returncode}]", file=sys.stderr)
            sys.exit(1)

        updated = (meta or {}).get("updated_at", "unknown")
        print(
            f"[codex-opinion] Session {session_id} (last used {updated}) is stale "
            f"({stderr}) — starting fresh.",
            file=sys.stderr,
        )
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
    proc = _run_codex_proc(cmd, prompt)
    stderr = proc.stderr.strip()

    if proc.returncode != 0:
        if stderr:
            print(stderr, file=sys.stderr)
        print(f"[codex exited {proc.returncode}]", file=sys.stderr)
        sys.exit(1)

    msg = extract_final_message(proc.stdout)
    new_id = extract_session_id(proc.stdout)

    if msg and new_id:
        save_session(new_id)

    if not msg:
        # Mirror the resume-path diagnostic; do NOT persist a thread that
        # produced no answer so the next call won't resume it.
        print(
            "[codex-opinion] Codex exited cleanly but produced no agent message.",
            file=sys.stderr,
        )
        if stderr:
            print(stderr, file=sys.stderr)
        sys.exit(1)

    return msg


def main():
    if not shutil.which("codex"):
        print("Codex CLI not found — install with: npm i -g @openai/codex", file=sys.stderr)
        sys.exit(1)

    if sys.stdin.isatty():
        print("No input piped. Usage: echo 'prompt' | python3 ask_codex.py", file=sys.stderr)
        sys.exit(1)

    stdin_content = sys.stdin.read()
    if not stdin_content.strip():
        print("Empty input — pipe a complete prompt instead.", file=sys.stderr)
        sys.exit(1)

    # Optional positional prefix — prepended to stdin with a blank-line
    # separator. Usually empty; Claude Code bakes framing into stdin.
    prefix = " ".join(sys.argv[1:]).strip()
    prompt = f"{prefix}\n\n{stdin_content}" if prefix else stdin_content

    print(run_codex(prompt))


if __name__ == "__main__":
    main()
