"""The measurement switch, [ads] in config/settings.toml (docs/DECISIONS.md, 20), without the real data.

Off, as it ships: no page names the family kit's measure.js, Google or "Measurement choices", the build copies no
measure.js, and the content security policy is the one the site always had, with no Google host. On, with a tag:
every page loads measure.js with the tag, the footer has "Measurement choices", the privacy page is the measurement
version, and the policy adds exactly the kit's hosts. tests/test_data.py builds the real pages both ways."""

from __future__ import annotations

import dataclasses
import json
import re

import pytest
from fastapi.testclient import TestClient

from landlords import api, site, site_pages
from landlords.config import load_settings, load_toml
from landlords.site import FAMILY

TAG = "AW-123456789"
KIT_CSP = json.loads((FAMILY / "measure-csp.json").read_text())
GOOGLE = re.compile(r"google|doubleclick", re.I)


def switched(settings, measurement: bool, tag: str = TAG):
    return dataclasses.replace(settings, raw={**settings.raw, "ads": {"measurement": measurement, "tag": tag}})


@pytest.fixture
def pages(tmp_path):
    """Draw pages for a build made with the switch as given, then put the module back as it was."""
    saved = (site._LAUNCHED, site._SITE, dict(site._ASSETS), site._MEASURE, dict(site._PARTS))

    def draw(settings, folder: str = "out"):
        out = tmp_path / folder
        names = site.write_assets(out, measure=bool(site.measure_tag(settings)))
        site.use_build(settings, names, False)
        return out, names

    yield draw
    site._LAUNCHED, site._SITE, site._ASSETS, site._MEASURE, site._PARTS = saved


def finished(w: dict) -> dict:
    """The wording, with the measurement notice's placeholders filled as the owner fills them before turning it on."""
    t = json.loads(json.dumps(w["privacy_measurement"]).replace("NNNNNNN", "1234567"))
    t["updated"] = "Last updated 1 March 2027."
    return {**w, "privacy_measurement": t}


def test_the_switch_ships_off_with_no_tag():
    s = load_settings(env={})
    assert s.section("ads") == {"measurement": False, "tag": ""}
    assert site.measure_tag(s) == ""
    assert site.measure_tag(switched(s, True, "")) == "", "on without a tag is still off"
    assert site.measure_tag(switched(s, True, 'AW-1"><script>')) == ""
    assert site.measure_tag(switched(s, True)) == TAG
    # the server sets it in deploy/.env, as it does the launch switch
    on = load_settings(env={"LANDLORDS_ADS_MEASUREMENT": "true", "LANDLORDS_ADS_TAG": TAG})
    assert site.measure_tag(on) == TAG


def test_off_no_page_names_measure_js_or_google_and_no_script_is_copied(settings, pages):
    out, names = pages(settings)
    assert "measure.js" not in names and not list((out / "assets").glob("measure.*.js"))
    w = load_toml("wording.toml")
    drawn = [site.page("A page | Where Landlords Stand", "<h1>A page</h1>", w, depth=1, path="a/"),
             site_pages.privacy_html(w), site_pages.thanks_html(w), site_pages.named_thanks_html(w)]
    for html in drawn:
        assert not re.search(r"measure\.|googletagmanager|data-wts-measure-open|Measurement choices", html)
        assert "<script" not in re.sub(r'<script type="application/ld\+json">.*?</script>', "", html)
    privacy = site_pages.privacy_html(w)
    assert "This site sets no cookies and uses no analytics or advertising." in privacy
    assert not GOOGLE.search(privacy) and 'id="measurement"' not in privacy


def test_off_the_policy_is_unchanged_and_names_no_google_host(settings):
    root = settings.data_dir / "site"
    root.mkdir(parents=True)
    (root / "index.html").write_text("<h1>home</h1>")
    r = TestClient(api.create_app(settings)).get("/")
    assert r.headers["content-security-policy"] == api.CSP
    assert not GOOGLE.search(r.headers["content-security-policy"])
    assert api.CSP == ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                       "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


def test_on_the_policy_adds_exactly_the_kits_hosts(settings):
    on = switched(settings, True)
    root = on.data_dir / "site"
    root.mkdir(parents=True)
    (root / "index.html").write_text("<h1>home</h1>")
    policy = TestClient(api.create_app(on)).get("/").headers["content-security-policy"]
    directives = {d.split()[0]: d.split()[1:] for d in policy.split("; ")}
    assert directives["script-src"] == ["'self'", *KIT_CSP["script-src"]]
    assert directives["img-src"] == ["'self'", "data:", *KIT_CSP["img-src"]]
    assert directives["connect-src"] == ["'self'", *KIT_CSP["connect-src"]]
    assert directives["frame-src"] == ["'self'", *KIT_CSP["frame-src"]]
    for name in ("default-src", "style-src", "form-action", "frame-ancestors", "base-uri"):
        assert directives[name] == {d.split()[0]: d.split()[1:] for d in api.CSP.split("; ")}[name]
    assert "unsafe" not in policy and "*" not in policy


def test_on_every_page_loads_measure_js_with_the_tag_and_the_footer_has_measurement_choices(settings, pages):
    out, names = pages(switched(settings, True))
    assert "measure.js" in names
    assert (out / names["measure.js"]).read_bytes() == (FAMILY / "measure.js").read_bytes()
    w = finished(load_toml("wording.toml"))
    for depth, html in ((1, site.page("A | Where Landlords Stand", "<h1>A</h1>", w, depth=1, path="a/")),
                        (2, site.page("B | Where Landlords Stand", "<h1>B</h1>", w, depth=2, path="a/b/")),
                        (1, site_pages.privacy_html(w)), (1, site_pages.thanks_html(w))):
        up = "../" * depth
        head = html.split("</head>")[0]
        assert (f'<script src="{up}{names["measure.js"]}" data-tag="{TAG}" data-privacy="{up}privacy/" '
                f'data-measures="source_opened download donate_click report_sent" defer></script>') in head
        assert (f'<p class="measure-choices"><a href="{up}privacy/#measurement" data-wts-measure-open>'
                "Measurement choices</a></p>") in html.split("<footer>")[1]
        # still six footer links, in the family's order: "Measurement choices" is a line of its own
        assert len(re.findall(r'<li><a href="[^"]*">[^<]*</a></li>', html.split('<ul class="foot-links">')[1].split("</ul>")[0])) == 6
        assert "googletagmanager" not in html     # only measure.js loads it, and only after Accept


def test_on_the_privacy_page_is_the_measurement_version_and_is_refused_unfinished(settings, pages):
    pages(switched(settings, True))
    w = load_toml("wording.toml")
    with pytest.raises(RuntimeError, match="NNNNNNN"):
        site_pages.privacy_html(w)
    html = site_pages.privacy_html(finished(w))
    for words in ("Google Ad Grants", "open a source, download a file, follow the Donate link or send a report",
                  "independent controller", "The legal basis is your consent", "90 days",
                  'href="https://policies.google.com/technologies/retention"',
                  'href="https://business.safety.google/privacy/"', "Measurement choices",
                  "Nothing is loaded from Google until you choose", "No ads are ever shown",
                  "nothing on them is personalised", "registered in England and Wales (charity number 1234567)",
                  "Last updated 1 March 2027."):
        assert words.replace('"', "&quot;") in html or words in html, words
    assert '<h2 id="measurement">' in html
    assert '<link rel="canonical"' not in html or 'privacy/"' in html


def test_on_then_off_the_pages_are_as_they_were(settings, pages):
    w = finished(load_toml("wording.toml"))

    def draw(s, folder):
        pages(s, folder)
        return [site.page("A | Where Landlords Stand", "<h1>A</h1>", w, depth=1, path="a/"),
                site_pages.privacy_html(w), site_pages.thanks_html(w)]

    before = draw(settings, "1")
    draw(switched(settings, True), "2")
    assert draw(switched(settings, False), "3") == before


def test_the_conversions_are_marked_where_they_happen(settings, pages):
    pages(settings)
    w = load_toml("wording.toml")
    # the inert attributes the kit's measure.js reads: harmless, and the same, with the switch off
    for html in (site_pages.thanks_html(w), site_pages.named_thanks_html(w)):
        assert '<p data-wts-conversion="report_sent">' in html
    files = [("landlords.csv", "a,b\n1,2\n", 1)]
    assert '<a href="landlords.csv" data-wts-conversion="download">landlords.csv</a>' in site_pages.downloads_html(files, w)
    sources = site.Sources([{"sha": "x", "publisher": "The Regulator of Social Housing", "page": "https://example.org/p",
                             "title": "Tenant Satisfaction Measures", "period": "2025/26", "url": "https://example.org/f.xlsx",
                             "fetched_at": "2026-11-01T00:00:00", "licence": "OGL"}]).html(w)
    assert '<a href="https://example.org/p" data-wts-conversion="source_opened">' in sources
    assert '<a href="https://example.org/f.xlsx" data-wts-conversion="source_opened">The file</a>' in sources
    assert 'data-wts-conversion="donate_click">Donate</a>' in (FAMILY / "shelf.html").read_text()
