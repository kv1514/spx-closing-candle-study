"""The locked closing-imbalance test (preregistration/spx_candle_imbalance.md).

Modes (from /Users/kv15/trading):
  .venv/bin/python -B backtests/spx_candle_imbalance/imbalance.py selftest     # synthetic data, temp files, no network
  .venv/bin/python -B backtests/spx_candle_imbalance/imbalance.py dryrun <empty temp dir>   # fake data end to end
  .venv/bin/python -B backtests/spx_candle_imbalance/imbalance.py pull [--workers 4] [--limit N]
  .venv/bin/python -B backtests/spx_candle_imbalance/imbalance.py run [--defect "reason"]

Start-up checks (pull and run): the locked plan's SHA-256 must match its line in preregistration/LEDGER.md, and
every file in the plan's "Lock record" table must match its recorded SHA-256. The selftest must pass first.

Money (plan section 10): every request is priced with the free metadata.get_cost for its own dataset (and must
match the frozen quote in quote_manifest.json within 1%); refused if the logged total in spend_log.csv would pass
$120; a reservation row is appended to spend_log.csv and flushed to disk BEFORE the request. Paid requests use this
file's own single-attempt code (the older helper, which retries HTTP 429/5xx, is used only for its key loader): a
paid request is never retried automatically. A failed (day, dataset) keeps its reservation and may be tried again on
a later `pull` with a new reservation, at most three attempts in all. The API key is never printed.

The run computes no outcome before the imbalance classification of every day is fixed; agreement_days.csv holds no
outcome column. One registered run: a second `run` is refused unless --defect names a documented defect, and
earlier outputs are kept.
"""
from __future__ import annotations

import base64
import csv
import fcntl
import gzip
import http.client
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = ROOT / "preregistration" / "spx_candle_imbalance.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
OUT = ROOT / "data" / "spx_1549" / "databento" / "imbalance_1550-1600"
ATTEMPTS = OUT / "attempts.csv"
DOWNLOADS = OUT / "downloads.csv"
RES_DIR = HERE                      # where results.json, RESULTS.md and agreement_days.csv go (dryrun: a temp folder)
SPEND_LOG = ROOT / "data" / "spx_1549" / "databento" / "spend_log.csv"
SPEND_COLUMNS = ["utc_time", "schema", "day", "n_symbols", "quoted_cost_usd", "rows", "file"]
API = "https://hist.databento.com/v0/"
ET = ZoneInfo("America/New_York")
CAP = 120.0
MIN_LOGGED = 93.579          # logged spend at the lock (plan section 10); a smaller total means the log was damaged
MAX_ATTEMPTS = 3
DATASETS = ("XNYS.PILLAR", "XNAS.ITCH")
CLOSING_CODES = {"XNYS.PILLAR": {"C", "R"}, "XNAS.ITCH": {"C"}}
UNDEF_PRICE = 9223372036854775807
UNDEF_ORDER_SIZE = 4294967295
SIDE = {"B": 1, "A": -1, "N": 0}
MIN_STOCKS = 10
MIN_GROUP = 30
BOOT_DRAWS, BOOT_BLOCK, BOOT_SEED, BOOT_MIN_OK = 10_000, 20, 20261111, 9_000
START, END = "2021-01-04", "2026-10-20"
OPTION_CELL = "15:50 body>=0.60 with ITM10"
# the CSV header Databento returns for this request (seen in the format samples, section 2a)
HEADER = ("ts_recv,ts_event,rtype,publisher_id,instrument_id,ref_price,auction_time,cont_book_clr_price,"
          "auct_interest_clr_price,ssr_filling_price,ind_match_price,upper_collar,lower_collar,paired_qty,"
          "total_imbalance_qty,market_imbalance_qty,unpaired_qty,auction_type,side,auction_status,freeze_status,"
          "num_extensions,unpaired_side,significant_imbalance,symbol")
DL_FIELDS = ["day", "dataset", "rows", "sha256_uncompressed", "quoted_cost_usd", "file"]
ATT_FIELDS = ["utc_time", "day", "dataset", "quoted_cost_usd"]

_dbx = None
_dbx_lock = threading.Lock()


def dbx():
    """The older helper, loaded once. Thread-safe: the module is published only after it has fully loaded (two
    download threads once raced here and one saw a half-loaded module; nothing was reserved or billed for it)."""
    global _dbx
    with _dbx_lock:
        if _dbx is None:
            spec = importlib.util.spec_from_file_location("dbx", ROOT / "tools" / "databento_spxw.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _dbx = mod
    return _dbx


def api_key() -> str:
    return dbx().api_key()


def http_post(endpoint: str, params: dict, *, paid: bool) -> bytes:
    """One POST to Databento. Free endpoints (paid=False) retry HTTP 429/5xx and network errors; a paid request is
    made exactly once, and any failure raises RequestFailed (its reservation stays in the spend log)."""
    key = api_key()
    auth = base64.b64encode((key + ":").encode()).decode()
    req = urllib.request.Request(API + endpoint, data=urllib.parse.urlencode(params).encode(), method="POST",
                                 headers={"Authorization": f"Basic {auth}", "User-Agent": "spx-research/1.0"})
    for attempt in range(1 if paid else 6):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            msg = redact(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}", key, auth)[:300]
        except (http.client.HTTPException, OSError) as e:
            msg = redact(f"network error {type(e).__name__}: {e}", key, auth)[:300]
        if paid:
            raise RequestFailed(f"{endpoint}: {msg}")
        time.sleep(5 * (attempt + 1))
    raise RequestFailed(f"{endpoint}: gave up after retries: {msg}")


class RequestFailed(Exception):
    pass


def redact(msg: str, *secrets: str) -> str:
    for x in secrets:
        if x:
            msg = msg.replace(x, "[redacted]")
    return msg


def spent() -> float:
    """Logged spend (quoted costs, reservations included). Refuses a log with a non-finite or negative amount."""
    if not SPEND_LOG.exists():
        raise SystemExit(f"{SPEND_LOG} is missing: refusing (the plan records $93.58 already spent)")
    total = 0.0
    with open(SPEND_LOG, newline="") as fh:
        for r in csv.DictReader(fh):
            v = float(r["quoted_cost_usd"])
            if not math.isfinite(v) or v < 0:
                raise SystemExit(f"spend log has an invalid amount {r['quoted_cost_usd']!r}: refusing")
            total += v
    return total


def scan_module():
    sys.path.insert(0, str(ROOT / "backtests" / "spx_candle_scan"))
    import scan  # noqa: E402
    return scan


# ------------------------------------------------------------------------------------------------
# hash gate
# ------------------------------------------------------------------------------------------------
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check_hashes():
    plan_hash = sha256(PLAN)
    ledger = LEDGER.read_text()
    if not re.search(rf"\b{plan_hash}\s+spx_candle_imbalance\.md\b", ledger):
        raise SystemExit(f"plan hash {plan_hash} is not in the ledger: refusing")
    rows = re.findall(r"^\| `([^`]+)`[^|]*\| `([0-9a-f]{64})` \|$", PLAN.read_text(), flags=re.M)
    if len(rows) < 12:
        raise SystemExit(f"lock record has {len(rows)} rows, expected 12")
    for path, h in rows:
        got = sha256(ROOT / path)
        if got != h:
            raise SystemExit(f"{path}: SHA-256 {got} differs from the lock record {h}: refusing")
    return {"plan_sha256": plan_hash, "lock_record": dict(rows)}


# ------------------------------------------------------------------------------------------------
# time helpers
# ------------------------------------------------------------------------------------------------
def ns_et(day: str, hms: str) -> int:
    dt = datetime.fromisoformat(f"{day}T{hms}").replace(tzinfo=ET)
    return int(dt.timestamp()) * 1_000_000_000 + dt.microsecond * 1000


# ------------------------------------------------------------------------------------------------
# pull
# ------------------------------------------------------------------------------------------------
def manifest():
    return json.loads((HERE / "quote_manifest.json").read_text())


def read_attempts():
    n = Counter()
    if ATTEMPTS.exists():
        for r in csv.DictReader(open(ATTEMPTS)):
            n[(r["day"], r["dataset"])] += 1
    return n


def append_row(path: Path, fields: list[str], row: dict):
    new = not path.exists()
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)
        fh.flush()
        os.fsync(fh.fileno())


def rel(f: Path) -> str:
    return str(f.relative_to(ROOT)) if ROOT in f.parents else str(f)


def file_for(day: str, ds: str) -> Path:
    return OUT / ds / f"{day}.csv.gz"


def validate_csv(body: bytes, day: str | None = None, syms: list[str] | None = None) -> int:
    """Number of data rows in a complete imbalance CSV for the request; ValueError (or UnicodeDecodeError) if the body
    is empty or has no data rows (every signal day has records for its stocks, so an empty answer is treated as a
    failed attempt), is truncated, has another header, a row with the wrong number of fields or a non-integer
    ts_recv, or (when day and syms are given) a record outside the day's 15:50-16:00 window or of a symbol that was
    not requested."""
    if body == b"":
        raise ValueError("empty response")
    text = body.decode("utf-8")
    if not text.endswith("\n"):
        raise ValueError("no final newline (truncated?)")
    rd = csv.reader(io.StringIO(text))
    hdr = next(rd)
    if ",".join(hdr) != HEADER:
        raise ValueError(f"unexpected header {','.join(hdr)[:120]!r}")
    n = 0
    for row in rd:
        n += 1
        if len(row) != len(hdr):
            raise ValueError(f"data row {n} has {len(row)} fields, header {len(hdr)}")
        t = parse_int(row[0])
        if t is None:
            raise ValueError(f"data row {n}: ts_recv {row[0]!r} is not an integer")
        if day is not None and not (ns_et(day, "15:50:00") <= t < ns_et(day, "16:00:00")):
            raise ValueError(f"data row {n}: ts_recv {t} is outside {day} 15:50-16:00 ET")
        if syms is not None and row[-1] not in syms:
            raise ValueError(f"data row {n}: symbol {row[-1]!r} was not requested")
    if n == 0:
        raise ValueError("no data rows")
    return n


def read_downloads() -> dict:
    """(day, dataset) -> the last download-manifest row for it."""
    out = {}
    if DOWNLOADS.exists():
        for r in csv.DictReader(open(DOWNLOADS, newline="")):
            out[(r["day"], r["dataset"])] = r
    return out


def verify_file(day: str, ds: str, downloads: dict, syms: list[str]) -> int:
    """The saved file must match its download-manifest row (SHA-256 of the uncompressed CSV and row count) and be a
    complete imbalance CSV. Returns the row count; SystemExit otherwise (never spend or analyse on a bad file)."""
    f, row = file_for(day, ds), downloads.get((day, ds))
    if row is None:
        raise SystemExit(f"{f} has no row in {DOWNLOADS.name}: refusing (inspect it by hand)")
    body = gzip.decompress(f.read_bytes())
    if hashlib.sha256(body).hexdigest() != row["sha256_uncompressed"]:
        raise SystemExit(f"{f}: SHA-256 differs from {DOWNLOADS.name}: refusing")
    try:
        n = validate_csv(body, day, syms)
    except (ValueError, UnicodeDecodeError) as e:
        raise SystemExit(f"{f}: not a complete imbalance CSV for the request ({e}): refusing")
    if n != int(row["rows"]):
        raise SystemExit(f"{f}: {n} rows, {DOWNLOADS.name} says {row['rows']}: refusing")
    return n


def recover_tmp(day: str, ds: str, downloads: dict, syms: list[str]) -> bool:
    """A crash after the manifest row but before the rename leaves a complete temporary file: if it matches its
    manifest row and validates, move it into place instead of paying for it again."""
    f = file_for(day, ds)
    tmp = f.with_name(f.name + ".tmp")
    row = downloads.get((day, ds))
    if f.exists() or not tmp.exists() or row is None:
        return False
    try:
        body = gzip.decompress(tmp.read_bytes())
        ok = (hashlib.sha256(body).hexdigest() == row["sha256_uncompressed"]
              and validate_csv(body, day, syms) == int(row["rows"]))
    except (OSError, EOFError, ValueError, UnicodeDecodeError, gzip.BadGzipFile):
        ok = False
    if ok:
        os.replace(tmp, f)
        print(f"recovered {f.name} ({ds}) from its committed temporary file", flush=True)
    return ok


def save_download(day: str, ds: str, body: bytes, cost_repr: str, n_rows: int):
    """Durable order: the gzip goes to a temporary file (fsynced), the manifest row is appended (fsynced), and only
    then is the file renamed into place, so a saved file always has its manifest row. A crash before the rename
    leaves no file, and the pair is requested again later with a new reservation."""
    f = file_for(day, ds)
    tmp = f.with_name(f.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(gzip.compress(body, 6))
        fh.flush()
        os.fsync(fh.fileno())
    append_row(DOWNLOADS, DL_FIELDS, {"day": day, "dataset": ds, "rows": n_rows,
                                      "sha256_uncompressed": hashlib.sha256(body).hexdigest(),
                                      "quoted_cost_usd": cost_repr, "file": rel(f)})
    os.replace(tmp, f)
    dfd = os.open(f.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def request_params(day: str, ds: str, syms: list[str]) -> dict:
    return {"dataset": ds, "symbols": ",".join(syms), "schema": "imbalance", "start": ns_et(day, "15:50:00"),
            "end": ns_et(day, "16:00:00"), "stype_in": "raw_symbol"}


MAX_FAILED_PER_PULL = 5      # circuit breaker: a systematic problem must not burn many paid attempts


def cmd_pull(workers: int, limit: int | None = None):
    OUT.mkdir(parents=True, exist_ok=True)
    lock_fh = open(OUT / ".pull.lock", "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.close()
        raise SystemExit("another pull is running: refusing")
    try:
        return _pull(workers, limit)
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


def _pull(workers: int, limit: int | None = None):
    m = manifest()
    logged = spent()
    if logged < MIN_LOGGED:
        raise SystemExit(f"logged spend ${logged:.4f} is below the ${MIN_LOGGED} at the lock: refusing")
    attempts, downloads = read_attempts(), read_downloads()
    todo = []
    for day, by in sorted(m["days"].items()):
        for ds in DATASETS:
            recover_tmp(day, ds, downloads, by[ds]["symbols"])
            if file_for(day, ds).exists():
                verify_file(day, ds, downloads, by[ds]["symbols"])
                continue
            if attempts[(day, ds)] >= MAX_ATTEMPTS:
                continue
            todo.append((day, ds, by[ds]["symbols"], float(by[ds]["quoted_cost_usd"])))
    if limit is not None:
        todo = todo[:limit]
    if todo:
        api_key()                     # load the key once, before any worker thread starts
    print(f"{len(todo)} requests to make; logged spend ${spent():.4f}", flush=True)
    for ds in DATASETS:
        (OUT / ds).mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    state = {"stop": None, "saved": 0, "failed": 0}

    def fail(msg):
        with lock:
            state["failed"] += 1
            if state["failed"] >= MAX_FAILED_PER_PULL and not state["stop"]:
                state["stop"] = f"STOP: {state['failed']} failures in this pull (circuit breaker)"
        print(msg, flush=True)

    def one(item):
        day, ds, syms, frozen = item
        if state["stop"]:
            return
        p = request_params(day, ds, syms)
        try:
            cost = float(json.loads(http_post("metadata.get_cost", p, paid=False)))
        except (RequestFailed, ValueError, TypeError) as e:
            fail(f"QUOTE FAILED {day} {ds} (nothing reserved): {str(e)[:200]}")
            return
        f = file_for(day, ds)
        with lock:
            if state["stop"]:
                return
            if not math.isfinite(cost) or cost < 0:
                state["stop"] = f"STOP at {day} {ds}: invalid quote {cost!r}"
                return
            if abs(cost - frozen) > 0.01 * frozen + 1e-9:
                state["stop"] = f"STOP at {day} {ds}: quote ${cost:.6f} differs from the frozen ${frozen:.6f}"
                return
            logged = spent()
            if logged + cost > CAP + 1e-12:
                state["stop"] = f"STOP before {day} {ds}: ${logged:.4f} logged + ${cost:.4f} would pass ${CAP}"
                return
            utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            append_row(SPEND_LOG, SPEND_COLUMNS, {
                "utc_time": utc, "schema": f"imbalance:{ds}", "day": day, "n_symbols": len(syms),
                "quoted_cost_usd": repr(cost), "rows": "reserved", "file": rel(f)})
            append_row(ATTEMPTS, ATT_FIELDS, {"utc_time": utc, "day": day, "dataset": ds,
                                              "quoted_cost_usd": repr(cost)})
        try:
            body = http_post("timeseries.get_range", {**p, "encoding": "csv", "compression": "none",
                                                      "pretty_px": "false", "pretty_ts": "false",
                                                      "map_symbols": "true"}, paid=True)
        except RequestFailed as e:
            fail(f"FAILED {day} {ds} (reservation kept): {str(e)[:200]}")
            return
        try:
            n_rows = validate_csv(body, day, syms)
        except (ValueError, UnicodeDecodeError) as e:
            bad = OUT / "rejected" / f"{ds}_{day}_{time.time_ns()}.bin"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_bytes(body)
            fail(f"REJECTED {day} {ds} (reservation kept; body saved to {bad.name}): {str(e)[:200]}")
            return
        with lock:
            save_download(day, ds, body, repr(cost), n_rows)
            state["saved"] += 1
            if state["saved"] % 100 == 0:
                print(f"{state['saved']} saved, logged ${spent():.4f}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))
    if state["stop"]:
        print(state["stop"], flush=True)
    have = sum(1 for d in m["days"] for ds in DATASETS if file_for(d, ds).exists())
    print(f"saved this run {state['saved']}, failed {state['failed']}; files {have} of {2 * len(m['days'])}; "
          f"logged spend ${spent():.4f}", flush=True)
    return state


# ------------------------------------------------------------------------------------------------
# imbalance measure (pure functions, tested by the selftest)
# ------------------------------------------------------------------------------------------------
def parse_int(x: str):
    x = (x or "").strip()
    if not re.fullmatch(r"-?\d+", x):
        return None
    return int(x)


def usable(rec: dict):
    """Return (side, qty, price) for a usable record, or (None, reason)."""
    side = SIDE.get((rec.get("side") or "").strip())
    if side is None:
        return None, "bad_side"
    q = parse_int(rec.get("total_imbalance_qty"))
    if q is None or q == UNDEF_ORDER_SIZE:
        return None, "bad_qty"
    p = parse_int(rec.get("ref_price"))
    if p is None or p == UNDEF_PRICE or p <= 0:
        return None, "bad_price"
    return (side, q, p), None


def pick(records: list[dict], ds: str, lo: int, hi: int, which: str):
    """records: one stock's rows in file order. Closing codes only, ts_recv in [lo, hi). Earliest (ties: first in
    file order) or latest (ties: last in file order)."""
    best, best_t = None, None
    for r in records:
        if (r.get("auction_type") or "").strip() not in CLOSING_CODES[ds]:
            continue
        t = parse_int(r.get("ts_recv"))
        if t is None or not (lo <= t < hi):
            continue
        if best is None or (which == "first" and t < best_t) or (which == "last" and t >= best_t):
            best, best_t = r, t
    return best


def day_measure(rows_by_ds: dict, symbols_by_ds: dict, day: str, which: str = "first", venues=DATASETS):
    """D (int, 1e-9 dollars), usable stock count, and per-reason counts for one day."""
    lo, hi = ns_et(day, "15:50:00"), ns_et(day, "15:51:00")
    D, n_ok, reasons = 0, 0, Counter()
    for ds in venues:
        per = defaultdict(list)
        for r in rows_by_ds.get(ds, []):
            per[r.get("symbol")].append(r)
        for s in symbols_by_ds.get(ds, []):
            rec = pick(per.get(s, []), ds, lo, hi, which)
            if rec is None:
                reasons["no_record"] += 1
                continue
            u, why = usable(rec)
            if u is None:
                reasons[why] += 1
                continue
            side, q, p = u
            D += side * q * p
            n_ok += 1
    return D, n_ok, reasons


def sign(x: int) -> int:
    """Sign of an exact Python integer (D can exceed the int64 range, so NumPy is not used)."""
    return (x > 0) - (x < 0)


def classify(D: int, n_ok: int) -> str:
    if n_ok < MIN_STOCKS:
        return "uncovered"
    if D == 0:
        return "zero"
    return "classified"


# ------------------------------------------------------------------------------------------------
# statistics (pure)
# ------------------------------------------------------------------------------------------------
def h1(hits_a: list[int], hits_d: list[int]):
    """Hit rates, d, se and t are reported whenever they can be computed (descriptive); the verdict needs both
    groups >= 30 and se > 0 ("not evaluable" otherwise, which counts as not passed)."""
    na, nd = len(hits_a), len(hits_d)
    out = {"n_agree": na, "n_disagree": nd}
    if na:
        out["hit_agree"] = sum(hits_a) / na
    if nd:
        out["hit_disagree"] = sum(hits_d) / nd
    se = None
    if na and nd:
        ha, hd = out["hit_agree"], out["hit_disagree"]
        se = math.sqrt(ha * (1 - ha) / na + hd * (1 - hd) / nd)
        out.update({"d": ha - hd, "se": se})
        if se > 0:
            out["t"] = (ha - hd) / se
    if na < MIN_GROUP or nd < MIN_GROUP:
        return {**out, "evaluable": False, "passed": False, "reason": "group below 30"}
    if se == 0:
        return {**out, "evaluable": False, "passed": False, "reason": "se is 0"}
    return {**out, "evaluable": True, "passed": bool(out["d"] > 0 and out["t"] >= 2.0)}


def binom_upper(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    return float(Fraction(sum(math.comb(n, i) for i in range(k, n + 1)), 2 ** n))


def holm2(p2: float, p3: float):
    order = [("H2", p2), ("H3", p3)]
    order.sort(key=lambda x: (x[1], 0 if x[0] == "H2" else 1))
    first, second = order
    r1 = first[1] <= 0.025
    r2 = r1 and second[1] <= 0.05
    return {first[0]: r1, second[0]: r2, "order": [first[0], second[0]]}


def welch(a: list[float], b: list[float], zero_variance_group_ok: bool = True):
    """Welch t of mean(a) - mean(b). Not evaluable with fewer than 2 in a group or se = 0; with
    zero_variance_group_ok=False (option P&L, plan section 7 item 5) also when either group has zero variance."""
    na, nb = len(a), len(b)
    out = {"n_a": na, "n_b": nb}
    if na:
        out["mean_a"] = float(np.mean(a))
    if nb:
        out["mean_b"] = float(np.mean(b))
    if na and nb:
        out["diff"] = out["mean_a"] - out["mean_b"]
    if na < 2 or nb < 2:
        return {**out, "evaluable": False}
    va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    se = math.sqrt(va / na + vb / nb)
    if se > 0:
        out["t"] = out["diff"] / se
    if se == 0 or (not zero_variance_group_ok and (va == 0 or vb == 0)):
        return {**out, "evaluable": False}
    return {**out, "evaluable": True}


def wilson(k: int, n: int, z: float = 1.959963984540054):
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [c - w, c + w]


def bootstrap_d(n_days: int, rows: dict, rng, draws=BOOT_DRAWS, block=BOOT_BLOCK):
    """rows: day index -> (agree: bool, hit: int) for classified, outcome-eligible signal days."""
    starts_max = n_days - block
    ds, dropped = [], 0
    for _ in range(draws):
        idx = []
        while len(idx) < n_days:
            s = int(rng.integers(0, starts_max + 1))
            idx.extend(range(s, s + block))
        idx = idx[:n_days]
        a = [rows[i][1] for i in idx if i in rows and rows[i][0]]
        d = [rows[i][1] for i in idx if i in rows and not rows[i][0]]
        if len(a) < MIN_GROUP or len(d) < MIN_GROUP:
            dropped += 1
            continue
        ds.append(sum(a) / len(a) - sum(d) / len(d))
    out = {"attempted": draws, "kept": len(ds), "dropped": dropped}
    if ds:
        lo, hi = np.percentile(ds, [2.5, 97.5])
        out.update({"p2_5": float(lo), "p97_5": float(hi), "reliable": len(ds) >= BOOT_MIN_OK})
    return out


# ------------------------------------------------------------------------------------------------
# run
# ------------------------------------------------------------------------------------------------
def read_day_rows(day: str):
    rows = {}
    for ds in DATASETS:
        f = file_for(day, ds)
        if not f.exists():
            return None
        rows[ds] = list(csv.DictReader(io.StringIO(gzip.decompress(f.read_bytes()).decode())))
    return rows


RUN_OUTPUTS = ("run_started.json", "results.json", "RESULTS.md", "agreement_days.csv")


RUN_LEDGER_FIELDS = ["utc_time", "event", "plan_sha256", "defect_rerun_reason"]


def cmd_run(defect: str | None):
    """Holds an exclusive lock for the whole run. runs_ledger.csv (never archived or rewritten) gets a durable
    "start" row before anything is archived or any outcome is read; any earlier row means a run has started, and
    a new run then needs --defect."""
    RES_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    lock_fh = open(RES_DIR / ".run.lock", "w")
    pull_fh = open(OUT / ".pull.lock", "w")
    try:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit("another run is in progress: refusing")
        try:
            fcntl.flock(pull_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)      # no download may be in flight during a run
        except OSError:
            raise SystemExit("a pull is running: refusing (wait for it to finish)")
        _run(defect)
    finally:
        pull_fh.close()
        lock_fh.close()


def fsync_dir(d: Path):
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _run(defect: str | None):
    res_path, start_path, ledger = RES_DIR / "results.json", RES_DIR / "run_started.json", RES_DIR / "runs_ledger.csv"
    started = ledger.exists() or start_path.exists() or res_path.exists()
    if started and not defect:
        raise SystemExit("a registered run has already started (runs_ledger.csv): one registered run only; use "
                         "--defect \"reason\" for a documented defect")
    gate = check_hashes()
    m = manifest()
    for day, by in m["days"].items():
        a, b = by["XNYS.PILLAR"]["symbols"], by["XNAS.ITCH"]["symbols"]
        assert len(set(a)) == len(a) and len(set(b)) == len(b) and not set(a) & set(b) and len(a) + len(b) == 50, day
    days = list(m["days"])
    sig = [(r["date"], int(r["direction"])) for r in csv.DictReader(open(HERE / "signal_days.csv"))]
    assert [d for d, _ in sig] == days, "signal days differ from the quote manifest"
    attempts, downloads = read_attempts(), read_downloads()
    for d in days:
        for ds in DATASETS:
            recover_tmp(d, ds, downloads, m["days"][d][ds]["symbols"])
    missing = [(d, ds) for d in days for ds in DATASETS if not file_for(d, ds).exists()]
    retryable = [x for x in missing if attempts[x] < MAX_ATTEMPTS]
    if retryable:
        raise SystemExit(f"{len(retryable)} downloads missing with attempts left; run `pull` again first")
    n_files = 0
    for d in days:
        for ds in DATASETS:
            if file_for(d, ds).exists():
                verify_file(d, ds, downloads, m["days"][d][ds]["symbols"])
                n_files += 1
    # every check passed: record the start durably, then archive a previous run's outputs (defect rerun)
    append_row(ledger, RUN_LEDGER_FIELDS, {"utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           "event": "start", "plan_sha256": gate["plan_sha256"],
                                           "defect_rerun_reason": defect or ""})
    fsync_dir(RES_DIR)
    if started:
        k = 1
        while any((RES_DIR / n.replace(".", f"_run{k}.", 1)).exists() for n in RUN_OUTPUTS):
            k += 1
        for name in RUN_OUTPUTS:
            if (RES_DIR / name).exists():
                (RES_DIR / name).rename(RES_DIR / name.replace(".", f"_run{k}.", 1))
    fd = os.open(start_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as fh:
        json.dump({"started_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "plan_sha256": gate["plan_sha256"], "defect_rerun_reason": defect, "files_verified": n_files,
                   "pairs_missing_after_3_attempts": [list(x) for x in missing]}, fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    fsync_dir(RES_DIR)

    # 1) classification of every signal day, before any outcome is read
    cls = {}
    rob = {"last": {}, "nyse": {}, "nasdaq": {}}
    reasons_total, rec_count, first_times = Counter(), defaultdict(list), defaultdict(list)
    in_minute = defaultdict(Counter)
    all_records = defaultdict(Counter)
    for day, s in sig:
        rows = read_day_rows(day)
        syms = {ds: m["days"][day][ds]["symbols"] for ds in DATASETS}
        if rows is None:
            cls[day] = {"s": s, "D": None, "n_ok": 0, "status": "download_failed"}
            for k in rob:
                rob[k][day] = cls[day]
            continue
        D, n_ok, why = day_measure(rows, syms, day, "first")
        reasons_total.update(why)
        reasons_total["usable"] += n_ok
        cls[day] = {"s": s, "D": D, "n_ok": n_ok, "status": classify(D, n_ok)}
        for key, kw in (("last", {"which": "last"}), ("nyse", {"venues": ("XNYS.PILLAR",)}),
                        ("nasdaq", {"venues": ("XNAS.ITCH",)})):
            D2, n2, _ = day_measure(rows, syms, day, **kw)
            rob[key][day] = {"s": s, "D": D2, "n_ok": n2, "status": classify(D2, n2)}
        lo, hi = ns_et(day, "15:50:00"), ns_et(day, "15:51:00")
        for ds in DATASETS:
            per_all = Counter(r.get("symbol") for r in rows[ds])
            first_ts = {}
            for r in rows[ds]:
                if (r.get("auction_type") or "").strip() not in CLOSING_CODES[ds]:
                    continue
                t = parse_int(r.get("ts_recv"))
                if t is not None and t >= lo and (r.get("symbol") not in first_ts or t < first_ts[r.get("symbol")]):
                    first_ts[r.get("symbol")] = t
            listed = set(syms[ds])
            for r in rows[ds]:
                if r.get("symbol") not in listed or (r.get("auction_type") or "").strip() not in CLOSING_CODES[ds]:
                    continue
                t = parse_int(r.get("ts_recv"))
                if t is not None and lo <= t < hi:
                    u, why = usable(r)
                    all_records[ds]["usable" if u is not None else why] += 1
            for sym in syms[ds]:
                rec_count[ds].append(per_all.get(sym, 0))
                if sym in first_ts:
                    first_times[ds].append((first_ts[sym] - lo) / 1e9)
                in_minute[ds]["closing_record_in_15_50_minute" if sym in first_ts and first_ts[sym] < hi
                              else "none_in_15_50_minute"] += 1
    for d in cls.values():
        d["agree"] = (d["status"] == "classified") and (sign(d["D"]) == d["s"])
    with open(RES_DIR / "agreement_days.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "s", "D_1e-9_usd", "usable_stocks", "status", "agreement"])
        for day, d in cls.items():
            w.writerow([day, d["s"], "" if d["D"] is None else d["D"], d["n_ok"], d["status"],
                        "" if d["status"] != "classified" else ("agree" if d["agree"] else "disagree")])
        fh.flush()
        os.fsync(fh.fileno())
    fsync_dir(RES_DIR)
    agreement_sha = sha256(RES_DIR / "agreement_days.csv")

    # 2) outcomes
    scan = scan_module()
    P = scan.load_panel(START, END)
    pdates = [str(x) for x in P.dates]
    assert len(pdates) == 1446 and pdates == sorted(pdates), len(pdates)
    o, h, l_, c = scan.candle_1m(P, scan.mi("15:50"))
    o51 = P.O[:, scan.mi("15:51")]
    c59 = P.C[:, scan.mi("15:59")]
    pos = {d: i for i, d in enumerate(pdates)}
    y = {}
    for day, s in sig:
        i = pos[day]
        with np.errstate(invalid="ignore"):
            strong = (np.isfinite([o[i], h[i], l_[i], c[i]]).all() and h[i] - l_[i] > 0
                      and abs(c[i] - o[i]) >= 0.6 * (h[i] - l_[i]))
        assert strong and (1 if c[i] > o[i] else -1) == s, f"signal mismatch on {day}"
        a, b = o51[i], c59[i]
        if np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0 and math.log(b / a) != 0:
            y[day] = math.log(b / a)

    def groups(table):
        A, Dg = [], []
        for day, d in table.items():
            if d["status"] != "classified" or day not in y:
                continue
            hit = int(d["s"] * y[day] > 0)
            agree = sign(d["D"]) == d["s"]
            (A if agree else Dg).append((day, hit))
        return A, Dg

    A, Dg = groups(cls)
    U = [(d, int(cls[d]["s"] * y[d] > 0)) for d in cls if cls[d]["status"] != "classified" and d in y]
    primary = h1([x for _, x in A], [x for _, x in Dg])
    classified = [d for d in cls if cls[d]["status"] == "classified"]
    k2 = sum(1 for d in classified if cls[d]["agree"])
    p2 = binom_upper(k2, len(classified))
    elig3 = [d for d in classified if d in y]
    k3 = sum(1 for d in elig3 if sign(cls[d]["D"]) * y[d] > 0)
    p3 = binom_upper(k3, len(elig3))
    secondary = {"H2": {"classified": len(classified), "agree": k2, "share": k2 / len(classified) if classified
                        else None, "p_upper": p2, "evaluable": len(classified) > 0},
                 "H3": {"n": len(elig3), "imbalance_right": k3, "share": k3 / len(elig3) if elig3 else None,
                        "p_upper": p3, "evaluable": len(elig3) > 0},
                 "holm": holm2(p2, p3)}

    # robustness
    rows_b = {pos[d]: (True, x) for d, x in A}
    rows_b.update({pos[d]: (False, x) for d, x in Dg})
    boot = bootstrap_d(len(pdates), rows_b, np.random.default_rng(BOOT_SEED))
    robust = {"bootstrap_d": boot}
    for key in ("last", "nyse", "nasdaq"):
        a2, d2 = groups(rob[key])
        robust[f"h1_{key}"] = h1([x for _, x in a2], [x for _, x in d2])
        robust[f"h1_{key}"]["status_counts"] = dict(Counter(v["status"] for v in rob[key].values()))
    robust["signed_move_bps"] = welch([cls[d]["s"] * y[d] * 1e4 for d, _ in A],
                                      [cls[d]["s"] * y[d] * 1e4 for d, _ in Dg])
    opt = [r for r in csv.DictReader(open(ROOT / "data/spx_1549/databento/realprice_trades.csv"))
           if r["config"] == "current" and r["period"] == "confirmation" and r["cell"] == OPTION_CELL
           and r["status"] == "priced"]
    assert len(opt) == 585 and len({r["date"] for r in opt}) == 585
    oa = [float(r["pnl_fee_0.09"]) for r in opt if cls.get(r["date"], {}).get("status") == "classified"
          and cls[r["date"]]["agree"]]
    od = [float(r["pnl_fee_0.09"]) for r in opt if cls.get(r["date"], {}).get("status") == "classified"
          and not cls[r["date"]]["agree"]]
    robust["option_pnl_usd"] = welch(oa, od, zero_variance_group_ok=False)
    cells = defaultdict(lambda: ([], []))
    for lst, is_a in ((A, True), (Dg, False)):
        for day, x in lst:
            cells[(day[:4], cls[day]["s"])][0 if is_a else 1].append(x)
    num, den, used = 0.0, 0.0, 0
    for (yr, s), (a, d) in sorted(cells.items()):
        if a and d:
            w = len(a) * len(d) / (len(a) + len(d))
            num += w * (sum(a) / len(a) - sum(d) / len(d))
            den += w
            used += 1
    robust["year_direction_adjusted_d"] = {"d": num / den if den else None, "cells_used": used}

    # descriptive
    by_year = {}
    for yr in sorted({d[:4] for d in cls}):
        dd = [d for d in cls if d[:4] == yr]
        row = {"signal_days": len(dd), "status": dict(Counter(cls[d]["status"] for d in dd)),
               "classified_agree_days": sum(1 for d in dd if cls[d]["status"] == "classified" and cls[d]["agree"]),
               "classified_disagree_days": sum(1 for d in dd if cls[d]["status"] == "classified"
                                               and not cls[d]["agree"])}
        for name, lst in (("agree", A), ("disagree", Dg), ("unclassified", U)):
            xs = [(d, x) for d, x in lst if d[:4] == yr]
            k, n = sum(x for _, x in xs), len(xs)
            row[name] = {"n": n, "hits": k, "hit_rate": k / n if n else None, "wilson95": wilson(k, n),
                         "mean_signed_move_bps": float(np.mean([cls[d]["s"] * y[d] * 1e4 for d, _ in xs]))
                         if xs else None}
        by_year[yr] = row
    descriptive = {
        "by_year": by_year,
        "status_counts": dict(Counter(v["status"] for v in cls.values())),
        "outcome_excluded_signal_days": len(sig) - len(y),
        "stock_days_by_status_first_record": dict(reasons_total),
        "closing_record_in_15_50_minute": {ds: dict(v) for ds, v in in_minute.items()},
        "all_closing_records_in_15_50_minute_by_status": {ds: dict(v) for ds, v in all_records.items()},
        "records_per_stock_day_15_50_to_16_00": {ds: {"median": float(np.median(v)), "min": int(min(v)),
                                                      "max": int(max(v))} for ds, v in rec_count.items()},
        "first_closing_record_after_15_50_seconds": {ds: {"median": float(np.median(v)), "max": float(max(v))}
                                                     for ds, v in first_times.items()},
        "usable_stocks_per_day": {"median": float(np.median([v["n_ok"] for v in cls.values()])),
                                  "min": int(min(v["n_ok"] for v in cls.values()))},
    }
    results = {"plan": "preregistration/spx_candle_imbalance.md", "hash_gate": gate,
               "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "defect_rerun_reason": defect, "agreement_days_sha256": agreement_sha,
               "H1_primary": primary, "secondary": secondary, "robustness": robust, "descriptive": descriptive}
    res_path.write_text(json.dumps(results, indent=1, default=float) + "\n")
    write_md(results)
    append_row(ledger, RUN_LEDGER_FIELDS, {"utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           "event": "finished", "plan_sha256": gate["plan_sha256"],
                                           "defect_rerun_reason": defect or ""})
    print(json.dumps({"H1": primary, "H2": secondary["H2"], "H3": secondary["H3"], "holm": secondary["holm"],
                      "bootstrap": boot}, indent=1, default=float))


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def write_md(r):
    p = r["H1_primary"]
    s = r["secondary"]
    rb = r["robustness"]
    b = rb["bootstrap_d"]
    L = ["# Closing-imbalance test: results of the registered run", "",
         f"Plan: `{r['plan']}` (SHA-256 `{r['hash_gate']['plan_sha256']}`). Run {r['run_utc']}.", "",
         "## Primary (H1)", ""]
    def rate(key):
        return pct(p.get(key))
    L.append(f"- Agreeing days: {p['n_agree']}, hit rate {rate('hit_agree')}; disagreeing days: {p['n_disagree']}, "
             f"hit rate {rate('hit_disagree')}.")
    if "d" in p:
        L.append(f"- d = {100 * p['d']:.1f} points, se {100 * p['se']:.1f}"
                 + (f", t = {p['t']:.2f}." if "t" in p else ", t undefined."))
    if p["evaluable"]:
        L.append(f"- **H1 {'PASSED' if p['passed'] else 'NOT PASSED'}** (bar: d > 0 and t >= 2.0).")
    else:
        L.append(f"- Not evaluable ({p['reason']}). **H1 NOT PASSED.**")
    L.append(f"- Block bootstrap of d (20-day blocks, {b['kept']} of {b['attempted']} draws kept): "
             f"{100 * b['p2_5']:.1f} to {100 * b['p97_5']:.1f} points"
             f"{'' if b.get('reliable') else ' (unreliable: fewer than 9,000 draws kept)'}." if "p2_5" in b
             else "- Block bootstrap of d: no draw kept.")
    L += ["", "## Secondary (decide nothing)", "",
          f"- H2 agreement: {s['H2']['agree']} of {s['H2']['classified']} classified days "
          f"({pct(s['H2']['share'])}), one-sided p = {s['H2']['p_upper']:.4g}.",
          f"- H3 imbalance direction alone right: {s['H3']['imbalance_right']} of {s['H3']['n']} "
          f"({pct(s['H3']['share'])}), one-sided p = {s['H3']['p_upper']:.4g}.",
          f"- Holm: H2 {'rejects' if s['holm']['H2'] else 'does not reject'} 1/2, H3 "
          f"{'rejects' if s['holm']['H3'] else 'does not reject'} 1/2.", "", "## Robustness (reported only)", ""]
    for k, label in (("h1_last", "Last record before 15:51"), ("h1_nyse", "NYSE stocks only"),
                     ("h1_nasdaq", "Nasdaq stocks only")):
        q = rb[k]
        L.append(f"- {label}: {pct(q.get('hit_agree'))} vs {pct(q.get('hit_disagree'))} (n {q['n_agree']} / "
                 f"{q['n_disagree']})" + (f", d {100 * q['d']:.1f} points" if "d" in q else "")
                 + (f", t {q['t']:.2f}" if "t" in q else "")
                 + ("." if q["evaluable"] else f"; not evaluable ({q.get('reason')})."))
    for k, label, unit in (("signed_move_bps", "Signed move to the close", "bps"),
                           ("option_pnl_usd", "Option P&L at the ask (ITM10, $0.09 fee)", "$ per trade")):
        q = rb[k]
        def num(key):
            return f"{q[key]:.2f}" if key in q else "n/a"
        L.append(f"- {label}: agree {num('mean_a')}, disagree {num('mean_b')} {unit} (n {q['n_a']} / {q['n_b']}), "
                 f"difference {num('diff')}" + (f", Welch t {q['t']:.2f}" if q["evaluable"] else
                                                "; Welch t not evaluable") + ".")
    adj = rb["year_direction_adjusted_d"]
    L.append(f"- Year-and-direction adjusted d: " + ("n/a" if adj["d"] is None else
                                                      f"{100 * adj['d']:.1f} points ({adj['cells_used']} cells)."))
    d = r["descriptive"]
    L += ["", "## Descriptive", "", f"- Day status: {d['status_counts']}; signal days without an eligible outcome: "
          f"{d['outcome_excluded_signal_days']}.",
          f"- Usable stocks per day: median {d['usable_stocks_per_day']['median']:.0f}, minimum "
          f"{d['usable_stocks_per_day']['min']}. Stock-days by status of the first record: "
          f"{d['stock_days_by_status_first_record']}.", "",
          "| Year | Signal days | Agree n | Agree hit (95% CI) | Disagree n | Disagree hit (95% CI) | "
          "Unclassified n | Unclassified hit (95% CI) |",
          "|---|---|---|---|---|---|---|---|"]
    for yr, row in d["by_year"].items():
        def cell(g):
            if not g["n"]:
                return "n/a"
            lo, hi = g["wilson95"]
            return f"{pct(g['hit_rate'])} ({100 * lo:.0f}-{100 * hi:.0f})"
        L.append(f"| {yr} | {row['signal_days']} | {row['agree']['n']} | {cell(row['agree'])} | "
                 f"{row['disagree']['n']} | {cell(row['disagree'])} | {row['unclassified']['n']} | "
                 f"{cell(row['unclassified'])} |")
    L += ["", "Classified signal days by year, whatever the outcome (the table above counts only days with an eligible "
          "outcome):", "", "| Year | Signal days | Classified, agree | Classified, disagree | Status counts |",
          "|---|---|---|---|---|"]
    for yr, row in d["by_year"].items():
        L.append(f"| {yr} | {row['signal_days']} | {row['classified_agree_days']} | {row['classified_disagree_days']} "
                 f"| {row['status']} |")
    L += ["", "All closing-imbalance records of list stocks with ts_recv in the 15:50 minute, by status (every record, "
          f"not only the first per stock): {d['all_closing_records_in_15_50_minute_by_status']}.",
          f"Stocks with at least one closing record in the 15:50 minute (stock-days): "
          f"{d['closing_record_in_15_50_minute']}.", "", "Research only; not investment advice."]
    (RES_DIR / "RESULTS.md").write_text("\n".join(L) + "\n")


# ------------------------------------------------------------------------------------------------
# selftest (synthetic data only)
# ------------------------------------------------------------------------------------------------
class _FixedStarts:
    """Stand-in for a NumPy Generator: returns the given block starts in order and checks the start range."""
    def __init__(self, starts, n_days, block):
        self.starts, self.n_days, self.block = list(starts), n_days, block

    def integers(self, lo, hi):
        assert (lo, hi) == (0, self.n_days - self.block + 1), (lo, hi)   # every start that fits, no wrap-around
        return self.starts.pop(0)


def _selftest_bootstrap():
    # 100 days, 20-day blocks; days 0-19 agree & hit, 20-39 agree & miss, 40-59 disagree (half hit), 60-99 none
    rows = {i: (True, 1) for i in range(20)}
    rows.update({i: (True, 0) for i in range(20, 40)})
    rows.update({i: (False, i % 2) for i in range(40, 60)})
    # starts 0, 0, 20, 40, 40: days 0-19 and 40-59 drawn twice. With multiplicity: agree 40 hits of 60, disagree
    # 20 of 40 -> d = 2/3 - 1/2. A version that dropped repeats would see 20 + 20 agree and 20 disagree (< 30).
    r = bootstrap_d(100, rows, _FixedStarts([0, 0, 20, 40, 40], 100, 20), draws=1, block=20)
    assert r["kept"] == 1 and abs(r["p2_5"] - (2 / 3 - 1 / 2)) < 1e-12, r
    # truncation: 50 days need 3 blocks (60 days) cut to 50; the third block's last 10 days are dropped
    rows2 = {i: (True, 1) for i in range(30)}
    rows2.update({i: (False, 0) for i in range(30, 50)})
    # starts 0, 0, 30: agree 0-19 twice (40), disagree only 30-39 (10, the cut) -> group below 30, dropped
    r2 = bootstrap_d(50, rows2, _FixedStarts([0, 0, 30], 50, 20), draws=1, block=20)
    assert r2["kept"] == 0 and r2["dropped"] == 1
    # one kept draw and one dropped draw are both counted
    r3 = bootstrap_d(100, rows, _FixedStarts([0, 0, 20, 40, 40, 60, 60, 60, 60, 60], 100, 20), draws=2, block=20)
    assert (r3["kept"], r3["dropped"], r3["reliable"]) == (1, 1, False)


def _selftest_pull():
    """The pull on fake endpoints in a temporary folder: reservation on disk before every paid call, no automatic
    retry, rejection of a truncated body, skip of saved pairs, the three-attempt limit, the cap, a changed quote,
    a non-finite quote, a failed reservation, a tampered file and a second concurrent pull."""
    import tempfile
    global OUT, ATTEMPTS, DOWNLOADS, SPEND_LOG
    names = ("OUT", "ATTEMPTS", "DOWNLOADS", "SPEND_LOG", "http_post", "manifest", "append_row", "api_key")
    saved = {k: globals()[k] for k in names}
    globals()["api_key"] = lambda: "selftest-not-a-key"          # never the real key loader
    td = tempfile.TemporaryDirectory()
    try:
        tdp = Path(td.name)
        OUT, SPEND_LOG = tdp / "out", tdp / "spend_log.csv"
        ATTEMPTS, DOWNLOADS = OUT / "attempts.csv", OUT / "downloads.csv"
        real_append = saved["append_row"]
        real_append(SPEND_LOG, SPEND_COLUMNS, {"utc_time": "x", "schema": "old", "day": "", "n_symbols": 0,
                                               "quoted_cost_usd": "100", "rows": "1", "file": ""})
        def body_for(t: int, sym: str) -> bytes:
            return (HEADER + "\n" + f"{t},{t},20,9,1,10,0,0,0,0,0,0,0,1,5,0,0,C,B,0,0,0,N, ,{sym}\n").encode()
        good = body_for(ns_et("2023-06-14", "15:50:01"), "2023-06-14N")
        plan = {}
        fsyncs = {"spend_log": 0}
        real_fsync = os.fsync

        def counting_fsync(fd):
            if os.fstat(fd).st_ino == os.stat(SPEND_LOG).st_ino:
                fsyncs["spend_log"] += 1
                if fsyncs.get("fail"):
                    raise OSError("synthetic fsync failure")
            return real_fsync(fd)
        os.fsync = counting_fsync            # symbol -> {"cost": float, "paid": [behaviour per call: "ok" | "fail" | "trunc"]}
        log = []

        def fake_post(endpoint, params, *, paid):
            sym = params["symbols"]
            if endpoint == "metadata.get_cost":
                assert not paid
                log.append(("quote", sym))
                return json.dumps(plan[sym]["cost"]).encode()
            assert paid and endpoint == "timeseries.get_range"
            rows_ = list(csv.DictReader(open(SPEND_LOG, newline="")))
            last = rows_[-1]
            assert last["rows"] == "reserved" and float(last["quoted_cost_usd"]) == plan[sym]["cost"], last
            # every reservation row written so far was fsynced before this paid call
            assert fsyncs["spend_log"] >= sum(1 for r in rows_ if r["rows"] == "reserved"), fsyncs
            log.append(("paid", sym))
            what = plan[sym]["paid"].pop(0)
            if what == "fail":
                raise RequestFailed("synthetic failure")
            b = body_for(int(params["start"]) + 10 ** 9, sym)
            return {"ok": b, "trunc": b[:-5], "empty": b"", "wrongday": body_for(int(params["start"]) - 10 ** 9, sym),
                    "wrongsym": body_for(int(params["start"]) + 10 ** 9, "ZZZ")}[what]

        def man(days):
            return lambda: {"days": {d: {"XNYS.PILLAR": {"symbols": [f"{d}N"], "quoted_cost_usd": 0.5},
                                         "XNAS.ITCH": {"symbols": [f"{d}Q"], "quoted_cost_usd": 0.5}}
                                     for d in days}}
        globals()["http_post"] = fake_post
        d1, d2 = "2023-06-14", "2023-06-15"
        plan.update({f"{d1}N": {"cost": 0.5, "paid": ["ok"]}, f"{d1}Q": {"cost": 0.5, "paid": ["ok"]},
                     f"{d2}N": {"cost": 0.5, "paid": ["fail", "fail", "fail"]},
                     f"{d2}Q": {"cost": 0.5, "paid": ["trunc", "empty", "ok"]}})
        globals()["manifest"] = man([d1, d2])
        st = cmd_pull(1) or {}
        assert sum(1 for x in log if x[0] == "paid") == 4 and abs(spent() - 102.0) < 1e-9
        assert file_for(d1, "XNYS.PILLAR").exists() and file_for(d1, "XNAS.ITCH").exists()
        assert not file_for(d2, "XNYS.PILLAR").exists() and not file_for(d2, "XNAS.ITCH").exists()
        assert len(list((OUT / "rejected").iterdir())) == 1
        dl = read_downloads()
        assert verify_file(d1, "XNYS.PILLAR", dl, [f"{d1}N"]) == 1 and len(dl) == 2
        log.clear()
        cmd_pull(1)                                   # d1 skipped; d2N fails again; d2Q's empty answer rejected
        assert ("quote", f"{d1}N") not in log and not file_for(d2, "XNAS.ITCH").exists()
        log.clear()
        cmd_pull(1)                                   # third and last attempt of each d2 pair; d2Q now succeeds
        assert file_for(d2, "XNAS.ITCH").exists()
        log.clear()
        cmd_pull(1)                                   # nothing left to try
        assert log == [] and read_attempts()[(d2, "XNYS.PILLAR")] == 3 and abs(spent() - 104.0) < 1e-9
        assert len(list((OUT / "rejected").iterdir())) == 2
        # wrong day or wrong symbol in an answer: rejected, nothing saved
        for d5, what in (("2023-06-22", "wrongday"), ("2023-06-23", "wrongsym")):
            plan.update({f"{d5}N": {"cost": 0.5, "paid": [what]}, f"{d5}Q": {"cost": 0.5, "paid": [what]}})
            globals()["manifest"] = man([d5])
            cmd_pull(1)
            assert not file_for(d5, "XNYS.PILLAR").exists() and not file_for(d5, "XNAS.ITCH").exists()
        assert abs(spent() - 106.0) < 1e-9
        # the circuit breaker: five failures stop the pull (one worker: the sixth pair is never tried)
        d7 = ["2023-07-05", "2023-07-06", "2023-07-07"]
        for d in d7:
            plan.update({f"{d}N": {"cost": 0.5, "paid": ["fail"]}, f"{d}Q": {"cost": 0.5, "paid": ["fail"]}})
        globals()["manifest"] = man(d7)
        log.clear()
        st = cmd_pull(1)
        assert st["failed"] == 5 and sum(1 for x in log if x[0] == "paid") == 5 and "circuit" in st["stop"]
        SPEND_LOG.write_text("\n".join(x for x in SPEND_LOG.read_text().splitlines()
                                       if not any(d in x for d in d7)) + "\n")
        # --limit
        globals()["manifest"] = man(["2023-07-10"])
        plan.update({"2023-07-10N": {"cost": 0.5, "paid": ["ok"]}, "2023-07-10Q": {"cost": 0.5, "paid": ["ok"]}})
        st = cmd_pull(1, limit=1)
        assert st["saved"] == 1 and file_for("2023-07-10", "XNYS.PILLAR").exists()
        assert not file_for("2023-07-10", "XNAS.ITCH").exists()
        SPEND_LOG.write_text("\n".join(x for x in SPEND_LOG.read_text().splitlines() if "2023-07-10" not in x)
                             + "\n")
        # a committed temporary file is recovered instead of bought again
        globals()["manifest"] = man([d1])
        f1 = file_for(d1, "XNAS.ITCH")
        os.replace(f1, f1.with_name(f1.name + ".tmp"))
        log.clear()
        cmd_pull(1)
        assert f1.exists() and log == []
        # an fsync failure on the reservation stops before any paid request
        d6 = "2023-06-26"
        plan.update({f"{d6}N": {"cost": 0.5, "paid": ["ok"]}, f"{d6}Q": {"cost": 0.5, "paid": ["ok"]}})
        globals()["manifest"] = man([d6])
        fsyncs["fail"] = True
        log.clear()
        try:
            cmd_pull(1)
            raise AssertionError("an fsync failure did not stop the pull")
        except OSError:
            pass
        fsyncs["fail"] = False
        assert [x for x in log if x[0] == "paid"] == []
        # a changed quote, a non-finite quote and the cap: nothing reserved, nothing requested
        SPEND_LOG.write_text("\n".join(x for x in SPEND_LOG.read_text().splitlines() if "2023-06-26" not in x)
                             + "\n")
        for d3, cost in (("2023-06-16", 0.7), ("2023-06-20", float("nan"))):
            plan.update({f"{d3}N": {"cost": cost, "paid": ["ok"]}, f"{d3}Q": {"cost": cost, "paid": ["ok"]}})
            globals()["manifest"] = man([d3])
            log.clear()
            before = spent()
            cmd_pull(1)
            assert [x for x in log if x[0] == "paid"] == [] and spent() == before
        real_append(SPEND_LOG, SPEND_COLUMNS, {"utc_time": "x", "schema": "old", "day": "", "n_symbols": 0,
                                               "quoted_cost_usd": "13.8", "rows": "1", "file": ""})
        d4 = "2023-06-21"
        plan.update({f"{d4}N": {"cost": 0.5, "paid": ["ok"]}, f"{d4}Q": {"cost": 0.5, "paid": ["ok"]}})
        globals()["manifest"] = man([d4])
        log.clear()
        cmd_pull(1)                                   # 119.8 logged: the first 0.5 would pass 120
        assert [x for x in log if x[0] == "paid"] == [] and abs(spent() - 119.8) < 1e-9
        # a failed reservation stops before any paid request
        SPEND_LOG.write_text(SPEND_LOG.read_text().replace("13.8", "0.0"))

        def failing_append(path, fields, row):
            if path == SPEND_LOG:
                raise OSError("synthetic disk failure")
            return real_append(path, fields, row)
        globals()["append_row"] = failing_append
        log.clear()
        try:
            cmd_pull(1)
            raise AssertionError("a failed reservation did not stop the pull")
        except OSError:
            pass
        assert [x for x in log if x[0] == "paid"] == []
        globals()["append_row"] = real_append
        # a tampered saved file stops the pull before any request
        globals()["manifest"] = man([d1])
        f = file_for(d1, "XNYS.PILLAR")
        f.write_bytes(gzip.compress(gzip.decompress(f.read_bytes()).replace(b",B,", b",A,")))
        log.clear()
        try:
            cmd_pull(1)
            raise AssertionError("a tampered file did not stop the pull")
        except SystemExit as e:
            assert "SHA-256 differs" in str(e)
        assert log == []
        # a second pull while one holds the lock is refused
        with open(OUT / ".pull.lock", "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                cmd_pull(1)
                raise AssertionError("a concurrent pull was not refused")
            except SystemExit as e:
                assert "another pull" in str(e)
        # a non-finite amount in the log is refused
        real_append(SPEND_LOG, SPEND_COLUMNS, {"utc_time": "x", "schema": "bad", "day": "", "n_symbols": 0,
                                               "quoted_cost_usd": "nan", "rows": "1", "file": ""})
        try:
            spent()
            raise AssertionError("a NaN in the spend log was accepted")
        except SystemExit:
            pass
        # CSV validation
        assert validate_csv(good) == 1 and validate_csv(good, "2023-06-14", ["2023-06-14N"]) == 1
        for bad, kw in ((good[:-1], {}), (good.replace(b"symbol", b"sym"), {}),
                        (good.replace(b",2023-06-14N\n", b"\n"), {}), (good.replace(b"\n1", b"\nx", 1), {}),
                        (b"", {}), ((HEADER + "\n").encode(), {}),
                        (good, {"day": "2023-06-15", "syms": ["2023-06-14N"]}),
                        (good, {"day": "2023-06-14", "syms": ["OTHER"]})):
            try:
                validate_csv(bad, **kw)
                raise AssertionError(f"accepted {bad[-40:]!r} {kw}")
            except ValueError:
                pass
        assert redact("key abc and xyz", "abc", "xyz") == "key [redacted] and [redacted]"
        SPEND_LOG.unlink()
        try:
            spent()
            raise AssertionError("a missing spend log was accepted")
        except SystemExit:
            pass
    finally:
        os.fsync = real_fsync
        for k, v in saved.items():
            globals()[k] = v
        td.cleanup()


def selftest():
    day = "2023-06-14"
    t0 = ns_et(day, "15:50:00")
    assert ns_et(day, "15:51:00") - t0 == 60 * 10 ** 9
    assert datetime.fromtimestamp(t0 / 1e9, tz=ET).strftime("%H:%M:%S") == "15:50:00"

    def rec(sym, t, side="B", q="100", p="10000000000", at="C"):
        return {"symbol": sym, "ts_recv": str(t), "side": side, "total_imbalance_qty": q, "ref_price": p,
                "auction_type": at}
    # usability and sentinels
    assert usable(rec("X", t0))[0] == (1, 100, 10 ** 10)
    assert usable(rec("X", t0, side="A"))[0][0] == -1 and usable(rec("X", t0, side="N"))[0][0] == 0
    assert usable(rec("X", t0, side="Z"))[1] == "bad_side"
    assert usable(rec("X", t0, q=str(UNDEF_ORDER_SIZE)))[1] == "bad_qty"
    assert usable(rec("X", t0, q=""))[1] == "bad_qty"
    assert usable(rec("X", t0, p=str(UNDEF_PRICE)))[1] == "bad_price"
    assert usable(rec("X", t0, p="0"))[1] == "bad_price" and usable(rec("X", t0, p=""))[1] == "bad_price"
    assert usable(rec("X", t0, q="0", side="N"))[0] == (0, 0, 10 ** 10)
    # window edges and ties
    rs = [rec("X", t0 - 1, side="A"), rec("X", t0, side="B", q="1"), rec("X", t0, side="A", q="2"),
          rec("X", t0 + 60 * 10 ** 9 - 1, side="A", q="3"), rec("X", t0 + 60 * 10 ** 9, side="B", q="4")]
    assert pick(rs, "XNAS.ITCH", t0, t0 + 60 * 10 ** 9, "first")["total_imbalance_qty"] == "1"
    assert pick(rs, "XNAS.ITCH", t0, t0 + 60 * 10 ** 9, "last")["total_imbalance_qty"] == "3"
    tie = [rec("X", t0 + 5, q="7"), rec("X", t0 + 5, q="8")]
    assert pick(tie, "XNAS.ITCH", t0, t0 + 60 * 10 ** 9, "first")["total_imbalance_qty"] == "7"
    assert pick(tie, "XNAS.ITCH", t0, t0 + 60 * 10 ** 9, "last")["total_imbalance_qty"] == "8"
    # closing codes by venue
    assert pick([rec("X", t0, at="R")], "XNYS.PILLAR", t0, t0 + 10, "first") is not None
    assert pick([rec("X", t0, at="R")], "XNAS.ITCH", t0, t0 + 10, "first") is None
    assert pick([rec("X", t0, at="O")], "XNYS.PILLAR", t0, t0 + 10, "first") is None
    # first record unusable -> stock unusable (no search)
    rows = {"XNAS.ITCH": [rec("A", t0, q=str(UNDEF_ORDER_SIZE)), rec("A", t0 + 1, q="5")],
            "XNYS.PILLAR": []}
    D, n, why = day_measure(rows, {"XNAS.ITCH": ["A"], "XNYS.PILLAR": []}, day)
    assert (D, n, why["bad_qty"]) == (0, 0, 1)
    # exact integer cancellation and coverage
    syms = {"XNYS.PILLAR": [f"N{i}" for i in range(6)], "XNAS.ITCH": [f"Q{i}" for i in range(6)]}
    rows = {"XNYS.PILLAR": [rec(f"N{i}", t0 + i, side="B", q="3", p="333333333") for i in range(6)],
            "XNAS.ITCH": [rec(f"Q{i}", t0 + i, side="A", q="1", p="999999999") for i in range(6)]}
    D, n, _ = day_measure(rows, syms, day)
    assert D == 0 and n == 12 and classify(D, n) == "zero"
    rows["XNAS.ITCH"][0]["q"] = "x"
    rows["XNAS.ITCH"][0]["total_imbalance_qty"] = "2"
    D, n, _ = day_measure(rows, syms, day)
    assert D == -999999999 and classify(D, n) == "classified"
    assert classify(5, 9) == "uncovered" and classify(5, 10) == "classified"
    # a symbol not in the day's list is ignored; a listed symbol with no record counts as no_record
    rows["XNYS.PILLAR"].append(rec("ZZZ", t0, q="1000000"))
    syms2 = {"XNYS.PILLAR": syms["XNYS.PILLAR"] + ["MISSING"], "XNAS.ITCH": syms["XNAS.ITCH"]}
    D2, n2, why2 = day_measure(rows, syms2, day)
    assert D2 == D and n2 == n and why2["no_record"] == 1
    # venue restriction
    Dn, nn, _ = day_measure(rows, syms, day, venues=("XNYS.PILLAR",))
    assert nn == 6 and Dn == 6 * 3 * 333333333
    # both-venue duplicates: a stock's records in the other venue's file are never used
    syms3 = {"XNYS.PILLAR": ["JPM"], "XNAS.ITCH": ["AAPL"]}
    rows3 = {"XNYS.PILLAR": [rec("JPM", t0 + 5, side="B", q="10", p="2"), rec("AAPL", t0, side="A", q="999", p="9")],
             "XNAS.ITCH": [rec("JPM", t0, side="A", q="999", p="9", at="C"), rec("AAPL", t0 + 5, side="A", q="1",
                                                                              p="3")]}
    D3, n3, _ = day_measure(rows3, syms3, day)
    assert (D3, n3) == (10 * 2 - 3, 2)
    # sums beyond the int64 range stay exact, and sign() handles them
    big = {"XNYS.PILLAR": [rec(f"N{i}", t0, side="B", q="4000000000", p="9000000000000") for i in range(10)],
           "XNAS.ITCH": []}
    Db, nb, _ = day_measure(big, {"XNYS.PILLAR": [f"N{i}" for i in range(10)], "XNAS.ITCH": []}, day)
    assert Db == 10 * 4000000000 * 9000000000000 and Db > 2 ** 63 and sign(Db) == 1 and sign(-Db) == -1
    assert sign(0) == 0 and classify(Db, nb) == "classified"
    # H1 against a direct computation
    a, d = [1] * 40 + [0] * 20, [1] * 15 + [0] * 25
    r = h1(a, d)
    ha, hd = 40 / 60, 15 / 40
    se = math.sqrt(ha * (1 - ha) / 60 + hd * (1 - hd) / 40)
    assert abs(r["d"] - (ha - hd)) < 1e-12 and abs(r["t"] - (ha - hd) / se) < 1e-12 and r["passed"]
    assert not h1([1] * 29, [0] * 40)["evaluable"]
    assert not h1([1] * 40, [1] * 40)["evaluable"]          # se = 0
    assert not h1([0] * 20 + [1] * 20, [1] * 30 + [0] * 10)["passed"]
    # binomial and Holm
    assert binom_upper(0, 10) == 1.0 and abs(binom_upper(10, 10) - 1 / 1024) < 1e-15
    assert abs(binom_upper(6, 10) - 386 / 1024) < 1e-15 and binom_upper(0, 0) == 1.0
    hm = holm2(0.01, 0.04)
    assert hm["H2"] and hm["H3"] and hm["order"] == ["H2", "H3"]
    hm = holm2(0.03, 0.01)
    assert hm["H3"] and hm["H2"] and hm["order"] == ["H3", "H2"]
    hm = holm2(0.03, 0.03)
    assert not hm["H2"] and not hm["H3"] and hm["order"] == ["H2", "H3"]
    hm = holm2(0.02, 0.06)
    assert hm["H2"] and not hm["H3"]
    # Welch
    w = welch([1.0, 2.0, 3.0], [0.0, 0.0, 3.0])
    assert abs(w["t"] - (2 - 1) / math.sqrt(1 / 3 + 3 / 3)) < 1e-12
    assert not welch([1.0], [1.0, 2.0])["evaluable"] and not welch([1.0, 1.0], [2.0, 2.0])["evaluable"]
    assert welch([1.0, 1.0], [2.0, 3.0])["evaluable"]
    w0 = welch([1.0, 1.0], [2.0, 3.0], zero_variance_group_ok=False)
    assert not w0["evaluable"] and w0["diff"] == -1.5 and w0["mean_b"] == 2.5
    w1 = welch([4.0], [1.0, 2.0])
    assert not w1["evaluable"] and w1["diff"] == 2.5 and "t" not in w1
    # Wilson
    lo, hi = wilson(50, 100)
    assert abs(lo - 0.4038) < 1e-3 and abs(hi - 0.5962) < 1e-3
    # bootstrap: multiplicity, drop rule, determinism
    rows_b = {i: (i % 2 == 0, 1 if i % 4 == 0 else 0) for i in range(0, 200)}
    b1 = bootstrap_d(200, rows_b, np.random.default_rng(1), draws=200, block=20)
    b2 = bootstrap_d(200, rows_b, np.random.default_rng(1), draws=200, block=20)
    assert b1 == b2 and b1["kept"] + b1["dropped"] == 200
    # all agree rows hit, all disagree miss -> d == 1 in every kept draw
    rows_c = {i: (i % 2 == 0, 1 if i % 2 == 0 else 0) for i in range(200)}
    bc = bootstrap_d(200, rows_c, np.random.default_rng(2), draws=50, block=20)
    assert bc["kept"] == 50 and bc["p2_5"] == 1.0 and bc["p97_5"] == 1.0
    bd = bootstrap_d(200, {i: (True, 1) for i in range(200)}, np.random.default_rng(3), draws=20, block=20)
    assert bd["kept"] == 0 and bd["dropped"] == 20 and "p2_5" not in bd
    # reservation is written before the request: append_row flushes; order checked by reading the code path
    src = Path(__file__).read_text()
    src = src[:src.index("def selftest")]
    i_res = src.index('"rows": "reserved"')
    i_req = src.index('http_post("timeseries.get_range"')
    assert i_res < i_req and "paid=True" in src[i_req:i_req + 300]
    assert src.count('http_post("timeseries.get_range"') == 1
    # a paid request is attempted exactly once, a free one is retried (urlopen and sleep replaced; no network)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise OSError("synthetic network failure")
    real_open, real_sleep, real_key = urllib.request.urlopen, time.sleep, globals()["api_key"]
    urllib.request.urlopen, time.sleep = fake_urlopen, (lambda x: None)
    globals()["api_key"] = lambda: "selftest-not-a-key"
    try:
        for paid, want in ((True, 1), (False, 6)):
            calls["n"] = 0
            try:
                http_post("timeseries.get_range" if paid else "metadata.get_cost", {"x": 1}, paid=paid)
                raise AssertionError("expected RequestFailed")
            except RequestFailed:
                pass
            assert calls["n"] == want, (paid, calls["n"])
    finally:
        urllib.request.urlopen, time.sleep = real_open, real_sleep
        globals()["api_key"] = real_key
    _selftest_bootstrap()
    _selftest_pull()
    print("selftest passed")


def dryrun(tmp: Path):
    """End-to-end rehearsal on FAKE imbalance files in `tmp` (never the real download folder): random sides, some
    unusable first records, some thin days, one day whose download 'failed' three times. Checks that the run
    completes, refuses a second run, keeps earlier outputs on a defect rerun, and that the counts add up. Also parses
    the two real format-sample days (outside the sample) for usable-stock counts only (no direction is printed)."""
    global OUT, ATTEMPTS, DOWNLOADS, RES_DIR
    import random
    import shutil
    tmp = tmp.resolve()
    assert ROOT / "data" not in tmp.parents and HERE not in tmp.parents and tmp != HERE
    if tmp.exists():
        shutil.rmtree(tmp)
    OUT, RES_DIR = tmp / "data", tmp / "results"
    ATTEMPTS, DOWNLOADS = OUT / "attempts.csv", OUT / "downloads.csv"
    RES_DIR.mkdir(parents=True)
    rnd = random.Random(7)
    m = manifest()
    days = sorted(m["days"])
    failed_day = days[100]
    for i, day in enumerate(days):
        t0 = ns_et(day, "15:50:00")
        for ds in DATASETS:
            if day == failed_day and ds == "XNAS.ITCH":
                for _ in range(MAX_ATTEMPTS):
                    append_row(ATTEMPTS, ATT_FIELDS, {"utc_time": "x", "day": day, "dataset": ds,
                                                      "quoted_cost_usd": "0"})
                continue
            syms = m["days"][day][ds]["symbols"]
            if i % 50 == 7:
                syms = syms[:3]                          # thin day -> fewer than 10 usable stocks
            lines = [HEADER]
            for sym in syms:
                times = ([t0 + rnd.randrange(1, 5_000_000)] + [t0 + k * 10 ** 9 + rnd.randrange(0, 999)
                                                                for k in range(1, 120)]
                         if ds == "XNYS.PILLAR" else [t0 + k * 10 ** 10 for k in range(30)]
                         + [ns_et(day, "15:55:00") + k * 10 ** 9 for k in range(60)])
                for j, t in enumerate(times):
                    side = rnd.choice("BAN")
                    q = str(rnd.randrange(0, 2_000_000))
                    if j == 0 and rnd.random() < 0.03:
                        q = str(UNDEF_ORDER_SIZE)
                    at = ("R" if j == 0 else "C") if ds == "XNYS.PILLAR" else "C"
                    lines.append(f"{t},{t},20,9,1,{rnd.randrange(10, 900) * 10 ** 9},0,0,0,0,0,0,0,1,{q},0,0,"
                                 f"{at},{side},0,0,0,N, ,{sym}")
            body = ("\n".join(lines) + "\n").encode()
            file_for(day, ds).parent.mkdir(parents=True, exist_ok=True)
            save_download(day, ds, body, "0", validate_csv(body, day, m["days"][day][ds]["symbols"]))
    # the run refuses while a pull holds its lock, and writes nothing
    with open(OUT / ".pull.lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            cmd_run(None)
            raise AssertionError("a run during a pull was not refused")
        except SystemExit as e:
            assert "pull is running" in str(e)
    assert not (RES_DIR / "runs_ledger.csv").exists()
    # a committed temporary file is recovered by the run instead of being counted as missing
    f0 = file_for(days[5], "XNAS.ITCH")
    os.replace(f0, f0.with_name(f0.name + ".tmp"))
    cmd_run(None)
    assert f0.exists()
    r = json.loads((RES_DIR / "results.json").read_text())
    st = r["descriptive"]["status_counts"]
    assert st.get("download_failed") == 1 and sum(st.values()) == 644, st
    p1 = r["H1_primary"]
    n_cls_elig = p1["n_agree"] + p1["n_disagree"]
    assert n_cls_elig == r["secondary"]["H3"]["n"] <= r["secondary"]["H2"]["classified"] == st["classified"]
    by = r["descriptive"]["by_year"]
    assert sum(v["agree"]["n"] for v in by.values()) == p1["n_agree"]
    assert sum(v["agree"]["n"] + v["disagree"]["n"] + v["unclassified"]["n"] for v in by.values()) == \
        644 - r["descriptive"]["outcome_excluded_signal_days"]
    hdr = (RES_DIR / "agreement_days.csv").read_text().splitlines()[0]
    assert hdr == "date,s,D_1e-9_usd,usable_stocks,status,agreement", hdr
    try:
        cmd_run(None)
        raise AssertionError("a second run was not refused")
    except SystemExit as e:
        assert "one registered run" in str(e)
    cmd_run("dryrun defect test")
    assert (RES_DIR / "results_run1.json").exists() and (RES_DIR / "RESULTS_run1.md").exists()
    assert (RES_DIR / "run_started_run1.json").exists() and (RES_DIR / "run_started.json").exists()
    ev = [r["event"] for r in csv.DictReader(open(RES_DIR / "runs_ledger.csv"))]
    assert ev == ["start", "finished", "start", "finished"], ev
    assert json.loads((RES_DIR / "results.json").read_text())["defect_rerun_reason"] == "dryrun defect test"
    # a crash after the start record (simulated: start record present, no results) still blocks an undocumented run
    (RES_DIR / "results.json").unlink()
    try:
        cmd_run(None)
        raise AssertionError("a run after a started run was not refused")
    except SystemExit as e:
        assert "already started" in str(e)
    # a tampered download is refused before anything is archived
    f = file_for(days[0], "XNYS.PILLAR")
    good = f.read_bytes()
    f.write_bytes(gzip.compress(gzip.decompress(good).replace(b",B,", b",A,", 1)))
    try:
        cmd_run("tamper test")
        raise AssertionError("a tampered file was not refused")
    except SystemExit as e:
        assert "SHA-256 differs" in str(e)
    assert (RES_DIR / "run_started.json").exists() and not (RES_DIR / "results_run2.json").exists()
    f.write_bytes(good)
    print("dryrun: status", st, "| bootstrap kept", r["robustness"]["bootstrap_d"]["kept"],
          "| option groups", r["robustness"]["option_pnl_usd"].get("n_a"), r["robustness"]["option_pnl_usd"].get("n_b"))
    # real file format: the two format-sample days (15:45-16:00 files; only the 15:50 minute is used)
    fs = ROOT / "data" / "spx_1549" / "databento" / "imbalance_format_sample"
    venues = list(csv.DictReader(open(HERE / "venues.csv")))
    for day, year in (("2020-12-30", "2021"), ("2026-11-06", "2026")):
        rows = {ds: list(csv.DictReader(io.StringIO(gzip.decompress((fs / f"{ds}_{day}.csv.gz").read_bytes())
                                                    .decode()))) for ds in DATASETS}
        segs = [v for v in venues if v["year"] == year]
        chosen = [v for v in segs if (v["from"] == min(x["from"] for x in segs if x["isin"] == v["isin"]))] \
            if day < "2021" else [v for v in segs if v["to"] == max(x["to"] for x in segs if x["isin"] == v["isin"])]
        syms = {ds: [v["raw_symbol"] for v in chosen if v["venue"] == ds] for ds in DATASETS}
        _, n_ok, why = day_measure(rows, syms, day)
        print(f"format sample {day}: {len(chosen)} stocks listed, {n_ok} usable; {dict(why)}")
        assert n_ok >= 45, (day, n_ok, why)
    print("dryrun passed (fake imbalance data; these numbers mean nothing)")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("selftest", "dryrun", "pull", "run"):
        raise SystemExit(__doc__)
    if sys.argv[1] == "selftest":
        selftest()
        return
    selftest()
    if sys.argv[1] == "dryrun":
        dryrun(Path(sys.argv[2]))
        return
    if sys.argv[1] == "pull":
        check_hashes()
        w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        cmd_pull(w, lim)
    else:
        defect = sys.argv[sys.argv.index("--defect") + 1] if "--defect" in sys.argv else None
        cmd_run(defect)


if __name__ == "__main__":
    main()
