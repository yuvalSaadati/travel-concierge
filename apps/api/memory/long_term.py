import json, os
from typing import Dict, Any

MEM_PATH = os.path.join(os.path.dirname(__file__), "user_prefs.json")

def _read() -> Dict[str, Any]:
    if not os.path.exists(MEM_PATH):
        return {}
    try:
        with open(MEM_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _write(data: Dict[str, Any]):
    os.makedirs(os.path.dirname(MEM_PATH), exist_ok=True)
    with open(MEM_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_prefs(user: str) -> Dict[str, Any]:
    return _read().get(user, {})

def upsert_prefs(user: str, prefs: Dict[str, Any]):
    data = _read()
    cur = data.get(user, {})
    cur.update(prefs)
    data[user] = cur
    _write(data)
