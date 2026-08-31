"""Generate the synthetic datasets used by every project in this repo.

Nothing here is real. No employer data, customer data, or candidate data appears
anywhere in this repository. The generator is seeded, so `python3 tools/make_sample_data.py`
reproduces byte-identical CSVs and every documented number in the READMEs stays true.

The distributions are deliberately shaped to mirror the patterns described in the
case studies on bonniechen88.github.io -- privacy-regulated verticals convert
better, tool sprawl clusters in a few categories, agency sourcing is expensive --
so the scripts have something real to find.

Author: Bonnie Chen
"""

import csv
import os
import random
from datetime import date, timedelta

SEED = 8801
AS_OF = date(2026, 6, 30)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

rng = random.Random(SEED)


def out(project, name):
    path = os.path.join(ROOT, "projects", project, "data", "sample", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def write(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print("wrote %-58s %4d rows" % (os.path.relpath(path, ROOT), len(rows)))


def d(dt):
    return dt.isoformat()


# --------------------------------------------------------------------------
# Shared vocabulary
# --------------------------------------------------------------------------
REGULATED = ["Healthcare", "Banking", "Pharmaceuticals"]
OTHER_INDUSTRIES = ["Retail", "Manufacturing", "Media", "Logistics",
                    "Education", "Hospitality", "Real Estate"]
INDUSTRIES = REGULATED + OTHER_INDUSTRIES
REGIONS = ["US-East", "US-West", "Canada", "UK/EU"]
SOURCES = ["Outbound SDR", "Inbound Demo", "Partner Referral",
           "Webinar", "Paid Search", "Conference"]

PREFIX = ["Vault", "Nova", "Clearwave", "Northbridge", "Kestrel", "Halden",
          "Brightline", "Meridian", "Ardent", "Copperfield", "Silverpine",
          "Tessera", "Junction", "Lattice", "Foxglove", "Ironwood", "Peregrine",
          "Marlowe", "Sable", "Wren", "Cobalt", "Thornbury", "Aldergrove",
          "Bellamy", "Cascadia", "Dunmore", "Everly", "Fairhaven", "Glenmore",
          "Harrowgate", "Inverness", "Jesmond", "Kingsley", "Langford",
          "Maplewood", "Nightingale", "Oakhurst", "Pemberton", "Quarry Hill",
          "Redbourne", "Stonegate", "Tamarack", "Umberton", "Vantage",
          "Westmere", "Yarrow", "Ashcombe", "Braemar", "Carrickfern",
          "Dalhousie", "Elderwood", "Fenwick", "Grayling", "Hollingsworth",
          "Ivywood", "Jarvis", "Kilmarnock", "Loxley", "Merrivale", "Norbury"]
SUFFIX = ["Health", "Systems", "Labs", "Group", "Partners", "Logistics",
          "Financial", "Diagnostics", "Analytics", "Networks", "Holdings",
          "Bioscience", "Retail Co", "Media", "Industries", "Therapeutics",
          "Capital", "Clinical", "Technologies", "Robotics", "Foods",
          "Insurance", "Aviation", "Materials"]

_used_names = set()


def company_name():
    """Unique-ish fake company names. Falls back to a numeric suffix once the
    prefix x suffix space is exhausted, so this never spins."""
    for _ in range(40):
        n = "%s %s" % (rng.choice(PREFIX), rng.choice(SUFFIX))
        if n not in _used_names:
            _used_names.add(n)
            return n
    n = "%s %s %d" % (rng.choice(PREFIX), rng.choice(SUFFIX), len(_used_names))
    _used_names.add(n)
    return n


# --------------------------------------------------------------------------
# 02a -- Salesforce open pipeline
# --------------------------------------------------------------------------
STAGES = ["Discovery", "Qualification", "Proposal", "Negotiation", "Contracting"]
SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]
AE_NAMES = ["D. Okafor", "M. Reyes", "S. Lindqvist", "J. Baptiste",
            "R. Chowdhury", "T. Nakamura", "A. Whitfield"]
NEXT_STEPS = ["Security review scheduled", "Pricing sent, awaiting legal",
              "Champion intro to CFO", "Pilot scoping call", "Redlines returned",
              "Procurement portal submitted", ""]


def gen_pipeline():
    rows = []
    for i in range(140):
        seg = rng.choices(SEGMENTS, weights=[45, 35, 20])[0]
        industry = rng.choices(INDUSTRIES, weights=[16, 14, 10] + [6] * 7)[0]
        stage = rng.choices(STAGES, weights=[32, 26, 20, 14, 8])[0]

        base = {"SMB": 24000, "Mid-Market": 85000, "Enterprise": 310000}[seg]
        amount = int(base * rng.uniform(0.55, 1.9) / 500) * 500
        # A handful of records with no amount -- real CRMs always have these.
        if rng.random() < 0.05:
            amount = 0

        age = int(rng.gauss({"SMB": 38, "Mid-Market": 74, "Enterprise": 132}[seg], 34))
        age = max(5, age)
        created = AS_OF - timedelta(days=age)

        # Roughly a third of the book has gone quiet; Enterprise goes quiet longest.
        if rng.random() < 0.34:
            inactive = int(rng.uniform(31, min(age, 190) + 1))
        else:
            inactive = int(rng.uniform(0, 30))
        inactive = min(inactive, age)
        last_activity = AS_OF - timedelta(days=inactive)

        close = AS_OF + timedelta(days=int(rng.gauss(45, 55)))
        if rng.random() < 0.18:                      # past-due close dates
            close = AS_OF - timedelta(days=int(rng.uniform(1, 120)))

        fc = {"Discovery": "Pipeline", "Qualification": "Pipeline",
              "Proposal": "Best Case", "Negotiation": "Commit",
              "Contracting": "Commit"}[stage]
        if rng.random() < 0.09:                      # optimistic categorisation
            fc = "Commit"

        rows.append([
            "0068D%05d" % (41000 + i), company_name(), industry, seg,
            rng.choice(AE_NAMES), amount, stage, fc,
            d(created), d(close), d(last_activity),
            rng.choices(NEXT_STEPS, weights=[15, 15, 12, 12, 10, 10, 26])[0],
        ])
    write(out("02-revenue-reporting-pack", "salesforce_opportunities.csv"),
          ["opportunity_id", "account_name", "industry", "segment", "owner",
           "amount", "stage", "forecast_category", "created_date", "close_date",
           "last_activity_date", "next_step"], rows)


# --------------------------------------------------------------------------
# 01 -- Closed-won / closed-lost history + open accounts to score
# --------------------------------------------------------------------------
def gen_icp():
    closed = []
    for i in range(420):
        industry = rng.choices(INDUSTRIES, weights=[15, 13, 10] + [8.9] * 7)[0]
        regulated = industry in REGULATED
        employees = int(rng.choices([80, 260, 900, 3200, 11000],
                                    weights=[26, 28, 22, 16, 8])[0]
                        * rng.uniform(0.6, 1.5))
        region = rng.choices(REGIONS, weights=[38, 24, 22, 16])[0]
        source = rng.choices(SOURCES, weights=[24, 22, 14, 16, 14, 10])[0]

        # Compliance-driven urgency is the ICP signal the VaultIQ study found.
        p_win = 0.19
        if regulated:
            p_win += 0.28
        if 200 <= employees <= 4000:
            p_win += 0.07
        if source in ("Partner Referral", "Inbound Demo"):
            p_win += 0.09
        if region == "UK/EU" and regulated:
            p_win += 0.04
        won = rng.random() < min(p_win, 0.82)

        cycle = rng.gauss(96 if not regulated else 77, 22)
        if employees > 4000:
            cycle += 26
        cycle = int(max(14, cycle))

        arr = int(max(9000, rng.gauss(employees * 42, employees * 14)) / 1000) * 1000
        close = AS_OF - timedelta(days=int(rng.uniform(1, 730)))

        closed.append(["D-%05d" % (10000 + i), company_name(), industry, employees,
                       region, source, arr, "won" if won else "lost", cycle, d(close)])
    write(out("01-gtm-segmentation-icp", "closed_deals.csv"),
          ["deal_id", "account_name", "industry", "employees", "region",
           "lead_source", "arr", "outcome", "cycle_days", "close_date"], closed)

    openacc = []
    for i in range(75):
        industry = rng.choice(INDUSTRIES)
        employees = int(rng.choices([70, 240, 850, 3000, 9500],
                                    weights=[24, 27, 23, 17, 9])[0]
                        * rng.uniform(0.6, 1.5))
        openacc.append([
            "A-%05d" % (7000 + i), company_name(), industry, employees,
            rng.choices(REGIONS, weights=[38, 24, 22, 16])[0],
            rng.choice(SOURCES),
            int(max(12000, rng.gauss(employees * 40, employees * 15)) / 1000) * 1000,
            d(AS_OF - timedelta(days=int(rng.uniform(3, 160)))),
        ])
    write(out("01-gtm-segmentation-icp", "open_accounts.csv"),
          ["account_id", "account_name", "industry", "employees", "region",
           "lead_source", "est_arr", "created_date"], openacc)


# --------------------------------------------------------------------------
# 03 -- Lever recruiting funnel
# --------------------------------------------------------------------------
ATS_STAGES = ["Applied", "Recruiter Screen", "HM Screen", "Onsite", "Offer", "Hired"]
REQS = [
    ("REQ-201", "Senior Account Executive", "Sales", "D. Okafor", 45),
    ("REQ-202", "Sales Development Rep", "Sales", "D. Okafor", 30),
    ("REQ-203", "Revenue Operations Analyst", "Revenue Ops", "B. Chen", 40),
    ("REQ-204", "Data Engineer", "Data", "P. Anand", 55),
    ("REQ-205", "Analytics Engineer", "Data", "P. Anand", 50),
    ("REQ-206", "Product Designer", "Product", "L. Moreau", 45),
    ("REQ-207", "Backend Engineer", "Engineering", "K. Osei", 55),
    ("REQ-208", "Backend Engineer II", "Engineering", "K. Osei", 55),
    ("REQ-209", "Customer Success Manager", "Customer Success", "R. Iyer", 35),
    ("REQ-210", "Implementation Consultant", "Customer Success", "R. Iyer", 40),
    ("REQ-211", "Finance Manager", "Finance", "S. Adeyemi", 45),
    ("REQ-212", "People Ops Coordinator", "People Ops", "N. Kowalski", 30),
]
ATS_SOURCES = ["Agency", "Referral", "Inbound Application", "LinkedIn Outbound",
               "Job Board", "Career Fair"]
FIRST = ["Amara", "Jonas", "Priya", "Tomas", "Wei", "Sofia", "Liam", "Nadia",
         "Ravi", "Elena", "Marcus", "Yuki", "Dara", "Owen", "Isla", "Hugo",
         "Zara", "Felix", "Noor", "Ada", "Bram", "Cleo", "Dmitri", "Esme"]
LAST = ["Nwosu", "Berg", "Raman", "Silva", "Zhang", "Novak", "O'Doherty",
        "Haddad", "Kaur", "Petrov", "Ellis", "Tanaka", "Mbeki", "Fischer",
        "Lindgren", "Costa", "Ahmed", "Rossi", "Dubois", "Larsen"]


def gen_recruiting():
    reqs = []
    for req_id, role, dept, hm, target in REQS:
        opened = AS_OF - timedelta(days=int(rng.uniform(25, 190)))
        reqs.append([req_id, role, dept, hm, d(opened), target, "open"])
    write(out("03-recruiting-funnel-ops", "requisitions.csv"),
          ["req_id", "role", "department", "hiring_manager", "opened_date",
           "target_days_to_hire", "status"], reqs)

    # Stage-to-stage pass rates; referrals convert far better than job boards,
    # which is the source-mix finding the report is meant to surface.
    pass_rate = {"Applied": 0.46, "Recruiter Screen": 0.58,
                 "HM Screen": 0.56, "Onsite": 0.52, "Offer": 0.85}
    src_mult = {"Referral": 1.35, "Inbound Application": 0.9, "Agency": 1.1,
                "LinkedIn Outbound": 1.0, "Job Board": 0.66, "Career Fair": 0.75}
    dwell = {"Applied": 4, "Recruiter Screen": 6, "HM Screen": 8,
             "Onsite": 11, "Offer": 7}
    # Chance a candidate is simply sitting in this stage waiting on someone.
    # Highest where a hiring manager has to act -- which is the whole point.
    stall_rate = {"Applied": 0.10, "Recruiter Screen": 0.14, "HM Screen": 0.26,
                  "Onsite": 0.24, "Offer": 0.12}

    rows = []
    cid = 0
    for req_id, role, dept, hm, target in REQS:
        for _ in range(int(rng.uniform(26, 46))):
            cid += 1
            source = rng.choices(ATS_SOURCES, weights=[14, 12, 30, 22, 16, 6])[0]
            applied = AS_OF - timedelta(days=int(rng.uniform(6, 210)))
            entered = applied              # when they entered their current stage
            cursor = applied
            stage_i = 0
            status = "active"
            hired_date = ""
            for s in ATS_STAGES[:-1]:
                if rng.random() < stall_rate[s]:
                    # Still waiting in this stage. Most waits are days, not
                    # months -- but a long tail of forgotten candidates is
                    # exactly what the nudge command exists to catch.
                    wait = int(rng.uniform(26, 62)) if rng.random() < 0.22 \
                        else max(0, int(rng.gauss(8, 7)))
                    entered = max(cursor, AS_OF - timedelta(days=wait))
                    break
                cursor += timedelta(days=max(1, int(rng.gauss(dwell[s], dwell[s] * 0.6))))
                if cursor > AS_OF:
                    cursor = AS_OF
                    break
                if rng.random() < min(0.95, pass_rate[s] * src_mult[source]):
                    stage_i += 1
                    entered = cursor
                else:
                    status = "rejected"
                    break
            stage = ATS_STAGES[min(stage_i, 5)]
            if stage == "Hired" and status == "active":
                status = "hired"
                hired_date = d(entered)
            if status == "active" and rng.random() < 0.05:
                status = "withdrawn"

            if status == "active":
                cursor = max(cursor, entered)
                # Some active candidates are moving, some have gone quiet.
                gap = int(rng.uniform(0, max(1, (AS_OF - entered).days)))
                last = AS_OF - timedelta(days=gap)
                if last < entered:
                    last = entered
            else:
                last = cursor

            rows.append([
                "C-%05d" % (30000 + cid),
                "%s %s" % (rng.choice(FIRST), rng.choice(LAST)),
                req_id, role, dept, hm, source, stage, status,
                d(applied), d(entered), d(min(last, AS_OF)), hired_date,
            ])
    write(out("03-recruiting-funnel-ops", "lever_candidates.csv"),
          ["candidate_id", "candidate_name", "req_id", "role", "department",
           "hiring_manager", "source", "current_stage", "status", "applied_date",
           "stage_entered_date", "last_activity_date", "hired_date"], rows)


# --------------------------------------------------------------------------
# 02b -- ARR movement events (the raw material for the monthly revenue pack)
# --------------------------------------------------------------------------
CUSTOMER_BOOK = []          # shared with the AR dataset below


def month_add(anchor, n):
    m = anchor.month - 1 + n
    return date(anchor.year + m // 12, m % 12 + 1, 1)


def gen_arr():
    """24 months of ARR movement, plus an opening balance month.

    Shaped like a Series A book: steady new logos, healthy expansion in
    Mid-Market/Enterprise, and a churn pocket concentrated in SMB.
    """
    rows = []
    start = date(2024, 6, 1)                     # opening balance month
    book = {}                                    # customer_id -> [name, seg, ind, arr]

    def add_customer(cid, month, seed_arr=None):
        seg = rng.choices(SEGMENTS, weights=[46, 36, 18])[0]
        ind = rng.choices(INDUSTRIES, weights=[15, 13, 10] + [8.9] * 7)[0]
        base = {"SMB": 21000, "Mid-Market": 74000, "Enterprise": 240000}[seg]
        arr = seed_arr or int(base * rng.uniform(0.6, 1.7) / 1000) * 1000
        name = company_name()
        book[cid] = [name, seg, ind, arr]
        rows.append([d(month), cid, name, seg, ind, "new", arr])

    cid_n = 0
    for _ in range(52):                          # opening book
        cid_n += 1
        add_customer("CUST-%04d" % (2000 + cid_n), start)

    for m in range(1, 25):
        month = month_add(start, m)
        for _ in range(rng.randint(3, 8)):       # new logos
            cid_n += 1
            add_customer("CUST-%04d" % (2000 + cid_n), month)

        existing = [c for c in book if book[c][3] > 0]
        for cid in rng.sample(existing, min(len(existing), rng.randint(2, 7))):
            name, seg, ind, arr = book[cid]
            up = int(arr * rng.uniform(0.08, 0.35) / 500) * 500
            if up:
                book[cid][3] = arr + up
                rows.append([d(month), cid, name, seg, ind, "expansion", up])
        for cid in rng.sample(existing, min(len(existing), rng.randint(0, 3))):
            name, seg, ind, arr = book[cid]
            down = int(arr * rng.uniform(0.05, 0.22) / 500) * 500
            if down:
                book[cid][3] = arr - down
                rows.append([d(month), cid, name, seg, ind, "contraction", -down])

        # Churn skews SMB -- the pattern the segmentation project also picks up.
        pool = [c for c in existing if rng.random() < (0.6 if book[c][1] == "SMB" else 0.2)]
        for cid in rng.sample(pool, min(len(pool), rng.randint(0, 3))):
            name, seg, ind, arr = book[cid]
            rows.append([d(month), cid, name, seg, ind, "churn", -arr])
            book[cid][3] = 0

    for cid, (name, seg, ind, arr) in book.items():
        if arr > 0:
            CUSTOMER_BOOK.append((cid, name, seg, ind, arr))
    write(out("02-revenue-reporting-pack", "arr_events.csv"),
          ["month", "customer_id", "customer_name", "segment", "industry",
           "event_type", "delta_arr"], rows)


# --------------------------------------------------------------------------
# 04 -- Accounts receivable
# --------------------------------------------------------------------------
def gen_invoices():
    """Nine months of invoices with a deliberate collections problem in them:
    a cluster of Net-60 enterprise accounts and a few disputed invoices drag
    DSO well past terms. That is the 'before' state the dunning agent works on.
    """
    rows = []
    n = 0
    for cid, name, seg, ind, arr in CUSTOMER_BOOK:
        cadence = rng.choices(["monthly", "quarterly", "annual"],
                              weights=[46, 34, 20])[0]
        per = {"monthly": arr / 12.0, "quarterly": arr / 4.0, "annual": float(arr)}[cadence]
        step = {"monthly": 1, "quarterly": 3, "annual": 12}[cadence]
        terms = rng.choices([30, 45, 60], weights=[52, 26, 22])[0]
        owner = rng.choice(["B. Chen", "S. Adeyemi", "M. Reyes"])
        contact = "ap@%s.example" % name.split()[0].lower()

        for k in range(0, 9, step):
            issued = month_add(date(2025, 10, 1), k)
            if issued > AS_OF:
                break
            n += 1
            due = issued + timedelta(days=terms)
            amount = int(per / 10) * 10

            # Late-payment risk rises with terms, deal size and a bad-actor tail.
            p_late = 0.10 + (terms - 30) * 0.005 + (0.08 if seg == "Enterprise" else 0)
            if rng.random() < 0.05:
                p_late += 0.35                    # chronic late payers
            late = rng.random() < min(p_late, 0.85)

            # Disputes are raised on a small share of invoices and mostly get
            # resolved; only recent ones are still open on the ledger.
            disputed = (rng.random() < 0.03
                        and (AS_OF - issued).days < 95)
            # A small set of accounts simply do not pay without being chased.
            # These are what fills the 60+ buckets and justifies the escalation
            # ladder -- without them the aging report has nothing to find.
            # Delinquency thins out with age -- collections eventually recovers
            # most of it, so the 90+ bucket is a tail, not the biggest bucket.
            age = (AS_OF - due).days
            decay = 1.0 if age < 60 else (0.45 if age < 120 else 0.2)
            delinquent = rng.random() < 0.075 * decay

            if due <= AS_OF and not late and not disputed and not delinquent:
                paid_date = due - timedelta(days=int(rng.uniform(0, 12)))
                status, paid = "paid", amount
            elif due <= AS_OF:
                overdue_days = int(rng.gauss(21, 16))
                paid_on = due + timedelta(days=max(3, overdue_days))
                if paid_on <= AS_OF and not disputed and not delinquent:
                    paid_date, status, paid = paid_on, "paid", amount
                else:
                    paid_date, status = "", ("disputed" if disputed else "open")
                    # Part-payments are common on aged balances.
                    paid = int(amount * 0.4) if rng.random() < 0.15 else 0
            else:
                paid_date, status, paid = "", "open", 0
                if rng.random() < 0.35:           # some pay early
                    paid_date, status, paid = d(issued + timedelta(days=9)), "paid", amount

            last_reminder = ""
            if status in ("open", "disputed") and due < AS_OF and rng.random() < 0.45:
                last_reminder = d(due + timedelta(days=int(rng.uniform(2, 25))))

            rows.append(["INV-%05d" % (60000 + n), cid, name, seg,
                         d(issued), d(due), terms, amount, paid, status,
                         paid_date if isinstance(paid_date, str) else d(paid_date),
                         owner, contact, last_reminder])
    write(out("04-ar-collections-agent", "invoices.csv"),
          ["invoice_id", "customer_id", "customer_name", "segment",
           "issue_date", "due_date", "payment_terms_days", "amount",
           "amount_paid", "status", "paid_date", "ar_owner",
           "billing_contact", "last_reminder_sent"], rows)


if __name__ == "__main__":
    print("Reference date (AS_OF): %s   seed: %d\n" % (AS_OF, SEED))
    gen_pipeline()
    gen_icp()
    gen_arr()
    gen_recruiting()
    gen_invoices()
    print("\nAll datasets are synthetic. Re-running reproduces them exactly.")
