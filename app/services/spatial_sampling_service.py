from typing import List, Tuple


def sample_bbox_points(bbox, n: int = 5) -> List[Tuple[float, float]]:
    """
    bbox = [min_lon, min_lat, max_lon, max_lat]
    return list of (lat, lon)
    """
    min_lon, min_lat, max_lon, max_lat = bbox

    lats = [min_lat + (max_lat - min_lat) * i / (n - 1) for i in range(n)]
    lons = [min_lon + (max_lon - min_lon) * i / (n - 1) for i in range(n)]

    points = []

    for lat in lats:
        for lon in lons:
            points.append((lat, lon))

    return points
