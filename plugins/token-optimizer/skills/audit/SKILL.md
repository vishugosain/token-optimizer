---
name: audit
description: Measure where Claude Code tokens go. Runs a content-free analysis of local session logs, saves a shareable report, and compares it with earlier reports. Use when the user says "token audit", "check my usage", "where did my tokens go", "usage report", or wants a before/after on their token habits.
---

# Token audit

1. Run the script in this skill's base directory:
   `python3 "<base directory>/session_stats.py" --save`
   It covers the last 14 days (widening to 30 if there are fewer than 5 sessions). If the user asks for a window, add a number of days (`21`) or two dates (`2026-09-01 2026-09-15`) before `--save`.
2. The script prints the Findings, a comparison with earlier reports, and the report path. Work only from that output: don't open the report file or any transcript.
3. Reply with:
   - the findings in plain words
   - what got better or worse since the baseline, if there is one
   - the 1–3 changes that would save the most, tied to the findings (e.g. "sub-agents inherit Opus → run `/token-optimizer:setup` and set a Sonnet sub-agent default"; "74% of cost above 150k context → compact earlier or lower `TOKEN_OPT_CONTEXT_LIMIT`")
   - the report path, noting that it contains numbers only and is safe to share
