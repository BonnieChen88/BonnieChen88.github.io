---
name: revenue-report
description: Generate and review the monthly revenue pack — ARR waterfall, NRR/GRR, risk-adjusted pipeline forecast and hygiene flags. Use for month-end close, board and investor reporting, forecast calls, or any question about ARR movement, retention or pipeline coverage.
---

# Monthly Revenue Reporting Pack

## Running it

```bash
python3 src/revenue_pack.py --month YYYY-MM --as-of YYYY-MM-DD
```

Add `--next-quarter-target` when the real board target is known; the default is a
run-rate estimate and should not be presented to a board as if it were the plan.

## Reading the output before anyone else does

**Reconcile the waterfall first.** Opening + new + expansion − contraction − churn must
equal closing. It is replayed from the event log so it should always tie; if it does
not, the export is incomplete and nothing downstream is trustworthy.

**Report GRR alongside NRR, never NRR alone.** NRR can look healthy while the base is
eroding underneath, because expansion from a few accounts masks churn in many. The gap
between the two is the story.

**Never present raw pipeline coverage as the forecast.** The pack deliberately shows
raw and risk-adjusted side by side. Raw coverage of 7x with risk-adjusted coverage of
1.5x is not a strong quarter — it is a hygiene problem wearing a good number. Lead with
the risk-adjusted figure and explain the haircut.

**Treat the Commit gap as the sharpest hygiene signal.** Deals in Commit that sit in
Discovery, or that no one has touched in 90 days, mean the forecast category is being
used as a wish. Name the number.

## When something looks unusual

Before writing commentary, check whether a movement is one account or a trend. A single
large churn or expansion can swing a month; the board question is always "is this
structural?" Look at the customer-level detail and say which it is.

## Writing the commentary

Investors want the delta and the reason, in that order. State what moved, what caused
it, and what changes next month. Avoid adjectives that the numbers do not support —
"strong" and "encouraging" cost credibility when growth decelerates the next month.

Flag anything that will look worse next month before it does. Being early on bad news
is the entire value of this report.

## Before sending

The pack contains customer-level revenue detail. Confirm the audience before posting
the Slack summary or sharing the markdown — investor packs, all-hands and board decks
are three different levels of disclosure.
