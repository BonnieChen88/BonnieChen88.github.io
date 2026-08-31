# Zapier recipe — automated month-end revenue pack

## Zap 1 — Monthly close pack

| Step | App | Configuration |
|---|---|---|
| 1 | Schedule by Zapier | 1st of each month, 07:00 |
| 2 | Zuora (or Stripe) | Export subscription events for the closed month |
| 3 | Salesforce | Find Records — open `Opportunity`, all fields used by the model |
| 4 | Code by Zapier (Python) | Run `revenue_pack.py --month <last month>` |
| 5 | Google Drive | Upload `board_pack.md` to the board folder |
| 6 | Slack | Post `slack_summary.json` blocks to `#leadership` |
| 7 | Gmail | Draft — *not send* — the investor update with the pack attached |

Step 7 drafts rather than sends on purpose. Investor communications get a human read
before they leave the building.

## Zap 2 — Weekly pipeline hygiene nudge

| Step | App | Configuration |
|---|---|---|
| 1 | Schedule by Zapier | Every Tuesday, 08:00 |
| 2 | Code by Zapier | Run the pack, keep only `pipeline_hygiene.csv` |
| 3 | Formatter | Group flagged opportunities by `owner` |
| 4 | Slack | DM each AE their own flagged list; post the totals to `#revenue-ops` |

One DM per rep, listing only their deals. A single channel post naming everyone's
stale pipeline gets ignored on week two.

## Notes

- Run the pack against a *frozen* export of the closed month. Re-running it later
  against live data will produce different numbers than the board saw.
- Keep every month's `revenue_metrics.json`. Restating a prior month is legitimate;
  doing it silently is not.
- The forecast-category logic assumes standard Salesforce values (Pipeline / Best Case
  / Commit). Map custom values before the first run.
