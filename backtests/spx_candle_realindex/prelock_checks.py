"""Checks on the CNBC candle archive that use price LEVELS and file counts only (no body, ratio, band, direction,
index move or P&L). Run before the plan is locked; the output is quoted in the plan.

Run from the repository root:  .venv/bin/python -I backtests/spx_candle_realindex/prelock_checks.py
"""
import csv, gzip, hashlib, json, math, sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "spx_1549"
ARCH = D / "cnbc_1m"
sys.path.insert(0, str(ROOT / "backtests" / "spx_candle_audit"))
import feeds as F                      # real_spx(): the broker's own SPX minute bars already on disk

START, END = "2021-01-01", "2026-10-20"


def archive():
    out = {}
    for p in sorted(ARCH.glob("2*.json")):
        j = json.load(open(p))
        out[j["date"]] = j
    return out


def manifest():
    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(ARCH.glob("2*.json"))]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), len(lines)


def main():
    A = archive()
    days = list(csv.DictReader(open(D / "d1_days.csv")))
    base = [r["date"] for r in days if r["calendar"] == "full" and START <= r["date"] <= END]
    closes = {}
    for r in csv.DictReader(open(D / "spx_official_closes_cboe.csv")):
        m, d, y = r["DATE"].split("/")
        closes[f"{y}-{m}-{d}"] = float(r["SPX"])
    qdir = D / "databento" / "cbbo-1m_1500-1601_k60"
    has_q = {p.name[:10] for p in qdir.glob("*.csv.gz")}
    marker = {p.name[:10] for p in qdir.glob("*.none")}
    res = {"base_dates": len(base)}
    # ---- exclusions and coverage, by year
    by = {}
    for d in base:
        y = by.setdefault(d[:4], {"base": 0, "no_expiry_marker": 0, "no_quote_file_no_marker": 0, "no_close": 0,
                                  "denominator": 0, "no_cnbc_file": 0, "no_1550_bar": 0, "invalid_1550_bar": 0, "eligible": 0})
        y["base"] += 1
        if d in marker and d not in has_q:
            y["no_expiry_marker"] += 1; continue
        if d not in has_q:
            y["no_quote_file_no_marker"] += 1; continue
        if not math.isfinite(closes.get(d, math.nan)):
            y["no_close"] += 1; continue
        y["denominator"] += 1
        j = A.get(d)
        if j is None:
            y["no_cnbc_file"] += 1; continue
        b = j["bars"].get("15:50")
        if b is None:
            y["no_1550_bar"] += 1; continue
        o, h, l, c = b
        if not all(math.isfinite(x) for x in b) or h < max(o, c) or l > min(o, c) or h < l:
            y["invalid_1550_bar"] += 1; continue
        y["eligible"] += 1
    tot = {k: sum(v[k] for v in by.values()) for k in next(iter(by.values()))}
    res["by_year"] = by
    res["total"] = tot
    res["coverage"] = tot["eligible"] / tot["denominator"]
    res["coverage_by_year"] = {y: round(v["eligible"] / v["denominator"], 4) if v["denominator"] else None for y, v in by.items()}
    # ---- the vendor's candle against the broker's candle (same minute label), four prices
    R = F.real_spx()
    same = diff = 0
    worst = 0.0
    both = sorted(d for d in R if d in A and "15:50" in A[d]["bars"] and "15:50" in R[d])
    for d in both:
        a, b = A[d]["bars"]["15:50"], R[d]["15:50"]
        g = max(abs(round(x, 2) - round(y, 2)) for x, y in zip(a, b))
        worst = max(worst, g)
        same += g < 0.005
        diff += g >= 0.005
    res["cnbc_vs_broker_1550_bar"] = {"sessions": len(both), "first": both[0] if both else None, "last": both[-1] if both else None,
                                      "all_four_prices_equal": same, "differ": diff, "largest_difference": worst,
                                      "sessions_before_clock_change_2026-11-01": sum(d < "2026-11-01" for d in both),
                                      "sessions_after": sum(d >= "2026-11-01" for d in both)}
    # ---- which minute is it? CNBC's 15:50 close against the feed's close of 15:49, 15:50 and 15:51 (levels)
    feed = {}
    with gzip.open(D / "d1_usa500_rth_1m.csv.gz", "rt", newline="") as f:
        rd = csv.reader(f); next(rd)
        for d, t, o, h, l, c, _ in rd:
            if d >= "2019-01-01" and t in ("15:49", "15:50", "15:51"):
                feed.setdefault(d, {})[t] = float(c)
    al = {}
    dst_weeks = {}
    for d, j in A.items():
        b = j["bars"].get("15:50")
        if b is None or d not in feed or len(feed[d]) < 3:
            continue
        y = al.setdefault(d[:4], {"n": 0, "15:49": 0.0, "15:50": 0.0, "15:51": 0.0})
        y["n"] += 1
        for t in ("15:49", "15:50", "15:51"):
            y[t] += abs(b[3] - feed[d][t])
        dd = date.fromisoformat(d)
        if (dd.month == 3 and 5 <= dd.day <= 21) or (dd.month in (10, 11) and (dd.month == 10 and dd.day >= 25 or dd.month == 11 and dd.day <= 10)):
            w = dst_weeks.setdefault("around_clock_changes", {"n": 0, "15:49": 0.0, "15:50": 0.0, "15:51": 0.0})
            w["n"] += 1
            for t in ("15:49", "15:50", "15:51"):
                w[t] += abs(b[3] - feed[d][t])
    fmt = lambda v: {"n": v["n"], **{t: round(v[t] / v["n"], 3) for t in ("15:49", "15:50", "15:51")}}
    res["mean_abs_gap_cnbc_1550_close_vs_feed_close_at"] = {y: fmt(v) for y, v in sorted(al.items())}
    res["mean_abs_gap_around_clock_changes"] = {k: fmt(v) for k, v in dst_weeks.items()}
    res["years_where_1550_is_not_the_closest_minute"] = [y for y, v in al.items() if not (v["15:50"] < v["15:49"] and v["15:50"] < v["15:51"])]
    # ---- bars per file and requests
    res["files"] = len(A)
    res["requests_per_filled_session"] = {}
    for j in A.values():
        if "15:50" in j["bars"]:
            k = str(j.get("requests", 1))
            res["requests_per_filled_session"][k] = res["requests_per_filled_session"].get(k, 0) + 1
    res["manifest_sha256"], res["manifest_files"] = manifest()
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
