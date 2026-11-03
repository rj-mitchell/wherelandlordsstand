# Testing with applicants

Phase 3's gate is that the bidder tools have been tested with the people they are for (the brief: "Gate: tested with
users"). This is the plan. It needs people, so it is for the owner to run, ideally with an advice service or a
housing association's tenant panel.

## Who

Six to eight people, at least half of them currently on a housing register and bidding (or who bid in the last year),
including:

- someone who mostly uses a phone, not a computer;
- someone who reads English as a second language, or finds reading hard;
- someone offered a home through homelessness services;
- a shared ownership buyer or mutual exchange applicant;
- an advice worker who helps people bid.

Pay people for their time. Get written consent; record notes, not names.

## Setting up

Run the site on a laptop (`landlords serve`), or publish a test build where only testers can reach it. Use real
adverts from the applicant's own area if they have them; otherwise the examples below. Give each person a phone if they
don't want to use their own.

## Tasks (about 30 minutes each)

Say: "We're testing the site, not you. Think out loud." Don't help unless someone is stuck for two minutes.

1. **From an advert.** Show a real choice-based lettings advert with a landlord's name (for example a Warwick
   HomeChoice advert naming "Orbit Housing"). "You're thinking of bidding for this. Find out what the landlord is like."
   Watch: do they search, or use the list? Do they find it under the advert's name?
2. **A logo only.** Show a Kent Homechoice advert with only a logo (Moat, Golding Homes). "The advert only shows a
   logo. What would you do?" Watch: do they find the area list?
3. **Read the card.** On the landlord's page: "In your own words, what does this tell you?" Then ask: what does "C2"
   mean? What does "bottom quarter" mean, and compared with whom? Is anything worrying, or reassuring? Would it change
   whether you bid?
4. **Not covered.** "Your friend's landlord is Park Properties Housing Association. What does the site say?"
5. **Compare.** "You can bid for one of two homes. Compare their landlords." (Pick two in the tester's area.)
6. **Your rights.** "The home you're offered has damp. What can you do?"
7. **Turning down an offer.** Ask what they understood from the line about turning down offers. Did anything on the
   site make them want to refuse an offer? (If yes, that is a serious finding: the site must never push people to
   refuse.)

## What to measure

- Did they find the landlord within a minute, on a phone? (The brief's aim.)
- Could they explain the grade and one band correctly?
- Did anyone read a band as a ranking of all landlords, or as a reason to refuse?
- Words they didn't understand; things they expected and didn't find.

## After

Write up each session in a page of notes (no names). Fix what three or more people struggled with; change wording
only in `config/wording.toml` and `config/rights.toml`, and send the changes to the adviser who signs off the wording.
Record the result of the gate in docs/DECISIONS.md.
