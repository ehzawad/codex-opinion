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


def _state_path():
    """Return the per-project session state file path."""
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
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(_state_path(), "w") as f:
        json.dump(meta, f, indent=2)


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


def run_codex(stdin_content, instruction):
    """Run codex exec, resuming the prior session for this project."""

    session_id, meta = load_session()

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
                save_session(actual_id)
                return msg
        # Resume failed — start fresh
        updated = (meta or {}).get("updated_at", "unknown")
        print(
            f"[codex-opinion] Session {session_id} (last used {updated}) "
            f"could not be resumed — starting fresh.",
            file=sys.stderr,
        )
        clear_session()

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

    instruction = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_INSTRUCTION

    output = run_codex(stdin_content, instruction)
    if output:
        print(output)
    else:
        print("Codex returned no output.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
