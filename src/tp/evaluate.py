"""Phase 3: open the test split once with the frozen manifest; metrics + CIs of protocol §5 -> artifacts JSON.

Refuses to run if any frozen file differs from artifacts/protocol_manifest.json. Once artifacts/test_results.json
exists, a re-run needs --rerun "<reason>", which is appended to docs/lab/PROTOCOL_DEVIATIONS.md.
--rehearse runs the same code on the validation split first (deviation 2): no test row is read, nothing is opened.
Run: PYTHONPATH=src .venv/bin/python -m tp.evaluate data/processed/g0/m0 --mimicry data/processed/g0/m0.5 data/processed/g0/m1 [--rehearse]
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from tp.dataset import HN_GROUPS, HOLDOUTS, ROOT, VARIANTS
from tp.features import DAY
from tp.metrics import (BUDGETS, P_ALT, P_MAIN, PRIMARY, SEED, bootstrap, ci, episode_outcomes, fp_per_tp,
                        threshold_at_budget, verdict)
from tp.train import ARMS, ARTIFACTS, MANIFEST, score

RESULTS = ARTIFACTS / "test_results.json"
REHEARSAL = ARTIFACTS / "rehearsal_val.json"
DEVIATIONS = ROOT / "docs/lab/PROTOCOL_DEVIATIONS.md"
ORDER = ("arm0", "rule", "arm1", "arm2e", "arm2", "arm3")
PAIRS = {"H1 arm2-arm1": ("arm2", "arm1"), "H1s arm2-arm2e": ("arm2", "arm2e"), "arm2e-arm1": ("arm2e", "arm1"),
         "H2 rule-arm0": ("rule", "arm0"), "G1 arm2-rule": ("arm2", "rule"), "arm1-arm0": ("arm1", "arm0"),
         "H5 arm3-arm2": ("arm3", "arm2")}
BUDGET_SLACK = 0.2   # deviation 2: a "pass" needs the winner's realized test FPR within 0.2 x budget of the other arm
G3_MIN_ALERTS = 10   # deviation 2: fewer arm 2 + rule alerts in a hard-negative group = too few to compare


def sha256(path):
    if not path.exists():
        return None
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def check_frozen(manifest, d, mimicry=()):
    """Every frozen code/doc file, the dataset and the models must match the manifest written before test."""
    bad = [f for f, h in manifest["code_sha256"].items() if h is None or sha256(ROOT / f) != h]
    bad += [f"{d.name}/{f}" for f, h in manifest["data_sha256"].items() if sha256(d / f) != h]
    if sha256(ARTIFACTS / f"dataset_profile_{d.name}.json") != manifest["profile_sha256"]:
        bad.append(f"dataset_profile_{d.name}.json")
    for variant in mimicry:
        path = Path(variant)
        expected = manifest.get("mimicry_sha256", {}).get(path.name)
        if expected is None:
            bad.append(f"unfrozen mimicry dataset: {path}")
        else:
            bad += [f"{path.name}/{f}" for f, h in expected.items() if sha256(path / f) != h]
    bad += [f"models/{a}.txt" for a, h in manifest["lightgbm"]["model_sha256"].items()
            if sha256(ARTIFACTS / "models" / f"{a}.txt") != h]
    if bad:
        sys.exit("Frozen files differ from the manifest: " + ", ".join(bad) +
                 "\nBefore opening test: re-run tp.train. After: fix, then log it in PROTOCOL_DEVIATIONS.md.")


def guard(rerun):
    if RESULTS.exists() and not rerun:
        sys.exit("Test already opened (artifacts/test_results.json). Re-run only with --rerun '<reason>'.")
    if RESULTS.exists():
        with DEVIATIONS.open("a") as f:
            f.write(f"| auto | {time.strftime('%Y-%m-%d %H:%M')} | tp.evaluate re-run: {rerun} | ใช่ | ต้องระบุใน report |\n")


def load_split(d, split="test"):
    """T2 rows, episodes and victim outbound of one split, plus the ring-payer rows cut from the T2 population."""
    rows = pd.read_parquet(d / "features.parquet", filters=[("split", "==", split)])
    ring = rows[rows.ring_payer].reset_index(drop=True)
    rows = rows[rows.in_t2].reset_index(drop=True)
    eps = pd.read_parquet(d / "episodes.parquet", filters=[("split", "==", split)])
    ep_events = pd.read_parquet(d / "episode_events.parquet", filters=[("episode_id", "in", eps.episode_id.tolist())])
    return rows, eps, ep_events, ring


def score_all(rows, manifest):
    models = {a: lgb.Booster(model_file=str(ARTIFACTS / "models" / f"{a}.txt")) for a in ARMS}
    return {a: np.asarray(score(a, rows, models.get(a), manifest["rule_k"]), float) for a in ORDER}


def populations(eps, split="test"):
    """Episode sets of the protocol: H1 = family A without holdouts; D = placebo; holdouts and variants apart.
    Every pre-registered set must be non-empty (holdouts exist in test only): an empty one stops the run."""
    eps = eps.assign(variant=eps.variant.fillna(""))
    ho = eps.is_holdout.astype(bool)
    a = eps[(eps.family == "A") & ~ho]
    pops = {"A": a, "D_placebo": eps[eps.family == "D"]}
    pops |= {f"holdout_{h}": eps[ho & eps.variant.str.contains(h)] for h in HOLDOUTS if split == "test"}
    pops |= {f"A_variant_{v}": a[a.variant.str.contains(v)] for v in VARIANTS}
    pops["A_variant_none"] = a[a.variant == ""]
    empty = [k for k, v in pops.items() if not len(v)]
    if empty:
        sys.exit(f"Pre-registered populations empty in {split}: {', '.join(empty)} (docs/lab/G0_DATA_CONTRACT.md)")
    return pops


def confound(pairs, fpr, budget):
    """Deviation 2: a win bought with more false alerts is not a win. Downgrade a verdict when the winning arm's
    realized FPR on this split exceeds the other arm's by more than BUDGET_SLACK x budget."""
    for name, (a, b) in PAIRS.items():
        for m in ("recall", "exposure"):
            p = pairs[f"{name} {m}"]
            win, lose = {"ผ่าน": (a, b), "ไม่ผ่าน": (b, a)}.get(p["verdict"], (None, None))
            if win and fpr[win] - fpr[lose] > BUDGET_SLACK * budget:
                p["verdict"] = "สรุปไม่ได้ (งบจริงไม่เท่ากัน)"


def per_unit(codes, n, values):
    return np.bincount(codes, weights=np.asarray(values, float), minlength=n)


def episode_block(eps, ep_events, rows, scores, thresholds):
    """Recall before largest, missed rate and exposure per arm, with ring-bootstrap CIs and paired differences."""
    ids = eps.episode_id.to_numpy()
    ev = ep_events[ep_events.episode_id.isin(set(ids))]
    codes, rings = pd.factorize(eps.ring_id.to_numpy())
    cols, names = [], []
    for a in ORDER:
        o = episode_outcomes(ev, set(rows.event_id[scores[a] >= thresholds[a]])).reindex(ids)
        for metric, v in (("recall", o.warned_before_largest.fillna(False)), ("missed", o.missed.fillna(True)),
                          ("exposure", o.exposure.fillna(1.0))):
            cols.append(per_unit(codes, len(rings), v))
            names.append((a, metric))
    num, den = np.column_stack(cols), per_unit(codes, len(rings), np.ones(len(ids)))
    reps = bootstrap(num, den)
    point = dict(zip(names, num.sum(0) / den.sum()))
    col = {n: i for i, n in enumerate(names)}
    out = {"episodes": len(ids), "rings": len(rings),
           "arms": {a: {m: [point[(a, m)], *ci(reps[:, col[(a, m)]])] for m in ("recall", "missed", "exposure")}
                    for a in ORDER}}
    for name, (a, b) in PAIRS.items():
        for m in ("recall", "exposure"):
            lo, hi = ci(reps[:, col[(a, m)]] - reps[:, col[(b, m)]])
            better = verdict(lo, hi) if m == "recall" else verdict(-hi, -lo)   # lower exposure is better
            out.setdefault("pairs", {})[f"{name} {m}"] = {"diff": point[(a, m)] - point[(b, m)], "ci": [lo, hi],
                                                          "verdict": better}
    return out


def intent_block(rows, scores, thresholds, holdout_eps):
    """Intent-level rates and weighted FP:TP. Positives = non-holdout scam intents (bootstrap by ring);
    negatives = legitimate intents (bootstrap by payer account)."""
    y = rows.y_true.to_numpy(bool)
    pos = y & ~rows.episode_id.isin(holdout_eps).to_numpy()
    analysed = pos | ~y
    rc, rings = pd.factorize(rows.ring_id[pos])
    pc, payers = pd.factorize(rows.payer_token[~y])
    alerts = {a: scores[a] >= thresholds[a] for a in ORDER}
    tpr_reps = bootstrap(np.column_stack([per_unit(rc, len(rings), alerts[a][pos]) for a in ORDER]),
                         per_unit(rc, len(rings), np.ones(pos.sum())))
    fpr_reps = bootstrap(np.column_stack([per_unit(pc, len(payers), alerts[a][~y]) for a in ORDER]),
                         per_unit(pc, len(payers), np.ones((~y).sum())), seed=SEED + 1)
    out = {"positives": int(pos.sum()), "rings": len(rings), "negatives": int((~y).sum()),
           "payers": len(payers), "holdout_positive_intents_excluded": int((y & ~pos).sum())}
    for i, a in enumerate(ORDER):
        al = alerts[a]
        tpr, fpr = al[pos].mean(), al[~y].mean()
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = {f"1:{round(1 / p):,}": [fp_per_tp(fpr, tpr, p),
                                             *ci(fpr_reps[:, i] * (1 - p) / (tpr_reps[:, i] * p))]
                     for p in (P_MAIN, P_ALT)}
        out[a] = {"alerts": int(al[analysed].sum()), "all_test_alerts": int(al.sum()),
                  "tp": int(al[pos].sum()), "fp": int(al[~y].sum()), "tpr": float(tpr),
                  "fpr": float(fpr), "weighted_rate_per_10k": float((fpr * (1 - P_MAIN) + tpr * P_MAIN) * 1e4),
                  "fp_per_tp": ratio}
    return out


def hn_block(rows, scores, thresholds):
    """False-warning rate per hard-negative group (subject bootstrap) and the paired arm 2 − rule gap (G3).
    Raw alert counts go with every rate; fewer than G3_MIN_ALERTS (arm 2 + rule) is flagged as too few to compare."""
    missing = sorted(set(HN_GROUPS) - set(rows.hn_group.dropna()))
    if missing:
        sys.exit(f"Hard-negative groups without scored intents: {', '.join(missing)} (docs/lab/G0_DATA_CONTRACT.md)")
    out = {}
    for group in HN_GROUPS:
        g = (rows.hn_group == group).to_numpy() & ~rows.y_true.to_numpy(bool)
        sc, subjects = pd.factorize(rows.payer_token[g])
        num = np.column_stack([per_unit(sc, len(subjects), scores[a][g] >= thresholds[a]) for a in ORDER])
        den = per_unit(sc, len(subjects), np.ones(g.sum()))
        reps = bootstrap(num, den, seed=SEED + 2)
        rate = dict(zip(ORDER, num.sum(0) / den.sum()))
        alerts = dict(zip(ORDER, num.sum(0).astype(int).tolist()))
        lo, hi = ci(reps[:, ORDER.index("arm2")] - reps[:, ORDER.index("rule")])
        out[group] = {"intents": int(g.sum()), "subjects": len(subjects), "alerts": alerts,
                      **{a: [rate[a], *ci(reps[:, i])] for i, a in enumerate(ORDER)},
                      "arm2-rule": {"diff": rate["arm2"] - rate["rule"], "ci": [lo, hi]},
                      "G3_arm2_le_rule": bool(rate["arm2"] <= rate["rule"]),
                      "too_few_alerts": alerts["arm2"] + alerts["rule"] < G3_MIN_ALERTS}
    return out


def timeline(event_ids, events, rows, scores, t0=None):
    """Rows of one episode or hard negative for the report: day, direction, amount, visibility and arm 2 score."""
    ev = events[events.event_id.isin(set(event_ids))].sort_values(["ts", "event_id"])
    s = pd.Series(scores["arm2"], index=rows.event_id)
    t0 = ev.ts.iloc[0] if t0 is None else t0
    return [{"day": round((r.ts - t0) / DAY, 2), "payer": r.payer_token[-6:], "payee": r.payee_token[-6:],
             "amount_thb": float(r.amount_thb), "route": r.route_scope, "txn_type": r.txn_type,
             "arm2_score": None if r.event_id not in s.index else round(float(s[r.event_id]), 4)}
            for r in ev.itertuples()]


def examples(d, eps, rows, scores, thresholds):
    """Two H1 episodes arm 2 did not warn before the largest transfer, two legitimate intents it warned."""
    a = eps[(eps.family == "A") & ~eps.is_holdout.astype(bool)]
    ev = pd.read_parquet(d / "episode_events.parquet", filters=[("episode_id", "in", a.episode_id.tolist())])
    o = episode_outcomes(ev, set(rows.event_id[scores["arm2"] >= thresholds["arm2"]]))
    seen = set(ev.episode_id[ev.scored])
    missed = [e for e in o.index[~o.warned_before_largest] if e in seen][:2]
    fp = rows[(scores["arm2"] >= thresholds["arm2"]) & rows.hn_group.notna().to_numpy()].head(2)
    labels = pd.read_parquet(d / "labels.parquet", filters=[("episode_id", "in", missed)]) if missed else None
    hn = pd.read_parquet(d / "hn_events.parquet", filters=[("hn_id", "in", fp.hn_id.tolist())]) if len(fp) else None
    wanted = ([] if labels is None else labels.event_id.tolist()) + ([] if hn is None else hn.event_id.tolist())
    events = pd.read_parquet(d / "events.parquet", filters=[("event_id", "in", wanted)]) if wanted else None
    return {
        "missed_episodes": [{"episode_id": e, "variant": a.set_index("episode_id").variant[e],
                             "rows": timeline(labels.event_id[labels.episode_id == e], events, rows, scores)}
                            for e in missed],
        "false_warnings": [{"hn_id": r.hn_id, "group": r.hn_group, "alerted_event": r.event_id,
                            "rows": timeline(hn.event_id[hn.hn_id == r.hn_id], events, rows, scores)}
                           for r in fp.itertuples()],
    }


def evaluate(d, manifest, split="test"):
    rows, eps, ep_events, ring = load_split(d, split)
    scores = score_all(rows, manifest)
    pops = populations(eps, split)
    holdout_eps = set(eps.episode_id[eps.is_holdout.astype(bool)])
    ring_scores = score_all(ring, manifest) if len(ring) else None
    res = {"episodes": {}, "intents": {}, "hard_negatives": {}, "ring_payer_alerts": {"intents": len(ring)}}
    for b in BUDGETS:
        th = {a: manifest["thresholds"][a][b] for a in ORDER}
        res["episodes"][b] = {name: episode_block(p, ep_events, rows, scores, th) for name, p in pops.items()}
        res["intents"][b] = intent_block(rows, scores, th, holdout_eps)
        res["hard_negatives"][b] = hn_block(rows, scores, th)
        fpr = {a: res["intents"][b][a]["fpr"] for a in ORDER}
        for block in res["episodes"][b].values():
            confound(block["pairs"], fpr, BUDGETS[b])
        res["ring_payer_alerts"][b] = {a: 0 if ring_scores is None else int((ring_scores[a] >= th[a]).sum())
                                       for a in ORDER}   # scored in production, cut from T2 here (deviation 2)
    y = rows.y_true.to_numpy(bool)
    res["pr_auc"] = {a: float(average_precision_score(y, scores[a])) for a in ORDER}
    a_eps = pops["A"]
    a_events = ep_events[ep_events.episode_id.isin(set(a_eps.episode_id))]

    warned = {}
    for a in ORDER:   # §8.4 / D42: episodes each arm warns before the largest at weighted FP:TP 5:1
        o = episode_outcomes(a_events, set(rows.event_id[scores[a] >= manifest["fp_tp5_thresholds"][a]]))
        warned[a] = set(o.index[o.warned_before_largest])
    res["fp_tp5"] = {a: {"warned_before_largest": len(w), "extra_vs_arm0": len(w - warned["arm0"])}
                     for a, w in warned.items()}
    matched = {a: threshold_at_budget(scores[a], y, BUDGETS[PRIMARY]) for a in ORDER}
    res["diagnostic_matched_on_test"] = {
        "note": "threshold re-set on test labels to hit the primary budget exactly; diagnostic only, never a decision",
        **{a: float(episode_outcomes(a_events, set(rows.event_id[scores[a] >= matched[a]])).warned_before_largest
                    .reindex(a_eps.episode_id).fillna(False).mean()) for a in ORDER}}
    res["counts"] = {"test_intents": len(rows), "test_accounts": int(rows.payer_token.nunique()),
                     "test_positive_intents": int(y.sum()), "test_episodes": len(eps),
                     "test_rings": int(eps.ring_id.nunique()),
                     "pr_auc_audit_trigger": [a for a, v in res["pr_auc"].items() if v >= 0.99]}
    res["examples"] = examples(d, eps, rows, scores, {a: manifest["thresholds"][a][PRIMARY] for a in ORDER})
    return res, scores


def mimicry(d, manifest, base, split="test"):
    """H4 / G7: same frozen models and thresholds on test sets whose seed timing/return ratios mimic hard negatives."""
    rows, eps, ep_events, _ = load_split(d, split)
    scores = score_all(rows, manifest)
    th = {a: manifest["thresholds"][a][PRIMARY] for a in ORDER}
    block = episode_block(populations(eps, split)["A"], ep_events, rows, scores, th)
    ratio = {a: block["arms"][a]["recall"][0] / base["arms"][a]["recall"][0] if base["arms"][a]["recall"][0] else None
             for a in ORDER}
    return {"episodes_mimicked": int(eps.mimicry_applied.astype(bool).sum()), "A": block,
            "recall_ratio_vs_m0": ratio, "G7_arm2_pass": bool(ratio["arm2"] is not None and ratio["arm2"] >= 0.7)}


def same_history(d, variants):
    """Rehearsal: a mimicry set may differ from m0 only inside the test window (spec §2.5), so its train and
    validation rows must equal m0's. Otherwise G7 would compare different worlds."""
    before_test = lambda p: pd.read_parquet(p / "features.parquet", filters=[("split", "in", ["train", "val"])])  # noqa: E731
    base = before_test(d)
    bad = [str(v) for v in variants if not before_test(Path(v)).equals(base)]
    if bad:
        sys.exit(f"Mimicry sets differ from {d.name} before the test window: {', '.join(bad)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default=str(ROOT / "data/processed/g0/m0"))
    ap.add_argument("--mimicry", nargs="*", default=[])
    ap.add_argument("--rerun", default="")
    ap.add_argument("--rehearse", action="store_true", help="validation dry run; reads no test row, opens nothing")
    args = ap.parse_args()
    d = Path(args.data).resolve()
    split, out = ("val", REHEARSAL) if args.rehearse else ("test", RESULTS)
    manifest = json.loads(MANIFEST.read_text())
    check_frozen(manifest, d, args.mimicry)
    if args.rehearse:
        same_history(d, args.mimicry)
    else:
        guard(args.rerun)
    started = time.time()
    res, _ = evaluate(d, manifest, split)
    res["mimicry"] = {Path(m).name: mimicry(Path(m), manifest, res["episodes"][PRIMARY]["A"], split)
                      for m in args.mimicry}
    res["meta"] = {"opened_at": time.strftime("%Y-%m-%d %H:%M:%S"), "data": str(d.relative_to(ROOT)),
                   "manifest_sha256": sha256(MANIFEST), "rerun_reason": args.rerun or None,
                   "rehearsal": args.rehearse,
                   "labels": {"data_source": "simulator g0 (synthetic, is_synthetic=1)",
                              "observation_view": "switch: cross-bank P2P only",
                              "split": "val, days 270-329 (rehearsal)" if args.rehearse else "test, days 330-449",
                              "budget_weighting": f"p = 1:{round(1 / P_MAIN):,}", "claim": "learnability only"},
                   "seconds": round(time.time() - started, 1)}
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))
    h1 = res["episodes"][PRIMARY]["A"]["pairs"]["H1 arm2-arm1 recall"]
    print(json.dumps({"split": split, "H1": h1, "seconds": res["meta"]["seconds"]}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
