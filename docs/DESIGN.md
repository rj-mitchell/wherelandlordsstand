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
- **Icons and the link card in the cloth:** the favicon and touch icon are this site's mark, the open front door on
  roof slate ("The mark", below), drawn by the kit from the same drawing (from kit 1.1.0), `theme-color` is roof
  slate, and links shared in a chat or a feed show the family's card for this site, with the mark on it. Every page
  also has Open Graph and Twitter tags and a canonical link to its own address.
- **Headings in Source Serif 4** (`class="wts-headings"` on `<body>`, the family plan's decision 1). This site sets
  its body text in Source Serif 4 as well, so nothing changes to the eye.
- **The same furniture, worded the same way:** the alpha banner links to the report form, with the email address
  second (it keeps the owner's "use it at your own risk" sentence, so it is two sentences, not the family's one); the
  footer's links follow the family's order (About · How it works · Corrections · Accessibility · Privacy · Terms ·
  Data · Press · Status · Source code), with the contact address, admin@wherelandlordsstand.com.
- **Links to a sister site show its spine:** a council's page and each area's page link to the council on Where
  Councils Stand with that site's brown spine beside the link.

This site keeps its own picture mark beside its name (the family plan, decision 4): a front door open on a lit hall,
on a roof-slate tile ("The mark", below).

## The mark

The front door swung wide towards you, on a tile of roof slate (`#40484D`) with rounded corners and a fine gilt edge
(`#D9BC72`, the family's spine gilt, so the edge still shows at 16 pixels), drawn in the same manner as the sister
sites' marks. The door is ivory (`#F3EAD6`), swung open towards you, with its two panels, letterbox and gilt knob in
view; behind it, in the ivory frame, the hall is lit in gilt, and the light falls out over the step. The owner chose
it on 6 November 2026 (docs/DECISIONS.md, 14). It has no book in it: the book is already the spine in "A Where They
Stand project" under the name. It must stay distinct from Where Councils Stand's town hall.

It is drawn inline in the masthead (`MARK` in `src/landlords/site.py`) at 52 px, as the sister sites' marks are, and
44 px on a phone, where it fits beside the name and endorsement without making the masthead taller. Its colours are
in the page, so it is drawn right without the stylesheet, and it is hidden from screen readers (the name beside it
says the same) and isn't a link (the name is). In dark mode the tile and the door's lines are the kit's lifted cloth
(`--wts-cloth-landlords`, `#5B666D`), at 3:1 against the page; the ivory and gilt keep their colours. In forced
colours it is redrawn in the system's two colours: the frame and the door in the text colour, the doorway and the
tile in the background colour, inside a ruled edge.

The same drawing is in `src/landlords/static/` for others to use, and the press page offers it at `/press/` under
those names (`mark.svg`, `mark-dark.svg` on the lifted slate, and `mark-small.svg` and `mark-small-dark.svg` for 16 to
32 pixels, with a heavier edge and door outline, a plain knob and no panels or letterbox). A test checks the masthead's
mark and `mark.svg` have the same shapes. The favicon, the touch icon and the link card come from the family kit
("The family binding", above), which draws them from the same door.

## Type and colour

| Token | Use | Light | Dark |
|---|---|---|---|
| Paper and ink | page and text | `#f5f0e3` (the charity's paper) / `#1c2427` (the charity's ink) | `#14181a` / `#e9e6de` |
| Slate | filled bands, the card's top rule, current tab, buttons | `#40484d` | `#b9c3c9` |
| Roof slate, the cloth | the mark's tile (the kit's `--wts-cloth-landlords`), the spines | `#40484D` | `#5B666D` |
| Link | links | `#2f4a5e` | `#a9c6dc` |
| Gilt | the rule beside "Before you bid" | `#7a5c1c` | `#d9bc72` |
| The mark's gilt and ivory | its edge, the lit hall and the knob; the door and its frame | `#D9BC72` / `#F3EAD6` | the same |

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
- **The masthead:** the mark (the open front door, "The mark" above), the name in Source Serif, the
  family's endorsement under it, the tagline and the independence line in italic, both on the left, then the tabs,
  with the current page underlined in slate, over a double rule. On phones it is lighter, so a landlord's grade is on the first
  screen: a smaller mark, name and endorsement, no tagline (the home page says the same), the independence line in
  smaller type, and closer spacing. With the endorsement added, the grade is on the first screen at 390 x 844 for the
  same 326 of the 363 landlords as before (6 November 2026), with the alpha strip's type and the masthead's spacing
  a little tighter on phones to make room. With the door mark (44 px on a phone, up from the old mark's 34 px), the
  masthead is no taller: measured by where the grade itself ends (or, for a landlord with no grade of its own, the
  grade's heading), it is on the first screen at 390 x 844 for 356 of the 363 landlords both before and after the
  change (6 November 2026).
- **The tabs on a phone** are one line that scrolls sideways, rather than wrapping and leaving "How we compare" alone
  on a second line at 360 to 390 px. Each tab is a snap point, the scroll stays in the row, and the row's edge fades
  where there is more to see (in browsers that tie an animation to scrolling, the left edge fades only once the row
  is scrolled, and the right edge stops fading at the end). On the two pages whose tab can start out of sight (Your
  rights, How we compare) a small script, `static/tabs.js`, scrolls the row so the current tab shows; no other page
  loads it. The row has room above and below for the focus ring, and the fade is dropped while a tab has the
  keyboard's focus, so the ring is never cut off or faded. The labels are unchanged. With the tabs on one line the
  masthead is a line shorter on a phone, and, measured as above, the grade is on the first screen at 390 x 844 for
  356 of the 363 landlords, up from 294 while the tabs wrapped (8 November 2026).
- **Section headings** (`h2`) in small capitals under a rule. The home page's letters (A, B, C ...) are bold
  Source Serif over a thin rule, as the family's headings are.
- **Tables** have small sans-serif column headings over a heavy rule. On a narrow phone (under 30rem) the area tables
  and the status page's table of files are drawn one block per row: the landlord (or the set of files) on a line of
  its own, then each figure or date under its column's heading in small capitals, so no name or date is broken
  mid-word ("Birmingh|am", "Nove|mber"). The column headings stay in the table for screen readers, which skip the
  small labels, and ARIA roles keep it a table whatever the stylesheet does (`stack_table` in `site.py`). A
  landlord's own tables keep their columns; below 22rem a long word in them may be hyphenated or broken so they fit.
- **Search** on the home page lists the landlords found as each letter is typed. That list is not read out as it
  changes; a separate, hidden status line tells screen readers how many were found ("8 landlords found", "No
  landlords found", in `[search]` of `config/wording.toml`) half a second after typing stops, or at once on Enter.
- **The landlord's card:** a panel with a slate top rule. Its parts (grade, how it compares, complaints, safety) have
  small sans-serif headings between thin rules. "Before you bid" sits beside a gilt rule.
- **A statement in a landlord's own words** (docs/DECISIONS.md, 15) never looks like the site's own text: it is in
  the sans, inside a dashed rule, with its words set off by a thin rule on the left, headed "Statement from [name],
  [date]" and ending with "In their own words. Not checked or endorsed by Where Landlords Stand." in small italic.
  Inside the card it sits at the end of the part it is about, under a smaller heading; elsewhere after the card, or
  at the end of an area's table. It is a note for screen readers (`role="note"`), named by its heading.
- **Forms** (the report form, the statement form) have a label over each field and hints in small sans-serif type
  under it. The report form's kinds are radio buttons, each with its hint under its label.
- **The footer** under a double rule, like the masthead: the site's own links and its contact address, then the
  family shelf. "Corrections and problems" and "If you're named" sit side by side, as the family glossary says.

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

Square corners, ruled lists, colour only where it carries meaning, one fluid type scale, visible focus rings (the
slate ring, which the family shelf wears too, through the kit's `--wts-focus`), hover styles that need a mouse with a
pressed state for touch, colour fades only, and no sideways scrolling on phones (checked on every area page and
every landlord's page at 320, 340, 360 and 390 px, and the area pages at 481, 560 and 640 px too: no table box
scrolls; only the compare table, with three landlords, scrolls inside its own box, which takes the keyboard's
focus, as any table that is still too wide does). The footer's links are at least 24 px tall, as the shelf's are, and the footer shelf keeps the
page's own side margins, so its column lines up with the page's.

## Checking a change

Every kind of page (home, three kinds of landlord page, areas, an area, compare, rights, method, downloads,
corrections, privacy, about, terms, accessibility, not found) is checked with axe-core against WCAG 2.2 AA in light
and dark mode, at 1280 px and 390 px: 64 checks, all passing on 6 November 2026. After the family binding was added
the same day, home, a housing association, a council, an area, the method, about and "not found" were checked again
in the same way, with no failures.
