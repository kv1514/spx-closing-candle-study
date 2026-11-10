"""Pull real XSP (Mini-SPX) and SPY 0DTE option quotes (and trade bars) for the last hour of each session from
Databento (OPRA), inside the shared budget.

Data acquisition only: this script computes no P&L, hit rate, fill or spread statistic. Any analysis of what it
saves needs its own locked pre-registration first (draft: backtests/spx_candle_mini/PREREG_DRAFT.md).

Shares the key, the API helper, the cost call, the spend log, the budget rule and the day list with
tools/databento_spxw.py (imported, not copied). The API key is never printed, logged or written anywhere. Every
request is priced first with the free metadata.get_cost and refused if the logged total across every schema would
pass --budget (default $100; later raised to $120 of the $125 free credit). A paid request is booked
against the budget before it is sent, is not retried on a dropped connection (it may already be billed), and is
written to the spend log before its file is published: the log can over-count, never under-count. The budget is
checked within one process: two pulls at the same time must split the headroom between their --budget values.

Days: the D1 days 2021-01-04 .. 2026-10-20 that databento_spxw.days_and_spot() returns.
Contracts expiring that same day, strike step $1, calls and puts, window 15:00-16:01 ET:
  XSP  center = floor(S / 10 + 0.5); S = D1's 15:51 open.
  SPY  center = floor(S * r + 0.5); r = SPY close / official SPX close on the previous session (SPY closes:
       data/spx_1549/spy_daily_closes.csv from the `closes` command; SPX closes:
       data/spx_1549/spx_official_closes_cboe.csv).
Targets (root, schema -> strikes, days, folder under data/spx_1549/databento/):
  XSP cbbo-1m   center +- 8  (34 symbols), every day         cbbo-1m_1500-1601_xsp_k8
  SPY cbbo-1m   center +- 10 (42 symbols), every day         cbbo-1m_1500-1601_spy_k10
  XSP ohlcv-1m  center +- 8  (34 symbols), every day         ohlcv-1m_1500-1601_xsp_k8
  SPY ohlcv-1m  center +- 3  (14 symbols), F2 signal days only (the dates of the SPX real-price confirmation's
                trade list, data/spx_1549/databento/realprice_trades.csv, config current, period confirmation;
                only its config/period/date columns are read)          ohlcv-1m_1500-1601_spy_k3_signal

Usage (from /Users/kv15/trading):
  .venv/bin/python -B tools/databento_mini.py selftest                         # offline, no key needed
  .venv/bin/python -B tools/databento_mini.py closes                           # free: SPY daily closes from Yahoo
  .venv/bin/python -B tools/databento_mini.py plan --root XSP|SPY [--schema S]  # days and symbols, no key needed
  .venv/bin/python -B tools/databento_mini.py estimate --root XSP|SPY [--schema cbbo-1m|ohlcv-1m]   # free
  .venv/bin/python -B tools/databento_mini.py pull --root XSP|SPY [--schema S] [--budget 100] [--workers 4]
                                                   [--limit-days N] [--reverse]
  .venv/bin/python -B tools/databento_mini.py status --root XSP|SPY [--schema S]   # files, markers, format checks

Saves gzipped CSVs as <folder>/<YYYY-MM-DD>.csv.gz (git-ignored), a <day>.none marker for a day on which none of
the requested symbols resolved (no same-day expiry), and manifest.json.
"""
from __future__ import annotations

import csv
import gzip
import importlib.util
import io
import json
import math
import sys
import threading
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_spec = importlib.util.spec_from_file_location("databento_spxw_shared", Path(__file__).with_name("databento_spxw.py"))
dbx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbx)

START_DAY = "2021-01-04"
END_DAY = dbx.END_DAY                         # 2026-10-20, the last D1 day
SCHEMA = "cbbo-1m"                            # the default schema
WINDOW_ET = dbx.WINDOW_ET                     # 15:00 .. 16:01 ET (end exclusive)
STEP = 1
HALF_WIDTH = {"XSP": 8, "SPY": 10}            # the quote files' strike bands
# (root, schema) -> strike half-width, whether only F2 signal days are pulled, folder suffix, spend-log label
TARGETS = {
    ("XSP", "cbbo-1m"): {"hw": 8, "signal_only": False, "suffix": "xsp_k8", "label": "cbbo-1m_xsp"},
    ("SPY", "cbbo-1m"): {"hw": 10, "signal_only": False, "suffix": "spy_k10", "label": "cbbo-1m_spy"},
    ("XSP", "ohlcv-1m"): {"hw": 8, "signal_only": False, "suffix": "xsp_k8", "label": "ohlcv-1m_xsp"},
    ("SPY", "ohlcv-1m"): {"hw": 3, "signal_only": True, "suffix": "spy_k3_signal", "label": "ohlcv-1m_spy_k3_signal"},
}
REALPRICE_TRADES = dbx.OUT / "realprice_trades.csv"
OHLCV_COLUMNS = ["ts_event", "rtype", "publisher_id", "instrument_id", "open", "high", "low", "close", "volume",
                 "symbol"]
DEFAULT_WORKERS = 4
SPY_CLOSES = dbx.ROOT / "data" / "spx_1549" / "spy_daily_closes.csv"
SPX_CLOSES = dbx.ROOT / "data" / "spx_1549" / "spx_official_closes_cboe.csv"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=10y"
YAHOO_SOURCE = ("Yahoo Finance chart API v8 (query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=10y), "
                "indicators.quote[0].close: split-adjusted only, not dividend-adjusted (adjclose is not used)")
RATIO_BOUNDS = (0.095, 0.102)                 # SPY / SPX sits near 0.0995-0.1000 (0.1005 on 2025-04-09); outside, stop
ET = ZoneInfo("America/New_York")
CBBO_COLUMNS = ["ts_recv", "ts_event", "rtype", "publisher_id", "instrument_id", "side", "price", "size", "flags",
                "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00", "bid_pb_00", "ask_pb_00", "symbol"]


# ------------------------------------------------------------------------------------------------
# pure helpers (self-tested)
# ------------------------------------------------------------------------------------------------
def check_root(root: str) -> str:
    if root not in HALF_WIDTH:
        raise SystemExit(f"--root must be one of {sorted(HALF_WIDTH)}, not {root!r}")
    return root


def target(root: str, schema: str) -> dict:
    t = TARGETS.get((root, schema))
    if t is None:
        raise SystemExit(f"no target for {root} {schema}; targets: {sorted(TARGETS)}")
    return dict(t, root=root, schema=schema)


def read_signal_days(path: Path = REALPRICE_TRADES) -> set:
    """The F2 signal days of the SPX real-price confirmation: dates of its trade list (config current, period
    confirmation). Only those three columns are used."""
    with open(path, newline="") as fh:
        return {r["date"] for r in csv.DictReader(fh) if r["config"] == "current" and r["period"] == "confirmation"}


def occ(root: str, day: str, kind: str, strike: float) -> str:
    """OSI raw symbol as OPRA prints it: root padded to 6, YYMMDD, C/P, strike x 1000 in 8 digits."""
    return f"{root:<6}{day[2:4]}{day[5:7]}{day[8:10]}{'C' if kind == 'call' else 'P'}{round(strike * 1000):08d}"


def xsp_center(s_1551: float) -> float:
    """Nearest $1 XSP strike to S / 10 (halves round up)."""
    return float(math.floor(s_1551 / 10 + 0.5))


def spy_center(s_1551: float, ratio: float) -> float:
    """Nearest $1 SPY strike to S x (SPY close / SPX close of the previous session) (halves round up)."""
    return float(math.floor(s_1551 * ratio + 0.5))


def symbols_for(root: str, day: str, center: float, hw: int | None = None) -> list[str]:
    hw = HALF_WIDTH[root] if hw is None else hw
    ks = [center + d for d in range(-hw * STEP, hw * STEP + 1, STEP)]
    return [occ(root, day, kind, k) for k in ks for kind in ("call", "put")]


def folder_for(root: str, schema: str = SCHEMA) -> Path:
    return dbx.OUT / f"{schema}_{WINDOW_ET[0].replace(':', '')}-{WINDOW_ET[1].replace(':', '')}_{target(root, schema)['suffix']}"


def prev_ratio(day: str, spy: dict, spx: dict) -> tuple[float, str]:
    """(SPY close / SPX official close, date) on the latest session before `day` that has both closes."""
    for d in sorted((d for d in spy if d < day and d in spx), reverse=True)[:1]:
        r = spy[d] / spx[d]
        if not RATIO_BOUNDS[0] <= r <= RATIO_BOUNDS[1]:
            raise SystemExit(f"SPY/SPX ratio {r:.5f} on {d} is outside {RATIO_BOUNDS}; check the close files")
        return r, d
    raise SystemExit(f"no session before {day} has both a SPY close and an official SPX close")


def parse_yahoo(js: dict) -> dict:
    """{YYYY-MM-DD (New York date): close} from a Yahoo chart v8 JSON; days with a null close are skipped."""
    res = js["chart"]["result"][0]
    tz = ZoneInfo(res["meta"].get("exchangeTimezoneName", "America/New_York"))
    closes = res["indicators"]["quote"][0]["close"]
    out = {}
    for ts, c in zip(res["timestamp"], closes):
        if c is None or not math.isfinite(c) or c <= 0:
            continue
        out[datetime.fromtimestamp(ts, timezone.utc).astimezone(tz).strftime("%Y-%m-%d")] = round(float(c), 4)
    return out


def read_spy_closes(path: Path = SPY_CLOSES) -> dict:
    if not path.exists():
        raise SystemExit(f"{path} is missing: run `databento_mini.py closes` first")
    with open(path, newline="") as fh:
        return {r["date"]: float(r["close"]) for r in csv.DictReader(fh)}


def read_spx_closes(path: Path = SPX_CLOSES) -> dict:
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            m, d, y = r["DATE"].split("/")
            v = float(r["SPX"])
            if v > 0:
                out[f"{y}-{m}-{d}"] = v
    return out


def plan_days(root: str, days_spot: list, spy: dict | None = None, spx: dict | None = None) -> list[dict]:
    """[{day, s_1551, center, ratio, ratio_day}] for the D1 days START_DAY .. END_DAY."""
    out = []
    for d, s in days_spot:
        if not START_DAY <= d <= END_DAY:
            continue
        if root == "XSP":
            out.append({"day": d, "s_1551": s, "center": xsp_center(s), "ratio": None, "ratio_day": None})
        else:
            r, rd = prev_ratio(d, spy, spx)
            out.append({"day": d, "s_1551": s, "center": spy_center(s, r), "ratio": r, "ratio_day": rd})
    return out


def check_file_text(text: str, root: str, day: str, schema: str = SCHEMA) -> dict:
    """Format check of one saved file (no price field is converted or used): header, roots, expiries, and for
    cbbo-1m whether a 15:51:00 row exists."""
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    n = {"rows": 0, "bad_root": 0, "other_expiry": 0, "symbols": set(), "has_1551": False}
    if header != (CBBO_COLUMNS if schema == "cbbo-1m" else OHLCV_COLUMNS):
        n["bad_header"] = True
        return n
    exp = f"{day[2:4]}{day[5:7]}{day[8:10]}"
    t1551 = datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), 15, 51, tzinfo=ET).astimezone(timezone.utc)
    stamp = t1551.strftime("%Y-%m-%dT%H:%M:00.000000000Z")
    for r in rd:
        if not r:
            continue
        n["rows"] += 1
        sym = r[-1]
        n["symbols"].add(sym)
        if sym[:6] != f"{root:<6}":
            n["bad_root"] += 1
        elif sym[6:12] != exp:
            n["other_expiry"] += 1
        if r[0] == stamp:
            n["has_1551"] = True
    return n


# ------------------------------------------------------------------------------------------------
# one day: price first, book, download, log, then publish
# ------------------------------------------------------------------------------------------------
def cost_of(syms: list[str], day: str, schema: str = SCHEMA) -> float:
    a, b = dbx.window_ns(day, WINDOW_ET)
    return dbx.get_cost(schema, syms, a, b)


def fetch(syms: list[str], day: str, schema: str = SCHEMA) -> bytes:
    """One paid request. A dropped connection is NOT retried (it may already be billed)."""
    a, b = dbx.window_ns(day, WINDOW_ET)
    return dbx.call("timeseries.get_range", {"dataset": dbx.DATASET, "symbols": ",".join(syms), "schema": schema,
                                            "start": a, "end": b, "stype_in": "raw_symbol", "encoding": "csv",
                                            "compression": "none", "pretty_px": "true", "pretty_ts": "true",
                                            "map_symbols": "true"}, raw=True, retry_network=False)


def log_spend(label: str, day: str, n_symbols: int, c: float, rows: int, file_label: str,
              log: Path | None = None) -> None:
    """Record a paid request BEFORE its file is published, in databento_spxw's spend-log format."""
    log = log or dbx.SPEND_LOG
    new = not log.exists()
    with open(log, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=dbx.SPEND_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({"utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "schema": label, "day": day, "n_symbols": n_symbols,
                    "quoted_cost_usd": f"{c:.6f}", "rows": rows, "file": file_label})
        fh.flush()


def publish(folder: Path, day: str, body: bytes) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    f, tmp = folder / f"{day}.csv.gz", folder / f"{day}.tmp"
    tmp.write_bytes(gzip.compress(body, 6))
    tmp.replace(f)
    return f


def download_day(tg: dict, item: dict, reserve, lock, folder: Path, *, coster=None, fetcher=None,
                 log: Path | None = None) -> dict:
    """Returns {"status": saved|none|failed|stopped, ...}. reserve(cost) -> bool books the cost first."""
    coster = coster or (lambda s, d: cost_of(s, d, tg["schema"]))
    fetcher = fetcher or (lambda s, d: fetch(s, d, tg["schema"]))
    d = item["day"]
    syms = symbols_for(tg["root"], d, item["center"], tg["hw"])
    try:
        c = coster(syms, d)
    except SystemExit as e:
        if dbx.NO_CONTRACTS in str(e):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{d}.none").write_text(f"none of the requested {tg['root']} symbols expiring this day "
                                              f"resolved\n")
            return {"status": "none"}
        return {"status": "failed", "error": f"cost: {e}"}
    if not reserve(c):
        return {"status": "stopped"}
    try:
        body = fetcher(syms, d)
    except SystemExit as e:
        with lock:
            log_spend(tg["label"], d, len(syms), c, 0, "(failed: may be billed; retried next run)", log)
        return {"status": "failed", "error": str(e)}
    rows = max(0, body.count(b"\n") - 1)
    f = folder / f"{d}.csv.gz"
    with lock:
        log_spend(tg["label"], d, len(syms), c, rows,
                  str(f.relative_to(dbx.ROOT)) if f.is_relative_to(dbx.ROOT) else str(f), log)
        publish(folder, d, body)
    return {"status": "saved", "rows": rows, "cost": c}


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------
def load_plan(tg: dict) -> list[dict]:
    days = dbx.days_and_spot()
    if tg["root"] == "SPY":
        plan = plan_days("SPY", days, read_spy_closes(), read_spx_closes())
    else:
        plan = plan_days("XSP", days)
    if tg["signal_only"]:
        sig = read_signal_days()
        plan = [it for it in plan if it["day"] in sig]
        if len(plan) != len(sig):
            raise SystemExit(f"{len(sig)} signal days in {REALPRICE_TRADES.name} but {len(plan)} in the D1 plan")
    return plan


def cmd_closes():
    req = urllib.request.Request(YAHOO_URL, headers={"User-Agent": "Mozilla/5.0 spx-research/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        js = json.loads(r.read())
    closes = parse_yahoo(js)
    closes.pop(datetime.now(ET).strftime("%Y-%m-%d"), None)          # today's bar may still be intraday
    if len(closes) < 2000 or min(closes) > "2020-12-01":
        raise SystemExit(f"Yahoo answer too short ({len(closes)} days from {min(closes) if closes else None})")
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = SPY_CLOSES.with_suffix(".tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close", "source", "fetched_utc"])
        for d in sorted(closes):
            w.writerow([d, f"{closes[d]:.4f}", YAHOO_SOURCE, fetched])
    tmp.replace(SPY_CLOSES)
    ds = sorted(closes)
    print(f"SPY closes: {len(ds)} days {ds[0]} .. {ds[-1]} -> {SPY_CLOSES.relative_to(dbx.ROOT)}")


def cmd_plan(tg: dict):
    plan = load_plan(tg)
    folder = folder_for(tg["root"], tg["schema"])
    print(f"{tg['root']} {tg['schema']}: {len(plan)} days {plan[0]['day']} .. {plan[-1]['day']}, "
          f"{2 * (2 * tg['hw'] + 1)} symbols a day, window {WINDOW_ET[0]}-{WINDOW_ET[1]} ET -> "
          f"{folder.relative_to(dbx.ROOT)}")
    for it in (plan[0], plan[-1]):
        syms = symbols_for(tg["root"], it["day"], it["center"], tg["hw"])
        extra = f", r {it['ratio']:.5f} from {it['ratio_day']}" if it["ratio"] else ""
        print(f"  {it['day']}: D1 15:51 open {it['s_1551']:.2f}{extra} -> center {it['center']:.0f}: "
              f"{syms[0]!r} .. {syms[-1]!r}")


def cmd_estimate(tg: dict, full: bool = False):
    """Free: the sampled cost (every 1/30th day), or with --full the exact quoted cost of every day."""
    plan = load_plan(tg)
    sample = plan if full else plan[::max(1, len(plan) // 30)]
    costs, none = [], 0
    for it in sample:
        try:
            costs.append(cost_of(symbols_for(tg["root"], it["day"], it["center"], tg["hw"]), it["day"],
                                 tg["schema"]))
        except SystemExit as e:
            if dbx.NO_CONTRACTS not in str(e):
                raise
            costs.append(0.0)
            none += 1
    mean = sum(costs) / len(costs)
    what = (f"all {len(sample)} days priced: ${sum(costs):.4f}" if full else
            f"sampled {len(sample)} days, mean ${mean:.5f} a day, max ${max(costs):.5f} -> about "
            f"${mean * len(plan):.2f} for all {len(plan)} days")
    print(f"{tg['root']} {tg['schema']} +-{tg['hw']}{' signal days' if tg['signal_only'] else ''}: {what} "
          f"({none} with no requested symbol resolved; logged so far ${dbx.spent():.4f})")


def write_manifest(tg: dict, plan: list[dict]) -> None:
    root = tg["root"]
    folder = folder_for(root, tg["schema"])
    folder.mkdir(parents=True, exist_ok=True)
    m = {"dataset": dbx.DATASET, "schema": tg["schema"], "root": root, "window_et": WINDOW_ET,
         "half_width": tg["hw"], "step": STEP,
         "center": ("floor(D1 15:51 open / 10 + 0.5)" if root == "XSP" else
                    "floor(D1 15:51 open x SPY close / official SPX close of the previous session + 0.5)"),
         "days_rule": ("F2 signal days: dates of realprice_trades.csv rows with config current, period confirmation"
                       if tg["signal_only"] else "every D1 day in start..end"),
         "spy_closes": str(SPY_CLOSES.relative_to(dbx.ROOT)) if root == "SPY" else None,
         "start": START_DAY, "end": END_DAY,
         "days": [{k: it[k] for k in ("day", "center", "ratio_day")} if root == "SPY" else
                  {"day": it["day"], "center": it["center"]} for it in plan]}
    tmp = folder / "manifest.tmp"
    tmp.write_text(json.dumps(m, indent=1) + "\n")
    tmp.replace(folder / "manifest.json")


def cmd_pull(tg: dict, budget: float, workers: int, limit_days: int | None, reverse: bool = False):
    root = tg["root"]
    plan = load_plan(tg)
    folder = folder_for(root, tg["schema"])
    write_manifest(tg, plan)
    todo = [it for it in plan
            if not (folder / f"{it['day']}.csv.gz").exists() and not (folder / f"{it['day']}.none").exists()]
    if reverse:                                   # newest first, so a second process can work from the other end
        todo = todo[::-1]
    if limit_days is not None:
        todo = todo[:limit_days]
    lock = threading.Lock()
    before = dbx.spent()
    state = {"spent": before, "saved": 0, "none": 0, "stop": None, "failed": []}

    def reserve(c):
        with lock:
            if state["stop"] or not dbx.allowed(state["spent"], c, budget):
                state["stop"] = state["stop"] or (f"STOP: ${state['spent']:.4f} booked + ${c:.6f} would pass the "
                                                  f"${budget:.2f} budget")
                return False
            state["spent"] += c
            return True

    def one(it):
        if state["stop"]:
            return
        if (folder / f"{it['day']}.csv.gz").exists() or (folder / f"{it['day']}.none").exists():
            return                                # done meanwhile (e.g. by a process working from the other end)
        r = download_day(tg, it, reserve, lock, folder)
        with lock:
            if r["status"] == "failed":
                state["failed"].append(it["day"])
                print(f"FAILED {it['day']}: {r['error']}", flush=True)
            elif r["status"] == "none":
                state["none"] += 1
            elif r["status"] == "saved":
                state["saved"] += 1
                if state["saved"] % 200 == 0:
                    print(f"{root}: {state['saved']} days saved this run, ${state['spent']:.4f} booked", flush=True)

    print(f"{root} {tg['schema']}: {len(todo)} days to fetch of {len(plan)}; logged spend before ${before:.6f}",
          flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in ex.map(one, todo):
            pass
    if state["stop"]:
        print(state["stop"])
    if state["failed"]:
        print(f"{len(state['failed'])} days failed (run pull again to retry): {', '.join(state['failed'][:30])}")
    have = len(list(folder.glob("*.csv.gz")))
    nones = len(list(folder.glob("*.none")))
    print(f"{root} {tg['schema']}: this run saved {state['saved']}, marked {state['none']} no-expiry; folder has "
          f"{have} files + {nones} .none of {len(plan)} days; logged spend ${before:.6f} -> ${dbx.spent():.6f} "
          f"(budget ${budget:.2f})", flush=True)


def cmd_status(tg: dict):
    """Counts by year and weekday and a format check of every saved file (no price field is converted or used)."""
    root, schema = tg["root"], tg["schema"]
    plan = [it["day"] for it in load_plan(tg)]
    folder = folder_for(root, schema)
    by, wd = {}, {}
    problems = Counter()
    n_syms = Counter()
    for d in plan:
        y = by.setdefault(d[:4], Counter())
        w = wd.setdefault(datetime(int(d[:4]), int(d[5:7]), int(d[8:10])).strftime("%a"), Counter())
        f = folder / f"{d}.csv.gz"
        if f.exists():
            y["file"] += 1
            w["file"] += 1
            n = check_file_text(gzip.decompress(f.read_bytes()).decode(), root, d, schema)
            if n.get("bad_header"):
                problems["bad header"] += 1
                continue
            if n["rows"] == 0:
                problems["files with no rows"] += 1
            if n["bad_root"]:
                problems["files with rows of another root"] += 1
            if n["other_expiry"]:
                problems["files with rows of another expiry"] += 1
            if schema == "cbbo-1m" and not n["has_1551"]:
                problems["files with no 15:51:00 row"] += 1
            n_syms[len(n["symbols"])] += 1
        elif (folder / f"{d}.none").exists():
            y["none"] += 1
            w["none"] += 1
        else:
            y["missing"] += 1
            w["missing"] += 1
    print(f"{root} {schema} ({folder.relative_to(dbx.ROOT)}): {len(plan)} days")
    print("year  days  file  no symbol resolved (.none)  missing")
    tot = Counter()
    for yr in sorted(by):
        c = by[yr]
        n = c["file"] + c["none"] + c["missing"]
        tot.update({"n": n, "file": c["file"], "none": c["none"], "missing": c["missing"]})
        print(f"{yr}  {n:4d}  {c['file']:4d}  {c['none']:26d}  {c['missing']:7d}")
    print(f"all   {tot['n']:4d}  {tot['file']:4d}  {tot['none']:26d}  {tot['missing']:7d}")
    print("by weekday (file / none / missing):",
          {k: (wd[k]["file"], wd[k]["none"], wd[k]["missing"]) for k in ("Mon", "Tue", "Wed", "Thu", "Fri") if k in wd})
    print("format problems:", dict(problems) if problems else "none")
    print("distinct symbols per file (count: files):", dict(sorted(n_syms.items())))


def selftest():
    assert occ("XSP", "2025-06-02", "call", 594) == "XSP   250602C00594000"
    assert occ("SPY", "2025-06-02", "put", 592) == "SPY   250602P00592000"
    assert len(occ("XSP", "2025-06-02", "call", 594)) == 21 and len(occ("SPY", "2021-01-04", "put", 371)) == 21
    assert xsp_center(5934.99) == 593.0 and xsp_center(5935.0) == 594.0 and xsp_center(5944.9) == 594.0
    assert spy_center(5935.0, 0.0995) == 591.0          # 590.5325 -> 591
    assert spy_center(5934.0, 0.0995) == 590.0          # 590.433 -> 590
    xs = symbols_for("XSP", "2025-06-02", 594.0)
    assert len(xs) == 34 and xs[0] == "XSP   250602C00586000" and xs[-1] == "XSP   250602P00602000"
    ss = symbols_for("SPY", "2025-06-02", 592.0)
    assert len(ss) == 42 and ss[0] == "SPY   250602C00582000" and ss[-1] == "SPY   250602P00602000"
    assert len(set(xs)) == 34 and len(set(ss)) == 42
    assert folder_for("XSP").name == "cbbo-1m_1500-1601_xsp_k8"
    assert folder_for("SPY").name == "cbbo-1m_1500-1601_spy_k10"
    assert folder_for("XSP").parent == dbx.OUT
    assert folder_for("XSP", "ohlcv-1m").name == "ohlcv-1m_1500-1601_xsp_k8"
    assert folder_for("SPY", "ohlcv-1m").name == "ohlcv-1m_1500-1601_spy_k3_signal"
    k3 = symbols_for("SPY", "2025-06-02", 592.0, target("SPY", "ohlcv-1m")["hw"])
    assert len(k3) == 14 and k3[0] == "SPY   250602C00589000" and k3[-1] == "SPY   250602P00595000"
    assert target("SPY", "ohlcv-1m")["signal_only"] and not target("XSP", "ohlcv-1m")["signal_only"]
    assert target("XSP", "cbbo-1m")["label"] == "cbbo-1m_xsp" and target("SPY", "cbbo-1m")["label"] == "cbbo-1m_spy"
    try:
        target("SPY", "trades")
        raise AssertionError("target accepted an unknown schema")
    except SystemExit:
        pass
    spy = {"2025-05-29": 590.0, "2025-05-30": 591.0, "2025-06-02": 600.0}
    spx = {"2025-05-29": 5920.0, "2025-05-30": 5935.0, "2025-06-02": 6010.0}
    r, d = prev_ratio("2025-06-02", spy, spx)            # the previous session, never the day itself
    assert d == "2025-05-30" and abs(r - 591.0 / 5935.0) < 1e-15
    r, d = prev_ratio("2025-05-30", spy, {"2025-05-29": 5920.0})
    assert d == "2025-05-29"
    for bad in ({"2025-05-29": 1.0}, {}):
        try:
            prev_ratio("2025-06-02", bad, spx)
            raise AssertionError("prev_ratio accepted a bad ratio / no data")
        except SystemExit:
            pass
    plan = plan_days("SPY", [("2020-12-31", 3700.0), ("2025-06-02", 5935.0), ("2026-10-21", 1.0)], spy, spx)
    assert [p["day"] for p in plan] == ["2025-06-02"] and plan[0]["center"] == spy_center(5935.0, 591.0 / 5935.0)
    plan = plan_days("XSP", [("2020-12-31", 3700.0), ("2021-01-04", 3712.4), ("2026-10-20", 6700.0)])
    assert [(p["day"], p["center"]) for p in plan] == [("2021-01-04", 371.0), ("2026-10-20", 670.0)]
    # Yahoo parsing: New York dates, null closes skipped
    js = {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York"},
                                "timestamp": [1748871000, 1748957400, 1749043800],     # 2025-06-02/03/04 09:30 ET
                                "indicators": {"quote": [{"close": [592.71, None, 596.09]}]}}]}}
    assert parse_yahoo(js) == {"2025-06-02": 592.71, "2025-06-04": 596.09}
    # window: EDT and EST
    a, b = dbx.window_ns("2025-06-02", WINDOW_ET)
    assert datetime.fromtimestamp(a / 1e9, timezone.utc).strftime("%H:%M") == "19:00" and b - a == 61 * 60 * 10**9
    a, _ = dbx.window_ns("2025-12-01", WINDOW_ET)
    assert datetime.fromtimestamp(a / 1e9, timezone.utc).strftime("%H:%M") == "20:00"
    # format check of a file
    hdr = ",".join(CBBO_COLUMNS)
    txt = (hdr + "\n2025-06-02T19:51:00.000000000Z,x,193,30,1,N,1,1,0,1,1.1,1,1,1,1,XSP   250602C00594000\n"
           "2025-06-02T19:52:00.000000000Z,x,193,30,1,N,1,1,0,1,1.1,1,1,1,1,XSP   250603C00594000\n")
    n = check_file_text(txt, "XSP", "2025-06-02")
    assert n["rows"] == 2 and n["has_1551"] and n["other_expiry"] == 1 and n["bad_root"] == 0
    assert check_file_text("a,b\n", "XSP", "2025-06-02").get("bad_header")
    otxt = (",".join(OHLCV_COLUMNS) + "\n2025-06-02T19:51:00.000000000Z,33,30,1,1,1,1,1,5,SPY   250602C00592000\n")
    n = check_file_text(otxt, "SPY", "2025-06-02", "ohlcv-1m")
    assert n["rows"] == 1 and not n.get("bad_header") and n["bad_root"] == 0 and n["other_expiry"] == 0
    assert check_file_text(otxt, "SPY", "2025-06-02", "cbbo-1m").get("bad_header")
    # signal days: only config current, period confirmation
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "trades.csv"
        p.write_text("config,cell,date,period,signal\ncurrent,c,2021-01-05,confirmation,1\n"
                     "chosen,c,2021-01-06,confirmation,1\ncurrent,c,2019-01-07,discovery,-1\n"
                     "current,c,2026-10-20,confirmation,-1\n")
        assert read_signal_days(p) == {"2021-01-05", "2026-10-20"}
    # accounting: price first, book, log BEFORE publish, failures logged, .none on no expiry, budget stop
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        log, folder = t / "log.csv", t / "out"
        lock = threading.Lock()
        seen = []

        def fetch_ok(syms, d):
            seen.append(("fetch", log.exists()))
            return b"h\nr1\nr2\n"

        def publish_spy(folder_, d, body):                                  # check the log line is already there
            seen.append(("publish", log.exists() and d in log.read_text()))
            return real_publish(folder_, d, body)

        real_publish = globals()["publish"]
        globals()["publish"] = publish_spy
        try:
            booked = []
            it = {"day": "2025-06-02", "center": 594.0}
            r = download_day(target("XSP", "cbbo-1m"), it, lambda c: booked.append(c) or True, lock, folder,
                             coster=lambda s, d: 0.0003, fetcher=fetch_ok, log=log)
        finally:
            globals()["publish"] = real_publish
        assert r["status"] == "saved" and r["rows"] == 2 and booked == [0.0003]
        assert seen == [("fetch", False), ("publish", True)]
        assert gzip.decompress((folder / "2025-06-02.csv.gz").read_bytes()) == b"h\nr1\nr2\n"
        assert abs(dbx.spent(log) - 0.0003) < 1e-12
        row = list(csv.DictReader(open(log)))[0]
        assert list(row) == dbx.SPEND_COLUMNS and row["schema"] == "cbbo-1m_xsp" and row["n_symbols"] == "34"

        def fetch_fail(syms, d):
            raise SystemExit("Databento timeseries.get_range: network error")
        r = download_day(target("SPY", "ohlcv-1m"), {"day": "2025-06-03", "center": 592.0}, lambda c: True, lock,
                         folder, coster=lambda s, d: 0.0004, fetcher=fetch_fail, log=log)
        assert r["status"] == "failed" and not (folder / "2025-06-03.csv.gz").exists()
        assert abs(dbx.spent(log) - 0.0007) < 1e-12                      # the failed paid request is logged
        row = list(csv.DictReader(open(log)))[1]
        assert row["schema"] == "ohlcv-1m_spy_k3_signal" and row["n_symbols"] == "14" and row["rows"] == "0"

        def no_expiry(s, d):
            raise SystemExit(f"Databento metadata.get_cost: HTTP 422: {dbx.NO_CONTRACTS}")
        r = download_day(target("XSP", "cbbo-1m"), {"day": "2025-06-03", "center": 594.0}, lambda c: True, lock,
                         folder, coster=no_expiry, fetcher=fetch_ok, log=log)
        assert r["status"] == "none" and (folder / "2025-06-03.none").exists()
        r = download_day(target("XSP", "cbbo-1m"), {"day": "2025-06-04", "center": 594.0}, lambda c: False, lock,
                         folder, coster=lambda s, d: 0.0003, fetcher=fetch_ok, log=log)
        assert r["status"] == "stopped" and not (folder / "2025-06-04.csv.gz").exists()
        assert abs(dbx.spent(log) - 0.0007) < 1e-12
    assert dbx.allowed(119.99, 0.01, 120.0) and not dbx.allowed(119.99, 0.02, 120.0)
    print("selftest: all checks passed")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    if cmd == "selftest":
        selftest()
    elif cmd == "closes":
        cmd_closes()
    elif cmd in ("plan", "estimate", "pull", "status"):
        tg = target(check_root(opt("--root", "")), opt("--schema", SCHEMA))
        if cmd == "plan":
            cmd_plan(tg)
        elif cmd == "estimate":
            cmd_estimate(tg, "--full" in args)
        elif cmd == "pull":
            lim = opt("--limit-days")
            cmd_pull(tg, float(opt("--budget", dbx.DEFAULT_BUDGET)), int(opt("--workers", DEFAULT_WORKERS)),
                     int(lim) if lim else None, "--reverse" in args)
        else:
            cmd_status(tg)
    else:
        raise SystemExit(__doc__)
