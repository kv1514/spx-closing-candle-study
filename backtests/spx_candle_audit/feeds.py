"""How does the real SPX one-minute candle (Robinhood index bars) compare with the Dukascopy US500 candle the
backtests used? Descriptive, 2026-09-21 onward (the only days with real index minute bars on file).

Run from the repository root:
  .venv/bin/python -I backtests/spx_candle_audit/feeds.py DUKA_EXT_DIR
DUKA_EXT_DIR holds Dukascopy .bi5 files for days after 2026-10-20 (downloaded 2026-11-09 to
data/spx_1549/dukascopy_ext_2026-11-09/; they are not part of the frozen D1 file, which ends 2026-10-20).
"""
import csv, gzip, json, lzma, math, struct, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "spx_1549"
NY = ZoneInfo("America/New_York")
REC = struct.Struct(">iiiiif")   # seconds, open, close, low, high, volume (prices x 1000)


def et_label(dt_utc):
    e = dt_utc.astimezone(NY)
    return e.strftime("%Y-%m-%d"), e.strftime("%H:%M")


def real_spx():
    """date -> {HH:MM: (o,h,l,c)} from the Robinhood SPX index minute files; interpolated bars dropped."""
    out = {}
    files = sorted((D / "robinhood" / "raw").glob("2026-*/spx_1m.json")) + sorted(D.glob("live_*/spx_1m.json"))
    for p in files:
        j = json.load(open(p))
        for res in j["data"]["results"]:
            for b in res["bars"]:
                if b.get("interpolated"):
                    continue
                dt = datetime.strptime(b["begins_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                d, t = et_label(dt)
                out.setdefault(d, {})[t] = tuple(float(b[k]) for k in ("open_value", "high_value", "low_value", "close_value"))
    return out


def duka(ext_dir):
    out = {}
    with gzip.open(D / "d1_usa500_rth_1m.csv.gz", "rt", newline="") as f:
        rd = csv.reader(f); next(rd)
        for d, t, o, h, l, c, tk in rd:
            if d >= "2026-09-01":
                out.setdefault(d, {})[t] = (float(o), float(h), float(l), float(c))
    for p in sorted(Path(ext_dir).glob("*.bi5")):
        day = datetime.strptime(p.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        for secs, o, c, lo, hi, vol in REC.iter_unpack(lzma.decompress(p.read_bytes())):
            d, t = et_label(day + timedelta(seconds=secs))
            if d == p.stem and "09:30" <= t <= "15:59":
                out.setdefault(d, {})[t] = (o / 1000, hi / 1000, lo / 1000, c / 1000)
    return out


def ratio(b):
    o, h, l, c = b
    return abs(c - o) / (h - l) if h > l else math.nan


def main(ext_dir):
    R, K = real_spx(), duka(ext_dir)
    days = sorted(d for d in R if d in K and "15:50" in R[d] and "15:50" in K[d] and len(R[d]) >= 380)
    res = {"days": len(days), "first": days[0], "last": days[-1], "at_1550": [], "thresholds": {}}
    for d in days:
        r, k = R[d]["15:50"], K[d]["15:50"]
        res["at_1550"].append({"date": d, "real_ratio": round(ratio(r), 3), "duka_ratio": round(ratio(k), 3),
                               "real_body": round(r[3] - r[0], 2), "duka_body": round(k[3] - k[0], 2),
                               "real_range": round(r[1] - r[2], 2), "duka_range": round(k[1] - k[2], 2)})
    a = res["at_1550"]
    rr, kr = np.array([ratio(R[d]["15:50"]) for d in days]), np.array([ratio(K[d]["15:50"]) for d in days])
    rs, ks = np.sign([x["real_body"] for x in a]), np.sign([x["duka_body"] for x in a])
    res["summary_1550"] = {
        "real_fires_0.60": int((rr >= 0.6).sum()), "duka_fires_0.60": int((kr >= 0.6).sum()),
        "both": int(((rr >= 0.6) & (kr >= 0.6)).sum()), "real_only": int(((rr >= 0.6) & ~(kr >= 0.6)).sum()),
        "duka_only": int((~(rr >= 0.6) & (kr >= 0.6)).sum()), "same_direction": int((rs == ks).sum()),
        "median_real_ratio": float(np.nanmedian(rr)), "median_duka_ratio": float(np.nanmedian(kr)),
        "mean_real_range": float(np.mean([x["real_range"] for x in a])), "mean_duka_range": float(np.mean([x["duka_range"] for x in a])),
        "mean_abs_real_body": float(np.mean(np.abs([x["real_body"] for x in a]))), "mean_abs_duka_body": float(np.mean(np.abs([x["duka_body"] for x in a]))),
    }
    # at 15:50: if you used threshold x on the real chart, how well would you reproduce the backtest's days?
    res["real_threshold_at_1550"] = {}
    base = kr >= 0.6
    for th in (0.6, 0.65, 0.7, 0.75, 0.8):
        f = rr >= th
        res["real_threshold_at_1550"][str(th)] = {"real_fires": int(f.sum()), "of_those_backtest_days": int((f & base).sum()),
                                                  "backtest_days_caught": int((f & base).sum()), "backtest_days": int(base.sum()),
                                                  "extra_days": int((f & ~base).sum())}
    # every minute of the last half hour, to learn how the two feeds' ratios relate (many more candles)
    for name, lo in (("15:30-15:59", "15:30"), ("15:45-15:55", "15:45")):
        hi = "15:59" if name.startswith("15:30") else "15:55"
        pr, pk = [], []
        for d in days:
            for t in R[d]:
                if lo <= t <= hi and t in K[d]:
                    x, y = ratio(R[d][t]), ratio(K[d][t])
                    if math.isfinite(x) and math.isfinite(y):
                        pr.append(x); pk.append(y)
        pr, pk = np.array(pr), np.array(pk)
        tab = {}
        base = pk >= 0.6
        for th in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9):
            f = pr >= th
            tab[str(th)] = {"real_fires": float(f.mean()), "agree_with_duka_0.60": float((f == base).mean()),
                            "of_real_fires_duka_also": float(base[f].mean()) if f.any() else None,
                            "of_duka_fires_real_also": float(f[base].mean())}
        cond = {}
        for a_, b_ in ((0.0, 0.4), (0.4, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
            m = (pr >= a_) & (pr < b_)
            cond[f"{a_:.1f}-{min(b_, 1.0):.1f}"] = {"candles": int(m.sum()), "share_duka_at_least_0.60": float(base[m].mean()),
                                                     "median_duka_ratio": float(np.median(pk[m]))}
        res["thresholds"][name] = {"candles": len(pr), "duka_ratio_given_real_ratio": cond, "duka_fires_0.60": float(base.mean()),
                                   "median_real_ratio": float(np.median(pr)), "median_duka_ratio": float(np.median(pk)),
                                   "corr": float(np.corrcoef(pr, pk)[0, 1]), "real_threshold_table": tab,
                                   "real_quantile_matching_duka_0.60": float(np.quantile(pr, 1 - base.mean()))}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
