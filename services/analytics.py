# services/analytics.py
import os, json, time, hashlib, threading
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

_LOCK = threading.Lock()

ANALYTICS_ENABLE = os.getenv("ANALYTICS_ENABLE", "0") == "1"
ANALYTICS_PATH = os.getenv("ANALYTICS_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "events.jsonl"))

def _ensure_dir(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _hash_client(client_hint: Optional[str]) -> str:
    """
    Create a stable, anonymous id from any client-provided hint (optional).
    If none provided, generate a random-ish id per process boot.
    """
    if not client_hint:
        client_hint = f"boot:{time.time_ns()}"
    return hashlib.sha256(client_hint.encode("utf-8")).hexdigest()[:16]

def round_coord(latlng: Optional[Tuple[float,float]], places: int = 2) -> Optional[Tuple[float,float]]:
    if not latlng:
        return None
    (lat, lng) = latlng
    return (round(float(lat), places), round(float(lng), places))

def log_event(event: Dict[str, Any]) -> None:
    """
    Append a single JSON event to analytics file if enabled.
    """
    if not ANALYTICS_ENABLE:
        return
    _ensure_dir(ANALYTICS_PATH)
    event = dict(event)
    event["ts_iso"] = datetime.utcnow().isoformat() + "Z"
    line = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    with _LOCK:
        with open(ANALYTICS_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
