# api_vehicle_options.py
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query
import os, aiohttp

options_router = APIRouter()

# --- static for instant responses ---
STATIC_MAKES: List[str] = [
    "Acura","Alfa Romeo","Audi","BMW","Buick","Cadillac","Chevrolet","Chrysler",
    "Dodge","Fiat","Ford","Genesis","GMC","Honda","Hyundai","Infiniti","Jaguar",
    "Jeep","Kia","Land Rover","Lexus","Lincoln","Mazda","Mercedes-Benz","Mini",
    "Mitsubishi","Nissan","Porsche","Ram","Subaru","Tesla","Toyota","Volkswagen",
    "Volvo","Rivian","Polestar"
]
POPULAR_MODELS_BY_MAKE: Dict[str, List[str]] = {
    "Toyota": ["Camry","Corolla","RAV4","Highlander","Tacoma","Tundra","Prius","Sienna","4Runner"],
    "Honda": ["Civic","Accord","CR-V","Pilot","Odyssey","HR-V","Ridgeline","Passport"],
    "Ford": ["F-150","F-250","F-350","Explorer","Escape","Edge","Expedition","Mustang","Ranger","Bronco","Maverick"],
    "Chevrolet": ["Silverado 1500","Silverado 2500HD","Silverado 3500HD","Tahoe","Suburban","Traverse","Equinox","Colorado","Malibu","Camaro","Blazer"],
    "Tesla": ["Model 3","Model Y","Model S","Model X","Cybertruck"],
    "Subaru": ["Outback","Forester","Crosstrek","Impreza","Ascent","Legacy"],
    "Nissan": ["Altima","Sentra","Rogue","Murano","Pathfinder","Frontier","Versa","Maxima"],
    "GMC": ["Sierra 1500","Sierra 2500HD","Sierra 3500HD","Yukon","Acadia","Terrain","Canyon"],
    "Ram": ["1500","2500","3500","ProMaster"],
    "Dodge": ["Durango","Charger","Challenger","Hornet","Journey"],
    "Jeep": ["Wrangler","Grand Cherokee","Cherokee","Compass","Renegade","Gladiator","Wagoneer"],
    "Volkswagen": ["Jetta","Golf","Tiguan","Atlas","Taos","ID.4","Passat"],
    "Hyundai": ["Elantra","Sonata","Tucson","Santa Fe","Palisade","Kona","Venue","Ioniq 5"],
    "Kia": ["Forte","K5","Soul","Sportage","Sorento","Telluride","Seltos","Niro"],
    "Mazda": ["Mazda3","Mazda6","CX-30","CX-5","CX-50","CX-9"],
    "Lexus": ["RX","NX","ES","IS","GX","LX","UX"],
    "Acura": ["Integra","ILX","TLX","RDX","MDX"],
    "BMW": ["3 Series","5 Series","7 Series","X1","X3","X5","X7","M3","M4","i4","iX"],
    "Mercedes-Benz": ["C-Class","E-Class","S-Class","GLA","GLC","GLE","GLS","G-Class","EQE","EQS"],
    "Audi": ["A3","A4","A6","Q3","Q5","Q7","Q8","e-tron"],
    "Volvo": ["S60","S90","V60","XC40","XC60","XC90","EX30","EX90"],
    "Porsche": ["Macan","Cayenne","Panamera","911","Taycan"],
    "Cadillac": ["Escalade","XT4","XT5","XT6","CT4","CT5","Lyriq"],
    "Buick": ["Encore","Envista","Envision","Enclave"],
    "Chrysler": ["Pacifica","Voyager","300"],
    "Lincoln": ["Navigator","Aviator","Nautilus","Corsair"],
    "Mitsubishi": ["Outlander","Outlander Sport","Eclipse Cross","Mirage"],
    "Infiniti": ["Q50","Q60","QX50","QX60","QX80"],
    "Genesis": ["G70","G80","G90","GV70","GV80"],
    "Jaguar": ["F-Pace","E-Pace","I-Pace","XE","XF"],
    "Land Rover": ["Range Rover","Range Rover Sport","Range Rover Velar","Discovery","Defender"],
    "Mini": ["Cooper","Clubman","Countryman"],
    "Rivian": ["R1T","R1S"],
    "Polestar": ["2","3"]
}

def _canon(s: str) -> str:
    return (s or "").lower().replace(" ", "").replace("-", "").strip()

# Optional CarAPI lookup by year (then we filter locally by make)
_CARAPI_BASE = (os.getenv("CARAPI_BASE") or "https://carapi.app").rstrip("/")
if _CARAPI_BASE.lower().endswith("/api"):
    _CARAPI_BASE = _CARAPI_BASE[:-4]
_HEADERS = {
    "Accept": "application/json",
    **({"Authorization": f"Bearer {(os.getenv('CARAPI_TOKEN') or '').strip()}"} if os.getenv("CARAPI_TOKEN") else {}),
    **({"X-Api-Secret": (os.getenv('CARAPI_SECRET') or '').strip()} if os.getenv("CARAPI_SECRET") else {}),
}
_TIMEOUT = aiohttp.ClientTimeout(total=10)

async def _http_get_json(url: str, params: Dict[str, Any]) -> Any:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.get(url, headers=_HEADERS, params=params) as r:
            return await r.json()

def _rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list): return payload
    if isinstance(payload, dict):
        for k in ("data","bodies","items","results"):
            v = payload.get(k)
            if isinstance(v, list): return v
    return []

def _norm_make(r: Dict[str, Any]) -> Optional[str]:
    for k in ("make","make_name","manufacturer"):
        v = r.get(k)
        if isinstance(v, str) and v.strip(): return v.strip()
    if isinstance(r.get("make"), dict):
        v = r["make"].get("name") or r["make"].get("make") or r["make"].get("manufacturer")
        if isinstance(v, str) and v.strip(): return v.strip()
    return None

def _norm_model(r: Dict[str, Any]) -> Optional[str]:
    for k in ("model","model_name","series"):
        v = r.get(k)
        if isinstance(v, str) and v.strip(): return v.strip()
    if isinstance(r.get("model"), dict):
        v = r["model"].get("name") or r["model"].get("model")
        if isinstance(v, str) and v.strip(): return v.strip()
    return None

@options_router.get("/vehicle-options/makes")
async def get_makes(year: Optional[int] = Query(default=None)):
    # Static list (fast + always available). You can enhance with CarAPI if you want.
    return {"makes": sorted(STATIC_MAKES, key=str.lower)}

@options_router.get("/vehicle-options/models")
async def get_models(make: str = Query(...), year: Optional[int] = Query(default=None)):
    # Try CarAPI by year (limit 200), then filter locally by make
    try:
        url = f"{_CARAPI_BASE}/api/bodies/v2"
        params: Dict[str, Any] = {"direction": "asc", "limit": "200"}
        if year: params["year"] = str(year)
        payload = await _http_get_json(url, params)
        want = _canon(make)
        seen, out = set(), []
        for r in _rows(payload):
            mk = _norm_make(r)
            if _canon(mk or "") != want: continue
            mdl = _norm_model(r)
            if mdl and _canon(mdl) not in seen:
                seen.add(_canon(mdl)); out.append(mdl)
        if out:
            return {"models": sorted(out, key=str.lower)}
    except Exception:
        pass
    # Fallback to static if CarAPI not available
    return {"models": sorted(POPULAR_MODELS_BY_MAKE.get(make, []), key=str.lower)}
