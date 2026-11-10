"""Download Dukascopy USA500.IDX/USD 1-minute BID candles (dataset D1 of preregistration/spx_1549_close.md).

One file per UTC day:
    https://datafeed.dukascopy.com/datafeed/USA500IDXUSD/YYYY/MM/DD/BID_candles_min_1.bi5
    MM in the URL is ZERO-based (January = 00, December = 11).

Saved to (month is ONE-based here, January = 01, so the folder names read normally):
    data/spx_1549/dukascopy/raw/YYYY/MM/DD.bi5      the file exactly as served (LZMA compressed)
    data/spx_1549/dukascopy/raw/YYYY/MM/DD.nodata   empty marker: the server said 404 or sent 0 bytes
Files already present (either kind) are skipped, so the script can be re-run to resume.

File format (checked by decode_bi5 and tests/test_d1.py): lzma.decompress -> 24-byte big-endian
records '>iiiiif' = (seconds since 00:00 UTC of that day, open, close, low, high, volume).
Prices are integers / 1000 (6584125 -> 6584.125).

Only Monday-Friday UTC days are requested by default: a Saturday or Sunday UTC day can never contain
any part of the 09:30-16:00 ET cash session, so fetching them would only load the server. Use
--all-days to fetch weekends too.

Server behaviour seen on 2026-10-21: 404 = no data for that day; 503 ("No server is available") and
timeouts happen often and are transient; 429 is returned for generic tool User-Agents. The script
identifies itself honestly with its own User-Agent, keeps a global minimum gap between requests,
and retries 429/5xx/timeouts with exponential backoff. A day that still fails is NOT marked as
no-data; it is listed in the manifest and fetched again on the next run.

Usage:
    .venv/bin/python -B backtests/spx_close_1549/fetch_dukascopy.py --probe-only
    .venv/bin/python -B backtests/spx_close_1549/fetch_dukascopy.py            # probe + download
    .venv/bin/python -B backtests/spx_close_1549/fetch_dukascopy.py --start 2013-01-01
"""

from __future__ import annotations

import argparse
import json
import lzma
import os
import random
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path("/Users/kv15/trading")
DATA_DIR = ROOT / "data" / "spx_1549" / "dukascopy"
RAW_DIR = DATA_DIR / "raw"
MANIFEST = DATA_DIR / "fetch_manifest.json"
PROBE_FILE = DATA_DIR / "probe_earliest.json"

SYMBOL = "USA500IDXUSD"
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m0:02d}/{d:02d}/BID_candles_min_1.bi5"
USER_AGENT = "spx1549-research-fetcher/1.0 (personal research backtest; low request rate)"
END_DEFAULT = date(2026, 10, 20)

RECORD = struct.Struct(">iiiiif")  # seconds, open, close, low, high, volume
PRICE_SCALE = 1000.0

MIN_GAP_SECONDS = 0.35   # global minimum time between two request starts (all workers together)
MAX_ATTEMPTS = 12
TIMEOUT = (15, 90)       # connect, read (the server often takes 10-30 s to answer)


# ---------------------------------------------------------------------------------------------
# Paths, URLs and decoding
# ---------------------------------------------------------------------------------------------

def url_for(day: date) -> str:
    return URL.format(sym=SYMBOL, y=day.year, m0=day.month - 1, d=day.day)


def raw_path(day: date) -> Path:
    return RAW_DIR / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}.bi5"


def nodata_path(day: date) -> Path:
    return raw_path(day).with_suffix(".nodata")


def decode_bi5_bytes(payload: bytes, day: date | None = None):
    """Decode the compressed candle file. Returns a list of tuples
    (utc_datetime or seconds, open, high, low, close, volume) with prices as floats.

    If `day` is given, the first item is a timezone-aware UTC datetime; otherwise the raw seconds.
    """

    if not payload:
        return []
    blob = lzma.decompress(payload)
    if len(blob) % RECORD.size:
        raise ValueError(f"decoded length {len(blob)} is not a multiple of {RECORD.size}")
    out = []
    midnight = None
    if day is not None:
        midnight = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    for secs, o, c, lo, hi, vol in RECORD.iter_unpack(blob):
        stamp = midnight + timedelta(seconds=secs) if midnight is not None else secs
        out.append((stamp, o / PRICE_SCALE, hi / PRICE_SCALE, lo / PRICE_SCALE, c / PRICE_SCALE, vol))
    return out


def decode_file(day: date):
    path = raw_path(day)
    if not path.exists():
        return []
    return decode_bi5_bytes(path.read_bytes(), day)


# ---------------------------------------------------------------------------------------------
# Polite HTTP
# ---------------------------------------------------------------------------------------------

_gap_lock = threading.Lock()
_last_start = [0.0]
_local = threading.local()


def _session() -> requests.Session:
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        _local.s = s
    return _local.s


def _wait_turn() -> None:
    with _gap_lock:
        now = time.monotonic()
        wait = _last_start[0] + MIN_GAP_SECONDS - now
        if wait > 0:
            time.sleep(wait)
        _last_start[0] = time.monotonic()


def fetch_day(day: date) -> tuple[str, int, str]:
    """Fetch one UTC day. Returns (status, n_bytes, detail).

    status: 'data' (saved .bi5), 'nodata' (404 or empty body, marker saved), 'failed' (gave up).
    """

    detail = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _wait_turn()
        try:
            resp = _session().get(url_for(day), timeout=TIMEOUT)
            code = resp.status_code
            body = resp.content
        except requests.RequestException as error:
            code, body, detail = None, b"", type(error).__name__
        if code == 404 or (code == 200 and len(body) == 0):
            target = nodata_path(day)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"")
            return "nodata", 0, f"http {code}"
        if code == 200:
            try:
                decode_bi5_bytes(body)  # make sure the download is complete and decodable
            except (lzma.LZMAError, ValueError, EOFError) as error:
                detail = f"bad payload: {error}"
            else:
                target = raw_path(day)
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".part")
                tmp.write_bytes(body)
                os.replace(tmp, target)
                return "data", len(body), "http 200"
        else:
            detail = f"http {code}" if code is not None else detail
        # back off: exponential and long for 429 (explicit rate limit); linear for 503/timeouts,
        # which on this server are capacity errors unrelated to our own (low) request rate
        if code == 429:
            pause = min(300.0, 20.0 * (2 ** (attempt - 1)))
        else:
            pause = min(30.0, 3.0 * attempt)
        time.sleep(pause * (0.7 + 0.6 * random.random()))
    return "failed", 0, detail


def already_have(day: date) -> bool:
    return raw_path(day).exists() or nodata_path(day).exists()


# ---------------------------------------------------------------------------------------------
# Probe for the earliest year/month with data
# ---------------------------------------------------------------------------------------------

def _probe_status(day: date) -> str:
    """'data' / 'nodata' / 'failed' for one day; uses (and fills) the raw cache."""

    if raw_path(day).exists():
        return "data"
    if nodata_path(day).exists():
        return "nodata"
    return fetch_day(day)[0]


def _mid_month_weekdays(year: int, month: int) -> list[date]:
    """Three weekdays in the middle of a month (one success is enough to say "data exists")."""

    out, d = [], date(year, month, 10)
    while len(out) < 3:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _probe_month(year: int, month: int) -> dict:
    """Ask for mid-month weekdays until one gives a definite answer (data or 404)."""

    statuses = {}
    for day in _mid_month_weekdays(year, month):
        status = _probe_status(day)
        statuses[day.isoformat()] = status
        if status != "failed":
            break
    return {"month": f"{year:04d}-{month:02d}", "results": statuses}


def probe_earliest(first_year: int = 2010, last_year: int = 2014, workers: int = 4) -> dict:
    """Find the earliest month in first_year..last_year with data. One mid-month weekday is asked
    per month (the next weekday only if the server gave no definite answer). Months are probed in
    parallel with the same polite pool. The result is also written to probe_earliest.json."""

    months = [(y, m) for y in range(first_year, last_year + 1) for m in range(1, 13)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tried = list(pool.map(lambda ym: _probe_month(*ym), months))
    earliest = None
    for (year, month), item in zip(months, tried):
        if "data" in item["results"].values():
            earliest = (year, month)
            break
    unresolved = [t for t in tried if set(t["results"].values()) == {"failed"}]
    # conservative start: a month the server never answered for, if it comes before the first
    # month seen with data, might also have data
    first_open = earliest
    for (year, month), item in zip(months, tried):
        if earliest and (year, month) >= earliest:
            break
        if set(item["results"].values()) == {"failed"}:
            first_open = (year, month)
            break
    if first_open is None:
        start = None
    else:
        y, m = first_open
        # start one month earlier than the first month seen with data, so a start date between
        # the 1st of the previous month and the probe days is not missed
        start = date(y - 1, 12, 1) if m == 1 else date(y, m - 1, 1)
    result = {
        "symbol": SYMBOL,
        "probed_years": [first_year, last_year],
        "earliest_month_with_data": None if earliest is None else f"{earliest[0]:04d}-{earliest[1]:02d}",
        "download_start": None if start is None else start.isoformat(),
        "months_where_every_probe_failed_transiently": [t["month"] for t in unresolved],
        "probes": tried,
        "probed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    PROBE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROBE_FILE.write_text(json.dumps(result, indent=2))
    return result


# ---------------------------------------------------------------------------------------------
# Bulk download
# ---------------------------------------------------------------------------------------------

def days_between(start: date, end: date, all_days: bool) -> list[date]:
    out, d = [], start
    while d <= end:
        if all_days or d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def download(start: date, end: date, workers: int = 4, all_days: bool = False) -> dict:
    wanted = days_between(start, end, all_days)
    # newest first, so the validation overlap (Sep-Oct 2026) is on disk early
    todo = [d for d in reversed(wanted) if not already_have(d)]
    print(f"{len(wanted)} days in range, {len(wanted) - len(todo)} already on disk, {len(todo)} to fetch",
          flush=True)
    counts = {"data": 0, "nodata": 0, "failed": 0}
    failed = []
    done = 0
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_day, d): d for d in todo}
        for fut in as_completed(futures):
            day = futures[fut]
            status, _, detail = fut.result()
            counts[status] += 1
            if status == "failed":
                failed.append({"day": day.isoformat(), "last_error": detail})
            done += 1
            if done % 50 == 0 or done == len(todo):
                rate = done / max(1e-9, time.monotonic() - t0)
                print(f"  {done}/{len(todo)}  {counts}  {rate:.2f} files/s", flush=True)
    on_disk_data = sum(raw_path(d).exists() for d in wanted)
    on_disk_nodata = sum(nodata_path(d).exists() for d in wanted)
    manifest = {
        "symbol": SYMBOL,
        "url_template": URL,
        "month_in_url": "zero-based (Jan=00)",
        "month_in_path": "one-based (Jan=01): raw/YYYY/MM/DD.bi5",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "weekdays_only": not all_days,
        "days_in_range": len(wanted),
        "this_run": counts,
        "on_disk_with_data": on_disk_data,
        "on_disk_nodata_markers": on_disk_nodata,
        "missing_after_run": [f["day"] for f in failed],
        "failed_details": failed,
        "user_agent": USER_AGENT,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", help="YYYY-MM-DD; default = probe result")
    ap.add_argument("--end", default=END_DEFAULT.isoformat())
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--all-days", action="store_true", help="also fetch Saturday/Sunday UTC files")
    ap.add_argument("--probe-only", action="store_true")
    args = ap.parse_args(argv)

    if args.start:
        start = date.fromisoformat(args.start)
    else:
        probe = probe_earliest()
        print(json.dumps({k: v for k, v in probe.items() if k != "probes"}, indent=2), flush=True)
        if probe["download_start"] is None:
            print("no data found in the probe years", file=sys.stderr)
            return 1
        start = date.fromisoformat(probe["download_start"])
    if args.probe_only:
        return 0
    manifest = download(start, date.fromisoformat(args.end), args.workers, args.all_days)
    print(json.dumps({k: v for k, v in manifest.items() if k != "failed_details"}, indent=2))
    return 0 if not manifest["missing_after_run"] else 2


if __name__ == "__main__":
    sys.exit(main())
