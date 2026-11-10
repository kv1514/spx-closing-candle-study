"""Independent audit of the 15:50 candle rule (2026-11-09). Descriptive; not a pre-registered test.

Part A  data checks: calendar, bars, official closes, the option-implied index against the Dukascopy bars.
Part B  rebuild the published real-price result from the raw files and compare it trade by trade.
Part C  the body threshold: fine grid, body buckets, paired differences, walk-forward choice, bootstrap.

Shares no code with scan.py / realprice.py / refine.py. The definitions (signal, implied spot, strike, P&L,
Newey-West lag 5) are re-implemented from the text of preregistration/spx_candle_realprice.md.

Run from the repository root:
  .venv/bin/python -I backtests/spx_candle_audit/audit.py CACHE.pkl
"""
import csv, json, math, pickle, sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FEE = 0.09
START, SPLIT, END = "2013-04-01", "2021-01-01", "2026-10-20"
OFFSETS = {"ITM20": 20, "ITM15": 15, "ITM10": 10, "ITM5": 5, "ATM": 0, "OTM5": -5, "OTM10": -10}


# ---------------------------------------------------------------- basic pieces
def nw(y, lag=5):
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    n = len(y)
    if n < lag + 3:
        return {"n": n, "mean": float(y.mean()) if n else None, "t": None}
    mu = y.mean()
    e = y - mu
    v = e @ e / n
    for j in range(1, lag + 1):
        v += 2 * (1 - j / (lag + 1)) * (e[j:] @ e[:-j]) / n
    se = math.sqrt(max(v, 0) / n)
    return {"n": n, "mean": float(mu), "t": float(mu / se) if se > 0 else None}


def valid(q):
    return (q is not None and math.isfinite(q[0]) and math.isfinite(q[1]) and q[1] > 0 and 0 <= q[0] <= q[1])


def implied_spot(book):
    """Median of K + call mid - put mid over the 3 strikes where the two mids are closest (both bids > 0).
    A tie in closeness goes to the lower strike (the sort key is (gap, strike))."""
    rows = []
    for (kind, k), q in book.items():
        if kind != "C":
            continue
        p = book.get(("P", k))
        if valid(q) and valid(p) and q[0] > 0 and p[0] > 0:
            cm, pm = (q[0] + q[1]) / 2, (p[0] + p[1]) / 2
            rows.append((abs(cm - pm), k, k + cm - pm))
    if len(rows) < 3:
        return None
    rows.sort()
    return float(np.median([r[2] for r in rows[:3]]))


def atm_of(s):
    return math.floor(s / 5 + 0.5) * 5


def candle(bars_day, t="15:50"):
    b = bars_day.get(t)
    if b is None:
        return None
    o, h, l, c, _ = b
    rng = h - l
    if not rng > 0:
        return {"o": o, "h": h, "l": l, "c": c, "body": abs(c - o), "rng": rng, "ratio": math.nan, "sign": 0}
    return {"o": o, "h": h, "l": l, "c": c, "body": abs(c - o), "rng": rng, "ratio": abs(c - o) / rng,
            "sign": int(np.sign(c - o))}


def fires(cd, lo, hi=None):
    """The plan's test, in floats exactly as written: range > 0 and |body| >= lo x range (and below hi x range)."""
    if cd is None or not cd["rng"] > 0 or cd["sign"] == 0:
        return False
    if not cd["body"] >= lo * cd["rng"]:
        return False
    return hi is None or not cd["body"] >= hi * cd["rng"]


def fires_exact(cd, lo, hi=None):
    """Sensitivity: the same test in exact arithmetic on prices in thousandths (D1 has 3 decimals)."""
    if cd is None:
        return False
    o, h, l, c = (round(cd[k] * 1000) for k in ("o", "h", "l", "c"))
    body, rng = abs(c - o), h - l
    if not rng > 0 or c == o:
        return False
    if body * 100 < round(lo * 100) * rng:
        return False
    return hi is None or body * 100 < round(hi * 100) * rng


# ---------------------------------------------------------------- build the per-day table
def build(cache):
    bars, closes, quotes = cache["bars"], cache["closes"], cache["quotes"]
    keep = [r["date"] for r in cache["days"] if r["keep"].strip().lower() == "true" and START <= r["date"] <= END]
    table = []
    for d in keep:
        cd = candle(bars[d])
        row = {"date": d, "candle": cd, "has_quotes": d in quotes, "close": closes.get(d)}
        row["d1_1551_open"] = bars[d]["15:51"][0] if "15:51" in bars[d] else None
        row["d1_1559_close"] = bars[d]["15:59"][3] if "15:59" in bars[d] else None
        if d in quotes:
            q = quotes[d]
            row["S"] = {m: implied_spot(q[m]) for m in ("15:50", "15:51", "15:59", "16:00")}
            s = row["S"]["15:51"]
            row["atm"] = atm_of(s) if s is not None else None
        table.append(row)
    return table


def price(row, quotes, sign, off, minute="15:51"):
    """(ask, mid, bid, strike, kind) of the option `off` points in the money for direction `sign`, or None."""
    if row.get("atm") is None or sign == 0:
        return None
    kind = "C" if sign > 0 else "P"
    k = row["atm"] - off if sign > 0 else row["atm"] + off
    q = quotes[row["date"]][minute].get((kind, float(k)))
    if not valid(q):
        return None
    return {"ask": q[1], "bid": q[0], "mid": (q[0] + q[1]) / 2, "strike": k, "kind": kind}


def settle(kind, k, close):
    return max(0.0, close - k) if kind == "C" else max(0.0, k - close)


def pnl_series(table, quotes, theta_lo, theta_hi=None, off=10, lo=SPLIT, hi=END, at="ask", minute="15:51", test=None):
    """Per-day P&L list (0 on no-signal days, nan when it cannot be priced) for body ratio in [theta_lo, theta_hi)."""
    out, dates, trades = [], [], []
    for row in table:
        d = row["date"]
        if not (lo <= d <= hi) or not row["has_quotes"] or row["close"] is None:
            continue
        cd = row["candle"]
        if cd is None:
            continue
        dates.append(d)
        ratio = cd["ratio"]
        if not (test or fires)(cd, theta_lo, theta_hi):
            out.append(0.0)
            continue
        p = price(row, quotes, cd["sign"], off, minute)
        if p is None:
            out.append(math.nan)
            continue
        v = 100 * (settle(p["kind"], p["strike"], row["close"]) - p[at]) - FEE
        out.append(v)
        trades.append({"date": d, "sign": cd["sign"], "ratio": ratio, "S": row["S"]["15:51"], **p, "pnl": v})
    return np.array(out), dates, trades


def stats(series, trades):
    r = nw(series)
    p = np.array([t["pnl"] for t in trades])
    return {"days": r["n"], "trades": len(p), "per_day": r["mean"], "t": r["t"],
            "per_trade": float(p.mean()) if len(p) else None, "won": float((p > 0).mean()) if len(p) else None,
            "median": float(np.median(p)) if len(p) else None, "worst": float(p.min()) if len(p) else None,
            "avg_cost": float(np.mean([100 * t["ask"] for t in trades])) if trades else None}


# ---------------------------------------------------------------- Part A
def part_a(cache, table):
    out = {"bars": cache["bar_checks"]}
    days = cache["days"]
    in_rng = [r for r in days if START <= r["date"] <= END]
    out["calendar"] = {
        "weekdays_listed": len(in_rng),
        "holidays": sum(r["calendar"] == "nyse_holiday" for r in in_rng),
        "half_days": sum(r["calendar"] == "half_day" or "half" in r["calendar"] for r in in_rng),
        "kept": sum(r["keep"].strip().lower() == "true" for r in in_rng),
        "dropped_by_reason": {},
    }
    for r in in_rng:
        if r["keep"].strip().lower() != "true":
            k = r["reason"] or r["calendar"]
            out["calendar"]["dropped_by_reason"][k] = out["calendar"]["dropped_by_reason"].get(k, 0) + 1
    # every kept day must have either quotes or a 'none' marker, and an official close
    none = set(cache["none_days"])
    out["kept_days_with_neither_quotes_nor_marker"] = [r["date"] for r in table if not r["has_quotes"] and r["date"] not in none]
    out["kept_days_without_official_close"] = [r["date"] for r in table if r["close"] is None]
    # independent calendar check: Cboe's close file lists every trading day; a weekday missing from it is a holiday
    d0, d1, wk = date.fromisoformat(START), date.fromisoformat(END), []
    while d0 <= d1:
        if d0.weekday() < 5:
            wk.append(d0.isoformat())
        d0 += timedelta(days=1)
    cl = cache["closes"]
    listed_hol = {r["date"] for r in in_rng if r["calendar"] == "nyse_holiday"}
    cboe_hol = {d for d in wk if d not in cl}
    out["calendar_vs_cboe_close_file"] = {"weekdays": len(wk), "weekdays_without_a_cboe_close": len(cboe_hol),
                                          "listed_holidays": len(listed_hol), "disagreements": sorted(cboe_hol ^ listed_hol)}
    # official closes against the broker's daily closes (non-interpolated bars), wherever both exist
    rh = {}
    files = sorted((ROOT / "data/spx_1549/robinhood/raw").glob("spx_daily*.json")) + sorted((ROOT / "data/spx_1549").glob("live_*/spx_daily.json"))
    for p in files:
        for res in json.load(open(p))["data"]["results"]:
            for b in res["bars"]:
                if not b.get("interpolated"):
                    rh[b["begins_at"][:10]] = float(b["close_value"])
    both = sorted(d for d in rh if d in cl)
    gaps = [abs(rh[d] - cl[d]) for d in both]
    out["cboe_close_vs_broker_close"] = {"days": len(both), "first": both[0], "last": both[-1], "max_abs_diff": max(gaps),
                                         "days_differing_by_more_than_0.01": int(sum(g > 0.01 for g in gaps))}
    out["quote_file_rows"] = cache.get("quote_totals")
    out["inputs_sha256"] = cache.get("inputs_sha256")
    # official close against the option-implied index at 16:00 and at 15:59
    for m in ("16:00", "15:59"):
        gaps = [(r["S"][m] - r["close"]) for r in table if r["has_quotes"] and r["close"] and r["S"].get(m) is not None]
        g = np.array(gaps)
        out[f"implied_{m}_minus_official_close"] = {"n": len(g), "mean": float(g.mean()), "mean_abs": float(np.abs(g).mean()),
                                                    "p95_abs": float(np.percentile(np.abs(g), 95)), "max_abs": float(np.abs(g).max())}
    # Dukascopy against the option-implied index (level basis at 15:51, and the 15:50 body)
    basis, body_d1, body_im, per = [], [], [], {}
    for r in table:
        if not r["has_quotes"] or r["candle"] is None:
            continue
        s50, s51 = r["S"].get("15:50"), r["S"].get("15:51")
        if s51 is not None and r["d1_1551_open"] is not None:
            basis.append(r["d1_1551_open"] - s51)
        if s50 is not None and s51 is not None:
            body_d1.append(r["candle"]["c"] - r["candle"]["o"])
            body_im.append(s51 - s50)
            per.setdefault("2013-2020" if r["date"] < SPLIT else "2021-2026", []).append((body_d1[-1], body_im[-1], r["candle"]["ratio"]))
    b = np.array(basis)
    out["d1_1551_open_minus_implied_1551"] = {"n": len(b), "mean": float(b.mean()), "mean_abs": float(np.abs(b).mean()),
                                              "p95_abs": float(np.percentile(np.abs(b), 95))}
    out["body_1550_d1_vs_option_implied"] = {}
    for k, v in per.items():
        a = np.array(v)
        strong = a[:, 2] >= 0.6
        nz = (a[:, 0] != 0) & (a[:, 1] != 0)
        out["body_1550_d1_vs_option_implied"][k] = {
            "n": len(a), "corr": float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]),
            "same_sign_all": float((np.sign(a[nz, 0]) == np.sign(a[nz, 1])).mean()),
            "n_strong": int(strong.sum()),
            "same_sign_strong_body_days": float((np.sign(a[strong & nz, 0]) == np.sign(a[strong & nz, 1])).mean()),
            "mean_abs_body_d1": float(np.abs(a[:, 0]).mean()), "mean_abs_body_implied": float(np.abs(a[:, 1]).mean()),
        }
    return out


# ---------------------------------------------------------------- Part B
def part_b(table, quotes):
    pub = {}
    with open(ROOT / "data/spx_1549/databento/realprice_trades.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["config"] == "current":
                pub[r["date"]] = r
    out = {}
    for name, lo, hi in (("2013-2020", START, "2020-12-31"), ("2021-2026", SPLIT, END)):
        s, dates, trades = pnl_series(table, quotes, 0.60, off=10, lo=lo, hi=hi)
        mine = {t["date"]: t for t in trades}
        theirs = {d: r for d, r in pub.items() if lo <= d <= hi}
        priced_theirs = {d for d, r in theirs.items() if r["status"] == "priced"}
        diffs = []
        for d in sorted(set(mine) & priced_theirs):
            t, r = mine[d], theirs[d]
            if (abs(t["pnl"] - float(r["pnl_fee_0.09"])) > 0.005 or abs(t["ask"] - float(r["ask"])) > 1e-9
                    or abs(t["strike"] - float(r["strike"])) > 1e-9 or int(r["signal"]) != t["sign"]):
                diffs.append(d)
        nanm = [d for d, v in zip(dates, s) if not math.isfinite(v)]
        out[name] = {"mine": stats(s, trades), "published_priced": len(priced_theirs),
                     "published_signal_days": len(theirs), "my_signal_days": int(sum(1 for v in s if v != 0 or not math.isfinite(v))),
                     "signal_days_only_mine": sorted(set(mine) - set(theirs))[:10],
                     "signal_days_only_published": sorted(priced_theirs - set(mine))[:10],
                     "trades_that_differ": diffs[:10], "n_trades_that_differ": len(diffs),
                     "my_unpriced_signal_days": nanm[:10], "n_my_unpriced": len(nanm),
                     "published_mean": float(np.mean([float(theirs[d]["pnl_fee_0.09"]) for d in priced_theirs])) if priced_theirs else None}
        s_mid, _, tr_mid = pnl_series(table, quotes, 0.60, off=10, lo=lo, hi=hi, at="mid")
        out[name]["at_mid"] = stats(s_mid, tr_mid)
        # coverage: how many signal days could be priced, and why not
        cov = {"signal_days_with_quote_file": 0, "priced": len(trades), "no_implied_spot": 0, "no_valid_contract_quote": 0,
               "unpriced_by_year": {}, "signal_days_by_year": {}}
        extra_ask, extra_mid = [], []
        for row in table:
            d = row["date"]
            if not (lo <= d <= hi) or not row["has_quotes"] or row["close"] is None or not fires(row["candle"], 0.60):
                continue
            cov["signal_days_with_quote_file"] += 1
            cov["signal_days_by_year"][d[:4]] = cov["signal_days_by_year"].get(d[:4], 0) + 1
            if d in mine:
                continue
            cov["unpriced_by_year"][d[:4]] = cov["unpriced_by_year"].get(d[:4], 0) + 1
            if row.get("atm") is None:
                cov["no_implied_spot"] += 1
                # sensitivity only: take the spot from the D1 15:51 open instead, same strike and price rules
                if row["d1_1551_open"] is not None:
                    sign = row["candle"]["sign"]
                    k = atm_of(row["d1_1551_open"]) - 10 if sign > 0 else atm_of(row["d1_1551_open"]) + 10
                    kind = "C" if sign > 0 else "P"
                    q = quotes[d]["15:51"].get((kind, float(k)))
                    if valid(q):
                        v = settle(kind, k, row["close"])
                        extra_ask.append(100 * (v - q[1]) - FEE); extra_mid.append(100 * (v - (q[0] + q[1]) / 2) - FEE)
            else:
                cov["no_valid_contract_quote"] += 1
        cov["sensitivity_d1_spot_for_days_without_implied_spot"] = {
            "trades": len(extra_ask), "per_trade_ask": float(np.mean(extra_ask)) if extra_ask else None,
            "per_trade_mid": float(np.mean(extra_mid)) if extra_mid else None,
            "all_days_per_trade_ask": float(np.mean(extra_ask + [t["pnl"] for t in trades])) if extra_ask else None,
            "all_days_per_trade_mid": float(np.mean(extra_mid + [t["pnl"] for t in tr_mid])) if extra_mid else None}
        out[name]["coverage"] = cov
    return out


def alignment(table, quotes):
    """Is the Dukascopy 15:50 bar really the 15:50 minute? Correlate its body with the option-implied index
    change over the minute before, the same minute and the minute after."""
    out = {}
    for name, a, b in (("minute_before_15:49-15:50", "15:49", "15:50"), ("same_minute_15:50-15:51", "15:50", "15:51"),
                       ("minute_after_15:51-15:52", "15:51", "15:52")):
        x, y = [], []
        for r in table:
            if not r["has_quotes"] or r["candle"] is None or r["date"] < SPLIT:
                continue
            sa, sb = implied_spot(quotes[r["date"]][a]), implied_spot(quotes[r["date"]][b])
            if sa is None or sb is None:
                continue
            x.append(r["candle"]["c"] - r["candle"]["o"]); y.append(sb - sa)
        out[name] = {"n": len(x), "corr": float(np.corrcoef(x, y)[0, 1])}
    return out


def part_d(table, quotes):
    """Re-derive other published 2021-2026 figures for the rule (15:50, 0.60, with, ITM10)."""
    out = {"strikes": {}, "late_entry_same_contract_at_ask": {}, "sell_at_bid_at_minute": {}, "by_year": {}}
    for name, off in OFFSETS.items():
        s, _, tr = pnl_series(table, quotes, 0.60, off=off)
        out["strikes"][name] = stats(s, tr)
    s, dates, trades = pnl_series(table, quotes, 0.60, off=10)
    by = {t["date"]: t for t in trades}
    rows = {r["date"]: r for r in table}
    for m in ("15:52", "15:53", "15:55", "15:57"):
        v = []
        for d, t in by.items():
            q = quotes[d][m].get((t["kind"], float(t["strike"])))
            if valid(q):
                v.append(100 * (settle(t["kind"], t["strike"], rows[d]["close"]) - q[1]) - FEE)
        out["late_entry_same_contract_at_ask"][m] = {"trades": len(v), "per_trade": float(np.mean(v))}
    for m in ("15:52", "15:53", "15:54", "15:55", "15:56", "15:57", "15:58", "15:59"):
        v, hold = [], []
        for d, t in by.items():
            q = quotes[d][m].get((t["kind"], float(t["strike"])))
            if valid(q):
                v.append(100 * (q[0] - t["ask"]) - 2 * FEE); hold.append(t["pnl"])
        out["sell_at_bid_at_minute"][m] = {"trades": len(v), "per_trade": float(np.mean(v)), "hold_same_trades": float(np.mean(hold))}
    for th in (0.60, 0.70):
        _, _, tr = pnl_series(table, quotes, th, off=10)
        yr = {}
        for t in tr:
            yr.setdefault(t["date"][:4], []).append(t["pnl"])
        out["by_year"][f"{th:.2f}"] = {y: {"trades": len(v), "per_trade": float(np.mean(v)), "total": float(np.sum(v))} for y, v in sorted(yr.items())}
    return out


if __name__ == "__main__":
    cache = pickle.load(open(sys.argv[1], "rb"))
    table = build(cache)
    res = {"part_a": part_a(cache, table), "part_b": part_b(table, cache["quotes"]),
           "part_d": part_d(table, cache["quotes"])}
    res["part_a"]["minute_alignment_2021_2026"] = alignment(table, cache["quotes"])
    if len(sys.argv) > 2:
        json.dump(res, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(res, indent=1))
