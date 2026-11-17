from datetime import date

from landlords.load.common import as_date, code, parse_value, text


def test_codes_stored_as_numbers_come_back_as_text():
    assert code(4747.0) == "4747"
    assert code(" L4203 ") == "L4203"
    assert code("00GL") == "00GL"


def test_markers_are_statuses_not_numbers():
    assert parse_value("[U]") == (None, "undefined")   # zero denominator: not applicable, never zero
    assert parse_value("[E]") == (None, "excluded")
    assert parse_value("[S]") == (None, "suppressed")
    assert parse_value("[x]") == (None, "blank")
    assert parse_value("[Z]") == (None, "not required")
    assert parse_value("0") == (0.0, "value")
    assert parse_value("1,234.5") == (1234.5, "value")
    assert parse_value(71.8) == (71.8, "value")
    assert parse_value("") == (None, "empty")
    assert parse_value("Telephone") == (None, "text")


def test_names_and_dates():
    assert text("Abbeyfield Society  (The) ") == "Abbeyfield Society (The)"
    assert as_date("2026-04-29") == date(2026, 4, 29)
    assert as_date("17/04/2023") == date(2023, 4, 17)
    assert as_date("15 October 2026") == date(2026, 10, 15)
    assert as_date("-") is None


def test_the_server_can_set_the_address_and_the_launch_switch(monkeypatch):
    from landlords.config import load_settings

    monkeypatch.setenv("LANDLORDS_SITE_URL", "https://example.org")
    monkeypatch.setenv("LANDLORDS_LAUNCHED", "true")
    s = load_settings()
    assert s.section("site")["url"] == "https://example.org" and s.section("site")["launched"] is True
    monkeypatch.setenv("LANDLORDS_LAUNCHED", "false")
    assert load_settings().section("site")["launched"] is False


def test_2025_26_field_names_are_read_as_before():
    from landlords.load.tsm import harmonise

    assert harmonise("Relevant_ten_pop_size_a", "LCRA", "LCRA_perception") == "Relevant_ten_pop_size_LCRA"
    assert harmonise("Total_sample_size_b", "LCHO", "LCHO_perception") == "Total_sample_size_LCHO"
    assert harmonise("Responses_Telephone_c", "COMB", "COMB_perception") == "Responses_Telephone_COMB"
    assert harmonise("Predominant method", "LCRA", "LCRA_perception") == "Predominant_method_LCRA"
    assert harmonise("RSH Comments", "LCHO", "LCHO_perception") == "RSH_Comments_LCHO"
    assert harmonise("Above 30% SH", None, "Management_info") == "Above_30_SH"
    assert harmonise("RSH Comments", None, "Management_info") == "RSH Comments"      # not a survey table
    assert harmonise("TP01_Satisfied_Calc_LCRA", "LCRA", "LCRA_perception") == "TP01_Satisfied_Calc_LCRA"
    assert harmonise("Landlord code", None, "Table_coverage") == "Landlord_code"


def test_the_pages_show_the_licence_as_sources_toml_says_now(settings):
    """A file fetched before a change to its licence line still gets the new line (no internal notes on the pages)."""
    import json

    from landlords.fetch import entries
    from landlords.load.common import record_sources

    e = next(e for e in entries() if e.source == "ombudsman")
    note = {"sha256": "abc", "source": e.source, "role": e.role, "period": e.period, "title": "t", "url": "u",
            "page": "p", "publisher": e.publisher, "licence": "old words (docs/DECISIONS.md, 9)",
            "fetched_at": "2026-11-03T00:00:00+00:00", "file": "abc.xlsx"}
    settings.staging_dir.mkdir(parents=True)
    record_sources(settings, [note])
    licence = json.loads((settings.staging_dir / "sources.json").read_text())["abc"]["licence"]
    assert licence == e.licence and "docs/" not in licence
    for entry in entries():
        assert "docs/" not in entry.licence and ".md" not in entry.licence, entry
