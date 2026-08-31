---
name: gtm-segmentation
description: Run and interpret the ICP scoring engine — segment closed-won/lost deal history to find which verticals, company sizes and lead sources actually convert, then score open accounts for routing. Use when asked about ICP, segmentation, win rates by segment, lead prioritisation, territory or outbound targeting.
---

# GTM Segmentation & ICP Scoring

## When to use this

Someone asks who we should be selling to, why win rate has plateaued, which segments
deserve outbound capacity, or how to prioritise a list of open accounts.

## How to run it

```bash
python3 src/icp_engine.py analyze          # writes out/icp_profile.json
python3 src/icp_engine.py score            # writes out/scored_accounts.csv
```

Run `analyze` first — `score` depends on the profile it writes. Use `--deals` and
`--accounts` to point at real exports.

## How to read the output

**Lift is the number that matters.** A segment at 1.35x converts 35% better than the
company baseline. Anything between roughly 0.9x and 1.1x is noise — do not build a
strategy on it.

**Check the sample size before believing a segment.** Segments under 12 deals are
pinned to 1.0x lift on purpose. If a stakeholder points at a small segment with a
gaudy win rate, that is the guardrail doing its job — say so.

**Look for a shared driver, not just a list.** Three verticals topping the table is a
finding; understanding *why* they convert (a compliance deadline, a regulator, a
budget cycle) is what makes it actionable for marketing. Always ask what the top
segments have in common before presenting the ICP.

**Cross-check win rate against cycle length and ARR.** A high-win-rate segment with
tiny deals is a distraction. The case for an ICP is strongest when win rate, cycle
speed and deal size point the same way.

## When presenting this

Lead with the concentration line — "X% of won ARR from Y% of volume" — because that
is the sentence that moves a sales leader. Then the shared driver. Then the tier
counts, framed as capacity freed rather than accounts abandoned.

Be explicit about what the analysis cannot see: it reads closed deals, so it is blind
to markets never prospected. Recommend the ICP as where to concentrate now, plus one
deliberate experiment outside it, rather than as a permanent fence.

## Before writing scores back to the CRM

Tier D means "suppress from outbound". Confirm with the sales lead before pushing
`hubspot_batch_update.json` — a bad tier on a live account is a real cost, and the
write is a batch update against production records.
