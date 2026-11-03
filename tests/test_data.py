"""Checks on the real data. Skipped unless the files have been fetched and loaded (`landlords fetch`, `load`)."""

import pytest

from landlords import checks
from landlords.config import load_settings

settings = load_settings()
pytestmark = pytest.mark.skipif(not (settings.staging_dir / "tsm.parquet").exists(),
                                reason="data not fetched and loaded")


@pytest.fixture(scope="module")
def report():
    return {c["name"]: c for c in checks.run(settings)["checks"]}


def test_reconciles_to_published_figures(report):
    for name, c in report.items():
        if "2024/25" in name or "2025-26" in name or "2025/26" in name:
            assert c["ok"], f"{name}: {c['detail']}"


def test_register_is_sound(report):
    for name in ("aliases point to known landlords and kinds", "no alias points to two landlords",
                 "slugs are unique", "no published slug has disappeared",
                 "every profiled landlord has a name, slug and type"):
        assert report[name]["ok"], report[name]["detail"]


def test_every_row_with_a_code_has_a_landlord(report):
    for table in ("tsm", "tsm_coverage", "grades", "stock_area", "providers"):
        c = report[f"every {table} row has a landlord"]
        assert c["ok"], c["detail"]


SITE = settings.data_dir / "site"


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="pages not built (`landlords build`)")
def test_pages_are_small_self_contained_and_carry_the_warning():
    import re

    from landlords.config import load_toml

    refusal = load_toml("wording.toml")["card"]["refusal"].replace("'", "&#x27;")
    pages = list((SITE / "landlords").glob("*/index.html"))
    assert len(pages) >= 360
    for path in pages:
        text = path.read_text()
        assert len(text.encode()) < 100 * 1024, path
        assert refusal in text, path
        assert "<script" not in text, path                       # readable without JavaScript, nothing third-party
        assert not re.search(r'<link[^>]+href="https?:', text), path
        assert 'id="sources"' in text, path                      # every page lists its sources
        for ref in re.findall(r'href="#source-(\d+)"', text):    # every figure's link goes to a listed file
            assert f'id="source-{ref}"' in text, (path, ref)
