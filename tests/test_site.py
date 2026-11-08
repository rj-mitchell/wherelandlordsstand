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
