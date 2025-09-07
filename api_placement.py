# api_placement.py
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services.placement_heuristic import compute_placement

router = APIRouter()

# Keep these aligned with your rig and frontend defaults
DEFAULT_DECK_HEIGHT_FT = 5.0
DEFAULT_UPPER_DECK_OFFSET_FT = 2.5  # fallback for unknown top slots
DEFAULT_SLOT_OFFSETS_TOP = {
    # Per-slot top-deck offsets (tune to your trailer)
    "T1_HEAD": 2.0,
    "T2_FRONT": 2.6,
    "T3_MID": 2.8,
    "T4_REAR": 2.5,
}
SLOTS_LOWER = ["B1_FRONT", "B2_MID", "B3_REAR", "B4_REAR2", "B5_TAIL"]
SLOTS_TOP   = ["T1_HEAD", "T2_FRONT", "T3_MID", "T4_REAR"]

# Simple height guideline; adjust per jurisdiction/permits as needed
MAX_HEIGHT_FT_GUIDELINE = 13.5


class PlacementCar(BaseModel):
    id: str
    length_ft: float
    width_ft: float
    height_ft: float
    weight_lbs: float
    drop_order: int


class OrientationRules(BaseModel):
    allow_reversed: bool = True
    top_only: bool = True
    # Only consider reversing if car is at least this tall
    min_height_for_benefit_ft: float = 5.6
    # Simple benefit (in feet) for reversing on eligible slots/vehicles
    reverse_bonus_ft: float = 0.30


class PlacementRequest(BaseModel):
    cars: List[PlacementCar]
    deck_height_ft: float = Field(default=DEFAULT_DECK_HEIGHT_FT)
    # Optional per-slot overrides; unknown top slots fall back to DEFAULT_UPPER_DECK_OFFSET_FT
    slot_offsets_ft: Optional[Dict[str, float]] = None
    orientation_rules: Optional[OrientationRules] = None
    max_iters: int = 400


def _is_top_slot(slot_id: str) -> bool:
    s = str(slot_id).upper()
    return s.startswith("T") or s in SLOTS_TOP or "TOP" in s


def _slot_offset(slot_id: str, top_map: Dict[str, float]) -> float:
    if _is_top_slot(slot_id):
        return float(top_map.get(str(slot_id), DEFAULT_UPPER_DECK_OFFSET_FT))
    return 0.0


@router.post("/placement-plan")
def placement_plan(req: PlacementRequest) -> Dict[str, Any]:
    """
    Returns:
      {
        assignments: [{car_id, slot_id, orientation, loaded_ft, offset_ft}, ...],
        scores: {...},
        warnings: [...],
        heights_by_deck: {lower_loaded_ft, upper_loaded_ft, upper_deck_offset_ft},
        max_loaded: {lower: {slot_id, loaded_ft}|None, upper: {slot_id, loaded_ft}|None},
        deck_profile_used: { deck_height_ft },
        slot_offsets_used: { ... per top slot ... },
        orientation_rules_used: { ... }
      }
    """
    # 1) Base placement (slot selection)
    try:
        base: Dict[str, Any] = compute_placement(
            cars_input=[c.dict() for c in req.cars],
            max_iters=req.max_iters,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"compute_placement failed: {e}")

    # 2) Per-slot offsets map
    slot_offsets = {**DEFAULT_SLOT_OFFSETS_TOP}
    if req.slot_offsets_ft:
        slot_offsets.update({str(k): float(v) for k, v in req.slot_offsets_ft.items()})

    # 3) Orientation rules
    rules = req.orientation_rules or OrientationRules()

    # 4) Car lookup
    car_by_id = {c.id: c for c in req.cars}

    # 5) Apply offsets + pick orientation to minimize loaded height (simple heuristic)
    assignments_out: List[Dict[str, Any]] = []
    lower_max = 0.0
    upper_max = 0.0
    lower_max_slot: Optional[str] = None
    upper_max_slot: Optional[str] = None

    for a in base.get("assignments", []):
        cid = a.get("car_id")
        sid = str(a.get("slot_id"))
        car = car_by_id.get(cid)
        if not car or not sid:
            continue

        is_top = _is_top_slot(sid)
        offset = _slot_offset(sid, slot_offsets)

        # forward / reversed decision
        orientation = "forward"
        reverse_bonus_ft = 0.0

        if rules.allow_reversed and (not rules.top_only or is_top):
            if float(car.height_ft) >= rules.min_height_for_benefit_ft:
                # Take the simple benefit if reversed: lower peak by reverse_bonus_ft
                reverse_bonus_ft = rules.reverse_bonus_ft
                # Choose reversed only if it actually reduces height
                orientation = "reversed"

        loaded_ft = req.deck_height_ft + offset + float(car.height_ft) - (reverse_bonus_ft if orientation == "reversed" else 0.0)
        loaded_ft = round(max(0.0, loaded_ft), 2)

        if is_top:
            if loaded_ft > upper_max:
                upper_max = loaded_ft
                upper_max_slot = sid
        else:
            if loaded_ft > lower_max:
                lower_max = loaded_ft
                lower_max_slot = sid

        assignments_out.append({
            "car_id": cid,
            "slot_id": sid,
            "orientation": orientation,
            "loaded_ft": loaded_ft,
            "offset_ft": round(offset, 2),
        })

    # 6) Merge warnings (height guideline check)
    warnings = list(base.get("warnings", []))
    over = [f"{x['slot_id']} ({x['car_id']}) {x['loaded_ft']} ft"
            for x in assignments_out if x["loaded_ft"] > MAX_HEIGHT_FT_GUIDELINE]
    if over:
        warnings.append(
            f"Loaded height exceeds {MAX_HEIGHT_FT_GUIDELINE:.1f} ft at: " + ", ".join(over)
        )

    # 7) Finish payload
    base["assignments"] = assignments_out
    base["warnings"] = warnings
    base["heights_by_deck"] = {
        "lower_loaded_ft": round(lower_max, 2),
        "upper_loaded_ft": round(upper_max, 2),
        # Echo a representative offset; individual per-slot offsets are in slot_offsets_used
        "upper_deck_offset_ft": None,
    }
    base["max_loaded"] = {
        "lower": None if lower_max_slot is None else {"slot_id": lower_max_slot, "loaded_ft": round(lower_max, 2)},
        "upper": None if upper_max_slot is None else {"slot_id": upper_max_slot, "loaded_ft": round(upper_max, 2)},
    }
    base["deck_profile_used"] = {"deck_height_ft": float(req.deck_height_ft)}
    base["slot_offsets_used"] = slot_offsets
    base["orientation_rules_used"] = rules.dict()

    return base