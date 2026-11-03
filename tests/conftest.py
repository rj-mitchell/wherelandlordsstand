from __future__ import annotations

import pytest

from landlords import register
from landlords.config import load_settings


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
