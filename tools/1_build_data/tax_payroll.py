#!/usr/bin/env python3
"""
tax_payroll.py — GST, BAS, pay runs and banking days, in one place for the model (financial_model.py),
the history and October to date (history.py), the daily cash (warehouse.py) and the 13-week cash forecast
(fourthsheet/catalogue.py). Australian rules, as at October 2026.

GST          10%, accruals basis: GST on a sale is owed when it's invoiced, a credit on a purchase is claimed when
             it's billed. All three samples are registered (the charity is over the $150,000 not-for-profit
             threshold). Wages and super are GST-free; bank interest is input-taxed (no GST either way).
BAS          quarterly, self-lodged: GST on sales − GST credits + PAYG withheld + PAYG instalment, due on the 28th of
             the month after the quarter (the October to December quarter is due 28 February).
Pay runs     fortnightly, on Thursdays. Each pay run is a 26th of the year's gross wages (wages excluding super,
             payroll tax and leave): employees get net pay on the day, PAYG withheld goes to the ATO with the BAS.
Super        12% of gross wages (superannuation guarantee from 1 July 2025). Payday Super (from 1 July 2026): paid
             with each pay run, so it reaches the fund within 7 business days.
Payroll tax  Queensland: 4.75% of wages above $1.3 million a year. Both SMEs are under the threshold; the charity is
             exempt (wages for its charitable work). So none in any sample.
Banking days no money moves on a Saturday, Sunday or Queensland public holiday: it moves on the next banking day.
"""

from datetime import date, timedelta

import data_status as ds

GST_RATE = 0.10
SUPER_RATE = 0.12
PAYROLL_TAX = {"threshold": 1_300_000, "rate": 0.0475}
PAYG_RATE = {"trades": 0.20, "services": 0.24, "nfp": 0.17}    # average PAYG withheld from gross pay (assumption)
FIRST_PAY_DAY = date(2026, 7, 9)                               # fortnightly Thursdays: 9 Jul, 23 Jul, 6 Aug, 20 Aug ...
NFP_GST = {"Donations": False, "Fundraising events": True, "Program fees": True, "Interest": False, "grants": True}


def half_up(x):
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def gst_on(x):
    """GST on a GST-exclusive amount, to the dollar."""
    return half_up(x * GST_RATE)


def with_gst(x):
    return x + gst_on(x)


def banking_day(d):
    return ds.working(d)


def next_banking_day(d):
    """The day money actually moves: the same day, or the next one that isn't a weekend or Queensland public holiday."""
    while not ds.working(d):
        d += timedelta(days=1)
    return d


def pay_days(start, end):
    """Every fortnightly pay day from start to end (inclusive). Pay days are Thursdays; one on a holiday moves to the next banking day."""
    d, out = FIRST_PAY_DAY, []
    while d > start:
        d -= timedelta(days=14)
    while d <= end:
        if d >= start:
            out.append(next_banking_day(d))
        d += timedelta(days=14)
    return out


def pay_days_in(mo):
    y, m = map(int, mo.split("-"))
    return pay_days(date(y, m, 1), ds.month_end(mo))


def working_days(mo):
    y, m = map(int, mo.split("-"))
    d, n = date(y, m, 1), 0
    while d.month == m:
        n += ds.working(d)
        d += timedelta(days=1)
    return n


def fy_months(fy_start="2026-07"):
    y, m = map(int, fy_start.split("-"))
    return [f"{y + (m + k - 1) // 12}-{(m + k - 1) % 12 + 1:02d}" for k in range(12)]


def gross_from_cost(wage_cost, leave):
    """Gross wages from a month's wage cost incl. on-costs: cost = gross + super (12%) + leave accrued. No payroll tax (see above)."""
    return half_up((wage_cost - leave) / (1 + SUPER_RATE))


def pay_run(annual_gross, org):
    """One fortnightly pay run: gross = a 26th of the year's gross wages; PAYG withheld from it; super on top."""
    gross = half_up(annual_gross / 26)
    payg = half_up(gross * PAYG_RATE[org])
    sup = half_up(gross * SUPER_RATE)
    return {"gross": gross, "payg": payg, "net": gross - payg, "super": sup, "cash": gross - payg + sup, "annual_gross": annual_gross}


def quarter_of(mo):
    y, m = map(int, mo.split("-"))
    q_end = ((m - 1) // 3 + 1) * 3
    return [f"{y}-{k:02d}" for k in range(q_end - 2, q_end + 1)]


def bas_due(mo_in_quarter):
    """When the BAS for the quarter holding this month is due (quarterly, self-lodged): the 28th of the month after
    the quarter, except the October to December quarter, due 28 February."""
    q = quarter_of(mo_in_quarter)
    y, m = map(int, q[-1].split("-"))
    if m == 12:
        return date(y + 1, 2, 28)
    return date(y + (m == 12), m % 12 + 1, 28)


def bas_payments_between(start, end):
    """[(quarter months, due date as paid: next banking day)] for every BAS paid in (start, end]."""
    out, seen = [], set()
    d = date(start.year, start.month, 1) - timedelta(days=200)
    while d <= end:
        mo = d.strftime("%Y-%m")
        q = tuple(quarter_of(mo))
        if q not in seen:
            seen.add(q)
            paid = next_banking_day(bas_due(mo))
            if start < paid <= end:
                out.append((list(q), paid))
        d += timedelta(days=28)
    return out


def payroll_tax_check(org, annual_gross):
    """Queensland payroll tax is on wages + super above the threshold. Returns the tax a year (0 under the threshold or for the charity)."""
    if org == "nfp":
        return 0                                   # registered charity: wages for its charitable work are exempt (assumption)
    taxable = annual_gross * (1 + SUPER_RATE)
    return 0 if taxable <= PAYROLL_TAX["threshold"] else half_up((taxable - PAYROLL_TAX["threshold"]) * PAYROLL_TAX["rate"])
