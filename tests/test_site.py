"""The pages' shared parts, without the real data."""

from types import SimpleNamespace

from landlords.profile import source_order


def test_sources_from_the_same_source_and_period_are_numbered_the_same_way_every_time():
    sources = {"b1": {"source": "stock", "period": "2025/26", "title": "Private registered providers data release"},
               "a2": {"source": "stock", "period": "2025/26", "title": "Local authority registered provider data release"},
               "c3": {"source": "grades", "period": "2025/26", "title": "Regulatory judgements"}}
    data = SimpleNamespace(sources=sources)
    for used in ({"b1", "a2", "c3"}, {"c3", "a2", "b1"}, ["a2", "c3", "b1"], ["b1", "c3", "a2"]):
        assert sorted(used, key=lambda s: source_order(data, s)) == ["c3", "a2", "b1"]


def test_the_family_kit_is_copied_in_unedited():
    """src/landlords/family/ is the kit as its sync script wrote it (docs/DESIGN.md): its VERSION file carries a hash
    of every other file, made as the script makes it, so an edit to the copy fails here. To change it, change the kit
    and sync again."""
    import hashlib
    import re

    from landlords.site import FAMILY

    version = (FAMILY / "VERSION").read_text()
    assert "site landlords" in version and "base /family/" in version
    digest = hashlib.sha256()
    for path in sorted(p.relative_to(FAMILY).as_posix() for p in FAMILY.rglob("*") if p.is_file()):
        if path != "VERSION":
            digest.update(path.encode() + b"\0" + (FAMILY / path).read_bytes() + b"\0")
    assert re.search(r"^sha256 ([0-9a-f]{64})$", version, re.M)[1] == digest.hexdigest()


def test_the_kit_partials_name_their_files_at_their_fingerprinted_addresses(tmp_path):
    from landlords import site

    names = site.write_assets(tmp_path)
    parts = site.family_parts(names)
    head = parts["head"].replace(site.UP, "../")
    assert f'href="../{names["fonts.css"]}"' in head and f'href="../{names["family.css"]}"' in head
    assert f'content="https://wherelandlordsstand.com/{names["card.png"]}"' in head
    assert "/family/" not in head and "<script" not in "".join(parts.values())
    assert 'class="wts-endorse"' in parts["endorsement"] and 'class="wts-shelf"' in parts["shelf"]


def test_sentences_with_links():
    from landlords.site import fill_html, rich

    assert rich("Read <this> [the code](https://example.org/a?b=1&c=2).") == (
        'Read &lt;this&gt; <a href="https://example.org/a?b=1&amp;c=2">the code</a>.')
    assert rich("Use the [form](corrections/index.html).", "../") == (
        'Use the <a href="../corrections/index.html">form</a>.')
    assert rich("Email [a@b.org](mailto:a@b.org).") == 'Email <a href="mailto:a@b.org">a@b.org</a>.'
    assert fill_html("It's {link}, or {x}.", link="<a>here</a>", x="<b>") == "It&#x27;s <a>here</a>, or <b>."
