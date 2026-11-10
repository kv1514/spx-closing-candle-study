"""Checks on the CNBC SPY candle archive that use price LEVELS and file counts only (no body, ratio, band,
direction, index move or P&L). Specified in the plan before they were run; the output is quoted in the plan.

Run from the repository root:  .venv/bin/python -I backtests/spx_candle_spy/prelock_checks.py
"""
import csv, hashlib, json, math, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "spx_1549"
SPY, IDX = D / "cnbc_spy_1m", D / "cnbc_1m"
START, END = "2021-01-01", "2026-10-20"
NY = ZoneInfo("America/New_York")


def load(arch):
    out = {}
    for p in sorted(arch.glob("2*.json")):
        j = json.load(open(p))
        assert j["date"] == p.stem, p
        out[j["date"]] = j
    return out


def manifest(arch):
    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(arch.glob("2*.json"))]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), len(lines)


def ok(b):
    if b is None or len(b) != 4 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in b):
        return False
    o, h, l, c = b
    return not (h < max(o, c) or l > min(o, c) or h < l)


def other_archive(path, tcol):
    """{date: {HH:MM: (o,h,l,c)}} from an earlier SPY minute file whose time column is New York time."""
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            t = r[tcol]
            d, hm = t[:10], t[11:16]
            if "15:45" <= hm <= "15:59":
                try:
                    out.setdefault(d, {})[hm] = tuple(float(r[k]) for k in ("open", "high", "low", "close"))
                except ValueError:
                    pass
    return out


def main():
    S, X = load(SPY), load(IDX)
    days = list(csv.DictReader(open(D / "d1_days.csv")))
    base = sorted({r["date"] for r in days if r["calendar"] == "full" and START <= r["date"] <= END})
    closes = {}
    for r in csv.DictReader(open(D / "spx_official_closes_cboe.csv")):
        m, d, y = r["DATE"].split("/")
        closes[f"{y}-{m}-{d}"] = float(r["SPX"])
    qdir = D / "databento" / "cbbo-1m_1500-1601_k60"
    has_q = {p.name[:10] for p in qdir.glob("*.csv.gz")}
    marker = {p.name[:10] for p in qdir.glob("*.none")}
    res = {"base_dates": len(base)}
    by = {}
    for d in base:
        y = by.setdefault(d[:4], {"base": 0, "no_expiry_marker": 0, "no_quote_file_no_marker": 0, "no_close": 0,
                                  "denominator": 0, "no_spy_file": 0, "no_1550_bar": 0, "invalid_1550_bar": 0, "eligible": 0,
                                  "eligible_with_index_bar": 0})
        y["base"] += 1
        if d not in has_q:
            y["no_expiry_marker" if d in marker else "no_quote_file_no_marker"] += 1
            continue
        if not math.isfinite(closes.get(d, math.nan)):
            y["no_close"] += 1
            continue
        y["denominator"] += 1
        j = S.get(d)
        if j is None:
            y["no_spy_file"] += 1
            continue
        b = j["bars"].get("15:50")
        if b is None:
            y["no_1550_bar"] += 1
            continue
        if not ok(b):
            y["invalid_1550_bar"] += 1
            continue
        y["eligible"] += 1
        y["eligible_with_index_bar"] += ok((X.get(d) or {"bars": {}})["bars"].get("15:50"))
    tot = {k: sum(v[k] for v in by.values()) for k in next(iter(by.values()))}
    res["by_year"], res["total"] = by, tot
    res["coverage"] = tot["eligible"] / tot["denominator"]
    # requests per filled session, and the window that answered
    req, win = {}, {}
    for d, j in S.items():
        if "15:50" in j["bars"]:
            req[str(j.get("requests", 1))] = req.get(str(j.get("requests", 1)), 0) + 1
            win[j.get("window") or "first request 1545-1600"] = win.get(j.get("window") or "first request 1545-1600", 0) + 1
    res["requests_per_filled_session"] = dict(sorted(req.items(), key=lambda kv: int(kv[0])))
    res["answering_window"] = win
    # 3. which minute? SPY 15:50 close scaled by the 15:45 index/SPY ratio, against the index close at 15:49/15:50/15:51
    al = {}
    for d in base:
        s, x = (S.get(d) or {"bars": {}})["bars"], (X.get(d) or {"bars": {}})["bars"]
        if not all(ok(s.get(t)) for t in ("15:45", "15:50")) or not all(ok(x.get(t)) for t in ("15:45", "15:49", "15:50", "15:51")):
            continue
        r = x["15:45"][3] / s["15:45"][3]
        y = al.setdefault(d[:4], {"n": 0, "15:49": 0.0, "15:50": 0.0, "15:51": 0.0})
        y["n"] += 1
        for t in ("15:49", "15:50", "15:51"):
            y[t] += abs(s["15:50"][3] * r - x[t][3])
    res["scaled_spy_1550_close_vs_index_close_at"] = {y: {"n": v["n"], **{t: round(v[t] / v["n"], 3) for t in ("15:49", "15:50", "15:51")}}
                                                       for y, v in sorted(al.items())}
    res["years_where_1550_is_not_the_closest_minute"] = [y for y, v in al.items() if not (v["15:50"] < v["15:49"] and v["15:50"] < v["15:51"])]
    # 5. against the earlier SPY archives, each separately: the 15:50 bar's four prices, and close offsets
    res["against_earlier_spy_archives"] = {}
    srcs = {"recorder bars_1m": [(ROOT / "data/bars_1m" / f"SPY_1m_2026-{m}.csv", "timestamp_ny") for m in ("09", "10", "11")],
            "yahoo_1m": [(ROOT / "data/yahoo_1m/SPY_1m.csv", "timestamp_ny")]}
    for name, files in srcs.items():
        O = {}
        for p, tcol in files:
            if p.exists():
                for d, v in other_archive(p, tcol).items():
                    O.setdefault(d, {}).update(v)
        both = sorted(d for d in O if d in S and ok(S[d]["bars"].get("15:50")) and "15:50" in O[d])
        if not both:
            res["against_earlier_spy_archives"][name] = {"sessions": 0}
            continue
        diffs = np.array([[abs(a - b) for a, b in zip(S[d]["bars"]["15:50"], O[d]["15:50"])] for d in both])
        cents_eq = sum(all(int(round(a * 100)) == int(round(b * 100)) for a, b in zip(S[d]["bars"]["15:50"], O[d]["15:50"])) for d in both)
        exact = sum(list(S[d]["bars"]["15:50"]) == list(O[d]["15:50"]) for d in both)
        off = {}
        for t in ("15:49", "15:50", "15:51"):
            g = [abs(S[d]["bars"]["15:50"][3] - O[d][t][3]) for d in both if t in O[d]]
            off[t] = round(float(np.mean(g)), 4) if g else None
        res["against_earlier_spy_archives"][name] = {
            "sessions": len(both), "first": both[0], "last": both[-1], "exactly_equal": exact, "equal_in_whole_cents": cents_eq,
            "median_abs_diff": {k: round(float(np.median(diffs[:, i])), 4) for i, k in enumerate(("open", "high", "low", "close"))},
            "max_abs_diff": {k: round(float(diffs[:, i].max()), 4) for i, k in enumerate(("open", "high", "low", "close"))},
            "mean_abs_gap_cnbc_1550_close_vs_other_close_at": off}
    # 6. what "adjusted" does: the 15:59 close against the unadjusted daily close, by year
    daily = {r["date"]: float(r["close"]) for r in csv.DictReader(open(D / "spy_daily_closes.csv"))}
    adj = {}
    for d in base:
        b = (S.get(d) or {"bars": {}})["bars"].get("15:59")
        if ok(b) and d in daily:
            adj.setdefault(d[:4], []).append(b[3] / daily[d])
    res["cnbc_1559_close_over_unadjusted_daily_close"] = {y: {"n": len(v), "median": round(float(np.median(v)), 5), "min": round(min(v), 5), "max": round(max(v), 5)}
                                                         for y, v in sorted(adj.items())}
    # how many stored prices are not on a whole cent (sub-penny prints)
    sub = tot_px = 0
    for d in base:
        b = (S.get(d) or {"bars": {}})["bars"].get("15:50")
        if ok(b):
            for x in b:
                tot_px += 1
                sub += abs(x * 100 - round(x * 100)) > 1e-6
    res["prices_in_1550_bars_not_on_a_whole_cent"] = {"prices": tot_px, "off_cent": sub}
    # raw samples, if present
    raw = {}
    for p in sorted((SPY / "raw_samples").glob("*.json")) if (SPY / "raw_samples").exists() else []:
        j = json.load(open(p))
        pb = j["barData"]["priceBars"]
        tt = [x["tradeTime"] for x in pb]
        x = next((b for b in pb if b["tradeTime"][8:12] == "1550"), None)
        ep = datetime.fromtimestamp(int(x["tradeTimeinMills"]) / 1000, tz=NY).strftime("%Y-%m-%d %H:%M:%S %Z") if x else None
        stored = S.get(p.stem, {"bars": {}})["bars"].get("15:50")
        raw[p.stem] = {"symbol": j["barData"].get("symbol"), "bars": len(pb), "all_on_the_minute": all(t[12:] == "00" for t in tt),
                       "all_dated_that_day": all(t[:8] == p.stem.replace("-", "") for t in tt), "duplicate_labels": len(tt) - len(set(tt)),
                       "epoch_of_1550_bar_new_york": ep,
                       "equals_stored_file": (x is not None and stored == [float(x[k]) for k in ("open", "high", "low", "close")])}
    res["raw_samples"] = raw
    res["manifest_sha256"], res["manifest_files"] = manifest(SPY)
    res["index_manifest_sha256"], res["index_manifest_files"] = manifest(IDX)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
