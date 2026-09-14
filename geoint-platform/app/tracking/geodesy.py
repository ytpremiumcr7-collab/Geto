from pyproj import Geod

WGS84 = Geod(ellps="WGS84")


def distance_m(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    _, _, distance = WGS84.inv(
        lon1,
        lat1,
        lon2,
        lat2,
    )

    return distance
