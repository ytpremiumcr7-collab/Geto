from datetime import datetime

from sgp4.api import Satrec
from sgp4.conveniences import jday


def propagate_tle(
    line1: str,
    line2: str,
    when: datetime,
):

    satellite = Satrec.twoline2rv(
        line1,
        line2,
    )

    jd, fr = jday(
        when.year,
        when.month,
        when.day,
        when.hour,
        when.minute,
        when.second + when.microsecond / 1e6,
    )

    error, position_km, velocity_km_s = satellite.sgp4(jd, fr)

    if error != 0:
        raise RuntimeError(f"SGP4 propagation failed: {error}")

    return {
        "position_km": position_km,
        "velocity_km_s": velocity_km_s,
        "timestamp": when.isoformat(),
    }
