from landlords.score import band, merge_groups, method_key, percentiles, size_band


def test_percentiles_run_best_high_whichever_way_the_measure_runs():
    up = percentiles({"a": 50.0, "b": 60.0, "c": 70.0, "d": 80.0})
    assert up["d"] > up["c"] > up["b"] > up["a"]
    assert up == {"a": 12.5, "b": 37.5, "c": 62.5, "d": 87.5}
    down = percentiles({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}, higher_is_better=False)  # e.g. non-decent homes
    assert down["a"] == 87.5 and down["d"] == 12.5


def test_ties_share_a_percentile():
    p = percentiles({"a": 70.0, "b": 70.0, "c": 50.0})
    assert p["a"] == p["b"] == 100 * (1 + 0.5 + 0.5) / 3


def test_bands_are_quarters():
    edges = [25, 50, 75]
    assert [band(x, edges) for x in (0, 24.9, 25, 49.9, 50, 74.9, 75, 100)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert band(None, edges) is None


def test_size_bands():
    edges = [1000, 10000, 50000]
    assert [size_band(h, edges) for h in (900, 1000, 9999, 10000, 49999, 50000, 120000)] == [0, 0, 0, 1, 1, 2, 2]


def test_small_groups_merge_down_and_small_types_join_another():
    members = {f"c{i}": ("council", 0) for i in range(20)} | {f"C{i}": ("council", 1) for i in range(16)} \
        | {"big": ("council", 2)} | {f"h{i}": ("housing association", 0) for i in range(30)} \
        | {f"f{i}": ("for-profit", 0) for i in range(4)}
    g = merge_groups(members, ["council", "housing association", "for-profit"], 3, 15,
                     {"for-profit": "housing association"})
    assert g["big"] == ("council", (1, 2))          # one 50,000+ council joins 10,000-49,999
    assert g["c0"] == ("council", (0,))
    assert g["f0"] == g["h0"] == ("housing association", (0, 1, 2))


def test_survey_methods_are_named_the_same_way_every_year():
    assert method_key("Face to Face") == method_key("FacetoFace") == "face to face"
    assert method_key("No predominant method") == "mixed"
    assert method_key("Telephone") == "telephone"
