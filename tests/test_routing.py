from app_routing import _haversine, _nearest_neighbor


def test_haversine_distance_is_reasonable():
    distance = _haversine((35.6892, 51.3890), (35.7219, 51.3347))
    assert 5_000 < distance < 7_000


def test_nearest_neighbor_uses_matrix_costs():
    matrix = [
        [0, 20, 5, 30],
        [20, 0, 8, 4],
        [5, 8, 0, 10],
        [30, 4, 10, 0],
    ]
    assert _nearest_neighbor(matrix) == [2, 1, 3]
