"""Content-free Claude Code usage analysis for the token-optimizer plugin.

Reads ~/.claude/projects/**/*.jsonl and prints a Markdown report containing numbers only:
no message text, prompts, code, file paths, or repo names (repos become repo-1, repo-2...).

Usage: python3 session_stats.py            # last 14 days (auto-widens to 30 if quiet)
       python3 session_stats.py 21         # last N days
       python3 session_stats.py 2026-09-12 2026-09-21
       add --save to store the report in ~/.claude/token-optimizer/reports/ and compare with earlier ones
       add --json for raw JSON instead of the report
"""
import collections, datetime as dt, glob, hashlib, json, os, statistics, sys

ROOT = os.path.expanduser("~/.claude/projects")
EXPLORE = {"Read", "Grep", "Glob"}
EDITS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
BUILTIN_AGENTS = {"Explore", "Plan", "general-purpose", "claude", "claude-code-guide", "statusline-setup"}
BIG_RESULT_CHARS = 20_000
TRACKED_ENV = ("TOKEN_OPT_CONTEXT_LIMIT", "TOKEN_OPT_READ_MAX_LINES", "TOKEN_OPT_IDLE_MINUTES",
               "CLAUDE_CODE_SUBAGENT_MODEL", "BASH_MAX_OUTPUT_LENGTH", "MAX_MCP_OUTPUT_TOKENS")
REPORT_DIR = os.path.expanduser("~/.claude/token-optimizer/reports")


def family(model):
    return next((f for f in ("opus", "sonnet", "haiku", "fable") if f in (model or "")), "other")


def cost_units(inp, out, cw, cr):
    return inp + 5 * out + 1.25 * cw + 0.1 * cr


def result_chars(content):
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


def load(start, end):
    by_session, first_seen = collections.defaultdict(list), {}
    for path in glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True):
        with open(path, errors="ignore") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                    t = dt.datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                sid = e.get("sessionId") or path
                first_seen[sid] = min(first_seen.get(sid, t), t)
                if start <= t < end:
                    by_session[sid].append((t, e))
    return {sid: (events, first_seen[sid] >= start) for sid, events in by_session.items()}


def analyze(start, end):
    repo_labels, seen = {}, set()
    rows = []
    for events, started_in_window in load(start, end).values():
        events.sort(key=lambda x: x[0])
        s = collections.Counter()
        tools, tool_chars, tool_errors = collections.Counter(), collections.Counter(), collections.Counter()
        agent_types, agent_models, effort = collections.Counter(), collections.Counter(), collections.Counter()
        fam_cost_main, fam_cost_sub = collections.Counter(), collections.Counter()
        reads, reads_sub, id_to_tool, agents_per_request = collections.Counter(), collections.Counter(), {}, collections.Counter()
        main_reqs, repo, first_edit_seen, explore_before_edit = [], None, False, 0
        err_streak = max_err_streak = 0
        for t, e in events:
            cwd = e.get("cwd")
            if cwd and not repo:
                repo = repo_labels.setdefault(cwd, f"repo-{len(repo_labels) + 1}")
            side, typ = bool(e.get("isSidechain")), e.get("type")
            if typ == "system":
                sub = e.get("subtype")
                s["compactions"] += sub == "compact_boundary"
                s["api_errors"] += sub == "api_error"
                s["stop_hook_runs"] += sub == "stop_hook_summary"
            if typ in ("user", "assistant") and not side:
                s["msgs"] += 1
            if e.get("effort") and typ == "assistant":
                effort[e["effort"]] += 1
            m = e.get("message") if isinstance(e.get("message"), dict) else {}
            content = m.get("content")
            if typ == "user" and not side and not e.get("isMeta") and isinstance(content, str):
                s["prompts"] += 1
                s["prompt_chars_max"] = max(s["prompt_chars_max"], len(content))
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    name = b.get("name", "?")
                    name = "MCP" if name.startswith("mcp__") else name
                    id_to_tool[b.get("id")] = name
                    tools[name] += 1
                    inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                    if name == "Read":
                        (reads_sub if side else reads)[hashlib.sha1(str(inp.get("file_path")).encode()).hexdigest()] += 1
                        s["full_reads"] += not (inp.get("limit") or inp.get("offset"))
                    if name == "Agent":
                        st = inp.get("subagent_type") or "general-purpose"
                        agent_types[st if st in BUILTIN_AGENTS else "custom"] += 1
                        agent_models[inp.get("model") or "inherit"] += 1
                        s["agents_background"] += bool(inp.get("run_in_background"))
                        agents_per_request[e.get("requestId")] += 1
                    if name in ("EnterPlanMode", "ExitPlanMode"):
                        s[name] += 1
                    if not side:
                        if name in EDITS:
                            first_edit_seen = True
                        elif name in EXPLORE and not first_edit_seen:
                            explore_before_edit += 1
                elif b.get("type") == "tool_result":
                    name = id_to_tool.get(b.get("tool_use_id"), "?")
                    n = result_chars(b.get("content"))
                    tool_chars[name] += n
                    s["big_results"] += n > BIG_RESULT_CHARS
                    if b.get("is_error"):
                        tool_errors[name] += 1
                        if not side:
                            err_streak += 1
                            max_err_streak = max(max_err_streak, err_streak)
                    elif not side:
                        err_streak = 0
            u, rid, model = m.get("usage"), e.get("requestId") or m.get("id"), m.get("model", "?")
            if typ != "assistant" or not u or rid in seen or model == "<synthetic>":
                continue
            seen.add(rid)
            inp, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
            cw, cr = u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0)
            cu = cost_units(inp, out, cw, cr)
            s["tokens"] += inp + out + cw + cr
            s["output"] += out
            s["cost"] += cu
            if side:
                s["sub_requests"] += 1
                s["sub_cost"] += cu
                fam_cost_sub[family(model)] += cu
            else:
                fam_cost_main[family(model)] += cu
                main_reqs.append((t, inp + cw + cr, cw, cu, model))
        if not s["cost"]:
            continue
        ctx = [r[1] for r in main_reqs]
        idle_5m = idle_1h = 0
        idle_rewrite = 0.0
        switches = sum(1 for a, b in zip(main_reqs, main_reqs[1:]) if a[4] != b[4])
        for a, b in zip(main_reqs, main_reqs[1:]):
            gap = (b[0] - a[0]).total_seconds()
            if gap > 300:
                idle_5m += 1
                idle_rewrite += 1.25 * b[2]
            idle_1h += gap > 3600
        rows.append({
            "date": events[0][0].date().isoformat(),
            "repo": repo or "?",
            "hours": round((events[-1][0] - events[0][0]).total_seconds() / 3600, 1),
            "msgs": s["msgs"],
            "prompts_approx": s["prompts"],
            "requests_main": len(main_reqs),
            "requests_sub": s["sub_requests"],
            "cost_units_m": round(s["cost"] / 1e6, 2),
            "tokens_m": round(s["tokens"] / 1e6, 1),
            "output_k": round(s["output"] / 1e3),
            "started_in_window": started_in_window,
            "startup_ctx_k": round(ctx[0] / 1e3) if ctx and started_in_window else None,
            "peak_ctx_k": round(max(ctx) / 1e3) if ctx else 0,
            "cost_pct_ctx_over_150k": round(100 * sum(r[3] for r in main_reqs if r[1] > 150_000) / s["cost"]),
            "cost_pct_ctx_over_500k": round(100 * sum(r[3] for r in main_reqs if r[1] > 500_000) / s["cost"]),
            "subagent_cost_pct": round(100 * s["sub_cost"] / s["cost"]),
            "cost_by_family_main": {k: round(v / 1e6, 2) for k, v in fam_cost_main.items()},
            "cost_by_family_sub": {k: round(v / 1e6, 2) for k, v in fam_cost_sub.items()},
            "model_switches": switches,
            "effort": dict(effort),
            "compactions": s["compactions"],
            "idle_gaps_over_5m": idle_5m,
            "idle_gaps_over_1h": idle_1h,
            "idle_cache_rewrite_units_m": round(idle_rewrite / 1e6, 2),
            "tool_calls": dict(tools),
            "tool_result_chars_k": {k: round(v / 1e3) for k, v in tool_chars.items() if v},
            "big_tool_results": s["big_results"],
            "tool_errors": dict(tool_errors),
            "max_error_streak": max_err_streak,
            "file_rereads": sum(n - 1 for n in reads.values() if n > 1),
            "file_rereads_sub": sum(n - 1 for n in reads_sub.values() if n > 1),
            "distinct_files_read": len(set(reads) | set(reads_sub)),
            "full_file_reads": s["full_reads"],
            "explore_calls_before_first_edit": explore_before_edit if first_edit_seen else None,
            "agent_calls": sum(agent_types.values()),
            "agent_types": dict(agent_types),
            "agent_model_overrides": dict(agent_models),
            "agents_background": s["agents_background"],
            "max_parallel_agents": max(agents_per_request.values(), default=0),
            "plan_mode_enter": s["EnterPlanMode"],
            "plan_mode_exit": s["ExitPlanMode"],
            "api_errors": s["api_errors"],
            "stop_hook_runs": s["stop_hook_runs"],
            "prompt_chars_max": s["prompt_chars_max"],
        })
    rows.sort(key=lambda r: -r["cost_units_m"])
    return rows, len(repo_labels)


def config_snapshot():
    home = os.path.expanduser("~/.claude")
    snap = {}
    try:
        cfg = json.load(open(os.path.join(home, "settings.json")))
        env, plugins = cfg.get("env") or {}, cfg.get("enabledPlugins") or {}
        snap.update(model=cfg.get("model"), effortLevel=cfg.get("effortLevel"),
                    defaultMode=(cfg.get("permissions") or {}).get("defaultMode"),
                    enabled_plugins=sum(bool(v) for v in plugins.values()),
                    token_optimizer_plugin=any(v and k.startswith("token-optimizer@") for k, v in plugins.items()),
                    hooks_configured=sorted((cfg.get("hooks") or {}).keys()),
                    env={k: env[k] for k in TRACKED_ENV if k in env})
    except (OSError, ValueError):
        snap["settings"] = "unreadable"
    md = os.path.join(home, "CLAUDE.md")
    snap["global_claude_md_bytes"] = os.path.getsize(md) if os.path.exists(md) else 0
    snap["token_rules_installed"] = snap["global_claude_md_bytes"] > 0 and "token discipline" in open(md, errors="ignore").read()
    snap["agents"] = {a: os.path.exists(os.path.join(home, "agents", a + ".md")) for a in ("rename-helper", "doc-writer")}
    return snap


def summarize(rows, repos, start, end):
    tot = sum(r["cost_units_m"] for r in rows) or 1e-9
    fam = collections.Counter()
    for r in rows:
        for k, v in r["cost_by_family_main"].items():
            fam[f"{k}-main"] += v
        for k, v in r["cost_by_family_sub"].items():
            fam[f"{k}-sub"] += v
    tools, chars, errors, effort, atypes, amodels = (collections.Counter() for _ in range(6))
    for r in rows:
        tools.update(r["tool_calls"]); chars.update(r["tool_result_chars_k"]); errors.update(r["tool_errors"])
        effort.update(r["effort"]); atypes.update(r["agent_types"]); amodels.update(r["agent_model_overrides"])
    w = lambda key: round(sum(r[key] * r["cost_units_m"] for r in rows) / tot)
    med = lambda key: statistics.median([r[key] for r in rows if r[key] is not None] or [0])
    eff_total = sum(effort.values()) or 1
    return {
        "window": f"{start.date()} to {(end - dt.timedelta(seconds=1)).date()}",
        "window_days": round((end - start).total_seconds() / 86400, 1),
        "sessions": len(rows), "repos": repos,
        "cost_units_m_total": round(tot, 1),
        "output_tokens_m_total": round(sum(r["output_k"] for r in rows) / 1e3, 2),
        "cost_share_pct_by_model": {k: round(100 * v / tot) for k, v in fam.most_common()},
        "effort_share_pct_of_turns": {k: round(100 * v / eff_total) for k, v in effort.most_common()},
        "context": {
            "min_startup_ctx_k": min((r["startup_ctx_k"] for r in rows if r["startup_ctx_k"] is not None), default=None),
            "median_startup_ctx_k": med("startup_ctx_k"),
            "sessions_started_over_150k": sum((r["startup_ctx_k"] or 0) > 150 for r in rows),
            "median_peak_ctx_k": med("peak_ctx_k"),
            "sessions_peak_over_150k": sum(r["peak_ctx_k"] > 150 for r in rows),
            "sessions_peak_over_500k": sum(r["peak_ctx_k"] > 500 for r in rows),
            "cost_pct_at_ctx_over_150k": w("cost_pct_ctx_over_150k"),
            "cost_pct_at_ctx_over_500k": w("cost_pct_ctx_over_500k"),
            "sessions_with_compaction": sum(r["compactions"] > 0 for r in rows),
        },
        "session_length": {
            "median_msgs": med("msgs"),
            "cost_weighted_avg_msgs": w("msgs"),
            "over_1000_msgs": sum(r["msgs"] > 1000 for r in rows),
            "over_2500_msgs": sum(r["msgs"] > 2500 for r in rows),
            "median_requests_per_prompt": round(statistics.median([r["requests_main"] / max(r["prompts_approx"], 1) for r in rows]), 1),
            "max_prompt_chars": max(r["prompt_chars_max"] for r in rows),
        },
        "idle": {
            "gaps_over_5m": sum(r["idle_gaps_over_5m"] for r in rows),
            "gaps_over_1h": sum(r["idle_gaps_over_1h"] for r in rows),
            "cache_rewrite_after_idle_pct_of_cost": round(100 * sum(r["idle_cache_rewrite_units_m"] for r in rows) / tot),
        },
        "tools": {
            "calls": dict(tools.most_common(12)),
            "result_chars_k": dict(chars.most_common(8)),
            "big_results_over_20k_chars": sum(r["big_tool_results"] for r in rows),
            "errors": dict(errors.most_common(6)),
            "max_error_streak": max(r["max_error_streak"] for r in rows),
            "file_rereads": sum(r["file_rereads"] for r in rows),
            "file_rereads_sub": sum(r["file_rereads_sub"] for r in rows),
            "distinct_files_read": sum(r["distinct_files_read"] for r in rows),
            "full_file_reads_pct": round(100 * sum(r["full_file_reads"] for r in rows) / max(tools["Read"], 1)),
            "median_explore_before_first_edit": med("explore_calls_before_first_edit"),
        },
        "delegation": {
            "agent_calls": sum(r["agent_calls"] for r in rows),
            "agent_types": dict(atypes),
            "agent_model_overrides": dict(amodels),
            "max_parallel_agents": max(r["max_parallel_agents"] for r in rows),
            "subagent_cost_pct": w("subagent_cost_pct"),
            "inherit_pct_of_agent_calls": round(100 * amodels.get("inherit", 0) / max(sum(amodels.values()), 1)),
            "subagent_cost_share_pct_by_model": {
                k[:-4]: round(100 * v / max(sum(x for kk, x in fam.items() if kk.endswith("-sub")), 1e-9))
                for k, v in fam.most_common() if k.endswith("-sub") and v},
        },
        "plan_mode": {"sessions_using": sum(r["plan_mode_exit"] > 0 for r in rows),
                      "exit_plan_calls": sum(r["plan_mode_exit"] for r in rows)},
        "api_errors": sum(r["api_errors"] for r in rows),
        "stop_hook_runs": sum(r["stop_hook_runs"] for r in rows),
    }


def findings(sm):
    f, c, t, d = [], sm["context"], sm["tools"], sm["delegation"]
    opus = sum(v for k, v in sm["cost_share_pct_by_model"].items() if k.startswith("opus"))
    cheap = sum(v for k, v in sm["cost_share_pct_by_model"].items() if k.startswith(("haiku", "sonnet")))
    f.append(f"Opus carries {opus}% of cost; Sonnet+Haiku {cheap}%.")
    f.append(f"{c['cost_pct_at_ctx_over_150k']}% of cost was spent on turns whose context exceeded 150k tokens "
             f"({c['cost_pct_at_ctx_over_500k']}% above 500k); {c['sessions_with_compaction']} of {sm['sessions']} sessions ever compacted.")
    if c["min_startup_ctx_k"] is not None:
        f.append(f"Fixed context per new session: ~{c['min_startup_ctx_k']}k tokens minimum, {c['median_startup_ctx_k']:.0f}k median "
                 f"(system prompt, tools, MCP, CLAUDE.md); {c['sessions_started_over_150k']} sessions started above 150k "
                 f"(resumed, forked or continued from a big session).")
    if t["result_chars_k"]:
        top, n = next(iter(t["result_chars_k"].items()))
        f.append(f"Largest context feeder: {top} results ({n / 1e3:.1f}M chars); {t['big_results_over_20k_chars']} single results exceeded 20k chars.")
    f.append(f"{t['file_rereads']} repeat reads of an already-read file in the main thread ({t['file_rereads_sub']} more inside "
             f"sub-agents); {t['full_file_reads_pct']}% of Reads loaded the whole file.")
    if d["agent_calls"]:
        mix = ", ".join(f"{k} {v}%" for k, v in d["subagent_cost_share_pct_by_model"].items()) or "n/a"
        f.append(f"{d['agent_calls']} sub-agent calls (max {d['max_parallel_agents']} in one turn) cost {d['subagent_cost_pct']}% "
                 f"of the total; {d['inherit_pct_of_agent_calls']}% set no model and inherited the default. "
                 f"Sub-agent cost by model: {mix}.")
    x = sm["effort_share_pct_of_turns"].get("xhigh", 0)
    if x:
        f.append(f"{x}% of turns ran at xhigh effort.")
    if sm["idle"]["cache_rewrite_after_idle_pct_of_cost"]:
        f.append(f"{sm['idle']['cache_rewrite_after_idle_pct_of_cost']}% of cost was cache rebuilt after idle gaps (>5 min) in long-lived sessions.")
    if t["max_error_streak"] >= 5:
        f.append(f"Longest run of consecutive tool errors: {t['max_error_streak']} (possible retry loop).")
    return f


COMPARE = [
    ("Cost units per day (M)", lambda s: s["cost_units_m_total"] / max(s["window_days"], 1)),
    ("Messages per session (cost-weighted avg)", lambda s: s["session_length"]["cost_weighted_avg_msgs"]),
    ("Cost at context >150k (%)", lambda s: s["context"]["cost_pct_at_ctx_over_150k"]),
    ("Opus share of cost (%)", lambda s: sum(v for k, v in s["cost_share_pct_by_model"].items() if k.startswith("opus"))),
    ("Sub-agent share of cost (%)", lambda s: s["delegation"]["subagent_cost_pct"]),
    ("Whole-file Reads (%)", lambda s: s["tools"]["full_file_reads_pct"]),
    ("Tool results >20k chars per session", lambda s: s["tools"]["big_results_over_20k_chars"] / max(s["sessions"], 1)),
]


def saved_reports():
    try:
        names = sorted(n for n in os.listdir(REPORT_DIR) if n.startswith("token-usage-report-") and n.endswith(".md"))
    except OSError:
        return []
    out = []
    for n in names:
        txt = open(os.path.join(REPORT_DIR, n)).read()
        start = txt.find("```json\n")
        try:
            out.append((n[19:-3], json.loads(txt[start + 8:txt.index("\n```", start + 8)])["summary"]))
        except (ValueError, KeyError):
            continue
    return out


def comparison(current, today):
    prior = [(d, s) for d, s in saved_reports() if d != today]
    if not prior:
        return "No earlier report yet: this one is your baseline. Run the audit again in a week or two to see the change."
    cols = [prior[0]] + ([prior[-1]] if len(prior) > 1 else [])
    head = "| Metric | " + " | ".join(f"{'Baseline' if i == 0 else 'Previous'} ({d})" for i, (d, _) in enumerate(cols)) + " | Now | vs baseline |"
    lines = [head, "|" + "---|" * (len(cols) + 3)]
    for label, get in COMPARE:
        try:
            base, now = get(cols[0][1]), get(current)
            olds = [get(s) for _, s in cols]
        except (KeyError, TypeError):
            continue
        verdict = "same" if abs(now - base) <= max(abs(base) * 0.05, 0.5) else ("better" if now < base else "worse")
        lines.append(f"| {label} | " + " | ".join(f"{v:.1f}" for v in olds) + f" | {now:.1f} | {verdict} |")
    return "\n".join(lines)


def main(argv):
    as_json, save = "--json" in argv, "--save" in argv
    args = [a for a in argv if not a.startswith("--")]
    now = dt.datetime.now(dt.timezone.utc)
    if len(args) >= 2:
        start, end = (dt.datetime.fromisoformat(a + "T00:00:00+00:00") for a in args[:2])
    else:
        end, start = now, now - dt.timedelta(days=int(args[0]) if args else 14)
    rows, repos = analyze(start, end)
    if not args and len(rows) < 5:
        start = now - dt.timedelta(days=30)
        rows, repos = analyze(start, end)
    if not rows:
        print("No sessions found in the window.")
        return
    sm = summarize(rows, repos, start, end)
    data = {"generated": now.date().isoformat(), "config": config_snapshot(), "summary": sm, "sessions_top15_by_cost": rows[:15]}
    if as_json:
        print(json.dumps(data, indent=1))
        return
    today = now.date().isoformat()
    top = (f"# Token usage report — {sm['window']}\n\n"
           "Generated by the token-optimizer analysis script. Numbers only: no message text, code, paths or repo names.\n\n"
           "## Findings\n" + "\n".join(f"- {x}" for x in findings(sm)) + "\n")
    compare = "\n## Change over time\n" + comparison(sm, today) + "\n" if save else ""
    body = "\n## Data\n```json\n" + json.dumps(data, indent=1) + "\n```\n"
    if not save:
        print(top + body)
        return
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f"token-usage-report-{today}.md")
    with open(path, "w") as fh:
        fh.write(top + compare + body)
    print(top + compare + f"\nFull report (numbers only, safe to share): {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
