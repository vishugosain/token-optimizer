import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import env_int, prune_state


def main():
    limit = env_int("TOKEN_OPT_CONTEXT_LIMIT", 250000)
    shown = f"{limit // 1000}k" if limit > 0 else "(guard off)"
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.md")) as fh:
        print(fh.read().replace("{LIMIT}", shown))
    prune_state()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
