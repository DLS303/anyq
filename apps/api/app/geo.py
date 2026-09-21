from math import asin, cos, radians, sin, sqrt


def centroid(polygon: list[list[float]]) -> tuple[float, float] | None:
    pts = polygon[:-1] if len(polygon) > 1 and polygon[0] == polygon[-1] else polygon
    if not pts:
        return None
    lat = sum(p[0] for p in pts) / len(pts)
    lng = sum(p[1] for p in pts) / len(pts)
    return lat, lng


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(h))
