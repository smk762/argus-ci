import json


def load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        pass
    return {}


def first_ok(items: list[str]) -> list[dict]:
    out = []
    for item in items:
        try:
            out.append(json.loads(item))
        except Exception:
            continue
    return out
