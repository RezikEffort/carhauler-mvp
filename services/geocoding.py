# services/geocoding.py
import os
import re
import requests
from typing import Optional, Tuple, Dict, Any
from dotenv import load_dotenv

# Load env for local dev; in production rely on host envs
load_dotenv()

HERE_API_KEY = os.getenv("HERE_API_KEY")
GEOCODE_DEBUG = os.getenv("GEOCODE_DEBUG", "0") == "1"

MODULE_VERSION = "geocode-2025-08-31-qq-fallback-usa-us-nofilter"
if GEOCODE_DEBUG:
    print(f"[GEOCODE] MODULE {MODULE_VERSION} (key_loaded={'yes' if HERE_API_KEY else 'no'})")

# -----------------------------
# Patterns & helpers
# -----------------------------
_LATLNG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
# "Baltimore, MD" | "New York, NY" | optional trailing ", USA"
_CITY_STATE_RE = re.compile(r"^\s*([A-Za-z .'-]+)\s*,\s*([A-Za-z]{2})(?:\s*,\s*USA)?\s*$")

def _dbg(*args):
    if GEOCODE_DEBUG:
        print("[GEOCODE]", *args)

def _try_parse_latlng(text: str) -> Optional[Tuple[float, float]]:
    if not isinstance(text, str):
        return None
    m = _LATLNG_RE.match(text)
    if not m:
        return None
    try:
        lat = float(m.group(1)); lng = float(m.group(2))
        if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
            return (lat, lng)
    except Exception:
        pass
    return None

def _looks_like_ocean(lat: float, lng: float) -> bool:
    # reject obvious junk
    if abs(lat) < 1e-9 and abs(lng) < 1e-9:
        return True
    if abs(lat) < 0.2 and abs(lng) < 0.2:
        return True
    return False

def _is_reasonable_us_coordinate(lat: float, lng: float) -> bool:
    # loose CONUS bbox
    return 24.0 <= lat <= 50.0 and -125.0 <= lng <= -66.0

def _call_here(params: Dict[str, Any], timeout_sec: float) -> Optional[Tuple[float, float, str]]:
    """
    Low-level HERE call. Returns (lat,lng,label) or None.
    """
    if not HERE_API_KEY:
        _dbg("Missing HERE_API_KEY")
        return None
    url = "https://geocode.search.hereapi.com/v1/geocode"
    p = dict(params)
    p["apiKey"] = HERE_API_KEY
    # log exactly what we send (safe)
    _dbg("REQUEST", {"url": url, "params": p})

    try:
        resp = requests.get(url, params=p, timeout=timeout_sec)
        if 400 <= resp.status_code < 500:
            _dbg(f"HTTP {resp.status_code} BODY:", resp.text[:600])
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        _dbg("HTTP error:", e)
        return None

    items = data.get("items") or []
    if not items:
        _dbg("No items for", p)
        return None

    best = items[0]
    pos = best.get("position") or {}
    try:
        lat = float(pos["lat"]); lng = float(pos["lng"])
    except Exception:
        _dbg("Missing/invalid position in HERE response")
        return None
    label = best.get("title") or (best.get("address") or {}).get("label") or (p.get("q") or p.get("qq") or "")
    return (lat, lng, label)

# -----------------------------
# Public API
# -----------------------------
def geocode_address(query: str, *, timeout_sec: float = 10.0) -> Optional[Tuple[float, float]]:
    """
    Geocode a free-form address or 'lat,lng' to (lat,lng).
    Order of attempts:
      0) 'lat,lng' direct
      1) If looks like 'City, ST': use qq=city=City;state=ST;country=USA
      2) q=... with in=countryCode:USA
      3) q=... with in=countryCode:US
      4) q=... with no 'in'
    Returns None if all fail or result looks bogus.
    """
    # 0) Allow explicit lat,lng
    direct = _try_parse_latlng(query)
    if direct is not None:
        _dbg("Parsed lat,lng directly:", direct)
        return direct

    # 1) Structured City,ST -> qq
    m = _CITY_STATE_RE.match(query)
    if m:
        city = m.group(1).strip()
        st = m.group(2).strip().upper()
        # HERE prefers qq for structured address pieces
        params = {"qq": f"city={city};state={st};country=USA", "limit": 1}
        ans = _call_here(params, timeout_sec)
        if ans:
            lat, lng, _ = ans
            if not _looks_like_ocean(lat, lng) and _is_reasonable_us_coordinate(lat, lng):
                return (lat, lng)
            _dbg("qq City,ST result looked invalid, will try freeform")

    # 2) Freeform with USA (ISO-3)
    ans = _call_here({"q": query, "limit": 1, "in": "countryCode:USA"}, timeout_sec)
    if ans:
        lat, lng, _ = ans
        if not _looks_like_ocean(lat, lng) and _is_reasonable_us_coordinate(lat, lng):
            return (lat, lng)
        _dbg("USA-filter result looked invalid; will try US")

    # 3) Freeform with US (ISO-2) — some tenants prefer this
    ans = _call_here({"q": query, "limit": 1, "in": "countryCode:US"}, timeout_sec)
    if ans:
        lat, lng, _ = ans
        if not _looks_like_ocean(lat, lng) and _is_reasonable_us_coordinate(lat, lng):
            return (lat, lng)
        _dbg("US-filter result looked invalid; will drop filter")

    # 4) Freeform with no filter
    ans = _call_here({"q": query, "limit": 1}, timeout_sec)
    if ans:
        lat, lng, _ = ans
        if not _looks_like_ocean(lat, lng):
            return (lat, lng)

    _dbg("Geocode failed for:", query)
    return None


def geocode_with_label(query: str, *, timeout_sec: float = 10.0) -> Optional[Tuple[Tuple[float, float], str]]:
    """
    Same as geocode_address, but returns ((lat,lng), label) or None.
    """
    direct = _try_parse_latlng(query)
    if direct is not None:
        return direct, f"{direct[0]:.6f},{direct[1]:.6f}"

    # Try qq if City,ST
    m = _CITY_STATE_RE.match(query)
    if m:
        city = m.group(1).strip()
        st = m.group(2).strip().upper()
        ans = _call_here({"qq": f"city={city};state={st};country=USA", "limit": 1}, timeout_sec)
        if ans:
            lat, lng, label = ans
            if not _looks_like_ocean(lat, lng) and _is_reasonable_us_coordinate(lat, lng):
                return ( (lat, lng), label )

    # Freeform ladder: USA -> US -> none
    for in_filter in ("countryCode:USA", "countryCode:US", None):
        params = {"q": query, "limit": 1}
        if in_filter:
            params["in"] = in_filter
        ans = _call_here(params, timeout_sec)
        if ans:
            lat, lng, label = ans
            if not _looks_like_ocean(lat, lng) and (in_filter is None or _is_reasonable_us_coordinate(lat, lng)):
                return ( (lat, lng), label )

    return None
