# services/routing.py
import os
import math
import json
import requests
from typing import Any, Dict, List, Optional, Tuple, Union

HERE_API_KEY = os.getenv("HERE_API_KEY")

# ----------------- unit helpers -----------------
def feet_to_meters(ft: float) -> float:
    return ft * 0.3048

def pounds_to_kg(lb: float) -> float:
    return lb * 0.45359237

# ----------------- geo helpers -----------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

def offset_point(lat: float, lng: float, distance_m: float, bearing_deg: float) -> Tuple[float, float]:
    R = 6371000.0
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lng)
    lat2 = math.asin(math.sin(lat1)*math.cos(distance_m/R) + math.cos(lat1)*math.sin(distance_m/R)*math.cos(br))
    lon2 = lon1 + math.atan2(math.sin(br)*math.sin(distance_m/R)*math.cos(lat1),
                             math.cos(distance_m/R)-math.sin(lat1)*math.sin(lat2))
    return (math.degrees(lat2), math.degrees(lon2))

def _float_pair(xy: Union[Tuple[Any, Any], List[Any], str]) -> Tuple[float, float]:
    """Normalize a coordinate pair to (lat: float, lng: float)."""
    if isinstance(xy, str):
        if "," in xy:
            a, b = xy.split(",", 1)
            return (float(a.strip()), float(b.strip()))
        raise ValueError(f"Bad coordinate string: {xy}")
    if isinstance(xy, (list, tuple)) and len(xy) >= 2:
        return (float(xy[0]), float(xy[1]))
    raise ValueError(f"Unsupported coordinate format: {xy!r}")

# ----------------- HERE Flexible Polyline (spec-correct) -----------------
# Spec: https://github.com/heremaps/flexible-polyline
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_CHAR_TO_VAL = {c: i for i, c in enumerate(_ALPHABET)}

def _read_varint(s: str, idx: int):
    result = 0
    shift = 0
    while True:
        if idx >= len(s):
            raise ValueError("Invalid flexible polyline: truncated varint")
        ch = s[idx]
        if ch not in _CHAR_TO_VAL:
            raise ValueError(f"Invalid flexible polyline char: {ch!r}")
        val = _CHAR_TO_VAL[ch]
        idx += 1
        result |= (val & 0x1f) << shift
        if (val & 0x20) == 0:
            break
        shift += 5
    return result, idx

def _zigzag_decode(n: int) -> int:
    return (n >> 1) ^ (-(n & 1))

def decode_flexible_polyline(encoded: str) -> List[Tuple[float, float]]:
    """Decode HERE Flexible Polyline to list of (lat, lng)."""
    if not encoded:
        return []
    idx = 0
    header, idx = _read_varint(encoded, idx)
    precision = header & 15
    third_dim = (header >> 4) & 7
    third_dim_prec = (header >> 7) & 15  # noqa: F841

    scale = 10 ** precision
    has_z = (third_dim != 0)

    lat = 0
    lng = 0
    out: List[Tuple[float, float]] = []

    while idx < len(encoded):
        dlat, idx = _read_varint(encoded, idx)
        dlng, idx = _read_varint(encoded, idx)
        lat += _zigzag_decode(dlat)
        lng += _zigzag_decode(dlng)
        if has_z:
            dz, idx = _read_varint(encoded, idx)  # ignore 3rd dimension
            _ = _zigzag_decode(dz)
        out.append((lat / scale, lng / scale))

    # Filter invalid points
    return [(la, lo) for (la, lo) in out if -90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0]

# ----------------- optional facilities (blockers) -----------------
def load_facilities(fpath: Optional[str]) -> List[Dict[str, Any]]:
    if not fpath:
        return []
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("items", [])
    except Exception:
        return []

def detect_blockers_near(dest: Tuple[float, float], facilities: List[Dict[str, Any]], within_m=5000) -> List[str]:
    blockers = []
    if not facilities:
        return blockers
    dlat, dlng = dest
    for it in facilities:
        try:
            lat = float(it.get("lat"))
            lng = float(it.get("lng"))
            radius = float(it.get("radius_m", 500))
            name = str(it.get("name") or "facility")
            dist = haversine_m(dlat, dlng, lat, lng)
            if dist <= within_m + radius:
                blockers.append(name)
        except Exception:
            continue
    return blockers[:10]

# ----------------- HERE routing calls -----------------
def _build_vehicle_params(height_m: float, weight_kg: float,
                          length_m: Optional[float], width_m: Optional[float],
                          weight_per_axle_kg: Optional[float],
                          shipped_hazardous_goods: Optional[str],
                          tunnel_category: Optional[str]) -> Dict[str, Any]:
    """
    Build query params for HERE v8. We request notices/spans (if allowed) to surface violations.
    """
    p = {
        "transportMode": "truck",
        "routingMode": "fast",
        # ask for notices; if an account rejects this, we auto-fallback in _call_here_route
        "return": "summary,polyline,actions,notices",
        "spans": "notices",
    }
    if height_m:
        p["vehicle[height]"] = int(round(height_m * 100))  # cm
    if width_m:
        p["vehicle[width]"] = int(round(width_m * 100))
    if length_m:
        p["vehicle[length]"] = int(round(length_m * 100))
    if weight_kg:
        p["vehicle[grossWeight]"] = int(round(weight_kg))
    if weight_per_axle_kg:
        p["vehicle[weightPerAxle]"] = int(round(weight_per_axle_kg))
    if shipped_hazardous_goods:
        p["vehicle[shippedHazardousGoods]"] = shipped_hazardous_goods
    if tunnel_category:
        p["vehicle[tunnelCategory]"] = tunnel_category
    # 'tunnels' is not a valid avoid feature in v8; keep "difficultTurns" bias
    p["avoid[features]"] = "difficultTurns"
    return p

def _call_here_route(origin: Tuple[float, float], dest: Tuple[float, float],
                     vehicle_params: Dict[str, Any],
                     via: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
    """
    Calls HERE routes endpoint.
    If a 400 complains about 'return' or 'spans', retry without notices so older accounts still work.
    """
    base = "https://router.hereapi.com/v8/routes"

    def _do(params: Dict[str, Any]) -> requests.Response:
        return requests.get(base, params=params, timeout=18)

    params = dict(vehicle_params)
    params["origin"] = f"{origin[0]},{origin[1]}"
    params["destination"] = f"{dest[0]},{dest[1]}"
    if via:
        params["via"] = f"{via[0]},{via[1]}"
    params["apikey"] = HERE_API_KEY

    try:
        r = _do(params)
        data = r.json() if r.content else {}
        if r.status_code == 400:
            cause = ""
            try:
                cause = (data.get("cause") or data.get("title") or "").lower()
            except Exception:
                cause = ""
            if "invalid value for parameter 'spans'" in cause or "invalid value for parameter 'return'" in cause or "invalid return" in cause:
                # fallback: strip notices/spans and retry
                p2 = dict(params)
                if "spans" in p2: del p2["spans"]
                p2["return"] = "summary,polyline,actions"
                r = _do(p2)
                data = r.json() if r.content else {}
        ok = (r.status_code == 200 and "routes" in data and data["routes"])
        return {"ok": ok, "status": r.status_code, "raw": data}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e), "raw": None}

def _polyline_from_route_or_section(raw: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Try to pull a polyline string from section; if missing, try route level."""
    try:
        route = raw["routes"][0]
        for sec in route.get("sections", []):
            if "polyline" in sec:
                return sec.get("polyline"), sec
        if "polyline" in route:
            return route.get("polyline"), None
    except Exception:
        pass
    return None, None

def _extract_endpoints(sec: Optional[Dict[str, Any]], raw: Dict[str, Any]) -> Tuple[Tuple[float,float], Tuple[float,float]]:
    """Get (dep, arr) from the section if present; else from route summary."""
    if sec:
        try:
            dep_loc = sec.get("departure", {}).get("place", {}).get("location", {})
            arr_loc = sec.get("arrival", {}).get("place", {}).get("location", {})
            dep = (float(dep_loc.get("lat")), float(dep_loc.get("lng")))
            arr = (float(arr_loc.get("lat")), float(arr_loc.get("lng")))
            if all(abs(x) > 0 for x in [dep[0], dep[1], arr[0], arr[1]]):
                return dep, arr
        except Exception:
            pass
    try:
        bounds = raw["routes"][0].get("bbox")
        if bounds:
            south, west, north, east = bounds
            dep = (south, west); arr = (north, east)
            return dep, arr
    except Exception:
        pass
    return (0.0, 0.0), (0.0, 0.0)

def _extract_summary_and_path(route_data: Dict[str, Any]):
    """
    Extract route summary and a robust path for mapping.
    """
    try:
        if not route_data or "routes" not in route_data or not route_data["routes"]:
            return {"ok": False}, []
        route = route_data["routes"][0]
        sec0 = route.get("sections", [{}])[0]
        summ = {
            "ok": True,
            "duration": sec0.get("summary", {}).get("duration"),
            "length": sec0.get("summary", {}).get("length"),
            "mode": "truck",
        }
        poly_str, sec_poly = _polyline_from_route_or_section(route_data)
        dep, arr = _extract_endpoints(sec_poly or sec0, route_data)

        path: List[Tuple[float, float]] = []
        if poly_str:
            try:
                path = decode_flexible_polyline(poly_str)
            except Exception:
                path = []

        def _same_area(a: Tuple[float,float], b: Tuple[float,float]) -> bool:
            return haversine_m(a[0], a[1], b[0], b[1]) < 50000.0

        if not path or not _same_area(path[0], dep) or not _same_area(path[-1], arr):
            if all(abs(x) > 0 for x in [dep[0], dep[1], arr[0], arr[1]]):
                path = [dep, arr]
            else:
                path = []

        cleaned = [(la, lo) for (la, lo) in path if -90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0]
        if len(cleaned) >= 2:
            path = cleaned

        return summ, path
    except Exception:
        return {"ok": False}, []

def _collect_notices(raw: Optional[Dict[str, Any]]) -> List[str]:
    """
    Pull restriction/violation notices from route + sections + spans (if present).
    We normalize to short human-readable strings.
    """
    msgs: List[str] = []
    if not raw:
        return msgs
    try:
        route = raw.get("routes", [{}])[0]
        # route-level
        for n in route.get("notices", []) or []:
            title = str(n.get("title") or n.get("message") or n.get("code") or "Notice")
            cat = n.get("category") or n.get("type")
            if cat and cat not in title:
                title = f"{title} ({cat})"
            if title not in msgs:
                msgs.append(title)
        # section-level and spans
        for sec in route.get("sections", []) or []:
            for n in sec.get("notices", []) or []:
                title = str(n.get("title") or n.get("message") or n.get("code") or "Notice")
                cat = n.get("category") or n.get("type")
                if cat and cat not in title:
                    title = f"{title} ({cat})"
                if title not in msgs:
                    msgs.append(title)
            for sp in sec.get("spans", []) or []:
                for n in sp.get("notices", []) or []:
                    title = str(n.get("title") or n.get("message") or n.get("code") or "Notice")
                    cat = n.get("category") or n.get("type")
                    if cat and cat not in title:
                        title = f"{title} ({cat})"
                    if title not in msgs:
                        msgs.append(title)
    except Exception:
        pass
    return msgs

def _has_critical(notices: List[str]) -> bool:
    """
    Heuristic: treat as critical if text suggests illegality/restriction for trucks.
    """
    if not notices:
        return False
    crit_kw = [
        "violation", "forbidden", "prohibit", "no truck", "no trucks",
        "low bridge", "low clearance", "clearance", "height", "overheight",
        "weight", "gross weight", "gvm", "axle", "tunnel", "hazardous"
    ]
    low = " ".join(notices).lower()
    return any(k in low for k in crit_kw)

# Known via that biases against NYC tunnels when overheight (George Washington Bridge upper deck)
GWB_UPPER = (40.85177, -73.95272)

# ----------------- public entry -----------------
def plan_with_height_analysis(
    start: Tuple[float, float],
    end: Tuple[float, float],
    height_m: float,
    weight_kg: float,
    length_m: Optional[float],
    width_m: Optional[float],
    weight_per_axle_kg: Optional[float],
    shipped_hazardous_goods: Optional[str],
    tunnel_category: Optional[str],
    total_height_ft: float,
    facilities_file: Optional[str] = None,
) -> Dict[str, Any]:

    # normalize coordinates to floats early
    start = _float_pair(start)
    end = _float_pair(end)

    if not HERE_API_KEY:
        return {
            "primary_route": None,
            "primary_summary": {"ok": False, "status": 401, "error": "Missing HERE_API_KEY"},
            "warnings": ["Routing disabled: HERE_API_KEY missing."],
        }

    warnings: List[str] = []
    facilities = load_facilities(facilities_file)

    # Vehicle params
    vparams = _build_vehicle_params(
        height_m=height_m,
        weight_kg=weight_kg,
        length_m=length_m,
        width_m=width_m,
        weight_per_axle_kg=weight_per_axle_kg,
        shipped_hazardous_goods=shipped_hazardous_goods,
        tunnel_category=tunnel_category,
    )

    # -------- PRIMARY (to the exact destination) --------
    primary = _call_here_route(start, end, vparams)
    primary_summary, primary_path = _extract_summary_and_path(primary["raw"]) if primary["ok"] else ({"ok": False}, [])
    primary_notices = _collect_notices(primary["raw"]) if primary.get("ok") else []
    primary_critical = _has_critical(primary_notices) if primary.get("ok") else False

    # -------- ALTERNATIVE (same destination; optional via bias for NYC) --------
    alternative = None
    alternative_summary = None
    alternative_path: List[Tuple[float, float]] = []
    alternative_notices: List[str] = []
    alternative_critical = False

    nyc_like = (abs(end[0] - 40.75) < 0.5 and abs(end[1] - (-73.98)) < 0.7)
    via_hint = GWB_UPPER if (total_height_ft > 13.5 and nyc_like) else None

    alt_try = _call_here_route(start, end, vparams, via=via_hint)
    if alt_try["ok"]:
        alternative = alt_try
        alternative_summary, alternative_path = _extract_summary_and_path(alternative["raw"])
        alternative_notices = _collect_notices(alternative["raw"])
        alternative_critical = _has_critical(alternative_notices)

    # -------- Escalate to fallback if both routes are critical --------
    force_fallback = (primary.get("ok") and primary_critical) and (alternative and alternative.get("ok") and alternative_critical)

    # -------- Fallback staging point near destination (if both fail or forced) --------
    fallback_used = False
    fallback_dest: Optional[Tuple[float, float]] = None
    fallback_summary = None
    fallback_path: List[Tuple[float, float]] = []
    fallback_distance_remaining_m = None
    blockers: List[str] = []
    fallback_notices: List[str] = []

    if (not primary["ok"] and not (alternative and alternative.get("ok"))) or force_fallback:
        cand = find_reachable_near_dest(
            start=start,
            end=end,
            vehicle_params=vparams,
            rings_m=[500, 1500, 3000, 5000, 8000],
            bearings=[0, 45, 90, 135, 180, 225, 270, 315],
        )
        if cand:
            fallback_used = True
            fallback_dest = cand["dest"]
            fallback_summary, fallback_path = _extract_summary_and_path(cand["raw"])
            fallback_notices = _collect_notices(cand["raw"])
            fallback_distance_remaining_m = haversine_m(fallback_dest[0], fallback_dest[1], end[0], end[1])
            blockers = detect_blockers_near(end, facilities, within_m=6000)
            if force_fallback:
                warnings.append(
                    "Both primary and alternative include critical truck restrictions; suggesting the nearest reachable staging point."
                )
            else:
                warnings.append(
                    "Cannot find legal truck route to exact drop-off. "
                    "Suggested staging point nearby; proceed last segment with caution/per local guidance."
                )

    # Height guideline notice
    if total_height_ft > 13.5:
        warnings.append(f"Total height {total_height_ft:.2f} ft exceeds common US interstate guideline (13'6\").")

    # Merge HERE notices into warnings (de-duplicated, human friendly)
    def _merge_notices(label: str, items: List[str]):
        for t in items or []:
            msg = t.strip()
            if not msg:
                continue
            final = f"{label}: {msg}"
            if final not in warnings:
                warnings.append(final)

    _merge_notices("Primary notice", primary_notices)
    _merge_notices("Alternative notice", alternative_notices)
    _merge_notices("Fallback notice", fallback_notices)

    # Choose which route is 'chosen' for the banner
    chosen_summary = None
    choice_reason = ""
    use_alt = False
    if alternative and alternative.get("ok"):
        if not primary["ok"]:
            use_alt = True
            choice_reason = "Primary unreachable; using alternative."
        else:
            if total_height_ft > 13.5 or via_hint is not None:
                use_alt = True
                choice_reason = "Over height or local restriction risk; using tunnel-free biased alternative."
    elif fallback_used and fallback_summary and fallback_summary.get("ok"):
        use_alt = True
        choice_reason = "Exact drop-off unreachable; using nearest reachable staging point."

    if use_alt and (alternative_summary and alternative_summary.get("ok")):
        chosen_summary = alternative_summary
    elif use_alt and fallback_summary and fallback_summary.get("ok"):
        chosen_summary = fallback_summary
    else:
        chosen_summary = primary_summary

    # legality flags (non-breaking addition)
    legal = {
        "primary": bool(primary.get("ok") and not primary_critical),
        "alternative": bool((alternative and alternative.get("ok")) and not alternative_critical),
        "fallback": bool(fallback_used and fallback_summary and fallback_summary.get("ok")),
    }

    return {
        "warnings": warnings,
        "primary_route": primary["raw"] if primary.get("ok") else primary,
        "primary_summary": primary_summary,
        "primary_path": primary_path,
        "alternative_route": alternative["raw"] if (alternative and alternative.get("ok")) else None,
        "alternative_summary": alternative_summary if (alternative_summary and alternative_summary.get("ok")) else None,
        "alternative_path": alternative_path if alternative_path else None,
        "fallback_used": fallback_used,
        "fallback": {
            "used": fallback_used,
            "dest": list(fallback_dest) if fallback_dest else None,
            "remaining_m": fallback_distance_remaining_m,
            "summary": fallback_summary,
            "path": fallback_path,
            "blockers": blockers,
        },
        "route_notices": {
            "primary": primary_notices,
            "alternative": alternative_notices,
            "fallback": fallback_notices,
        },
        "legal": legal,
        "chosen_is_alternative": bool(use_alt and (alternative_summary and alternative_summary.get("ok"))),
        "chose_reason": choice_reason,
    }

# ----------------- fallback finder -----------------
def find_reachable_near_dest(
    start: Tuple[float, float],
    end: Tuple[float, float],
    vehicle_params: Dict[str, Any],
    rings_m: List[int],
    bearings: List[int],
) -> Optional[Dict[str, Any]]:
    start = _float_pair(start)
    end = _float_pair(end)
    best = None
    best_dist = 1e12
    for r in rings_m:
        for b in bearings:
            cand = offset_point(end[0], end[1], r, b)
            resp = _call_here_route(start, cand, vehicle_params)
            if resp["ok"]:
                dist = haversine_m(cand[0], cand[1], end[0], end[1])
                if dist < best_dist:
                    best = {"dest": cand, "raw": resp["raw"]}
                    best_dist = dist
        if best is not None:
            break
    return best
