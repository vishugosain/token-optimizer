# token-optimizer

A Claude Code plugin that cuts token usage. It targets the patterns that actually drive cost in real sessions:
- very large context that gets re-read on every turn
- sub-agents quietly inheriting the most expensive model
- whole-file reads and huge command output filling the context
- sessions left open for days

**Status:** v0.1.0, early pilot. Feedback welcome.

## Install

```bash
claude plugin marketplace add vishugosain/token-optimizer
```

```bash
claude plugin install token-optimizer@token-optimizer
```

Start a new session. Then, optionally, run `/token-optimizer:setup` to pick a preset, and `/token-optimizer:audit` to record your baseline.

Requires `python3` on your PATH.

## What it does

| Piece | Behaviour |
|---|---|
| Rules (session start) | A short set of token rules injected each session: plan before editing, read existing docs instead of re-exploring, put deliverables in files, Grep then Read with offset/limit, give sub-agents a cheap model, at most 3 sub-agents in parallel, one phase per session, save facts to a file before compacting. |
| Context guard | On each prompt, checks the real context size. Above your limit it shows a one-line warning and has Claude suggest `/compact` or a fresh session. It warns again only after another 25% of growth. It also warns when you resume a big session after the prompt cache has expired. It never blocks a prompt. |
| Read guard | The first whole-file Read of a large file is refused once, with guidance to use Grep or offset/limit. Repeating the same Read goes through. |
| `rename-helper`, `doc-writer` | Haiku sub-agents for mechanical edits and docs. |
| `/token-optimizer:setup` | Shows your settings and applies a Balanced or Max-savings preset, only after you confirm. |
| `/token-optimizer:audit` | Content-free usage report with a comparison over time. |

## Configuration

Set these in the `env` block of `~/.claude/settings.json` (or in a repo's `.claude/settings.json`):

| Variable | Default | Max savings | Meaning |
|---|---|---|---|
| `TOKEN_OPT_CONTEXT_LIMIT` | `250000` | `150000` | Context size (tokens) that triggers the guard. `0` turns it off. |
| `TOKEN_OPT_READ_MAX_LINES` | `1000` | `600` | Files longer than this get the read guard. `0` turns it off. |
| `TOKEN_OPT_IDLE_MINUTES` | `60` | `60` | Idle time after which resuming a big session triggers a warning. `0` turns it off. |
| `CLAUDE_CODE_SUBAGENT_MODEL` | inherit | `sonnet` | Claude Code setting: model for sub-agents that don't name one. |
| `BASH_MAX_OUTPUT_LENGTH` | Claude Code default | `15000` | Claude Code setting: max characters of Bash output kept in context. |

## What the audit reads

`/token-optimizer:audit` reads your local session logs (`~/.claude/projects/**/*.jsonl`) and records **numbers only**:
- token counts per model
- context sizes
- tool names and call counts
- sizes of tool results
- counts of sub-agents, compactions and errors
- the settings listed above

It never records message text, prompts, code, file paths or repo names: repos appear as `repo-1`, `repo-2`, and file paths are hashed only to count repeat reads. Reports are saved in `~/.claude/token-optimizer/reports/`. Cost figures are relative units (output ×5, cache write ×1.25, cache read ×0.1) and don't account for price differences between models.

## Uninstall

```bash
claude plugin uninstall token-optimizer@token-optimizer
```

Also remove any `TOKEN_OPT_*` keys you added to `env`. Hook state lives in `~/.claude/token-optimizer/` and is safe to delete.
