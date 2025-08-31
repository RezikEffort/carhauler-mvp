# services/vehicles.py
import json
import re
from typing import Dict, List, Tuple
from functools import lru_cache
import requests

# Fallback specs (approx curb weight & overall height) for common models you tested
# Use conservative/taller & heavier values where ranges exist.
FALLBACK_SPECS = {
    ("honda", "civic", 2020):     {"height_ft": 4.64, "weight_lbs": 2771},
    ("toyota", "camry", 2018):    {"height_ft": 4.74, "weight_lbs": 3340},
    ("tesla", "model 3", 2020):   {"height_ft": 4.73, "weight_lbs": 4032},
    ("honda", "cr-v", 2020):      {"height_ft": 5.54, "weight_lbs": 3521},
    ("toyota", "rav4", 2020):     {"height_ft": 5.58, "weight_lbs": 3490},
    ("ford", "f-150", 2021):      {"height_ft": 6.43, "weight_lbs": 4705},
    ("chevrolet", "tahoe", 2020): {"height_ft": 6.20, "weight_lbs": 5602},
    ("ford", "explorer", 2020):   {"height_ft": 5.83, "weight_lbs": 4345},
    ("subaru", "outback", 2019):  {"height_ft": 5.54, "weight_lbs": 3686},
}

CARQUERY_BASE = "https://www.carqueryapi.com/api/0.3/"  # free, no key

def _to_ft(mm: float) -> float:
    return round((mm or 0.0) / 304.8, 2)

def _to_lbs(kg: float) -> float:
    return round((kg or 0.0) * 2.20462262185, 0)

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _first_json_block(text: str) -> dict:
    """
    CarQuery often returns JSONP (`?({...});`).
    Extract the first {...} block safely.
    """
    if not isinstance(text, str):
        raise ValueError("CarQuery response not text")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in CarQuery response")
    return json.loads(text[start:end+1])

@lru_cache(maxsize=512)
def carquery_get_trims(make: str, model: str, year: int) -> List[dict]:
    """
    Query CarQuery for all trims matching year/make/model.
    Returns list of trims; each may contain model_height_mm, model_weight_kg.
    """
    params = {
        "cmd": "getTrims",
        "make": make,
        "model": model,
        "year": str(year),
    }
    # CarQuery prefers JSONP; we'll parse JSON out of it.
    r = requests.get(CARQUERY_BASE, params=params, timeout=15)
    r.raise_for_status()
    data = _first_json_block(r.text)
    return data.get("Trims") or []

def resolve_vehicle_specs_once(make: str, model: str, year: int) -> Tuple[float, float, List[str]]:
    """
    Returns: (height_ft, weight_lbs, warnings)
    Tries CarQuery first; falls back to a small built-in table; if still missing, raises.
    """
    warnings: List[str] = []
    mk = _norm(make)
    md = _norm(model)
    yr = int(year)

    # 1) Try CarQuery
    try:
        trims = carquery_get_trims(mk, md, yr)
        if trims:
            # Choose a conservative/tall & heavy option across trims
            heights_ft = []
            weights_lbs = []
            for t in trims:
                h_mm = t.get("model_height_mm")
                w_kg = t.get("model_weight_kg")
                # some values can be strings like "1643" or empty ""
                try:
                    if h_mm not in (None, "", "0"):
                        heights_ft.append(_to_ft(float(h_mm)))
                except Exception:
                    pass
                try:
                    if w_kg not in (None, "", "0"):
                        weights_lbs.append(_to_lbs(float(w_kg)))
                except Exception:
                    pass

            h_ft = max(heights_ft) if heights_ft else None
            w_lb = max(weights_lbs) if weights_lbs else None

            if h_ft and w_lb:
                return float(h_ft), float(w_lb), warnings
            # Partial success → warn and fall through to fallback map to try fill missing
            if not h_ft:
                warnings.append(f"No height from CarQuery for {year} {make} {model}.")
            if not w_lb:
                warnings.append(f"No weight from CarQuery for {year} {make} {model}.")
    except Exception as e:
        warnings.append(f"CarQuery lookup failed for {year} {make} {model}: {e}")

    # 2) Fallback table
    fb = FALLBACK_SPECS.get((mk, md, yr))
    if fb and fb.get("height_ft") and fb.get("weight_lbs"):
        return float(fb["height_ft"]), float(fb["weight_lbs"]), warnings

    # 3) Give up
    raise ValueError(f"Could not resolve specs for {year} {make} {model}")

def resolve_missing_specs(cars: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    For each car, if height_ft or weight_lbs is **missing (None)**, resolve via CarQuery/fallback.
    If user provided a value, we keep it exactly as-is.
    """
    resolved: List[Dict] = []
    warnings: List[str] = []
    for c in cars:
        car = dict(c)

        # Only fill in if the field is truly missing (None), not just falsy.
        height_val = car.get("height_ft", None)
        weight_val = car.get("weight_lbs", None)
        need_height = (height_val is None)
        need_weight = (weight_val is None)

        if need_height or need_weight:
            try:
                h_ft, w_lb, w = resolve_vehicle_specs_once(car["make"], car["model"], int(car["year"]))
                warnings.extend(w)
                if need_height:
                    car["height_ft"] = h_ft
                if need_weight:
                    car["weight_lbs"] = w_lb
            except Exception as e:
                warnings.append(str(e))

        resolved.append(car)

    return resolved, warnings