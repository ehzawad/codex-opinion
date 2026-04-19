# Live integration test

One env-gated test that exercises the real Codex CLI end-to-end. Skipped
by default because it consumes API tokens. Opt in with:

```bash
CODEX_OPINION_RUN_LIVE_TESTS=1 python3 -m unittest discover \
    -s tests/integration -p 'test_*.py' -v
```

Uses a unique `CODEX_OPINION_SESSION_KEY` per run so it doesn't touch
your normal project thread.

Covers the happy path only: fresh session creates a state file with a
non-empty session_id; a second call resumes the same thread_id. If this
passes, fresh + resume + final-message extraction are all working
against the current codex JSONL shape.
