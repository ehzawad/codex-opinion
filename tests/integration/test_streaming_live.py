"""Live integration tests against the real Codex CLI.

Skipped unless CODEX_OPINION_RUN_LIVE_TESTS=1. Each test uses a unique
CODEX_OPINION_SESSION_KEY so it doesn't touch the normal project thread.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "plugins", "codex-opinion", "skills", "codex-opinion", "scripts", "ask_codex.py",
))

LIVE = os.environ.get("CODEX_OPINION_RUN_LIVE_TESTS", "").strip() == "1"


def _run_script(prompt, env_overrides=None, timeout=120):
    """Invoke ask_codex.py with a prompt on stdin; return (rc, stdout, stderr)."""
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
class LiveStreamingTests(unittest.TestCase):
    def setUp(self):
        # Unique session key per test keeps each thread isolated.
        self.session_key = f"itest-{os.getpid()}-{int(time.time())}-{self._testMethodName}"

    def test_default_mode_backward_compat(self):
        rc, stdout, stderr = _run_script(
            "Respond with exactly one word: hi",
            env_overrides={"CODEX_OPINION_SESSION_KEY": self.session_key},
        )
        self.assertEqual(rc, 0, stderr)
        # Default mode: no streaming sentinel, plain text answer.
        self.assertNotIn(">>", stdout)
        self.assertTrue(stdout.strip(), "expected non-empty answer on stdout")

    def test_stream_mode_trivial_prompt(self):
        rc, stdout, stderr = _run_script(
            "Respond with exactly one word: hello",
            env_overrides={
                "CODEX_OPINION_SESSION_KEY": self.session_key,
                "CODEX_OPINION_STREAM": "monitor",
            },
        )
        self.assertEqual(rc, 0, stderr)
        self.assertIn(">> thread:", stdout)
        self.assertIn(">> turn started", stdout)
        self.assertIn(">> agent message ready", stdout)
        self.assertIn(">> turn done:", stdout)
        # Final-message sentinel points at a sidecar file that exists.
        final_lines = [l for l in stdout.splitlines() if l.startswith(">> final-message: ")]
        self.assertEqual(len(final_lines), 1)
        sidecar_path = final_lines[0][len(">> final-message: "):]
        self.assertTrue(os.path.exists(sidecar_path), f"sidecar missing: {sidecar_path}")
        with open(sidecar_path) as f:
            self.assertTrue(f.read().strip(), "sidecar is empty")

    def test_multi_tool_incremental_flush(self):
        """Regression guard: events stream live, not batched at end.

        Uses a prompt with three 15s shell sleeps. Records arrival
        timestamps of `>> tool done:` lines and asserts the first one
        arrives before the second sleep would finish (i.e., well under
        the total runtime), which is the strongest evidence that we're
        actually streaming.
        """
        prompt = (
            "Run exactly these as three separate shell commands, one after another, "
            "not combined:\n"
            "1. printf 'first-start\\n'; sleep 15; printf 'first-end\\n'\n"
            "2. printf 'second-start\\n'; sleep 15; printf 'second-end\\n'\n"
            "3. printf 'third-start\\n'; sleep 15; printf 'third-end\\n'\n"
            "Then reply with exactly: DONE\n"
        )
        env = dict(os.environ)
        env.update({
            "CODEX_OPINION_SESSION_KEY": self.session_key,
            "CODEX_OPINION_STREAM": "monitor",
        })
        proc = subprocess.Popen(
            [sys.executable, SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        tool_done_times = []
        t0 = time.monotonic()
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for line in proc.stdout:
                t = time.monotonic() - t0
                if line.startswith(">> tool done:"):
                    tool_done_times.append(t)
        finally:
            try:
                proc.stdout.close()
            except OSError:
                pass
            try:
                proc.stderr.close()
            except OSError:
                pass
            rc = proc.wait(timeout=180)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(len(tool_done_times), 3,
            f"expected >=3 tool-done events, got {len(tool_done_times)}")
        # Regression guard: first tool-done arrives well before the last
        # one; if events batched, they'd all arrive within a second.
        self.assertGreater(tool_done_times[-1] - tool_done_times[0], 10,
            "tool-done events look batched; streaming may be broken")

    def test_detach_watch_collect_end_to_end(self):
        """Detached codex run: kick off, watch to completion, collect final."""
        # detach: spawn codex detached; capture job-id from stdout
        rc, stdout, stderr = _run_script(
            "Respond with exactly: detached",
            env_overrides={
                "CODEX_OPINION_SESSION_KEY": self.session_key,
                "CODEX_OPINION_STREAM": "detach",
            },
        )
        self.assertEqual(rc, 0, stderr)
        job_id = None
        for line in stdout.splitlines():
            if line.startswith(">> job-id: "):
                job_id = line[len(">> job-id: "):].strip()
                break
        self.assertIsNotNone(job_id, f"no job-id line in detach output: {stdout}")

        # watch: tail the job until it completes
        rc, watch_stdout, watch_stderr = _run_script(
            "",
            env_overrides={
                "CODEX_OPINION_SESSION_KEY": self.session_key,
                "CODEX_OPINION_STREAM": "watch",
                "CODEX_OPINION_JOB_ID": job_id,
            },
            timeout=180,
        )
        self.assertEqual(rc, 0, watch_stderr)
        self.assertIn(">> final-message:", watch_stdout)
        self.assertIn(">> turn done:", watch_stdout)

        # collect: print the final answer
        rc, collect_stdout, collect_stderr = _run_script(
            "",
            env_overrides={
                "CODEX_OPINION_SESSION_KEY": self.session_key,
                "CODEX_OPINION_STREAM": "collect",
                "CODEX_OPINION_JOB_ID": job_id,
            },
        )
        self.assertEqual(rc, 0, collect_stderr)
        self.assertIn("detached", collect_stdout)

    def test_stream_mode_sidecar_gc(self):
        """Old sidecars get cleaned up on next invocation."""
        # Compute the sidecar dir, pre-populate with an aged dummy
        # file, then run ask_codex.py and verify cleanup.
        state_dir = os.path.join(
            os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
            "codex-opinion",
        )
        sidecar_dir = os.path.join(state_dir, "lastmsg")
        os.makedirs(sidecar_dir, exist_ok=True)
        victim = os.path.join(sidecar_dir, "ancient-dummy.txt")
        with open(victim, "w") as f:
            f.write("ancient")
        past = time.time() - (48 * 3600)
        os.utime(victim, (past, past))

        rc, stdout, stderr = _run_script(
            "Say exactly: bye",
            env_overrides={
                "CODEX_OPINION_SESSION_KEY": self.session_key,
                "CODEX_OPINION_STREAM": "monitor",
            },
        )
        self.assertEqual(rc, 0, stderr)
        self.assertFalse(os.path.exists(victim), "aged sidecar should be GC'd")


if __name__ == "__main__":
    unittest.main()
