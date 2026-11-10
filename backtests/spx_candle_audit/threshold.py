"""Part C of the audit: how sure can anyone be about the body threshold? Descriptive; same 2021-2026 days the
rule was already confirmed on, so nothing here is a fresh test.

Run from the repository root:
  .venv/bin/python -I backtests/spx_candle_audit/threshold.py CACHE.pkl OUT.json
"""
import json, math, pickle, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as A

GRID = [round(0.05 * i, 2) for i in range(0, 20)]          # 0.00 .. 0.95
BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, None)]


def day_matrix(table, quotes, lo, hi, off=10, at="ask"):
    cols, dates = [], None
    for th in GRID:
        s, d, _ = A.pnl_series(table, quotes, th, off=off, lo=lo, hi=hi, at=at)
        cols.append(s)
        dates = d
    return np.array(cols).T, dates                       # days x thresholds


def grid_table(table, quotes, lo, hi, off=10):
    out = {}
    for th in GRID:
        s, _, tr = A.pnl_series(table, quotes, th, off=off, lo=lo, hi=hi)
        sm, _, trm = A.pnl_series(table, quotes, th, off=off, lo=lo, hi=hi, at="mid")
        st = A.stats(s, tr)
        st["per_trade_mid"] = A.stats(sm, trm)["per_trade"]
        out[f"{th:.2f}"] = st
    return out


def bucket_table(table, quotes, lo, hi, off=10):
    out = {}
    for a, b in BUCKETS:
        s, _, tr = A.pnl_series(table, quotes, a, b, off=off, lo=lo, hi=hi)
        _, _, trm = A.pnl_series(table, quotes, a, b, off=off, lo=lo, hi=hi, at="mid")
        p = np.array([t["pnl"] for t in tr]); pm = np.array([t["pnl"] for t in trm])
        se = p.std(ddof=1) / math.sqrt(len(p)) if len(p) > 2 else None
        _, _, trx = A.pnl_series(table, quotes, a, b, off=off, lo=lo, hi=hi, test=A.fires_exact)
        px = np.array([t["pnl"] for t in trx])
        out[f"{a:.1f}-{b or 1.0:.1f}"] = {"trades": len(p), "per_trade_ask": float(p.mean()), "se": se,
                                             "t_ordinary": float(p.mean() / se) if se else None, "won": float((p > 0).mean()),
                                             "per_trade_mid": float(pm.mean()),
                                             "exact_decimal_trades": len(px), "exact_decimal_per_trade_ask": float(px.mean())}
    return out


def index_move_by_bucket(cache, lo, hi):
    """The raw signal, no options: the D1 move 15:51 open -> 15:59 close in the candle's direction, in basis points."""
    keep = [r["date"] for r in cache["days"] if r["keep"].strip().lower() == "true" and lo <= r["date"] <= hi]
    rows = []
    for d in keep:
        b = cache["bars"][d]
        cd = A.candle(b)
        if cd is None or cd["sign"] == 0 or not math.isfinite(cd["ratio"]):
            continue
        o, c = b["15:51"][0], b["15:59"][3]
        rows.append((cd, cd["sign"] * 1e4 * math.log(c / o)))
    out = {}
    for name, x, y in (("below_0.60", 0.0, 0.6), ("at_least_0.60", 0.6, None)):
        v = np.array([r for cd, r in rows if A.fires(cd, x, y)])
        out[name] = {"days": len(v), "mean_bps": float(v.mean()), "t": float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))),
                     "t_newey_west_lag5": A.nw(v)["t"], "right_way": float((v > 0).sum() / (v != 0).sum())}
    for x, y in BUCKETS:
        v = np.array([r for cd, r in rows if A.fires(cd, x, y)])
        m = np.ones(len(v), bool)
        out[f"{x:.1f}-{y or 1.0:.1f}"] = {"t_newey_west_lag5": A.nw(v)["t"], "days": int(m.sum()), "mean_bps": float(v.mean()),
                                             "t": float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))),
                                             "right_way": float((v > 0).sum() / (v != 0).sum())}
    return out


def paired_vs_060(M):
    j0 = GRID.index(0.60)
    out = {}
    for j, th in enumerate(GRID):
        if j == j0:
            continue
        d = M[:, j] - M[:, j0]
        r = A.nw(d)
        out[f"{th:.2f}"] = {"per_day_minus_0.60": r["mean"], "t": r["t"]}
    return out


def walk_forward(M, dates, first_test_year=None):
    """Each test year uses the threshold with the highest mean per day on every earlier day in M (never a later one)."""
    years = sorted({d[:4] for d in dates})
    yr = np.array([d[:4] for d in dates])
    j0 = GRID.index(0.60)
    picks = {}
    series_pick, series_fixed = [], []
    for y in (years[1:] if first_test_year is None else [x for x in years if x >= first_test_year]):
        past, now = yr < y, yr == y
        means = np.nanmean(M[past], axis=0)
        j = int(np.nanargmax(means))
        picks[y] = {"picked": GRID[j], "picked_per_day": float(np.nanmean(M[now, j])), "fixed_0.60_per_day": float(np.nanmean(M[now, j0]))}
        series_pick += list(M[now, j]); series_fixed += list(M[now, j0])
    d = np.array(series_pick) - np.array(series_fixed)
    return {"training_starts": dates[0], "by_year": picks, "picked_per_day": float(np.nanmean(series_pick)),
            "fixed_0.60_per_day": float(np.nanmean(series_fixed)), "difference": A.nw(d)}


def bootstrap(M, reps=5000, block=5, seed=20261109):
    rng = np.random.default_rng(seed)
    n = len(M)                                           # unpriced days stay NaN and are left out of every mean
    j0 = GRID.index(0.60)
    nb = math.ceil(n / block)
    j7 = GRID.index(0.70)
    best, gap, m60, pt60, pt70, d70 = [], [], [], [], [], []
    for _ in range(reps):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        S = M[idx]
        mu = np.nanmean(S, axis=0)
        j = int(mu.argmax())
        best.append(GRID[j]); gap.append(mu[j] - mu[j0]); m60.append(mu[j0]); d70.append(mu[j7] - mu[j0])
        pt60.append(np.nansum(S[:, j0]) / max(1, np.nansum(S[:, j0] != 0) - np.isnan(S[:, j0]).sum()))
        pt70.append(np.nansum(S[:, j7]) / max(1, np.nansum(S[:, j7] != 0) - np.isnan(S[:, j7]).sum()))
    best = np.array(best)
    hist = {f"{th:.2f}": float((best == th).mean()) for th in GRID}
    obs = np.nanmean(M, axis=0)
    return {"note": "Shares describe how unstable the best threshold is on this sample. They are not the probability "
                    "that a threshold is truly best, and blocks are 5 consecutive eligible days.",
            "reps": reps, "block_days": block, "share_of_resamples_each_threshold_is_best": hist,
            "observed_best": GRID[int(obs.argmax())], "observed_per_day": {f"{th:.2f}": float(v) for th, v in zip(GRID, obs)},
            "middle_90pct_of_best": [float(np.quantile(best, 0.05)), float(np.quantile(best, 0.95))],
            "per_day_0.60_ci90": [float(np.quantile(m60, 0.05)), float(np.quantile(m60, 0.95))],
            "per_trade_0.60_ci90": [float(np.quantile(pt60, 0.05)), float(np.quantile(pt60, 0.95))],
            "per_trade_0.70_ci90": [float(np.quantile(pt70, 0.05)), float(np.quantile(pt70, 0.95))],
            "per_day_0.70_minus_0.60_ci90": [float(np.quantile(d70, 0.05)), float(np.quantile(d70, 0.95))],
            "share_0.70_beats_0.60_per_day": float((np.array(d70) > 0).mean()),
            "share_best_between_0.50_and_0.80": float(((best >= 0.5) & (best <= 0.8)).mean())}


def main(cache_path, out_path):
    cache = pickle.load(open(cache_path, "rb"))
    table, quotes = A.build(cache), cache["quotes"]
    res = {}
    M, dates = day_matrix(table, quotes, A.SPLIT, A.END)
    res["grid_2021_2026_ITM10"] = grid_table(table, quotes, A.SPLIT, A.END)
    res["grid_2021_2023_ITM10"] = grid_table(table, quotes, "2021-01-01", "2023-12-31")
    res["grid_2024_2026_ITM10"] = grid_table(table, quotes, "2024-01-01", A.END)
    res["grid_2013_2020_ITM10"] = grid_table(table, quotes, A.START, "2020-12-31")
    res["buckets_2021_2026_ITM10"] = bucket_table(table, quotes, A.SPLIT, A.END)
    res["buckets_2013_2020_ITM10"] = bucket_table(table, quotes, A.START, "2020-12-31")
    res["index_move_by_bucket_2013_2020"] = index_move_by_bucket(cache, A.START, "2020-12-31")
    res["index_move_by_bucket_2021_2026"] = index_move_by_bucket(cache, A.SPLIT, A.END)
    res["paired_vs_0.60_2021_2026"] = paired_vs_060(M)
    res["walk_forward_training_from_2021"] = walk_forward(M, dates)
    M13, dates13 = day_matrix(table, quotes, A.START, A.END)
    res["walk_forward_training_from_2013"] = walk_forward(M13, dates13, first_test_year="2022")
    res["bootstrap"] = bootstrap(M)
    res["strike_by_threshold_2021_2026"] = {}
    for name, off in A.OFFSETS.items():
        res["strike_by_threshold_2021_2026"][name] = {}
        for th in (0.5, 0.6, 0.7, 0.8):
            s, _, tr = A.pnl_series(table, quotes, th, off=off, lo=A.SPLIT, hi=A.END)
            res["strike_by_threshold_2021_2026"][name][f"{th:.2f}"] = A.stats(s, tr)
    json.dump(res, open(out_path, "w"), indent=1)
    return res


if __name__ == "__main__":
    r = main(sys.argv[1], sys.argv[2])
    f = lambda v, n=0: "   n/a" if v is None else f"{v:+.{n}f}"
    for key in ("grid_2021_2026_ITM10", "grid_2021_2023_ITM10", "grid_2024_2026_ITM10", "grid_2013_2020_ITM10"):
        print(key); print("  theta trades  $/trade  $/day    t    won  mid$/trade")
        for th, s in r[key].items():
            print(f"  {th}  {s['trades']:5d}  {f(s['per_trade'])}  {f(s['per_day'],1)}  {f(s['t'],2)}  {s['won']:.2f}  {f(s['per_trade_mid'])}")
    for key in ("buckets_2021_2026_ITM10", "buckets_2013_2020_ITM10"):
        print(key)
        for b, s in r[key].items():
            print(f"  {b}  n={s['trades']:4d}  ask {f(s['per_trade_ask'])}  t {f(s['t_ordinary'],2)}  won {s['won']:.2f}  mid {f(s['per_trade_mid'])}  exact {s['exact_decimal_trades']} {f(s['exact_decimal_per_trade_ask'])}")
    for key in ("index_move_by_bucket_2013_2020", "index_move_by_bucket_2021_2026"):
        print(key)
        for b, s in r[key].items():
            print(f"  {b}  days={s['days']:4d}  {s['mean_bps']:+.2f} bps  t {s['t']:+.2f}  right {s['right_way']:.3f}")
    print("paired vs 0.60"); [print("  ", k, f(v["per_day_minus_0.60"], 1), f(v["t"], 2)) for k, v in r["paired_vs_0.60_2021_2026"].items()]
    print(json.dumps(r["walk_forward_training_from_2021"], indent=1)); print(json.dumps(r["walk_forward_training_from_2013"], indent=1)); print(json.dumps(r["bootstrap"], indent=1))
    for name, v in r["strike_by_threshold_2021_2026"].items():
        print(name, {th: (round(s["per_trade"]), round(s["t"], 2), round(s["avg_cost"])) for th, s in v.items()})
