#!/usr/bin/env python3
"""Route a prompt to Codex CLI for a second opinion.

Reads content from stdin, sends it to `codex exec` with full permissions
using your configured Codex model and settings. Resumes the prior Codex
session for the current Claude Code session and project.

Usage:
    git diff HEAD | python3 ask_codex.py
    echo "explain this" | python3 ask_codex.py "focus on error handling"
"""

import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
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


def _project_key():
    """Derive a stable key for the current project from its git repo root."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        ).stdout.strip()
    except OSError:
        root = ""
    if not root:
        root = os.getcwd()
    return hashlib.sha256(root.encode()).hexdigest()[:16]


def _claude_code_pid():
    """Walk up the process tree to find the Claude Code process PID.

    Works regardless of nesting depth — handles direct invocation,
    Monitor, test wrappers, nested shells, etc. Falls back to parent
    PID if no Claude process is found.
    """
    pid = os.getpid()
    visited = set()
    while pid > 1 and pid not in visited:
        visited.add(pid)
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                capture_output=True, text=True,
            )
            line = result.stdout.strip()
            parts = line.split(None, 1)
            ppid = int(parts[0])
            comm = parts[1] if len(parts) > 1 else ""
            if "claude" in comm.lower() and "codex" not in comm.lower():
                return pid
            pid = ppid
        except (ValueError, IndexError, OSError):
            break
    ppid = os.getppid()
    return ppid if ppid > 1 else os.getpid()


def _is_pid_alive(pid):
    """Check if a PID corresponds to a running process."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _state_path(claude_pid):
    """Return the session state file path, scoped by project and Claude session."""
    proj = _project_key()
    return os.path.join(STATE_DIR, f"{proj}_{claude_pid}.json")


def _cleanup_dead(project_key, exclude_pid=None):
    """Remove state files for dead Claude Code PIDs on this project.

    Called on every invocation so dead files don't accumulate, even when
    the current session already has its own file.
    """
    pattern = os.path.join(STATE_DIR, f"{project_key}_*.json")
    for path in glob.glob(pattern):
        basename = os.path.basename(path)
        try:
            pid_str = basename[len(project_key) + 1 : -len(".json")]
            pid = int(pid_str)
        except (ValueError, IndexError):
            continue
        if pid == exclude_pid:
            continue  # Don't touch our own or the one we're about to adopt
        if not _is_pid_alive(pid):
            try:
                os.remove(path)
            except OSError:
                pass


def load_session(claude_pid):
    """Load session for this project, adopting a prior session if available.

    Priority:
    1. Our own PID's state file (resume within same Claude Code session)
    2. The most recent state file from a dead Claude Code session (adopt
       for continuity — Codex keeps its accumulated codebase knowledge)
    3. None (start fresh)

    Concurrent live sessions are never touched — each keeps its own file.
    Dead files are cleaned up on every invocation.
    """
    project_key = _project_key()

    # 1. Check our own file first
    our_path = _state_path(claude_pid)
    try:
        with open(our_path) as f:
            meta = json.load(f)
            if meta.get("session_id"):
                # Clean up dead files from other sessions while we're here
                _cleanup_dead(project_key, exclude_pid=claude_pid)
                return meta["session_id"], meta
    except (OSError, json.JSONDecodeError, KeyError):
        pass

    # 2. Look for adoptable sessions from dead Claude Code PIDs
    pattern = os.path.join(STATE_DIR, f"{project_key}_*.json")
    candidates = []
    for path in glob.glob(pattern):
        if path == our_path:
            continue
        basename = os.path.basename(path)
        try:
            pid_str = basename[len(project_key) + 1 : -len(".json")]
            pid = int(pid_str)
        except (ValueError, IndexError):
            continue
        if _is_pid_alive(pid):
            continue  # Live concurrent session — don't touch
        try:
            with open(path) as f:
                meta = json.load(f)
            candidates.append((path, pid, meta))
        except (OSError, json.JSONDecodeError):
            continue

    if candidates:
        # Pick the most recently saved dead session
        candidates.sort(key=lambda x: x[2].get("updated_at", ""), reverse=True)
        best_path, best_pid, best_meta = candidates[0]

        # Adopt via atomic rename: move old file to our PID.
        # os.rename is atomic on the same filesystem, so two new sessions
        # racing on the same candidate won't both succeed — the loser's
        # rename fails with FileNotFoundError and falls through to fresh.
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            os.rename(best_path, our_path)
        except (OSError, FileNotFoundError):
            # Another session grabbed it first — start fresh
            return None, None

        # Update metadata in the adopted file
        best_meta["claude_pid"] = claude_pid
        with open(our_path, "w") as f:
            json.dump(best_meta, f, indent=2)

        # Clean up remaining dead sessions
        for path, _, _ in candidates[1:]:
            try:
                os.remove(path)
            except OSError:
                pass

        sid = best_meta.get("session_id")
        if sid:
            print(
                f"[codex-opinion] Adopting session {sid[:12]}... "
                f"from a previous Claude Code session.",
                file=sys.stderr,
            )
            return sid, best_meta

    return None, None


def save_session(session_id, claude_pid):
    """Persist session metadata for future resume calls."""
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        project_path = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        ).stdout.strip()
    except OSError:
        project_path = os.getcwd()
    meta = {
        "session_id": session_id,
        "project_path": project_path or os.getcwd(),
        "claude_pid": claude_pid,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(_state_path(claude_pid), "w") as f:
        json.dump(meta, f, indent=2)


def clear_session(claude_pid):
    """Remove stale session state."""
    try:
        os.remove(_state_path(claude_pid))
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


def run_codex(stdin_content, instruction):
    """Run codex exec, resuming the prior session for this Claude Code session."""

    claude_pid = _claude_code_pid()

    session_id, meta = load_session(claude_pid)

    if session_id:
        full_prompt = f"{instruction}\n\n{stdin_content}"
        cmd = [
            "codex", "exec", "resume", session_id,
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json", "-",
        ]
        proc = subprocess.run(
            cmd, input=full_prompt, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            msg = extract_final_message(proc.stdout)
            if msg:
                actual_id = extract_session_id(proc.stdout) or session_id
                save_session(actual_id, claude_pid)
                return msg
        # Resume failed — start fresh and tell the caller
        updated = (meta or {}).get("updated_at", "unknown")
        print(
            f"[codex-opinion] Session {session_id} (last used {updated}) "
            f"could not be resumed — starting fresh.",
            file=sys.stderr,
        )
        clear_session(claude_pid)

    # Fresh session
    full_prompt = f"{instruction}\n\n{stdin_content}"
    cmd = [
        "codex", "exec",
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
        save_session(new_id, claude_pid)

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

    instruction = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_INSTRUCTION

    output = run_codex(stdin_content, instruction)
    if output:
        print(output)
    else:
        print("Codex returned no output.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
