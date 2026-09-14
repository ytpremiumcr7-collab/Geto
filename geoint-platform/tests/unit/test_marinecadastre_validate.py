from pathlib import Path

import pytest

from scripts.ingest_marinecadastre import validate_csv


def test_validate_ok(tmp_path: Path):
    f = tmp_path / "ok.csv"
    f.write_text("MMSI,LAT,LON,SOG\n3661,29.7,-95.3,10\n")
    report = validate_csv(f)
    assert report["valid"] == 1
    assert report["invalid"] == 0


def test_validate_missing_columns(tmp_path: Path):
    f = tmp_path / "bad.csv"
    f.write_text("MMSI,SOG\n1,3\n")
    with pytest.raises(ValueError, match="ausentes"):
        validate_csv(f)
