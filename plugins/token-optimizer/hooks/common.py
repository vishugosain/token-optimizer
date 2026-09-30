import json, os, time

STATE_DIR = os.path.expanduser("~/.claude/token-optimizer/state")


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def load_state(key):
    try:
        with open(os.path.join(STATE_DIR, f"{key}.json")) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(key, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, f"{key}.json"), "w") as fh:
        json.dump(data, fh)


def prune_state(max_age_days=14):
    cutoff = time.time() - max_age_days * 86400
    try:
        for name in os.listdir(STATE_DIR):
            path = os.path.join(STATE_DIR, name)
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
    except OSError:
        pass
