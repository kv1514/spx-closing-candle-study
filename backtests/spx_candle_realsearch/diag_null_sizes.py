"""Diagnostic only: in the index-move shift benchmark, which cells give each shift's largest t (sample sizes)?"""
import sys, math
import numpy as np
sys.path.insert(0, "/Users/kv15/trading/backtests/spx_candle_realsearch")
import realsearch as RS
g = RS.Guard("2021-01-01", "2026-10-20", "diag")
rows = RS.day_rows()
days = RS.base_dates(rows, "2021-01-01", "2026-10-20")
idx = RS.load_archive(RS.IDX_ARCH, days, g); spy = RS.load_archive(RS.SPY_ARCH, days, g)
raw, _ = RS.raw_signals([idx, spy], days)
mv = np.full((len(days), len(RS.ENTRIES)), np.nan)
for i, d in enumerate(days):
    b = idx.get(d, {}); last = b.get("15:59")
    if last is None or not RS.SC.bar_ok(last): continue
    for e, m in enumerate(RS.ENTRIES):
        x = b.get(m)
        if x is None or not RS.SC.bar_ok(x) or not x[0] > 0: continue
        mv[i, e] = 1e4 * (last[3] - x[0]) / x[0]
ns, big = [], []
for s_ in RS.shifts_for(len(days))[::4]:
    sig = RS.with_both(np.roll(raw, s_, axis=0))
    best = (-1e9, None, None)
    bestbig = -1e9
    for si in range(3):
        for a in range(11):
            for b in range(12):
                s = sig[:, si, a, b]
                keep = np.isfinite(s) & (s != 0) & np.isfinite(mv[:, a])
                r = RS.nw(s[keep] * mv[keep, a])
                if r["t"] is None: continue
                if r["t"] > best[0]: best = (r["t"], int(keep.sum()), (si, a, b))
                if keep.sum() >= 300: bestbig = max(bestbig, r["t"])
    ns.append(best[1]); big.append(bestbig)
import json
from pathlib import Path
out = {"note": "post-hoc diagnostic, chosen after the registered run; decides nothing", "shifts_checked": len(ns),
       "every_kth_shift": 4, "median_days_in_max_t_cell": float(np.median(ns)),
       "share_of_max_t_cells_under_100_days": float(np.mean(np.array(ns) < 100)), "min_days_large": 300,
       "large_cells_null_max_t_median": float(np.median(big)), "large_cells_null_max_t_q95": float(np.quantile(big, .95))}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1))
print("shifts checked", len(ns))
print("days in the max-t cell: median", np.median(ns), "share under 100 days", np.mean(np.array(ns) < 100))
print("max t among cells with >=300 days: median %.2f, 95th %.2f" % (np.median(big), np.quantile(big, .95)))
