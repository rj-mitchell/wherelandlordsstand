# Decisions

Product decisions made by the owner. They override anything else in this repo. Add new decisions here once they're
made.

All the decisions proposed in the planning session of 3 November 2026 have now been confirmed by the owner.

## Made

| # | Topic | Decision |
|---|---|---|
| 1 | Name and domain | **Where Landlords Stand**, at **wherelandlordsstand.com** (proposed as a working title, 3 November 2026; the domain is registered and the site will go there, owner, 5 November 2026). The charity's hub links to www.wherelandlordsstand.com, which Cloudflare redirects to the bare domain. Contact: admin@wherelandlordsstand.com (owner, 5 November 2026). |
| 2 | No league table | No single overall ranking of landlords. Only bands within a peer group (top quarter, upper middle, lower middle, bottom quarter) for overall satisfaction and each pillar, with the regulator's own grade beside them (owner, 3 November 2026). |
| 3 | Coverage | England, landlords with **1,000 or more homes**: those in the latest Tenant Satisfaction Measures data. Smaller landlords get a "not covered" message that explains the threshold (owner, 3 November 2026). |
| 4 | Councils | Council landlords get full profiles, linking to their page on Where Councils Stand (wherecouncilsstand.com/councils/<GSS code>) where that site covers the council (owner, 3 November 2026). |
| 5 | Building safety | Building safety checks (BS01–BS05) are shown outside the ranking: "all done" when every check that applies is published as 100%, otherwise each check with the published share of homes that had it (owner, 3 November 2026). The share is shown as published rather than as "gaps in N%", which would mean subtracting from a published figure. |
| 6 | No AI | No AI in version 1, and no Anthropic API key (owner, 3 November 2026). |
| 7 | Corrections | Our own processing errors are fixed and logged. Publishers' figures are never changed by us (owner, 3 November 2026). |
| 8 | Owner | A project of **Where They Stand** (wheretheystand.uk), like the sibling sites (owner, 3 November 2026). |
| 9 | Ombudsman data, for now | The Ombudsman's landlord tables are used while its reuse terms are confirmed (owner, 3 November 2026). **To do:** send the Ombudsman the drafted email asking for its reuse terms and attribution, home numbers per landlord, and Table 6; record the answer here. |
| 10 | Ombudsman figures | Only the Ombudsman's own published figures are shown: findings, the share found at fault (its maladministration rate), severe findings and compensation. No rate per 1,000 homes is worked out by us, because the Ombudsman doesn't publish one (owner, 3 November 2026). |
| 11 | Licence for our own work | Our own work (the text we write, bands, peer groups, homes by council area, the method) is licensed under **CC BY 4.0**, as on Where MPs Stand. Publishers' figures stay under their own terms; the name and mark are not covered (owner, 3 November 2026). |

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
