import json

from landlords import fetch


def entry(**kw):
    base = dict(source="tsm", role="full-data", period="2024/25", publisher="RSH", licence="OGL")
    return fetch.Entry(**{**base, **kw})


def test_a_file_is_never_overwritten(settings):
    e = entry()
    f = fetch.Found(url="https://assets.example/a.xlsx", title="Full data", page="https://www.gov.uk/x")
    note1, new1 = fetch.store(settings, e, f, b"first", "application/x")
    note2, new2 = fetch.store(settings, e, f, b"first", "application/x")
    note3, new3 = fetch.store(settings, e, f, b"second", "application/x")
    assert (new1, new2, new3) == (True, False, True)
    folder = settings.raw_dir / "tsm"
    assert (folder / note1["file"]).read_bytes() == b"first"
    assert (folder / note3["file"]).read_bytes() == b"second"
    saved = json.loads((folder / f"{note1['sha256']}.note.json").read_text())
    assert saved["url"] == f.url and saved["page"] == f.page and saved["period"] == "2024/25"
    assert len(fetch.read_index(settings, "tsm")) == 3
    assert fetch.latest(settings, "tsm", "full-data")["sha256"] == note3["sha256"]


def test_a_json_page_and_its_note_do_not_clash(settings):
    e = entry(source="judgements", role="under-review", period="current")
    note, _ = fetch.store(settings, e, fetch.Found("https://www.gov.uk/api/content/x", "", ""), b"{}",
                          "application/json", ext="json")
    folder = settings.raw_dir / "judgements"
    assert (folder / f"{note['sha256']}.json").read_bytes() == b"{}"
    assert (folder / f"{note['sha256']}.note.json").exists()


def test_govuk_attachments_are_picked_by_title_and_type():
    content = {"public_updated_at": "2025-11-04", "details": {"attachments": [
        {"title": "Tenant Satisfaction Measures 2025: full data set", "url": "https://assets/a.xlsx"},
        {"title": "Tenant Satisfaction Measures 2025: full data set", "url": "https://assets/a.zip"},
        {"title": "Headline Report (PDF)", "url": "https://assets/r.pdf"},
        {"title": "Headline Report", "url": "/government/statistics/x/headline"},
    ]}}
    found = fetch.find_govuk(content, entry(govuk="/x", match="full data set", types=("zip",)))
    assert [f.url for f in found] == ["https://assets/a.zip"]
    found = fetch.find_govuk(content, entry(govuk="/x", match="headline"))
    assert [f.url for f in found] == ["https://assets/r.pdf"]  # HTML attachments are pages, not files


def test_links_are_picked_by_address():
    html = ('<a href="/app/uploads/2026/09/Tables-for-landlords-2025-26.xlsx">Landlords performance data tables'
            '</a> <a href="https://x.org/Register-of-Interests.pdf">Register</a>')
    e = entry(source="ombudsman", page="https://www.housing-ombudsman.org.uk/acr/", links=r"tables-for-landlords.*\.xlsx$")
    found = fetch.find_links(html, e)
    assert [f.url for f in found] == ["https://www.housing-ombudsman.org.uk/app/uploads/2026/09/Tables-for-landlords-2025-26.xlsx"]
    assert found[0].title == "Landlords performance data tables"


def test_sources_file_is_valid():
    entries = fetch.entries()
    assert {e.source for e in entries} >= {"tsm", "judgements", "providers", "stock", "ombudsman"}
    for e in entries:
        assert bool(e.govuk) + bool(e.page) + bool(e.urls) >= 1, e
