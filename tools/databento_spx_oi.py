"""Pull daily open interest for ALL SPX and SPXW options from Databento OPRA `statistics`, inside the shared budget.

Data acquisition only: this script computes no gamma, return or P&L. The analysis that uses it (the dealer-gamma
part of the intraday-momentum study) needs its own locked pre-registration first.

OPRA publishes each contract's open interest once a day before the open; it reflects positions at the end of the
prior session. This script asks for the parent symbols SPX.OPT and SPXW.OPT in a 00:00-09:31 ET window per D1 day,
keeps only the open-interest rows (stat_type 9) and saves them gzipped. Before 2023 that window costs the same as the
whole day; from 2023 the whole day costs ~17x more, so the window matters.

Shares the key, the API helper, the spend log and the budget rule with tools/databento_spxw.py. Every request is
priced first with the free metadata.get_cost and refused if the logged total would pass --budget (default $100 of
the $125 free credit). Do not run this at the same time as another pull: the budget is checked within one process.

Usage (from /Users/kv15/trading):
  .venv/bin/python -B tools/databento_spx_oi.py selftest
  .venv/bin/python -B tools/databento_spx_oi.py estimate              # free: sampled cost of all days
  .venv/bin/python -B tools/databento_spx_oi.py probe [--day YYYY-MM-DD]   # one paid day (~$0.002-0.02), then a summary
  .venv/bin/python -B tools/databento_spx_oi.py pull [--budget 100] [--workers 4] [--limit-days N]
"""
from __future__ import annotations

import csv
import gzip
import importlib.util
import io
import json
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("databento_spxw_shared", Path(__file__).with_name("databento_spxw.py"))
dbx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbx)

SCHEMA = "statistics"
PARENTS = "SPX.OPT,SPXW.OPT"
WINDOW_ET = ("00:00", "09:31")      # from PILLAR_LIVE: OI arrives ~06:30 ET (probed 2026-10-20)
FULL_DAY_ET = ("00:00", "23:59")    # before PILLAR_LIVE: OI is stamped 09:31 ET (probed 2013-06-03) and the full day
PILLAR_LIVE = "2023-03-28"          #   costs the same as the pre-open window; from here the full day costs ~17x more
FALLBACK_ET = ("09:31", "10:01")    # tried only when the main window has no OI rows
OI_STAT = "9"                       # Databento StatType.OPEN_INTEREST
FOLDER = dbx.OUT / "statistics_oi_spx_spxw"
DEFAULT_WORKERS = 4


def window_for(day: str) -> tuple[str, str]:
    return FULL_DAY_ET if day < PILLAR_LIVE else WINDOW_ET


def cost(day: str, window=None) -> float:
    a, b = dbx.window_ns(day, window or window_for(day))
    return float(dbx.call("metadata.get_cost", {"dataset": dbx.DATASET, "symbols": PARENTS, "schema": SCHEMA,
                                               "start": a, "end": b, "stype_in": "parent"}))


def fetch(day: str, window=None) -> bytes:
    """One paid request. A dropped connection is NOT retried here (it may already be billed); the caller logs the
    charge and the day is retried on the next run with a fresh reservation."""
    a, b = dbx.window_ns(day, window or window_for(day))
    return dbx.call("timeseries.get_range", {"dataset": dbx.DATASET, "symbols": PARENTS, "schema": SCHEMA,
                                            "start": a, "end": b, "stype_in": "parent", "encoding": "csv",
                                            "compression": "none", "pretty_px": "true", "pretty_ts": "true",
                                            "map_symbols": "true"}, raw=True, retry_network=False)


def keep_oi(body: bytes) -> tuple[str, dict]:
    """The open-interest rows of a statistics CSV (all columns kept), plus counts by stat_type."""
    text = body.decode("utf-8", "replace")
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    if header is None:
        return "", {"rows": 0, "oi_rows": 0, "by_stat_type": {}}
    st = header.index("stat_type")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    by = Counter()
    n = 0
    for r in rd:
        if not r:
            continue
        n += 1
        by[r[st]] += 1
        if r[st] == OI_STAT:
            w.writerow(r)
    return out.getvalue(), {"rows": n, "oi_rows": by.get(OI_STAT, 0), "by_stat_type": dict(by)}


def day_file(day: str) -> Path:
    return FOLDER / f"{day}.csv.gz"


def log_spend(day: str, c: float, rows: int, label: str, window) -> None:
    """Record a paid request BEFORE its file is published, so a charge is never missing from the log (a crash in
    between leaves the charge logged and the day to be fetched again: the log over-counts, never under-counts)."""
    new = not dbx.SPEND_LOG.exists()
    with open(dbx.SPEND_LOG, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=dbx.SPEND_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({"utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "schema": f"{SCHEMA}_oi_{window[0].replace(':', '')}-{window[1].replace(':', '')}",
                    "day": day, "n_symbols": 0, "quoted_cost_usd": f"{c:.6f}", "rows": rows, "file": label})
        fh.flush()


def publish(day: str, kept: str) -> Path:
    FOLDER.mkdir(parents=True, exist_ok=True)
    f, tmp = day_file(day), FOLDER / f"{day}.tmp"
    tmp.write_bytes(gzip.compress(kept.encode(), 6))
    tmp.replace(f)
    return f


def download_day(d: str, reserve, lock) -> dict:
    """Fetch one day's open interest: the main window, then the fallback window if a post-2023-03-28 day has none.
    reserve(cost) -> bool books the cost against the budget first. Every paid request is logged, whatever happens.
    Returns {"status": saved|empty|failed|stopped, "window", "counts", "bytes", "error"}."""
    win = window_for(d)
    tries = [win] + ([FALLBACK_ET] if win != FULL_DAY_ET else [])
    for k, w_ in enumerate(tries):
        c = cost(d, w_)
        if not reserve(c):
            return {"status": "stopped", "window": w_}
        try:
            body = fetch(d, w_)
        except SystemExit as e:
            with lock:
                log_spend(d, c, 0, "(failed: may be billed; retried next run)", w_)
            return {"status": "failed", "window": w_, "error": str(e)}
        kept, counts = keep_oi(body)
        with lock:
            if counts["oi_rows"] == 0:
                log_spend(d, c, 0, "(no open interest in this window)", w_)
                if k == len(tries) - 1:
                    return {"status": "empty", "window": w_, "counts": counts, "bytes": len(body)}
                continue
            log_spend(d, c, counts["oi_rows"], str(day_file(d).relative_to(dbx.ROOT)), w_)
            publish(d, kept)
            if w_ == FALLBACK_ET:
                with open(FOLDER / "fallback_days.txt", "a") as fh:
                    fh.write(d + "\n")
        return {"status": "saved", "window": w_, "counts": counts, "bytes": len(body), "kept": kept}
    return {"status": "empty", "window": tries[-1]}


def write_manifest(days: list) -> None:
    FOLDER.mkdir(parents=True, exist_ok=True)
    m = {"dataset": dbx.DATASET, "schema": SCHEMA, "parents": PARENTS, "kept": "stat_type 9 (open interest)",
         "window_rule_et": {f"before {PILLAR_LIVE}": FULL_DAY_ET, f"from {PILLAR_LIVE}": WINDOW_ET,
                            "fallback if no open interest (listed in fallback_days.txt)": FALLBACK_ET},
         "days": days}
    tmp = FOLDER / "manifest.tmp"
    tmp.write_text(json.dumps(m, indent=1) + "\n")
    tmp.replace(FOLDER / "manifest.json")


def all_days() -> list[str]:
    return [d for d, _ in dbx.days_and_spot()]


def cmd_estimate():
    days = all_days()
    sample = days[::max(1, len(days) // 30)]
    cs = [cost(d) for d in sample]
    mean = sum(cs) / len(cs)
    print(f"{SCHEMA} OI window {WINDOW_ET[0]}-{WINDOW_ET[1]} ET: sampled {len(sample)} days, mean ${mean:.5f} a day "
          f"-> about ${mean * len(days):.2f} for all {len(days)} days (already spent ${dbx.spent():.2f})")


def cmd_probe(day: str, budget: float):
    if day_file(day).exists():
        raise SystemExit(f"{day_file(day).relative_to(dbx.ROOT)} already exists; probe a day not yet downloaded")
    lock = threading.Lock()

    def reserve(c):
        return dbx.allowed(dbx.spent(), c, budget)          # the log is written per request, so spent() is current

    r = download_day(day, reserve, lock)
    print(f"probe {day}: {r['status']} (window {r['window'][0]}-{r['window'][1]} ET)")
    if r["status"] != "saved":
        print("  ", r.get("error") or r.get("counts"))
        return
    rows = list(csv.DictReader(io.StringIO(r["kept"])))
    syms = {x["symbol"] for x in rows}
    roots = Counter(x.split()[0] for x in syms if x)
    ts = Counter(x["ts_recv"][11:16] for x in rows)
    print(f"  {r['bytes']:,} bytes, stat types {r['counts']['by_stat_type']}, open-interest rows "
          f"{r['counts']['oi_rows']:,}, distinct contracts {len(syms):,}, roots {dict(roots)}")
    print(f"  OI timestamps (UTC HH:MM, top 5) {ts.most_common(5)}; columns {list(rows[0].keys())}")


def cmd_pull(budget: float, workers: int, limit_days: int | None):
    days = all_days()
    write_manifest(days)
    todo = [d for d in days if not day_file(d).exists()]
    if limit_days is not None:
        todo = todo[:limit_days]
    lock = threading.Lock()
    state = {"spent": dbx.spent(), "saved": 0, "stop": None, "failed": [], "empty": []}

    def reserve(c):
        with lock:
            if state["stop"] or not dbx.allowed(state["spent"], c, budget):
                state["stop"] = state["stop"] or (f"STOP: ${state['spent']:.2f} reserved + ${c:.4f} would pass the "
                                                  f"${budget:.2f} budget")
                return False
            state["spent"] += c
            return True

    def one(d):
        if state["stop"]:
            return
        r = download_day(d, reserve, lock)
        with lock:
            if r["status"] == "failed":
                state["failed"].append(d)
                print(f"FAILED {d}: {r['error']}", flush=True)
            elif r["status"] == "empty":
                state["empty"].append(d)
            elif r["status"] == "saved":
                state["saved"] += 1
                if state["saved"] % 100 == 0:
                    print(f"{state['saved']} days saved this run, ${state['spent']:.2f} reserved", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in ex.map(one, todo):
            pass
    if state["stop"]:
        print(state["stop"])
    if state["failed"]:
        print(f"{len(state['failed'])} days failed (run pull again to retry): {', '.join(state['failed'][:20])}")
    if state["empty"]:
        print(f"{len(state['empty'])} days had no open-interest rows in any window: {', '.join(state['empty'][:20])}")
    have = len(list(FOLDER.glob("*.csv.gz")))
    print(f"open interest: {have} of {len(days)} days saved; total logged spend ${dbx.spent():.4f} of "
          f"${budget:.2f} budget", flush=True)


def selftest():
    body = (b"ts_recv,ts_event,rtype,publisher_id,instrument_id,ts_ref,price,quantity,sequence,ts_in_delta,stat_type,"
            b"channel_id,update_action,stat_flags,symbol\n"
            b"2026-10-20T10:30:00.000000000Z,,24,30,1,,,1500,1,0,9,1,1,0,SPXW  261020C06700000\n"
            b"2026-10-20T10:30:00.000000000Z,,24,30,2,,1.25,,2,0,3,1,1,0,SPXW  261020P06700000\n"
            b"2026-10-20T10:30:00.000000000Z,,24,30,3,,,250,3,0,9,1,1,0,SPX   261120P06000000\n")
    kept, n = keep_oi(body)
    rows = list(csv.DictReader(io.StringIO(kept)))
    assert n == {"rows": 3, "oi_rows": 2, "by_stat_type": {"9": 2, "3": 1}}
    assert [r["quantity"] for r in rows] == ["1500", "250"] and rows[1]["symbol"].startswith("SPX ")
    assert keep_oi(b"") == ("", {"rows": 0, "oi_rows": 0, "by_stat_type": {}})
    a, b = dbx.window_ns("2026-10-20", WINDOW_ET)        # EDT: 00:00 ET = 04:00 UTC
    assert datetime.fromtimestamp(a / 1e9, timezone.utc).strftime("%H:%M") == "04:00"
    assert (b - a) == (9 * 60 + 31) * 60 * 10**9
    assert window_for("2013-06-03") == FULL_DAY_ET and window_for("2023-03-27") == FULL_DAY_ET
    assert window_for("2023-03-28") == WINDOW_ET and window_for("2026-10-20") == WINDOW_ET
    assert FOLDER.parent == dbx.OUT
    print("selftest: all checks passed")


if __name__ == "__main__":
    args = sys.argv[1:]

    def opt(name, default, cast):
        return cast(args[args.index(name) + 1]) if name in args else default

    cmd = args[0] if args else "selftest"
    if cmd == "selftest":
        selftest()
    elif cmd == "estimate":
        cmd_estimate()
    elif cmd == "probe":
        cmd_probe(opt("--day", "2026-10-20", str), opt("--budget", dbx.DEFAULT_BUDGET, float))
    elif cmd == "pull":
        cmd_pull(opt("--budget", dbx.DEFAULT_BUDGET, float), opt("--workers", DEFAULT_WORKERS, int),
                 opt("--limit-days", None, int))
    else:
        raise SystemExit(__doc__)
