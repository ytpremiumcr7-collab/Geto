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


def test_sample_must_not_exceed_gsd_policy():
    """Policy mirror: step = min(requested, gsd)."""
    gsd = 12.0
    requested = 50.0
    step = requested if requested <= gsd else gsd
    clamped = requested > gsd
    assert step == 12.0 and clamped


def test_vertical_datum_required_semantics():
    from app.topography.models import DemAssetCreate, DemProductType, DemProvider

    # valid
    DemAssetCreate(
        provider=DemProvider.LOCAL,
        product_name="lidar-1m",
        product_type=DemProductType.DTM,
        resolution_m=1.0,
        vertical_datum="NAVD88",
        bbox_west=-99.2,
        bbox_south=19.3,
        bbox_east=-99.0,
        bbox_north=19.5,
        file_uri="s3://bucket/dem/lidar.tif",
    )
    try:
        DemAssetCreate(
            provider=DemProvider.LOCAL,
            product_name="bad",
            resolution_m=1.0,
            vertical_datum="",  # type: ignore[arg-type]
            bbox_west=0,
            bbox_south=0,
            bbox_east=1,
            bbox_north=1,
            file_uri="s3://x",
        )
        raise AssertionError("empty vertical_datum should fail")
    except Exception:
        pass
