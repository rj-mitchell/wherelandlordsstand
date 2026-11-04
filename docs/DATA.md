# Data

What each source publishes, what is really in the files, how it is loaded, and what doesn't fit. Written from the
files themselves, downloaded on 3 November 2026: one year of each source in phase 1, and a second year of the TSMs
and the Ombudsman's tables in phase 2 (below, "A second year").

## The files

`landlords fetch` downloads each file listed in `config/sources.toml` into `data/raw/<source>/`, named by its SHA-256
hash, with a note beside it (`<hash>.note.json`) giving its address, the page that linked to it, its title there,
the period it covers, the publisher, the licence and when it was fetched. A file is never overwritten; a changed file
gets a new hash and sits beside the old one. GOV.UK pages are found through the Content API
(`https://www.gov.uk/api/content/<path>`), which lists each page's attachments with their titles.

| Source | File | Period | Size | Hash (start) |
|---|---|---|---|---|
| Regulator of Social Housing (RSH) | [Tenant Satisfaction Measures 2025: full data set](https://www.gov.uk/government/statistics/tenant-satisfaction-measures-202425) (xlsx, v1.1) | 2024/25 | 713 KB | `b9f541da9ef0` |
| RSH | The same data set as a zip of CSVs (**this is the one loaded**) | 2024/25 | 202 KB | `bb3440670af5` |
| RSH | TSM 2024/25 Headline Report (PDF) | 2024/25 | 697 KB | `751b6cad2eca` |
| RSH | TSM 2024/25 Data quality and methodology (PDF) | 2024/25 | 271 KB | `4d89251ebdbe` |
| RSH | [Regulatory judgements and enforcement notices table](https://www.gov.uk/government/publications/regulatory-judgements-and-enforcement-notices), 28 October 2026 | current | 83 KB | `ee78f97049fa` |
| RSH | [Archived regulatory judgements and notices table](https://www.gov.uk/government/publications/archived-regulatory-judgements-and-notices-table) | 2012 to March 2024 | 447 KB | `19213668f605` |
| RSH | [Gradings under review list](https://www.gov.uk/guidance/gradings-under-review-list) (the page itself, as Content API JSON) | current | 19 KB | `b10405e2c573` |
| RSH | [List of registered providers](https://www.gov.uk/government/publications/registered-providers-of-social-housing), 20 October 2026 | current | 87 KB | `cd0922f7577a` |
| RSH | [Private registered providers data release](https://www.gov.uk/government/statistics/private-registered-provider-social-housing-stock-and-rents-in-england-2025-to-2026) (Statistical Data Return, v1.1) | 2025/26 | 9.5 MB | `d21919e4da5c` |
| RSH | [Local authority registered provider data release](https://www.gov.uk/government/statistics/local-authority-registered-provider-social-housing-stock-and-rents-in-england-2025-to-2026) (Local Authority Data Return) | 2025/26 | 440 KB | `cfdea04e8440` |
| RSH | Private registered providers: technical notes and definitions (PDF) | 2025/26 | 491 KB | `a8f1000586da` |
| RSH | [TSM full data release 2024](https://www.gov.uk/government/statistics/data-release-tsm-2024) (xlsx only, v2.1) | 2023/24 | 718 KB | `b481648689c8` |
| RSH | TSM 2023/24 Headline Report (PDF) | 2023/24 | 834 KB | `c3cb6dec14d1` |
| Housing Ombudsman | [Tables for landlords with individual performance reports 2024-25](https://www.housing-ombudsman.org.uk/annual-complaint-review-reports/annual-complaints-review-2024-25/) | 2024-25 | 402 KB | `460adfbe5d40` |
| Housing Ombudsman | [Tables for landlords with individual performance reports 2025-26](https://www.housing-ombudsman.org.uk/annual-complaint-review-reports/annual-complaints-review-2025-26/) (xlsx, "latest update 15 September 2026") | 2025-26 | 406 KB | `fe9766f953ec` |

**Licences.** The regulator's files are under the Open Government Licence v3.0. The Ombudsman's pages say only
"© Housing Ombudsman Service 2026". No reuse licence was found anywhere on its site: not on the decision, landlord,
publication scheme or freedom of information pages, nor any page in its sitemap; the footer's "Legal" heading covers
only privacy and FOI. Landlord Record (landlordrecord.co.uk/data), an independent site built from the Ombudsman's
decisions, states that "the source decisions are made available under the Open Government Licence v3.0", but it
doesn't say where the Ombudsman says so. Its figures are used for now while the Ombudsman is asked to confirm its terms
(docs/DECISIONS.md, 9; open question 1).

`landlords load` reads the newest file for each source into tidy tables in `data/staging/` (Parquet). Every row
carries `source_file` (the file's hash) and `period`, and `data/staging/sources.json` maps each hash to its note, so
every figure can be traced to its file and year.

## Tenant Satisfaction Measures, 2024/25

The regulator's TSM return: landlords that own 1,000 or more social homes report 12 tenant perception measures from
a survey (TP01–TP12) and 10 management measures from their records (building safety BS01–BS05, repairs RP01–RP02,
complaints CH01–CH02, anti-social behaviour NM01). The year runs 1 April 2024 to 31 March 2025; the data was published
4 November 2025, and v1.1 (December 2025) corrected the headings of TP05 and TP06 only. The 2025/26 release has not
been published yet (3 November 2026).

**Which file is loaded.** The xlsx and the zip hold the same data. The xlsx's columns are long questions
("Proportion of respondents who report that they are satisfied with the overall service…") with footnote numbers
attached; the zip's CSVs use the regulator's field names (`TP01_Satisfied_Calc_LCRA`), which are steadier between
releases. The loader reads the CSVs. Their data dictionary maps each field to the question.

**Tables in the file.**

| File in the zip | Rows | What it is |
|---|---|---|
| `File 0B - Table_coverage` | 363 | Every landlord, with Yes/No for each table |
| `File 01 - LCRA_perception` | 353 | Survey results for low cost rental (rented homes): 135 columns |
| `File 02 - LCHO_perception` | 59 | Survey results for low cost home ownership (shared owners): 111 columns |
| `File 03 - COMB_perception` | 2 | Combined results, for landlords allowed to survey both together |
| `File 04 - Management_info` | 359 | Management measures, with numerators and denominators: 104 columns |
| `File 05 - Perception_not_inc` | 2 | Landlords whose survey results were excluded |
| `File 06 - Man_not_inc` | 1 | Landlords whose management measures were excluded |
| `File 0A - Data_dictionary` | 485 | Each column's heading, field name, question and source |

**Who is in it.** 363 landlords: 203 private providers (housing associations and for-profit providers) and 160
councils. Three of them (Grainger Trust 4743, ReSI Homes 5092, The Abbeyfield Society H1046) have no results in any
table, which leaves the **360 submissions** the headline report counts. Each landlord appears under the regulator's
code, the same code the register and judgements use. For a group, the TSMs are often submitted by the group's parent
(A2Dominion Housing Group, L4240), while its homes are owned by a subsidiary (A2Dominion Homes, LH0391): see "Homes
by area".

**What each row gives.**

* Context: the regulator's size band (`<5,000`, `5,000-40,000`, `>40,000` homes, LCRA and LCHO combined), predominant
  region (South, North, Midlands, London, Mixed), whether more than 30% of rented homes are
  supported housing (30 landlords), and the landlord's own TSM web page.
* Survey: the relevant tenant population, the minimum sample needed, the sample achieved, the margin of error, census
  or sample, responses by method (telephone, internet, face to face, postal, SMS, other), the predominant method,
  whether a contractor was used, and the weighting used.
* Results: each TP measure as a percentage satisfied, the counts behind it (very satisfied … very dissatisfied), and
  TP01 for each survey method separately.
* Management measures: each as published (`*_Calculated_Value`) with its numerator and denominator, and for repairs
  the landlord's own target timescales. RP02 is measured against each landlord's own target, and the targets vary
  widely: the maximum non-emergency target runs from 5 to 260 (median 28) and the emergency one from 2 to 168
  (median 24). The data dictionary doesn't give units; most look like days and hours respectively.
* The data dictionary describes several stage one complaint fields (CH02_1) as "stage two". The field names are
  right; the descriptions are the publisher's slip.

**Shared owners aren't asked about repairs.** The LCHO table has no TP02–TP04.

**Markers.** In place of a number the regulator writes:

| Marker | Meaning | Kept as status |
|---|---|---|
| `[U]` | The denominator was zero, so the figure is undefined: **not applicable, never zero** | `undefined` |
| `[E]` | Excluded by the regulator after review | `excluded` |
| `[S]` | Fewer than 50 surveys by that method, so satisfaction by that method is suppressed | `suppressed` |
| `[X]` | Left blank by the landlord | `blank` |
| `[Z]` | A response was not required | `not required` |

Counted over the loaded measures: 2,648 complaints rows are `[U]` (mostly landlords with no shared owners or no
combined survey), 16 building safety and 9 repairs rows are `[U]`, and 11 rows are `[E]`.

**Exclusions.** The data quality note's list matches the data exactly: Stoke-on-Trent (00GL) and Cannock Chase (41UB)
perception results (survey wording differed materially); St Mungo (LH0279) TP09; Your Housing Group (L4203) TP10 —
**for rented homes only**: its shared ownership TP10 (61.4%) is published; Tandridge (43UK) all management measures;
Brent (00AE) BS02–BS05; Adur (45UB) RP02 non-emergency; Canterbury (29UC) RP01; Octavia (L0717) RP02, both parts;
Islington (00AU) CH02 stage one. The regulator also adds comments to some landlords' rows, for example that Cheltenham
(23UB)'s "TSMs do not include results for an entity", or that a landlord "has not been able to provide all contextual
information on repairs". These are kept in `tsm_coverage.rsh_comment` and should be shown beside the figures.

**Building safety is near 100% for most landlords, but not all.** Of 359 landlords with building safety measures,
113 report 100% on every one, and 77 report below 95% on at least one. The median of each of BS01–BS05 is 100%. The
lowest are 83.1% (gas, BS01), 21.9% (fire risk assessments, BS02), 0% (asbestos, BS03; water, BS04) and 41.6% (lifts,
BS05). This supports showing building safety as "all checks done" or "gaps in N% of homes" (docs/DECISIONS.md, 5).

**Survey method matters.** Satisfaction varies with how the survey was done (headline report, 2.7). Predominant
method, from the loaded data: telephone 245 landlords, internet 46, postal 29, face to face 15, SMS 5, no predominant
method 18 (of 358 with a perception table).

**Size bands.** The regulator's bands (`<5,000`, `5,000-40,000`, `>40,000`) aren't the peer groups used for
scoring (1,000–9,999; 10,000–49,999; 50,000+). Those bands need each landlord's homes, which the stock
data gives (phase 2).

### Reconciliation with the published figures

`landlords check` compares the loaded data with the figures the regulator prints (`config/reconciliation.toml`):

| Published figure | Loaded data | Result |
|---|---|---|
| 360 submissions | 360 (363 listed, 3 with no results) | matches |
| 299 rented only, 56 rented and shared ownership separately, 3 shared ownership only, 2 combined | the same (the 299 include Cannock Chase and Stoke-on-Trent, whose survey results were excluded) | matches |
| TP01 (rented), landlord quartiles 64.7%, 71.8%, 78.9% | 64.7%, 71.8%, 78.9% from 353 landlords (inclusive quartiles) | matches |
| Surveys by method (Table 2): postal 40,514, face to face 57,409, telephone 313,104, SMS 7,287, internet 80,505 | the same | matches |
| Satisfaction by method (Table 2): 80.2%, 78.9%, 69.4%, 63.2%, 60.1% | 80.3%, 78.9%, 69.4%, 63.2%, 60.2%, weighting each landlord's published figure by its responses | within 0.1 (published figures are rounded to 0.1) |
| "71% of landlords used telephone surveys as their principal survey collection method" (2.5, Figure 4: 71%, 12%, 7%, 4%, 4%, 1%) | 245 of 358 (68.4%), internet 12.8%, postal 8.1%, face to face 4.2%, none 5.0%, SMS 1.4% | **does not match; not yet explained** (open question 3) |
| The excluded results listed above | each is marked `[E]` or absent | matches |

## Regulatory judgements and gradings

**The current table** (`20261028_RegulatoryJudgementsNotices_Published.xlsx`, sheet "Regulatory Judgements") has one
row for each landlord's latest judgement since April 2024: 317 rows, 206 private providers and 111 councils, all
"Current". For each standard it gives the grade, how it changed, and the grade's date:

| Standard | Grades in the table |
|---|---|
| Consumer (C1 best – C4) | C1 90, C2 105, C3 46, C4 8; none yet 68 ("Not assessed yet" 59, "-" 8, and 1 "Not assessed yet (as the merged entity)") |
| Governance (G1–G4) | G1 154, G2 36, G3 7, G4 1; none for 118 landlords: the 111 councils (not graded on governance or viability) and 7 private providers |
| Viability (V1–V4) | V1 65, V2 129, V3 3, V4 1; none for the same 118 |
| Rent | 6 landlords with a rent judgement ("Y") |

* A `*` after a grade (`C1*`, `G2*`) marks a for-profit provider (stated in the archived table's heading). It is
  stored as `for_profit` and removed from the grade.
* Changes are written in words: "First grading", "Assessed and unchanged", "Upgrade", "Downgrade", "Regrade V1 to V2",
  "Based on previous assessment", "Interim grading" (also spelled "Interim Grading"), "First Grade".
* Dates are real dates, except where there is no grade ("-").
* Other columns: the kind of publication (Narrative RJ 310, Interim RJ 5, Grading Under Review 2), its date, the
  engagement that led to it (Inspection 164, Stability Check 86, Responsive Engagement 57, and combinations), other
  landlords the judgement covers, and the regulator's note of name changes and mergers ("Octavia Housing merged with
  Abri Group Limited 16 February 2026").
* Two codes appear twice. **L4331** is Chelmer Housing Partnership (a narrative judgement, 26 November 2025) and Delta
  Housing (an interim judgement, 29 July 2026): the register lists only Delta Housing under L4331, so this is a change
  of name, and "Chelmer Housing Partnership Limited" is kept as an alias. **4747** (Pivotal Housing Association) has
  two judgements, January and June 2026.
* A second sheet lists 3 current enforcement notices.

**Coverage of profiled landlords.** 303 of the 363 TSM landlords have a judgement in the current table; 244 have a
consumer grade (C2 105, C1 85, C3 46, C4 8). Of the 119 without a consumer grade, 66 are housing associations, 50
councils and 3 for-profit providers: the regulator is still working through its first inspections, so many profiles
will say "not yet graded on the consumer standards".

**The archived table** (2012 to March 2024) has 2,727 rows for 408 codes: every published judgement and notice with
the governance and viability grades at the time (there were no consumer grades before April 2024). Older judgements
were mostly "Strapline RJ" (1,748) confirming existing grades. It names many landlords that have since merged or
deregistered: 109 of its codes are no longer on the register.

**Gradings under review.** The list is the page itself. On 3 November 2026 it had two entries: Hexagon Housing
Association (L1538, 15 October 2026) and Rentplus Homes (5204, 18 August 2026), both under investigation on the
governance and financial viability standard. Each heading reads "15 October 2026: Hexagon Housing Association Limited
(L1538)"; the loader stops if a heading can't be read.

All of these go into one table, `grades`: one row per landlord, publication and standard, with `table` saying where
it came from (`current`, `archive`, `under-review`, `enforcement`).

## The register of providers

The monthly list (20 October 2026) has **1,577 registered providers**: 232 local authorities, 1,253 non-profit and 92
for-profit providers, with registration number, registration date and corporate form. (The brief's 1,580 was the count
on 31 March 2026.) Every code in the TSM data and the current judgements is on it.

Councils registered in 2010 have the old ONS-style codes (Adur 45UB, Stoke-on-Trent 00GL); councils registered later
have numbers (Amber Valley 5164, BCP Council 5069). The Local Authority Data Return gives each council's GSS code, so
no separate lookup is needed: 230 councils, all on the register. Two councils on the register have no return:
Epsom & Ewell (5238, registered 8 April 2026) and Preston (5241, 29 May 2026), both registered after the return's
date of 31 March 2026.

## Stock and rents, 2025/26

From the Statistical Data Return (private providers) and the Local Authority Data Return (councils), at 31 March 2026,
published 27–30 October 2026.

**Private providers: the data release xlsx (v1.1)** has 18 tables, each on its own sheet with a coverage sheet and a
data dictionary. "Large" providers (1,000 or more homes) fill in the full return; "Small" ones a short one. The ones
that matter here:

| Sheet | Rows | What it is |
|---|---|---|
| `SDR26_STOCK_INFORMATION_BY_LA` | 10,428 | **Each provider's homes in each local authority area**: rented homes owned and managed (general needs, bedspaces, supported housing, housing for older people), shared ownership owned and managed, homes failing the Decent Homes Standard, vacancies, sales and demolitions. Small providers give owned rented homes only. |
| `SDR26_Group_Structure` | 2,081 | Each provider's registered parent and subsidiaries |
| `SDR26_Entity_Level_Information` | 1,307 | Size, non-profit or profit, code of governance |
| `SDR26_LCRR_PRP_LEVEL` | 1,307 | Each provider's totals, Decent Homes failures, EPC ratings, age and type of homes |
| `SDR26_RENTS_*` (six sheets) | 1,471–3,622 | Average weekly rents and service charges **by area and by number of bedrooms**, general needs and supported housing, with and without exceptions |
| `SDR26_ARGN_Rents`, `SDR26_ARSHHOP_Rents` | 3,716, 501 | Affordable Rent by area and bedrooms |
| `SDR26_Stock_Usage` | 228 | Lettings, mutual exchanges and evictions |

**So the landlord × council breakdown the brief asked about exists for housing associations and for-profit
providers**, for homes and for rents. Area codes are current GSS codes (E06, E07, E08, E09) for 300 English areas;
33 loaded values are in Wales (W92…), Scotland (S92…) or Northern Ireland (N92…), and 2 are coded `9300000XX`
"Outside UK".
`[x]` means not available.

**Councils: the LADR data release** gives each council's homes as a total, by type (social rent, Affordable Rent,
shared ownership) and number of bedrooms. It counts homes the council owns "regardless of where the stock is
geographically located", so it has **no breakdown by area**. A council's homes are placed in its own area, and the
area table says so (`basis = council total`). Of 230 returns, 218 report homes; the other 12 report none.

**Rents are not loaded yet.** They are published by area and number of bedrooms, not as one average per landlord.
Showing "average rent" would mean combining them, which is our arithmetic, not a published figure (open question 5).

`stock_area` keeps the published counts, one row per company, area and measure; zero and blank cells are left out.

## The Housing Ombudsman's landlord tables, 2025-26

The Ombudsman reports on each landlord with five or more findings in cases it decided between 1 April 2025 and 31
March 2026. The notes say there are 296 such landlords and that 6 "with only one determination" were left out "as
publishing this data could indirectly reveal personal information about a resident"; **Table 1 has 290 rows**, which
matches.

| Sheet | What it is |
|---|---|
| Table 1 | Each landlord's size band, type, determinations, findings, maladministration findings (severe maladministration, maladministration and service failure together, which the Ombudsman calls "upheld"), orders, recommendations, Complaint Handling Failure Orders, compensation, maladministration rate, and findings by outcome. **Loaded.** |
| Table 2 | Findings by category (repairs, complaint handling, ASB …) and outcome |
| Table 3 | Findings by highlighted sub-category (noise, damp and mould …) |
| Table 4 | Findings by sub-category |
| Table 5 | Orders by type (apology, compensation, repairs …) |
| Table 6 | "TBC": empty |
| Table 7 | Compensation ordered and recommended, by category |

* **No regulator codes.** Landlords are named, nothing more, so each name is matched to the register (below). Names
  are the landlords' legal names as the Ombudsman holds them, sometimes out of date: "Chelmer Housing Partnership
  Limited" (now Delta Housing), "Paradigm Housing Group Limited" (now Lifestone Homes), "Metropolitan Thames Valley
  Housing (MTV)".
* **The maladministration rate** is a fraction (0.67), defined as maladministration findings as a share of "total
  findings excluding Outside Jurisdiction and Withdrawn". It reproduces from the counts (A2Dominion: 231 / 343).
* **Size band** is the homes "owned or managed by the member landlord under the Ombudsman's jurisdiction as of 31
  March 2025", from the regulator and landlords. The bands are the member's own: a group parent can be "Less than 100
  units" (Platform Housing Group Limited, 137 findings) while its homes are in subsidiaries.
* **Types:** Housing Association 160, Local Authority / ALMO or TMO 122, Other 8 ("voluntary members, almshouses,
  de-registered publicly funded providers, co-operatives, Abbeyfield and for-profit providers").
* **No figure per 1,000 homes.** The table gives no rate per home. "Upheld per 1,000 homes", as proposed in the plan,
  would mean dividing the Ombudsman's count by the regulator's homes: our arithmetic on two publishers' figures (open
  question 2).
* **A break in the series.** From October 2025 the Ombudsman examines complaint handling in every case it
  investigates, which it says "affects how this year's maladministration rates compare with previous years and sets
  a new benchmark". 2025-26 must not be compared with earlier years without saying so.
* **Earlier years.** The 2024-25 table is on the 2024-25 review's page
  (`Tables-for-landlords-with-individual-performance-reports-2024-25.xlsx`); reviews go back to 2021-22. Only 2025-26
  is loaded.
* The Ombudsman reported an IT security incident affecting its case system in October 2026 (its news page, 3 November
  2026). The 2025-26 tables were published before it, on 15 September 2026.

Matching: 284 names are a landlord's exact legal name, 3 are aliases (all renames), 1 matches after normalising
("Legal and General Affordable Homes Limited"), 1 is Octavia Housing (now merged into Abri), and 1 is a group
reported under its parent: **MHS Homes Ltd**, typed "Other", is not on the register because it is the **unregistered
parent** of Heart of Medway Housing Association (4634), as the stock return's group table records ("mhs homes Ltd").
The regulator's TSM file also links Heart of Medway's results to a page on mhs.org.uk under "MHS Homes Group". It is
kept as an alias of kind "group". `landlords match` now offers a company's registered subsidiaries first when a name
is an unregistered parent (109 companies in the group table have one).

## A second year

Added in phase 2 so that profiles can show changes since the year before.

**TSM 2023/24** is published only as an xlsx (v2.1, December 2025). Version 2.0 (November 2025) replaced zeros with
`[U]` where the denominator was zero, and included data "resubmitted since November 2024"; the headline report
(October 2024) describes v1.0. What differs from 2024/25:

* **No CSVs**, so the loader reads the xlsx. Its data dictionary can't be used to translate headings: several field
  names carry a stray `_a` suffix, identifiers are given as "System Property", and 13 LCRA headings don't match the
  sheet. Each heading is instead mapped by the measure code it carries ("(TP01)", "(RP02 1)", "LCRA - … (CH02 1
  Numerator)") to the field name the 2024/25 CSVs use (`load/tsm.py`, `field_name`).
* **Notes below the tables** ("Notes:", "1. Landlord TSM Publication URL…") rather than above them; rows without a
  landlord code are skipped.
* **Unrounded figures** (74.9898332655551) where 2024/25 gives one decimal place (75.0). Kept as published; pages show
  one decimal place.
* **Labels**: "FacetoFace" for "Face to Face", ">40000" for ">40,000", and a group size of "Merged during year".
* **Landlords only on the exclusion lists**: Castle Point (22UE, "did not collect tenant perception information")
  and Guildford (43UD, "Did not submit TSM data for 2023/24. This failure has been included in our consumer
  grading") are on the not-included lists but not in the coverage table. They are kept, with the regulator's note.

It reconciles with its headline report: 360 submissions (302 rented only, 54 both, 2 shared ownership only, 2
combined), TP01 quartiles 63.7, 71.3 and 78.4 (published as 64%, 71%, 78%), and surveys and satisfaction by method
(postal 50,622 at 77.2%, face to face 28,395 at 74.7%, telephone 299,190 at 69.8%, SMS 10,756 at 63.1%, internet
90,618 at 58.3%) within 0.1.

**Ombudsman 2024-25** has the same Table 1 columns. The notes say 281 landlords had reports and that those with one
determination were withheld, without saying how many; Table 1 has 277 rows. Its names differ from 2025-26's: councils
by short name ("Camden Council" for the London Borough of Camden), "54North Homes Limited", and initials in brackets
("Notting Hill Genesis (NHG)", "London & Quadrant Housing Trust (L&Q)"). The 21 names that weren't exact were checked
by hand and added as aliases (kind "short" or "published", source "Housing Ombudsman 2024-25; checked by hand"). Its
figures are from before the Ombudsman began examining complaint handling in every case (October 2025), so they are
shown separately, under "Earlier Ombudsman figures", and never compared with 2025-26.

## The name register

**`data_static/landlords.csv`** has one row for every registered provider (1,577) and every former provider still
named in a loaded file (112, almost all from the archived judgements), 1,689 in all.

| Column | What it is |
|---|---|
| `id` | The regulator's code, as in the TSM data and judgements (L4203, 00GL, 5069). The key every table joins on. |
| `legal_name` | From the register (or, for a former provider, its name in its latest judgement) |
| `display_name` | Profiled landlords only. **Made by a rule** (legal suffixes such as "Limited" removed, "(The)" moved to the front) and to be checked by hand: "Abri Group", "Sage Homes RP", "City of Doncaster Council". |
| `type` | council, housing association or for-profit (the register's designation) |
| `gss` | Councils: their area's GSS code, from the LADR |
| `group_id` | The ultimate registered parent, from the SDR's group structure; empty if none |
| `registration_date` | From the register (the brief's `registration`) |
| `status` | active, merged or deregistered; `successor_id` and `successor_date` for a merger. Octavia Housing (L0717) is marked merged into Abri (L4172) on 16 February 2026, in the regulator's words; nothing else has been marked by hand yet. |
| `profiled` | yes for the 363 landlords in the TSM data (194 housing associations, 160 councils, 9 for-profit providers) |
| `slug` | Profiled landlords only. Never changes once published (`data_static/published_slugs.txt`, empty for now). |

`landlords register` adds new rows and refreshes the facts that come from the regulator. It never removes a row, and
never changes a display name, slug, status or successor that is already there: those are edited by hand.

**`data_static/aliases.csv`** (`landlord_id`, `alias`, `kind`, `source`, `valid_to`) has 107 aliases (21 added in phase 2 for the Ombudsman's 2024-25 names; the table below is phase 1's 86):

| Kind | Count | From |
|---|---|---|
| published | 14 | Names publishers print next to a landlord's code that differ from its legal name, added by `landlords register` (the TSM data still uses some old names: "Paradigm Housing Group Limited" for Lifestone Homes, "Bespoke Supportive Tenancies Ltd" for Portus), and "Aster Housing Group" from BCP's partner list |
| former | 57 | Names in the archived judgements for codes whose name has since changed (Radian Group, Affinity Sutton Group, Sovereign Housing Association …), and "Synergy" and "L&H Homes" from BCP's list and a West Lindsey advert |
| short | 9 | Names on lettings adverts and partner lists: Platform Housing, Orbit Housing, Citizen, Abri, Aster, Amplius, Clarion, Golding, Hyde ("Sovereign", "Radian" and "Affinity Sutton" were already covered by former names) |
| trading | 2 | "Metropolitan Thames Valley Housing (MTV)" (Ombudsman), "Bournemouth Housing Landlord Services" (BCP) |
| logo label | 2 | "Orbit", "Moat" (Kent Homechoice logo alt text) |
| managing body | 1 | "Poole Housing Partnership", BCP Council's ALMO |
| group | 1 | "MHS Homes Ltd", the unregistered parent of Heart of Medway Housing Association |

Names on adverts that weren't given an alias: names that already match a legal name (Golding Homes, Town & Country
Housing, Southern Housing, West Kent Housing Association, Places for People, Park Properties Housing Association,
Walsall Housing Group, Warwick District Council), and two that can't point to one landlord: **"Sage"** (Sage Homes RP
5082 and Sage Rented 5083 are both profiled) and "MHS Homes" (now matched through its subsidiary, above). Park Properties Housing
Association (5056) is a for-profit provider below the TSM threshold, so it isn't profiled.

**Matching names without a code.** `landlords match` looks each name up in tiers and stops at the first tier with an
answer: an alias exactly; a legal name exactly among active landlords; a legal name exactly among all; then the same
again after normalising (lower case, "&" to "and", "Limited", "Ltd", "Group", "Housing Association", "The" and
punctuation dropped). Exact names come first so that a short alias ("Clarion") can't capture a different company
whose full name normalises the same way ("Clarion Housing Association Limited"). If a tier finds two landlords, the
name is left for a person. What's left is written to `data/staging/match-review.csv` with up to three candidates each
(rapidfuzz); a person marks `accept = yes` and runs `landlords match --accept <file>`. Nothing is accepted
automatically.

The register is wider than the brief's "about 360" because every row of every loaded file must match a landlord, and
the files name small and former providers too. Only the 363 profiled landlords get pages.

## Homes by area

`landlord_area` gives, for each profiled landlord and council area, its rented homes (low cost rental owned: general
needs, bedspaces, supported housing and housing for older people) and its shared ownership homes. For a group, it adds
up the homes of each company whose nearest profiled parent is that landlord (`owners`). **This is the one place phase
1 adds up published figures**, and the method page will say so.

Checked against each landlord's own TSM figures: the rented homes added up this way are within a third of the
"relevant tenant population" it reported for its TSMs for 350 of 355 landlords. The 5 that differ are all changes
between 31 March 2025 (TSM) and 31 March 2026 (stock):

| Landlord | TSM population | Homes by area, 2026 | Why |
|---|---|---|---|
| Octavia Housing (L0717) | 4,104 | 0 | Merged with Abri, 16 February 2026 |
| Estuary Housing Association (L3535) | 3,381 | 0 | No homes in the 2026 return; still on the register as active. Probably merged (Delta Housing's homes rose by about the same number), but the regulator's files don't say so (open question 6) |
| Delta Housing (L4331) | 9,694 | 13,838 | See Estuary |
| Portus Supported Housing (4718) | 1,381 | 2,244 | Created by a merger on 1 December 2025 (the regulator's note) |
| Legal & General Affordable Homes (AR) LLP (5149) | 1,287 | 1,789 | Growth (a for-profit provider) |

361 of the 363 profiled landlords have homes in at least one area (all but Octavia and Estuary). 296 English areas
have at least one profiled landlord; the median area has 22.

**Area codes.** Every English area code in the stock data is a council in `data_static/councils.csv`, a copy of Where
Councils Stand's council list, after one correction to our copy: **Where Councils Stand's file has Barnsley and
Sheffield under their pre-2019 codes (E08000016, E08000019)**. The regulator uses the current codes (E08000038,
E08000039), and so does our copy now. Where Councils Stand now uses the current codes too (fixed there on 4 November 2026).

## Checks

`landlords check` writes `data/staging/check-report.json` and a change report. On the data above, all 30 checks pass (both TSM years and both Ombudsman years
are reconciled):

* every row of the TSM, coverage, judgements, stock, providers and Ombudsman tables has a landlord: pass (**the phase 1
  gate**);
* aliases point to known landlords and kinds, no alias points to two landlords, slugs unique, no published slug
  missing, every profiled landlord has a name, slug and type, every TSM landlord profiled: pass;
* values in range (percentages 0–100, rates not negative, maladministration rate 0–1, grades C/G/V 1–4): pass;
* every reconciliation in the TSM table above, the Ombudsman's 290, and 230 council returns: pass (the 71% telephone
  figure is reported as a known difference);
* every English area is a council in `councils.csv`: pass;
* homes by area against TSM populations: 5 differ, reported as a warning (above).

The change report lists grade changes in the current judgements (upgrades, downgrades and regrades, newest first).
With two TSM years loaded it also lists the biggest
movers in TP01 (rented) between them.

## Open questions

1. **The Ombudsman's reuse terms.** No licence is stated on its site. A third party says its decisions are under the
   Open Government Licence; the landlord tables may not be covered by the same terms. **To do:** ask the Ombudsman
   (email drafted, 3 November 2026). Until it answers, the data is used (docs/DECISIONS.md, 9).
2. ~~Ombudsman figures per 1,000 homes~~: decided. Only the Ombudsman's own figures are shown (docs/DECISIONS.md, 10).
3. **"71% used telephone".** The data gives 68.4%. Possibly a different base (all submissions, or rented only before
   exclusions); worth asking the regulator if the figure is used.
4. ~~MHS Homes Ltd~~: resolved. It is the unregistered parent of Heart of Medway Housing Association (above).
5. **Average rent.** Published per area and number of bedrooms, not per landlord. Show the published figures by
   bedroom size, or compute an average and say so?
6. **Estuary Housing Association.** Active on the register but with no homes in 2026. Find the regulator's statement
   before marking it merged.
7. **Display names.** 363 rule-made names to check by hand, and which name to lead with where adverts use another
   ("Abri" or "Abri Group").
8. **Where a group's TSMs are submitted by its parent** (most groups), the Ombudsman may report the parent and its
   subsidiaries separately. Westminster (with Westminster Community Homes) and Peabody (with Town and Country Housing)
   each have two Ombudsman rows. Profiles will show both as published, never added together.
