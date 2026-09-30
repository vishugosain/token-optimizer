import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import env_int, load_state, save_state

BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf", ".ipynb"}


def count_lines(path, stop_after):
    n = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            n += chunk.count(b"\n")
            if n > stop_after:
                break
    return n


def main():
    data = json.load(sys.stdin)
    max_lines = env_int("TOKEN_OPT_READ_MAX_LINES", 1000)
    inp = data.get("tool_input") or {}
    path = inp.get("file_path")
    if max_lines <= 0 or inp.get("limit") or inp.get("offset") or not path or not os.path.isfile(path):
        return
    if os.path.splitext(path)[1].lower() in BINARY_EXT:
        return
    lines = count_lines(path, max_lines)
    if lines <= max_lines:
        return
    key = f"reads-{data.get('session_id', 'unknown')}"
    state = load_state(key)
    marker = f"{path}:{os.path.getmtime(path)}"
    if marker in state.get("bounced", []):
        return
    state.setdefault("bounced", []).append(marker)
    save_state(key, state)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"[token-optimizer] {os.path.basename(path)} has more than {max_lines} lines. Read only what you need: "
            f"Grep for the relevant part, then Read with offset/limit. If you really need the whole file, "
            f"repeat this exact Read and it will be allowed."),
    }}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
