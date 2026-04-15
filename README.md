# codex-opinion

A Claude Code plugin that gets a read-only second opinion from OpenAI's Codex CLI on your work.

When you invoke `/codex-opinion`, Claude pipes your diff, plan, or context to `codex exec -s read-only`. Codex analyzes your code but **cannot modify anything** — the read-only sandbox is enforced at the OS level. Claude reads Codex's response, fixes what it catches, and summarizes the findings.

Codex maintains session continuity across calls via `codex exec resume --last`, so follow-up reviews build on prior context.

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

Or add to your project's `.claude/settings.json`:

```json
{
  "plugins": ["~/.claude/plugins/local/codex-opinion"]
}
```

### Manual install

Copy the files into your user-level Claude Code config:

```bash
# Skill
mkdir -p ~/.claude/skills/codex-opinion/scripts
cp skills/codex-opinion/SKILL.md ~/.claude/skills/codex-opinion/
cp skills/codex-opinion/scripts/ask_codex.py ~/.claude/skills/codex-opinion/scripts/
chmod +x ~/.claude/skills/codex-opinion/scripts/ask_codex.py

# Command (registers /codex-opinion)
mkdir -p ~/.claude/commands
cp commands/codex-opinion.md ~/.claude/commands/
```

## Usage

In any Claude Code session:

```
/codex-opinion
```

With a custom instruction:

```
/codex-opinion focus on security vulnerabilities
```

Claude will pipe the relevant context to Codex, read the analysis, and report back.

## How it works

```
User prompt
    │
    ▼
Claude Code ──pipes diff/plan──▶ ask_codex.py ──▶ codex exec -s read-only
    │                                                      │
    ◀──────────── reads stdout ◀──────────────────────────┘
    │
    ▼
Fixes issues, summarizes findings
```

- First call starts a fresh Codex session
- Follow-up calls use `codex exec resume --last` for continuity (1-hour TTL)
- Codex runs in `read-only` sandbox — it can read your codebase but cannot write, edit, or delete anything

## License

MIT
