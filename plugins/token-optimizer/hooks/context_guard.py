import datetime as dt, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import env_int, load_state, save_state

TAIL_BYTES = (2 << 20, 16 << 20)


def last_context(path):
    """Context size and timestamp of the latest main-thread turn; (0, None) right after a compact."""
    size = os.path.getsize(path)
    for tail in TAIL_BYTES:
        with open(path, "rb") as fh:
            fh.seek(max(0, size - tail))
            lines = fh.read().splitlines()
        if size > tail:
            lines = lines[1:]
        for raw in reversed(lines):
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
                return 0, None
            m = e.get("message") if isinstance(e.get("message"), dict) else {}
            u = m.get("usage")
            if e.get("type") == "assistant" and u and not e.get("isSidechain") and m.get("model") != "<synthetic>":
                ctx = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                       + u.get("cache_creation_input_tokens", 0))
                ts = dt.datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                return ctx, ts
        if size <= tail:
            break
    return 0, None


def emit(user_msg, claude_msg):
    print(json.dumps({
        "systemMessage": user_msg,
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": claude_msg},
    }))


def main():
    data = json.load(sys.stdin)
    limit = env_int("TOKEN_OPT_CONTEXT_LIMIT", 250000)
    idle_min = env_int("TOKEN_OPT_IDLE_MINUTES", 60)
    path = data.get("transcript_path")
    if limit <= 0 or not path or not os.path.exists(path):
        return
    ctx, ts = last_context(path)
    key = f"ctx-{data.get('session_id', 'unknown')}"
    state = load_state(key)
    k = lambda n: f"{n / 1000:.0f}k"

    if ts and idle_min > 0 and ctx > limit / 2:
        idle = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 60
        if idle > idle_min and state.get("idle_warned") != ts.isoformat():
            state["idle_warned"] = ts.isoformat()
            save_state(key, state)
            hours = f"{idle / 60:.1f}h" if idle >= 60 else f"{idle:.0f}m"
            emit(f"token-optimizer: resuming a {k(ctx)}-token session after {hours} idle. The cache has expired, "
                 f"so this turn re-processes all of it. /compact or a fresh session keeps later turns cheap.",
                 f"[token-optimizer] This session resumed after {hours} idle with ~{k(ctx)} tokens of context; "
                 f"the prompt cache expired and every turn re-processes it. After answering, suggest in one line: "
                 f"save key facts to a file, then /compact or hand off to a fresh session.")
            return

    if ctx < limit:
        if state.get("warned_at"):
            state.pop("warned_at")
            save_state(key, state)
        return
    if state.get("warned_at") and ctx < state["warned_at"] + limit * 0.25:
        return
    state["warned_at"] = ctx
    save_state(key, state)
    emit(f"token-optimizer: context is {k(ctx)} tokens (limit {k(limit)}). "
         f"Every turn re-reads all of it; /compact or a fresh session is cheaper.",
         f"[token-optimizer] Context is ~{k(ctx)} tokens, above the configured limit of {k(limit)} "
         f"(TOKEN_OPT_CONTEXT_LIMIT). After answering the user's message, suggest in one line: "
         f"save key facts (paths, decisions, SHAs) to a file, then /compact or hand off to a fresh session.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
