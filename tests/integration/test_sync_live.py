"""Single env-gated live integration test against the real Codex CLI.

Skipped unless CODEX_OPINION_RUN_LIVE_TESTS=1 is set. Uses a unique
CODEX_OPINION_SESSION_KEY per run so it doesn't touch the developer's
normal project thread.

Covers the happy path end-to-end:
  1. First invocation with no prior state creates a session file.
  2. Second invocation resumes the same thread_id.
Nothing else. If this passes, fresh + resume + final-message extraction
are all working against the real codex JSONL shape.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import unittest


SCRIPT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "plugins", "codex-opinion", "skills", "codex-opinion", "scripts", "ask_codex.py",
))

LIVE = os.environ.get("CODEX_OPINION_RUN_LIVE_TESTS", "").strip() == "1"


def _run_script(prompt, env_overrides=None, timeout=120):
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.Popen(
        [sys.executable, SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise
    return proc.returncode, stdout, stderr


@unittest.skipUnless(LIVE, "set CODEX_OPINION_RUN_LIVE_TESTS=1 to run")
@unittest.skipUnless(shutil.which("codex"), "codex CLI not installed")
class SyncLiveTest(unittest.TestCase):
    def test_fresh_then_resume(self):
        session_key = f"itest-{os.getpid()}-{int(time.time())}"
        env = {"CODEX_OPINION_SESSION_KEY": session_key}

        # First call: fresh. Should succeed and write a state file with a
        # non-empty session_id.
        rc, stdout, stderr = _run_script("Respond with exactly one word: hi", env_overrides=env)
        self.assertEqual(rc, 0, stderr)
        self.assertTrue(stdout.strip())

        state_dir = os.path.join(
            os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
            "codex-opinion",
        )
        # Find the file by session_key stored inside rather than filename.
        matched = None
        for f in os.listdir(state_dir) if os.path.isdir(state_dir) else []:
            p = os.path.join(state_dir, f)
            if not p.endswith(".json"):
                continue
            try:
                with open(p) as fh:
                    meta = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("session_key") == session_key:
                matched = (p, meta)
                break
        self.assertIsNotNone(matched, "state file for this session_key was not written")
        first_sid = matched[1]["session_id"]
        self.assertTrue(first_sid)

        # Second call: resume. Should succeed and the state file's
        # session_id should remain the same (or be re-saved equal).
        rc, stdout2, stderr2 = _run_script("And now reply with exactly one word: bye", env_overrides=env)
        self.assertEqual(rc, 0, stderr2)
        self.assertTrue(stdout2.strip())

        with open(matched[0]) as fh:
            meta_after = json.load(fh)
        self.assertEqual(meta_after["session_id"], first_sid,
                         "resume should preserve the same thread_id")

        # Cleanup
        try:
            os.remove(matched[0])
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
