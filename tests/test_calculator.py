
from services.calculator import calculate_load

def test_calculate_under_limits():
    result = calculate_load(
        truck_weight_lbs=18000,
        trailer_weight_lbs=15000,
        trailer_height_ft=5.0,
        cars=[
            {"make": "Honda", "model": "Civic", "year": 2020, "weight_lbs": 2900, "height_ft": 4.8},
            {"make": "Ford", "model": "F-150", "year": 2021, "weight_lbs": 4500, "height_ft": 6.2},
        ],
    )
    assert result["total_weight_lbs"] == 18000 + 15000 + 2900 + 4500
    assert result["total_height_ft"] == 5.0 + 6.2
    assert result["warnings"] == []

def test_calculate_over_limits():
    result = calculate_load(
        truck_weight_lbs=30000,
        trailer_weight_lbs=20000,
        trailer_height_ft=8.0,
        cars=[{"make": "Ram", "model": "2500", "year": 2022, "weight_lbs": 40000, "height_ft": 6.0}],
    )
    assert any("exceeds DOT limit" in w for w in result["warnings"])
