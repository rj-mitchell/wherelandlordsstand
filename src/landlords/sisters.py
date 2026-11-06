"""Links where the records meet: from a council's page here, and from each council area's page, to the council's
page on Where Councils Stand, where that site covers the council (docs/DECISIONS.md, 4; the family plan, section 4).

Which councils it covers is kept in ``data_static/councils_covered.csv``, made from Where Councils Stand's own list
of councils (`landlords sister-councils`): a council is covered once its meetings have been loaded there. Both sites
use the ONS (GSS) code for a council, so the link is ``https://wherecouncilsstand.com/councils/<code>``.
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache

from landlords.config import STATIC_DIR, Settings

COVERED = STATIC_DIR / "councils_covered.csv"


@lru_cache(maxsize=1)
def councils_covered() -> dict[str, str]:
    """The councils Where Councils Stand covers: code -> name."""
    if not COVERED.exists():
        return {}
    with open(COVERED, newline="", encoding="utf-8") as fh:
        return {r["gss"]: r["name"] for r in csv.DictReader(fh)}


def council_url(settings: Settings, gss: str) -> str:
    """The council's page on Where Councils Stand, if that site covers it; otherwise ""."""
    template = settings.section("sister_sites").get("where_councils_stand")
    if not gss or not template or gss not in councils_covered():
        return ""
    return template.format(gss=gss)


def refresh(settings: Settings) -> dict[str, int]:
    """Read Where Councils Stand's list of councils (one request) and write the ones it covers to
    data_static/councils_covered.csv. Review the change before committing it, as with the name register."""
    import httpx

    url = settings.section("sister_sites")["where_councils_stand_list"]
    response = httpx.get(url, headers={"User-Agent": settings.fetch["user_agent"]},
                         timeout=settings.fetch.get("timeout_seconds", 60), follow_redirects=True)
    response.raise_for_status()
    councils = json.loads(response.text)["councils"]
    covered = sorted((c["gss"], c["name"]) for c in councils if c.get("loaded"))
    if not covered:
        raise RuntimeError(f"{url} lists no councils with their meetings loaded: not changing {COVERED.name}")
    before = set(councils_covered())
    with open(COVERED, "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh, lineterminator="\n")
        out.writerow(["gss", "name"])
        out.writerows(covered)
    councils_covered.cache_clear()
    now = set(councils_covered())
    return {"listed": len(councils), "covered": len(now), "added": len(now - before), "removed": len(before - now)}
