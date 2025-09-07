# main.py
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from api_specs import specs_router
# main.py – add below your existing index() route
from fastapi import HTTPException

# Routers (ensure these files exist per the latest backend you added)
from api_placement import router as placement_router
from api_vehicle_options import options_router
from api_specs import specs_router

# Services
from services.geocoding import geocode_address
from services.analytics import log_event
from services.routing import plan_with_height_analysis, feet_to_meters, pounds_to_kg

# -----------------------------
# Env / HERE key
# -----------------------------
load_dotenv()

def _sanitize_key(k: Optional[str]) -> Optional[str]:
    if k is None:
        return None
    k = k.strip()
    return " ".join(k.split())

HERE_API_KEY = _sanitize_key(os.getenv("HERE_API_KEY"))
print("DEBUG HERE_API_KEY:", ("<missing>" if not HERE_API_KEY else HERE_API_KEY[:4] + "…" + HERE_API_KEY[-4:]))

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")

# -----------------------------
# FastAPI setup
# -----------------------------
app = FastAPI(title="Car Hauler Planner (MVP)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount feature routers
app.include_router(placement_router)   # /placement-plan
app.include_router(options_router)     # /vehicle-options/*  (makes, models, vehicle-specs -> CarAPI Bodies v2)
app.include_router(specs_router)  
# /vehicle-specs      (legacy passthrough -> Bodies v2)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Serve UI
@app.get("/", include_in_schema=False)
def index():
    for fname in ("app.html", "index.html"):
        f = os.path.join(STATIC_DIR, fname)
        if os.path.exists(f):
            return FileResponse(f)
    return JSONResponse({"ok": True, "msg": "UI not found; put app.html or index.html in /static"})



@app.get("/picker", include_in_schema=False)
def picker():
    f = os.path.join(STATIC_DIR, "picker.html")
    if os.path.exists(f):
        return FileResponse(f)
    raise HTTPException(status_code=404, detail="picker.html not found")

# Optional health/debug
@app.get("/health")
def health():
    return {"ok": True, "service": "carhauler", "routes": ["/plan-route"]}

@app.get("/_debug/env")
def debug_env():
    return {
        "ok": True,
        "has_here_key": bool(HERE_API_KEY),
        "static_exists": os.path.isdir(STATIC_DIR),
    }

# -----------------------------
# Models
# -----------------------------
class CarIn(BaseModel):
    make: str
    model: str
    year: int
    height_ft: Optional[float] = None
    weight_lbs: Optional[float] = None

class PlanRequest(BaseModel):
    origin: str
    destination: str
    cars: List[CarIn] = Field(default_factory=list)

    # truck/trailer profile (defaults used if missing)
    truck_weight_lbs: Optional[float] = 20000
    trailer_weight_lbs: Optional[float] = 18000
    trailer_height_ft: Optional[float] = 5.0  # deck height
    truck_length_ft: Optional[float] = 75.0
    truck_width_ft: Optional[float] = 8.5
    weight_per_axle_lbs: Optional[float] = 12000

    shipped_hazardous_goods: Optional[str] = None
    tunnel_category: Optional[str] = None

# -----------------------------
# Geocoding helpers (accept address or lat,lng)
# -----------------------------
def _try_parse_latlng(text: str) -> Optional[Tuple[float, float]]:
    """Return (lat,lng) if text looks like 'lat,lng'."""
    if not isinstance(text, str) or "," not in text:
        return None
    a, b = text.split(",", 1)
    try:
        lat = float(a.strip())
        lng = float(b.strip())
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return None
        return (lat, lng)
    except Exception:
        return None

def _resolve_place(text: str) -> Tuple[Tuple[float, float], str]:
    """
    Accepts either 'lat,lng' or a freeform address.
    Uses services.geocoding.geocode_address for addresses (US-biased).
    """
    pair = _try_parse_latlng(text)
    if pair:
        return (float(pair[0]), float(pair[1])), f"{pair[0]:.6f},{pair[1]:.6f}"
    # Address path
    latlng = geocode_address(text)
    if not latlng:
        raise HTTPException(status_code=422, detail=f"Could not geocode: {text}")
    return (float(latlng[0]), float(latlng[1])), text

# -----------------------------
# Simple load/height suggestion
# -----------------------------
SLOTS = [
    "LOWER_FRONT", "LOWER_MID1", "LOWER_MID2", "LOWER_REAR", "LOWER_TAIL",
    "TOP_FRONT", "TOP_MID1", "TOP_MID2", "TOP_REAR"
]
MAX_CARS = 9

def suggest_layout_and_heights(cars: List[CarIn], deck_height_ft: float) -> Dict[str, Any]:
    """
    Simple heuristic:
      - Put tallest cars on lower deck first.
      - Then fill top deck with remaining.
      - Compute loaded heights.
    """
    norm: List[Dict[str, Any]] = []
    for c in cars[:MAX_CARS]:
        h = c.height_ft if (c.height_ft is not None) else 5.0
        w = c.weight_lbs if (c.weight_lbs is not None) else 3500.0
        norm.append({"car": c, "h": float(h), "w": float(w)})

    norm.sort(key=lambda x: (-x["h"], x["w"]))
    picked = norm[:MAX_CARS]

    lower = picked[:5]
    upper = picked[5:]

    upper_offset = max(2.3, min(3.0, deck_height_ft * 0.5))
    lower_loaded_max = max([deck_height_ft + x["h"] for x in lower], default=0.0)
    upper_loaded_max = max([upper_offset + x["h"] for x in upper], default=0.0)

    layout: Dict[str, Any] = {}

    def _pack(names: List[str], arr: List[Dict[str, Any]], is_upper: bool):
        for i, name in enumerate(names):
            if i < len(arr):
                car = arr[i]["car"]
                base = upper_offset if is_upper else deck_height_ft
                layout[name] = {
                    "car": {
                        "make": car.make, "model": car.model, "year": car.year,
                        "height_ft": arr[i]["h"], "weight_lbs": arr[i]["w"]
                    },
                    "loaded_height_ft": round(base + arr[i]["h"], 2)
                }
            else:
                layout[name] = None

    _pack(SLOTS[:5], lower, is_upper=False)
    _pack(SLOTS[5:], upper, is_upper=True)

    return {
        "layout": layout,
        "heights_by_deck": {
            "lower_loaded_ft": round(lower_loaded_max, 2),
            "upper_loaded_ft": round(upper_loaded_max, 2),
            "upper_deck_offset_ft": round(upper_offset, 2),
        }
    }

def sum_weights(cars: List[CarIn], truck_lbs: float, trailer_lbs: float) -> float:
    total = (truck_lbs or 0) + (trailer_lbs or 0)
    for c in cars[:MAX_CARS]:
        total += float(c.weight_lbs) if c.weight_lbs is not None else 3500.0
    return total

# -----------------------------
# Route planning endpoint
# -----------------------------
@app.post("/plan-route")
def plan_route(req: PlanRequest):
    if not req.cars:
        raise HTTPException(status_code=400, detail="Add at least one car.")

    # 1) Resolve origin/destination
    try:
        (o_latlng, o_label) = _resolve_place(req.origin)
        (d_latlng, d_label) = _resolve_place(req.destination)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to resolve origin/destination: {e}")

    # 2) Build suggestion & totals
    deck_ft = float(req.trailer_height_ft or 5.0)
    suggestion = suggest_layout_and_heights(req.cars, deck_height_ft=deck_ft)

    total_height_ft = max(
        suggestion["heights_by_deck"]["lower_loaded_ft"],
        suggestion["heights_by_deck"]["upper_loaded_ft"]
    )
    total_weight_lbs = sum_weights(req.cars, req.truck_weight_lbs or 0.0, req.trailer_weight_lbs or 0.0)

    totals_for_here = {
        "total_height_ft": round(total_height_ft, 2),
        "total_height_m": round(feet_to_meters(total_height_ft), 3),
        "total_weight_lbs": round(total_weight_lbs, 1),
        "total_weight_kg": round(pounds_to_kg(total_weight_lbs), 1),
    }

    # 3) Call routing (fallback handled inside)
    try:
        facilities_path = os.path.join(APP_DIR, "data", "facilities_us_seed.json")
        route_pkg = plan_with_height_analysis(
            start=o_latlng,
            end=d_latlng,
            height_m=feet_to_meters(total_height_ft),
            weight_kg=pounds_to_kg(total_weight_lbs),
            length_m=feet_to_meters(float(req.truck_length_ft or 0.0)) if req.truck_length_ft else None,
            width_m=feet_to_meters(float(req.truck_width_ft or 0.0)) if req.truck_width_ft else None,
            weight_per_axle_kg=pounds_to_kg(float(req.weight_per_axle_lbs or 0.0)) if req.weight_per_axle_lbs else None,
            shipped_hazardous_goods=req.shipped_hazardous_goods,
            tunnel_category=req.tunnel_category,
            total_height_ft=total_height_ft,
            facilities_file=facilities_path if os.path.exists(facilities_path) else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing call failed: {e}")

    # 4) Choose summary for the banner
    chosen = route_pkg.get("alternative_summary") if route_pkg.get("chosen_is_alternative") else route_pkg.get("primary_summary")
    if not chosen or not chosen.get("ok"):
        chosen = route_pkg.get("primary_summary") or {}

    # 5) Analytics (fire-and-forget)
    try:
        event = {
            "type": "plan_route",
            "anon_user": "public",
            "origin_label": o_label,
            "destination_label": d_label,
            "origin_coord_round": [round(o_latlng[0], 2), round(o_latlng[1], 2)],
            "destination_coord_round": [round(d_latlng[0], 2), round(d_latlng[1], 2)],
            "total_height_ft": totals_for_here.get("total_height_ft"),
            "total_weight_lbs": totals_for_here.get("total_weight_lbs"),
            "warnings": route_pkg.get("warnings", []),
            "primary_summary": route_pkg.get("primary_summary"),
            "alternative_summary": route_pkg.get("alternative_summary"),
            "chosen_is_alternative": route_pkg.get("chosen_is_alternative"),
            "chose_reason": route_pkg.get("chose_reason"),
            "heights_by_deck": suggestion.get("heights_by_deck"),
            "cars_count": len(req.cars or []),
        }
        log_event(event)
    except Exception:
        pass

    # 6) Return full payload for the UI
    return {
        "geocoding": {
            "origin_input": req.origin,
            "destination_input": req.destination,
            "origin_coord": [o_latlng[0], o_latlng[1]],
            "destination_coord": [d_latlng[0], d_latlng[1]],
            "origin_label": o_label,
            "destination_label": d_label,
        },
        "profile_used": {
            "truck_weight_lbs": req.truck_weight_lbs,
            "trailer_weight_lbs": req.trailer_weight_lbs,
            "trailer_height_ft": req.trailer_height_ft,
            "truck_length_ft": req.truck_length_ft,
            "truck_width_ft": req.truck_width_ft,
            "weight_per_axle_lbs": req.weight_per_axle_lbs,
        },
        "totals_for_here": totals_for_here,
        "suggestion": suggestion,
        "routing": route_pkg,            # includes *_path, summaries, warnings (from services.routing)
        "chosen_summary": chosen,
        "decision": {
            "reason": route_pkg.get("chose_reason", ""),
        },
    }