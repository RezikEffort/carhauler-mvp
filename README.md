
# Car Hauler Backend (MVP)

FastAPI backend for a car hauler **load calculator** with optional **route warnings** (HERE Routing).

## 🧱 Project Structure
```
carhauler_backend/
  ├── main.py
  ├── services/
  │     ├── calculator.py
  │     ├── nhtsa.py
  │     └── routing.py
  ├── tests/
  │     └── test_calculator.py
  ├── requirements.txt
  ├── .env.example
  └── README.md
```

## ✅ Step-by-Step Setup

1) **Create and activate a virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2) **Install dependencies**
```bash
pip install -r requirements.txt
```

3) **Environment variables**
- Copy `.env.example` to `.env` and set `HERE_API_KEY` (optional for /plan-route).
- You can override DOT thresholds with `DOT_MAX_HEIGHT_FEET` and `DOT_MAX_WEIGHT_LBS`.

4) **Run the server**
```bash
uvicorn main:app --reload
```

5) **Try the calculator endpoint**
```bash
curl -X POST "http://127.0.0.1:8000/calculate"   -H "Content-Type: application/json"   -d '{
    "truck_weight_lbs": 18000,
    "trailer_weight_lbs": 15000,
    "trailer_height_ft": 5.0,
    "cars": [
      {"make":"Honda","model":"Civic","year":2020,"weight_lbs":2900,"height_ft":4.8},
      {"make":"Ford","model":"F-150","year":2021,"weight_lbs":4500,"height_ft":6.2}
    ]
  }'
```

6) **Try the combined route plan** (requires HERE key)
```bash
curl -X POST "http://127.0.0.1:8000/plan-route"   -H "Content-Type: application/json"   -d '{
    "origin": "40.7128,-74.0060",
    "destination": "39.9526,-75.1652",
    "truck_weight_lbs": 18000,
    "trailer_weight_lbs": 15000,
    "trailer_height_ft": 5.0,
    "cars": [
      {"weight_lbs": 2900, "height_ft": 4.8},
      {"weight_lbs": 4500, "height_ft": 6.2}
    ]
  }'
```

7) **Run tests**
```bash
pytest -q
```

## 📌 Notes on Car Data
- NHTSA vPIC is great for *makes/models*, but it often lacks dimensions and curb weight.
- For MVP, use **manual inputs** and save common vehicles to your own DB.
- Later, consider licensing complete spec data from a commercial provider or building a curated dataset.

## 🛡️ Warnings Logic
- The calculator checks **height** (default 13.5 ft) and **gross weight** (default 80,000 lbs).
- You can add state-specific thresholds later by passing the state and overriding the env values per request.

## 🚀 Deployment Tips
- Add a `Dockerfile`, push to a registry, deploy to Render/Fly/Railway.
- Put your `.env` variables in the platform's secret manager.

---

**You now have a working backend scaffold**: 
- `/calculate` → totals + warnings
- `/plan-route` → totals + HERE route summary + best-effort notices parsing
