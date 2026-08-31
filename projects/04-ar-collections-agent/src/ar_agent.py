#!/usr/bin/env python3
"""Accounts receivable aging and a dunning agent.

    aging     AR aging buckets, DSO, delinquency rate, on-time payment rate,
              and the concentration analysis that says whether you have a
              collections problem or three difficult customers.

    dunning   Build the collections queue. Every open invoice is placed in an
              escalation tier by days overdue, disputes are pulled out of the
              automated cadence entirely, and anyone contacted in the last
              seven days is suppressed. Emits ready-to-send drafts, a Slack
              digest, and the call list.

The design principle: automate the cadence, never the judgement. Disputes,
large balances and strategic accounts always route to a person.

Standard library only. Author: Bonnie Chen
"""

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEF_INV = os.path.join(HERE, "data", "sample", "invoices.csv")

BUCKETS = [(0, 0, "Current"), (1, 30, "1-30"), (31, 60, "31-60"),
           (61, 90, "61-90"), (91, 10 ** 6, "90+")]

# Escalation ladder. Each tier names the channel and who owns the action --
# an alert with no owner is not a process.
TIERS = [
    (1, 14, "reminder", "automated email", "AR owner",
     "Friendly reminder, payment link included"),
    (15, 30, "second notice", "email + AE copied", "AR owner",
     "Second notice; account team looped in"),
    (31, 60, "escalation", "call + email to AP lead", "AR owner",
     "Phone call required; renewal flagged to CS"),
    (61, 10 ** 6, "collections review", "finance lead", "Finance lead",
     "Manual review: payment plan, credit hold, or write-off"),
]

# Never auto-dun above this balance -- a large invoice gets a call first.
MANUAL_REVIEW_ABOVE = 100000
# Do not contact the same account twice inside this window.
CONTACT_COOLDOWN_DAYS = 7


def parse_date(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def read_csv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def money(x):
    if abs(x) >= 1e6:
        return "$%.2fM" % (x / 1e6)
    return "$%.1fK" % (x / 1e3)


def pct(x):
    return "%.1f%%" % (100 * x)


def bucket_for(days):
    for lo, hi, label in BUCKETS:
        if lo <= days <= hi:
            return label
    return "Current"


def enrich(invoices, as_of):
    rows = []
    for i in invoices:
        amount = float(i["amount"])
        paid = float(i["amount_paid"])
        due = parse_date(i["due_date"])
        outstanding = amount - paid
        overdue_days = (as_of - due).days if due < as_of else 0
        rows.append(dict(
            i, amount=amount, amount_paid=paid, outstanding=outstanding,
            issue=parse_date(i["issue_date"]), due=due,
            paid_on=parse_date(i["paid_date"]) if i["paid_date"] else None,
            overdue_days=overdue_days if i["status"] != "paid" else 0,
            bucket=bucket_for(overdue_days) if i["status"] != "paid" else "Paid",
        ))
    return rows


# ------------------------------------------------------------------ aging ----
def aging(args):
    as_of = parse_date(args.as_of)
    rows = enrich(read_csv(args.invoices), as_of)
    open_rows = [r for r in rows if r["status"] != "paid" and r["outstanding"] > 0]

    total_ar = sum(r["outstanding"] for r in open_rows)
    by_bucket = defaultdict(float)
    count_bucket = defaultdict(int)
    for r in open_rows:
        by_bucket[r["bucket"]] += r["outstanding"]
        count_bucket[r["bucket"]] += 1
    overdue = sum(v for k, v in by_bucket.items() if k != "Current")
    past_30 = sum(v for k, v in by_bucket.items() if k in ("31-60", "61-90", "90+"))

    # DSO on the last 90 days of billing (the standard countback approximation).
    window_start = date.fromordinal(as_of.toordinal() - 90)
    billed_90 = sum(r["amount"] for r in rows if r["issue"] >= window_start)
    dso = (total_ar / billed_90 * 90) if billed_90 else 0

    settled = [r for r in rows if r["status"] == "paid" and r["paid_on"]]
    on_time = sum(1 for r in settled if r["paid_on"] <= r["due"])
    avg_days_late = (sum(max(0, (r["paid_on"] - r["due"]).days) for r in settled)
                     / len(settled)) if settled else 0

    print("AR AGING -- as of %s\n" % args.as_of)
    print("%-10s %6s %14s %9s" % ("BUCKET", "INV", "OUTSTANDING", "SHARE"))
    for _, _, label in BUCKETS:
        if count_bucket[label]:
            print("%-10s %6d %14s %9s"
                  % (label, count_bucket[label], money(by_bucket[label]),
                     pct(by_bucket[label] / total_ar)))
    print("%-10s %6d %14s" % ("TOTAL", len(open_rows), money(total_ar)))

    print("\nDSO                     %.0f days" % dso)
    print("Delinquency rate        %s of open AR is past due" % pct(overdue / total_ar))
    print("Seriously past due      %s is 30+ days late" % pct(past_30 / total_ar))
    print("On-time payment rate    %s of settled invoices (%d of %d)"
          % (pct(on_time / len(settled)), on_time, len(settled)))
    print("Average days late       %.1f days when late" % avg_days_late)

    by_cust = defaultdict(float)
    late_count = defaultdict(int)
    for r in open_rows:
        if r["bucket"] != "Current":
            by_cust[r["customer_name"]] += r["outstanding"]
            late_count[r["customer_name"]] += 1
    worst = sorted(by_cust.items(), key=lambda kv: -kv[1])[:8]
    if worst:
        top5 = sum(v for _, v in worst[:5])
        print("\nCONCENTRATION -- top 5 overdue accounts are %s of all overdue AR"
              % pct(top5 / overdue))
        print("%-30s %12s %8s" % ("ACCOUNT", "OVERDUE", "INVOICES"))
        for name, amt in worst:
            print("%-30s %12s %8d" % (name[:30], money(amt), late_count[name]))

    by_seg = defaultdict(lambda: [0.0, 0.0])
    for r in open_rows:
        by_seg[r["segment"]][0] += r["outstanding"]
        if r["bucket"] != "Current":
            by_seg[r["segment"]][1] += r["outstanding"]
    print("\n%-14s %13s %13s %9s" % ("SEGMENT", "OPEN AR", "OVERDUE", "RATE"))
    for seg, (tot, od) in sorted(by_seg.items(), key=lambda kv: -kv[1][1]):
        print("%-14s %13s %13s %9s" % (seg, money(tot), money(od), pct(od / tot)))

    disputed = [r for r in open_rows if r["status"] == "disputed"]
    if disputed:
        print("\nDISPUTED  %d invoices, %s -- excluded from automated dunning"
              % (len(disputed), money(sum(r["outstanding"] for r in disputed))))

    metrics = {
        "as_of": args.as_of, "open_invoices": len(open_rows),
        "total_ar": round(total_ar), "dso_days": round(dso, 1),
        "delinquency_rate": round(overdue / total_ar, 4) if total_ar else 0,
        "past_30_rate": round(past_30 / total_ar, 4) if total_ar else 0,
        "on_time_payment_rate": round(on_time / len(settled), 4) if settled else None,
        "avg_days_late": round(avg_days_late, 1),
        "aging": {label: round(by_bucket[label]) for _, _, label in BUCKETS},
        "by_segment": {k: {"open_ar": round(v[0]), "overdue": round(v[1])}
                       for k, v in by_seg.items()},
        "top_overdue_accounts": [{"account": n, "overdue": round(a)} for n, a in worst],
        "disputed_value": round(sum(r["outstanding"] for r in disputed)),
    }
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "ar_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)
    print("\nWrote ar_metrics.json to %s" % os.path.relpath(args.out_dir, HERE))


# ---------------------------------------------------------------- dunning ----
def tier_for(days):
    for lo, hi, name, channel, owner, action in TIERS:
        if lo <= days <= hi:
            return name, channel, owner, action
    return None


EMAIL_TEMPLATES = {
    "reminder": (
        "Subject: Invoice {invoice_id} — now past due\n\n"
        "Hi,\n\n"
        "Invoice {invoice_id} for {amount} was due on {due_date} and shows as "
        "outstanding on our side. If it is already scheduled for payment, please "
        "ignore this note and let me know the date.\n\n"
        "Payment link and a copy of the invoice are attached.\n\n"
        "Best,\n{owner}"),
    "second notice": (
        "Subject: Second notice — invoice {invoice_id}, {days} days past due\n\n"
        "Hi,\n\n"
        "Invoice {invoice_id} for {amount} is now {days} days past due. I have "
        "copied {ae_note} so we can sort out anything blocking approval on your "
        "side.\n\n"
        "If there is an issue with the invoice itself, tell me and I will open a "
        "dispute rather than keep chasing payment.\n\n"
        "Best,\n{owner}"),
    "escalation": (
        "Subject: Invoice {invoice_id} — {days} days past due, need a call\n\n"
        "Hi,\n\n"
        "Invoice {invoice_id} for {amount} is {days} days past due and past the "
        "point where email is working. Could we find fifteen minutes this week to "
        "agree a payment date?\n\n"
        "Flagging that balances at this age affect renewal terms, so I would "
        "rather resolve it with you directly.\n\n"
        "Best,\n{owner}"),
}


def dunning(args):
    as_of = parse_date(args.as_of)
    rows = enrich(read_csv(args.invoices), as_of)
    open_rows = [r for r in rows if r["status"] != "paid" and r["outstanding"] > 0]

    queue, suppressed = [], []
    for r in open_rows:
        days = r["overdue_days"]
        if days < 1:
            continue
        t = tier_for(days)
        if not t:
            continue
        name, channel, owner, action = t

        reason = None
        if r["status"] == "disputed":
            reason = "disputed — route to dispute resolution, not dunning"
        elif r["outstanding"] > MANUAL_REVIEW_ABOVE:
            reason = "balance over %s — call before any automated contact" % money(MANUAL_REVIEW_ABOVE)
        elif r["last_reminder_sent"]:
            since = (as_of - parse_date(r["last_reminder_sent"])).days
            if since < CONTACT_COOLDOWN_DAYS:
                reason = "contacted %d days ago — inside the %d-day cooldown" % (
                    since, CONTACT_COOLDOWN_DAYS)

        item = {
            "invoice_id": r["invoice_id"], "customer_name": r["customer_name"],
            "segment": r["segment"], "outstanding": round(r["outstanding"], 2),
            "due_date": r["due_date"], "days_overdue": days, "bucket": r["bucket"],
            "tier": name, "channel": channel, "action_owner": r["ar_owner"],
            "escalate_to": owner, "action": action,
            "billing_contact": r["billing_contact"],
            "automated": reason is None, "hold_reason": reason or "",
        }
        (queue if reason is None else suppressed).append(item)

    queue.sort(key=lambda x: (-x["days_overdue"], -x["outstanding"]))
    suppressed.sort(key=lambda x: -x["outstanding"])

    os.makedirs(args.out_dir, exist_ok=True)
    all_items = queue + suppressed
    with open(os.path.join(args.out_dir, "dunning_queue.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(all_items[0].keys()))
        w.writeheader()
        w.writerows(all_items)

    drafts = []
    for q in queue:
        tpl = EMAIL_TEMPLATES.get(q["tier"])
        if not tpl:
            continue
        drafts.append("## %s — %s (%s, %d days overdue)\n\n```\n%s\n```\n"
                      % (q["invoice_id"], q["customer_name"], money(q["outstanding"]),
                         q["days_overdue"],
                         tpl.format(invoice_id=q["invoice_id"],
                                    amount=money(q["outstanding"]),
                                    due_date=q["due_date"], days=q["days_overdue"],
                                    owner=q["action_owner"],
                                    ae_note="the account team")))
    with open(os.path.join(args.out_dir, "email_drafts.md"), "w") as fh:
        fh.write("# Collections drafts — %s\n\n_Review before sending. "
                 "Nothing here goes out automatically above %s._\n\n%s"
                 % (args.as_of, money(MANUAL_REVIEW_ABOVE), "\n".join(drafts)))

    by_tier = defaultdict(lambda: {"n": 0, "amount": 0.0})
    for q in queue:
        by_tier[q["tier"]]["n"] += 1
        by_tier[q["tier"]]["amount"] += q["outstanding"]

    total_q = sum(q["outstanding"] for q in queue)
    print("DUNNING QUEUE -- as of %s\n" % args.as_of)
    print("%-20s %6s %14s   %s" % ("TIER", "INV", "AMOUNT", "CHANNEL"))
    for _, _, name, channel, owner, action in TIERS:
        if by_tier[name]["n"]:
            print("%-20s %6d %14s   %s"
                  % (name, by_tier[name]["n"], money(by_tier[name]["amount"]), channel))
    print("%-20s %6d %14s" % ("TOTAL AUTOMATED", len(queue), money(total_q)))

    if suppressed:
        print("\nHELD BACK FROM AUTOMATION -- %d invoices, %s"
              % (len(suppressed), money(sum(s["outstanding"] for s in suppressed))))
        for s in suppressed[:8]:
            print("  %-11s %-24s %10s  %s"
                  % (s["invoice_id"], s["customer_name"][:24],
                     money(s["outstanding"]), s["hold_reason"]))
        if len(suppressed) > 8:
            print("  ... %d more in dunning_queue.csv" % (len(suppressed) - 8))

    print("\nOLDEST BALANCES")
    for q in queue[:8]:
        print("  %-11s %-24s %10s %5dd  %s"
              % (q["invoice_id"], q["customer_name"][:24], money(q["outstanding"]),
                 q["days_overdue"], q["tier"]))

    calls = [q for q in queue if q["tier"] in ("escalation", "collections review")]
    blocks = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": "Collections queue — %s" % args.as_of}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": "*In queue*\n%d invoices · %s"
             % (len(queue), money(total_q))},
            {"type": "mrkdwn", "text": "*Needs a call*\n%d accounts" % len(calls)},
            {"type": "mrkdwn", "text": "*Held for review*\n%d invoices · %s"
             % (len(suppressed), money(sum(s["outstanding"] for s in suppressed)))},
            {"type": "mrkdwn", "text": "*Oldest*\n%d days"
             % (queue[0]["days_overdue"] if queue else 0)},
        ]},
    ]
    if calls:
        lines = ["*Call list — email has stopped working on these:*"]
        for c in calls[:6]:
            lines.append("• %s — %s, %d days (%s)"
                         % (c["customer_name"], money(c["outstanding"]),
                            c["days_overdue"], c["action_owner"]))
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
                   "text": "Drafts are queued for review — nothing sends without "
                           "a human clicking send."}]})
    with open(os.path.join(args.out_dir, "slack_digest.json"), "w") as fh:
        json.dump({"channel": "#finance-ops", "blocks": blocks}, fh, indent=2)

    print("\nWrote dunning_queue.csv, email_drafts.md, slack_digest.json to %s"
          % os.path.relpath(args.out_dir, HERE))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--invoices", default=DEF_INV)
    p.add_argument("--as-of", default="2026-06-30")
    p.add_argument("--out-dir", default=os.path.join(HERE, "out"))
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("aging", help="aging buckets, DSO, delinquency")
    a.set_defaults(func=aging)
    dn = sub.add_parser("dunning", help="collections queue and drafts")
    dn.set_defaults(func=dunning)
    args = p.parse_args()
    if not getattr(args, "func", None):
        p.print_help()
        raise SystemExit(1)
    args.func(args)


if __name__ == "__main__":
    main()
