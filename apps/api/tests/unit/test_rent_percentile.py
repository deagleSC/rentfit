from app.services.rent_suggestion import percentile


def test_percentile_matches_numpy_linear() -> None:
    v = [20000, 25000, 30000, 35000, 40000]
    assert (percentile(v, 0.25), percentile(v, 0.5), percentile(v, 0.75)) == (25000, 30000, 35000)
    assert percentile([30000], 0.75) == 30000
    assert percentile([20000, 30000], 0.5) == 25000
