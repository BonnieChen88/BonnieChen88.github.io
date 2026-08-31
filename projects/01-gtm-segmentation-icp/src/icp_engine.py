#!/usr/bin/env python3
"""GTM segmentation and ICP scoring engine.

Two commands:

    analyze   Read 24 months of closed-won/closed-lost deals and work out which
              segments actually convert -- win rate, deal cycle and revenue
              concentration by industry, company size and lead source. Writes an
              ICP profile (weights derived from observed lift, not hand-picked).

    score     Apply that profile to open accounts, producing a 0-100 fit score,
              an A/B/C/D tier, and a plain-English reason per account. Emits a
              HubSpot property-update payload so the tiers land back in the CRM
              where sales actually works.

Standard library only -- no install step, runs anywhere Python 3.8+ runs.

Author: Bonnie Chen
"""

import argparse
import csv
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEALS = os.path.join(HERE, "data", "sample", "closed_deals.csv")
DEFAULT_ACCOUNTS = os.path.join(HERE, "data", "sample", "open_accounts.csv")
DEFAULT_PROFILE = os.path.join(HERE, "out", "icp_profile.json")

# Minimum deals before a segment's win rate is trusted. Below this the segment
# inherits the baseline -- otherwise a 2-for-2 vertical looks like the best
# market you have ever seen.
MIN_SAMPLE = 12

SIZE_BANDS = [(0, 100, "1-100"), (100, 500, "100-500"), (500, 2000, "500-2K"),
              (2000, 5000, "2K-5K"), (5000, 10 ** 9, "5K+")]


def size_band(employees):
    for lo, hi, label in SIZE_BANDS:
        if lo <= employees < hi:
            return label
    return "unknown"


def read_csv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def pct(x):
    return "%.1f%%" % (100 * x)


def money(x):
    return "$%.1fM" % (x / 1e6) if abs(x) >= 1e6 else "$%.0fK" % (x / 1e3)


# ---------------------------------------------------------------- analyze ----
def summarize(deals, key_fn):
    """Win rate, median cycle and won-ARR for each value of a dimension."""
    buckets = defaultdict(lambda: {"n": 0, "won": 0, "arr": 0, "cycles": []})
    for d in deals:
        b = buckets[key_fn(d)]
        b["n"] += 1
        if d["outcome"] == "won":
            b["won"] += 1
            b["arr"] += int(d["arr"])
            b["cycles"].append(int(d["cycle_days"]))
    result = {}
    for k, b in buckets.items():
        cycles = sorted(b["cycles"])
        result[k] = {
            "deals": b["n"],
            "won": b["won"],
            "win_rate": b["won"] / b["n"] if b["n"] else 0.0,
            "won_arr": b["arr"],
            "median_cycle_days": cycles[len(cycles) // 2] if cycles else None,
        }
    return result


def analyze(args):
    deals = read_csv(args.deals)
    baseline = sum(1 for d in deals if d["outcome"] == "won") / len(deals)
    total_won_arr = sum(int(d["arr"]) for d in deals if d["outcome"] == "won")
    all_cycles = sorted(int(d["cycle_days"]) for d in deals if d["outcome"] == "won")
    baseline_cycle = all_cycles[len(all_cycles) // 2]

    dims = {
        "industry": summarize(deals, lambda d: d["industry"]),
        "size_band": summarize(deals, lambda d: size_band(int(d["employees"]))),
        "region": summarize(deals, lambda d: d["region"]),
        "lead_source": summarize(deals, lambda d: d["lead_source"]),
    }

    # Lift = how much better than baseline a segment converts. Segments below
    # MIN_SAMPLE are pinned to 1.0 (no evidence, no credit).
    weights = {}
    for dim, buckets in dims.items():
        weights[dim] = {}
        for k, s in buckets.items():
            lift = (s["win_rate"] / baseline) if s["deals"] >= MIN_SAMPLE and baseline else 1.0
            weights[dim][k] = round(lift, 3)

    # Normalising against the observed lift range keeps the 0-100 score
    # readable: the best-converting segment on a dimension earns full points,
    # the worst earns none, everything else lands proportionally between.
    lift_range = {}
    for dim, lifts in weights.items():
        credible = [v for k, v in lifts.items()
                    if dims[dim][k]["deals"] >= MIN_SAMPLE]
        lo, hi = (min(credible), max(credible)) if credible else (1.0, 1.0)
        lift_range[dim] = [round(lo, 3), round(hi, 3)]

    profile = {
        "generated_from": os.path.basename(args.deals),
        "deals_analyzed": len(deals),
        "baseline_win_rate": round(baseline, 4),
        "baseline_median_cycle_days": baseline_cycle,
        "min_sample_for_credit": MIN_SAMPLE,
        "dimension_weights": weights,
        "lift_range": lift_range,
        "dimensions": dims,
        # Points available per dimension when scoring. Industry dominates
        # because it carried by far the widest win-rate spread.
        "score_allocation": {"industry": 45, "size_band": 25,
                             "lead_source": 20, "region": 10},
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(profile, fh, indent=2)

    print("GTM SEGMENTATION -- %d closed deals" % len(deals))
    print("Baseline win rate %s | median won-deal cycle %d days | %s won ARR\n"
          % (pct(baseline), baseline_cycle, money(total_won_arr)))
    for dim in ("industry", "size_band", "lead_source"):
        print("%-14s %6s %8s %7s %8s %10s" %
              (dim.upper(), "DEALS", "WIN RATE", "LIFT", "CYCLE", "WON ARR"))
        ranked = sorted(dims[dim].items(), key=lambda kv: -kv[1]["win_rate"])
        for k, s in ranked:
            flag = "" if s["deals"] >= MIN_SAMPLE else "  (low n)"
            print("  %-12s %6d %8s %6.2fx %6s d %10s%s" %
                  (k[:12], s["deals"], pct(s["win_rate"]),
                   weights[dim][k], s["median_cycle_days"] or "-",
                   money(s["won_arr"]), flag))
        print()

    top = sorted(dims["industry"].items(),
                 key=lambda kv: -kv[1]["win_rate"])[:3]
    top_arr = sum(s["won_arr"] for _, s in top)
    top_deals = sum(s["deals"] for _, s in top)
    print("ICP CANDIDATE: %s" % ", ".join(k for k, _ in top))
    print("  %s of won ARR from %s of pipeline volume"
          % (pct(top_arr / total_won_arr), pct(top_deals / len(deals))))
    cyc = [s["median_cycle_days"] for _, s in top if s["median_cycle_days"]]
    if cyc:
        print("  median cycle %d days vs %d overall (%d days shorter)"
              % (sum(cyc) / len(cyc), baseline_cycle,
                 baseline_cycle - sum(cyc) / len(cyc)))
    print("\nProfile written to %s" % os.path.relpath(args.out, HERE))


# ------------------------------------------------------------------ score ----
TIERS = [(75, "A"), (55, "B"), (35, "C"), (0, "D")]
ACTION = {"A": "Route to AE today, personalised outreach",
          "B": "SDR sequence, standard cadence",
          "C": "Nurture campaign only",
          "D": "Do not work -- suppress from outbound"}


def tier_for(score):
    for cut, name in TIERS:
        if score >= cut:
            return name
    return "D"


def score_account(acct, profile):
    alloc = profile["score_allocation"]
    w = profile["dimension_weights"]
    values = {"industry": acct["industry"],
              "size_band": size_band(int(acct["employees"])),
              "lead_source": acct["lead_source"],
              "region": acct["region"]}

    score, reasons = 0.0, []
    for dim, points in alloc.items():
        lift = w.get(dim, {}).get(values[dim], 1.0)
        lo, hi = profile.get("lift_range", {}).get(dim, [0.5, 2.0])
        span = (hi - lo) or 1.0
        share = max(0.0, min(1.0, (lift - lo) / span))
        earned = points * share
        score += earned
        if earned >= points * 0.7:
            reasons.append("%s=%s (%.2fx win rate)" % (dim, values[dim], lift))
        elif earned <= points * 0.3:
            reasons.append("weak %s=%s (%.2fx)" % (dim, values[dim], lift))
    return round(score, 1), reasons


def score(args):
    with open(args.profile) as fh:
        profile = json.load(fh)
    accounts = read_csv(args.accounts)

    scored = []
    for a in accounts:
        s, reasons = score_account(a, profile)
        t = tier_for(s)
        scored.append({"account_id": a["account_id"], "account_name": a["account_name"],
                       "industry": a["industry"], "employees": int(a["employees"]),
                       "region": a["region"], "lead_source": a["lead_source"],
                       "est_arr": int(a["est_arr"]), "icp_score": s, "icp_tier": t,
                       "recommended_action": ACTION[t], "why": "; ".join(reasons[:3])})
    scored.sort(key=lambda r: -r["icp_score"])

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(scored[0].keys()))
        w.writeheader()
        w.writerows(scored)

    counts = defaultdict(int)
    arr_by_tier = defaultdict(int)
    for r in scored:
        counts[r["icp_tier"]] += 1
        arr_by_tier[r["icp_tier"]] += r["est_arr"]

    print("ICP SCORING -- %d open accounts\n" % len(scored))
    print("%-6s %7s %10s   %s" % ("TIER", "ACCTS", "EST ARR", "ACTION"))
    for t in "ABCD":
        if counts[t]:
            print("%-6s %7d %10s   %s" % (t, counts[t], money(arr_by_tier[t]), ACTION[t]))
    focus = counts["A"] + counts["B"]
    print("\nSales works %d of %d accounts (%s) covering %s of estimated ARR"
          % (focus, len(scored), pct(focus / len(scored)),
             pct((arr_by_tier["A"] + arr_by_tier["B"]) / sum(arr_by_tier.values()))))

    print("\nTOP 10 ACCOUNTS")
    for r in scored[:10]:
        print("  %-5s %-26s %5.1f  %-14s %s"
              % (r["icp_tier"], r["account_name"][:26], r["icp_score"],
                 r["industry"][:14], money(r["est_arr"])))

    # What a Zapier / HubSpot workflow would POST back to the CRM.
    payload = [{"properties": {"hs_object_id": r["account_id"],
                               "icp_score": r["icp_score"],
                               "icp_tier": r["icp_tier"],
                               "icp_reason": r["why"]}} for r in scored]
    hs = os.path.join(os.path.dirname(args.out), "hubspot_batch_update.json")
    with open(hs, "w") as fh:
        json.dump({"inputs": payload}, fh, indent=2)
    print("\nWrote %s" % os.path.relpath(args.out, HERE))
    print("Wrote %s  (POST /crm/v3/objects/companies/batch/update)"
          % os.path.relpath(hs, HERE))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("analyze", help="segment closed-won/lost history")
    a.add_argument("--deals", default=DEFAULT_DEALS)
    a.add_argument("--out", default=DEFAULT_PROFILE)
    a.set_defaults(func=analyze)

    s = sub.add_parser("score", help="score open accounts against the profile")
    s.add_argument("--accounts", default=DEFAULT_ACCOUNTS)
    s.add_argument("--profile", default=DEFAULT_PROFILE)
    s.add_argument("--out", default=os.path.join(HERE, "out", "scored_accounts.csv"))
    s.set_defaults(func=score)

    args = p.parse_args()
    if not getattr(args, "func", None):
        p.print_help()
        raise SystemExit(1)
    args.func(args)


if __name__ == "__main__":
    main()
