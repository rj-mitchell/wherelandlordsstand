# Design: a volume in the family

Where Landlords Stand looks like its siblings (Where MPs Stand, Where Countries Stand, Where Councils Stand) and the
charity's hub at wheretheystand.uk, whose "Bound Volume" identity gives each project a volume on a shelf and a cloth
colour. This site's cloth is **roof slate**, `#40484D`, as on the hub's United Kingdom shelf.

## The rule: like the record, never like a landlord

- **No landlord's or the regulator's logo, colours or house style**, and nothing that resembles them.
- **Independence is stated on every page**, in the masthead and the footer ("Independent. Not part of the Regulator
  of Social Housing, the Housing Ombudsman or any landlord.").
- **No colour says good or bad.** The bands are slate squares, filled from the left (one for the bottom quarter, four
  for the top), never red to green: a band is a position among similar landlords, not a verdict. The regulator's
  grade is set in a plain ruled box, whatever the grade.
- **No party colours** (the brand's rule for the United Kingdom shelf): slate is a neutral grey, not a blue.

## Type and colour

| Token | Use | Light | Dark |
|---|---|---|---|
| Paper and ink | page and text | `#f7f5ef` / `#1c2427` (the charity's ink) | `#14181a` / `#e9e6de` |
| Slate | the mark, filled bands, the card's top rule, current tab, buttons | `#40484d` | `#b9c3c9` |
| Link | links | `#2f4a5e` | `#a9c6dc` |
| Gilt | the mark's bands; the rule beside "Before you bid" | `#b08d3c` / `#7a5c1c` (text) | `#d9bc72` |

- **Source Serif 4** (SIL Open Font License), the hub's and Where MPs Stand's face, for everything people read. The
  files are the hub's, served from this site (`src/landlords/static/fonts/`), so no request goes to Google.
- **The system's sans-serif** for controls and small print: the alpha strip, tabs, labels, hints, source links, table
  headings and the footer. No second font to download.
- Dark mode follows the system setting.

## The parts

- **The alpha strip** across the top, as on the siblings: a dark "ALPHA" label and one sentence (`[site] alpha` in
  `config/wording.toml`).
- **The masthead:** the mark (a roof over a bound volume with gilt bands, on a shelf), the name in Source Serif, the
  tagline in italic, the independence line on the right, then the tabs, with the current page underlined in slate,
  over a double rule.
- **Section headings** (`h2`) in small capitals under a rule, as Where Councils Stand's are.
- **The landlord's card:** a panel with a slate top rule. Its parts (grade, how it compares, complaints, safety) have
  small sans-serif headings between thin rules. "Before you bid" sits beside a gilt rule.
- **The footer** under a double rule, like the masthead.

## Shared with the siblings

Square corners, ruled lists, colour only where it carries meaning, one fluid type scale, visible focus rings, hover
styles that need a mouse, animation only when reduced motion isn't requested, and no sideways scrolling on phones
(checked at 390 px).

## Checking a change

Every kind of page (home, three kinds of landlord page, areas, an area, compare, rights, method, downloads,
corrections, privacy, about, terms, accessibility, not found) is checked with axe-core against WCAG 2.2 AA in light
and dark mode, at 1280 px and 390 px: 64 checks, all passing on 6 November 2026.
