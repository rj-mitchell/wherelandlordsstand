# Design: a volume in the family

Where Landlords Stand is one of the Where They Stand projects, beside Where MPs Stand, Where Councils Stand, Where
Countries Stand and Where Lives Stand. The charity's "Bound Volume" identity gives each project a volume (a spine) on
a shelf and a cloth colour. This site's cloth is **roof slate**, `#40484D`, on the United Kingdom shelf.

The family shares its binding, not its pages (the charity's family plan, section 3): a few things every site carries
in the same form and place, so that someone who has seen one site knows the next. Everything else here is this
site's own.

## The rule: like the record, never like a landlord

- **No landlord's or the regulator's logo, colours or house style**, and nothing that resembles them.
- **Independence is stated on every page**, in the masthead, in the family glossary's short form ("Independent. Not
  affiliated with the Regulator of Social Housing, the Housing Ombudsman Service or any landlord."). The about and
  terms pages have the full line: "Where Landlords Stand is independent. It is not affiliated with or endorsed by the
  Regulator of Social Housing, the Housing Ombudsman Service or any landlord."
- **No colour says good or bad.** The bands are slate squares, filled from the left (one for the bottom quarter, four
  for the top), never red to green: a band is a position among similar landlords, not a verdict. The regulator's
  grade is set in a plain ruled box, whatever the grade.
- **No party colours** (the brand's rule for the United Kingdom shelf): slate is a neutral grey, not a blue.

## The family binding

From the Where They Stand family kit, copied into `src/landlords/family/` by the kit's own script and never edited
here (docs/OPERATIONS.md, "Scoring and the pages"):

- **The endorsement** under the site's name: this site's spine and "A Where They Stand project" in gilt capitals,
  linking to wheretheystand.uk.
- **The family shelf** at the foot of every page, under the site's own footer links: the Where They Stand wordmark,
  the charity's line ("Where They Stand is applying to register as a charity in England and Wales."), links to
  wheretheystand.uk and its Donate page, and every project's spine with a link to it by name, this site's raised.
- **Icons and the link card in the cloth:** the favicon and touch icon are this site's spine on roof slate,
  `theme-color` is roof slate, and links shared in a chat or a feed show the family's card for this site. Every page
  also has Open Graph and Twitter tags and a canonical link to its own address.
- **Headings in Source Serif 4** (`class="wts-headings"` on `<body>`, the family plan's decision 1). This site sets
  its body text in Source Serif 4 as well, so nothing changes to the eye.
- **The same furniture, worded the same way:** the alpha banner links to the report form, with the email address
  second (it keeps the owner's "use it at your own risk" sentence, so it is two sentences, not the family's one); the footer's links follow the family's order (About · How it works · Corrections ·
  Accessibility · Privacy · Terms · Data · Source code; the site has no press or status page yet), with the contact
  address, admin@wherelandlordsstand.com.
- **Links to a sister site show its spine:** a council's page and each area's page link to the council on Where
  Councils Stand with that site's brown spine beside the link.

This site keeps its own picture mark (a roof over a bound volume with gilt bands, on a shelf), drawn in roof slate
(the family plan, decision 4), beside its name.

## Type and colour

| Token | Use | Light | Dark |
|---|---|---|---|
| Paper and ink | page and text | `#f5f0e3` (the charity's paper) / `#1c2427` (the charity's ink) | `#14181a` / `#e9e6de` |
| Slate | filled bands, the card's top rule, current tab, buttons | `#40484d` | `#b9c3c9` |
| Roof slate, the cloth | the mark (the kit's `--wts-cloth-landlords`), the spines | `#40484D` | `#5B666D` |
| Link | links | `#2f4a5e` | `#a9c6dc` |
| Gilt | the mark's bands; the rule beside "Before you bid" | `#b08d3c` / `#7a5c1c` (text) | `#d9bc72` |

- **Source Serif 4** (SIL Open Font License), the family's face, for everything people read. The files and their
  `@font-face` rules come with the family kit (`src/landlords/family/fonts/`, `fonts.css`) and are served from this
  site, so no request goes to Google.
- **The system's sans-serif** for controls and small print: the alpha strip, tabs, labels, hints, source links, table
  headings and the footer. No second font to download.
- Dark mode follows the system setting.

## The parts

- **The alpha strip** across the top, as on the siblings: a dark "ALPHA" label, the notice (that the site is still
  being tested, and to use it at your own risk), a link to the report form, then the email address (`[site] alpha`
  in `config/wording.toml`). On phones its type is a little smaller.
- **The masthead:** the mark (a roof over a bound volume with gilt bands, on a shelf), the name in Source Serif, the
  family's endorsement under it, the tagline in italic, the independence line on the right, then the tabs, with the
  current page underlined in slate, over a double rule. On phones it is lighter, so a landlord's grade is on the first
  screen: a smaller mark, name and endorsement, no tagline (the home page says the same), the independence line in
  smaller type, and closer spacing. With the endorsement added, the grade is on the first screen at 390 x 844 for the
  same 326 of the 363 landlords as before (6 November 2026), with the alpha strip's type and the masthead's spacing
  a little tighter on phones to make room.
- **Section headings** (`h2`) in small capitals under a rule.
- **The landlord's card:** a panel with a slate top rule. Its parts (grade, how it compares, complaints, safety) have
  small sans-serif headings between thin rules. "Before you bid" sits beside a gilt rule.
- **The footer** under a double rule, like the masthead: the site's own links and its contact address, then the
  family shelf.

## Where the look lives

The stylesheet is `src/landlords/static/styles.css`, beside the scripts. The family kit's files are in
`src/landlords/family/`: its two stylesheets (`fonts.css`, `family.css`, loaded before the site's own), the fonts,
the icons and the link card. The build copies them all into `assets/`, each with a fingerprint of its content in its name (`assets/styles.3f9a2c1d.css`), and the
pages name those files. A changed file gets a new address, so Cloudflare and browsers can keep anything in `assets/`
for a year and still never serve a page with an old stylesheet. Pages themselves are checked with the server each
time. The kit's head partial names its files under `/family/`; the build gives each its fingerprinted address
instead, so the kit's files get the same caching as the site's own, and the copy in `src/landlords/family/` stays
exactly as the kit wrote it. The favicon is also copied to the site's root, where browsers ask for it. The mark and
the spines have their size in the page as well as in the stylesheet, so they stay small if the stylesheet fails.

## Shared with the siblings

Square corners, ruled lists, colour only where it carries meaning, one fluid type scale, visible focus rings, hover
styles that need a mouse, animation only when reduced motion isn't requested, and no sideways scrolling on phones
(checked at 390 px, where the area tables fit without scrolling).

## Checking a change

Every kind of page (home, three kinds of landlord page, areas, an area, compare, rights, method, downloads,
corrections, privacy, about, terms, accessibility, not found) is checked with axe-core against WCAG 2.2 AA in light
and dark mode, at 1280 px and 390 px: 64 checks, all passing on 6 November 2026. After the family binding was added
the same day, home, a housing association, a council, an area, the method, about and "not found" were checked again
in the same way, with no failures.
