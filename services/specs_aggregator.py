# services/specs_aggregator.py
# Orchestrates CarAPI -> CarQuery -> Heuristic

from __future__ import annotations
from typing import Dict, Optional
import anyio

# CarAPI client is optional; if it can't find specs or isn't configured, we fall through.
try:
    from services.carapi_client import lookup_specs as carapi_lookup_specs  # type: ignore
except Exception:
    carapi_lookup_specs = None  # not critical

from services.carquery_client import lookup_specs as carquery_lookup_specs
from services.specs_heuristics import estimate_specs

async def resolve_vehicle_specs(year: int, make: str, model: str) -> Dict:
    # 1) CarAPI (if available)
    if callable(carapi_lookup_specs):
        try:
            spec = await anyio.to_thread.run_sync(carapi_lookup_specs, year, make, model)
            if spec and (spec.get("height_ft") or spec.get("weight_lbs")):
                spec["source"] = spec.get("source") or "carapi"
                return spec
        except Exception:
            pass

    # 2) CarQuery
    try:
        spec = await anyio.to_thread.run_sync(carquery_lookup_specs, year, make, model)
        if spec and (spec.get("height_ft") or spec.get("weight_lbs")):
            return spec
    except Exception:
        pass

    # 3) Heuristic
    return estimate_specs(year, make, model)
