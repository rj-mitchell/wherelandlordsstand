# Method: how landlords are compared

For review. Phase 2's gate is that a housing-data reviewer has checked this method. The rules live in
`config/scoring.toml`; `src/landlords/score.py` applies them; the site's method page (`data/site/method/index.html`)
is generated from the same file. Decisions it rests on: docs/DECISIONS.md, 2, 3, 5 and 10.

## What a reader sees

Each profiled landlord's page opens with a "Before you bid" card:

1. A line on every card: "Thinking of turning down an offer? Check your council's rules first. Saying no to an offer
   can affect your place on the housing register." (The site never tells anyone to avoid or refuse a landlord.)
2. Homes: the tenant population in rented homes from its own latest TSM survey.
3. **The regulator's consumer grade** (C1–C4) and its date. Where the landlord itself has none but a registered parent
   does, the parent's grade, named as the group's. Gradings under review and enforcement notices, if any.
4. **Bands among similar landlords** for overall satisfaction (TP01) and three pillars, with arrows for moves since the
   year before. The regulator's notes about the landlord's results, and a note on survey method where it differs from
   its peers'.
5. **The Housing Ombudsman's figures**, as it publishes them, for the latest year, for each registered company in the
   landlord's group that has a report; otherwise a line saying there is no report and why.
6. **Safety checks**: "all done", or each check with the published share of homes that had it.

Below the card: every figure behind the bands, the measures shown but not compared, earlier Ombudsman figures, the
council areas where it has homes, and the list of source files. Every figure links to its file.

## The steps

**1. Peer groups.** Each landlord is compared only within its type (council, or housing association) and size band
(1,000–9,999; 10,000–49,999; 50,000+ homes). Size is the tenant population in the landlord's own TSM survey that year
(rented, shared ownership and combined added together); for the 2 landlords with no survey population (results
excluded), its homes in the 2026 stock return. A group with fewer than 15 landlords is merged with the next band down
(up, for the smallest). A type with fewer than 15 landlords in all (for-profit providers: 4 scored in 2024/25) joins
housing associations.

In 2024/25 that gives four groups: councils with 1,000–9,999 homes (110), councils with 10,000 or more (50, including
the 2 with 50,000+), housing associations and for-profit landlords with 1,000–9,999 homes (125), and housing
associations with 10,000 or more (72, including the 9 with 50,000+).

**2. Results scored.** Rented homes (LCRA). The 2 landlords allowed to report rented and shared ownership together are
scored on those combined results (COMB). A landlord whose survey results were excluded (Cannock Chase, Stoke-on-Trent
in 2024/25) is scored on its management measures for rented homes only. Landlords with only shared owners (3 in
2024/25) are not scored.

**3. Each measure.** Within the peer group, each landlord with a published figure gets a mid-rank percentile: the share
of the group's figures it beats, ties counting half, so the best of n is close to 100 and the worst close to 0,
whether a high or a low figure is better. A measure is scored only if at least 10 peers have a figure. Excluded,
undefined (`[U]`) and missing figures are left out, never counted as zero.

**4. Pillars.** A pillar's score is the median of its measures' percentiles, if the landlord has at least half of them.

| Pillar | Measures |
|---|---|
| Repairs and homes | TP02, TP03, TP04 (satisfaction with repairs, their speed, the home being well maintained); RP01 (homes not meeting the Decent Homes Standard, lower is better); RP02 non-emergency and emergency (repairs done in the landlord's target time) |
| Being heard | TP06, TP07, TP08, TP09 (listens and acts, keeps informed, fair and respectful, complaints handling); CH02 stage one and stage two (complaints answered in time) |
| Neighbourhood | TP10, TP11, TP12 (communal areas, the neighbourhood, anti-social behaviour) |
| Overall satisfaction | TP01, on its own |

**5. Bands.** Overall satisfaction's percentile, and each pillar's score ranked again within the group, are shown only
as four bands: bottom quarter (below 25), lower middle (25–50), upper middle (50–75), top quarter (75 and up). The
re-ranking makes each band hold about a quarter of the group, so "top quarter" means what it says. Nothing is ever
added up into a single ranking.

**6. Trends.** An arrow when a band changed since the previous TSM year, and only if both years were scored on the same
number of measures.

**7. Survey method.** A note where the landlord's predominant survey method differs from its group's most common one.

**Shown, not compared:** TP05 (the home is safe), complaints per 1,000 homes (CH01) and anti-social behaviour cases per
1,000 homes (NM01). Complaints and ASB cases are volumes: a high figure can mean tenants find it easy to complain or
report.

## Worked example: A2Dominion Housing Group (L4240), 2024/25

Peer group: housing associations with 10,000 homes or more (72, itself included). Its survey population: 24,748.

| Measure | Published | Percentile | Band |
|---|---|---|---|
| TP01 overall satisfaction | 60.7% | 6.2 | bottom quarter |
| TP02 repairs | 63.7% | 8.3 | |
| TP03 repair time | 61.1% | 22.2 | |
| TP04 well maintained | 63.8% | 10.4 | |
| RP01 non-decent (lower is better) | 0.2% | 32.6 | |
| RP02 non-emergency in time | 73.9% | 34.0 | |
| RP02 emergency in time | 85.3% | 13.2 | |

Repairs and homes: the median of 8.3, 22.2, 10.4, 32.6, 34.0 and 13.2 is 17.7; ranked again among the 72, that is the
6.2nd percentile: bottom quarter. Being heard (6 of 6 measures) and Neighbourhood (3 of 3) work the same way; both are
bottom quarter. Its survey was mainly by telephone, like its group's, so there is no method note. In 2023/24 it
surveyed mainly by text message.

## Questions for the reviewer

1. **TP05** (the home is safe) isn't in a pillar in the plan. Should it join Repairs and homes?
2. **Size** is the TSM survey population, not homes owned, so that size and results come from the same return.
   Acceptable?
3. **Merging:** the 50,000+ bands are too small for their own groups (9 housing associations, 2 councils), so they are
   compared with 10,000–49,999. For-profit providers are compared with housing associations.
4. **Re-ranking pillar scores** so each band holds a quarter of the group, against banding the median percentile
   directly (which bunches pillar scores in the middle bands).
5. **Churn:** 255 of 363 profiles show at least one band move since 2023/24. Should a move need to be larger (for
   example, two bands, or a change in the published figure beyond the survey's margin of error)?
6. **Survey method note:** 111 landlords get it, because every group's most common method is telephone. Should the note
   be kept for methods the regulator found to differ most (internet, postal, face to face)?
7. **Margins of error.** The TSM data gives each landlord's survey margin of error. Small landlords'
   bands may move on noise. Should bands carry a "small survey" note, or be withheld below a sample size?
8. **Repairs and homes for landlords with excluded surveys** is scored on its three management measures alone (half of
   six). Keep, or require at least one survey measure?
9. **Group grades:** where a landlord has no consumer grade but its registered parent does, the parent's is shown and
   named as the group's. Right?
