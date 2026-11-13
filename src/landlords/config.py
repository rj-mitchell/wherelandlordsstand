"""The site's settings: config/settings.toml, read by the Where They Stand sites' shared loader (wts-core,
``wts_core.settings``), and the facts about this site that are fixed in its code.

The loader reads config/settings.toml (or the file named by ``LANDLORDS_CONFIG``), then ``settings.local.toml`` in
the data folder if there is one, then the two settings the server keeps in deploy/.env: ``LANDLORDS_SITE_URL`` and
``LANDLORDS_LAUNCHED`` (docs/LAUNCH.md). The data folder is ``LANDLORDS_DATA_DIR``, else ``[paths] data_dir``.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path
from typing import Any

from wts_core import settings as core

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
STATIC_DIR = REPO_ROOT / "data_static"


def _version() -> str:
    try:
        return metadata.version("landlords")
    except metadata.PackageNotFoundError:      # run from the source without being installed
        return "0"


SITE = core.Site(
    name="Where Landlords Stand",
    package="landlords",
    env_prefix="LANDLORDS",           # LANDLORDS_DATA_DIR, LANDLORDS_CONFIG, LANDLORDS_B2_BUCKET, LANDLORDS_CHECK_TOKEN…
    root=REPO_ROOT,
    hosts=("wherelandlordsstand.com", "www.wherelandlordsstand.com"),
    state_file="state.db",
    version=_version(),
    # On the server the site's settings live in deploy/.env (never in git), so the address and the launch switch can
    # be set there without changing the repository: LANDLORDS_SITE_URL sets [site] url, and LANDLORDS_LAUNCHED
    # ("1", "true" or "yes") sets [site] launched.
    env_settings=(
        core.EnvSetting("SITE_URL", "site", "url"),
        core.EnvSetting("LAUNCHED", "site", "launched", "flag"),
    ),
)


class Settings(core.Settings):
    """The shared package's settings, with this site's own accessors."""

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


def load_settings(config_path: str | Path | None = None, env: Mapping[str, str] | None = None) -> Settings:
    settings = core.load_settings(Settings, SITE, config_path, env)
    settings.raw.setdefault("site", {})        # there even in a file without one, as this site's code expects
    return settings


def load_toml(name: str) -> dict[str, Any]:
    """A file in config/, such as sources.toml."""
    with open(CONFIG_DIR / name, "rb") as fh:
        return tomllib.load(fh)
