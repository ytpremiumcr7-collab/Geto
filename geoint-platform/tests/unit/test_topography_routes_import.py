"""Smoke: topography router imports and uses get_db (not get_session)."""

from pathlib import Path


def test_routes_use_get_db():
    src = Path(__file__).resolve().parents[2] / "app/api/routes/topography.py"
    text = src.read_text()
    assert "get_session" not in text
    assert "from app.db.session import get_db" in text
    assert "Depends(get_db)" in text


def test_clip_bbox_exists():
    from app.topography.engine import TopographyEngine

    assert hasattr(TopographyEngine, "clip_bbox")


def test_ingest_script_exists():
    script = Path(__file__).resolve().parents[2] / "scripts/ingest_inegi_cog.py"
    assert script.exists()
    text = script.read_text()
    assert "DemAssetCreate" in text
    assert "put_bytes" in text
