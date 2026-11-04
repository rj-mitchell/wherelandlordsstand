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
