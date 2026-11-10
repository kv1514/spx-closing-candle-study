#!/usr/bin/env python
"""SPX close candle scan: does any candle predict the SPX close move?

Implements /Users/kv15/trading/preregistration/spx_close_candle_scan.md (read-only and binding), in two
separately runnable steps:

    PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B scan.py discover
    PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B scan.py holdout

discover  reads ONLY the DISCOVERY days (2013-02-28 .. 2020-12-31). The bar file is streamed in date order
          and reading stops at the first row dated after 2020-12-31, so no holdout bar is ever parsed; the
          panel is asserted to hold no holdout date before any target is computed. It computes the 41
          pre-registered features (+ the P3 reference row), writes discovery.json, the frozen candidate list
          candidates.json and its SHA-256 in candidates.sha256.
holdout   refuses to run unless candidates.json matches candidates.sha256 (checked before any data is
          read), then tests the frozen candidates on HOLDOUT (2021-01-01 .. 2026-10-20; one-sided, Holm 5%),
          runs the 11:49/11:51 placebo, the option economics, the straddle-cost cross-check, and the
          descriptive full-sample hit rates; writes holdout.json.

Conventions reused from backtests/spx_close_1549/analysis.py (read, not imported):
  * bar m = minutes after 09:30 ET, left-labelled: the 15:50 bar covers 15:50:00-15:50:59; 390 bars.
  * the information set at the open of bar k = opens of bars <= k and highs/lows/closes of bars < k.
  * r = ln(P_end / P_start); target = ln(close of the 15:59 bar / open of the entry bar).
  * day set = d1_days.csv column `keep`; Newey-West (Bartlett) lag 5 on the per-day series in date order;
    mean of signal x target in bps over all defined days (zero-signal days count as 0); hit rate over days
    with a non-zero signal and a non-zero target (the analysis.py convention; the version that counts a
    zero-move trade as a miss is reported next to it); normal p-values from the NW t.

Post-audit (2026-10-21, see audits/DISPOSITION.md): every overwrite of discovery.json / holdout.json first
archives the previous file in runs/, the holdout step aborts if the current code no longer reproduces the
frozen discovery, and it records old -> new for every headline number of the previous run.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")          # single process, single thread (another heavy job is running)

import argparse  # noqa: E402
import csv  # noqa: E402
import datetime as dt  # noqa: E402
import glob  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import tomllib  # noqa: E402
import warnings  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

# ------------------------------------------------------------------------------------------------
# paths and constants (every constant below is fixed by the pre-registration params block, checked at
# run time by `check_prereg_params`, or stated as an implementation choice in DECISIONS)
# ------------------------------------------------------------------------------------------------
ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
PREREG = ROOT / "preregistration" / "spx_close_candle_scan.md"
DATA = ROOT / "data" / "spx_1549"
D1_FILE = DATA / "d1_usa500_rth_1m.csv.gz"
D1_DAYS = DATA / "d1_days.csv"
RH_RAW = DATA / "robinhood" / "raw"
RESULTS_1549 = ROOT / "backtests" / "spx_close_1549" / "results.json"
LIVE_1021 = DATA / "live_2026-10-21" / "scorecard.json"

DAY_SET = "keep"
DISCOVERY = ("2013-02-28", "2020-12-31")
HOLDOUT = ("2021-01-01", "2026-10-20")
ENTRIES = ("15:49", "15:51")
TARGET_END = "15:59"
N_FEATURES = 41
NW_LAG = 5
DISCOVERY_ABS_T = 2.5
MAX_CANDIDATES = 8
ALPHA = 0.05
HALF_SPREAD = 0.10        # $ per option, option-price units (= index points)
FEES = (0.09, 0.74)       # $ per contract
MULT = 100                # SPX option multiplier
STRIKE_STEP = 5.0
PLACEBO_SHIFT = -240      # minutes: entry 15:49 -> 11:49, 15:51 -> 11:51, target end 15:59 -> 11:59
POWER = 0.80
Z_ALPHA_ONE_SIDED = 1.6448536269514722   # Phi^-1(0.95)
Z_POWER = 0.8416212335729143             # Phi^-1(0.80)
Z95 = 1.959963984540054
OVERLAP_P3_THRESHOLD = 0.90
LATE_START = "2023-01-01"
EARLY_END = "2022-12-31"
N_MIN = 390
N_BOOT = 10_000
SIZE_SIMS = 2_000         # random-sign series per period x entry in the real-data null check
SHIFT_MIN_GAP = 21        # circular shifts of at least 21 trading days (well past the NW lag)
SHIFT_STEP = 6            # every 6th admissible shift

CAND_FILE = "candidates.json"
SHA_FILE = "candidates.sha256"
DISC_FILE = "discovery.json"
HOLD_FILE = "holdout.json"
RUNS_DIR = "runs"

DECISIONS = [
    {"id": "entry-assignment",
     "text": "Each feature is assigned the earliest pre-registered entry its candles allow: a feature whose "
             "candles all close by 15:48:59 uses entry 15:49 (target r(15:49 open -> 15:59 close)); a feature "
             "that uses the 15:49 or 15:50 one-minute bar uses entry 15:51 (target r(15:51 open -> 15:59 "
             "close)). So F1 15:30..15:48 and F3 15:20..15:40 enter at 15:49; F1 15:49, F1 15:50, every F2 "
             "shape (the 15:50 1-minute candle and the 15:45-15:49 five-minute candle, which closes at "
             "15:49:59) and F3 15:45 enter at 15:51; every F4 feature is a 'day level at entry' and enters at "
             "15:49.",
     "kind": "implementation choice (the pre-registration's entry rule applied feature by feature)"},
    {"id": "f4-definitions",
     "text": "F4: P = open of the entry bar (15:49). CLV = (P - day low)/(day high - day low) with high/low "
             "over the 1-minute bars 09:30..15:48 and P itself; signal sign(CLV - 0.5), 0 if high = low. "
             "Opening gap = sign(09:30 open - prior session's 15:59 close). Prior-day candle = sign(prior "
             "session's 15:59 close - its 09:30 open). The prior session is the previous NYSE session in "
             "d1_days.csv (calendar != nyse_holiday); if that session is not in the keep set (no bars) the "
             "two prior-day features are undefined for that day (dropped, not zero). Day-so-far = P1 = "
             "sign(ln(15:49 open / 09:30 open)).",
     "kind": "implementation choice"},
    {"id": "f2-definitions",
     "text": "F2 candle = (open of its first minute, max high, min low, close of its last minute); body = "
             "close - open, range = high - low, upper wick = high - max(open, close), lower wick = min(open, "
             "close) - low. strong body: sign(body) if range > 0 and |body| >= 0.6 range, else 0. hammer: +1 if "
             "range > 0, lower wick >= 2|body| and lower wick >= 0.6 range, else 0. shooting star: -1 if range "
             "> 0, upper wick >= 2|body| and upper wick >= 0.6 range, else 0. engulfing vs the prior candle of "
             "the same size (1-minute 15:49; five-minute 15:40-15:44): +1 if prior close < prior open, current "
             "close > current open, current open <= prior close and current close >= prior open; -1 for the "
             "mirror case; else 0. big candle: sign(body) if |body| >= 2 x the median (high - low) of the "
             "day's 1-minute bars from 09:30 through the candle's last minute, else 0. A candle with any of "
             "its bars missing is undefined (dropped).",
     "kind": "implementation choice"},
    {"id": "p3-reference",
     "text": "The P3 reference row is P3 exactly as in spx_close_1549/analysis.py: sign(ln(15:51 open / 15:50 "
             "open)), entry 15:51. It is never eligible as a candidate and is outside the BH family. F1 15:50 "
             "(sign(close - open) of the 15:50 bar) and the F2 shapes on the 15:50 candle are in the 41 as "
             "the pre-registration lists them; any candidate whose non-zero signals agree with P3 on >= 90% of "
             "discovery days is flagged overlaps_known_P3, because P3's 2013-2026 result (which includes the "
             "holdout years) was known when the pre-registration was written, so its holdout is not a clean "
             "out-of-sample test.",
     "kind": "interpretation (flag only; nothing is excluded)"},
    {"id": "stat-conventions",
     "text": "Per feature: y = signal x target x 1e4 over days where both are defined; mean and Newey-West t "
             "(lag 5) over all those days (zero-signal days contribute 0, as in analysis.py); hit rate = share "
             "of days with signal != 0 and target != 0 on which signal x target > 0. Discovery p-values are "
             "two-sided normal; BH q-values over the 41. Holdout: one-sided normal p of mean > 0 with the "
             "frozen direction; Holm over the candidates. Hit-rate 95% CI = Wilson score interval treating days "
             "as independent.",
     "kind": "implementation choice (statistics as in analysis.py where it has them)"},
    {"id": "economics",
     "text": "Buy one ATM 0DTE call (signal x direction > 0) or put (< 0) at the entry price, strike = entry "
             "price (idealised ATM), hold to the 15:59 close. Payoff = |move| on correct days, 0 on wrong "
             "days (a zero move counts as wrong). Option cost = half the realized-move-fair straddle = 0.5 x "
             "mean |move| over the candidate's holdout trade days, + $0.10 half-spread + one fee ($0.09 or "
             "$0.74 per contract = 0.0009 or 0.0074 points; no exit fee at expiry, as analysis.py). Break-even "
             "hit rate = cost / mean |move| on correct days (primary, uses the correct- vs wrong-day |move| "
             "distribution); also reported: the size-neutral break-even cost / mean |move| (= 0.5 + (spread + "
             "fee)/mean|move|) and both at the last D1 price level (moves in return units x the 2026-10-20 "
             "15:49 open). Trades needed (one-sided 5%, 80% power, iid normal approximation): n = ((z_a + "
             "z_b) sd / mean)^2 for the per-trade signed return and for the per-trade option P&L; for the hit "
             "rate vs 50% and vs the break-even, n = ((z_a sqrt(p0 q0) + z_b sqrt(p q)) / (p - p0))^2.",
     "kind": "implementation choice (the pre-registration's step 4 made concrete)"},
    {"id": "straddle-crosscheck",
     "text": "Cross-check: on the 22 Robinhood 10-minute days the ATM straddle = call + put 15:40-bar close "
             "(last trade in 15:40:00-15:49:59, about 15:50) at the strike nearest the SPX 15:49-bar close, in "
             "bps of that SPX price, versus the assumed realized-move-fair straddle (D1 holdout mean |move| in "
             "bps, for the 15:49 and 15:51 entries, which bracket a 15:50 mark) and versus the official "
             "|settle - S| on the same days. The two fully priced days use the 15:49 one-minute marks: "
             "2026-10-20 from spx_close_1549/results.json, 2026-10-21 from the live scorecard (settlement "
             "provisional there).",
     "kind": "implementation choice"},
    {"id": "placebo",
     "text": "Placebo: every candidate rebuilt 240 minutes earlier (every bar index - 240: entry 15:49 -> "
             "11:49, 15:51 -> 11:51, target to the 11:59 close; F1 15:40 -> 11:40, etc.), with its frozen "
             "direction. Opening gap and prior-day candle keep their signal (only the target moves); "
             "day-so-far becomes sign(11:49 open / 09:30 open). Reported on discovery and holdout, "
             "descriptive.",
     "kind": "implementation choice"},
    {"id": "holdout-rerun",
     "text": "The holdout step was re-run on the same frozen file (hash unchanged) after its first run, to "
             "change two reporting items: (a) the straddle-cost sensitivity had scaled the option cost "
             "by market straddle / D1 holdout mean |move|, a ratio across different volatility regimes (2026 "
             "vs 2021-2026) that made the break-even look far too low (about 36%); it now uses the market's "
             "markup over the realized official move on the same 22 days, with a bootstrap CI; (b) the plain "
             "summary now states the P3 overlap, the 2023-2026 descriptive hit rate, the size-neutral "
             "break-even and the calendar time to confirm. No test statistic, candidate, direction, or "
             "pre-registered economics number changed (the code is deterministic).",
     "kind": "DEVIATION in reporting only (labelled), made after seeing the first holdout output"},
    {"id": "zero-target-hit-rate",
     "text": "The pre-registration says the hit rate excludes (and counts) zero signals. The primary hit rate "
             "here also drops trades whose target move is exactly 0, as analysis.py does; those trades are "
             "counted (n_trades_zero_target). Because the option economics treats a zero move as a paid trade "
             "with zero payoff, every hit rate is also reported with zero-move trades counted as misses "
             "(hit_rate_zero_target_as_miss and its Wilson CI), and the accuracy verdict is given under both.",
     "kind": "DEVIATION (minor, disclosed by the audits): extra exclusion in the primary hit rate; the "
             "economics-consistent version is reported next to it"},
    {"id": "post-audit-reporting",
     "text": "After the two audits (audits/DISPOSITION.md) the holdout step was re-run on the same "
             "frozen file, and the discovery step was re-run first (same candidates and directions, frozen file "
             "kept byte for byte, hash unchanged). Added, all reporting: (a) the direct one-sided test of the "
             "option P&L per trade (iid and NW t) and the straddle markups at which the break-even reaches the "
             "hit-rate CI lower bound and at which the mean P&L is 0; (b) the accuracy verdict against the "
             "size-neutral break-even and trades needed against it; (c) holdout sub-periods 2021-2022, "
             "2023-2026 and each year, with each period's own economics and trades needed at its effect size; "
             "(d) the straddle cross-check against the straddle's own payoff |settle - K| next to |settle - S|, "
             "the same-day payoff for the two fully priced days, and the markup sensitivity on both; (e) the "
             "D1 CFD target vs the official SPX settlement target on the overlapping Robinhood days, and the "
             "hit rate mapped to the settlement; (f) known-effect flags for P1 as well as P3 (computed in the "
             "holdout step; the frozen file is unchanged); (g) a real-data null check (random-sign signals and "
             "circular shifts of the real signals against the real D1 targets); (h) the provenance changes in "
             "the module docstring. Nothing in the pre-registered steps 1-4 changed: no feature, candidate, "
             "direction, test, threshold or pre-registered economics number.",
     "kind": "DEVIATION in reporting only (labelled), made after the audits and after seeing the holdout"},
]


def mi(hhmm: str) -> int:
    """Minute index of the bar that begins at hh:mm ET."""
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m - (9 * 60 + 30)


def hhmm(k: int) -> str:
    t = 9 * 60 + 30 + int(k)
    return f"{t // 60:02d}:{t % 60:02d}"


I1549, I1550, I1551, I1559 = mi("15:49"), mi("15:50"), mi("15:51"), mi("15:59")


# ------------------------------------------------------------------------------------------------
# pre-registration binding check
# ------------------------------------------------------------------------------------------------
def prereg_params(path: Path = PREREG) -> dict:
    txt = path.read_text()
    m = re.search(r"```toml tradelab-params\n(.*?)```", txt, re.S)
    assert m, "params block not found in the pre-registration"
    return tomllib.loads(m.group(1))


def check_prereg_params(path: Path = PREREG) -> dict:
    p = prereg_params(path)
    assert p["data"] == "data/spx_1549/d1_usa500_rth_1m.csv.gz"
    assert p["day_set"] == DAY_SET
    assert tuple(p["discovery"]) == DISCOVERY and tuple(p["holdout"]) == HOLDOUT
    assert tuple(p["entries"]) == ENTRIES and p["target_end"] == "15:59 close"
    assert p["n_features"] == N_FEATURES
    assert p["f1_minutes"] == ["15:30", "15:50"]
    assert p["f2_candles"] == ["1m 15:50", "5m 15:45-15:49"]
    assert p["f2_shapes"] == ["strong_body_0.6", "hammer_2x_0.6", "shooting_star_2x_0.6", "engulfing",
                              "big_candle_2x_median_range"]
    assert p["f3_5m_starts"] == ["15:20", "15:25", "15:30", "15:35", "15:40", "15:45"]
    assert p["f4"] == ["clv_vs_0.5", "open_gap", "prior_day_candle", "day_so_far"]
    assert p["nw_lag"] == NW_LAG and p["discovery_abs_t"] == DISCOVERY_ABS_T
    assert p["max_candidates"] == MAX_CANDIDATES and p["holdout_test"] == "one-sided, Holm 5%"
    assert p["half_spread"] == HALF_SPREAD and tuple(p["fees"]) == FEES
    assert p["placebo_entries"] == ["11:49", "11:51"]
    assert [hhmm(mi(e) + PLACEBO_SHIFT) for e in ENTRIES] == p["placebo_entries"]
    return {"params": p, "sha256": sha256_file(path), "all_constants_match": True}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


# ------------------------------------------------------------------------------------------------
# data: a panel of days x 390 minute bars
# ------------------------------------------------------------------------------------------------
@dataclass
class Panel:
    dates: np.ndarray        # str, sorted
    O: np.ndarray            # days x 390
    H: np.ndarray
    L: np.ndarray
    C: np.ndarray
    prev_open: np.ndarray    # prior session's 09:30 open (NaN if that session has no bars)
    prev_close: np.ndarray   # prior session's 15:59 close
    meta: dict


def sub(P: Panel, mask) -> Panel:
    mask = np.asarray(mask, bool)
    return Panel(P.dates[mask], P.O[mask], P.H[mask], P.L[mask], P.C[mask], P.prev_open[mask],
                 P.prev_close[mask], dict(P.meta, subset=True))


def _read_days(days_file: Path):
    with open(days_file, newline="") as f:
        rows = list(csv.DictReader(f))
    sessions = [r["date"] for r in rows if r["calendar"] != "nyse_holiday"]
    assert sessions == sorted(sessions)
    keep = {r["date"] for r in rows if r[DAY_SET].strip().lower() == "true"}
    return sessions, keep


def load_panel(start: str, end: str, d1_file: Path = D1_FILE, days_file: Path = D1_DAYS) -> Panel:
    """Keep-set days in [start, end]. The gzip CSV is streamed in date order and reading STOPS at the first
    row dated after `end`, so no later bar is parsed. The prior session of the first day (if it is a keep
    day before `start`) is read only for its 09:30 open and 15:59 close (prior-day features)."""
    sessions, keep = _read_days(days_file)
    prev = {d: (sessions[i - 1] if i > 0 else None) for i, d in enumerate(sessions)}
    want = sorted(d for d in keep if start <= d <= end)
    want_set = set(want)
    extra = {prev[d] for d in want if prev.get(d) and prev[d] < start and prev[d] in keep}
    lo = min([start] + sorted(extra))
    data = {}
    rows_parsed, stop_date, last_d = 0, None, ""
    with gzip.open(d1_file, "rt", newline="") as f:
        rd = csv.reader(f)
        header = next(rd)
        assert header[:6] == ["date", "time_et", "open", "high", "low", "close"], header
        for row in rd:
            d = row[0]
            assert d >= last_d, "D1 bar file is not sorted by date"
            last_d = d
            if d > end:
                stop_date = d           # only the date field of this row was looked at
                break
            if d < lo or (d not in want_set and d not in extra):
                continue
            k = mi(row[1])
            assert 0 <= k < N_MIN
            data.setdefault(d, []).append((k, float(row[2]), float(row[3]), float(row[4]), float(row[5])))
            rows_parsed += 1
    missing = [d for d in want if d not in data]
    assert not missing, f"keep days without bars: {missing[:5]}"
    n = len(want)
    O = np.full((n, N_MIN), np.nan)
    H, L, C = O.copy(), O.copy(), O.copy()
    for i, d in enumerate(want):
        for k, o, h, l_, c in data[d]:
            O[i, k], H[i, k], L[i, k], C[i, k] = o, h, l_, c
    po = np.full(n, np.nan)
    pc = np.full(n, np.nan)
    for i, d in enumerate(want):
        p = prev.get(d)
        if p is not None and p in data:
            bars = {k: (o, c) for k, o, _, _, c in data[p]}
            po[i] = bars.get(0, (np.nan, np.nan))[0]
            pc[i] = bars.get(I1559, (np.nan, np.nan))[1]
    dates = np.array(want, dtype=object)
    assert ((dates >= start) & (dates <= end)).all()
    assert np.isfinite(O[:, mi("15:19"):I1559 + 1]).all(), "a kept day is missing a bar in 15:19-15:59"
    meta = {"window": [start, end], "n_days": n, "first": want[0] if want else None,
            "last": want[-1] if want else None, "rows_parsed": rows_parsed,
            "prior_session_rows_loaded_before_window": sorted(extra),
            "stopped_at_first_row_dated": stop_date, "d1_file": str(d1_file), "days_file": str(days_file)}
    return Panel(dates, O, H, L, C, po, pc, meta)


def assert_no_holdout(dates, holdout_start: str = HOLDOUT[0]) -> None:
    """Guard used by the discovery step before any target is computed."""
    d = np.asarray(dates, dtype=object)
    bad = d[d >= holdout_start]
    assert bad.size == 0, f"holdout date(s) reached discovery: {list(bad[:5])}"


# ------------------------------------------------------------------------------------------------
# features (pure functions of the panel; `sh` shifts every bar index, used by the placebo)
# ------------------------------------------------------------------------------------------------
def lr(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(np.asarray(b, dtype=float) / np.asarray(a, dtype=float))


def _valid(*arrs):
    return np.logical_and.reduce([np.isfinite(a) for a in arrs])


def _nan_where_invalid(s, *arrs):
    s = np.asarray(s, dtype=float).copy()
    s[~_valid(*arrs)] = np.nan
    return s


def candle_1m(P: Panel, k: int):
    return P.O[:, k], P.H[:, k], P.L[:, k], P.C[:, k]


def candle_5m(P: Panel, s: int):
    sl = slice(s, s + 5)
    ok = (np.isfinite(P.O[:, sl]) & np.isfinite(P.H[:, sl]) & np.isfinite(P.L[:, sl]) &
          np.isfinite(P.C[:, sl])).all(axis=1)
    o = np.where(ok, P.O[:, s], np.nan)
    c = np.where(ok, P.C[:, s + 4], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        h = np.where(ok, np.max(np.where(ok[:, None], P.H[:, sl], -np.inf), axis=1), np.nan)
        l_ = np.where(ok, np.min(np.where(ok[:, None], P.L[:, sl], np.inf), axis=1), np.nan)
    return o, h, l_, c


def direction(o, c):
    return np.sign(np.asarray(c, float) - np.asarray(o, float))      # NaN propagates


def shape_strong_body(o, h, l_, c):
    body, rng = c - o, h - l_
    with np.errstate(invalid="ignore"):
        s = np.where((rng > 0) & (np.abs(body) >= 0.6 * rng), np.sign(body), 0.0)
    return _nan_where_invalid(s, o, h, l_, c)


def shape_hammer(o, h, l_, c):
    body, rng = c - o, h - l_
    lw = np.minimum(o, c) - l_
    with np.errstate(invalid="ignore"):
        s = np.where((rng > 0) & (lw >= 2.0 * np.abs(body)) & (lw >= 0.6 * rng), 1.0, 0.0)
    return _nan_where_invalid(s, o, h, l_, c)


def shape_shooting_star(o, h, l_, c):
    body, rng = c - o, h - l_
    uw = h - np.maximum(o, c)
    with np.errstate(invalid="ignore"):
        s = np.where((rng > 0) & (uw >= 2.0 * np.abs(body)) & (uw >= 0.6 * rng), -1.0, 0.0)
    return _nan_where_invalid(s, o, h, l_, c)


def shape_engulfing(prev, cur):
    op, _, _, cp = prev
    oc, hc, lc, cc = cur
    with np.errstate(invalid="ignore"):
        bull = (cp < op) & (cc > oc) & (oc <= cp) & (cc >= op)
        bear = (cp > op) & (cc < oc) & (oc >= cp) & (cc <= op)
    s = bull.astype(float) - bear.astype(float)
    return _nan_where_invalid(s, op, cp, oc, hc, lc, cc)


def median_range_so_far(P: Panel, last: int):
    r = P.H[:, :last + 1] - P.L[:, :last + 1]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(r, axis=1)


def shape_big_candle(o, h, l_, c, med):
    body = c - o
    with np.errstate(invalid="ignore"):
        s = np.where(np.abs(body) >= 2.0 * med, np.sign(body), 0.0)
    return _nan_where_invalid(s, o, h, l_, c, med)


def clv_signal(P: Panel, entry_bar: int):
    p = P.O[:, entry_bar]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        hi = np.fmax(np.nanmax(P.H[:, :entry_bar], axis=1), p)
        lo = np.fmin(np.nanmin(P.L[:, :entry_bar], axis=1), p)
    with np.errstate(invalid="ignore", divide="ignore"):
        clv = (p - lo) / (hi - lo)
        s = np.where(hi > lo, np.sign(clv - 0.5), 0.0)
    return _nan_where_invalid(s, p, hi, lo)


@dataclass
class Feature:
    fid: str
    family: str
    desc: str
    entry: str          # "15:49" or "15:51"
    fn: object          # fn(P, sh) -> signal array in {-1, 0, +1, NaN}

    def signal(self, P: Panel, sh: int = 0):
        return self.fn(P, sh)


def _f1(k):
    return lambda P, sh: direction(P.O[:, k + sh], P.C[:, k + sh])


def _f3(s):
    def fn(P, sh):
        o, _, _, c = candle_5m(P, s + sh)
        return direction(o, c)
    return fn


def _f2(candle, shape):
    if candle == "1m_1550":
        cur = lambda P, sh: candle_1m(P, I1550 + sh)            # noqa: E731
        prv = lambda P, sh: candle_1m(P, mi("15:49") + sh)      # noqa: E731
        last = I1550
    else:
        cur = lambda P, sh: candle_5m(P, mi("15:45") + sh)      # noqa: E731
        prv = lambda P, sh: candle_5m(P, mi("15:40") + sh)      # noqa: E731
        last = mi("15:49")

    def fn(P, sh):
        o, h, l_, c = cur(P, sh)
        if shape == "strong_body":
            return shape_strong_body(o, h, l_, c)
        if shape == "hammer":
            return shape_hammer(o, h, l_, c)
        if shape == "shooting_star":
            return shape_shooting_star(o, h, l_, c)
        if shape == "engulfing":
            return shape_engulfing(prv(P, sh), (o, h, l_, c))
        if shape == "big_candle":
            return shape_big_candle(o, h, l_, c, median_range_so_far(P, last + sh))
        raise ValueError(shape)
    return fn


def _f4(name):
    def fn(P, sh):
        if name == "clv":
            return clv_signal(P, I1549 + sh)
        if name == "open_gap":
            return direction(P.prev_close, P.O[:, 0])
        if name == "prior_day_candle":
            return direction(P.prev_open, P.prev_close)
        if name == "day_so_far":
            return np.sign(lr(P.O[:, 0], P.O[:, I1549 + sh]))
        raise ValueError(name)
    return fn


SHAPE_DESC = {"strong_body": "strong body (|body| >= 0.6 range): sign(body)",
              "hammer": "hammer (lower wick >= 2 body and >= 0.6 range): +1",
              "shooting_star": "shooting star (upper wick >= 2 body and >= 0.6 range): -1",
              "engulfing": "bullish (+1) / bearish (-1) engulfing vs the prior candle of the same size",
              "big_candle": "big candle (|body| >= 2 x the day's median 1-minute range so far): sign(body)"}


def feature_specs() -> list[Feature]:
    out = []
    for k in range(mi("15:30"), mi("15:50") + 1):
        out.append(Feature(f"F1_1m_{hhmm(k)}", "F1", f"sign(close - open) of the {hhmm(k)} 1-minute candle",
                           "15:49" if k <= mi("15:48") else "15:51", _f1(k)))
    for cand, lab in (("1m_1550", "15:50 1-minute candle"), ("5m_1545", "15:45-15:49 five-minute candle")):
        for shape in ("strong_body", "hammer", "shooting_star", "engulfing", "big_candle"):
            out.append(Feature(f"F2_{cand}_{shape}", "F2", f"{SHAPE_DESC[shape]}; on the {lab}", "15:51",
                               _f2(cand, shape)))
    for s in range(mi("15:20"), mi("15:45") + 1, 5):
        out.append(Feature(f"F3_5m_{hhmm(s)}", "F3", f"sign(close - open) of the {hhmm(s)}-{hhmm(s + 4)} "
                           "five-minute candle", "15:49" if s + 4 <= mi("15:48") else "15:51", _f3(s)))
    for name, d in (("clv", "sign(CLV - 0.5), CLV = (P - day low)/(day high - day low) at the 15:49 open"),
                    ("open_gap", "sign(09:30 open - prior session's close)"),
                    ("prior_day_candle", "sign(prior session's close - its open)"),
                    ("day_so_far", "sign r(09:30 open -> 15:49 open) (= P1)")):
        out.append(Feature(f"F4_{name}", "F4", d, "15:49", _f4(name)))
    assert len(out) == N_FEATURES and len({f.fid for f in out}) == N_FEATURES
    return out


P3_REF = Feature("P3_reference", "reference", "P3: sign r(15:50 open -> 15:51 open) (known before the scan)",
                 "15:51", lambda P, sh: np.sign(lr(P.O[:, I1550 + sh], P.O[:, I1551 + sh])))


def spec_by_id(fid: str) -> Feature:
    for f in feature_specs() + [P3_REF]:
        if f.fid == fid:
            return f
    raise KeyError(fid)


def target(P: Panel, entry: str, sh: int = 0):
    return lr(P.O[:, mi(entry) + sh], P.C[:, I1559 + sh])


def lookahead_selfcheck(P: Panel, sh: int = 0, seed: int = 20261021) -> list:
    """Every feature equals itself computed on (1) the information set at its entry bar's open and
    (2) data with everything after that cut-off scrambled; its target starts at the entry bar."""
    rng = np.random.default_rng(seed)
    log = []
    for f in feature_specs() + [P3_REF]:
        e = mi(f.entry) + sh
        full = f.signal(P, sh)
        Om, Hm, Lm, Cm = (np.array(a, copy=True) for a in (P.O, P.H, P.L, P.C))
        Om[:, e + 1:] = np.nan
        Hm[:, e:] = np.nan
        Lm[:, e:] = np.nan
        Cm[:, e:] = np.nan
        Pm = Panel(P.dates, Om, Hm, Lm, Cm, P.prev_open, P.prev_close, P.meta)
        assert np.array_equal(full, f.signal(Pm, sh), equal_nan=True), f"{f.fid}: uses data after its entry"
        Os, Hs, Ls, Cs = (np.array(a, copy=True) for a in (P.O, P.H, P.L, P.C))
        for A_, cut in ((Os, e + 1), (Hs, e), (Ls, e), (Cs, e)):
            A_[:, cut:] *= np.exp(rng.normal(0, 0.01, A_[:, cut:].shape))
        Ps = Panel(P.dates, Os, Hs, Ls, Cs, P.prev_open, P.prev_close, P.meta)
        assert np.array_equal(full, f.signal(Ps, sh), equal_nan=True), f"{f.fid}: changes with the future"
        log.append(f.fid)
    return [f"{len(log)} signals (41 features + P3) at shift {sh} min: masked-at-entry == full and "
            "scrambled-future == full; every target starts at the entry bar open"]


# ------------------------------------------------------------------------------------------------
# statistics (NW and Holm as in analysis.py; BH and Wilson added here)
# ------------------------------------------------------------------------------------------------
def norm_two_sided_p(t: float) -> float:
    return float(math.erfc(abs(t) / math.sqrt(2.0)))


def norm_sf(t: float) -> float:
    return float(0.5 * math.erfc(t / math.sqrt(2.0)))


def nw_mean_test(y, lag: int = NW_LAG) -> dict:
    """Mean of y with a Newey-West (Bartlett) standard error. NaNs are dropped first (analysis.py)."""
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    n = int(len(y))
    if n < lag + 3:
        return {"n": n, "mean": float(np.mean(y)) if n else None, "se": None, "t": None, "p": None}
    mu = float(y.mean())
    e = y - mu
    lrv = float(e @ e) / n
    for j in range(1, lag + 1):
        lrv += 2.0 * (1.0 - j / (lag + 1.0)) * float(e[j:] @ e[:-j]) / n
    se = math.sqrt(max(lrv, 0.0) / n)
    if not se > 0:
        return {"n": n, "mean": mu, "se": se, "t": None, "p": None}
    t = mu / se
    return {"n": n, "mean": mu, "se": se, "t": t, "p": norm_two_sided_p(t)}


def nw_t_rows(Y, lag: int = NW_LAG) -> np.ndarray:
    """Row-wise NW t of a matrix with no NaNs; identical to nw_mean_test row by row (used by the null check)."""
    Y = np.asarray(Y, dtype=float)
    n = Y.shape[1]
    mu = Y.mean(axis=1)
    E = Y - mu[:, None]
    lrv = (E * E).sum(axis=1) / n
    for j in range(1, lag + 1):
        lrv += 2.0 * (1.0 - j / (lag + 1.0)) * (E[:, j:] * E[:, :-j]).sum(axis=1) / n
    se = np.sqrt(np.maximum(lrv, 0.0) / n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return mu / se


def holm(pvals) -> list:
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(np.argsort(p, kind="stable")):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj.tolist()


def bh_q(pvals) -> list:
    p = np.array([1.0 if (x is None or not np.isfinite(x)) else x for x in pvals], dtype=float)
    m = len(p)
    order = np.argsort(p, kind="stable")
    q = np.empty(m)
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, p[i] * m / rank)
        q[i] = prev
    return q.tolist()


def wilson(k: int, n: int, z: float = Z95):
    if n <= 0:
        return None
    ph = k / n
    den = 1.0 + z * z / n
    centre = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return [centre - half, centre + half]


def summarize(sig, tgt, dirn: int = 1) -> dict:
    s = dirn * np.asarray(sig, float)
    tgt = np.asarray(tgt, float)
    with np.errstate(invalid="ignore"):
        y = s * tgt * 1e4
    ok = np.isfinite(y)
    nw = nw_mean_test(y[ok])
    trade = ok & (s != 0)
    nz = trade & (tgt != 0)
    k = int((y[nz] > 0).sum())
    n_nz = int(nz.sum())
    yt = y[trade]
    n_tr = int(trade.sum())
    return {"n": int(ok.sum()), "n_undefined": int((~ok).sum()), "n_zero_signal": int((ok & (s == 0)).sum()),
            "n_trades": n_tr, "n_trades_zero_target": int((trade & (tgt == 0)).sum()),
            "mean_bps": nw["mean"], "nw_se_bps": nw["se"], "nw_t": nw["t"], "p_two_sided": nw["p"],
            "mean_bps_per_trade": float(yt.mean()) if yt.size else None,
            "sd_bps_per_trade": float(yt.std(ddof=1)) if yt.size > 1 else None,
            "hit_rate": k / n_nz if n_nz else None, "n_hits": k, "n_hit_days": n_nz,
            "hit_rate_wilson95": wilson(k, n_nz),
            "hit_rate_zero_target_as_miss": k / n_tr if n_tr else None,
            "hit_rate_zero_target_as_miss_wilson95": wilson(k, n_tr)}


def n_needed_mean(mean, sd):
    if mean is None or sd is None or not mean > 0:
        return None
    return int(math.ceil(((Z_ALPHA_ONE_SIDED + Z_POWER) * sd / mean) ** 2))


def n_needed_prop(p, p0):
    if p is None or p0 is None or not p > p0 or not 0 < p0 < 1:
        return None
    num = Z_ALPHA_ONE_SIDED * math.sqrt(p0 * (1 - p0)) + Z_POWER * math.sqrt(p * (1 - p))
    return int(math.ceil((num / (p - p0)) ** 2))


# ------------------------------------------------------------------------------------------------
# step 1: discovery
# ------------------------------------------------------------------------------------------------
SELECTION_RULE = (f"candidates = features with |NW t| >= {DISCOVERY_ABS_T} in DISCOVERY, at most the "
                  f"{MAX_CANDIDATES} largest |t| (ties by feature order); direction = sign of the discovery mean")


def p3_agreement(P: Panel, fid: str) -> float | None:
    s = spec_by_id(fid).signal(P)
    p3 = P3_REF.signal(P)
    m = np.isfinite(s) & np.isfinite(p3) & (s != 0)
    return float((np.sign(s[m]) == np.sign(p3[m])).mean()) if m.any() else None


def discover_core(P: Panel) -> tuple[dict, list]:
    assert_no_holdout(P.dates)                       # before any target is computed
    assert P.dates.max() <= DISCOVERY[1]
    rows = []
    for f in feature_specs():
        st = summarize(f.signal(P), target(P, f.entry))
        rows.append({"feature": f.fid, "family": f.family, "desc": f.desc, "entry": f.entry,
                     "target": f"r({f.entry} open -> 15:59 close)", **st})
    q = bh_q([r["p_two_sided"] for r in rows])
    for r, qq in zip(rows, q):
        r["bh_q"] = qq
    eligible = [i for i, r in enumerate(rows) if r["nw_t"] is not None and abs(r["nw_t"]) >= DISCOVERY_ABS_T]
    eligible.sort(key=lambda i: (-abs(rows[i]["nw_t"]), i))
    chosen = eligible[:MAX_CANDIDATES]
    cands = []
    for rank, i in enumerate(chosen, 1):
        r = rows[i]
        agree = p3_agreement(P, r["feature"])
        cands.append({"rank": rank, "feature": r["feature"], "direction": int(np.sign(r["mean_bps"])),
                      "entry": r["entry"], "target": r["target"], "desc": r["desc"],
                      "discovery_nw_t": r["nw_t"], "discovery_mean_bps": r["mean_bps"],
                      "discovery_hit_rate": r["hit_rate"], "discovery_bh_q": r["bh_q"],
                      "discovery_agreement_with_P3_sign": agree,
                      "overlaps_known_P3": bool(agree is not None and agree >= OVERLAP_P3_THRESHOLD)})
    for r in rows:
        r["candidate"] = r["feature"] in {c["feature"] for c in cands}
    p3 = summarize(P3_REF.signal(P), target(P, P3_REF.entry))
    out = {"features": rows,
           "p3_reference_row": {"feature": P3_REF.fid, "desc": P3_REF.desc, "entry": P3_REF.entry,
                                "note": "reference only: never a candidate, outside the BH family", **p3},
           "n_features": len(rows), "n_abs_t_ge_threshold": len(eligible),
           "n_bh_q_lt_0.05": int(sum(1 for r in rows if r["bh_q"] < 0.05)),
           "n_bh_q_lt_0.10": int(sum(1 for r in rows if r["bh_q"] < 0.10)),
           "selection_rule": SELECTION_RULE,
           "candidates": [{"feature": c["feature"], "direction": c["direction"], "discovery_nw_t": c["discovery_nw_t"]}
                          for c in cands]}
    return out, cands


def candidates_payload(cands: list, P: Panel, prereg_sha: str, scan_sha: str) -> dict:
    return {"what": "Frozen candidate list of the SPX close candle scan (features + direction). Written and "
                    "hashed by `scan.py discover` before any holdout return is read; `scan.py holdout` "
                    "refuses to run unless this file matches candidates.sha256.",
            "prereg": str(PREREG), "prereg_sha256": prereg_sha,
            "scan_py_sha256_at_freeze": scan_sha,
            "frozen_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "discovery_window": list(DISCOVERY),
            "discovery_sample": {"first": str(P.dates.min()), "last": str(P.dates.max()), "n_days": int(len(P.dates))},
            "selection_rule": SELECTION_RULE,
            "n_candidates": len(cands), "candidates": cands}


def write_frozen(out_dir: Path, payload: dict) -> str:
    b = (json.dumps(_clean(payload), indent=1) + "\n").encode()
    (out_dir / CAND_FILE).write_bytes(b)
    h = sha256_bytes(b)
    (out_dir / SHA_FILE).write_text(f"{h}  {CAND_FILE}\n")
    return h


class HashGateError(RuntimeError):
    pass


def verify_gate(out_dir: Path) -> dict:
    cp, sp = Path(out_dir) / CAND_FILE, Path(out_dir) / SHA_FILE
    if not sp.exists():
        raise HashGateError(f"refusing to run: {sp} is missing (run `scan.py discover` first)")
    if not cp.exists():
        raise HashGateError(f"refusing to run: {cp} is missing")
    expected = sp.read_text().split()[0].strip().lower()
    actual = sha256_file(cp)
    if expected != actual:
        raise HashGateError(f"refusing to run: {CAND_FILE} SHA-256 {actual} != frozen {expected}")
    c = json.loads(cp.read_text())
    return {"candidates": c, "sha256": actual}


def run_discover(out_dir: Path = HERE, d1_file: Path = D1_FILE, days_file: Path = D1_DAYS,
                 refreeze: bool = False, prereg: Path = PREREG) -> dict:
    t0 = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pr = check_prereg_params(prereg)
    P = load_panel(DISCOVERY[0], DISCOVERY[1], d1_file, days_file)
    assert_no_holdout(P.dates)
    look = lookahead_selfcheck(P)
    disc, cands = discover_core(P)
    scan_sha = sha256_file(Path(__file__))
    cp = out_dir / CAND_FILE
    freeze = {}
    new_list = [(c["feature"], c["direction"]) for c in cands]
    if cp.exists():
        old = json.loads(cp.read_text())
        old_list = [(c["feature"], c["direction"]) for c in old["candidates"]]
        if old_list == new_list:
            verify_gate(out_dir)            # existing freeze kept byte-for-byte; its hash must still match
            freeze = {"action": "existing frozen file kept unchanged (same candidates and directions)",
                      "sha256": sha256_file(cp)}
        else:
            if not refreeze or (out_dir / HOLD_FILE).exists():
                raise RuntimeError("discovery now selects different candidates than the frozen file; refusing "
                                   "to overwrite (use --refreeze, and only before holdout.json exists)")
            freeze = {"action": "re-frozen (explicit --refreeze before any holdout run)",
                      "sha256": write_frozen(out_dir, candidates_payload(cands, P, pr["sha256"], scan_sha))}
    else:
        freeze = {"action": "frozen", "sha256": write_frozen(out_dir, candidates_payload(cands, P, pr["sha256"], scan_sha))}
    res = {"what": "SPX close candle scan, step 1 (DISCOVERY only, 2013-02-28 .. 2020-12-31). Every number "
                   "here comes from discovery days; no holdout bar was parsed (the bar file is read in date "
                   "order and reading stopped at the first row after 2020-12-31).",
           "meta": {"prereg": str(prereg), "prereg_sha256": pr["sha256"], "prereg_params_checked": True,
                    "script": str(Path(__file__)), "scan_py_sha256": scan_sha,
                    "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "decisions_and_interpretations": DECISIONS, "runtime_s": None},
           "data": {**P.meta, "holdout_dates_present": bool((P.dates >= HOLDOUT[0]).any()),
                    "max_date": str(P.dates.max())},
           "lookahead_selfcheck": look,
           **disc,
           "freeze": {"file": str(cp), "sha_file": str(out_dir / SHA_FILE), **freeze}}
    prev = archive_previous(out_dir, DISC_FILE, "discovery")
    if prev is not None:
        old_t = {r["feature"]: r.get("nw_t") for r in prev["content"].get("features", [])}
        dts = [abs(r["nw_t"] - old_t[r["feature"]]) for r in res["features"]
               if r["nw_t"] is not None and old_t.get(r["feature"]) is not None]
        res["rerun_vs_previous_run"] = {
            "previous_file_archived_to": prev["archived_to"], "previous_generated_utc": prev["generated_utc"],
            "previous_scan_py_sha256": prev["scan_py_sha256"], "this_scan_py_sha256": scan_sha,
            "previous_candidates": prev["content"].get("candidates"), "this_candidates": res["candidates"],
            "same_candidates": prev["content"].get("candidates") == _clean(res["candidates"]),
            "max_abs_t_diff_all_41": max(dts) if dts else None}
    res["meta"]["runtime_s"] = round(time.time() - t0, 2)
    write_json(out_dir / DISC_FILE, res)
    return res


# ------------------------------------------------------------------------------------------------
# step 2: holdout
# ------------------------------------------------------------------------------------------------
def holdout_tests(P: Panel, cands: list) -> dict:
    rows = []
    for c in cands:
        f = spec_by_id(c["feature"])
        st = summarize(f.signal(P), target(P, f.entry), c["direction"])
        p1 = norm_sf(st["nw_t"]) if st["nw_t"] is not None else 1.0
        rows.append({"feature": c["feature"], "direction": c["direction"], "entry": f.entry,
                     "discovery_nw_t": c.get("discovery_nw_t"), **st, "p_one_sided": p1,
                     "overlaps_known_P3": c.get("overlaps_known_P3")})
    adj = holm([r["p_one_sided"] for r in rows]) if rows else []
    for r, a in zip(rows, adj):
        r["p_holm"] = a
        r["passes_holm_5pct"] = bool(a < ALPHA)
    return {"rows": rows, "n_candidates": len(rows), "n_pass_holm": int(sum(r["passes_holm_5pct"] for r in rows))}


def economics(P: Panel, sig, entry: str, dirn: int, level_scale: float | None = None) -> dict:
    s = dirn * np.asarray(sig, float)
    o = P.O[:, mi(entry)]
    cl = P.C[:, I1559]
    trade = np.isfinite(s) & np.isfinite(o) & np.isfinite(cl) & (s != 0)
    if level_scale is None:
        m = (cl - o)[trade]
    else:
        m = (cl / o - 1.0)[trade] * level_scale
    st = s[trade]
    am = np.abs(m)
    correct = st * m > 0
    n = int(trade.sum())
    if n == 0 or correct.sum() == 0:
        return {"n_trades": n, "evaluable": False}
    E_all, E_c = float(am.mean()), float(am[correct].mean())
    E_w = float(am[~correct].mean()) if (~correct).any() else None
    pay = np.where(correct, am, 0.0)
    signed = float((st * m).mean())
    out = {"n_trades": n, "units": "index points" + ("" if level_scale is None else f" at level {level_scale:.2f}"),
           "share_correct_incl_zero_moves": float(correct.mean()),
           "mean_abs_move_all": E_all, "mean_abs_move_correct_days": E_c, "mean_abs_move_wrong_days": E_w,
           "ratio_abs_move_correct_to_all": E_c / E_all if E_all > 0 else None,
           "median_abs_move_correct_days": float(np.median(am[correct])),
           "median_abs_move_wrong_days": float(np.median(am[~correct])) if (~correct).any() else None,
           "mean_signed_move": signed,
           "realized_move_fair_straddle": E_all, "option_cost_ex_costs_half_straddle": 0.5 * E_all,
           "fee_cases": {}}
    if level_scale is not None:
        out["caveat"] = ("2021-2026 moves rescaled to the last D1 price level; this ignores that recent volatility "
                         "is lower than the 2021-2026 average, so it flatters the break-even (the fixed half-spread "
                         "becomes relatively smaller)")
    for fee in FEES:
        extras = HALF_SPREAD + fee / MULT
        cost = 0.5 * E_all + extras
        h_be = cost / E_c
        h_sn = cost / E_all
        pnl_usd = MULT * (pay - cost)
        mu = float(pnl_usd.mean())
        sd = float(pnl_usd.std(ddof=1)) if n > 1 else None
        t_iid = mu / (sd / math.sqrt(n)) if sd else None
        nwp = nw_mean_test(pnl_usd)
        out["fee_cases"][f"fee_{fee:.2f}"] = {
            "option_cost_pts": cost, "breakeven_hit_rate": h_be, "breakeven_hit_rate_size_neutral": h_sn,
            "mean_pnl_usd_per_trade_at_observed_hits": mu, "sd_pnl_usd_per_trade": sd,
            "trades_needed_option_pnl_80pct_power": n_needed_mean(mu, sd),
            "option_pnl_test": {
                "what": "direct one-sided test of mean option P&L per trade > 0 (trades in date order)",
                "mean_usd": mu, "t_iid": t_iid, "p_one_sided_iid": norm_sf(t_iid) if t_iid is not None else None,
                "t_nw5": nwp["t"], "p_one_sided_nw5": norm_sf(nwp["t"]) if nwp["t"] is not None else None,
                "identity_usd_0.5_x_mean_signed_move_minus_spread_and_fee": MULT * (0.5 * signed - extras),
                "identity_note": "with strike = entry price and cost = half the realized-move-fair straddle + "
                                 "extras, mean P&L = 0.5 x mean signed move - extras exactly, so this test is "
                                 "the mean-return test in option units"},
            "markup_where_mean_pnl_is_zero": (float(pay.mean()) - extras) / (0.5 * E_all) if E_all > 0 else None}
    return out


def min_hit_rate_accurate(n: int | None, be: float | None) -> float | None:
    """Smallest hit rate k/n whose Wilson 95% lower bound exceeds the break-even `be` (the 'accurate' bar)."""
    if not n or be is None or not 0 < be < 1:
        return None
    for k in range(max(0, int(math.floor(be * n))), n + 1):
        if wilson(k, n)[0] > be:
            return k / n
    return None


def markup_for_breakeven(e_pts: dict, hit: float | None, fee: float) -> float | None:
    """Straddle markup over realized-fair at which the primary break-even equals `hit`."""
    if hit is None or not e_pts.get("fee_cases"):
        return None
    return (hit * e_pts["mean_abs_move_correct_days"] - HALF_SPREAD - fee / MULT) / (0.5 * e_pts["mean_abs_move_all"])


def placebo(P: Panel, cands: list) -> list:
    out = []
    for c in cands:
        f = spec_by_id(c["feature"])
        st = summarize(f.signal(P, PLACEBO_SHIFT), target(P, f.entry, PLACEBO_SHIFT), c["direction"])
        st["p_one_sided"] = norm_sf(st["nw_t"]) if st["nw_t"] is not None else None
        out.append({"feature": c["feature"], "direction": c["direction"],
                    "placebo_entry": hhmm(mi(f.entry) + PLACEBO_SHIFT), "placebo_target_end": hhmm(I1559 + PLACEBO_SHIFT),
                    **st})
    return out


def descriptive_all(P: Panel, label: str) -> dict:
    rows = {}
    for f in feature_specs() + [P3_REF]:
        st = summarize(f.signal(P), target(P, f.entry))
        rows[f.fid] = {k: st[k] for k in ("n_trades", "hit_rate", "hit_rate_wilson95", "mean_bps", "nw_t")}
    return {"label": label, "first": str(P.dates.min()), "last": str(P.dates.max()), "n_days": int(len(P.dates)),
            "NOT_A_TEST": "descriptive only: raw signal direction (+1 = up), no selection, no multiple-testing "
                          "control; do not read significance into these", "features": rows}


def load_daily_closes():
    closes = {}
    for f in sorted(glob.glob(str(RH_RAW / "spx_daily_*.json"))):
        j = json.loads(Path(f).read_text())
        for res in j["data"]["results"]:
            if res.get("symbol") != "SPX" or res.get("interval") != "day":
                continue
            for b in res["bars"]:
                if b.get("interpolated"):
                    continue
                d = b["begins_at"][:10]
                c = float(b["close_value"])
                if d in closes:
                    assert abs(closes[d] - c) < 0.005, f"daily close mismatch {d}"
                closes[d] = c
    return closes


def _read_csv_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _ratio_boot_ci(rows, n_boot: int = N_BOOT, seed: int = 20261021, den: str = "realized_abs_move_official_bps"):
    """iid day bootstrap of mean(market straddle bps) / mean(den bps)."""
    pairs = np.array([(r["straddle_bps"], r[den]) for r in rows if r[den] is not None])
    if len(pairs) < 2:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(pairs), (n_boot, len(pairs)))
    ratio = pairs[idx, 0].mean(axis=1) / pairs[idx, 1].mean(axis=1)
    return [float(np.quantile(ratio, 0.025)), float(np.quantile(ratio, 0.975))]


def straddle_crosscheck(P_hold: Panel) -> dict:
    """Market ATM straddle vs the assumed realized-move-fair straddle (D1 holdout mean |move|)."""
    fair = {}
    for entry in ENTRIES:
        r = np.exp(target(P_hold, entry)) - 1.0
        ok = np.isfinite(r)
        late = ok & (P_hold.dates >= LATE_START)
        fair[entry] = {"holdout_mean_abs_move_bps": float(np.abs(r[ok]).mean() * 1e4),
                       "late_2023_2026_mean_abs_move_bps": float(np.abs(r[late]).mean() * 1e4)}
    files10 = sorted(glob.glob(str(DATA / "d2_chunk_*_options_10m.csv")))
    spx_files = sorted(glob.glob(str(DATA / "d2_chunk_*_spx_1m.csv")))
    marks = {}
    for f in files10:
        for r in _read_csv_rows(f):
            if r["interpolated"].strip().lower() == "true" or r["time_et"] != "15:40":
                continue
            marks[(r["date"], r["type"], float(r["strike"]))] = float(r["close"])
    s1549 = {}
    for f in spx_files:
        for r in _read_csv_rows(f):
            if r["time_et"] == "15:49" and r["interpolated"].strip().lower() != "true":
                s1549[r["date"]] = float(r["close"])
    closes = load_daily_closes()
    d1_ix = {d: i for i, d in enumerate(P_hold.dates)}
    days = sorted({d for d, _, _ in marks})
    rows = []
    for d in days:
        if d not in s1549:
            continue
        S = s1549[d]
        K = math.floor(S / STRIKE_STEP + 0.5) * STRIKE_STEP
        c, p = marks.get((d, "call", K)), marks.get((d, "put", K))
        if c is None or p is None:
            continue
        settle = closes.get(d)
        i = d1_ix.get(d)
        d1_abs = {e: (float(abs(math.exp(target(P_hold, e)[i]) - 1.0) * 1e4) if i is not None else None) for e in ENTRIES}
        rows.append({"date": d, "spx_1549_close": S, "K": K, "K_minus_S": K - S, "call_10m_1540_close": c,
                     "put_10m_1540_close": p, "straddle_pts": c + p, "straddle_bps": (c + p) / S * 1e4,
                     "parity_atm_dev_pts": c - p - (S - K), "settle_official": settle,
                     "realized_abs_move_official_bps": abs(settle - S) / S * 1e4 if settle else None,
                     "straddle_payoff_abs_settle_minus_K_pts": abs(settle - K) if settle else None,
                     "straddle_payoff_abs_settle_minus_K_bps": abs(settle - K) / S * 1e4 if settle else None,
                     "d1_abs_move_bps_same_day": d1_abs})
    mk = np.array([r["straddle_bps"] for r in rows])
    real = np.array([r["realized_abs_move_official_bps"] for r in rows if r["realized_abs_move_official_bps"] is not None])
    payk = np.array([r["straddle_payoff_abs_settle_minus_K_bps"] for r in rows
                     if r["straddle_payoff_abs_settle_minus_K_bps"] is not None])
    diff_pts = np.array([r["straddle_pts"] - r["straddle_payoff_abs_settle_minus_K_pts"] for r in rows
                         if r["straddle_payoff_abs_settle_minus_K_pts"] is not None])
    ten = {"files": [Path(f).name for f in files10], "n_days": len(rows),
           "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None,
           "mean_market_straddle_bps": float(mk.mean()) if len(mk) else None,
           "median_market_straddle_bps": float(np.median(mk)) if len(mk) else None,
           "mean_realized_abs_move_official_bps_same_days": float(real.mean()) if len(real) else None,
           "ratio_market_to_realized_same_days": float(mk.mean() / real.mean()) if len(real) else None,
           "ratio_market_to_realized_same_days_boot95": _ratio_boot_ci(rows),
           "mean_straddle_payoff_abs_settle_minus_K_bps": float(payk.mean()) if len(payk) else None,
           "ratio_market_to_own_payoff_same_days": float(mk.mean() / payk.mean()) if len(payk) else None,
           "ratio_market_to_own_payoff_same_days_boot95": _ratio_boot_ci(
               rows, den="straddle_payoff_abs_settle_minus_K_bps"),
           "mean_straddle_minus_own_payoff_pts": float(diff_pts.mean()) if len(diff_pts) else None,
           "share_days_straddle_above_own_payoff": float((diff_pts > 0).mean()) if len(diff_pts) else None,
           "how_to_read": "ratio_market_to_own_payoff_same_days (added after the audits) is the like-for-like "
                          "markup: the straddle is struck at K, so its payoff is |settle - K|. "
                          "ratio_market_to_realized_same_days divides by |settle - S| instead (S = the SPX 15:49 "
                          "close; |K - S| <= 2.5 points). 1 = priced at realized-move-fair, the pre-registered "
                          "assumption. Either way this is an approximate cross-check on 22 days, not a validated "
                          "pricing multiplier. The ratio_market_to_assumed_fair_* values compare these 2026 days "
                          "with the D1 holdout average, i.e. different volatility regimes: below 1 they say the "
                          "recent move is smaller than the 2021-2026 average, not that options are cheap.",
           "max_abs_parity_dev_pts": float(max(abs(r["parity_atm_dev_pts"]) for r in rows)) if rows else None,
           "note": "10-minute closes are last trades in 15:40:00-15:49:59 (about 15:50), not simultaneous with "
                   "each other or with SPX; the straddle (call + put) is much less sensitive to that than either leg",
           "rows": rows}
    for e in ENTRIES:
        ten[f"ratio_market_to_assumed_fair_entry_{e}_holdout"] = float(mk.mean() / fair[e]["holdout_mean_abs_move_bps"]) if len(mk) else None
        ten[f"ratio_market_to_assumed_fair_entry_{e}_2023_2026"] = float(mk.mean() / fair[e]["late_2023_2026_mean_abs_move_bps"]) if len(mk) else None
    priced = []
    try:
        r = json.loads(RESULTS_1549.read_text())["h3"]["per_day"]["2026-10-20"]
        priced.append({"date": "2026-10-20", "source": str(RESULTS_1549), "S0_1549_open": r["S0"], "K0": r["K0"],
                       "straddle_mark_1549_pts": r["straddle_mark"], "settle": r["settle"], "settle_provisional": False})
    except Exception as exc:  # noqa: BLE001
        priced.append({"date": "2026-10-20", "error": repr(exc)})
    try:
        s = json.loads(LIVE_1021.read_text())
        priced.append({"date": s["date"], "source": str(LIVE_1021), "S0_1549_open": s["t0_spx"], "K0": s["K0"],
                       "straddle_mark_1549_pts": s["straddle_mark_1549"],
                       "straddle_ask_live_154851_pts": s.get("straddle_ask_live_154851"),
                       "settle": s["settlement_provisional"], "settle_provisional": True})
    except Exception as exc:  # noqa: BLE001
        priced.append({"date": "2026-10-21", "error": repr(exc)})
    for d in priced:
        if "error" in d:
            continue
        S0 = d["S0_1549_open"]
        fb = fair["15:49"]["holdout_mean_abs_move_bps"]
        d["straddle_bps"] = d["straddle_mark_1549_pts"] / S0 * 1e4
        d["assumed_fair_straddle_pts_entry_1549_holdout"] = fb * S0 / 1e4
        d["ratio_market_to_assumed_fair_holdout"] = d["straddle_mark_1549_pts"] / (fb * S0 / 1e4)
        d["ratio_market_to_assumed_fair_2023_2026"] = d["straddle_bps"] / fair["15:49"]["late_2023_2026_mean_abs_move_bps"]
        d["ratio_note"] = ("ratio_market_to_assumed_fair_* compare one 2026 straddle with the 2021-2026 (or 2023-2026) "
                           "average move: a volatility-regime comparison, not a pricing check. Use the same-day "
                           "straddle vs its own payoff instead.")
        d["realized_abs_move_pts"] = abs(d["settle"] - S0)
        d["straddle_payoff_abs_settle_minus_K0_pts"] = abs(d["settle"] - d["K0"])
        d["straddle_minus_own_payoff_pts"] = d["straddle_mark_1549_pts"] - abs(d["settle"] - d["K0"])
    return {"assumed_fair_straddle_bps_from_d1": fair, "robinhood_10m_days": ten, "fully_priced_days": priced}


def load_rh_spx_1m() -> tuple[dict, int]:
    """Robinhood SPX one-minute bars (non-interpolated) keyed by (date, time_et); duplicates across chunk files
    must agree to 0.005."""
    bars, n_dup_mismatch = {}, 0
    for f in sorted(glob.glob(str(DATA / "d2_chunk_*_spx_1m.csv"))):
        for r in _read_csv_rows(f):
            if r["interpolated"].strip().lower() == "true":
                continue
            key = (r["date"], r["time_et"])
            v = (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
            if key in bars and max(abs(a - b) for a, b in zip(bars[key], v)) >= 0.005:
                n_dup_mismatch += 1
            bars.setdefault(key, v)
    return bars, n_dup_mismatch


def cfd_vs_settlement(P_hold: Panel, test_rows: list) -> dict:
    """Does the D1 CFD target (entry open -> 15:59 bar close) have the same sign as the target the option pays
    on (SPX entry open -> official settlement)? Overlapping Robinhood days only (descriptive)."""
    spx, n_mis = load_rh_spx_1m()
    closes = load_daily_closes()
    d1_ix = {d: i for i, d in enumerate(P_hold.dates)}
    days = sorted({d for d, _ in spx} & set(d1_ix) & set(closes))
    by_entry = {}
    for e in ENTRIES:
        rows = []
        for d in days:
            i = d1_ix[d]
            so = spx.get((d, e))
            sc = spx.get((d, TARGET_END))
            if so is None or sc is None:
                continue
            a = math.log(P_hold.C[i, I1559] / P_hold.O[i, mi(e)])
            b = math.log(closes[d] / so[0])
            c = math.log(sc[3] / so[0])
            rows.append((d, a * 1e4, b * 1e4, c * 1e4))
        if len(rows) < 3:
            by_entry[e] = {"n_days": len(rows)}
            continue
        R = np.array([r[1:] for r in rows], float)
        by_entry[e] = {"n_days": len(rows), "first": rows[0][0], "last": rows[-1][0],
                       "corr_d1_vs_spx_settle": float(np.corrcoef(R[:, 0], R[:, 1])[0, 1]),
                       "sign_agreement_d1_vs_spx_settle": float((np.sign(R[:, 0]) == np.sign(R[:, 1])).mean()),
                       "sign_agreement_d1_vs_spx_1559_close": float((np.sign(R[:, 0]) == np.sign(R[:, 2])).mean()),
                       "mean_abs_d1_bps": float(np.abs(R[:, 0]).mean()),
                       "mean_abs_spx_settle_bps": float(np.abs(R[:, 1]).mean()),
                       "mean_abs_diff_d1_minus_spx_settle_bps": float(np.abs(R[:, 0] - R[:, 1]).mean()),
                       "rows_date_d1_spxsettle_spx1559_bps": [[r[0], round(r[1], 2), round(r[2], 2), round(r[3], 2)]
                                                              for r in rows]}
    # the 15:50 candle itself, D1 vs SPX
    agree_dir, agree_sb, n_c = [], [], 0
    for d in days:
        i = d1_ix[d]
        b = spx.get((d, "15:50"))
        if b is None:
            continue
        n_c += 1
        o, h, l_, c = (np.array([x]) for x in b)
        agree_dir.append(np.sign(c - o)[0] == np.sign(P_hold.C[i, I1550] - P_hold.O[i, I1550]))
        d1c = tuple(np.array([x]) for x in (P_hold.O[i, I1550], P_hold.H[i, I1550], P_hold.L[i, I1550], P_hold.C[i, I1550]))
        agree_sb.append(shape_strong_body(o, h, l_, c)[0] == shape_strong_body(*d1c)[0])
    mapped = {}
    for r in test_rows:
        e = spec_by_id(r["feature"]).entry
        a = by_entry.get(e, {}).get("sign_agreement_d1_vs_spx_settle")
        h = r.get("hit_rate")
        lo = (r.get("hit_rate_wilson95") or [None, None])[0]
        if a is None or h is None:
            continue
        mapped[r["feature"]] = {"sign_agreement_used": a, "hit_rate_cfd": h, "hit_rate_mapped": h * a + (1 - h) * (1 - a),
                                "ci_lower_cfd": lo,
                                "ci_lower_mapped": lo * a + (1 - lo) * (1 - a) if lo is not None else None}
    return {"what": "D1 CFD target vs the SPX settlement target the option pays on (descriptive, few days)",
            "n_duplicate_bar_mismatches_across_chunks": n_mis, "by_entry": by_entry,
            "candle_1550_n_days": n_c,
            "candle_1550_direction_agreement_d1_vs_spx": float(np.mean(agree_dir)) if agree_dir else None,
            "candle_1550_strong_body_signal_agreement_d1_vs_spx": float(np.mean(agree_sb)) if agree_sb else None,
            "hit_rate_mapped_to_settlement": mapped,
            "mapping_rule": "SENSITIVITY: if the settlement sign disagrees with the CFD sign on a share (1 - a) of "
                            "days, independently of whether the signal was right, a CFD hit rate h becomes "
                            "h a + (1 - h)(1 - a) against the settlement (same map for the CI lower bound)"}


def subperiods(Ph: Panel, cands: list, econ: dict) -> dict:
    """Descriptive: each candidate on 2021-2022, 2023-2026 and each holdout year, with that period's own
    economics (fair straddle from the period's own moves) and trades needed at the period's effect size."""
    years = sorted({d[:4] for d in Ph.dates})
    periods = [("2021_2022", Ph.dates <= EARLY_END), ("2023_2026", Ph.dates >= LATE_START)] + \
              [(y, np.array([d[:4] == y for d in Ph.dates])) for y in years]
    out = {}
    for c in cands:
        f = spec_by_id(c["feature"])
        full_ec = econ.get(c["feature"], {})
        tpy = full_ec.get("holdout_trades_per_252_days")
        be_full = full_ec.get("holdout_points", {}).get("fee_cases", {}).get("fee_0.09", {})
        rows = {}
        for lab, mask in periods:
            if not mask.any():
                continue
            P = sub(Ph, mask)
            sig = f.signal(P)
            st = summarize(sig, target(P, f.entry), c["direction"])
            ec = economics(P, sig, f.entry, c["direction"])
            fc = ec.get("fee_cases", {}).get("fee_0.09", {})
            ot = fc.get("option_pnl_test", {})
            ci = st["hit_rate_wilson95"] or [None, None]
            row = {"first": str(P.dates.min()), "last": str(P.dates.max()), "n_days": int(len(P.dates)),
                   "n_trades": st["n_trades"], "n_hit_days": st["n_hit_days"], "hit_rate": st["hit_rate"],
                   "hit_rate_wilson95": st["hit_rate_wilson95"], "mean_bps": st["mean_bps"], "nw_t": st["nw_t"],
                   "mean_bps_per_trade": st["mean_bps_per_trade"],
                   "own_breakeven_hit_rate_fee_0.09": fc.get("breakeven_hit_rate"),
                   "own_breakeven_size_neutral_fee_0.09": fc.get("breakeven_hit_rate_size_neutral"),
                   "option_pnl_usd_per_trade_fee_0.09": ot.get("mean_usd"), "option_pnl_t_iid": ot.get("t_iid"),
                   "option_pnl_t_nw5": ot.get("t_nw5"), "sd_pnl_usd_per_trade": fc.get("sd_pnl_usd_per_trade")}
            if lab in ("2021_2022", "2023_2026"):
                row["ci_vs_full_holdout_breakevens_fee_0.09"] = {
                    "ci_lower": ci[0], "includes_50pct": bool(ci[0] is not None and ci[0] <= 0.5),
                    "includes_primary_breakeven": bool(ci[0] is not None and be_full.get("breakeven_hit_rate") is not None
                                                       and ci[0] <= be_full["breakeven_hit_rate"]),
                    "includes_size_neutral_breakeven": bool(
                        ci[0] is not None and be_full.get("breakeven_hit_rate_size_neutral") is not None
                        and ci[0] <= be_full["breakeven_hit_rate_size_neutral"])}
                need = {"mean_return": n_needed_mean(st["mean_bps_per_trade"], st["sd_bps_per_trade"]),
                        "hit_vs_50pct": n_needed_prop(st["hit_rate"], 0.5),
                        "hit_vs_own_size_neutral_breakeven": n_needed_prop(st["hit_rate"],
                                                                           fc.get("breakeven_hit_rate_size_neutral")),
                        "option_pnl": fc.get("trades_needed_option_pnl_80pct_power")}
                row["trades_needed_at_this_period_effect_80pct_power"] = need
                row["years_needed_at_full_holdout_trade_rate"] = {k: (v / tpy if v is not None and tpy else None)
                                                                  for k, v in need.items()}
            rows[lab] = row
        out[c["feature"]] = rows
    return {"NOT_A_TEST": "descriptive sub-periods inside the holdout; no multiple-testing control", "candidates": out}


P1_SIGNAL = lambda P: np.sign(lr(P.O[:, 0], P.O[:, I1549]))      # noqa: E731  (P1 of spx_close_1549)


def known_effect_flags(Pd: Panel, cands: list) -> dict:
    """Which frozen candidates are already-known effects (P3 or P1 of spx_close_1549, whose 2013-2026 results,
    which include the holdout years, were known before the pre-registration)."""
    p1 = P1_SIGNAL(Pd)
    out = {}
    for c in cands:
        s = spec_by_id(c["feature"]).signal(Pd)
        m = np.isfinite(s) & np.isfinite(p1) & (s != 0)
        a1 = float((np.sign(s[m]) == np.sign(p1[m])).mean()) if m.any() else None    # raw sign, as p3_agreement
        p3 = bool(c.get("overlaps_known_P3"))
        p1f = bool(a1 is not None and a1 >= OVERLAP_P3_THRESHOLD)
        out[c["feature"]] = {"discovery_agreement_with_P3_sign": c.get("discovery_agreement_with_P3_sign"),
                             "overlaps_known_P3": p3, "discovery_agreement_with_P1_sign": a1,
                             "overlaps_known_P1": p1f, "holdout_is_blind_test": not (p3 or p1f)}
    return {"rule": f"agreement of the candidate's non-zero signals (frozen direction) with the known signal's sign "
                    f"on discovery days >= {OVERLAP_P3_THRESHOLD:.0%}; computed in the holdout step, the frozen file "
                    "is unchanged",
            "candidates": out, "n_blind": int(sum(v["holdout_is_blind_test"] for v in out.values()))}


def empirical_size_real_data(Pd: Panel, Ph: Panel, cands: list, n_sims: int = SIZE_SIMS,
                             seed: int = 20261021) -> dict:
    """Real-data null check for the NW tests: (a) random-sign signals against the real D1 targets; (b) the real
    41 discovery signals circularly shifted as a block against the real targets (keeps their autocorrelation
    and cross-correlation, breaks the day alignment), with the discovery selection rule applied; (c) the
    frozen candidates' holdout signals circularly shifted, with the one-sided test and Holm."""
    rng = np.random.default_rng(seed)
    out = {"what": "how often the NW tests 'find' an effect when there is none, on the real D1 targets",
           "nominal": {"abs_t_ge_2.5": norm_two_sided_p(DISCOVERY_ABS_T), "one_sided_5pct": 0.05}}
    rs = {}
    for lab, P in (("discovery", Pd), ("holdout", Ph)):
        for e in ENTRIES:
            tg = target(P, e) * 1e4
            tg = tg[np.isfinite(tg)]
            ts = nw_t_rows(rng.choice([-1.0, 1.0], size=(n_sims, len(tg))) * tg[None, :])
            rs[f"{lab}_entry_{e}"] = {"n_sims": n_sims, "n_days": int(len(tg)),
                                      "share_abs_t_ge_2.5": float((np.abs(ts) >= DISCOVERY_ABS_T).mean()),
                                      "share_abs_t_ge_1.96": float((np.abs(ts) >= Z95).mean()),
                                      "share_one_sided_p_lt_5pct": float((ts >= Z_ALPHA_ONE_SIDED).mean())}
    out["random_sign_signals"] = rs
    feats = feature_specs()
    sig_d = [f.signal(Pd) for f in feats]
    tgt_d = {e: target(Pd, e) for e in ENTRIES}
    n = len(Pd.dates)
    offs = list(range(SHIFT_MIN_GAP, n - SHIFT_MIN_GAP + 1, SHIFT_STEP))
    counts, maxt, single = [], [], []
    for k in offs:
        ts = []
        for f, s in zip(feats, sig_d):
            t = nw_mean_test(np.roll(s, k) * tgt_d[f.entry] * 1e4)["t"]
            ts.append(abs(t) if t is not None else 0.0)
        ts = np.array(ts)
        counts.append(int((ts >= DISCOVERY_ABS_T).sum()))
        maxt.append(float(ts.max()))
        single.extend(ts.tolist())
    counts, maxt = np.array(counts), np.array(maxt)
    obs = [abs(c["discovery_nw_t"]) for c in cands if c.get("discovery_nw_t") is not None]
    out["circular_shift_41_features_discovery"] = {
        "n_shifts": len(offs), "shift_days": [offs[0], offs[-1], SHIFT_STEP] if offs else None,
        "share_single_tests_abs_t_ge_2.5": float(np.mean(np.array(single) >= DISCOVERY_ABS_T)) if single else None,
        "mean_n_features_abs_t_ge_2.5": float(counts.mean()) if len(counts) else None,
        "share_shifts_ge_1_candidate": float((counts >= 1).mean()) if len(counts) else None,
        "observed_n_candidates": len(obs),
        "share_shifts_ge_observed_n_candidates": float((counts >= len(obs)).mean()) if len(counts) and obs else None,
        "observed_max_abs_t": max(obs) if obs else None,
        "share_shifts_max_abs_t_ge_observed": float((maxt >= max(obs)).mean()) if len(maxt) and obs else None}
    nh = len(Ph.dates)
    offs_h = list(range(SHIFT_MIN_GAP, nh - SHIFT_MIN_GAP + 1, SHIFT_STEP))
    sig_h = [(c, spec_by_id(c["feature"]).signal(Ph)) for c in cands]
    rej, anyholm, ntest = 0, 0, 0
    for k in offs_h:
        ps = []
        for c, s in sig_h:
            f = spec_by_id(c["feature"])
            t = nw_mean_test(c["direction"] * np.roll(s, k) * target(Ph, f.entry) * 1e4)["t"]
            ps.append(norm_sf(t) if t is not None else 1.0)
        rej += sum(p < ALPHA for p in ps)
        ntest += len(ps)
        anyholm += bool(ps) and min(holm(ps)) < ALPHA
    out["circular_shift_candidates_holdout"] = {
        "n_shifts": len(offs_h), "n_candidates": len(cands),
        "share_single_one_sided_p_lt_5pct": rej / ntest if ntest else None,
        "share_shifts_any_holm_pass": anyholm / len(offs_h) if offs_h and cands else None}
    return out


def archive_previous(out_dir: Path, fname: str, kind: str) -> dict | None:
    """Copy an existing output into runs/ (named by its own generated_utc and scan SHA) before it is overwritten."""
    p = Path(out_dir) / fname
    if not p.exists():
        return None
    raw = p.read_bytes()
    j = json.loads(raw)
    meta = j.get("meta", {})
    tag = re.sub(r"[^0-9TZ]", "", meta.get("generated_utc") or "unknown")
    sha = (meta.get("scan_py_sha256") or "nosha")[:12]
    dest = Path(out_dir) / RUNS_DIR / f"{kind}_{tag}_scan{sha}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(raw)
    return {"archived_to": str(dest), "sha256": sha256_bytes(raw), "generated_utc": meta.get("generated_utc"),
            "scan_py_sha256": meta.get("scan_py_sha256"), "content": j}


def _g(d, *path):
    for k in path:
        if isinstance(d, dict):
            d = d.get(k)
        elif isinstance(d, list) and isinstance(k, int) and -len(d) <= k < len(d):
            d = d[k]
        else:
            return None
    return d


def compare_holdout_runs(old: dict, new: dict) -> dict:
    """old -> new for the headline numbers of two holdout outputs."""
    rows = []

    def add(key, a, b):
        same = (a == b) if not (isinstance(a, float) and isinstance(b, float)) else abs(a - b) <= 1e-12 * max(1, abs(a))
        rows.append({"key": key, "old": a, "new": b, "changed": not same})

    o_rows = {r["feature"]: r for r in _g(old, "holdout_test", "rows") or []}
    for r in _g(new, "holdout_test", "rows") or []:
        f = r["feature"]
        o = o_rows.get(f, {})
        for k in ("direction", "n_trades", "n_hit_days", "mean_bps", "nw_t", "p_one_sided", "p_holm",
                  "passes_holm_5pct", "hit_rate"):
            add(f"{f}.{k}", o.get(k), r.get(k))
        add(f"{f}.hit_rate_ci_lower", _g(o, "hit_rate_wilson95", 0), _g(r, "hit_rate_wilson95", 0))
        for fee in FEES:
            fk = f"fee_{fee:.2f}"
            for k in ("breakeven_hit_rate", "accurate_ci_lower_above_breakeven",
                      "trades_needed_hit_vs_breakeven_80pct_power"):
                add(f"{f}.{fk}.{k}", _g(old, "economics", "candidates", f, "verdict_vs_breakeven", fk, k),
                    _g(new, "economics", "candidates", f, "verdict_vs_breakeven", fk, k))
            add(f"{f}.{fk}.breakeven_size_neutral",
                _g(old, "economics", "candidates", f, "holdout_points", "fee_cases", fk, "breakeven_hit_rate_size_neutral"),
                _g(new, "economics", "candidates", f, "holdout_points", "fee_cases", fk, "breakeven_hit_rate_size_neutral"))
            add(f"{f}.{fk}.mean_option_pnl_usd",
                _g(old, "economics", "candidates", f, "holdout_points", "fee_cases", fk, "mean_pnl_usd_per_trade_at_observed_hits"),
                _g(new, "economics", "candidates", f, "holdout_points", "fee_cases", fk, "mean_pnl_usd_per_trade_at_observed_hits"))
        for lab in ("holdout", "discovery"):
            po = {x["feature"]: x for x in _g(old, "placebo_1149_1151", lab) or []}.get(f, {})
            pn = {x["feature"]: x for x in _g(new, "placebo_1149_1151", lab) or []}.get(f, {})
            add(f"{f}.placebo_{lab}.nw_t", po.get("nw_t"), pn.get("nw_t"))
    add("p3_reference_holdout.nw_t", _g(old, "p3_reference_holdout", "nw_t"), _g(new, "p3_reference_holdout", "nw_t"))
    add("straddle.ratio_market_to_realized_same_days",
        _g(old, "straddle_cost_crosscheck", "robinhood_10m_days", "ratio_market_to_realized_same_days"),
        _g(new, "straddle_cost_crosscheck", "robinhood_10m_days", "ratio_market_to_realized_same_days"))
    add("hash_gate.sha256", _g(old, "hash_gate", "sha256"), _g(new, "hash_gate", "sha256"))
    changed = [r for r in rows if r["changed"]]
    return {"n_compared": len(rows), "n_changed": len(changed), "changed_keys": [r["key"] for r in changed],
            "rows": rows}


def run_holdout(out_dir: Path = HERE, d1_file: Path = D1_FILE, days_file: Path = D1_DAYS,
                crosscheck: bool = True, prereg: Path = PREREG) -> dict:
    t0 = time.time()
    out_dir = Path(out_dir)
    gate = verify_gate(out_dir)                      # BEFORE any data is read
    frozen = gate["candidates"]
    pr = check_prereg_params(prereg)
    cands = frozen["candidates"]
    full = load_panel(DISCOVERY[0], HOLDOUT[1], d1_file, days_file)
    Ph = sub(full, full.dates >= HOLDOUT[0])
    Pd = sub(full, full.dates <= DISCOVERY[1])
    assert len(Ph.dates) + len(Pd.dates) == len(full.dates)
    look = lookahead_selfcheck(Ph) + lookahead_selfcheck(Ph, PLACEBO_SHIFT)
    disc_now, cands_now = discover_core(Pd)          # current code, discovery slice only
    repro = {"same_candidates_and_directions": [(c["feature"], c["direction"]) for c in cands_now]
             == [(c["feature"], c["direction"]) for c in cands]}
    now_t = {c["feature"]: c["discovery_nw_t"] for c in cands_now}
    fd = [abs(now_t[c["feature"]] - c["discovery_nw_t"]) for c in cands
          if c.get("discovery_nw_t") is not None and now_t.get(c["feature"]) is not None]
    repro["max_abs_t_diff_vs_frozen_candidates"] = max(fd) if fd else None
    dj = out_dir / DISC_FILE
    if dj.exists():
        old = {r["feature"]: r["nw_t"] for r in json.loads(dj.read_text())["features"]}
        diffs = [abs(r["nw_t"] - old[r["feature"]]) for r in disc_now["features"]
                 if r["nw_t"] is not None and old.get(r["feature"]) is not None]
        repro["max_abs_t_diff_vs_discovery_json"] = max(diffs) if diffs else None
    # enforcing (post-audit): the current code must reproduce the frozen discovery before any holdout test
    if not repro["same_candidates_and_directions"]:
        raise RuntimeError("current code selects different discovery candidates than the frozen file; aborting")
    for k in ("max_abs_t_diff_vs_frozen_candidates", "max_abs_t_diff_vs_discovery_json"):
        if repro.get(k) is not None and repro[k] > 1e-9:
            raise RuntimeError(f"current code does not reproduce discovery ({k} = {repro[k]}); aborting")
    repro["enforced"] = "aborts unless candidates/directions match and every t differs by <= 1e-9"
    tests = holdout_tests(Ph, cands)
    known = known_effect_flags(Pd, cands)
    for r in tests["rows"]:
        r.update({k: known["candidates"][r["feature"]][k] for k in ("overlaps_known_P1", "holdout_is_blind_test")})
    p3h = summarize(P3_REF.signal(Ph), target(Ph, P3_REF.entry))
    p3h["p_one_sided_positive"] = norm_sf(p3h["nw_t"]) if p3h["nw_t"] is not None else None
    last_level = float(full.O[-1, I1549])
    xc = straddle_crosscheck(Ph) if crosscheck else None
    econ = {}
    generic = {}
    for e in ENTRIES:   # size-neutral reference: always buy the call (direction irrelevant to |move|)
        ones = np.ones(len(Ph.dates))
        generic[e] = {"holdout_points": economics(Ph, ones, e, 1), "at_last_level": economics(Ph, ones, e, 1, last_level)}
    for r in tests["rows"]:
        f = spec_by_id(r["feature"])
        sig = f.signal(Ph)
        e_pts = economics(Ph, sig, f.entry, r["direction"])
        e_lvl = economics(Ph, sig, f.entry, r["direction"], last_level)
        h, lo = r["hit_rate"], (r["hit_rate_wilson95"] or [None, None])[0]
        lo_z = (r.get("hit_rate_zero_target_as_miss_wilson95") or [None, None])[0]
        verdict = {}
        for fee in FEES:
            key = f"fee_{fee:.2f}"
            fc = e_pts["fee_cases"][key] if e_pts.get("fee_cases") else {}
            be = fc.get("breakeven_hit_rate")
            be_sn = fc.get("breakeven_hit_rate_size_neutral")
            be_l = e_lvl["fee_cases"][key]["breakeven_hit_rate"] if e_lvl.get("fee_cases") else None
            verdict[key] = {"breakeven_hit_rate": be, "breakeven_hit_rate_at_last_level": be_l,
                            "hit_rate_ci_lower": lo,
                            "accurate_ci_lower_above_breakeven": bool(lo is not None and be is not None and lo > be),
                            "trades_needed_hit_vs_breakeven_80pct_power": n_needed_prop(h, be),
                            "trades_needed_hit_vs_breakeven_at_last_level": n_needed_prop(h, be_l),
                            # post-audit additions (reporting)
                            "breakeven_hit_rate_size_neutral": be_sn,
                            "accurate_vs_size_neutral_breakeven": bool(lo is not None and be_sn is not None and lo > be_sn),
                            "trades_needed_hit_vs_size_neutral_breakeven_80pct_power": n_needed_prop(h, be_sn),
                            "hit_rate_zero_target_as_miss": r.get("hit_rate_zero_target_as_miss"),
                            "ci_lower_zero_target_as_miss": lo_z,
                            "accurate_zero_target_as_miss": bool(lo_z is not None and be is not None and lo_z > be),
                            "min_hit_rate_accurate_at_holdout_n": min_hit_rate_accurate(r["n_hit_days"], be),
                            "min_hit_rate_accurate_size_neutral_at_holdout_n": min_hit_rate_accurate(r["n_hit_days"], be_sn),
                            "one_year_of_trades": int(round(r["n_trades"] / len(Ph.dates) * 252)),
                            "min_hit_rate_accurate_in_one_year": min_hit_rate_accurate(
                                int(round(r["n_trades"] / len(Ph.dates) * 252)), be),
                            "min_hit_rate_accurate_size_neutral_in_one_year": min_hit_rate_accurate(
                                int(round(r["n_trades"] / len(Ph.dates) * 252)), be_sn),
                            "markup_where_breakeven_equals_ci_lower": markup_for_breakeven(e_pts, lo, fee),
                            "markup_where_mean_pnl_is_zero": fc.get("markup_where_mean_pnl_is_zero"),
                            "option_pnl_test": fc.get("option_pnl_test")}
        if xc:
            t10 = xc["robinhood_10m_days"]
            sens = {}
            for basis, pk, ck in (("vs_abs_settle_minus_S", "ratio_market_to_realized_same_days",
                                   "ratio_market_to_realized_same_days_boot95"),
                                  ("vs_own_payoff_abs_settle_minus_K", "ratio_market_to_own_payoff_same_days",
                                   "ratio_market_to_own_payoff_same_days_boot95")):
                mk_pt, mk_ci = t10.get(pk), t10.get(ck)
                if not mk_pt or not e_pts.get("fee_cases"):
                    continue
                sens[basis] = {}
                for lab, ratio in (("point", mk_pt), ("boot95_low", (mk_ci or [None, None])[0]),
                                   ("boot95_high", (mk_ci or [None, None])[1])):
                    if ratio is None:
                        continue
                    sens[basis][lab] = {"markup": ratio}
                    for fee in FEES:
                        cost = 0.5 * ratio * e_pts["mean_abs_move_all"] + HALF_SPREAD + fee / MULT
                        sens[basis][lab][f"fee_{fee:.2f}"] = cost / e_pts["mean_abs_move_correct_days"]
            e_pts["sensitivity_breakeven_with_observed_market_markup"] = {
                "rule": "option cost = 0.5 x markup x realized-move-fair straddle + half-spread + fee, markup = "
                        "market straddle / realized official move on the 22 Robinhood 10-minute days; "
                        "vs_own_payoff_abs_settle_minus_K is the like-for-like basis (added after the audits)",
                "breakeven_hit_rate": sens,
                "caveat": "sensitivity, not the pre-registered assumption; 22 days, so the markup is uncertain"}
        econ[r["feature"]] = {"holdout_points": e_pts, "at_last_level": e_lvl, "verdict_vs_breakeven": verdict,
                              "trades_needed_mean_return_80pct_power": n_needed_mean(r["mean_bps_per_trade"], r["sd_bps_per_trade"]),
                              "trades_needed_hit_vs_50pct_80pct_power": n_needed_prop(h, 0.5),
                              "holdout_trades_available": r["n_trades"],
                              "holdout_trades_per_252_days": r["n_trades"] / len(Ph.dates) * 252}
        tpy = econ[r["feature"]]["holdout_trades_per_252_days"]
        econ[r["feature"]]["years_needed_at_holdout_trade_rate"] = {
            k: (v / tpy if v is not None and tpy else None) for k, v in (
                ("mean_return", econ[r["feature"]]["trades_needed_mean_return_80pct_power"]),
                ("hit_vs_breakeven_fee_0.09", verdict["fee_0.09"]["trades_needed_hit_vs_breakeven_80pct_power"]),
                ("option_pnl_fee_0.09", e_pts.get("fee_cases", {}).get("fee_0.09", {}).get("trades_needed_option_pnl_80pct_power")))}
    pl_h = placebo(Ph, cands)
    pl_d = placebo(Pd, cands)
    late = sub(full, full.dates >= LATE_START)
    desc = {"full_2013_2026": descriptive_all(full, "2013-02-28 .. 2026-10-20 (discovery + holdout)"),
            "late_2023_2026": descriptive_all(late, "2023-01-01 .. 2026-10-20 (inside the holdout)")}
    subp = subperiods(Ph, cands, econ)
    settle_chk = cfd_vs_settlement(Ph, tests["rows"]) if crosscheck else None
    null_chk = empirical_size_real_data(Pd, Ph, cands)
    prev = archive_previous(out_dir, HOLD_FILE, "holdout")
    res = {"what": "SPX close candle scan, step 2 (HOLDOUT 2021-01-01 .. 2026-10-20), run on the frozen "
                   "candidate list after its SHA-256 matched.",
           "summary_plain_english": None,
           "meta": {"prereg": str(prereg), "prereg_sha256": pr["sha256"], "prereg_params_checked": True,
                    "script": str(Path(__file__)), "scan_py_sha256": sha256_file(Path(__file__)),
                    "scan_py_sha256_at_freeze": frozen.get("scan_py_sha256_at_freeze"),
                    "scan_py_changed_since_freeze": sha256_file(Path(__file__)) != frozen.get("scan_py_sha256_at_freeze"),
                    "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "decisions_and_interpretations": DECISIONS, "runtime_s": None},
           "hash_gate": {"file": str(out_dir / CAND_FILE), "sha256": gate["sha256"], "matched": True,
                         "frozen_utc": frozen.get("frozen_utc")},
           "data": {"holdout": {"first": str(Ph.dates.min()), "last": str(Ph.dates.max()), "n_days": int(len(Ph.dates))},
                    "discovery": {"first": str(Pd.dates.min()), "last": str(Pd.dates.max()), "n_days": int(len(Pd.dates))},
                    "last_d1_level_1549_open": last_level, "last_d1_date": str(full.dates[-1])},
           "lookahead_selfcheck": look,
           "discovery_reproduced_with_current_code": repro,
           "frozen_candidates": cands,
           "holdout_test": {"rule": "one-sided NW test of mean(direction x signal x target) > 0; Holm across "
                                    "candidates at 5%; a candle 'predicts' only if it passes",
                            **tests},
           "p3_reference_holdout": {"note": "reference only, not tested, not in Holm", **p3h},
           "economics": {"rule": "see decisions 'economics'", "candidates": econ,
                         "size_neutral_reference_by_entry": generic},
           "straddle_cost_crosscheck": xc,
           "placebo_1149_1151": {"note": "descriptive; each candidate rebuilt 240 minutes earlier with its "
                                         "frozen direction, target to the 11:59 close (session-anchored F4 "
                                         "features keep their anchors, see decision 'placebo')",
                                 "holdout": pl_h, "discovery": pl_d},
           "descriptive_hit_rates_NOT_TESTS": desc,
           "known_effects": known,
           "holdout_subperiods_NOT_TESTS": subp,
           "cfd_vs_settlement_target": settle_chk,
           "real_data_null_check": null_chk,
           "forward_test": {"status": "not run", "why": "pre-registered as descriptive (Robinhood minute data from "
                                                        "2026-10-21 on); only 1 day exists and its settlement is "
                                                        "still provisional"},
           "rerun_vs_previous_run": None}
    res["summary_plain_english"] = plain_summary(res)
    res["meta"]["runtime_s"] = round(time.time() - t0, 2)
    clean_res = _clean(res)
    if prev is not None:
        cmp_ = compare_holdout_runs(prev["content"], clean_res)
        res["rerun_vs_previous_run"] = {
            "previous_file_archived_to": prev["archived_to"], "previous_sha256": prev["sha256"],
            "previous_generated_utc": prev["generated_utc"], "previous_scan_py_sha256": prev["scan_py_sha256"],
            "this_scan_py_sha256": res["meta"]["scan_py_sha256"], **cmp_}
    hist = []
    for fp in sorted((out_dir / RUNS_DIR).glob("holdout_*.json")) if (out_dir / RUNS_DIR).exists() else []:
        oj = json.loads(fp.read_text())
        cm = compare_holdout_runs(oj, clean_res)
        hist.append({"archived_file": str(fp), "sha256": sha256_file(fp),
                     "generated_utc": _g(oj, "meta", "generated_utc"), "scan_py_sha256": _g(oj, "meta", "scan_py_sha256"),
                     "n_compared": cm["n_compared"], "n_changed": cm["n_changed"], "changed_keys": cm["changed_keys"]})
    res["rerun_vs_archived_runs"] = {
        "what": "old -> new for the headline numbers (tests, Holm, hit rates, break-evens, accuracy flags, option "
                "P&L, placebo, P3, straddle ratio, hash) against every earlier holdout output kept in runs/; the "
                "full old/new rows are in rerun_vs_previous_run for the immediately previous run",
        "this_scan_py_sha256": res["meta"]["scan_py_sha256"], "runs": hist}
    write_json(out_dir / HOLD_FILE, res)
    return res


def _pct(x, nd=1):
    return "n/a" if x is None else f"{100 * x:.{nd}f}%"


def _num(x, fmt=".2f"):
    return "n/a" if x is None or (isinstance(x, float) and not math.isfinite(x)) else format(x, fmt)


def plain_summary(res: dict) -> list:
    """Plain-English lines built only from numbers already in `res` (rewritten after the audits)."""
    t = res["holdout_test"]
    ec = res["economics"]["candidates"]
    lines = []
    if t["n_candidates"] == 0:
        lines.append("No feature reached |t| >= 2.5 in 2013-2020, so there was nothing to test in 2021-2026: "
                     "no candle predicts the close move under this pre-registration.")
        return lines
    passed = [r for r in t["rows"] if r["passes_holm_5pct"]]
    failed = [r for r in t["rows"] if not r["passes_holm_5pct"]]
    n_feat = len(feature_specs())
    n_not_cand = n_feat - t["n_candidates"]
    known = (res.get("known_effects") or {}).get("candidates", {})
    disc = {c["feature"]: c for c in res["frozen_candidates"]}
    sp = (res.get("holdout_subperiods_NOT_TESTS") or {}).get("candidates", {})
    plac = {r["feature"]: r for r in res["placebo_1149_1151"]["holdout"]}
    acc = [r for r in passed if ec[r["feature"]]["verdict_vs_breakeven"]["fee_0.09"]["accurate_ci_lower_above_breakeven"]]
    lines.append(f"Question: does any candle near the close predict the SPX move into the close? {n_feat} candle "
                 f"features were scored on 2013-2020 only; {t['n_candidates']} reached |t| >= 2.5 and were frozen "
                 f"(with their direction, hashed) before any 2021-2026 bar was read. In 2021-2026, {len(passed)} of "
                 f"them pass the pre-registered test (one-sided, Holm 5%), i.e. 'predict' the direction better than "
                 f"chance, and {len(acc)} of those is 'accurate' (hit-rate CI lower bound above the option "
                 "break-even).")
    for r in t["rows"]:
        f = r["feature"]
        e = ec[f]
        v = e["verdict_vs_breakeven"]["fee_0.09"]
        ci = r["hit_rate_wilson95"] or [None, None]
        kn = known.get(f, {})
        tag = ("the known P3 effect" if kn.get("overlaps_known_P3") else
               "the known P1 effect" if kn.get("overlaps_known_P1") else None)
        txt = (f"{f}: 2013-2020 right {_pct(disc.get(f, {}).get('discovery_hit_rate'))}; 2021-2026 right "
               f"{_pct(r['hit_rate'])} (95% CI {_pct(ci[0])}-{_pct(ci[1])}) on {r['n_hit_days']} trades with a "
               f"non-zero move ({r['n_trades']} trades in all), mean {_num(r['mean_bps'])} bps/day, Holm p "
               f"{_num(r['p_holm'], '.3g')} -> {'PASSES' if r['passes_holm_5pct'] else 'fails'}. Option break-even "
               f"{_pct(v['breakeven_hit_rate'])} (size-neutral {_pct(v.get('breakeven_hit_rate_size_neutral'))}); "
               f"with {r['n_hit_days']} trades 'accurate' needs a hit rate of at least "
               f"{_pct(v.get('min_hit_rate_accurate_at_holdout_n'))} (size-neutral "
               f"{_pct(v.get('min_hit_rate_accurate_size_neutral_at_holdout_n'))}): "
               f"{'accurate' if v['accurate_ci_lower_above_breakeven'] else 'NOT accurate enough to pay for the option'}.")
        if tag:
            txt += (f" It is {tag} in another form, so its holdout "
                    + ("pass is nominal, not a blind confirmation." if r["passes_holm_5pct"] else
                       "result is not a blind test either (the known effect had already failed on 2013-2026)."
                       if kn.get("overlaps_known_P1") else "result is not a blind test."))
        lines.append(txt)
    for r in acc:
        f = r["feature"]
        e = ec[f]
        v = e["verdict_vs_breakeven"]["fee_0.09"]
        ot = v.get("option_pnl_test") or {}
        rat = e["holdout_points"].get("ratio_abs_move_correct_to_all")
        txt = (f"{f} economics (pre-registered model: buy the ATM 0DTE option at the entry, cost = half the "
               f"realized-move-fair straddle + $0.10 + $0.09): mean option P&L {_num(ot.get('mean_usd'), '+.1f')} $ "
               f"per trade, t {_num(ot.get('t_iid'))} (iid) / {_num(ot.get('t_nw5'))} (NW). The CI lower bound "
               f"{_pct(v['hit_rate_ci_lower'])} clears both the primary break-even {_pct(v['breakeven_hit_rate'])} and "
               f"the size-neutral {_pct(v.get('breakeven_hit_rate_size_neutral'))}; the primary one is below 50% only "
               f"because moves on right days were {_num(rat, '.3f')}x the average in 2021-2026. Fragile: the verdict "
               f"flips if the market charges more than {_num(v.get('markup_where_breakeven_equals_ci_lower'), '.3f')}x "
               f"the realized-fair straddle, and the mean P&L is 0 at {_num(v.get('markup_where_mean_pnl_is_zero'), '.3f')}x.")
        xc = res.get("straddle_cost_crosscheck")
        if xc:
            t10 = xc["robinhood_10m_days"]
            b = t10.get("ratio_market_to_own_payoff_same_days_boot95") or [None, None]
            txt += (f" Measured on {t10['n_days']} Robinhood days: straddle / its own payoff = "
                    f"{_num(t10.get('ratio_market_to_own_payoff_same_days'))} (95% CI {_num(b[0])}-{_num(b[1])}), "
                    "too few days to tell which side of the tipping point the market is on.")
        lines.append(txt)
        s = sp.get(f, {})
        a, b2 = s.get("2021_2022", {}), s.get("2023_2026", {})
        if a and b2:
            bci = b2.get("hit_rate_wilson95") or [None, None]
            cv = b2.get("ci_vs_full_holdout_breakevens_fee_0.09", {})
            lines.append(
                f"{f} over time (descriptive): 2021-2022 right {_pct(a.get('hit_rate'))} of {a.get('n_trades')} trades, "
                f"NW t {_num(a.get('nw_t'))}, option P&L {_num(a.get('option_pnl_usd_per_trade_fee_0.09'), '+.1f')} $/trade "
                f"(t {_num(a.get('option_pnl_t_iid'))}); 2023-2026 right {_pct(b2.get('hit_rate'))} of "
                f"{b2.get('n_trades')} (CI {_pct(bci[0])}-{_pct(bci[1])}: "
                f"{'includes' if cv.get('includes_50pct') else 'excludes'} 50%, "
                f"{'includes' if cv.get('includes_size_neutral_breakeven') else 'excludes'} the size-neutral break-even, "
                f"{'includes' if cv.get('includes_primary_breakeven') else 'just clears'} the primary one), option P&L "
                f"{_num(b2.get('option_pnl_usd_per_trade_fee_0.09'), '+.1f')} $/trade (t {_num(b2.get('option_pnl_t_iid'))}, "
                "not significant). Most of the holdout edge comes from 2021-2022.")
            yrs = e["years_needed_at_holdout_trade_rate"]
            nl = b2.get("trades_needed_at_this_period_effect_80pct_power", {})
            yl = b2.get("years_needed_at_full_holdout_trade_rate", {})
            vsn = v.get("trades_needed_hit_vs_size_neutral_breakeven_80pct_power")
            lines.append(
                f"{f}, trades needed to confirm going forward (5% one-sided, 80% power, about "
                f"{_num(e['holdout_trades_per_252_days'], '.0f')} trades a year): option P&L "
                f"{e['holdout_points']['fee_cases']['fee_0.09']['trades_needed_option_pnl_80pct_power']} trades "
                f"(~{_num(yrs['option_pnl_fee_0.09'], '.1f')} years) if the full 2021-2026 effect is the truth, "
                f"{nl.get('option_pnl')} (~{_num(yl.get('option_pnl'), '.1f')} years) at the 2023-2026 effect; hit rate "
                f"vs the size-neutral break-even {vsn} (~{_num(vsn / e['holdout_trades_per_252_days'] if vsn else None, '.1f')} "
                f"years); vs the primary break-even {v['trades_needed_hit_vs_breakeven_80pct_power']} "
                f"(~{_num(yrs['hit_vs_breakeven_fee_0.09'], '.1f')} years, assumes the bigger moves on right days persist).")
    for r in passed:
        if r in acc:
            continue
        v = ec[r["feature"]]["verdict_vs_breakeven"]["fee_0.09"]
        lines.append(f"{r['feature']} passes the holdout test but is not accurate: its CI lower bound "
                     f"{_pct(v['hit_rate_ci_lower'])} is below its break-even {_pct(v['breakeven_hit_rate'])}.")
    pl = [f"{r['feature']} t {_num(plac.get(r['feature'], {}).get('nw_t'))}" for r in t["rows"]]
    if pl:
        lines.append(f"Placebo (same candles at {plac.get(t['rows'][0]['feature'], {}).get('placebo_entry')} with the "
                     f"target to {plac.get(t['rows'][0]['feature'], {}).get('placebo_target_end')}, 2021-2026): "
                     f"{'; '.join(pl)}. Nothing there, as expected if the effect is specific to the close.")
    sc = res.get("cfd_vs_settlement_target") or {}
    e51 = (sc.get("by_entry") or {}).get("15:51", {})
    if e51.get("sign_agreement_d1_vs_spx_settle") is not None:
        mp = sc.get("hit_rate_mapped_to_settlement", {})
        mtxt = "; ".join(f"{k} {_pct(x['hit_rate_mapped'])} (CI lower {_pct(x['ci_lower_mapped'])})"
                         for k, x in mp.items() if k in {r['feature'] for r in acc})
        lines.append(f"Target caveat: the test uses the Dukascopy CFD to the 15:59 bar close; the option pays on the "
                     f"official SPX settlement. On {e51['n_days']} overlapping days their 15:51 -> close moves agree in "
                     f"sign on {_pct(e51['sign_agreement_d1_vs_spx_settle'], 0)} of days. If the disagreements are "
                     f"unrelated to the signal, the hit rate against the settlement would be about: {mtxt or 'n/a'}.")
    nc = res.get("real_data_null_check") or {}
    cs = nc.get("circular_shift_41_features_discovery") or {}
    if cs.get("n_shifts"):
        lines.append(f"Chance check on the real data: with the 41 signals shifted against the real 2013-2020 "
                     f"targets ({cs['n_shifts']} shifts), on average {_num(cs.get('mean_n_features_abs_t_ge_2.5'))} "
                     f"features reach |t| >= 2.5 by chance, {_pct(cs.get('share_shifts_ge_observed_n_candidates'))} of "
                     f"shifts give {cs.get('observed_n_candidates')} or more, and {_pct(cs.get('share_shifts_max_abs_t_ge_observed'))} "
                     f"give a best |t| of {_num(cs.get('observed_max_abs_t'))} or more.")
    if not passed:
        lines.append("Plain answer: no candle predicts the close move out of sample under this pre-registration.")
    elif not acc:
        lines.append("Plain answer: a candle predicts the direction slightly better than a coin flip out of sample, "
                     "but none is accurate enough to pay for buying the at-the-money 0DTE option.")
    else:
        known_acc = all(known.get(r["feature"], {}).get("overlaps_known_P3") or
                        known.get(r["feature"], {}).get("overlaps_known_P1") for r in acc)
        lines.append(
            f"Plain answer: {len(passed)} feature(s) pass the holdout test and {len(acc)} is 'accurate': "
            f"{', '.join(r['feature'] for r in acc)}"
            + (", which is the already-known P3 effect (the 15:50 one-minute candle), so this is a nominal pass, not a "
               "new or blind discovery" if known_acc else "")
            + ". It clears the accuracy bar only just: under the exact fair-straddle cost assumption, on the CFD series "
              "rather than the settlement, and mostly because of 2021-2022. Treat it as a lead to forward-test, not an "
              f"established edge. The other {n_feat - len(passed)} features are not shown to predict: {n_not_cand} never "
              f"reached the discovery bar and {len(failed)} candidate(s) failed the holdout. The pre-registered forward "
              "test (descriptive) has not been run: 1 day of data.")
    return lines


# ------------------------------------------------------------------------------------------------
# JSON
# ------------------------------------------------------------------------------------------------
def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return o


def write_json(path: Path, obj) -> None:
    Path(path).write_text(json.dumps(_clean(obj), indent=1) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["discover", "holdout"])
    ap.add_argument("--refreeze", action="store_true", help="discover: overwrite a differing frozen list "
                    "(refused once holdout.json exists)")
    a = ap.parse_args(argv)
    if a.step == "discover":
        r = run_discover(refreeze=a.refreeze)
        print(json.dumps({"candidates": r["candidates"], "freeze": r["freeze"], "runtime_s": r["meta"]["runtime_s"]}, indent=1))
    else:
        try:
            r = run_holdout()
        except HashGateError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print("\n".join(r["summary_plain_english"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
