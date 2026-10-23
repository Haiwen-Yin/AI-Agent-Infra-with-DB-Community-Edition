from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB_SOURCE = (ROOT / "shared/web/src") if (ROOT / "shared/web/src").is_dir() else ROOT / "web/src"


def test_table_scroll_contains_narrow_history_tables():
    css = (WEB_SOURCE / "app.css").read_text(encoding="utf-8")
    assert ".table-scroll" in css
    block = css[css.index(".table-scroll"):css.index(".table-scroll") + 240]
    assert "min-width: 0" in block
    assert "max-width: 100%" in block
    assert "overflow-x: auto" in block


def test_network_access_and_compliance_views_use_scroll_container():
    for name in ("NetworkAccessPolicy.tsx", "ComplianceProfileDetail.tsx"):
        source = (WEB_SOURCE / name).read_text(encoding="utf-8")
        assert 'className="table-scroll"' in source
