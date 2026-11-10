#!/usr/bin/env python
"""Extra audit checks (independent of scan.py): bar labelling, DST, and the straddle-markup tipping points.

    PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B recompute_extra.py

1. Bar labelling: correlate D1 (Dukascopy CFD) one-minute close-to-close returns with Robinhood SPX one-minute
   returns on the overlapping days at lags -1, 0, +1 minutes. Left-labelled bars on both sides => lag 0 wins.
2. DST: mean |ln(C/O)| per bar 15:44..15:56 for EST months (Jan-Feb, Nov 15-Dec) vs EDT months (Jun-Aug).
   The 15:50 imbalance spike must sit on the 15:50 bar in both (an hour shift would move it off the window).
3. Markup tipping points for F2_1m_1550_strong_body in the holdout: the straddle markup over the realized-
   move-fair price at which (a) the pre-registered break-even reaches the hit-rate CI lower bound and (b) the
   mean option P&L reaches 0. AUDIT_SENSITIVITY, not a test.
Writes recompute_extra_out.json.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import glob  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DATA = Path("/Users/kv15/trading/data/spx_1549")
OUT = Path(__file__).resolve().parent / "recompute_extra_out.json"
res = {}

d1 = pd.read_csv(DATA / "d1_usa500_rth_1m.csv.gz", dtype={"date": str, "time_et": str})
days = pd.read_csv(DATA / "d1_days.csv", dtype={"date": str})
keep = set(days.loc[days["keep"].astype(str).str.lower() == "true", "date"])
d1 = d1[d1["date"].isin(keep)]

# 1. labelling vs Robinhood SPX
spx = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str})
                 for f in sorted(glob.glob(str(DATA / "d2_chunk_*_spx_1m.csv")))]).drop_duplicates(["date", "time_et"])
spx = spx[spx["interpolated"].astype(str).str.lower() != "true"]
common = sorted(set(spx["date"]) & set(d1["date"]))


def piv(df):
    p = df.pivot(index="date", columns="time_et", values="close").reindex(common)
    return p.reindex(columns=sorted(p.columns))


A = piv(d1[d1["date"].isin(common)])
B = piv(spx[spx["date"].isin(common)])
cols = [c for c in A.columns if c in B.columns]
ra = np.log(A[cols]).diff(axis=1).to_numpy()
rb = np.log(B[cols]).diff(axis=1).to_numpy()
lags = {}
for lag in (-1, 0, 1):
    if lag >= 0:
        x, y = ra[:, 1 + lag:], rb[:, 1:rb.shape[1] - lag]
    else:
        x, y = ra[:, 1:ra.shape[1] + lag], rb[:, 1 - lag:]
    m = np.isfinite(x) & np.isfinite(y)
    lags[str(lag)] = float(np.corrcoef(x[m], y[m])[0, 1])
res["labelling_corr_d1_vs_rh_spx_1m_returns_by_lag"] = {"n_days": len(common), "first": common[0] if common else None,
                                                         "last": common[-1] if common else None, "corr": lags,
                                                         "how_to_read": "lag +1 = D1 return of bar t+1 vs SPX bar t"}

# 2. DST check
d1["month"] = d1["date"].str[5:7].astype(int)
d1["md"] = d1["date"].str[5:]
d1["absr"] = np.abs(np.log(d1["close"] / d1["open"])) * 1e4
win = [f"15:{m:02d}" for m in range(44, 57)]
est = d1[(d1["month"].isin([1, 2])) | (d1["md"] >= "11-15")]
edt = d1[d1["month"].isin([6, 7, 8])]
prof = {}
for lab, df in (("EST_jan_feb_midnov_dec", est), ("EDT_jun_aug", edt)):
    g = df[df["time_et"].isin(win)].groupby("time_et")["absr"].mean()
    prof[lab] = {t: float(g[t]) for t in win}
    prof[lab]["argmax"] = max(win, key=lambda t: g[t])
res["dst_mean_abs_bar_return_bps_15_44_to_15_56"] = prof

# 3. markup tipping points (inputs from the audit recompute)
rc = json.loads((Path(__file__).resolve().parent / "recompute_out.json").read_text())
ec = rc["economics_strong_body"]["holdout_points"]
h = rc["holdout"]["F2_1m_1550_strong_body"]
extra = 0.10 + 0.09 / 100
lo = h["wilson95"][0]
res["markup_tipping_points_strong_body_holdout"] = {
    "AUDIT_SENSITIVITY": True,
    "markup_where_breakeven_equals_ci_lower": (lo * ec["E_correct"] - extra) / (0.5 * ec["E_all"]),
    "markup_where_mean_option_pnl_is_zero": (h["hit_rate"] * ec["E_correct"] - extra) / (0.5 * ec["E_all"]),
    "breakeven_at_markup_1.10": (0.5 * 1.10 * ec["E_all"] + extra) / ec["E_correct"],
    "ci_lower": lo, "hit_rate": h["hit_rate"]}
OUT.write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res, indent=1))

# 4. AUDIT: does the D1 CFD target track the SPX settlement target on the overlapping Robinhood days?
#    D1 r(15:51 open -> 15:59 close) vs SPX r(15:51 open -> official settle) and vs SPX r(15:51 open -> 15:59 close).
closes = {}
for f in sorted(glob.glob(str(DATA / "robinhood" / "raw" / "spx_daily_*.json"))):
    for r in json.loads(Path(f).read_text())["data"]["results"]:
        if r.get("symbol") == "SPX" and r.get("interval") == "day":
            for b in r["bars"]:
                if not b.get("interpolated"):
                    closes[b["begins_at"][:10]] = float(b["close_value"])
po = d1.pivot(index="date", columns="time_et", values="open")
pc = d1.pivot(index="date", columns="time_et", values="close")
so = spx.pivot(index="date", columns="time_et", values="open")
sc = spx.pivot(index="date", columns="time_et", values="close")
rows = []
for d in common:
    try:
        a = math.log(pc.loc[d, "15:59"] / po.loc[d, "15:51"])
        b = math.log(closes[d] / so.loc[d, "15:51"])
        c = math.log(sc.loc[d, "15:59"] / so.loc[d, "15:51"])
        s50 = np.sign(pc.loc[d, "15:50"] - po.loc[d, "15:50"])
        x50 = np.sign(sc.loc[d, "15:50"] - so.loc[d, "15:50"])
    except (KeyError, TypeError):
        continue
    if not all(map(math.isfinite, (a, b, c))):
        continue
    rows.append((d, a * 1e4, b * 1e4, c * 1e4, s50, x50))
R = np.array([r[1:] for r in rows], float)
res["AUDIT_d1_target_vs_spx_settlement_target"] = {
    "n_days": len(rows),
    "corr_d1_vs_spx_settle": float(np.corrcoef(R[:, 0], R[:, 1])[0, 1]),
    "corr_d1_vs_spx_1559_close": float(np.corrcoef(R[:, 0], R[:, 2])[0, 1]),
    "sign_agreement_d1_vs_spx_settle": float((np.sign(R[:, 0]) == np.sign(R[:, 1])).mean()),
    "sign_agreement_d1_vs_spx_1559_close": float((np.sign(R[:, 0]) == np.sign(R[:, 2])).mean()),
    "mean_abs_d1_bps": float(np.abs(R[:, 0]).mean()), "mean_abs_spx_settle_bps": float(np.abs(R[:, 1]).mean()),
    "mean_abs_diff_d1_minus_spx_settle_bps": float(np.abs(R[:, 0] - R[:, 1]).mean()),
    "sign_agreement_1550_candle_d1_vs_spx": float((R[:, 3] == R[:, 4]).mean()),
    "rows_date_d1bps_spxsettlebps_spx1559bps": [[r[0], round(r[1], 2), round(r[2], 2), round(r[3], 2)] for r in rows]}
OUT.write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res["AUDIT_d1_target_vs_spx_settlement_target"], indent=1))

# 5. AUDIT_SENSITIVITY: CFD hit rate mapped to the settlement if sign disagreements were unrelated to the signal
a = res["AUDIT_d1_target_vs_spx_settlement_target"]["sign_agreement_d1_vs_spx_settle"]
hr = rc["holdout"]["F2_1m_1550_strong_body"]
res["AUDIT_hit_rate_mapped_to_settlement_if_disagreement_random"] = {
    "sign_agreement": a,
    "hit_rate": hr["hit_rate"] * a + (1 - hr["hit_rate"]) * (1 - a),
    "ci_lower": hr["wilson95"][0] * a + (1 - hr["wilson95"][0]) * (1 - a)}
OUT.write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res["AUDIT_hit_rate_mapped_to_settlement_if_disagreement_random"], indent=1))
