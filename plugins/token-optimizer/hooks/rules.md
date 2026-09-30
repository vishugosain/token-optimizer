[token-optimizer rules: keep token use low]

Plan first
- Feature work or a bug fix: investigate, present a plan, and wait for approval before editing files. Pure questions need no plan.
- Confirm scope before a large execution. A shaky direction should die in a short scoping exchange, not thousands of messages in.

Models and sub-agents
- Keep the main session for analysis, planning and hard reasoning. For mechanical or low-judgment steps (renames, find-and-replace, formatting, counting, summaries, docs), ask the user before handing them to `token-optimizer:rename-helper` or `token-optimizer:doc-writer` (both Haiku).
- When spawning any sub-agent, pass the cheapest model that can do the job (`haiku` for search and mechanical work, `sonnet` for normal coding) instead of inheriting the main model. Run at most 3 sub-agents in parallel.
- Model and effort are user settings: suggest a switch in one line, never claim to have changed them.

Don't re-derive
- Read the repo's existing docs, maps and CLAUDE.md before exploring, and trust them. Don't re-scan to rebuild documented facts; fix a stale doc instead. Build a new knowledge map only for a large or unfamiliar repo that will be worked in repeatedly, and ask first.

Keep context thin
- Put deliverables (guides, plans, write-ups) in files, not long chat replies.
- Grep first, then Read with offset/limit. Don't re-read an unchanged file that is still in context.
- Filter command output (grep, head, quiet flags) instead of dumping it.
- Run code review in a fresh session or a pre-commit gate, not in the session that made the change.

Session length
- One PR or phase per session; suggest a fresh session at phase boundaries.
- Before any compact, write key facts (paths, decisions, SHAs, numbers) to a file. Compaction is lossy.
- The context guard warns above {LIMIT} tokens. When it does, suggest /compact or a handoff.

Other sessions
- Never message or spawn other sessions on your own; ask the user which session, every time.
- Hand work off through a file (or memory) plus a task the user starts in a fresh session, not live session-to-session messages.
