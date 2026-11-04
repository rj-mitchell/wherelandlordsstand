"""The weekly email's approval link: opening it never publishes; the button does, once; undo puts back the pages."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from landlords import notify, publish
from landlords.api import State, create_app


def _build(settings, name, failed=()):
    d = publish.builds_dir(settings) / name
    (d / "landlords" / "x").mkdir(parents=True)
    (d / "index.html").write_text(f"home {name}")
    (d / "landlords" / "x" / "index.html").write_text(f"landlord {name}")
    (d / "build-info.json").write_text(json.dumps({"build": name, "checks_failed": list(failed),
                                                   "new_file_titles": ["RSH: TSM 2025/26 full data (2025/26)"]}))


@pytest.fixture
def site(settings):
    _build(settings, "20261101-000000")
    _build(settings, "20261105-000000")
    publish.publish(settings, "20261101-000000")
    state = State(settings.data_dir / "state.db")
    return settings, state, TestClient(create_app(settings))


def test_opening_the_link_does_not_publish_but_the_button_does(site):
    settings, state, client = site
    token = state.add_approval("20261105-000000", 14)
    page = client.get(f"/admin/approve/{token}")
    assert page.status_code == 200 and "Publish these pages" in page.text and "TSM 2025/26" in page.text
    assert page.headers["x-robots-tag"] == "noindex" and page.headers["cache-control"] == "no-store"
    assert publish.current(settings) == "20261101-000000"             # still the old pages
    assert client.get(f"/admin/preview/{token}/landlords/x/").text == "landlord 20261105-000000"
    r = client.post(f"/admin/approve/{token}", follow_redirects=False)
    assert r.status_code == 303 and publish.current(settings) == "20261105-000000"
    assert "Undo" in client.get(f"/admin/approve/{token}").text
    client.post(f"/admin/approve/{token}")                                # pressing again changes nothing
    assert publish.current(settings) == "20261105-000000"
    client.post(f"/admin/rollback/{token}")
    assert publish.current(settings) == "20261101-000000"
    assert "taken down again" in client.get(f"/admin/approve/{token}").text


def test_bad_expired_and_failed_links_publish_nothing(site):
    settings, state, client = site
    assert client.get("/admin/approve/not-a-token").status_code == 404
    expired = state.add_approval("20261105-000000", 14)
    sqlite3.connect(settings.data_dir / "state.db").execute(
        "update approvals set expires = '2000-01-01T00:00:00+00:00'").connection.commit()
    assert client.post(f"/admin/approve/{expired}").status_code == 404
    _build(settings, "20261106-000000", failed=["a check"])
    token = state.add_approval("20261106-000000", 14)
    assert "can't be published" in client.get(f"/admin/approve/{token}").text
    assert client.post(f"/admin/approve/{token}").status_code == 409
    assert publish.current(settings) == "20261101-000000"


def test_preview_stays_inside_its_build(site):
    settings, state, client = site
    (settings.data_dir / "secret.txt").write_text("no")
    token = state.add_approval("20261105-000000", 14)
    for path in ("../../secret.txt", "..%2F..%2Fsecret.txt", "/etc/passwd"):
        assert client.get(f"/admin/preview/{token}/{path}").text != "no"
        assert "root:" not in client.get(f"/admin/preview/{token}/{path}").text


def test_only_a_hash_of_the_token_is_stored(site):
    settings, state, _ = site
    token = state.add_approval("20261105-000000", 14)
    stored = sqlite3.connect(settings.data_dir / "state.db").execute("select token_hash from approvals").fetchall()
    assert all(token not in row[0] for row in stored)


def test_the_email(settings, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, context=None, timeout=None):
            sent.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            sent.append(("login", user))

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    assert notify.send(settings, "s", "b").startswith("not sent: email is not set up")
    monkeypatch.setenv("LANDLORDS_SMTP_USER", "sender@example.org")
    monkeypatch.setenv("LANDLORDS_SMTP_PASSWORD", "app-password")
    subject, body = notify.report({"build": "b1", "new_file_titles": ["RSH: TSM 2025/26"], "checks_failed": []},
                                  {"approve": "https://x/admin/approve/T", "preview": "https://x/p", "days": 14},
                                  {"open_reports": 2, "rights_due": ["Complaints (due 2026-11-10)"]})
    assert "to approve" in subject and "https://x/admin/approve/T" in body and "Publish button" in body
    assert "Readers' reports of mistakes waiting: 2" in body and "Complaints" in body
    assert notify.send(settings, subject, body) == "sent to wherestheystanduk@gmail.com"
    msg = sent[-1]
    assert msg["To"] == "wherestheystanduk@gmail.com" and "app-password" not in msg.as_string()
