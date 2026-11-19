"""Phase 2: arm 0, rule T2 and LightGBM arms; every knob set on validation; freeze a manifest (protocol §4, §7).

Only train and validation rows are read (parquet filters), so the test split stays closed until tp.evaluate.
Run: PYTHONPATH=src .venv/bin/python -m tp.train data/processed/g0/m0
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from tp.dataset import DAY0, FEATURES, FIT_START, ROOT, TRAIN_LABEL_CUTOFF
from tp.features import DAY, GENERIC, NETWORK, TRUST, TRUST_ESCALATION
from tp.metrics import BUDGETS, P_ALT, P_MAIN, PRIMARY, SEED, episode_outcomes, threshold_at_budget, threshold_at_fp_tp

ARMS = {"arm1": GENERIC, "arm2e": GENERIC + TRUST_ESCALATION, "arm2": GENERIC + TRUST,
        "arm3": GENERIC + TRUST + NETWORK}
CEILING = 0.95   # deviation 2: arm 1 validation recall at the primary budget at or above this = H1 cannot discriminate
LGBM = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 50,
        "metric": "average_precision", "seed": SEED, "deterministic": True, "force_row_wise": True,
        "num_threads": 4, "verbose": -1}
ROUNDS, PATIENCE = 2000, 50
RULE_K = (1, 2, 3)
FROZEN = ["src/tp/sim.py", "src/tp/features.py", "src/tp/dataset.py", "src/tp/metrics.py", "src/tp/train.py",
          "src/tp/evaluate.py", "src/tp/demo.py", "scripts/make_report.py", "docs/lab/G0_EXPERIMENT_PROTOCOL.md", "docs/lab/G0_SCENARIO_SPEC.md",
          "docs/lab/G0_GENERATOR_BRIEF.md", "docs/lab/G0_DATA_CONTRACT.md"]
DATA_FILES = ("events.parquet", "labels.parquet", "episodes.parquet", "ring_accounts.parquet",
              "hn_events.parquet", "features.parquet", "episode_events.parquet")
ARTIFACTS = ROOT / "artifacts"
MANIFEST = ARTIFACTS / "protocol_manifest.json"


def arm0_score(t):
    """Arm 0 control: new payee (no observed history with the payee) and amount >= X; the score is the amount."""
    return np.where(t.relationship_age_observed_days.isna(), t.amount_abs, -1.0)


def rule_t2_score(t, k):
    """Rule T2 (§6.2): seed-like inbound >= k and intent >= m x max(pair max, new-cluster max), falling back to the
    p95 established baseline. The score is that escalation multiple, so m is set at the budget like a threshold."""
    esc = np.fmin(t.escalation_vs_pair, t.escalation_vs_new_cluster).fillna(t.escalation_vs_established)
    return np.where(t.seed_like_inbound_count_90d >= k, esc.fillna(-1.0), -1.0)


def fit(train, val, features, path):
    """LightGBM on labels known at the training cutoff; early stopping on validation average precision.
    Saves the best iteration and returns the reloaded file, so validation and test score the same model."""
    dtrain = lgb.Dataset(train[list(features)], train.y_train.astype(int), free_raw_data=False)
    dval = lgb.Dataset(val[list(features)], val.y_true.astype(int), reference=dtrain)
    model = lgb.train(LGBM, dtrain, ROUNDS, valid_sets=[dval], callbacks=[lgb.early_stopping(PATIENCE, verbose=False)])
    model.save_model(path, num_iteration=model.best_iteration)
    return lgb.Booster(model_file=str(path))


def score(arm, t, model=None, k=None):
    """Scores of one arm; evaluate.py and demo.py call this with the frozen model / k."""
    if arm == "arm0":
        return arm0_score(t)
    if arm == "rule":
        return rule_t2_score(t, k)
    return model.predict(t[list(ARMS[arm])])


def load(d):
    """Train + validation T2 rows, the validation H1 episodes and their scam outbound. Test rows are never read."""
    rows = pd.read_parquet(d / "features.parquet", filters=[("split", "in", ["train", "val"])])
    rows = rows[rows.in_t2]
    eps = pd.read_parquet(d / "episodes.parquet", filters=[("split", "==", "val")])
    h1 = eps[(eps.family == "A") & ~eps.is_holdout.astype(bool)].episode_id.tolist()
    ep_val = pd.read_parquet(d / "episode_events.parquet", filters=[("episode_id", "in", h1)])
    return rows[rows.split == "train"], rows[rows.split == "val"], ep_val


def fit_rows(train):
    """Deviation 3: the state starts empty on day 0, so seed-like flags of days 0-30 stay in the 90-day window
    until about day 120. Train rows before FIT_START stay history only and are never fitted."""
    return train[train.ts >= FIT_START]


def val_summary(val, ep_val, s, threshold):
    alert = s >= threshold
    y = val.y_true.to_numpy(bool)
    tpr, fpr = alert[y].mean(), alert[~y].mean()
    return {"threshold": threshold,
            "recall_before_largest": float(episode_outcomes(ep_val, set(val.event_id[alert])).warned_before_largest.mean()),
            "alerts": int(alert.sum()), "weighted_rate_per_10k": float((fpr * (1 - P_MAIN) + tpr * P_MAIN) * 1e4)}


def select(train, val, ep_val, models_dir):
    """Fit every arm and pick all knobs on validation: rule k at the primary budget, then thresholds per budget."""
    models_dir.mkdir(parents=True, exist_ok=True)
    models = {arm: fit(train, val, feats, models_dir / f"{arm}.txt") for arm, feats in ARMS.items()}
    scores = {"arm0": arm0_score(val)} | {arm: score(arm, val, m) for arm, m in models.items()}
    y = val.y_true
    k_recall = {}
    for k in RULE_K:
        s = rule_t2_score(val, k)
        k_recall[k] = val_summary(val, ep_val, s, threshold_at_budget(s, y, BUDGETS[PRIMARY]))["recall_before_largest"]
    k = max(RULE_K, key=lambda k: (k_recall[k], -k))   # tie -> fewer seeds required
    scores["rule"] = rule_t2_score(val, k)
    thresholds = {arm: {b: threshold_at_budget(s, y, v) for b, v in BUDGETS.items()} for arm, s in scores.items()}
    validation = {arm: {b: val_summary(val, ep_val, s, th) for b, th in thresholds[arm].items()}
                  for arm, s in scores.items()}
    arm1_recall = validation["arm1"][PRIMARY]["recall_before_largest"]
    return models, k, k_recall, thresholds, {
        "fp_tp5_thresholds": {arm: threshold_at_fp_tp(s, y) for arm, s in scores.items()},
        "validation": validation,
        "ceiling": {"arm1_val_recall": arm1_recall, "at_or_above": CEILING, "flag": bool(arm1_recall >= CEILING)},
        "g4_audit_val": {"pr_auc": {arm: float(average_precision_score(y, s)) for arm, s in scores.items()},
                         "single_feature_ap": single_feature_ap(val)}}


def single_feature_ap(t):
    """G4 audit on validation (deviation 2): AP of each feature alone, best direction, missing ranked last.
    A feature near 1.0 on its own means the simulator separates the classes too easily."""
    y, out = t.y_true.to_numpy(bool), {}
    for f in FEATURES:
        x = t[f].to_numpy(float)
        if not np.isnan(x).all():
            out[f] = max(average_precision_score(y, np.where(np.isnan(x), np.nanmin(s) - 1, s)) for s in (x, -x))
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def sha256(path):
    if not path.exists():
        return None
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def data_hashes(d):
    hashes = {f: sha256(d / f) for f in DATA_FILES}
    missing = [f for f, h in hashes.items() if h is None]
    if missing:
        raise FileNotFoundError(f"Incomplete dataset {d}: {', '.join(missing)}")
    return hashes


def main(path):
    started = time.time()
    d = Path(path).resolve()
    source_hashes = data_hashes(d)
    mimicry_hashes = {name: data_hashes(d.parent / name) for name in ("m0.5", "m1")
                      if (d.parent / name).exists()}
    profile_path = ARTIFACTS / f"dataset_profile_{d.name}.json"
    profile_hash = sha256(profile_path)
    if profile_hash is None:
        raise FileNotFoundError(f"Missing dataset profile: {profile_path}")
    train_all, val, ep_val = load(d)
    train = fit_rows(train_all)
    models, k, k_recall, thresholds, extra = select(train, val, ep_val, ARTIFACTS / "models")
    manifest = {
        "note": "Frozen before the test split is opened. Learnability on synthetic data, not production accuracy.",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data": str(d.relative_to(ROOT)),
        "data_sha256": source_hashes,
        "mimicry_sha256": mimicry_hashes,
        "profile_sha256": profile_hash,
        "code_sha256": {f: sha256(ROOT / f) for f in FROZEN},
        "seed": SEED, "split_bounds_day": [90, 270, 330, 450], "train_label_cutoff_day": 330,
        "p_main": P_MAIN, "p_alt": P_ALT, "budgets": BUDGETS, "primary_budget": PRIMARY,
        "rule_k": k, "rule_k_val_recall": k_recall, "thresholds": thresholds, **extra,
        "lightgbm": {"params": LGBM, "rounds": ROUNDS, "patience": PATIENCE,
                     "trees": {arm: m.num_trees() for arm, m in models.items()},
                     "model_sha256": {arm: sha256(ARTIFACTS / "models" / f"{arm}.txt") for arm in models}},
        "fit_start_day": (FIT_START - DAY0) // DAY,
        "rows": {"train": len(train), "train_pos_true": int(train.y_true.sum()),
                 "train_cold_start_excluded": len(train_all) - len(train),
                 "train_pos_cold_start_excluded": int(train_all.y_true.sum() - train.y_true.sum()),
                 "train_pos_known_at_cutoff": int(train.y_train.sum()), "val": len(val),
                 "val_pos": int(val.y_true.sum()),
                 "val_pos_known_at_cutoff": int((val.y_true & val.label_effective_ts.le(TRAIN_LABEL_CUTOFF)).sum()),
                 "val_h1_episodes": int(ep_val.episode_id.nunique())},
        "bootstrap": {"reps": 2000, "seed": SEED},
        "seconds": round(time.time() - started, 1),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({"rule_k": k, "validation": manifest["validation"], "trees": manifest["lightgbm"]["trees"],
                      "ceiling": manifest["ceiling"], "g4_audit_val": manifest["g4_audit_val"],
                      "mimicry_frozen": sorted(mimicry_hashes) or "NONE: H4 needs m0.5/m1 processed before tp.train",
                      "seconds": manifest["seconds"]}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/processed/g0/m0")
