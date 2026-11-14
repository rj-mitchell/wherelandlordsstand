from __future__ import annotations

import os

# Typer draws a command's --help with colour codes when it thinks a terminal is watching, and it thinks so on GitHub
# Actions (it looks for GITHUB_ACTIONS). The codes split an option's name in two, so a test that reads --help passed
# on a developer's machine and failed in CI. Typer reads these when it is first imported, so they are set here,
# before anything imports it.
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
os.environ["NO_COLOR"] = "1"

import pytest

from landlords import register
from landlords.config import load_settings


@pytest.fixture(autouse=True)
def no_real_email(monkeypatch):
    """Never a real email from a test: no SMTP account, and letters go to each test's own outbox."""
    for k in ("LANDLORDS_MAIL", "LANDLORDS_SMTP_USER", "LANDLORDS_SMTP_PASSWORD", "LANDLORDS_NOTIFY_TO"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LANDLORDS_DATA_DIR", str(tmp_path / "data"))
    return load_settings()


@pytest.fixture
def static(tmp_path, monkeypatch):
    """A register and alias table of our own, in place of data_static/."""
    monkeypatch.setattr(register, "LANDLORDS_CSV", tmp_path / "landlords.csv")
    monkeypatch.setattr(register, "ALIASES_CSV", tmp_path / "aliases.csv")
    monkeypatch.setattr(register, "PUBLISHED_SLUGS", tmp_path / "published_slugs.txt")
    return tmp_path
