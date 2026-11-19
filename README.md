# Zero Scam Shield: Trust Provenance

**Catching authorized-push-payment scams *before* the victim's largest transfer, by asking how the trust between two accounts was built rather than whether a single payment looks odd.**

![Finalist](https://img.shields.io/badge/NITMX_Fintech_Bootcamp_2026-Finalist_·_Top_15_of_306-success)
![Role](https://img.shields.io/badge/Role-Team_Lead-blue)
![LightGBM](https://img.shields.io/badge/LightGBM-02569B)
![Tests](https://img.shields.io/badge/leakage_%26_pipeline_tests-48_passing-brightgreen)

> **Context:** NITMX Fintech Bootcamp 2026, Track 1 (team of 5, Jun – Oct 2026). This is the **final-round detection prototype**. It runs entirely on **synthetic data** from its own simulator, so no bank data or personal data is included.

---

## The problem

In an authorized scam, the victim presses "transfer" themselves. Banks can confirm *who* authorized the payment, but not whether the *reason* they were given is real. Detection usually looks at one transaction or one account at a time, so it misses a pattern that unfolds over days:

> small "investment" → a fake payout comes back → bigger transfers → the largest transfer → the money moves on

From **185 real AOC 1441 case reports**, the 15% of cases that used small fake payouts before escalating accounted for **43% of total losses**. Stopping those victims *before the largest transfer* is where the money is saved.

## The idea: Trust Provenance

For each payment about to be authorized at the switch, score the **history of the relationship** between payer and payee:

- How old is this relationship?
- Did money come *back* first (a seed payout)?
- Is the amount ladder climbing?
- Is it unusual against this payer's own baseline?

All features come from the payment ledger only, never from chats or device data, to stay within PDPA limits. Every alert carries **TreeSHAP reason codes**, so a bank officer can see *why* the payment was paused.

## Experiment design

| | |
|---|---|
| **Data** | Simulator ([`src/tp/sim.py`](src/tp/sim.py)): a multi-bank retail population, injected scam rings with scenarios calibrated from AOC case statistics, plus hard negatives (family transfers, partial refunds, chit funds, legitimate escalating payments). **~1.44M payment intents**, seeded and byte-reproducible. |
| **Split** | By time: train and validation before day 330, test on days 330–449. Scam rings never cross splits. |
| **Arms** | Arm 0: "new payee + large amount" control · Rule T2: a hand-written rule · Arm 1: generic LightGBM · Arm 2e: + amount ladder · **Arm 2: + trust provenance** |
| **Budget** | Every arm gets the same alert budget: **20 alerts per 10,000 payments**. |
| **Locked first** | Thresholds come from validation only. The [protocol](docs/lab/G0_EXPERIMENT_PROTOCOL.md) and a manifest hash were frozen before the test split was opened. |
| **Leakage tests** | [48 unit tests](tests/): point-in-time features (including a test that *must* fail if a leak is planted), score-before-update, ring isolation across splits, determinism, batch/replay parity. |

## Results (test split, budget 20/10k)

| Arm | Scams caught **before the largest transfer** | 95% CI |
|---|---|---|
| Rule T2 | 3.9% | 1.5 – 7.1 |
| Arm 0: new payee + amount | 30.3% | 24.5 – 35.6 |
| Arm 1: generic LightGBM | 57.9% | 51.5 – 64.4 |
| Arm 2e: + amount ladder | 58.3% | 52.1 – 64.7 |
| **Arm 2: + trust provenance** | **60.6%** | 54.5 – 67.1 |

**What holds up:**
- ML beats the hand-written rule by **+56.7 pp** (CI +49.8 to +63.6).
- ML roughly **doubles** the "new payee" control.
- When the simulator makes scammers imitate normal payment behaviour (mimicry level 0.5), Arm 2 still keeps 91.6% of its recall.

**What doesn't (yet):** trust provenance on top of a generic model adds **+2.8 pp, with a CI from −0.4 to +6.4**, so its added value is **inconclusive** on this data. The report says so rather than claiming the feature set wins. Arm 2 also raises more false alerts than the rule on three hard-negative groups (partial refunds, family transfers, legitimately escalating payments). That is exactly what a pilot on real rails would have to measure.

Full numbers: [`reports/G0_LAB_REPORT.md`](reports/G0_LAB_REPORT.md) (Thai).

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests          # 48 tests, ~25 s

# Full pipeline: generate synthetic data → features → train → evaluate → report
for m in 0 0.5 1; do PYTHONPATH=src .venv/bin/python -m tp.sim --seed 20261003 --mimicry $m --out data/processed/g0/m$m; done
PYTHONPATH=src .venv/bin/python -m tp.dataset  data/processed/g0/m0
PYTHONPATH=src .venv/bin/python -m tp.train    data/processed/g0/m0
PYTHONPATH=src .venv/bin/python -m tp.evaluate data/processed/g0/m0 --mimicry data/processed/g0/m0.5 data/processed/g0/m1
.venv/bin/python scripts/make_report.py
```

The data recipe and SHA-256 of every generated file are in [`data/SOURCES.md`](data/SOURCES.md). Trained models (`artifacts/models/`) and all metrics (`artifacts/*.json`) are committed.

## Repository map

```
src/tp/        sim (data generator) · features (point-in-time state) · dataset · train · evaluate · metrics · demo
tests/         48 leakage, determinism and pipeline tests
docs/lab/      scenario spec, data contract, experiment protocol, deviations log
artifacts/     frozen manifest, trained models, test results
reports/       lab report and rehearsal validation
DECISIONS.md   design decision log
```

## Limits

Every number here measures **learnability on synthetic data, not production fraud accuracy**. Real accuracy, and above all the real false-alarm burden on honest customers, needs a shadow test on pseudonymized bank data. The pilot data request is spelled out in `DECISIONS.md`.

## Team

Team Lead (research, data science, pitch): **Athiphat Sunsit**, with Nut, Tawan, Purich and Cheese. NITMX Fintech Bootcamp 2026, Track 1 finalist.
