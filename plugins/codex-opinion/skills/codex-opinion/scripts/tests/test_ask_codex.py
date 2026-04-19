"""Unit tests for ask_codex.py.

Runs without the Codex CLI installed. Covers the pure helpers:
key computation, state file I/O, JSONL parsing, stale-resume detection.

Run from repo root:
    python3 -m unittest discover \
        -s plugins/codex-opinion/skills/codex-opinion/scripts/tests \
        -p 'test_*.py'
"""

import hashlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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


if __name__ == "__main__":
    unittest.main()
