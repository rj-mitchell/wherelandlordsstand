"""Readers' reports and statements from landlords (the charity's impartiality policy, section 7; docs/DECISIONS.md,
15), kept by the Where They Stand sites' shared package (wts-core, ``wts_core.replies``; its docs/adr/0008).

The package owns the rules and the rows: what a statement may be, its life (pending, then published or declined; a
published one withdrawn by its author or removed by us), the log of every decision, and the deleting of email
addresses in time. This file is what the site passes in:

* ``Items``: where a statement may sit on this site. A landlord's page, one part of it (the grade, the bands, the
  Ombudsman's figures, the safety checks), or a council area's page that lists the landlord.
* ``RULES``: this site's limits (a statement of 3 to 150 words and up to 2,000 characters, a report of up to 4,000),
  and the kinds of report its form sends.
* ``messages()``: every word a sender can be shown.

How a statement looks on the pages, and where it is placed, is in src/landlords/statements.py. Nothing about a
visitor is passed to the package: the site counts nobody's reports or statements, and keeps no visitor code.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.replies import Item, NotDone, Refused, Replies, ReplyMessages, ReplyRules
from wts_core.state import StateDB

from landlords.config import SITE, Settings, load_toml
from landlords.publish import site_dir

# The pages a statement can sit beside: a landlord's page, and a council area's page (which lists landlords)
PAGE = re.compile(r"^(landlords|areas)/([a-z0-9][a-z0-9-]*)/?(?:index\.html)?$")
# The parts of a landlord's "Before you bid" card a statement can sit beside, by the id of each part's heading. A
# statement about anything else on the page (its names, a merger, the figures, the areas) sits after the card.
PARTS = ("grade", "bands", "ombudsman", "safety")
# The routes of the charity's impartiality policy (section 7.1) on the report form, by the family glossary's names
# (config/wording.toml, [corrections] kinds). The third route, a statement, has its own form. "takedown" is a request to
# remove a person's details, dealt with first. A report from an older copy of the form has no kind.
KINDS = ("wrong", "unfair", "takedown", "other")
# ?kind= and the posted value also accept the words the sister sites use, so a link made for one of them still works
KIND_ALIASES = {"correction": "wrong", "error": "wrong", "mistake": "wrong", "complaint": "unfair",
                "general": "other"}

RULES = ReplyRules(
    min_words=3, max_words=150, max_chars=2000, name_max=120, role_max=200, link_max=300, email_max=200,
    # the package can limit how many one visitor sends in a day; this site passes it no visitor, so these never apply
    daily_statements=5, daily_reports=10,
    about_required=True,               # a statement is shown on its landlord's own page too: which landlord?
    report_kinds={**{k: k for k in KINDS}, **KIND_ALIASES},
    report_kind_required=False,        # a word that is none of them: kept, with no kind
    report_min=1, report_max=4000, page_max=300, contact_max=200,
    email_kept_months=3,               # after a statement is withdrawn, declined or removed (the privacy page)
)


def report_kind(value: str) -> str:
    """The kind of a report, from the form or a link's ?kind=: one of KINDS, or "" if it is none of them."""
    return RULES.report_kinds.get(value.strip().lower(), "")


@lru_cache(maxsize=1)
def messages() -> ReplyMessages:
    """Every word a sender can be shown. A statement's heading and the line under it are the family glossary's, from
    config/wording.toml ([statement]), where the pages take them from too."""
    w = load_toml("wording.toml")
    return ReplyMessages(
        too_few_words="Please write the statement: a sentence or more.",
        too_many_words="A statement can be up to {max} words. This one is {n}.",
        too_many_chars="A statement can be up to {max:,} characters. This one is {n:,}.",
        name_missing="Please give the name the statement is from.",
        name_too_long="Your name can be up to {max:,} characters. This one is {n:,}.",
        role_missing="Please give your role and the landlord you speak for, for example \"Chief executive, Example "
                     "Housing\".",
        role_too_long="Your role can be up to {max:,} characters. This one is {n:,}.",
        bad_link="The link to the record should be a full web address, starting https://.",
        link_too_long="The link to the record can be up to {max:,} characters. This one is {n:,}.",
        bad_email="Please give an email address, so we can confirm who the statement is from.",
        item_not_shown="We couldn't find that page on the site. Please copy its address from your browser.",
        # never shown: no visitor is counted (see RULES)
        daily_statements="Thank you, we have your statements. Please email us if there is more to add.",
        daily_reports="Thank you, we have your reports. Please email us if there is more to add.",
        report_kind="please say what kind of problem it is",     # never shown: a report with no kind is kept
        report_too_short="please say what is wrong",
        # the form stops at these lengths, so only a post made some other way meets them: refused, where what was
        # too long used to be cut to fit and kept
        report_too_long="the report is too long: it can be up to {max:,} characters, and this one is {n:,}",
        contact_too_long="the email address is too long: it can be up to {max:,} characters",
        # the reason recorded for a statement nobody decided in three months; its sender is told if they ask
        lapsed="No decision was made in time; please send it again",
        heading=w["statement"]["heading"], disclaimer=w["statement"]["endorsed"],
        record_link=w["statement"]["record"], site=w["site"]["name"])


def beside(page: str, part: str = "") -> str:
    """What the statement form sent, as one address: the page's own, with the part of it chosen in the form's own
    field, which comes before any #part in the address pasted."""
    page, part = (page or "").strip()[:RULES.page_max], (part or "").strip()[:20].strip().lower()
    if not part:
        return page
    return page.split("#", 1)[0] + (f"#{part}" if part in PARTS else "")


class Items:
    """Where a statement may sit on this site (``wts_core.replies.Items``)."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def resolve(self, pasted: str) -> Item:
        """The page a statement is about, from what someone pasted (a full address, or a path):
        "landlords/abri-group/", with its part ("grade") from the address's #fragment. The landlord is known from
        its own page's address, and for an area's page is set by the owner when publishing."""
        address = (pasted or "").strip()
        if "://" not in address:            # "wherelandlordsstand.com/landlords/…", or a path
            host = address.split("/")[0]
            address = "https://" + (address if host in SITE.hosts else f"{SITE.hosts[0]}/" + address.lstrip("/"))
        parsed = urlparse(address)
        found = PAGE.match(parsed.path.lstrip("/")) if parsed.hostname in SITE.hosts else None
        if not found:
            raise Refused("Please give the address of a page on wherelandlordsstand.com that names your landlord: "
                          "its own page (with /landlords/ in it), or a council area's page (with /areas/ in it).",
                          "bad_item")
        kind, slug = found.groups()
        part = (parsed.fragment or "").strip().lower()
        return Item(address=f"{kind}/{slug}/", about=slug if kind == "landlords" else None,
                    part=part if kind == "landlords" and part in PARTS else "")

    def shown(self, item: Item) -> bool:
        """Whether the page is on the live site."""
        return (site_dir(self.settings) / item.address / "index.html").is_file()


def landlord(settings: Settings, slug: str) -> str:
    """The landlord a statement speaks for, as the owner typed it (its slug), if its page is on the site."""
    slug = (slug or "").strip()
    if not (site_dir(settings) / "landlords" / slug / "index.html").is_file():
        raise ValueError(f"no landlord's page landlords/{slug}/ on the site")
    return slug


class OwnersDesk:
    """The shared package's desk as the owner's commands use it, with one check of this site's own before a
    statement is published: the landlord it would be published for (the one the owner names, else the one its page
    names) must still have a page on the site. A statement is shown on its landlord's own page, and a landlord's page
    can go between a statement being sent and being decided (a merger, say). Everything else is the package's,
    untouched."""

    def __init__(self, replies: Replies, settings: Settings):
        self._replies, self._settings = replies, settings

    def publish(self, sid: int, *, checked: str, about: str | None = None) -> None:
        waiting = self._replies.statement(sid)
        # the package's own refusals come first, in its order: no such statement, not waiting, no note of how the
        # sender was confirmed
        if waiting and waiting["status"] == "pending" and (checked or "").strip():
            speaks_for = (about or "").strip() or waiting["about"]
            if speaks_for:
                try:
                    landlord(self._settings, speaks_for)
                except ValueError as exc:
                    raise NotDone(str(exc)) from exc
        self._replies.publish(sid, checked=checked, about=about)

    def __getattr__(self, name: str):
        return getattr(self._replies, name)


def open_replies(settings: Settings, db: StateDB | None = None, clock: Clock = SYSTEM_CLOCK) -> Replies:
    """Reports and statements, for the site's endpoints, its pages and the owner's commands alike."""
    from landlords.state import open_state

    return Replies(db or open_state(settings, clock), items=Items(settings), rules=RULES, messages=messages(),
                   clock=clock)
