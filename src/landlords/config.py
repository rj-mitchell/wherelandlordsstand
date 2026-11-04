"""Settings loaded from config/settings.toml, with environment overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
STATIC_DIR = REPO_ROOT / "data_static"


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]
    data_dir: Path
    config_path: Path

    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {})

    @property
    def fetch(self) -> dict[str, Any]:
        return self.section("fetch")

    # Data layout -------------------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        """Every downloaded file, by source and content hash. Nothing here is ever overwritten."""
        return self.data_dir / "raw"

    @property
    def staging_dir(self) -> Path:
        """Tidy tables built from the raw files, and the checks on them. Never served directly."""
        return self.data_dir / "staging"


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = _resolve(config_path or os.environ.get("LANDLORDS_CONFIG") or CONFIG_DIR / "settings.toml")
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    data_dir = _resolve(os.environ.get("LANDLORDS_DATA_DIR") or raw.get("paths", {}).get("data_dir", "data"))
    # On the shared server each site's settings live in its env file (parentwheretheystand: env/landlords.env), so
    # the address and the launch switch can be set there without changing the repository.
    site = raw.setdefault("site", {})
    if os.environ.get("LANDLORDS_SITE_URL"):
        site["url"] = os.environ["LANDLORDS_SITE_URL"].strip()
    if os.environ.get("LANDLORDS_LAUNCHED"):
        site["launched"] = os.environ["LANDLORDS_LAUNCHED"].strip().lower() in ("1", "true", "yes")
    return Settings(raw=raw, data_dir=data_dir, config_path=path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def load_toml(name: str) -> dict[str, Any]:
    """A file in config/, such as sources.toml."""
    with open(CONFIG_DIR / name, "rb") as fh:
        return tomllib.load(fh)
