"""G-0 simulator: multi-bank retail population + injected scam rings + hard negatives.

Implements docs/lab/G0_SCENARIO_SPEC.md (parameter ranges frozen in section 1,
detector-side answers in section 6). Written detector-blind: nothing here knows the
detector's features, windows or thresholds. Every number measured on this data is
learnability on synthetic data, not production accuracy.

    PYTHONPATH=src .venv/bin/python -m tp.sim --seed 20261003 --mimicry 0 --out data/processed/g0/m0

Only stdlib + numpy + pandas + pyarrow. One seed -> identical output bytes.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

GENERATOR_VERSION = "g0-sim-1.0.0"

DAY0 = 1735664400  # 2025-01-01 00:00 ICT in epoch seconds (spec 6.1)
DAY = 86_400
HOUR = 3_600
N_DAYS = 450
MONTHS = N_DAYS / 30
SPLITS = {"warmup": (0, 90), "train": (90, 270), "val": (270, 330), "test": (330, 450)}  # [start, end) days
SCAM_SPLITS = ("train", "val", "test")

BANKS = ["B1", "B2", "B3", "B4", "B5", "B6"]
BANK_SHARE = np.array([0.35, 0.20, 0.18, 0.10, 0.09, 0.08])

KINDS = ["PERSON", "MERCHANT", "BILLER", "EMPLOYER", "UNKNOWN"]
PERSON, MERCHANT, BILLER, EMPLOYER, UNKNOWN = range(5)
TXN_TYPES = ["P2P", "MERCHANT", "BILL", "PAYROLL"]
P2P, T_MERCHANT, T_BILL, T_PAYROLL = range(4)
RAILS = ["PROMPTPAY", "ACCOUNT", "PROMPTPAY_QR", "BILL", "PAYROLL"]
R_PROMPTPAY, R_ACCOUNT, R_QR, R_BILL, R_PAYROLL = range(5)
CHANNELS = ["MOBILE", "INTERNET", "OTHER"]
C_OTHER = 2
STATUSES = ["SETTLED", "FAILED"]
EVENT_ROLES = ["SIGNUP_FEE", "STEP", "UNLOCK_FEE", "SEED_INFLOW", "GROOMING_OUT", "GROOMING_IN"]
VICTIM_OUT_ROLES = ("SIGNUP_FEE", "STEP", "UNLOCK_FEE", "GROOMING_OUT")

# Hour-of-day weights in ICT: peaks at 12:00 and 19:00, 00-06 about 4% (spec 1.1).
HOUR_W = np.array([1.6, .9, .5, .3, .4, .8, 1.5, 3, 4.5, 5, 5.5, 7, 9, 7, 5, 5, 5.5, 6.5, 8.5, 10, 8.5, 6.5, 4, 2.5])
HOUR_P = HOUR_W / HOUR_W.sum()

RING_COUNTS = {"A": {"train": 160, "val": 55, "test": 80}, "D": {"train": 80, "val": 28, "test": 40}}
MIN_EPISODES_RINGS = {"train": (600, 120), "val": (200, 40), "test": (200, 40)}  # brief; scale=1 only
R_EMPIRICAL = {  # declared destination-account counts in AOC (spec 1.2 / 1.3)
    "A": ([1, 2, 3, 4, 5, 6], [2, 2, 2, 3, 3, 2]),
    "D": ([1, 2, 3, 4, 5, 6, 7], [3, 2, 5, 8, 9, 4, 1]),
}
HN_RATES = {  # per account per 30 days (spec 1.5)
    "SHOP_PARTIAL_REFUND": 0.015, "FRIEND_LOAN_REPAID": 0.04, "BILL_SPLIT": 0.06,
    "FAMILY": 0.03, "DEPOSIT_RETURNED": 0.015, "LEGIT_ESCALATION": 0.015,
}
HN_GROUPS = list(HN_RATES)

# event_id streams: disjoint ranges so (stream, counter) is unique for every event
S_NEW, S_REGULAR, S_RENT, S_INCOME, S_SALARY, S_MERCHANT, S_BILL = range(1, 8)
S_HN, S_COVER, S_EPISODE = 10_000, 20_000, 1_000_000


# ---------------------------------------------------------------- utilities

def mix64(x) -> np.ndarray:
    """SplitMix64 finalizer. A bijection on uint64: distinct inputs give distinct ids."""
    z = np.atleast_1d(np.asarray(x, dtype=np.uint64)) + np.uint64(0x9E3779B97F4A7C15)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return z ^ (z >> np.uint64(31))


def key64(seed: int, name: str) -> np.uint64:
    """Secret per-purpose key derived from the seed, so ids are opaque without it."""
    return np.uint64(int.from_bytes(hashlib.sha256(f"{seed}:{name}".encode()).digest()[:8], "little"))


def opaque_ids(key: np.uint64, stream, counter) -> np.ndarray:
    """uint64 ids from (stream, counter); unique because mix64 is a bijection."""
    s = np.asarray(stream, dtype=np.uint64) << np.uint64(32)
    return mix64(key ^ (s | np.asarray(counter, dtype=np.uint64)))


_HEX = np.frombuffer(b"0123456789abcdef", dtype=np.uint8)


def hex16(x: np.ndarray) -> pd.Series:
    """uint64 -> 16-char lowercase hex strings, vectorised."""
    b = np.atleast_1d(x).astype(">u8").view(np.uint8).reshape(-1, 8)
    out = np.empty((len(b), 16), dtype=np.uint8)
    out[:, 0::2] = _HEX[b >> 4]
    out[:, 1::2] = _HEX[b & 15]
    return pd.Series(pa.array(out.view("S16").ravel()).cast(pa.string()).to_pandas(), dtype="str")


def enum_col(codes: np.ndarray, names: list[str]) -> pd.Series:
    return pd.Series(pd.Categorical.from_codes(np.asarray(codes, dtype=np.int64), categories=names)).astype("str")


def lognormal(rng, median, sigma, size=None):
    """Log-normal parameterised as in the spec: LN(median, sigma on log scale)."""
    return median * np.exp(sigma * rng.standard_normal(size))


def tlognormal(rng, median, sigma, lo, hi, size):
    """Truncated log-normal [lo, hi] by redrawing out-of-range values."""
    x = lognormal(rng, median, sigma, size)
    bad = (x < lo) | (x > hi)
    while bad.any():
        x[bad] = lognormal(rng, median, sigma, int(bad.sum()))
        bad = (x < lo) | (x > hi)
    return x


def tln(rng, median, sigma, lo, hi) -> float:
    """Scalar truncated log-normal."""
    while True:
        x = median * math.exp(sigma * rng.standard_normal())
        if lo <= x <= hi:
            return x


def tods(rng, n) -> np.ndarray:
    """Seconds after local midnight drawn from the diurnal profile."""
    return rng.choice(24, size=n, p=HOUR_P) * HOUR + rng.integers(0, HOUR, size=n)


def round_amounts(x, u, v) -> np.ndarray:
    """Spec 1.1 rounding, identical for every P2P class (normal, scam, HN).

    >= 1,000: whole thousands p .5, whole hundreds p .3, else fine. Fine = whole baht or satang (.5/.5).
    """
    x = np.asarray(x, dtype=float)
    big = x >= 1000
    fine = np.where(np.asarray(v) < 0.5, np.round(x), np.round(x, 2))
    out = np.where(big & (np.asarray(u) < 0.5), np.round(x / 1000) * 1000,
                   np.where(big & (np.asarray(u) < 0.8), np.round(x / 100) * 100, fine))
    return np.where(out > 0, out, np.maximum(np.round(x, 2), 0.01))


def round_p2p(rng, x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return round_amounts(x, rng.random(x.shape), rng.random(x.shape))


def money(x) -> np.ndarray:
    """Non-P2P amounts: 2 decimals, strictly positive."""
    return np.maximum(np.round(np.asarray(x, dtype=float), 2), 0.01)


def channels(rng, n) -> np.ndarray:
    return rng.choice(3, size=n, p=[0.95, 0.04, 0.01])


def p2p_rails(rng, n) -> np.ndarray:
    return np.where(rng.random(n) < 0.7, R_PROMPTPAY, R_ACCOUNT)


def month_starts() -> list[int]:
    """Day index of the 1st of every calendar month touching the horizon."""
    out, d = [], dt.date(2025, 1, 1)
    while (d - dt.date(2025, 1, 1)).days < N_DAYS:
        out.append((d - dt.date(2025, 1, 1)).days)
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def days_in_month(start_day: int) -> int:
    d = dt.date(2025, 1, 1) + dt.timedelta(days=int(start_day))
    nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - d).days


def chain(gaps, tod_list) -> list[float]:
    """Relative times (seconds after the anchor day's midnight) from successive gaps.

    The first event and every event after a gap >= 1 day land on a diurnal time of day,
    so multi-day sequences keep the population's daily rhythm; short gaps stay exact.
    """
    out, cur = [], float(tod_list[0])
    for i, g in enumerate(gaps):
        if i:
            nxt = cur + g
            if g >= DAY:
                nxt = (nxt // DAY) * DAY + tod_list[i]
                if nxt <= cur:
                    nxt += DAY
            cur = nxt
        out.append(cur)
    return out


class Events:
    """Column buffers for events built outside the vectorised population block."""

    COLS = ("ts", "payer", "payee", "amount", "txn", "rail", "channel", "status", "stream", "counter")

    def __init__(self):
        self.rows = {c: [] for c in self.COLS}

    def add(self, ts, payer, payee, amount, txn, rail, channel, stream, counter, status=0):
        for c, v in zip(self.COLS, (int(ts), int(payer), int(payee), float(amount), txn, rail, channel,
                                    status, stream, counter)):
            self.rows[c].append(v)

    def arrays(self) -> dict[str, np.ndarray]:
        dtypes = {"ts": np.int64, "payer": np.int64, "payee": np.int64, "amount": float, "txn": np.int8,
                  "rail": np.int8, "channel": np.int8, "status": np.int8, "stream": np.int64, "counter": np.int64}
        return {c: np.asarray(self.rows[c], dtype=dtypes[c]) for c in self.COLS}


def concat(parts: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    return {c: np.concatenate([p[c] for p in parts]) for c in Events.COLS}


# ---------------------------------------------------------------- population (spec 1.1, 2.1)

@dataclass
class Population:
    kind: np.ndarray          # per entity: PERSON / MERCHANT / BILLER / EMPLOYER (ring accounts appended later)
    bank: np.ndarray          # per entity: 0..5
    n_person: int
    by_bank: list             # person indices per bank
    activity: np.ndarray      # a_i
    lam: np.ndarray           # P2P out per 30 days = 8 a_i
    nu: np.ndarray            # first transfers to new counterparts per 30 days (part of lam)
    slot_start: np.ndarray    # regular counterparts: family slots first, then friends
    n_family: np.ndarray
    n_slots: np.ndarray
    slot_cp: np.ndarray
    slot_base: np.ndarray
    landlord: np.ndarray      # -1 = pays no rent
    rent: np.ndarray
    rent_dom: np.ndarray
    salaried: np.ndarray
    salary: np.ndarray
    employer: np.ndarray
    pay_dom: np.ndarray       # per entity, used for employers
    income_rate: np.ndarray   # irregular inflows per 30 days for non-salaried persons
    merchants: np.ndarray
    merchant_p: np.ndarray
    billers: np.ndarray
    bill_person: np.ndarray
    bill_biller: np.ndarray
    bill_base: np.ndarray
    bill_dom: np.ndarray
    sellers: np.ndarray       # persons who sell online (HN1)
    monthly_income: np.ndarray = field(default=None)  # mean settled inflow per 30 days in warm-up


def pick_persons(rng, by_bank, near_bank, exclude=None) -> np.ndarray:
    """Random persons: same bank as near_bank with p = share + .10, else another bank by share."""
    near_bank = np.atleast_1d(np.asarray(near_bank, dtype=np.int64))
    n = len(near_bank)
    bank = near_bank.copy()
    move = rng.random(n) >= BANK_SHARE[near_bank] + 0.10
    for b in range(6):
        m = move & (near_bank == b)
        p = BANK_SHARE.copy()
        p[b] = 0.0
        bank[m] = rng.choice(6, size=int(m.sum()), p=p / p.sum())
    pos = rng.random(n)
    ex = None if exclude is None else np.broadcast_to(np.asarray(exclude, dtype=np.int64), (n,))
    out = np.empty(n, dtype=np.int64)
    for b in range(6):
        m = bank == b
        pool = by_bank[b]
        i = (pos[m] * len(pool)).astype(np.int64)
        if ex is not None:  # never pay yourself
            clash = pool[i] == ex[m]
            i[clash] = (i[clash] + 1) % len(pool)
        out[m] = pool[i]
    return out


def make_population(seed: int, scale: float) -> Population:
    rng = np.random.default_rng([seed, 1, 0])
    n_p = max(60, round(12_000 * scale))
    counts = [n_p, max(8, round(800 * scale)), max(3, round(60 * scale)), max(4, round(400 * scale))]
    kind = np.repeat(np.arange(4), counts).astype(np.int8)
    bank = rng.choice(6, size=len(kind), p=BANK_SHARE).astype(np.int8)
    persons = np.arange(n_p)
    by_bank = [persons[bank[:n_p] == b] for b in range(6)]
    by_bank = [p if len(p) else persons for p in by_bank]

    a = lognormal(rng, 1.0, 0.9, n_p)
    lam = 8 * a
    # ponytail: new-counterpart rate capped by the P2P budget (a quiet account cannot have more new payees than transfers)
    nu = np.minimum(lognormal(rng, 1.5, 0.8, n_p), lam)
    k = 2 + rng.poisson(4, n_p)
    has_landlord = rng.random(n_p) < 0.35
    n_slots = k - has_landlord
    n_family = np.minimum(rng.integers(1, 4, n_p), n_slots)
    slot_start = np.concatenate([[0], np.cumsum(n_slots)[:-1]])
    slot_person = np.repeat(persons, n_slots)
    slot_family = (np.arange(len(slot_person)) - slot_start[slot_person]) < n_family[slot_person]
    slot_cp = pick_persons(rng, by_bank, bank[slot_person], exclude=slot_person)
    slot_base = np.where(slot_family, lognormal(rng, 3000, 0.8, len(slot_person)),
                         lognormal(rng, 500, 1.2, len(slot_person)))
    landlord = np.where(has_landlord, pick_persons(rng, by_bank, bank[:n_p], exclude=persons), -1)
    rent = round_p2p(rng, rng.uniform(3000, 15000, n_p))
    rent_dom = rng.integers(1, 6, n_p)

    salaried = rng.random(n_p) < 0.65
    salary = tlognormal(rng, 18_000, 0.6, 9_000, 300_000, n_p)
    employer = rng.choice(np.flatnonzero(kind == EMPLOYER), n_p)
    pay_dom = rng.choice([25, 26, 27, 28, 29, 30, 31, 1], size=len(kind))
    income_rate = np.where(salaried, 0, rng.integers(2, 9, n_p))

    merchants = np.flatnonzero(kind == MERCHANT)
    w = lognormal(rng, 1.0, 1.0, len(merchants))
    billers = np.flatnonzero(kind == BILLER)
    n_bills = np.minimum(rng.integers(2, 6, n_p), len(billers))
    bill_person = np.repeat(persons, n_bills)
    bill_biller = np.concatenate([rng.choice(billers, size=n, replace=False) for n in n_bills])
    sellers = rng.choice(persons, size=max(5, round(0.02 * n_p)), replace=False)
    return Population(
        kind=kind, bank=bank, n_person=n_p, by_bank=by_bank, activity=a, lam=lam, nu=nu,
        slot_start=slot_start, n_family=n_family, n_slots=n_slots, slot_cp=slot_cp, slot_base=slot_base,
        landlord=landlord, rent=rent, rent_dom=rent_dom, salaried=salaried, salary=salary, employer=employer,
        pay_dom=pay_dom, income_rate=income_rate, merchants=merchants, merchant_p=w / w.sum(), billers=billers,
        bill_person=bill_person, bill_biller=bill_biller, bill_base=lognormal(rng, 600, 0.8, len(bill_person)),
        bill_dom=rng.integers(1, 29, len(bill_person)), sellers=sellers)


def population_events(seed: int, pop: Population) -> dict[str, np.ndarray]:
    """Normal activity of every person over days 0-449, vectorised by transaction kind."""
    rng = np.random.default_rng([seed, 1, 1])
    persons = np.arange(pop.n_person)
    ms = np.array(month_starts())
    dim = np.array([days_in_month(m) for m in ms])
    parts = []

    def when(n):
        return DAY0 + rng.integers(0, N_DAYS, n) * DAY + tods(rng, n)

    def add(stream, ts, payer, payee, amount, txn, rail, channel=None, fail=True):
        n = len(ts)
        parts.append({
            "ts": np.asarray(ts, np.int64), "payer": np.asarray(payer, np.int64), "payee": np.asarray(payee, np.int64),
            "amount": np.asarray(amount, float), "txn": np.full(n, txn, np.int8),
            "rail": np.broadcast_to(np.asarray(rail, np.int8), (n,)).copy(),
            "channel": (channels(rng, n) if channel is None else np.full(n, channel)).astype(np.int8),
            # FAILED only on normal activity (spec 6.7)
            "status": ((rng.random(n) < 0.015) if fail else np.zeros(n, bool)).astype(np.int8),
            "stream": np.full(n, stream, np.int64), "counter": np.arange(n, dtype=np.int64)})

    # first transfers to new counterparts; p .2 of them replace a friend slot from then on
    payer = np.repeat(persons, rng.poisson(pop.nu * MONTHS))
    ts = when(len(payer))
    payee = pick_persons(rng, pop.by_bank, pop.bank[payer], exclude=payer)
    base = lognormal(rng, 500, 1.2, len(payer))
    add(S_NEW, ts, payer, payee, round_p2p(rng, base * lognormal(rng, 1, 0.4, len(payer))), P2P,
        p2p_rails(rng, len(payer)))
    n_friend = pop.n_slots - pop.n_family
    conv = (rng.random(len(payer)) < 0.2) & (n_friend[payer] > 0)
    cp = payer[conv]
    c_slot = pop.slot_start[cp] + pop.n_family[cp] + (rng.random(len(cp)) * n_friend[cp]).astype(np.int64)
    n_slot_total = len(pop.slot_cp)
    chg_slot = np.concatenate([np.arange(n_slot_total), c_slot])
    chg_time = np.concatenate([np.zeros(n_slot_total, np.int64), ts[conv] - DAY0 + 1])
    chg_cp = np.concatenate([pop.slot_cp, payee[conv]])
    chg_base = np.concatenate([pop.slot_base, base[conv]])
    order = np.lexsort((chg_time, chg_slot))
    keys = (chg_slot[order] << 32) | chg_time[order]

    # transfers to regular counterparts (the slot's counterpart at that moment)
    payer = np.repeat(persons, rng.poisson((pop.lam - pop.nu) * MONTHS))
    ts = when(len(payer))
    slot = pop.slot_start[payer] + (rng.random(len(payer)) * pop.n_slots[payer]).astype(np.int64)
    j = order[np.searchsorted(keys, (slot << 32) | (ts - DAY0 + 1), side="right") - 1]
    add(S_REGULAR, ts, payer, chg_cp[j], round_p2p(rng, chg_base[j] * lognormal(rng, 1, 0.4, len(payer))), P2P,
        p2p_rails(rng, len(payer)))

    # rent on day 1-5 of each month
    has = np.flatnonzero(pop.landlord >= 0)
    payer = np.repeat(has, len(ms))
    day = (ms[None, :] + pop.rent_dom[has, None] - 1).ravel()
    payer, day = payer[day < N_DAYS], day[day < N_DAYS]
    add(S_RENT, DAY0 + day * DAY + tods(rng, len(day)), payer, pop.landlord[payer], pop.rent[payer], P2P,
        p2p_rails(rng, len(payer)))

    # irregular income of non-salaried persons: family member or a client
    payee = np.repeat(persons, rng.poisson(pop.income_rate * MONTHS))
    ts = when(len(payee))
    fam = pop.slot_cp[pop.slot_start[payee] + (rng.random(len(payee)) * pop.n_family[payee]).astype(np.int64)]
    client = pick_persons(rng, pop.by_bank, pop.bank[payee], exclude=payee)
    payer = np.where(rng.random(len(payee)) < 0.5, fam, client)
    amount = round_p2p(rng, lognormal(rng, 3000, 0.8, len(payee)) * lognormal(rng, 1, 0.4, len(payee)))
    add(S_INCOME, ts, payer, payee, amount, P2P, p2p_rails(rng, len(payee)))

    # salary on the employer's pay day (25th to month end, or the 1st)
    sal = np.flatnonzero(pop.salaried)
    dom = pop.pay_dom[pop.employer[sal]]
    payee = np.repeat(sal, len(ms))
    day = (ms[None, :] + np.minimum(dom[:, None], dim[None, :]) - 1).ravel()
    payee, day = payee[day < N_DAYS], day[day < N_DAYS]
    ts = DAY0 + day * DAY + rng.integers(6 * HOUR, 10 * HOUR, len(day))
    add(S_SALARY, ts, pop.employer[payee], payee, money(pop.salary[payee]), T_PAYROLL, R_PAYROLL,
        channel=C_OTHER, fail=False)

    # merchant QR payments
    payer = np.repeat(persons, rng.poisson(8 * pop.activity * MONTHS))
    ts = when(len(payer))
    payee = pop.merchants[rng.choice(len(pop.merchants), size=len(payer), p=pop.merchant_p)]
    add(S_MERCHANT, ts, payer, payee, money(lognormal(rng, 150, 1.0, len(payer))), T_MERCHANT, R_QR)

    # monthly bills
    idx = np.repeat(np.arange(len(pop.bill_person)), len(ms))
    day = (ms[None, :] + pop.bill_dom[:, None] - 1).ravel()
    idx, day = idx[day < N_DAYS], day[day < N_DAYS]
    amount = money(pop.bill_base[idx] * lognormal(rng, 1, 0.15, len(idx)))
    add(S_BILL, DAY0 + day * DAY + tods(rng, len(day)), pop.bill_person[idx], pop.bill_biller[idx], amount,
        T_BILL, R_BILL)

    ev = concat(parts)
    warm = (ev["ts"] < DAY0 + 90 * DAY) & (ev["status"] == 0) & (ev["payee"] < pop.n_person)
    pop.monthly_income = np.bincount(ev["payee"][warm], weights=ev["amount"][warm], minlength=pop.n_person) / 3
    return ev


def _other_bank_cdf() -> np.ndarray:
    cdf = np.empty((6, 6))
    for b in range(6):
        p = BANK_SHARE.copy()
        p[b] = 0.0
        cdf[b] = np.cumsum(p / p.sum())
    return cdf


OTHER_BANK_CDF = _other_bank_cdf()


def pick_person(rng, pop: Population, near_bank: int, exclude: int) -> int:
    """Scalar pick_persons for the Python-level builders (same rule)."""
    b = int(near_bank)
    if rng.random() >= BANK_SHARE[b] + 0.10:
        b = min(int(np.searchsorted(OTHER_BANK_CDF[b], rng.random(), side="right")), 5)
    pool = pop.by_bank[b]
    i = int(rng.random() * len(pool))
    if pool[i] == exclude:
        i = (i + 1) % len(pool)
    return int(pool[i])


def known_or_new(rng, pop: Population, s: int, p_known: float, family_only: bool = False) -> int:
    """An existing regular counterpart of s with p_known, else a new person."""
    if rng.random() < p_known:
        n = pop.n_family[s] if family_only else pop.n_slots[s]
        return int(pop.slot_cp[pop.slot_start[s] + int(rng.random() * n)])
    return pick_person(rng, pop, pop.bank[s], s)


# ---------------------------------------------------------------- hard negatives (spec 1.5, 2.4)
# Builders return (offset_s, inbound, counterpart, amount, is_merchant) relative to the first event.

def hn_shop_partial_refund(rng, pop, s):
    seller = int(pop.sellers[int(rng.random() * len(pop.sellers))])
    if seller == s:
        seller = int(pop.sellers[(np.flatnonzero(pop.sellers == s)[0] + 1) % len(pop.sellers)])
    x = lognormal(rng, 800, 1.0)
    t = tln(rng, DAY, 1.0, HOUR, 10 * DAY)
    ev = [(0.0, False, seller, x, False), (t, True, seller, x * rng.uniform(0.05, 0.6), False)]
    for _ in range(rng.integers(1, 4)):
        t += rng.uniform(1, 45) * DAY
        ev.append((t, False, seller, x * lognormal(rng, 1, 0.8), False))
    return ev


def hn_friend_loan_repaid(rng, pop, s):
    f = known_or_new(rng, pop, s, 0.7)
    loan = lognormal(rng, 2000, 1.0)
    n = int(rng.integers(1, 4))
    total, w = loan * rng.uniform(0.5, 1.0), rng.dirichlet(np.full(n, 2.0))
    times = np.sort(rng.uniform(3, 60, n)) * DAY
    ev = [(0.0, False, f, loan, False)] + [(t, True, f, total * x, False) for t, x in zip(times, w)]
    if rng.random() < 0.5:
        ev.append((times[-1] + rng.uniform(1, 30) * DAY, False, f, loan * lognormal(rng, 1.3, 0.6), False))
    return ev


def hn_bill_split(rng, pop, s):
    total, k = lognormal(rng, 2500, 0.9), int(rng.integers(2, 9))
    if rng.random() < 0.6:  # s pays first, friends send their shares
        to_merchant = rng.random() < 0.5
        first = (int(pop.merchants[rng.choice(len(pop.merchants), p=pop.merchant_p)]) if to_merchant
                 else pick_person(rng, pop, pop.bank[s], s))
        friends = [known_or_new(rng, pop, s, 0.7) for _ in range(k)]
        times = np.sort(rng.uniform(0, 5, k)) * DAY + 60
        ev = [(0.0, False, first, total, to_merchant)]
        ev += [(t, True, f, total / (k + 1) * rng.uniform(0.8, 1.2), False) for f, t in zip(friends, times)]
        nxt = friends[int(rng.random() * k)] if (to_merchant or rng.random() < 0.5) else first
        ev.append((times[-1] + rng.uniform(0, 30) * DAY + 60, False, nxt, lognormal(rng, 500, 1.2), False))
        return ev
    org, share = known_or_new(rng, pop, s, 0.7), total / (k + 1)  # s is a participant
    t = rng.uniform(0, 5) * DAY + 60
    return [(0.0, False, org, share, False), (t, True, org, share * rng.uniform(0.05, 0.4), False),
            (t + rng.uniform(1, 30) * DAY, False, org, share * lognormal(rng, 1, 0.5), False)]


def hn_family(rng, pop, s):
    rel = known_or_new(rng, pop, s, 0.8, family_only=True)
    n = int(rng.integers(2, 7))
    amounts = lognormal(rng, 3000, 0.8) * np.cumprod(np.r_[1.0, lognormal(rng, 1.3, 0.5, n - 1)])
    times = np.r_[0.0, np.cumsum(rng.uniform(1, 14, n - 1))] * DAY
    ev = [(t, False, rel, a, False) for t, a in zip(times, amounts)]
    if rng.random() < 0.4:
        j = int(rng.integers(0, n - 1))
        ev.append((times[j] + rng.uniform(0.1, 0.9) * (times[j + 1] - times[j]), True, rel,
                   amounts[j] * rng.uniform(0.05, 0.5), False))
    return ev


def hn_deposit_returned(rng, pop, s):
    p = known_or_new(rng, pop, s, 0.1)
    dep = lognormal(rng, 3000, 1.0)
    t = rng.uniform(1, 45) * DAY
    ev = [(0.0, False, p, dep, False), (t, True, p, dep * rng.uniform(0.5, 1.0), False)]
    if rng.random() < 0.6:
        q = p if rng.random() < 0.5 else pick_person(rng, pop, pop.bank[s], s)
        ev.append((t + rng.uniform(0, 14) * DAY + 60, False, q, dep * lognormal(rng, 2, 0.7), False))
    return ev


def hn_legit_escalation(rng, pop, s):
    c = known_or_new(rng, pop, s, 0.2)
    n = int(rng.integers(3, 9))
    spacing = rng.uniform(2, 16) * 7 * DAY / (n - 1)
    times = np.sort(np.maximum(np.arange(n) * spacing + rng.uniform(-0.2, 0.2, n) * spacing, 0.0))
    times[0] = 0.0
    amounts = lognormal(rng, 3000, 1.0) * np.cumprod(np.r_[1.0, lognormal(rng, 1.4, 0.4, n - 1)])
    ev = [(t, False, c, a, False) for t, a in zip(times, amounts)]
    if rng.random() < 0.25:
        j = int(rng.integers(0, n - 1))
        ev.append((times[j] + rng.uniform(0.1, 0.9) * (times[j + 1] - times[j]), True, c,
                   amounts[j] * rng.uniform(0.02, 0.15), False))
    return ev


HN_BUILDERS = [hn_shop_partial_refund, hn_friend_loan_repaid, hn_bill_split, hn_family, hn_deposit_returned,
               hn_legit_escalation]


def fit_in_window(rel: list[float], d0: int, d1: int, rng) -> tuple[int, list[float], bool]:
    """Pick an anchor day so every relative time lands in [d0, d1); compress the sequence if it cannot fit."""
    hi = math.floor((d1 * DAY - 1 - max(rel)) / DAY)
    if hi >= d0:
        return int(rng.integers(d0, hi + 1)), rel, False
    # ponytail: proportional compression keeps order and counts when a sequence is longer than its split
    room = (d1 - d0) * DAY - 1 - rel[0]
    f = room / (max(rel) - rel[0])
    return d0, [rel[0] + (t - rel[0]) * f for t in rel], True


def make_hard_negatives(seed: int, pop: Population, diag: dict):
    """Hard-negative sequences in every period, subjects drawn uniformly from all persons."""
    ev, rows, tuples = Events(), [], []
    compressed = 0
    for gi, group in enumerate(HN_GROUPS):
        for pi, (period, (d0, d1)) in enumerate(SPLITS.items()):
            rng = np.random.default_rng([seed, 5, gi, pi])
            n = rng.binomial(int(pop.n_person * (d1 - d0) / 30), HN_RATES[group])
            stream, counter = S_HN + gi * 10 + pi, 0
            for i, s in enumerate(rng.integers(0, pop.n_person, n)):
                s = int(s)
                seq = sorted(HN_BUILDERS[gi](rng, pop, s), key=lambda e: e[0])
                offs = [e[0] for e in seq]
                rel = chain([0.0] + list(np.diff(offs)), tods(rng, len(seq)))
                day, rel, squeezed = fit_in_window(rel, d0, d1, rng)
                compressed += squeezed
                raw = np.array([e[3] for e in seq])
                amounts = np.where([e[4] for e in seq], money(raw), round_p2p(rng, raw))
                chan, rails = channels(rng, len(seq)), p2p_rails(rng, len(seq))
                seen_out, t_seq = False, []
                for (off, inbound, cp, _, is_m), t, amt, ch, rl in zip(seq, rel, amounts, chan, rails):
                    ts = DAY0 + day * DAY + int(t)
                    payer, payee = (cp, s) if inbound else (s, cp)
                    ev.add(ts, payer, payee, amt, T_MERCHANT if is_m else P2P, R_QR if is_m else rl, ch, stream, counter)
                    step = "IN" if inbound else ("NEXT" if seen_out else "OUT")
                    seen_out |= not inbound
                    rows.append((gi, pi, i, s, stream, counter, step, period))
                    t_seq.append((ts, step, amt))
                    counter += 1
                if period == "train":
                    tuples.extend(mimicry_tuple(t_seq))
    diag["hn_compressed_sequences"] = compressed
    return ev.arrays(), rows, np.array(tuples, dtype=float).reshape(-1, 3)


def mimicry_tuple(t_seq) -> list[tuple[float, float, float]]:
    """(outbound -> first inbound delay, inbound / that outbound, inbound -> next outbound delay)."""
    t_seq = sorted(t_seq)
    ins = [k for k, e in enumerate(t_seq) if e[1] == "IN"]
    if not ins:
        return []
    k = ins[0]
    outs_before = [e for e in t_seq[:k] if e[1] != "IN"]
    outs_after = [e for e in t_seq[k + 1:] if e[1] != "IN"]
    if not outs_before or not outs_after:
        return []
    out, inn, nxt = outs_before[-1], t_seq[k], outs_after[0]
    return [(inn[0] - out[0], inn[2] / out[2], nxt[0] - inn[0])]


# ---------------------------------------------------------------- scam episodes (spec 1.2-1.4, 2.2-2.5)

OUT_ROLES = ("SIGNUP_FEE", "STEP", "UNLOCK_FEE")


@dataclass
class Ev:
    """One victim-timeline event of an episode plan. All randomness is drawn when the plan is built,
    so materialising a plan is deterministic and mimicry never shifts another stream."""
    role: str
    gap: float                 # seconds after the previous timeline event
    tod: int = 0               # time of day used when gap >= 1 day
    amount: float = 0.0        # outbound amount before rounding (SEED: from ratio)
    slot: int = -1             # outbound slot -> receiver block (a seed carries its step's slot)
    step: int = -1
    shift: int = 0             # SPLIT: part goes to the next receiver of the block
    qr: bool = False           # D: step paid to the ring merchant by QR
    ratio: float = 0.0
    seed_src: int = -1         # -1 = receiver of the preceding step, else seeder index
    pieces: tuple = ()         # FRAGMENTED_SEED: ((fraction, offset_s), ...)
    u: tuple = (0.0, 0.0)      # rounding uniforms
    channel: int = 0
    rail: int = 0
    fwd: tuple = ()            # forward by the receiving ring account: (delay_s, frac, to_seeder_u, pick_u, u, v, ch, rail)


@dataclass
class Plan:
    victim: int
    fam: str
    split: str
    holdout: str | None
    events: list
    variants: list
    fund: dict                 # slot -> (u, lead_s, frac, payer, u1, u2, channel, rail)
    report_delay: float
    on_us: bool
    on_us_u: float
    acc_u: tuple               # FRAGMENTED_SEED account picks
    day: int = -1
    R: int = 0
    blocks: list = field(default_factory=list)
    receivers: list = field(default_factory=list)
    mimicked: bool = False


def seed_ratio(rng) -> float:
    u = rng.random()
    return rng.uniform(0.1, 0.6) if u < 0.5 else rng.uniform(1.0, 1.6) if u < 0.9 else rng.uniform(2, 15)


def plan_episode(rng, pop: Population, fam: str, split: str, holdout, victim: int, n_seeders: int,
                 p_same: float) -> Plan:
    A = fam == "A"
    n_steps = int(min(2 + rng.negative_binomial(2, 0.4), 30))
    amounts = [tln(rng, 3000, 1.5, 100, 200_000) if A else tln(rng, 1500, 1.4, 100, 100_000)]
    for _ in range(n_steps - 1):
        r = tln(rng, 2.0, 0.8, 0.3, 50) if A else (1.0 if rng.random() < 0.3 else float(lognormal(rng, 1.6, 0.6)))
        amounts.append(amounts[-1] * r)
    # a seed always leads to a next step, so at most n_steps - 1 seeds
    n_seed = min(int(rng.choice([1, 2, 3], p=[0.6, 0.3, 0.1])), n_steps - 1) if A else 0
    signup = float(rng.uniform(100, 600)) if rng.random() < 0.2 else 0.0
    fee_mult = [tln(rng, 0.3, 0.9, 0.02, 5) for _ in range(int(rng.integers(1, 5)))] if rng.random() < 0.5 else []
    capacity = pop.monthly_income[victim] * tln(rng, 6, 1.0, 0.5, 120)

    outs, cum = [], 0.0  # stop after the outbound that pushes the total past capacity (step 1 always happens)
    if signup:
        outs.append(("SIGNUP_FEE", signup, -1))
        cum += signup
    for k, a in enumerate(amounts):
        if k and cum > capacity:
            break
        outs.append(("STEP", a, k))
        cum += a
    for m in fee_mult:
        if cum > capacity:
            break
        outs.append(("UNLOCK_FEE", cum * m, -1))
        cum += cum * m

    variants, split_steps = [], {}
    if rng.random() < 0.25:
        steps = sorted((o for o in outs if o[0] == "STEP"), key=lambda o: -o[1])
        for o in steps[:int(rng.integers(1, 3))]:
            split_steps[o[2]] = (int(rng.integers(2, 7)), int(rng.integers(1, 3)))  # parts, receivers
        variants.append("SPLIT")
    want_long_gap = rng.random() < 0.15
    on_us = rng.random() < (0.15 if A else 0.35)

    events, first_gap = [], 0.0
    if holdout == "AGED_RECEIVER":  # small two-way transfers with the first receiver 20-45 days before
        g_total = rng.uniform(20, 45) * DAY
        marks = []
        for t in np.sort(rng.uniform(0, g_total - 5 * DAY, int(rng.integers(1, 4)))):
            marks += [(t, "GROOMING_OUT"), (t + rng.uniform(HOUR, 3 * DAY), "GROOMING_IN")]
        prev = 0.0
        for t, role in sorted(marks):
            events.append(Ev(role, t - prev, amount=rng.uniform(100, 1000), slot=0))
            prev = t
        first_gap = g_total - prev

    slot = 0
    for role, amount, k in outs:
        prev_role = events[-1].role if events else None
        if prev_role is None:
            gap = 0.0
        elif prev_role.startswith("GROOMING"):
            gap = first_gap
        elif prev_role == "SEED_INFLOW":
            gap = tln(rng, 18 * HOUR, 1.2, 600, 30 * DAY)
        else:
            gap = tln(rng, 1.5 * DAY, 1.3, 120, 30 * DAY)
        qr = (not A) and role == "STEP" and rng.random() < 0.2
        parts, n_recv = split_steps.get(k, (1, 1)) if role == "STEP" else (1, 1)
        fracs = rng.uniform(0.8, 1.2, parts) / parts if parts > 1 else np.ones(1)
        pgaps = lognormal(rng, 600, 1.0, parts - 1)
        if pgaps.sum() > 6 * HOUR:  # all parts within 6 hours
            pgaps *= 6 * HOUR / pgaps.sum()
        for p in range(parts):
            events.append(Ev(role, gap if p == 0 else float(pgaps[p - 1]), amount=amount * fracs[p], slot=slot,
                             step=k, shift=p % 2 if n_recv == 2 else 0, qr=qr))
        if role == "STEP" and k < n_seed:
            ratio = seed_ratio(rng)
            src = -1 if rng.random() < p_same else int(rng.integers(n_seeders))
            pieces = ()
            if holdout == "FRAGMENTED_SEED":
                n_p = int(rng.integers(2, 6))
                pieces = tuple(zip(rng.dirichlet(np.ones(n_p)), np.r_[0.0, np.sort(rng.uniform(0, DAY, n_p - 1))]))
            events.append(Ev("SEED_INFLOW", tln(rng, 3 * HOUR, 1.2, 300, 72 * HOUR), ratio=ratio, seed_src=src,
                             slot=slot, step=k, pieces=pieces))
        slot += 1

    n = len(events)
    tod_a, u_a, ch_a, rail_a = tods(rng, n), rng.random((n, 2)), channels(rng, n), p2p_rails(rng, n)
    fwd_a = np.column_stack([lognormal(rng, 2 * HOUR, 1.0, n), rng.uniform(0.8, 1.0, n), rng.random((n, 4)),
                             channels(rng, n), p2p_rails(rng, n)])
    for i, e in enumerate(events):
        e.tod, e.u, e.channel, e.rail = int(tod_a[i]), (u_a[i, 0], u_a[i, 1]), int(ch_a[i]), int(rail_a[i])
        if e.role in OUT_ROLES:
            f = fwd_a[i]
            e.fwd = (f[0], f[1], f[2] if A else 1.0, f[3], f[4], f[5], int(f[6]), int(f[7]))
    fam_lo, n_fam = pop.slot_start[victim], pop.n_family[victim]
    fund = {s: (rng.random(), rng.uniform(0, 48 * HOUR), rng.uniform(0.3, 1.0),
                int(pop.slot_cp[fam_lo + int(rng.random() * n_fam)]), rng.random(), rng.random(),
                int(channels(rng, 1)[0]), int(p2p_rails(rng, 1)[0])) for s in range(slot)}
    fast = rng.random() < (0.2 if A else 0.05)  # bank or police contacts the victim first
    delay = tln(rng, DAY, 0.7, 2 * HOUR, 7 * DAY) if fast else tln(rng, 7 * DAY, 1.1, 6 * HOUR, 180 * DAY)
    plan = Plan(victim, fam, split, holdout, events, variants, fund, delay, on_us, rng.random(), tuple(rng.random(3)))
    if want_long_gap:
        add_long_gap(plan, pop, rng)
    return plan


def slot_totals(plan: Plan) -> dict[int, float]:
    tot = {}
    for e in plan.events:
        if e.role in OUT_ROLES:
            tot[e.slot] = tot.get(e.slot, 0.0) + e.amount
    return tot


def funded_slots(plan: Plan, pop: Population) -> set[int]:
    """Slots bigger than one month of income get money from family first with p .5 (spec 1.2)."""
    inc = pop.monthly_income[plan.victim]
    return {s for s, a in slot_totals(plan).items() if a > inc and plan.fund[s][0] < 0.5}


def extent(plan: Plan, pop: Population) -> tuple[float, float]:
    """Earliest and latest relative time over every event the plan will produce."""
    rel = chain([e.gap for e in plan.events], [e.tod for e in plan.events])
    lo, hi = min(rel), max(rel)
    first_of_slot = {}
    for e, t in zip(plan.events, rel):
        if e.role in OUT_ROLES:
            first_of_slot.setdefault(e.slot, t)
            hi = max(hi, t + e.fwd[0])
        for frac, off in e.pieces:
            hi = max(hi, t + off)
    for s in funded_slots(plan, pop):
        lo = min(lo, first_of_slot[s] - plan.fund[s][1])
    return lo, hi


def add_long_gap(plan: Plan, pop: Population, rng) -> None:
    """LONG_GAP: one gap after step 1 becomes 40±5 / 60±5 / 90-110 days, only options that fit the split."""
    ev = plan.events
    cands = [i for i, e in enumerate(ev) if i and e.role in ("STEP", "UNLOCK_FEE") and e.step != 0
             and ev[i - 1].slot != e.slot and ev[i - 1].role != "SEED_INFLOW"]
    d0, d1 = SPLITS[plan.split]
    lo, hi = extent(plan, pop)
    room = (d1 - d0) - (hi - lo) / DAY - 1
    options = [o for o in ((35, 45), (55, 65), (90, 110)) if o[0] <= room]
    if not cands or not options:
        return
    a, b = options[int(rng.integers(len(options)))]
    ev[cands[int(rng.integers(len(cands)))]].gap = rng.uniform(a, min(b, room)) * DAY
    plan.variants.append("LONG_GAP")


def fit_day(plan: Plan, pop: Population, ring_start: float, ring_end: float, rng) -> int | None:
    """Anchor day so every event is inside the split; inside the ring's active window when possible."""
    lo_r, hi_r = extent(plan, pop)
    d0, d1 = SPLITS[plan.split]
    lo, hi = math.ceil((d0 * DAY - lo_r) / DAY), math.floor((d1 * DAY - 1 - hi_r) / DAY)
    if lo > hi:
        return None
    rlo, rhi = max(lo, int(ring_start)), min(hi, int(ring_end))
    return int(rng.integers(rlo, rhi + 1)) if rlo <= rhi else int(rng.integers(lo, hi + 1))


def fits(plan: Plan, pop: Population, day: int) -> bool:
    lo_r, hi_r = extent(plan, pop)
    d0, d1 = SPLITS[plan.split]
    return day * DAY + lo_r >= d0 * DAY and day * DAY + hi_r <= d1 * DAY - 1


def drop_last_slot(plan: Plan) -> bool:
    """Truncate the episode after its second-to-last outbound slot (victim stops earlier). False if impossible."""
    ev = plan.events
    last = max(e.slot for e in ev if e.role in OUT_ROLES)
    first_step_slot = min(e.slot for e in ev if e.role == "STEP")
    if last <= first_step_slot:
        return False
    cut = next(i for i, e in enumerate(ev) if e.role in OUT_ROLES and e.slot == last)
    plan.events = ev[:cut]
    plan.fund = {s: v for s, v in plan.fund.items() if s < last}
    return True


def apply_mimicry(plan: Plan, tuples: np.ndarray, rng) -> bool:
    """Replace seed timing and amount using joint triples from training hard negatives."""
    if not len(tuples):
        return False
    for i, e in enumerate(plan.events):
        if e.role != "SEED_INFLOW" or i + 1 == len(plan.events):
            continue
        delay, ratio, next_delay = tuples[int(rng.integers(len(tuples)))]
        e.gap = max(300.0, float(delay))
        e.ratio = max(0.01, float(ratio))
        plan.events[i + 1].gap = max(600.0, float(next_delay))
    return True


def make_rings(seed: int, pop: Population, hn_tuples: np.ndarray, mimicry: float,
               diag: dict):
    """Build the frozen A/D ring population without consulting detector features."""
    kinds, banks = pop.kind.tolist(), pop.bank.tolist()
    extra = Events()
    labels, episodes, accounts = [], [], []
    victims = np.random.default_rng([seed, 6]).permutation(pop.n_person)
    victim_at = 0
    ring_no, skipped, mimic_retries = 0, 0, 0
    for family in ("A", "D"):
        for split in SCAM_SPLITS:
            d0, d1 = SPLITS[split]
            count = RING_COUNTS[family][split]
            for j in range(count):
                rng = np.random.default_rng([seed, 7, 0 if family == "A" else 1,
                                             SCAM_SPLITS.index(split), j])
                ring_id = f"r{int(opaque_ids(key64(seed, 'ring'), 0, ring_no)[0]):016x}"
                stream = S_EPISODE + ring_no
                ring_no += 1
                holdout = None
                if family == "A" and split == "test":
                    if j < round(count * 0.15):
                        holdout = "FRAGMENTED_SEED"
                    elif j < round(count * 0.30):
                        holdout = "AGED_RECEIVER"
                n_victims = min(1 + int(rng.negative_binomial(1.5, 1.5 / 5.5)), 25)
                n_seeders = int(rng.integers(2 if holdout == "FRAGMENTED_SEED" else 1, 5))
                p_same = float(rng.beta(2, 3))
                active = min(float(rng.uniform(15, 90)), d1 - d0)
                ring_start = float(rng.uniform(d0, d1 - active))
                ring_end = ring_start + active

                def new_account(kind, bank, role):
                    idx = len(kinds)
                    kinds.append(kind)
                    banks.append(int(bank))
                    accounts.append((ring_id, idx, role))
                    return idx

                seeders = [new_account(PERSON, rng.choice(6, p=BANK_SHARE), "SEEDER")
                           for _ in range(n_seeders)]
                sink = new_account(UNKNOWN, rng.choice(6, p=BANK_SHARE), "SINK")
                merchant = new_account(MERCHANT, rng.choice(6, p=BANK_SHARE), "RING_MERCHANT")
                receivers = []
                counter = 0
                for ep_no in range(n_victims):
                    if victim_at == len(victims):
                        raise ValueError("not enough distinct victims")
                    victim = int(victims[victim_at])
                    victim_at += 1
                    empirical, weights = R_EMPIRICAL[family]
                    desired = int(rng.choice(empirical, p=np.array(weights) / sum(weights)))
                    # Account reuse across victims is determined before the episode, without labels or scores.
                    reuse = min(len(receivers), int(rng.binomial(desired, 0.45)))
                    block = (list(rng.choice(receivers, size=reuse, replace=False)) if reuse else [])
                    while len(block) < desired:
                        account = new_account(PERSON, rng.choice(6, p=BANK_SHARE), "RECEIVER")
                        receivers.append(account)
                        block.append(account)
                    rng.shuffle(block)
                    plan = None
                    for attempt in range(20):
                        candidate = plan_episode(rng, pop, family, split, holdout, victim, n_seeders, p_same)
                        day = fit_day(candidate, pop, ring_start, ring_end, rng)
                        while day is None and drop_last_slot(candidate):
                            day = fit_day(candidate, pop, ring_start, ring_end, rng)
                        if day is not None:
                            candidate.day = day
                            plan = candidate
                            break
                    if plan is None:
                        skipped += 1
                        continue
                    n_slots = len({e.slot for e in plan.events if e.role in OUT_ROLES})
                    plan.R = n_slots if holdout == "FRAGMENTED_SEED" else min(desired, n_slots)
                    plan.receivers = block[:plan.R]
                    while len(plan.receivers) < plan.R:
                        a = new_account(PERSON, rng.choice(6, p=BANK_SHARE), "RECEIVER")
                        receivers.append(a)
                        plan.receivers.append(a)
                    if plan.on_us:
                        if not any(banks[a] == banks[victim] for a in plan.receivers):
                            a = new_account(PERSON, banks[victim], "RECEIVER")
                            receivers.append(a)
                            plan.receivers[-1] = a
                        plan.variants.append("ON_US_HOP")
                    if family == "A" and split == "test" and not holdout:
                        mimic_rng = np.random.default_rng([seed, 8, ring_no, ep_no])
                        if mimic_rng.random() < mimicry:
                            for _ in range(20):
                                modified = copy.deepcopy(plan)
                                apply_mimicry(modified, hn_tuples, mimic_rng)
                                if fits(modified, pop, plan.day):
                                    plan = modified
                                    plan.mimicked = True
                                    break
                                mimic_retries += 1
                    ep_id = f"e{int(opaque_ids(key64(seed, 'episode'), ring_no, ep_no)[0]):016x}"
                    new_labels, counter, loss, start, end = materialize_episode(
                        extra, plan, pop, kinds, banks, seeders, sink, merchant, stream, counter,
                        ep_id, ring_id, seed)
                    labels.extend(new_labels)
                    variant = list(dict.fromkeys(([holdout] if holdout else []) + plan.variants))
                    episodes.append((ep_id, ring_id, victim, split, family, "|".join(variant),
                                     int(bool(holdout)), int(plan.mimicked), loss, start, end,
                                     seeders.copy(), plan.receivers.copy()))

                # Ring accounts have ordinary cover activity during their split; this never carries a scam label.
                for a in seeders + receivers:
                    if rng.random() >= 0.5:
                        continue
                    for _ in range(int(rng.integers(1, 4))):
                        day = int(rng.integers(d0, d1))
                        ts = DAY0 + day * DAY + int(tods(rng, 1)[0])
                        kind = int(rng.choice([P2P, T_MERCHANT, T_BILL]))
                        dest = (pick_person(rng, pop, banks[a], a) if kind == P2P else
                                int(rng.choice(pop.merchants if kind == T_MERCHANT else pop.billers)))
                        amount = round_p2p(rng, [rng.uniform(50, 1000)])[0]
                        extra.add(ts, a, dest, amount, kind,
                                  R_PROMPTPAY if kind == P2P else R_QR if kind == T_MERCHANT else R_BILL,
                                  int(channels(rng, 1)[0]), S_COVER + ring_no, counter)
                        counter += 1
    diag.update({"ring_count": ring_no, "episodes_skipped": skipped,
                 "mimicry_fit_retries": mimic_retries})
    return extra.arrays(), labels, episodes, accounts, np.asarray(kinds, np.int8), np.asarray(banks, np.int8)


def materialize_episode(extra: Events, plan: Plan, pop: Population, kinds: list, banks: list,
                        seeders: list, sink: int, merchant: int, stream: int, counter: int,
                        ep_id: str, ring_id: str, seed: int):
    """Turn one plan into event rows and label rows; all normal population events remain untouched."""
    rel = chain([e.gap for e in plan.events], [e.tod for e in plan.events])
    start = DAY0 + plan.day * DAY + int(min(rel))
    end = DAY0 + plan.day * DAY + int(max(rel))
    report_ts = end + int(plan.report_delay)
    out, loss = [], 0.0
    first_slot, slot_paid, last_receiver = set(), {}, plan.receivers[0]
    all_slots = sorted({e.slot for e in plan.events if e.role in OUT_ROLES})
    receiver_for_slot = {}
    for s in all_slots:
        receiver_for_slot[s] = plan.receivers[min(s, len(plan.receivers) - 1)]
        if s and s >= len(plan.receivers) and plan.acc_u[s % len(plan.acc_u)] < 0.2:
            receiver_for_slot[s] = receiver_for_slot[s - 1]
    funds = funded_slots(plan, pop)
    totals = slot_totals(plan)
    eid_key = key64(seed, "event")

    def add(ts, payer, payee, amount, role=None, channel=0, rail=R_PROMPTPAY, txn=P2P):
        nonlocal counter, loss
        amount = float(max(round(amount, 2), 0.01))
        extra.add(ts, payer, payee, amount, txn, rail, channel, stream, counter)
        if role:
            event_id = f"{int(opaque_ids(eid_key, stream, counter)[0]):016x}"
            out.append((event_id, ep_id, plan.victim, role, ts, report_ts, start, end))
            if payer == plan.victim:
                loss += amount
        counter += 1

    for e, t in zip(plan.events, rel):
        ts = DAY0 + plan.day * DAY + int(t)
        if e.role in OUT_ROLES:
            recv = receiver_for_slot[e.slot]
            if e.shift:
                recv = plan.receivers[(plan.receivers.index(recv) + e.shift) % len(plan.receivers)]
            if e.slot not in first_slot:
                first_slot.add(e.slot)
                if e.slot in funds:
                    _, lead, frac, payer, u, v, ch, rail = plan.fund[e.slot]
                    amt = round_amounts([totals[e.slot] * frac], [u], [v])[0]
                    add(ts - int(lead), payer, plan.victim, amt, channel=ch, rail=rail)
            if e.qr:
                recv = merchant
            amt = float(round_amounts([e.amount], [e.u[0]], [e.u[1]])[0])
            add(ts, plan.victim, recv, amt, role=e.role, channel=e.channel,
                rail=R_QR if e.qr else e.rail, txn=T_MERCHANT if e.qr else P2P)
            slot_paid[e.slot] = slot_paid.get(e.slot, 0.0) + amt
            last_receiver = recv
            delay, frac, to_seed, pick, u, v, ch, rail = e.fwd
            dest = seeders[int(pick * len(seeders))] if to_seed < 0.5 else sink
            fwd_amt = float(round_amounts([amt * frac], [u], [v])[0])
            add(ts + int(delay), recv, dest, fwd_amt, channel=ch, rail=rail)
        elif e.role == "SEED_INFLOW":
            sender = last_receiver if e.seed_src < 0 else seeders[e.seed_src % len(seeders)]
            total = float(round_amounts([slot_paid[e.slot] * e.ratio], [e.u[0]], [e.u[1]])[0])
            pieces = e.pieces or ((1.0, 0.0),)
            sources = [last_receiver] + [s for s in seeders if s != last_receiver]
            for j, (part, offset) in enumerate(pieces):
                source = sources[j % min(len(sources), 3)] if e.pieces else sender
                add(ts + int(offset), source, plan.victim, total * part, role=e.role,
                    channel=e.channel, rail=e.rail)
        elif e.role == "GROOMING_OUT":
            amt = float(round_amounts([e.amount], [e.u[0]], [e.u[1]])[0])
            add(ts, plan.victim, plan.receivers[0], amt, role=e.role, channel=e.channel, rail=e.rail)
        elif e.role == "GROOMING_IN":
            amt = float(round_amounts([e.amount], [e.u[0]], [e.u[1]])[0])
            add(ts, plan.receivers[0], plan.victim, amt, role=e.role, channel=e.channel, rail=e.rail)
    end = max(row[4] for row in out)
    report_ts = end + int(plan.report_delay)
    out = [(event_id, episode_id, subject, role, ts, report_ts, start, end)
           for event_id, episode_id, subject, role, ts, _, start, _ in out]
    return out, counter, round(loss, 2), start, end


def save(seed: int, mimicry: float, out_dir: Path, scale: float = 1.0):
    started = time.time()
    diag = {}
    pop = make_population(seed, scale)
    normal = population_events(seed, pop)
    hn, hn_rows, hn_tuples = make_hard_negatives(seed, pop, diag)
    scam, label_rows, ep_rows, account_rows, kinds, banks = make_rings(seed, pop, hn_tuples, mimicry, diag)
    all_ev = concat([normal, hn, scam])
    raw_ids = opaque_ids(key64(seed, "event"), all_ev["stream"], all_ev["counter"])
    order = np.lexsort((raw_ids, all_ev["ts"]))
    all_ev = {k: v[order] for k, v in all_ev.items()}
    payer, payee = all_ev["payer"], all_ev["payee"]
    tokens = hex16(opaque_ids(key64(seed, "account"), 0, np.arange(len(kinds)))).to_numpy()
    event_id = hex16(raw_ids[order])
    event = pd.DataFrame({
        "event_id": event_id, "ts": all_ev["ts"], "ingested_at": all_ev["ts"],
        "payer_token": tokens[payer], "payee_token": tokens[payee],
        "payer_bank": enum_col(banks[payer], BANKS), "payee_bank": enum_col(banks[payee], BANKS),
        "amount_thb": all_ev["amount"], "txn_type": enum_col(all_ev["txn"], TXN_TYPES),
        "payer_type": enum_col(kinds[payer], KINDS), "payee_type": enum_col(kinds[payee], KINDS),
        "channel": enum_col(all_ev["channel"], CHANNELS), "rail": enum_col(all_ev["rail"], RAILS),
        "route_scope": np.where(banks[payer] == banks[payee], "ON_US", "CROSS_BANK"),
        "event_status": enum_col(all_ev["status"], STATUSES), "source": "SIM_G0",
        "is_synthetic": np.ones(len(order), np.int8), "synthetic_fields": "ALL",
    })
    labels = pd.DataFrame(label_rows, columns=["event_id", "episode_id", "subject_idx", "event_role",
                                               "event_ts", "report_ts", "window_start", "window_end"])
    labels["subject_token"] = tokens[labels.pop("subject_idx").to_numpy(dtype=int)]
    labels["label_id"] = "l" + labels.event_id
    labels["label_unit"] = "TRANSACTION"
    labels["intent_id"] = labels.event_id
    labels["intent_revision"] = 1
    labels["label"] = "CONFIRMED_SCAM"
    labels["label_source"] = "INJECTED"
    labels["label_effective_ts"] = labels.report_ts
    labels["review_reference"] = ""
    labels["revision_of"] = ""
    episodes = pd.DataFrame(ep_rows, columns=["episode_id", "ring_id", "victim_idx", "split", "family",
                                             "variant", "is_holdout", "mimicry_applied", "loss_thb",
                                             "start_ts", "end_ts", "seeder_idx", "receiver_idx"])
    episodes["victim_token"] = tokens[episodes.pop("victim_idx").to_numpy(dtype=int)]
    episodes["seeder_tokens"] = episodes.pop("seeder_idx").map(lambda x: [tokens[i] for i in x])
    episodes["receiver_tokens"] = episodes.pop("receiver_idx").map(lambda x: [tokens[i] for i in x])
    ring_accounts = pd.DataFrame(account_rows, columns=["ring_id", "idx", "role"])
    ring_accounts["token"] = tokens[ring_accounts.pop("idx").to_numpy(dtype=int)]
    hn_events = pd.DataFrame(hn_rows, columns=["group_idx", "period_idx", "hn_no", "subject_idx",
                                               "stream", "counter", "step", "split"])
    hn_events["event_id"] = hex16(opaque_ids(key64(seed, "event"), hn_events.pop("stream"),
                                                 hn_events.pop("counter")))
    hn_events["group"] = enum_col(hn_events.pop("group_idx"), HN_GROUPS)
    hn_events["subject_token"] = tokens[hn_events.pop("subject_idx").to_numpy(dtype=int)]
    hn_events["hn_id"] = hn_events.apply(lambda r: f"h{r.period_idx}_{r.group}_{r.hn_no}", axis=1)
    hn_events = hn_events.drop(columns=["period_idx", "hn_no"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in (("events", event), ("labels", labels), ("episodes", episodes),
                        ("ring_accounts", ring_accounts), ("hn_events", hn_events)):
        table.to_parquet(out_dir / f"{name}.parquet", index=False)
    diag.update({"seed": seed, "mimicry": mimicry, "scale": scale, "seconds": round(time.time() - started, 1),
                 "events": len(event), "labels": len(labels), "episodes": len(episodes),
                 "hard_negative_sequences": hn_events.hn_id.nunique()})
    print(json.dumps(diag, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--mimicry", type=float, choices=[0, 0.5, 1], default=0)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=1.0, help="small local smoke run only; full protocol uses 1")
    args = parser.parse_args()
    save(args.seed, args.mimicry, args.out, args.scale)
