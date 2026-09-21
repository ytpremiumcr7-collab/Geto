"""Alembic revision graph must resolve without touching a database."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_revision_graph_resolves_to_single_head():
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))

    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())

    assert revisions
    assert script.get_current_head() == "0014"
    assert {revision.revision for revision in revisions} >= {
        "0011_alert_deliveries",
        "0012",
        "0013",
        "0014",
    }
