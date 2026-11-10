#!/usr/bin/env python
"""Independent recomputation for the audit of the SPX close candle scan.

Does NOT import scan.py. Re-implements from the pre-registration text: the D1 panel (pandas pivot), the 41
features + P3, Newey-West (autocovariance form), Holm, BH, Wilson, the option economics and the power
formulas, the 11:49/11:51 placebo and the straddle cross-check. Adds audit-only sensitivities that are
labelled AUDIT_SENSITIVITY (not tests, not pre-registered).

    PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B recompute.py

Writes recompute_out.json next to this file. Single process.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import glob  # noqa: E402
import warnings  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path("/Users/kv15/trading")
DATA = ROOT / "data" / "spx_1549"
SCAN = ROOT / "backtests" / "spx_candle_scan"
OUT = Path(__file__).resolve().parent / "recompute_out.json"

DISC_END, HOLD_START, HOLD_END = "2020-12-31", "2021-01-01", "2026-10-20"
LAG = 5


def k_of(t: str) -> int:
    h, m = t.split(":")
    return (int(h) - 9) * 60 + int(m) - 30


# ---------------------------------------------------------------------------------------------
# data (independent loader: pandas pivot of the whole file, then split by date)
# ---------------------------------------------------------------------------------------------
days = pd.read_csv(DATA / "d1_days.csv", dtype={"date": str})
keep = sorted(days.loc[days["keep"].astype(str).str.lower() == "true", "date"])
sessions = days.loc[days["calendar"] != "nyse_holiday", "date"].tolist()
prev_session = {d: (sessions[i - 1] if i else None) for i, d in enumerate(sessions)}

bars = pd.read_csv(DATA / "d1_usa500_rth_1m.csv.gz", dtype={"date": str, "time_et": str})
bars = bars[bars["date"].isin(set(keep))].copy()
bars["k"] = bars["time_et"].map(k_of)
dates = np.array(keep, dtype=object)
idx = {d: i for i, d in enumerate(keep)}
N = len(keep)
A = {}
for col in ("open", "high", "low", "close"):
    M = np.full((N, 390), np.nan)
    M[bars["date"].map(idx).to_numpy(), bars["k"].to_numpy()] = bars[col].to_numpy(float)
    A[col] = M
O, H, L, C = A["open"], A["high"], A["low"], A["close"]
prevO = np.array([O[idx[prev_session[d]], 0] if prev_session.get(d) in idx else np.nan for d in keep])
prevC = np.array([C[idx[prev_session[d]], 389] if prev_session.get(d) in idx else np.nan for d in keep])


def sgn(x):
    return np.sign(x)


def c1(k):
    return O[:, k], H[:, k], L[:, k], C[:, k]


def c5(s):
    sl = slice(s, s + 5)
    ok = np.isfinite(O[:, sl]).all(1) & np.isfinite(H[:, sl]).all(1) & np.isfinite(L[:, sl]).all(1) & \
        np.isfinite(C[:, sl]).all(1)
    o = np.where(ok, O[:, s], np.nan)
    c = np.where(ok, C[:, s + 4], np.nan)
    h = np.where(ok, np.nanmax(np.where(ok[:, None], H[:, sl], np.nan), 1), np.nan) if ok.any() else o
    lo = np.where(ok, np.nanmin(np.where(ok[:, None], L[:, sl], np.nan), 1), np.nan) if ok.any() else o
    return o, h, lo, c


def nanify(s, *arrs):
    s = s.astype(float)
    bad = np.zeros(len(s), bool)
    for a in arrs:
        bad |= ~np.isfinite(a)
    s[bad] = np.nan
    return s


def strong(o, h, lo, c):
    b, r = c - o, h - lo
    with np.errstate(invalid="ignore"):
        return nanify(np.where((r > 0) & (np.abs(b) >= 0.6 * r), sgn(b), 0.0), o, h, lo, c)


def hammer(o, h, lo, c):
    b, r = c - o, h - lo
    lw = np.minimum(o, c) - lo
    with np.errstate(invalid="ignore"):
        return nanify(np.where((r > 0) & (lw >= 2 * np.abs(b)) & (lw >= 0.6 * r), 1.0, 0.0), o, h, lo, c)


def star(o, h, lo, c):
    b, r = c - o, h - lo
    uw = h - np.maximum(o, c)
    with np.errstate(invalid="ignore"):
        return nanify(np.where((r > 0) & (uw >= 2 * np.abs(b)) & (uw >= 0.6 * r), -1.0, 0.0), o, h, lo, c)


def engulf(pv, cu):
    po, _, _, pc = pv
    co, ch, cl, cc = cu
    with np.errstate(invalid="ignore"):
        bull = (pc < po) & (cc > co) & (co <= pc) & (cc >= po)
        bear = (pc > po) & (cc < co) & (co >= pc) & (cc <= po)
    return nanify(bull.astype(float) - bear.astype(float), po, pc, co, ch, cl, cc)


def big(cu, last):
    o, h, lo, c = cu
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(H[:, :last + 1] - L[:, :last + 1], 1)
        s = np.where(np.abs(c - o) >= 2 * med, sgn(c - o), 0.0)
    return nanify(s, o, h, lo, c, med)


def clv(k):
    p = O[:, k]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        hi = np.fmax(np.nanmax(H[:, :k], 1), p)
        lo = np.fmin(np.nanmin(L[:, :k], 1), p)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(hi > lo, sgn((p - lo) / (hi - lo) - 0.5), 0.0)
    return nanify(s, p, hi, lo)


E49, E51 = "15:49", "15:51"
feats = {}
for k in range(k_of("15:30"), k_of("15:50") + 1):
    t = f"{(k + 570) // 60:02d}:{(k + 570) % 60:02d}"
    feats[f"F1_1m_{t}"] = (sgn(C[:, k] - O[:, k]), E49 if k <= k_of("15:48") else E51)
K50, K49, K45, K40 = k_of("15:50"), k_of("15:49"), k_of("15:45"), k_of("15:40")
cur1, prv1 = c1(K50), c1(K49)
cur5, prv5 = c5(K45), c5(K40)
for lab, cu, pv, last in (("1m_1550", cur1, prv1, K50), ("5m_1545", cur5, prv5, K49)):
    feats[f"F2_{lab}_strong_body"] = (strong(*cu), E51)
    feats[f"F2_{lab}_hammer"] = (hammer(*cu), E51)
    feats[f"F2_{lab}_shooting_star"] = (star(*cu), E51)
    feats[f"F2_{lab}_engulfing"] = (engulf(pv, cu), E51)
    feats[f"F2_{lab}_big_candle"] = (big(cu, last), E51)
for s in range(k_of("15:20"), k_of("15:45") + 1, 5):
    o, _, _, c = c5(s)
    t = f"{(s + 570) // 60:02d}:{(s + 570) % 60:02d}"
    feats[f"F3_5m_{t}"] = (sgn(c - o), E49 if s + 4 <= k_of("15:48") else E51)
feats["F4_clv"] = (clv(K49), E49)
feats["F4_open_gap"] = (sgn(O[:, 0] - prevC), E49)
feats["F4_prior_day_candle"] = (sgn(prevC - prevO), E49)
with np.errstate(divide="ignore", invalid="ignore"):
    feats["F4_day_so_far"] = (sgn(np.log(O[:, K49] / O[:, 0])), E49)
    P3 = sgn(np.log(O[:, k_of("15:51")] / O[:, K50]))
assert len(feats) == 41


def tgt(entry, end="15:59", shift=0):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(C[:, k_of(end) + shift] / O[:, k_of(entry) + shift])


# ---------------------------------------------------------------------------------------------
# statistics (independent forms)
# ---------------------------------------------------------------------------------------------
def nw_t(y, lag=LAG):
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    n = len(y)
    e = y - y.mean()
    gam = [np.dot(e[j:], e[:n - j]) / n for j in range(lag + 1)]
    lrv = gam[0] + 2 * sum((1 - j / (lag + 1)) * gam[j] for j in range(1, lag + 1))
    se = math.sqrt(lrv / n)
    return float(y.mean()), float(se), float(y.mean() / se), n


def phi_sf(x):
    return 0.5 * math.erfc(x / math.sqrt(2))


def bh(p):
    p = np.asarray(p, float)
    m = len(p)
    o = np.argsort(p)
    q_sorted = np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]
    q = np.empty(m)
    q[o] = np.minimum(q_sorted, 1)
    return q


def holm(p):
    p = np.asarray(p, float)
    m = len(p)
    o = np.argsort(p)
    adj_sorted = np.maximum.accumulate(np.minimum((m - np.arange(m)) * p[o], 1))
    out = np.empty(m)
    out[o] = adj_sorted
    return out


def wilson(k, n, z=1.959963984540054):
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    hw = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return [c - hw, c + hw]


def stats(sig, t, mask, dirn=1):
    s = dirn * sig[mask]
    tt = t[mask]
    y = s * tt * 1e4
    ok = np.isfinite(y)
    mu, se, tv, n = nw_t(y[ok])
    tr = ok & (s != 0)
    nz = tr & (tt != 0)
    k = int((y[nz] > 0).sum())
    return {"n": n, "mean_bps_per_day": mu, "nw_t": tv, "n_trades": int(tr.sum()), "n_hit_days": int(nz.sum()),
            "hits": k, "hit_rate": k / nz.sum(), "wilson95": wilson(k, int(nz.sum())),
            "mean_bps_per_trade": float(y[tr].mean()), "sd_bps_per_trade": float(y[tr].std(ddof=1))}


disc = dates <= DISC_END
hold = (dates >= HOLD_START) & (dates <= HOLD_END)
late = dates >= "2023-01-01"
res = {"data": {"n_disc": int(disc.sum()), "n_hold": int(hold.sum()), "first": keep[0], "last": keep[-1]}}

# 1. discovery: all 41, |t| >= 2.5, BH
rows = {}
for fid, (s, e) in feats.items():
    rows[fid] = stats(s, tgt(e), disc)
p2 = [2 * phi_sf(abs(r["nw_t"])) for r in rows.values()]
q = bh(p2)
for (fid, r), qq in zip(rows.items(), q):
    r["bh_q"] = float(qq)
scan_disc = {r["feature"]: r for r in json.loads((SCAN / "discovery.json").read_text())["features"]}
res["discovery"] = {
    "n_abs_t_ge_2.5": sum(abs(r["nw_t"]) >= 2.5 for r in rows.values()),
    "candidates_by_abs_t": sorted([(f, r["nw_t"]) for f, r in rows.items() if abs(r["nw_t"]) >= 2.5],
                                  key=lambda x: -abs(x[1])),
    "n_bh_q_lt_0.05": int((q < 0.05).sum()), "n_bh_q_lt_0.10": int((q < 0.10).sum()),
    "max_abs_t_diff_vs_scan": max(abs(rows[f]["nw_t"] - scan_disc[f]["nw_t"]) for f in rows),
    "max_abs_q_diff_vs_scan": max(abs(rows[f]["bh_q"] - scan_disc[f]["bh_q"]) for f in rows),
    "max_abs_hit_diff_vs_scan": max(abs(rows[f]["hit_rate"] - scan_disc[f]["hit_rate"]) for f in rows),
    "p3_reference": stats(P3, tgt(E51), disc),
    "selected": {f: rows[f] for f in ("F2_1m_1550_strong_body", "F1_1m_15:50", "F4_day_so_far")},
}
agree = {}
for f in ("F2_1m_1550_strong_body", "F1_1m_15:50", "F4_day_so_far"):
    s = feats[f][0]
    m = disc & np.isfinite(s) & np.isfinite(P3) & (s != 0)
    agree[f] = float((sgn(s[m]) == sgn(P3[m])).mean())
res["discovery"]["agreement_with_P3_sign"] = agree

# 2. holdout: frozen candidates, one-sided, Holm
cands = [("F2_1m_1550_strong_body", 1), ("F1_1m_15:50", 1), ("F4_day_so_far", 1)]
hrows = {f: stats(feats[f][0], tgt(feats[f][1]), hold, d) for f, d in cands}
p1 = [phi_sf(hrows[f]["nw_t"]) for f, _ in cands]
for (f, _), pp, hh in zip(cands, p1, holm(p1)):
    hrows[f]["p_one_sided"] = pp
    hrows[f]["p_holm"] = float(hh)
res["holdout"] = hrows
res["holdout_p3_reference"] = stats(P3, tgt(E51), hold)


# 3. economics (pre-registered break-even) + audit identity and option-P&L test
def econ(sig, entry, mask, dirn=1, level=None, half_spread=0.10, fee=0.09):
    s = dirn * sig
    o, cl = O[:, k_of(entry)], C[:, 389]
    tr = mask & np.isfinite(s) & np.isfinite(o) & np.isfinite(cl) & (s != 0)
    m = (cl - o)[tr] if level is None else (cl / o - 1)[tr] * level
    st = s[tr]
    am = np.abs(m)
    corr = st * m > 0
    cost = 0.5 * am.mean() + half_spread + fee / 100
    pnl = 100 * (np.where(corr, am, 0) - cost)
    p = corr.mean()
    out = {"n": int(tr.sum()), "E_all": float(am.mean()), "E_correct": float(am[corr].mean()),
           "E_wrong": float(am[~corr].mean()), "cost_pts": float(cost),
           "breakeven": float(cost / am[corr].mean()), "breakeven_size_neutral": float(cost / am.mean()),
           "hit_incl_zero_moves": float(p),
           "mean_pnl_usd": float(pnl.mean()), "sd_pnl_usd": float(pnl.std(ddof=1)),
           "t_pnl_iid": float(pnl.mean() / (pnl.std(ddof=1) / math.sqrt(len(pnl)))),
           "identity_check_0.5_signed_move_minus_costs_usd": float(100 * (0.5 * (st * m).mean() - half_spread - fee / 100)),
           "mean_signed_move_pts": float((st * m).mean())}
    # NW t of the option P&L on the per-trade series in date order
    out["t_pnl_nw5"] = nw_t(pnl)[2]
    return out


def n_mean(mu, sd, za=1.6448536269514722, zb=0.8416212335729143):
    return math.ceil(((za + zb) * sd / mu) ** 2)


def n_prop(p, p0, za=1.6448536269514722, zb=0.8416212335729143):
    return math.ceil(((za * math.sqrt(p0 * (1 - p0)) + zb * math.sqrt(p * (1 - p))) / (p - p0)) ** 2)


sb, sbe = feats["F2_1m_1550_strong_body"]
ec = econ(sb, sbe, hold)
ec_lvl = econ(sb, sbe, hold, level=float(O[-1, K49]))
h = hrows["F2_1m_1550_strong_body"]
res["economics_strong_body"] = {
    "holdout_points": ec, "at_last_level": ec_lvl, "last_level": float(O[-1, K49]),
    "accurate_ci_lower_gt_breakeven": h["wilson95"][0] > ec["breakeven"],
    "accurate_ci_lower_gt_size_neutral_breakeven": h["wilson95"][0] > ec["breakeven_size_neutral"],
    "trades_needed": {"mean_return": n_mean(h["mean_bps_per_trade"], h["sd_bps_per_trade"]),
                      "hit_vs_50": n_prop(h["hit_rate"], 0.5),
                      "hit_vs_breakeven": n_prop(h["hit_rate"], ec["breakeven"]),
                      "AUDIT_hit_vs_size_neutral_breakeven": n_prop(h["hit_rate"], ec["breakeven_size_neutral"]),
                      "option_pnl": n_mean(ec["mean_pnl_usd"], ec["sd_pnl_usd"])},
    "trades_per_year": h["n_trades"] / hold.sum() * 252,
}
tpy = res["economics_strong_body"]["trades_per_year"]
res["economics_strong_body"]["years_needed"] = {k: v / tpy for k, v in res["economics_strong_body"]["trades_needed"].items()}
f1, f1e = feats["F1_1m_15:50"]
res["economics_F1_1550"] = econ(f1, f1e, hold)
# AUDIT_SENSITIVITY: break-even with E_correct/E_all taken from DISCOVERY (not from the holdout itself)
ecd = econ(sb, sbe, disc)
ratio_disc = ecd["E_correct"] / ecd["E_all"]
res["economics_strong_body"]["AUDIT_breakeven_with_discovery_Ec_over_Eall"] = {
    "discovery_Ec_over_Eall": ratio_disc, "holdout_Ec_over_Eall": ec["E_correct"] / ec["E_all"],
    "breakeven": ec["cost_pts"] / (ratio_disc * ec["E_all"])}

# 4. placebo 11:51 (shift -240)
sh = -240
cu = c1(K50 + sh)
pl_strong = strong(*cu)
res["placebo_strong_body_1151"] = {"holdout": stats(pl_strong, tgt(E51, shift=sh), hold),
                                   "discovery": stats(pl_strong, tgt(E51, shift=sh), disc)}

# 5. AUDIT_SENSITIVITY: one-minute execution delay (enter at the 15:52 open)
res["AUDIT_latency_strong_body_enter_1552"] = {
    "holdout": stats(sb, tgt("15:52"), hold), "discovery": stats(sb, tgt("15:52"), disc),
    "holdout_first_minute_only_r1551_open_to_1552_open": stats(
        sb, np.log(O[:, k_of("15:52")] / O[:, k_of("15:51")]), hold)}

# 6. AUDIT: is strong body a sharper form of the 15:50 candle? strong vs weak-body days of F1 15:50
weak = np.isfinite(sb) & (sb == 0) & np.isfinite(f1) & (f1 != 0)
t51 = tgt(E51)
sw = {}
for lab, msk in (("holdout", hold), ("discovery", disc)):
    ys = (sb * t51 * 1e4)[msk & (sb != 0) & np.isfinite(sb)]
    yw = (f1 * t51 * 1e4)[msk & weak]
    se = math.sqrt(ys.var(ddof=1) / len(ys) + yw.var(ddof=1) / len(yw))
    sw[lab] = {"strong_n": len(ys), "strong_mean_bps_per_trade": float(ys.mean()),
               "weak_n": len(yw), "weak_mean_bps_per_trade": float(yw.mean()),
               "weak_hit": float((yw > 0).sum() / (yw != 0).sum()),
               "diff_t_welch_iid": float((ys.mean() - yw.mean()) / se)}
res["AUDIT_strong_vs_weak_body_days"] = sw

# 7. AUDIT: year by year strong body hit rate in the holdout, and 2023-2026
yy = {}
years = np.array([d[:4] for d in dates])
for y in sorted(set(years[hold])):
    yy[y] = {k: v for k, v in stats(sb, t51, hold & (years == y)).items()
             if k in ("n_trades", "hit_rate", "mean_bps_per_trade", "nw_t")}
res["AUDIT_strong_body_by_year_holdout"] = yy
lt = stats(sb, t51, late)
res["late_2023_2026_strong_body"] = lt
res["late_2023_2026_ci_vs_breakevens"] = {
    "ci": lt["wilson95"], "primary_breakeven_holdout": ec["breakeven"],
    "size_neutral_breakeven_holdout": ec["breakeven_size_neutral"],
    "ci_includes_primary_breakeven": lt["wilson95"][0] <= ec["breakeven"],
    "ci_includes_size_neutral_breakeven": lt["wilson95"][0] <= ec["breakeven_size_neutral"],
    "late_own_breakeven": econ(sb, sbe, late)["breakeven"],
    "late_own_breakeven_size_neutral": econ(sb, sbe, late)["breakeven_size_neutral"]}
h2122 = hold & (dates < "2023-01-01")
res["AUDIT_strong_body_2021_2022"] = stats(sb, t51, h2122)
# AUDIT_SENSITIVITY: trades needed if the true edge is the 2023-2026 one (not the full-holdout point estimate)
el = econ(sb, sbe, late)
res["AUDIT_trades_needed_at_2023_2026_effect"] = {
    "mean_return": n_mean(lt["mean_bps_per_trade"], lt["sd_bps_per_trade"]),
    "hit_vs_50": n_prop(lt["hit_rate"], 0.5),
    "hit_vs_own_size_neutral_breakeven": n_prop(lt["hit_rate"], el["breakeven_size_neutral"]),
    "option_pnl": n_mean(el["mean_pnl_usd"], el["sd_pnl_usd"]) if el["mean_pnl_usd"] > 0 else None,
    "late_mean_pnl_usd": el["mean_pnl_usd"], "late_sd_pnl_usd": el["sd_pnl_usd"], "late_t_pnl_iid": el["t_pnl_iid"],
    "trades_per_year": tpy}
res["AUDIT_trades_needed_at_2023_2026_effect"]["years"] = {
    k: (v / tpy if isinstance(v, int) else None) for k, v in res["AUDIT_trades_needed_at_2023_2026_effect"].items()
    if k in ("mean_return", "hit_vs_50", "hit_vs_own_size_neutral_breakeven", "option_pnl")}

# 8. straddle cross-check, recomputed, plus |settle - K| (the straddle's actual payoff)
closes = {}
for f in sorted(glob.glob(str(DATA / "robinhood" / "raw" / "spx_daily_*.json"))):
    for r in json.loads(Path(f).read_text())["data"]["results"]:
        if r.get("symbol") == "SPX" and r.get("interval") == "day":
            for b in r["bars"]:
                if not b.get("interpolated"):
                    closes[b["begins_at"][:10]] = float(b["close_value"])
opt = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str})
                 for f in sorted(glob.glob(str(DATA / "d2_chunk_*_options_10m.csv")))])
opt = opt[(opt["time_et"] == "15:40") & (opt["interpolated"].astype(str).str.lower() != "true")]
spx = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str})
                 for f in sorted(glob.glob(str(DATA / "d2_chunk_*_spx_1m.csv")))])
spx = spx[(spx["time_et"] == "15:49") & (spx["interpolated"].astype(str).str.lower() != "true")]
S1549 = dict(zip(spx["date"], spx["close"].astype(float)))
mk = {(r.date, r.type, float(r.strike)): float(r.close) for r in opt.itertuples()}
xr = []
for d in sorted({k[0] for k in mk}):
    if d not in S1549 or d not in closes:
        continue
    S = S1549[d]
    K = math.floor(S / 5 + 0.5) * 5
    c, p = mk.get((d, "call", K)), mk.get((d, "put", K))
    if c is None or p is None:
        continue
    st = closes[d]
    xr.append({"date": d, "S": S, "K": K, "straddle": c + p, "abs_settle_minus_S": abs(st - S),
               "abs_settle_minus_K": abs(st - K)})
X = pd.DataFrame(xr)
rng = np.random.default_rng(1)
bi = rng.integers(0, len(X), (10000, len(X)))
r_K = X["straddle"].to_numpy()[bi].mean(1) / X["abs_settle_minus_K"].to_numpy()[bi].mean(1)
res["straddle_crosscheck"] = {
    "n_days": len(X),
    "mean_straddle_bps": float((X["straddle"] / X["S"]).mean() * 1e4),
    "mean_abs_settle_minus_S_bps": float((X["abs_settle_minus_S"] / X["S"]).mean() * 1e4),
    "ratio_bps_means_as_scan": float((X["straddle"] / X["S"]).mean() / (X["abs_settle_minus_S"] / X["S"]).mean()),
    "AUDIT_ratio_vs_straddle_payoff_abs_settle_minus_K": float(X["straddle"].mean() / X["abs_settle_minus_K"].mean()),
    "AUDIT_ratio_vs_payoff_boot95": [float(np.quantile(r_K, 0.025)), float(np.quantile(r_K, 0.975))],
    "AUDIT_mean_straddle_minus_payoff_pts": float((X["straddle"] - X["abs_settle_minus_K"]).mean()),
    "AUDIT_median_ratio_daily": float(np.median(X["straddle"] / X["abs_settle_minus_K"].clip(lower=1e-9))),
    "AUDIT_share_days_straddle_gt_payoff": float((X["straddle"] > X["abs_settle_minus_K"]).mean()),
}
for e in (E49, E51):
    r = np.exp(tgt(e)) - 1
    m = hold & np.isfinite(r)
    res["straddle_crosscheck"][f"d1_holdout_mean_abs_move_bps_{e}"] = float(np.abs(r[m]).mean() * 1e4)


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return float(o) if math.isfinite(float(o)) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


OUT.write_text(json.dumps(clean(res), indent=1) + "\n")
print(json.dumps(clean(res), indent=1))
