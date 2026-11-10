#!/usr/bin/env python
"""Forward log of the SPX close candle-scan candidates (descriptive only).

The pre-registration (preregistration/spx_close_candle_scan.md, read-only) says "Forward = Robinhood minute
data from 2026-10-21 on (descriptive only)". This script logs, for every full regular NYSE session, the frozen
candidates of backtests/spx_candle_scan/scan.py, computed the way scan.py computes them: float64 arithmetic on
the prices exactly as the source file stores them (no rounding).

  * F2_1m_1550_strong_body: the 15:50 one-minute candle has a strong body, |close - open| >= 0.6 x (high - low)
    with high > low (scan.py's float test, shape_strong_body); signal = sign(close - open). Holdout: passed
    the Holm test and the accuracy bar, but it overlaps the known P3 effect, so it is not a blind pass.
  * F1_1m_15:50: sign(close - open) of the 15:50 one-minute candle (any body). Holdout: passed the Holm test
    but not the accuracy bar (95% CI lower bound below its break-even); it also overlaps P3.
  * P3_reference: sign(ln(15:51 open / 15:50 open)) (the known effect, logged for reference).
  * F4_day_so_far (= P1; failed the holdout): sign(ln(15:49 open / 09:30 open)).
  The three 15:51 signals share the target r_bps = 1e4 x ln(15:59 bar close / 15:51 bar open); day-so-far
  uses r(15:49 open -> 15:59 close). hit = (sign(r) == frozen direction x signal); a day with r exactly 0 is
  counted separately (hit left blank) and also as a miss in a second column (scan.py's zero-as-miss
  sensitivity). Bars are labelled by their ET START time (the 15:50 bar covers 15:50:00-15:50:59), the
  convention of scan.py's Dukascopy D1 file; this is checked on the data on every run.

  Sensitivity (NOT the binding test): F2_1m_1550_strong_body_exact_decimal applies |body| >= 0.6 x range in
  exact decimal arithmetic to prices normalised to the source's precision (SPY rounded to 4 decimals, which
  removes Yahoo's float32 noise; Robinhood strings as given). It differs from the binding float test only at
  (near-)exact 60% ties and is reported separately.

Run (rebuilds every output from whatever data exists; the same inputs give byte-identical outputs):

    PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B analysis/candle_1550_forward.py

Inputs (local files only, read-only; no network, no connector):
  * SPY 1-minute regular-hours bars saved by the recorder: data/bars_1m/SPY_1m_YYYY-MM.csv (Yahoo).
  * Robinhood SPX index minute bars: data/spx_1549/live_*/spx_1m.json (forward collection) and
    data/spx_1549/robinhood/raw/*/spx_1m.json (earlier pulls, all before 2026-10-21). Bars flagged
    interpolated=true are gap-fill and are discarded. data/spx_1549/live_*/spx.csv (timestamped SPX quotes)
    is used only for the bar-label check.
  * Overlap consistency check: the Dukascopy D1 file and day set, read through scan.py's own loader and
    feature functions (scan.py is imported read-only by path; importing it writes nothing).
  * backtests/spx_candle_scan/candidates.json (frozen directions; must match candidates.sha256) and
    holdout.json (candidate status and the sample-size numbers quoted in FORWARD.md).

Outputs:
  data/spx_1549/forward/candle_1550_log.csv      one row per session day per source (skipped and no-data
                                                  sessions included, with the reason)
  data/spx_1549/forward/overlap_vs_dukascopy.csv  per overlap day: this log vs scan.py's D1 values
  data/spx_1549/forward/summary.json             tallies (FORWARD and OVERLAP kept apart), checks, decisions
  backtests/spx_candle_scan/FORWARD.md           plain-English status page

Nothing here is trading advice; the log is descriptive, as pre-registered.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import csv  # noqa: E402
import glob  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from functools import lru_cache  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import NamedTuple  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

# ------------------------------------------------------------------------------------------------
# paths and constants
# ------------------------------------------------------------------------------------------------
ROOT = Path("/Users/kv15/trading")
BARS_DIR = ROOT / "data" / "bars_1m"
SPY_GLOB = "SPY_1m_*.csv"
SPX_ROOT = ROOT / "data" / "spx_1549"
# order matters: a later pattern's bar replaces an earlier one for the same minute (live files win)
SPX_GLOBS = ("robinhood/raw/*/spx_1m.json", "live_*/spx_1m.json")
SPX_QUOTE_GLOB = "live_*/spx.csv"
D1_FILE = SPX_ROOT / "d1_usa500_rth_1m.csv.gz"
D1_DAYS = SPX_ROOT / "d1_days.csv"
SCAN_DIR = ROOT / "backtests" / "spx_candle_scan"
SCAN_PY = SCAN_DIR / "scan.py"
CAND_FILE = SCAN_DIR / "candidates.json"
CAND_SHA = SCAN_DIR / "candidates.sha256"
HOLDOUT_JSON = SCAN_DIR / "holdout.json"
PREREG = ROOT / "preregistration" / "spx_close_candle_scan.md"
OUT_DIR = SPX_ROOT / "forward"
FORWARD_MD = SCAN_DIR / "FORWARD.md"

LOG_NAME = "candle_1550_log.csv"
OVERLAP_NAME = "overlap_vs_dukascopy.csv"
SUMMARY_NAME = "summary.json"

ET = ZoneInfo("America/New_York")
FORWARD_START = "2026-10-21"                  # pre-registration: "Robinhood minute data from 2026-10-21 on"
HOLDOUT = ("2021-01-01", "2026-10-20")        # scan.py HOLDOUT; OVERLAP days lie inside it
N_MIN = 390
Z95 = 1.959963984540054
Z_ALPHA_ONE_SIDED = 1.6448536269514722        # scan.py's constants for its trades-needed formula
Z_POWER = 0.8416212335729143
SIX_TENTHS = Decimal("0.6")
SPX = "SPX_robinhood"
SPY = "SPY_recorder"
SOURCES = (SPX, SPY)
MIXED = "mixed_SPX_else_SPY"                  # per day: SPX if it has a full session, else SPY
MIXED_LABEL = "mixed_SPX_else_SPY (not pre-registered)"
SPY_DECIMALS = 4                              # used ONLY by the exact-decimal sensitivity (float32 noise removal)
SPY_MIN_FETCH_DELAY = timedelta(minutes=6)    # a SPY bar is kept only if fetched >= 5 min after it ended
STALE_MIN_FLAT = 3                            # skip a day if >= 3 of the bars 15:49..15:59 have high == low
OHLC_SPY = ("open", "high", "low", "close")
OHLC_RH = ("open_value", "high_value", "low_value", "close_value")


def mi(hhmm_: str) -> int:
    """Minute index of the bar that BEGINS at hh:mm ET (09:30 -> 0, 15:59 -> 389)."""
    h, m = map(int, hhmm_.split(":"))
    return h * 60 + m - (9 * 60 + 30)


def hhmm(k: int) -> str:
    t = 9 * 60 + 30 + int(k)
    return f"{t // 60:02d}:{t % 60:02d}"


I0930, I1549, I1550, I1551, I1559 = mi("09:30"), mi("15:49"), mi("15:50"), mi("15:51"), mi("15:59")
REQUIRED = tuple(range(I1549, I1559 + 1))     # a day is used only if every bar 15:49..15:59 is present
SHAPE_MINUTES = tuple(range(mi("09:31"), mi("15:58") + 1))

# signal id -> target key; the target key names the entry bar
SIGNALS = (
    ("F2_1m_1550_strong_body", "r1551"),
    ("F1_1m_15:50", "r1551"),
    ("P3_reference", "r1551"),
    ("F4_day_so_far", "r1549"),
)
SB = "F2_1m_1550_strong_body"
SB_EXACT = "F2_1m_1550_strong_body_exact_decimal"
SENSITIVITY = ((SB_EXACT, "r1551"),)          # reported separately; never the headline
ALL_SIGNALS = SIGNALS + SENSITIVITY
SHORT = {"F2_1m_1550_strong_body": "sb", "F1_1m_15:50": "f1", "P3_reference": "p3", "F4_day_so_far": "dsf",
         SB_EXACT: "sbx"}

# candidate status, copied from holdout.json in case it cannot be read (the live values are read every run)
STATUS_FALLBACK = {
    "F2_1m_1550_strong_body": {"passes_holm": True, "p_holm": 6.282041659989389e-05, "hit_rate": 0.5745341614906833,
                               "accurate": True, "ci_lower": 0.5360177849163231, "breakeven": 0.49518004381241787,
                               "overlaps_known_P3": True, "overlaps_known_P1": False, "blind_test": False},
    "F1_1m_15:50": {"passes_holm": True, "p_holm": 0.010877823547524982, "hit_rate": 0.5401662049861495,
                    "accurate": False, "ci_lower": 0.5143878846256181, "breakeven": 0.5154575551123196,
                    "overlaps_known_P3": True, "overlaps_known_P1": False, "blind_test": False},
    "F4_day_so_far": {"passes_holm": False, "p_holm": 0.526466507014383, "hit_rate": 0.48409405255878285,
                      "accurate": False, "ci_lower": 0.45841219315834725, "breakeven": 0.5102880531559109,
                      "overlaps_known_P3": False, "overlaps_known_P1": True, "blind_test": False},
}

# trades-needed fallback, copied from holdout.json (economics -> F2_1m_1550_strong_body, fee 0.09) in case it
# cannot be read; the live values are read from holdout.json on every run
REMINDER_FALLBACK = {"holdout_strong_body_days": 644, "holdout_days": 1446, "hit_rate": 0.5745341614906833,
                     "trades_needed_hit_vs_breakeven": 244, "trades_needed_hit_vs_size_neutral_breakeven": 483,
                     "trades_needed_option_pnl": 808, "trades_per_year": 112.23236514522823,
                     "breakeven_hit_rate": 0.49518004381241787,
                     "breakeven_hit_rate_size_neutral": 0.518182784842997}

DECISIONS = [
    "Sources are tallied separately. SPX_robinhood is the pre-registered forward source and the headline; "
    "SPY_recorder (Yahoo SPY bars the recorder saves every day) is a stand-in for the same signal. "
    "mixed_SPX_else_SPY is NOT pre-registered: a per-day fallback series (SPX on days with a full SPX session, "
    "SPY otherwise) that mixes two feeds which select different candles; it is shown last, for reference.",
    "Signals and targets use scan.py's own arithmetic: float64 on the prices exactly as the file stores them "
    "(Robinhood strings; SPY's float32-widened Yahoo numbers), with no rounding. On every D1 keep day this "
    "reproduces scan.py exactly (see the self-check). JSON numbers are parsed as decimals, never through a "
    "binary float first.",
    "DEVIATION, reported only as a sensitivity: F2_1m_1550_strong_body_exact_decimal applies |body| >= 0.6 x "
    "range in exact decimal arithmetic to prices normalised to the source's precision (SPY rounded to 4 "
    "decimals, Robinhood as given). It follows the pre-registration's literal '>=' at an exact 60% tie, where "
    "scan.py's float test can go either way (D1 2017-09-18; SPY 2026-10-05). Both tallies are in summary.json; "
    "FORWARD.md lists every day where they differ.",
    "Robinhood SPX minute files are read from data/spx_1549/live_*/ and also data/spx_1549/robinhood/raw/*/ "
    "(earlier pulls, all before 2026-10-21, so they only add OVERLAP days). For the same ET minute a live_* "
    "bar replaces a raw/ bar; disagreeing duplicates are counted in summary.json.",
    "Interpolated Robinhood bars (interpolated=true, gap-fill) are discarded before anything else, so a day "
    "whose 15:49-15:59 bars are gap-fill is skipped as missing bars.",
    "Bars beginning after 15:59 ET are discarded during ingestion and never used in signals or targets. For "
    "Robinhood their presence (not their prices) is recorded per file: the file that supplied the 15:59 bar "
    "must also contain a real bar after 15:59, otherwise the 15:59 bar may be unfinished and the day is "
    "skipped as possibly_unfinished_1559.",
    "A SPY bar is kept only if its fetched_at_utc is a parseable, timezone-aware time at least 5 minutes after "
    "the bar ended (bar start + 6 min); bars with a missing or invalid fetch time are dropped.",
    "Bars with a non-finite or non-positive price, or with high < max(open, close), low > min(open, close) or "
    "high < low, are dropped and counted. A day with 3 or more flat bars (high == low) in 15:49-15:59 is "
    "skipped as stale_bars.",
    "Sessions follow the NYSE calendar of backtests/spx_close_1549/build_d1.py: weekends, recurring holidays "
    "and its special closures (2012-10-29/30, 2018-12-05, 2025-01-09) are not sessions; half-days (13:00 "
    "early closes: day after Thanksgiving; Christmas Eve and July 3 when Monday-Thursday and not a holiday) "
    "are skipped even if bars exist. Every full forward session up to the latest date on disk gets a row per "
    "source; a source without data that day gets a no_data row, so coverage is visible.",
    "Directions are the frozen ones in candidates.json, read from the same bytes whose SHA-256 must match "
    "candidates.sha256 (all three are +1: the signal is the candle's own direction). P3 uses +1 as in "
    "scan.py's reference row.",
    "The target ends at the close of the 15:59 one-minute bar, as in scan.py, not at the official SPX "
    "settlement that 0DTE options pay on.",
    "FORWARD = date >= 2026-10-21; OVERLAP = earlier dates (inside the 2021-01-01..2026-10-20 holdout, so they "
    "are not out of sample and are used only for the consistency checks against scan.py's D1 values).",
]


# ------------------------------------------------------------------------------------------------
# NYSE calendar (rules copied from backtests/spx_close_1549/build_d1.py; not imported because that module
# imports the Dukascopy fetcher)
# ------------------------------------------------------------------------------------------------
SPECIAL_CLOSURES = {
    date(2012, 10, 29): "Hurricane Sandy",
    date(2012, 10, 30): "Hurricane Sandy",
    date(2018, 12, 5): "National Day of Mourning (G.H.W. Bush)",
    date(2025, 1, 9): "National Day of Mourning (Carter)",
}


def _easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> frozenset:
    out = set()
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:
        out.add(_observed(new_year))
    out.add(_nth_weekday(year, 1, 0, 3))
    out.add(_nth_weekday(year, 2, 0, 3))
    out.add(_easter(year) - timedelta(days=2))
    out.add(_nth_weekday(year, 5, 0, -1))
    if year >= 2022:
        out.add(_observed(date(year, 6, 19)))
    out.add(_observed(date(year, 7, 4)))
    out.add(_nth_weekday(year, 9, 0, 1))
    out.add(_nth_weekday(year, 11, 3, 4))
    out.add(_observed(date(year, 12, 25)))
    out.update(d for d in SPECIAL_CLOSURES if d.year == year)
    return frozenset(out)


@lru_cache(maxsize=None)
def nyse_early_closes(year: int) -> frozenset:
    hol = nyse_holidays(year)
    out = {_nth_weekday(year, 11, 3, 4) + timedelta(days=1)}
    dec24 = date(year, 12, 24)
    if dec24.weekday() < 5 and dec24 not in hol:
        out.add(dec24)
    jul3 = date(year, 7, 3)
    if jul3.weekday() < 4 and jul3 not in hol:
        out.add(jul3)
    return frozenset(out)


def is_full_session(day: date) -> bool:
    return day.weekday() < 5 and day not in nyse_holidays(day.year) and day not in nyse_early_closes(day.year)


def forward_calendar(last: str | None) -> list:
    """Full NYSE sessions from FORWARD_START to `last` (inclusive), as ISO dates."""
    if last is None or last < FORWARD_START:
        return []
    out, d, end = [], date.fromisoformat(FORWARD_START), date.fromisoformat(last)
    while d <= end:
        if is_full_session(d):
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ------------------------------------------------------------------------------------------------
# small helpers
# ------------------------------------------------------------------------------------------------
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def rel(p: Path) -> str:
    p = Path(p).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def sgn(x) -> int:
    return (x > 0) - (x < 0)


def wilson(k: int, n: int, z: float = Z95):
    """Wilson score interval, the formula of scan.py's `wilson`."""
    if n <= 0:
        return None
    ph = k / n
    den = 1.0 + z * z / n
    centre = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return [centre - half, centre + half]


def n_needed_prop(p, p0):
    """scan.py's n_needed_prop: trades for a one-sided 5% test of a hit rate p vs p0 with 80% power."""
    if p is None or p0 is None or not p > p0 or not 0 < p0 < 1:
        return None
    num = Z_ALPHA_ONE_SIDED * math.sqrt(p0 * (1 - p0)) + Z_POWER * math.sqrt(p * (1 - p))
    return int(math.ceil((num / (p - p0)) ** 2))


def period_of(d: str) -> str:
    if d >= FORWARD_START:
        return "FORWARD"
    if HOLDOUT[0] <= d <= HOLDOUT[1]:
        return "OVERLAP"
    return "PRE_HOLDOUT"


def write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _price(x) -> Decimal:
    """A price exactly as stored (string, decimal or int); never through a binary float."""
    if isinstance(x, bool) or x is None or isinstance(x, float):
        raise ValueError(f"unexpected price value {x!r}")
    return Decimal(str(x).strip())


def bar_problem(bar) -> str | None:
    """None for a usable bar, else the diagnostics key under which it is dropped."""
    if not all(x.is_finite() for x in bar):
        return "non_finite_price_dropped"
    o, h, l_, c = bar
    if min(bar) <= 0:
        return "non_positive_price_dropped"
    if h < l_ or h < max(o, c) or l_ > min(o, c):
        return "inconsistent_ohlc_dropped"
    return None


# ------------------------------------------------------------------------------------------------
# readers: every reader returns FeedData with sessions = {ET date: {minute 0..389: (o, h, l, c) Decimals}}
# ------------------------------------------------------------------------------------------------
class FeedData(NamedTuple):
    sessions: dict
    files_by_date: dict
    diag: dict
    interp_by_date: dict
    close_check: dict | None      # SPX: {date: {"file_1559", "post_close_bar_in_that_file"}}; SPY: None


def _store(sessions, files_by_date, minute_src, diag, d, k, bar, src_file):
    old = sessions[d].get(k)
    if old is not None:
        diag["duplicate_minutes"] += 1
        if old != bar:
            diag["duplicate_minutes_with_different_prices"] += 1
    sessions[d][k] = bar
    minute_src[d][k] = src_file
    files_by_date[d].add(src_file)


def _label_counts(diag: dict, per_day_minutes: dict, prefix: str) -> None:
    first_label, last_label = Counter(), Counter()
    for _, ks in per_day_minutes.items():
        first_label[hhmm(min(ks))] += 1
        last_label[hhmm(max(ks))] += 1
    diag[f"first_{prefix}bar_label_et_counts"] = dict(sorted(first_label.items()))
    diag[f"last_{prefix}bar_label_et_counts"] = dict(sorted(last_label.items()))


def _parse_fetch(text) -> datetime | None:
    t = (text or "").strip()
    if not t:
        return None
    try:
        f = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    return f if f.tzinfo is not None else None


SPY_NEED = {"timestamp_utc", "timestamp_ny", "open", "high", "low", "close", "fetched_at_utc"}


def read_spy(files) -> FeedData:
    """Recorder CSVs (columns timestamp_utc, timestamp_ny, open, high, low, close, ..., fetched_at_utc). The ET
    label is computed from timestamp_utc with zoneinfo and must equal timestamp_ny (mismatches are counted). A
    bar is labelled by its START time; only bars beginning 09:30..15:59 ET are kept. A bar is kept only if its
    fetch time is known and at least 5 minutes after the bar ended, so an unfinished or not-yet-revised bar
    (e.g. a 15:59 bar fetched during the close) is never used. Prices are kept exactly as written."""
    sessions, files_by_date, minute_src, diag = defaultdict(dict), defaultdict(set), defaultdict(dict), Counter()
    per_day_minutes = defaultdict(set)
    for path in sorted(Path(p) for p in files):
        diag["files"] += 1
        with open(path, newline="") as f:
            rd = csv.DictReader(f)
            missing = SPY_NEED - set(rd.fieldnames or [])
            if missing:
                raise ValueError(f"{path}: missing columns {sorted(missing)}")
            for row in rd:
                diag["rows"] += 1
                t_utc = datetime.fromisoformat(row["timestamp_utc"].strip())
                if t_utc.tzinfo is None:
                    raise ValueError(f"{path}: naive timestamp_utc {row['timestamp_utc']!r}")
                et = t_utc.astimezone(ET)
                ny = datetime.strptime(row["timestamp_ny"].strip(), "%Y-%m-%d %H:%M:%S%z")
                if ny != et or ny.utcoffset() != et.utcoffset() or ny.replace(tzinfo=None) != et.replace(tzinfo=None):
                    diag["timestamp_ny_disagrees_with_utc"] += 1
                if et.second or et.microsecond:
                    diag["not_on_a_minute_dropped"] += 1
                    continue
                d = et.date().isoformat()
                k = et.hour * 60 + et.minute - (9 * 60 + 30)
                per_day_minutes[d].add(k)
                if k < 0:
                    diag["before_0930_dropped"] += 1
                    continue
                if k > I1559:
                    diag["after_1559_discarded"] += 1      # never stored, so never used in signals or targets
                    continue
                f_utc = _parse_fetch(row.get("fetched_at_utc"))
                if f_utc is None:
                    diag["fetch_time_missing_or_invalid_dropped"] += 1
                    continue
                if f_utc < t_utc + SPY_MIN_FETCH_DELAY:
                    diag["fetched_less_than_5min_after_bar_end_dropped"] += 1
                    continue
                try:
                    bar = tuple(_price(row[c]) for c in OHLC_SPY)
                except (ValueError, ArithmeticError):
                    diag["unparseable_price_dropped"] += 1
                    continue
                problem = bar_problem(bar)
                if problem:
                    diag[problem] += 1
                    continue
                _store(sessions, files_by_date, minute_src, diag, d, k, bar, rel(path))
    diag = dict(diag)
    _label_counts(diag, per_day_minutes, "")
    return FeedData(dict(sessions), {d: sorted(v) for d, v in files_by_date.items()}, diag, {}, None)


def _rh_bar_list(payload) -> list:
    """The SPX minute bars inside a Robinhood index-historicals payload (several shapes accepted)."""
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "begins_at" in payload[0]:
            return payload
        results = payload
    elif isinstance(payload, dict):
        body = payload.get("data", payload)
        if isinstance(body, dict) and "results" in body:
            results = body["results"]
        elif isinstance(body, dict) and "bars" in body:
            results = [body]
        else:
            results = []
    else:
        results = []
    out = []
    for res in results or []:
        if not isinstance(res, dict):
            continue
        if str(res.get("symbol", "SPX")).upper() != "SPX":
            continue
        if str(res.get("interval", "minute")).lower() not in ("minute", "1m", "1minute"):
            continue
        out.extend(res.get("bars") or [])
    return out


def is_interpolated(bar: dict) -> bool:
    v = bar.get("interpolated", False)
    return v is True or str(v).strip().lower() == "true"


def read_spx(files) -> FeedData:
    """Robinhood SPX minute JSON files (parsed with JSON numbers as decimals). begins_at is the bar's START in
    UTC; converted to ET with zoneinfo. Interpolated (gap-fill) bars are discarded; only bars beginning
    09:30..15:59 ET are stored. Files are read in the order given, a later file's bar replacing an earlier one
    for the same minute. A date whose bars are all interpolated still gets an (empty) session, so it is logged
    as skipped. Bars beginning after 15:59 are never parsed for prices; only their presence per (file, date)
    is recorded, as evidence that the file was saved after the 15:59 bar had finished."""
    sessions, files_by_date, minute_src, diag = defaultdict(dict), defaultdict(set), defaultdict(dict), Counter()
    per_day_minutes = defaultdict(set)
    interp_by_date = Counter()
    post_close = set()
    for path in [Path(p) for p in files]:
        diag["files"] += 1
        bars = _rh_bar_list(json.loads(Path(path).read_text(), parse_float=Decimal))
        for b in bars:
            diag["bars"] += 1
            t_utc = datetime.fromisoformat(str(b["begins_at"]).replace("Z", "+00:00"))
            if t_utc.tzinfo is None:
                raise ValueError(f"{path}: naive begins_at {b['begins_at']!r}")
            et = t_utc.astimezone(ET)
            if is_interpolated(b):
                diag["interpolated_dropped"] += 1
                k_i = et.hour * 60 + et.minute - (9 * 60 + 30)
                if 0 <= k_i <= I1559:
                    d_i = et.date().isoformat()
                    interp_by_date[d_i] += 1
                    files_by_date[d_i].add(rel(path))
                continue
            if et.second or et.microsecond:
                diag["not_on_a_minute_dropped"] += 1
                continue
            d = et.date().isoformat()
            k = et.hour * 60 + et.minute - (9 * 60 + 30)
            per_day_minutes[d].add(k)
            if k < 0:
                diag["before_0930_dropped"] += 1
                continue
            if k > I1559:
                diag["after_1559_discarded"] += 1          # prices never parsed; presence noted below
                post_close.add((rel(path), d))
                continue
            try:
                bar = tuple(_price(b[c]) for c in OHLC_RH)
            except (KeyError, ArithmeticError, ValueError, TypeError):
                diag["unparseable_price_dropped"] += 1
                continue
            problem = bar_problem(bar)
            if problem:
                diag[problem] += 1
                continue
            _store(sessions, files_by_date, minute_src, diag, d, k, bar, rel(path))
    for d in interp_by_date:
        sessions[d]                                        # noqa: B018  (creates an empty session if needed)
    close_check = {d: {"file_1559": minute_src[d][I1559],
                       "post_close_bar_in_that_file": (minute_src[d][I1559], d) in post_close}
                   for d in sessions if I1559 in sessions[d]}
    diag = dict(diag)
    _label_counts(diag, per_day_minutes, "real_")
    return FeedData(dict(sessions), {d: sorted(v) for d, v in files_by_date.items()}, diag, dict(interp_by_date),
                    close_check)


def spx_files(spx_root: Path = SPX_ROOT, patterns=SPX_GLOBS) -> list:
    out = []
    for pat in patterns:
        out.extend(sorted(Path(p) for p in glob.glob(str(Path(spx_root) / pat))))
    return out


def spx_quote_files(spx_root: Path = SPX_ROOT, pattern: str = SPX_QUOTE_GLOB) -> list:
    return sorted(Path(p) for p in glob.glob(str(Path(spx_root) / pattern)))


def spy_files(bars_dir: Path = BARS_DIR, pattern: str = SPY_GLOB) -> list:
    return sorted(Path(p) for p in glob.glob(str(Path(bars_dir) / pattern)))


# ------------------------------------------------------------------------------------------------
# one session -> signals (pure; reads ONLY the bars 09:30, 15:49, 15:50, 15:51 and 15:59)
# ------------------------------------------------------------------------------------------------
def classify(d: str, bars, unfinished_1559: bool = False) -> tuple[str, str, str]:
    """(status, skip_reason, detail). status 'ok' only for a full regular session with bars 15:49..15:59."""
    day = date.fromisoformat(d)
    if day.weekday() >= 5 or day in nyse_holidays(day.year):
        return "skipped", "not_an_nyse_session", "weekend or NYSE holiday/closure"
    if day in nyse_early_closes(day.year):
        return "skipped", "half_day", "NYSE 13:00 early close"
    missing = [k for k in REQUIRED if k not in bars]
    if missing:
        last = max(bars) if bars else None
        detail = (f"{len(missing)} of the 11 bars 15:49-15:59 missing (first missing {hhmm(missing[0])}); "
                  f"last bar {hhmm(last) if last is not None else 'none'}")
        return "skipped", "missing_bar_1549_1559", detail
    flat = [k for k in REQUIRED if bars[k][1] == bars[k][2]]
    if len(flat) >= STALE_MIN_FLAT:
        return "skipped", "stale_bars", f"{len(flat)} of the 11 bars 15:49-15:59 have high == low"
    if unfinished_1559:
        return ("skipped", "possibly_unfinished_1559",
                "the file that supplied the 15:59 bar has no real bar after 15:59, so it may have been saved "
                "before 16:00 ET; re-save it after 16:01 ET")
    return "ok", "", ""


def _score(trade: int, r_sign: int, r_bps: float) -> dict:
    """trade = frozen direction x signal in {-1, 0, +1}."""
    if trade == 0:
        return {"trade": 0, "hit": None, "hit_zero_as_miss": None, "signed_r_bps": None}
    if r_sign == 0:
        return {"trade": trade, "hit": None, "hit_zero_as_miss": 0, "signed_r_bps": 0.0}
    hit = int(r_sign == trade)
    return {"trade": trade, "hit": hit, "hit_zero_as_miss": hit, "signed_r_bps": trade * r_bps}


def strong_body_float(o: float, h: float, l_: float, c: float) -> int:
    """scan.py's shape_strong_body for one candle (float64, the binding test)."""
    body, rng = c - o, h - l_
    return sgn(body) if (rng > 0 and abs(body) >= 0.6 * rng) else 0


def compute_day(bars, directions: dict, price_decimals: int | None = None) -> dict:
    """Signals and targets of one full session. `bars` maps minute index -> (open, high, low, close) Decimals as
    stored in the source. Binding values use float64 as scan.py does; `price_decimals` only sets the
    normalisation of the exact-decimal sensitivity. Only the bars 09:30, 15:49, 15:50, 15:51 and 15:59 are
    looked up; nothing after 15:59."""
    o, h, l_, c = bars[I1550]
    of, hf, lf, cf = float(o), float(h), float(l_), float(c)
    strong = strong_body_float(of, hf, lf, cf)
    direction = sgn(cf - of)
    if price_decimals is None:
        on, hn, ln, cn = o, h, l_, c
    else:
        q = Decimal(1).scaleb(-price_decimals)
        on, hn, ln, cn = (x.quantize(q) for x in (o, h, l_, c))
    body_n, rng_n = cn - on, hn - ln
    strong_exact = sgn(body_n) if (rng_n > 0 and abs(body_n) >= SIX_TENTHS * rng_n) else 0
    o1551, o1549, exit_ = bars[I1551][0], bars[I1549][0], bars[I1559][3]
    o1551f, o1549f, exitf = float(o1551), float(o1549), float(exit_)
    p3 = sgn(math.log(o1551f / of))
    r1551 = 1e4 * math.log(exitf / o1551f)
    r1549 = 1e4 * math.log(exitf / o1549f)
    has_open = I0930 in bars
    o0930 = bars[I0930][0] if has_open else None
    dsf = sgn(math.log(o1549f / float(o0930))) if has_open else None
    body, rng = c - o, h - l_
    out = {"o_1550": o, "h_1550": h, "l_1550": l_, "c_1550": c, "body_1550": body, "range_1550": rng,
           "body_to_range": (abs(body) / rng) if rng > 0 else None,
           "strong_body": int(strong != 0), "direction_1550": direction,
           "body_exactly_60pct_normalised": int(rng_n > 0 and abs(body_n) == SIX_TENTHS * rng_n),
           "open_0930": o0930, "open_1549": o1549, "entry_1551_open": o1551, "exit_1559_close": exit_,
           "r1551_bps": r1551, "r1551_is_zero": int(r1551 == 0), "r1551_sign": sgn(r1551),
           "r1549_bps": r1549, "r1549_is_zero": int(r1549 == 0), "r1549_sign": sgn(r1549),
           "signals": {"F2_1m_1550_strong_body": strong, "F1_1m_15:50": direction, "P3_reference": p3,
                       "F4_day_so_far": dsf, SB_EXACT: strong_exact}}
    scores = {}
    for sid, tkey in ALL_SIGNALS:
        s = out["signals"][sid]
        if s is None:
            scores[sid] = {"trade": None, "hit": None, "hit_zero_as_miss": None, "signed_r_bps": None}
            continue
        dkey = SB if sid == SB_EXACT else sid
        scores[sid] = _score(directions.get(dkey, 1) * s, out[f"{tkey}_sign"], out[f"{tkey}_bps"])
    out["scores"] = scores
    return out


# ------------------------------------------------------------------------------------------------
# frozen candidates, candidate status and the scan module (read-only)
# ------------------------------------------------------------------------------------------------
class GateError(RuntimeError):
    pass


def frozen_directions(cand_file: Path = CAND_FILE, sha_file: Path = CAND_SHA) -> dict:
    if not Path(cand_file).exists() or not Path(sha_file).exists():
        raise GateError(f"refusing to run: {cand_file} or {sha_file} is missing")
    expected = Path(sha_file).read_text().split()[0].strip().lower()
    raw = Path(cand_file).read_bytes()                 # hash and parse the very same bytes
    actual = sha256_bytes(raw)
    if expected != actual:
        raise GateError(f"refusing to run: candidates.json SHA-256 {actual} != frozen {expected}")
    c = json.loads(raw.decode("utf-8"))
    dirs = {x["feature"]: int(x["direction"]) for x in c["candidates"]}
    want = {"F2_1m_1550_strong_body", "F1_1m_15:50", "F4_day_so_far"}
    if set(dirs) != want:
        raise GateError(f"frozen candidates {sorted(dirs)} are not the expected {sorted(want)}")
    if any(v not in (-1, 1) for v in dirs.values()):
        raise GateError(f"frozen directions {dirs} are not +-1")
    dirs["P3_reference"] = 1
    return {"directions": dirs, "sha256": actual}


def load_scan(scan_py: Path = SCAN_PY):
    """Import scan.py by path without writing a .pyc (it has no import-time side effects on disk)."""
    name = "spx_candle_scan_readonly"
    if name in sys.modules:
        return sys.modules[name]
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(name, scan_py)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod                          # dataclasses need the module registered
        try:
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return mod
    finally:
        sys.dont_write_bytecode = old


def candidate_status(holdout_json: Path = HOLDOUT_JSON) -> dict:
    """Holdout status of the frozen candidates (Holm pass, accuracy vs the $0.09-fee break-even, P3/P1 overlap)."""
    out = {k: dict(v, source="fallback constants (holdout.json not readable)") for k, v in STATUS_FALLBACK.items()}
    try:
        h = json.loads(Path(holdout_json).read_text())
        rows = {r["feature"]: r for r in h["holdout_test"]["rows"]}
        new = {}
        for sid in STATUS_FALLBACK:
            r = rows[sid]
            v = h["economics"]["candidates"][sid]["verdict_vs_breakeven"]["fee_0.09"]
            new[sid] = {"passes_holm": bool(r["passes_holm_5pct"]), "p_holm": r["p_holm"], "hit_rate": r["hit_rate"],
                        "accurate": bool(v["accurate_ci_lower_above_breakeven"]), "ci_lower": v["hit_rate_ci_lower"],
                        "breakeven": v["breakeven_hit_rate"], "overlaps_known_P3": bool(r.get("overlaps_known_P3")),
                        "overlaps_known_P1": bool(r.get("overlaps_known_P1")),
                        "blind_test": bool(r.get("holdout_is_blind_test")),
                        "source": f"{rel(holdout_json)} -> holdout_test.rows, economics (fee $0.09)"}
        out = new
    except (OSError, KeyError, ValueError, TypeError):
        pass
    return out


def plain_label(sid: str, status: dict) -> str:
    if sid == "P3_reference":
        return "P3 reference (15:50 open -> 15:51 open direction; known before the scan)"
    if sid == SB_EXACT:
        return "15:50 candle, strong body, exact-decimal test (sensitivity, not the binding test)"
    name = {"F2_1m_1550_strong_body": "15:50 candle, strong body", "F1_1m_15:50": "15:50 candle direction, any body",
            "F4_day_so_far": "Day so far, 09:30 open -> 15:49 open direction"}[sid]
    s = status.get(sid)
    if not s:
        return name
    if not s["passes_holm"]:
        tag = "failed the holdout test"
    elif s["accurate"]:
        tag = "passed the holdout test and the accuracy bar"
    else:
        tag = "passed the holdout test, not the accuracy bar"
    if s["overlaps_known_P3"]:
        tag += "; overlaps the known P3 effect, not a blind pass" if s["passes_holm"] else "; overlaps P3"
    if s["overlaps_known_P1"]:
        tag += "; this is the known P1"
    return f"{name} ({tag})"


def reminder_numbers(holdout_json: Path = HOLDOUT_JSON) -> dict:
    out = dict(REMINDER_FALLBACK, source="fallback constants (holdout.json not readable)")
    recent = None
    try:
        h = json.loads(Path(holdout_json).read_text())
        e = h["economics"]["candidates"]["F2_1m_1550_strong_body"]
        v = e["verdict_vs_breakeven"]["fee_0.09"]
        row = next(x for x in h["holdout_test"]["rows"] if x["feature"] == "F2_1m_1550_strong_body")
        out = {"holdout_strong_body_days": row["n_trades"], "holdout_days": row["n"], "hit_rate": row["hit_rate"],
               "trades_needed_hit_vs_breakeven": v["trades_needed_hit_vs_breakeven_80pct_power"],
               "trades_needed_hit_vs_size_neutral_breakeven": v["trades_needed_hit_vs_size_neutral_breakeven_80pct_power"],
               "trades_needed_option_pnl": e["holdout_points"]["fee_cases"]["fee_0.09"]["trades_needed_option_pnl_80pct_power"],
               "trades_per_year": e["holdout_trades_per_252_days"],
               "breakeven_hit_rate": v["breakeven_hit_rate"],
               "breakeven_hit_rate_size_neutral": v["breakeven_hit_rate_size_neutral"],
               "source": f"{rel(holdout_json)} -> economics.candidates.F2_1m_1550_strong_body (fee $0.09)"}
        sub = h["holdout_subperiods_NOT_TESTS"]["candidates"]["F2_1m_1550_strong_body"]["2023_2026"]
        need = sub["trades_needed_at_this_period_effect_80pct_power"]
        recent = {"period": f"{sub['first'][:4]}-{sub['last'][:4]}", "hit_rate": sub["hit_rate"],
                  "n_trades": sub["n_trades"],
                  "trades_needed_hit_vs_breakeven": n_needed_prop(sub["hit_rate"], out["breakeven_hit_rate"]),
                  "trades_needed_hit_vs_size_neutral_breakeven": need["hit_vs_own_size_neutral_breakeven"],
                  "size_neutral_breakeven_used": sub["own_breakeven_size_neutral_fee_0.09"],
                  "trades_needed_option_pnl": need["option_pnl"],
                  "source": (f"{rel(holdout_json)} -> holdout_subperiods_NOT_TESTS (2023_2026); the hit-rate-vs-"
                             "primary-break-even count uses scan.py's n_needed_prop with the 2021-2026 "
                             "break-even")}
    except (OSError, KeyError, ValueError, TypeError, StopIteration):
        pass
    out["holdout_strong_body_share"] = out["holdout_strong_body_days"] / out["holdout_days"]
    tpy = out["trades_per_year"]
    for blk in (out, recent):
        if blk is None:
            continue
        for k in ("trades_needed_hit_vs_breakeven", "trades_needed_hit_vs_size_neutral_breakeven",
                  "trades_needed_option_pnl"):
            blk[k.replace("trades_needed", "years_needed")] = None if blk.get(k) is None else blk[k] / tpy
    out["recent_effect"] = recent
    return out


# ------------------------------------------------------------------------------------------------
# log rows
# ------------------------------------------------------------------------------------------------
def _rec(d: str, source: str, status: str, reason: str, detail: str, bars=None, files: str = "",
         n_int: int = 0, evidence: str = "") -> dict:
    bars = bars or {}
    return {"date": d, "source": source, "period": period_of(d), "status": status, "skip_reason": reason,
            "skip_detail": detail, "source_files": files, "n_rth_bars": len(bars), "n_interpolated_dropped": n_int,
            "first_bar_et": hhmm(min(bars)) if bars else "", "last_bar_et": hhmm(max(bars)) if bars else "",
            "close_complete_evidence": evidence, "day": None}


def build_records(feed: FeedData, source: str, directions: dict, price_decimals: int | None = None,
                  check_close: bool = False, evidence_text: str = "") -> list:
    """One record per date in the feed. check_close=True (Robinhood): the 15:59 bar must come from a file that
    also holds a real bar after 15:59."""
    recs = []
    for d in sorted(feed.sessions):
        bars = feed.sessions[d]
        unfinished, evidence = False, evidence_text
        if check_close:
            cc = (feed.close_check or {}).get(d)
            if cc is not None:
                unfinished = not cc["post_close_bar_in_that_file"]
                evidence = "" if unfinished else f"real bar after 15:59 in {cc['file_1559']}"
        status, reason, detail = classify(d, bars, unfinished)
        n_int = feed.interp_by_date.get(d, 0)
        if status != "ok" and n_int:
            detail = f"{detail}; {n_int} interpolated bars discarded"
        rec = _rec(d, source, status, reason, detail, bars, ";".join(feed.files_by_date.get(d, [])), n_int,
                   evidence if status == "ok" else "")
        if status == "ok":
            rec["day"] = compute_day(bars, directions, price_decimals)
        recs.append(rec)
    return recs


def add_no_data_rows(recs: dict) -> list:
    """Give every full forward NYSE session up to the latest date on disk a row per source (no_data if the source
    has nothing that day). Returns the forward calendar used."""
    last = max((r["date"] for rs in recs.values() for r in rs), default=None)
    cal = forward_calendar(last)
    for src, rs in recs.items():
        have = {r["date"] for r in rs}
        for d in cal:
            if d not in have:
                rs.append(_rec(d, src, "skipped", "no_data", "no file on disk has a usable bar for this session"))
        rs.sort(key=lambda r: r["date"])
    return cal


def mixed_series(records_by_source: dict) -> list:
    by_date = defaultdict(dict)
    for src, recs in records_by_source.items():
        for r in recs:
            by_date[r["date"]][src] = r
    out = []
    for d in sorted(by_date):
        for src in SOURCES:
            r = by_date[d].get(src)
            if r is not None and r["status"] == "ok":
                out.append(r)
                break
    return out


LOG_COLUMNS = (
    ["date", "source", "period", "status", "skip_reason", "skip_detail", "source_files", "n_rth_bars",
     "n_interpolated_dropped", "first_bar_et", "last_bar_et", "close_complete_evidence",
     "o_1550", "h_1550", "l_1550", "c_1550", "body_1550", "range_1550", "body_to_range", "strong_body",
     "direction_1550", "entry_1551_open", "exit_1559_close", "r_bps", "r_is_zero"]
    + [f"{SHORT[s]}_{x}" for s, _ in SIGNALS[:3] for x in ("signal", "hit", "hit_zero_as_miss", "signed_r_bps")]
    + ["open_0930", "open_1549", "r1549_bps", "r1549_is_zero"]
    + [f"dsf_{x}" for x in ("signal", "hit", "hit_zero_as_miss", "signed_r_bps")]
    + ["body_exactly_60pct_normalised"]
    + [f"sbx_{x}" for x in ("signal", "hit", "hit_zero_as_miss", "signed_r_bps")]
)


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, float):
        return f"{v:.6f}"
    return str(v)


def log_row(rec: dict) -> dict:
    row = {c: "" for c in LOG_COLUMNS}
    for c in ("date", "source", "period", "status", "skip_reason", "skip_detail", "source_files", "n_rth_bars",
              "n_interpolated_dropped", "first_bar_et", "last_bar_et", "close_complete_evidence"):
        row[c] = _fmt(rec[c])
    day = rec["day"]
    if day is None:
        return row
    for c in ("o_1550", "h_1550", "l_1550", "c_1550", "body_1550", "range_1550", "strong_body",
              "body_exactly_60pct_normalised", "direction_1550", "entry_1551_open", "exit_1559_close", "open_0930",
              "open_1549"):
        row[c] = _fmt(day[c])
    row["body_to_range"] = _fmt(float(day["body_to_range"])) if day["body_to_range"] is not None else ""
    row["r_bps"] = _fmt(day["r1551_bps"])
    row["r_is_zero"] = _fmt(day["r1551_is_zero"])
    row["r1549_bps"] = _fmt(day["r1549_bps"])
    row["r1549_is_zero"] = _fmt(day["r1549_is_zero"])
    for sid, _ in ALL_SIGNALS:
        p = SHORT[sid]
        sc = day["scores"][sid]
        row[f"{p}_signal"] = _fmt(day["signals"][sid])
        row[f"{p}_hit"] = _fmt(sc["hit"])
        row[f"{p}_hit_zero_as_miss"] = _fmt(sc["hit_zero_as_miss"])
        row[f"{p}_signed_r_bps"] = _fmt(sc["signed_r_bps"])
    return row


def csv_text(rows: list, columns) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------
# tallies
# ------------------------------------------------------------------------------------------------
def tally(records: list, sid: str) -> dict:
    ok = [r for r in records if r["status"] == "ok"]
    trades = [r for r in ok if r["day"]["scores"][sid]["trade"] not in (None, 0)]
    undefined = sum(1 for r in ok if r["day"]["scores"][sid]["trade"] is None)
    n = len(trades)
    zero = sum(1 for r in trades if r["day"]["scores"][sid]["hit"] is None)
    k = sum(1 for r in trades if r["day"]["scores"][sid]["hit"] == 1)
    m = n - zero
    sr = [r["day"]["scores"][sid]["signed_r_bps"] for r in trades]
    return {"session_days": len(ok), "signal_undefined_days": undefined,
            "signal_days": n, "up_signals": sum(1 for r in trades if r["day"]["scores"][sid]["trade"] > 0),
            "down_signals": sum(1 for r in trades if r["day"]["scores"][sid]["trade"] < 0),
            "zero_r_days": zero, "hits": k, "misses": m - k, "hit_days_excluding_zero_r": m,
            "hit_rate": k / m if m else None, "hit_rate_wilson95": wilson(k, m),
            "hit_rate_zero_r_as_miss": k / n if n else None, "hit_rate_zero_r_as_miss_wilson95": wilson(k, n),
            "mean_signed_r_bps_per_signal_day": (sum(sr) / n) if n else None,
            "first_signal_date": trades[0]["date"] if trades else None,
            "last_signal_date": trades[-1]["date"] if trades else None}


def tallies(series: dict, period: str, sids=SIGNALS) -> dict:
    out = {}
    for name, recs in series.items():
        sel = [r for r in recs if r["period"] == period]
        out[name] = {sid: tally(sel, sid) for sid, _ in sids}
    return out


def exact_vs_binding_days(recs: list) -> list:
    """Days where the exact-decimal sensitivity and the binding float strong-body test disagree."""
    out = []
    for r in recs:
        if r["status"] != "ok":
            continue
        s = r["day"]["signals"]
        if s[SB] != s[SB_EXACT]:
            out.append({"date": r["date"], "source": r["source"], "period": r["period"], "binding": s[SB],
                        "exact_decimal": s[SB_EXACT],
                        "body_to_range": float(r["day"]["body_to_range"]) if r["day"]["body_to_range"] is not None
                        else None})
    return out


LATEST_N = 15


def latest_days(recs: list, n: int) -> list:
    out = []
    for r in [x for x in recs if x["status"] == "ok" and x["period"] == "FORWARD"][-n:]:
        day = r["day"]
        sb = day["scores"][SB]
        out.append({"date": r["date"], "source": r["source"],
                    "body_to_range": None if day["body_to_range"] is None else float(day["body_to_range"]),
                    "strong_body_signal": day["signals"][SB],
                    "direction_1550": day["direction_1550"], "r_bps": day["r1551_bps"],
                    "strong_body_hit": sb["hit"], "direction_hit": day["scores"]["F1_1m_15:50"]["hit"]})
    return out


def day_counts(recs: list) -> dict:
    ok = [r for r in recs if r["status"] == "ok"]
    sk = Counter(r["skip_reason"] for r in recs if r["status"] != "ok")
    fwd_sessions = [r for r in recs if r["period"] == "FORWARD"
                    and r["skip_reason"] not in ("not_an_nyse_session", "half_day")]
    return {"days_seen": len(recs), "days_ok": len(ok),
            "days_ok_forward": sum(1 for r in ok if r["period"] == "FORWARD"),
            "days_ok_overlap": sum(1 for r in ok if r["period"] == "OVERLAP"),
            "forward_sessions_on_calendar": len(fwd_sessions),
            "forward_sessions_logged": sum(1 for r in fwd_sessions if r["status"] == "ok"),
            "days_skipped": dict(sorted(sk.items())),
            "skipped_dates": [f"{r['date']} ({r['skip_reason']})" for r in recs if r["status"] != "ok"],
            "skipped_forward": [{"date": r["date"], "reason": r["skip_reason"], "last_bar_et": r["last_bar_et"]}
                                for r in recs if r["status"] != "ok" and r["period"] == "FORWARD"],
            "first_ok": ok[0]["date"] if ok else None, "last_ok": ok[-1]["date"] if ok else None}


# ------------------------------------------------------------------------------------------------
# overlap consistency check against scan.py's D1 values
# ------------------------------------------------------------------------------------------------
def _dec(x: float) -> Decimal:
    return Decimal(repr(float(x)))


def d1_reference(dates: list, d1_file: Path, d1_days: Path, scan_py: Path) -> tuple[dict, dict, dict]:
    """scan.py's own values on the D1 Dukascopy panel for the given OVERLAP dates, the D1 bars (for the lag and
    shape checks) and a self-check that this module's compute_day reproduces scan.py on those D1 days."""
    window = sorted(d for d in dates if HOLDOUT[0] <= d <= HOLDOUT[1])
    if not window:
        return {}, {}, {"status": "no overlap dates"}
    if not (Path(d1_file).exists() and Path(d1_days).exists()):
        return {}, {}, {"status": "D1 file or day set not found"}
    S = load_scan(scan_py)
    P = S.load_panel(window[0], window[-1], d1_file=Path(d1_file), days_file=Path(d1_days))
    feats = {"F2_1m_1550_strong_body": S.spec_by_id("F2_1m_1550_strong_body").signal(P),
             "F1_1m_15:50": S.spec_by_id("F1_1m_15:50").signal(P),
             "P3_reference": S.P3_REF.signal(P),
             "F4_day_so_far": S.spec_by_id("F4_day_so_far").signal(P)}
    t51 = S.target(P, "15:51") * 1e4
    t49 = S.target(P, "15:49") * 1e4
    ref, bars_by_date = {}, {}
    mism = Counter()
    bad_days, tie_days, exact_differs = [], [], []
    compared = 0
    for i, d in enumerate(P.dates):
        d = str(d)
        sig = {k: (None if not math.isfinite(float(v[i])) else int(v[i])) for k, v in feats.items()}
        ref[d] = {"signals": sig, "r1551_bps": float(t51[i]), "r1549_bps": float(t49[i])}
        bars = {}
        for k in range(N_MIN):
            vals = (P.O[i, k], P.H[i, k], P.L[i, k], P.C[i, k])
            if all(math.isfinite(float(v)) for v in vals):
                bars[k] = tuple(_dec(v) for v in vals)
        bars_by_date[d] = bars
        if all(k in bars for k in REQUIRED):
            compared += 1
            mine = compute_day(bars, {})
            bad = False
            for sid in feats:
                if mine["signals"][sid] != sig[sid]:
                    mism[sid] += 1
                    bad = True
            for key in ("r1551_bps", "r1549_bps"):
                if abs(mine[key] - ref[d][key]) > 1e-9:
                    mism[key] += 1
                    bad = True
            if bad:
                bad_days.append(d)
            if mine["body_exactly_60pct_normalised"]:
                tie_days.append(d)
            if mine["signals"][SB_EXACT] != mine["signals"][SB]:
                exact_differs.append(d)
    check = {"status": "ok", "d1_days_loaded": int(len(P.dates)), "window": [window[0], window[-1]],
             "dates_requested": len(window),
             "dates_not_in_d1_keep_set": sorted(set(window) - set(ref)),
             "self_check_this_module_vs_scan_py_on_d1": {
                 "what": "compute_day() run on the same D1 bars reproduces scan.py's signals and targets",
                 "days": compared, "mismatches": dict(mism), "days_with_any_mismatch": bad_days,
                 "exact_60pct_ties": tie_days, "exact_decimal_sensitivity_differs_on": exact_differs}}
    return ref, bars_by_date, check


def _pearson(a: list, b: list):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def _vals_from_rec(rec: dict) -> dict:
    day = rec["day"]
    return {"signals": dict(day["signals"]), "r1551_bps": day["r1551_bps"], "r1549_bps": day["r1549_bps"]}


def compare(a: dict, b: dict) -> tuple[dict, list]:
    """a, b: {date: {"signals": {...}, "r1551_bps", "r1549_bps"}}. Agreement rates on common dates."""
    common = sorted(set(a) & set(b))
    out = {"n_days": len(common), "dates": [common[0], common[-1]] if common else None}
    if not common:
        return out, []
    rows = []

    def rate(f):
        v = [f(d) for d in common]
        v = [x for x in v if x is not None]
        return {"agree": sum(v), "n": len(v), "rate": (sum(v) / len(v)) if v else None}

    sid = SB
    out["strong_body_flag_agreement"] = rate(lambda d: int(abs(a[d]["signals"][sid]) == abs(b[d]["signals"][sid])))
    out["strong_body_signal_agreement"] = rate(lambda d: int(a[d]["signals"][sid] == b[d]["signals"][sid]))
    conf = Counter()
    for d in common:
        fa, fb = a[d]["signals"][sid] != 0, b[d]["signals"][sid] != 0
        conf["both_strong" if fa and fb else "only_first" if fa else "only_second" if fb else "neither"] += 1
    out["strong_body_confusion"] = {k: conf.get(k, 0) for k in ("both_strong", "only_first", "only_second",
                                                                "neither")}
    out["strong_body_share_first"] = (conf["both_strong"] + conf["only_first"]) / len(common)
    out["strong_body_share_second"] = (conf["both_strong"] + conf["only_second"]) / len(common)
    both = [d for d in common if a[d]["signals"][sid] != 0 and b[d]["signals"][sid] != 0]
    out["strong_body_direction_agreement_when_both_strong"] = {
        "agree": sum(int(a[d]["signals"][sid] == b[d]["signals"][sid]) for d in both), "n": len(both)}
    out["direction_1550_agreement"] = rate(lambda d: int(a[d]["signals"]["F1_1m_15:50"] ==
                                                         b[d]["signals"]["F1_1m_15:50"]))
    out["p3_agreement"] = rate(lambda d: int(a[d]["signals"]["P3_reference"] == b[d]["signals"]["P3_reference"]))
    out["day_so_far_agreement"] = rate(
        lambda d: None if a[d]["signals"]["F4_day_so_far"] is None or b[d]["signals"]["F4_day_so_far"] is None
        else int(a[d]["signals"]["F4_day_so_far"] == b[d]["signals"]["F4_day_so_far"]))
    for key in ("r1551_bps", "r1549_bps"):
        xa = [a[d][key] for d in common]
        xb = [b[d][key] for d in common]
        out[f"{key}_pearson"] = _pearson(xa, xb)
        ag = sum(int(sgn(x) == sgn(y)) for x, y in zip(xa, xb))
        out[f"{key}_sign_agreement"] = {"agree": ag, "n": len(common), "rate": ag / len(common)}
        out[f"{key}_mean_abs_diff"] = sum(abs(x - y) for x, y in zip(xa, xb)) / len(common)
        out[f"{key}_median_abs_diff"] = statistics.median(abs(x - y) for x, y in zip(xa, xb))
    diffs = sorted(((abs(a[d]["r1551_bps"] - b[d]["r1551_bps"]), d) for d in common), reverse=True)
    out["largest_r1551_abs_diffs"] = [
        {"date": d, "first_bps": a[d]["r1551_bps"], "second_bps": b[d]["r1551_bps"], "abs_diff_bps": x,
         "opposite_signs": sgn(a[d]["r1551_bps"]) * sgn(b[d]["r1551_bps"]) < 0} for x, d in diffs[:3]]
    for d in common:
        rows.append((d, a[d], b[d]))
    return out, rows


def _bar_float(bar):
    return tuple(float(x) for x in bar)


def shape_check(first: dict, second: dict, dates) -> dict:
    """How often each feed's one-minute candles have a strong body (scan.py's float test), over every minute
    09:31-15:58 present in both feeds on the given dates. Descriptive; the frozen 0.6 cut-off is not changed."""
    per_day, ra, rb = [], [], []
    n = sa = sb = 0
    days = 0
    for d in dates:
        if d not in first or d not in second:
            continue
        ks = [k for k in SHAPE_MINUTES if k in first[d] and k in second[d]]
        if not ks:
            continue
        days += 1
        fa = [_bar_float(first[d][k]) for k in ks]
        fb = [_bar_float(second[d][k]) for k in ks]
        a = sum(1 for x in fa if strong_body_float(*x) != 0)
        b = sum(1 for x in fb if strong_body_float(*x) != 0)
        per_day.append((a - b) / len(ks))
        n, sa, sb = n + len(ks), sa + a, sb + b
        ra.extend(abs(c - o) / (h - l_) if h > l_ else -1.0 for o, h, l_, c in fa)
        rb.extend(abs(c - o) / (h - l_) if h > l_ else -1.0 for o, h, l_, c in fb)
    if not days:
        return {"n_days": 0}
    mean = sum(per_day) / days
    sd = statistics.stdev(per_day) if days > 1 else None
    t = mean / (sd / math.sqrt(days)) if sd else None
    share_a, share_b = sa / n, sb / n
    m = int(round(share_b * n))
    ra_sorted = sorted(ra, reverse=True)
    matched = ra_sorted[m - 1] if 1 <= m <= len(ra_sorted) else None
    return {"n_days": days, "n_minutes": n, "strong_share_first": share_a, "strong_share_second": share_b,
            "median_body_to_range_first": statistics.median(x for x in ra if x >= 0),
            "median_body_to_range_second": statistics.median(x for x in rb if x >= 0),
            "per_day_gap_mean": mean, "per_day_gap_sd": sd, "per_day_gap_t": t,
            "days_first_higher": sum(1 for x in per_day if x > 0), "days_first_lower": sum(1 for x in per_day if x < 0),
            "first_cutoff_matching_second_share": matched}


def _c2c(bars: dict) -> dict:
    """Close-to-close log return of bar k vs bar k-1 (both present)."""
    out = {}
    for k in range(1, I1559 + 1):
        if k in bars and k - 1 in bars:
            out[k] = math.log(float(bars[k][3]) / float(bars[k - 1][3]))
    return out


def label_lag_check(first: dict, second: dict, dates: list, lags=(-2, -1, 0, 1, 2)) -> dict:
    """Correlation of 1-minute close-to-close returns of `first` at minute t with `second` at t + lag, pooled
    over `dates`. If both are labelled the same way (bar START time), lag 0 is by far the largest."""
    res = {}
    rf = {d: _c2c(first[d]) for d in dates if d in first and d in second}
    rs = {d: _c2c(second[d]) for d in rf}
    for lag in lags:
        xa, xb = [], []
        for d in rf:
            for k, v in rf[d].items():
                w = rs[d].get(k + lag)
                if w is not None:
                    xa.append(v)
                    xb.append(w)
        res[str(lag)] = {"corr": _pearson(xa, xb), "n_pairs": len(xa)}
    best = max((lag for lag in res if res[lag]["corr"] is not None), key=lambda x: res[x]["corr"], default=None)
    return {"days": len(rf), "corr_by_lag_minutes": res, "best_lag": None if best is None else int(best),
            "labels_consistent": None if best is None else int(best) == 0}


def quote_in_bar_check(spx_sessions: dict, quote_files) -> dict:
    """Absolute label check: each timestamped SPX quote (live_*/spx.csv) must lie inside the [low, high] of the
    bar that STARTS in its minute. Also counted: how many would lie inside the bar labelled one minute later,
    which is where it would belong if bars were labelled by their END time."""
    n = inside = inside_end = bad_rows = no_bar = outside_rth = 0
    outside = []
    for p in quote_files:
        with open(p, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    t = datetime.fromisoformat((row.get("venue_timestamp_et") or "").strip())
                    q = Decimal((row.get("spx") or "").strip())
                except (ValueError, ArithmeticError):
                    bad_rows += 1
                    continue
                if t.tzinfo is None or not q.is_finite():
                    bad_rows += 1
                    continue
                et = t.astimezone(ET)
                k = et.hour * 60 + et.minute - (9 * 60 + 30)
                if not 0 <= k <= I1559:
                    outside_rth += 1
                    continue
                d = et.date().isoformat()
                bar = spx_sessions.get(d, {}).get(k)
                if bar is None:
                    no_bar += 1
                    continue
                n += 1
                if bar[2] <= q <= bar[1]:
                    inside += 1
                else:
                    outside.append({"time_et": et.isoformat(), "quote": str(q), "bar_low": str(bar[2]),
                                    "bar_high": str(bar[1])})
                nxt = spx_sessions.get(d, {}).get(k + 1)
                if nxt is not None and nxt[2] <= q <= nxt[1]:
                    inside_end += 1
    return {"files": [rel(p) for p in quote_files], "quotes_checked": n, "inside_start_labelled_bar": inside,
            "inside_bar_labelled_one_minute_later": inside_end, "outside_start_labelled_bar": outside[:10],
            "quotes_outside_0930_1559": outside_rth, "quotes_without_a_bar": no_bar, "unreadable_rows": bad_rows,
            "labels_consistent": None if n == 0 else inside == n}


def label_status(cons: dict) -> dict:
    checked, failed = [], []
    for name, v in sorted(cons.get("bar_label_check", {}).items()):
        if v.get("labels_consistent") is None:
            continue
        checked.append(name)
        if not v["labels_consistent"]:
            failed.append(name)
    q = cons.get("quote_in_bar_check") or {}
    if q.get("labels_consistent") is not None:
        checked.append("quote_in_bar_check")
        if not q["labels_consistent"]:
            failed.append("quote_in_bar_check")
    return {"status": "not checked" if not checked else ("failed" if failed else "ok"), "checked": checked,
            "failed": failed}


OVERLAP_COLUMNS = ["date", "source", "sb_source", "sb_d1", "dir1550_source", "dir1550_d1", "p3_source", "p3_d1",
                   "dsf_source", "dsf_d1", "r_bps_source", "r_bps_d1", "r1549_bps_source", "r1549_bps_d1"]


# ------------------------------------------------------------------------------------------------
# FORWARD.md
# ------------------------------------------------------------------------------------------------
def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _ci(ci) -> str:
    return "n/a" if not ci else f"{100 * ci[0]:.1f}-{100 * ci[1]:.1f}%"


def _bps(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def _rate_str(r: dict) -> str:
    if not r or r.get("n", 0) == 0:
        return "n/a"
    return f"{r['agree']}/{r['n']} ({_pct(r['rate'])})"


def _n_years(n, y) -> str:
    return "n/a" if n is None else f"{n:,} days (about {y:.1f} years)"


WHY = {"half_day": "half-day", "not_an_nyse_session": "not a session", "no_data": "no data on disk",
       "missing_bar_1549_1559": "a bar 15:49-15:59 is missing", "stale_bars": "stale (flat) bars",
       "possibly_unfinished_1559": "15:59 bar possibly unfinished (file saved before the close?)"}


def _forward_section(a, summary: dict) -> None:
    days, fw, status = summary["days"], summary["forward"], summary["candidate_status"]
    lab = summary["consistency_vs_dukascopy"].get("label_status", {})
    if lab.get("status") == "failed":
        a(f"> **Warning: the bar-label check failed ({', '.join(lab['failed'])}).** Until this is resolved the")
        a("> forward tallies below may be built on the wrong minute and should not be read.")
        a("")
    for src in SOURCES:
        dc = days[src]
        n, k = dc["forward_sessions_on_calendar"], dc["forward_sessions_logged"]
        fwd_skips = [f"{x['date']}: {WHY.get(x['reason'], x['reason'])}"
                     + (f", data ends {x['last_bar_et']}" if x["reason"] == "missing_bar_1549_1559" and x["last_bar_et"]
                        else "") for x in dc["skipped_forward"]]
        tag = " (pre-registered)" if src == SPX else " (stand-in)"
        a(f"- **{src}**{tag}: {k} of {n} forward NYSE session(s) logged"
          + (f"; not logged: {'; '.join(fwd_skips)}" if fwd_skips else "")
          + f". On disk in all: {dc['days_ok']} full sessions ({dc['days_ok_overlap']} overlap).")
    cal = summary.get("forward_calendar") or []
    if cal:
        a(f"- Forward NYSE sessions so far: {len(cal)} ({cal[0]} to {cal[-1]}, the latest date on disk).")
    a("")
    a("| Signal | Source | Forward days with a signal | Hits | Zero moves | Hit rate (95% CI) | Mean move in the signal's direction (bps) |")
    a("|---|---|---|---|---|---|---|")
    for sid, _ in SIGNALS:
        for src in SOURCES + (MIXED,):
            t = fw[src][sid]
            a(f"| {plain_label(sid, status)} | {MIXED_LABEL if src == MIXED else src} | {t['signal_days']} | "
              f"{t['hits']} | {t['zero_r_days']} | {_pct(t['hit_rate'])} ({_ci(t['hit_rate_wilson95'])}) | "
              f"{_bps(t['mean_signed_r_bps_per_signal_day'])} |")
    a("")
    sb = fw[SPX][SB]
    a(f"So far there are **{sb['signal_days']} strong-body forward day(s) in {SPX}**, the pre-registered source "
      f"({fw[SPY][SB]['signal_days']} in {SPY}, the stand-in). That is far too few to say anything.")
    a("")
    ex = summary["exact_decimal_sensitivity"]
    fwd_diff = [x for x in ex["differs_on"] if x["period"] == "FORWARD"]
    ovl_diff = [x for x in ex["differs_on"] if x["period"] != "FORWARD"]

    word = {1: "up", -1: "down", 0: "none"}

    def one(x):
        btr = "n/a" if x["body_to_range"] is None else f"{100 * x['body_to_range']:.4f}%"
        return (f"{x['date']} {x['source']} (binding test {word[x['binding']]}, exact-decimal "
                f"{word[x['exact_decimal']]}; body/range as stored {btr})")

    def dl(xs):
        return "; ".join(one(x) for x in xs)
    a("Exact-decimal sensitivity (not the binding test; it counts a body of exactly 60% of the range as strong "
      "after normalising the prices): "
      + (f"it differs from the binding test on {len(fwd_diff)} forward day(s): {dl(fwd_diff)}. Its forward tallies "
         f"are in `summary.json` (`forward_sensitivity_exact_decimal`)." if fwd_diff
         else "it agrees with the binding test on every forward day so far.")
      + (f" On overlap days it differs on {len(ovl_diff)}: {dl(ovl_diff)}." if ovl_diff else ""))
    a("")
    latest = summary["forward_days_latest"]
    if latest:
        a(f"Latest forward sessions (each source, up to {LATEST_N} rows):")
        a("")
        a("| Date | Source | 15:50 body / range | Strong body | 15:50 direction | Move 15:51 to 15:59 close (bps) | Strong body hit | Direction hit |")
        a("|---|---|---|---|---|---|---|---|")
        word = {1: "up", -1: "down", 0: "none", None: "n/a"}
        hitw = {1: "yes", 0: "no", None: "-"}
        for x in latest:
            a(f"| {x['date']} | {x['source']} | {_pct(x['body_to_range'])} | {word[x['strong_body_signal']]} | "
              f"{word[x['direction_1550']]} | {x['r_bps']:+.2f} | {hitw[x['strong_body_hit']]} | "
              f"{hitw[x['direction_hit']]} |")
        a("")


def _power_section(a, rem: dict) -> None:
    a("## How many strong-body days a firm answer would take (planning estimates)")
    a("")
    tpy = rem["trades_per_year"]
    rc = rem.get("recent_effect") or {}
    a(f"In 2021-2026 a strong body showed up on about {tpy:.0f} days a year (Dukascopy data). The table gives the")
    a("number of strong-body days a one-sided 5% test would need for 80% power, with the formula and inputs of")
    a("`holdout.json`. These are illustrative planning numbers, not deadlines. Each assumes that the true hit")
    a("rate equals a past period's, that strong bodies stay as frequent, and, for the break-evens, `scan.py`'s")
    a("option-cost model (half the realized-move-fair straddle, $0.10 half-spread, $0.09 fee). The break-evens")
    a("are model outputs, not observed option prices, and this log records no option P&L.")
    a("")
    a(f"| Question | If the 2021-2026 hit rate holds ({_pct(rem.get('hit_rate'))}) | "
      f"If the {rc.get('period', '2023-2026')} hit rate holds ({_pct(rc.get('hit_rate'))}) |")
    a("|---|---|---|")
    a(f"| Hit rate above the primary break-even ({_pct(rem['breakeven_hit_rate'])}) | "
      f"{_n_years(rem['trades_needed_hit_vs_breakeven'], rem['years_needed_hit_vs_breakeven'])} | "
      f"{_n_years(rc.get('trades_needed_hit_vs_breakeven'), rc.get('years_needed_hit_vs_breakeven') or 0)} |")
    a(f"| Hit rate above the size-neutral break-even ({_pct(rem['breakeven_hit_rate_size_neutral'])}) | "
      f"{_n_years(rem['trades_needed_hit_vs_size_neutral_breakeven'], rem['years_needed_hit_vs_size_neutral_breakeven'])} | "
      f"{_n_years(rc.get('trades_needed_hit_vs_size_neutral_breakeven'), rc.get('years_needed_hit_vs_size_neutral_breakeven') or 0)} |")
    a(f"| Mean option P&L per trade above zero | "
      f"{_n_years(rem['trades_needed_option_pnl'], rem['years_needed_option_pnl'])} | "
      f"{_n_years(rc.get('trades_needed_option_pnl'), rc.get('years_needed_option_pnl') or 0)} |")
    a("")
    a("The primary break-even is below 50% because moves on right days were bigger than on wrong days in")
    a("2021-2026, and the size of that pattern was not stable across periods; the size-neutral break-even does not")
    a("rely on it.")
    a(f"The {rc.get('period', '2023-2026')} size-neutral count uses that period's own size-neutral break-even, as in")
    a("`holdout.json`. A smaller sample still carries some information, and reaching these counts would not make")
    a("a conclusion certain. Until the sample is much larger, the tally is a descriptive record, and a short run")
    a("of hits or misses is weak evidence either way.")
    a("")


def _overlap_section(a, summary: dict) -> None:
    rem = summary["reminder"]
    cons = summary["consistency_vs_dukascopy"]
    a("## Does the data agree with the backtest data? (overlap days)")
    a("")
    if cons.get("status") != "ok":
        a(f"Not available: {cons.get('status')}.")
        a("")
        return
    a("On days before 2026-10-21 the same signals were computed from the Dukascopy US500 data that `scan.py`")
    a("used, with `scan.py`'s own code. Agreement with each forward source:")
    a("")
    a("| Check | SPX_robinhood vs Dukascopy | SPY_recorder vs Dukascopy | SPX vs SPY |")
    a("|---|---|---|---|")
    cmp_ = cons["comparisons"]
    keys = (f"{SPX}_vs_d1", f"{SPY}_vs_d1", f"{SPX}_vs_{SPY}")

    def cell(name, f):
        c = cmp_.get(name)
        return "n/a" if not c or not c.get("n_days") else f(c)
    rowdefs = [
        ("Days compared", lambda c: str(c["n_days"])),
        ("Strong body: same yes/no", lambda c: _rate_str(c["strong_body_flag_agreement"])),
        ("Strong body: same signal (up/down/none)", lambda c: _rate_str(c["strong_body_signal_agreement"])),
        ("Strong-body days: first feed / second feed", lambda c: f"{_pct(c['strong_body_share_first'])} / "
         f"{_pct(c['strong_body_share_second'])}"),
        ("15:50 direction: same", lambda c: _rate_str(c["direction_1550_agreement"])),
        ("P3: same", lambda c: _rate_str(c["p3_agreement"])),
        ("Move 15:51 to 15:59 close: correlation", lambda c: "n/a" if c["r1551_bps_pearson"] is None
         else f"{c['r1551_bps_pearson']:.3f}"),
        ("Move 15:51 to 15:59 close: same sign", lambda c: _rate_str(c["r1551_bps_sign_agreement"])),
        ("Move: mean / median absolute difference (bps)",
         lambda c: f"{c['r1551_bps_mean_abs_diff']:.2f} / {c['r1551_bps_median_abs_diff']:.2f}"),
    ]
    for label, f in rowdefs:
        a(f"| {label} | " + " | ".join(cell(k, f) for k in keys) + " |")
    a("")
    a("The two strong-body agreement rows differ only on a day when both feeds flag a strong body in opposite")
    a("directions. The 60% cut-off is sharp, so a candle near it can be strong in one feed and not in the other.")
    a("In the \"Strong-body days\" row the two shares are in the order of the column title. Over 2021-2026")
    a(f"Dukascopy had a strong body on {_pct(rem['holdout_strong_body_share'])} of days "
      f"({rem['holdout_strong_body_days']:,} of {rem['holdout_days']:,}).")
    a("")
    for name in keys[:2]:
        c = cmp_.get(name) or {}
        big = c.get("largest_r1551_abs_diffs") or []
        if big:
            src = name.replace("_vs_d1", "")
            parts = [f"{x['date']} ({x['first_bps']:+.2f} vs {x['second_bps']:+.2f}"
                     + (", opposite signs" if x["opposite_signs"] else "") + ")" for x in big]
            a(f"Largest differences in the 15:51-to-close move, {src} vs Dukascopy: {'; '.join(parts)}. "
              f"Median absolute difference {c['r1551_bps_median_abs_diff']:.2f} bps.")
            a("")
    sc = cons.get("d1_self_check", {}).get("self_check_this_module_vs_scan_py_on_d1", {})
    if sc:
        bad = sc.get("days_with_any_mismatch", [])
        if not bad:
            a(f"Code check: this script's own calculation, run on the same Dukascopy bars, reproduced every "
              f"`scan.py` signal and target on all {sc['days']} overlap days.")
        else:
            a(f"**Code check FAILED:** this script's calculation on the Dukascopy bars differs from `scan.py` on "
              f"{len(bad)} of {sc['days']} days ({', '.join(bad[:10])}; mismatches by field: {sc['mismatches']}). "
              "Do not read the tallies until this is fixed.")
        a("")
    lab = cons.get("bar_label_check", {})
    ls = cons.get("label_status", {})
    q = cons.get("quote_in_bar_check") or {}
    parts = [f"{name}: " + ("no common days yet" if v["best_lag"] is None
                            else f"best lag {v['best_lag']} min ({v['days']} days)")
             for name, v in sorted(lab.items())]
    qtxt = ("" if not q.get("quotes_checked") else
            f" Timestamped SPX quotes: {q['inside_start_labelled_bar']} of {q['quotes_checked']} lie inside the bar "
            f"that starts in their minute ({q['inside_bar_labelled_one_minute_later']} would fit the bar labelled "
            f"one minute later).")
    if ls.get("status") == "ok":
        a("Bar labels: every check that had data points to start-time labels, as `scan.py` uses ("
          + "; ".join(parts) + ")." + qtxt)
    elif ls.get("status") == "failed":
        a(f"**Bar-label check FAILED** ({', '.join(ls['failed'])}): " + "; ".join(parts) + "." + qtxt
          + " A non-zero best lag or a quote outside its bar means a feed may label bars differently from "
          "`scan.py`.")
    else:
        a("Bar labels: not checked (no data). " + "; ".join(parts) + qtxt)
    a("")


def _caveats(a, summary: dict) -> None:
    cons = summary["consistency_vs_dukascopy"]
    shapes = cons.get("shape_check", {})
    a("## Caveats")
    a("")
    a("- The move is measured to the close of the 15:59 bar, as in the backtest. SPX options settle on the")
    a("  official closing value, which can differ.")
    for src in SOURCES:
        s = shapes.get(f"{src}_vs_d1") or {}
        if not s.get("n_days"):
            continue
        t = s["per_day_gap_t"]
        clear = t is not None and abs(t) >= 2 and s["n_days"] >= 5
        more = s["strong_share_first"] > s["strong_share_second"]
        a(f"- **{src} candles are shaped {'differently from' if clear else 'much like'} the backtest's.** Over every "
          f"minute 09:31-15:58 on {s['n_days']} overlap days, {_pct(s['strong_share_first'])} of {src} one-minute "
          f"candles have a strong body, against {_pct(s['strong_share_second'])} of Dukascopy's on the same minutes "
          f"(median body/range {s['median_body_to_range_first']:.3f} vs {s['median_body_to_range_second']:.3f}). "
          f"{src} is higher on {s['days_first_higher']} of {s['n_days']} days (mean gap "
          f"{100 * s['per_day_gap_mean']:+.1f} points, paired t {'n/a' if t is None else f'{t:.1f}'}).")
        if clear:
            cut = s["first_cutoff_matching_second_share"]
            a(f"  So {src} flags strong bodies {'more' if more else 'less'} often than the backtest data did and its "
              "strong-body days are a different selection of candles: its forward hit rate is not a like-for-like")
            a("  check of the backtest." + (f" A cut-off of {cut:.3f} instead of 0.6 would match Dukascopy's share "
                                            "(descriptive only; the log keeps the frozen 0.6)." if cut else ""))
    a("- SPY is a stand-in. It trades on its own and can disagree with SPX on a small candle.")
    a("- The SPX index's 15:59-bar close can lag the tradable feeds by a few seconds. On 2026-10-20 Dukascopy")
    a("  (high 7717.09) and SPY (high 769.11) rallied in the last seconds of the 15:59 bar; the Robinhood SPX bar")
    a("  topped at 7712.22 and closed at 7711.70, the index then opened its 16:00 bar at 7714.52, and the official")
    a("  close was 7712.57. This is not a data error. Index and CFD price levels also differ by a basis, so only")
    a("  moves are compared, never levels.")
    a("- Robinhood SPX minute files are saved by hand, so coverage depends on someone saving them. Every forward")
    a("  session gets a row (`no_data` if nothing was saved), so gaps are visible; a gap is not filled by SPY in the")
    a("  pre-registered tally. The mixed series does fill it, which is why it is not the headline.")
    a("- This page reports what happened. It does not recommend any trade.")
    a("")


def forward_md(summary: dict) -> str:
    lines = []
    a = lines.append
    a("# Forward log: the 15:50 candle signals (descriptive only)")
    a("")
    a("This page is rebuilt by `analysis/candle_1550_forward.py` from whatever data is on disk. Do not edit it")
    a("by hand; re-run the script instead. It is a log, not a test: the pre-registration")
    a("(`preregistration/spx_close_candle_scan.md`) says the forward period is \"Robinhood minute data from")
    a("2026-10-21 on (descriptive only)\". Nothing here is trading advice.")
    a("")
    a("## What is logged")
    a("")
    status = summary["candidate_status"]
    a("For every full regular NYSE session, one row per data source in")
    a("`data/spx_1549/forward/candle_1550_log.csv`:")
    a("")
    a("- **The 15:50 one-minute candle** (the bar from 15:50:00 to 15:50:59 ET): open, high, low, close, body")
    a("  and range.")
    a(f"- **Strong body**: {plain_label(SB, status)}. The body is at least 60% of the candle's range (and the")
    a("  range is above zero), tested exactly as `scan.py` tests it. Its direction is up if the candle closed")
    a("  above its open, down if below.")
    a("- **The move it is scored on**: from the open of the 15:51 bar to the close of the 15:59 bar, in basis")
    a("  points, `r_bps = 10,000 x ln(exit / entry)`. A **hit** means the move went the candle's way. A move of")
    a("  exactly zero is counted separately and, in a second column, as a miss.")
    a(f"- **Also logged**: {plain_label('F1_1m_15:50', status)}; {plain_label('P3_reference', status)}; and")
    a(f"  {plain_label('F4_day_so_far', status)}, scored from the 15:49 open to the 15:59 close.")
    a("- **Source** and **period**. `SPX_robinhood` is Robinhood's SPX index minute bars, the pre-registered")
    a("  forward source and the headline. `SPY_recorder` is the SPY one-minute bars the daily recorder saves, a")
    a("  stand-in for SPX. The two are tallied separately. `mixed_SPX_else_SPY` (SPX when it has a full session,")
    a("  else SPY) is not pre-registered and is shown last. `FORWARD` days are 2026-10-21 or later; `OVERLAP` days")
    a("  are earlier, inside the 2021-2026 holdout, and are only used to check the data.")
    a("")
    a("A session is skipped if it is a half-day (13:00 close), if any one-minute bar from 15:49 to 15:59 is")
    a("missing, if 3 or more of those bars are flat (high = low), or, for Robinhood, if the file that supplied the")
    a("15:59 bar has no later bar (it may have been saved before 16:00 ET). A session with no file gets a `no_data`")
    a("row. Robinhood bars marked as interpolated (gap-fill) and bars with impossible prices are thrown away first.")
    a("Bars beginning after 15:59 ET are discarded during ingestion and never used in signals or targets. The")
    a("directions are the frozen ones in `candidates.json`, checked against its SHA-256.")
    a("")
    a("## How to run it")
    a("")
    a("```")
    a("PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B analysis/candle_1550_forward.py")
    a("PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B analysis/tests/test_candle_1550_forward.py")
    a("```")
    a("")
    a("It reads local files only and rebuilds every output from scratch, so running it twice gives the same")
    a("files. Run it after the recorder has saved the day's SPY bars (after about 16:30 ET), or after a new")
    a("`data/spx_1549/live_YYYY-MM-DD/spx_1m.json` has been saved. Save that file after 16:01 ET so that it holds")
    a("a bar after 15:59; otherwise the day is skipped as possibly unfinished. SPY bars are kept only if the")
    a("recorder fetched them at least 5 minutes after the bar ended.")
    a("")
    a("## Current forward tally")
    a("")
    _forward_section(a, summary)
    _power_section(a, summary["reminder"])
    _overlap_section(a, summary)
    _caveats(a, summary)
    a("## Files")
    a("")
    a("| File | What it is |")
    a("|---|---|")
    a("| `analysis/candle_1550_forward.py` | Builds everything on this page. |")
    a("| `analysis/tests/test_candle_1550_forward.py` | Unit tests on hand-built sessions. |")
    a("| `data/spx_1549/forward/candle_1550_log.csv` | One row per session per source, skipped and no-data sessions included with the reason. |")
    a("| `data/spx_1549/forward/overlap_vs_dukascopy.csv` | Overlap days: each source next to `scan.py`'s Dukascopy values. |")
    a("| `data/spx_1549/forward/summary.json` | All tallies (forward and overlap kept apart), checks and the decisions made. |")
    a("")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------
# build
# ------------------------------------------------------------------------------------------------
def build(spy_list=None, spx_list=None, quote_list=None, out_dir: Path = OUT_DIR, forward_md_path: Path = FORWARD_MD,
          d1_file: Path = D1_FILE, d1_days: Path = D1_DAYS, scan_py: Path = SCAN_PY,
          cand_file: Path = CAND_FILE, cand_sha: Path = CAND_SHA, holdout_json: Path = HOLDOUT_JSON,
          write: bool = True) -> dict:
    gate = frozen_directions(cand_file, cand_sha)
    dirs = gate["directions"]
    spy_list = spy_files() if spy_list is None else [Path(p) for p in spy_list]
    spx_list = spx_files() if spx_list is None else [Path(p) for p in spx_list]
    quote_list = spx_quote_files() if quote_list is None else [Path(p) for p in quote_list]

    spy = read_spy(spy_list)
    spx = read_spx(spx_list)
    sessions = {SPY: spy.sessions, SPX: spx.sessions}
    recs = {SPX: build_records(spx, SPX, dirs, None, check_close=True),
            SPY: build_records(spy, SPY, dirs, SPY_DECIMALS,
                               evidence_text="every stored bar fetched >= 5 min after it ended")}
    cal = add_no_data_rows(recs)
    mixed = mixed_series(recs)
    series = {SPX: recs[SPX], SPY: recs[SPY], MIXED: mixed}

    # log
    all_recs = sorted(recs[SPX] + recs[SPY], key=lambda r: (r["date"], r["source"]))
    log_txt = csv_text([log_row(r) for r in all_recs], LOG_COLUMNS)

    # consistency on OVERLAP days
    ok_overlap = {src: {r["date"]: r for r in recs[src] if r["status"] == "ok" and r["period"] == "OVERLAP"}
                  for src in SOURCES}
    ok_forward = {src: {r["date"] for r in recs[src] if r["status"] == "ok" and r["period"] == "FORWARD"}
                  for src in SOURCES}
    all_overlap_dates = sorted(set(ok_overlap[SPX]) | set(ok_overlap[SPY]))
    ref, d1_bars, d1_check = d1_reference(all_overlap_dates, d1_file, d1_days, scan_py)
    consistency = {"status": d1_check.get("status"), "d1_self_check": d1_check, "comparisons": {},
                   "shape_check": {}, "bar_label_check": {}}
    overlap_rows = []
    if d1_check.get("status") == "ok":
        vals = {src: {d: _vals_from_rec(r) for d, r in ok_overlap[src].items()} for src in SOURCES}
        for src in SOURCES:
            c, rows = compare(vals[src], ref)
            consistency["comparisons"][f"{src}_vs_d1"] = c
            for d, va, vb in rows:
                overlap_rows.append({
                    "date": d, "source": src,
                    "sb_source": va["signals"][SB], "sb_d1": vb["signals"][SB],
                    "dir1550_source": va["signals"]["F1_1m_15:50"], "dir1550_d1": vb["signals"]["F1_1m_15:50"],
                    "p3_source": va["signals"]["P3_reference"], "p3_d1": vb["signals"]["P3_reference"],
                    "dsf_source": _fmt(va["signals"]["F4_day_so_far"]), "dsf_d1": _fmt(vb["signals"]["F4_day_so_far"]),
                    "r_bps_source": _fmt(va["r1551_bps"]), "r_bps_d1": _fmt(vb["r1551_bps"]),
                    "r1549_bps_source": _fmt(va["r1549_bps"]), "r1549_bps_d1": _fmt(vb["r1549_bps"])})
            common = sorted(set(ok_overlap[src]) & set(d1_bars))
            consistency["bar_label_check"][f"{src}_vs_d1"] = label_lag_check(sessions[src], d1_bars, common)
            consistency["shape_check"][f"{src}_vs_d1"] = shape_check(sessions[src], d1_bars, common)
        c, _ = compare(vals[SPX], vals[SPY])
        consistency["comparisons"][f"{SPX}_vs_{SPY}"] = c
        consistency["bar_label_check"][f"{SPX}_vs_{SPY}"] = label_lag_check(
            sessions[SPX], sessions[SPY], sorted(set(ok_overlap[SPX]) & set(ok_overlap[SPY])))
        consistency["what"] = ("OVERLAP days (before 2026-10-21, inside the holdout): this log's values vs "
                               "scan.py's own Dukascopy D1 values (scan.load_panel + feature functions + target). "
                               "Agreement = share of common days with the same value; Pearson correlation of "
                               "r_bps (15:51 open -> 15:59 close). shape_check: strong-body share over every "
                               "minute 09:31-15:58 present in both feeds (descriptive).")
    # label checks that do not need D1: SPX vs SPY on FORWARD days, and the timestamped-quote check
    consistency["bar_label_check"][f"{SPX}_vs_{SPY}_FORWARD"] = label_lag_check(
        sessions[SPX], sessions[SPY], sorted(ok_forward[SPX] & ok_forward[SPY]))
    consistency["quote_in_bar_check"] = quote_in_bar_check(sessions[SPX], quote_list)
    consistency["label_status"] = label_status(consistency)
    overlap_rows.sort(key=lambda r: (r["date"], r["source"]))
    overlap_txt = csv_text(overlap_rows, OVERLAP_COLUMNS)

    inputs = []
    for p in list(spy_list) + list(spx_list) + list(quote_list):
        inputs.append({"path": rel(p), "sha256": sha256_file(p), "bytes": Path(p).stat().st_size})
    refs = []
    for p in (PREREG, scan_py, cand_file, cand_sha, holdout_json, d1_days):
        if Path(p).exists():
            refs.append({"path": rel(p), "sha256": sha256_file(p)})

    lab = consistency["label_status"]
    summary = {
        "what": ("Forward log of the SPX close candle-scan candidates (descriptive only, as pre-registered: "
                 "'Forward = Robinhood minute data from 2026-10-21 on'). Tallies are per source; SPX_robinhood is "
                 "the pre-registered headline; FORWARD and OVERLAP days are kept apart; OVERLAP days are inside "
                 "the holdout and are not out of sample."),
        "forward_status": ("LABEL CHECK FAILED: do not read the forward tallies until resolved"
                           if lab["status"] == "failed" else f"label check {lab['status']}"),
        "definitions": {
            "bar_label": "bars labelled by ET START time; the 15:50 bar covers 15:50:00-15:50:59",
            "arithmetic": "float64 on the prices exactly as stored in the source file, as scan.py does",
            "strong_body": "|close - open| >= 0.6 x (high - low) and high > low, on the 15:50 one-minute candle "
                           "(scan.py's float test); signal = sign(close - open)",
            "strong_body_exact_decimal": "SENSITIVITY: the same test in exact decimals on prices normalised to the "
                                         "source's precision (SPY 4 dp, Robinhood as given)",
            "direction_1550": "sign(close - open) of the 15:50 bar (F1_1m_15:50)",
            "P3_reference": "sign(ln(15:51 open / 15:50 open))",
            "F4_day_so_far": "sign(ln(15:49 open / 09:30 open)), target r(15:49 open -> 15:59 close)",
            "r_bps": "1e4 x ln(15:59 bar close / 15:51 bar open)",
            "hit": "sign(r) == frozen direction x signal, over signal days with r != 0",
            "hit_zero_as_miss": "same, but a day with r == 0 counts as a miss (scan.py's zero-as-miss version)",
            "mean_signed_r_bps_per_signal_day": "mean of frozen direction x signal x r_bps over signal days",
            "session": "full NYSE session (not a half-day), every bar 15:49..15:59 present, fewer than 3 flat bars "
                       "in 15:49..15:59, and (Robinhood) a real bar after 15:59 in the file that supplied 15:59",
            "FORWARD": f"date >= {FORWARD_START}", "OVERLAP": f"{HOLDOUT[0]} <= date <= {HOLDOUT[1]}"},
        "frozen_candidates": {"directions": dirs, "candidates_json_sha256": gate["sha256"],
                              "hash_matches_candidates_sha256": True},
        "candidate_status": candidate_status(holdout_json),
        "forward_calendar": cal,
        "days": {SPX: day_counts(recs[SPX]), SPY: day_counts(recs[SPY]),
                 MIXED: {"days_ok": len(mixed), "days_ok_forward": sum(1 for r in mixed if r["period"] == "FORWARD"),
                         "days_ok_overlap": sum(1 for r in mixed if r["period"] == "OVERLAP"),
                         "from_SPX": sum(1 for r in mixed if r["source"] == SPX),
                         "from_SPY": sum(1 for r in mixed if r["source"] == SPY),
                         "note": "not pre-registered; mixes two feeds"}},
        "forward": tallies(series, "FORWARD"),
        "forward_sensitivity_exact_decimal": tallies(series, "FORWARD", SENSITIVITY),
        "exact_decimal_sensitivity": {
            "what": "days where the exact-decimal strong-body sensitivity differs from the binding float test",
            "differs_on": exact_vs_binding_days(sorted(recs[SPX] + recs[SPY], key=lambda r: (r["date"], r["source"])))},
        "forward_days_latest": latest_days(sorted(recs[SPX] + recs[SPY], key=lambda r: (r["date"], r["source"])),
                                           LATEST_N),
        "overlap_NOT_OUT_OF_SAMPLE": tallies(series, "OVERLAP"),
        "overlap_sensitivity_exact_decimal_NOT_OUT_OF_SAMPLE": tallies(series, "OVERLAP", SENSITIVITY),
        "consistency_vs_dukascopy": consistency,
        "reader_diagnostics": {SPY: spy.diag, SPX: spx.diag},
        "reminder": reminder_numbers(holdout_json),
        "decisions": DECISIONS,
        "inputs": inputs,
        "reference_files": refs,
        "outputs": [rel(Path(out_dir) / LOG_NAME), rel(Path(out_dir) / OVERLAP_NAME),
                    rel(Path(out_dir) / SUMMARY_NAME), rel(forward_md_path)],
    }
    summary_txt = json.dumps(summary, indent=1, default=_json_default) + "\n"
    summary = json.loads(summary_txt)
    md_txt = forward_md(summary)

    if write:
        out_dir = Path(out_dir)
        write_atomic(out_dir / LOG_NAME, log_txt)
        write_atomic(out_dir / OVERLAP_NAME, overlap_txt)
        write_atomic(out_dir / SUMMARY_NAME, summary_txt)
        write_atomic(Path(forward_md_path), md_txt)
    return {"summary": summary, "log_csv": log_txt, "overlap_csv": overlap_txt, "forward_md": md_txt,
            "records": recs}


def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(f"not JSON serialisable: {type(o)}")


def console_summary(summary: dict) -> str:
    out = [f"status: {summary['forward_status']}"]
    for src in SOURCES:
        dc = summary["days"][src]
        out.append(f"{src}: {dc['days_seen']} days seen, {dc['days_ok']} full sessions "
                   f"({dc['days_ok_forward']} forward of {dc['forward_sessions_on_calendar']} forward sessions, "
                   f"{dc['days_ok_overlap']} overlap), skipped {dc['days_skipped']}")
    for src in SOURCES + (MIXED,):
        t = summary["forward"][src][SB]
        out.append(f"FORWARD strong body [{src}]: {t['signal_days']} signal days, {t['hits']} hits, "
                   f"{t['zero_r_days']} zero, hit rate {_pct(t['hit_rate'])} ({_ci(t['hit_rate_wilson95'])}), "
                   f"mean {_bps(t['mean_signed_r_bps_per_signal_day'])} bps")
    cons = summary["consistency_vs_dukascopy"]
    for name, c in cons.get("comparisons", {}).items():
        if c.get("n_days"):
            out.append(f"{name}: n={c['n_days']} strong flag {_rate_str(c['strong_body_flag_agreement'])}, "
                       f"strong signal {_rate_str(c['strong_body_signal_agreement'])}, direction "
                       f"{_rate_str(c['direction_1550_agreement'])}, r corr "
                       f"{c['r1551_bps_pearson'] if c['r1551_bps_pearson'] is None else round(c['r1551_bps_pearson'], 4)}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--forward-md", default=str(FORWARD_MD))
    a = ap.parse_args(argv)
    try:
        res = build(out_dir=Path(a.out_dir), forward_md_path=Path(a.forward_md))
    except GateError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(console_summary(res["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
