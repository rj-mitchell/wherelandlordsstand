"""Hiding a landlord's page while a concern about it is decided (the charity's impartiality policy, 7.3;
docs/DECISIONS.md, 17; src/landlords/hiding.py): `landlords hide landlords/<slug>/ --note "…"`, and `unhide`.

The pages here are made by the site's own page builders from three made-up landlords, so each place a landlord
appears has the shape the real build gives it. tests/test_data.py does the same on the real pages."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from landlords import hiding, publish, statements
from landlords.api import create_app
from landlords.cli import app
from landlords.config import load_toml
from landlords.replies import PARTS, open_replies
from landlords.site import page
from landlords.site_pages import (
    _csv,
    area_html,
    areas_index_html,
    downloads_html,
    index_html,
    names_json,
)
from landlords.statements import slot

W = load_toml("wording.toml")
HIDDEN = "This page is hidden while a concern about it is decided."
NOTE = "We are checking how we matched one of its names."
LANDLORDS = [
    {"id": "L1", "slug": "example-housing", "name": "Example Housing", "legal_name": "Example Housing Limited",
     "type": "ha", "also_known_as": ["Example"], "grade": {"grade": "C2"}, "bands": {}},
    {"id": "LA2", "slug": "example-council", "name": "Example Council", "legal_name": "Example City Council",
     "type": "council", "also_known_as": [], "grade": {"grade": "C3"}, "bands": {}},
    {"id": "L3", "slug": "other-homes", "name": "Other Homes", "legal_name": "Other Homes Ltd", "type": "ha",
     "also_known_as": [], "grade": {}, "bands": {}},
]
BY_SLUG = {p["slug"]: p for p in LANDLORDS}
AREAS = {"leeds": ("Leeds", [("example-council", 5000, "council total"), ("example-housing", 1200, ""),
                            ("other-homes", 30, "")]),
         "york": ("York", [("example-housing", 800, ""), ("other-homes", 400, "")]),
         "scilly": ("Isles of Scilly", [("example-council", 100, "council total")])}


def landlord_page(p: dict) -> str:
    card = "".join(f'<section><h3 id="{part}">{part}</h3><p>Grade {p["grade"].get("grade", "none")}.</p>{slot(part)}'
                   "</section>" for part in PARTS)
    body = f'<h1>{p["name"]}</h1><section class="card">{card}</section>{slot("page")}<h2>Figures</h2><p>87.5%</p>'
    return page(f"{p['name']} – {W['site']['name']}", body, W, depth=2, path=f"landlords/{p['slug']}/",
                description=f"{p['name']}: grade, tenant satisfaction and complaints.")


def build(root: Path) -> Path:
    """A set of pages with every place a landlord appears, each made as the real build makes it."""
    for p in LANDLORDS:
        (root / "landlords" / p["slug"]).mkdir(parents=True)
        (root / "landlords" / p["slug"] / "index.html").write_text(landlord_page(p))
    (root / "index.html").write_text(index_html(LANDLORDS, W))
    (root / "names.json").write_text(json.dumps(
        names_json(LANDLORDS, {"L9": {"status": "active", "legal_name": "Tiny Homes"}}, [], W), separators=(",", ":")))
    areas = {}
    for area_slug, (name, rows) in AREAS.items():
        areas[area_slug] = {"name": name, "slug": area_slug, "sources": set(),
                            "landlords": [(BY_SLUG[s], homes, basis) for s, homes, basis in rows]}
        (root / "areas" / area_slug).mkdir(parents=True)
        (root / "areas" / area_slug / "index.html").write_text(area_html(areas[area_slug], W, {}))
    (root / "areas" / "index.html").write_text(areas_index_html(areas, W))
    (root / "data" / "landlords").mkdir(parents=True)
    for p in LANDLORDS:
        (root / "data" / "landlords" / f"{p['slug']}.json").write_text(json.dumps({"name": p["name"], "slug": p["slug"]}))
    files = [
        ("landlords.csv", [{"landlord_id": p["id"], "name": p["name"], "page": f"landlords/{p['slug']}/"}
                           for p in LANDLORDS]),
        ("bands.csv", [{"landlord_id": p["id"], "item": i, "made_by": "Where Landlords Stand, from the figures"}
                       for p in LANDLORDS for i in ("overall", "repairs")]),
        ("tenant-satisfaction-measures.csv", [{"landlord_id": p["id"], "measure": "TP01", "value": 71.5,
                                               "source_title": 'A title, with a comma and a "quote"\nand a new line'}
                                              for p in LANDLORDS]),
        ("ombudsman.csv", [{"landlord_id": "LA2", "profile_id": "LA2", "measure": "findings", "value": 12},
                           {"landlord_id": "L7", "profile_id": "LA2", "measure": "findings", "value": 3},
                           {"landlord_id": "L8", "profile_id": "", "measure": "findings", "value": 1},
                           {"landlord_id": "L1", "profile_id": "L1", "measure": "findings", "value": 9}]),
        ("regulatory-judgements.csv", [{"landlord_id": p["id"], "grade": p["grade"].get("grade", "")}
                                       for p in LANDLORDS]),
        ("homes-by-area.csv", [{"landlord_id": BY_SLUG[s]["id"], "area_name": name, "rented_homes": homes}
                               for name, rows in AREAS.values() for s, homes, _ in rows]),
    ]
    written = []
    for name, rows in files:
        text = _csv(rows, list(rows[0]))
        (root / "data" / name).write_text(text)
        written.append((name, text, len(rows)))
    (root / "data" / "index.html").write_text(downloads_html(written, W))
    pages = sorted(p.relative_to(root).as_posix() for p in root.rglob("index.html"))
    (root / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>https://wherelandlordsstand.com/{p.removesuffix('index.html')}</loc></url>" for p in pages)
        + "</urlset>\n")
    for folder in ("corrections", "named"):
        (root / folder).mkdir()
        (root / folder / "thanks.html").write_text("thanks")
    return root


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def run(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.output


def table(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


@pytest.fixture
def site(settings):
    return build(settings.data_dir / "site")


def test_a_hidden_landlord_is_left_out_of_every_list_and_its_page_shows_the_note(settings, site):
    before = tree(site)
    assert run("hide", "landlords/example-council/", "--note", NOTE) == (0, json.dumps({
        "hidden": "landlords/example-council/", "note": NOTE, "pages_changed": 15}) + "\n")
    now = {name: text.decode() for name, text in tree(site).items()}

    # its own page: its name, the sentence and the note, in place of its figures; nothing else of the page changes
    own = now["landlords/example-council/index.html"]
    assert f"<main id=\"main\" class=\"wrap\"><h1>Example Council</h1><p>{HIDDEN}</p><p>{NOTE}</p></main>" in own
    assert "Grade C3" not in own and "87.5%" not in own and "<!--statements:" not in own
    assert own.count(HIDDEN) == 3 and "grade, tenant satisfaction and complaints" not in own   # nor its description
    was = before["landlords/example-council/index.html"].decode()
    assert own.split("<main")[0].replace(HIDDEN, "") == re.sub(
        r'(content=")Example Council: grade, tenant satisfaction and complaints\.', r"\1", was.split("<main")[0])
    assert own.split("</main>")[1] == was.split("</main>")[1]

    # the list of all landlords, and its count
    assert "landlords/example-council/" not in now["index.html"] and "Example Council" not in now["index.html"]
    assert "3 social landlords" in before["index.html"].decode() and "2 social landlords" in now["index.html"]
    assert 'landlords/example-housing/index.html">Example Housing</a>' in now["index.html"]
    # search, and the compare page's box and data
    names = json.loads(now["names.json"])
    assert [e.get("s") for e in names] == ["example-housing", "other-homes", None]
    assert "Council" not in now["names.json"] and "data/landlords/example-council.json" not in now
    assert "data/landlords/example-housing.json" in now
    # each council area's table, its count, and the note under it that explained the council's star
    leeds = now["areas/leeds/index.html"]
    assert "example-council" not in leeds and "Example Council" not in leeds and "5,000" not in leeds
    assert leeds.count("2 landlords we cover own homes in this area.") == 3 and "3 landlords" not in leeds
    assert "A council&#x27;s homes are counted in its own area." not in leeds
    assert "A council&#x27;s homes are counted in its own area." in before["areas/leeds/index.html"].decode()
    assert now["areas/york/index.html"] == before["areas/york/index.html"].decode()       # it has no homes there
    assert re.findall(r'<a href="(\w+)/index.html">[^<]*</a> <span class="hint">\((\d+)\)', now["areas/index.html"]) \
        == [("scilly", "0"), ("leeds", "2"), ("york", "2")]
    # an area where it was the only landlord keeps its page, with nobody in its table
    assert "example-council" not in now["areas/scilly/index.html"]
    assert "0 landlords we cover own homes in this area." in now["areas/scilly/index.html"]
    # the sitemap
    assert "landlords/example-council/" not in now["sitemap.xml"] and "landlords/example-housing/" in now["sitemap.xml"]
    # the downloads: its rows, and those of its companies, go from each file; the page says how many are left
    for name in hiding.DOWNLOADS:
        assert "LA2" not in now[f"data/{name}"], name
        assert {r["landlord_id"] for r in table(now[f"data/{name}"])} >= {"L1"}, name
    assert [r["landlord_id"] for r in table(now["data/ombudsman.csv"])] == ["L8", "L1"]
    assert table(now["data/tenant-satisfaction-measures.csv"])[0]["source_title"] == (
        'A title, with a comma and a "quote"\nand a new line')
    listing = now["data/index.html"]
    assert 'landlords.csv</a> <span class="hint">(2 rows, 1 KB)' in listing
    assert 'ombudsman.csv</a> <span class="hint">(2 rows, 1 KB)' in listing
    assert 'homes-by-area.csv</a> <span class="hint">(4 rows, 1 KB)' in listing
    # nowhere else: no other file names it, by its address or by its name
    named = sorted(name for name, text in now.items() if "example-council" in text or "Example Council" in text)
    assert named == ["landlords/example-council/index.html"]
    # the other landlords' own pages are untouched
    for slug in ("example-housing", "other-homes"):
        assert now[f"landlords/{slug}/index.html"] == before[f"landlords/{slug}/index.html"].decode()


def test_showing_it_again_puts_back_exactly_what_was_there(settings, site):
    before = tree(site)
    assert run("hide", "landlords/example-council/", "--note", NOTE)[0] == 0
    kept = settings.data_dir / "hidden-originals" / "site"
    assert (kept / "landlords" / "example-council" / "index.html").read_bytes() == before[
        "landlords/example-council/index.html"]                    # as built, outside the pages that are served
    assert run("hidden") == (0, json.dumps({"item": "landlords/example-council/", "note": NOTE,
                                            "at": open_replies(settings).all_hidden()[0]["at"]}) + "\n")
    assert json.loads(run("waiting")[1])["hidden"] == 1
    assert run("unhide", "landlords/example-council/") == (0, json.dumps({
        "shown": "landlords/example-council/", "pages_changed": 15}) + "\n")
    assert tree(site) == before
    assert not (settings.data_dir / "hidden-originals").exists()
    assert run("hidden") == (0, "") and run("unhide", "landlords/example-council/")[0] == 1


def test_two_landlords_are_hidden_and_shown_again_in_any_order(settings, site):
    before = tree(site)
    run("hide", "landlords/example-housing/", "--note", "A")
    only_housing = tree(site)
    run("unhide", "landlords/example-housing/")
    run("hide", "landlords/example-council/", "--note", "B")
    only_council = tree(site)
    run("hide", "landlords/example-housing/", "--note", "A")
    both = tree(site)
    assert "1 social landlords" in both["index.html"].decode()
    assert "1 landlords we cover own homes in this area." in both["areas/leeds/index.html"].decode()
    assert both["areas/leeds/index.html"].decode().count('<tr role="row"><td role="cell"><a href=') == 1
    assert json.loads(both["names.json"])[0]["s"] == "other-homes"
    run("unhide", "landlords/example-council/")                     # the one hidden first is shown first
    assert tree(site) == only_housing
    run("hide", "landlords/example-council/", "--note", "B")
    assert tree(site) == both
    run("unhide", "landlords/example-housing/")
    assert tree(site) == only_council
    run("unhide", "landlords/example-council/")
    assert tree(site) == before


def test_only_a_landlords_page_can_be_hidden_whatever_way_its_address_is_typed(settings, site):
    for typed, says in (
            ("areas/leeds/", "only a landlord's page can be hidden on this site: give its address, which has "
                             "/landlords/ in it"),
            ("compare/", "only a landlord's page can be hidden on this site: give its address, which has "
                         "/landlords/ in it"),
            ("https://example.org/landlords/example-council/", "only a landlord's page can be hidden on this site: "
                                                               "give its address, which has /landlords/ in it"),
            ("landlords/nobody-at-all/", "no landlord's page landlords/nobody-at-all/ on the site")):
        assert run("hide", typed, "--note", NOTE) == (1, f"Not done: {says}\n"), typed
    assert run("hidden") == (0, "") and run("hide", "landlords/example-council/")[0] == 2      # a note must be given
    typed = "https://www.wherelandlordsstand.com/landlords/example-council/index.html#bands"
    assert json.loads(run("hide", typed, "--note", NOTE)[1])["hidden"] == "landlords/example-council/"
    assert run("hide", "landlords/example-council", "--note", "again") == (
        1, "Not done: landlords/example-council/ is already hidden: unhide it first to change the note\n")
    assert json.loads(run("unhide", "/landlords/example-council/index.html")[1])["shown"] == "landlords/example-council/"


def test_statements_beside_a_hidden_landlord_are_hidden_with_it_and_none_is_taken(settings, site):
    client = TestClient(create_app(settings))
    form = {"name": "Jane Example", "role": "Head of housing, Example Council", "link": "",
            "text": "Our survey was carried out after a big change.", "email": "jane@example.gov.uk"}

    def send(page: str, **more) -> int:
        r = client.post("/api/statements", json={**form, "page": page, **more})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    replies = open_replies(settings)
    own = send("landlords/example-council/#grade", text="Words beside the council's own grade.")
    area = send("areas/leeds/", text="Words about Leeds, from the council.")
    other = send("landlords/example-housing/", text="Words from another landlord.", role="Director, Example Housing")
    waiting = send("areas/york/", text="Words waiting to be published for the council.")
    replies.publish(own, checked="letter")
    replies.publish(area, checked="letter", about="example-council")
    statements.refresh(settings)
    shown = tree(site)
    assert b"Words beside the council" in shown["landlords/example-council/index.html"]
    assert b"Words about Leeds" in shown["areas/leeds/index.html"]

    assert run("hide", "landlords/example-council/", "--note", NOTE)[0] == 0
    now = {name: text.decode() for name, text in tree(site).items()}
    assert not [name for name, text in now.items() if "Words beside the council" in text or "Words about Leeds" in text]
    # none is taken for it, and none is published for it, while it is hidden
    r = client.post("/api/statements", json={**form, "page": "landlords/example-council/"})
    assert (r.status_code, r.json()["error"]) == (400, "We couldn't find that page on the site. Please copy its "
                                                       "address from your browser.")
    assert run("statements", "publish", str(waiting), "--checked", "letter", "--landlord", "example-council") == (
        1, f"Not done: statement {waiting} is beside areas/york/, which cannot be shown: landlords/example-council/ "
           "is hidden while a concern about it is decided\n")
    # a statement published meanwhile for someone else goes onto its page as usual, and one withdrawn stays down
    assert run("statements", "publish", str(other), "--checked", "letter")[0] == 0
    assert "Words from another landlord" in (site / "landlords" / "example-housing" / "index.html").read_text()
    assert HIDDEN in (site / "landlords" / "example-council" / "index.html").read_text()
    assert run("statements", "withdraw", str(area), "--reason", "withdrawn by the author")[0] == 0

    assert run("unhide", "landlords/example-council/")[0] == 0
    back = {name: text.decode() for name, text in tree(site).items()}
    assert "Words beside the council" in back["landlords/example-council/index.html"]       # back with its page
    assert not [name for name, text in back.items() if "Words about Leeds" in text]         # withdrawn meanwhile
    assert "Words from another landlord" in back["landlords/example-housing/index.html"]
    assert "Grade C3" in back["landlords/example-council/index.html"]
    assert run("statements", "publish", str(waiting), "--checked", "letter", "--landlord", "example-council")[0] == 0
    assert "Words waiting to be published" in (site / "areas" / "york" / "index.html").read_text()


def test_the_site_serves_the_note_and_not_the_figures(settings, site):
    client = TestClient(create_app(settings))
    assert "Grade C3" in client.get("/landlords/example-council/").text
    assert client.get("/data/landlords/example-council.json").status_code == 200
    run("hide", "landlords/example-council/", "--note", NOTE)
    served = client.get("/landlords/example-council/")
    assert served.status_code == 200 and HIDDEN in served.text and NOTE in served.text and "Grade C3" not in served.text
    assert client.get("/data/landlords/example-council.json").status_code == 404        # the compare page finds nothing
    assert "example-council" not in client.get("/names.json").text
    assert "LA2" not in client.get("/data/landlords.csv").text
    # what was kept of the pages as built is not served
    assert client.get("/hidden-originals/site/landlords/example-council/index.html").status_code == 404


def test_every_set_of_pages_that_can_be_live_is_written_and_a_cleared_build_takes_its_copies_with_it(settings, site):
    for name in ("20261110-000000", "20261111-000000"):            # the live build, and one waiting for approval
        build(publish.builds_dir(settings) / name)
        (publish.builds_dir(settings) / name / "build-info.json").write_text(json.dumps({"build": name,
                                                                                         "checks_failed": []}))
    publish.publish(settings, "20261110-000000")
    assert json.loads(run("hide", "landlords/example-council/", "--note", NOTE)[1])["pages_changed"] == 45
    for folder in (settings.data_dir / "live", publish.builds_dir(settings) / "20261111-000000", site):
        assert HIDDEN in (folder / "landlords" / "example-council" / "index.html").read_text()
    publish.publish(settings, "20261111-000000")                    # approving the waiting pages keeps it hidden
    assert HIDDEN in (settings.data_dir / "live" / "landlords" / "example-council" / "index.html").read_text()
    publish.rollback(settings)                                       # and so does an undo
    assert HIDDEN in (settings.data_dir / "live" / "landlords" / "example-council" / "index.html").read_text()
    kept = settings.data_dir / "hidden-originals"
    assert sorted(p.name for p in kept.iterdir()) == ["builds__20261110-000000", "builds__20261111-000000", "site"]
    publish._prune(settings, 1, {"20261111-000000"})                 # an old build is cleared away
    assert sorted(p.name for p in kept.iterdir()) == ["builds__20261111-000000", "site"]
    assert json.loads(run("unhide", "landlords/example-council/")[1])["pages_changed"] == 30
    assert "Grade C3" in (publish.builds_dir(settings) / "20261111-000000" / "landlords" / "example-council"
                          / "index.html").read_text()
