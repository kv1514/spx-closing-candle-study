"""Buy the 15:45-16:01 SPXW quotes for a few signal days after the backtest's last day, inside the logged cap.

Uses tools/databento_spxw.py for the request, the free cost quote and the key handling (the key is never printed).
Files go to their own folder, data/spx_1549/databento/cbbo-1m_1545-1601_k60_forward/, so the folders that earlier
studies hashed are not touched. Every download is added to spend_log.csv.

Run from the repository root:
  .venv/bin/python -B backtests/spx_candle_spy/fetch_forward_quotes.py estimate DAY:SPOT [DAY:SPOT ...]
  .venv/bin/python -B backtests/spx_candle_spy/fetch_forward_quotes.py pull     DAY:SPOT [DAY:SPOT ...]
SPOT is the SPX level at 15:51 (the strikes requested are the 25 within 60 points of it, calls and puts).
"""
import csv, gzip, importlib.util, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("dbn", ROOT / "tools" / "databento_spxw.py")
dbn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbn)

FOLDER = dbn.OUT / "cbbo-1m_1545-1601_k60_forward"
WINDOW = ("15:45", "16:01")
CAP = 120.0                      # the logged spending cap; the free credit is $125
SCHEMA = "cbbo-1m"


def main(mode, items):
    FOLDER.mkdir(parents=True, exist_ok=True)
    already = dbn.spent()
    plan, total = [], 0.0
    for it in items:
        day, spot = it.split(":")
        if (FOLDER / f"{day}.csv.gz").exists():
            print(day, "already on disk")
            continue
        syms = dbn.symbols_for(day, float(spot))
        a, b = dbn.window_ns(day, WINDOW)
        cost = dbn.get_cost(SCHEMA, syms, a, b)          # free metadata call
        plan.append((day, syms, a, b, cost))
        total += cost
        print(f"{day}: {len(syms)} symbols, quoted ${cost:.4f}")
    print(f"quoted total ${total:.4f}; logged spend so far ${already:.4f}; cap ${CAP:.2f}")
    if mode != "pull":
        return 0
    if not dbn.allowed(already, total, CAP):
        raise SystemExit("stop: this would pass the cap")
    for day, syms, a, b, cost in plan:
        body = dbn.call("timeseries.get_range", {"dataset": dbn.DATASET, "symbols": ",".join(syms), "schema": SCHEMA,
                                                 "start": a, "end": b, "stype_in": "raw_symbol", "encoding": "csv",
                                                 "compression": "none", "pretty_px": "true", "pretty_ts": "true",
                                                 "map_symbols": "true"}, raw=True)
        f = FOLDER / f"{day}.csv.gz"
        tmp = FOLDER / f"{day}.tmp"
        tmp.write_bytes(gzip.compress(body, 6))
        tmp.replace(f)
        rows = max(0, body.count(b"\n") - 1)
        with open(dbn.SPEND_LOG, "a", newline="") as fh:
            csv.DictWriter(fh, fieldnames=dbn.SPEND_COLUMNS).writerow(
                {"utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "schema": SCHEMA + "_forward", "day": day,
                 "n_symbols": len(syms), "quoted_cost_usd": f"{cost:.6f}", "rows": rows, "file": str(f.relative_to(ROOT))})
        print(f"{day}: saved {rows} rows")
    print(f"logged spend now ${dbn.spent():.4f} of the ${CAP:.2f} cap")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
