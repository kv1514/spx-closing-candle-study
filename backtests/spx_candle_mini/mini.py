"""The 15:50 candle on cheaper contracts: XSP and SPY 0DTE options at real prices (2021-01-01 .. 2026-10-20).

Pre-registration: preregistration/spx_candle_mini.md (locked; its SHA-256 is in preregistration/LEDGER.md). It is the
specification; this file implements it and makes no choice of its own except where noted under IMPLEMENTATION NOTES.
`run` refuses to read any option price (XSP or SPY quote file, XSP trade-bar file, or the SPX real-price trade list)
unless that file exists and its SHA-256 is in the ledger.

  XSP, the one primary test. On every XSP-sample day, the D1 15:50 candle's strong-body signal (F2); an up signal
      buys the call at ATM - 1, a down signal the put at ATM + 1 (ATM = floor(implied XSP spot + 0.5), the implied
      spot from the 15:51:00 quotes by realprice.implied_spot), at the 15:51 ask, held to X = official SPX close / 10,
      $0.09 fee. Confirmed only if the per-day series has mean > 0 with Newey-West t >= 2.0 (lag 5).
  SPY, the secondary test (its own verdict line). The same strike rule on SPY's 15:51:00 quotes; version (b) buys at
      the 15:51 ask and sells at the 15:59 bid, $0.09 on each side, and carries SPY's verdict (same bar). Version (a),
      descriptive: valued at intrinsic on Yahoo's unadjusted SPY close, $0.09 once.
  Descriptive, deciding nothing: other strikes (ATM, ITM2), the mid, the $0.74 fee, by year, spread as a share of the
      premium, return per dollar of premium, affordability, paired with SPX / 10 (the SPX per-day series rebuilt from
      realprice_trades.csv, which must reproduce the SPX confirmation or the run stops), the no-implied-spot fallback,
      SPY (b)'s worst case for missing exits and its entry cohort, XSP settlement rounded to the cent, counts, and the
      fill check on XSP trade bars.

Stop rules (the plan's): the gate; the official-close check against Robinhood; an incomplete download; a SPY-sample day
without a SPY close or with SPY close / official SPX close outside 0.098 .. 0.101; the signal differing from scan.py's
F2 on a kept day; a sign differing from the SPX confirmation trade list; a SPX calendar signal day without a trade-list
row; the rebuilt SPX series not reproducing the SPX confirmation (1,321 days, 585 trades, +$29.87 a day, t 2.40).

Reuse (imported, not copied): scan.py's panel and F2; realprice.py's on_minute_of_day, et_minute, fnum, valid_quote,
implied_spot, intrinsic, body_signal, nw, describe, check_gate, check_closes, parse_cboe, bar_listing and fm;
candle_1550_options_forward.py's official_closes (Robinhood) and write_atomic. realprice.parse_symbol accepts only
SPXW, so the quote and bar parsers here take the root as a parameter and keep parse_quotes' / parse_bars' rules; the
self-test shows they give the same result as realprice's on SPXW files.

IMPLEMENTATION NOTES (where the plan leaves a detail to the code; none changes a verdict):
  - "Days shared with each root" (descriptive 6) and "the same days" (descriptive 5) are taken as the days on which
    both the root's entry and the SPX ITM10 entry were priced; the root's own numbers on exactly those days are shown
    next to SPX's. Descriptive 6 also shows SPX on every day in the root's sample (the other reading). The fill check
    shows SPX on the days of the XSP entries with a readable bar file, and both roots on the matched days (both entries
    priced, both with a readable bar file).
  - The official-close check applies realprice.check_closes' rule (>= 3 overlapping days, each within 0.01) in decimal
    arithmetic, so an exact one-cent difference is not rejected by binary rounding; whether realprice's float version
    agrees is recorded. Variant P&L columns in mini_trades.csv ($0.74, mid, cent settlement, worst case) are filled
    only on the ITM1 rows: the plan's perturbations are not crossed with other strikes.
  - The D1 fallback for SPY (descriptive 9) uses r = SPY close / official SPX close on the latest session before the
    day that has both closes, as tools/databento_mini.py did when it centred the download.
  - Two rows for one date in realprice_trades.csv (config current, period confirmation) stop the run: "the row" of a
    day would be ambiguous.
  - Every attempt is appended to backtests/spx_candle_mini/run_log.txt (start, then completed / stopped / crashed).

Usage (from /Users/kv15/trading):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_mini/mini.py selftest
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_mini/mini.py run

Outputs (rebuilt on each run): backtests/spx_candle_mini/results.json, backtests/spx_candle_mini/RESULTS.md,
data/spx_1549/databento/mini_trades.csv. Research only; nothing here is a trading recommendation.
"""
from __future__ import annotations

import bisect
import csv
import dataclasses
import gzip
import hashlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import traceback
from dataclasses import dataclass
from datetime import date as _date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
REALPRICE_PY = ROOT / "backtests" / "spx_candle_realprice" / "realprice.py"


def _load(name: str, path: Path):
    """realprice.py's importlib pattern, registered in sys.modules before it runs (so dataclasses work)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rp = _load("spx_candle_realprice_ro", REALPRICE_PY)                        # read-only: primitives only
scan = _load("spx_candle_scan_ro", rp.SCAN_PY)                             # the D1 panel and F2
cfo = _load("candle_1550_options_forward_ro", rp.OPTIONS_PY)               # Robinhood closes, write_atomic

# ------------------------------------------------------------------------------------------------
# constants (the plan's "Data", "The signal", "XSP", "SPY", "Descriptive")
# ------------------------------------------------------------------------------------------------
PREREG = ROOT / "preregistration" / "spx_candle_mini.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
SPX_ROOT = ROOT / "data" / "spx_1549"
DB = SPX_ROOT / "databento"
QUOTE_DIRS = {"XSP": DB / "cbbo-1m_1500-1601_xsp_k8", "SPY": DB / "cbbo-1m_1500-1601_spy_k10"}
XSP_BARS_DIR = DB / "ohlcv-1m_1500-1601_xsp_k8"
SPX_DIR = rp.DB_DIR                                                        # cbbo-1m_1500-1601_k60 (SPXW)
CLOSES_CSV = rp.CLOSES_CSV                                                 # spx_official_closes_cboe.csv
SPY_CLOSES_CSV = SPX_ROOT / "spy_daily_closes.csv"
REALPRICE_TRADES = DB / "realprice_trades.csv"
OUT_JSON = HERE / "results.json"
OUT_MD = HERE / "RESULTS.md"
OUT_TRADES = DB / "mini_trades.csv"
RUN_LOG = HERE / "run_log.txt"
ET = ZoneInfo("America/New_York")

ROOTS = ("XSP", "SPY")
PERIOD = ("2021-01-01", "2026-10-20")
SUBPERIODS = (("2021-2022", "2021-01-01", "2022-12-31"), ("2023-2026", "2023-01-01", "2026-10-20"))
YEARS = ("2021", "2022", "2023", "2024", "2025", "2026")
CANDLE, THETA, ENTRY, EXIT = "15:50", 0.60, "15:51", "15:59"
F2_ID = "F2_1m_1550_strong_body"
FEE, FEE_HIGH, MULT, T_BAR = rp.FEE, rp.FEE_HIGH, rp.MULT, rp.T_BAR
OFFSETS = (2, 1, 0)                                                        # $1 strikes in the money: ITM2, ITM1, ATM
LABEL = {2: "ITM2", 1: "ITM1", 0: "ATM"}
BASE = 1                                                                   # ITM1: the analogue of SPX ITM10
SPY_RATIO_BOUNDS = (0.098, 0.101)
AFFORD = 500.0
SPX_CONFIG, SPX_PERIOD = "current", "confirmation"
EXPECTED_SPX = {"days": 1321, "trades": 585, "mean_per_day": 29.87, "t": 2.40}
VERSIONS = ("xsp", "spy_b", "spy_a")
V_ROOT = {"xsp": "XSP", "spy_b": "SPY", "spy_a": "SPY"}
V_SIDES = {"xsp": 1, "spy_b": 2, "spy_a": 1}                               # fee charged once, or on each side
V_NAME = {"xsp": "XSP ITM1: 15:51 ask, settled at SPX close / 10",
          "spy_b": "SPY ITM1 (b): 15:51 ask, sold at the 15:59 bid",
          "spy_a": "SPY ITM1 (a): 15:51 ask, valued at Yahoo's SPY close"}
assert rp.NW_LAG == 5 and rp.PARITY_STRIKES == 3 and FEE == 0.09 and FEE_HIGH == 0.74 and MULT == 100.0
assert T_BAR == 2.0
NAN = float("nan")


# ------------------------------------------------------------------------------------------------
# the gate: no option price is read before it passes
# ------------------------------------------------------------------------------------------------
_GATE = {"sha": None}


def open_gate(prereg: Path = PREREG, ledger: Path = LEDGER) -> str:
    _GATE["sha"] = None
    _GATE["sha"] = rp.check_gate(prereg, ledger)                         # SystemExit unless the hash is in the ledger
    return _GATE["sha"]


def close_gate() -> None:
    _GATE["sha"] = None


def _require_gate(what: str) -> None:
    if not _GATE["sha"]:
        raise SystemExit(f"refusing to read {what}: the gate has not passed (preregistration/spx_candle_mini.md must "
                         "exist and its SHA-256 be in preregistration/LEDGER.md)")


def read_option_gz(path: Path) -> str:
    _require_gate(f"option prices in {path}")
    return gzip.decompress(Path(path).read_bytes()).decode()


def read_option_csv(path: Path) -> list:
    _require_gate(f"option prices in {path}")
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------------------------------------
# root-parameterised parsers (realprice.parse_quotes / parse_bars rules, any root)
# ------------------------------------------------------------------------------------------------
def parse_symbol_root(sym: str, root: str) -> tuple[str, str, float]:
    """OSI symbol 'ROOT  YYMMDD[C|P]SSSSSSSS' (root padded to 6, 21 characters) -> (expiry, kind, strike)."""
    if not (len(root) <= 6 and sym.startswith(f"{root:<6}") and len(sym) == 21):
        raise ValueError(sym)
    day = f"20{sym[6:8]}-{sym[8:10]}-{sym[10:12]}"
    kind = {"C": "call", "P": "put"}[sym[12]]
    return day, kind, int(sym[13:21]) / 1000.0


def parse_quotes_root(text: str, day: str, root: str) -> tuple[dict, dict]:
    """{HH:MM: {(kind, K): (bid, ask)}} of valid quotes for `root` contracts expiring on `day`, plus row counts. Same
    rules as realprice.parse_quotes: same-day expiry, ts_recv exactly on a minute of `day` (ET), valid quote
    (ask > 0, 0 <= bid <= ask), and for one contract at one instant the later valid row wins."""
    out: dict = {}
    n = {"rows": 0, "invalid": 0, "other_expiry": 0, "off_minute": 0}
    for r in csv.DictReader(io.StringIO(text)):
        n["rows"] += 1
        d, kind, K = parse_symbol_root(r["symbol"], root)
        if d != day:
            n["other_expiry"] += 1
            continue
        if not rp.on_minute_of_day(r["ts_recv"], day):
            n["off_minute"] += 1
            continue
        bid, ask = rp.fnum(r["bid_px_00"]), rp.fnum(r["ask_px_00"])
        if not rp.valid_quote(bid, ask):
            n["invalid"] += 1
            continue
        out.setdefault(rp.et_minute(r["ts_recv"]), {})[(kind, K)] = (bid, ask)
    return out, n


def parse_bars_root(text: str, day: str, root: str) -> tuple[dict, dict]:
    """{HH:MM: {(kind, K): (low, close, volume)}} from an ohlcv-1m file (realprice.parse_bars' rules, any root): a bar
    stamped HH:MM (ts_event, the bar's start) covers that minute's trades; same-day expiry only; a row with a missing
    low, close or volume is skipped."""
    out: dict = {}
    n = {"rows": 0, "other_expiry": 0, "bad": 0}
    for r in csv.DictReader(io.StringIO(text)):
        n["rows"] += 1
        d, kind, K = parse_symbol_root(r["symbol"], root)
        if d != day:
            n["other_expiry"] += 1
            continue
        lo, cl, vol = rp.fnum(r.get("low")), rp.fnum(r.get("close")), rp.fnum(r.get("volume"))
        if lo is None or cl is None or vol is None:
            n["bad"] += 1
            continue
        out.setdefault(rp.et_minute(r["ts_event"]), {})[(kind, K)] = (lo, cl, vol)
    return out, n


def load_day_bars_root(day: str, listing: dict, folder: Path, root: str = "XSP"):
    """(bars, status): 'ok', 'none' (no symbol resolved), 'missing' (no file when the run started) or 'unreadable'
    (the file did not parse; never stops the run)."""
    kind = listing.get(day)
    if kind is None:
        return None, "missing"
    if kind == "none":
        return None, "none"
    try:
        text = read_option_gz(Path(folder) / f"{day}.csv.gz")              # SystemExit (gate) is not caught below
        bars, _ = parse_bars_root(text, day, root)
    except Exception:                                                      # descriptive part: report, never stop
        return None, "unreadable"
    return bars, "ok"


# ------------------------------------------------------------------------------------------------
# closes
# ------------------------------------------------------------------------------------------------
def load_official_closes(path: Path) -> dict:
    """Cboe's official SPX closes from the file on disk (never downloaded here; realprice.parse_cboe)."""
    if not Path(path).exists():
        raise SystemExit(f"stop: {path} is missing; mini.py never downloads closes")
    return rp.parse_cboe(Path(path).read_text())


def check_closes_exact(closes: dict, rh: dict) -> dict:
    """realprice.check_closes' rule (at least MIN_CLOSE_OVERLAP overlapping days, every one within CLOSE_CHECK_TOL =
    0.01 of Robinhood's close, else stop), compared in decimals so an exact one-cent difference is not rejected by
    binary rounding (code review, point 2). Also records whether realprice's float check gives the same answer."""
    over = sorted(set(closes) & set(rh))
    tol = Decimal(repr(float(rp.CLOSE_CHECK_TOL)))

    def diff(d):
        return abs(Decimal(repr(float(closes[d]))) - Decimal(repr(float(rh[d][0]))))
    bad = [(d, closes[d], rh[d][0]) for d in over if diff(d) > tol]
    if len(over) < rp.MIN_CLOSE_OVERLAP or bad:
        raise SystemExit(f"official-close check failed: {len(over)} overlap days, mismatches {bad[:5]}")
    try:
        rp.check_closes(closes, rh)
        float_agrees = True
    except SystemExit:
        float_agrees = False
    return {"overlap_days": len(over), "max_abs_diff": float(max(diff(d) for d in over)),
            "realprice_float_check_agrees": float_agrees}


def load_spy_closes(path: Path) -> dict:
    if not Path(path).exists():
        raise SystemExit(f"stop: {path} is missing; mini.py never downloads closes")
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            v = rp.fnum(r.get("close"))
            if v is not None and v > 0:
                out[r["date"]] = v
    return out


def check_spy_closes(days: list, spy: dict, closes: dict) -> dict:
    """Every SPY-sample day needs a SPY close, and SPY close / official SPX close in 0.098 .. 0.101, else stop."""
    missing = [d for d in days if d not in spy]
    bad = [(d, spy[d] / closes[d]) for d in days if d in spy and not
           (SPY_RATIO_BOUNDS[0] <= spy[d] / closes[d] <= SPY_RATIO_BOUNDS[1])]
    if missing or bad:
        raise SystemExit(f"stop (SPY close check): {len(missing)} SPY-sample days without a SPY close (first "
                         f"{missing[:3]}), {len(bad)} with SPY / SPX outside {SPY_RATIO_BOUNDS} (first {bad[:3]})")
    r = [spy[d] / closes[d] for d in days]
    return {"days": len(days), "ratio_min": min(r) if r else None, "ratio_max": max(r) if r else None}


class PrevRatio:
    """r = SPY close / official SPX close on the latest session before `day` with both closes (databento_mini's rule
    for centring the SPY download; used only by the no-implied-spot fallback, descriptive 9)."""

    def __init__(self, spy: dict, spx: dict):
        self.both = sorted(d for d in spy if d in spx)
        self.spy, self.spx = spy, spx

    def __call__(self, day: str):
        i = bisect.bisect_left(self.both, day)
        if i == 0:
            return None
        d = self.both[i - 1]
        return self.spy[d] / self.spx[d]


# ------------------------------------------------------------------------------------------------
# pricing one day
# ------------------------------------------------------------------------------------------------
def atm1(s: float) -> float:
    """Nearest $1 strike, halves up: floor(S + 0.5)."""
    return float(math.floor(s + 0.5))


def contract(sgn: int, atm: float, offset: int) -> tuple[str, float]:
    """ITM by `offset` $1 strikes in the trade's direction: up -> call at ATM - offset, down -> put at ATM + offset."""
    return ("call", atm - offset) if sgn > 0 else ("put", atm + offset)


def _leg(kind: str, K: float, status: str) -> dict:
    return {"kind": kind, "K": K, "bid": NAN, "ask": NAN, "mid": NAN, "status": status,
            "exit_bid": NAN, "exit_ask": NAN, "exit_mid": NAN, "exit_status": ""}


def entry_leg(q51: dict, q59: dict, sgn: int, atm: float, offset: int, with_exit: bool) -> dict:
    kind, K = contract(sgn, atm, offset)
    leg = _leg(kind, K, "no_quote")
    qa = q51.get((kind, K))
    if qa is None:                                                         # no valid quote, or outside the band
        return leg
    leg.update(bid=qa[0], ask=qa[1], mid=(qa[0] + qa[1]) / 2, status="priced")
    if with_exit:
        qe = q59.get((kind, K))
        if qe is None:
            leg["exit_status"] = "no_exit_quote"
        else:
            leg.update(exit_bid=qe[0], exit_ask=qe[1], exit_mid=(qe[0] + qe[1]) / 2, exit_status="priced")
    return leg


def day_record(root: str, day: str, s: float, quotes: dict, settle: float, spx_close: float, d1_atm) -> dict:
    """Everything about one sample day: the signal, the implied spot and ATM at 15:51, and for a signal day the leg
    bought at each strike (and its 15:59 exit for SPY), plus the D1-ATM fallback leg on a no-spot day."""
    q51, q59 = quotes.get(ENTRY, {}), quotes.get(EXIT, {})
    spot = rp.implied_spot(q51)
    atm = atm1(spot) if spot is not None else None
    rec = {"root": root, "date": day, "s": float(s), "spot": spot, "atm": atm, "d1_atm": d1_atm, "settle": settle,
           "spx_close": spx_close, "legs": {}, "fallback": None}
    if not np.isfinite(s) or s == 0:
        return rec
    sgn = 1 if s > 0 else -1
    for o in OFFSETS:
        if atm is None:
            rec["legs"][o] = _leg("call" if sgn > 0 else "put", NAN, "no_spot")
        else:
            rec["legs"][o] = entry_leg(q51, q59, sgn, atm, o, root == "SPY")
    if atm is None and d1_atm is not None:
        rec["fallback"] = entry_leg(q51, q59, sgn, d1_atm, BASE, root == "SPY")
    return rec


def pnl_settle(leg, X: float, fee: float = FEE, price: str = "ask") -> float:
    """XSP and SPY (a): 100 x (intrinsic at X - entry price) - fee (once)."""
    if leg is None or leg["status"] != "priced":
        return NAN
    p = leg["ask"] if price == "ask" else leg["mid"]
    return MULT * (rp.intrinsic(leg["kind"], leg["K"], X) - p) - fee


def pnl_exit(leg, fee: float = FEE, price: str = "ask") -> float:
    """SPY (b): 100 x (15:59 bid - 15:51 ask) - 2 x fee (the mid version: mid to mid); not priced without an exit."""
    if leg is None or leg["status"] != "priced" or leg["exit_status"] != "priced":
        return NAN
    buy = leg["ask"] if price == "ask" else leg["mid"]
    sell = leg["exit_bid"] if price == "ask" else leg["exit_mid"]
    return MULT * (sell - buy) - 2 * fee


def pnl_exit_worst(leg, fee: float = FEE) -> float:
    """SPY (b) worst case: a priced entry with no 15:59 quote is charged the full premium plus both fees."""
    if leg is None or leg["status"] != "priced":
        return NAN
    if leg["exit_status"] == "no_exit_quote":
        return -MULT * leg["ask"] - 2 * fee
    return pnl_exit(leg, fee)


def pnl(v: str, rec: dict, leg, fee: float = FEE, price: str = "ask", settle=None) -> float:
    if v == "spy_b":
        return pnl_exit(leg, fee, price)
    return pnl_settle(leg, rec["settle"] if settle is None else settle, fee, price)


def settle_cent(spx_close: float) -> float:
    """SPX close / 10 rounded half up to the cent (descriptive 11), in decimal arithmetic."""
    return float((Decimal(repr(float(spx_close))) / Decimal(10)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def leg_status(v: str, leg) -> str:
    if leg is None:
        return "no_leg"
    if leg["status"] != "priced" or v != "spy_b":
        return leg["status"]
    return "priced" if leg["exit_status"] == "priced" else "no_exit_quote"


# ------------------------------------------------------------------------------------------------
# per-day series and statistics
# ------------------------------------------------------------------------------------------------
def series(recs: list, fn) -> np.ndarray:
    """Per day: fn(rec) on a signal day (NaN when not priced), 0 on a no-signal day, NaN when the candle is missing."""
    out = np.full(len(recs), np.nan)
    for i, r in enumerate(recs):
        s = r["s"]
        if not np.isfinite(s):
            continue
        out[i] = 0.0 if s == 0 else fn(r)
    return out


def vseries(recs: list, v: str, o: int = BASE, **kw) -> np.ndarray:
    return series(recs, lambda r: pnl(v, r, r["legs"].get(o), **kw))


def sarr(recs: list) -> np.ndarray:
    return np.array([r["s"] for r in recs], float)


def darr(recs: list) -> np.ndarray:
    return np.array([r["date"] for r in recs], dtype="U10")


def sliced(x, s, dates, lo: str, hi: str) -> dict:
    m = (dates >= lo) & (dates <= hi)
    return rp.describe(x[m], s[m])


def passes(st: dict) -> bool:
    m, t = st["mean_per_day"], st["nw_t_per_day"]
    return bool(m is not None and m > 0 and t is not None and t >= T_BAR)


def full_stats(x, s, dates) -> dict:
    out = rp.describe(x, s)
    out["subperiods"] = {name: sliced(x, s, dates, lo, hi) for name, lo, hi in SUBPERIODS}
    return out


def by_year(x, s, dates) -> dict:
    out = {y: sliced(x, s, dates, f"{y}-01-01", min(f"{y}-12-31", PERIOD[1])) for y in YEARS}
    out.update({name: sliced(x, s, dates, lo, hi) for name, lo, hi in SUBPERIODS})
    return out


def trade_stats(v: list) -> dict:
    a = np.asarray(v, float)
    if a.size == 0:
        return {"n": 0, "mean": None, "sum": None, "share_won": None, "median": None, "worst": None}
    return {"n": int(a.size), "mean": float(a.mean()), "sum": float(a.sum()), "share_won": float(np.mean(a > 0)),
            "median": float(np.median(a)), "worst": float(a.min())}


def mean_median(v: list) -> dict:
    a = np.asarray(v, float)
    return {"n": int(a.size), "mean": float(a.mean()) if a.size else None,
            "median": float(np.median(a)) if a.size else None}


# ------------------------------------------------------------------------------------------------
# the SPX ITM10 series, rebuilt from realprice_trades.csv without repricing (descriptive 8)
# ------------------------------------------------------------------------------------------------
def spx_rows_by_day(rows: list) -> dict:
    out = {}
    for r in rows:
        if r["config"] != SPX_CONFIG or r["period"] != SPX_PERIOD:
            continue
        if r["date"] in out:
            raise SystemExit(f"stop: two rows for {r['date']} in realprice_trades.csv (config {SPX_CONFIG}, period "
                             f"{SPX_PERIOD})")
        out[r["date"]] = r
    return out


def spx_series(cal: list, sig_by_day: dict, rows: dict) -> tuple[np.ndarray, np.ndarray]:
    x, s = np.full(len(cal), np.nan), np.full(len(cal), np.nan)
    missing = []
    for i, d in enumerate(cal):
        sd = sig_by_day[d]
        s[i] = sd
        if not np.isfinite(sd):
            continue
        if sd == 0:
            x[i] = 0.0
            continue
        r = rows.get(d)
        if r is None:
            missing.append(d)
            continue
        x[i] = float(r["pnl_fee_0.09"]) if r["status"] == "priced" else np.nan
    if missing:
        raise SystemExit(f"stop (SPX series rebuild): {len(missing)} SPX calendar days with a signal have no row in "
                         f"realprice_trades.csv (first {missing[:3]})")
    return x, s


def check_spx_reproduction(st: dict, expected: dict) -> dict:
    got = {"days": st["days"], "trades": st["trades"],
           "mean_per_day": round(st["mean_per_day"], 2) if st["mean_per_day"] is not None else None,
           "t": round(st["nw_t_per_day"], 2) if st["nw_t_per_day"] is not None else None}
    ok = (got["days"] == expected["days"] and got["trades"] == expected["trades"] and got["mean_per_day"] is not None
          and abs(got["mean_per_day"] - expected["mean_per_day"]) < 1e-9 and got["t"] is not None
          and abs(got["t"] - expected["t"]) < 1e-9)
    if not ok:
        raise SystemExit(f"stop (SPX reproduction): the rebuilt SPX series gives {got}, not the SPX confirmation "
                         f"{expected}")
    return {"expected": dict(expected), "got": got, "passed": True}


# ------------------------------------------------------------------------------------------------
# the environment (paths and loaders; the self-test swaps in synthetic ones)
# ------------------------------------------------------------------------------------------------
@dataclass
class Env:
    prereg: Path
    ledger: Path
    quote_dirs: dict
    bars_dir: Path
    spx_dir: Path
    closes_csv: Path
    spy_closes_csv: Path
    realprice_trades: Path
    rh_closes: object                  # () -> {date: (close, source)}
    load_panel: object                 # () -> scan.Panel of the D1 keep days in PERIOD
    f2: object                         # Panel -> scan.py's F2 signal
    expected_spx: dict
    out_json: Path
    out_md: Path
    out_trades: Path
    run_log: Path
    manifests: dict                    # root -> manifest.json (diagnostic only)


def default_env() -> Env:
    return Env(prereg=PREREG, ledger=LEDGER, quote_dirs=dict(QUOTE_DIRS), bars_dir=XSP_BARS_DIR, spx_dir=SPX_DIR,
               closes_csv=CLOSES_CSV, spy_closes_csv=SPY_CLOSES_CSV, realprice_trades=REALPRICE_TRADES,
               rh_closes=lambda: cfo.official_closes(SPX_ROOT)[0],
               load_panel=lambda: scan.load_panel(*PERIOD),
               f2=lambda P: np.asarray(scan.spec_by_id(F2_ID).signal(P), float),
               expected_spx=dict(EXPECTED_SPX), out_json=OUT_JSON, out_md=OUT_MD, out_trades=OUT_TRADES,
               run_log=RUN_LOG, manifests={r: QUOTE_DIRS[r] / "manifest.json" for r in ROOTS})


def listing_sha(folder: Path) -> str:
    files = sorted(Path(folder).glob("*")) if Path(folder).is_dir() else []
    return hashlib.sha256("\n".join(f"{f.name} {f.stat().st_size}" for f in files).encode()).hexdigest()


def weekday(d: str) -> str:
    return _date.fromisoformat(d).strftime("%a")


# ------------------------------------------------------------------------------------------------
# the run
# ------------------------------------------------------------------------------------------------
def run(env: Env) -> dict:
    sha = open_gate(env.prereg, env.ledger)
    bar_list = rp.bar_listing(env.bars_dir)                                # the fill check uses the files there now
    checks: dict = {}
    # official closes: Cboe file on disk, checked against Robinhood before any option is priced
    closes = load_official_closes(env.closes_csv)
    checks["official_close_check"] = check_closes_exact(closes, env.rh_closes())
    # the D1 panel and the signal; check 1: it equals scan.py's F2 on every kept day
    P = env.load_panel()
    dates = [str(d) for d in P.dates]
    if not dates or not all(PERIOD[0] <= d <= PERIOD[1] for d in dates) or dates != sorted(dates):
        raise SystemExit("stop: the D1 panel is empty, unsorted or outside the study period")
    k = scan.mi(CANDLE)
    sig = rp.body_signal(P.O[:, k], P.H[:, k], P.L[:, k], P.C[:, k], THETA)
    f2 = np.asarray(env.f2(P), float)
    if f2.shape != sig.shape or not np.array_equal(np.nan_to_num(sig, nan=9), np.nan_to_num(f2, nan=9)):
        raise SystemExit("stop (signal check 1): the 15:50 strong-body signal differs from scan.py's F2 on a kept day")
    checks["signal_check_1"] = {"kept_days": len(dates), "equal_to_scan_F2": True}
    sig_by_day = dict(zip(dates, (float(v) for v in sig)))
    s1551 = dict(zip(dates, (float(v) for v in P.O[:, scan.mi(ENTRY)])))
    # downloads complete: every D1 day has a file or a .none marker, for each root
    lists = {root: rp.bar_listing(env.quote_dirs[root]) for root in ROOTS}
    for root in ROOTS:
        miss = [d for d in dates if d not in lists[root]]
        if miss:
            raise SystemExit(f"stop: the {root} download is incomplete: {len(miss)} D1 days have neither a file nor a "
                             f".none marker (first {miss[:3]})")
    samples = {root: [d for d in dates if lists[root][d] == "file" and d in closes] for root in ROOTS}
    # SPY closes: every SPY-sample day, ratio in bounds
    spy = load_spy_closes(env.spy_closes_csv)
    checks["spy_close_check"] = check_spy_closes(samples["SPY"], spy, closes)
    # the SPX confirmation trade list; check 2: the same sign on every day in both
    spx_rows = spx_rows_by_day(read_option_csv(env.realprice_trades))
    both = [d for d in spx_rows if d in sig_by_day]
    bad = [d for d in both if not (np.isfinite(sig_by_day[d]) and sig_by_day[d] != 0
                                   and np.sign(float(spx_rows[d]["signal"])) == sig_by_day[d])]
    if bad:
        raise SystemExit(f"stop (signal check 2): the signal's sign differs from the SPX confirmation trade list on "
                         f"{len(bad)} days (first {bad[:3]})")
    checks["signal_check_2"] = {"days_in_both": len(both), "same_sign": True,
                                "trade_list_days_not_in_d1": len([d for d in spx_rows if d not in sig_by_day])}
    # the SPX ITM10 per-day series, rebuilt; it must reproduce the SPX confirmation
    spx_list = rp.bar_listing(env.spx_dir)
    spx_cal = [d for d in dates if spx_list.get(d) == "file" and d in closes]
    x_spx, s_spx = spx_series(spx_cal, sig_by_day, spx_rows)
    spx_st = full_stats(x_spx, s_spx, np.array(spx_cal, dtype="U10"))
    checks["spx_reproduction"] = check_spx_reproduction(spx_st, env.expected_spx)
    # price every sample day of each root
    prev_ratio = PrevRatio(spy, closes)
    recs, parse_counts = {}, {}
    for root in ROOTS:
        recs[root], pc = [], {"rows": 0, "invalid": 0, "other_expiry": 0, "off_minute": 0}
        for d in samples[root]:
            quotes, n = parse_quotes_root(read_option_gz(env.quote_dirs[root] / f"{d}.csv.gz"), d, root)
            for kk in pc:
                pc[kk] += n[kk]
            if root == "XSP":
                settle, d1_atm = closes[d] / 10.0, float(math.floor(s1551[d] / 10 + 0.5))
            else:
                r = prev_ratio(d)
                settle, d1_atm = spy[d], (float(math.floor(s1551[d] * r + 0.5)) if r is not None else None)
            recs[root].append(day_record(root, d, sig_by_day[d], quotes, settle, closes[d], d1_atm))
        parse_counts[root] = pc
    res, rows = analyse(recs, dates, sig_by_day, closes, lists, samples, spx_cal, x_spx, s_spx, spx_st, spx_rows,
                        bar_list, env)
    res = {"what": "The 15:50 candle on XSP and SPY 0DTE options at real prices (spx_candle_mini.md)",
           "prereg_sha256": sha, "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "period": list(PERIOD), "checks": checks,
           "data": {"quote_listing_sha256": {r: listing_sha(env.quote_dirs[r]) for r in ROOTS},
                    "xsp_bars_listing_sha256": listing_sha(env.bars_dir), "quote_rows_parsed": parse_counts,
                    "d1_center_vs_download_manifest": manifest_check(env, recs)},
           **res}
    write_outputs(res, rows, env)
    return res


def manifest_check(env: Env, recs: dict) -> dict:
    """Diagnostic only: on how many sample days the D1 centre used by the fallback equals the download's centre."""
    out = {}
    for root in ROOTS:
        p = env.manifests.get(root)
        if not p or not Path(p).exists():
            out[root] = None
            continue
        cen = {it["day"]: float(it["center"]) for it in json.loads(Path(p).read_text())["days"]}
        n = [r for r in recs[root] if r["date"] in cen]
        out[root] = {"days": len(n), "equal": sum(1 for r in n if r["d1_atm"] is not None and r["d1_atm"] == cen[r["date"]])}
    return out


# ------------------------------------------------------------------------------------------------
# analysis (everything after pricing)
# ------------------------------------------------------------------------------------------------
def unpriced(recs: list, v: str, o: int = BASE) -> dict:
    c = {"signal_days": 0, "priced": 0, "no_spot": 0, "no_quote": 0, "no_exit_quote": 0}
    for r in recs:
        if not np.isfinite(r["s"]) or r["s"] == 0:
            continue
        c["signal_days"] += 1
        st = leg_status(v, r["legs"].get(o))
        c[st if st in c else "no_quote"] += 1
    if v != "spy_b":
        c.pop("no_exit_quote")
    return c


def priced_legs(recs: list, v: str, o: int = BASE):
    """(rec, leg) for every priced trade of version v at offset o."""
    for r in recs:
        if np.isfinite(r["s"]) and r["s"] != 0 and leg_status(v, r["legs"].get(o)) == "priced":
            yield r, r["legs"][o]


def analyse(recs, dates, sig_by_day, closes, lists, samples, spx_cal, x_spx, s_spx, spx_st, spx_rows, bar_list,
            env) -> tuple[dict, list]:
    R = {v: recs[V_ROOT[v]] for v in VERSIONS}
    D = {v: darr(R[v]) for v in VERSIONS}
    S = {v: sarr(R[v]) for v in VERSIONS}
    base = {v: vseries(R[v], v) for v in VERSIONS}
    stats = {v: full_stats(base[v], S[v], D[v]) for v in VERSIONS}
    verdicts = {}
    for v in ("xsp", "spy_b"):
        ok = passes(stats[v])
        verdicts[v] = {"confirmed": ok, "stats": stats[v], "unpriced": unpriced(R[v], v), "line": verdict_line(v, stats[v], ok)}
    out = {"verdicts": verdicts,
           "primary": {v: {"name": V_NAME[v], **stats[v], "unpriced": unpriced(R[v], v)} for v in VERSIONS},
           "spx_itm10": {"name": "SPX ITM10 (SPXW), 15:51 ask, settled at the SPX close, $0.09: rebuilt from "
                                 "realprice_trades.csv, not repriced", **spx_st, "calendar_days": len(spx_cal)}}
    desc: dict = {}
    # 1-3: other strikes, the mid, the $0.74 fee
    desc["strikes_mid_fee"] = {}
    for v in VERSIONS:
        rows_v = {}
        for o in OFFSETS:
            rows_v[f"{LABEL[o]}, ask, $0.09"] = rp.describe(vseries(R[v], v, o), S[v])
        rows_v["ITM1, mid, $0.09"] = rp.describe(vseries(R[v], v, BASE, price="mid"), S[v])
        rows_v["ITM1, ask, $0.74"] = rp.describe(vseries(R[v], v, BASE, fee=FEE_HIGH), S[v])
        desc["strikes_mid_fee"][v] = {"rows": rows_v, "unpriced": {LABEL[o]: unpriced(R[v], v, o) for o in OFFSETS}}
    # 4: by year
    desc["by_year"] = {v: by_year(base[v], S[v], D[v]) for v in VERSIONS}
    desc["by_year"]["spx_itm10"] = by_year(x_spx, s_spx, np.array(spx_cal, dtype="U10"))
    # 5: spread as a share of the premium
    desc["spread_share"] = spread_share(R, spx_rows)
    # 6: return per dollar of premium
    desc["return_per_premium"] = return_per_premium(R, spx_rows)
    # 7: affordability
    desc["affordability"] = {v: affordability(R[v], v, base[v], S[v]) for v in VERSIONS}
    # 8: paired with SPX / 10
    desc["paired_with_spx"] = {v: paired(R[v], v, base[v], spx_cal, x_spx, s_spx) for v in VERSIONS}
    # 9: no implied spot, the D1 ATM instead
    desc["no_spot_fallback"] = {v: fallback(R[v], v, base[v], S[v]) for v in VERSIONS}
    # 10: SPY (b) worst case for missing exits; the entry cohort by year
    xw = series(R["spy_b"], lambda r: pnl_exit_worst(r["legs"].get(BASE)))
    desc["spy_b_worst_case"] = {**full_stats(xw, S["spy_b"], D["spy_b"]),
                                "trades_charged_full_premium": unpriced(R["spy_b"], "spy_b")["no_exit_quote"]}
    desc["spy_entry_cohort"] = entry_cohort(R["spy_b"])
    zero_bid = [r["date"] for r, lg in priced_legs(R["spy_b"], "spy_b") if lg["exit_bid"] == 0]
    desc["spy_b_exits_at_zero_bid"] = {"n": len(zero_bid), "days": zero_bid}
    # 11: XSP settlement rounded half up to the cent
    xc = series(R["xsp"], lambda r: pnl_settle(r["legs"].get(BASE), settle_cent(r["spx_close"])))
    desc["xsp_settlement_cent"] = {**full_stats(xc, S["xsp"], D["xsp"]),
                                   "max_abs_change_per_trade": float(np.nanmax(np.abs(xc - base["xsp"])))
                                   if np.isfinite(xc - base["xsp"]).any() else None}
    # 12: counts
    desc["counts"] = counts(recs, dates, sig_by_day, closes, lists, samples, spx_cal)
    out["descriptive"] = desc
    # trade rows, then the fill check (fills in the bar columns of the XSP ITM1 rows)
    rows = trade_rows(R)
    out["fill_check"] = fill_check(rows, bar_list, lambda d: load_day_bars_root(d, bar_list, env.bars_dir, "XSP"),
                                   spx_rows, env.bars_dir)
    return out, rows


def verdict_line(v: str, st: dict, ok: bool) -> str:
    fm = rp.fm
    core = (f"{fm(st['mean_per_day'])} a day, Newey-West t {fm(st['nw_t_per_day'])}, {st['days']} days, "
            f"{st['trades']} trades, {fm(st['mean_per_trade'])} a trade, {fm(st['share_trades_won'], pct=True)} won, "
            f"median {fm(st['median_trade'])}, worst {fm(st['worst_trade'])}")
    if v == "xsp":
        return ("XSP (the primary test; ITM1 at the 15:51 ask, settled at SPX close / 10, $0.09): "
                + ("CONFIRMED (per-day mean > 0 with Newey-West t >= 2.0): " if ok else
                   "not confirmed on XSP at real prices: ") + core)
    return ("SPY (secondary; version (b): ITM1 at the 15:51 ask, sold at the 15:59 bid, $0.09 each side): "
            + ("CONFIRMED (selling at the 15:59 bid; per-day mean > 0 with Newey-West t >= 2.0): " if ok else
               "not confirmed on SPY at real prices: ") + core)


def spread_share(R: dict, spx_rows: dict) -> dict:
    def spx_share(d):
        r = spx_rows.get(d)
        if r is None or r["status"] != "priced":
            return None
        a, m = float(r["ask"]), float(r["mid"])
        return 2 * (a - m) / m

    out = {}
    for name, v in (("xsp", "xsp"), ("spy_entry", "spy_a")):
        ent = [(r["date"], (lg["ask"] - lg["bid"]) / lg["mid"]) for r, lg in priced_legs(R[v], v)]
        pair = [(d, sh, spx_share(d)) for d, sh in ent if spx_share(d) is not None]
        res = {}
        for y in ("all",) + YEARS:
            e = [sh for d, sh in ent if y == "all" or d[:4] == y]
            p = [(sh, sx) for d, sh, sx in pair if y == "all" or d[:4] == y]
            res[y] = {"root": mean_median(e), "root_on_paired_days": mean_median([a for a, _ in p]),
                      "spx_itm10_on_paired_days": mean_median([b for _, b in p])}
        out[name] = res
    ex = [(r["date"], (lg["exit_ask"] - lg["exit_bid"]) / lg["exit_mid"]) for r, lg in priced_legs(R["spy_b"], "spy_b")]
    out["spy_b_exit_1559"] = {y: mean_median([sh for d, sh in ex if y == "all" or d[:4] == y]) for y in ("all",) + YEARS}
    return out


def _ppd(pnls: list, asks: list) -> dict:
    p, a = np.asarray(pnls, float), MULT * np.asarray(asks, float)
    return {"trades": int(p.size), "sum_pnl": float(p.sum()) if p.size else None,
            "sum_premium": float(a.sum()) if p.size else None,
            "return_per_dollar": float(p.sum() / a.sum()) if p.size and a.sum() > 0 else None,
            "mean_pnl": float(p.mean()) if p.size else None, "mean_premium": float(a.mean()) if p.size else None}


def return_per_premium(R: dict, spx_rows: dict) -> dict:
    spx_p = {d: r for d, r in spx_rows.items() if r["status"] == "priced" and PERIOD[0] <= d <= PERIOD[1]}
    out = {"spx_itm10_all": _ppd([float(r["pnl_fee_0.09"]) for r in spx_p.values()],
                                 [float(r["ask"]) for r in spx_p.values()])}
    for v in VERSIONS:
        tr = [(r["date"], pnl(v, r, lg), lg["ask"]) for r, lg in priced_legs(R[v], v)]
        sh = [t for t in tr if t[0] in spx_p]
        samp = {r["date"] for r in R[v]}
        cal = [d for d in sorted(spx_p) if d in samp]
        out[v] = {"all": _ppd([p for _, p, _ in tr], [a for _, _, a in tr]),
                  "on_days_shared_with_spx": _ppd([p for _, p, _ in sh], [a for _, _, a in sh]),
                  "spx_itm10_on_the_same_days": _ppd([float(spx_p[d]["pnl_fee_0.09"]) for d, _, _ in sh],
                                                     [float(spx_p[d]["ask"]) for d, _, _ in sh]),
                  # the other reading of "the days shared with each root": every SPX trade on a day in the root's sample
                  "spx_itm10_on_days_in_root_sample": _ppd([float(spx_p[d]["pnl_fee_0.09"]) for d in cal],
                                                           [float(spx_p[d]["ask"]) for d in cal])}
    return out


def affordability(recs: list, v: str, x, s) -> dict:
    """Share of priced trades with premium + entry fee <= $500; and the 'affordable only' series (a trade costing more
    is skipped: 0 that day, no trade; every other day unchanged)."""
    tr = [(r, lg) for r, lg in priced_legs(recs, v)]
    ok = [MULT * lg["ask"] + FEE <= AFFORD for _, lg in tr]
    xa, sa = np.array(x, float), np.array(s, float)
    skipped = 0
    for i, r in enumerate(recs):
        lg = r["legs"].get(BASE)
        if np.isfinite(r["s"]) and r["s"] != 0 and lg is not None and lg["status"] == "priced" \
                and MULT * lg["ask"] + FEE > AFFORD:
            xa[i], sa[i] = 0.0, 0.0
            skipped += 1
    return {"priced_trades": len(tr), "affordable": int(sum(ok)), "share_affordable": float(np.mean(ok)) if ok else None,
            "entries_skipped_as_unaffordable": skipped, "affordable_only": rp.describe(xa, sa)}


def paired(recs: list, v: str, x, spx_cal: list, x_spx, s_spx) -> dict:
    """Root - SPX / 10 per day on the days in both samples (missing if either is missing); and before fees: on traded
    days (root P&L + its fees) - (SPX P&L + $0.09) / 10, 0 on no-signal days."""
    spx_i = {d: i for i, d in enumerate(spx_cal)}
    diff, pre, n_traded = [], [], 0
    fees = V_SIDES[v] * FEE
    for i, r in enumerate(recs):
        j = spx_i.get(r["date"])
        if j is None:
            continue
        a, b = x[i], x_spx[j]
        diff.append(a - b / 10.0 if np.isfinite(a) and np.isfinite(b) else np.nan)
        if not np.isfinite(r["s"]):
            pre.append(np.nan)
        elif r["s"] == 0:
            pre.append(0.0)
        elif np.isfinite(a) and np.isfinite(b):
            pre.append((a + fees) - (b + FEE) / 10.0)
            n_traded += 1
        else:
            pre.append(np.nan)
    return {"days_in_both_samples": len(diff), "after_fees": rp.nw(diff), "before_fees": rp.nw(pre),
            "traded_days_in_both": n_traded}


def fallback(recs: list, v: str, x, s) -> dict:
    """Descriptive 9: on days not priced for lack of an implied spot, the same trade with ATM from D1."""
    no_spot = [r for r in recs if np.isfinite(r["s"]) and r["s"] != 0 and r["legs"][BASE]["status"] == "no_spot"]
    xf = np.array(x, float)
    idx = {r["date"]: i for i, r in enumerate(recs)}
    p, st = [], {"priced": 0, "no_quote": 0, "no_exit_quote": 0, "no_d1_atm": 0}
    for r in no_spot:
        lg = r["fallback"]
        if lg is None:
            st["no_d1_atm"] += 1
            continue
        k = leg_status(v, lg)
        st[k if k in st else "no_quote"] += 1
        if k == "priced":
            val = pnl(v, r, lg)
            p.append(val)
            xf[idx[r["date"]]] = val
    return {"no_spot_signal_days": len(no_spot), **st, "fallback_trades": trade_stats(p),
            "series_with_fallback": rp.describe(xf, s)}


def entry_cohort(recs: list) -> dict:
    out = {}
    for y in ("all",) + YEARS:
        e = [(r, lg) for r, lg in priced_legs(recs, "spy_a") if y == "all" or r["date"][:4] == y]
        q = sum(1 for _, lg in e if lg["exit_status"] == "priced")
        out[y] = {"priced_entries": len(e), "with_1559_quote": q, "share": q / len(e) if e else None}
    return out


def counts(recs, dates, sig_by_day, closes, lists, samples, spx_cal) -> dict:
    spx_set = set(spx_cal)
    out = {}
    for root in ROOTS:
        rs = {r["date"]: r for r in recs[root]}
        samp = set(samples[root])
        per = {}
        for y in YEARS + ("all",):
            ds = [d for d in dates if y == "all" or d[:4] == y]
            c = {"d1_days": len(ds), "file": sum(lists[root][d] == "file" for d in ds),
                 "no_symbol_resolved": sum(lists[root][d] == "none" for d in ds),
                 "file_no_official_close": sum(lists[root][d] == "file" and d not in closes for d in ds),
                 "sample_days": sum(d in samp for d in ds),
                 "signal_days": sum(d in samp and np.isfinite(sig_by_day[d]) and sig_by_day[d] != 0 for d in ds),
                 "missing_candles": sum(d in samp and not np.isfinite(sig_by_day[d]) for d in ds)}
            vs = ("xsp",) if root == "XSP" else ("spy_a", "spy_b")
            for v in vs:
                u = unpriced([rs[d] for d in ds if d in rs], v)
                key = "" if root == "XSP" else (" (entry)" if v == "spy_a" else " (b)")
                c[f"priced{key}"] = u["priced"]
                if v != "spy_b":
                    c["no_spot"], c["no_quote"] = u["no_spot"], u["no_quote"]
                else:
                    c["no_exit_quote"] = u["no_exit_quote"]
            c["in_sample_not_in_spx"] = sum(d in samp and d not in spx_set for d in ds)
            c["in_spx_not_in_sample"] = sum(d in spx_set and d not in samp for d in ds)
            per[y] = c
        wd = {}
        for tag, days in (("in_sample_not_in_spx", [d for d in samples[root] if d not in spx_set]),
                          ("in_spx_not_in_sample", [d for d in spx_cal if d not in samp])):
            wd[tag] = {w: sum(weekday(d) == w for d in days) for w in ("Mon", "Tue", "Wed", "Thu", "Fri")}
        out[root] = {"by_year": per, "by_weekday": wd}
    return out


TRADE_COLUMNS = ["version", "root", "strike_label", "date", "signal", "implied_spot", "atm", "d1_atm", "kind",
                 "strike", "entry_bid", "entry_ask", "entry_mid", "exit_bid_1559", "exit_ask_1559", "exit_mid_1559",
                 "settle", "pnl_fee_0.09", "pnl_fee_0.74", "pnl_mid_fee_0.09", "pnl_settle_cent", "pnl_worst_case",
                 "premium_plus_fee", "status", "bar_file", "bar_volume", "bar_low", "bar_close"]


def trade_rows(R: dict) -> list:
    """Every XSP and SPY entry at every reported strike and version, with its status (signal days in the sample)."""
    rows = []
    for v in VERSIONS:
        for r in R[v]:
            if not np.isfinite(r["s"]) or r["s"] == 0:
                continue
            legs = [(LABEL[o], r["legs"][o]) for o in OFFSETS]
            if r["fallback"] is not None:
                legs.append(("ITM1_d1_atm_no_spot_fallback", r["fallback"]))
            for lab, lg in legs:
                row = {"version": v, "root": V_ROOT[v], "strike_label": lab, "date": r["date"], "signal": int(r["s"]),
                       "implied_spot": r["spot"] if r["spot"] is not None else NAN,
                       "atm": r["atm"] if r["atm"] is not None else NAN,
                       "d1_atm": r["d1_atm"] if r["d1_atm"] is not None else NAN, "kind": lg["kind"], "strike": lg["K"],
                       "entry_bid": lg["bid"], "entry_ask": lg["ask"], "entry_mid": lg["mid"],
                       "exit_bid_1559": lg["exit_bid"] if v == "spy_b" else NAN,
                       "exit_ask_1559": lg["exit_ask"] if v == "spy_b" else NAN,
                       "exit_mid_1559": lg["exit_mid"] if v == "spy_b" else NAN,
                       "settle": r["settle"] if v != "spy_b" else NAN,
                       "pnl_fee_0.09": pnl(v, r, lg),
                       # the descriptive perturbations are ITM1-only and never crossed with another strike
                       "pnl_fee_0.74": pnl(v, r, lg, fee=FEE_HIGH) if lab == LABEL[BASE] else NAN,
                       "pnl_mid_fee_0.09": pnl(v, r, lg, price="mid") if lab == LABEL[BASE] else NAN,
                       "pnl_settle_cent": pnl_settle(lg, settle_cent(r["spx_close"]))
                       if v == "xsp" and lab == LABEL[BASE] else NAN,
                       "pnl_worst_case": pnl_exit_worst(lg) if v == "spy_b" and lab == LABEL[BASE] else NAN,
                       "premium_plus_fee": MULT * lg["ask"] + FEE
                       if lg["status"] == "priced" and lab == LABEL[BASE] else NAN,
                       "status": leg_status(v, lg), "bar_file": "", "bar_volume": NAN, "bar_low": NAN,
                       "bar_close": NAN}
                rows.append(row)
    return rows


FILL_PERIODS = (("2021-01-01..2026-10-20", PERIOD[0], PERIOD[1]),) + tuple(
    (f"{lo}..{hi}", lo, hi) for _, lo, hi in SUBPERIODS)


def _fills(items: list) -> dict:
    """items: (has a readable bar file, volume, low, ask, last, mid) per entry. Of the entries with a bar file: traded in
    the entry minute (volume > 0); of those, low <= ask; and the last trade minus the mid ($/share)."""
    ok = [it for it in items if it[0]]
    tr = [it for it in ok if it[1] > 0]
    lm = [it[4] - it[5] for it in tr]
    return {"entries_with_bar_file": len(ok), "entries_traded": len(tr),
            "share_traded": len(tr) / len(ok) if ok else None,
            "share_low_le_ask_of_traded": (sum(it[2] <= it[3] + 1e-9 for it in tr) / len(tr)) if tr else None,
            "mean_last_minus_mid": float(np.mean(lm)) if lm else None,
            "median_last_minus_mid": float(np.median(lm)) if lm else None}


def fill_check(rows: list, bar_list: dict, loader, spx_rows: dict, folder: Path) -> dict:
    """Every priced XSP base entry (ITM1, 15:51 ask): with a bar file that day; traded in the 15:51 minute (volume > 0);
    of those, the minute's low at or below the 15:51 ask; the minute's last trade minus the 15:51 mid ($/share). The
    same four numbers for SPX ITM10 on the same days (XSP entries with a readable bar file), from realprice_trades.csv's
    bar columns. Uses only the bar files that existed when the run started; never stops the run."""
    cache: dict = {}
    ent = []
    for r in rows:
        if r["version"] != "xsp" or r["strike_label"] != LABEL[BASE] or r["status"] != "priced":
            continue
        d = r["date"]
        if d not in cache:
            cache[d] = loader(d)
        bars, status = cache[d]
        r["bar_file"] = status
        if status == "ok":
            b = bars.get(ENTRY, {}).get((r["kind"], float(r["strike"])))
            if b is None or not b[2] > 0:
                r["bar_volume"] = 0.0
            else:
                r["bar_volume"], r["bar_low"], r["bar_close"] = b[2], b[0], b[1]
        ent.append(r)
    def xsp_item(r):
        return (r["bar_file"] == "ok", r["bar_volume"], r["bar_low"], r["entry_ask"], r["bar_close"], r["entry_mid"])

    def spx_item(q):
        return (q["bar_file"] == "ok", rp.fnum(q["bar_volume"]) or 0.0, rp.fnum(q["bar_low"]), float(q["ask"]),
                rp.fnum(q["bar_close"]), float(q["mid"]))

    def spx_ok(d):
        q = spx_rows.get(d)
        return q is not None and q["status"] == "priced" and q["bar_file"] == "ok"

    out = {}
    for name, lo, hi in FILL_PERIODS:
        E = [r for r in ent if lo <= r["date"] <= hi]
        ok = [r for r in E if r["bar_file"] == "ok"]
        x = {"entries_priced": len(E), **_fills([xsp_item(r) for r in E]),
             "days_with_bar_file": len({r["date"] for r in ok}),
             "entries_no_bar_file": sum(r["bar_file"] in ("missing", "none") for r in E),
             "entries_unreadable_file": sum(r["bar_file"] == "unreadable" for r in E)}
        # SPX ITM10 on the same days: the days of the XSP entries with a readable bar file, SPX entry priced there
        sp = [spx_rows[r["date"]] for r in ok if r["date"] in spx_rows and spx_rows[r["date"]]["status"] == "priced"]
        x["spx_itm10_same_days"] = {"entries_priced": len(sp), **_fills([spx_item(q) for q in sp])}
        # matched: days where both the XSP entry and the SPX entry are priced and both have a readable bar file
        m = [r for r in ok if spx_ok(r["date"])]
        x["matched_days"] = {"days": len(m), "xsp_itm1": _fills([xsp_item(r) for r in m]),
                             "spx_itm10": _fills([spx_item(spx_rows[r["date"]]) for r in m])}
        out[name] = x
    files = sum(1 for v in bar_list.values() if v == "file")
    fo = Path(folder)
    return {"folder": str(fo.relative_to(ROOT)) if fo.is_relative_to(ROOT) else str(fo), "bar_files_at_start": files,
            "none_markers_at_start": sum(1 for v in bar_list.values() if v == "none"),
            "note": None if files else "no trade-bar files existed when the run started: the fill check was not computed",
            "periods": out}


# ------------------------------------------------------------------------------------------------
# outputs
# ------------------------------------------------------------------------------------------------
def _cell(v):
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return "" if not math.isfinite(v) else f"{v:.6f}".rstrip("0").rstrip(".")
    return v


def write_outputs(res: dict, rows: list, env: Env) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TRADE_COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: _cell(r[k]) for k in TRADE_COLUMNS})
    j = rp.jsonable(res)
    cfo.write_atomic(env.out_trades, buf.getvalue())
    cfo.write_atomic(env.out_json, json.dumps(j, indent=1, allow_nan=False) + "\n")
    cfo.write_atomic(env.out_md, render_md(j))


def _row(name, s) -> str:
    fm = rp.fm
    return (f"| {name} | {s['days']} | {fm(s['mean_per_day'])} | {fm(s['nw_t_per_day'])} | {s['trades']} | "
            f"{fm(s['mean_per_trade'])} | {fm(s['share_trades_won'], pct=True)} | {fm(s['median_trade'])} | "
            f"{fm(s['worst_trade'])} |")


HDR = ("| | Days | $/day | t | Trades | $/trade | Won | Median | Worst |", "|---|---|---|---|---|---|---|---|---|")


def render_md(res: dict) -> str:
    fm = rp.fm
    L = []
    w = L.append
    V, P, d, ck = res["verdicts"], res["primary"], res["descriptive"], res["checks"]
    w("# The 15:50 candle on cheaper contracts: XSP and SPY 0DTE options at real prices\n")
    w(f"Pre-registration `preregistration/spx_candle_mini.md` (SHA-256 `{res['prereg_sha256'][:16]}...`), period "
      f"{res['period'][0]} .. {res['period'][1]}. One contract at a time, real Databento OPRA quotes (the 15:51:00 and "
      "15:59:00 snapshots). Research only; nothing here is a trading recommendation.\n")
    w("## The two verdicts (never combined)\n")
    w(f"- **{V['xsp']['line']}**")
    w(f"- **{V['spy_b']['line']}**\n")
    if V["xsp"]["confirmed"]:
        w("XSP's result confirms the 15:50 rule at XSP's real asks, with index outcomes that were already known. It "
          "is not a fresh test of the signal.\n")
    w("What this is and is not:\n")
    w("- The SPX outcomes on 2021-2026 were already known (XSP settles to SPX / 10, and SPY tracks SPX). This measures "
      "the net result of the analogous contracts (mostly their spreads and fees, plus the $1 strike grid, their own "
      "pricing and, for SPY, tracking and the 15:59 exit), not whether the signal works.")
    w("- It is a fixed one-contract price study with assumed fees ($0.09 a contract; $0.74 as a descriptive case), not "
      "a simulation of a $500 account.")
    w("- Signals come from D1, a CFD, on days chosen with bars after the entry (the D1 keep set needs every bar 15:19 "
      "to 15:59); the results are conditional on it. A fill at the quoted ask ignores order size and fast minutes, "
      "and XSP's quoted size can be small.")
    w("- For SPY, a broker may close an expiring position in a small account before 15:59, or refuse the order; this "
      "study cannot model that. Check the broker's rules. SPY (b)'s verdict is conditional on the exits that were "
      "quoted at 15:59 (the worst case below shows how much that matters).")
    w("- XSP's settlement value here is SPX close / 10, unrounded: the plan's fixed rule and a proxy for the "
      "published value (the rounded version is below).\n")
    w("## Checks (each would have stopped the run)\n")
    oc = ck["official_close_check"]
    w(f"- Official SPX closes (Cboe) against Robinhood: {oc['overlap_days']} overlapping days, largest difference "
      f"{oc['max_abs_diff']:.4f} (compared in decimals; realprice's float check agrees: "
      f"{oc['realprice_float_check_agrees']}).")
    sc = ck["spy_close_check"]
    w(f"- SPY closes: all {sc['days']} SPY-sample days have one; SPY / official SPX close in "
      f"{fm(sc['ratio_min'], 5, sign=False)} .. {fm(sc['ratio_max'], 5, sign=False)} (bounds {SPY_RATIO_BOUNDS[0]} .. "
      f"{SPY_RATIO_BOUNDS[1]}).")
    w(f"- Signal check 1: equal to scan.py's F2 on all {ck['signal_check_1']['kept_days']} D1 kept days. Signal check "
      f"2: the same sign as the SPX confirmation trade list on all {ck['signal_check_2']['days_in_both']} days in "
      f"both ({ck['signal_check_2']['trade_list_days_not_in_d1']} trade-list days not among the D1 days).")
    rpd = ck["spx_reproduction"]
    w(f"- The SPX ITM10 per-day series rebuilt from `realprice_trades.csv` reproduces the SPX confirmation: "
      f"{rpd['got']['days']} days, {rpd['got']['trades']} trades, {fm(rpd['got']['mean_per_day'])} a day, t "
      f"{fm(rpd['got']['t'])} (expected {rpd['expected']}).")
    w("- Downloads complete for both roots (every D1 day has a file or a no-symbol-resolved marker).\n")
    w("## Base case, 2021-01-01 .. 2026-10-20\n")
    w("Per-day series: the trade's P&L on a priced signal day, 0 on a no-signal day, missing when not priced. $ per "
      "contract.\n")
    w(HDR[0])
    w(HDR[1])
    for v in VERSIONS:
        w(_row(V_NAME[v], P[v]))
        for sp, s in P[v]["subperiods"].items():
            w(_row(f"  {v} {sp}", s))
    sx = res["spx_itm10"]
    w(_row("SPX ITM10 (rebuilt, not repriced)", sx))
    for sp, s in sx["subperiods"].items():
        w(_row(f"  SPX {sp}", s))
    w("\nSignal days not priced (base case):\n")
    for v in VERSIONS:
        u = P[v]["unpriced"]
        w(f"- {V_NAME[v]}: {u['signal_days']} signal days, {u['priced']} priced; not priced: no spot {u['no_spot']}, "
          f"no quote {u['no_quote']}" + (f", no exit quote {u['no_exit_quote']}" if "no_exit_quote" in u else "") + ".")
    w("\n## Descriptive (decides nothing)\n")
    w("### 1-3. Other strikes, the mid, the $0.74 fee\n")
    w("| Version | Variant | Days | $/day | t | Trades | $/trade | Won | Median | Worst |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for v in VERSIONS:
        for name, s in d["strikes_mid_fee"][v]["rows"].items():
            w(f"| {v} " + _row(name, s))
    w("\nThe mid version buys at the 15:51 mid (SPY (b) also sells at the 15:59 mid); fees as in the base case ($0.09 "
      "once, or on each side for SPY (b)). $0.74 is charged per contract on each side for SPY (b).\n")
    w("### 4. By year (Newey-West within each slice)\n")
    w("| Version | Slice | Days | $/day | t | Trades | $/trade | Won | Median | Worst |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for v in VERSIONS + ("spx_itm10",):
        for y, s in d["by_year"][v].items():
            w(f"| {v} " + _row(y, s))
    w("\n### 5. Spread as a share of the premium ((ask - bid) / mid at 15:51, the contract bought)\n")
    w("| Root | Slice | Entries | Mean | Median | Paired days | Root on paired days (mean / median) | SPX ITM10 on "
      "paired days (mean / median) |")
    w("|---|---|---|---|---|---|---|---|")
    for name in ("xsp", "spy_entry"):
        for y, s in d["spread_share"][name].items():
            a, b, c = s["root"], s["root_on_paired_days"], s["spx_itm10_on_paired_days"]
            w(f"| {name} | {y} | {a['n']} | {fm(a['mean'], 3, sign=False)} | {fm(a['median'], 3, sign=False)} | "
              f"{b['n']} | {fm(b['mean'], 3, sign=False)} / {fm(b['median'], 3, sign=False)} | "
              f"{fm(c['mean'], 3, sign=False)} / {fm(c['median'], 3, sign=False)} |")
    w("\nSPY (b), the contract sold at 15:59 ((ask - bid) / mid at 15:59):\n")
    w("| Slice | Exits | Mean | Median |")
    w("|---|---|---|---|")
    for y, s in d["spread_share"]["spy_b_exit_1559"].items():
        w(f"| {y} | {s['n']} | {fm(s['mean'], 3, sign=False)} | {fm(s['median'], 3, sign=False)} |")
    w("\n### 6. Return per dollar of premium (sum of P&L / sum of 100 x ask, priced trades)\n")
    w("| Series | Trades | Sum P&L | Sum premium | Return per $ | Mean P&L | Mean premium |")
    w("|---|---|---|---|---|---|---|")

    def prow(name, s):
        w(f"| {name} | {s['trades']} | {fm(s['sum_pnl'])} | {fm(s['sum_premium'], sign=False)} | "
          f"{fm(s['return_per_dollar'], 4)} | {fm(s['mean_pnl'])} | {fm(s['mean_premium'], sign=False)} |")
    prow("SPX ITM10, all trades", d["return_per_premium"]["spx_itm10_all"])
    for v in VERSIONS:
        x = d["return_per_premium"][v]
        prow(f"{V_NAME[v]}", x["all"])
        prow(f"  {v} on the days both it and SPX traded", x["on_days_shared_with_spx"])
        prow("  SPX ITM10 on those days", x["spx_itm10_on_the_same_days"])
        prow(f"  SPX ITM10 on every day in the {V_ROOT[v]} sample", x["spx_itm10_on_days_in_root_sample"])
    w(f"\n### 7. Affordability (premium + entry fee <= ${AFFORD:.0f})\n")
    w("| Version | Priced trades | Affordable | Share | Skipped | Affordable-only: days | $/day | t | Trades | $/trade |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for v in VERSIONS:
        a = d["affordability"][v]
        s = a["affordable_only"]
        w(f"| {v} | {a['priced_trades']} | {a['affordable']} | {fm(a['share_affordable'], pct=True)} | "
          f"{a['entries_skipped_as_unaffordable']} | {s['days']} | {fm(s['mean_per_day'])} | {fm(s['nw_t_per_day'])} | "
          f"{s['trades']} | {fm(s['mean_per_trade'])} |")
    w("\nThis still does not simulate an account that shrinks after losses, or whether a broker accepts the order.\n")
    w("### 8. Paired with SPX / 10 (an overall comparison of the implementations, not a spread estimate)\n")
    w("| Version | Days in both samples | Root - SPX/10: days | mean | t | Before fees: days | mean | t |")
    w("|---|---|---|---|---|---|---|---|")
    for v in VERSIONS:
        p = d["paired_with_spx"][v]
        a, b = p["after_fees"], p["before_fees"]
        w(f"| {v} | {p['days_in_both_samples']} | {a['n']} | {fm(a['mean'])} | {fm(a['t'])} | {b['n']} | "
          f"{fm(b['mean'])} | {fm(b['t'])} |")
    w("\nSPY is about 0.0997 x SPX, not exactly SPX / 10; the scaling stays 1/10.\n")
    w("### 9. No implied spot: the same trade with ATM from D1 (ITM1; never enters a verdict)\n")
    w("| Version | No-spot signal days | Priced with D1 ATM | No quote | No exit quote | Fallback $/trade | Won | "
      "Series with fallback: days | $/day | t | Trades |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for v in VERSIONS:
        f = d["no_spot_fallback"][v]
        t, s = f["fallback_trades"], f["series_with_fallback"]
        w(f"| {v} | {f['no_spot_signal_days']} | {f['priced']} | {f['no_quote']} | {f['no_exit_quote']} | "
          f"{fm(t['mean'])} | {fm(t['share_won'], pct=True)} | {s['days']} | {fm(s['mean_per_day'])} | "
          f"{fm(s['nw_t_per_day'])} | {s['trades']} |")
    w("\n### 10. SPY (b): missing exits\n")
    wc = d["spy_b_worst_case"]
    w(f"Worst case (each of the {wc['trades_charged_full_premium']} entries with no 15:59 quote charged the full "
      "premium plus both fees):\n")
    w(HDR[0])
    w(HDR[1])
    w(_row("SPY (b) worst case", wc))
    for sp, s in wc["subperiods"].items():
        w(_row(f"  {sp}", s))
    zb = d["spy_b_exits_at_zero_bid"]
    w(f"\nExits valued at a 15:59 bid of 0 (an assumption, not a shown sale): {zb['n']}.\n")
    w("Entry cohort (every priced SPY ITM1 entry, and how many had a valid 15:59 quote):\n")
    w("| Slice | Priced entries | With a 15:59 quote | Share |")
    w("|---|---|---|---|")
    for y, s in d["spy_entry_cohort"].items():
        w(f"| {y} | {s['priced_entries']} | {s['with_1559_quote']} | {fm(s['share'], pct=True)} |")
    w("\n### 11. XSP settlement rounded half up to the cent\n")
    sc11 = d["xsp_settlement_cent"]
    w(HDR[0])
    w(HDR[1])
    w(_row("XSP, X rounded to the cent", sc11))
    w(f"\nLargest change of one trade's P&L against the unrounded X: {fm(sc11['max_abs_change_per_trade'], sign=False)}.\n")
    w("### 12. Counts\n")
    for root in ROOTS:
        c = d["counts"][root]
        keys = list(c["by_year"]["all"].keys())
        w(f"{root}:\n")
        w("| Year | " + " | ".join(k.replace("_", " ") for k in keys) + " |")
        w("|---|" + "---|" * len(keys))
        for y, row in c["by_year"].items():
            w(f"| {y} | " + " | ".join(str(row[k]) for k in keys) + " |")
        w(f"\nBy weekday: in the {root} sample but not the SPX sample {c['by_weekday']['in_sample_not_in_spx']}; in "
          f"the SPX sample but not the {root} sample {c['by_weekday']['in_spx_not_in_sample']}.\n")
    fc = res["fill_check"]
    w("## Fill check on XSP trade bars (descriptive; decides nothing)\n")
    w(f"Trade bars from `{fc['folder']}`: {fc['bar_files_at_start']} day files and {fc['none_markers_at_start']} "
      "no-symbol-resolved markers when the run started. A bar stamped 15:51 covers the trades in that minute; "
      "\"last\" is the minute's last trade. Prices per share. SPX ITM10 on the same days is read from "
      "`realprice_trades.csv`'s bar columns, not recomputed.\n")
    if fc.get("note"):
        w(f"**{fc['note']}.**\n")
    w("| Series | Period | Priced entries | With a bar file (days) | No file / unreadable | Traded in 15:51 | "
      "Low <= ask (of traded) | Last - mid, mean | Last - mid, median |")
    w("|---|---|---|---|---|---|---|---|---|")
    for per, s in fc["periods"].items():
        w(f"| XSP ITM1 | {per} | {s['entries_priced']} | {s['entries_with_bar_file']} ({s['days_with_bar_file']}) | "
          f"{s['entries_no_bar_file']} / {s['entries_unreadable_file']} | {s['entries_traded']} "
          f"({fm(s['share_traded'], pct=True)}) | {fm(s['share_low_le_ask_of_traded'], pct=True)} | "
          f"{fm(s['mean_last_minus_mid'], 3)} | {fm(s['median_last_minus_mid'], 3)} |")
        x = s["spx_itm10_same_days"]
        w(f"| SPX ITM10 on the XSP days with a bar file | {per} | {x['entries_priced']} | {x['entries_with_bar_file']} | | "
          f"{x['entries_traded']} ({fm(x['share_traded'], pct=True)}) | {fm(x['share_low_le_ask_of_traded'], pct=True)} | "
          f"{fm(x['mean_last_minus_mid'], 3)} | {fm(x['median_last_minus_mid'], 3)} |")
        mt = s["matched_days"]
        for lab, y in (("XSP ITM1, matched days", mt["xsp_itm1"]), ("SPX ITM10, matched days", mt["spx_itm10"])):
            w(f"| {lab} | {per} | {mt['days']} | {y['entries_with_bar_file']} | | {y['entries_traded']} "
              f"({fm(y['share_traded'], pct=True)}) | {fm(y['share_low_le_ask_of_traded'], pct=True)} | "
              f"{fm(y['mean_last_minus_mid'], 3)} | {fm(y['median_last_minus_mid'], 3)} |")
    w("\nDenominators: the XSP rows use every priced XSP entry (the share traded is of those with a readable bar file). "
      "\"SPX ITM10 on the XSP days with a bar file\" uses the SPX entries priced on the days of XSP entries with a "
      "readable bar file. \"Matched days\" are the days on which both entries are priced and both have a readable bar "
      "file. SPY has no fill check (SPY trade bars were not pulled).\n")
    w("## Notes\n")
    dm = res["data"]["d1_center_vs_download_manifest"]
    w(f"- Diagnostic: the D1 centre used by the no-spot fallback equals the download's centre on "
      + "; ".join(f"{r} {v['equal']} of {v['days']} sample days" if v else f"{r} (no manifest)" for r, v in dm.items())
      + ".")
    w("- Forward days (after 2026-10-20) are not included: their XSP and SPY quotes have not been downloaded. They will "
      "be reported in a separate table and never pooled with 2021-2026.")
    w("- The two verdicts are separate; neither supports a claim that \"at least one cheaper contract works\", and "
      "neither changes the SPX result.")
    w("- Nothing here is a trading recommendation.")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------------------------
# self-test on synthetic data only
# ------------------------------------------------------------------------------------------------
CBBO_HEADER = ("ts_recv,ts_event,rtype,publisher_id,instrument_id,side,price,size,flags,bid_px_00,ask_px_00,bid_sz_00,"
               "ask_sz_00,bid_pb_00,ask_pb_00,symbol")
OHLCV_HEADER = "ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol"


def _occ(root: str, expiry: str, kind: str, K: float) -> str:
    return f"{root:<6}{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{'C' if kind == 'call' else 'P'}{round(K * 1000):08d}"


def _ts(day: str, hm: str, sec: int = 0, frac: str = "000000000") -> str:
    t = datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), int(hm[:2]), int(hm[3:]), sec, tzinfo=ET)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + frac + "Z"


def _qline(ts: str, sym: str, bid: float, ask: float) -> str:
    return f"{ts},{ts},177,30,1,N,,0,0,{bid:.9f},{ask:.9f},10,10,0,0,{sym}"


def _tv(S: float, K: float) -> float:
    return 0.30 + 0.5 * math.exp(-abs(S - K))


def _mid(kind: str, S: float, K: float) -> float:
    return (max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)) + _tv(S, K)


def _quote(kind, S, K, h=0.05):
    m = round(_mid(kind, S, K), 6)
    return round(m - h, 6), round(m + h, 6)


def _quotes_text(root: str, day: str, center: float, hw: int, spots: dict, edits=None, extra=()) -> str:
    """Synthetic cbbo-1m file: strikes center +- hw, calls and puts, at each minute in `spots` ({HH:MM: spot}). Put-call
    parity holds exactly at the mids, so the implied spot is the minute's spot. edits[(hm, kind, K)] = (bid, ask) or
    None (drop the row). `extra` lines are appended."""
    edits = edits or {}
    lines = [CBBO_HEADER]
    for hm, S in spots.items():
        ts = _ts(day, hm)
        for K in np.arange(center - hw, center + hw + 1, 1.0):
            for kind in ("call", "put"):
                q = edits.get((hm, kind, float(K)), _quote(kind, S, float(K)))
                if q is None:
                    continue
                lines.append(_qline(ts, _occ(root, day, kind, float(K)), *q))
    lines.extend(extra)
    return "\n".join(lines) + "\n"


def _gz(path: Path, text: str) -> None:
    path.write_bytes(gzip.compress(text.encode()))


def selftest() -> None:
    close_gate()
    selftest_parser()
    selftest_pricing()
    selftest_series_and_verdict()
    selftest_gate()
    selftest_pipeline()
    close_gate()
    print("selftest: all checks passed")


def selftest_parser():
    # the root-parameterised parser gives the same result as realprice.parse_quotes on an SPXW file
    day = "2019-06-14"
    spx_text = _quotes_text("SPXW", day, 2890.0, 30, {"15:50": 2891.3, "15:51": 2892.1, "15:59": 2895.0},
                            edits={("15:51", "call", 2880.0): None, ("15:51", "put", 2905.0): (3.0, 2.0),
                                   ("15:59", "call", 2900.0): (0.0, 0.05)})
    K0 = _occ("SPXW", day, "call", 2890.0)
    extra = [_qline(_ts(day, "15:51", 30), K0, 1.0, 2.0),                                   # off the minute
             _qline(_ts(day, "15:51", 0, "000000001"), K0, 1.0, 2.0),                       # 1 ns late
             _qline(_ts("2019-06-15", "15:51"), K0, 1.0, 2.0),                              # another day
             _qline(_ts(day, "15:51"), _occ("SPXW", "2019-06-17", "call", 2890.0), 1, 2),   # another expiry
             _qline(_ts(day, "15:51"), K0, 7.0, 7.5),                                       # same instant: later wins
             _qline(_ts(day, "15:51"), K0, 9.0, 8.0),                                       # later but invalid: skipped
             _qline(_ts(day, "15:52"), K0, -1.0, 2.0),                                      # negative bid: invalid
             _qline(_ts(day, "15:53"), K0, 0.0, 0.0)]                                       # ask 0: invalid
    text = spx_text.rstrip("\n") + "\n" + "\n".join(extra) + "\n"
    mine, theirs = parse_quotes_root(text, day, "SPXW"), rp.parse_quotes(text, day)
    assert mine == theirs, "parser differs from realprice.parse_quotes on an SPXW file"
    q, n = mine
    assert n == {"rows": n["rows"], "invalid": 4, "other_expiry": 1, "off_minute": 3}, n
    assert q["15:51"][("call", 2890.0)] == (7.0, 7.5) and ("call", 2880.0) not in q["15:51"]
    assert ("put", 2905.0) not in q["15:51"] and q["15:59"][("call", 2900.0)] == (0.0, 0.05)
    assert set(q) == {"15:50", "15:51", "15:59"}
    # XSP and SPY symbols
    assert parse_symbol_root("XSP   250602C00594000", "XSP") == ("2025-06-02", "call", 594.0)
    assert parse_symbol_root("SPY   210104P00371500", "SPY") == ("2021-01-04", "put", 371.5)
    assert parse_symbol_root("SPXW  130405P01495000", "SPXW") == rp.parse_symbol("SPXW  130405P01495000")
    for sym, root in (("SPY   250602C00594000", "XSP"), ("XSP   250602C00594000", "SPY"),
                      ("XSP  250602C00594000", "XSP"), ("XSP   250602X00594000", "XSP")):
        try:
            parse_symbol_root(sym, root)
            raise AssertionError(f"accepted {sym!r} as {root}")
        except (ValueError, KeyError):
            pass
    xt = _quotes_text("XSP", "2025-06-02", 594.0, 8, {"15:51": 594.3})
    qx, nx = parse_quotes_root(xt, "2025-06-02", "XSP")
    assert len(qx["15:51"]) == 34 and nx["rows"] == 34 and abs(rp.implied_spot(qx["15:51"]) - 594.3) < 1e-6
    try:
        parse_quotes_root(xt, "2025-06-02", "SPY")
        raise AssertionError("a file of another root was accepted")
    except ValueError:
        pass
    # bars: the same as realprice.parse_bars on an SPXW file; XSP bars
    bl = [OHLCV_HEADER]
    for hm, K, lo, cl, vol, exp in (("15:51", 2890.0, 1.0, 1.2, 5, day), ("15:51", 2895.0, 2.0, 2.1, 0, day),
                                    ("15:52", 2890.0, 1.1, 1.3, 2, day), ("15:51", 2890.0, 9, 9, 9, "2019-06-21")):
        bl.append(f"{_ts(day, hm)},33,30,1,{cl},{cl},{lo},{cl},{vol},{_occ('SPXW', exp, 'call', K)}")
    bl.append(f"{_ts(day, '15:53')},33,30,1,1,1,,1,1,{_occ('SPXW', day, 'call', 2890.0)}")      # missing low
    btxt = "\n".join(bl) + "\n"
    assert parse_bars_root(btxt, day, "SPXW") == rp.parse_bars(btxt, day)
    b, bn = parse_bars_root(btxt, day, "SPXW")
    assert bn == {"rows": 5, "other_expiry": 1, "bad": 1} and b["15:51"][("call", 2890.0)] == (1.0, 1.2, 5.0)
    xb = btxt.replace("SPXW  ", "XSP   ").replace("C02890000", "C00289000").replace("C02895000", "C00289500")
    bx, bxn = parse_bars_root(xb, day, "XSP")
    assert bx["15:51"][("call", 289.0)] == (1.0, 1.2, 5.0) and bx["15:51"][("call", 289.5)][2] == 0.0
    assert bxn == {"rows": 5, "other_expiry": 1, "bad": 1}
    try:
        parse_bars_root(btxt, day, "XSP")
        raise AssertionError("a bar file of another root was accepted")
    except ValueError:
        pass


def selftest_pricing():
    # $1 ATM, halves up; ITM1 for calls and puts
    assert atm1(600.5) == 601.0 and atm1(600.49) == 600.0 and atm1(599.5) == 600.0 and atm1(600.0) == 600.0
    assert contract(1, 600.0, 1) == ("call", 599.0) and contract(-1, 600.0, 1) == ("put", 601.0)
    assert contract(1, 600.0, 2) == ("call", 598.0) and contract(-1, 600.0, 0) == ("put", 600.0)
    # parity: the implied spot is the median over the 3 strikes whose mids are closest, and needs bids above 0
    day = "2025-06-02"
    q, _ = parse_quotes_root(_quotes_text("XSP", day, 600.0, 8, {"15:51": 600.7}), day, "XSP")
    q51 = q["15:51"]
    assert abs(rp.implied_spot(q51) - 600.7) < 1e-6
    # an XSP up day: ATM from the implied spot (601), not the D1 centre (600); call 600 bought at the 15:51 ask
    rec = day_record("XSP", day, 1.0, q, 6012.3 / 10, 6012.3, 600.0)
    assert rec["atm"] == 601.0 and rec["d1_atm"] == 600.0 and rec["fallback"] is None
    lg = rec["legs"][1]
    b, a = _quote("call", 600.7, 600.0)
    assert (lg["kind"], lg["K"], lg["status"]) == ("call", 600.0, "priced") and abs(lg["ask"] - a) < 1e-9
    assert abs(lg["mid"] - (a + b) / 2) < 1e-9 and rec["legs"][2]["K"] == 599.0 and rec["legs"][0]["K"] == 601.0
    # settlement at SPX / 10, $0.09 once; the mid; $0.74
    assert abs(pnl("xsp", rec, lg) - (100 * (601.23 - 600.0 - a) - 0.09)) < 1e-9
    assert abs(pnl("xsp", rec, lg, price="mid") - (100 * (601.23 - 600.0 - (a + b) / 2) - 0.09)) < 1e-9
    assert abs(pnl("xsp", rec, lg, fee=FEE_HIGH) - (100 * (601.23 - 600.0 - a) - 0.74)) < 1e-9
    # a down day: put at ATM + 1 = 602, out of the money at settlement -> loses the premium
    rec = day_record("XSP", day, -1.0, q, 6012.3 / 10, 6012.3, 600.0)
    lg = rec["legs"][1]
    b, a = _quote("put", 600.7, 602.0)
    assert (lg["kind"], lg["K"]) == ("put", 602.0) and abs(pnl("xsp", rec, lg) - (100 * (0.7700000000000005 - a) - 0.09)) < 1e-6
    # settlement rounded half up to the cent, in decimals
    assert settle_cent(4567.85) == 456.79 and settle_cent(4567.84) == 456.78 and settle_cent(6012.3) == 601.23
    assert settle_cent(4567.95) == 456.80 and settle_cent(4567.849999) == 456.78
    # no implied spot (fewer than 3 strikes with both bids above 0): not priced, the D1 ATM fallback is built
    bad = {("15:51", "put", float(K)): (0.0, 0.4) for K in range(592, 609)}
    qn, _ = parse_quotes_root(_quotes_text("XSP", day, 600.0, 8, {"15:51": 600.7}, edits=bad), day, "XSP")
    rec = day_record("XSP", day, -1.0, qn, 601.0, 6010.0, 600.0)
    assert rec["spot"] is None and all(rec["legs"][o]["status"] == "no_spot" for o in OFFSETS)
    fb = rec["fallback"]
    assert (fb["kind"], fb["K"], fb["status"], fb["ask"]) == ("put", 601.0, "priced", 0.4)   # bid 0 is a valid quote
    assert np.isnan(pnl("xsp", rec, rec["legs"][1])) and abs(pnl("xsp", rec, fb) - (100 * (0 - 0.4) - 0.09)) < 1e-9
    # no quote: the contract is missing, or outside the downloaded band
    qd, _ = parse_quotes_root(_quotes_text("XSP", day, 600.0, 8, {"15:51": 600.7},
                                           edits={("15:51", "call", 600.0): None}), day, "XSP")
    rec = day_record("XSP", day, 1.0, qd, 601.0, 6010.0, 600.0)
    assert rec["legs"][1]["status"] == "no_quote" and rec["legs"][0]["status"] == "priced"
    qe, _ = parse_quotes_root(_quotes_text("XSP", day, 600.0, 2, {"15:51": 601.9}), day, "XSP")
    rec = day_record("XSP", day, -1.0, qe, 601.0, 6010.0, 600.0)                 # ATM 602, put 603 is outside 598..602
    assert rec["atm"] == 602.0 and rec["legs"][1]["status"] == "no_quote" and rec["legs"][0]["status"] == "priced"
    # SPY: the 15:51 ask and the 15:59 bid, $0.09 on both sides; (a) at the SPY close, $0.09 once
    sd = "2024-04-03"
    spots = {"15:51": 520.4, "15:59": 521.6}
    qs, _ = parse_quotes_root(_quotes_text("SPY", sd, 520.0, 10, spots,
                                           extra=[_qline(_ts(sd, "15:59", 30), _occ("SPY", sd, "call", 519.0), 9, 9.1)]),
                              sd, "SPY")
    rec = day_record("SPY", sd, 1.0, qs, 521.75, 5230.0, 520.0)
    lg = rec["legs"][1]
    b1, a1 = _quote("call", 520.4, 519.0)
    b9, a9 = _quote("call", 521.6, 519.0)
    assert rec["atm"] == 520.0 and (lg["kind"], lg["K"]) == ("call", 519.0) and lg["exit_status"] == "priced"
    assert abs(lg["exit_bid"] - b9) < 1e-9                                        # the 15:59:30 row is ignored
    assert abs(pnl("spy_b", rec, lg) - (100 * (b9 - a1) - 0.18)) < 1e-9
    assert abs(pnl("spy_b", rec, lg, fee=FEE_HIGH) - (100 * (b9 - a1) - 1.48)) < 1e-9
    assert abs(pnl("spy_b", rec, lg, price="mid") - (100 * ((a9 + b9) / 2 - (a1 + b1) / 2) - 0.18)) < 1e-9
    assert abs(pnl("spy_a", rec, lg) - (100 * (521.75 - 519.0 - a1) - 0.09)) < 1e-9
    assert pnl_exit_worst(lg) == pnl("spy_b", rec, lg)
    # SPY: no 15:59 quote -> not priced for (b) (counted), priced for (a); worst case charges premium + both fees
    qs2, _ = parse_quotes_root(_quotes_text("SPY", sd, 520.0, 10, spots, edits={("15:59", "call", 519.0): None}),
                               sd, "SPY")
    rec2 = day_record("SPY", sd, 1.0, qs2, 521.75, 5230.0, 520.0)
    lg2 = rec2["legs"][1]
    assert lg2["exit_status"] == "no_exit_quote" and np.isnan(pnl("spy_b", rec2, lg2))
    assert leg_status("spy_b", lg2) == "no_exit_quote" and leg_status("spy_a", lg2) == "priced"
    assert abs(pnl_exit_worst(lg2) - (-100 * a1 - 0.18)) < 1e-9 and np.isfinite(pnl("spy_a", rec2, lg2))
    # SPY: a valid 15:59 quote with bid 0 is an exit at 0
    qs3, _ = parse_quotes_root(_quotes_text("SPY", sd, 520.0, 10, spots, edits={("15:59", "call", 519.0): (0.0, 0.02)}),
                               sd, "SPY")
    lg3 = day_record("SPY", sd, 1.0, qs3, 521.75, 5230.0, 520.0)["legs"][1]
    assert lg3["exit_bid"] == 0.0 and abs(pnl_exit(lg3) - (100 * (0 - a1) - 0.18)) < 1e-9
    # SPY: an invalid (crossed) 15:59 quote is no exit quote
    qs4, _ = parse_quotes_root(_quotes_text("SPY", sd, 520.0, 10, spots, edits={("15:59", "call", 519.0): (3.0, 2.9)}),
                               sd, "SPY")
    assert day_record("SPY", sd, 1.0, qs4, 521.75, 5230.0, 520.0)["legs"][1]["exit_status"] == "no_exit_quote"
    # no signal / missing candle: no legs
    assert day_record("XSP", day, 0.0, q, 601.0, 6010.0, 600.0)["legs"] == {}
    assert day_record("XSP", day, NAN, q, 601.0, 6010.0, 600.0)["legs"] == {}
    # the previous-session ratio for the SPY D1 centre
    # the official-close check: exactly one cent passes (realprice's float compare rejects it), more stops, < 3 days stops
    cl = {"2024-04-01": 4000.01, "2024-04-02": 5000.0, "2024-04-03": 5100.5}
    rh = {"2024-04-01": (4000.0, "x"), "2024-04-02": (5000.0, "x"), "2024-04-03": (5100.5, "x")}
    oc = check_closes_exact(cl, rh)
    assert oc["overlap_days"] == 3 and abs(oc["max_abs_diff"] - 0.01) < 1e-12 and not oc["realprice_float_check_agrees"]
    assert check_closes_exact({k: v[0] for k, v in rh.items()}, rh)["realprice_float_check_agrees"]
    for cl2, rh2 in ((dict(cl, **{"2024-04-01": 4000.011}), rh), (cl, dict(list(rh.items())[:2]))):
        try:
            check_closes_exact(cl2, rh2)
            raise AssertionError("close check did not stop")
        except SystemExit as e:
            assert "official-close check failed" in str(e)
    pr = PrevRatio({"2024-04-01": 523.0, "2024-04-02": 520.0, "2024-04-03": 521.0},
                   {"2024-04-01": 5243.0, "2024-04-03": 5211.0})
    assert pr("2024-04-01") is None and pr("2024-04-03") == 523.0 / 5243.0 and pr("2024-04-04") == 521.0 / 5211.0


def selftest_series_and_verdict():
    recs = [{"s": 1.0, "v": 10.0}, {"s": -1.0, "v": NAN}, {"s": 0.0, "v": 99.0}, {"s": NAN, "v": 5.0}]
    x = series(recs, lambda r: r["v"])
    assert np.array_equal(np.nan_to_num(x, nan=-7), [10.0, -7, 0.0, -7])
    st = rp.describe(x, sarr(recs))
    assert st["days"] == 2 and st["trades"] == 1 and st["mean_per_day"] == 5.0 and st["nw_t_per_day"] is None
    assert not passes(st)                                                         # fewer than 8 days: t not computed
    assert not passes({"mean_per_day": 1.0, "nw_t_per_day": 1.99}) and passes({"mean_per_day": 1.0, "nw_t_per_day": 2.0})
    assert not passes({"mean_per_day": -1.0, "nw_t_per_day": 3.0}) and not passes({"mean_per_day": 0.0, "nw_t_per_day": 3.0})
    assert not passes(rp.describe(np.zeros(20), np.zeros(20)))                    # zero standard error
    rng = np.random.default_rng(1)
    y = rng.normal(5, 10, 300)
    assert passes(rp.describe(y, np.ones(300))) and not passes(rp.describe(y - 5, np.ones(300)))
    # the NW t is realprice's (lag 5, Bartlett 1 - j/6)
    e = y - y.mean()
    lrv = e @ e / 300 + sum(2 * (1 - j / 6) * (e[j:] @ e[:-j]) / 300 for j in range(1, 6))
    assert abs(rp.nw(y)["t"] - y.mean() / math.sqrt(lrv / 300)) < 1e-9
    # verdict lines say the plan's words
    assert "not confirmed on XSP at real prices" in verdict_line("xsp", st, False)
    assert "not confirmed on SPY at real prices" in verdict_line("spy_b", st, False)
    assert "CONFIRMED (selling at the 15:59 bid" in verdict_line("spy_b", st, True)


def selftest_gate():
    close_gate()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        f = tmp / "2025-06-02.csv.gz"
        _gz(f, CBBO_HEADER + "\n")
        for fn in (lambda: read_option_gz(f), lambda: read_option_csv(f),
                   lambda: load_day_bars_root("2025-06-02", {"2025-06-02": "file"}, tmp)):
            try:
                fn()
                raise AssertionError("an option file was read with the gate closed")
            except SystemExit as e:
                assert "refusing to read" in str(e)
        pre, led = tmp / "plan.md", tmp / "LEDGER.md"
        led.write_text("- nothing\n")
        for setup in ("missing", "unlisted"):
            if setup == "unlisted":
                pre.write_text("the plan\n")
            try:
                open_gate(pre, led)
                raise AssertionError("gate did not refuse")
            except SystemExit as e:
                assert "refusing to run" in str(e)
            assert _GATE["sha"] is None
        led.write_text(f"- t  {hashlib.sha256(pre.read_bytes()).hexdigest()}  plan.md\n")
        assert open_gate(pre, led) == hashlib.sha256(pre.read_bytes()).hexdigest()
        assert read_option_gz(f) == CBBO_HEADER + "\n"
        pre.write_text("the plan, edited\n")                                    # an edited plan no longer passes
        try:
            open_gate(pre, led)
            raise AssertionError("gate accepted an edited plan")
        except SystemExit:
            pass
        assert _GATE["sha"] is None
    close_gate()


# ---- the synthetic pipeline -------------------------------------------------------------------
SYN_DAYS = ["2021-03-01", "2021-03-02", "2021-03-03", "2021-03-04", "2022-06-06", "2022-06-07", "2022-06-08",
            "2022-06-09", "2023-05-01", "2023-05-02", "2023-05-03", "2023-05-04", "2024-04-01", "2024-04-02",
            "2024-04-03", "2024-04-04", "2025-02-03", "2025-02-04", "2025-02-05", "2025-02-06", "2026-01-05",
            "2026-01-06", "2026-01-07", "2026-01-08"]
SYN_SIG = {"2021-03-01": 1, "2021-03-02": -1, "2021-03-03": 0, "2021-03-04": -1, "2022-06-06": 1, "2022-06-07": 1,
           "2022-06-08": -1, "2022-06-09": -1, "2023-05-01": 1, "2023-05-02": 1, "2023-05-03": -1, "2023-05-04": 0,
           "2024-04-01": 1, "2024-04-02": 1, "2024-04-03": -1, "2024-04-04": 1, "2025-02-03": -1, "2025-02-04": 1,
           "2025-02-05": None, "2025-02-06": 1, "2026-01-05": -1, "2026-01-06": 1, "2026-01-07": -1, "2026-01-08": 0}
SYN_R = 0.0997


def _syn_level(i: int) -> float:
    return 4000.0 + 37.3 * i


def _syn_move(i: int) -> float:
    return [6.0, -9.0, 2.0, -12.5, 8.5, 4.0, -7.0, 3.0][i % 8]


def _syn_world(tmp: Path) -> dict:
    """Synthetic files for 24 days in 2021-2026 (see the comments), and the expected outcomes computed directly."""
    qx, qs, bx, sx = tmp / "xsp", tmp / "spy", tmp / "xsp_bars", tmp / "spx"
    for p in (qx, qs, bx, sx):
        p.mkdir()
    n = len(SYN_DAYS)
    O = np.full((n, 390), 100.0)
    H, L, C = O + 0.5, O - 0.5, O + 0.1
    k, k1 = scan.mi("15:50"), scan.mi("15:51")
    closes, spy_close, info = {}, {}, {}
    closes["2021-02-26"], spy_close["2021-02-26"] = 3990.0, round(3990.0 * SYN_R, 4)    # the first day's prev ratio
    for i, d in enumerate(SYN_DAYS):
        S = _syn_level(i)
        O[i, k1] = S
        s = SYN_SIG[d]
        if s is None:
            O[i, k] = H[i, k] = L[i, k] = C[i, k] = np.nan
        else:
            o = S - 1.0
            c = o + (1.0 if s > 0 else -1.0 if s < 0 else 0.2)
            O[i, k], C[i, k] = o, c
            H[i, k], L[i, k] = max(o, c) + (0.15 if s else 0.5), min(o, c) - (0.15 if s else 0.5)
        X = round(S + _syn_move(i), 2)
        if d != "2025-02-04":                                                      # no official close that day
            closes[d] = X
            spy_close[d] = round(X * SYN_R + 0.03, 4)
        info[d] = {"S": S, "X": X, "s": s}
    closes["2023-05-03"] = 4371.85                                                 # X / 10 = 437.185: a half cent
    info["2023-05-03"]["X"] = 4371.85
    spy_close["2023-05-03"] = round(4371.85 * SYN_R + 0.03, 4)
    prev = PrevRatio(spy_close, closes)
    none_x, none_s, none_spx = {"2021-03-02"}, {"2021-03-02", "2021-03-04"}, {"2026-01-06"}
    manifests = {"XSP": [], "SPY": []}
    for i, d in enumerate(SYN_DAYS):
        S, s = info[d]["S"], info[d]["s"]
        sx_ = S / 10 + 0.33 + (0.6 if d == "2021-03-01" else 0.0)                  # implied spot != D1 S / 10
        cx = float(math.floor(S / 10 + 0.5))
        r = prev(d)
        cy = float(math.floor(S * r + 0.5))
        sy_ = S * SYN_R + 0.27
        mv = 0.15 * (1 if (s or 0) >= 0 else -1)
        info[d].update(sx=sx_, cx=cx, cy=cy, sy=sy_, sy59=sy_ + mv)
        manifests["XSP"].append({"day": d, "center": cx})
        manifests["SPY"].append({"day": d, "center": cy})
        # XSP
        if d in none_x:
            (qx / f"{d}.none").write_text("no XSP contract expiring this day among the requested symbols\n")
            (bx / f"{d}.none").write_text("x\n")
        elif d == "2022-06-07":
            _gz(qx / f"{d}.csv.gz", CBBO_HEADER + "\n")                            # an empty file: no spot
        else:
            edits, extra = {}, []
            atm = atm1(sx_)
            if d == "2022-06-08":                                                  # every put bid 0 -> no implied spot
                edits = {("15:51", "put", float(K)): (0.0, round(_mid("put", sx_, K) + 0.05, 6))
                         for K in np.arange(cx - 8, cx + 9, 1.0)}
            if d == "2023-05-02":                                                  # the ITM1 call has no quote
                edits = {("15:51", "call", atm - 1): None}
            if d == "2023-05-03":                                                  # off-minute row; later row wins
                sym = _occ("XSP", d, "put", atm + 1)
                b0, a0 = _quote("put", sx_, atm + 1)
                extra = [_qline(_ts(d, "15:51", 30), sym, 0.01, 0.02), _qline(_ts(d, "15:51"), sym, b0, a0 + 0.20)]
            if d == "2024-04-04":                                                  # an unaffordable premium
                edits = {("15:51", "call", atm - 1): (4.0, 5.5)}
            _gz(qx / f"{d}.csv.gz", _quotes_text("XSP", d, cx, 8, {"15:50": sx_, "15:51": sx_, "15:59": sx_ + mv},
                                                 edits, extra))
        # SPY
        if d in none_s:
            (qs / f"{d}.none").write_text("none\n")
        else:
            edits = {}
            atm_y = atm1(sy_)
            Ky = atm_y - 1 if (s or 0) > 0 else atm_y + 1
            kind_y = "call" if (s or 0) > 0 else "put"
            if d == "2024-04-02":
                edits = {("15:59", kind_y, Ky): None}                              # no exit quote
            if d == "2024-04-03":
                edits = {("15:59", kind_y, Ky): (0.0, 0.03)}                       # exit at a bid of 0
            _gz(qs / f"{d}.csv.gz", _quotes_text("SPY", d, cy, 10, {"15:51": sy_, "15:59": sy_ + mv}, edits))
        # SPX k60 files (only their existence is used)
        if d in none_spx:
            (sx / f"{d}.none").write_text("x\n")
        else:
            _gz(sx / f"{d}.csv.gz", CBBO_HEADER + "\n")
    for root, folder in (("XSP", qx), ("SPY", qs)):
        (folder / "manifest.json").write_text(json.dumps({"days": manifests[root]}))
    # official closes (Cboe format), SPY closes, Robinhood closes for 4 days
    lines = ["DATE,SPX"] + [f"{d[5:7]}/{d[8:10]}/{d[:4]},{v:.6f}" for d, v in sorted(closes.items())]
    (tmp / "cboe.csv").write_text("\n".join(lines) + "\n")
    with open(tmp / "spy.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close", "source", "fetched_utc"])
        for d in sorted(spy_close):
            w.writerow([d, f"{spy_close[d]:.4f}", "synthetic", "x"])
    rh = {d: (closes[d], "live_x/spx_daily.json") for d in ("2026-01-05", "2026-01-07", "2026-01-08", "2025-02-06")}
    # the SPX confirmation trade list: a row for every SPX-calendar signal day; one not priced; noise rows
    spx_pnl = {}
    rows = []
    cal = [d for d in SYN_DAYS if d not in none_spx and d in closes]
    for j, d in enumerate(cal):
        s = info[d]["s"]
        if not s:
            continue
        st = "not_priced" if d == "2026-01-07" else "priced"
        p = round(-150.0 + 97.3 * ((j * 7) % 11), 2) if st == "priced" else None
        spx_pnl[d] = p
        ask = 10.0 + 0.1 * j
        bar = {"bar_file": "ok", "bar_volume": "3", "bar_low": f"{ask - 0.2:.2f}", "bar_close": f"{ask - 0.25:.2f}"} \
            if st == "priced" else {"bar_file": "", "bar_volume": "", "bar_low": "", "bar_close": ""}
        if d == "2021-03-04":
            bar.update(bar_volume="0", bar_low="", bar_close="")
        if d == "2023-05-03":
            bar.update(bar_file="unreadable", bar_volume="", bar_low="", bar_close="")
        rows.append({"config": "current", "cell": "15:50 body>=0.60 with ITM10", "date": d, "period": "confirmation",
                     "signal": str(s), "entry_minute": "15:51", "implied_spot": "1", "kind": "call" if s > 0 else "put",
                     "strike": "1", "ask": f"{ask:.2f}" if st == "priced" else "",
                     "mid": f"{ask - 0.3:.2f}" if st == "priced" else "",
                     "pnl_fee_0.09": f"{p:.2f}" if st == "priced" else "", "pnl_fee_0.74": "", "pnl_mid_fee_0.09": "",
                     "status": st, **bar})
    rows.append(dict(rows[0], config="chosen", signal=str(-int(rows[0]["signal"]))))  # another config: ignored
    rows.append(dict(rows[0], date="2019-06-14", period="discovery"))                  # another period: ignored
    cols = list(rows[0].keys())
    with open(tmp / "trades.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    # XSP trade bars: traded at or below the ask; traded above it; volume 0; an unreadable file; others missing
    def bars_file(d, recs):
        lines = [OHLCV_HEADER] + [f"{_ts(d, hm)},33,30,1,{cl},{cl},{lo},{cl},{vol},{_occ('XSP', d, kind, K)}"
                                  for hm, kind, K, lo, cl, vol in recs]
        _gz(bx / f"{d}.csv.gz", "\n".join(lines) + "\n")
    i0 = info["2021-03-01"]
    a0 = atm1(i0["sx"])
    b_, a_ = _quote("call", i0["sx"], a0 - 1)
    bars_file("2021-03-01", [("15:51", "call", a0 - 1, a_ - 0.05, (a_ + b_) / 2 + 0.02, 5),
                             ("15:52", "call", a0 - 1, 0.01, 0.01, 9)])               # another minute: not the entry
    i4 = info["2021-03-04"]
    a4 = atm1(i4["sx"])
    b4, a4_ = _quote("put", i4["sx"], a4 + 1)
    bars_file("2021-03-04", [("15:51", "put", a4 + 1, a4_ + 0.02, (a4_ + b4) / 2 + 0.06, 2)])
    i5 = info["2023-05-03"]
    bars_file("2023-05-03", [("15:51", "put", atm1(i5["sx"]) + 1, 0.01, 0.01, 0)])
    (bx / "2024-04-01.csv.gz").write_bytes(b"not a gzip file")
    pre, led = tmp / "plan.md", tmp / "LEDGER.md"
    pre.write_text("synthetic plan\n")
    led.write_text(f"- t  {hashlib.sha256(pre.read_bytes()).hexdigest()}  plan.md\n")
    P = scan.Panel(np.array(SYN_DAYS, dtype=object), O, H, L, C, np.full(n, np.nan), np.full(n, np.nan), {})
    env = Env(prereg=pre, ledger=led, quote_dirs={"XSP": qx, "SPY": qs}, bars_dir=bx, spx_dir=sx,
              closes_csv=tmp / "cboe.csv", spy_closes_csv=tmp / "spy.csv", realprice_trades=tmp / "trades.csv",
              rh_closes=lambda: dict(rh), load_panel=lambda: P,
              f2=lambda P_: np.asarray(scan.spec_by_id(F2_ID).signal(P_), float), expected_spx={},
              out_json=tmp / "out" / "results.json", out_md=tmp / "out" / "RESULTS.md",
              out_trades=tmp / "out" / "trades.csv", run_log=tmp / "out" / "run_log.txt",
              manifests={"XSP": qx / "manifest.json", "SPY": qs / "manifest.json"})
    # the SPX series and its statistics, computed directly from the definitions above
    xs = []
    for d in cal:
        s = info[d]["s"]
        xs.append(np.nan if s is None else 0.0 if s == 0 else (np.nan if spx_pnl[d] is None else spx_pnl[d]))
    xs = np.array(xs)
    fin = xs[np.isfinite(xs)]
    nwd = rp.nw(xs)
    env.expected_spx = {"days": int(fin.size), "trades": int(sum(1 for d in cal if info[d]["s"] and spx_pnl.get(d) is not None)),
                        "mean_per_day": round(float(fin.mean()), 2), "t": round(nwd["t"], 2)}
    return {"env": env, "info": info, "closes": closes, "spy_close": spy_close, "spx_pnl": spx_pnl, "cal": cal,
            "P": P, "rh": rh, "rows": rows}


def _expect_stop(env: Env, needle: str) -> None:
    close_gate()
    try:
        run(env)
    except SystemExit as e:
        assert needle in str(e), (needle, str(e))
        assert not env.out_json.exists(), "outputs were written by a stopped run"
        return
    finally:
        close_gate()
    raise AssertionError(f"the run did not stop ({needle})")


def selftest_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        W = _syn_world(tmp)
        env, info = W["env"], W["info"]
        # ---- the stop rules first (no outputs may be written) ----
        _expect_stop(dataclasses.replace(env, prereg=tmp / "no_plan.md"), "refusing to run")
        led2 = tmp / "LEDGER2.md"
        led2.write_text("- nothing\n")
        _expect_stop(dataclasses.replace(env, ledger=led2), "refusing to run")
        bad_rh = dict(W["rh"])
        bad_rh["2026-01-05"] = (W["closes"]["2026-01-05"] + 0.02, "x")
        _expect_stop(dataclasses.replace(env, rh_closes=lambda: dict(bad_rh)), "official-close check failed")
        _expect_stop(dataclasses.replace(env, rh_closes=lambda: {k: v for k, v in list(W["rh"].items())[:2]}),
                     "official-close check failed")
        _expect_stop(dataclasses.replace(env, closes_csv=tmp / "nope.csv"), "never downloads")

        def f2_bad(P_):
            s = np.asarray(scan.spec_by_id(F2_ID).signal(P_), float)
            s[3] = -s[3] if s[3] else 1.0
            return s
        _expect_stop(dataclasses.replace(env, f2=f2_bad), "signal check 1")
        for folder, name in ((env.quote_dirs["XSP"], "2023-05-01.csv.gz"), (env.quote_dirs["SPY"], "2021-03-02.none")):
            (folder / name).rename(tmp / "moved")
            try:
                _expect_stop(env, "download is incomplete")
            finally:
                (tmp / "moved").rename(folder / name)
        spy_text = env.spy_closes_csv.read_text()
        try:
            env.spy_closes_csv.write_text("\n".join(l for l in spy_text.splitlines() if not l.startswith("2024-04-02")) + "\n")
            _expect_stop(env, "SPY close check")
            env.spy_closes_csv.write_text(spy_text.replace(f"2024-04-02,{W['spy_close']['2024-04-02']:.4f}",
                                                           f"2024-04-02,{W['closes']['2024-04-02'] * 0.1015:.4f}"))
            _expect_stop(env, "SPY close check")
        finally:
            env.spy_closes_csv.write_text(spy_text)
        tr_text = env.realprice_trades.read_text()
        try:
            lines = tr_text.splitlines()
            i = next(j for j, l in enumerate(lines) if ",2022-06-06,confirmation,1," in l)
            env.realprice_trades.write_text("\n".join(lines[:i] + [lines[i].replace(",confirmation,1,", ",confirmation,-1,")]
                                                      + lines[i + 1:]) + "\n")
            _expect_stop(env, "signal check 2")
            env.realprice_trades.write_text("\n".join(lines[:i] + lines[i + 1:]) + "\n")
            _expect_stop(env, "SPX series rebuild")
            env.realprice_trades.write_text("\n".join(lines + [lines[i]]) + "\n")
            _expect_stop(env, "two rows for 2022-06-06")
        finally:
            env.realprice_trades.write_text(tr_text)
        for key, delta in (("days", 1), ("trades", -1), ("mean_per_day", 0.01), ("t", 0.01)):
            exp = dict(env.expected_spx)
            exp[key] = exp[key] + delta
            _expect_stop(dataclasses.replace(env, expected_spx=exp), "SPX reproduction")
        # ---- the full run ----
        close_gate()
        res = run(env)
        close_gate()
        selftest_pipeline_checks(res, W)


def selftest_pipeline_checks(res: dict, W: dict):
    env, info, closes = W["env"], W["info"], W["closes"]
    d = res["descriptive"]
    ck = res["checks"]
    assert ck["official_close_check"]["overlap_days"] == 4 and ck["signal_check_1"]["kept_days"] == 24
    assert ck["spx_reproduction"]["passed"] and ck["signal_check_2"]["days_in_both"] == len(
        [r for r in W["rows"] if r["config"] == "current" and r["period"] == "confirmation"])
    # the samples: XSP files except 2021-03-02 (.none) and 2025-02-04 (no close); SPY also not 2021-03-04
    xs_days = [x for x in SYN_DAYS if x not in ("2021-03-02", "2025-02-04")]
    sy_days = [x for x in xs_days if x != "2021-03-04"]
    c = d["counts"]
    assert c["XSP"]["by_year"]["all"]["sample_days"] == len(xs_days) == 22
    assert c["SPY"]["by_year"]["all"]["sample_days"] == len(sy_days) == 21
    assert c["XSP"]["by_year"]["all"]["no_symbol_resolved"] == 1 and c["SPY"]["by_year"]["all"]["no_symbol_resolved"] == 2
    assert c["XSP"]["by_year"]["all"]["file_no_official_close"] == 1 and c["XSP"]["by_year"]["2025"]["missing_candles"] == 1
    assert c["XSP"]["by_year"]["all"]["in_sample_not_in_spx"] == 1                     # 2026-01-06 (Tue)
    assert c["XSP"]["by_weekday"]["in_sample_not_in_spx"]["Tue"] == 1
    assert c["XSP"]["by_year"]["all"]["in_spx_not_in_sample"] == 1                     # 2021-03-02 (Tue)
    assert c["SPY"]["by_weekday"]["in_spx_not_in_sample"] == {"Mon": 0, "Tue": 1, "Wed": 0, "Thu": 1, "Fri": 0}
    # XSP signal days: 22 sample days minus 3 no-signal (2021-03-03, 2023-05-04, 2026-01-08), minus 1 missing candle
    ux = res["primary"]["xsp"]["unpriced"]
    assert ux == {"signal_days": 18, "priced": 15, "no_spot": 2, "no_quote": 1}, ux
    uy = res["primary"]["spy_b"]["unpriced"]
    assert uy == {"signal_days": 17, "priced": 16, "no_spot": 0, "no_quote": 0, "no_exit_quote": 1}, uy
    assert res["primary"]["spy_a"]["unpriced"] == {"signal_days": 17, "priced": 17, "no_spot": 0, "no_quote": 0}
    assert c["SPY"]["by_year"]["2024"]["no_exit_quote"] == 1 and c["SPY"]["by_year"]["all"]["priced (entry)"] == 17
    # the XSP per-day series computed directly: up -> call at ATM - 1, down -> put at ATM + 1, 15:51 ask, X = close / 10
    exp_x, exp_s = [], []
    for day in xs_days:
        i = info[day]
        s = i["s"]
        exp_s.append(np.nan if s is None else float(s))
        if s is None:
            exp_x.append(np.nan)
            continue
        if s == 0:
            exp_x.append(0.0)
            continue
        if day in ("2022-06-07", "2022-06-08", "2023-05-02"):
            exp_x.append(np.nan)
            continue
        atm = atm1(i["sx"])
        kind, K = ("call", atm - 1) if s > 0 else ("put", atm + 1)
        b, a = _quote(kind, i["sx"], K)
        if day == "2023-05-03":
            a = a + 0.20                                                           # the later row won
        if day == "2024-04-04":
            a = 5.5
        X = closes[day] / 10
        exp_x.append(100 * ((max(X - K, 0) if kind == "call" else max(K - X, 0)) - a) - 0.09)
    exp_x = np.array(exp_x)
    st = rp.describe(exp_x, np.array(exp_s))
    got = res["primary"]["xsp"]
    for key in ("days", "trades"):
        assert got[key] == st[key], (key, got[key], st[key])
    for key in ("mean_per_day", "nw_t_per_day", "mean_per_trade", "median_trade", "worst_trade", "share_trades_won"):
        assert abs(got[key] - st[key]) < 1e-6, (key, got[key], st[key])
    assert res["verdicts"]["xsp"]["confirmed"] == passes(st)
    assert res["verdicts"]["xsp"]["line"] == verdict_line("xsp", res["primary"]["xsp"], passes(st))
    # SPY (b) per trade on two special days; the trade CSV
    with open(env.out_trades, newline="") as fh:
        rd = csv.DictReader(fh)
        T = list(rd)
        assert rd.fieldnames == TRADE_COLUMNS
    R = {(r["version"], r["strike_label"], r["date"]): r for r in T}
    i3 = info["2024-04-03"]
    atm = atm1(i3["sy"])
    b, a = _quote("put", i3["sy"], atm + 1)
    r3 = R[("spy_b", "ITM1", "2024-04-03")]
    assert r3["status"] == "priced" and abs(float(r3["pnl_fee_0.09"]) - (100 * (0.0 - a) - 0.18)) < 1e-4
    assert abs(float(r3["pnl_fee_0.74"]) - (100 * (0.0 - a) - 1.48)) < 1e-4
    r2 = R[("spy_b", "ITM1", "2024-04-02")]
    assert r2["status"] == "no_exit_quote" and r2["pnl_fee_0.09"] == ""
    b2, a2 = _quote("call", info["2024-04-02"]["sy"], atm1(info["2024-04-02"]["sy"]) - 1)
    assert abs(float(r2["pnl_worst_case"]) - (-100 * a2 - 0.18)) < 1e-4
    assert R[("spy_a", "ITM1", "2024-04-02")]["status"] == "priced"
    i1 = info["2021-03-01"]
    r1 = R[("xsp", "ITM1", "2021-03-01")]
    assert float(r1["atm"]) == atm1(i1["sx"]) != float(r1["d1_atm"]) == i1["cx"]   # ATM from the implied spot
    assert r1["kind"] == "call" and float(r1["strike"]) == atm1(i1["sx"]) - 1
    assert R[("xsp", "ITM1", "2023-05-02")]["status"] == "no_quote" and R[("xsp", "ATM", "2023-05-02")]["status"] == "priced"
    assert R[("xsp", "ITM1", "2022-06-07")]["status"] == "no_spot"
    assert R[("xsp", "ITM1_d1_atm_no_spot_fallback", "2022-06-08")]["status"] == "priced"
    assert R[("xsp", "ITM1_d1_atm_no_spot_fallback", "2022-06-07")]["status"] == "no_quote"
    assert len({(r["version"], r["date"]) for r in T if r["strike_label"] == "ITM2"}) == 18 + 17 + 17
    # the D1-ATM fallback (descriptive 9)
    fbx = d["no_spot_fallback"]["xsp"]
    assert (fbx["no_spot_signal_days"], fbx["priced"], fbx["no_quote"]) == (2, 1, 0 + 1)
    i8 = info["2022-06-08"]
    Kf = i8["cx"] + 1
    exp_fb = 100 * (max(Kf - closes["2022-06-08"] / 10, 0) - round(_mid("put", i8["sx"], Kf) + 0.05, 6)) - 0.09
    assert abs(fbx["fallback_trades"]["mean"] - exp_fb) < 1e-6
    assert fbx["series_with_fallback"]["trades"] == got["trades"] + 1
    # settlement rounded to the cent: 2023-05-03 (X / 10 = 437.185 -> 437.19), a put in the money: 0.5 less
    r5 = R[("xsp", "ITM1", "2023-05-03")]
    K5 = float(r5["strike"])
    assert r5["kind"] == "put" and K5 > 437.19 and abs(float(r5["settle"]) - 437.185) < 1e-9
    assert abs(float(r5["pnl_settle_cent"]) - float(r5["pnl_fee_0.09"]) + 0.5) < 1e-4
    assert abs(d["xsp_settlement_cent"]["max_abs_change_per_trade"] - 0.5) < 1e-6
    # the mid and the $0.74 fee
    sm = d["strikes_mid_fee"]["xsp"]["rows"]
    assert abs(sm["ITM1, ask, $0.74"]["mean_per_trade"] - (got["mean_per_trade"] - 0.65)) < 1e-9
    assert sm["ITM1, ask, $0.09"] == {k: v for k, v in got.items() if k in sm["ITM1, ask, $0.09"]}
    assert abs(d["strikes_mid_fee"]["spy_b"]["rows"]["ITM1, ask, $0.74"]["mean_per_trade"]
               - (res["primary"]["spy_b"]["mean_per_trade"] - 1.30)) < 1e-9
    # affordability: the 2024-04-04 XSP trade costs $550.09 -> skipped (0, no trade)
    af = d["affordability"]["xsp"]
    assert af["priced_trades"] == 15 and af["affordable"] == 14 and af["entries_skipped_as_unaffordable"] == 1
    assert af["affordable_only"]["trades"] == 14 and af["affordable_only"]["days"] == got["days"]
    # the SPY (b) worst case and the entry cohort
    assert d["spy_b_worst_case"]["trades"] == 17 and d["spy_b_worst_case"]["trades_charged_full_premium"] == 1
    assert d["spy_entry_cohort"]["all"] == {"priced_entries": 17, "with_1559_quote": 16, "share": 16 / 17}
    assert d["spy_b_exits_at_zero_bid"]["days"] == ["2024-04-03"]
    # paired with SPX / 10 on a day: 2021-03-01 (both priced)
    pr = d["paired_with_spx"]["xsp"]
    xspx = W["spx_pnl"]["2021-03-01"]
    assert pr["days_in_both_samples"] == len([x for x in xs_days if x in W["cal"]])
    diffs = []
    pre = []
    for day in xs_days:
        if day not in W["cal"]:
            continue
        j = xs_days.index(day)
        s = info[day]["s"]
        sp = np.nan if s is None else 0.0 if s == 0 else (np.nan if W["spx_pnl"][day] is None else W["spx_pnl"][day])
        a = exp_x[j]
        diffs.append(a - sp / 10 if np.isfinite(a) and np.isfinite(sp) else np.nan)
        pre.append(np.nan if s is None else 0.0 if s == 0 else
                   ((a + 0.09) - (sp + 0.09) / 10 if np.isfinite(a) and np.isfinite(sp) else np.nan))
    assert abs(pr["after_fees"]["mean"] - rp.nw(diffs)["mean"]) < 1e-9 and pr["after_fees"]["n"] == rp.nw(diffs)["n"]
    assert abs(pr["before_fees"]["mean"] - rp.nw(pre)["mean"]) < 1e-9
    assert np.isfinite(xspx)
    # return per premium and the spread share (SPX: 2 x (ask - mid) / mid = 0.6 / mid)
    rpp = d["return_per_premium"]
    assert rpp["spx_itm10_all"]["trades"] == len([p for p in W["spx_pnl"].values() if p is not None])
    tr = [(float(r["pnl_fee_0.09"]), float(r["entry_ask"])) for r in T
          if r["version"] == "xsp" and r["strike_label"] == "ITM1" and r["status"] == "priced"]
    assert abs(rpp["xsp"]["all"]["return_per_dollar"] - sum(p for p, _ in tr) / (100 * sum(a for _, a in tr))) < 1e-6
    ss = d["spread_share"]["xsp"]["all"]
    assert ss["root"]["n"] == 15 and ss["spx_itm10_on_paired_days"]["n"] == ss["root_on_paired_days"]["n"] > 0
    spx_sh = [0.6 / (float(r["ask"]) - 0.3) for r in W["rows"] if r["config"] == "current" and r["status"] == "priced"
              and r["period"] == "confirmation" and R.get(("xsp", "ITM1", r["date"]), {}).get("status") == "priced"]
    assert abs(ss["spx_itm10_on_paired_days"]["mean"] - np.mean(spx_sh)) < 1e-6
    assert d["spread_share"]["spy_b_exit_1559"]["all"]["n"] == 16
    # the fill check: 2021-03-01 traded at/below the ask; 2021-03-04 above; 2023-05-03 volume 0; 2024-04-01 unreadable
    fc = res["fill_check"]["periods"]["2021-01-01..2026-10-20"]
    assert (fc["entries_priced"], fc["entries_with_bar_file"], fc["days_with_bar_file"], fc["entries_unreadable_file"],
            fc["entries_traded"]) == (15, 3, 3, 1, 2), fc
    assert fc["entries_no_bar_file"] == 11 and fc["share_traded"] == 2 / 3 and fc["share_low_le_ask_of_traded"] == 0.5
    assert abs(fc["mean_last_minus_mid"] - 0.04) < 1e-6 and abs(fc["median_last_minus_mid"] - 0.04) < 1e-6
    sx = fc["spx_itm10_same_days"]
    assert (sx["entries_priced"], sx["entries_with_bar_file"], sx["entries_traded"]) == (3, 2, 1), sx
    assert sx["share_low_le_ask_of_traded"] == 1.0 and abs(sx["mean_last_minus_mid"] - 0.05) < 1e-9
    mt = fc["matched_days"]                                    # 2021-03-01 and 2021-03-04 (2023-05-03: SPX unreadable)
    assert mt["days"] == 2 and mt["xsp_itm1"]["entries_with_bar_file"] == 2 and mt["xsp_itm1"]["entries_traded"] == 2
    assert mt["xsp_itm1"]["share_low_le_ask_of_traded"] == 0.5 and abs(mt["xsp_itm1"]["mean_last_minus_mid"] - 0.04) < 1e-6
    assert (mt["spx_itm10"]["entries_with_bar_file"], mt["spx_itm10"]["entries_traded"]) == (2, 1)
    assert abs(mt["spx_itm10"]["mean_last_minus_mid"] - 0.05) < 1e-9
    f22 = res["fill_check"]["periods"]["2021-01-01..2022-12-31"]
    assert f22["entries_with_bar_file"] == 2 and f22["entries_traded"] == 2 and f22["matched_days"]["days"] == 2
    # the variant columns are ITM1-only (not crossed with other strikes or the fallback)
    for r in T:
        if r["strike_label"] != "ITM1":
            assert r["pnl_fee_0.74"] == r["pnl_mid_fee_0.09"] == r["pnl_settle_cent"] == r["pnl_worst_case"] == "" \
                == r["premium_plus_fee"], r
    assert R[("xsp", "ATM", "2021-03-01")]["pnl_fee_0.09"] != "" and R[("xsp", "ITM1", "2021-03-01")]["pnl_fee_0.74"] != ""
    # return per premium: the other reading (every SPX trade on a day in the root's sample)
    assert rpp["xsp"]["spx_itm10_on_days_in_root_sample"]["trades"] == len(
        [x for x in xs_days if W["spx_pnl"].get(x) is not None])
    assert R[("xsp", "ITM1", "2023-05-03")]["bar_volume"] == "0" and R[("xsp", "ITM1", "2024-04-01")]["bar_file"] == "unreadable"
    assert R[("xsp", "ITM1", "2022-06-06")]["bar_file"] == "missing"
    # by year and subperiods are computed within each slice
    by = d["by_year"]["xsp"]
    assert by["2021"]["days"] + by["2022"]["days"] == by["2021-2022"]["days"] == got["subperiods"]["2021-2022"]["days"]
    assert sum(by[y]["trades"] for y in YEARS) == got["trades"]
    # the manifest diagnostic, outputs and the run log
    assert res["data"]["d1_center_vs_download_manifest"]["XSP"] == {"days": 22, "equal": 22}
    assert res["data"]["d1_center_vs_download_manifest"]["SPY"] == {"days": 21, "equal": 21}
    md = env.out_md.read_text()
    assert res["verdicts"]["xsp"]["line"] in md and res["verdicts"]["spy_b"]["line"] in md
    assert "not a simulation of a $500 account" in md and "Nothing here is a trading recommendation" in md
    assert "already known" in md and "broker may close" in md and "never combined" in md
    back = json.loads(env.out_json.read_text())
    assert back["verdicts"]["xsp"]["stats"]["trades"] == got["trades"] and back["prereg_sha256"]


# ------------------------------------------------------------------------------------------------
# main: every attempt is logged
# ------------------------------------------------------------------------------------------------
def _log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {text}\n")


def main_run(env: Env) -> dict:
    code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    _log(env.run_log, f"start run, mini.py sha256 {code}")
    try:
        res = run(env)
    except SystemExit as e:
        _log(env.run_log, f"stopped: {e}")
        raise
    except Exception as e:
        _log(env.run_log, f"crashed: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise SystemExit(1)
    _log(env.run_log, "completed: " + " || ".join(res["verdicts"][v]["line"] for v in ("xsp", "spy_b")))
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        r = main_run(default_env())
        print(r["verdicts"]["xsp"]["line"])
        print(r["verdicts"]["spy_b"]["line"])
        print(f"wrote {OUT_MD}, {OUT_JSON}, {OUT_TRADES}")
    else:
        raise SystemExit("usage: mini.py selftest | run")
