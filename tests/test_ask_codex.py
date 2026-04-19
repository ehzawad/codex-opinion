"""Unit tests for ask_codex.py.

Runs without the Codex CLI installed. Covers the pure helpers:
key computation, state file I/O, JSONL parsing, stale-resume detection.

Lives outside the plugin subtree so end-user installs don't bundle it.
Run from repo root:
    python3 -m unittest discover -s tests -p 'test_*.py'
"""

import asyncio
import hashlib
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..",
    "plugins", "codex-opinion", "skills", "codex-opinion", "scripts",
))
sys.path.insert(0, SCRIPTS_DIR)

import ask_codex  # noqa: E402


FIXED_PROJECT_ROOT = "/fixed/project/root"
FIXED_PROJECT_HASH = hashlib.sha256(FIXED_PROJECT_ROOT.encode()).hexdigest()[:16]


def _env_without_session_key():
    """Current env minus CODEX_OPINION_SESSION_KEY, for patch.dict base."""
    return {k: v for k, v in os.environ.items() if k != "CODEX_OPINION_SESSION_KEY"}


class SessionKeyTests(unittest.TestCase):
    def test_unset_returns_empty(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            self.assertEqual(ask_codex._session_key(), "")

    def test_value_returned(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "foo"}, clear=False):
            self.assertEqual(ask_codex._session_key(), "foo")

    def test_whitespace_stripped(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "  spaced  "}, clear=False):
            self.assertEqual(ask_codex._session_key(), "spaced")

    def test_whitespace_only_is_empty(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "   "}, clear=False):
            self.assertEqual(ask_codex._session_key(), "")

    def test_empty_string_is_empty(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": ""}, clear=False):
            self.assertEqual(ask_codex._session_key(), "")


class ProjectKeyTests(unittest.TestCase):
    def setUp(self):
        self.project_patcher = patch.object(
            ask_codex, "_project_root", return_value=FIXED_PROJECT_ROOT
        )
        self.project_patcher.start()
        self.addCleanup(self.project_patcher.stop)

    def test_no_session_key_returns_project_hash(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            self.assertEqual(ask_codex._project_key(), FIXED_PROJECT_HASH)

    def test_with_session_key_appends_suffix(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "foo"}, clear=False):
            key = ask_codex._project_key()
        self.assertTrue(key.startswith(FIXED_PROJECT_HASH + "-"))
        suffix = key.split("-", 1)[1]
        self.assertEqual(len(suffix), 16)
        self.assertEqual(suffix, hashlib.sha256(b"foo").hexdigest()[:16])

    def test_distinct_session_keys_produce_distinct_suffixes(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "foo"}, clear=False):
            key_foo = ask_codex._project_key()
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "bar"}, clear=False):
            key_bar = ask_codex._project_key()
        self.assertNotEqual(key_foo, key_bar)

    def test_empty_session_key_falls_back_to_project_only(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": ""}, clear=False):
            self.assertEqual(ask_codex._project_key(), FIXED_PROJECT_HASH)

    def test_whitespace_session_key_falls_back_to_project_only(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "   "}, clear=False):
            self.assertEqual(ask_codex._project_key(), FIXED_PROJECT_HASH)


class StatePathTests(unittest.TestCase):
    def setUp(self):
        self.project_patcher = patch.object(
            ask_codex, "_project_root", return_value=FIXED_PROJECT_ROOT
        )
        self.project_patcher.start()
        self.addCleanup(self.project_patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_patcher = patch.object(ask_codex, "STATE_DIR", self.tmp.name)
        self.state_patcher.start()
        self.addCleanup(self.state_patcher.stop)

    def test_path_without_session_key(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            path = ask_codex._state_path()
        expected = os.path.join(self.tmp.name, f"{FIXED_PROJECT_HASH}.json")
        self.assertEqual(path, expected)

    def test_path_with_session_key_includes_suffix(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "foo"}, clear=False):
            path = ask_codex._state_path()
        filename = os.path.basename(path)
        self.assertTrue(filename.startswith(FIXED_PROJECT_HASH + "-"))
        self.assertTrue(filename.endswith(".json"))
        self.assertNotEqual(filename, f"{FIXED_PROJECT_HASH}.json")


class StateIOTests(unittest.TestCase):
    def setUp(self):
        self.project_patcher = patch.object(
            ask_codex, "_project_root", return_value=FIXED_PROJECT_ROOT
        )
        self.project_patcher.start()
        self.addCleanup(self.project_patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_patcher = patch.object(ask_codex, "STATE_DIR", self.tmp.name)
        self.state_patcher.start()
        self.addCleanup(self.state_patcher.stop)

    def test_save_and_load_roundtrip(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            ask_codex.save_session("session-xyz")
            sid, meta = ask_codex.load_session()
        self.assertEqual(sid, "session-xyz")
        self.assertEqual(meta["project_path"], FIXED_PROJECT_ROOT)
        self.assertNotIn("session_key", meta)

    def test_save_includes_session_key_when_set(self):
        with patch.dict(os.environ, {"CODEX_OPINION_SESSION_KEY": "alpha"}, clear=False):
            ask_codex.save_session("s-alpha")
            sid, meta = ask_codex.load_session()
        self.assertEqual(sid, "s-alpha")
        self.assertEqual(meta["session_key"], "alpha")

    def test_load_missing_returns_none_pair(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            sid, meta = ask_codex.load_session()
        self.assertIsNone(sid)
        self.assertIsNone(meta)

    def test_load_corrupt_returns_none_pair(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            path = ask_codex._state_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write("{not json")
            sid, meta = ask_codex.load_session()
        self.assertIsNone(sid)
        self.assertIsNone(meta)

    def test_clear_session_removes_file(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            ask_codex.save_session("to-be-cleared")
            path = ask_codex._state_path()
            self.assertTrue(os.path.exists(path))
            ask_codex.clear_session()
            self.assertFalse(os.path.exists(path))

    def test_clear_session_missing_is_noop(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            ask_codex.clear_session()  # no save first — must not raise

    def test_save_leaves_no_tempfiles(self):
        with patch.dict(os.environ, _env_without_session_key(), clear=True):
            ask_codex.save_session("abc")
        leftovers = [f for f in os.listdir(self.tmp.name) if f.startswith(".tmp.")]
        self.assertEqual(leftovers, [])


class ExtractSessionIDTests(unittest.TestCase):
    def test_extracts_thread_id_from_thread_started(self):
        jsonl = "\n".join([
            '{"type": "thread.started", "thread_id": "uuid-1234"}',
            '{"type": "turn.started"}',
        ])
        self.assertEqual(ask_codex.extract_session_id(jsonl), "uuid-1234")

    def test_returns_none_when_thread_started_missing(self):
        jsonl = '{"type": "turn.started"}\n{"type": "turn.completed"}'
        self.assertIsNone(ask_codex.extract_session_id(jsonl))

    def test_tolerates_garbage_and_blank_lines(self):
        jsonl = "\n".join([
            "garbage text",
            "",
            '{"type": "thread.started", "thread_id": "uuid-x"}',
            "{malformed",
        ])
        self.assertEqual(ask_codex.extract_session_id(jsonl), "uuid-x")


class ExtractFinalMessageTests(unittest.TestCase):
    def test_returns_last_agent_message(self):
        jsonl = "\n".join([
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "first"}}',
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "second"}}',
            '{"type": "turn.completed"}',
        ])
        self.assertEqual(ask_codex.extract_final_message(jsonl), "second")

    def test_returns_none_when_no_agent_message(self):
        jsonl = "\n".join([
            '{"type": "turn.started"}',
            '{"type": "turn.completed"}',
        ])
        self.assertIsNone(ask_codex.extract_final_message(jsonl))

    def test_ignores_non_agent_item_types(self):
        jsonl = "\n".join([
            '{"type": "item.completed", "item": {"type": "tool_call", "text": "ignore"}}',
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "keeper"}}',
        ])
        self.assertEqual(ask_codex.extract_final_message(jsonl), "keeper")


class StaleResumeErrorTests(unittest.TestCase):
    def test_matches_exact_marker(self):
        self.assertTrue(ask_codex._is_stale_resume_error("no rollout found"))

    def test_matches_case_insensitive(self):
        self.assertTrue(ask_codex._is_stale_resume_error("No Rollout Found here"))

    def test_matches_session_expired(self):
        self.assertTrue(ask_codex._is_stale_resume_error("session expired at some point"))

    def test_non_stale_error_returns_false(self):
        self.assertFalse(ask_codex._is_stale_resume_error("auth failure: token rejected"))

    def test_empty_stderr_returns_false(self):
        self.assertFalse(ask_codex._is_stale_resume_error(""))


def _fresh_jsonl():
    return (
        '{"type": "thread.started", "thread_id": "new-sid"}\n'
        '{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}'
    )


def _resume_jsonl():
    return '{"type": "item.completed", "item": {"type": "agent_message", "text": "resumed"}}'


def _stream_result(stdout="", stderr="", returncode=0):
    return ask_codex.StreamResult(returncode=returncode, stdout=stdout, stderr=stderr)


class RunCodexCommandShapeTests(unittest.TestCase):
    """Guard the `-C` placement foot-gun for `codex exec resume`."""

    def test_resume_places_C_before_resume_keyword(self):
        captured = {}

        async def fake_stream(cmd, prompt, **_kwargs):
            captured["cmd"] = cmd
            return _stream_result(stdout=_resume_jsonl())

        with patch.object(ask_codex, "_run_codex_stream_async", side_effect=fake_stream), \
             patch.object(ask_codex, "load_session", return_value=("existing-sid", {"updated_at": "t"})), \
             patch.object(ask_codex, "save_session"):
            asyncio.run(ask_codex.run_codex_async("hi"))

        cmd = captured["cmd"]
        self.assertIn("-C", cmd)
        self.assertIn("resume", cmd)
        self.assertLess(
            cmd.index("-C"),
            cmd.index("resume"),
            f"'-C' must appear before 'resume' in: {cmd}",
        )

    def test_fresh_call_has_no_resume_keyword(self):
        captured = {}

        async def fake_stream(cmd, prompt, **_kwargs):
            captured["cmd"] = cmd
            return _stream_result(stdout=_fresh_jsonl())

        with patch.object(ask_codex, "_run_codex_stream_async", side_effect=fake_stream), \
             patch.object(ask_codex, "load_session", return_value=(None, None)), \
             patch.object(ask_codex, "save_session"):
            asyncio.run(ask_codex.run_codex_async("hi"))

        self.assertNotIn("resume", captured["cmd"])
        self.assertIn("-C", captured["cmd"])


class StreamModeTests(unittest.TestCase):
    def test_off_by_default(self):
        with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "CODEX_OPINION_STREAM"}, clear=True):
            self.assertEqual(ask_codex._stream_mode(), "off")

    def test_monitor_value(self):
        with patch.dict(os.environ, {"CODEX_OPINION_STREAM": "monitor"}, clear=False):
            self.assertEqual(ask_codex._stream_mode(), "monitor")

    def test_monitor_case_insensitive(self):
        with patch.dict(os.environ, {"CODEX_OPINION_STREAM": "Monitor  "}, clear=False):
            self.assertEqual(ask_codex._stream_mode(), "monitor")

    def test_unrecognized_values_are_off(self):
        with patch.dict(os.environ, {"CODEX_OPINION_STREAM": "verbose"}, clear=False):
            self.assertEqual(ask_codex._stream_mode(), "off")


class ProgressLineTests(unittest.TestCase):
    def test_thread_started_truncated_id(self):
        line = ask_codex._event_to_progress_line({
            "type": "thread.started",
            "thread_id": "019da6a4-55a3-72f1-849c-bdded4782a3b",
        })
        self.assertTrue(line.startswith(">> thread:"))
        self.assertIn("019da6a4", line)
        self.assertIn("…", line)

    def test_turn_started(self):
        self.assertEqual(
            ask_codex._event_to_progress_line({"type": "turn.started"}),
            ">> turn started",
        )

    def test_turn_completed_with_usage(self):
        line = ask_codex._event_to_progress_line({
            "type": "turn.completed",
            "usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 12},
        })
        self.assertEqual(line, ">> turn done: in=100 cached=50 out=12")

    def test_item_started_command_truncates_long_command(self):
        long_cmd = "/bin/zsh -lc " + ("X" * 200)
        line = ask_codex._event_to_progress_line({
            "type": "item.started",
            "item": {"type": "command_execution", "command": long_cmd},
        })
        self.assertTrue(line.startswith(">> tool: "))
        self.assertTrue(line.endswith("..."))
        self.assertLessEqual(len(line), len(">> tool: ") + 80)

    def test_item_completed_command(self):
        line = ask_codex._event_to_progress_line({
            "type": "item.completed",
            "item": {"type": "command_execution", "exit_code": 0, "aggregated_output": "hello world"},
        })
        self.assertEqual(line, ">> tool done: exit=0 output=11 bytes")

    def test_item_completed_agent_message(self):
        line = ask_codex._event_to_progress_line({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Hello!"},
        })
        self.assertEqual(line, ">> agent message ready (6 chars)")

    def test_unknown_type_returns_none(self):
        self.assertIsNone(ask_codex._event_to_progress_line({"type": "totally.unknown"}))


class GCSidecarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sidecar_dir = os.path.join(self.tmp.name, "lastmsg")
        os.makedirs(self.sidecar_dir, exist_ok=True)
        self.patcher = patch.object(ask_codex, "SIDECAR_DIR", self.sidecar_dir)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_removes_old_files_keeps_new(self):
        old = os.path.join(self.sidecar_dir, "old.txt")
        new = os.path.join(self.sidecar_dir, "new.txt")
        with open(old, "w") as f:
            f.write("old")
        with open(new, "w") as f:
            f.write("new")
        # Backdate old file beyond threshold.
        past = time.time() - (ask_codex.SIDECAR_MAX_AGE_SECS + 60)
        os.utime(old, (past, past))
        ask_codex._gc_old_sidecars()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))

    def test_missing_dir_is_noop(self):
        # Point at a non-existent directory.
        with patch.object(ask_codex, "SIDECAR_DIR", os.path.join(self.tmp.name, "nope")):
            ask_codex._gc_old_sidecars()  # must not raise


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sidecar_dir = os.path.join(self.tmp.name, "lastmsg")
        self.patcher = patch.object(ask_codex, "SIDECAR_DIR", self.sidecar_dir)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_default_mode_returns_message(self):
        result = ask_codex._finalize("the answer", stream_mode="off", sidecar_path=None)
        self.assertEqual(result, "the answer")

    def test_monitor_mode_writes_sidecar_and_returns_empty(self):
        import time as _t
        sidecar = os.path.join(self.sidecar_dir, f"{os.getpid()}-{_t.time()}.txt")
        captured_stdout = []
        with patch.object(ask_codex.sys, "stdout") as mock_stdout:
            mock_stdout.write = lambda s: captured_stdout.append(s) or len(s)
            mock_stdout.flush = lambda: None
            result = ask_codex._finalize("monitor answer", stream_mode="monitor", sidecar_path=sidecar)
        self.assertEqual(result, "")
        self.assertTrue(os.path.exists(sidecar))
        with open(sidecar) as f:
            self.assertEqual(f.read(), "monitor answer")
        # Sentinel line was printed.
        joined = "".join(captured_stdout)
        self.assertIn(">> final-message:", joined)
        self.assertIn(sidecar, joined)


class StreamDriverTests(unittest.TestCase):
    """_run_codex_stream_async exercised against real python3 subprocesses.

    Rather than mock asyncio's subprocess transport (which requires real
    file descriptors), these tests invoke tiny python3 programs that
    emit scripted stdout/stderr, which is exactly what the real driver
    consumes. Fast (~0.1s each) and exercises real async I/O paths.
    """

    def _run_with_child(self, child_code, stream_mode="off"):
        """Spawn `python3 -c child_code` through the async driver."""
        captured_stdout = []
        with patch.object(ask_codex.sys, "stdout") as mock_stdout:
            mock_stdout.write = lambda s: captured_stdout.append(s) or len(s)
            mock_stdout.flush = lambda: None
            result = asyncio.run(ask_codex._run_codex_stream_async(
                [sys.executable, "-c", child_code],
                "",
                stream_mode=stream_mode,
            ))
        return result, "".join(captured_stdout)

    def test_default_mode_does_not_emit_progress(self):
        child = (
            "import sys\n"
            "for line in [\n"
            '    \'{"type": "thread.started", "thread_id": "abc"}\',\n'
            '    \'{"type": "turn.started"}\',\n'
            '    \'{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}\',\n'
            '    \'{"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}}\',\n'
            "]:\n"
            "    print(line, flush=True)\n"
        )
        result, stdout_captured = self._run_with_child(child, stream_mode="off")
        self.assertEqual(result.returncode, 0)
        self.assertIn("thread.started", result.stdout)
        self.assertIn("agent_message", result.stdout)
        self.assertNotIn(">>", stdout_captured)

    def test_monitor_mode_emits_compact_progress(self):
        child = (
            "import sys\n"
            "for line in [\n"
            '    \'{"type": "thread.started", "thread_id": "abcdef0123456789"}\',\n'
            '    \'{"type": "turn.started"}\',\n'
            '    \'{"type": "item.started", "item": {"type": "command_execution", "command": "/bin/zsh -lc ls"}}\',\n'
            '    \'{"type": "item.completed", "item": {"type": "command_execution", "exit_code": 0, "aggregated_output": "a\\\\nb\\\\nc"}}\',\n'
            '    \'{"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}\',\n'
            '    \'{"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 1}}\',\n'
            "]:\n"
            "    print(line, flush=True)\n"
        )
        result, stdout_captured = self._run_with_child(child, stream_mode="monitor")
        self.assertEqual(result.returncode, 0)
        self.assertIn(">> thread: abcdef01", stdout_captured)
        self.assertIn(">> turn started", stdout_captured)
        self.assertIn(">> tool: /bin/zsh -lc ls", stdout_captured)
        self.assertIn(">> tool done: exit=0 output=5 bytes", stdout_captured)
        self.assertIn(">> agent message ready (4 chars)", stdout_captured)
        self.assertIn(">> turn done: in=10 cached=2 out=1", stdout_captured)

    def test_malformed_json_line_skipped_not_raised(self):
        child = (
            "import sys\n"
            "print('not json', flush=True)\n"
            '''print('{"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}', flush=True)\n'''
        )
        result, stdout_captured = self._run_with_child(child, stream_mode="monitor")
        self.assertEqual(result.returncode, 0)
        self.assertIn(">> agent message ready (4 chars)", stdout_captured)

    def test_nonzero_returncode_surfaced(self):
        child = (
            "import sys\n"
            "sys.stderr.write('boom\\n')\n"
            "sys.stderr.flush()\n"
            "sys.exit(1)\n"
        )
        result, _ = self._run_with_child(child, stream_mode="off")
        self.assertEqual(result.returncode, 1)
        self.assertIn("boom", result.stderr)

    def test_concurrent_stdout_stderr_do_not_deadlock(self):
        """Heavy stderr alongside stdout should not hang."""
        child = (
            "import sys\n"
            "for i in range(200):\n"
            "    sys.stderr.write('E' * 200 + '\\n')\n"
            "    sys.stderr.flush()\n"
            "for i in range(5):\n"
            '    print(\'{"type":"turn.started"}\', flush=True)\n'
        )
        result, stdout_captured = self._run_with_child(child, stream_mode="monitor")
        self.assertEqual(result.returncode, 0)
        # Five turn.started events should each produce a progress line.
        self.assertEqual(stdout_captured.count(">> turn started"), 5)
        self.assertGreater(len(result.stderr), 1000)


if __name__ == "__main__":
    unittest.main()
