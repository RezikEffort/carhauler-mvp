#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

import requests
import flexpolyline

API_URL = "http://127.0.0.1:8000/plan-route"

def build_payload(args):
    # You can tweak defaults here for quick tests
    return {
        "truck_weight_lbs": args.truck_weight_lbs,
        "trailer_weight_lbs": args.trailer_weight_lbs,
        "trailer_height_ft": args.trailer_height_ft,  # deck height
        "truck_length_ft": args.truck_length_ft,
        "truck_width_ft": args.truck_width_ft,
        "weight_per_axle_lbs": args.weight_per_axle_lbs,
        "shipped_hazardous_goods": args.hazmat,
        "tunnel_category": args.tunnel_category,
        "origin": args.origin,           # "lat,lng"
        "destination": args.destination, # "lat,lng"
        "cars": [
            # Sample cars (edit or add more)
            {"make": "BMW", "model": "325ci", "year": 2006, "weight_lbs": 3300, "height_ft": 4.5},
            {"make": "Audi", "model": "A4",    "year": 2018, "weight_lbs": 3500, "height_ft": 4.6},
        ],
    }

def decode_first_polyline(route_data):
    """
    Extract and decode the first section polyline from HERE v8 response.
    Returns list of (lat, lon) tuples.
    """
    try:
        routes = route_data["routes"]
        sections = routes[0]["sections"]
        # pick the first section that has a polyline
        for sec in sections:
            if "polyline" in sec:
                return flexpolyline.decode(sec["polyline"]), sec
        raise KeyError("No polyline found in sections.")
    except Exception as e:
        raise RuntimeError(f"Could not extract/ decode polyline: {e}")

def to_feature_collection(coords_latlon, section, meta):
    """
    Build a GeoJSON FeatureCollection from decoded coordinates and metadata.
    GeoJSON expects [lon, lat] order for coordinates.
    """
    coords_lonlat = [[lon, lat] for (lat, lon) in coords_latlon]
    features = []

    # LineString for the route
    features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords_lonlat},
        "properties": {
            "summary": section.get("summary", {}),
            "transport": section.get("transport", {}),
            "meta": meta,  # we include totals and vehicle profile here
        },
    })

    # Start / End points (if available)
    dep = section.get("departure", {}).get("place", {}).get("location", {})
    arr = section.get("arrival", {}).get("place", {}).get("location", {})
    if "lat" in dep and "lng" in dep:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [dep["lng"], dep["lat"]]},
            "properties": {"role": "start"}
        })
    if "lat" in arr and "lng" in arr:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [arr["lng"], arr["lat"]]},
            "properties": {"role": "end"}
        })

    return {"type": "FeatureCollection", "features": features}

def main():
    parser = argparse.ArgumentParser(description="Call /plan-route, decode HERE polyline, write GeoJSON.")
    parser.add_argument("--origin", required=True, help='e.g. "52.5308,13.3847"')
    parser.add_argument("--destination", required=True, help='e.g. "52.5264,13.3686"')
    parser.add_argument("--truck_weight_lbs", type=float, default=30000)
    parser.add_argument("--trailer_weight_lbs", type=float, default=15000)
    parser.add_argument("--trailer_height_ft", type=float, default=5.0, help="Deck height, not total trailer height")
    parser.add_argument("--truck_length_ft", type=float, default=40.0)
    parser.add_argument("--truck_width_ft", type=float, default=8.5)
    parser.add_argument("--weight_per_axle_lbs", type=float, default=None)
    parser.add_argument("--hazmat", default=None, help='e.g. "flammable"')
    parser.add_argument("--tunnel_category", default=None, help='e.g. "C"')
    parser.add_argument("--out", default="route.geojson")
    args = parser.parse_args()

    payload = build_payload(args)
    r = requests.post(API_URL, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()

    # Check for HERE errors
    here = data.get("route", {}).get("route_data", {})
    if "status" in here and here.get("status") != 200 and "routes" not in here:
        # Likely an error structure from HERE
        print(json.dumps(here, indent=2))
        raise SystemExit("HERE API returned an error (see above).")

    # Extract/ decode the first polyline
    coords, section = decode_first_polyline(here)

    # Build metadata (useful in GIS properties)
    meta = {
        "warnings": data.get("route", {}).get("warnings", []),
        "sent_vehicle_profile": data.get("route", {}).get("sent_vehicle_profile", {}),
        "totals_for_here": data.get("totals_for_here", {}),
    }

    fc = to_feature_collection(coords, section, meta)

    out_path = Path(args.out).resolve()
    out_path.write_text(json.dumps(fc, indent=2))
    print(f"✅ Wrote GeoJSON to: {out_path}")
    if meta["warnings"]:
        print("⚠️ Warnings:")
        for w in meta["warnings"]:
            print(f" - {w}")

if __name__ == "__main__":
    main()