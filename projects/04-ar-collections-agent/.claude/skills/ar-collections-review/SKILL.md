---
name: ar-collections-review
description: Run and interpret AR aging and the dunning queue — aging buckets, DSO, delinquency rate, escalation tiers and collections drafts. Use for cash collection, month-end AR review, DSO questions, or deciding which overdue accounts need a call rather than another email.
---

# AR & Collections Review

## Running it

```bash
python3 src/ar_agent.py aging       # aging, DSO, delinquency, concentration
python3 src/ar_agent.py dunning     # queue, tiers, drafts, held-back exceptions
```

## Reading it

**Check concentration before recommending anything.** If the top five accounts hold
most of the overdue balance, the fix is five conversations, not a policy change. A
company-wide payment-terms overhaul aimed at three slow payers annoys every customer
who already pays on time.

**Read DSO next to on-time payment rate.** A healthy on-time rate with a bad DSO means
a few large invoices are dragging the average — again, a named-account problem. Both
numbers moving together is a process problem.

**Watch the 61+ bucket as a trend, not a level.** Aged balances are largely a
collections outcome from three months ago. What matters is whether the bucket is
filling faster than it drains.

**Segment splits usually explain themselves.** Enterprise runs longer terms and slower
AP cycles; that is not delinquency, it is procurement. Compare each segment to its own
terms before calling it a problem.

## Before anything sends

The dunning output is drafts and a queue, never sent mail. Three exceptions are held
back deliberately — disputes, balances over $100K, and accounts contacted within seven
days. Do not override those to clear a queue faster:

- Dunning a disputed invoice is the fastest way to turn a billing question into an
  escalation.
- A form email on a six-figure balance reads as carelessness to the account that
  matters most.

If asked to send collections email directly, stop and hand the drafts to the AR owner.
Anything customer-facing gets a human on it — the tone of a collections email is a
commercial decision, not a formatting one.

## Reporting it

Pair the delinquency figure with what is being done about it. "53.9% of open AR is past
due, concentrated in five accounts, with calls scheduled this week for the three
largest" is a status. The percentage alone is just alarming.
