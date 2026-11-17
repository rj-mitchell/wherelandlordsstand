# Contributing

Thank you for helping. To report a wrong figure or a problem with the site, the quickest route is the
[corrections page](https://wherelandlordsstand.com/corrections/). Issues and pull requests on GitHub are also welcome.

## Setting up

You need [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run landlords fetch && uv run landlords load && uv run landlords build   # optional: the real data and pages
uv run landlords serve                                                     # http://127.0.0.1:8000/
```

## Before you open a pull request

Run the same checks as CI:

```bash
uv sync --frozen
uv run ruff check .
uv run pytest
```

`tests/test_data.py` runs only once the data has been loaded and the pages built. If you change the pages or the
stylesheet, also run the accessibility check against a running `landlords serve`
(`node scripts/a11y.mjs http://127.0.0.1:8000`, with Node 22, Playwright and axe-core).

## Style

- Write in plain British English, in sentence case, with dates in the form 6 November 2026.
- Every sentence a reader sees lives in `config/wording.toml`, `config/pages.toml` or `config/rights.toml`, written
  for a reading age of about 9. Wording shared across the sites follows the Where They Stand family style guide
  (`family/GLOSSARY.md` in the charity's private repository).
- Never change a publisher's figure. A figure shown on the site must trace to a source file and year.
- Don't edit `src/landlords/family/`; it is a copy of the family kit (see [docs/DESIGN.md](docs/DESIGN.md)).
- Code is checked with ruff (`pyproject.toml`). Keep comments short and about the code as it is.
- A product decision goes in [docs/DECISIONS.md](docs/DECISIONS.md).

## Commit messages

Write a short summary line in plain words, then, if needed, a few sentences on what changed and why.

## Licence

By contributing you agree that your code is licensed under the AGPL-3.0 and your text under CC BY 4.0, as set out in
the [README](README.md#licence).
