# services/calculator.py
from typing import List, Dict, Any, Tuple

# Simple global limits (guideline)
MAX_HEIGHT_FEET = 13.5  # 13'6" guideline
MAX_WEIGHT_LBS = 80000  # typical US GVW cap (varies by state/permit)

# Model the upper deck rail/tilt offset conservatively
UPPER_DECK_OFFSET_FT = 2.5

SLOTS_LOWER = ["LOWER_FRONT", "LOWER_MID1", "LOWER_MID2", "LOWER_REAR", "LOWER_TAIL"]
SLOTS_TOP   = ["TOP_FRONT", "TOP_MID1", "TOP_MID2", "TOP_REAR"]
ALL_SLOTS   = SLOTS_LOWER + SLOTS_TOP


# ---------- Unit helpers ----------
def feet_to_meters(ft: float) -> float:
    return ft * 0.3048

def pounds_to_kg(lb: float) -> float:
    return lb * 0.45359237


# ---------- Core totals (doesn't do slotting) ----------
def calculate_load(
    truck_weight_lbs: float,
    trailer_weight_lbs: float,
    trailer_height_ft: float,
    cars: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_weight_lbs = truck_weight_lbs + trailer_weight_lbs + sum(c.get("weight_lbs", 0.0) for c in cars)
    tallest_car_ft = max((c.get("height_ft", 0.0) for c in cars), default=0.0)

    # naive overall height if everything were on a flat deck (not used for routing once we arrange)
    naive_total_height_ft = trailer_height_ft + tallest_car_ft

    return {
        "truck_weight_lbs": truck_weight_lbs,
        "trailer_weight_lbs": trailer_weight_lbs,
        "trailer_height_ft": trailer_height_ft,
        "total_weight_lbs": total_weight_lbs,
        "naive_total_height_ft": round(naive_total_height_ft, 2),
    }


# ---------- Arrangement ----------
def _loaded_height_for_slot(base_deck_ft: float, car_height_ft: float, is_upper: bool) -> float:
    """
    Loaded height = deck height (+ upper deck offset) + car height.
    We don't mutate car.height_ft; this returns per-slot loaded height.
    """
    if is_upper:
        return base_deck_ft + UPPER_DECK_OFFSET_FT + car_height_ft
    return base_deck_ft + car_height_ft


def _greedy_arrange(
    cars: List[Dict[str, Any]],
    deck_ft: float,
) -> Tuple[Dict[str, Dict[str, Any]], float, float]:
    """
    Place taller/heavier vehicles on LOWER first, shorter on TOP.
    Returns:
      layout: { SLOT: { car: {...}, loaded_height_ft: float, deck: "LOWER"/"TOP" } }
      lower_max_loaded_ft
      upper_max_loaded_ft
    """
    cars_copy = [dict(c) for c in cars]  # don't mutate caller's cars

    # Order: tallest first (breaking ties by heavier)
    cars_sorted = sorted(
        cars_copy,
        key=lambda c: (c.get("height_ft", 0.0), c.get("weight_lbs", 0.0)),
        reverse=True,
    )

    layout: Dict[str, Dict[str, Any]] = {slot: None for slot in ALL_SLOTS}

    lower_max = 0.0
    upper_max = 0.0

    # 1) Fill LOWER first (up to 5 slots) with tallest
    lower_i = 0
    upper_i = 0
    for car in cars_sorted:
        if lower_i < len(SLOTS_LOWER):
            slot = SLOTS_LOWER[lower_i]
            lower_i += 1
            loaded_h = _loaded_height_for_slot(deck_ft, car.get("height_ft", 0.0), is_upper=False)
            layout[slot] = {
                "car": car,
                "loaded_height_ft": round(loaded_h, 2),
                "deck": "LOWER",
            }
            if loaded_h > lower_max:
                lower_max = loaded_h
        else:
            break

    # 2) Remaining cars → TOP from shortest to tallest (to minimize height)
    remaining = cars_sorted[len(SLOTS_LOWER):]
    remaining_sorted_top = sorted(remaining, key=lambda c: c.get("height_ft", 0.0))  # shortest first

    for car in remaining_sorted_top:
        if upper_i < len(SLOTS_TOP):
            slot = SLOTS_TOP[upper_i]
            upper_i += 1
            loaded_h = _loaded_height_for_slot(deck_ft, car.get("height_ft", 0.0), is_upper=True)
            layout[slot] = {
                "car": car,
                "loaded_height_ft": round(loaded_h, 2),
                "deck": "TOP",
            }
            if loaded_h > upper_max:
                upper_max = loaded_h
        else:
            break

    return layout, round(lower_max, 2), round(upper_max, 2)


def suggest_arrangement(
    cars: List[Dict[str, Any]],
    trailer_height_ft: float,
    max_height_ft: float,
    truck_weight_lbs: float,
    trailer_weight_lbs: float,
    max_weight_lbs: float,
) -> Dict[str, Any]:
    """
    Returns a suggestion with:
      - layout: per slot: { car, loaded_height_ft, deck }
      - heights_by_deck: lower_loaded_ft, upper_loaded_ft, upper_deck_offset_ft
      - computed_max_height_ft
      - arranged_cars: the cars we actually placed (original heights preserved)
      - warnings: list
    """
    layout, lower_max_ft, upper_max_ft = _greedy_arrange(cars, deck_ft=trailer_height_ft)
    computed_max = max(lower_max_ft, upper_max_ft or 0.0)

    warnings: List[str] = []
    total_weight_lbs = truck_weight_lbs + trailer_weight_lbs + sum(c.get("weight_lbs", 0.0) for c in cars)
    if total_weight_lbs > max_weight_lbs:
        warnings.append(
            f"Total weight {total_weight_lbs:.0f} lbs exceeds common GVW cap of {max_weight_lbs:.0f} lbs without permits."
        )
    if computed_max > max_height_ft:
        warnings.append(
            f"Loaded height {computed_max:.2f} ft exceeds {max_height_ft:.1f} ft guideline. Consider moving taller cars to LOWER or reducing deck."
        )

    arranged_cars = [v["car"] for k, v in layout.items() if v]

    return {
        "layout": layout,
        "heights_by_deck": {
            "lower_loaded_ft": lower_max_ft,
            "upper_loaded_ft": upper_max_ft if upper_max_ft else 0.0,
            "upper_deck_offset_ft": UPPER_DECK_OFFSET_FT,
        },
        "computed_max_height_ft": round(computed_max, 2),
        "arranged_cars": arranged_cars,
        "warnings": warnings,
    }