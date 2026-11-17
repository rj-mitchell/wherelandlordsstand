"""Loaders: each reads the newest fetched file for its source and writes tidy tables to data/staging/."""

from __future__ import annotations

from landlords.config import Settings


def run(settings: Settings, only: list[str] | None = None) -> dict[str, dict]:
    from landlords.load import grades, ombudsman, providers, stock, tsm

    # The Ombudsman's names are matched through the register, so it is loaded last.
    steps = {"tsm": tsm.load, "grades": grades.load, "providers": providers.load, "stock": stock.load,
             "ombudsman": ombudsman.load}
    return {name: fn(settings) for name, fn in steps.items() if not only or name in only}
