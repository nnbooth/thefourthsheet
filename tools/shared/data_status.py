#!/usr/bin/env python3
"""
data_status.py — how final each period's numbers are, as at the time the
reports are run. Every page, export and database load uses this, so a report
always says what it can and can't be relied on for.

  Locked       the month has been closed (2nd working day of the next month).
               The numbers won't change.
  Provisional  the month (or day) is over but not yet locked: late invoices,
               proofs of delivery and adjustments can still change it.
  Incomplete   still happening: today, or the current month to date.

Change AS_AT to see what a report run on another day would say (e.g.
datetime(2026, 9, 1, 9, 0) shows August as provisional and September as
incomplete).
"""

from datetime import date, datetime, timedelta

# Brisbane public holidays, Oct 2024 to 2027 (one list for every tool: working days, dim_date, data status, banking days).
# From the holidays package (Queensland), plus the Ekka (Royal Queensland Show) People's Day, a Brisbane-only holiday.
import holidays as _holidays

_NAMES = {"Labor Day": "Labour Day", "ANZAC Day": "Anzac Day", "The Royal Queensland Show": "Royal Queensland Show (Ekka, Brisbane)"}
QLD_HOLIDAYS = {d: _NAMES.get(n, n) for d, n in sorted(_holidays.AU(subdiv="QLD", years=range(2024, 2028)).items())}
for _d in (date(2024, 8, 14), date(2025, 8, 13), date(2026, 8, 12), date(2027, 8, 11)):   # Ekka Wednesdays, in case the package drops them
    QLD_HOLIDAYS.setdefault(_d, "Royal Queensland Show (Ekka, Brisbane)")


def strf(d, pattern):
    """strftime that works on Windows too: %-d, %-m, %-I and %-H (no leading zero) are Mac/Linux-only codes."""
    for code, value in (("%-d", lambda: str(d.day)), ("%-m", lambda: str(d.month)),
                        ("%-I", lambda: str(int(d.strftime("%I")))), ("%-H", lambda: str(d.hour))):
        if code in pattern:
            pattern = pattern.replace(code, value())
    return d.strftime(pattern)


def working(d):
    return d.weekday() < 5 and d not in QLD_HOLIDAYS

AS_AT = datetime(2026, 10, 6, 14, 0)     # the reports are "run" at 2pm on Tuesday 6 October 2026
LOCK_WORKING_DAY = 2                      # months are locked on the 2nd working day of the next month


def month_end(month):
    y, m = map(int, month.split("-"))
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def lock_date(month):
    d, n = month_end(month), 0
    while n < LOCK_WORKING_DAY:
        d += timedelta(days=1)
        if working(d):
            n += 1
    return d


def month_status(month, as_at=AS_AT):
    """('Locked' | 'Provisional' | 'Incomplete', plain-English note)."""
    label = date.fromisoformat(month + "-01").strftime("%B %Y")
    if as_at.date() >= lock_date(month):
        return "Locked", f"{label} is locked (closed {strf(lock_date(month), '%-d %b %Y')}). These numbers won't change."
    if as_at.date() > month_end(month):
        return "Provisional", (f"{label} is over but not locked yet (due {strf(lock_date(month), '%-d %b')}). "
                               "Late invoices and adjustments can still change it.")
    return "Incomplete", f"{label} is still in progress: figures to {strf(as_at, '%-d %b')} only."


def day_status(d, as_at=AS_AT):
    if d > as_at.date():
        return "Future"
    if d == as_at.date():
        return "Incomplete"
    return "Locked" if as_at.date() >= lock_date(d.strftime("%Y-%m")) else "Provisional"


def as_at_text(as_at=AS_AT):
    return strf(as_at, "%-I%p, %a %-d %b %Y").replace("AM", "am").replace("PM", "pm")


def footer_text(months, as_at=AS_AT):
    """One line for page footers: 'Sep 2026 locked · Oct 2026 incomplete · as at 2pm, Tue 6 Oct 2026'."""
    bits = []
    for m in months:
        st, _ = month_status(m, as_at)
        bits.append(f"{date.fromisoformat(m + '-01').strftime('%b %Y')} {st.lower()}")
    return " · ".join(bits) + f" · as at {as_at_text(as_at)}"
