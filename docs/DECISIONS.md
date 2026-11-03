# Decisions

Product decisions made by the owner. They override anything else in this repo. Add new decisions here once they're
made.

**None of the decisions below is final yet.** They were proposed in the planning session of 3 November 2026 and are
recorded here as proposals. Each becomes a decision only when the owner confirms it; until then, nothing is built that
depends on one being final.

## Made

| # | Topic | Decision |
|---|---|---|
| 9 | Ombudsman data, for now | The Ombudsman's landlord tables are used while its reuse terms are confirmed (owner, 3 November 2026). **To do:** send the Ombudsman the drafted email asking for its reuse terms and attribution, home numbers per landlord, and Table 6; record the answer here. |

## Proposed (awaiting the owner)

| # | Topic | Proposal |
|---|---|---|
| 1 | Name | **Where Landlords Stand**, a working title. It may change to make "social housing" clear. |
| 2 | No league table | No single overall ranking of landlords. Only pillar bands (top quarter, upper middle, lower middle, bottom quarter within a peer group) and the regulator's own grade. |
| 3 | Coverage | England, landlords with **1,000 or more homes** (those that must submit Tenant Satisfaction Measures). Smaller landlords get a "not covered" message that explains the threshold. |
| 4 | Councils | Council landlords get full profiles, linking to Where Councils Stand. |
| 5 | Building safety | Building safety checks (BS01–BS05) are shown as "all checks done" or "gaps in N% of homes", outside the ranking. |
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
