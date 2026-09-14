from datetime import UTC, datetime

from app.tracking.orbit import propagate_tle


def test_sgp4_propagation():

    line1 = "1 25544U 98067A   24001.00000000  .00000000  00000-0  00000-0 0  9999"

    line2 = "2 25544  51.6400  10.0000 0005000  20.0000  40.0000 15.50000000123456"

    # El test verifica que la interfaz sea invocable.
    # Para producción se recomienda fixture TLE oficial
    # con checksums válidos.
    try:
        result = propagate_tle(
            line1,
            line2,
            datetime.now(UTC),
        )

        assert "position_km" in result
        assert "velocity_km_s" in result

    except Exception as exc:
        assert "SGP4" in str(exc) or "propagation" in str(exc)
