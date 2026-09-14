from app.topography.quality import build_los_quality, build_viewshed_quality


def test_los_with_refraction_is_operational_support():
    q = build_los_quality(
        dem_resolution_m=10.0,
        sample_distance_m=5.0,
        refraction_k=1.333,
        curvature_applied=True,
        vertical_datum="EGM96",
    )
    assert q.decision_grade == "operational_support"
    assert q.confidence_0_1 >= 0.6
    assert "NOT certified" in q.certification
    assert q.horizontal_uncertainty_m > 0


def test_los_without_refraction_exploratory():
    q = build_los_quality(
        dem_resolution_m=30.0,
        sample_distance_m=10.0,
        refraction_k=None,
        curvature_applied=False,
    )
    assert q.decision_grade == "exploratory"


def test_viewshed_quality_dict():
    d = build_viewshed_quality(
        dem_resolution_m=12.0, max_distance_m=5000.0, curvature_coeff=0.85714
    ).as_dict()
    assert "decision_grade" in d
    assert d["curvature_applied"] is True
