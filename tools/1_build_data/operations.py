#!/usr/bin/env python3
"""
operations.py — the non-financial data behind the questions that aren't about money.

Not every question a business asks is financial. These tables hold the operational and impact data for the sample
organisations, at daily (or single-event) grain, Oct 2024 to 2pm on 6 Oct 2026, ready for the same cloud database:

  SME trades (Sample Electrical & Air)
    fact_enquiry          every customer enquiry: when it came in, how, and when someone first called back.
                          Every call-out job in the ledger has the enquiry that booked it (same customer job id);
                          other enquiries were quotes or questions that didn't become a job.
    fact_shift_daily      each technician's day: ordinary and overtime hours, and why there was overtime.
                          Ordinary hours cover the hours charged to jobs that day (fact_timesheet_daily).

  Not-for-profit (Sample Community Services)
    fact_service_daily    each program, each day: people helped, and people the program couldn't reach (and why).
                          Scaled from the program's own grant spend that month, so cost per person ties to the ledger.
    fact_call             every call to the help line: when, answered or not, how long they waited, the outcome.
    dim_volunteer         the volunteers (codes only: no names), when they started.
    fact_volunteer_shift  every volunteer shift: who, which program, how many hours.

Seeded randomness: identical every run. Never touches the financial tables.
"""

import random
from datetime import date, datetime, timedelta

import data_status as ds
from ids import Running, scattered

AS_AT = ds.AS_AT                         # 2pm on Tuesday 6 October 2026
FIRST = date(2024, 10, 1)
TECHS = [f"T{n}" for n in range(1, 8)]   # 7 technicians (driver_month: Technicians)
ORDINARY = 7.6                           # hours per working day
TARGET_CALLBACK_MIN = 120                # first callback within 2 business hours
OPEN, CLOSE = 8.5, 17.0                  # help line staffed 8:30am to 5pm on working days
COST_PER_PERSON = {"Housing support": 310, "Youth outreach": 185, "Mental health first aid": 140, "Digital literacy": 95,
                   "Community meals": 22, "Emergency relief": 120}   # program spend per person helped (drives people helped from grant spend)
CURRENT = ["Housing support", "Youth outreach", "Mental health first aid", "Digital literacy", "Community meals"]   # programs running now
REACH_REASONS = ["Program at capacity", "Waitlist", "Outside the service area", "Not eligible", "Couldn't make contact"]


def V(n):
    return f"VARCHAR({n})"


def techs_in(mo):
    """Technicians employed in a month: the same headcount the ledger's wages use (history.py; 7 from January 2026)."""
    import history
    return history.trades_techs(mo)


def working(d):
    return d.weekday() < 5 and d not in ds.QLD_HOLIDAYS


def days():
    d, out = FIRST, []
    while d <= AS_AT.date():
        out.append(d)
        d += timedelta(days=1)
    return out


def key(d):
    return int(d.strftime("%Y%m%d"))


def trend(d):
    """0 at the start of the data, 1 at the as-at date: lets things drift over the two years."""
    return (d - FIRST).days / max(1, (AS_AT.date() - FIRST).days)


def business_minutes(start, end):
    """Minutes between two times that fall inside working hours (8:30 to 5pm, working days)."""
    if end <= start:
        return 0
    total, t = 0, start
    while t.date() <= end.date():
        if working(t.date()):
            o = datetime.combine(t.date(), datetime.min.time()) + timedelta(hours=OPEN)
            c = datetime.combine(t.date(), datetime.min.time()) + timedelta(hours=CLOSE)
            a, b = max(t, o), min(end, c)
            if b > a:
                total += (b - a).total_seconds() / 60
        t = datetime.combine(t.date() + timedelta(days=1), datetime.min.time())
    return round(total)


def build(res, history_jobs, timesheet_rows, grant_spend_rows, grant_rows):
    """res: the model; history_jobs: every trades job (model + history); timesheet_rows: fact_timesheet_daily rows;
    grant_spend_rows: fact_grant_spend_month rows [grant, month, spend, budget]; grant_rows: dim_grant rows. Returns {table: (description, columns, rows, ddl)}."""
    rnd = random.Random(20261006)
    T = {}

    def tbl(name, desc, cols, rows):
        T[name] = (desc, [c[0] for c in cols], rows, cols)

    asat = AS_AT.replace(tzinfo=None)

    # ------------------------------------------------------------------ trades: enquiries and callbacks
    enq = []
    enq_no = Running(20417, "enquiry")                  # the CRM's enquiry numbers
    callouts = sorted({(j["job"], j["invoice_date"]) for j in history_jobs if j["type"] == "Call-out"}, key=lambda x: (x[1], x[0]))
    n = 0

    def enquiry(received, kind, job=None):
        nonlocal n
        n += 1
        # callbacks get slower as the business gets busier (a gentle drift up), faster for urgent call-outs
        base = 35 + 70 * trend(received.date()) + (0 if kind == "Call-out" else 40)
        wait_bus = max(4, rnd.expovariate(1 / base))
        if rnd.random() < 0.06 + 0.06 * trend(received.date()):
            wait_bus += rnd.uniform(240, 900)       # the odd one that slips to the next day
        # walk forward through working hours to place the callback
        t, left = received, wait_bus
        while left > 0:
            if working(t.date()) and OPEN <= t.hour + t.minute / 60 < CLOSE:
                step = min(left, (CLOSE - (t.hour + t.minute / 60)) * 60)
                t += timedelta(minutes=step)
                left -= step
            else:
                nxt = t.date() + timedelta(days=0 if (t.hour + t.minute / 60) < OPEN and working(t.date()) else 1)
                while not working(nxt):
                    nxt += timedelta(days=1)
                t = datetime.combine(nxt, datetime.min.time()) + timedelta(hours=OPEN)
        responded = t if t <= asat else None
        mins = business_minutes(received, responded) if responded else None
        channel = rnd.choices(["Phone", "Web form", "Email"], [0.55, 0.3, 0.15])[0]
        enq.append([f"ENQ{enq_no.next()}", "trades", received.isoformat(timespec="minutes"), key(received.date()), channel, kind, job,
                    responded.isoformat(timespec="minutes") if responded else None, mins,
                    None if mins is None else int(mins <= TARGET_CALLBACK_MIN)])

    for job, inv in callouts:
        if inv > asat.date():
            continue
        d = inv - timedelta(days=rnd.choice([0, 0, 1, 1, 2]))
        while not working(d):
            d -= timedelta(days=1)
        d = max(d, FIRST)                         # the data starts 1 Oct 2024
        received = datetime.combine(d, datetime.min.time()) + timedelta(hours=rnd.uniform(7, 18.5))
        if received > asat:
            received = asat - timedelta(minutes=rnd.randint(20, 300))
        enquiry(received, "Call-out", job)
    for d in days():          # quotes and questions that didn't become a call-out
        for _ in range(rnd.choice([1, 2, 2, 3, 3, 4]) if working(d) else rnd.choice([0, 0, 1])):
            received = datetime.combine(d, datetime.min.time()) + timedelta(hours=rnd.uniform(6.5, 21))
            if received <= asat:
                enquiry(received, rnd.choices(["Quote", "Question", "Maintenance contract"], [0.55, 0.35, 0.10])[0])
    enq.sort(key=lambda r: r[2])
    tbl("fact_enquiry", "Trades: every customer enquiry, Oct 2024 to 2pm 6 Oct 2026: when it came in, the channel, what it was about, and when someone first called back. "
        "minutes_to_callback counts working minutes only (8:30am to 5pm, working days); within_target = called back within 2 working hours. Every call-out job has the enquiry that booked it (job_id). "
        "responded_at is empty where no-one has called back yet.",
        [("enquiry_id", V(8) + " PRIMARY KEY"), ("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("received_at", "DATETIME"), ("date_key", "INT REFERENCES dim_date(date_key)"),
         ("channel", V(10)), ("enquiry_type", V(24)), ("job_id", V(12)), ("responded_at", "DATETIME"), ("minutes_to_callback", "INT"), ("within_target", "INT")], enq)

    # ------------------------------------------------------------------ trades: shifts and overtime
    job_hours = {}
    for r in timesheet_rows:
        if r[1] == "trades":
            job_hours[r[0]] = job_hours.get(r[0], 0) + r[4]
    shifts = []
    for d in days():
        if d == asat.date():
            break                                 # today's shifts aren't over
        dk = key(d)
        crew = TECHS[:techs_in(d.strftime("%Y-%m"))]                          # the technicians employed that month
        on = [t for t in crew if working(d) and rnd.random() > 0.04]           # leave and sick days
        if not on and job_hours.get(dk, 0) == 0:
            continue
        busy = job_hours.get(dk, 0)
        for t in on:
            # overtime: more of it lately (the creep), mostly after-hours call-outs and installs running over
            p = 0.06 + 0.16 * trend(d) + (0.06 if busy > 5.8 * len(on) else 0)
            ot, why = 0.0, None
            if rnd.random() < p:
                why = rnd.choices(["After-hours call-out", "Installation ran over", "Short-staffed", "Paperwork and quotes"],
                                  [0.42, 0.33, 0.15, 0.10])[0]
                ot = round(rnd.choice([0.5, 1, 1.5, 2, 2, 2.5, 3]) * 2) / 2
            shifts.append([dk, "trades", t, ORDINARY, ot, why])
        if not working(d) and rnd.random() < 0.12 + 0.18 * trend(d):           # a weekend emergency
            shifts.append([dk, "trades", rnd.choice(TECHS[:techs_in(d.strftime("%Y-%m"))]), 0, rnd.choice([2, 2.5, 3, 4]), "After-hours call-out"])
    tbl("fact_shift_daily", "Trades: each technician's paid hours by day, Oct 2024 to 5 Oct 2026: ordinary hours (7.6 a working day) and overtime, with the main reason for the overtime. "
        "Technicians are codes (T1 to T7). Ordinary hours cover the hours charged to jobs (fact_timesheet_daily); the rest is travel, quoting and time not charged.",
        [("date_key", "INT REFERENCES dim_date(date_key)"), ("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("technician", V(4)),
         ("ordinary_hours", "DECIMAL(5,2)"), ("overtime_hours", "DECIMAL(5,2)"), ("overtime_reason", V(30))], shifts)
    charged = sum(v for k, v in job_hours.items() if k < key(asat.date()))
    paid = sum(r[3] for r in shifts)
    if charged > paid:
        raise SystemExit(f"operations: hours charged to jobs ({charged}) exceed ordinary hours paid ({paid})")

    # ------------------------------------------------------------------ not-for-profit: people helped and not reached
    from collections import defaultdict
    spend = defaultdict(float)                # (program, month) -> grant spend that month
    grant_prog = {g[0]: g[2].split(" (")[0] for g in grant_rows}   # dim_grant: [grant_id, org, program, ...]; "Community meals (2025-26)" is Community meals
    for g_, mo, amt, _budget in grant_spend_rows:
        prog = grant_prog.get(g_)
        if prog in COST_PER_PERSON:
            spend[(prog, mo)] += amt
    service = []
    for (prog, mo), amt in sorted(spend.items()):
        helped_month = round(amt / COST_PER_PERSON[prog])
        ds_ = [d for d in days() if d.strftime("%Y-%m") == mo and (working(d) or prog == "Community meals") and d < asat.date()]
        if not ds_ or helped_month <= 0:
            continue
        weights = [rnd.uniform(0.7, 1.3) for _ in ds_]
        tot = sum(weights)
        parts = [int(helped_month * w / tot) for w in weights]
        for i in range(helped_month - sum(parts)):
            parts[i % len(parts)] += 1
        for d, h in zip(ds_, parts):
            # demand outruns capacity more as the year goes on (more turned away in winter and lately)
            p_miss = 0.06 + 0.10 * trend(d) + (0.05 if d.month in (6, 7, 8) else 0)
            missed = sum(1 for _ in range(h) if rnd.random() < p_miss)
            reason = rnd.choices(REACH_REASONS, [0.4, 0.25, 0.12, 0.1, 0.13])[0] if missed else None
            service.append([key(d), "nfp", prog, h, missed, reason])
    tbl("fact_service_daily", "Not-for-profit: each program, each day, Oct 2024 to 5 Oct 2026: people helped, and people who came to the program but couldn't be helped, "
        "with the main reason. People helped are scaled from the program's grant spend that month (fact_grant_spend_month), so cost per person helped ties to the ledger.",
        [("date_key", "INT REFERENCES dim_date(date_key)"), ("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("program", V(40)),
         ("people_helped", "INT"), ("people_not_reached", "INT"), ("main_reason", V(40))], service)

    # ------------------------------------------------------------------ not-for-profit: calls for help
    calls, cn = [], 0
    call_no = Running(1048311, "call")                  # the phone system's call references
    for d in days():
        wk = working(d)
        base = (34 if d.weekday() == 0 else 26) if wk else 9
        base *= 1 + 0.25 * trend(d) + (0.15 if d.month in (6, 7, 8) else 0)
        for _ in range(max(0, round(rnd.gauss(base, base ** 0.5)))):
            # calls cluster mid-morning and early evening
            hour = rnd.choices(range(24), [1, 1, 1, 1, 1, 2, 4, 7, 10, 12, 12, 10, 9, 9, 9, 8, 9, 11, 10, 8, 6, 4, 3, 2])[0]
            at = datetime.combine(d, datetime.min.time()) + timedelta(hours=hour, minutes=rnd.randint(0, 59))
            if at > asat:
                continue
            cn += 1
            staffed = wk and OPEN <= hour + at.minute / 60 < CLOSE
            busy = rnd.random() < (0.10 + 0.12 * trend(d))         # all lines busy: more often lately
            answered = staffed and not busy
            wait = rnd.randint(8, 150) if answered else (rnd.randint(60, 420) if staffed else 0)
            outcome = (rnd.choices(["Helped on the call", "Booked into a program", "Referred elsewhere"], [0.45, 0.35, 0.2])[0] if answered
                       else "Hung up waiting" if staffed else "After hours: voicemail")
            calls.append([f"CL{call_no.next()}", "nfp", at.isoformat(timespec="minutes"), key(d), at.hour, int(answered), wait, outcome])
    tbl("fact_call", "Not-for-profit: every call to the help line, Oct 2024 to 2pm 6 Oct 2026: when it came in, whether it was answered, how long the caller waited (seconds), "
        "and what happened. The line is staffed 8:30am to 5pm on working days; outside those hours calls go to voicemail.",
        [("call_id", V(10) + " PRIMARY KEY"), ("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("received_at", "DATETIME"), ("date_key", "INT REFERENCES dim_date(date_key)"),
         ("hour_of_day", "INT"), ("answered", "INT"), ("wait_seconds", "INT"), ("outcome", V(30))], calls)

    # ------------------------------------------------------------------ not-for-profit: volunteers
    vols = []
    for i in range(1, 61):
        start = FIRST + timedelta(days=rnd.randint(-400, 650))
        vols.append([None, "nfp", start.isoformat(), rnd.choice(CURRENT + ["Volunteer coordinator"])])
    by_start = sorted(range(len(vols)), key=lambda i: vols[i][2])    # volunteer numbers are issued in the order people joined
    for i, no in zip(by_start, scattered(len(vols), 1084, "volunteer", (2, 19))):
        vols[i][0] = f"V{no}"
    tbl("dim_volunteer", "Not-for-profit: volunteers (codes only, no names), when they started and the program they mostly help.",
        [("volunteer_id", V(5) + " PRIMARY KEY"), ("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("started", "DATE"), ("main_program", V(40))], vols)
    shifts_v = []
    for d in days():
        if d >= asat.date():
            break
        active = [v for v in vols if date.fromisoformat(v[2]) <= d]
        k = round(len(active) * (0.16 if working(d) else 0.07) * (1.1 if d.weekday() in (2, 3) else 1))
        for v in rnd.sample(active, min(k, len(active))):
            prog = v[3] if rnd.random() < 0.8 else rnd.choice(CURRENT)
            shifts_v.append([key(d), "nfp", v[0], prog, rnd.choice([2, 3, 3, 3.5, 4, 4, 5])])
    tbl("fact_volunteer_shift", "Not-for-profit: every volunteer shift, Oct 2024 to 5 Oct 2026: who (volunteer code), which program, how many hours.",
        [("date_key", "INT REFERENCES dim_date(date_key)"), ("org_id", V(12) + " REFERENCES dim_org(org_id)"), ("volunteer_id", V(5) + " REFERENCES dim_volunteer(volunteer_id)"),
         ("program", V(40)), ("hours", "DECIMAL(4,1)")], shifts_v)
    return T
