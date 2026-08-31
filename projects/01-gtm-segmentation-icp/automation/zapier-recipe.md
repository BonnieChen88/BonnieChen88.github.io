# Zapier recipe — weekly ICP refresh and CRM write-back

Keeps account tiers current without anyone remembering to run anything.

## Zap 1 — Weekly rescore

| Step | App | Configuration |
|---|---|---|
| 1 | Schedule by Zapier | Every Monday, 06:00 local |
| 2 | Salesforce | Find Records — `Opportunity` where `IsClosed = true` and `CloseDate = LAST_N_MONTHS:24` |
| 3 | Code by Zapier (Python) | Run `analyze`, then `score`, against the exported rows |
| 4 | HubSpot | Batch update companies with `icp_score`, `icp_tier`, `icp_reason` |
| 5 | Slack | Post the tier summary to `#gtm-ops` |

## Zap 2 — Score new accounts on creation

| Step | App | Configuration |
|---|---|---|
| 1 | HubSpot | Trigger: New Company |
| 2 | Clay | Enrich — employee count, industry, regulatory status |
| 3 | Code by Zapier | Score the single account against the current `icp_profile.json` |
| 4 | Paths | Tier A → create Salesforce task for the AE · Tier B → enroll in SDR sequence · Tier C → nurture list · Tier D → set `outbound_suppressed = true` |

## Notes

- Cache `icp_profile.json` in Zapier Storage; refresh it weekly from Zap 1 rather
  than recomputing it on every new account.
- Guard Zap 2 against enrichment gaps: if Clay returns no employee count, route to
  manual review instead of scoring the account with a default.
- Tier changes should be logged, not silently overwritten. A company that drops from
  A to C mid-quarter is a conversation with the AE, not a database update.
