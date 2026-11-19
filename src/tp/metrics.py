"""Metrics of the G-0 protocol §4-5: thresholds at a weighted budget, episode outcomes, rates, bootstrap CIs."""
import numpy as np
import pandas as pd

SEED = 20261003
P_MAIN, P_ALT = 1 / 5_000, 1 / 50_000
BUDGETS = {"1/10k": 1e-4, "5/10k": 5e-4, "20/10k": 20e-4}
PRIMARY = "20/10k"   # ELEVATED+HIGH, chosen by the team for H1/G1


def threshold_at_budget(score, y, budget, p=P_MAIN):
    """Lowest threshold whose alert rate at prevalence p stays within budget: FPR·(1−p) + TPR·p ≤ budget.
    Alerts are score >= threshold; inf means not even the top score fits."""
    s, tpr, fpr = _curve(score, y)
    ok = fpr * (1 - p) + tpr * p <= budget
    return float(s[np.flatnonzero(ok)[-1]]) if ok.any() else float("inf")


def threshold_at_fp_tp(score, y, ratio=5.0, p=P_MAIN):
    """Lowest threshold with weighted FP:TP ≤ ratio (Pay.UK-style operating point of v3.3 §8.4)."""
    s, tpr, fpr = _curve(score, y)
    ok = (tpr > 0) & (fpr * (1 - p) <= ratio * tpr * p)
    return float(s[np.flatnonzero(ok)[-1]]) if ok.any() else float("inf")


def _curve(score, y):
    """TPR and FPR when alerting on score >= each distinct score value (ties alert together)."""
    score, y = np.asarray(score, float), np.asarray(y, bool)
    order = np.argsort(-score, kind="stable")
    s, yy = score[order], y[order]
    last = np.r_[s[1:] != s[:-1], True]
    return s[last], np.cumsum(yy)[last] / max(y.sum(), 1), np.cumsum(~yy)[last] / max((~y).sum(), 1)


def fp_per_tp(fpr, tpr, p):
    """Weighted FP:TP of §8.2; undefined (inf) when nothing is caught."""
    return fpr * (1 - p) / (tpr * p) if tpr > 0 else float("inf")


def episode_outcomes(ep_events, alerted):
    """Per episode (§8.1): warned at or before the largest transfer, missed, and exposure E/L.

    ep_events holds every victim scam outbound of the episodes, visible or not; only rows with scored=True can
    carry an alert. The largest transfer is the first one with the maximum amount; the alerted row itself is not
    part of the exposure.
    """
    e = ep_events.sort_values(["episode_id", "ts", "event_id"]).reset_index(drop=True)
    e["pos"] = e.groupby("episode_id").cumcount()
    e["before"] = e.groupby("episode_id").amount_thb.cumsum() - e.amount_thb
    g = e.groupby("episode_id")
    largest = g.amount_thb.idxmax()
    out = pd.DataFrame({"L": g.amount_thb.sum(), "largest_pos": e.pos.to_numpy()[largest.to_numpy()]},
                       index=largest.index)
    hit = e[e.scored & e.event_id.isin(alerted)].groupby("episode_id").first()
    out["alert_pos"] = hit.pos
    out["warned_before_largest"] = out.alert_pos <= out.largest_pos
    out["missed"] = out.alert_pos.isna()
    out["exposure"] = hit.before.reindex(out.index).fillna(out.L) / out.L
    return out


def bootstrap(num, den, reps=2000, seed=SEED, chunk=200):
    """Ratio of sums per replicate, resampling whole units (rings or subjects) with replacement.
    num: units x k numerators, den: units denominators -> reps x k ratios."""
    num = np.asarray(num, float).reshape(len(den), -1)
    den = np.asarray(den, float)
    rng = np.random.default_rng(seed)
    out = []
    for done in range(0, reps, chunk):
        w = rng.multinomial(len(den), np.full(len(den), 1 / len(den)), size=min(chunk, reps - done)).astype(float)
        out.append((w @ num) / (w @ den)[:, None])
    return np.vstack(out)


def ci(values):
    """Percentile 95% interval of bootstrap replicates."""
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def verdict(lo, hi):
    """Protocol §1: CI above 0 passes, below 0 fails, across 0 is inconclusive."""
    return "ผ่าน" if lo > 0 else "ไม่ผ่าน" if hi < 0 else "สรุปไม่ได้"
