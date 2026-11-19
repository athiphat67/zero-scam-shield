"""Point-in-time features for Trust Provenance (product design v3.3 §6.1, D42).

One code path for training replay, simulation and the API: State.add() ingests settled
events in time order, State.features() describes a transfer intent from history strictly
before its timestamp. Missing values are None, never 0 or infinity.
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median, quantiles
from typing import NamedTuple

DAY = 86_400
WINDOW = 90 * DAY        # online state retention (§4.2)
NEW = 14 * DAY           # new-relationship cluster and seed-like lookback (§6.1)
ESTABLISHED = 30 * DAY   # D32: counterparties observed longer than this are established
MIN_BASELINE = 3         # fewer outbound rows than this -> p95 baseline is missing

# Evaluation arms of §8.4: arm 1 = GENERIC, arm 2 = GENERIC + TRUST, arm 3 adds NETWORK.
# Arm 2e = GENERIC + TRUST_ESCALATION isolates what the money-back part adds (deviation 2).
GENERIC = (
    "amount_abs", "relationship_age_observed_days", "escalation_vs_pair",
    "escalation_vs_observed_outbound", "new_cluster_payee_count_14d", "outbound_count_24h",
    "split_transfer_cum_24h", "interval_compression", "in_out_ratio_90d",
)
TRUST_SEED = (
    "seed_like_inbound_count_90d", "new_payout_sources_14d", "hours_since_seed_like_inbound",
    "return_ratio", "new_cluster_return_ratio", "cycle_count", "account_context_cycle_count",
)
TRUST_ESCALATION = ("escalation_vs_new_cluster", "escalation_vs_established", "ladder_steps")
TRUST = TRUST_SEED + TRUST_ESCALATION
NETWORK = ("receiver_fan_in_7d",)  # group B: simulator only until A1-B is signed off (D41)


@dataclass(frozen=True, slots=True)
class Event:
    """A transfer in the canonical schema (D33). ts is epoch seconds UTC, amount is satang."""
    event_id: str
    ts: int
    payer: str
    payee: str
    amount: int
    txn_type: str = "UNKNOWN"
    payer_type: str = "UNKNOWN"
    payee_type: str = "UNKNOWN"
    status: str = "SETTLED"

    @classmethod
    def from_row(cls, row):
        """Build from a canonical-schema dict. Unknown types stay UNKNOWN, never guessed."""
        satang = Decimal(str(row["amount_thb"])) * 100
        if satang <= 0 or satang != satang.to_integral_value():
            raise ValueError(f"amount_thb must be positive whole satang: {row['amount_thb']!r} ({row['event_id']})")
        ts = row["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return cls(
            row["event_id"], int(ts.timestamp()), row["payer_token"], row["payee_token"], int(satang),
            row.get("txn_type") or "UNKNOWN", row.get("payer_type") or "UNKNOWN",
            row.get("payee_type") or "UNKNOWN", row.get("event_status") or "SETTLED",
        )


class _View(NamedTuple):
    """One settled event seen from one account (Scam Detect sends on-us payments the same way)."""
    ts: int
    out: bool        # True: this account paid cp
    cp: str
    amount: int
    p2p: bool
    cp_age: int      # seconds since cp was first observed in this account's window, at ts
    seed_like: bool  # inbound only


class State:
    """Per-account 90-day windows. Add events in time order and score before adding."""

    def __init__(self):
        self._views = defaultdict(deque)
        self._seen = set()  # ponytail: unbounded event_id set; production dedupes for 24 h (§4.2)

    def add(self, e):
        """Ingest one event. Returns False for duplicates and non-settled events."""
        if e.status != "SETTLED" or e.event_id in self._seen:
            return False
        self._seen.add(e.event_id)
        p2p = e.txn_type == "P2P"
        payer_age = self._age(e.payee, e.payer, e.ts)
        seed = (p2p and e.payer_type == "PERSON" and e.payee_type == "PERSON" and payer_age <= ESTABLISHED
                and e.amount < sum(v.amount for v in self._cluster(e.payee, e.ts)))
        self._push(e.payer, _View(e.ts, True, e.payee, e.amount, p2p, self._age(e.payer, e.payee, e.ts), False))
        self._push(e.payee, _View(e.ts, False, e.payer, e.amount, p2p, payer_age, seed))
        return True

    def features(self, payer, payee, amount, t):
        """Features for `payer` sending `amount` satang to `payee` at t, from events before t only."""
        w = [v for v in self._views.get(payer, ()) if t - WINDOW <= v.ts < t]
        out = [v for v in w if v.out and v.p2p]
        inb = [v for v in w if not v.out and v.p2p]
        seeds = [v for v in inb if v.seed_like]
        recent_seeds = [v for v in seeds if v.ts >= t - NEW]
        cluster = self._cluster(payer, t)
        pair_out = [v.amount for v in out if v.cp == payee]
        day = [v for v in out if v.ts >= t - DAY]
        first = next((v.ts for v in w if v.cp == payee), None)
        last4 = out[-4:]
        gaps = [b.ts - a.ts for a, b in zip(last4, last4[1:])]
        return {
            "amount_abs": amount / 100,
            "relationship_age_observed_days": None if first is None else (t - first) / DAY,
            "escalation_vs_pair": _ratio(amount, max(pair_out, default=0)),
            "escalation_vs_observed_outbound": _ratio(amount, _p95([v.amount for v in out])),
            "new_cluster_payee_count_14d": len({v.cp for v in cluster}),
            "outbound_count_24h": len(day),
            "split_transfer_cum_24h": (sum(v.amount for v in day) + amount) / 100,
            "interval_compression": median(gaps) / (t - out[-1].ts) if len(gaps) == 3 else None,
            "in_out_ratio_90d": _ratio(sum(v.amount for v in inb), sum(v.amount for v in out)),
            "seed_like_inbound_count_90d": len(seeds),
            "new_payout_sources_14d": len({v.cp for v in recent_seeds}),
            "hours_since_seed_like_inbound": (t - seeds[-1].ts) / 3600 if seeds else None,
            "return_ratio": _ratio(sum(v.amount for v in inb if v.cp == payee), sum(pair_out)),
            "new_cluster_return_ratio": _ratio(sum(v.amount for v in recent_seeds), sum(v.amount for v in cluster)),
            "cycle_count": _cycles(w, lambda v: v.p2p and v.cp == payee and (v.out or v.seed_like)),
            "account_context_cycle_count": _cycles(w, lambda v: v.p2p and (v.cp_age <= NEW if v.out else v.seed_like)),
            "escalation_vs_new_cluster": _ratio(amount, max((v.amount for v in cluster), default=0)),
            "escalation_vs_established": _ratio(amount, _p95([v.amount for v in out if v.cp_age > ESTABLISHED])),
            "ladder_steps": _ladder([v.amount for v in cluster] + [amount]) if first is None or t - first <= NEW else None,
            "receiver_fan_in_7d": len({v.cp for v in self._views.get(payee, ())
                                       if not v.out and v.p2p and t - 7 * DAY <= v.ts < t}),
        }

    def _age(self, account, cp, t):
        first = next((v.ts for v in self._views.get(account, ()) if v.cp == cp and v.ts >= t - WINDOW), t)
        return t - first

    def _cluster(self, account, t):
        """Outbound P2P in the 14 days before t to counterparties that were new when paid."""
        return [v for v in self._views.get(account, ())
                if v.out and v.p2p and v.cp_age <= NEW and t - NEW <= v.ts < t]

    def _push(self, account, view):
        dq = self._views[account]
        dq.append(view)
        while dq[0].ts < view.ts - WINDOW:
            dq.popleft()


def replay(events, want=None):
    """Yield (event, features) for every settled P2P transfer that `want(event)` accepts (default: all),
    scored before it enters the state. Every event still updates the state.

    ponytail: sorts in memory and ignores reversals/late events; stream by ingested_at when a real feed exists.
    """
    state = State()
    for e in sorted(events, key=lambda e: e.ts):
        scored = e.txn_type == "P2P" and (want is None or want(e))
        feats = state.features(e.payer, e.payee, e.amount, e.ts) if scored else None
        if state.add(e) and feats is not None:
            yield e, feats


def _ratio(a, b):
    return a / b if b else None


def _p95(amounts):
    return quantiles(amounts, n=20, method="inclusive")[-1] if len(amounts) >= MIN_BASELINE else None


def _cycles(views, keep):
    """Completed outbound -> seed-like inbound -> outbound rounds among the kept views."""
    n = phase = 0
    for v in views:
        if keep(v):
            if v.out:
                n += phase == 2
                phase = 1
            elif phase:
                phase = 2
    return n


def _ladder(amounts):
    """Consecutive increases ending at the last amount: 1,000 -> 5,000 -> 50,000 gives 2."""
    steps = 0
    for before, after in zip(amounts[-2::-1], amounts[::-1]):
        if after <= before:
            break
        steps += 1
    return steps
