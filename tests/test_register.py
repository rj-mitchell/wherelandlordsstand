from landlords import register
from landlords.area import owner_map
from landlords.register import Resolver, display_name, normalise, slugify


def test_normalise_follows_the_brief():
    assert normalise("Town & Country Housing") == "town and country housing"
    assert normalise("Abri Group Limited") == "abri"
    assert normalise("Abbeyfield Society  (The)") == normalise("The Abbeyfield Society") == "abbeyfield society"
    assert normalise("Hyde Housing Association Limited") == "hyde"
    assert normalise("Metropolitan Thames Valley Housing (MTV)") == "metropolitan thames valley housing mtv"


def test_display_names_and_slugs():
    assert display_name("Abri Group Limited") == "Abri Group"
    assert display_name("Abbeyfield Society (The)") == "The Abbeyfield Society"
    assert display_name("Sage Homes RP Limited") == "Sage Homes RP"
    assert slugify("The Guinness Partnership") == "guinness-partnership"
    assert slugify("Bournemouth, Christchurch and Poole Council") == "bournemouth-christchurch-and-poole-council"


def _register(static, landlords, aliases=()):
    register.write_csv(register.LANDLORDS_CSV, landlords, register.LANDLORD_FIELDS)
    register.write_csv(register.ALIASES_CSV, list(aliases), register.ALIAS_FIELDS)


def test_resolver_prefers_exact_and_active_names_and_stops_on_a_tie(static):
    _register(static, [
        {"id": "4878", "legal_name": "Peabody Trust", "status": "active"},
        {"id": "L0014", "legal_name": "Peabody Trust", "status": "deregistered"},
        {"id": "L4123", "legal_name": "Orbit Group Limited", "status": "active"},
        {"id": "L4060", "legal_name": "Orbit Housing Association Limited", "status": "active"},
        {"id": "4789", "legal_name": "Platform Housing Group Limited", "status": "active"},
        {"id": "5084", "legal_name": "Platform Housing Limited", "status": "active"},
        {"id": "LH4087", "legal_name": "Clarion Housing Group Limited", "status": "active"},
        {"id": "4865", "legal_name": "Clarion Housing Association Limited", "status": "active"},
    ], [{"landlord_id": "L4123", "alias": "Orbit Housing", "kind": "short", "source": "test"},
        {"landlord_id": "LH4087", "alias": "Clarion", "kind": "short", "source": "test"}])
    r = Resolver()
    assert r.resolve("Peabody Trust") == ("4878", "exact name")
    assert r.resolve("Orbit Group Limited") == ("L4123", "exact name")
    assert r.resolve("Orbit Housing") == ("L4123", "alias")
    assert r.resolve("Clarion") == ("LH4087", "alias")
    # a short alias must not capture another company whose name normalises the same way
    assert r.resolve("Clarion Housing Association Limited") == ("4865", "exact name")
    lid, why = r.resolve("Platform Housing")  # both normalise to "platform housing": a person decides
    assert lid == "" and why.startswith("ambiguous")
    assert r.resolve("Nobody Homes") == ("", "no match")


def test_accept_adds_only_rows_marked_yes(static, tmp_path):
    _register(static, [{"id": "L0726", "legal_name": "Metropolitan Housing Trust Limited", "status": "active"}])
    review = tmp_path / "review.csv"
    register.write_csv(review, [
        {"name_published": "Metropolitan Thames Valley Housing (MTV)", "source": "Ombudsman", "candidate_id": "L0726",
         "accept": "yes", "kind": "trading"},
        {"name_published": "Something else", "source": "Ombudsman", "candidate_id": "L0726", "accept": ""},
    ], register.REVIEW_FIELDS)
    assert register.accept(review) == 1
    assert [a["alias"] for a in register.aliases()] == ["Metropolitan Thames Valley Housing (MTV)"]


def test_companies_roll_up_to_the_nearest_profiled_landlord():
    parents = {"LH0391": "L4240", "SUB2": "LH0391", "LONE": "", "CHILD": "NOTPROFILED"}
    owners = owner_map(parents, {"L4240", "OWN"}, {"LH0391", "SUB2", "L4240", "OWN", "LONE", "CHILD"})
    assert owners["LH0391"] == ("L4240", "parent")
    assert owners["SUB2"] == ("L4240", "parent")
    assert owners["L4240"] == ("L4240", "itself")
    assert owners["OWN"] == ("OWN", "itself")
    assert owners["LONE"] == ("", "")
    assert owners["CHILD"] == ("", "")
