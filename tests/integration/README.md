# Live integration tests

These exercise the real Codex CLI end-to-end. They consume API tokens,
so they are **skipped by default**. Opt in with:

```bash
CODEX_OPINION_RUN_LIVE_TESTS=1 python3 -m unittest discover \
    -s tests/integration -p 'test_*.py' -v
```

Each test uses a unique `CODEX_OPINION_SESSION_KEY` so it doesn't touch
the developer's normal project thread.

- `test_streaming_live.py::test_stream_mode_trivial_prompt` — minimal
  prompt, asserts compact progress lines and a written sidecar file.
- `test_streaming_live.py::test_multi_tool_incremental_flush` — the
  regression guard that codex's JSONL events stream live (not batched
  at end) across multiple tool calls. Validates the refactor's core
  visibility promise on every future change.
- `test_streaming_live.py::test_default_mode_backward_compat` —
  silent run, final message on stdout, matching the pre-streaming
  contract.
