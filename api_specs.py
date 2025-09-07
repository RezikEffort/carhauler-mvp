# api_specs.py
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.carapi_client import lookup_body_specs

specs_router = APIRouter()

class SpecReq(BaseModel):
    year: int
    make: str
    model: str
    trim: Optional[str] = None
    # Default to 'first' per your request; 'median' or 'max' are still accepted
    strategy: Optional[str] = "first"

async def _lookup_specs(req: SpecReq) -> dict:
    try:
        data = await lookup_body_specs(
            req.year, req.make, req.model,
            trim=req.trim,
            strategy=(req.strategy or "first"),
        )
        if data:
            return data
    except Exception as e:
        print("CarAPI bodies/v2 lookup failed:", e)
    raise HTTPException(status_code=404, detail="No specs found for given Year/Make/Model")

# Keep both routes alive (new & legacy)
@specs_router.post("/vehicle-options/vehicle-specs")
async def vehicle_specs(req: SpecReq):
    return await _lookup_specs(req)

@specs_router.post("/vehicle-specs")
async def vehicle_specs_legacy(req: SpecReq):
    return await _lookup_specs(req)
