
"""
NHTSA vPIC is useful for make/model validation but generally does NOT include
reliable dimensions (height/length) or curb weight for all vehicles.

For the MVP, rely on manual inputs from drivers and build your own cache.
This module includes a minimal helper to search makes/models so you can
autocomplete, but expect missing specs and fall back to manual entry.
"""
import requests

BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"

def search_models(make: str, year: int):
    url = f"{BASE_URL}/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json().get("Results", [])

def makes():
    url = f"{BASE_URL}/getallmakes?format=json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json().get("Results", [])
