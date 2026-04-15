---
name: codex-opinion
description: Pipe your plan or diff to Codex for a read-only second opinion. Invoke manually with /codex-opinion.
---

# Codex Second Opinion

Get a second opinion from OpenAI Codex on your current work.

## How to call

IMPORTANT: Always run the script as a **foreground** Bash command. Never run it in the background — you need to read stdout directly.

Default (pipe a diff):

```bash
git diff HEAD | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

Pipe any context (a plan, code snippet, question):

```bash
echo "<your context here>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py
```

With a custom instruction:

```bash
echo "<your context here>" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/codex-opinion/scripts/ask_codex.py "focus on security implications"
```

If the user passes extra text after `/codex-opinion`, use it as the custom instruction argument.

The script auto-resumes Codex's prior session so it maintains context across calls within the conversation.

## Rules

- Run the script in the **foreground**. Read stdout directly. No timeout — let Codex finish.
- **Max 2 calls** to the script per prompt.
- **Skip trivial changes** — typos, formatting, single-line fixes don't need a second opinion.
- **Fix what Codex catches** before responding to the user.
- **Summarize** what Codex found for the user. Don't dump raw output.
