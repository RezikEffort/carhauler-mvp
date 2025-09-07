# tests/test_placement.py
from services.placement_heuristic import compute_placement

def demo_cars():
    return [
        {"id":"A","length_ft":15.8,"width_ft":6.2,"height_ft":5.3,"weight_lbs":4200,"drop_order":1},
        {"id":"B","length_ft":14.5,"width_ft":6.0,"height_ft":5.1,"weight_lbs":3600,"drop_order":2},
        {"id":"C","length_ft":16.2,"width_ft":6.1,"height_ft":5.8,"weight_lbs":4400,"drop_order":1},
        {"id":"D","length_ft":14.0,"width_ft":6.0,"height_ft":5.0,"weight_lbs":3300,"drop_order":3},
        {"id":"E","length_ft":15.0,"width_ft":6.1,"height_ft":5.2,"weight_lbs":3900,"drop_order":2},
        {"id":"F","length_ft":14.8,"width_ft":6.0,"height_ft":5.2,"weight_lbs":3700,"drop_order":3},
        {"id":"G","length_ft":14.6,"width_ft":6.0,"height_ft":5.0,"weight_lbs":3400,"drop_order":4},
        {"id":"H","length_ft":15.2,"width_ft":6.1,"height_ft":5.4,"weight_lbs":3950,"drop_order":4},
        {"id":"I","length_ft":14.9,"width_ft":6.1,"height_ft":5.1,"weight_lbs":3650,"drop_order":5},
    ]

def test_compute_placement_returns_plan():
    res = compute_placement(demo_cars(), max_iters=200)
    assert "assignments" in res
    assert len(res["assignments"]) == 9
    assert res["scores"]["fitness"] > -1e9
    assert res["scores"]["unload_moves"] >= 0
