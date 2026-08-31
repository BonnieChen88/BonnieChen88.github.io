#!/usr/bin/env python3
"""Monthly revenue reporting pack for investors and leadership.

Turns two raw exports -- ARR movement events and the open Salesforce pipeline --
into the pack that otherwise gets rebuilt by hand every month:

  * ARR waterfall (opening, new, expansion, contraction, churn, closing)
  * NRR and GRR on a trailing-twelve-month cohort basis
  * logo counts and logo churn
  * a risk-adjusted pipeline forecast, not a raw pipeline total
  * pipeline hygiene flags, so the forecast comes with its own health warning

Writes a board-ready markdown pack, a metrics JSON for dashboards, and a Slack
Block Kit payload for the Monday leadership post.

Standard library only. Author: Bonnie Chen
"""

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEF_EVENTS = os.path.join(HERE, "data", "sample", "arr_events.csv")
DEF_PIPE = os.path.join(HERE, "data", "sample", "salesforce_opportunities.csv")

# Historical win rate by stage and segment. In production these come from the
# same closed-won analysis that drives project 01; hard-coding them here keeps
# this script self-contained and auditable.
STAGE_WIN_RATE = {
    "SMB":         {"Discovery": .08, "Qualification": .18, "Proposal": .34,
                    "Negotiation": .58, "Contracting": .84},
    "Mid-Market":  {"Discovery": .06, "Qualification": .15, "Proposal": .31,
                    "Negotiation": .55, "Contracting": .82},
    "Enterprise":  {"Discovery": .04, "Qualification": .11, "Proposal": .26,
                    "Negotiation": .49, "Contracting": .78},
}

# A deal with no activity for 90 days is treated as worthless until someone
# touches it again. This single rule is what closed most of the historical gap
# between forecast and actual -- stale pipeline was being carried at full value.
DECAY_DAYS = 90
DECAY_FLOOR = 0.10

STALE_DAYS = 30


def parse_date(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def read_csv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def money(x):
    if abs(x) >= 1e6:
        return "$%.2fM" % (x / 1e6)
    return "$%.0fK" % (x / 1e3)


def pct(x, places=1):
    return ("%." + str(places) + "f%%") % (100 * x)


def month_key(d):
    return "%04d-%02d" % (d.year, d.month)


def months_back(key, n):
    y, m = (int(x) for x in key.split("-"))
    idx = y * 12 + (m - 1) - n
    return "%04d-%02d" % (idx // 12, idx % 12 + 1)


# ------------------------------------------------------------------- ARR ----
def build_arr(events, through):
    """Replay the event log into per-month movement and per-customer balances."""
    movement = defaultdict(lambda: defaultdict(float))
    balances = defaultdict(lambda: defaultdict(float))   # month -> cust -> arr
    running = defaultdict(float)
    segment_of = {}
    months = sorted({e["month"][:7] for e in events if e["month"][:7] <= through})

    by_month = defaultdict(list)
    for e in events:
        if e["month"][:7] <= through:
            by_month[e["month"][:7]].append(e)

    for m in months:
        for e in by_month[m]:
            delta = float(e["delta_arr"])
            movement[m][e["event_type"]] += delta
            running[e["customer_id"]] += delta
            segment_of[e["customer_id"]] = e["segment"]
        balances[m] = dict(running)
    return months, movement, balances, segment_of


def retention(balances, month, prior):
    """NRR / GRR against the cohort of customers who had ARR 12 months ago."""
    base = {c: v for c, v in balances.get(prior, {}).items() if v > 0}
    if not base:
        return None, None, 0
    now = balances.get(month, {})
    start = sum(base.values())
    end = sum(now.get(c, 0.0) for c in base)
    retained = sum(min(now.get(c, 0.0), v) for c, v in base.items())
    return end / start, retained / start, len(base)


# -------------------------------------------------------------- pipeline ----
def score_pipeline(opps, as_of):
    """Risk-adjust every open opportunity and flag the ones a forecast cannot trust."""
    rows = []
    for o in opps:
        amount = float(o["amount"] or 0)
        seg = o["segment"]
        wr = STAGE_WIN_RATE.get(seg, STAGE_WIN_RATE["Mid-Market"]).get(o["stage"], 0.1)
        inactive = (as_of - parse_date(o["last_activity_date"])).days
        decay = max(DECAY_FLOOR, 1.0 - inactive / float(DECAY_DAYS))
        close = parse_date(o["close_date"])

        flags = []
        if inactive > STALE_DAYS:
            flags.append("stale %dd" % inactive)
        if close < as_of:
            flags.append("close date %dd past due" % (as_of - close).days)
        if amount == 0:
            flags.append("no amount")
        if not o["next_step"].strip():
            flags.append("no next step")
        if o["forecast_category"] == "Commit" and o["stage"] in ("Discovery", "Qualification"):
            flags.append("committed from %s" % o["stage"].lower())

        rows.append({
            "opportunity_id": o["opportunity_id"], "account": o["account_name"],
            "owner": o["owner"], "segment": seg, "stage": o["stage"],
            "forecast_category": o["forecast_category"], "amount": amount,
            "days_inactive": inactive, "stage_win_rate": wr,
            "recency_factor": round(decay, 3),
            "risk_adjusted": round(amount * wr * decay, 2),
            "unadjusted_weighted": round(amount * wr, 2),
            "flags": flags,
        })
    return rows


# ---------------------------------------------------------------- report ----
def build(args):
    as_of = parse_date(args.as_of)
    month = args.month or month_key(as_of)
    prior = months_back(month, 12)

    events = read_csv(args.events)
    months, movement, balances, segment_of = build_arr(events, month)
    if month not in months:
        raise SystemExit("No ARR events for %s (data ends %s)" % (month, months[-1]))

    mv = movement[month]
    closing = sum(balances[month].values())
    opening = closing - sum(mv.values())
    prior_month = months_back(month, 1)
    ttm_start = sum(balances.get(prior, {}).values())

    nrr, grr, cohort_n = retention(balances, month, prior)
    logos = sum(1 for v in balances[month].values() if v > 0)
    logos_prior = sum(1 for v in balances.get(prior_month, {}).values() if v > 0)

    ttm = defaultdict(float)
    for i in range(12):
        for k, v in movement.get(months_back(month, i), {}).items():
            ttm[k] += v

    seg_arr = defaultdict(float)
    for c, v in balances[month].items():
        if v > 0:
            seg_arr[segment_of.get(c, "Unknown")] += v

    pipe = score_pipeline(read_csv(args.pipeline), as_of)
    open_total = sum(p["amount"] for p in pipe)
    weighted = sum(p["unadjusted_weighted"] for p in pipe)
    adjusted = sum(p["risk_adjusted"] for p in pipe)
    commit = sum(p["amount"] for p in pipe if p["forecast_category"] == "Commit")
    commit_adj = sum(p["risk_adjusted"] for p in pipe if p["forecast_category"] == "Commit")
    stale = [p for p in pipe if p["days_inactive"] > STALE_DAYS]
    flagged = [p for p in pipe if p["flags"]]

    target = args.next_quarter_target or round(max(ttm["new"] + ttm["expansion"], 1) / 4 * 1.25, -3)
    coverage = open_total / target if target else 0
    adj_coverage = adjusted / target if target else 0

    metrics = {
        "month": month, "as_of": args.as_of,
        "arr": {
            "opening": round(opening), "new": round(mv.get("new", 0)),
            "expansion": round(mv.get("expansion", 0)),
            "contraction": round(mv.get("contraction", 0)),
            "churn": round(mv.get("churn", 0)), "closing": round(closing),
            "net_new": round(closing - opening),
            "ttm_growth": round((closing - ttm_start) / ttm_start, 4) if ttm_start else None,
        },
        "retention": {"nrr": round(nrr, 4) if nrr else None,
                      "grr": round(grr, 4) if grr else None,
                      "cohort_customers": cohort_n},
        "logos": {"count": logos, "net_change_mom": logos - logos_prior},
        "segment_mix": {k: round(v) for k, v in sorted(seg_arr.items(), key=lambda kv: -kv[1])},
        "pipeline": {
            "open_total": round(open_total), "stage_weighted": round(weighted),
            "risk_adjusted": round(adjusted),
            "decay_haircut": round(weighted - adjusted),
            "commit_total": round(commit), "commit_risk_adjusted": round(commit_adj),
            "next_quarter_target": round(target),
            "raw_coverage": round(coverage, 2), "risk_adjusted_coverage": round(adj_coverage, 2),
            "opportunities": len(pipe), "stale_opportunities": len(stale),
            "stale_value": round(sum(p["amount"] for p in stale)),
            "flagged_opportunities": len(flagged),
        },
    }

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "revenue_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)
    write_markdown(os.path.join(args.out_dir, "board_pack.md"), metrics, pipe)
    write_slack(os.path.join(args.out_dir, "slack_summary.json"), metrics)
    write_hygiene(os.path.join(args.out_dir, "pipeline_hygiene.csv"), flagged)

    print_console(metrics, flagged)
    print("\nWrote board_pack.md, revenue_metrics.json, slack_summary.json, "
          "pipeline_hygiene.csv to %s" % os.path.relpath(args.out_dir, HERE))


def print_console(m, flagged):
    a, p, r = m["arr"], m["pipeline"], m["retention"]
    print("REVENUE PACK -- %s (as of %s)\n" % (m["month"], m["as_of"]))
    print("ARR WATERFALL")
    for label, key in (("Opening ARR", "opening"), ("  + New", "new"),
                       ("  + Expansion", "expansion"), ("  - Contraction", "contraction"),
                       ("  - Churn", "churn"), ("Closing ARR", "closing")):
        # Contraction and churn are stored signed but read better unsigned
        # next to a minus in the label.
        print("  %-16s %12s" % (label, money(abs(a[key]) if key in
                                             ("contraction", "churn") else a[key])))
    print("  %-16s %12s   (%s TTM growth)"
          % ("Net new", money(a["net_new"]),
             pct(a["ttm_growth"]) if a["ttm_growth"] is not None else "n/a"))
    print("\nRETENTION   NRR %s   GRR %s   (cohort of %d customers)"
          % (pct(r["nrr"]) if r["nrr"] else "n/a",
             pct(r["grr"]) if r["grr"] else "n/a", r["cohort_customers"]))
    print("LOGOS       %d active   (%+d vs last month)"
          % (m["logos"]["count"], m["logos"]["net_change_mom"]))
    print("\nPIPELINE (%d open opportunities)" % p["opportunities"])
    print("  Open pipeline        %12s" % money(p["open_total"]))
    print("  Stage-weighted       %12s" % money(p["stage_weighted"]))
    print("  Risk-adjusted        %12s   (%s haircut from the %d-day decay rule)"
          % (money(p["risk_adjusted"]), money(p["decay_haircut"]), DECAY_DAYS))
    print("  Next-quarter target  %12s" % money(p["next_quarter_target"]))
    print("  Coverage             %11.2fx raw  /  %.2fx risk-adjusted"
          % (p["raw_coverage"], p["risk_adjusted_coverage"]))
    print("\nHYGIENE     %d of %d opportunities flagged; %s sitting in pipeline "
          "with no activity for %d+ days"
          % (p["flagged_opportunities"], p["opportunities"],
             money(p["stale_value"]), STALE_DAYS))
    if p["commit_total"]:
        print("            Commit category %s raw vs %s risk-adjusted (%s gap)"
              % (money(p["commit_total"]), money(p["commit_risk_adjusted"]),
                 money(p["commit_total"] - p["commit_risk_adjusted"])))
    worst = sorted(flagged, key=lambda x: -x["amount"])[:5]
    if worst:
        print("\nLARGEST FLAGGED DEALS")
        for w in worst:
            print("  %-24s %9s  %-13s %s"
                  % (w["account"][:24], money(w["amount"]), w["stage"],
                     "; ".join(w["flags"])))


def write_markdown(path, m, pipe):
    a, p, r = m["arr"], m["pipeline"], m["retention"]
    L = []
    L.append("# Revenue Report — %s\n" % m["month"])
    L.append("_Prepared by Bonnie Chen · generated %s · figures in USD_\n" % m["as_of"])

    L.append("## Headline\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append("| Closing ARR | **%s** |" % money(a["closing"]))
    L.append("| Net new ARR (month) | %s |" % money(a["net_new"]))
    L.append("| TTM growth | %s |" % (pct(a["ttm_growth"]) if a["ttm_growth"] is not None else "n/a"))
    L.append("| Net revenue retention | %s |" % (pct(r["nrr"]) if r["nrr"] else "n/a"))
    L.append("| Gross revenue retention | %s |" % (pct(r["grr"]) if r["grr"] else "n/a"))
    L.append("| Active logos | %d (%+d MoM) |" % (m["logos"]["count"], m["logos"]["net_change_mom"]))
    L.append("| Risk-adjusted coverage | %.2fx |\n" % p["risk_adjusted_coverage"])

    L.append("## ARR waterfall\n")
    L.append("| Movement | Amount |")
    L.append("|---|---:|")
    for label, key in (("Opening ARR", "opening"), ("New", "new"), ("Expansion", "expansion"),
                       ("Contraction", "contraction"), ("Churn", "churn"),
                       ("**Closing ARR**", "closing")):
        v = -a[key] if key in ("contraction", "churn") else a[key]
        L.append("| %s | %s |" % (label, ("(%s)" % money(v)) if key in
                                 ("contraction", "churn") else money(v)))
    L.append("")

    L.append("## Segment mix\n")
    L.append("| Segment | ARR | Share |")
    L.append("|---|---:|---:|")
    tot = sum(m["segment_mix"].values()) or 1
    for k, v in m["segment_mix"].items():
        L.append("| %s | %s | %s |" % (k, money(v), pct(v / tot)))
    L.append("")

    L.append("## Pipeline and forecast\n")
    L.append("Open pipeline of **%s** across %d opportunities. Applying historical "
             "stage win rates gives %s; applying the %d-day activity decay rule on top "
             "gives a risk-adjusted **%s** — a %s haircut.\n"
             % (money(p["open_total"]), p["opportunities"], money(p["stage_weighted"]),
                DECAY_DAYS, money(p["risk_adjusted"]), money(p["decay_haircut"])))
    L.append("Against a next-quarter target of %s, that is **%.2fx raw coverage** but "
             "only **%.2fx risk-adjusted**. The second number is the one to plan from.\n"
             % (money(p["next_quarter_target"]), p["raw_coverage"],
                p["risk_adjusted_coverage"]))

    L.append("## Forecast health\n")
    L.append("- %d of %d opportunities carry at least one hygiene flag."
             % (p["flagged_opportunities"], p["opportunities"]))
    L.append("- %s of pipeline has had no activity in %d+ days."
             % (money(p["stale_value"]), STALE_DAYS))
    L.append("- Commit category holds %s raw against %s risk-adjusted, a %s gap."
             % (money(p["commit_total"]), money(p["commit_risk_adjusted"]),
                money(p["commit_total"] - p["commit_risk_adjusted"])))
    L.append("\nFull detail in `pipeline_hygiene.csv`. Owners are asked to clear flags "
             "before the forecast call.\n")
    L.append("---\n_All figures derived from synthetic data in this repository._")
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")


def write_slack(path, m):
    a, p, r = m["arr"], m["pipeline"], m["retention"]
    blocks = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": "Revenue snapshot — %s" % m["month"]}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": "*Closing ARR*\n%s" % money(a["closing"])},
            {"type": "mrkdwn", "text": "*Net new*\n%s" % money(a["net_new"])},
            {"type": "mrkdwn", "text": "*NRR*\n%s" % (pct(r["nrr"]) if r["nrr"] else "n/a")},
            {"type": "mrkdwn", "text": "*GRR*\n%s" % (pct(r["grr"]) if r["grr"] else "n/a")},
            {"type": "mrkdwn", "text": "*Risk-adj. coverage*\n%.2fx" % p["risk_adjusted_coverage"]},
            {"type": "mrkdwn", "text": "*Active logos*\n%d (%+d)" % (m["logos"]["count"],
                                                                     m["logos"]["net_change_mom"])},
        ]},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": ":warning: *%d opportunities flagged* — %s of pipeline has been quiet "
                 "for %d+ days. Clear flags before Thursday's forecast call."
                 % (p["flagged_opportunities"], money(p["stale_value"]), STALE_DAYS)}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": "Generated automatically from Salesforce + billing data · full pack in the drive"}]},
    ]
    with open(path, "w") as fh:
        json.dump({"channel": "#leadership", "blocks": blocks}, fh, indent=2)


def write_hygiene(path, flagged):
    cols = ["opportunity_id", "account", "owner", "segment", "stage",
            "forecast_category", "amount", "days_inactive", "recency_factor",
            "risk_adjusted", "flags"]
    rows = sorted(flagged, key=lambda x: -x["amount"])
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] if c != "flags" else "; ".join(r["flags"]) for c in cols])


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--events", default=DEF_EVENTS)
    p.add_argument("--pipeline", default=DEF_PIPE)
    p.add_argument("--as-of", default="2026-06-30")
    p.add_argument("--month", default=None, help="reporting month, YYYY-MM")
    p.add_argument("--next-quarter-target", type=float, default=None,
                   help="new+expansion ARR target; defaults to 1.25x trailing quarterly run rate")
    p.add_argument("--out-dir", default=os.path.join(HERE, "out"))
    build(p.parse_args())


if __name__ == "__main__":
    main()
