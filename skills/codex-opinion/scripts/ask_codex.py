#!/usr/bin/env python3
"""Route a prompt to Codex CLI for a second opinion.

Reads content from stdin, sends it to `codex exec` with full permissions
and the most capable model. Resumes the exact prior session by stored
session ID for continuity across calls.

Usage:
    git diff HEAD | python3 ask_codex.py
    echo "explain this" | python3 ask_codex.py "focus on error handling"
"""

import json
import os
import shutil
import subprocess
import sys
import time

STATE_FILE = "/tmp/codex-opinion-session"
TTL = 3600  # 1 hour

DEFAULT_INSTRUCTION = "Analyze the following and share your assessment."


def load_session():
    """Load stored session ID if recent enough."""
    try:
        age = time.time() - os.path.getmtime(STATE_FILE)
        if age >= TTL:
            return None
        with open(STATE_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_session(session_id):
    """Persist the session ID for future resume calls."""
    with open(STATE_FILE, "w") as f:
        f.write(session_id)


def clear_session():
    """Remove stale session state."""
    try:
        os.remove(STATE_FILE)
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
    """Run codex exec, resuming the exact prior session if one exists."""

    session_id = load_session()

    if session_id:
        full_prompt = f"{instruction}\n\n{stdin_content}"
        cmd = [
            "codex", "exec", "resume", session_id,
            "--dangerously-bypass-approvals-and-sandbox",
            "--json", "-",
        ]
        proc = subprocess.run(
            cmd, input=full_prompt, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            msg = extract_final_message(proc.stdout)
            if msg:
                save_session(session_id)
                return msg
        # Resume failed — fall through to fresh session
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
