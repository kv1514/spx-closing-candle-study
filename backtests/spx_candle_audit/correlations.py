"""How strongly do the 15:50 candle's body % (and its size) go with what happens next? Descriptive correlations.

Part 1  history, the backtest feed (Dukascopy D1): body %, body size and range size against the index move after
        15:51 and against the option trade's result. Same days every earlier study used: not a fresh test.
Part 2  the two feeds against each other: real SPX body % vs the feed's body %.
Part 3  the forward log (data/spx_1549/alerts/feeds_1550.csv, kept by tools/spx_1550_alert.py): by band, on both
        feeds. Re-run this script any time to refresh Part 3 as the log grows.

Run from the repository root:
  .venv/bin/python -I backtests/spx_candle_audit/correlations.py CACHE.pkl [OUT.json]
CACHE.pkl comes from build_cache.py. Correlation p-values assume independent days.
"""
import csv, json, math, pickle, sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as A
import feeds as F

ROOT = Path(__file__).resolve().parents[2]
FEEDS_LOG = ROOT / "data/spx_1549/alerts/feeds_1550.csv"
CLOSES_LOG = ROOT / "data/spx_1549/alerts/closes_1550.csv"
EXT = ROOT / "data/spx_1549/dukascopy_ext_2026-11-09"


def corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 8 or x.std() == 0 or y.std() == 0:
        return {"n": int(len(x)), "pearson": None, "spearman": None}
    p, pp = stats.pearsonr(x, y)
    s, sp = stats.spearmanr(x, y)
    return {"n": int(len(x)), "pearson": float(p), "pearson_p": float(pp), "spearman": float(s), "spearman_p": float(sp),
            "share_of_variation_explained": float(p * p)}


def history(cache, table, lo, hi, with_options):
    quotes = cache["quotes"]
    rows = []
    for r in table:
        d = r["date"]
        if not (lo <= d <= hi):
            continue
        cd = r["candle"]
        if cd is None or cd["sign"] == 0 or not cd["rng"] > 0:
            continue
        b = cache["bars"][d]
        move = cd["sign"] * 1e4 * math.log(b["15:59"][3] / b["15:51"][0])
        pnl = math.nan
        if with_options and r["has_quotes"] and r["close"] is not None:
            p = A.price(r, quotes, cd["sign"], 10)
            if p is not None:
                pnl = 100 * (A.settle(p["kind"], p["strike"], r["close"]) - p["ask"]) - A.FEE
        rows.append((cd["ratio"], 1e4 * cd["body"] / cd["o"], 1e4 * cd["rng"] / cd["o"], move, pnl, A.fires(cd, 0.6)))
    a = np.array(rows, float)
    sig = a[:, 5] == 1
    out = {"days": int(len(a)), "signal_days": int(sig.sum())}
    xs = {"body_pct": a[:, 0], "body_size_bps": a[:, 1], "range_size_bps": a[:, 2]}
    win = np.where(a[:, 3] != 0, (a[:, 3] > 0).astype(float), np.nan)
    ys = {"index_move_bps": a[:, 3], "went_the_candles_way": win}
    if with_options:
        ys["option_pnl_at_ask"] = a[:, 4]
        ys["option_trade_won"] = np.where(np.isfinite(a[:, 4]), (a[:, 4] > 0).astype(float), np.nan)
    for scope, m in (("all_days", np.ones(len(a), bool)), ("signal_days_only", sig)):
        out[scope] = {xn: {yn: corr(x[m], y[m]) for yn, y in ys.items()} for xn, x in xs.items()}
    out["body_pct_vs_body_size"] = corr(a[:, 0], a[:, 1])
    # the same thing as averages: thirds of the signal days by body %
    q = np.quantile(a[sig, 0], [1 / 3, 2 / 3])
    out["signal_days_by_third_of_body_pct"] = {}
    for name, m in (("lowest third", sig & (a[:, 0] <= q[0])), ("middle third", sig & (a[:, 0] > q[0]) & (a[:, 0] <= q[1])),
                    ("highest third", sig & (a[:, 0] > q[1]))):
        e = {"days": int(m.sum()), "body_pct_from": float(a[m, 0].min()), "body_pct_to": float(a[m, 0].max()),
             "mean_index_move_bps": float(a[m, 3].mean())}
        if with_options:
            v = a[m, 4][np.isfinite(a[m, 4])]
            e.update({"option_trades": int(len(v)), "option_pnl_at_ask": float(v.mean())})
        out["signal_days_by_third_of_body_pct"][name] = e
    return out


def two_feeds():
    R, K = F.real_spx(), F.duka(EXT)
    days = sorted(d for d in R if d in K and "15:50" in R[d] and "15:50" in K[d] and len(R[d]) >= 380)
    r50 = [F.ratio(R[d]["15:50"]) for d in days]
    k50 = [F.ratio(K[d]["15:50"]) for d in days]
    pr, pk = [], []
    for d in days:
        for t in R[d]:
            if "15:30" <= t <= "15:59" and t in K[d]:
                x, y = F.ratio(R[d][t]), F.ratio(K[d][t])
                if math.isfinite(x) and math.isfinite(y):
                    pr.append(x); pk.append(y)
    fit = stats.linregress(pr, pk)
    return {"days": len(days), "at_1550": corr(r50, k50), "candles_1530_1559": corr(pr, pk),
            "line_feed_pct_from_real_pct": {"intercept": float(fit.intercept), "slope": float(fit.slope),
                                            "feed_pct_when_real_is_0.60": float(fit.intercept + 0.6 * fit.slope),
                                            "feed_pct_when_real_is_0.70": float(fit.intercept + 0.7 * fit.slope),
                                            "real_pct_where_feed_is_0.60": float((0.6 - fit.intercept) / fit.slope)},
            "mean_gap_real_minus_feed_at_1550": float(np.mean(np.array(r50) - np.array(k50)))}


def forward_log():
    if not FEEDS_LOG.exists():
        return {"days": 0}
    rows = [r for r in csv.DictReader(FEEDS_LOG.open()) if r.get("real_ratio") and r.get("move_pts")]
    closes = {r["date"]: r for r in csv.DictReader(CLOSES_LOG.open())} if CLOSES_LOG.exists() else {}
    out = {"days": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"],
           "days_after_2026-10-20_(not_in_any_backtest)": sum(r["date"] > "2026-10-20" for r in rows)}
    mv = np.array([float(r["move_pts"]) for r in rows])
    rr = np.array([float(r["real_ratio"]) for r in rows])
    fr = np.array([float(r["feed_ratio"]) if r.get("feed_ratio") else math.nan for r in rows])
    out["real_pct_vs_move_pts"] = corr(rr, mv)
    out["feed_pct_vs_move_pts"] = corr(fr, mv)
    for key in ("real_band", "feed_band"):
        tab = {}
        for band in ("70%+", "60-70%", "under 60%"):
            g = [r for r in rows if r.get(key) == band]
            if not g:
                tab[band] = {"days": 0}
                continue
            m = np.array([float(r["move_pts"]) for r in g])
            e = {"days": len(g), "went_the_candles_way": int((m > 0).sum()), "mean_move_pts": float(m.mean()),
                 "median_move_pts": float(np.median(m))}
            if key == "real_band":
                p = [float(closes[r["date"]]["pnl_at_ask"]) for r in g
                     if r["date"] in closes and closes[r["date"]].get("pnl_at_ask") not in ("", None)]
                e["alerted_trades_priced"] = len(p)
                e["alerted_pnl_at_ask_total"] = float(sum(p)) if p else None
            tab[band] = e
        out[f"by_{key}"] = tab
    # the cross table: where do the two feeds put the same day?
    cross = {}
    for r in rows:
        if r.get("feed_band"):
            k = f"real {r['real_band']} / feed {r['feed_band']}"
            c = cross.setdefault(k, {"days": 0, "went_the_candles_way": 0, "sum_move": 0.0})
            c["days"] += 1; c["went_the_candles_way"] += float(r["move_pts"]) > 0; c["sum_move"] += float(r["move_pts"])
    out["cross"] = {k: {"days": v["days"], "went_the_candles_way": v["went_the_candles_way"],
                        "mean_move_pts": v["sum_move"] / v["days"]} for k, v in sorted(cross.items())}
    return out


if __name__ == "__main__":
    cache = pickle.load(open(sys.argv[1], "rb"))
    table = A.build(cache)
    res = {"history_2013_2020": history(cache, table, A.START, "2020-12-31", False),
           "history_2021_2026": history(cache, table, A.SPLIT, A.END, True),
           "two_feeds": two_feeds(), "forward_log": forward_log()}
    if len(sys.argv) > 2:
        json.dump(res, open(sys.argv[2], "w"), indent=1)
    f = lambda c: "n/a" if not c or c.get("pearson") is None else f"r {c['pearson']:+.3f} (p {c['pearson_p']:.3f})  rank {c['spearman']:+.3f} (p {c['spearman_p']:.3f})  n {c['n']}"
    for per in ("history_2013_2020", "history_2021_2026"):
        h = res[per]
        print(per, "days", h["days"], "signal days", h["signal_days"])
        for scope in ("all_days", "signal_days_only"):
            for xn, d in h[scope].items():
                for yn, c in d.items():
                    print(f"  {scope:<17} {xn:<15} vs {yn:<22} {f(c)}")
        print("  body % vs body size:", f(h["body_pct_vs_body_size"]))
        for k, v in h["signal_days_by_third_of_body_pct"].items():
            print("  ", k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
    t = res["two_feeds"]
    print("two feeds: 15:50", f(t["at_1550"]), "| candles", f(t["candles_1530_1559"]))
    print("  ", {k: round(v, 3) for k, v in t["line_feed_pct_from_real_pct"].items()}, "gap", round(t["mean_gap_real_minus_feed_at_1550"], 3))
    fw = res["forward_log"]
    print("forward log", {k: v for k, v in fw.items() if not isinstance(v, dict)})
    print("  real % vs move", f(fw.get("real_pct_vs_move_pts")), "| feed % vs move", f(fw.get("feed_pct_vs_move_pts")))
    for key in ("by_real_band", "by_feed_band", "cross"):
        for k, v in fw.get(key, {}).items():
            print("  ", key, k, {a: (round(b, 2) if isinstance(b, float) else b) for a, b in v.items()})
