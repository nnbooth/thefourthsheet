"""
period.py — the reporting period a report is run for, and every date that hangs off it.

A report is always run for one month (the period). From it come: the month before, the same month last
year, the financial year to date (July to the period) and the same months a year earlier, the 24 months
on the charts, and each month's data status (Locked / Provisional / Incomplete) as at the time of the run.
"""

from datetime import date

import data_status as ds


def add_months(mo, n):
    y, m = map(int, mo.split("-"))
    k = y * 12 + m - 1 + n
    return f"{k // 12}-{k % 12 + 1:02d}"


def mdate(mo):
    return date.fromisoformat(mo + "-01")


def mlabel(mo):
    return mdate(mo).strftime("%b %y")


CURRENT = ds.AS_AT.strftime("%Y-%m")     # the month the report is run in (still in progress)


class Period:
    def __init__(self, mo, months):
        """mo: 'YYYY-MM'. months: every month the data has (sorted)."""
        if mo not in months:
            raise SystemExit(f"No data for {mo}. The data runs from {months[0]} to {months[-1]}.")
        self.mo, self.months = mo, months
        d = mdate(mo)
        self.prev, self.ly = add_months(mo, -1), add_months(mo, -12)
        self.status, self.note = ds.month_status(mo)
        self.incomplete = self.status == "Incomplete"
        self.month = d.strftime("%B")                                       # September
        self.when = self.month + (" so far" if self.incomplete else "")    # September / October so far
        self.label = d.strftime("%B %Y") + (" to date" if self.incomplete else "")
        self.short = d.strftime("%b %Y")
        self.prev_month = mdate(self.prev).strftime("%B")
        # the latest complete month at or before the period (bridges and rates can't use a part month)
        self.full = self.prev if self.incomplete else mo
        self.full_month = mdate(self.full).strftime("%B")
        self.full_label = mdate(self.full).strftime("%B %Y")
        fy_start = f"{d.year if d.month >= 7 else d.year - 1}-07"
        self.fy = f"FY{d.year + 1 if d.month >= 7 else d.year}"
        self.fytd = [m for m in months if fy_start <= m <= mo]
        self.pfytd = [add_months(m, -12) for m in self.fytd]
        self.pfytd_ok = all(m in months for m in self.pfytd) and len(self.fytd) == (int(mo[5:]) - 7) % 12 + 1
        self.ly_ok = self.ly in months
        self.window = [m for m in months if m <= mo][-24:]
        a = mdate(self.fytd[0])
        self.fytd_l = d.strftime("%b %Y") if len(self.fytd) == 1 else f"{a.strftime('%b')} to {d.strftime('%b %Y')}"
        self.pfytd_l = mdate(self.ly).strftime("%b %Y") if len(self.fytd) == 1 else f"{a.strftime('%b')} to {mdate(self.ly).strftime('%b %Y')}"
        self.ytd_name = f"Year to date ({self.fytd_l})"
        self.status_months = [self.prev, mo] + ([CURRENT] if CURRENT > mo else [])
        self.no_ly = f"Not available: the data starts {mdate(months[0]).strftime('%B %Y')}."
        self.part_note = (f"{self.month} is still in progress (data to {ds.strf(ds.AS_AT, '%-d %B')}), so it is a part month against full months."
                          if self.incomplete else "")

    def end_date(self):
        """The last day the period's numbers cover."""
        e = ds.month_end(self.mo)
        return min(e, ds.AS_AT.date()) if self.incomplete else e

    def status_of(self, mo):
        return ds.month_status(mo)[0]

    def option(self):
        return {"value": self.mo, "label": self.label, "status": self.status}
