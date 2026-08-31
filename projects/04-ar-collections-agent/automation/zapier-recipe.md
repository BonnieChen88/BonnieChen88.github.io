# Zapier recipe — collections cadence

## Zap 1 — Weekly dunning run

| Step | App | Configuration |
|---|---|---|
| 1 | Schedule by Zapier | Every Tuesday, 08:00 |
| 2 | Zuora (or NetSuite) | Export open invoices with aging |
| 3 | Code by Zapier (Python) | Run `ar_agent.py dunning` |
| 4 | Filter | Only rows where `automated = true` |
| 5 | Gmail | **Create Draft** in the AR owner's mailbox — one per invoice |
| 6 | Slack | Post `slack_digest.json` to `#finance-ops` |
| 7 | Slack | DM the finance lead the held-back list with reasons |

Step 5 creates drafts rather than sending. The cadence is automated; the decision to
contact a customer is not.

## Zap 2 — Pre-due courtesy reminder

| Step | App | Configuration |
|---|---|---|
| 1 | Schedule by Zapier | Daily, 07:00 |
| 2 | Zuora | Find invoices due in exactly 5 days, unpaid |
| 3 | Filter | Skip accounts with an open dispute |
| 4 | Gmail | Send the courtesy reminder (safe to automate — nothing is late yet) |

This zap is where delinquency actually falls. Most late payment is an AP calendar
problem, not an unwillingness to pay, and a reminder before the due date costs nothing.

## Zap 3 — Payment received

| Step | App | Configuration |
|---|---|---|
| 1 | Stripe / bank feed | Trigger: payment received |
| 2 | Zuora | Apply payment, close the invoice |
| 3 | Storage by Zapier | Clear that account's dunning state |
| 4 | Slack | Post to `#finance-ops` if the invoice was 60+ days overdue |

Step 3 matters: without it the next run chases an invoice that has just been paid.

## Notes

- Reconcile against a frozen AR export. Running mid-sync produces a queue that
  disagrees with the ledger, and one wrong chaser costs more trust than the whole
  cadence saves.
- Log every automated contact back to the invoice record so the seven-day cooldown
  works across runs.
- Do not let the escalation tier reach a customer. Internal language like
  "collections review" belongs in the queue, never in the email.
