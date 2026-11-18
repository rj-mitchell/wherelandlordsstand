"""The pages' shared parts, without the real data."""

from types import SimpleNamespace

from landlords.profile import source_order


def test_sources_from_the_same_source_and_period_are_numbered_the_same_way_every_time():
    sources = {"b1": {"source": "stock", "period": "2025/26", "title": "Private registered providers data release"},
               "a2": {"source": "stock", "period": "2025/26", "title": "Local authority registered provider data release"},
               "c3": {"source": "grades", "period": "2025/26", "title": "Regulatory judgements"}}
    data = SimpleNamespace(sources=sources)
    for used in ({"b1", "a2", "c3"}, {"c3", "a2", "b1"}, ["a2", "c3", "b1"], ["b1", "c3", "a2"]):
        assert sorted(used, key=lambda s: source_order(data, s)) == ["c3", "a2", "b1"]


def test_the_family_kit_is_copied_in_unedited():
    """src/landlords/family/ is the kit as its sync script wrote it (docs/DESIGN.md): its VERSION file carries a hash
    of every other file, made as the script makes it, so an edit to the copy fails here. To change it, change the kit
    and sync again."""
    import hashlib
    import re

    from landlords.site import FAMILY

    version = (FAMILY / "VERSION").read_text()
    assert "site landlords" in version and "base /family/" in version
    digest = hashlib.sha256()
    for path in sorted(p.relative_to(FAMILY).as_posix() for p in FAMILY.rglob("*") if p.is_file()):
        if path != "VERSION":
            digest.update(path.encode() + b"\0" + (FAMILY / path).read_bytes() + b"\0")
    assert re.search(r"^sha256 ([0-9a-f]{64})$", version, re.M)[1] == digest.hexdigest()


def test_the_kit_partials_name_their_files_at_their_fingerprinted_addresses(tmp_path):
    from landlords import site

    names = site.write_assets(tmp_path)
    parts = site.family_parts(names)
    head = parts["head"].replace(site.UP, "../")
    assert f'href="../{names["fonts.css"]}"' in head and f'href="../{names["family.css"]}"' in head
    assert f'content="https://wherelandlordsstand.com/{names["card.png"]}"' in head
    assert "/family/" not in head and "<script" not in "".join(parts.values())
    assert 'class="wts-endorse"' in parts["endorsement"] and 'class="wts-shelf"' in parts["shelf"]
    # the kit's VERSION is at /family/VERSION, for the charity's nightly family check
    version = (tmp_path / "family" / "VERSION").read_text()
    assert version.startswith("Where They Stand family kit") and "\nsite landlords\n" in version


def test_the_masthead_mark_is_the_press_pages_mark():
    """The mark drawn in the masthead (site.MARK) has the same shapes and colours as static/mark.svg, the file the
    press page offers; mark-dark.svg is the same drawing on the lifted slate, and the small files are square too."""
    import re

    from landlords.site import MARK, STATIC

    def shapes(svg: str) -> list[str]:
        svg = re.sub(r' (class|id|width|height|viewBox|xmlns|aria-hidden|focusable)="[^"]*"', "", svg)
        return re.findall(r"<(?:rect|path|circle|stop)[^>]*>", svg)

    light = (STATIC / "mark.svg").read_text()
    assert shapes(MARK) == shapes(light)
    assert (STATIC / "mark-dark.svg").read_text() == light.replace("#40484D", "#5B666D")
    small = (STATIC / "mark-small.svg").read_text()
    assert (STATIC / "mark-small-dark.svg").read_text() == small.replace("#40484D", "#5B666D")
    for svg in (light, small):
        assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"')
        assert "<title>Where Landlords Stand</title>" in svg
        assert "href" not in svg and not re.search(r"url\((?!#)", svg)                    # nothing from outside
    assert 'aria-hidden="true"' in MARK and 'width="52" height="52"' in MARK


def test_sentences_with_links():
    from landlords.site import fill_html, rich

    assert rich("Read <this> [the code](https://example.org/a?b=1&c=2).") == (
        'Read &lt;this&gt; <a href="https://example.org/a?b=1&amp;c=2">the code</a>.')
    assert rich("Use the [form](corrections/index.html).", "../") == (
        'Use the <a href="../corrections/index.html">form</a>.')
    assert rich("Email [a@b.org](mailto:a@b.org).") == 'Email <a href="mailto:a@b.org">a@b.org</a>.'
    assert fill_html("It's {link}, or {x}.", link="<a>here</a>", x="<b>") == "It&#x27;s <a>here</a>, or <b>."


def test_area_tables_stack_on_a_phone_and_stay_tables():
    """On a narrow phone each landlord in an area is a block, its figures under their headings (styles.css), so no
    name is broken mid-word ('Birmingh|am'). The headings stay in the table, and ARIA roles keep it a table for screen
    readers whatever the stylesheet does to it (8 November 2026)."""
    from landlords.config import load_toml
    from landlords.site_pages import area_html

    w = load_toml("wording.toml")
    t = w["area"]
    p = {"slug": "abri-group", "name": "Abri Group", "grade": {"grade": "G1"}, "bands": {"headline": {"band": 4}}}
    area = {"name": "Birmingham", "slug": "birmingham", "landlords": [(p, 12345, "")], "sources": set()}
    html = area_html(area, w, {})
    assert '<table class="stack" role="table"><thead role="rowgroup"><tr role="row">' in html
    assert f'<th scope="col" role="columnheader" class="n">{t["homes"]}</th>' in html
    for label, value in ((t["homes"], "12,345"), (t["grade"], "G1")):
        assert f'data-label="{label}">{value}</td>' in html
    assert '<tr role="row"><td role="cell"><a href="../../landlords/abri-group/index.html">Abri Group</a></td>' in html


def test_search_tells_screen_readers_the_number_found_not_the_whole_list():
    """The list of results is rebuilt with every letter typed, so it is not a live region; a separate status line
    says how many were found once typing stops (search.js), in the words of config/wording.toml."""
    import json
    import re

    from landlords.config import load_toml
    from landlords.site_pages import index_html

    w = load_toml("wording.toml")
    html = index_html([], w)
    assert '<ul id="results" class="results"></ul>' in html
    assert '<p id="results-status" class="sr-only" role="status" aria-live="polite"></p>' in html
    text = json.loads(re.search(r'<script type="application/json" id="search-text">(.*?)</script>', html).group(1))
    assert text["found"] == w["search"]["found"] and "{count}" in text["found"]
    assert {"found_one", "found_none", "found_small"} <= set(text)


def test_only_the_pages_whose_tab_can_start_out_of_sight_on_a_phone_load_the_tab_script():
    from landlords.config import load_toml
    from landlords.site import NAV, page

    w = load_toml("wording.toml")
    for i, (here, _) in enumerate(NAV):
        assert ("tabs." in page("T", "", w, depth=1, here=here)) == (i >= 3), here
    assert "<script" not in page("T", "", w, depth=2)                # a landlord's page has no tab, and no script


# Search's list of names (site_pages.names_json) and what search.js says about each

SEARCH_PROFILES = [
    {"id": "G1", "slug": "example-group", "name": "Example Group", "legal_name": "Example Group Limited",
     "type": "housing association", "also_known_as": []},
    {"id": "P1", "slug": "sibling-homes", "name": "Sibling Homes", "legal_name": "Sibling Homes Limited",
     "type": "housing association", "also_known_as": []},
    {"id": "C1", "slug": "example-council", "name": "Example Council", "legal_name": "Example City Council",
     "type": "council", "also_known_as": []},
]
SEARCH_REGISTER = {
    "G1": {"legal_name": "Example Group Limited", "group_id": "", "status": "active"},
    "S1": {"legal_name": "Example Homes Limited", "group_id": "G1", "status": "active"},   # the SDR calls it Large
    "S2": {"legal_name": "Example North Limited", "group_id": "G1", "status": "active"},   # Small, under S1
    "T1": {"legal_name": "Top Holdings Limited", "group_id": "", "status": "active"},      # parent of P1 and T2
    "P1": {"legal_name": "Sibling Homes Limited", "group_id": "T1", "status": "active"},
    "T2": {"legal_name": "Sibling Care Limited", "group_id": "T1", "status": "active"},
    "X1": {"legal_name": "Tiny Homes Limited", "group_id": "", "status": "active"},        # Small
    "U1": {"legal_name": "Unknown Homes Limited", "group_id": "", "status": "active"},     # no size figure
    "C1": {"legal_name": "Example City Council", "group_id": "", "status": "active"},
    "D1": {"legal_name": "Gone Homes Limited", "group_id": "", "status": "deregistered"},
}
SEARCH_PARENTS = {"S1": "G1", "S2": "S1", "P1": "T1", "T2": "T1"}
SEARCH_SMALL = {"S2", "X1", "T2"}
SEARCH_ALIASES = [{"landlord_id": "C1", "alias": "Example Homes Trust", "kind": "managing body", "valid_to": ""}]


def _search_names() -> list[dict]:
    from landlords.config import load_toml
    from landlords.site_pages import names_json

    return names_json(SEARCH_PROFILES, SEARCH_REGISTER, SEARCH_ALIASES, load_toml("wording.toml"), SEARCH_PARENTS,
                      SEARCH_SMALL)


def test_search_sends_a_groups_companies_to_the_page_of_the_landlord_we_cover():
    """A company with no page of its own, in the group of a landlord we cover (the regulator's group structure), is
    listed as part of it and links to its page: it is never called small, whatever its size (18 November 2026: the
    regulator lists Clarion Housing Association Ltd as Large, and search said it had fewer than 1,000 homes)."""
    by_name = {e["n"]: e for e in _search_names()}
    assert {k: by_name["Example Homes Limited"][k] for k in ("s", "g", "r")} == \
        {"s": "example-group", "g": "Example Group", "r": "part"}
    assert {k: by_name["Example North Limited"][k] for k in ("s", "g", "r")} == \
        {"s": "example-group", "g": "Example Group", "r": "part"}                  # through its parent, S1
    # no profiled parent, but the one company in its group that we cover: said to be in the same group, not part of it
    assert {k: by_name["Sibling Care Limited"][k] for k in ("s", "g", "r")} == \
        {"s": "sibling-homes", "g": "Sibling Homes", "r": "group"}
    assert {k: by_name["Top Holdings Limited"][k] for k in ("s", "r")} == {"s": "sibling-homes", "r": "group"}
    assert "Gone Homes Limited" not in by_name


def test_no_company_in_a_covered_group_gets_the_small_wording():
    profiled = {p["id"] for p in SEARCH_PROFILES}
    covered_groups = {SEARCH_REGISTER[i]["group_id"] or i for i in profiled}
    names = {e["n"]: e for e in _search_names()}
    for lid, r in SEARCH_REGISTER.items():
        if lid not in profiled and r["status"] == "active" and (r["group_id"] or lid) in covered_groups:
            assert "z" not in names[r["legal_name"]] and names[r["legal_name"]]["s"], lid


def test_search_calls_a_landlord_small_only_from_the_regulators_figures():
    """Having no page is not a size: a landlord is said to have fewer than 1,000 homes only when the regulator's
    figures say so; any other gets the neutral wording."""
    by_name = {e["n"]: e for e in _search_names()}
    assert by_name["Tiny Homes Limited"] == {"n": "Tiny Homes Limited", "k": ["tiny homes"], "z": 1}
    assert by_name["Unknown Homes Limited"] == {"n": "Unknown Homes Limited", "k": ["unknown homes"]}
    assert "example homes trust" in by_name["Example Council"]["k"]                 # a managing body's name


def test_search_facts_come_from_the_group_structure_and_the_councils_return(tmp_path):
    from landlords.config import load_settings
    from landlords.load.common import write_table
    from landlords.load.providers import GROUPS
    from landlords.load.stock import SCHEMA
    from landlords.site_pages import search_facts

    s = load_settings(env={"LANDLORDS_DATA_DIR": str(tmp_path)})
    group = {"in_group": True, "is_group_parent": False, "parent_name": "", "unregistered_parent": "", "name": "",
             "source_file": ""}
    write_table(s, "groups", [{**group, "landlord_id": "S1", "size": "Large", "parent_id": "G1"},
                              {**group, "landlord_id": "X1", "size": "Small", "parent_id": ""}], GROUPS)
    stock = {"name_published": "", "period": "2025/26", "gss": "E1", "area_name": "", "source_file": ""}
    write_table(s, "stock_area", [
        {**stock, "landlord_id": "C1", "basis": "council total", "measure": "all_owned", "value": 32.0},
        {**stock, "landlord_id": "C2", "basis": "council total", "measure": "all_owned", "value": 5200.0},
        {**stock, "landlord_id": "C3", "basis": "council total", "measure": "lcho_owned", "value": 10.0},
        {**stock, "landlord_id": "S1", "basis": "by area", "measure": "lcr_owned_general_needs", "value": 12.0},
    ], SCHEMA)
    assert search_facts(s) == ({"S1": "G1"}, {"X1", "C1"})


def _run_search_page(names: list[dict], q: str) -> dict:
    """The home page's search, run by node with a stand-in for the page: what it lists, what a screen reader hears,
    and what it sends as a missed search."""
    import json
    import re
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    from landlords.config import load_toml
    from landlords.site_pages import index_html

    if not shutil.which("node"):
        pytest.skip("node not installed")
    html = index_html([], load_toml("wording.toml"))
    text = re.search(r'<script type="application/json" id="search-text">(.*?)</script>', html).group(1)
    js = Path(__file__).parents[1] / "src/landlords/static/search.js"
    script = f"""
      const items = [], posts = [];
      const input = {{ value: "", addEventListener() {{}} }};
      const els = {{
        search: {{ dataset: {{ root: "" }}, querySelector: () => input, addEventListener() {{}} }},
        results: {{ set innerHTML(v) {{ items.length = 0; }}, append(el) {{ items.push(el.innerHTML); }} }},
        "results-status": {{ textContent: "" }},
        "search-text": {{ textContent: {json.dumps(text)} }},
      }};
      global.window = global;                                         // as in a browser, WLS is a global
      global.document = {{ getElementById: (id) => els[id], createElement: () => ({{ innerHTML: "" }}) }};
      global.location = {{ search: "?q=" + encodeURIComponent({json.dumps(q)}) }};
      global.fetch = (url, opts) => url.endsWith("names.json")
        ? Promise.resolve({{ json: () => {json.dumps(names)} }}) : (posts.push(JSON.parse(opts.body)), Promise.resolve({{}}));
      require({json.dumps(str(js))});
      setTimeout(() => console.log(JSON.stringify({{ items, posts, status: els["results-status"].textContent }})), 50);
    """
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


def test_the_search_page_links_a_groups_company_to_the_group_and_counts_no_miss():
    from landlords.config import load_toml

    s = load_toml("wording.toml")["search"]
    r = _run_search_page(_search_names(), "Example North")
    assert r["items"] == [s["part"].replace("{name}", "Example North Limited").replace(
        "{group}", '<a href="landlords/example-group/index.html">Example Group</a>')]
    assert r["status"] == s["found_one"] and r["posts"] == []
    r = _run_search_page(_search_names(), "Sibling Care")
    assert r["items"] == [s["group"].replace("{name}", "Sibling Care Limited").replace(
        "{group}", '<a href="landlords/sibling-homes/index.html">Sibling Homes</a>')]


def test_the_search_page_counts_a_miss_when_it_finds_only_landlords_without_a_page():
    """A search that finds only a landlord we have no page for is counted as missed, so the owner sees it
    (`landlords missed`); before 18 November 2026 only a search that found no name at all was counted."""
    from landlords.config import load_toml

    s = load_toml("wording.toml")["search"]
    areas = f' <a href="areas/index.html">{s["areas_link"]}</a>'
    r = _run_search_page(_search_names(), "Tiny Homes")
    assert r["items"] == [s["small"].replace("{name}", "Tiny Homes Limited"), s["unlisted_areas"] + areas]
    assert r["status"] == s["found_small"] and r["posts"] == [{"q": "Tiny Homes"}]
    r = _run_search_page(_search_names(), "Unknown Homes")
    assert r["items"] == [s["unlisted"].replace("{name}", "Unknown Homes Limited"), s["unlisted_areas"] + areas]
    assert r["status"] == s["found_unlisted"] and r["posts"] == [{"q": "Unknown Homes"}]
    assert "1,000" not in r["items"][0]
    r = _run_search_page(_search_names(), "Nobody At All")
    assert r["items"] == [s["none"] + areas] and r["status"] == s["found_none"] and r["posts"] == [{"q": "Nobody At All"}]
    r = _run_search_page(_search_names(), "Example Council")
    assert r["posts"] == [] and r["items"][0].startswith('<a href="landlords/example-council/index.html">')
