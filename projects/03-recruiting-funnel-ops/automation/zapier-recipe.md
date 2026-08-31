# Zapier recipe — recruiting funnel automation

## Zap 1 — Twice-weekly stalled-candidate nudges

| Step | App | Configuration |
|---|---|---|
| 1 | Schedule by Zapier | Tuesday and Thursday, 09:00 |
| 2 | Lever | Find Opportunities — all active candidates on open postings |
| 3 | Code by Zapier (Python) | Run `funnel_ops.py nudge` |
| 4 | Looping by Zapier | One iteration per hiring manager in `slack_nudges.json` |
| 5 | Slack | `chat.postMessage` as a DM to that manager only |
| 6 | Filter | Continue only if `escalations > 0` |
| 7 | Slack | Post the escalation count (no names) to `#talent-ops` |

Step 5 is a DM by design. A shared channel post listing every manager's stalled
candidates is both a public performance review and, by the second week, wallpaper.

## Zap 2 — Weekly funnel report

| Step | App | Configuration |
|---|---|---|
| 1 | Schedule by Zapier | Monday, 07:00 |
| 2 | Lever | Export candidates and postings |
| 3 | Code by Zapier | Run `funnel_ops.py report` |
| 4 | Google Drive | Upload `funnel_report.md` to the talent review folder |
| 5 | Slack | Post funnel + time-to-hire summary to `#talent-ops` — aggregates only |

## Zap 3 — Offer-stage watch

| Step | App | Configuration |
|---|---|---|
| 1 | Lever | Trigger: candidate moved to Offer |
| 2 | Delay by Zapier | 5 days (the Offer SLA) |
| 3 | Lever | Find that candidate again |
| 4 | Filter | Continue only if still in Offer |
| 5 | Slack | DM the recruiter and the hiring manager together |

## Notes

- Rate-limit the Lever API pulls; the full candidate export on a busy req list will
  exceed the default Zapier task timeout. Page it, or run the export nightly to a
  sheet and read the sheet.
- Never write candidate names into Zapier Storage or a Google Sheet that is broadly
  shared. Keep names in Lever and in the DM.
- Set `STAGE_SLA` with the recruiting lead before switching nudges on. An SLA nobody
  agreed to produces alerts nobody actions.
