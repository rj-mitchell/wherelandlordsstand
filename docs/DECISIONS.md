# Decisions

Product decisions made by the owner. They override anything else in this repo. Add new decisions here once they're
made.

The decisions under "Proposed" were put forward in the planning session of 3 November 2026 and are not final. Each
becomes a decision only when the owner confirms it; until then, nothing is built that depends on one being final.

## Made

| # | Topic | Decision |
|---|---|---|
| 2 | No league table | No single overall ranking of landlords. Only bands within a peer group (top quarter, upper middle, lower middle, bottom quarter) for overall satisfaction and each pillar, with the regulator's own grade beside them (owner, 3 November 2026). |
| 3 | Coverage | England, landlords with **1,000 or more homes**: those in the latest Tenant Satisfaction Measures data. Smaller landlords get a "not covered" message that explains the threshold (owner, 3 November 2026). |
| 5 | Building safety | Building safety checks (BS01–BS05) are shown outside the ranking: "all done" when every check that applies is published as 100%, otherwise each check with the published share of homes that had it (owner, 3 November 2026). The share is shown as published rather than as "gaps in N%", which would mean subtracting from a published figure. |
| 9 | Ombudsman data, for now | The Ombudsman's landlord tables are used while its reuse terms are confirmed (owner, 3 November 2026). **To do:** send the Ombudsman the drafted email asking for its reuse terms and attribution, home numbers per landlord, and Table 6; record the answer here. |
| 10 | Ombudsman figures | Only the Ombudsman's own published figures are shown: findings, the share found at fault (its maladministration rate), severe findings and compensation. No rate per 1,000 homes is worked out by us, because the Ombudsman doesn't publish one (owner, 3 November 2026). |

## Proposed (awaiting the owner)

| # | Topic | Proposal |
|---|---|---|
| 1 | Name | **Where Landlords Stand**, a working title. It may change to make "social housing" clear. |
| 4 | Councils | Council landlords get full profiles, linking to Where Councils Stand. |
| 6 | No AI | No AI in version 1, and no Anthropic API key. |
| 7 | Corrections | Our own processing errors are fixed and logged. Publishers' figures are never changed by us. |
| 8 | Owner | A project of the Where They Stand Foundation, like the sibling sites. |

## Ground rules from the brief

These come from the owner's brief (3 November 2026) and are followed from the start:

- Every figure shown traces to a source file and year. A guess is never presented as data.
- Readers are never told to avoid or refuse a landlord: refusing an offer can cost an applicant their priority.
- Only published figures are used, and a publisher's figure is never changed by us.
- No landlord logos. Names only.
- Being a good citizen when fetching: one request at a time, at least a second apart, with an identifying user agent,
  and every response kept so it is fetched once.
- The repository is public, like the sibling sites (owner, 3 November 2026). Nothing is deployed until the owner
  says so.
- Code: AGPL-3.0, as the sibling sites, same author.
