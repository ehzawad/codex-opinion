#!/usr/bin/env python3
"""Route a prompt to Codex CLI for a second opinion.

Reads content from stdin, sends it to `codex exec` with full permissions
using your configured Codex model and settings. Resumes the prior Codex
session for the current project.

Usage:
    git diff HEAD | python3 ask_codex.py
    echo "explain this" | python3 ask_codex.py "focus on error handling"
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
    "codex-opinion",
)

DEFAULT_INSTRUCTION = (
    "Read the project structure, key files, and architectural decisions. "
    "Understand the codebase as a developer, reviewer, and system architect. "
    "Then give a second-opinion review: correctness, bugs, regressions, "
    "risky assumptions, incomplete assumptions, trade-offs, and anything "
    "you would flag in a thorough code or architecture review. "
    "Prioritize actionable findings. If nothing material stands out, say so clearly. "
    "Take full effort, no rush, no panic — just take your time and do the job thoroughly."
)

# Lowercased stderr substrings from `codex exec resume` that indicate the
# stored session can no longer be resumed (stale/expired/missing). On match
# we start fresh; any other failure is surfaced verbatim and exits non-zero.
# Add new variants here as Codex CLI evolves its wording.
STALE_RESUME_MARKERS = (
    "no rollout found",
    "thread not found",
    "session not found",
    "session expired",
    "thread expired",
)


def _project_root():
    """Return the git repo root for the current dir, falling back to cwd."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        ).stdout.strip()
    except OSError:
        root = ""
    return root or os.getcwd()


def _project_key():
    """Stable per-project key derived from the git repo root."""
    return hashlib.sha256(_project_root().encode()).hexdigest()[:16]


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
    except (OSError, json.JSONDecodeError, KeyError):
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


def run_codex(stdin_content, instruction):
    """Run codex exec, resuming the prior session for this project."""

    root = _project_root()
    session_id, meta = load_session()
    full_prompt = f"{instruction}\n\n{stdin_content}"

    if session_id:
        # `-C` is a parent option of `codex exec`; placing it after `resume`
        # is rejected as an unknown argument by the CLI parser.
        cmd = [
            "codex", "exec", "-C", root, "resume", session_id,
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json", "-",
        ]
        proc = subprocess.run(
            cmd, input=full_prompt, capture_output=True, text=True,
        )
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
            # Real failure (auth, network, config, …) — surface and exit.
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
        # replaced the stale ID with a fresh one. Only delete if it's still ours.
        # Best-effort — there's still a tiny TOCTOU window without flock, but
        # flock is intentionally rejected in this project.
        current_id, _ = load_session()
        if current_id == session_id:
            clear_session()

    # Fresh session
    cmd = [
        "codex", "exec", "-C", root,
        "--dangerously-bypass-approvals-and-sandbox",
        "--json", "--skip-git-repo-check", "-",
    ]
    proc = subprocess.run(
        cmd, input=full_prompt, capture_output=True, text=True,
    )

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if stderr:
            print(stderr, file=sys.stderr)
        print(f"[codex exited {proc.returncode}]", file=sys.stderr)
        sys.exit(1)

    new_id = extract_session_id(proc.stdout)
    if new_id:
        save_session(new_id)

    msg = extract_final_message(proc.stdout)
    return msg


def main():
    if not shutil.which("codex"):
        print("Codex CLI not found — install with: npm i -g @openai/codex", file=sys.stderr)
        sys.exit(1)

    if sys.stdin.isatty():
        print("No input piped. Usage: echo 'context' | python3 ask_codex.py", file=sys.stderr)
        sys.exit(1)

    stdin_content = sys.stdin.read().strip()
    if not stdin_content:
        print("Empty input — pipe project context instead.", file=sys.stderr)
        sys.exit(1)

    # Args augment the default review prompt rather than replacing it.
    # This keeps the thorough framing in place and lets user text act as
    # an additional focus directive.
    focus = " ".join(sys.argv[1:]).strip()
    instruction = DEFAULT_INSTRUCTION
    if focus:
        instruction = f"{DEFAULT_INSTRUCTION}\n\nAdditional user focus: {focus}"

    output = run_codex(stdin_content, instruction)
    if output:
        print(output)
    else:
        print("Codex returned no output.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
