# codex-opinion

A Claude Code plugin that gets a second opinion from OpenAI's Codex CLI on your work.

When you invoke `codex-opinion`, Claude pipes your diff, plan, or context to `codex exec` running at full capability. Codex can read the codebase, run commands, and do deep analysis. Claude reads the response and reports back.

Codex maintains session continuity by storing the exact session ID — follow-up calls resume that session so Codex builds on its prior analysis.

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- [OpenAI Codex CLI](https://developers.openai.com/codex/cli) installed and authenticated (`npm i -g @openai/codex`)

## Install

### As a plugin (recommended)

```bash
git clone https://github.com/ehzawad/codex-opinion.git ~/.claude/plugins/local/codex-opinion
```

Then load it in a session:

```bash
claude --plugin-dir ~/.claude/plugins/local/codex-opinion
```

### Manual install

```bash
mkdir -p ~/.claude/skills/codex-opinion/scripts
cp skills/codex-opinion/SKILL.md ~/.claude/skills/codex-opinion/
cp skills/codex-opinion/scripts/ask_codex.py ~/.claude/skills/codex-opinion/scripts/
chmod +x ~/.claude/skills/codex-opinion/scripts/ask_codex.py
```

## Usage

In any Claude Code session, type `codex-opinion` or invoke the skill:

```
codex-opinion
```

With a custom instruction:

```
codex-opinion focus on security vulnerabilities
```

Claude will pipe the relevant context to Codex, read the analysis, and report back.

## How it works

```
User prompt
    │
    ▼
Claude Code ──pipes diff/plan──▶ ask_codex.py ──▶ codex exec (full capability)
    │                                                      │
    ◀──────────── reads stdout ◀──────────────────────────┘
    │
    ▼
Reports what Codex found
```

- First call starts a fresh Codex session (captures session ID via `--json`)
- Follow-up calls resume that exact session by ID (1-hour TTL)
- Codex runs with full permissions for thorough analysis

## License

MIT
