"""Pre-lock counts for the draft closing-imbalance plan (PREREG_DRAFT.md).

COUNTS ONLY. load_panel loads the whole one-minute panel, but only the 15:50 bar (open, high, low, close) is
used, to list the signal days and their candle direction. No later bar is used and no return, hit, P&L or other
outcome is computed. The trade list is parsed row by row, but only its date, config and period columns are used.
Outputs: signal_days.csv (date, direction) and prelock_counts.json.
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spx_candle_scan"))
import scan  # noqa: E402  (loader and candle helpers; importing runs nothing)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
START, END = "2021-01-04", "2026-10-20"
REALPRICE = ROOT / "data" / "spx_1549" / "databento" / "realprice_trades.csv"


def main():
    P = scan.load_panel(START, END)
    o, h, l_, c = scan.candle_1m(P, scan.mi("15:50"))
    with np.errstate(invalid="ignore"):
        strong = np.isfinite(o + h + l_ + c) & (h - l_ > 0) & (np.abs(c - o) >= 0.6 * (h - l_))
    days = [(str(d), 1 if cc > oo else -1) for d, oo, cc, s in zip(P.dates, o, c, strong) if s]
    with open(HERE / "signal_days.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "direction"])
        w.writerows(days)
    # dates only from the real-price trade list (no P&L column is read)
    with open(REALPRICE, newline="") as fh:
        priced = {r["date"] for r in csv.DictReader(fh)
                  if r["config"] == "current" and r["period"] == "confirmation"}
    sig = {d for d, _ in days}
    out = {"what": "counts only (signal days from the 15:50 bar); no outcome computed",
           "d1_file_sha256": scan.sha256_file(scan.D1_FILE),
           "days_file_sha256": scan.sha256_file(scan.D1_DAYS),
           "panel": {k: P.meta[k] for k in ("first", "last", "n_days")},
           "signal_days": len(days),
           "up": sum(1 for _, s in days if s > 0), "down": sum(1 for _, s in days if s < 0),
           "by_year": dict(sorted(Counter(d[:4] for d, _ in days).items())),
           "realprice_confirmation_dates": len(priced),
           "realprice_dates_that_are_signal_days": len(priced & sig),
           "realprice_dates_not_signal_days": sorted(priced - sig)[:20]}
    (HERE / "prelock_counts.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
