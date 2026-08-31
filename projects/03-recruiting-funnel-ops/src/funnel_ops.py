#!/usr/bin/env python3
"""Recruiting funnel operations on a Lever-shaped candidate export.

    report   Funnel conversion by stage, time-to-hire against target by
             requisition, source efficiency, and where the process actually
             loses time.

    nudge    Find candidates stalled past the SLA for the stage they are in,
             group them by hiring manager, and write the Slack DMs that ask
             each manager to move their own people -- not a channel blast.

The premise is that time-to-hire is not one number to improve, it is a stack of
stage dwell times, and only two or three of them are actually the problem.

Standard library only. Author: Bonnie Chen
"""

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEF_CAND = os.path.join(HERE, "data", "sample", "lever_candidates.csv")
DEF_REQS = os.path.join(HERE, "data", "sample", "requisitions.csv")

STAGES = ["Applied", "Recruiter Screen", "HM Screen", "Onsite", "Offer", "Hired"]

# Days a candidate may sit in a stage before someone is asked about it. These
# are the service levels the process is held to, not observed averages.
STAGE_SLA = {"Applied": 5, "Recruiter Screen": 7, "HM Screen": 7,
             "Onsite": 10, "Offer": 5}

# Who owns the next action when a candidate stalls in each stage.
STAGE_OWNER = {"Applied": "recruiter", "Recruiter Screen": "recruiter",
               "HM Screen": "hiring_manager", "Onsite": "hiring_manager",
               "Offer": "recruiter"}


def parse_date(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def read_csv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def pct(x):
    return "%.1f%%" % (100 * x)


def stage_index(s):
    return STAGES.index(s) if s in STAGES else 0


def load(args):
    cands = read_csv(args.candidates)
    reqs = {r["req_id"]: r for r in read_csv(args.reqs)}
    return cands, reqs


# ----------------------------------------------------------------- report ----
def funnel(cands):
    """Count how many candidates ever reached each stage.

    `current_stage` is the furthest stage a candidate got to, so reaching stage
    N implies having passed everything before it.
    """
    reached = defaultdict(int)
    for c in cands:
        for i in range(stage_index(c["current_stage"]) + 1):
            reached[STAGES[i]] += 1
    return reached


def report(args):
    cands, reqs = load(args)
    as_of = parse_date(args.as_of)
    reached = funnel(cands)

    print("RECRUITING FUNNEL -- %d candidates across %d open requisitions\n"
          % (len(cands), len(reqs)))
    print("%-18s %8s %12s %10s" % ("STAGE", "REACHED", "STEP CONV", "CUM CONV"))
    top = reached[STAGES[0]] or 1
    for i, s in enumerate(STAGES):
        prev = reached[STAGES[i - 1]] if i else reached[s]
        step = reached[s] / prev if prev else 0
        print("%-18s %8d %11s %10s"
              % (s, reached[s], "-" if i == 0 else pct(step), pct(reached[s] / top)))

    hires = [c for c in cands if c["status"] == "hired" and c["hired_date"]]
    tth = [(parse_date(c["hired_date"]) - parse_date(c["applied_date"])).days for c in hires]
    print("\nTIME TO HIRE   %d hires   median %s days   range %s-%s"
          % (len(hires), median(tth), min(tth) if tth else "-", max(tth) if tth else "-"))

    # Where the days actually go. This measures candidates *currently* sitting
    # in each stage -- the live queue, not history. A rejected candidate's
    # dwell time tells you when a decision was recorded, not how long the
    # process took, so including them would flatter every stage.
    dwell = defaultdict(list)
    for c in cands:
        if c["status"] != "active":
            continue
        dwell[c["current_stage"]].append(
            max(0, (as_of - parse_date(c["stage_entered_date"])).days))
    print("\nWAITING NOW (active candidates only)")
    print("%-18s %6s %8s %8s %9s" % ("STAGE", "N", "MEDIAN", "SLA", "STATUS"))
    for s in STAGES[:-1]:
        m = median(dwell.get(s, []))
        if m is None:
            continue
        sla = STAGE_SLA[s]
        print("%-18s %6d %6s d %6d d %9s"
              % (s, len(dwell[s]), m, sla, "OVER" if m > sla else "ok"))

    print("\n%-14s %7s %8s %7s %9s %10s"
          % ("SOURCE", "APPS", "ONSITE+", "HIRES", "APP->HIRE", "QUALITY"))
    by_src = defaultdict(lambda: {"apps": 0, "onsite": 0, "hires": 0})
    for c in cands:
        b = by_src[c["source"]]
        b["apps"] += 1
        if stage_index(c["current_stage"]) >= stage_index("Onsite"):
            b["onsite"] += 1
        if c["status"] == "hired":
            b["hires"] += 1
    ranked = sorted(by_src.items(), key=lambda kv: -(kv[1]["hires"] / max(kv[1]["apps"], 1)))
    for src, b in ranked:
        quality = b["onsite"] / b["apps"] if b["apps"] else 0
        print("%-14s %7d %8d %7d %9s %10s"
              % (src[:14], b["apps"], b["onsite"], b["hires"],
                 pct(b["hires"] / b["apps"]) if b["apps"] else "-", pct(quality)))

    print("\n%-30s %6s %8s %8s %8s"
          % ("REQUISITION", "OPEN", "TARGET", "ACTIVE", "AT RISK"))
    req_rows = []
    for rid, r in sorted(reqs.items()):
        days_open = (as_of - parse_date(r["opened_date"])).days
        active = [c for c in cands if c["req_id"] == rid and c["status"] == "active"]
        late = days_open > int(r["target_days_to_hire"])
        deep = [c for c in active if stage_index(c["current_stage"]) >= stage_index("HM Screen")]
        at_risk = late and not deep
        req_rows.append({"req_id": rid, "role": r["role"],
                         "department": r["department"],
                         "hiring_manager": r["hiring_manager"],
                         "days_open": days_open,
                         "target_days": int(r["target_days_to_hire"]),
                         "active_candidates": len(active),
                         "late_stage_candidates": len(deep),
                         "at_risk": at_risk})
        print("%-30s %5dd %7dd %8d %8s"
              % (r["role"][:30], days_open, int(r["target_days_to_hire"]),
                 len(active), "YES" if at_risk else ""))

    metrics = {
        "as_of": args.as_of,
        "candidates": len(cands),
        "funnel": {s: reached[s] for s in STAGES},
        "step_conversion": {STAGES[i]: round(reached[STAGES[i]] / reached[STAGES[i - 1]], 4)
                            for i in range(1, len(STAGES)) if reached[STAGES[i - 1]]},
        "time_to_hire": {"hires": len(hires), "median_days": median(tth),
                         "min_days": min(tth) if tth else None,
                         "max_days": max(tth) if tth else None},
        "median_days_waiting": {s: median(v) for s, v in dwell.items()},
        "active_in_stage": {s: len(v) for s, v in dwell.items()},
        "stage_sla_days": STAGE_SLA,
        "sources": {k: dict(v, app_to_hire=round(v["hires"] / v["apps"], 4) if v["apps"] else 0)
                    for k, v in by_src.items()},
        "requisitions": req_rows,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "funnel_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)
    write_report_md(os.path.join(args.out_dir, "funnel_report.md"), metrics)

    over_sla = sum(1 for c in cands if c["status"] == "active"
                   and c["current_stage"] in STAGE_SLA
                   and (as_of - parse_date(c["stage_entered_date"])).days
                   > STAGE_SLA[c["current_stage"]])
    active_n = sum(1 for c in cands if c["status"] == "active")
    worst = [(median(v) - STAGE_SLA[s], s) for s, v in dwell.items()
             if v and s in STAGE_SLA]
    if worst:
        gap, stage = max(worst)
        print("\nBOTTLENECK: %s -- median wait %s days against a %d-day SLA. "
              "%d of %d active candidates are past SLA somewhere in the funnel; "
              "run `nudge` to route them to the person who owes the next action."
              % (stage, median(dwell[stage]), STAGE_SLA[stage], over_sla, active_n))
    print("\nWrote funnel_metrics.json, funnel_report.md to %s"
          % os.path.relpath(args.out_dir, HERE))


def write_report_md(path, m):
    L = ["# Recruiting Funnel Report\n",
         "_Prepared by Bonnie Chen · as of %s · %d candidates_\n"
         % (m["as_of"], m["candidates"]),
         "## Funnel\n", "| Stage | Reached | Step conversion |", "|---|---:|---:|"]
    for i, s in enumerate(STAGES):
        conv = m["step_conversion"].get(s)
        L.append("| %s | %d | %s |" % (s, m["funnel"][s],
                                       pct(conv) if conv is not None else "—"))
    t = m["time_to_hire"]
    L += ["", "## Time to hire\n",
          "Median **%s days** across %d hires (range %s–%s).\n"
          % (t["median_days"], t["hires"], t["min_days"], t["max_days"]),
          "## Where candidates are waiting now\n",
          "| Stage | Active | Median wait | SLA | Status |", "|---|---:|---:|---:|---|"]
    for s in STAGES[:-1]:
        d = m["median_days_waiting"].get(s)
        if d is None:
            continue
        sla = m["stage_sla_days"][s]
        L.append("| %s | %d | %s d | %d d | %s |"
                 % (s, m["active_in_stage"][s], d, sla,
                    "**over**" if d > sla else "ok"))
    L += ["", "## Source efficiency\n",
          "| Source | Applications | Hires | App→hire |", "|---|---:|---:|---:|"]
    for src, b in sorted(m["sources"].items(), key=lambda kv: -kv[1]["app_to_hire"]):
        L.append("| %s | %d | %d | %s |" % (src, b["apps"], b["hires"],
                                            pct(b["app_to_hire"])))
    at_risk = [r for r in m["requisitions"] if r["at_risk"]]
    L += ["", "## Requisitions at risk\n"]
    if at_risk:
        L += ["| Req | Role | Manager | Days open | Target | Late-stage candidates |",
              "|---|---|---|---:|---:|---:|"]
        for r in at_risk:
            L.append("| %s | %s | %s | %d | %d | %d |"
                     % (r["req_id"], r["role"], r["hiring_manager"],
                        r["days_open"], r["target_days"], r["late_stage_candidates"]))
        L.append("\nOpen past target with nobody past HM screen — these need new "
                 "sourcing, not more pipeline review.\n")
    else:
        L.append("None.\n")
    L.append("---\n_Synthetic data. No real candidate information appears in this repository._")
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")


# ------------------------------------------------------------------ nudge ----
def nudge(args):
    cands, reqs = load(args)
    as_of = parse_date(args.as_of)

    stalled = []
    for c in cands:
        if c["status"] != "active" or c["current_stage"] == "Hired":
            continue
        sla = STAGE_SLA.get(c["current_stage"])
        if sla is None:
            continue
        in_stage = (as_of - parse_date(c["stage_entered_date"])).days
        quiet = (as_of - parse_date(c["last_activity_date"])).days
        if in_stage <= sla:
            continue
        stalled.append({
            "candidate_id": c["candidate_id"], "candidate_name": c["candidate_name"],
            "req_id": c["req_id"], "role": c["role"],
            "hiring_manager": c["hiring_manager"], "stage": c["current_stage"],
            "days_in_stage": in_stage, "days_since_activity": quiet,
            "sla_days": sla, "days_over_sla": in_stage - sla,
            "action_owner": STAGE_OWNER[c["current_stage"]],
            # Two weeks past SLA in an interview stage is where candidates start
            # accepting other offers, so it escalates rather than nags.
            "severity": "escalate" if in_stage - sla > 14 else "nudge",
        })
    stalled.sort(key=lambda r: -r["days_over_sla"])

    os.makedirs(args.out_dir, exist_ok=True)
    out_csv = os.path.join(args.out_dir, "stalled_candidates.csv")
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(stalled[0].keys()))
        w.writeheader()
        w.writerows(stalled)

    by_hm = defaultdict(list)
    for s in stalled:
        if s["action_owner"] == "hiring_manager":
            by_hm[s["hiring_manager"]].append(s)

    messages = []
    for hm, items in sorted(by_hm.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda r: -r["days_over_sla"])
        lines = ["*%s* — %d candidate%s waiting on you"
                 % (hm, len(items), "" if len(items) == 1 else "s")]
        for s in items[:8]:
            lines.append("• %s — %s, %s (%d days in stage, %d over SLA)"
                         % (s["candidate_name"], s["role"], s["stage"],
                            s["days_in_stage"], s["days_over_sla"]))
        if len(items) > 8:
            lines.append("_…and %d more in the full list._" % (len(items) - 8))
        messages.append({
            "hiring_manager": hm,
            "escalations": sum(1 for s in items if s["severity"] == "escalate"),
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
                {"type": "context", "elements": [{"type": "mrkdwn",
                 "text": "Reply in thread if any of these should be closed out — "
                         "an honest reject is faster than a silent one."}]},
            ],
        })

    with open(os.path.join(args.out_dir, "slack_nudges.json"), "w") as fh:
        json.dump({"messages": messages}, fh, indent=2)

    esc = sum(1 for s in stalled if s["severity"] == "escalate")
    print("STALLED CANDIDATES -- %d past stage SLA (%d escalations)\n"
          % (len(stalled), esc))
    print("%-22s %-26s %-16s %6s %6s" % ("CANDIDATE", "ROLE", "STAGE", "IN", "OVER"))
    for s in stalled[:15]:
        print("%-22s %-26s %-16s %5dd %5dd"
              % (s["candidate_name"][:22], s["role"][:26], s["stage"],
                 s["days_in_stage"], s["days_over_sla"]))
    if len(stalled) > 15:
        print("... %d more in stalled_candidates.csv" % (len(stalled) - 15))

    owner_counts = defaultdict(int)
    for s in stalled:
        owner_counts[s["action_owner"]] += 1
    print("\nNEXT ACTION SITS WITH:")
    for owner, n in sorted(owner_counts.items(), key=lambda kv: -kv[1]):
        print("  %-16s %d candidates" % (owner.replace("_", " "), n))
    print("\n%d hiring-manager DMs queued in slack_nudges.json" % len(messages))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--candidates", default=DEF_CAND)
    p.add_argument("--reqs", default=DEF_REQS)
    p.add_argument("--as-of", default="2026-06-30")
    p.add_argument("--out-dir", default=os.path.join(HERE, "out"))
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("report", help="funnel, time-to-hire and source metrics")
    r.set_defaults(func=report)
    n = sub.add_parser("nudge", help="stalled candidates and hiring-manager DMs")
    n.set_defaults(func=nudge)
    args = p.parse_args()
    if not getattr(args, "func", None):
        p.print_help()
        raise SystemExit(1)
    args.func(args)


if __name__ == "__main__":
    main()
