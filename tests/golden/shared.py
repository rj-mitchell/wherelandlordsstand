"""What the golden recorder (record.py, run on the site's code as it was before wts-core) and the parity tests
(tests/test_parity.py, run on the code as it is now) both need: the pages the scenarios run on, a simulated
Backblaze B2, and the scripts themselves. Nothing here imports the site's code, so it reads the same under either.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

GOLDEN = Path(__file__).parent
START = "2026-11-13T09:00:00+00:00"          # where every scenario's clock starts
PARTS = ("grade", "bands", "ombudsman", "safety")
WORDS = "Our survey was carried out after a big change to our repairs service, and we have published newer results."
FORM = {"name": "Jane Example", "role": "Chief executive, Example Housing", "page": "landlords/example-housing/",
        "part": "", "text": WORDS, "link": "https://example.org/results", "email": "jane@example-housing.org.uk"}
LONG = " ".join(["extraordinarily"] * 140)   # within 150 words, but 2,239 characters


def slot(key: str) -> str:
    return f"<!--statements:{key}--><!--/statements:{key}-->"


def landlord_page(name: str, parts=PARTS) -> str:
    """A landlord's page cut down to its slots: one beside each part of the card, one after it."""
    card = "".join(f'<section><h3 id="{p}">{p}</h3><p>Our words.</p>{slot(p)}</section>' for p in parts)
    return f'<h1>{name}</h1><section class="card">{card}</section>{slot("page")}<h2>Figures</h2>'


def fixture_site(data_dir: Path) -> Path:
    """data/site with two landlords' pages (one without the safety part), an area's page, and the thank-you pages."""
    root = data_dir / "site"
    for slug, name, parts in (("example-housing", "Example Housing", PARTS),
                              ("example-council", "Example Council", PARTS[:3])):
        (root / "landlords" / slug).mkdir(parents=True)
        (root / "landlords" / slug / "index.html").write_text(landlord_page(name, parts))
    (root / "areas" / "leeds").mkdir(parents=True)
    (root / "areas" / "leeds" / "index.html").write_text(f'<h1>Leeds</h1><p class="warn">w</p>{slot("page")}')
    (root / "index.html").write_text("<h1>home</h1>")
    for folder in ("corrections", "named"):
        (root / folder).mkdir()
        (root / folder / "thanks.html").write_text("thanks")
    return root


def pages(root: Path) -> dict[str, str]:
    """Every landlord's and area's page under ``root``, by its address."""
    return {p.parent.relative_to(root).as_posix() + "/": p.read_text()
            for p in sorted(root.glob("*/*/index.html")) if p.parts[-3] in ("landlords", "areas")}


def read(name: str):
    return json.loads((GOLDEN / name).read_text())


def write(out: Path, name: str, value) -> None:
    (out / name).write_text(json.dumps(value, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


# ---- settings ------------------------------------------------------------------------------------------------------

SAMPLE_CONFIG = """\
[paths]
data_dir = "{data_dir}"

[fetch]
user_agent = "Sample/1.0"
retries = 2

[coverage]
min_homes = 500
"""
SETTINGS_CASES = [
    {"name": "the real settings file", "config": "real", "env": {}},
    {"name": "the real file, the data folder from the environment (absolute)", "config": "real",
     "env": {"LANDLORDS_DATA_DIR": "<tmp>/elsewhere"}},
    {"name": "the real file, the data folder from the environment (relative)", "config": "real",
     "env": {"LANDLORDS_DATA_DIR": "other/data"}},
    *({"name": f"the real file, LANDLORDS_LAUNCHED={value!r}", "config": "real", "env": {"LANDLORDS_LAUNCHED": value}}
      for value in ("1", "true", "YES", " True ", "no", "0", "false", "launched", " ")),
    {"name": "the real file, the address from the environment", "config": "real",
     "env": {"LANDLORDS_SITE_URL": " https://example.test/ ", "LANDLORDS_LAUNCHED": "true"}},
    {"name": "the real file, an empty address in the environment", "config": "real", "env": {"LANDLORDS_SITE_URL": ""}},
    {"name": "a sample file with no [site], named by LANDLORDS_CONFIG", "config": SAMPLE_CONFIG,
     "data_dir": "<tmp>/sample-data", "env": {}},
    {"name": "a sample file with a relative data folder", "config": SAMPLE_CONFIG, "data_dir": "var/data", "env": {}},
    {"name": "a sample file with no [site], and both settings in the environment", "config": SAMPLE_CONFIG,
     "data_dir": "var/data", "env": {"LANDLORDS_SITE_URL": "https://example.test", "LANDLORDS_LAUNCHED": "1",
                                     "LANDLORDS_DATA_DIR": "<tmp>/from-env"}},
    {"name": "a sample file given as an argument", "config": SAMPLE_CONFIG, "data_dir": "var/data", "env": {},
     "as_argument": True},
]

# ---- the limit on posts -------------------------------------------------------------------------------------------

A, B = "203.0.113.7", "2001:db8::7"
LIMITER_SCRIPT = (
    [[0.0, A]] * 11 + [[0.0, B], [0.0, ""]] + [[30.0, A], [59.9, A], [60.0, A], [60.1, A]] + [[60.1, A]] * 10
    + [[60.2, B]] * 10 + [[120.0, B], [120.3, B], [120.3, B], [200.0, A], [200.0, B]]
)

# ---- off-site copies: a simulated Backblaze B2 ------------------------------------------------------------------

B2_ENV = {"LANDLORDS_B2_BUCKET": "wts-backups", "LANDLORDS_B2_KEY_ID": "kid", "LANDLORDS_B2_APPLICATION_KEY": "secret"}


class FakeB2:
    def __init__(self, bucket="wts-backups", fail_uploads=0, can_delete=True):
        self.bucket, self.fail_uploads, self.can_delete = bucket, fail_uploads, can_delete
        self.files: dict[str, bytes] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("b2_authorize_account"):
            if request.headers.get("authorization") != httpx.BasicAuth("kid", "secret")._auth_header:
                return httpx.Response(401)
            return httpx.Response(200, json={"accountId": "acc", "apiUrl": "https://api.b2.test",
                                             "authorizationToken": "tok",
                                             "allowed": {"bucketId": "b1", "bucketName": self.bucket}})
        assert request.headers.get("authorization") in ("tok", "up"), "every call carries a token"
        body = json.loads(request.content or b"{}") if path.startswith("/b2api") else {}
        if path.endswith("b2_get_upload_url"):
            return httpx.Response(200, json={"uploadUrl": "https://up.b2.test/upload", "authorizationToken": "up"})
        if path == "/upload":
            if self.fail_uploads:
                self.fail_uploads -= 1
                return httpx.Response(503)
            assert request.headers["x-bz-content-sha1"] == hashlib.sha1(request.content).hexdigest()  # noqa: S324
            self.files[request.headers["x-bz-file-name"]] = request.content
            return httpx.Response(200, json={"fileName": request.headers["x-bz-file-name"]})
        if path.endswith("b2_list_file_names"):
            return httpx.Response(200, json={"files": [{"fileName": n, "fileId": f"id-{n}"} for n in sorted(self.files)
                                                       if n.startswith(body["prefix"])]})
        if path.endswith("b2_delete_file_version"):
            if not self.can_delete:
                return httpx.Response(401, json={"code": "unauthorized"})
            del self.files[body["fileName"]]
            return httpx.Response(200, json={})
        return httpx.Response(404)


def b2_client(b2: FakeB2) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(b2))


# Each case: the simulated bucket, the key, the archives sent in turn and how many are kept
OFFSITE_CASES = [
    {"name": "three nights, one upload retried, the newest two kept", "b2": {"fail_uploads": 1}, "keep": 2,
     "days": ["20261010-045200", "20261011-045200", "20261012-045200"]},
    {"name": "a key without delete rights still stores", "b2": {"can_delete": False}, "keep": 1,
     "days": ["20261011-045200", "20261012-045200"]},
    {"name": "a key Backblaze does not accept", "b2": {}, "keep": 60, "days": ["20261012-045200"],
     "env": {"LANDLORDS_B2_APPLICATION_KEY": "wrong"}},
    {"name": "a key for another bucket", "b2": {"bucket": "someone-else"}, "keep": 60, "days": ["20261012-045200"]},
    {"name": "another site's backups in the same bucket are left alone", "b2": {}, "keep": 1,
     "days": ["20261011-045200", "20261012-045200"], "already": ["where-they-stand-2026-10-01.tar.gz"]},
]

# ---- what is sent to the API ------------------------------------------------------------------------------------
# Each step is a request (the clock moves on 61 seconds first, so the limit of ten a minute never bites), until
# "burst", after which the clock stands still.


def _statement(case: str, **fields) -> dict:
    return {"case": case, "post": "/api/statements", "json": {**FORM, **fields}}


def _report(case: str, **fields) -> dict:
    return {"case": case, "post": "/api/corrections", "json": fields}


API_STEPS: list[dict] = [
    _statement("a statement, its page a full address with a part"
               , page="https://www.wherelandlordsstand.com/landlords/example-housing/index.html#bands"),
    {"case": "a statement from the form", "post": "/api/statements", "data": {**FORM, "page": "areas/leeds/"}},
    _statement("the part from the form's own field, over the address's", part="safety",
               page="wherelandlordsstand.com/landlords/example-housing#bands"),
    _statement("a part that is none of the card's, with one in the address", part="figures",
               page="/landlords/example-housing/#bands"),
    _statement("line endings made plain and blank lines closed up", link="",
               text="Line one <b>bold</b>\r\nline two\r\n\r\n\r\n\r\npara two & more"),
    _statement("spaces inside the name and role", name="Jane   Example", role="Chief  executive,  Example Housing"),
    _statement("just within every limit", name="N" * 120, role="R" * 200, link="https://example.org/" + "a" * 280,
               email="a" * 188 + "@example.org", text=" ".join(["a" * 20] + ["b" * 19] * 99)),
    _statement("no name", name=""),
    _statement("a name too long", name="N" * 121),
    _statement("no role", role=" "),
    _statement("a role too long", role="R" * 201),
    _statement("no words", text=""),
    _statement("two words", text="Two words"),
    _statement("151 words", text=" ".join(["word"] * 151)),
    _statement("within 150 words but too many characters", text=LONG),
    _statement("no email address", email=""),
    _statement("not an email address", email="not-an-address"),
    _statement("an email address too long", email="a" * 189 + "@example.org"),
    _statement("no page", page=""),
    _statement("a page on another site", page="https://example.org/landlords/example-housing/"),
    _statement("a page a statement cannot sit beside", page="/compare/"),
    _statement("a page that is not on the site", page="landlords/nobody-at-all/"),
    _statement("a link that is no web address", link="javascript:alert(1)"),
    _statement("a link with a space", link="https://example.org/a b"),
    _statement("a link too long", link="https://example.org/" + "a" * 281),
    _statement("two faults: no name and no words", name="", text=""),
    _statement("two faults: a bad link and a page not on the site", link="nope", page="landlords/nobody-at-all/"),
    _statement("two faults: a bad email address and a bad link", email="nope", link="nope"),
    _statement("the hidden field robots fill in", website="https://spam.example"),
    {"case": "the hidden field, from the form", "post": "/api/statements",
     "data": {**FORM, "website": "https://spam.example"}},
    {"case": "151 words, from the form", "post": "/api/statements", "data": {**FORM, "text": " ".join(["word"] * 151)}},
    {"case": "more than the form can take, from the form", "post": "/api/statements",
     "data": {**FORM, "text": "word " * 5000}},
    _statement("more than the form can take", text="word " * 5000),
    {"case": "a JSON body cut short", "post": "/api/statements", "content": "{not json"},
    {"case": "a JSON list", "post": "/api/statements", "content": '["a", "list"]'},
    {"case": "bytes that are not text", "post": "/api/statements", "content": "\xff\xfe"},
    _report("a report with the sister sites' word for its kind", kind="complaint", page="landlords/x/",
            message="A loaded word", email="reader@example.org"),
    {"case": "a report from the form", "post": "/api/corrections",
     "data": {"kind": "takedown", "message": "My name is on a page", "page": "areas/leeds/"}},
    _report("a report from an older form, with no kind", message="Wrong grade", email="a@b.org"),
    _report("a kind that is none of them", kind="nonsense", message="Something else entirely"),
    _report("an email address with no @ is not kept", kind="wrong", message="Wrong band", email="not-an-address"),
    _report("values that are not text", message=12345, email=None),
    _report("a page longer than its limit is cut", kind="other", message="A long address", page="p" * 301),
    _report("no message", kind="wrong", message="  "),
    _report("a message longer than its limit", kind="wrong", message="m" * 4001),
    _report("an email address longer than its limit", kind="wrong", message="Wrong", email="a" * 190 + "@example.org"),
    _report("the hidden field robots fill in", message="Buy cheap pills", website="https://spam.example"),
    {"case": "the hidden field, from the report form", "post": "/api/corrections",
     "data": {"message": "Buy cheap pills", "website": "https://spam.example"}},
    {"case": "a report cut short", "post": "/api/corrections", "content": "{not json"},
    {"case": "a search that found nothing", "post": "/api/missed", "json": {"q": "Nobody Homes Ltd"}},
    {"case": "a missed search that cannot be read", "post": "/api/missed", "content": "{not json"},
    {"case": "health", "get": "/api/health"},
    {"burst": True},
    *({"case": f"missed search {n} of 11 in a minute", "post": "/api/missed", "json": {"q": "nobody homes"}}
      for n in range(1, 12)),
    _report("too many: a report", message="Wrong grade"),
    _statement("too many: a statement"),
    {"case": "too many: an approval link", "get": "/admin/approve/not-a-token"},
]

# ---- what the owner types ---------------------------------------------------------------------------------------
# Sent first, one each minute: four statements and three reports. Then the owner's command lines, in the shape the
# site had before wts-core (`statements --publish 1`), one each minute. "<tmp>" is the scenario's own folder.

OWNER_SENT: list[dict] = [
    _statement("1: about the landlord's page"),
    _statement("2: about an area's page", page="https://wherelandlordsstand.com/areas/leeds/", name="Sam Officer",
               role="Head of housing, Example Council", link=""),
    _statement("3: beside the bands", page="landlords/example-housing/#bands", link=""),
    _statement("4: to be declined", page="landlords/example-council/", part="safety"),
    _report("1", kind="wrong", page="landlords/x/", message="Wrong grade", email="reader@example.org"),
    _report("2", kind="takedown", message="My name is on a page"),
    _report("3", message="From an older form"),
]
OWNER_FILES = {"new.txt": "Our newer results are published every quarter on our website.",
               "long.txt": " ".join(["word"] * 151), "wide.txt": LONG}
OWNER_COMMANDS: list[list[str]] = [
    ["statements"],
    ["statements", "--publish", "1"],
    ["statements", "--publish", "1", "--checked", "replied from the landlord's own address, 14 Nov"],
    ["statements", "--publish", "2", "--checked", "phoned the council"],
    ["statements", "--publish", "2", "--checked", "phoned", "--landlord", "nobody"],
    ["statements", "--publish", "2", "--checked", "phoned the council", "--landlord", "example-council"],
    ["statements", "--update", "1", "--text-file", "<tmp>/new.txt", "--reason", "the author's new version"],
    ["statements", "--update", "1", "--text-file", "<tmp>/long.txt"],
    ["statements", "--update", "1", "--text-file", "<tmp>/wide.txt"],
    ["statements", "--update", "1", "--name", "N" * 121],
    ["statements", "--update", "1", "--role", "R" * 201],
    ["statements", "--update", "1", "--link", "https://example.org/" + "a" * 281],
    ["statements", "--update", "1"],
    ["statements", "--update", "1", "--link", "", "--reason", "the link has gone"],
    ["statements", "--publish", "3", "--checked", "letter"],
    ["statements", "--withdraw", "3"],
    ["statements", "--withdraw", "3", "--reason", "withdrawn by the author"],
    ["statements", "--publish", "3", "--checked", "again"],
    ["statements", "--decline", "4"],
    ["statements", "--decline", "4", "--reason", "it names a tenant"],
    ["statements", "--decline", "9", "--reason", "no such statement"],
    ["statements", "--log", "1"],
    ["statements", "--log", "3"],
    ["statements", "--all"],
    ["statements"],
    ["reports"],
    ["reports", "--close", "1", "--outcome", "fixed alias"],
    ["reports", "--close", "1", "--outcome", "again"],
    ["reports", "--close", "9"],
    ["reports"],
    ["missed"],
]
