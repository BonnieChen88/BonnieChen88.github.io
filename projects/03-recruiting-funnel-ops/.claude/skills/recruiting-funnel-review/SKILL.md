---
name: recruiting-funnel-review
description: Run and interpret the recruiting funnel report and stalled-candidate nudges — stage conversion, time-to-hire against target, source efficiency, and who owes the next action. Use for talent reviews, time-to-hire questions, hiring pipeline health, or agency-versus-referral spend decisions.
---

# Recruiting Funnel Review

## Running it

```bash
python3 src/funnel_ops.py report      # funnel, time-to-hire, sources, req health
python3 src/funnel_ops.py nudge       # stalled candidates + hiring-manager DMs
```

## Reading it

**Never stop at the median.** Stage medians can all sit inside SLA while dozens of
individual candidates are weeks past it. Always report the median *and* the count past
SLA — the second number is the one that loses candidates.

**Check who owes the next action before assigning blame.** The `nudge` output splits
stalls by owner. Recruiting teams tend to assume hiring managers are the constraint;
the data often says otherwise, and saying so with a count is the difference between a
process change and an argument.

**Judge sources at onsite, not applications.** A channel with high volume and no
interviews is spend, not supply. Frame the recommendation as reallocating budget
between named channels, with the conversion figures attached.

**A requisition open past target with no late-stage candidates needs sourcing, not a
pipeline review.** Those are flagged `at_risk` for exactly this reason — reviewing an
empty pipeline weekly changes nothing.

## Handling candidate data carefully

This output names real people and their interview status. Keep two rules:

- Send each hiring manager only their own candidates. Never post a stalled list naming
  everyone's candidates to a shared channel — it is a performance conversation held in
  public, and it gets ignored by week two.
- Do not paste candidate names into general channels, tickets, or anywhere outside the
  ATS and the direct message. Aggregate counts are fine to share; names are not.

## Framing the recommendation

Tie every proposed change to days removed from a specific stage, and be conservative
about the claim. "Reducing HM screen scheduling from 13 days to the 7-day SLA takes
about six days out of time-to-hire" is defensible. A headline improvement percentage
without the stage-level arithmetic behind it is not.

Also recommend the reject. Many stalled candidates should be closed out rather than
advanced, and an honest reject at week three is better for the candidate and the funnel
than silence at week eight.
