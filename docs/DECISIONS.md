# Decisions

The product decisions for Where Landlords Stand, numbered in the order they were made, each with who made it and
when. Where another document disagrees with one of these, the decision stands. A new decision goes at the end with
the next number; when one replaces another, the old one keeps a line saying which replaced it.

## Ground rules

Set by the owner when the project began (3 November 2026):

- Every figure shown traces to a source file and year. A guess is never presented as data.
- Readers are never told to avoid or refuse a landlord: refusing an offer can cost an applicant their priority.
- Only published figures are used, and a publisher's figure is never changed by us.
- No landlord logos. Names only.
- Fetching is done as a good citizen: one request at a time, at least a second apart, with a user agent that names
  the project, and every response kept so it is fetched once.
- The repository is public, like the sister sites'. The code is under the AGPL-3.0, as theirs is.

## 1. Name and domain

Where Landlords Stand, at wherelandlordsstand.com (owner, 5 November 2026). The charity's hub links to
www.wherelandlordsstand.com, which Cloudflare redirects to the bare domain. The contact address is
admin@wherelandlordsstand.com.

## 2. No league table

There is no single overall ranking of landlords. A landlord is shown only in bands within its peer group (top
quarter, upper middle, lower middle, bottom quarter) for overall satisfaction and each pillar, with the regulator's
own grade beside them (owner, 3 November 2026). docs/METHOD.md explains the bands.

## 3. Coverage

England, landlords with 1,000 or more homes: those in the latest Tenant Satisfaction Measures data. Smaller
landlords get a "not covered" message that explains the threshold (owner, 3 November 2026).

## 4. Councils

Council landlords get full profiles, and link to their page on Where Councils Stand
(wherecouncilsstand.com/councils/<GSS code>) where that site covers the council (owner, 3 November 2026).

## 5. Building safety

The building safety checks (BS01 to BS05) are shown outside the bands: "all done" when every check that applies is
published as 100%, otherwise each check with the published share of homes that had it (owner, 3 November 2026). The
share is shown as published, because "gaps in N% of homes" would mean subtracting from a published figure.

## 6. No AI

No AI in version 1: the site publishes no AI-written text, uses no AI service and installs no AI library (owner,
3 November 2026). `tests/test_dependencies.py` fails if an AI library is ever installed.

## 7. Corrections

Our own processing errors are fixed and listed on the corrections page. Publishers' figures are never changed by us
(owner, 3 November 2026).

## 8. Owner

A project of Where They Stand (wheretheystand.uk), like the sister sites (owner, 3 November 2026).

## 9. Ombudsman data, for now

The Ombudsman's landlord tables are used while its reuse terms are confirmed (owner, 3 November 2026). Still open:
send the Ombudsman the drafted email asking for its reuse terms and attribution, the number of homes per landlord,
and its empty Table 6, and record the answer here (docs/BETA.md).

## 10. Ombudsman figures

Only the Ombudsman's own published figures are shown: findings, the share found at fault (its maladministration
rate), severe findings and compensation. We work out no rate per 1,000 homes, because the Ombudsman doesn't publish
one (owner, 3 November 2026).

## 11. Licence for our own work

Our own work (the text we write, the bands, peer groups, homes by council area and the method) is under CC BY 4.0,
as on Where MPs Stand. Publishers' figures stay under their own terms. The name and mark are not covered (owner,
3 November 2026).

## 12. Public alpha

The site is public at wherelandlordsstand.com, in alpha, and says so with a banner on every page (owner,
6 November 2026). New pages from the weekly update go live only when the owner approves them by email. Beta needs
three gates: a review of the method, testing with applicants and an adviser's sign-off of the wording
(docs/BETA.md). The launch switch (`[site] launched`) only lets search engines in, and was turned on in November 2026
(docs/DEPLOY.md, "The launch switch").

## 13. The alpha banner's wording

The banner follows the family's shape: one sentence, then a link to the report form (17 November 2026, with family
kit 2.0).

## 14. The mark

The site's picture mark is a front door swung wide towards the reader, its panels, letterbox and knob in view and the
hall lit behind it, on the family's rounded roof-slate tile (`#40484D`) with a fine gilt edge (`#D9BC72`), drawn in
ivory (`#F3EAD6`). The owner chose it on 6 November 2026. It has no book, because the book is already the spine in
"A Where They Stand project", and it must stay distinct from Where Councils Stand's town hall. docs/DESIGN.md, "The
mark", describes it.

## 15. Corrections and the right of reply

The charity's impartiality policy, section 7, is built into the site, in the family glossary's words (owner,
12 November 2026). The policy's own figures (150 words, 5 and 20 working days, three months) are used as they stand.

- Corrections cover everything the site says about a landlord, not only its figures: how its grade and bands are
  shown, its peer group, how its names are matched and its companies grouped, mergers, the homes listed in each area
  and the compare page.
- The report form offers the policy's routes ("Something is wrong", "You've been characterised unfairly"), a
  person's details to remove (dealt with first) and anything else. It works without JavaScript.
- "If you're named" (`/named/`) explains the routes, what a statement can say and how it is shown, how the sender is
  checked, the response times (a reply within 5 working days and a decision within 20), and how to appeal.
- A landlord can send a statement of up to 150 words. The owner confirms who sent it, then publishes it as written
  or declines it with reasons. A statement is never edited, so one over a limit is refused and the sender told why,
  never cut to fit. Every decision and its reason is logged.
- A published statement goes on the live pages at once, beside its item and on the landlord's own page, headed
  "Statement from [name], [date]" and marked as the landlord's own words. It is never part of the figures: search,
  the downloads, the bands and the checks never see it (`tests/test_statements.py`).

docs/OPERATIONS.md, "Readers' reports, statements and missed searches", says how it works.

## 16. The family's shared package

The parts every Where They Stand site shares come from the charity's shared package, wts-core: settings, the state
database, the limit on posts, readers' reports and the right of reply, backups, and the commands for them (owner,
13 November 2026). It is installed as the wheel of a tagged release, without its AI part (decision 6). Everything
about landlords stays here: the data, the method, the pages and every word a reader sees.

The site's behaviour before the move was recorded in `tests/golden/`, and the tests check that the site still gives
it, with each intended difference named. Readers saw three changes: two sentences of the privacy page and one on "If
you're named" now say what the code does (a statement's email address is deleted three months after the statement
is withdrawn, declined or removed; backups are kept for up to two months), and a statement's markup asks search
engines not to quote it as the site's own words. The site's old tables are kept for the way back until 1 February
2027 (docs/OPERATIONS.md, "Going back, and coming forward again").

## 17. Hiding a landlord's page while a concern is decided

The impartiality policy says an item is hidden, with a note, while a concern about it is decided (7.3). Here the item
is a landlord's page (owner, 15 November 2026). Hiding takes effect at once, with no rebuild or approval, and
`landlords unhide` puts everything back exactly. While hidden, the page shows only the landlord's name, a sentence
saying it is hidden and the note; the landlord is left out of every list, search, the compare page, the sitemap and
the downloads. Pages that name it for their own reasons, and bands worked out with it among its peers, are left as
they are. docs/OPERATIONS.md, "Hiding a landlord's page while a concern is decided", has the details.

Decided at the same time: the corrections page's list of fixes also shows the public note given when a report is
closed, and never anything a reporter typed.

## 18. wts-core 0.3.0

The site went live on wts-core 0.3.0, so that it was deployed onto the shared package once (November 2026). Not
taken from 0.3.0, as this site does not need them: the package's `would-lapse` command (the site's own
`landlords lapsing` says the same), the check route's weekly figures and the privacy check of briefings (this site
has no briefings), and the notice about older command names (this site keeps its own).

## 19. Titles, descriptions and links between pages

Search results showed most pages under the same few words (November 2026): every area's description was "N landlords
we cover own homes in this area.", and a landlord's page didn't say what it holds for people who search for a
landlord's "reviews" or "complaints". So (19 November 2026):

- A landlord's title is "[name]: tenant satisfaction and complaints", and its description is made only from figures
  its page shows, in the page's terms: the regulator's grade and its month, overall satisfaction and its band among
  similar landlords, and the Ombudsman's latest share of findings at fault, as many as fit in 160 characters. The
  word "reviews" is not used: the tenant survey is the regulator's measure, not reviews.
- An area's title is "Housing associations in [area]", or "Housing associations and council landlords in [area]"
  where a council we cover owns homes there; its description gives how many landlords we cover own rented homes
  there and which owns the most.
- A title ends "| Where Landlords Stand" only where that keeps it to 70 characters.
- A landlord's page links to the council areas where it owns homes, and to up to six landlords in its group of
  similar landlords, those nearest it in size (the number of tenants in its survey, which the groups are made by).
  The order is by size only, never by any result, so it is not a ranking (decision 2).

The wording is in `config/wording.toml` ([profile], [similar], [area]).
