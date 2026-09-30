---
name: setup
description: Configure token-optimizer. Shows the current token-related settings and applies a Balanced or Max-savings preset (or custom values) to ~/.claude/settings.json after the user confirms. Use when the user says "token-optimizer setup", "configure token optimizer", "max savings", or wants to change the context limit, read limit, sub-agent model or Bash output cap.
---

# token-optimizer setup

1. **Read only these keys** from `~/.claude/settings.json` (use a short python one-liner; never print anything else from the file, since it may hold secrets): `model`, `effortLevel`, and `env.TOKEN_OPT_CONTEXT_LIMIT`, `env.TOKEN_OPT_READ_MAX_LINES`, `env.TOKEN_OPT_IDLE_MINUTES`, `env.CLAUDE_CODE_SUBAGENT_MODEL`, `env.BASH_MAX_OUTPUT_LENGTH`.

2. **Show a table** of those settings with their current value next to each preset (an unset value uses the default shown):

   | Setting | What it does | Default | Balanced | Max savings |
   |---|---|---|---|---|
   | `TOKEN_OPT_CONTEXT_LIMIT` | Context guard warns above this many tokens (`0` = off) | 250000 | 250000 | 150000 |
   | `TOKEN_OPT_READ_MAX_LINES` | First whole-file Read above this many lines is bounced once (`0` = off) | 1000 | 1000 | 600 |
   | `TOKEN_OPT_IDLE_MINUTES` | Warn when resuming a big session after this idle time (`0` = off) | 60 | 60 | 60 |
   | `CLAUDE_CODE_SUBAGENT_MODEL` | Model for sub-agents that don't name one (otherwise they inherit the main model) | inherit | sonnet | sonnet |
   | `BASH_MAX_OUTPUT_LENGTH` | Max characters of Bash output kept in context | Claude Code default | unchanged | 15000 |
   | `effortLevel` | Reasoning effort per turn | user's choice | unchanged | medium |

3. **Ask** with AskUserQuestion: Balanced, Max savings, or custom (the user names the values). Don't write anything before the answer.

4. **Apply** with a python script that loads the JSON, merges only the chosen keys (add `env` if missing; keep every other key untouched), and writes it back with 2-space indent. Then reload the file to confirm it parses, and print only the changed keys.

5. **Tell the user** the changes apply to new sessions, and show how to undo them (delete those keys from `env`).
