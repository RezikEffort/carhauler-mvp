# services/restrictions.py
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import json
from pathlib import Path
from functools import lru_cache

@dataclass
class Facility:
    name: str
    kind: str  # "tunnel" | "bridge" | ...
    bbox: Tuple[float, float, float, float]  # (S, W, N, E)
    min_height_ft: float
    notes: str
    avoid_area_param: str
    via: Optional[str] = None

def point_in_bbox(lat: float, lng: float, bbox: Tuple[float, float, float, float]) -> bool:
    s, w, n, e = bbox
    return (s <= lat <= n) and (w <= lng <= e)

@lru_cache(maxsize=4)
def load_facilities(path: str) -> List[Facility]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Facilities file not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    facs: List[Facility] = []
    for f in raw.get("facilities", []):
        facs.append(
            Facility(
                name=f["name"],
                kind=f["kind"],
                bbox=tuple(f["bbox"]),
                min_height_ft=float(f["min_height_ft"]),
                notes=f.get("notes", ""),
                avoid_area_param=f["avoid_area_param"],
                via=f.get("via"),
            )
        )
    return facs

def scan_polyline_against_facilities(
    coords: List[Tuple[float, float]],
    facilities: List[Facility],
    max_height_ft: float
) -> List[Dict]:
    """
    Returns list of hits with conflict flag:
    [{'facility': Facility, 'conflict': True/False}]
    """
    hits: List[Dict] = []
    if not coords:
        return hits
    for fac in facilities:
        if any(point_in_bbox(lat, lon, fac.bbox) for (lat, lon) in coords):
            hits.append({
                "facility": fac,
                "conflict": (max_height_ft > fac.min_height_ft)
            })
    return hits