"""The site on the shared package (wts-core) gives what its own code gave before.

tests/golden/ holds what the site's code gave on 13 November 2026, before the switch, recorded by
tests/golden/record.py from the scripts in tests/golden/shared.py. Each test here plays the same script to the site
as it is now and compares. Where the two differ on purpose, the difference is asserted, with the entry of wts-core's
docs/AS-BUILT.md (or docs/MIGRATION.md) that lists it: nothing is skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "golden"))

import pytest  # noqa: E402
import shared  # noqa: E402

from landlords.config import REPO_ROOT, load_settings  # noqa: E402


def plain(value, tmp: Path):
    """As the recorder wrote it: the scenario's own folder as "<tmp>", the repository as "<root>"."""
    return json.loads(json.dumps(value).replace(str(tmp), "<tmp>").replace(str(REPO_ROOT), "<root>"))


# ---- settings (wts-core docs/MIGRATION.md, 1.1: no difference) -----------------------------------------------------


@pytest.mark.parametrize("case", shared.read("settings.json"), ids=lambda case: case["name"])
def test_settings_resolve_as_before(case, tmp_path):
    tmp = tmp_path.resolve()
    env = {k: v.replace("<tmp>", str(tmp)) for k, v in case["env"].items()}
    argument = None
    if case["config"] != "real":
        path = tmp / "sample.toml"
        path.write_text(case["config"].format(data_dir=case["data_dir"].replace("<tmp>", str(tmp))))
        if case.get("as_argument"):
            argument = path
        else:
            env["LANDLORDS_CONFIG"] = str(path)
    s = load_settings(argument, env)
    assert plain({"raw": s.raw, "data_dir": str(s.data_dir), "config_path": str(s.config_path), "fetch": s.fetch,
                  "raw_dir": str(s.raw_dir), "staging_dir": str(s.staging_dir), "site": s.section("site"),
                  "no_such_section": s.section("no_such_section")}, tmp) == case["gives"]


def test_the_environment_settings_are_read_from_the_real_environment_too(monkeypatch, tmp_path):
    monkeypatch.setenv("LANDLORDS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LANDLORDS_SITE_URL", "https://example.test")
    monkeypatch.setenv("LANDLORDS_LAUNCHED", "yes")
    s = load_settings()
    assert (s.data_dir, s.section("site")["url"], s.section("site")["launched"]) == (
        tmp_path / "data", "https://example.test", True)
    assert s.state_db == tmp_path / "data" / "state.db" and s.site.env_prefix == "LANDLORDS"


def test_a_local_settings_file_in_the_data_folder_is_laid_over_the_repositorys(tmp_path):
    """New with the shared loader (MIGRATION 1.1: "the local layer becomes available; nothing uses it"): the server
    has no such file, so nothing changes there."""
    (tmp_path / "settings.local.toml").write_text('[publish]\nkeep_builds = 9\n')
    s = load_settings(env={"LANDLORDS_DATA_DIR": str(tmp_path)})
    assert s.section("publish")["keep_builds"] == 9 and s.section("publish")["mode"] == "approve"
