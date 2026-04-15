#!/usr/bin/env python3
"""Route a prompt to Codex CLI for a read-only second opinion.

Reads content from stdin, sends it to `codex exec` in a read-only sandbox,
and prints the response to stdout. Automatically resumes the previous Codex
session when one exists (1-hour TTL) so Codex maintains context across calls.

Usage:
    git diff HEAD | python3 ask_codex.py
    echo "explain this" | python3 ask_codex.py "focus on error handling"
"""

import os
import shutil
import subprocess
import sys
import time

STATE_FILE = "/tmp/codex-opinion-active"
TTL = 3600  # 1 hour

DEFAULT_INSTRUCTION = "Analyze the following and share your assessment."


def has_active_session():
    """Check if a recent Codex session exists."""
    try:
        age = time.time() - os.path.getmtime(STATE_FILE)
        return age < TTL
    except OSError:
        return False


def touch_state():
    """Mark that an active session exists."""
    with open(STATE_FILE, "w") as f:
        f.write(str(os.getpid()))


def clear_state():
    """Remove stale state."""
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def run_codex(stdin_content, instruction):
    """Run codex exec, resuming if a prior session exists."""

    if has_active_session():
        # Resume previous session for continuity
        cmd = ["codex", "exec", "resume", "--last", instruction]
        proc = subprocess.run(
            cmd,
            input=stdin_content,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            touch_state()
            return proc.stdout

        # Resume failed — fall through to fresh session
        clear_state()

    # Fresh session
    full_prompt = f"{instruction}\n\n{stdin_content}"
    cmd = ["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-"]
    proc = subprocess.run(
        cmd,
        input=full_prompt,
        capture_output=True,
        text=True,
    )

    if proc.returncode == 0:
        touch_state()
    else:
        # Print whatever Codex produced, even on failure
        output = proc.stdout.strip()
        if output:
            print(output)
        print(f"[codex exited {proc.returncode}]", file=sys.stderr)

    return proc.stdout


def main():
    if not shutil.which("codex"):
        print("Codex CLI not found — install with: npm i -g @openai/codex")
        return

    if sys.stdin.isatty():
        print("No input piped. Usage: echo 'context' | python3 ask_codex.py")
        return

    stdin_content = sys.stdin.read().strip()
    if not stdin_content:
        print("Empty input — nothing to analyze. If git diff is empty, pipe project context instead.")
        return

    instruction = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_INSTRUCTION

    try:
        output = run_codex(stdin_content, instruction)
        if output:
            print(output.strip())
    except Exception as e:
        print(f"Codex error: {e}")


if __name__ == "__main__":
    main()
