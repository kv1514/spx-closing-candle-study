"""Pull real SPXW 0DTE option quotes for the last hour of each session from Databento (OPRA), inside a hard budget.

Data acquisition only: this script computes no P&L. Any analysis of what it saves needs its own
pre-registration first.

The API key is read from the environment variable DATABENTO_API_KEY, or else from ~/.config/databento/key.
It is never printed, logged or written anywhere.

Every download is priced first with Databento's free metadata.get_cost. The script refuses any request that
would take the logged total past --budget (default $100 of the $125 free credit).

Usage (from /Users/kv15/trading):
  .venv/bin/python -B tools/databento_spxw.py selftest          # offline checks, no key needed
  .venv/bin/python -B tools/databento_spxw.py plan              # days and symbols, no key needed
  .venv/bin/python -B tools/databento_spxw.py probe             # schemas, date range, symbol check, one-day cost
  .venv/bin/python -B tools/databento_spxw.py estimate --schema cbbo-1m   # sampled cost of the whole pull
  .venv/bin/python -B tools/databento_spxw.py pull --schema cbbo-1m [--budget 100] [--limit-days N] [--workers 6]

Saves gzipped CSVs to data/spx_1549/databento/<schema>_<window>_k<half width>/<YYYY-MM-DD>.csv.gz (git-ignored),
a <day>.none marker for a day with no same-day expiry, plus spend_log.csv and manifest.json.
"""
from __future__ import annotations

import base64
import csv
import gzip
import http.client
import importlib.util
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/Users/kv15/trading")
SCAN_PY = ROOT / "backtests" / "spx_candle_scan" / "scan.py"
OUT = ROOT / "data" / "spx_1549" / "databento"
SPEND_LOG = OUT / "spend_log.csv"
KEY_FILE = Path.home() / ".config" / "databento" / "key"
API = "https://hist.databento.com/v0/"
DATASET = "OPRA.PILLAR"
ET = ZoneInfo("America/New_York")

START_DAY = "2013-04-01"          # first OPRA.PILLAR cbbo-1m day at Databento
END_DAY = "2026-10-20"            # last D1 day (the center strike comes from D1's 15:51 open)
WINDOW_ET = ("15:00", "16:01")    # bars 15:00 .. 16:00 ET (end exclusive): the last hour
HALF_WIDTH = 60                   # strikes K_center +- 60 in steps of 5 -> 25 strikes x call/put = 50 symbols
STEP = 5
DEFAULT_BUDGET = 100.0
DEFAULT_WORKERS = 6
NO_CONTRACTS = "None of the symbols could be resolved"   # Databento's answer on a day with no SPXW expiry
SPEND_COLUMNS = ["utc_time", "schema", "day", "n_symbols", "quoted_cost_usd", "rows", "file"]


# ------------------------------------------------------------------------------------------------
# pure helpers (self-tested)
# ------------------------------------------------------------------------------------------------
def occ(day: str, kind: str, strike: float) -> str:
    """OSI raw symbol as OPRA prints it: root padded to 6, YYMMDD, C/P, strike x 1000 in 8 digits."""
    return f"{'SPXW':<6}{day[2:4]}{day[5:7]}{day[8:10]}{'C' if kind == 'call' else 'P'}{round(strike * 1000):08d}"


def center_strike(s: float) -> float:
    return float(int(s / STEP + 0.5) * STEP)


def symbols_for(day: str, s_1551: float, half_width: int = HALF_WIDTH) -> list[str]:
    k0 = center_strike(s_1551)
    ks = [k0 + d for d in range(-half_width, half_width + 1, STEP)]
    return [occ(day, kind, k) for k in ks for kind in ("call", "put")]


def window_ns(day: str, window=WINDOW_ET) -> tuple[int, int]:
    def ns(hm):
        h, m = map(int, hm.split(":"))
        t = datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), h, m, tzinfo=ET)
        return int(t.astimezone(timezone.utc).timestamp()) * 1_000_000_000
    return ns(window[0]), ns(window[1])


def folder_for(schema: str) -> Path:
    return OUT / f"{schema}_{WINDOW_ET[0].replace(':', '')}-{WINDOW_ET[1].replace(':', '')}_k{HALF_WIDTH}"


def spent(log: Path = SPEND_LOG) -> float:
    if not log.exists():
        return 0.0
    with open(log, newline="") as fh:
        return sum(float(r["quoted_cost_usd"]) for r in csv.DictReader(fh))


def allowed(already: float, cost: float, budget: float) -> bool:
    return cost >= 0 and already + cost <= budget + 1e-12


# ------------------------------------------------------------------------------------------------
# API (key never printed)
# ------------------------------------------------------------------------------------------------
def api_key() -> str:
    k = os.environ.get("DATABENTO_API_KEY", "").strip()
    if not k and KEY_FILE.exists():
        k = KEY_FILE.read_text().strip()
    if not k:
        raise SystemExit(f"no Databento key: set DATABENTO_API_KEY or save it to {KEY_FILE} (chmod 600)")
    return k


def call(endpoint: str, params: dict, *, post: bool = True, raw: bool = False, retry_network: bool = True):
    """POST/GET a Databento endpoint. HTTP 429/5xx answers are retried (nothing was delivered). Dropped connections
    and partial reads are retried only when retry_network is True: a paid download that broke midway may already be
    billed, so budget-sensitive callers pass False and re-reserve before trying again."""
    auth = base64.b64encode((api_key() + ":").encode()).decode()
    data = urllib.parse.urlencode(params).encode()
    url = API + endpoint + ("" if post else "?" + data.decode())
    req = urllib.request.Request(url, data=data if post else None, method="POST" if post else "GET",
                                 headers={"Authorization": f"Basic {auth}", "User-Agent": "spx-research/1.0"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit(f"Databento {endpoint}: HTTP {e.code}: {msg}")
        except (http.client.HTTPException, OSError) as e:      # dropped connections, partial reads, timeouts
            if retry_network and attempt < 5:
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit(f"Databento {endpoint}: network error {type(e).__name__}: {e}")
    raise SystemExit(f"Databento {endpoint}: gave up after retries")


def get_cost(schema: str, syms: list[str], start: int, end: int) -> float:
    return float(call("metadata.get_cost", {"dataset": DATASET, "symbols": ",".join(syms), "schema": schema,
                                             "start": start, "end": end, "stype_in": "raw_symbol"}))


# ------------------------------------------------------------------------------------------------
# days
# ------------------------------------------------------------------------------------------------
def days_and_spot() -> list[tuple[str, float]]:
    spec = importlib.util.spec_from_file_location("spx_candle_scan_ro", SCAN_PY)
    scan = importlib.util.module_from_spec(spec)
    sys.modules["spx_candle_scan_ro"] = scan
    spec.loader.exec_module(scan)
    P = scan.load_panel(START_DAY, END_DAY)
    out = []
    for d, s in zip(P.dates, P.O[:, scan.I1551]):
        if s == s and s > 0:
            out.append((str(d), float(s)))
    return out


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------
def cmd_plan():
    days = days_and_spot()
    print(f"{len(days)} days {days[0][0]} .. {days[-1][0]}, {2 * (2 * HALF_WIDTH // STEP + 1)} symbols a day, "
          f"window {WINDOW_ET[0]}-{WINDOW_ET[1]} ET")
    d, s = days[-1]
    print(f"example {d}: D1 15:51 open {s:.2f} -> {symbols_for(d, s)[:4]} ...")


def cmd_probe():
    print("schemas:", call("metadata.list_schemas", {"dataset": DATASET}, post=False))
    days = days_and_spot()
    d, s = days[-1]
    syms = symbols_for(d, s)
    a, b = window_ns(d)
    for schema in ("cbbo-1m", "ohlcv-1m"):
        print(f"cost {d} {len(syms)} symbols {schema}: ${get_cost(schema, syms, a, b):.4f}")


def cmd_estimate(schema: str):
    days = days_and_spot()
    sample = days[::max(1, len(days) // 30)]
    costs = []
    for d, s in sample:
        a, b = window_ns(d)
        try:
            costs.append(get_cost(schema, symbols_for(d, s), a, b))
        except SystemExit as e:
            if NO_CONTRACTS not in str(e):
                raise
            costs.append(0.0)
    mean = sum(costs) / len(costs)
    print(f"{schema}: sampled {len(sample)} days, mean ${mean:.5f} a day -> about ${mean * len(days):.2f} "
          f"for all {len(days)} days (already spent ${spent():.2f})")


def cmd_pull(schema: str, budget: float, limit_days: int | None, workers: int):
    days = days_and_spot()
    folder = folder_for(schema)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"dataset": DATASET, "schema": schema, "window_et": WINDOW_ET, "half_width": HALF_WIDTH,
                "center": "D1 15:51 open rounded to 5", "start": START_DAY, "end": END_DAY,
                "days": [d for d, _ in days]}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    todo = [(d, s) for d, s in days
            if not (folder / f"{d}.csv.gz").exists() and not (folder / f"{d}.none").exists()]
    if limit_days is not None:
        todo = todo[:limit_days]
    lock = threading.Lock()
    state = {"spent": spent(), "saved": 0, "none": 0, "stop": None, "failed": []}

    def one(item):
        d, s = item
        if state["stop"]:
            return
        syms = symbols_for(d, s)
        a, b = window_ns(d)
        try:
            cost = get_cost(schema, syms, a, b)
        except SystemExit as e:
            if NO_CONTRACTS in str(e):
                (folder / f"{d}.none").write_text("no SPXW contract expiring this day among the requested symbols\n")
                with lock:
                    state["none"] += 1
                return
            raise
        with lock:
            if state["stop"] or not allowed(state["spent"], cost, budget):
                state["stop"] = state["stop"] or (f"STOP before {d}: ${state['spent']:.2f} spent + ${cost:.4f} "
                                                  f"would pass the ${budget:.2f} budget")
                return
            state["spent"] += cost                      # reserve before downloading
        try:
            body = call("timeseries.get_range", {"dataset": DATASET, "symbols": ",".join(syms), "schema": schema,
                                                 "start": a, "end": b, "stype_in": "raw_symbol", "encoding": "csv",
                                                 "compression": "none", "pretty_px": "true", "pretty_ts": "true",
                                                 "map_symbols": "true"}, raw=True)
        except SystemExit as e:                         # keep the reservation (it may have been billed); retry next run
            with lock:
                state["failed"].append(d)
            print(f"FAILED {d}: {e}", flush=True)
            return
        f = folder / f"{d}.csv.gz"
        tmp = folder / f"{d}.tmp"
        tmp.write_bytes(gzip.compress(body, 6))
        tmp.replace(f)
        rows = max(0, body.count(b"\n") - 1)
        with lock:
            new = not SPEND_LOG.exists()
            with open(SPEND_LOG, "a", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=SPEND_COLUMNS)
                if new:
                    w.writeheader()
                w.writerow({"utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "schema": schema, "day": d, "n_symbols": len(syms), "quoted_cost_usd": f"{cost:.6f}",
                            "rows": rows, "file": str(f.relative_to(ROOT))})
            state["saved"] += 1
            if state["saved"] % 100 == 0:
                print(f"{state['saved']} days saved this run, ${state['spent']:.2f} spent", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in ex.map(one, todo):
            pass
    if state["stop"]:
        print(state["stop"])
    if state["failed"]:
        print(f"{len(state['failed'])} days failed after retries (run pull again to retry them): "
              f"{', '.join(state['failed'][:20])}")
    have = len(list(folder.glob("*.csv.gz")))
    nones = len(list(folder.glob("*.none")))
    print(f"{schema}: {have} of {len(days)} days saved, {nones} days with no same-day expiry; "
          f"total quoted spend ${spent():.4f} of ${budget:.2f} budget", flush=True)


def selftest():
    assert occ("2026-10-20", "call", 6705.0) == "SPXW  261020C06705000"
    assert occ("2013-04-05", "put", 1555.0) == "SPXW  130405P01555000"
    assert len(occ("2026-10-20", "call", 6705.0)) == 21
    assert center_strike(6702.5) == 6705.0 and center_strike(6702.49) == 6700.0
    syms = symbols_for("2026-10-20", 6701.2)
    assert len(syms) == 50 and syms[0] == "SPXW  261020C06640000" and syms[-1] == "SPXW  261020P06760000"
    a, b = window_ns("2026-10-20")        # EDT: 15:00 ET = 19:00 UTC
    assert datetime.fromtimestamp(a / 1e9, timezone.utc).strftime("%H:%M") == "19:00" and b - a == 61 * 60 * 10**9
    a, _ = window_ns("2026-12-01")        # EST: 15:00 ET = 20:00 UTC
    assert datetime.fromtimestamp(a / 1e9, timezone.utc).strftime("%H:%M") == "20:00"
    assert folder_for("cbbo-1m").name == "cbbo-1m_1500-1601_k60"
    assert allowed(90.0, 9.99, 100.0) and not allowed(90.0, 10.01, 100.0) and not allowed(0.0, -1.0, 100.0)
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "log.csv"
        p.write_text("utc_time,schema,day,n_symbols,quoted_cost_usd,rows,file\nx,s,d,34,1.25,10,f\nx,s,d,34,0.5,9,f\n")
        assert abs(spent(p) - 1.75) < 1e-12
        assert spent(Path(t) / "none.csv") == 0.0
    print("selftest: all checks passed")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    if cmd == "selftest":
        selftest()
    elif cmd == "plan":
        cmd_plan()
    elif cmd == "probe":
        cmd_probe()
    elif cmd == "estimate":
        cmd_estimate(opt("--schema", "cbbo-1m"))
    elif cmd == "pull":
        lim = opt("--limit-days")
        cmd_pull(opt("--schema", "cbbo-1m"), float(opt("--budget", DEFAULT_BUDGET)), int(lim) if lim else None,
                 int(opt("--workers", DEFAULT_WORKERS)))
    else:
        raise SystemExit(__doc__)
