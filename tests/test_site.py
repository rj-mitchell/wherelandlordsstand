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
