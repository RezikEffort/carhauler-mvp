# services/specs_heuristics.py
# Last-resort segment-based estimates when APIs can't provide specs.

from __future__ import annotations
from typing import Dict

PICKUP_TOKENS = {
    "F-150","F150","SILVERADO","SIERRA","RAM","TACOMA","TUNDRA","RANGER",
    "COLORADO","CANYON","FRONTIER","RIDGELINE","TITAN",
}
SUV_TOKENS = {
    "CR-V","CRV","RAV4","HIGHLANDER","4RUNNER","EXPLORER","ESCAPE","EDGE",
    "ROGUE","PATHFINDER","OUTBACK","FORESTER","PILOT","CX-5","CX5","CX-9","CX9",
    "SORENTO","TELLURIDE","TAHOE","SUBURBAN","EXPEDITION","GLC","GLA","Q5","X3","X5","MODEL Y"
}
SEDAN_TOKENS = {
    "CIVIC","COROLLA","CAMRY","ACCORD","ALTIMA","ELANTRA","SONATA","MODEL 3","MODEL S",
}

def _segment(make: str, model: str) -> str:
    m = (make + " " + model).upper()
    if any(tok in m for tok in PICKUP_TOKENS):
        return "pickup"
    if any(tok in m for tok in SUV_TOKENS):
        return "suv"
    if any(tok in m for tok in SEDAN_TOKENS):
        return "sedan"
    # default guess by common distribution
    return "sedan"

def estimate_specs(year: int, make: str, model: str) -> Dict:
    seg = _segment(make, model)
    if seg == "pickup":
        height_ft = 6.3
        weight_lbs = 4800
    elif seg == "suv":
        height_ft = 5.7
        weight_lbs = 3950
    else:  # sedan/hatch
        height_ft = 4.8
        weight_lbs = 3200

    return {
        "height_ft": round(float(height_ft), 2),
        "weight_lbs": round(float(weight_lbs), 0),
        "source": "estimate",
        "notes": f"segment-based ({seg})",
    }
