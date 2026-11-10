"""Re-tune the 15:50 candle rule on 2021-2023 real SPXW prices, then test the pick once on 2024-2026.

Pre-registration (locked, binding): preregistration/spx_candle_refine.md. `tune` and `test` refuse to run unless that
file exists and its SHA-256 is in preregistration/LEDGER.md. The section names in the comments below are the plan's.

  tune      Part 1 on 2021-01-01 .. 2023-12-31 ONLY (the plan's "Isolation" section): the D1 panel of those dates,
            the official closes filtered record by record to those dates (checked against the Robinhood 2021-2023
            closes before any selection), and quote files of those dates (the quote loader refuses any other date).
            Scores the 2,178-cell grid, applies eligibility, the pick rule, the circular-shift luck diagnostic (only
            if some cell is eligible) and the gates, then writes selection.json + selection.sha256 (both read-only,
            never overwritten), tune_results.json, the tuning rows of data/spx_1549/databento/refine_trades.csv,
            the tuning section of RESULTS.md and, last, tune_complete.json (the SHA-256s of all of them).
  test      Refuses unless the plan's gate passes, selection.sha256 matches selection.json and tune_complete.json
            matches the tuning artifacts (checked before any test-period input is read). Reads the 2024-01-01 ..
            2026-10-20 panel, closes (checked against Robinhood) and quotes; until the Part 2 decision (or the
            "no test" / "already evaluated" decision) is written to results.json it builds only the pick's and the
            current rule's signals and prices only the contracts those rules bought; only then computes the
            descriptive Part 3 test-period items.
  selftest  Synthetic data only; every file it writes goes to a temp folder.

Runs: each of tune and test holds an exclusive lock file (backtests/spx_candle_refine/.refine.lock) and, before it
reads any outcome-bearing input, writes an attempt record runs/<UTC>_<command>_<pid>.json; RESULTS.md reports how
many times each was started. It then loads the panel for its window and writes the content manifest of its
inputs and code (inputs_tune.json / inputs_test.json, read-only; the panel enters as a digest of what the loader
returned, not as the whole D1 file) before computing anything; a later attempt of the same step must reproduce that
manifest exactly or it stops without computing, and after computing, before publishing the outcome, the manifest is
recomputed and must still match ("inputs changed during the run; not publishing"). Every output is written
atomically (temp file, fsync, rename,
directory fsync). A rerun after a crash recomputes everything under the frozen manifest and continues only if what
is already written (the selection and tuning artifacts, or the decision block) is reproduced exactly; it then writes
only the missing outputs, and refuses otherwise. No temporary file is ever used to decide anything.

Usage (from /Users/kv15/trading):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_refine/refine.py selftest
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_refine/refine.py tune
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_refine/refine.py test

Reuse: realprice.py and scan.py are imported read-only, for primitives only (quote parsing, valid quote, implied spot,
ATM, intrinsic, the body signal, nw(), fnum, check_closes, check_gate, load_module and the grid constants;
scan.load_panel, scan.mi and scan.py's F2 signal). Every piece of orchestration is new here. Research only; nothing
here trades and nothing here is a trading recommendation.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
import types
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
REALPRICE_PY = ROOT / "backtests" / "spx_candle_realprice" / "realprice.py"


def _load_module(name: str, path: Path):
    """realprice.py's own importlib pattern (it is used to bootstrap realprice itself); registered in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rp = _load_module("spx_candle_realprice_ro", REALPRICE_PY)            # read-only: primitives and constants only

# ------------------------------------------------------------------------------------------------
# constants (the plan's "Data", "The grid", "Part 1", "Part 2" and "Choices fixed here")
# ------------------------------------------------------------------------------------------------
CANDLES, ENTRIES, THRESHOLDS = rp.CANDLES, rp.ENTRIES, rp.THRESHOLDS     # 15:40..15:50, 15:41..15:51, 0.40..0.90
DIRECTIONS, OFFSETS, CURRENT = rp.DIRECTIONS, rp.OFFSETS, rp.CURRENT     # (with, against), ITM20..OTM20
FEE, FEE_HIGH, MULT = rp.FEE, rp.FEE_HIGH, rp.MULT                       # $0.09 decides; $0.74 descriptive
assert len(CANDLES) == 11 and len(THRESHOLDS) == 11 and DIRECTIONS == (1, -1)
assert OFFSETS == (20, 15, 10, 5, 0, -5, -10, -15, -20) and CURRENT == ("15:50", 0.60, 1, 10)
assert [int(k[3:]) + 1 for k in CANDLES] == [int(e[3:]) for e in ENTRIES]  # entry = the next minute's open
assert rp.NW_LAG == 5 and FEE == 0.09 and FEE_HIGH == 0.74
GRID_SHAPE = (len(CANDLES), len(THRESHOLDS), len(DIRECTIONS), len(OFFSETS))
N_CELLS = int(np.prod(GRID_SHAPE))
assert N_CELLS == 2178

PREREG = ROOT / "preregistration" / "spx_candle_refine.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
SPX_ROOT = ROOT / "data" / "spx_1549"
OUT_TRADES = SPX_ROOT / "databento" / "refine_trades.csv"
FORWARD_DIR = SPX_ROOT / "forward"
RH_TUNE_FILE = SPX_ROOT / "robinhood_spx_daily_2021_2023.json"   # Robinhood SPX closes fetched for 2021-2023
ET = ZoneInfo("America/New_York")

TUNE = ("2021-01-01", "2023-12-31")
HALVES = (("H1", ("2021-01-01", "2022-09-30")), ("H2", ("2022-10-01", "2023-12-31")))
TEST = ("2024-01-01", "2026-10-20")
TEST_YEARS = (("2024", ("2024-01-01", "2024-12-31")), ("2025", ("2025-01-01", "2025-12-31")),
              ("2026", ("2026-01-01", "2026-10-20")))

MIN_TRADES = 100                 # Part 1 "Eligible": at least 100 trades ...
MIN_TRADES_HALF = 40             # ... at least 40 in each half ...
COVERAGE_MIN = (95, 100)         # ... coverage >= 95% overall and in each half (integer test: 100 * priced >= 95 * signal)
NULL_ALPHA = 0.05                # "Goes to the test" condition 2
T_BAR = 2.0                      # Part 2 (a) and (b)
SHIFT_MIN_GAP, SHIFT_STEP = 21, 3   # shifts: range(21, n - 21 + 1, 3)
NULL_CHUNK = 48                  # shifts per batch in the null (memory: 48 x n x 121 floats)
MIN_CLOSE_OVERLAP = 3            # Robinhood close check needs at least 3 overlapping days ...
CLOSE_TOL = 0.01                 # ... and every one within 0.01 of the Cboe close
assert rp.CLOSE_CHECK_TOL == CLOSE_TOL and rp.MIN_CLOSE_OVERLAP == MIN_CLOSE_OVERLAP   # test uses rp.check_closes
F2_ID = "F2_1m_1550_strong_body"
PROFILE_CANDLE, PROFILE_DIRECTION, PROFILE_OFFSETS = "15:50", 1, (10, 0)   # Part 3 threshold profile: ITM10 and ATM
FORWARD_SOURCE = "SPX_robinhood"

NO_ADVANCE = "No candidate advanced under the prespecified rules"
FAMILY_TEXT = "already evaluated on 2024-2026; it can only be confirmed on future days"
NULL_NOT_RUN = "not run (no eligible cell)"
TUNE_MD_MARK = "## Part 1: tuning"
TEST_MD_MARK = "## Part 2: the test"
ATTEMPT_RE = re.compile(r"^\d{8}T\d{6}\.\d{6}Z_(tune|test)_\d+\.json$")   # runs/<UTC>_<command>_<pid>.json
GATE_TEXT = {"not_in_current_family": "the pick is not in the current rule's family (15:50, 0.60, with, any strike)",
             "p_le_alpha": f"luck diagnostic p <= {NULL_ALPHA}",
             "paired_mean_gt_0": "on tuning, the paired per-day difference (pick - current) has a mean above 0"}
TRADE_COLUMNS = ["config", "cell", "date", "period", "signal", "entry_minute", "implied_spot", "kind", "strike", "ask",
                 "mid", "pnl_ask_fee_0.09", "pnl_ask_fee_0.74", "pnl_mid_fee_0.09", "status"]


class IsolationError(RuntimeError):
    """Raised when a step would read an outcome-bearing input outside its window."""


# ------------------------------------------------------------------------------------------------
# cells
# ------------------------------------------------------------------------------------------------
def label(o: int) -> str:
    return "ATM" if o == 0 else (f"ITM{o}" if o > 0 else f"OTM{-o}")


def cell_name(c) -> str:
    k, th, d, o = c
    return f"{k} body>={float(th):.2f} {'with' if d > 0 else 'against'} {label(int(o))}"


def idx_of(c) -> tuple:
    k, th, d, o = c
    return CANDLES.index(k), THRESHOLDS.index(round(float(th), 2)), DIRECTIONS.index(int(d)), OFFSETS.index(int(o))


def cell_of(ix) -> tuple:
    a, b, di, j = (int(x) for x in ix)
    return CANDLES[a], THRESHOLDS[b], DIRECTIONS[di], OFFSETS[j]


def distance_to_current(ix) -> int:
    """Grid-index Manhattan distance: one candle minute, one 0.05 step, a direction flip, one 5-point strike step."""
    a, b, di, j = ix
    ca, cb, cdi, cj = idx_of(CURRENT)
    return abs(a - ca) + abs(b - cb) + int(di != cdi) + abs(j - cj)


def in_current_family(c) -> bool:
    """The current rule's family: 15:50, 0.60, with, any strike."""
    return c[0] == CURRENT[0] and round(float(c[1]), 2) == CURRENT[1] and int(c[2]) == CURRENT[2]


# ------------------------------------------------------------------------------------------------
# Isolation: windows, the guarded quote loader, closes filtered record by record, listings (metadata)
# ------------------------------------------------------------------------------------------------
def in_window(day: str, window) -> bool:
    return window[0] <= day <= window[1]


def assert_window(dates, window, what: str) -> None:
    bad = [str(d) for d in dates if not in_window(str(d), window)]
    if bad:
        raise IsolationError(f"{what}: {len(bad)} date(s) outside {window[0]}..{window[1]}, first {bad[:3]}")


def window_loader(folder: Path, window, calls: list | None = None, cache: dict | None = None):
    """Quote loader that refuses (IsolationError) any date outside `window` before touching the file. `cache` is a
    selftest-only memo (None in tune and test); it is consulted only after the window check."""
    def load(day: str):
        if not in_window(day, window):
            raise IsolationError(f"quote loader for {window[0]}..{window[1]} refused {day}")
        if calls is not None:
            calls.append(day)
        if cache is None:
            return rp.load_day_quotes(day, folder)
        key = (str(folder), day)
        if key not in cache:
            cache[key] = rp.load_day_quotes(day, folder)
        return cache[key]
    return load


def _csv_day(field_: str) -> str | None:
    """MM/DD/YYYY -> YYYY-MM-DD (the Cboe CSV's DATE field), or None."""
    parts = field_.split("/")
    if len(parts) != 3:
        return None
    m, d, y = parts
    return f"{y}-{m.zfill(2)}-{d.zfill(2)}"


def load_closes(path: Path, window) -> dict:
    """Official Cboe closes in `window`. Each CSV record's DATE field is parsed first and a record outside the window
    is skipped before its SPX field is looked at, so no out-of-window close is ever converted or stored. Never
    downloads (realprice.fetch_closes would); a missing file stops the step."""
    if not Path(path).exists():
        raise SystemExit(f"official closes file {path} is missing; this code never downloads it")
    out = {}
    with open(path, newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        i_date, i_spx = header.index("DATE"), header.index("SPX")
        for rec in rd:
            if len(rec) <= max(i_date, i_spx):
                continue
            day = _csv_day(rec[i_date])
            if day is None or not in_window(day, window):
                continue                                                   # the value is never converted
            v = rp.fnum(rec[i_spx])
            if v and v > 0:
                out[day] = v
    return out


def closes_window_sha(closes: dict) -> str:
    text = "\n".join(f"{d} {closes[d]!r}" for d in sorted(closes))
    return hashlib.sha256(text.encode()).hexdigest()


def read_rh_tune_closes(path: Path, window) -> dict:
    """The Robinhood SPX daily closes fetched for 2021-2023: {"source", "fetched_utc", "closes": {date: close}}.
    Numbers are kept as text by the JSON parser; every key must lie in `window` (else the step stops) before any value
    is converted. Returns {date: (close, file name)}."""
    try:
        doc = json.loads(Path(path).read_text(), parse_float=str, parse_int=str)
        raw = doc["closes"]
    except (ValueError, KeyError, TypeError) as e:
        raise SystemExit(f"stopping before any selection: {path} is not in the expected format ({e})")
    if not isinstance(raw, dict) or not raw:
        raise SystemExit(f"stopping before any selection: {path} holds no closes")
    outside = sorted(d for d in raw if not (isinstance(d, str) and len(d) == 10 and in_window(d, window)))
    if outside:
        raise SystemExit(f"stopping before any selection: {path} has {len(outside)} date(s) outside "
                         f"{window[0]}..{window[1]} (first {outside[:3]}); the tuning step reads none")
    out = {}
    for d, v in raw.items():
        x = rp.fnum(v)
        if x is None or x <= 0:
            raise SystemExit(f"stopping before any selection: {path} has an unusable close on {d}")
        out[d] = (x, Path(path).name)
    return out


def _bar_groups(doc):
    if isinstance(doc, dict):
        if isinstance(doc.get("bars"), list):
            yield doc
        for v in doc.values():
            yield from _bar_groups(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from _bar_groups(v)


def rh_closes_window(paths, window, spx_id: str | None) -> dict:
    """Robinhood daily closes from live_*/spx_daily.json files (as candle_1550_options_forward.official_closes: SPX
    instrument, day bars, not interpolated, close > 0, the later file wins), restricted to `window`: numbers are kept
    as text by the JSON parser and a bar's date is checked before its close is converted. Conflicting closes for an
    in-window date (> 0.005 apart) stop the step. Returns {date: (close, file name)}."""
    found: dict = {}
    for p in paths:
        try:
            doc = json.loads(Path(p).read_text(), parse_float=str, parse_int=str)
        except ValueError:
            continue
        for res in _bar_groups(doc):
            if res.get("interval", "day") != "day" or (spx_id and res.get("instrument_id", spx_id) != spx_id):
                continue
            for b in res["bars"]:
                ts = b.get("begins_at") if isinstance(b, dict) else None
                if not isinstance(ts, str) or not in_window(ts[:10], window):
                    continue                                               # the value is never converted
                if b.get("interpolated") is True:
                    continue
                v = rp.fnum(b.get("close_value"))
                if v is not None and v > 0:
                    found.setdefault(ts[:10], []).append((v, Path(p).parent.name))
    bad = [d for d, v in found.items() if max(c for c, _ in v) - min(c for c, _ in v) > 0.005]
    if bad:
        raise SystemExit(f"Robinhood closes conflict on {len(bad)} in-window date(s), first {sorted(bad)[:3]}")
    return {d: v[-1] for d, v in found.items()}


def quote_listing(folder: Path) -> dict:
    """{day: 'file' | 'none'} for every quote file / no-expiry marker: metadata, may cover any date."""
    out = {f.name[:-len(".none")]: "none" for f in Path(folder).glob("*.none")}
    out.update({f.name[:-len(".csv.gz")]: "file" for f in Path(folder).glob("*.csv.gz")})
    return out


def listing_sha(folder: Path, window) -> dict:
    files = sorted(f for f in Path(folder).iterdir()
                   if (f.name.endswith(".csv.gz") or f.name.endswith(".none")) and in_window(f.name[:10], window))
    text = "\n".join(f"{f.name} {f.stat().st_size}" for f in files)
    return {"window": list(window), "files": len(files), "sha256": hashlib.sha256(text.encode()).hexdigest()}


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------
# Data: pricing per day (mirrors realprice.day_cube, restricted to the contracts asked for)
# ------------------------------------------------------------------------------------------------
def _needs_map(needs) -> dict:
    """{entry index: {offset index: sides}} from None (whole grid, both sides), (entry, offset) pairs (both sides) or
    (entry, offset, side) triples (that side only; side 'up' = the call, 'dn' = the put)."""
    if needs is None:
        needs = [(i, j) for i in range(len(ENTRIES)) for j in range(len(OFFSETS))]
    m: dict = {}
    for t in needs:
        m.setdefault(t[0], {}).setdefault(t[1], set()).update((t[2],) if len(t) == 3 else ("up", "dn"))
    return m


def price_day(quotes: dict, close: float, needs=None) -> dict:
    """Per entry minute and offset: P&L of buying the call (up) and/or the put (down) at the ask at the entry minute's
    open, settled at intrinsic on `close`, minus $0.09; plus ask, mid, implied spot and ATM. Only the contracts in
    `needs` are priced (see _needs_map), and the implied spot only at their entry minutes. An entry minute with no
    implied spot leaves spot NaN ("no_spot"); a contract with no valid quote leaves its P&L NaN with a finite spot
    ("no_quote")."""
    E, O = len(ENTRIES), len(OFFSETS)
    out = {k: np.full((E, O), np.nan) for k in ("up", "dn", "ask_up", "ask_dn", "mid_up", "mid_dn")}
    out["spot"], out["atm"] = np.full(E, np.nan), np.full(E, np.nan)
    for i, js in sorted(_needs_map(needs).items()):
        q = quotes.get(ENTRIES[i], {})
        s = rp.implied_spot(q)
        if s is None:
            continue
        atm = rp.atm_of(s)
        out["spot"][i], out["atm"][i] = s, atm
        for j, sides in sorted(js.items()):
            o = OFFSETS[j]
            for kind, K, side in (("call", atm - o, "up"), ("put", atm + o, "dn")):
                if side not in sides:
                    continue
                qa = q.get((kind, K))
                if qa is None or not rp.valid_quote(*qa):
                    continue
                bid, ask = qa
                out["ask_" + side][i, j], out["mid_" + side][i, j] = ask, (bid + ask) / 2
                out[side][i, j] = MULT * (rp.intrinsic(kind, K, close) - ask) - FEE
    return out


def kept_days(days: list, closes: dict, listing: dict) -> tuple:
    """Days with a quote file and an official close, in date order (the plan's "Days"), from the file listing and the
    closes only (no quote is read). A day with neither a file nor a .none marker means the download is incomplete:
    the step stops."""
    keep = []
    drops = {"no_expiry": [], "missing_file": [], "no_close": []}
    for day in days:
        st = listing.get(day)
        if st is None:
            drops["missing_file"].append(day)
        elif st == "none":
            drops["no_expiry"].append(day)
        elif day not in closes:
            drops["no_close"].append(day)
        else:
            keep.append(day)
    if drops["missing_file"]:
        raise SystemExit(f"download incomplete: {len(drops['missing_file'])} D1 day(s) have neither a quote file nor "
                         f"a .none marker, first {drops['missing_file'][:3]}")
    return keep, drops


def price_days(keep: list, closes: dict, loader, needs, env=None, tag: str = "") -> dict:
    """Stack price_day over the kept days. `needs` is None (whole grid), one set for every day, or a list with one
    set per kept day; a day whose set is empty is not loaded at all."""
    if env is not None:
        env.events.append(("price", tag, "grid" if needs is None else
                           ("per_day" if isinstance(needs, list) else frozenset(needs))))
    E, O = len(ENTRIES), len(OFFSETS)
    empty = {k: np.full((E, O), np.nan) for k in ("up", "dn", "ask_up", "ask_dn", "mid_up", "mid_dn")}
    empty.update(spot=np.full(E, np.nan), atm=np.full(E, np.nan))
    cubes = []
    for k, day in enumerate(keep):
        nd = needs[k] if isinstance(needs, list) else needs
        if nd is not None and not nd:
            cubes.append(empty)
            continue
        q, _ = loader(day)
        if not isinstance(q, dict):
            raise SystemExit(f"{day}: listed as a quote file but did not load")
        if env is not None and env.priced is not None:
            env.priced.append((tag, day, "grid" if nd is None else frozenset(nd)))
        cubes.append(price_day(q, closes[day], nd))
    cube = {"dates": np.array(keep, dtype=object)}
    for k in ("up", "dn", "ask_up", "ask_dn", "mid_up", "mid_dn"):
        cube[k] = np.array([c[k] for c in cubes]) if cubes else np.zeros((0, E, O))
    for k in ("spot", "atm"):
        cube[k] = np.array([c[k] for c in cubes]) if cubes else np.zeros((0, E))
    return cube


def bought_contracts(sig, cells) -> list:
    """Per kept day: the set of (entry index, offset index, side) actually bought by the given rules that day (a
    finite, nonzero signal; side 'up' buys the call, 'dn' the put)."""
    out = []
    for i in range(sig.shape[0]):
        s_day = set()
        for c in cells:
            a, b, di, j = idx_of(c)
            s = sig[i, a, b] * DIRECTIONS[di]
            if np.isfinite(s) and s != 0:
                s_day.add((a, j, "up" if s > 0 else "dn"))
        out.append(s_day)
    return out


# ------------------------------------------------------------------------------------------------
# The grid: signals and per-day series
# ------------------------------------------------------------------------------------------------
def signals(P, rows, scan) -> np.ndarray:
    """sig[day, candle, threshold] in {-1, 0, +1, NaN}: range > 0 and |body| >= theta x range, sign(body); NaN when a
    bar is missing (realprice.body_signal). `rows` are panel rows of the kept days."""
    rows = np.asarray(rows, int)
    sig = np.full((len(rows), len(CANDLES), len(THRESHOLDS)), np.nan)
    for a, k in enumerate(CANDLES):
        i = scan.mi(k)
        o, h, l_, c = (X[rows, i] for X in (P.O, P.H, P.L, P.C))
        for b, th in enumerate(THRESHOLDS):
            sig[:, a, b] = rp.body_signal(o, h, l_, c, th)
    return sig


def rule_signals(P, rows, scan, cells) -> np.ndarray:
    """The same tensor as signals(), but with only the columns (candle, threshold) of the given rules filled (NaN
    elsewhere): what `test` builds before its decision."""
    rows = np.asarray(rows, int)
    sig = np.full((len(rows), len(CANDLES), len(THRESHOLDS)), np.nan)
    for c in cells:
        a, b, _, _ = idx_of(c)
        i = scan.mi(CANDLES[a])
        o, h, l_, cl = (X[rows, i] for X in (P.O, P.H, P.L, P.C))
        sig[:, a, b] = rp.body_signal(o, h, l_, cl, THRESHOLDS[b])
    return sig


def f2_check(P, rows, sig, scan) -> dict:
    """The grid's 15:50 / 0.60 / with column must equal scan.py's F2 on every kept day of the step, or it stops."""
    f2 = np.asarray(scan.spec_by_id(F2_ID).signal(P), float)[np.asarray(rows, int)]
    a, b, _, _ = idx_of(CURRENT)
    mine = sig[:, a, b] * CURRENT[2]
    bad = int(np.sum(np.nan_to_num(mine, nan=9) != np.nan_to_num(f2, nan=9)))
    if bad:
        raise SystemExit(f"check failed: 15:50/0.60/with differs from scan.py's F2 on {bad} kept day(s)")
    return {"kept_days": int(len(rows)), "equal_on_every_day": True,
            "signal_days": int(np.sum(np.isfinite(f2) & (f2 != 0)))}


def day_series(s, up_k, dn_k):
    """Per-day P&L: the call's on +1, the put's on -1, 0 on 0 (no trade), NaN if the signal is missing or the trade
    could not be priced."""
    s = np.asarray(s, float)
    with np.errstate(invalid="ignore"):
        return np.where(s > 0, up_k, np.where(s < 0, dn_k, np.where(s == 0, 0.0, np.nan)))


def cell_series(c, sig, cube) -> tuple:
    a, b, di, j = idx_of(c)
    s = sig[:, a, b] * DIRECTIONS[di]
    return day_series(s, cube["up"][:, a, j], cube["dn"][:, a, j]), s


def grid_stats(sig, up, dn, masks: list) -> list:
    """For each day mask: per cell [candle, threshold, direction, offset] the mean per day (over non-missing days),
    the priced trades, the signal days and the coverage (priced / signal days). sig is (n, C, T), or (S, n, C, T) for
    S shifted copies; up/dn are (n, E, O) and stay fixed."""
    lead = sig.shape[:-3]
    shp = lead + GRID_SHAPE
    out = [{"sum": np.zeros(shp), "n_days": np.zeros(shp, int), "n_trades": np.zeros(shp, int),
            "n_signal": np.zeros(shp, int)} for _ in masks]
    for a in range(len(CANDLES)):
        U, D = up[:, a, :], dn[:, a, :]                                       # (n, O)
        for b in range(len(THRESHOLDS)):
            s0 = sig[..., a, b]                                               # (n,) or (S, n)
            with np.errstate(invalid="ignore"):
                sigday = np.isfinite(s0) & (s0 != 0)
            for di, d in enumerate(DIRECTIONS):
                X = day_series((s0 * d)[..., None], U, D)                     # (n, O) or (S, n, O)
                fin = np.isfinite(X)
                Xz = np.where(fin, X, 0.0)
                tr = fin & sigday[..., None]
                for r, m in zip(out, masks):
                    r["sum"][..., a, b, di, :] = Xz[..., m, :].sum(axis=-2)
                    r["n_days"][..., a, b, di, :] = fin[..., m, :].sum(axis=-2)
                    r["n_trades"][..., a, b, di, :] = tr[..., m, :].sum(axis=-2)
                    r["n_signal"][..., a, b, di, :] = sigday[..., m].sum(axis=-1)[..., None]
    for r in out:
        with np.errstate(invalid="ignore", divide="ignore"):
            r["mean"] = np.where(r["n_days"] > 0, r["sum"] / np.maximum(r["n_days"], 1), np.nan)
            r["coverage"] = np.where(r["n_signal"] > 0, r["n_trades"] / np.maximum(r["n_signal"], 1), np.nan)
    return out


# ------------------------------------------------------------------------------------------------
# Part 1: score, eligibility, pick
# ------------------------------------------------------------------------------------------------
def plateau_score(mean) -> np.ndarray:
    """Score = average of the cell's mean per day and its neighbours at theta +- 0.05 that exist on the grid.
    Neighbours count whether eligible or not; a non-finite neighbour is ignored; the cell's own mean must be finite."""
    m = np.asarray(mean, float)
    ax = m.ndim - 3                                                            # threshold axis
    T = m.shape[ax]
    fin = np.isfinite(m)
    tot, cnt = np.where(fin, m, 0.0), fin.astype(int)
    for lo_dst, lo_src in ((slice(1, T), slice(0, T - 1)), (slice(0, T - 1), slice(1, T))):
        nb = np.full_like(m, np.nan)
        dst, src = [slice(None)] * m.ndim, [slice(None)] * m.ndim
        dst[ax], src[ax] = lo_dst, lo_src
        nb[tuple(dst)] = m[tuple(src)]
        f = np.isfinite(nb)
        tot = tot + np.where(f, nb, 0.0)
        cnt = cnt + f
    return np.where(fin, tot / np.maximum(cnt, 1), np.nan)


def coverage_ok(r) -> np.ndarray:
    return (r["n_signal"] > 0) & (r["n_trades"] * COVERAGE_MIN[1] >= COVERAGE_MIN[0] * r["n_signal"])


def eligible(full, h1, h2) -> np.ndarray:
    """At least 100 trades, at least 40 in each half, a mean per day above 0 in each half, coverage >= 95% overall and
    in each half."""
    with np.errstate(invalid="ignore"):
        return ((full["n_trades"] >= MIN_TRADES) & (h1["n_trades"] >= MIN_TRADES_HALF) &
                (h2["n_trades"] >= MIN_TRADES_HALF) & (h1["mean"] > 0) & (h2["mean"] > 0) &
                coverage_ok(full) & coverage_ok(h1) & coverage_ok(h2) & np.isfinite(full["mean"]))


def pick_cell(score, elig):
    """The eligible cell with the highest score; exact ties go to the nearest cell to the current rule; remaining ties
    to the first in enumeration order (candle, threshold, direction with first, strike ITM20 first), which is
    np.argwhere's C order on [candle, threshold, direction, offset]. None if nothing is eligible."""
    s = np.where(elig & np.isfinite(score), score, -np.inf)
    if not np.isfinite(s).any():
        return None
    ties = [tuple(int(v) for v in ix) for ix in np.argwhere(s == s.max())]
    return min(ties, key=distance_to_current)                                  # min keeps the first of equal distances


def ranked_eligible(score, elig, candle: int | None = None) -> list:
    """Eligible cells in pick order (score, then distance, then enumeration); optionally one candle minute."""
    s = np.where(elig & np.isfinite(score), score, -np.inf)
    ix = [tuple(int(v) for v in x) for x in np.argwhere(np.isfinite(s))]
    if candle is not None:
        ix = [x for x in ix if x[0] == candle]
    return sorted(ix, key=lambda x: (-s[x], distance_to_current(x), np.ravel_multi_index(x, s.shape)))


# ------------------------------------------------------------------------------------------------
# Part 1: luck diagnostic (prespecified, circular shift)
# ------------------------------------------------------------------------------------------------
def shifts_for(n: int) -> list:
    return list(range(SHIFT_MIN_GAP, n - SHIFT_MIN_GAP + 1, SHIFT_STEP))


def shifted(sig, shifts) -> np.ndarray:
    """(len(shifts), n, C, T): the whole signal tensor rolled along the day axis, = np.roll(sig, s, axis=0) for each s."""
    n = sig.shape[0]
    idx = (np.arange(n)[None, :] - np.asarray(shifts)[:, None]) % n
    return sig[idx]


def null_best(sig, up, dn, masks, shifts, chunk: int = NULL_CHUNK) -> np.ndarray:
    """For each shift: the best eligible score over the whole grid with the signal rolled against the fixed outcomes
    and the fixed half masks of the destination days; -inf when nothing is eligible under that shift."""
    out = []
    for i in range(0, len(shifts), chunk):
        sh = shifts[i:i + chunk]
        st = grid_stats(shifted(sig, sh), up, dn, masks)
        sc = plateau_score(st[0]["mean"])
        el = eligible(*st)
        out.extend(np.where(el, sc, -np.inf).reshape(len(sh), -1).max(axis=1).tolist())
    return np.array(out, float)


def p_value(nulls, observed: float) -> float:
    nulls = np.asarray(nulls, float)
    return (1 + int(np.sum(nulls >= observed))) / (1 + len(nulls))


def null_quantile(nulls, q: float):
    """Quantile of the whole null, a shift with nothing eligible counting as -inf; None when the quantile falls on or
    next to such a shift (as realprice.null_quantile)."""
    if len(nulls) == 0:
        return None
    v = np.sort(np.asarray(nulls, float))
    pos = q / 100 * (len(v) - 1)
    lo, hi = v[int(np.floor(pos))], v[int(np.ceil(pos))]
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return None
    return float(np.percentile(v, q))


# ------------------------------------------------------------------------------------------------
# Paired difference, statistics, gates, outcomes
# ------------------------------------------------------------------------------------------------
def paired(x, y, dates) -> dict:
    """pick series - current series on the same days; a day is dropped if either is missing; 0 on no-signal days is
    kept. Newey-West (lag 5) on the retained days in date order."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    keep = np.isfinite(x) & np.isfinite(y)
    r = rp.nw(x[keep] - y[keep])
    return {"paired_n": int(keep.sum()), "dropped_days": int((~keep).sum()),
            "dropped_dates": [str(d) for d in np.asarray(dates)[~keep]], "mean": r["mean"], "nw_t": r["t"]}


def passes(mean, t) -> bool:
    """A criterion of the form 'mean > 0 with t >= 2.0'; a mean or t that could not be computed fails."""
    return mean is not None and t is not None and math.isfinite(mean) and math.isfinite(t) and mean > 0 and t >= T_BAR


def decide(pick, p, paired_mean) -> dict:
    """Part 1 "Goes to the test" and "Outcomes"."""
    if pick is None:
        return {"decision": "no_pick", "goes_to_test": False, "gates": None, "failed_gates": ["no eligible cell"],
                "text": f"{NO_ADVANCE}: no cell was eligible, so there is no pick and no test. The current rule stays."}
    gates = {"not_in_current_family": not in_current_family(pick),
             "p_le_alpha": p is not None and p <= NULL_ALPHA,
             "paired_mean_gt_0": paired_mean is not None and math.isfinite(paired_mean) and paired_mean > 0}
    failed = [k for k, ok in gates.items() if not ok]
    if in_current_family(pick):
        return {"decision": "already_evaluated", "goes_to_test": False, "gates": gates, "failed_gates": failed,
                "text": (f"{NO_ADVANCE}: the pick ({cell_name(pick)}) is in the current rule's family (15:50, "
                         f"0.60, with), so it is {FAMILY_TEXT}. Part 2 is not run for it, and no runner-up is "
                         "substituted. The current rule stays.")}
    if failed:
        return {"decision": "no_test", "goes_to_test": False, "gates": gates, "failed_gates": failed,
                "text": (f"{NO_ADVANCE}. Failed gate(s): " + "; ".join(GATE_TEXT[k] for k in failed)
                         + ". The current rule stays.")}
    return {"decision": "test", "goes_to_test": True, "gates": gates, "failed_gates": [],
            "text": f"The pick ({cell_name(pick)}) passed all three gates and goes to the test."}


def part2_outcome(works: bool, better: bool) -> dict:
    if works and better:
        return {"outcome": "adopt", "text": "Adopt the pick: (a) and (b) both hold."}
    if works:
        return {"outcome": "works_not_better",
                "text": "The pick also works but is not shown to be better; the current rule stays."}
    return {"outcome": "not_confirmed", "text": "Not confirmed; the current rule stays."}


def part2(pick, sig, cube) -> dict:
    """Part 2: (a) the pick's mean per day > 0 with t >= 2.0; (b) the paired difference (pick - current) > 0 with
    t >= 2.0. Newey-West lag 5 on the retained days in date order; adopt only if both hold."""
    xp, sp = cell_series(pick, sig, cube)
    xc, sc = cell_series(CURRENT, sig, cube)
    a = rp.nw(xp)
    b = paired(xp, xc, cube["dates"])
    works, better = passes(a["mean"], a["t"]), passes(b["mean"], b["nw_t"])
    return {"run": True, "pick": list(pick), "pick_name": cell_name(pick),
            "a_works": {"days": a["n"], "mean_per_day": a["mean"], "nw_t": a["t"], "passes": works},
            "b_better": dict(b, passes=better), **part2_outcome(works, better),
            "pick_stats": describe(xp, sp), "current_stats": describe(xc, sc),
            "power_note": ("(b) is a hard bar: the pick may trade on far fewer days than the current rule, and a pick "
                           "that is truly somewhat better can easily fail it. 'Not better' does not show that it is "
                           "worse.")}


def describe(x, s) -> dict:
    """Per-day statistics (Newey-West lag 5) plus per-trade statistics (trades = priced signal days)."""
    x, s = np.asarray(x, float), np.asarray(s, float)
    with np.errstate(invalid="ignore"):
        sigday = np.isfinite(s) & (s != 0)
    traded = sigday & np.isfinite(x)
    t = x[traded]
    d = rp.nw(x)
    return {"days": d["n"], "mean_per_day": d["mean"], "nw_t_per_day": d["t"], "signal_days": int(sigday.sum()),
            "trades": int(traded.sum()), "coverage": float(traded.sum() / sigday.sum()) if sigday.sum() else None,
            "mean_per_trade": float(t.mean()) if t.size else None,
            "share_won": float(np.mean(t > 0)) if t.size else None,
            "median_trade": float(np.median(t)) if t.size else None,
            "worst_trade": float(t.min()) if t.size else None}


def not_priced(s, spot_col, pnl_col) -> dict:
    """Signal days by pricing status: no implied spot at the entry minute, or no valid quote for the contract."""
    s = np.asarray(s, float)
    with np.errstate(invalid="ignore"):
        sigday = np.isfinite(s) & (s != 0)
    priced = sigday & np.isfinite(pnl_col)
    no_spot = sigday & ~np.isfinite(spot_col)
    no_quote = sigday & np.isfinite(spot_col) & ~np.isfinite(pnl_col)
    return {"signal_days": int(sigday.sum()), "priced": int(priced.sum()), "no_spot": int(no_spot.sum()),
            "no_quote": int(no_quote.sum())}


def cell_report(c, sig, cube, masks: dict) -> dict:
    """describe() and not-priced counts by reason for one cell on each named day mask."""
    x, s = cell_series(c, sig, cube)
    a, _, _, j = idx_of(c)
    with np.errstate(invalid="ignore"):
        pnl = np.where(s > 0, cube["up"][:, a, j], cube["dn"][:, a, j])
    out = {"cell": list(c), "name": cell_name(c)}
    for k, m in masks.items():
        out[k] = dict(describe(x[m], s[m]), not_priced=not_priced(s[m], cube["spot"][m, a], pnl[m]))
    return out


def threshold_profile(sig, cube, masks: dict) -> dict:
    """Part 3: 15:50, with, at ITM10 and at ATM, theta 0.40 .. 0.90."""
    return {label(o): [dict(cell_report((PROFILE_CANDLE, th, PROFILE_DIRECTION, o), sig, cube, masks), theta=th)
                       for th in THRESHOLDS] for o in PROFILE_OFFSETS}


def cost_versions(c, sig, cube, periods: dict) -> dict:
    """Part 3 test period: the criterion's prices (ask, $0.09), the $0.74 fee, and the mid ($0.09), per period."""
    x, s = cell_series(c, sig, cube)
    a, _, _, j = idx_of(c)
    with np.errstate(invalid="ignore"):
        traded = np.isfinite(x) & np.isfinite(s) & (s != 0)
    x74 = np.where(traded, x - (FEE_HIGH - FEE), x)
    up_mid = cube["up"][:, a, j] + MULT * (cube["ask_up"][:, a, j] - cube["mid_up"][:, a, j])
    dn_mid = cube["dn"][:, a, j] + MULT * (cube["ask_dn"][:, a, j] - cube["mid_dn"][:, a, j])
    xm = day_series(s, up_mid, dn_mid)
    return {per: {v: describe(y[m], s[m]) for v, y in (("ask_fee_0.09", x), ("ask_fee_0.74", x74),
                                                        ("mid_fee_0.09", xm))} for per, m in periods.items()}


def grid_rows(st: list, score, elig) -> list:
    full, h1, h2 = st
    rows = []
    for ix in np.ndindex(*GRID_SHAPE):
        rows.append({"cell": cell_name(cell_of(ix)), "score": score[ix], "mean_per_day": full["mean"][ix],
                     "trades": full["n_trades"][ix], "signal_days": full["n_signal"][ix],
                     "coverage": full["coverage"][ix], "h1_mean": h1["mean"][ix], "h1_trades": h1["n_trades"][ix],
                     "h1_coverage": h1["coverage"][ix], "h2_mean": h2["mean"][ix], "h2_trades": h2["n_trades"][ix],
                     "h2_coverage": h2["coverage"][ix], "eligible": elig[ix]})
    return rows


def cell_row(ix, st, score) -> dict:
    full, h1, h2 = st
    return {"cell": cell_name(cell_of(ix)), "score": score[ix], "mean_per_day": full["mean"][ix],
            "trades": full["n_trades"][ix], "signal_days": full["n_signal"][ix], "coverage": full["coverage"][ix],
            "halves": {"H1": {"mean_per_day": h1["mean"][ix], "trades": h1["n_trades"][ix],
                              "coverage": h1["coverage"][ix]},
                       "H2": {"mean_per_day": h2["mean"][ix], "trades": h2["n_trades"][ix],
                              "coverage": h2["coverage"][ix]}}}


# ------------------------------------------------------------------------------------------------
# environment (paths and data sources; selftest swaps in temp folders and synthetic data)
# ------------------------------------------------------------------------------------------------
@dataclass
class Env:
    out_dir: Path
    quote_dir: Path
    closes_csv: Path
    trades_csv: Path
    prereg: Path
    ledger: Path
    forward_dir: Path
    code_path: Path
    scan: object
    load_panel: object                  # (start, end) -> scan.Panel of keep days in [start, end]
    rh_tune_file: Path                  # Robinhood SPX daily closes fetched for 2021-2023 (tune's close check)
    rh_test_files: object               # () -> live_*/spx_daily.json paths (test's close check)
    spx_id: str | None = None           # Robinhood SPX instrument id (live files)
    days_file: Path | None = None       # the D1 day listing (dates and data-quality flags; no prices)
    code_files: list = field(default_factory=list)      # executable dependencies besides code_path (hashed too)
    events: list = field(default_factory=list)
    loader_calls: list = field(default_factory=list)
    priced: list | None = None          # selftest only: (tag, day, contracts priced that day)
    quote_cache: dict | None = None     # selftest only: memo of parsed quote files
    probe: object = None                # selftest only: probe(step, stage) at "frozen", "computed", "part3"
    null_chunk: int = NULL_CHUNK

    @property
    def selection_json(self) -> Path:
        return self.out_dir / "selection.json"

    @property
    def selection_sha(self) -> Path:
        return self.out_dir / "selection.sha256"

    @property
    def tune_json(self) -> Path:
        return self.out_dir / "tune_results.json"

    @property
    def results_json(self) -> Path:
        return self.out_dir / "results.json"

    @property
    def results_md(self) -> Path:
        return self.out_dir / "RESULTS.md"

    @property
    def runs_dir(self) -> Path:
        return self.out_dir / "runs"

    @property
    def inputs_tune(self) -> Path:
        return self.out_dir / "inputs_tune.json"

    @property
    def inputs_test(self) -> Path:
        return self.out_dir / "inputs_test.json"

    @property
    def tune_complete(self) -> Path:
        return self.out_dir / "tune_complete.json"

    @property
    def lock_file(self) -> Path:
        return self.out_dir / ".refine.lock"


def repo_modules() -> list:
    """Source files of every module loaded from this repository (outside .venv): the executable dependencies."""
    out = set()
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if f and str(Path(f).resolve()).startswith(str(ROOT) + "/") and "/.venv/" not in str(Path(f).resolve()):
            out.add(Path(f).resolve())
    return sorted(out)


def default_env() -> Env:
    scan = rp.load_module("spx_candle_scan_ro", rp.SCAN_PY)
    cfo = rp.load_module("candle_1550_options_forward_ro", rp.OPTIONS_PY)       # for the SPX instrument id only
    code = sorted({Path(__file__).resolve(), REALPRICE_PY, rp.SCAN_PY, rp.OPTIONS_PY} | set(repo_modules()))
    return Env(out_dir=HERE, quote_dir=rp.DB_DIR, closes_csv=rp.CLOSES_CSV, trades_csv=OUT_TRADES, prereg=PREREG,
               ledger=LEDGER, forward_dir=FORWARD_DIR, code_path=Path(__file__).resolve(), scan=scan,
               load_panel=scan.load_panel, rh_tune_file=RH_TUNE_FILE,
               rh_test_files=lambda: sorted(rp.SPX_ROOT.glob("live_*/spx_daily.json")), spx_id=cfo.SPX_ID,
               days_file=scan.D1_DAYS, code_files=code)


# ------------------------------------------------------------------------------------------------
# output helpers: atomic writes (tmp + fsync + rename + directory fsync), the run lock, the run log
# ------------------------------------------------------------------------------------------------
def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        o = float(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def dumps(obj) -> str:
    return json.dumps(jsonable(obj), indent=1, allow_nan=False) + "\n"


class SimulatedCrash(RuntimeError):
    """Raised only by the selftest's write hook."""


_WRITE_HOOK = None          # selftest only: called as hook(path, phase) at the start of every output write


def _hook(path, phase: str) -> None:
    if _WRITE_HOOK is not None:
        _WRITE_HOOK(Path(path), phase)


def _fsync_dir(d: Path) -> None:
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, text: str, readonly: bool = False, exclusive: bool = False) -> None:
    """Write a temp file, fsync it, rename it into place, fsync the directory. `exclusive`: the target must not exist
    (hard link instead of replace, so an existing file is never overwritten). `readonly`: mode 0444."""
    path = Path(path)
    _hook(path, "start")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    if tmp.exists():
        tmp.unlink()                                                           # left by a crashed run
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    if readonly:
        os.chmod(tmp, 0o444)
    _hook(path, "tmp_written")
    if exclusive:
        os.link(tmp, path)                                                     # FileExistsError if it exists
        os.unlink(tmp)
    else:
        os.replace(tmp, path)
    _fsync_dir(path.parent)


def record_attempt(env: Env, command: str, record: dict) -> Path:
    """One attempt record per run: runs/<UTC timestamp>_<command>_<pid>.json, written atomically (read-only, never
    overwritten) before the run reads any outcome-bearing input. A crash mid-write leaves at most a hidden .tmp file,
    which run_counts ignores."""
    now = datetime.now(timezone.utc)
    path = env.runs_dir / f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}_{command}_{os.getpid()}.json"
    atomic_write(path, dumps(dict(record, command=command, utc=now.isoformat(), pid=os.getpid())), readonly=True,
                 exclusive=True)
    return path


def run_counts(env: Env) -> dict:
    """How many times tune and test were started: the published attempt records (anything else in runs/, such as a
    .tmp left by a crash, is ignored)."""
    out = {"tune": 0, "test": 0}
    if env.runs_dir.is_dir():
        for f in sorted(env.runs_dir.iterdir()):
            m = ATTEMPT_RE.match(f.name)
            if m and f.is_file():
                out[m.group(1)] += 1
    return out


@contextmanager
def run_lock(env: Env, command: str):
    """Exclusive run lock (O_CREAT | O_EXCL) in the output folder, removed on exit."""
    env.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(env.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise SystemExit(f"refusing to run {command}: the lock file {env.lock_file} exists, so another refine.py run "
                         "may be active. If no refine.py process is running (check with `ps aux | grep refine.py`), "
                         f"the lock is stale from a crash: delete it by hand (rm '{env.lock_file}') and run again.")
    try:
        os.write(fd, (json.dumps({"command": command, "pid": os.getpid(),
                                  "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n").encode())
        os.fsync(fd)
        os.close(fd)
        yield
    finally:
        try:
            os.unlink(env.lock_file)
        except FileNotFoundError:
            pass


def _stat(p) -> dict:
    p = Path(p)
    return {"file": str(p), "bytes": p.stat().st_size if p.exists() else None}


def input_fingerprints(env: Env, window, rh_files) -> dict:
    """Metadata only (names and sizes, no content): what the attempt record holds."""
    return {"window": list(window), "quote_listing": listing_sha(env.quote_dir, window),
            "closes_csv": _stat(env.closes_csv), "robinhood": [_stat(f) for f in rh_files],
            "days_listing": _stat(env.days_file) if env.days_file else None}


def _sha_or_none(p) -> str | None:
    return sha256_file(p) if Path(p).is_file() else None


def _rows_digest(path: Path, window, col: str, to_day) -> dict:
    """SHA-256 of a CSV's header and of its raw lines whose date (column `col`, mapped by `to_day`) is in `window`,
    as text: no other field is converted."""
    lines = Path(path).read_bytes().decode().splitlines()
    i_date = next(csv.reader([lines[0]])).index(col)
    h = hashlib.sha256((lines[0] + "\n").encode())
    n = 0
    for ln in lines[1:]:
        rec = next(csv.reader([ln]), None)
        day = to_day(rec[i_date]) if rec and len(rec) > i_date else None
        if day is not None and in_window(day, window):
            h.update((ln + "\n").encode())
            n += 1
    return {"file": str(path), "rows": n, "sha256": h.hexdigest()}


def close_rows_digest(path: Path, window) -> dict:
    """The closes CSV's rows dated in `window`, hashed as text (no close is converted)."""
    if not Path(path).exists():
        raise SystemExit(f"official closes file {path} is missing; this code never downloads it")
    return _rows_digest(path, window, "DATE", _csv_day)


def days_rows_digest(path: Path, window) -> dict:
    """The D1 day listing's rows dated in `window`, hashed as text (later rows may be appended without changing it)."""
    if not Path(path).exists():
        raise SystemExit(f"D1 day listing {path} is missing")
    return _rows_digest(path, window, "date", lambda x: x if len(x) == 10 else None)


def panel_digest(P) -> dict:
    """SHA-256 of exactly what the panel loader returned for the step's window: the dates, the O/H/L/C arrays, the
    prior-session open/close it consumed and the dates of the prior sessions it read (dtype and shape included)."""
    h = hashlib.sha256()
    dates = [str(d) for d in P.dates]
    h.update(("dates\n" + "\n".join(dates) + "\n").encode())
    for name in ("O", "H", "L", "C", "prev_open", "prev_close"):
        a = np.ascontiguousarray(getattr(P, name))
        h.update(f"{name} {a.dtype.str} {a.shape}\n".encode())
        h.update(a.tobytes())
    prior = list((getattr(P, "meta", None) or {}).get("prior_session_rows_loaded_before_window", []))
    h.update(("prior_sessions\n" + "\n".join(map(str, prior)) + "\n").encode())
    return {"days": len(dates), "first": dates[0] if dates else None, "last": dates[-1] if dates else None,
            "prior_sessions": prior, "sha256": h.hexdigest()}


def quote_files_digest(folder: Path, window) -> dict:
    """SHA-256 of every quote file / no-expiry marker dated in `window`."""
    files = sorted(f for f in Path(folder).iterdir()
                   if (f.name.endswith(".csv.gz") or f.name.endswith(".none")) and in_window(f.name[:10], window))
    per = {f.name: sha256_file(f) for f in files}
    agg = hashlib.sha256("\n".join(f"{k} {v}" for k, v in per.items()).encode()).hexdigest()
    return {"folder": str(folder), "files": len(per), "sha256": agg, "per_file": per}


def inputs_manifest(env: Env, step: str, window, rh_files, prereg_sha: str, P, extra: dict | None = None) -> dict:
    """The content manifest of everything the step reads (A): the quote files of the window, the closes CSV's
    windowed rows as text, the Robinhood files, what the panel loader returned for the window (not the whole D1
    file), the D1 day listing's windowed rows, the pre-registration and every executable dependency.
    Deterministic (no time stamp), so a later attempt, and the check after use, can require byte equality."""
    code = sorted({str(Path(env.code_path).resolve())} | {str(Path(f).resolve()) for f in env.code_files})
    m = {"step": step, "window": list(window), "prereg_sha256": prereg_sha,
         "code": {f: _sha_or_none(f) for f in code},
         "panel": panel_digest(P),
         "days_listing": days_rows_digest(env.days_file, window) if env.days_file else None,
         "closes_rows": close_rows_digest(env.closes_csv, window),
         "robinhood": {str(f): _sha_or_none(f) for f in rh_files},
         "quotes": quote_files_digest(env.quote_dir, window)}
    m.update(extra or {})
    return m


def freeze_inputs(env: Env, step: str, path: Path, manifest: dict) -> str:
    """The first attempt writes the manifest (atomic, read-only) before computing anything; every later attempt
    recomputes it and must reproduce it byte for byte, or it stops before computing anything. Returns its SHA-256."""
    text = dumps(manifest)
    if path.exists():
        old = path.read_text()
        if old != text:
            raise SystemExit(f"refusing to continue {step}: inputs or code changed since the first attempt; not "
                             f"recomputing. {path.name}, frozen at the first attempt, differs in: "
                             f"{', '.join(_manifest_diff(old, text))}.")
        env.events.append(("manifest_matched", step))
    else:
        atomic_write(path, text, readonly=True, exclusive=True)
        env.events.append(("manifest_written", step))
    return hashlib.sha256(text.encode()).hexdigest()


def _manifest_diff(old: str, new: str) -> list:
    try:
        prev = json.loads(old)
    except ValueError:
        prev = {}
    cur = json.loads(new)
    return sorted(k for k in set(prev) | set(cur) if prev.get(k) != cur.get(k))


def check_after_use(env: Env, step: str, path: Path, manifest: dict) -> None:
    """(A) After computing and before publishing: the inputs, recomputed now, must still equal the frozen manifest
    (an input that changed between the check before use and the loading is caught here); otherwise nothing is
    published."""
    text = dumps(manifest)
    old = path.read_text()
    if old != text:
        raise SystemExit(f"refusing to publish {step}: inputs changed during the run; not publishing. The inputs now "
                         f"differ from {path.name} in: {', '.join(_manifest_diff(old, text))}.")
    env.events.append(("post_check_ok", step))


def _probe(env: Env, step: str, stage: str) -> None:
    if env.probe is not None:
        env.probe(step, stage)


def md_section(text: str, mark: str) -> str | None:
    """The block of RESULTS.md from the heading line starting with `mark` up to the next '## ' heading."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith(mark)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def tune_artifact_hashes(env: Env) -> dict:
    """SHA-256 of the committed tuning artifacts (B). The trades CSV and RESULTS.md are shared with test, which
    rewrites them; for those two the tuning rows and the tuning section are hashed (test reproduces both unchanged)."""
    rows = read_trade_rows(env.trades_csv, "tuning")
    md = env.results_md.read_text() if env.results_md.exists() else ""
    sec = md_section(md, TUNE_MD_MARK)
    h = lambda t: hashlib.sha256(t.encode()).hexdigest()                     # noqa: E731
    return {"inputs_tune.json": _sha_or_none(env.inputs_tune), "selection.json": _sha_or_none(env.selection_json),
            "selection.sha256": _sha_or_none(env.selection_sha), "tune_results.json": _sha_or_none(env.tune_json),
            "tuning trade rows": h(trades_text(rows)) if rows else None,
            "RESULTS.md tuning section": h(sec) if sec is not None else None}


def tune_complete_mismatch(env: Env) -> list:
    try:
        doc = json.loads(env.tune_complete.read_text())
        want = doc["artifacts"]
    except (ValueError, KeyError, TypeError, OSError):
        return ["tune_complete.json itself (unreadable)"]
    got = tune_artifact_hashes(env)
    return [k for k in sorted(set(want) | set(got)) if want.get(k) != got.get(k) or got.get(k) is None]


def verify_tune_complete(env: Env, command: str) -> str:
    """test's precondition (B), checked before any test-period input is read."""
    if not env.tune_complete.exists():
        raise SystemExit(f"refusing to run {command}: tune_complete.json not found, so tune did not finish (it is "
                         "written last, after every tuning artifact); run tune again to complete it")
    bad = tune_complete_mismatch(env)
    if bad:
        raise SystemExit(f"refusing to run {command}: tune_complete.json does not match the tuning artifacts "
                         f"({', '.join(bad)}); they changed after tune completed")
    return sha256_file(env.tune_complete)


def trade_rows(config: str, c, sig, cube, period: str) -> list:
    """Every signal day of one cell: priced, or not priced with the reason (no_spot / no_quote)."""
    a, b, di, j = idx_of(c)
    s = sig[:, a, b] * DIRECTIONS[di]
    o = OFFSETS[j]
    rows = []
    for i, day in enumerate(cube["dates"]):
        if not np.isfinite(s[i]) or s[i] == 0:
            continue
        up = s[i] > 0
        side = "up" if up else "dn"
        spot, atm = float(cube["spot"][i, a]), float(cube["atm"][i, a])
        pnl, ask, mid = (float(cube[k][i, a, j]) for k in (side, "ask_" + side, "mid_" + side))
        status = "priced" if math.isfinite(pnl) else ("no_spot" if not math.isfinite(spot) else "no_quote")
        rows.append({"config": config, "cell": cell_name(c), "date": str(day), "period": period, "signal": int(s[i]),
                     "entry_minute": ENTRIES[a], "implied_spot": spot, "kind": "call" if up else "put",
                     "strike": (atm - o) if up else (atm + o), "ask": ask, "mid": mid, "pnl_ask_fee_0.09": pnl,
                     "pnl_ask_fee_0.74": pnl - (FEE_HIGH - FEE), "pnl_mid_fee_0.09": pnl + MULT * (ask - mid),
                     "status": status})
    return rows


def _fmt_cell(v):
    if isinstance(v, float):
        return "" if not math.isfinite(v) else f"{v:.6f}".rstrip("0").rstrip(".")
    return v


def trades_text(rows: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TRADE_COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: _fmt_cell(r.get(k, "")) for k in TRADE_COLUMNS})
    return buf.getvalue()


def read_trade_rows(path: Path, period: str) -> list:
    if not Path(path).exists():
        return []
    with open(path, newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("period") == period]


def md_has(path: Path, marker: str) -> bool:
    return Path(path).exists() and marker in Path(path).read_text()


def require_same(path: Path, text: str, what: str) -> bool:
    """An artifact already written by an earlier attempt must equal the recomputed one; returns whether it existed."""
    if not path.exists():
        return False
    if path.read_text() != text:
        raise SystemExit(f"refusing to continue tune: {what} differs; not overwriting. The recomputed {what} does "
                         f"not equal the existing {path} byte for byte, although the inputs manifest matched.")
    return True


# ------------------------------------------------------------------------------------------------
# tune (Part 1 and the tuning half of Part 3)
# ------------------------------------------------------------------------------------------------
def tune_close_check(env: Env, closes_tune: dict) -> dict:
    """The Cboe closes against Robinhood's on the tuning range (never deferred): the Robinhood file must exist, hold
    only tuning dates, overlap the Cboe closes on at least 3 days and agree within 0.01 on every one, or the step stops
    before any selection."""
    f = Path(env.rh_tune_file)
    if not f.exists():
        raise SystemExit(f"stopping before any selection: the Robinhood 2021-2023 closes file {f} does not exist; "
                         "tune's close check is required and is never deferred")
    rh = read_rh_tune_closes(f, TUNE)
    over = sorted(set(rh) & set(closes_tune))
    diffs = [abs(closes_tune[d] - rh[d][0]) for d in over]
    bad = [(d, closes_tune[d], rh[d][0]) for d, x in zip(over, diffs) if x > CLOSE_TOL]
    if len(over) < MIN_CLOSE_OVERLAP or bad:
        raise SystemExit(f"stopping before any selection: official-close check failed on the tuning range: "
                         f"{len(over)} overlapping day(s) (need >= {MIN_CLOSE_OVERLAP}), mismatches over {CLOSE_TOL}: "
                         f"{bad[:5]}")
    mx = max(diffs)
    return {"status": "checked", "file": f.name, "robinhood_days": len(rh), "overlap_days": len(over),
            "max_abs_diff": mx,
            "text": f"checked against Robinhood ({f.name}) on {len(over)} tuning days, largest difference {mx:.4f}"}


def run_tune(env: Env) -> dict:
    with run_lock(env, "tune"):
        return _tune_locked(env)


def _tune_locked(env: Env) -> dict:
    prereg_sha = rp.check_gate(env.prereg, env.ledger)
    code_sha = sha256_file(env.code_path)
    # earlier runs (nothing outcome-bearing is read here)
    if env.results_json.exists():
        raise SystemExit(f"refusing to run tune: {env.results_json} exists, so test has run; the tuning artifacts "
                         "are frozen")
    sel_exists, sha_exists = env.selection_json.exists(), env.selection_sha.exists()
    if sha_exists and not sel_exists:
        raise SystemExit("refusing to run tune: selection.sha256 exists without selection.json; inconsistent state, "
                         "not continuing")
    if sel_exists and sha_exists:
        verify_selection(env, "tune")
    if env.tune_complete.exists():
        bad = tune_complete_mismatch(env)
        if bad:
            raise SystemExit("refusing to run tune: tune_complete.json does not match the tuning artifacts "
                             f"({', '.join(bad)}); they changed after tune completed; not continuing")
        raise SystemExit("refusing to run tune: already done (tune_complete.json exists and matches selection.json, "
                         "selection.sha256, tune_results.json, the tuning trade rows and the tuning section of "
                         "RESULTS.md)")
    # the attempt record (C), before any outcome-bearing input is read
    record_attempt(env, "tune", {"code_sha256": code_sha, "prereg_sha256": prereg_sha,
                                 "inputs": input_fingerprints(env, TUNE, [env.rh_tune_file])})
    scan = env.scan
    # Isolation: the only outcome-bearing inputs are the panel, the closes and the quotes of 2021-01-01 .. 2023-12-31
    P = env.load_panel(*TUNE)    # the plan's permitted call; its 2020-12-31 prior-session row is not test-period data
    assert_window(P.dates, TUNE, "tuning panel")
    # frozen inputs (A): the content manifest (with the digest of the panel just loaded) is written before anything
    # is computed; a later attempt must reproduce it first, and it is checked again after use, before publishing
    manifest_now = lambda: inputs_manifest(env, "tune", TUNE, [env.rh_tune_file], prereg_sha, P)   # noqa: E731
    manifest_sha = freeze_inputs(env, "tune", env.inputs_tune, manifest_now())
    _probe(env, "tune", "frozen")
    closes = load_closes(env.closes_csv, TUNE)                                 # filtered record by record
    assert_window(closes, TUNE, "tuning closes")
    close_check = tune_close_check(env, closes)                                # stops before any selection
    listing = quote_listing(env.quote_dir)                                     # metadata, any date
    lhash = listing_sha(env.quote_dir, TUNE)
    loader = window_loader(env.quote_dir, TUNE, env.loader_calls, env.quote_cache)   # refuses any later date
    days = [str(d) for d in P.dates]
    keep, drops = kept_days(days, closes, listing)
    assert_window(keep, TUNE, "tuning days")
    cube = price_days(keep, closes, loader, None, env, "tune")
    dates = cube["dates"]
    assert_window(dates, TUNE, "tuning arrays")
    row = {d: i for i, d in enumerate(days)}
    rows = [row[d] for d in dates]
    sig = signals(P, rows, scan)
    f2 = f2_check(P, rows, sig, scan)
    n = len(dates)
    # Part 1 definitions: kept tuning days in date order, halves H1 and H2
    hm = {name: np.array([in_window(d, w) for d in dates], bool) for name, w in HALVES}
    masks = [np.ones(n, bool), hm["H1"], hm["H2"]]
    st = grid_stats(sig, cube["up"], cube["dn"], masks)
    score = plateau_score(st[0]["mean"])
    elig = eligible(*st)
    best = pick_cell(score, elig)
    pick = cell_of(best) if best is not None else None
    # luck diagnostic: only if some observed cell is eligible
    if best is None:
        observed, p = None, None
        null_summary = {"status": NULL_NOT_RUN}
    else:
        shifts = shifts_for(n)
        nulls = null_best(sig, cube["up"], cube["dn"], masks, shifts, env.null_chunk)
        observed = float(score[best])
        p = p_value(nulls, observed)
        null_summary = {"status": "run", "n_shifts": len(shifts),
                        "shift_range": [SHIFT_MIN_GAP, n - SHIFT_MIN_GAP, SHIFT_STEP],
                        "n_shifts_nothing_eligible": int(np.sum(~np.isfinite(nulls))),
                        "median": null_quantile(nulls, 50), "p95": null_quantile(nulls, 95)}
    pair = None
    if pick is not None:
        pair = paired(cell_series(pick, sig, cube)[0], cell_series(CURRENT, sig, cube)[0], dates)
    dec = decide(pick, p, pair["mean"] if pair else None)
    named = {"tuning": masks[0], "H1": masks[1], "H2": masks[2]}

    def stats_of(c):
        ix = idx_of(c)
        return dict(cell_report(c, sig, cube, named), score=score[ix], eligible=bool(elig[ix]))

    selection = {
        "what": "Selection from the tuning step of preregistration/spx_candle_refine.md (Part 1)",
        "prereg_sha256": prereg_sha, "code_sha256": code_sha, "inputs_manifest_sha256": manifest_sha,
        "tuning_quote_listing": lhash,
        "tuning_closes_window_sha256": closes_window_sha(closes),
        "tuning_window": list(TUNE), "halves": {k: list(w) for k, w in HALVES},
        "kept_days": n, "kept_days_by_half": {k: int(m.sum()) for k, m in hm.items()},
        "decision": dec["decision"], "decision_text": dec["text"], "goes_to_test": dec["goes_to_test"],
        "gates": dec["gates"], "failed_gates": dec["failed_gates"],
        "pick": {"cell": list(pick), "name": cell_name(pick)} if pick else None,
        "p": p, "observed_best_score": observed, "null": null_summary,
        "tuning_stats": {"pick": stats_of(pick) if pick else None, "current": stats_of(CURRENT)},
        "paired_tuning_difference": pair, "close_check": close_check}
    # Part 3 (tuning, descriptive)
    left_out = st[0]["n_signal"] - st[0]["n_trades"]
    top = [cell_row(ix, st, score) for ix in ranked_eligible(score, elig)[:15]]
    by_candle = {}
    for a, k in enumerate(CANDLES):
        r = ranked_eligible(score, elig, a)
        by_candle[k] = cell_row(r[0], st, score) if r else None
    part3 = {"n_eligible": int(elig.sum()), "top15": top, "best_by_candle": by_candle,
             "null": dict(null_summary, p=p, observed_best_score=observed),
             "not_priced_per_cell": {"median": float(np.median(left_out)), "max": int(left_out.max()),
                                     "cell_with_max": cell_name(cell_of(np.unravel_index(left_out.argmax(),
                                                                                         left_out.shape)))},
             "threshold_profile": threshold_profile(sig, cube, named)}
    data = {"d1_days": len(days), "kept_days": n, "first": str(dates[0]) if n else None,
            "last": str(dates[-1]) if n else None,
            "no_expiry_days": len(drops["no_expiry"]), "no_close_days": drops["no_close"],
            "day_minutes_no_spot": int(np.sum(~np.isfinite(cube["spot"]))),
            "contract_slots_no_quote": int(sum(np.sum(np.isfinite(cube["spot"])[:, :, None] & ~np.isfinite(cube[k]))
                                               for k in ("up", "dn"))),
            "close_check": close_check, "f2_check": f2, "quote_listing": lhash}
    tune_res = {"what": "Tuning step of preregistration/spx_candle_refine.md", "selection": selection,
                "data": data, "part3_tuning": part3, "grid": grid_rows(st, score, elig)}
    trades = trade_rows("current", CURRENT, sig, cube, "tuning")
    if pick:
        trades = trade_rows("pick", pick, sig, cube, "tuning") + trades
    # check after use (A): everything is computed; the inputs must still be the frozen ones, or nothing is published
    _probe(env, "tune", "computed")
    check_after_use(env, "tune", env.inputs_tune, manifest_now())
    # outputs, in this order: selection.json, selection.sha256, tune_results.json, the tuning trade rows, RESULTS.md,
    # and LAST tune_complete.json (B). Anything an earlier attempt already wrote must equal the recomputed version
    # byte for byte (else stop, overwriting nothing); only missing artifacts are written; RESULTS.md (derived, with
    # the run counts) is always rewritten.
    sel_text = dumps(selection)
    if require_same(env.selection_json, sel_text, "selection"):
        env.events.append(("selection_matched",))
    else:
        atomic_write(env.selection_json, sel_text, readonly=True, exclusive=True)
    sha_text = f"{hashlib.sha256(sel_text.encode()).hexdigest()}  selection.json\n"
    if not require_same(env.selection_sha, sha_text, "selection.sha256"):
        atomic_write(env.selection_sha, sha_text, readonly=True, exclusive=True)
    tr_text = dumps(tune_res)
    if not require_same(env.tune_json, tr_text, "tune_results.json"):
        atomic_write(env.tune_json, tr_text)
    rows_text = trades_text(trades)
    old_rows = read_trade_rows(env.trades_csv, "tuning")
    if old_rows:
        if trades_text(old_rows) != rows_text:
            raise SystemExit(f"refusing to continue tune: the tuning trade rows differ; not overwriting {env.trades_csv}")
    else:
        atomic_write(env.trades_csv, rows_text)
    atomic_write(env.results_md, render_md(jsonable(tune_res), None, run_counts(env)))
    atomic_write(env.tune_complete, dumps({"what": "tune finished; every tuning artifact below was committed first",
                                           "inputs_manifest_sha256": manifest_sha,
                                           "artifacts": tune_artifact_hashes(env)}), readonly=True, exclusive=True)
    return tune_res


# ------------------------------------------------------------------------------------------------
# test (Part 2 and the test half of Part 3)
# ------------------------------------------------------------------------------------------------
def verify_selection(env: Env, command: str) -> tuple:
    if not env.selection_json.exists() or not env.selection_sha.exists():
        raise SystemExit(f"refusing to run {command}: selection.json / selection.sha256 not found (run tune first)")
    want = env.selection_sha.read_text().split()
    got = sha256_file(env.selection_json)
    if not want or want[0] != got:
        raise SystemExit(f"refusing to run {command}: selection.json (SHA-256 {got}) does not match selection.sha256")
    return json.loads(env.selection_json.read_text()), got


def forward_rows(rows: list, fresh_after: str) -> dict:
    out = []
    for r in rows:
        out.append({"date": r["date"], "status": r.get("status", ""), "kind": r.get("kind", ""),
                    "strike": rp.fnum(r.get("strike")), "paid_incl_0.10": rp.fnum(r.get("cost_incl_half_spread")),
                    "exit_a_value": rp.fnum(r.get("exit_a_value")), "pnl_fee_0.09": rp.fnum(r.get("pnl_a_fee_0.09")),
                    "provisional": r.get("provisional", ""),
                    "label": "fresh" if r["date"] > fresh_after else "previously available"})
    traded = [x["pnl_fee_0.09"] for x in out if x["status"] == "traded" and x["pnl_fee_0.09"] is not None]
    return {"available": True, "days": len(out), "traded": len(traded),
            "fresh_days": sum(x["label"] == "fresh" for x in out),
            "mean_pnl_traded": float(np.mean(traded)) if traded else None, "rows": out}


def forward_days(fdir: Path, fresh_after: str, pick) -> dict:
    """Part 3 "Days after 2026-10-20", descriptive. The current rule from the forward strike-ladder log; the pick only
    if that data has its candle and its entry-minute price (15:50 candle, with, entry 15:51), else 'not available'."""
    basis = ("Robinhood one-minute option bars: the 15:51 bar open + $0.10, held to the official close (the forward "
             "log's Exit A), $0.09 fee. Not the Databento ask, so not the same price basis as Parts 1-2.")
    out = {"price_basis": basis, "fresh_after_et_date": fresh_after, "current": None, "pick": None}
    log = Path(fdir) / "strikes_forward_log.csv"
    if not log.exists():
        out["current"] = {"available": False, "reason": f"no forward strike log at {log}"}
        if pick is not None:
            out["pick"] = {"available": False, "reason": f"no forward strike log at {log}"}
        return out
    with open(log, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("date", "") > TEST[1]]
    out["current"] = forward_rows(sorted((r for r in rows if r["signal_name"] == F2_ID
                                          and r["offset"] == label(CURRENT[3])), key=lambda r: r["date"]), fresh_after)
    if pick is None:
        return out
    if pick[0] != "15:50" or int(pick[2]) != 1:
        out["pick"] = {"available": False, "reason": ("the forward data has only the 15:50 candle's with-direction "
                                                      "contracts priced at the 15:51 bar; the pick needs "
                                                      f"{pick[0]} {'with' if int(pick[2]) > 0 else 'against'}")}
        return out
    clog = Path(fdir) / "candle_1550_log.csv"
    if not clog.exists():
        out["pick"] = {"available": False, "reason": f"no forward candle log at {clog}"}
        return out
    th = float(pick[1])
    on = {}
    with open(clog, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("source") != FORWARD_SOURCE or r.get("status") != "ok" or r.get("date", "") <= TEST[1]:
                continue
            body, rng = rp.fnum(r.get("body_1550")), rp.fnum(r.get("range_1550"))
            if body is not None and rng is not None and rng > 0 and abs(body) >= th * rng:
                on[r["date"]] = 1 if body > 0 else -1
    f1 = {r["date"]: r for r in rows if r["signal_name"] == "F1_1m_15:50" and r["offset"] == label(int(pick[3]))}
    sel = []
    for d, sgn in sorted(on.items()):
        r = f1.get(d)
        if r is None:
            sel.append({"date": d, "status": "not_logged"})
        elif int(float(r.get("signal") or 0)) != sgn:
            sel.append({"date": d, "status": "direction_mismatch"})
        else:
            sel.append(r)
    out["pick"] = dict(forward_rows(sel, fresh_after),
                       note="the 15:50 candle direction log's contract at the pick's strike, on days the forward "
                            "candle's body is at least the pick's threshold")
    return out


def commit_decision(env: Env, head: dict, block: dict, existing: dict | None) -> None:
    """Write the decision to results.json (atomic, fsync'd) before any Part 3 test-period item is computed. If
    results.json already holds a decision (an earlier run crashed later), the recomputed block must be identical:
    outcome, means, t's, n's and input fingerprints; otherwise the step stops without overwriting anything."""
    if existing is not None:
        if dumps(existing["part2"]) != dumps(block):
            raise SystemExit("refusing to continue test: decision differs; not overwriting. The recomputed decision "
                             f"block does not equal the one already in {env.results_json}, so an input or the code "
                             "changed since it was written.")
        env.events.append(("decision_matched",))
        return
    atomic_write(env.results_json, dumps(dict(head, stage="decision written; Part 3 not yet computed",
                                              decision_written_utc=datetime.now(timezone.utc).isoformat(
                                                  timespec="seconds"), part2=block)))
    env.events.append(("decision_written",))


def run_test(env: Env) -> dict:
    with run_lock(env, "test"):
        return _test_locked(env)


def _test_locked(env: Env) -> dict:
    prereg_sha = rp.check_gate(env.prereg, env.ledger)
    sel, sel_sha = verify_selection(env, "test")
    if sel.get("prereg_sha256") != prereg_sha:
        raise SystemExit("refusing to run test: the selection was made under a different pre-registration SHA-256")
    tc_sha = verify_tune_complete(env, "test")                                 # (B) before any test-period input
    existing = json.loads(env.results_json.read_text()) if env.results_json.exists() else None
    if existing is not None and not isinstance(existing.get("part2"), dict):
        raise SystemExit(f"refusing to run test: {env.results_json} exists without a decision block; inconsistent "
                         "state, not continuing")
    complete = existing is not None and existing.get("stage") == "complete"
    if complete and read_trade_rows(env.trades_csv, "test") and md_has(env.results_md, TEST_MD_MARK):
        raise SystemExit("refusing to run test: already done (results.json is complete and the test trade rows and "
                         "the test sections of RESULTS.md exist)")
    scan = env.scan
    pick = tuple(sel["pick"]["cell"]) if sel.get("pick") else None
    pick = (pick[0], round(float(pick[1]), 2), int(pick[2]), int(pick[3])) if pick else None
    go = sel["decision"] == "test"
    code_sha = sha256_file(env.code_path)
    # the Robinhood live files: listed at the first attempt; a later attempt reads exactly the files frozen in
    # inputs_test.json (a live_* folder added since is not an input of this step)
    if env.inputs_test.exists():
        rh_files = [Path(f) for f in json.loads(env.inputs_test.read_text())["robinhood"]]
    else:
        rh_files = list(env.rh_test_files())
    # the attempt record (C), before any outcome-bearing input is read
    record_attempt(env, "test", {"code_sha256": code_sha, "prereg_sha256": prereg_sha, "selection_sha256": sel_sha,
                                 "inputs": input_fingerprints(env, TEST, rh_files)})
    P = env.load_panel(*TEST)
    assert_window(P.dates, TEST, "test panel")
    # frozen inputs (A): the content manifest (with the digest of the panel just loaded) is written before anything
    # is computed; a later attempt must reproduce it first, and it is checked again after use, before publishing
    manifest_now = lambda: inputs_manifest(env, "test", TEST, rh_files, prereg_sha, P,   # noqa: E731
                                           {"selection_json_sha256": sel_sha, "tune_complete_sha256": tc_sha})
    manifest_sha = freeze_inputs(env, "test", env.inputs_test, manifest_now())
    _probe(env, "test", "frozen")
    head = {"what": "Test step of preregistration/spx_candle_refine.md", "prereg_sha256": prereg_sha,
            "selection_sha256": sel_sha, "selection_decision": sel["decision"],
            "code_sha256": code_sha, "code_sha256_at_tune": sel.get("code_sha256"),
            "code_changed_since_tune": code_sha != sel.get("code_sha256"), "test_window": list(TEST)}
    inputs = {"inputs_manifest_sha256": manifest_sha, "selection_sha256": sel_sha, "code_sha256": code_sha,
              "test_quote_listing": listing_sha(env.quote_dir, TEST)}
    if not go:                         # "no test" / "already evaluated": the decision is written before anything else
        _probe(env, "test", "computed")
        check_after_use(env, "test", env.inputs_test, manifest_now())
        commit_decision(env, head, {"run": False, "decision": sel["decision"], "text": sel["decision_text"],
                                    "inputs": dict(inputs, closes_window_sha256=None,
                                                   note="follows from selection.json alone; written before any "
                                                        "test-period close or quote was read")}, existing)
    # Isolation: the 2024-01-01 .. 2026-10-20 panel (loaded above), closes and quotes
    closes = load_closes(env.closes_csv, TEST)                                 # filtered record by record
    rh = rh_closes_window(rh_files, TEST, env.spx_id)                          # windowed before any conversion
    close_check = rp.check_closes(closes, rh)                                  # stops on < 3 days or any mismatch
    listing = quote_listing(env.quote_dir)
    loader = window_loader(env.quote_dir, TEST, env.loader_calls, env.quote_cache)
    days = [str(d) for d in P.dates]
    keep, drops = kept_days(days, closes, listing)
    assert_window(keep, TEST, "test days")
    row = {d: i for i, d in enumerate(days)}
    rows = [row[d] for d in keep]
    cells = {"current": CURRENT} if pick is None else {"pick": pick, "current": CURRENT}
    sig = rule_signals(P, rows, scan, cells.values())                          # only the rules' own signals
    f2 = f2_check(P, rows, sig, scan)
    bought = bought_contracts(sig, cells.values())                             # per day: only the contracts bought
    cube = price_days(keep, closes, loader, bought, env, "test")
    dates = cube["dates"]
    assert_window(dates, TEST, "test arrays")
    if go:
        p2 = dict(part2(pick, sig, cube), inputs=dict(inputs, closes_window_sha256=closes_window_sha(closes)))
        # check after use (A): the decision is computed; the inputs must still be the frozen ones, or nothing is
        # published
        _probe(env, "test", "computed")
        check_after_use(env, "test", env.inputs_test, manifest_now())
        commit_decision(env, head, p2, existing)
    else:
        p2 = json.loads(env.results_json.read_text())["part2"]
    # ---- Part 3, test period: only after the decision is in results.json ----
    env.events.append(("part3_start",))
    n = len(dates)
    periods = {"2024-01-01..2026-10-20": np.ones(n, bool)}
    periods.update({y: np.array([in_window(d, w) for d in dates], bool) for y, w in TEST_YEARS})
    part3 = {"label": "descriptive; computed after the decision was written",
             "configs": {name: {"cell": cell_name(c), "versions": cost_versions(c, sig, cube, periods),
                                "report": cell_report(c, sig, cube, periods)} for name, c in cells.items()}}
    sig_all = signals(P, rows, scan)
    prof_needs = {(ENTRIES.index("15:51"), OFFSETS.index(o)) for o in PROFILE_OFFSETS}
    cube2 = price_days(keep, closes, loader, prof_needs, env, "test_profile")
    part3["threshold_profile"] = {"label": "looked at after the decision",
                                  "rows": threshold_profile(sig_all, cube2, {"test": np.ones(n, bool)})}
    written = datetime.fromtimestamp(env.selection_json.stat().st_mtime, timezone.utc)
    fwd = forward_days(env.forward_dir, written.astimezone(ET).date().isoformat(), pick)
    data = {"d1_days": len(days), "kept_days": n, "first": str(dates[0]) if n else None,
            "last": str(dates[-1]) if n else None, "no_expiry_days": len(drops["no_expiry"]),
            "no_close_days": drops["no_close"], "close_check": close_check, "f2_check": f2,
            "quote_listing": inputs["test_quote_listing"]}
    stored = json.loads(env.results_json.read_text())
    res = dict(head, stage="complete", decision_written_utc=stored.get("decision_written_utc"), part2=p2, data=data,
               part3_test=part3, forward=fwd)
    # check after use again, before the Part 3 outputs are published (the decision is already written and stays)
    _probe(env, "test", "part3")
    check_after_use(env, "test", env.inputs_test, manifest_now())
    # outputs: only what is missing; RESULTS.md (derived, with the run counts) is always rewritten
    if not complete:
        atomic_write(env.results_json, dumps(res))
    if not read_trade_rows(env.trades_csv, "test"):
        res_rows = [r for name, c in cells.items() for r in trade_rows(name, c, sig, cube, "test")]
        atomic_write(env.trades_csv, trades_text(read_trade_rows(env.trades_csv, "tuning") + res_rows))
    tune_res = json.loads(env.tune_json.read_text()) if env.tune_json.exists() else None
    atomic_write(env.results_md, render_md(tune_res, jsonable(res), run_counts(env)))
    return res


# ------------------------------------------------------------------------------------------------
# RESULTS.md
# ------------------------------------------------------------------------------------------------
def fm(x, nd=2, sign=True, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if pct:
        return f"{x * 100:.0f}%"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


def _stat_row(name, s) -> str:
    return (f"| {name} | {s['days']} | {fm(s['mean_per_day'])} | {fm(s['nw_t_per_day'])} | {s['signal_days']} | "
            f"{s['trades']} | {fm(s['coverage'], pct=True)} | {fm(s['mean_per_trade'])} | "
            f"{fm(s['share_won'], pct=True)} | {fm(s['median_trade'])} | {fm(s['worst_trade'])} |")


STAT_HEAD = ("| | Days | $/day | t | Signal days | Trades | Coverage | $/trade | Won | Median | Worst |\n"
             "|---|---|---|---|---|---|---|---|---|---|---|")


def _np_row(name, period, v) -> str:
    return (f"| {name} | {period} | {v['signal_days']} | {v['priced']} | {v['no_spot']} | {v['no_quote']} |")


def _profile_table(w, prof: dict) -> None:
    w("| Strike | θ | Signal days | Trades | Coverage | $/day | $/trade | Won | Median | Worst |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for k, lst in prof.items():
        for r in lst:
            per = next(v for kk, v in r.items() if isinstance(v, dict) and "mean_per_day" in v)
            mark = " (current)" if abs(r["theta"] - CURRENT[1]) < 1e-9 else ""
            w(f"| {k} | {r['theta']:.2f}{mark} | {per['signal_days']} | {per['trades']} | "
              f"{fm(per['coverage'], pct=True)} | {fm(per['mean_per_day'])} | {fm(per['mean_per_trade'])} | "
              f"{fm(per['share_won'], pct=True)} | {fm(per['median_trade'])} | {fm(per['worst_trade'])} |")


def render_md(tune_res: dict | None, test_res: dict | None, counts: dict | None = None) -> str:
    L: list = []
    w = L.append
    w("# Re-tuning the 15:50 rule on 2021-2023 real prices, one test on 2024-2026\n")
    sel = tune_res["selection"] if tune_res else None
    sha = (sel or test_res or {}).get("prereg_sha256", "")
    w(f"Pre-registration `preregistration/spx_candle_refine.md` (SHA-256 `{sha[:16]}...`). Real Databento OPRA "
      "quotes: buy at the ask at the entry minute's open, settle at intrinsic on the official SPX close, $0.09 fee; "
      "every decision uses this. Research only; nothing here is a trading recommendation.\n")
    w("**Not fresh.** The 2021-2026 index outcomes were used before: for the scan candidates, the P1/P3 known "
      "effects, the weak-body audit and the intraday-momentum study. 2024-2026 is not fresh for the current rule's "
      "family (15:50, 0.60, with, any strike): its real-price results there were already computed and seen.\n")
    if counts is not None:
        w(f"Runs started (attempt records in runs/): tune {counts.get('tune', 0)}, test {counts.get('test', 0)}. "
          "A run is "
          "counted once it passes its start checks, before it reads any outcome-bearing input, so a run that later "
          "crashed or stopped counts too.\n")
    if sel:
        d = tune_res["data"]
        w(f"## Part 1: tuning, {TUNE[0]} .. {TUNE[1]}\n")
        w(f"**Decision: {sel['decision_text']}**\n")
        w(f"Data: {d['kept_days']} kept days (H1 {sel['kept_days_by_half']['H1']}, H2 "
          f"{sel['kept_days_by_half']['H2']}) with a quote file and an official close, of {d['d1_days']} D1 days; "
          f"{d['no_expiry_days']} with no same-day expiry, {len(d['no_close_days'])} with no official close. "
          f"Official closes checked against Robinhood ({d['close_check']['file']}) on "
          f"{d['close_check']['overlap_days']} overlapping tuning days, largest difference "
          f"{d['close_check']['max_abs_diff']:.4f}. 15:50/0.60/with equals scan.py's F2 on every kept day. "
          f"Across all kept days and entry minutes: {d['day_minutes_no_spot']} day-minutes with no implied spot, "
          f"{d['contract_slots_no_quote']} contract slots with no valid quote.\n")
        nl = sel["null"]
        if sel["pick"]:
            ps = sel["tuning_stats"]["pick"]
            t = ps["tuning"]
            w(f"- Pick: **{sel['pick']['name']}**, score {fm(sel['observed_best_score'])} a day; mean "
              f"{fm(t['mean_per_day'])} a day over {t['trades']} trades (coverage {fm(t['coverage'], pct=True)}); "
              f"H1 {fm(ps['H1']['mean_per_day'])}, H2 {fm(ps['H2']['mean_per_day'])}.")
            w(f"- Luck diagnostic: best eligible score under {nl['n_shifts']} circular shifts "
              f"({nl['n_shifts_nothing_eligible']} with nothing eligible, counted as −∞): median {fm(nl['median'])}, "
              f"95th percentile {fm(nl['p95'])}; p = {sel['p']:.3f}. It asks whether the best score beats the best "
              "score from signals unrelated to the days; it is not an exact test, does not test superiority over the "
              "current rule and does not pay for earlier studies.")
            pr = sel["paired_tuning_difference"]
            w(f"- Paired difference, pick − current, on tuning: {fm(pr['mean'])} a day (Newey-West t "
              f"{fm(pr['nw_t'])}, descriptive; no t-bar on tuning), paired n {pr['paired_n']}, "
              f"{pr['dropped_days']} day(s) dropped (a series missing).")
            w("\n| Gate | Holds |\n|---|---|")
            for k, ok in sel["gates"].items():
                w(f"| {GATE_TEXT[k]} | {'yes' if ok else 'NO'} |")
            w("")
        else:
            w(f"- No cell was eligible, so there is no pick. Luck diagnostic: {nl['status']}.\n")
        w(STAT_HEAD)
        for name, key in (("pick", "pick"), ("current", "current")):
            s = sel["tuning_stats"].get(key)
            if s:
                for per in ("tuning", "H1", "H2"):
                    w(_stat_row(f"{name} ({s['name']}) {per}", s[per]))
        w("")
        p3 = tune_res["part3_tuning"]
        w("### Part 3, tuning (descriptive; decides nothing)\n")
        w(f"{p3['n_eligible']} of {N_CELLS:,} cells eligible. The 15 best eligible cells:\n")
        w("| Rank | Cell | Score $/day | Mean $/day | Trades | H1 $/day (trades) | H2 $/day (trades) | "
          "Coverage all / H1 / H2 |")
        w("|---|---|---|---|---|---|---|---|")
        for i, t in enumerate(p3["top15"], 1):
            h1, h2 = t["halves"]["H1"], t["halves"]["H2"]
            w(f"| {i} | {t['cell']} | {fm(t['score'])} | {fm(t['mean_per_day'])} | {t['trades']} | "
              f"{fm(h1['mean_per_day'])} ({h1['trades']}) | {fm(h2['mean_per_day'])} ({h2['trades']}) | "
              f"{fm(t['coverage'], pct=True)} / {fm(h1['coverage'], pct=True)} / {fm(h2['coverage'], pct=True)} |")
        w("\nBest eligible cell for each candle minute:\n")
        w("| Candle | Best cell | Score $/day | Trades |")
        w("|---|---|---|---|")
        for k, v in p3["best_by_candle"].items():
            w(f"| {k} | {v['cell'] if v else 'none eligible'} | {fm(v['score']) if v else '—'} | "
              f"{v['trades'] if v else '—'} |")
        npc = p3["not_priced_per_cell"]
        w(f"\nNot-priced signal days per cell on tuning: median {npc['median']:.0f}, at most {npc['max']} "
          f"({npc['cell_with_max']}). By reason and half:\n")
        w("| Config | Period | Signal days | Priced | No spot | No quote |")
        w("|---|---|---|---|---|---|")
        for key in ("pick", "current"):
            s = sel["tuning_stats"].get(key)
            if s:
                for per in ("tuning", "H1", "H2"):
                    w(_np_row(f"{key} ({s['name']})", per, s[per]["not_priced"]))
        w("\nThreshold profile on tuning (15:50, with):\n")
        _profile_table(w, p3["threshold_profile"])
        w("")
    if test_res:
        p2 = test_res["part2"]
        w(f"## Part 2: the test, {TEST[0]} .. {TEST[1]} (once)\n")
        if p2.get("run"):
            a, b = p2["a_works"], p2["b_better"]
            w(f"**{p2['text']}**\n")
            w(f"- (a) Works: {p2['pick_name']} {fm(a['mean_per_day'])} a day, Newey-West t {fm(a['nw_t'])} over "
              f"{a['days']} days: {'holds' if a['passes'] else 'fails'} (needs mean > 0 with t ≥ {T_BAR}).")
            w(f"- (b) Better: pick − current {fm(b['mean'])} a day, t {fm(b['nw_t'])}, paired n {b['paired_n']}, "
              f"{b['dropped_days']} day(s) dropped: {'holds' if b['passes'] else 'fails'}.")
            w(f"- {p2['power_note']}\n")
        else:
            w(f"**Part 2 was not run. {p2['text']}**\n")
            w("This does not show that the current rule is the best setting.\n")
        d = test_res["data"]
        w(f"Data: {d['kept_days']} kept test days of {d['d1_days']} D1 days; {d['no_expiry_days']} with no same-day "
          f"expiry, {len(d['no_close_days'])} with no official close. Official closes checked against Robinhood on "
          f"{d['close_check']['overlap_days']} days (largest difference {d['close_check']['max_abs_diff']:.4f}). "
          "15:50/0.60/with equals scan.py's F2 on every kept day.")
        if test_res.get("code_changed_since_tune"):
            w("\nNote: refine.py changed between `tune` and `test` (the SHA-256 differs from the one in selection.json).")
        w("")
        p3 = test_res["part3_test"]
        w("## Part 3, test period (descriptive; computed after the decision was written)\n")
        w("The current rule's numbers on 2024-2026 were already known before this study.\n")
        w("| Config | Period | Version | Days | $/day | t | Trades | $/trade | Won | Median | Worst |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        vname = {"ask_fee_0.09": f"ask, ${FEE:.2f}", "ask_fee_0.74": f"ask, ${FEE_HIGH:.2f}",
                 "mid_fee_0.09": f"mid, ${FEE:.2f}"}
        for name, v in p3["configs"].items():
            for per, vers in v["versions"].items():
                for vk, s in vers.items():
                    w(f"| {name} ({v['cell']}) | {per} | {vname[vk]} | {s['days']} | {fm(s['mean_per_day'])} | "
                      f"{fm(s['nw_t_per_day'])} | {s['trades']} | {fm(s['mean_per_trade'])} | "
                      f"{fm(s['share_won'], pct=True)} | {fm(s['median_trade'])} | {fm(s['worst_trade'])} |")
        w("\nNot priced on the test period, by reason:\n")
        w("| Config | Period | Signal days | Priced | No spot | No quote |")
        w("|---|---|---|---|---|---|")
        for name, v in p3["configs"].items():
            for per, s in v["report"].items():
                if isinstance(s, dict) and "not_priced" in s:
                    w(_np_row(f"{name} ({v['cell']})", per, s["not_priced"]))
        w(f"\nThreshold profile on 2024-2026 (15:50, with), **{p3['threshold_profile']['label']}**:\n")
        _profile_table(w, p3["threshold_profile"]["rows"])
        fw = test_res["forward"]
        w(f"\n## Days after {TEST[1]} (descriptive)\n")
        w(f"Price basis: {fw['price_basis']} Only days after the selection was written "
          f"({fw['fresh_after_et_date']}, ET) count as fresh.\n")
        for name in ("current", "pick"):
            v = fw.get(name)
            if v is None:
                continue
            if not v.get("available"):
                w(f"- {name}: not available ({v['reason']}).")
                continue
            w(f"- {name}: {v['days']} signal day(s), {v['traded']} with a price, {v['fresh_days']} fresh; mean of the "
              f"priced ones {fm(v['mean_pnl_traded'])}." + (f" ({v['note']}.)" if v.get("note") else ""))
            if v["rows"]:
                w("\n| Date | Status | Option | Paid | Exit A | P&L $0.09 | Provisional | Label |")
                w("|---|---|---|---|---|---|---|---|")
                for r in v["rows"]:
                    strike = f"{r['strike']:.0f}" if r["strike"] is not None else "—"
                    w(f"| {r['date']} | {r['status']} | {r['kind']} {strike} | "
                      f"{fm(r['paid_incl_0.10'], sign=False)} | {fm(r['exit_a_value'], sign=False)} | "
                      f"{fm(r['pnl_fee_0.09'])} | {r['provisional']} | {r['label']} |")
                w("")
        w("")
    w("## Caveats\n")
    w("- Signals come from D1 (a CFD). A fill at the quoted ask ignores order size and fast minutes; the fill study "
      "found that a mid limit does not capture the mid.")
    w("- The download holds the 25 strikes within 60 points of the D1 15:51 ATM, so for earlier entries a missing "
      "price can depend on the later move. Cells need 95% coverage overall and in each half; inference is about "
      "priced days only.")
    w("- Expiry frequency, volatility and pricing changed over 2021-2023, so the circular-shift luck diagnostic is not "
      "an exact test.")
    if sel and not sel["goes_to_test"]:
        gates = "; ".join(GATE_TEXT.get(k, k) for k in sel["failed_gates"]) or "none"
        w(f"- {NO_ADVANCE} (failed gate: {gates}). That does not show that the current rule is the best setting.")
    w("- Nothing here is a trading recommendation.")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------------------------
# selftest (synthetic data only; every file goes to a temp folder)
# ------------------------------------------------------------------------------------------------
_QHDR = ("ts_recv,ts_event,rtype,publisher_id,instrument_id,side,price,size,flags,bid_px_00,ask_px_00,bid_sz_00,"
         "ask_sz_00,bid_pb_00,ask_pb_00,symbol")


def _syn_quotes_text(day: str, spots: dict, center: float, drop_minutes=(), drop_contracts=()) -> str:
    """cbbo-1m-like rows at each minute's open: mid = intrinsic + 1.00, bid/ask = mid -/+ 0.10, strikes center +- 60."""
    lines = [_QHDR]
    y, mo, dd = (int(x) for x in day.split("-"))
    for hm, S in spots.items():
        if hm in drop_minutes:
            continue
        ts = datetime(y, mo, dd, int(hm[:2]), int(hm[3:]), tzinfo=ET).astimezone(timezone.utc)
        ts = ts.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        for K in np.arange(center - 60, center + 61, 5.0):
            for kind in ("call", "put"):
                if (hm, kind, float(K)) in drop_contracts:
                    continue
                mid = rp.intrinsic(kind, float(K), S) + 1.0
                sym = f"{'SPXW':<6}{day[2:4]}{day[5:7]}{day[8:10]}{'C' if kind == 'call' else 'P'}{round(K * 1000):08d}"
                lines.append(f"{ts},,193,30,1,N,,0,200,{mid - 0.1:.9f},{mid + 0.1:.9f},10,10,0,0,{sym}")
    return "\n".join(lines) + "\n"


def _bdays(lo: str, hi: str) -> list:
    d = np.arange(np.datetime64(lo), np.datetime64(hi) + np.timedelta64(1, "D"))
    return [str(x) for x in d[np.is_busday(d)]]


def _syn_world(tmp: Path, scan, seed: int, per_half: int, n_test: int, plant: bool) -> Env:
    """A synthetic world in `tmp`: a D1-like panel (2021-2026), quote files, closes, Robinhood stubs, forward logs.
    Planted (if asked): the 15:45 candle with |body| >= 0.65 range moves the close 25 points its way after 15:46."""
    rng = np.random.default_rng(seed)
    pick_days = lambda lo, hi, k: sorted(rng.choice(_bdays(lo, hi), k, replace=False).tolist())   # noqa: E731
    dates = (pick_days("2021-01-04", "2022-09-30", per_half) + pick_days("2022-10-03", "2023-12-29", per_half)
             + pick_days("2024-01-02", "2026-10-20", n_test))
    n = len(dates)
    O = np.full((n, scan.N_MIN), 4000.0)
    H, L, C = O + 0.5, O - 0.5, O.copy()
    ratio = rng.uniform(0, 1, (n, len(CANDLES)))
    sgn = rng.choice([-1.0, 1.0], (n, len(CANDLES)))
    for a, k in enumerate(CANDLES):
        i = scan.mi(k)
        R = rng.uniform(1, 3, n)
        body = sgn[:, a] * ratio[:, a] * R
        O[:, i] = 4000.0 + rng.normal(0, 5, n)
        C[:, i] = O[:, i] + body
        H[:, i] = np.maximum(O[:, i], C[:, i]) + (R - np.abs(body)) / 2
        L[:, i] = np.minimum(O[:, i], C[:, i]) - (R - np.abs(body)) / 2
    O[3, scan.mi("15:47")] = np.nan                                         # a missing bar -> a missing signal
    tmp.mkdir(parents=True, exist_ok=True)
    npz = tmp / "d1_syn.npz"                                                # the panel's source file
    with open(npz, "wb") as fh:
        np.savez(fh, dates=np.array(dates), O=O, H=H, L=L, C=C)
    qdir = tmp / "quotes"
    qdir.mkdir(parents=True)
    tune_days = [d for d in dates if d <= TUNE[1]]
    none_days = {tune_days[5], tune_days[-7], [d for d in dates if d >= TEST[0]][4]}
    no_close = tune_days[9]
    closes = {}
    a45 = CANDLES.index("15:45")
    for i, d in enumerate(dates):
        if d in none_days:
            (qdir / f"{d}.none").write_text("no expiry\n")
            continue
        base = 4000.0 + rng.normal(0, 40)
        spots = {m: base + x for m, x in zip(ENTRIES, np.cumsum(rng.normal(0, 0.6, len(ENTRIES))))}
        if plant and ratio[i, a45] >= 0.65:
            X = spots["15:46"] + sgn[i, a45] * 25.0
        else:
            X = spots["15:51"] + rng.normal(0, 3)                          # about fair for a $1.00 time value
        drop_m = {m for m in ENTRIES if rng.uniform() < 0.01}               # no implied spot at that minute
        center = rp.atm_of(spots["15:51"])
        drop_c = {("15:51", "call", center - 10)} if i % 37 == 0 else set()  # one missing contract -> no_quote
        text = _syn_quotes_text(d, spots, center, drop_m, drop_c)
        (qdir / f"{d}.csv.gz").write_bytes(gzip.compress(text.encode()))
        if d != no_close:
            closes[d] = round(X, 2)
    ccsv = tmp / "closes.csv"
    ccsv.write_text("DATE,SPX\n" + "".join(f"{d[5:7]}/{d[8:10]}/{d[:4]},{v:.6f}\n" for d, v in sorted(closes.items())))
    rh_days = [d for d in dates if d >= TEST[0] and d in closes][:6]
    rh_tune_days = [d for d in dates if d <= TUNE[1] and d in closes][:8]
    rh_tune = tmp / "robinhood_spx_daily_2021_2023.json"
    rh_tune.write_text(json.dumps({"source": "synthetic", "fetched_utc": "2026-11-09T00:00:00Z",
                                   "closes": {d: closes[d] for d in rh_tune_days}}))
    live = tmp / "spx" / "live_2026-10-21"
    live.mkdir(parents=True)
    bars = [{"begins_at": f"{d}T13:30:00Z", "close_value": f"{closes[d]:.4f}", "interpolated": False}
            for d in rh_days]
    bars.append({"begins_at": "2026-11-02T14:30:00Z", "close_value": "1.0", "interpolated": False})   # after TEST
    (live / "spx_daily.json").write_text(json.dumps({"data": {"results": [
        {"instrument_id": "SYN-SPX", "symbol": "SPX", "interval": "day", "bars": bars}]}}))
    days_csv = tmp / "d1_days_syn.csv"                                      # the D1 day listing (no prices)
    days_csv.write_text("date,calendar,keep\n" + "".join(f"{d},nyse,True\n" for d in dates))
    calls: list = []
    dep = tmp / "syn_dep.py"                                                # a synthetic executable dependency
    dep.write_text("# synthetic dependency of refine.py (selftest only)\n")
    out_dir = tmp / "out"
    out_dir.mkdir()
    fdir = tmp / "forward"
    fdir.mkdir()
    prereg, ledger = tmp / "prereg.md", tmp / "LEDGER.md"
    prereg.write_text("synthetic locked plan\n")
    ledger.write_text(f"- t  {sha256_file(prereg)}  prereg.md\n")
    env = Env(out_dir=out_dir, quote_dir=qdir, closes_csv=ccsv, trades_csv=tmp / "trades.csv", prereg=prereg,
              ledger=ledger, forward_dir=fdir, code_path=Path(__file__).resolve(), scan=scan,
              load_panel=_syn_panel_loader(scan, npz, calls), rh_tune_file=rh_tune,
              rh_test_files=lambda: sorted((tmp / "spx").glob("live_*/spx_daily.json")), spx_id="SYN-SPX",
              days_file=days_csv, code_files=[REALPRICE_PY, rp.SCAN_PY, dep], quote_cache={})
    env.panel_calls = calls                                                 # type: ignore[attr-defined]
    env.rh_tune_days = rh_tune_days                                         # type: ignore[attr-defined]
    env.rh_test_days = rh_days                                              # type: ignore[attr-defined]
    env.syn_dep, env.syn_npz = dep, npz                                     # type: ignore[attr-defined]
    return env


def _syn_panel_loader(scan, npz: Path, calls: list):
    """load_panel of the synthetic world: reads the panel file on every call, so its bytes are a real input."""
    def load_panel(start, end):
        calls.append((start, end))
        with np.load(npz, allow_pickle=False) as z:
            dates = z["dates"].astype(object)
            P = scan.Panel(dates, z["O"], z["H"], z["L"], z["C"], np.full(len(dates), np.nan),
                           np.full(len(dates), np.nan), {"syn": True})
        return scan.sub(P, (dates >= start) & (dates <= end))
    return load_panel


def _isolated_world(env: Env, d: Path) -> Env:
    """The same synthetic world with private copies of every input file (quotes, closes, panel file, Robinhood files,
    the synthetic code dependency), so a check can change one of them in place."""
    d.mkdir(parents=True)
    shutil.copytree(env.quote_dir, d / "quotes")
    shutil.copy2(env.closes_csv, d / "closes.csv")
    shutil.copy2(env.syn_npz, d / "d1_syn.npz")
    shutil.copy2(env.days_file, d / "d1_days_syn.csv")
    shutil.copy2(env.rh_tune_file, d / env.rh_tune_file.name)
    shutil.copy2(env.syn_dep, d / "syn_dep.py")
    for f in env.rh_test_files():
        (d / "spx" / f.parent.name).mkdir(parents=True)
        shutil.copy2(f, d / "spx" / f.parent.name / f.name)
    e = _env_copy(env, d / "out", quote_dir=d / "quotes", closes_csv=d / "closes.csv", rh_tune_file=d /
                  env.rh_tune_file.name, rh_test_files=lambda: sorted((d / "spx").glob("live_*/spx_daily.json")),
                  days_file=d / "d1_days_syn.csv", code_files=[REALPRICE_PY, rp.SCAN_PY, d / "syn_dep.py"],
                  quote_cache={})
    calls: list = []
    e.load_panel = _syn_panel_loader(env.scan, d / "d1_syn.npz", calls)
    e.panel_calls, e.syn_dep, e.syn_npz = calls, d / "syn_dep.py", d / "d1_syn.npz"   # type: ignore[attr-defined]
    return e


def _env_copy(env: Env, out_dir: Path, **kw) -> Env:
    """The same synthetic world with a fresh output folder (and fresh event lists)."""
    e = Env(**{k: getattr(env, k) for k in env.__dataclass_fields__})
    e.out_dir, e.trades_csv = out_dir, out_dir / "trades.csv"
    e.events, e.loader_calls, e.priced = [], [], None
    for k in ("rh_tune_days", "rh_test_days", "syn_dep", "syn_npz"):
        setattr(e, k, getattr(env, k))
    for k, v in kw.items():
        setattr(e, k, v)
    out_dir.mkdir(parents=True, exist_ok=True)
    calls: list = []
    inner = env.load_panel

    def load_panel(start, end):
        calls.append((start, end))
        return inner(start, end)

    e.load_panel = load_panel
    e.panel_calls = calls                                                   # type: ignore[attr-defined]
    return e


def _csv_rows(path: Path, period: str | None = None) -> list:
    with open(path, newline="") as fh:
        return [r for r in csv.DictReader(fh) if period is None or r["period"] == period]


def _expect_msg(fn, text: str, exc=(SystemExit,)):
    try:
        fn()
    except exc as e:
        assert text in str(e), (text, str(e))
        return e
    raise AssertionError(f"did not refuse (expected: {text})")


class _Hook:
    """Selftest write hook: records every output write step and raises SimulatedCrash at step `crash_at`."""

    def __init__(self, crash_at: int | None = None):
        self.crash_at, self.steps = crash_at, []

    def __call__(self, path: Path, phase: str) -> None:
        self.steps.append(("runs/attempt" if path.parent.name == "runs" else path.name, phase))
        if self.crash_at is not None and len(self.steps) == self.crash_at:
            raise SimulatedCrash(f"simulated crash at write step {self.crash_at} ({path.name}, {phase})")


def _with_hook(hook, fn):
    global _WRITE_HOOK
    _WRITE_HOOK = hook
    try:
        return fn()
    finally:
        _WRITE_HOOK = None


class _FnumRecorder:
    """Wraps realprice.fnum to record every value converted."""

    def __init__(self):
        self.seen, self.orig = [], rp.fnum

    def __enter__(self):
        def rec(x):
            self.seen.append(x)
            return self.orig(x)
        rp.fnum = rec
        return self

    def __exit__(self, *a):
        rp.fnum = self.orig


def _write_forward_logs(fdir: Path) -> None:
    sl = ["date,signal_name,signal,offset,status,kind,strike,S_1551_open,settle,settle_source,provisional,"
          "entry_open_1551,cost_incl_half_spread,exit_a_value,pnl_a_fee_0.09,pnl_a_fee_0.74,return_on_premium_a,"
          "exit_b_status,exit_b_close_1559,pnl_b_fee_0.09,pnl_b_fee_0.74",
          "2026-10-20,F2_1m_1550_strong_body,1,ITM10,traded,call,7000,,,,,,5,6,99.91,,,,,,",       # not after TEST
          "2026-10-21,F2_1m_1550_strong_body,1,ITM10,traded,call,7750,,,,False,,12.1,15.0,289.91,,,,,,",
          "2026-10-22,F2_1m_1550_strong_body,-1,ITM10,no_minute_option_bars,put,7670,,,,,,,,,,,,,,",
          "2026-10-21,F1_1m_15:50,1,ITM20,traded,call,7740,,,,False,,22.1,25.0,289.91,,,,,,",
          "2026-10-22,F1_1m_15:50,-1,ITM20,traded,put,7680,,,,False,,21.0,10.0,-1100.09,,,,,,",
          "2026-10-23,F1_1m_15:50,1,ITM20,traded,call,7600,,,,False,,20.0,30.0,999.91,,,,,,"]
    (fdir / "strikes_forward_log.csv").write_text("\n".join(sl) + "\n")
    cl = ["date,source,period,status,body_1550,range_1550",
          "2026-10-21,SPX_robinhood,FORWARD,ok,0.9,1.0",                    # body 90%: on at 0.80
          "2026-10-21,SPY_recorder,FORWARD,ok,-0.9,1.0",                    # other source: ignored
          "2026-10-22,SPX_robinhood,FORWARD,ok,-0.7,1.0",                   # 70%: off at 0.80
          "2026-10-23,SPX_robinhood,FORWARD,ok,-0.85,1.0",                  # on at 0.80 but the log says +1: mismatch
          "2026-10-26,SPX_robinhood,FORWARD,ok,0.95,1.0"]                   # on, but no F1 row: not logged
    (fdir / "candle_1550_log.csv").write_text("\n".join(cl) + "\n")


def _expect_exit(fn, what: str, exc=(SystemExit,)):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"{what}: did not refuse")


def selftest_grid_brute(scan) -> None:
    """grid_stats against a direct loop on a tiny random cube (NaN signals, unpriced trades, two masks)."""
    rng = np.random.default_rng(1)
    n = 23
    sig = rng.choice([-1.0, 0.0, 1.0], (n, len(CANDLES), len(THRESHOLDS)))
    sig[rng.uniform(size=sig.shape) < 0.08] = np.nan
    up = rng.normal(0, 100, (n, len(ENTRIES), len(OFFSETS)))
    dn = rng.normal(0, 100, (n, len(ENTRIES), len(OFFSETS)))
    up[rng.uniform(size=up.shape) < 0.15] = np.nan
    dn[rng.uniform(size=dn.shape) < 0.15] = np.nan
    masks = [np.ones(n, bool), np.arange(n) < 11, np.arange(n) >= 11]
    st = grid_stats(sig, up, dn, masks)
    for mi_, m in enumerate(masks):
        for ix in np.ndindex(*GRID_SHAPE):
            a, b, di, j = ix
            vals, trades, sigd = [], 0, 0
            for i in np.flatnonzero(m):
                s = sig[i, a, b]
                if np.isnan(s):
                    continue
                s *= DIRECTIONS[di]
                if s == 0:
                    vals.append(0.0)
                    continue
                sigd += 1
                v = up[i, a, j] if s > 0 else dn[i, a, j]
                if np.isfinite(v):
                    vals.append(v)
                    trades += 1
            r = st[mi_]
            assert r["n_trades"][ix] == trades and r["n_signal"][ix] == sigd and r["n_days"][ix] == len(vals), ix
            if vals:
                assert abs(r["mean"][ix] - np.mean(vals)) < 1e-9, ix
            else:
                assert np.isnan(r["mean"][ix])
            if sigd:
                assert abs(r["coverage"][ix] - trades / sigd) < 1e-12
            else:
                assert np.isnan(r["coverage"][ix])
    # one shifted copy equals the grid of np.roll(sig, s)
    S = shifted(sig, [3, 7])
    assert np.array_equal(np.nan_to_num(S[1], nan=9), np.nan_to_num(np.roll(sig, 7, axis=0), nan=9))
    st2 = grid_stats(S, up, dn, masks)
    st3 = grid_stats(np.roll(sig, 3, axis=0), up, dn, masks)
    for k in ("n_trades", "n_signal", "n_days"):
        assert np.array_equal(st2[1][k][0], st3[1][k])
    assert np.allclose(np.nan_to_num(st2[0]["mean"][0], nan=7), np.nan_to_num(st3[0]["mean"], nan=7))


def selftest_plateau_eligibility_pick() -> None:
    # plateau: neighbours at +-0.05 whether eligible or not; non-finite neighbours ignored; finite centre required
    m = np.full(GRID_SHAPE, np.nan)
    m[0, :, 0, 0] = [1.0, 4.0, np.nan, 2.0, 6.0, np.nan, np.nan, 3.0, 5.0, 7.0, -1.0]
    p = plateau_score(m)
    exp = [2.5, 2.5, np.nan, 4.0, 4.0, np.nan, np.nan, 4.0, 5.0, 11 / 3, 3.0]
    for b, e in enumerate(exp):
        assert (np.isnan(p[0, b, 0, 0]) if np.isnan(e) else abs(p[0, b, 0, 0] - e) < 1e-12), (b, p[0, b, 0, 0])
    assert np.isnan(p[1]).all()
    # leading (shift) axis: same result per copy
    p2 = plateau_score(np.stack([m, m * 2]))
    assert np.allclose(np.nan_to_num(p2[1], nan=0), np.nan_to_num(2 * p, nan=0))

    # eligibility incl. coverage (exactly 95% passes, just under fails), per half
    def mk(**kv):
        base = {"n_trades": 100, "n_signal": 100, "mean": 1.0}
        base.update(kv)
        return {k: np.full(GRID_SHAPE, v, float if k == "mean" else int) for k, v in base.items()}

    ok = (mk(n_trades=100, n_signal=105), mk(n_trades=40, n_signal=42), mk(n_trades=60, n_signal=63))
    assert 100 / 105 > 0.95 and 40 / 42 > 0.95 and 60 / 63 > 0.95 and eligible(*ok).all()
    assert eligible(mk(n_trades=190, n_signal=200), mk(n_trades=95, n_signal=100), mk(n_trades=95, n_signal=100)).all()
    for bad in ((mk(n_trades=99), ok[1], ok[2]),                                 # too few trades
                (ok[0], mk(n_trades=39, n_signal=39), ok[2]),                    # too few in H1
                (ok[0], ok[1], mk(n_trades=40, n_signal=40, mean=0.0)),          # H2 mean not above 0
                (ok[0], mk(n_trades=40, n_signal=40, mean=np.nan), ok[2]),       # H1 mean missing
                (mk(n_trades=100, n_signal=106), ok[1], ok[2]),                  # 94.3% overall
                (ok[0], mk(n_trades=40, n_signal=43), ok[2]),                    # 93.0% in H1
                (ok[0], ok[1], mk(n_trades=94, n_signal=99))):                   # 94.9% in H2
        assert not eligible(*bad).any()

    # pick: highest score; score ties -> distance to the current rule; then enumeration order
    def put(cells_scores):
        sc = np.full(GRID_SHAPE, -50.0)
        el = np.zeros(GRID_SHAPE, bool)
        for c, v in cells_scores:
            sc[idx_of(c)] = v
            el[idx_of(c)] = True
        return sc, el

    sc, el = put([(("15:42", 0.40, 1, 20), 9.0), (("15:50", 0.65, 1, 10), 9.0), (("15:49", 0.60, 1, 10), 9.0),
                  (("15:50", 0.60, 1, 10), 8.0)])
    assert cell_of(pick_cell(sc, el)) == ("15:49", 0.60, 1, 10)                # distance 1 twice: candle order first
    sc, el = put([(("15:48", 0.60, 1, 10), 5.0), (("15:50", 0.70, 1, 10), 5.0), (("15:49", 0.60, -1, 10), 5.0)])
    assert cell_of(pick_cell(sc, el)) == ("15:48", 0.60, 1, 10)                # all distance 2: 15:48 first
    sc, el = put([(("15:49", 0.60, -1, 10), 5.0), (("15:49", 0.60, 1, 15), 5.0)])
    assert cell_of(pick_cell(sc, el)) == ("15:49", 0.60, 1, 15)                # distance 2: with before against
    sc, el = put([(("15:50", 0.60, 1, 5), 5.0), (("15:50", 0.60, 1, 15), 5.0)])
    assert cell_of(pick_cell(sc, el)) == ("15:50", 0.60, 1, 15)                # distance 1: ITM15 before ITM5
    sc, el = put([(("15:40", 0.90, -1, -20), 5.0), (("15:47", 0.60, 1, 10), 5.0)])
    assert cell_of(pick_cell(sc, el)) == ("15:47", 0.60, 1, 10)                # nearer wins although later in order
    sc, el = put([(("15:40", 0.90, -1, -20), 5.0 + 1e-12), (("15:50", 0.65, 1, 10), 5.0)])
    assert cell_of(pick_cell(sc, el)) == ("15:40", 0.90, -1, -20)              # exact ties only
    sc[idx_of(("15:41", 0.40, 1, 0))] = 99.0                                   # highest, but not eligible
    assert cell_of(pick_cell(sc, el)) == ("15:40", 0.90, -1, -20)
    assert pick_cell(sc, np.zeros(GRID_SHAPE, bool)) is None
    order = ranked_eligible(*put([(("15:45", 0.50, 1, 0), 3.0), (("15:50", 0.60, 1, 10), 3.0),
                                  (("15:41", 0.40, 1, 0), 4.0)]))
    assert [cell_of(x) for x in order] == [("15:41", 0.40, 1, 0), ("15:50", 0.60, 1, 10), ("15:45", 0.50, 1, 0)]
    # an eligible peak whose ineligible neighbours are bad loses to a flat eligible plateau
    mean = np.full(GRID_SHAPE, -1.0)
    elg = np.zeros(GRID_SHAPE, bool)
    a1 = idx_of(("15:43", 0.60, 1, 5))
    mean[a1], elg[a1] = 10.0, True
    mean[idx_of(("15:43", 0.55, 1, 5))] = mean[idx_of(("15:43", 0.65, 1, 5))] = -30.0
    for th in (0.45, 0.50, 0.55):
        mean[idx_of(("15:44", th, 1, 5))] = 5.0
    elg[idx_of(("15:44", 0.50, 1, 5))] = True
    assert cell_of(pick_cell(plateau_score(mean), elg)) == ("15:44", 0.50, 1, 5)


def _array_world(seed: int, n: int, plant: bool):
    rng = np.random.default_rng(seed)
    ratio = rng.uniform(0, 1, (n, len(CANDLES)))
    sgn = rng.choice([-1.0, 1.0], (n, len(CANDLES)))
    sig = np.where(ratio[:, :, None] >= np.array(THRESHOLDS)[None, None, :], sgn[:, :, None], 0.0)
    up = rng.normal(-15, 200, (n, len(ENTRIES), len(OFFSETS)))
    dn = rng.normal(-15, 200, (n, len(ENTRIES), len(OFFSETS)))
    if plant:
        a = CANDLES.index("15:44")
        on = ratio[:, a] >= 0.60
        up[on & (sgn[:, a] > 0), a, :5] += 220.0
        dn[on & (sgn[:, a] < 0), a, :5] += 220.0
    dates = np.array(sorted(rng.choice(_bdays(*TUNE), n, replace=False).tolist()), dtype=object)
    masks = [np.ones(n, bool)] + [np.array([in_window(d, w) for d in dates]) for _, w in HALVES]
    return sig, up, dn, masks


def selftest_null() -> None:
    """A planted edge gives a small p; on pure noise p is not systematically small (the mean p over six noise worlds
    is checked, since a single noise world gives p below 0.05 one time in twenty)."""
    noise_p = []
    for plant, seed in ((True, 21), (False, 100), (False, 101), (False, 102), (False, 103), (False, 104),
                        (False, 105)):
        sig, up, dn, masks = _array_world(seed, 360, plant)
        st = grid_stats(sig, up, dn, masks)
        score = plateau_score(st[0]["mean"])
        best = pick_cell(score, eligible(*st))
        shifts = shifts_for(len(sig))
        assert shifts[0] == 21 and shifts[-1] <= len(sig) - 21 and np.all(np.diff(shifts) == 3)
        nulls = null_best(sig, up, dn, masks, shifts, chunk=40)
        assert len(nulls) == len(shifts)
        if plant:
            assert best is not None and cell_of(best)[0] == "15:44" and cell_of(best)[2] == 1, best
            p = p_value(nulls, float(score[best]))
            assert p <= 0.02, p
        else:
            noise_p.append(p_value(nulls, float(score[best])) if best is not None else 1.0)
    assert 0.2 < float(np.mean(noise_p)) < 0.8 and max(noise_p) > 0.3, noise_p
    # one shift checked directly
    sig, up, dn, masks = _array_world(23, 120, True)
    nb = null_best(sig, up, dn, masks, [30, 33], chunk=1)
    st = grid_stats(np.roll(sig, 33, axis=0), up, dn, masks)
    v = np.where(eligible(*st), plateau_score(st[0]["mean"]), -np.inf).max()
    assert nb[1] == v
    assert p_value(np.array([1.0, 2.0, 3.0, -np.inf]), 2.0) == 3 / 5
    assert null_quantile(np.array([-np.inf, -np.inf, 1.0, 2.0]), 50) is None
    assert null_quantile(np.array([-np.inf, 1.0, 2.0]), 50) == 1.0


def selftest_decisions() -> None:
    fam = decide(("15:50", 0.60, 1, 20), 0.001, 5.0)
    assert fam["decision"] == "already_evaluated" and not fam["goes_to_test"] and FAMILY_TEXT in fam["text"]
    assert NO_ADVANCE in fam["text"] and "no runner-up is substituted" in fam["text"]
    assert decide(("15:50", 0.60, 1, 10), 0.9, -5.0)["decision"] == "already_evaluated"
    assert decide(("15:50", 0.65, 1, 10), 0.01, 5.0)["decision"] == "test"
    assert decide(("15:50", 0.60, -1, 10), 0.05, 0.1)["decision"] == "test"           # against is not the family
    nt = decide(("15:45", 0.70, 1, 5), 0.2, 5.0)
    assert nt["decision"] == "no_test" and nt["failed_gates"] == ["p_le_alpha"] and nt["text"].startswith(NO_ADVANCE)
    nt = decide(("15:45", 0.70, 1, 5), 0.01, 0.0)
    assert nt["failed_gates"] == ["paired_mean_gt_0"] and GATE_TEXT["paired_mean_gt_0"] in nt["text"]
    assert decide(("15:45", 0.70, 1, 5), None, None)["failed_gates"] == ["p_le_alpha", "paired_mean_gt_0"]
    npk = decide(None, None, None)
    assert npk["decision"] == "no_pick" and npk["text"].startswith(NO_ADVANCE)
    assert "best setting" not in npk["text"] and "best setting" not in nt["text"]
    # paired difference: complete case, zeros kept
    pr = paired([1.0, np.nan, 0.0, 3.0, 2.0, 0.0], [0.0, 1.0, np.nan, 0.0, 0.0, 0.0], np.array(list("abcdef")))
    assert pr["paired_n"] == 4 and pr["dropped_days"] == 2 and pr["dropped_dates"] == ["b", "c"]
    assert abs(pr["mean"] - 6 / 4) < 1e-12 and pr["nw_t"] is None                   # n < 8 -> no t
    # criteria (a)/(b): t=None fails (n < 8, zero standard error)
    assert not passes(*(lambda r: (r["mean"], r["t"]))(rp.nw([5.0] * 7)))
    assert not passes(*(lambda r: (r["mean"], r["t"]))(rp.nw([5.0] * 30)))         # zero SE
    rng = np.random.default_rng(4)
    good = rp.nw(rng.normal(50, 10, 200))
    assert passes(good["mean"], good["t"]) and not passes(-good["mean"], good["t"]) and not passes(1.0, 1.99)
    assert passes(1.0, 2.0) and not passes(None, 3.0) and not passes(0.0, 3.0)
    assert part2_outcome(True, True)["outcome"] == "adopt"
    assert part2_outcome(True, False)["outcome"] == "works_not_better"
    assert part2_outcome(False, True)["outcome"] == "not_confirmed" == part2_outcome(False, False)["outcome"]
    # Part 2 on a synthetic cube with a pick that wins and one that is 7 days only
    n = 60
    sig = np.zeros((n, len(CANDLES), len(THRESHOLDS)))
    a, b, _, j = idx_of(("15:45", 0.70, 1, 5))
    sig[:, a, b] = rng.choice([-1.0, 1.0], n)
    cube = {"dates": np.array([f"2024-01-{i:02d}" for i in range(n)], dtype=object),
            "up": np.full((n, len(ENTRIES), len(OFFSETS)), np.nan), "dn": np.full((n, len(ENTRIES), len(OFFSETS)), np.nan)}
    cube["up"][:, a, j] = rng.normal(300, 50, n)
    cube["dn"][:, a, j] = rng.normal(300, 50, n)
    r = part2(("15:45", 0.70, 1, 5), sig, cube)
    assert r["a_works"]["passes"] and r["b_better"]["passes"] and r["outcome"] == "adopt"
    assert r["b_better"]["paired_n"] == n                                          # the current rule: 0 every day
    cube["up"][7:, a, j] = np.nan
    cube["dn"][7:, a, j] = np.nan
    r = part2(("15:45", 0.70, 1, 5), sig, cube)
    assert r["a_works"]["nw_t"] is None and not r["a_works"]["passes"] and r["outcome"] == "not_confirmed"


def selftest_pricing() -> None:
    day = "2024-03-15"
    spots = {m: 5000.0 + 0.4 * i for i, m in enumerate(ENTRIES)}
    center = rp.atm_of(spots["15:51"])
    text = _syn_quotes_text(day, spots, center, drop_minutes={"15:43"},
                            drop_contracts={("15:51", "put", center + 10)})
    q, _ = rp.parse_quotes(text, day)
    X = 5012.0
    full = price_day(q, X)
    i51, j10 = ENTRIES.index("15:51"), OFFSETS.index(10)
    assert abs(full["spot"][i51] - spots["15:51"]) < 1e-9 and full["atm"][i51] == center
    K = center - 10
    assert abs(full["up"][i51, j10] - (100 * (X - K - (spots["15:51"] - K + 1.1)) - FEE)) < 1e-6
    assert abs(full["mid_up"][i51, j10] - (full["ask_up"][i51, j10] - 0.1)) < 1e-9
    assert np.isnan(full["dn"][i51, j10]) and np.isfinite(full["spot"][i51])           # no_quote
    assert np.isnan(full["spot"][ENTRIES.index("15:43")]) and np.isnan(full["up"][ENTRIES.index("15:43")]).all()
    only = price_day(q, X, {(i51, j10)})
    assert np.isfinite(only["up"]).sum() == 1 and np.isfinite(only["spot"]).sum() == 1
    assert only["up"][i51, j10] == full["up"][i51, j10]
    # trade rows carry the reason
    cube = {k: v[None] for k, v in full.items()}
    cube["dates"] = np.array([day], dtype=object)
    sig = np.zeros((1, len(CANDLES), len(THRESHOLDS)))
    sig[0, CANDLES.index("15:50"), THRESHOLDS.index(0.60)] = -1.0
    sig[0, CANDLES.index("15:42"), THRESHOLDS.index(0.60)] = 1.0
    r = trade_rows("current", CURRENT, sig, cube, "test")
    assert len(r) == 1 and r[0]["status"] == "no_quote" and r[0]["kind"] == "put" and r[0]["strike"] == center + 10
    r = trade_rows("pick", ("15:42", 0.60, 1, 0), sig, cube, "test")
    assert r[0]["status"] == "no_spot" and r[0]["entry_minute"] == "15:43"
    sig[0, CANDLES.index("15:50"), THRESHOLDS.index(0.60)] = 1.0
    r = trade_rows("current", CURRENT, sig, cube, "test")[0]
    assert r["status"] == "priced" and abs(r["pnl_ask_fee_0.74"] - (r["pnl_ask_fee_0.09"] - 0.65)) < 1e-9
    assert abs(r["pnl_mid_fee_0.09"] - (r["pnl_ask_fee_0.09"] + 10.0)) < 1e-6
    npc = not_priced(np.array([1.0, -1.0, 0.0, np.nan, 1.0]), np.array([np.nan, 5.0, 5.0, 5.0, 5.0]),
                     np.array([np.nan, np.nan, 0.0, 1.0, 3.0]))
    assert npc == {"signal_days": 3, "priced": 1, "no_spot": 1, "no_quote": 1}


def selftest_isolation_units(tmp: Path) -> None:
    folder = tmp / "iso"
    folder.mkdir()
    (folder / "2023-12-29.csv.gz").write_bytes(gzip.compress(_syn_quotes_text(
        "2023-12-29", {"15:51": 4700.0}, 4700.0).encode()))
    (folder / "2024-01-02.csv.gz").write_bytes(gzip.compress(_syn_quotes_text(
        "2024-01-02", {"15:51": 4700.0}, 4700.0).encode()))
    calls: list = []
    ld = window_loader(folder, TUNE, calls)
    q, _ = ld("2023-12-29")
    assert "15:51" in q and calls == ["2023-12-29"]
    _expect_exit(lambda: ld("2024-01-02"), "tuning loader on 2024", (IsolationError,))
    _expect_exit(lambda: ld("2020-12-31"), "tuning loader before 2021", (IsolationError,))
    assert calls == ["2023-12-29"]
    _expect_exit(lambda: window_loader(folder, TEST)("2023-12-29"), "test loader on 2023", (IsolationError,))
    cache: dict = {}
    _expect_exit(lambda: window_loader(folder, TUNE, None, cache)("2024-01-02"), "cached loader", (IsolationError,))
    assert cache == {}                                                        # the window check comes first
    _expect_exit(lambda: assert_window(["2023-12-29", "2024-01-02"], TUNE, "x"), "assert_window", (IsolationError,))
    assert quote_listing(folder) == {"2023-12-29": "file", "2024-01-02": "file"}
    assert listing_sha(folder, TUNE)["files"] == 1 and listing_sha(folder, TEST)["files"] == 1
    # fix 1: closes are filtered record by record before any value is converted
    c = tmp / "c.csv"
    c.write_text("DATE,SPX\n12/31/2020,3756.070000\n12/29/2023,4769.830000\n01/02/2024,4742.830000\n"
                 "1/3/2024,4704.810000\n")
    with _FnumRecorder() as r:
        assert load_closes(c, TUNE) == {"2023-12-29": 4769.83}
    assert r.seen == ["4769.830000"], r.seen
    with _FnumRecorder() as r:
        assert load_closes(c, TEST) == {"2024-01-02": 4742.83, "2024-01-03": 4704.81}
    assert r.seen == ["4742.830000", "4704.810000"], r.seen
    _expect_exit(lambda: load_closes(tmp / "nope.csv", TUNE), "missing closes")
    # fix 5: the Robinhood 2021-2023 file: every key must be in the tuning window, values converted only after that
    good = tmp / "rh_good.json"
    good.write_text('{"source": "s", "fetched_utc": "t", "closes": {"2021-03-01": 3901.82, "2023-10-02": 4288.39}}')
    with _FnumRecorder() as r:
        got = read_rh_tune_closes(good, TUNE)
    assert got == {"2021-03-01": (3901.82, "rh_good.json"), "2023-10-02": (4288.39, "rh_good.json")}
    assert sorted(r.seen) == ["3901.82", "4288.39"]                           # parsed as text, converted here
    bad = tmp / "rh_bad.json"
    bad.write_text('{"source": "s", "fetched_utc": "t", "closes": {"2021-03-01": 3901.82, "2024-01-02": 4742.83}}')
    with _FnumRecorder() as r:
        _expect_msg(lambda: read_rh_tune_closes(bad, TUNE), "1 date(s) outside 2021-01-01..2023-12-31")
    assert r.seen == []                                                       # refused before converting anything
    nofmt = tmp / "rh_nofmt.json"
    nofmt.write_text('{"data": []}')
    _expect_msg(lambda: read_rh_tune_closes(nofmt, TUNE), "stopping before any selection")
    # the tuning close check (unit level): missing file, < 3 overlap days, a mismatch, a pass
    tc = {"2023-12-27": 4781.58, "2023-12-28": 4783.35, "2023-12-29": 4769.83, "2023-12-26": 4774.75}

    def rh_file(name, closes):
        f = tmp / name
        f.write_text(json.dumps({"source": "s", "fetched_utc": "t", "closes": closes}))
        return types.SimpleNamespace(rh_tune_file=f)

    _expect_msg(lambda: tune_close_check(types.SimpleNamespace(rh_tune_file=tmp / "absent.json"), tc),
                "does not exist; tune's close check is required and is never deferred")
    two = {d: tc[d] for d in ("2023-12-27", "2023-12-28")} | {"2022-06-01": 4101.23}
    _expect_msg(lambda: tune_close_check(rh_file("rh2.json", two), tc), "2 overlapping day(s) (need >= 3)")
    off = {d: v for d, v in tc.items()} | {"2023-12-28": tc["2023-12-28"] + 0.02}
    _expect_msg(lambda: tune_close_check(rh_file("rh3.json", off), tc), "mismatches over 0.01")
    ok = {d: v for d, v in tc.items()} | {"2023-12-28": tc["2023-12-28"] + 0.005, "2021-03-01": 1.0}
    r = tune_close_check(rh_file("rh4.json", ok), tc)
    assert r["status"] == "checked" and r["overlap_days"] == 4 and r["robinhood_days"] == 5
    assert abs(r["max_abs_diff"] - 0.005) < 1e-6 and "4 tuning days" in r["text"]
    # the test-period Robinhood reader: a bar's date is checked before its close is converted; other instruments,
    # interpolated bars and other intervals are skipped; conflicts inside the window stop
    live = tmp / "spx" / "live_2026-10-21"
    live.mkdir(parents=True)
    doc = {"data": {"results": [
        {"instrument_id": "SPX-ID", "interval": "day", "bars": [
            {"begins_at": "2023-12-29T14:30:00Z", "close_value": "4769.83"},          # before TEST
            {"begins_at": "2025-06-02T13:30:00Z", "close_value": "5935.94"},
            {"begins_at": "2025-06-03T13:30:00Z", "close_value": "5970.37", "interpolated": True},
            {"begins_at": "2026-11-02T14:30:00Z", "close_value": "6800.00"}]},        # after TEST
        {"instrument_id": "OTHER", "interval": "day", "bars": [
            {"begins_at": "2025-06-02T13:30:00Z", "close_value": "591.00"}]},
        {"instrument_id": "SPX-ID", "interval": "5minute", "bars": [
            {"begins_at": "2025-06-02T19:55:00Z", "close_value": "5930.00"}]}]}}
    (live / "spx_daily.json").write_text(json.dumps(doc))
    with _FnumRecorder() as r:
        got = rh_closes_window([live / "spx_daily.json"], TEST, "SPX-ID")
    assert got == {"2025-06-02": (5935.94, "live_2026-10-21")}, got
    assert r.seen == ["5935.94"], r.seen
    with _FnumRecorder() as r:
        assert rh_closes_window([live / "spx_daily.json"], TUNE, "SPX-ID") == {"2023-12-29": (4769.83,
                                                                                               "live_2026-10-21")}
    assert r.seen == ["4769.83"]
    live2 = tmp / "spx" / "live_2026-10-22"
    live2.mkdir(parents=True)
    (live2 / "spx_daily.json").write_text(json.dumps({"data": {"results": [{"instrument_id": "SPX-ID", "bars": [
        {"begins_at": "2025-06-02T13:30:00Z", "close_value": "5936.94"}]}]}}))
    _expect_msg(lambda: rh_closes_window([live / "spx_daily.json", live2 / "spx_daily.json"], TEST, "SPX-ID"),
                "conflict")
    # fix 2: side-aware pricing and the contracts bought
    m = _needs_map([(10, 2, "up"), (10, 2), (3, 4, "dn")])
    assert m == {10: {2: {"up", "dn"}}, 3: {4: {"dn"}}}
    spots = {k: 5000.0 + 0.4 * i for i, k in enumerate(ENTRIES)}
    center = rp.atm_of(spots["15:51"])
    q, _ = rp.parse_quotes(_syn_quotes_text("2024-03-15", spots, center), "2024-03-15")
    i51, j10 = ENTRIES.index("15:51"), OFFSETS.index(10)
    one = price_day(q, 5012.0, {(i51, j10, "dn")})
    assert np.isfinite(one["dn"]).sum() == 1 and np.isfinite(one["dn"][i51, j10]) and np.isnan(one["up"]).all()
    assert np.isnan(one["ask_up"]).all() and np.isfinite(one["spot"]).sum() == 1
    sig = np.zeros((3, len(CANDLES), len(THRESHOLDS)))
    a50, b60 = CANDLES.index("15:50"), THRESHOLDS.index(0.60)
    a45, b70 = CANDLES.index("15:45"), THRESHOLDS.index(0.70)
    sig[0, a50, b60], sig[1, a45, b70], sig[2, a50, b60] = 1.0, -1.0, np.nan
    sig[2, a45, b70] = 1.0
    bc = bought_contracts(sig, [CURRENT, ("15:45", 0.70, -1, 0)])
    assert bc == [{(i51, j10, "up")}, {(ENTRIES.index("15:46"), OFFSETS.index(0), "up")},
                  {(ENTRIES.index("15:46"), OFFSETS.index(0), "dn")}], bc
    cnt = []
    cube = price_days(["2024-03-15", "2024-03-18"], {"2024-03-15": 5012.0, "2024-03-18": 5000.0},
                      lambda d: (cnt.append(d), (q, 0))[1], [{(i51, j10, "up")}, set()])
    assert cnt == ["2024-03-15"] and np.isnan(cube["up"][1]).all() and np.isnan(cube["spot"][1]).all()
    assert np.isfinite(cube["up"][0]).sum() == 1 and np.isnan(cube["dn"]).all()


def selftest_writers_lock(tmp: Path) -> None:
    """Fix 3+4 building blocks: atomic writes, the exclusive lock, the fsync'd run log."""
    d = tmp / "w"
    d.mkdir()
    f = d / "a.json"
    (d / ".a.json.tmp").write_text("left by a crash")
    atomic_write(f, "one\n")
    assert f.read_text() == "one\n" and not (d / ".a.json.tmp").exists()
    atomic_write(f, "two\n")
    assert f.read_text() == "two\n"
    g = d / "sel.json"
    atomic_write(g, "x\n", readonly=True, exclusive=True)
    assert g.read_text() == "x\n" and not (g.stat().st_mode & 0o222)
    _expect_exit(lambda: atomic_write(g, "y\n", readonly=True, exclusive=True), "exclusive overwrite",
                 (FileExistsError,))
    assert g.read_text() == "x\n"
    h = _Hook(crash_at=2)
    _expect_exit(lambda: _with_hook(h, lambda: atomic_write(d / "b.json", "b\n")), "hook", (SimulatedCrash,))
    assert not (d / "b.json").exists() and (d / ".b.json.tmp").exists() and h.steps[-1] == ("b.json", "tmp_written")
    atomic_write(d / "b.json", "b\n")
    assert (d / "b.json").read_text() == "b\n" and not (d / ".b.json.tmp").exists()
    env = types.SimpleNamespace(out_dir=d, lock_file=d / ".refine.lock", runs_dir=d / "runs")
    r1 = record_attempt(env, "tune", {"x": 1})
    record_attempt(env, "test", {})
    record_attempt(env, "tune", {})
    assert run_counts(env) == {"tune": 2, "test": 1}
    assert ATTEMPT_RE.match(r1.name) and json.loads(r1.read_text())["command"] == "tune"
    assert json.loads(r1.read_text())["x"] == 1 and not (r1.stat().st_mode & 0o222)
    # C: a leftover partial .tmp file and other stray files are ignored; a crash while an attempt record is being
    # written publishes nothing, leaves the counts unchanged and does not block the next record
    (env.runs_dir / ".20261109T000000.000000Z_tune_1.json.tmp").write_text('{"command": "tu')
    (env.runs_dir / "20261109T000000.000000Z_test_1.json.tmp").write_text("partial")
    (env.runs_dir / "notes.txt").write_text("x")
    assert run_counts(env) == {"tune": 2, "test": 1}
    for k in (1, 2):
        _expect_exit(lambda: _with_hook(_Hook(crash_at=k), lambda: record_attempt(env, "test", {})),
                     "attempt record crash", (SimulatedCrash,))
        assert run_counts(env) == {"tune": 2, "test": 1}
    assert len([f for f in env.runs_dir.iterdir() if f.name.endswith(".tmp")]) == 3     # one left by the crash
    record_attempt(env, "test", {})
    assert run_counts(env) == {"tune": 2, "test": 2}
    with run_lock(env, "tune"):
        assert env.lock_file.exists() and json.loads(env.lock_file.read_text())["command"] == "tune"
        _expect_msg(lambda: run_lock(env, "test").__enter__(), "delete it by hand")
    assert not env.lock_file.exists()
    try:
        with run_lock(env, "test"):
            raise SimulatedCrash("inside")
    except SimulatedCrash:
        pass
    assert not env.lock_file.exists()                                        # removed on any exit


def _close_line(path: Path, day: str, delta: float) -> None:
    lines = Path(path).read_text().splitlines()
    key = f"{day[5:7]}/{day[8:10]}/{day[:4]},"
    hit = [i for i, ln in enumerate(lines) if ln.startswith(key)]
    assert len(hit) == 1, day
    v = float(lines[hit[0]].split(",")[1])
    lines[hit[0]] = f"{key}{v + delta:.6f}"
    Path(path).write_text("\n".join(lines) + "\n")


def selftest_end_to_end(scan, tmp: Path) -> tuple:
    """tune -> selection files -> test on a synthetic world with a planted edge, then the no-pick path."""
    real = {n: (HERE / n).exists() for n in ("selection.json", "selection.sha256", "results.json", "runs",
                                             ".refine.lock", "tune_results.json", "inputs_tune.json",
                                             "inputs_test.json", "tune_complete.json", "RESULTS.md")}
    env = _syn_world(tmp / "A", scan, seed=31, per_half=200, n_test=160, plant=True)
    _write_forward_logs(env.forward_dir)
    assert str(env.out_dir).startswith(str(tmp)) and str(env.trades_csv).startswith(str(tmp))
    h_tune = _Hook()
    tr = _with_hook(h_tune, lambda: run_tune(env))
    sel = tr["selection"]
    # the output order: the attempt record first (C), the input manifest (A), selection.json, selection.sha256,
    # the other tuning artifacts, and tune_complete.json last (B)
    starts = [n for n, ph in h_tune.steps if ph == "start"]
    assert starts == ["runs/attempt", "inputs_tune.json", "selection.json", "selection.sha256", "tune_results.json",
                      "trades.csv", "RESULTS.md", "tune_complete.json"], starts
    recs = sorted(f for f in env.runs_dir.iterdir() if ATTEMPT_RE.match(f.name))
    log = [json.loads(f.read_text()) for f in recs]
    assert len(log) == 1 and log[0]["command"] == "tune" and log[0]["code_sha256"] == sha256_file(env.code_path)
    assert log[0]["prereg_sha256"] == sha256_file(env.prereg) and log[0]["inputs"]["quote_listing"]["files"] > 0
    assert log[0]["inputs"]["robinhood"][0]["bytes"] == env.rh_tune_file.stat().st_size
    assert not env.lock_file.exists()
    # A: the manifest of the tuning inputs, read-only, covering only the tuning window
    man = json.loads(env.inputs_tune.read_text())
    assert not (env.inputs_tune.stat().st_mode & 0o222) and man["step"] == "tune" and man["window"] == list(TUNE)
    assert man["quotes"]["files"] == len(man["quotes"]["per_file"]) > 0
    assert all(in_window(f[:10], TUNE) for f in man["quotes"]["per_file"])
    assert man["quotes"]["per_file"][sorted(man["quotes"]["per_file"])[0]] == sha256_file(
        env.quote_dir / sorted(man["quotes"]["per_file"])[0])
    n_rows = len([1 for ln in env.closes_csv.read_text().splitlines()[1:] if in_window(_csv_day(ln.split(",")[0]),
                                                                                       TUNE)])
    assert man["closes_rows"]["rows"] == n_rows and man["robinhood"] == {str(env.rh_tune_file):
                                                                            sha256_file(env.rh_tune_file)}
    assert man["panel"]["days"] == tr["data"]["d1_days"] and man["panel"]["last"] <= TUNE[1]
    assert man["panel"]["sha256"] == panel_digest(env.load_panel(*TUNE))["sha256"]      # what the loader returned
    env.panel_calls.pop()
    assert man["days_listing"]["rows"] == sum(1 for ln in env.days_file.read_text().splitlines()[1:]
                                              if in_window(ln[:10], TUNE))
    assert "post_check_ok" in [ev[0] for ev in env.events]
    assert set(man["code"]) == {str(Path(f).resolve()) for f in (__file__, REALPRICE_PY, rp.SCAN_PY, env.syn_dep)}
    assert ("manifest_written", "tune") in env.events
    # B: tune_complete.json, read-only, matches the artifacts
    tc = json.loads(env.tune_complete.read_text())
    assert not (env.tune_complete.stat().st_mode & 0o222) and tune_complete_mismatch(env) == []
    assert tc["inputs_manifest_sha256"] == sha256_file(env.inputs_tune)
    assert tc["artifacts"]["selection.json"] == sha256_file(env.selection_json) and None not in tc["artifacts"].values()
    # isolation: the tuning step never asked for, priced or kept a date after 2023-12-31
    assert env.panel_calls == [TUNE], env.panel_calls
    assert env.loader_calls and max(env.loader_calls) <= TUNE[1] and min(env.loader_calls) >= TUNE[0]
    assert tr["data"]["last"] <= TUNE[1] and sel["kept_days"] == tr["data"]["kept_days"]
    assert tr["data"]["no_expiry_days"] == 2 and len(tr["data"]["no_close_days"]) == 1
    # fix 5: the close check ran on the tuning range, before any selection
    cc = sel["close_check"]
    assert cc["status"] == "checked" and cc["overlap_days"] == 8 and cc["max_abs_diff"] == 0.0, cc
    assert tr["data"]["close_check"] == cc
    tcsv = _csv_rows(env.trades_csv)
    assert tcsv and all(r["date"] <= TUNE[1] and r["period"] == "tuning" for r in tcsv)
    assert {r["status"] for r in tcsv} <= {"priced", "no_spot", "no_quote"} and "priced" in {r["status"] for r in tcsv}
    # the planted edge is picked and goes to the test
    pk = sel["pick"]["cell"]
    assert pk[0] == "15:45" and pk[2] == 1 and 0.55 <= pk[1] <= 0.75, sel["pick"]
    assert sel["decision"] == "test" and sel["p"] <= NULL_ALPHA and sel["paired_tuning_difference"]["mean"] > 0
    assert sel["null"]["status"] == "run" and sel["null"]["n_shifts"] > 0
    assert sel["tuning_stats"]["pick"]["tuning"]["coverage"] >= 0.95
    assert tr["part3_tuning"]["top15"][0]["cell"] == sel["pick"]["name"]
    assert sel["code_sha256"] == sha256_file(Path(__file__).resolve()) and len(sel["prereg_sha256"]) == 64
    assert "written_utc" not in sel                                            # deterministic content
    assert sel["inputs_manifest_sha256"] == sha256_file(env.inputs_tune)
    # selection files: read-only, hash matches, never overwritten
    for f in (env.selection_json, env.selection_sha):
        assert not (f.stat().st_mode & 0o222), f
    assert env.selection_sha.read_text().split()[0] == sha256_file(env.selection_json)
    _expect_msg(lambda: run_tune(env), "already done")
    assert run_counts(env) == {"tune": 1, "test": 0}                          # refused before the log line
    md = env.results_md.read_text()
    assert "## Part 1: tuning" in md and "Part 2" not in md and "not fresh for the current rule's" in md
    assert "Runs started (attempt records in runs/): tune 1, test 0" in md
    assert "checked against Robinhood (robinhood_spx_daily_2021_2023.json) on 8 overlapping tuning days, largest " \
           "difference 0.0000" in md
    fam = jsonable(tr)                                                         # the family wording, rendered
    dfam = decide(("15:50", 0.60, 1, 20), 0.01, 3.0)
    fam["selection"].update(decision=dfam["decision"], decision_text=dfam["text"], goes_to_test=False,
                            failed_gates=dfam["failed_gates"], gates=dfam["gates"])
    mdf = render_md(fam, None)
    assert FAMILY_TEXT in mdf and NO_ADVANCE in mdf and "no runner-up is substituted" in mdf
    assert f"{NO_ADVANCE} (failed gate: {GATE_TEXT['not_in_current_family']})" in mdf
    # test
    env.events.clear()
    env.loader_calls.clear()
    env.priced = []
    h_test = _Hook()
    res = _with_hook(h_test, lambda: run_test(env))
    starts = [n for n, ph in h_test.steps if ph == "start"]
    assert starts == ["runs/attempt", "inputs_test.json", "results.json", "results.json", "trades.csv",
                      "RESULTS.md"], starts
    mt = json.loads(env.inputs_test.read_text())
    assert not (env.inputs_test.stat().st_mode & 0o222) and mt["step"] == "test" and mt["window"] == list(TEST)
    assert mt["quotes"]["files"] > 0 and all(in_window(f[:10], TEST) for f in mt["quotes"]["per_file"])
    assert list(mt["robinhood"]) == [str(f) for f in env.rh_test_files()]
    assert mt["selection_json_sha256"] == sha256_file(env.selection_json)
    assert mt["tune_complete_sha256"] == sha256_file(env.tune_complete)
    assert env.panel_calls[-1] == TEST and min(env.loader_calls) >= TEST[0] and max(env.loader_calls) <= TEST[1]
    pick = tuple(pk)
    kinds = [e[0] if e[0] != "price" else ("price", e[1], e[2]) for e in env.events]
    assert kinds == ["manifest_written", ("price", "test", "per_day"), "post_check_ok", "decision_written",
                     "part3_start", ("price", "test_profile", frozenset({(10, 2), (10, 4)})), "post_check_ok"], kinds
    # fix 2: before the decision, only the contracts bought by the pick and the current rule were priced, per day;
    # recomputed here independently from the full signal tensor of the synthetic panel
    P = env.load_panel(*TEST)
    days = [str(d) for d in P.dates]
    keep, _ = kept_days(days, load_closes(env.closes_csv, TEST), quote_listing(env.quote_dir))
    rows = [days.index(d) for d in keep]
    full = signals(P, rows, scan)
    want = {}
    for i, d in enumerate(keep):
        sday = set()
        for c in (pick, CURRENT):
            a, b, di, j = idx_of(c)
            x = full[i, a, b] * DIRECTIONS[di]
            if np.isfinite(x) and x != 0:
                sday.add((a, j, "up" if x > 0 else "dn"))
        if sday:
            want[d] = frozenset(sday)
    got = {d: nd for tag, d, nd in env.priced if tag == "test"}
    assert got == want and len([1 for tag, *_ in env.priced if tag == "test"]) == len(want)
    assert 0 < len(want) < len(keep)                                           # no-signal days were never loaded
    assert all(len(v) <= 2 for v in want.values())                             # one side per rule, never both
    assert res["part2"]["run"] and res["part2"]["outcome"] == "adopt", res["part2"]
    inp = res["part2"]["inputs"]
    assert inp["inputs_manifest_sha256"] == sha256_file(env.inputs_test)
    assert inp["selection_sha256"] == sha256_file(env.selection_json) and inp["code_sha256"] == sel["code_sha256"]
    assert inp["test_quote_listing"]["files"] > 0 and len(inp["closes_window_sha256"]) == 64
    assert res["data"]["close_check"]["overlap_days"] == 6 and res["data"]["last"] <= TEST[1]
    assert res["forward"]["pick"]["available"] is False and res["forward"]["current"]["days"] == 2
    assert {r["label"] for r in res["forward"]["current"]["rows"]} == {"previously available"}
    back = json.loads(env.results_json.read_text())
    assert back["stage"] == "complete" and back["part2"]["outcome"] == "adopt" and back["decision_written_utc"]
    assert set(back["part3_test"]["configs"]) == {"pick", "current"}
    v = back["part3_test"]["configs"]["current"]["versions"]["2024-01-01..2026-10-20"]
    base, high, mid = v["ask_fee_0.09"], v["ask_fee_0.74"], v["mid_fee_0.09"]
    assert base["trades"] == high["trades"] == mid["trades"] > 0
    assert abs(high["mean_per_trade"] - (base["mean_per_trade"] - 0.65)) < 1e-9
    assert abs(mid["mean_per_trade"] - (base["mean_per_trade"] + 10.0)) < 1e-6
    assert set(back["part3_test"]["configs"]["pick"]["versions"]) == {"2024-01-01..2026-10-20", "2024", "2025", "2026"}
    rows = _csv_rows(env.trades_csv)
    assert {r["period"] for r in rows} == {"tuning", "test"} and {r["config"] for r in rows} == {"pick", "current"}
    assert [r for r in rows if r["period"] == "tuning"] == tcsv
    assert all(r["date"] >= TEST[0] for r in rows if r["period"] == "test")
    md = env.results_md.read_text()
    for s in ("## Part 1: tuning", "## Part 2: the test", "Adopt the pick", "looked at after the decision",
              "## Days after 2026-10-20", "| ask, $0.74 |", "| mid, $0.09 |", "(current)", "a mid limit does not "
              "capture the mid", "Nothing here is a trading recommendation", "not available",
              "Runs started (attempt records in runs/): tune 1, test 1"):
        assert s in md, s
    _expect_msg(lambda: run_test(env), "already done")
    _expect_msg(lambda: run_tune(env), "test has run")
    assert tune_complete_mismatch(env) == []           # B: test rewrote the trades CSV and RESULTS.md; tuning parts kept
    assert run_counts(env) == {"tune": 1, "test": 1} and not env.lock_file.exists()
    # a tampered selection.json is refused (copy the outputs, edit one byte)
    env2 = _env_copy(env, tmp / "A" / "out_tampered")
    shutil.rmtree(env2.out_dir)
    shutil.copytree(env.out_dir, env2.out_dir)
    (env2.out_dir / "results.json").unlink()
    os.chmod(env2.selection_json, 0o644)
    env2.selection_json.write_text(env2.selection_json.read_text().replace('"p":', '"p" :', 1))
    _expect_msg(lambda: run_test(env2), "does not match selection.sha256")
    _expect_msg(lambda: run_tune(env2), "does not match selection.sha256")
    env2.selection_sha.unlink()
    _expect_msg(lambda: run_test(env2), "not found (run tune first)")
    # the plan's gate: a ledger without the hash refuses both steps
    env3 = _env_copy(env, tmp / "A" / "out3", ledger=tmp / "A" / "empty_ledger.md")
    env3.ledger.write_text("nothing\n")
    _expect_exit(lambda: run_tune(env3), "tune without the ledger hash")
    assert run_counts(env3) == {"tune": 0, "test": 0}
    # fix 6: no-pick path; the null is not run at all (null_best patched to fail if called)
    envB = _syn_world(tmp / "B", scan, seed=32, per_half=60, n_test=50, plant=False)
    g = globals()
    orig = g["null_best"]

    def boom(*a, **k):
        raise AssertionError("null_best called although no cell is eligible")

    g["null_best"] = boom
    try:
        trB = run_tune(envB)
    finally:
        g["null_best"] = orig
    sB = trB["selection"]
    assert sB["decision"] == "no_pick" and sB["pick"] is None and sB["p"] is None
    assert sB["null"] == {"status": NULL_NOT_RUN} and trB["part3_tuning"]["n_eligible"] == 0
    assert "Luck diagnostic: not run (no eligible cell)." in envB.results_md.read_text()
    envB.events.clear()
    envB.priced = []
    resB = run_test(envB)
    kinds = [e[0] for e in envB.events]
    assert kinds == ["manifest_written", "post_check_ok", "decision_written", "price", "part3_start", "price",
                     "post_check_ok"], kinds
    assert envB.events[3][2] == "per_day" and resB["part2"]["run"] is False
    a, b, di, j = idx_of(CURRENT)
    assert envB.priced and all(tag != "test" or nd in (frozenset({(a, j, "up")}), frozenset({(a, j, "dn")}))
                               for tag, _, nd in envB.priced)
    assert resB["part2"]["inputs"]["closes_window_sha256"] is None
    assert resB["forward"]["current"] == {"available": False,
                                          "reason": f"no forward strike log at {envB.forward_dir}/strikes_forward_log.csv"}
    mdB = envB.results_md.read_text()
    assert "Part 2 was not run" in mdB and NO_ADVANCE in mdB and "does not show that the current rule is the best" in mdB
    assert set(json.loads(envB.results_json.read_text())["part3_test"]["configs"]) == {"current"}
    assert {n: (HERE / n).exists() for n in real} == real, "selftest touched the real output files"
    return env, h_tune.steps, h_test.steps, res


def selftest_close_check_stops(env: Env, tmp: Path) -> None:
    """Fix 5 end to end: tune stops before any selection (and before any quote or panel read) when the Robinhood
    2021-2023 file is missing, holds a later date, overlaps on fewer than 3 days or disagrees by more than 0.01."""
    tmp.mkdir(parents=True, exist_ok=True)
    good = json.loads(env.rh_tune_file.read_text())
    days = env.rh_tune_days
    variants = {
        "missing": (None, "does not exist"),
        "later": (dict(good, closes=dict(good["closes"], **{"2024-01-02": 4742.83})), "outside 2021-01-01..2023-12-31"),
        "few": (dict(good, closes={d: good["closes"][d] for d in days[:2]}), "2 overlapping day(s) (need >= 3)"),
        "off": (dict(good, closes=dict(good["closes"], **{days[3]: good["closes"][days[3]] + 0.011})),
                "mismatches over 0.01")}
    for name, (doc, msg) in variants.items():
        f = tmp / f"rh_{name}.json"
        if doc is not None:
            f.write_text(json.dumps(doc))
        e = _env_copy(env, tmp / f"out_cc_{name}", rh_tune_file=f)
        ex = _expect_msg(lambda: run_tune(e), msg)
        assert "stopping before any selection" in str(ex)
        assert not e.selection_json.exists() and not e.selection_sha.exists() and not e.tune_json.exists()
        assert e.loader_calls == [] and e.panel_calls == [TUNE] and not e.lock_file.exists()
        assert run_counts(e) == {"tune": 1, "test": 0}                          # logged before any input was read


def _plant_bogus_tmps(out_dir: Path) -> list:
    """Overwrite every temp file a crash left with a bogus outcome; a rerun must never use one."""
    out = []
    for f in Path(out_dir).iterdir():
        if f.name.endswith(".tmp") and f.is_file():
            os.chmod(f, 0o644)
            f.write_text('{"decision": "test", "outcome": "adopt", "bogus": true}\n')
            out.append(f.name)
    return out


def _tune_outputs_copy(src: Env, dst: Env) -> Env:
    """dst gets src's finished tuning outputs (as a test step would find them)."""
    for n in ("selection.json", "selection.sha256", "tune_results.json", "inputs_tune.json", "tune_complete.json",
              "RESULTS.md"):
        shutil.copy2(src.out_dir / n, dst.out_dir / n)
    dst.runs_dir.mkdir()
    for f in src.runs_dir.iterdir():
        if ATTEMPT_RE.match(f.name) and "_tune_" in f.name:
            shutil.copy2(f, dst.runs_dir / f.name)
    dst.trades_csv.write_text(trades_text(_csv_rows(src.trades_csv, "tuning")))
    md = render_md(json.loads(dst.tune_json.read_text()), None, run_counts(dst))
    old = (src.out_dir / "RESULTS.md").read_text()
    assert md_section(md, TUNE_MD_MARK) == md_section(old, TUNE_MD_MARK)
    dst.results_md.write_text(md)
    return dst


def _probe_once(step: str, stage: str, fn):
    """A selftest probe that runs `fn` once, at the given step and stage of a run."""
    done: list = []

    def probe(s, st):
        if (s, st) == (step, stage) and not done:
            done.append(1)
            fn()
    return probe


def _regzip(f: Path) -> None:
    """Rewrite a quote file with the same rows but a different gzip header (different bytes)."""
    f.write_bytes(gzip.compress(gzip.decompress(f.read_bytes()), mtime=12345))


def _nudge_panel(f: Path, day_from: str = TUNE[0]) -> None:
    """Change the 10:00 bar (no candle used by the grid) of the first panel day on or after `day_from`."""
    with np.load(f, allow_pickle=False) as z:
        arrs = {k: z[k].copy() for k in z.files}
    i = int(np.argmax(arrs["dates"] >= day_from))
    arrs["O"][i, 30] += 0.25
    with open(f, "wb") as fh:
        np.savez(fh, **arrs)


def selftest_recovery(env: Env, tune_steps: list, test_steps: list, res_ref: dict, tmp: Path) -> None:
    """A, B, C on full runs: crashes at every write step, crashes after computing but before publishing followed by a
    changed (or unchanged) input, the tune_complete.json gate, and the attempt records."""
    tmp.mkdir(parents=True, exist_ok=True)
    ref_sel, ref_complete = env.selection_json.read_bytes(), env.tune_complete.read_bytes()
    ref_tr = json.loads(env.tune_json.read_text())
    k_tune_pub = tune_steps.index(("selection.json", "start")) + 1   # everything computed, nothing published yet
    k_test_pub = test_steps.index(("results.json", "start")) + 1     # the decision computed, not yet written
    assert tune_steps[:4] == [("runs/attempt", "start"), ("runs/attempt", "tmp_written"),
                              ("inputs_tune.json", "start"), ("inputs_tune.json", "tmp_written")]

    # ---- tune: a crash at every write step; the rerun (under the frozen manifest) gives the same selection,
    # tune_complete.json, tune_results.json and trade rows; test refuses until tune_complete.json exists
    bogus: list = []
    for k in range(1, len(tune_steps) + 1):
        e = _env_copy(env, tmp / f"tune_k{k}")
        _expect_exit(lambda: _with_hook(_Hook(crash_at=k), lambda: run_tune(e)), f"tune crash {k}", (SimulatedCrash,))
        assert not e.lock_file.exists() and not e.tune_complete.exists()
        _expect_msg(lambda: run_test(e), "not found")                          # B: no tune_complete.json yet
        before = e.selection_json.read_bytes() if e.selection_json.exists() else None
        had_manifest = e.inputs_tune.exists()
        assert before in (None, ref_sel)
        bogus += _plant_bogus_tmps(e.out_dir)
        e.events.clear()
        run_tune(e)
        assert e.selection_json.read_bytes() == ref_sel and e.tune_complete.read_bytes() == ref_complete, k
        assert e.selection_sha.read_text().split()[0] == sha256_file(e.selection_json)
        assert json.loads(e.tune_json.read_text()) == ref_tr
        assert _csv_rows(e.trades_csv) == _csv_rows(env.trades_csv, "tuning")
        assert (("selection_matched",) in e.events) == (before is not None), k
        assert (("manifest_matched", "tune") in e.events) == had_manifest, k
        n_runs = 1 if k <= 2 else 2                                            # k = 1, 2: the record never published
        assert run_counts(e) == {"tune": n_runs, "test": 0}, (k, run_counts(e))
        assert f"Runs started (attempt records in runs/): tune {n_runs}, test 0" in e.results_md.read_text()
        assert not [p for p in e.out_dir.iterdir() if p.name.endswith(".tmp")]
        _expect_msg(lambda: run_tune(e), "already done")
    assert {".selection.json.tmp", ".selection.sha256.tmp", ".tune_results.json.tmp", ".trades.csv.tmp",
            ".RESULTS.md.tmp", ".tune_complete.json.tmp", ".inputs_tune.json.tmp"} <= set(bogus), bogus
    # a published artifact that does not match the recompute (here: edited by hand after a crash) is not overwritten
    k_sel = tune_steps.index(("selection.sha256", "start")) + 1               # selection.json published, sha not
    e = _env_copy(env, tmp / "tune_sel_differs")
    _expect_exit(lambda: _with_hook(_Hook(crash_at=k_sel), lambda: run_tune(e)), "tune crash", (SimulatedCrash,))
    os.chmod(e.selection_json, 0o644)
    e.selection_json.write_text(e.selection_json.read_text().replace('"p":', '"p" :', 1))
    edited = e.selection_json.read_bytes()
    _expect_msg(lambda: run_tune(e), "selection differs; not overwriting")
    assert e.selection_json.read_bytes() == edited and not e.selection_sha.exists() and not e.tune_complete.exists()

    # ---- A on tune: crash after computing, before publishing; then a changed input -> refuse before computing;
    # the same input restored -> the identical outcome
    iso = _isolated_world(env, tmp / "iso")
    iso_ref = _env_copy(iso, tmp / "iso_ref")
    run_tune(iso_ref)
    iso_sel = iso_ref.selection_json.read_bytes()
    tune_day = next(d for d in (r["date"] for r in _csv_rows(iso_ref.trades_csv, "tuning"))
                    if d not in env.rh_tune_days)
    tq = iso.quote_dir / f"{tune_day}.csv.gz"
    rh_doc = json.loads(iso.rh_tune_file.read_text())

    def edit_days_row(day):
        iso.days_file.write_text(iso.days_file.read_text().replace(f"{day},nyse,True", f"{day},nyse,True ", 1))

    changes = {"closes_rows": (iso.closes_csv, lambda: _close_line(iso.closes_csv, tune_day, 30.0)),
               "quotes": (tq, lambda: _regzip(tq)),
               "panel": (iso.syn_npz, lambda: _nudge_panel(iso.syn_npz)),
               "days_listing": (iso.days_file, lambda: edit_days_row(tune_day)),
               "code": (iso.syn_dep, lambda: iso.syn_dep.write_text(iso.syn_dep.read_text() + "# edited\n")),
               "robinhood": (iso.rh_tune_file, lambda: iso.rh_tune_file.write_text(json.dumps(rh_doc, indent=2)))}
    for name, (f, change) in changes.items():
        saved = f.read_bytes()
        e = _env_copy(iso, tmp / f"tune_changed_{name}")
        _expect_exit(lambda: _with_hook(_Hook(crash_at=k_tune_pub), lambda: run_tune(e)), "crash", (SimulatedCrash,))
        assert e.inputs_tune.exists() and not e.selection_json.exists() and e.loader_calls   # it had computed
        change()
        e.loader_calls.clear()
        e.panel_calls.clear()
        ex = _expect_msg(lambda: run_tune(e), "inputs or code changed since the first attempt; not recomputing")
        assert f"differs in: {name}." in str(ex), str(ex)
        assert e.loader_calls == [] and e.panel_calls == [TUNE] and not e.selection_json.exists()
        f.write_bytes(saved)                                                   # the same input again
        run_tune(e)
        assert e.selection_json.read_bytes() == iso_sel and tune_complete_mismatch(e) == []
        assert run_counts(e) == {"tune": 3, "test": 0}                          # three attempts, all recorded
    # A2: no whole-file D1 hash: a changed test-period bar in the panel file and a day-listing row appended after
    # the window do not block a tune retry (the loader never returns them), and the outcome is identical
    e = _env_copy(iso, tmp / "tune_outside")
    _expect_exit(lambda: _with_hook(_Hook(crash_at=k_tune_pub), lambda: run_tune(e)), "crash", (SimulatedCrash,))
    saved_npz, saved_days = iso.syn_npz.read_bytes(), iso.days_file.read_bytes()
    _nudge_panel(iso.syn_npz, TEST[0])
    with open(iso.days_file, "a") as fh:
        fh.write("2026-11-02,nyse,True\n")
    run_tune(e)
    assert e.selection_json.read_bytes() == iso_sel and ("manifest_matched", "tune") in e.events
    iso.syn_npz.write_bytes(saved_npz)
    iso.days_file.write_bytes(saved_days)
    # A1: check after use. An in-window input that changes after the manifest check (here: right after it, or
    # after all computing) makes the run refuse and publish nothing; with the input restored, a rerun publishes the
    # reference outcome
    for stage, (name, f, change) in (("frozen", ("closes_rows", iso.closes_csv,
                                                 lambda: _close_line(iso.closes_csv, tune_day, 30.0))),
                                     ("computed", ("quotes", tq, lambda: _regzip(tq)))):
        saved = f.read_bytes()
        e = _env_copy(iso, tmp / f"tune_during_{stage}")
        e.probe = _probe_once("tune", stage, change)
        ex = _expect_msg(lambda: run_tune(e), "inputs changed during the run; not publishing")
        assert f"in: {name}." in str(ex) and e.loader_calls                     # it had computed
        assert not [n for n in ("selection.json", "selection.sha256", "tune_results.json", "trades.csv",
                                "RESULTS.md", "tune_complete.json") if (e.out_dir / n).exists()]
        assert e.inputs_tune.exists() and not e.lock_file.exists()
        f.write_bytes(saved)
        e.probe = None
        run_tune(e)
        assert e.selection_json.read_bytes() == iso_sel and tune_complete_mismatch(e) == []

    # ---- B: test refuses, before reading any test-period input, without or with a mismatching tune_complete.json
    def tampered(name, edit, msg):
        e = _env_copy(env, tmp / f"b_{name}")
        _tune_outputs_copy(env, e)
        edit(e)
        e.loader_calls.clear()
        e.panel_calls.clear()
        _expect_msg(lambda: run_test(e), msg)
        assert e.loader_calls == [] and e.panel_calls == [] and run_counts(e)["test"] == 0
        assert not e.inputs_test.exists() and not e.results_json.exists()
        return e

    def edit_ro(f: Path, fn):
        os.chmod(f, 0o644)
        f.write_text(fn(f.read_text()))

    tampered("missing", lambda e: e.tune_complete.unlink(), "tune_complete.json not found")
    tampered("marker", lambda e: edit_ro(e.tune_complete, lambda t: t.replace(
        json.loads(t)["artifacts"]["tune_results.json"], "0" * 64)), "does not match the tuning artifacts "
             "(tune_results.json)")
    tampered("tune_results", lambda e: e.tune_json.write_text(e.tune_json.read_text() + " "), "(tune_results.json)")
    tampered("inputs_tune", lambda e: edit_ro(e.inputs_tune, lambda t: t + " "), "(inputs_tune.json)")
    tampered("trade_rows", lambda e: e.trades_csv.write_text(e.trades_csv.read_text().replace(",priced", ",no_quote", 1)),
             "(tuning trade rows)")
    tampered("results_md", lambda e: e.results_md.write_text(e.results_md.read_text().replace("Pick:", "Pick :", 1)),
             "(RESULTS.md tuning section)")
    e = _env_copy(env, tmp / "b_outside_section")                               # outside the tuning section: fine
    _tune_outputs_copy(env, e)
    e.results_md.write_text(e.results_md.read_text().replace("## Caveats", "## Caveats\n\n(edited)", 1))
    assert verify_tune_complete(e, "check") == sha256_file(e.tune_complete)
    e = _env_copy(env, tmp / "b_tune_refuses")                                  # tune refuses too
    _tune_outputs_copy(env, e)
    e.tune_json.write_text(e.tune_json.read_text() + " ")
    _expect_msg(lambda: run_tune(e), "tune_complete.json does not match the tuning artifacts (tune_results.json)")

    # ---- test: a crash at every write step; the rerun recomputes and gives the identical decision block
    ref_p2 = dumps(res_ref["part2"])
    bogus = []
    for k in range(1, len(test_steps) + 1):
        e = _tune_outputs_copy(env, _env_copy(env, tmp / f"test_k{k}"))
        _expect_exit(lambda: _with_hook(_Hook(crash_at=k), lambda: run_test(e)), f"test crash {k}", (SimulatedCrash,))
        assert not e.lock_file.exists()
        had = e.results_json.exists()
        had_manifest = e.inputs_test.exists()
        if had:
            assert dumps(json.loads(e.results_json.read_text())["part2"]) == ref_p2
        bogus += _plant_bogus_tmps(e.out_dir)
        e.events.clear()
        r = run_test(e)
        assert dumps(r["part2"]) == ref_p2 and dumps(json.loads(e.results_json.read_text())["part2"]) == ref_p2, k
        assert (("decision_matched",) in e.events) == had and (("decision_written",) in e.events) == (not had)
        assert (("manifest_matched", "test") in e.events) == had_manifest
        assert any(ev[0] == "price" and ev[1] == "test" for ev in e.events)    # recomputed, never read back
        back = json.loads(e.results_json.read_text())
        assert back["stage"] == "complete" and set(back["part3_test"]["configs"]) == {"pick", "current"}
        assert _csv_rows(e.trades_csv) == _csv_rows(env.trades_csv)
        n_runs = 1 if k <= 2 else 2
        assert f"Runs started (attempt records in runs/): tune 1, test {n_runs}" in e.results_md.read_text()
        assert not [p for p in e.out_dir.iterdir() if p.name.endswith(".tmp")]
        assert tune_complete_mismatch(e) == []
        _expect_msg(lambda: run_test(e), "already done")
    assert {".results.json.tmp", ".inputs_test.json.tmp", ".trades.csv.tmp", ".RESULTS.md.tmp"} <= set(bogus), bogus
    # a decision already written that the recompute does not reproduce (edited by hand) is not overwritten
    k_dec = test_steps.index(("results.json", "tmp_written")) + 2              # crash right after the decision
    e = _tune_outputs_copy(env, _env_copy(env, tmp / "test_dec_differs"))
    _expect_exit(lambda: _with_hook(_Hook(crash_at=k_dec), lambda: run_test(e)), "test crash", (SimulatedCrash,))
    doc = json.loads(e.results_json.read_text())
    assert doc["stage"].startswith("decision written")
    doc["part2"]["a_works"]["mean_per_day"] += 1.0
    e.results_json.write_text(dumps(doc))
    edited = e.results_json.read_bytes()
    _expect_msg(lambda: run_test(e), "decision differs; not overwriting")
    assert e.results_json.read_bytes() == edited

    # ---- A on test: crash after computing, before publishing; a changed input -> refuse before computing; the same
    # input restored -> the identical decision. A change outside the frozen inputs does not matter.
    iso_t = _tune_outputs_copy(iso_ref, _env_copy(iso, tmp / "iso_test_ref"))
    iso_p2 = dumps(run_test(iso_t)["part2"])
    test_day = next(d for d in (r["date"] for r in _csv_rows(iso_t.trades_csv, "test")) if d not in env.rh_test_days)
    xq = iso.quote_dir / f"{test_day}.csv.gz"
    live = iso.rh_test_files()[0]
    changes = {"closes_rows": (iso.closes_csv, lambda: _close_line(iso.closes_csv, test_day, 30.0)),
               "quotes": (xq, lambda: _regzip(xq)),
               "robinhood": (live, lambda: live.write_text(live.read_text() + " ")),
               "code": (iso.syn_dep, lambda: iso.syn_dep.write_text(iso.syn_dep.read_text() + "# edited\n"))}
    for name, (f, change) in changes.items():
        saved = f.read_bytes()
        e = _tune_outputs_copy(iso_ref, _env_copy(iso, tmp / f"test_changed_{name}"))
        _expect_exit(lambda: _with_hook(_Hook(crash_at=k_test_pub), lambda: run_test(e)), "crash", (SimulatedCrash,))
        assert e.inputs_test.exists() and not e.results_json.exists() and e.loader_calls
        change()
        e.loader_calls.clear()
        e.panel_calls.clear()
        ex = _expect_msg(lambda: run_test(e), "inputs or code changed since the first attempt; not recomputing")
        assert f"differs in: {name}." in str(ex), str(ex)
        assert e.loader_calls == [] and e.panel_calls == [TEST] and not e.results_json.exists()
        f.write_bytes(saved)
        assert dumps(run_test(e)["part2"]) == iso_p2
    # A1 on test: an input changed after the manifest check refuses before the decision (nothing published), or
    # after the decision but before the Part 3 outputs (the decision stays; Part 3 is not published); restored, a
    # rerun publishes the reference decision and completes
    for stage, (name, f, change) in (("frozen", ("closes_rows", iso.closes_csv,
                                                 lambda: _close_line(iso.closes_csv, test_day, 30.0))),
                                     ("computed", ("robinhood", live, lambda: live.write_text(live.read_text() + " "))),
                                     ("part3", ("quotes", xq, lambda: _regzip(xq)))):
        saved = f.read_bytes()
        e = _tune_outputs_copy(iso_ref, _env_copy(iso, tmp / f"test_during_{stage}"))
        e.probe = _probe_once("test", stage, change)
        ex = _expect_msg(lambda: run_test(e), "inputs changed during the run; not publishing")
        assert f"in: {name}." in str(ex) and e.loader_calls and not e.lock_file.exists()
        if stage == "part3":
            back = json.loads(e.results_json.read_text())
            assert back["stage"].startswith("decision written") and dumps(back["part2"]) == iso_p2
        else:
            assert not e.results_json.exists()
        assert not read_trade_rows(e.trades_csv, "test") and TEST_MD_MARK not in e.results_md.read_text()
        f.write_bytes(saved)
        e.probe = None
        e.events.clear()
        r = run_test(e)
        assert dumps(r["part2"]) == iso_p2 and json.loads(e.results_json.read_text())["stage"] == "complete"
        assert (("decision_matched",) in e.events) == (stage == "part3")
    # outside the frozen inputs: a close row after 2026-10-20 and a new live_* folder do not block a retry
    e = _tune_outputs_copy(iso_ref, _env_copy(iso, tmp / "test_outside"))
    _expect_exit(lambda: _with_hook(_Hook(crash_at=k_test_pub), lambda: run_test(e)), "crash", (SimulatedCrash,))
    saved = iso.closes_csv.read_bytes()
    with open(iso.closes_csv, "a") as fh:
        fh.write("11/02/2026,6800.000000\n")
    extra = live.parent.parent / "live_2026-11-03"
    extra.mkdir()
    (extra / "spx_daily.json").write_text(json.dumps({"data": {"results": [{"instrument_id": "SYN-SPX", "bars": [
        {"begins_at": f"{env.rh_test_days[0]}T13:30:00Z", "close_value": "1.0"}]}]}}))     # would fail the check
    assert len(iso.rh_test_files()) == 2
    assert dumps(run_test(e)["part2"]) == iso_p2 and ("manifest_matched", "test") in e.events
    iso.closes_csv.write_bytes(saved)
    shutil.rmtree(extra)


def selftest_forward(tmp: Path) -> None:
    fdir = tmp / "fwd"
    fdir.mkdir()
    _write_forward_logs(fdir)
    f = forward_days(fdir, "2026-10-21", ("15:50", 0.80, 1, 20))
    cur = f["current"]
    assert [r["date"] for r in cur["rows"]] == ["2026-10-21", "2026-10-22"] and cur["traded"] == 1
    assert cur["rows"][0]["label"] == "previously available" and cur["rows"][1]["label"] == "fresh"
    assert abs(cur["mean_pnl_traded"] - 289.91) < 1e-9
    pk = f["pick"]
    assert [(r["date"], r["status"]) for r in pk["rows"]] == [("2026-10-21", "traded"),
                                                              ("2026-10-23", "direction_mismatch"),
                                                              ("2026-10-26", "not_logged")], pk["rows"]
    assert forward_days(fdir, "2026-10-21", ("15:49", 0.60, 1, 10))["pick"]["available"] is False
    assert forward_days(fdir, "2026-10-21", ("15:50", 0.60, -1, 10))["pick"]["available"] is False
    assert forward_days(fdir, "2026-10-21", None)["pick"] is None
    assert forward_days(fdir, "2026-10-20", CURRENT)["pick"]["rows"][0]["label"] == "fresh"


def selftest() -> None:
    scan = rp.load_module("spx_candle_scan_ro", rp.SCAN_PY)
    assert label(20) == "ITM20" and label(0) == "ATM" and label(-5) == "OTM5"
    assert cell_name(CURRENT) == "15:50 body>=0.60 with ITM10" and distance_to_current(idx_of(CURRENT)) == 0
    assert distance_to_current(idx_of(("15:40", 0.40, -1, -20))) == 10 + 4 + 1 + 6
    assert in_current_family(("15:50", 0.6, 1, -20)) and not in_current_family(("15:50", 0.65, 1, 10))
    assert [n for n, _ in HALVES] == ["H1", "H2"] and HALVES[0][1][1] == "2022-09-30"
    selftest_grid_brute(scan)
    selftest_plateau_eligibility_pick()
    selftest_null()
    selftest_decisions()
    selftest_pricing()
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        selftest_isolation_units(tmp)
        selftest_writers_lock(tmp)
        selftest_forward(tmp)
        env, tune_steps, test_steps, res = selftest_end_to_end(scan, tmp)
        selftest_close_check_stops(env, tmp / "cc")
        selftest_recovery(env, tune_steps, test_steps, res, tmp / "recovery")
        for p in tmp.rglob("*"):                                             # let the temp folder be removed
            if p.is_file() or p.is_dir():
                os.chmod(p, 0o755 if p.is_dir() else 0o644)
    print("selftest: all checks passed")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "tune":
        r = run_tune(default_env())
        print(f"tune: {r['selection']['decision_text']}")
        print(f"wrote {HERE / 'selection.json'}, selection.sha256, tune_results.json, RESULTS.md and {OUT_TRADES}")
    elif cmd == "test":
        r = run_test(default_env())
        p2 = r["part2"]
        print(f"test: {p2['text']}")
        print(f"wrote {HERE / 'results.json'}, RESULTS.md and {OUT_TRADES}")
    else:
        raise SystemExit("usage: refine.py selftest | tune | test")
