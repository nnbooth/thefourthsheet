#!/usr/bin/env python3
"""
ids.py — identifiers that look like a real system's, not 1, 2, 3 ...

Real systems don't start the sample data at record number 1:
  scattered()  master records (customers, suppliers, contracts, volunteers, clients, staff): issued over years with
               other records in between, so the numbers rise with gaps. Pass them out in the order records were created.
  Running      transactions (calls, deliveries, goods receipts, enquiries, call-out jobs, appointments): one running
               sequence that started long before the data begins, with the odd number skipped (voided, cancelled or
               test records).
Everything is seeded, so the same build always gives the same numbers.
"""

import random


def scattered(n, start, seed, gap=(2, 40)):
    """n rising numbers from just above start, each a random gap from the last."""
    rng = random.Random(f"ids-{seed}")
    out, v = [], start
    for _ in range(n):
        v += rng.randint(*gap)
        out.append(v)
    return out


class Running:
    """A running number: next() is the last one plus one, now and then plus two (a voided or cancelled record)."""

    def __init__(self, start, seed, skip=0.03):
        self.v, self.skip, self.rng = start, skip, random.Random(f"run-{seed}")

    def next(self):
        self.v += 2 if self.rng.random() < self.skip else 1
        return self.v


# trades: maintenance contract numbers (in the order the contracts were signed) and call-out job numbers
CONTRACT_NOS = scattered(14, 1038, "contract", (4, 37))


def contract_no(i):
    return f"MC-{CONTRACT_NOS[i]}"


def callout_no(month, k):
    """The k-th call-out (from 0) in a month: job numbers run through the months (about 90 a month at most), with gaps."""
    y, m = map(int, month.split("-"))
    base = 47108 + ((y - 2024) * 12 + m - 10) * 92
    return f"CO-{base + k + (k * 3) // 17}"
