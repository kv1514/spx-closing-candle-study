"""Independent re-computation for the adversarial audit of the SPX 15:49 study.
Written from the pre-registration text, NOT importing analysis.py. Reads raw/tidy data only.
Run: /Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/audits/audit_recompute.py
Prints JSON to stdout and writes audits/audit_recompute_out.json.
"""
import glob, json, math
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats

ROOT = Path("/Users/kv15/trading"); DATA = ROOT / "data/spx_1549"
OUT = ROOT / "backtests/spx_close_1549/audits/audit_recompute_out.json"
res = {}

def m(hhmm):
    h, mm = map(int, hhmm.split(":")); return h * 60 + mm - 570

# ---------------- D1 -------------------------------------------------------------------------
days = pd.read_csv(DATA / "d1_days.csv", dtype={"date": str})
keep = days.loc[days["keep"].astype(bool), "date"].tolist()
b = pd.read_csv(DATA / "d1_usa500_rth_1m.csv.gz", dtype={"date": str, "time_et": str})
b = b[b["date"].isin(set(keep))]
b["m"] = b["time_et"].map(m)
O = b.pivot(index="date", columns="m", values="open").reindex(columns=range(390))
C = b.pivot(index="date", columns="m", values="close").reindex(columns=range(390))
dates = O.index.to_numpy(); Ov = O.to_numpy(); Cv = C.to_numpy()
res["d1_n_days"] = len(dates)

rc = np.log(Cv[:, m("15:59")] / Ov[:, m("15:49")])
r38 = np.log(Cv[:, m("15:48")] / Ov[:, m("15:38")])
win = np.stack([np.log(Cv[:, s + 10] / Ov[:, s]) for s in range(m("10:00"), m("15:38") + 1)], 1)
med = np.nanmedian(np.abs(win), 1)
eps = 1e-5
for name, base in (("a_1538", np.abs(r38)), ("b_median", med)):
    x = np.log(np.abs(rc) + eps) - np.log(base + eps); x = x[np.isfinite(x)]
    t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))
    res[f"H1_{name}"] = {"n": len(x), "mean_log_diff": x.mean(), "t": t,
                         "mean_abs_rclose_bps": np.nanmean(np.abs(rc)) * 1e4, "mean_base_bps": np.nanmean(base) * 1e4}

def nw(y, L=5):
    y = y[np.isfinite(y)]; n = len(y); e = y - y.mean()
    g = [e @ e / n] + [e[k:] @ e[:-k] / n for k in range(1, L + 1)]
    v = g[0] + 2 * sum((1 - k / (L + 1)) * g[k] for k in range(1, L + 1))
    se = math.sqrt(v / n); t = y.mean() / se
    return {"n": n, "mean_bps": y.mean(), "t": t, "p": 2 * stats.norm.sf(abs(t))}

o = lambda t: Ov[:, m(t)]
tgt_close = np.log(Cv[:, m("15:59")] / o("15:49")) * 1e4
tgt_1551 = np.log(Cv[:, m("15:59")] / o("15:51")) * 1e4
P = {"P1": (np.sign(np.log(o("15:49") / o("09:30"))), tgt_close),
     "P2": (np.sign(np.log(o("15:49") / o("15:19"))), tgt_close),
     "P3": (np.sign(np.log(o("15:51") / o("15:50"))), tgt_1551),
     "P4": (np.sign(np.log(o("10:00") / o("09:30"))), tgt_close)}
h2 = {k: nw(s * y) for k, (s, y) in P.items()}
ps = np.array([h2[k]["p"] for k in P]); order = np.argsort(ps); adj = np.empty(4); run = 0
for r, i in enumerate(order):
    run = max(run, min(1, (4 - r) * ps[i])); adj[i] = run
for k, a in zip(P, adj):
    h2[k]["holm"] = a
s3, y3 = P["P3"]
for lab, lo, hi in (("2013-2019", "0000", "2019-12-31"), ("2020-2022", "2020-01-01", "2022-12-31"), ("2023-2026", "2023-01-01", "9999")):
    mk = (dates >= lo) & (dates <= hi)
    h2[f"P3_{lab}"] = nw((s3 * y3)[mk])
res["H2"] = h2

# placebo: the P3 construction at every other minute of the day (signal = sign of one-minute open-to-open
# change at minute k -> k+1, target = open k+1 -> close k+9, same 9-bar horizon as 15:51 -> 15:59)
plac = {}
for k in range(m("10:00"), m("15:41") + 1):
    sgn = np.sign(np.log(Ov[:, k + 1] / Ov[:, k])); y = np.log(Cv[:, k + 9] / Ov[:, k + 1]) * 1e4
    r = nw(sgn * y); plac[k] = (r["mean_bps"], r["t"])
tt = np.array([v[1] for v in plac.values()]); mm_ = np.array([v[0] for v in plac.values()])
res["P3_placebo_other_minutes"] = {"n_minutes": len(tt), "median_t": float(np.median(tt)), "mean_t": float(tt.mean()),
    "share_t_gt_2": float((tt > 2).mean()), "share_t_lt_-2": float((tt < -2).mean()), "mean_of_means_bps": float(mm_.mean()),
    "max_t": float(tt.max()), "rank_of_P3_t_among_all": int((tt >= h2["P3"]["t"]).sum()) + 1}
# placebo restricted to 2023-2026
sel = dates >= "2023-01-01"; tt2 = []
for k in range(m("10:00"), m("15:41") + 1):
    sgn = np.sign(np.log(Ov[sel, k + 1] / Ov[sel, k])); y = np.log(Cv[sel, k + 9] / Ov[sel, k + 1]) * 1e4
    tt2.append(nw(sgn * y)["t"])
tt2 = np.array(tt2)
res["P3_placebo_2023_2026"] = {"median_t": float(np.median(tt2)), "share_t_gt_2": float((tt2 > 2).mean()), "share_t_lt_-2": float((tt2 < -2).mean())}

# DST check: US/EU mismatch weeks (US DST on, EU not yet / EU off, US still on)
def mismatch(d):
    d = pd.Timestamp(d); y = d.year
    us_on = pd.Timestamp(f"{y}-03-01") + pd.offsets.Week(weekday=6) * 2  # 2nd Sunday March
    us_on = pd.Timestamp(y, 3, 8) + pd.Timedelta(days=(6 - pd.Timestamp(y, 3, 8).weekday()) % 7)
    eu_on = pd.Timestamp(y, 3, 31) - pd.Timedelta(days=(pd.Timestamp(y, 3, 31).weekday() + 1) % 7)
    eu_off = pd.Timestamp(y, 10, 31) - pd.Timedelta(days=(pd.Timestamp(y, 10, 31).weekday() + 1) % 7)
    us_off = pd.Timestamp(y, 11, 1) + pd.Timedelta(days=(6 - pd.Timestamp(y, 11, 1).weekday()) % 7)
    return (us_on <= d < eu_on) or (eu_off <= d < us_off)
mis = np.array([mismatch(d) for d in dates])
absr = np.abs(np.log(Cv[:, 1:] / Cv[:, :-1])) * 1e4  # column j = bar j+1
def prof(mask):
    p = np.nanmean(absr[mask], 0); ref = np.nanmedian(p[m("10:00") - 1:m("15:30") - 1])
    top = [(int(j + 1), round(float(p[j] / ref), 2)) for j in np.argsort(-p)[:4]]
    lab = lambda k: f"{(570 + k) // 60:02d}:{(570 + k) % 60:02d}"
    return {"n_days": int(mask.sum()), "top_bars": [(lab(k), v) for k, v in top],
            "x_1550": round(float(p[m('15:50') - 1] / ref), 2), "x_1000": round(float(p[m('10:00') - 1] / ref), 2)}
res["DST_mismatch_weeks_profile"] = prof(mis & (dates >= "2017-01-01"))
res["DST_other_days_profile"] = prof(~mis & (dates >= "2017-01-01"))
res["profile_2013_2016"] = prof(dates < "2017-01-01")

# implied vs realized regression (2023+), and a version fitted only on days before the D2 window
rv = np.sqrt(np.nansum(np.log(Ov[:, 1:m("15:49") + 1] / Ov[:, :m("15:49")]) ** 2, 1) * m("15:49") /
             np.isfinite(np.log(Ov[:, 1:m("15:49") + 1] / Ov[:, :m("15:49")])).sum(1))
absmove = np.abs(np.exp(rc) - 1)
def fit(mask):
    mk = mask & np.isfinite(rv) & np.isfinite(absmove)
    bb, aa = np.polyfit(rv[mk], absmove[mk], 1); return aa, bb, int(mk.sum())
i1020 = int(np.where(dates == "2026-10-20")[0][0])
a1, b1, n1 = fit(dates >= "2023-01-01")
a2, b2, n2 = fit((dates >= "2023-01-01") & (dates < "2026-09-21"))
S0 = 7710.93; imp = 5.90
res["IVR"] = {"fit_all": {"a": a1, "b": b1, "n": n1, "pred_pts_1020": (a1 + b1 * rv[i1020]) * S0},
              "fit_pre_D2_window": {"a": a2, "b": b2, "n": n2, "pred_pts_1020": (a2 + b2 * rv[i1020]) * S0},
              "rv_1020_bps": rv[i1020] * 1e4, "implied": imp}
win22 = (dates >= "2026-09-21") & (dates <= "2026-10-20")
res["IVR"]["d2_window_D1"] = {"n": int(win22.sum()), "mean_abs_rclose_bps": float(np.nanmean(np.abs(rc[win22])) * 1e4),
                              "mean_pred_regression_bps": float(np.nanmean(a1 + b1 * rv[win22]) * 1e4),
                              "mean_rv_bps": float(np.nanmean(rv[win22]) * 1e4)}

# ---------------- D2 -------------------------------------------------------------------------
spx = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str}) for f in sorted(glob.glob(str(DATA / "d2_chunk_*_spx_1m.csv")))])
spx = spx[~spx["interpolated"].astype(str).str.lower().eq("true")]
opt = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str}) for f in sorted(glob.glob(str(DATA / "d2_chunk_*_options_1m.csv")))])
res["d2_option_bars"] = {"total": len(opt), "interpolated": int(opt["interpolated"].astype(str).str.lower().eq("true").sum())}
opt = opt[~opt["interpolated"].astype(str).str.lower().eq("true")]
res["d2_days_with_real_option_bars"] = sorted(opt["date"].unique().tolist())
daily = {}
for f in sorted(glob.glob(str(DATA / "robinhood/raw/spx_daily_*.json"))):
    for r_ in json.load(open(f))["data"]["results"]:
        for bar in r_["bars"]:
            if not bar.get("interpolated"):
                daily.setdefault(bar["begins_at"][:10], set()).add(float(bar["close_value"]))
res["daily_close_conflicts"] = {d: sorted(v) for d, v in daily.items() if len(v) > 1}
settle = {d: min(v) for d, v in daily.items()}
D = "2026-10-20"
sd = spx[spx["date"] == D].set_index("time_et")
od = opt[opt["date"] == D]
q = lambda kind, k, t, f="open": float(od[(od["type"] == kind) & (od["strike"] == k) & (od["time_et"] == t)][f].iloc[0])
s0 = float(sd.loc["15:49", "open"]); K0 = 5 * math.floor(s0 / 5 + 0.5); ST = settle[D]
c, p = q("call", K0, "15:49"), q("put", K0, "15:49")
hs, fee = 0.10, 0.09
S1 = 100 * (max(ST - K0, 0) + max(K0 - ST, 0) - (c + p + 2 * hs)) - 2 * fee
p3 = np.sign(sd.loc["15:51", "open"] - sd.loc["15:50", "open"])
s51 = float(sd.loc["15:51", "open"]); K2 = 5 * math.floor(s51 / 5 + 0.5)
kind = "call" if p3 > 0 else "put"; m2 = q(kind, K2, "15:51")
S2 = 100 * ((max(ST - K2, 0) if kind == "call" else max(K2 - ST, 0)) - (m2 + hs)) - fee
legs = {}
for kind3, k3 in (("call", K0 + 5), ("put", K0 - 5)):
    mk3 = q(kind3, k3, "15:49")
    closes = od[(od["type"] == kind3) & (od["strike"] == k3)].set_index("time_et")["close"].loc["15:49":"15:58"]
    hit = bool((closes >= 2 * mk3).any())
    val = (2 * mk3 - hs) if hit else (max(ST - k3, 0) if kind3 == "call" else max(k3 - ST, 0))
    legs[kind3] = {"strike": k3, "mark": mk3, "max_close": float(closes.max()), "hit2x": hit,
                   "pnl": 100 * (val - (mk3 + hs)) - fee * (2 if hit else 1)}
res["D2_1020"] = {"S0": s0, "K0": K0, "settle": ST, "call": c, "put": p, "S1_usd": S1, "P3_sign": p3, "S2_kind": kind,
                  "S2_strike": K2, "S2_mark": m2, "S2_usd": S2, "S3_legs": legs, "S3_usd": sum(v["pnl"] for v in legs.values())}

# put-call parity alignment on 10-20: option-implied index (K + C - P, median over strikes) vs SPX opens at lags
piv = od.pivot_table(index=["time_et"], columns=["type", "strike"], values="open")
strikes = sorted(set(od["strike"]))
impl = pd.Series({t: np.nanmedian([k + piv.loc[t, ("call", k)] - piv.loc[t, ("put", k)] for k in strikes
                                   if abs(k - K0) <= 15]) for t in piv.index})
spx_open = sd["open"]
times = [t for t in impl.index if "10:00" <= t <= "15:58"]
lagres = {}
for L in range(-3, 4):  # compare option-implied at t with SPX open at t+L
    idx = spx_open.index.tolist()
    diffs = []
    for t in times:
        j = idx.index(t) + L if t in idx else None
        if j is not None and 0 <= j < len(idx):
            diffs.append(impl[t] - spx_open.iloc[j])
    d = np.array(diffs)
    lagres[L] = {"mean_dev": float(d.mean()), "mean_abs_dev": float(np.abs(d).mean())}
res["parity_lag_1020"] = {"implied_minus_spx_open_at_t_plus_L": lagres,
                          "at_1549": {"implied": float(impl["15:49"]), "spx_open_1549": s0,
                                      "spx_close_1548": float(sd.loc["15:48", "close"]), "spx_open_1548": float(sd.loc["15:48", "open"]),
                                      "spx_open_1550": float(sd.loc["15:50", "open"])}}
# change-based alignment (robust to a constant basis)
di = impl.loc[times].diff().dropna()
cl = {}
for L in range(-3, 4):
    s_ = spx_open.diff().shift(-L).reindex(di.index)
    k_ = pd.concat([di, s_], axis=1).dropna()
    cl[L] = float(np.corrcoef(k_.iloc[:, 0], k_.iloc[:, 1])[0, 1])
res["parity_lag_1020"]["corr_changes_by_L"] = cl

# (iii) 15:59 close -> official close
g = []
for d0, grp in spx.groupby("date"):
    gg = grp.set_index("time_et")
    if "15:59" in gg.index and d0 in settle:
        g.append(math.log(settle[d0] / gg.loc["15:59", "close"]) * 1e4)
g = np.array(g); res["iii_gap"] = {"n": len(g), "mean_bps": g.mean(), "mean_abs_bps": np.abs(g).mean(), "max_abs": np.abs(g).max()}

# D1 vs D2 SPX: P3 sign agreement and r_close magnitude on overlap days
agree, n_ = 0, 0; rows = []
for d0, grp in spx.groupby("date"):
    gg = grp.set_index("time_et")
    if d0 in O.index and all(t in gg.index for t in ("15:50", "15:51", "15:49", "15:59")):
        i = int(np.where(dates == d0)[0][0])
        sd1 = np.sign(Ov[i, m("15:51")] - Ov[i, m("15:50")]); sd2 = np.sign(gg.loc["15:51", "open"] - gg.loc["15:50", "open"])
        n_ += 1; agree += int(sd1 == sd2); rows.append((d0, int(sd1), int(sd2)))
res["P3_sign_agreement_D1_vs_RH_SPX"] = {"n": n_, "agree": agree, "rows": rows}

def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, np.bool_): return bool(o)
    return o
OUT.write_text(json.dumps(clean(res), indent=1))
print(json.dumps(clean(res), indent=1))
