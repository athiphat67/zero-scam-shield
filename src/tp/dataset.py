"""G-0 feature table: switch view -> point-in-time replay -> eligible T2 intents with labels (protocol §2-3).

Only event fields reach features.py. Labels, episodes, rings and hard-negative metadata are joined after
the replay and are for evaluation only; model inputs are the arm feature lists, never these columns.

Run: PYTHONPATH=src .venv/bin/python -m tp.dataset data/processed/g0/m0
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from tp.features import DAY, GENERIC, NETWORK, TRUST, Event, replay

ROOT = Path(__file__).resolve().parents[2]
DAY0 = 1_735_664_400                          # 2025-01-01 00:00 ICT = simulator day 0 (spec §6)
BOUNDS = np.array([DAY0 + d * DAY for d in (90, 270, 330, 450)])
SPLITS = np.array(["warmup", "train", "val", "test", "after"])
TRAIN_LABEL_CUTOFF = DAY0 + 330 * DAY         # labels known when the model is trained (protocol §2)
FIT_START = DAY0 + 120 * DAY                  # deviation 3: days 90-119 are history only (cold-start seed-like flags)
FEATURES = GENERIC + TRUST + NETWORK
TABLES = ("events", "labels", "episodes", "ring_accounts", "hn_events")

# Generator output contract: docs/lab/G0_DATA_CONTRACT.md (schema only, no detector knowledge)
VARIANTS = ("SPLIT", "LONG_GAP", "ON_US_HOP")
HOLDOUTS = ("FRAGMENTED_SEED", "AGED_RECEIVER")
HN_GROUPS = ("SHOP_PARTIAL_REFUND", "FRIEND_LOAN_REPAID", "BILL_SPLIT", "FAMILY", "DEPOSIT_RETURNED",
             "LEGIT_ESCALATION")
COLUMNS = {
    "events": {"event_id", "ts", "payer_token", "payee_token", "amount_thb", "txn_type", "payer_type", "payee_type",
               "route_scope", "event_status", "is_synthetic"},
    "labels": {"event_id", "label", "subject_token", "episode_id", "event_role", "label_effective_ts"},
    "episodes": {"episode_id", "ring_id", "split", "family", "variant", "is_holdout", "victim_token", "loss_thb",
                 "mimicry_applied"},
    "ring_accounts": {"ring_id", "token", "role"},
    "hn_events": {"event_id", "hn_id", "group", "subject_token", "step"},
}
PARTY = {"PERSON", "MERCHANT", "BILLER", "EMPLOYER", "UNKNOWN"}
ENUMS = {
    ("events", "txn_type"): {"P2P", "MERCHANT", "BILL", "PAYROLL"}, ("events", "payer_type"): PARTY,
    ("events", "payee_type"): PARTY, ("events", "route_scope"): {"CROSS_BANK", "ON_US"},
    ("events", "event_status"): {"SETTLED", "FAILED"}, ("labels", "label"): {"CONFIRMED_SCAM"},
    ("labels", "event_role"): {"SIGNUP_FEE", "STEP", "UNLOCK_FEE", "SEED_INFLOW", "GROOMING_OUT", "GROOMING_IN"},
    ("episodes", "split"): {"train", "val", "test"}, ("episodes", "family"): {"A", "D"},
    ("ring_accounts", "role"): {"SEEDER", "RECEIVER", "SINK", "RING_MERCHANT"},
    ("hn_events", "group"): set(HN_GROUPS), ("hn_events", "step"): {"OUT", "IN", "NEXT"},
}


def check_contract(tables):
    """Fail loudly when generator output breaks the contract, instead of silently losing rows or populations."""
    missing = [f"{n}: missing {sorted(c - set(tables[n].columns))}" for n, c in COLUMNS.items()
               if c - set(tables[n].columns)]
    if missing:
        raise ValueError("Data contract (docs/lab/G0_DATA_CONTRACT.md):\n" + "\n".join(missing))
    ev, lab, ep = tables["events"], tables["labels"], tables["episodes"]
    extra = {(n, c): set(map(str, tables[n][c].dropna().unique())) - ok for (n, c), ok in ENUMS.items()}
    unknown = set(ep.variant.fillna("").str.split("|").explode()) - {""} - set(VARIANTS + HOLDOUTS)
    holdout = ep.variant.fillna("").str.contains("|".join(HOLDOUTS))
    checks = [
        *[(not x, f"{n}.{c}: unexpected {sorted(x)[:5]}") for (n, c), x in extra.items()],
        *[(pd.api.types.is_integer_dtype(tables[n][c]), f"{n}.{c}: int64 epoch seconds expected")
          for n, c in (("events", "ts"), ("labels", "label_effective_ts"))],
        (not unknown, f"episodes.variant: unexpected {sorted(map(str, unknown))[:5]} (use '|' between tokens)"),
        ((ep.is_holdout.astype(bool) == (holdout & (ep.family == "A") & (ep.split == "test"))).all(),
         "episodes.is_holdout must be 1 exactly for family A test episodes with a holdout variant"),
        ((ev.is_synthetic == 1).all(), "events.is_synthetic must be 1 on every row"),
        (not ev.event_id.duplicated().any(), "events.event_id must be unique"),
        (lab.event_id.isin(ev.event_id).all(), "labels.event_id not in events"),
        (tables["hn_events"].event_id.isin(ev.event_id).all(), "hn_events.event_id not in events"),
        (lab.episode_id.isin(ep.episode_id).all(), "labels.episode_id not in episodes"),
    ]
    bad = [msg for ok, msg in checks if not ok]
    if bad:
        raise ValueError("Data contract (docs/lab/G0_DATA_CONTRACT.md):\n" + "\n".join(bad))


def split_of(ts):
    return SPLITS[np.searchsorted(BOUNDS, np.asarray(ts), side="right")]


def switch_view(events):
    """What the PromptPay switch sees: cross-bank P2P rows (on-us is invisible), deduplicated, in time order."""
    v = events[(events.txn_type == "P2P") & (events.route_scope == "CROSS_BANK")]
    return v.drop_duplicates("event_id").sort_values(["ts", "event_id"], kind="stable").reset_index(drop=True)


def to_events(view):
    """Vectorized Event.from_row for the switch view. Repeated strings are shared to keep ~2M events small."""
    amount = view.amount_thb.to_numpy(float) * 100
    satang = np.rint(amount)
    bad = (satang <= 0) | (np.abs(amount - satang) > 1e-6)
    if bad.any():
        raise ValueError(f"amount_thb must be positive whole satang: {view.event_id[bad].tolist()[:5]}")
    if view.payer_token.isna().any() or view.payee_token.isna().any():
        raise ValueError("payer_token/payee_token must not be missing")
    cols = [_shared(view[c].fillna(default)) for c, default in (
        ("payer_token", ""), ("payee_token", ""), ("txn_type", "UNKNOWN"), ("payer_type", "UNKNOWN"),
        ("payee_type", "UNKNOWN"), ("event_status", "SETTLED"))]
    return [Event(i, t, payer, payee, a, tx, pt, qt, st) for i, t, a, payer, payee, tx, pt, qt, st in
            zip(view.event_id.tolist(), view.ts.astype("int64").tolist(), satang.astype("int64").tolist(), *cols)]


def _shared(col):
    cat = col.astype("category")
    names = list(cat.cat.categories)
    return [names[c] for c in cat.cat.codes.tolist()]


def score(view):
    """Point-in-time features of every PERSON->PERSON intent after warm-up, in one pass over the timeline."""
    start, end = int(BOUNDS[0]), int(BOUNDS[-1])
    want = lambda e: e.payer_type == "PERSON" and e.payee_type == "PERSON" and start <= e.ts < end  # noqa: E731
    ids, blocks, rows = [], [], []
    for e, f in replay(to_events(view), want):
        ids.append(e.event_id)
        rows.append([f[k] for k in FEATURES])
        if len(rows) == 100_000:  # numpy blocks: a list of 1M+ feature dicts would need ~2 GB
            blocks.append(np.array(rows, dtype=float))
            rows = []
    blocks.append(np.array(rows, dtype=float).reshape(-1, len(FEATURES)))  # None -> NaN
    out = pd.DataFrame(np.vstack(blocks), columns=list(FEATURES))
    out.insert(0, "event_id", ids)
    return out


def history_insufficient(view, payer, t):
    """v3.3 §2.2 status (reported, not routed): < 10 visible settled P2P rows in 90 days or < 30 days observed."""
    ok = view[view.event_status.fillna("SETTLED") == "SETTLED"]
    acc = pd.concat([ok.payer_token, ok.payee_token], ignore_index=True)
    ts = pd.concat([ok.ts, ok.ts], ignore_index=True).to_numpy(np.int64)
    cats = pd.Categorical(acc)
    key = np.sort(cats.codes.astype(np.int64) << 32 | ts)
    code = pd.Categorical(payer, categories=cats.categories).codes.astype(np.int64) << 32
    t = np.asarray(t, np.int64)
    n = np.searchsorted(key, code | t) - np.searchsorted(key, code | (t - 90 * DAY))
    first = key[np.minimum(np.searchsorted(key, code), len(key) - 1)]
    observed = np.where((first >> 32) == (code >> 32), t - (first & 0xFFFFFFFF), 0)
    return (n < 10) | (observed < 30 * DAY)


def build(tables):
    """One row per scored intent: features + evaluation-only columns. `in_t2` marks the T2 population."""
    view = switch_view(tables["events"])
    t = score(view).merge(view[["event_id", "ts", "payer_token", "payee_token", "amount_thb"]], on="event_id")
    t["split"] = split_of(t.ts)
    t["ring_payer"] = t.payer_token.isin(set(tables["ring_accounts"].token))

    lab = tables["labels"]
    lab = lab.loc[lab.label == "CONFIRMED_SCAM",
                  ["event_id", "subject_token", "episode_id", "event_role", "label_effective_ts"]]
    if lab.event_id.duplicated().any():
        raise ValueError("one confirmed label per event expected")
    t = t.merge(lab, on="event_id", how="left")
    t["y_true"] = t.payer_token == t.subject_token          # victim's own scam outbound (protocol §2)
    ep = tables["episodes"][["episode_id", "ring_id", "split", "family", "variant", "is_holdout"]]
    t = t.merge(ep.rename(columns={"split": "episode_split"}), on="episode_id", how="left")
    t["purged"] = t.y_true & (t.episode_split != t.split)
    t["y_train"] = t.y_true & (t.label_effective_ts <= TRAIN_LABEL_CUTOFF)  # label as known at training time

    hn = tables["hn_events"]
    hn = hn.loc[hn.step.isin(["OUT", "NEXT"]), ["event_id", "hn_id", "group", "subject_token"]]
    hn = hn.drop_duplicates("event_id").rename(columns={"group": "hn_group", "subject_token": "hn_subject"})
    t = t.merge(hn, on="event_id", how="left")
    own = t.hn_subject == t.payer_token                                  # only the subject's own outbound
    t["hn_id"], t["hn_group"] = t.hn_id.where(own), t.hn_group.where(own)
    t = t.drop(columns="hn_subject")

    t["insufficient_history"] = history_insufficient(view, t.payer_token, t.ts)
    t["in_t2"] = t.split.isin(["train", "val", "test"]) & ~t.ring_payer & ~t.purged
    return t


def episode_events(tables, t):
    """Every victim scam outbound (visible or not) per episode: the base of L_e, largest transfer and exposure."""
    lab = tables["labels"]
    lab = lab.loc[lab.label == "CONFIRMED_SCAM", ["event_id", "episode_id", "subject_token", "event_role"]]
    ev = tables["events"][["event_id", "ts", "payer_token", "amount_thb", "txn_type", "route_scope", "event_status"]]
    e = lab.merge(ev, on="event_id")
    e = e[(e.payer_token == e.subject_token) & (e.event_status == "SETTLED")]
    e["scored"] = e.event_id.isin(set(t.loc[t.in_t2, "event_id"]))
    return e.drop(columns=["payer_token", "subject_token"]).sort_values(["episode_id", "ts", "event_id"])


def profile(t, tables, ep_events):
    ep = tables["episodes"]
    splits = {}
    for s in ("train", "val", "test"):
        g = t[t.in_t2 & (t.split == s)]
        e = ep[ep.split == s]
        seen = ep_events[ep_events.scored].episode_id
        splits[s] = {
            "intents": len(g),
            "accounts": int(g.payer_token.nunique()),
            "positive_intents": int(g.y_true.sum()),
            "positive_intents_known_at_cutoff": int(g.y_train.sum()) if s == "train" else None,
            "episodes": {f"{fam}{'_holdout' if h else ''}": int(n) for (fam, h), n in
                         e.groupby(["family", e.is_holdout.astype(bool)]).size().items()},
            "episodes_without_visible_intent": int((~e.episode_id.isin(seen)).sum()),
            "rings": int(e.ring_id.nunique()),
            "hn_intents": {k: int(v) for k, v in g.hn_group.value_counts().sort_index().items()},
            "insufficient_history_share": round(float(g.insufficient_history.mean()), 4),
        }
    neg = t[t.in_t2 & ~t.y_true]   # cold start: state is empty on day 0, so early seed-like flags may be artifacts
    period = pd.cut((neg.ts - DAY0) // DAY, [90, 120, 150, 270, 330, 450], right=False)
    return {
        "observation_view": "switch (cross-bank P2P only) · synthetic · learnability only",
        "events_all": len(tables["events"]),
        "scored_rows": len(t),
        "splits": splits,
        "negative_seed_like_mean_by_day": {str(k): round(float(v), 3) for k, v in
                                           neg.groupby(period, observed=True).seed_like_inbound_count_90d.mean().items()},
        "excluded": {
            "ring_payer_intents": int((t.ring_payer & t.split.isin(["train", "val", "test"])).sum()),
            "purged_scam_intents": int(t.purged.sum()),
            "train_positive_intents_unknown_at_cutoff": int((t.in_t2 & (t.split == "train") & t.y_true & ~t.y_train).sum()),
        },
    }


def example_episode(tables, family="A", split="test"):
    """Timeline of one ordinary episode (victim's in/out scam rows) for the Phase 1 profile."""
    ep = tables["episodes"]
    e = ep[(ep.family == family) & (ep.split == split) & ~ep.is_holdout.astype(bool)].sort_values("episode_id").iloc[0]
    lab = tables["labels"]
    rows = lab[lab.episode_id == e.episode_id].merge(tables["events"], on="event_id").sort_values("ts")
    return {
        "episode_id": e.episode_id, "variant": e.variant, "loss_thb": float(e.loss_thb),
        "rows": [{"day": round((r.ts - rows.ts.iloc[0]) / DAY, 2), "role": r.event_role,
                  "direction": "OUT" if r.payer_token == e.victim_token else "IN",
                  "amount_thb": float(r.amount_thb), "route": r.route_scope, "txn_type": r.txn_type}
                 for r in rows.itertuples()],
    }


def main(path):
    started = time.time()
    d = Path(path)
    tables = {n: pd.read_parquet(d / f"{n}.parquet") for n in TABLES}
    check_contract(tables)
    t = build(tables)
    ep_events = episode_events(tables, t)
    t.to_parquet(d / "features.parquet", index=False)
    ep_events.to_parquet(d / "episode_events.parquet", index=False)
    prof = profile(t, tables, ep_events)
    prof["example_episode"] = example_episode(tables)
    prof["seconds"] = round(time.time() - started, 1)
    out = ROOT / "artifacts" / f"dataset_profile_{d.name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(prof, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({k: prof[k] for k in ("splits", "excluded", "seconds")}, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/processed/g0/m0")
