"""This site has no AI (docs/DECISIONS.md, 6), so it takes the shared package (wts-core) without its "ai" extra, and
none of the libraries that extra brings is ever installed here."""

import re
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).parents[1]
# what wts-core's "ai" extra installs, and the two heaviest libraries those bring with them
AI_LIBRARIES = {"anthropic", "fastembed", "lancedb", "onnxruntime", "tokenizers"}


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    [wts_core] = [d for d in project["dependencies"] if canonical(d.split("[")[0].split("@")[0].strip()) == "wts-core"]
    return wts_core


def test_the_shared_package_is_taken_without_its_ai_extra():
    name, address = (part.strip() for part in requirement().split("@", 1))
    assert name == "wts-core[cli,offsite]"            # Typer for the shared commands, httpx for off-site copies
    # the wheel of a tagged release, by its address: the Docker image has no git (wts-core docs/adr/0006)
    assert re.fullmatch(r"https://github\.com/rj-mitchell/wts-core/releases/download/v(\d+\.\d+\.\d+)/"
                        r"wts_core-\1-py3-none-any\.whl", address)


def test_no_ai_library_is_locked():
    """uv.lock is what `uv sync --frozen` installs, on the server and in CI."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = {canonical(p["name"]): p for p in lock["package"]}
    assert not AI_LIBRARIES & set(locked)
    assert set(locked["wts-core"]["optional-dependencies"]) == {"cli", "offsite"}
    [ours] = [d for d in locked["landlords"]["dependencies"] if d["name"] == "wts-core"]
    assert sorted(ours["extra"]) == ["cli", "offsite"]
    assert locked["wts-core"]["source"]["url"] == requirement().split("@", 1)[1].strip()


def test_no_ai_library_is_installed():
    """After `uv sync --frozen`, which is how CI and the Docker image install the site."""
    installed = {canonical(d.metadata["Name"]) for d in metadata.distributions()}
    assert "wts-core" in installed and "typer" in installed and "httpx" in installed
    assert not AI_LIBRARIES & installed


def test_the_site_runs_without_them():
    """Every module of the site and every command loads with none of them in reach."""
    import subprocess
    import sys

    code = ("import sys, pkgutil, importlib, landlords\n"
            "for m in pkgutil.walk_packages(landlords.__path__, 'landlords.'): importlib.import_module(m.name)\n"
            "import typer.main; from landlords.cli import app; typer.main.get_command(app)\n"
            "print(sorted({m.split('.')[0] for m in sys.modules}))")
    loaded = set(eval(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout))
    assert "wts_core" in loaded
    assert not AI_LIBRARIES & loaded
