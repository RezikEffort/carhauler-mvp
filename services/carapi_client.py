# services/carapi_client.py
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv, find_dotenv

# Load .env (override OS vars so you don't get stale values)
ENV_PATH = find_dotenv(usecwd=True)
load_dotenv(ENV_PATH, override=True)

def _clean_base(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip().rstrip("/")
    # If someone set CARAPI_BASE=https://carapi.app/api, drop the trailing /api
    if raw.lower().endswith("/api"):
        raw = raw[:-4]
    return raw

CARAPI_BASE   = _clean_base(os.getenv("CARAPI_BASE")) or "https://carapi.app"
CARAPI_TOKEN  = (os.getenv("CARAPI_TOKEN")  or "").strip()
CARAPI_SECRET = (os.getenv("CARAPI_SECRET") or "").strip()

BASE_HEADERS   = {"Accept": "application/json"}
HEADERS_BEARER = ({**BASE_HEADERS, "Authorization": f"Bearer {CARAPI_TOKEN}"} if CARAPI_TOKEN else BASE_HEADERS)
HEADERS_SECRET = ({**BASE_HEADERS, "X-Api-Secret": CARAPI_SECRET} if CARAPI_SECRET else BASE_HEADERS)
# Preference: use secret if present (works for many CarAPI endpoints), else bearer, else no-auth
PREFERRED_CHAIN: List[Dict[str, str]] = []
if CARAPI_SECRET:
    PREFERRED_CHAIN.append(HEADERS_SECRET)
if CARAPI_TOKEN:
    PREFERRED_CHAIN.append(HEADERS_BEARER)
PREFERRED_CHAIN.append(BASE_HEADERS)

TIMEOUT = aiohttp.ClientTimeout(total=15)

# ---------------------------
# HTTP + payload helpers
# ---------------------------
async def _fetch_json_with_headers(url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Tuple[int, str, Optional[Dict[str, Any]]]:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            text = await resp.text()
            if resp.status >= 400:
                return resp.status, text, None
            try:
                return resp.status, text, await resp.json()
            except Exception as e:
                raise RuntimeError(f"CarAPI JSON parse error @ {url}: {e} :: {text[:200]}")

async def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Try preferred auth, then fall back to others (including no-auth) if we get an auth error.
    """
    last_err = None
    for hdrs in PREFERRED_CHAIN:
        code, text, data = await _fetch_json_with_headers(url, params, hdrs)
        if data is not None:
            return data
        # retry on common auth failures or generic 400/401/403
        if code in (400, 401, 403) and ("InvalidAuthenticationHeaderException" in text or "invalid" in text.lower()):
            last_err = RuntimeError(f"CarAPI auth failed {code} @ {url} :: {text[:200]}")
            continue
        # other 4xx/5xx: keep last and break
        last_err = RuntimeError(f"CarAPI GET {code} @ {url} :: {text[:200]}")
        break
    raise last_err or RuntimeError(f"CarAPI request failed @ {url}")

def _list_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "bodies", "items", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    return []

# ---------------------------
# Unit normalization + parsing
# ---------------------------
_NUM_LIKE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*$")

def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # strip common decorations like commas or units in the same string
        s = s.replace(",", "")
        # quick path: pure number string
        if _NUM_LIKE.match(s):
            try:
                return float(s)
            except Exception:
                return None
        # handle things like 5'9", 5 ft 9 in, etc.
        m = re.match(r"(?i)^\s*(\d+(?:\.\d+)?)\s*(?:ft|')\s*(\d+(?:\.\d+)?)?\s*(?:in|\"|)?\s*$", s)
        if m:
            ft = float(m.group(1))
            inches = float(m.group(2) or 0.0)
            return ft + inches / 12.0
    return None

def _to_feet(v: Optional[float], unit: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    u = (unit or "").lower()
    try:
        x = float(v)
    except Exception:
        return None

    if u in ("ft", "feet"):
        return x
    if u in ("in", "inch", "inches"):
        return x / 12.0
    if u in ("mm", "millimeter", "millimetre"):
        return x / 304.8
    if u in ("cm", "centimeter", "centimetre"):
        return x / 30.48
    if u in ("m", "meter", "metre", "meters", "metres"):
        return x * 3.28084

    # Guess by magnitude if unit omitted
    if x > 1000:   # likely mm
        return x / 304.8
    if x > 100:    # likely inches
        return x / 12.0
    if x < 10:     # likely feet already
        return x
    return x / 12.0

def _to_lbs(v: Optional[float], unit: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    u = (unit or "").lower()
    try:
        x = float(v)
    except Exception:
        return None

    if u in ("lb", "lbs", "pound", "pounds", ""):
        return x
    if u in ("kg", "kilogram", "kilograms"):
        return x * 2.2046226218

    # Guess: over a thousand -> probably pounds already
    if x > 1000:
        return x
    # else treat as kg
    return x * 2.2046226218

# ---------------------------
# Field extraction (accept strings or numbers)
# ---------------------------
def _get_from(obj: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for k in keys:
        if k in obj:
            val = _num(obj.get(k))
            if val is not None:
                return val
    return None

def _extract_height_ft(rec: Dict[str, Any]) -> Optional[float]:
    dims = rec.get("dimensions") or {}
    if isinstance(dims, dict):
        v = _get_from(dims, ["height", "height_in", "height_mm", "height_cm", "height_ft"])
        if v is not None:
            # try to infer unit from key
            for k in ("height_ft",):
                if k in dims:
                    return _to_feet(v, "ft")
            for k in ("height_in",):
                if k in dims:
                    return _to_feet(v, "in")
            for k in ("height_mm",):
                if k in dims:
                    return _to_feet(v, "mm")
            for k in ("height_cm",):
                if k in dims:
                    return _to_feet(v, "cm")
            return _to_feet(v, dims.get("height_unit") or dims.get("unit"))
    # common top-level fields in CarAPI bodies (often inches)
    v = _get_from(rec, ["height_in", "height_inches", "height_mm", "height_cm", "height"])
    if v is not None:
        # infer by key name
        if "mm" in [k for k in rec.keys() if "height_mm" in k]:
            return _to_feet(v, "mm")
        if "cm" in [k for k in rec.keys() if "height_cm" in k]:
            return _to_feet(v, "cm")
        if "height_in" in rec or "height_inches" in rec:
            return _to_feet(v, "in")
        return _to_feet(v, None)
    return None

def _extract_length_ft(rec: Dict[str, Any]) -> Optional[float]:
    dims = rec.get("dimensions") or {}
    if isinstance(dims, dict):
        v = _get_from(dims, ["length", "length_in", "length_mm", "length_cm", "length_ft"])
        if v is not None:
            for k in ("length_ft",):
                if k in dims:
                    return _to_feet(v, "ft")
            for k in ("length_in",):
                if k in dims:
                    return _to_feet(v, "in")
            for k in ("length_mm",):
                if k in dims:
                    return _to_feet(v, "mm")
            for k in ("length_cm",):
                if k in dims:
                    return _to_feet(v, "cm")
            return _to_feet(v, dims.get("length_unit") or dims.get("unit"))
    v = _get_from(rec, ["length_in", "length_inches", "length_mm", "length_cm", "length"])
    if v is not None:
        if "mm" in [k for k in rec.keys() if "length_mm" in k]:
            return _to_feet(v, "mm")
        if "cm" in [k for k in rec.keys() if "length_cm" in k]:
            return _to_feet(v, "cm")
        if "length_in" in rec or "length_inches" in rec:
            return _to_feet(v, "in")
        return _to_feet(v, None)
    return None

def _extract_curb_weight_lbs(rec: Dict[str, Any]) -> Optional[float]:
    weights = rec.get("weights") or rec.get("specs") or {}
    if isinstance(weights, dict):
        v = _get_from(weights, ["curb_weight_lbs", "curb_weight_lb", "weight_lbs", "gross_weight_lbs"])
        if v is not None:
            return _to_lbs(v, "lbs")
        v = _get_from(weights, ["curb_weight_kg", "weight_kg", "gross_weight_kg"])
        if v is not None:
            return _to_lbs(v, "kg")
        v = _get_from(weights, ["curb_weight", "weight", "gross_weight"])
        if v is not None:
            # crude inference: >1000 looks like lbs
            return _to_lbs(v, "lbs" if float(v) > 1000 else "kg")

    v = _get_from(rec, ["curb_weight_lbs", "weight_lbs", "curb_weight_lb"])
    if v is not None:
        return _to_lbs(v, "lbs")
    v = _get_from(rec, ["curb_weight_kg", "weight_kg"])
    if v is not None:
        return _to_lbs(v, "kg")
    v = _get_from(rec, ["curb_weight", "weight", "gross_weight"])
    if v is not None:
        return _to_lbs(v, "lbs" if float(v) > 1000 else "kg")
    return None

# ---------------------------
# Aggregation helpers
# ---------------------------
def _median(nums: List[float]) -> Optional[float]:
    arr = [float(x) for x in nums if isinstance(x, (int, float)) or _num(x) is not None]
    arr = [float(x) if isinstance(x, (int, float)) else float(_num(x)) for x in arr]
    if not arr:
        return None
    arr.sort()
    n = len(arr)
    mid = n // 2
    if n % 2 == 1:
        return float(arr[mid])
    return float((arr[mid - 1] + arr[mid]) / 2.0)

def _aggregate_specs(items: List[Dict[str, Any]], strategy: str = "median") -> Dict[str, Optional[float]]:
    heights = [h for h in (_extract_height_ft(i) for i in items) if h is not None]
    lengths = [l for l in (_extract_length_ft(i) for i in items) if l is not None]
    weights = [w for w in (_extract_curb_weight_lbs(i) for i in items) if w is not None]

    if strategy == "max":
        height_ft = max(heights) if heights else None
        length_ft = max(lengths) if lengths else None
        weight_lbs = max(weights) if weights else None
    else:  # median default
        height_ft = _median(heights)
        length_ft = _median(lengths)
        weight_lbs = _median(weights)

    return {"height_ft": height_ft, "length_ft": length_ft, "weight_lbs": weight_lbs}

def _normalize_trim_name(rec: Dict[str, Any]) -> Optional[str]:
    for k in ("trim", "trim_name", "series", "grade", "name"):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

# ---------------------------
# Public: lookup specs via CarAPI bodies v2
# ---------------------------
async def list_trims(year: int, make: str, model: str) -> List[str]:
    url = f"{CARAPI_BASE}/api/bodies/v2"
    params = {"direction": "asc", "year": str(year), "make": make, "model": model, "limit": "200"}
    payload = await _get_json(url, params)
    items = _list_from_payload(payload)
    trims: List[str] = []
    seen = set()
    for rec in items:
        t = _normalize_trim_name(rec)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            trims.append(t)
    return sorted(trims, key=lambda s: (s.lower()))

async def lookup_body_specs(
    year: int,
    make: str,
    model: str,
    trim: Optional[str] = None,
    strategy: str = "first",   # default to 'first' per your requirement
) -> Optional[Dict[str, Any]]:
    """
    Call CarAPI bodies v2 and return normalized specs.
    - If trim is provided, pick the best matching record (most complete specs).
    - Otherwise, strategy:
        * 'first': return the first record that has any numeric (height/weight/length).
        * 'median' (or 'max'): aggregate across all records.
    """
    url = f"{CARAPI_BASE}/api/bodies/v2"
    params = {"direction": "asc", "year": str(year), "make": make, "model": model, "limit": "200"}
    payload = await _get_json(url, params)
    items = _list_from_payload(payload)
    if not items:
        return None

    selected_items = items
    used_trim = None

    if trim:
        t_lower = trim.strip().lower()
        exact = [r for r in items if (_normalize_trim_name(r) or "").lower() == t_lower]
        if not exact:
            exact = [r for r in items if t_lower in (_normalize_trim_name(r) or "").lower()]
        if exact:
            def score(r: Dict[str, Any]) -> int:
                s = 0
                if _extract_height_ft(r) is not None: s += 2
                if _extract_curb_weight_lbs(r) is not None: s += 2
                if _extract_length_ft(r) is not None: s += 1
                return s
            exact.sort(key=score, reverse=True)
            selected_items = [exact[0]]
            used_trim = _normalize_trim_name(exact[0])

    # Strategy: first-with-data (preferred)
    if not trim and strategy and strategy.lower() == "first":
        for rec in selected_items:
            data = {
                "height_ft": _extract_height_ft(rec),
                "length_ft": _extract_length_ft(rec),
                "weight_lbs": _extract_curb_weight_lbs(rec),
                "source": "CarAPI)",
                "notes": "bodies/v2: first record with numeric fields",
            }
            if any(v is not None for v in (data["height_ft"], data["length_ft"], data["weight_lbs"])):
                return data
        # fall through to aggregate if we couldn't parse anything

    # If we have a single selected record (exact trim), use it
    if len(selected_items) == 1:
        rec = selected_items[0]
        data = {
            "height_ft": _extract_height_ft(rec),
            "length_ft": _extract_length_ft(rec),
            "weight_lbs": _extract_curb_weight_lbs(rec),
            "source": "CarAPI bodies/v2 (trim exact)" if used_trim else "CarAPI bodies/v2 (first)",
            "notes": f"bodies/v2: trim={used_trim}" if used_trim else "bodies/v2: first record",
        }
        if any(v is not None for v in (data["height_ft"], data["length_ft"], data["weight_lbs"])):
            return data

    # Aggregate across selected_items
    strat = (strategy or "median").lower()
    agg = _aggregate_specs(selected_items, strategy=("max" if strat == "max" else "median"))
    if any(v is not None for v in (agg["height_ft"], agg["length_ft"], agg["weight_lbs"])):        
        label = f"CarAPI bodies/v2 (aggregate: {'max' if strat == 'max' else 'median'}, N={len(selected_items)})"
        return {**agg, "source": label, "notes": ("trim=" + used_trim) if used_trim else ""}

    return None