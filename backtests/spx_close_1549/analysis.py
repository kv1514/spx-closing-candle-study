#!/usr/bin/env python
"""SPX 15:49 ET close-move study: the pre-registered analysis.

Implements /Users/kv15/trading/preregistration/spx_1549_close.md (read-only and binding) on
  D1 = data/spx_1549/d1_usa500_rth_1m.csv.gz   (Dukascopy USA500 1-minute bars, America/New_York)
  D2 = data/spx_1549/d2_chunk_*_{spx,options}_1m.csv + robinhood/raw/spx_daily_*.json (Robinhood)

Run:
    /Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/analysis.py
Writes backtests/spx_close_1549/results.json and backtests/spx_close_1549/RESULTS_RAW.md.

Conventions (from the pre-registration unless marked as an implementation choice):
  * Minute index m = minutes after 09:30 ET; bar m begins at 09:30 + m. 390 bars, 09:30 .. 15:59.
  * Info set at the open of bar k = opens of bars <= k and closes of bars < k (see `visible`).
  * r_close = ln(P_end / P_t0), t0 = open of the 15:49 bar; P_end = close of the 15:59 bar (D1)
    or the SPX official close (D2).
  * 11-minute window starting at bar s = ln(close of bar s+10 / open of bar s).
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:  # scipy is present in .venv (1.18); fall back to a normal approximation if it ever is not
    from scipy import stats as _sps
except Exception:  # noqa: BLE001
    _sps = None

# ------------------------------------------------------------------------------------------------
# constants (all fixed by the pre-registration or stated as implementation choices up front)
# ------------------------------------------------------------------------------------------------
ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
DATA = ROOT / "data" / "spx_1549"
PREREG = ROOT / "preregistration" / "spx_1549_close.md"
D1_FILE = DATA / "d1_usa500_rth_1m.csv.gz"
D1_DAYS = DATA / "d1_days.csv"
D1_VALIDATION = HERE / "d1_validation.json"
RH_RAW = DATA / "robinhood" / "raw"
OUT_JSON = HERE / "results.json"
OUT_MD = HERE / "RESULTS_RAW.md"

SEED = 20261021
EPS = 1e-5               # H1 log offset (return units)
NW_LAG = 5               # Newey-West lag for H2
N_BOOT = 10_000          # bootstrap replications
ALPHA = 0.05
STRIKE_STEP = 5.0        # SPXW strike grid near the money
MULT = 100               # SPX option multiplier ($ per index point)
HALF_SPREADS = (0.05, 0.10, 0.25)   # $ per leg, in option-price units
BASE_HALF_SPREAD = 0.10
# $ per contract per side: Robinhood 0.09 (base); + ~0.65 index exchange fee (pre-registered
# sensitivity); 1.13 = upper end of the actual Robinhood SPXW all-in fee found in
# research/SPX_1549_RESEARCH.md (extra, labelled sensitivity added after the audit round)
FEES = (0.09, 0.74, 1.13)
BASE_FEE = 0.09
EXTRA_FEES = (1.13,)     # not pre-registered: reported as a labelled extra sensitivity
BLOCK_LEN = 20           # moving-block bootstrap block (trading days) for every D1 resample
PLANNED_D2_DAYS = 35     # the pre-registration's "~35 days"
PARITY_FILTER_PTS = 0.5  # exploratory (iv) parity filter on the ATM strike (audit finding 8)
NYSE_1550_SWITCH = "2019-04-01"   # NYSE moved its imbalance publication 15:45 -> 15:50 (research file)
S3_OFFSET = 5.0
S3_MULTIPLE = 2.0
EXPL_OFFSETS = (5, 10, 15, 20, 25, 30)
EXPL_MULTIPLES = (2.0, 3.0, 5.0)
SUBPERIODS = {"start-2019": (None, "2019-12-31"),
              "2020-2022": ("2020-01-01", "2022-12-31"),
              "2023-2026": ("2023-01-01", None)}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
N_MIN = 390


def mi(hhmm: str) -> int:
    """Minute index of the bar that begins at hh:mm ET."""
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m - (9 * 60 + 30)


I0930, I1000, I1519, I1530 = mi("09:30"), mi("10:00"), mi("15:19"), mi("15:30")
I1538, I1548, I1549, I1550 = mi("15:38"), mi("15:48"), mi("15:49"), mi("15:50")
I1551, I1558, I1559 = mi("15:51"), mi("15:58"), mi("15:59")
COMP_STARTS = np.arange(mi("10:00"), mi("15:38") + 1)   # 339 comparison windows
WIN = 11                                                # bars per window

DECISIONS = [
    {"id": "D1-day-rule",
     "kind": "DEVIATION from the literal pre-registration wording",
     "text": "The pre-registration says 'days with any missing bar 15:19-15:59 are dropped'. Primary D1 "
             "day set = build_d1.py default `keep`, which treats a run of 1-4 no-update (flat, zero-volume) "
             "Dukascopy minutes as a valid carry-forward bar (runs >= 5 or starting 09:30 are missing). "
             "This is looser than the literal wording: the strict reading (`keep_strict`: any no-update "
             "minute in 15:19-15:59 counts as missing) drops 374 more days (mostly the sparse-feed years "
             "2013-14 and 2017). Kept as primary because it was fixed before any H1/H2 number was "
             "computed and switching after seeing both results would itself be a post-hoc choice; the "
             "strict reading is reported in full for H1/H2 and gives the same H1/H2 conclusions.",
     "source": "this analysis; relabelled from 'interpretation' to 'deviation' after audit finding 7"},
    {"id": "S2-best-predictor",
     "text": "S2 'best full-sample D1 t-stat' = the H2 predictor with the largest |Newey-West t| on the "
             "full D1 sample (as pre-registered); trade direction: buy the ATM call if sign(t) x P > 0, "
             "else (including P = 0) buy the ATM put, as the pre-registration's 'else ATM put' says. If the "
             "predictor is undefined (a bar it needs is missing) the day is excluded from the S2 mean, "
             "not booked as $0. Look-ahead check: the same selection repeated on D1 dates before the "
             "first D2 session is reported next to it.",
     "source": "workflow clarification (labelled); zero/undefined handling changed after audit finding 3"},
    {"id": "S2-P3-entry",
     "kind": "DEVIATION forced by the no-look-ahead rule",
     "text": "If P3 is the selected predictor its value is only known at the 15:51 open, so S2 enters at "
             "the 15:51 bar open (strike nearest SPX then) instead of the pre-registered t0 = 15:49 "
             "('same entry/exit'). The other reading of the rule (best |t| among the predictors known at "
             "t0, i.e. P1/P2/P4, entering at 15:49) is reported next to it as 'S2-alt' with its own pass "
             "rule evaluation.",
     "source": "this analysis; S2-alt added after audit finding 3"},
    {"id": "lookahead-cutoff",
     "text": "The implied-vs-realized model is fitted on D1 days from 2023-01-01 up to the day before the "
             "first D2 session collected, so no D2 test day (or any day in the D2 window) is inside the "
             "fit that predicts it. Its out-of-sample calibration on D1 days inside the D2 window is "
             "reported.",
     "source": "this analysis; added after audit finding 5 (before: fit ran through 2026-10-20)"},
    {"id": "evaluability",
     "text": "Pass-rule conditions are three-valued: yes / no / not evaluable. Condition 1 for S1/S3 needs "
             "a bootstrap CI over D2 days, so it is not evaluable with fewer than 2 usable D2 days. "
             "Condition 2 requires CIs to be reported, so it is not evaluable with fewer than 2 usable D2 "
             "days. A strategy is a candidate only if both are 'yes'; anything else is FAIL, and a FAIL "
             "caused by 'not evaluable' is labelled 'D2 test not run'.",
     "source": "this analysis; added after audit findings 1 and 2"},
    {"id": "settlement-gap",
     "text": "The realized-move model is fitted to the D1 move to the 15:59 bar close (16:00:00), while "
             "the straddle settles on the SPX official close. In D2 the 15:59-close -> official-close gap "
             "averages about 1.3 bps in absolute value (exploratory (iii)), so the model slightly "
             "understates the move the option actually pays on; this works against the S1/S3 premise.",
     "source": "this analysis; added after audit finding 9"},
    {"id": "option-marks",
     "text": "Robinhood option bar opens look like sampled prints/marks, not clean bid-ask mids (bar open "
             "is not the previous close; put-call parity is off by up to ~1.6 points at 15:49-15:50 on "
             "the one real day). If they are trade prints, adding a $0.10 half-spread may double-count "
             "part of the cost; if they are mids it is the right charge. Parity per usable day is "
             "reported as a data-quality line.",
     "source": "this analysis; added after audit finding 4"},
    {"id": "windows",
     "text": "11-minute window starting at bar s = open of bar s to close of bar s+10 (same length as "
             "r_close: 15:49:00-16:00:00). The 15:38 window is open 15:38 -> close 15:48. Same-day "
             "median uses every available window starting 10:00..15:38 (339 when no bar is missing).",
     "source": "this analysis (reading of 'every 11-minute window')"},
    {"id": "strike",
     "text": "Strike nearest SPX = nearest point on the 5-point grid, ties rounded up; the contract must "
             "have a real (non-interpolated) 1-minute bar at entry or the day is not usable.",
     "source": "this analysis"},
    {"id": "fees",
     "text": "Fees are charged per executed trade: entry always; exit only when a leg is sold before "
             "expiry (cash settlement is not a trade). Half-spread is added to the entry mark and "
             "subtracted from a sale price; settlement value is intrinsic at the SPX official close.",
     "source": "this analysis (reading of '$0.09/contract per side')"},
    {"id": "S3-trigger",
     "text": "S3 / exploratory (i): a leg is sold at multiple x entry mark minus half-spread (floored at "
             "0) if the close of any real bar beginning 15:49..15:58 is >= multiple x entry mark (the "
             "15:49 bar's close at 15:49:59 is later than the 15:49:00 entry).",
     "source": "this analysis (reading of 'any later bar's close ... before 15:59')"},
    {"id": "implied-vs-realized",
     "text": "Realized vol to t0 = sqrt(sum of squared 1-minute log changes of bar opens 09:30..15:49, "
             "rescaled for missing pairs), from D1 on the D2 date. Model fitted on D1 2023-01-01 .. the "
             "day before the first D2 session: |P_end/P_t0 - 1| = a + b*rv (OLS). Predicted move (points) = prediction x SPX "
             "at t0; compared with the D2 15:49 ATM straddle mark (C+P open). Pass-rule statistic = mean "
             "over usable D2 days of (predicted - implied); 95% CI from a day bootstrap that resamples "
             "D1 days (refitting, 20-day moving blocks) and D2 days (iid). The ratio model (sum|r|/sum "
             "rv) and the unconditional mean are reported as descriptive alternatives.",
     "source": "this analysis (pre-registration says 'ratio and regression'; workflow asked for the "
               "regression)"},
    {"id": "bootstrap",
     "text": f"Day-block bootstrap for every D1 resample = circular moving-block bootstrap with blocks of "
             f"{BLOCK_LEN} consecutive trading days (keeps volatility clustering), {N_BOOT} replications, "
             f"percentile 95% CI, seed {SEED}; the 1-day-block (iid) version is reported as a "
             "sensitivity. Samples of D2 trades (<= ~35 days) are resampled iid, since a 20-day block "
             "on 22 days would leave almost nothing to resample. For the implied-vs-realized premise the "
             "CI must lie above zero under BOTH the 20-day-block and the iid D1 resample (conservative: "
             "for the regression the block CI is narrower than the iid one, because the regression score "
             "has lag-1 autocorrelation of about -0.76, driven by back-to-back extreme-volatility days).",
     "source": "this analysis; block length changed 1 -> 20 after audit finding 6"},
    {"id": "fees-actual",
     "text": "An extra fee case of $1.13 per contract per side (upper end of Robinhood's actual SPXW fee: "
             "contract fee + exchange fee + regulatory, research/SPX_1549_RESEARCH.md section F) is added "
             "to the cost grid as a labelled, not pre-registered sensitivity.",
     "source": "this analysis; added after the literature review"},
    {"id": "nw",
     "text": "Newey-West: Bartlett weights, lag 5, p-value from the normal distribution; days where the "
             "predictor or target is undefined are dropped from that predictor's series.",
     "source": "this analysis"},
]


# ------------------------------------------------------------------------------------------------
# small statistics (implemented by hand; no statsmodels in .venv)
# ------------------------------------------------------------------------------------------------
def _norm_two_sided_p(t: float) -> float:
    return float(math.erfc(abs(t) / math.sqrt(2.0)))


def _t_two_sided_p(t: float, df: int) -> float:
    if _sps is not None:
        return float(2.0 * _sps.t.sf(abs(t), df))
    return _norm_two_sided_p(t)


def nw_mean_test(y, lag: int = NW_LAG) -> dict:
    """Mean of y with a Newey-West (Bartlett) standard error. NaNs are dropped first."""
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    n = int(len(y))
    if n < lag + 3:
        return {"n": n, "mean": float(np.mean(y)) if n else None, "se": None, "t": None, "p": None}
    mu = float(y.mean())
    e = y - mu
    lrv = float(e @ e) / n
    for lag_i in range(1, lag + 1):
        lrv += 2.0 * (1.0 - lag_i / (lag + 1.0)) * float(e[lag_i:] @ e[:-lag_i]) / n
    se = math.sqrt(max(lrv, 0.0) / n)
    t = mu / se if se > 0 else float("nan")
    return {"n": n, "mean": mu, "se": se, "t": t, "p": _norm_two_sided_p(t) if se > 0 else None}


def holm(pvals) -> list:
    """Holm step-down adjusted p-values (same order as the input)."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(np.argsort(p, kind="stable")):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj.tolist()


def ttest_mean_zero(x) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return {"n": n, "mean": float(x.mean()) if n else None, "t": None, "p": None}
    sd = float(x.std(ddof=1))
    t = float(x.mean()) / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    return {"n": n, "mean": float(x.mean()), "sd": sd, "t": t, "p": _t_two_sided_p(t, n - 1)}


def block_indices(n: int, block: int, rng, size: int) -> np.ndarray:
    """`size` bootstrap index vectors of length n. block = 1: iid days. block > 1: circular moving-block
    bootstrap (blocks of `block` consecutive days, start drawn uniformly, wrapped at the end)."""
    if block <= 1:
        return rng.integers(0, n, size=(size, n))
    nb = -(-n // block)
    starts = rng.integers(0, n, size=(size, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(size, nb * block)[:, :n]


def boot_mean_ci(x, rng, n_boot: int = N_BOOT, level: float = 0.95, block: int = 1):
    """Day-block bootstrap percentile CI of the mean. x must be in time order when block > 1."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return None
    block = min(block, n)
    means = np.empty(n_boot)
    step = max(1, 2_000_000 // n)
    for lo in range(0, n_boot, step):
        hi = min(n_boot, lo + step)
        means[lo:hi] = x[block_indices(n, block, rng, hi - lo)].mean(axis=1)
    a = (1.0 - level) / 2.0
    return [float(np.quantile(means, a)), float(np.quantile(means, 1.0 - a))]


def t_ci(x, level: float = 0.95):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return None
    q = _sps.t.ppf(0.5 + level / 2.0, n - 1) if _sps is not None else 1.959964
    h = q * x.std(ddof=1) / math.sqrt(n)
    return [float(x.mean() - h), float(x.mean() + h)]


def ols(x, y):
    """y = a + b x; returns (a, b)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    xm, ym = x.mean(), y.mean()
    b = float(((x - xm) * (y - ym)).sum() / ((x - xm) ** 2).sum())
    return float(ym - b * xm), b


# ------------------------------------------------------------------------------------------------
# information sets, predictors and targets (pure functions of open/close matrices, days x 390)
# ------------------------------------------------------------------------------------------------
def lr(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(np.asarray(b, dtype=float) / np.asarray(a, dtype=float))


def visible(O, C, k: int):
    """Information available at the open of bar k: opens of bars <= k, closes of bars < k."""
    O2 = np.array(O, dtype=float, copy=True)
    C2 = np.array(C, dtype=float, copy=True)
    O2[..., k + 1:] = np.nan
    C2[..., k:] = np.nan
    return O2, C2


def _p1(O, C):
    return np.sign(lr(O[..., I0930], O[..., I1549]))


def _p2(O, C):
    return np.sign(lr(O[..., I1519], O[..., I1549]))


def _p3(O, C):
    return np.sign(lr(O[..., I1550], O[..., I1551]))


def _p4(O, C):
    return np.sign(lr(O[..., I0930], O[..., I1000]))


PREDICTORS = {
    "P1": {"desc": "sign r(09:30 open -> 15:49 open)  intraday momentum", "fn": _p1,
           "entry": I1549, "target": "r_close"},
    "P2": {"desc": "sign r(15:19 open -> 15:49 open)  last-30-minute momentum", "fn": _p2,
           "entry": I1549, "target": "r_close"},
    "P3": {"desc": "sign r(15:50 open -> 15:51 open)  first reaction to the 15:50 imbalance",
           "fn": _p3, "entry": I1551, "target": "r_1551"},
    "P4": {"desc": "sign r(09:30 open -> 10:00 open)  first half-hour", "fn": _p4,
           "entry": I1549, "target": "r_close"},
}
# target name -> (start bar whose OPEN starts the return, end bar whose CLOSE ends it)
TARGETS = {"r_close": (I1549, I1559), "r_1551": (I1551, I1559)}


def target_values(O, C, name: str):
    s, e = TARGETS[name]
    return lr(O[..., s], C[..., e])


def realized_vol_to_t0(O):
    """sqrt(sum of squared 1-minute log changes of bar opens 09:30..15:49), rescaled for missing pairs.
    Uses only opens of bars <= 15:49, i.e. information at t0."""
    O = np.atleast_2d(np.asarray(O, dtype=float))
    r = lr(O[:, I0930:I1549], O[:, I0930 + 1:I1549 + 1])
    ok = np.isfinite(r)
    n_ok = ok.sum(axis=1)
    ss = np.where(ok, r, 0.0) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        rv = np.sqrt(ss.sum(axis=1) * (I1549 - I0930) / n_ok)
    rv[n_ok < 0.8 * (I1549 - I0930)] = np.nan
    return rv


def lookahead_selfcheck(O, C, rng) -> list:
    """Assertion-based proof that every predictor (and rv) uses only data at or before its entry:
    (1) value on the masked info set equals the value on full data; (2) scrambling everything after
    the info cutoff leaves it unchanged; (3) each target starts at or after the predictor's entry."""
    log = []
    for name, spec in PREDICTORS.items():
        k = spec["entry"]
        full = spec["fn"](O, C)
        Ov, Cv = visible(O, C, k)
        vis = spec["fn"](Ov, Cv)
        assert np.array_equal(full, vis, equal_nan=True), f"{name}: uses data after its entry bar"
        Os, Cs = np.array(O, copy=True), np.array(C, copy=True)
        Os[..., k + 1:] *= np.exp(rng.normal(0, 0.01, Os[..., k + 1:].shape))
        Cs[..., k:] *= np.exp(rng.normal(0, 0.01, Cs[..., k:].shape))
        assert np.array_equal(full, spec["fn"](Os, Cs), equal_nan=True), f"{name}: changes with future"
        assert TARGETS[spec["target"]][0] >= k, f"{name}: target starts before entry"
        log.append(f"{name}: entry bar {k} ({spec['target']} starts bar {TARGETS[spec['target']][0]}); "
                   "masked == full, scrambled-future == full")
    rv = realized_vol_to_t0(O)
    Ov, _ = visible(O, C, I1549)
    assert np.array_equal(rv, realized_vol_to_t0(Ov), equal_nan=True), "rv uses data after t0"
    log.append("rv(09:30..15:49 opens): masked at t0 == full")
    return log


# ------------------------------------------------------------------------------------------------
# H1 and H2 (pure functions on matrices)
# ------------------------------------------------------------------------------------------------
def comparison_window_abs(O, C):
    W = np.stack([lr(O[:, s], C[:, s + WIN - 1]) for s in COMP_STARTS], axis=1)
    return np.abs(W)


def h1_test(O, C, rng) -> dict:
    rc = target_values(O, C, "r_close")
    r38 = lr(O[:, I1538], C[:, I1538 + WIN - 1])
    Wabs = comparison_window_abs(O, C)
    n_win = np.isfinite(Wabs).sum(axis=1)
    med = np.full(len(rc), np.nan)
    has = n_win > 0
    med[has] = np.nanmedian(Wabs[has], axis=1)
    out = {"n_days_input": int(len(rc)),
           "n_days_full_339_windows": int((n_win == len(COMP_STARTS)).sum()),
           "min_windows_on_a_day": int(n_win.min()) if len(n_win) else 0}
    for key, base in (("a_vs_1538_1549_window", np.abs(r38)), ("b_vs_same_day_median_window", med)):
        x = np.log(np.abs(rc) + EPS) - np.log(base + EPS)
        ok = np.isfinite(x)
        tt = ttest_mean_zero(x[ok])
        ci = boot_mean_ci(x[ok], rng, block=BLOCK_LEN)
        ci_iid = boot_mean_ci(x[ok], rng, block=1)
        diff_bps = (np.abs(rc) - base)[ok] * 1e4
        out[key] = {
            "n_days": int(ok.sum()),
            "n_dropped_undefined": int((~ok).sum()),
            "mean_abs_r_close_bps": float(np.abs(rc[ok]).mean() * 1e4),
            "mean_baseline_bps": float(base[ok].mean() * 1e4),
            "ratio_of_means": float(np.abs(rc[ok]).mean() / base[ok].mean()),
            "mean_log_diff": tt["mean"], "geometric_ratio": float(math.exp(tt["mean"])),
            "t": tt["t"], "p_two_sided": tt["p"], "boot95_mean_log_diff": ci,
            "boot95_mean_log_diff_block": BLOCK_LEN, "boot95_mean_log_diff_iid_sensitivity": ci_iid,
            "mean_diff_bps": float(diff_bps.mean()),
            "boot95_mean_diff_bps": boot_mean_ci(diff_bps, rng, block=BLOCK_LEN),
            "share_days_r_close_larger": float((np.abs(rc[ok]) > base[ok]).mean()),
            "passes": bool(tt["p"] is not None and tt["p"] < ALPHA and tt["mean"] > 0 and ci is not None and ci[0] > 0),
        }
    return out


def _signal_series(O, C, name):
    spec = PREDICTORS[name]
    s = spec["fn"](O, C)
    y = s * target_values(O, C, spec["target"]) * 1e4
    return s, y


def _summ(s, y) -> dict:
    ok = np.isfinite(y)
    nw = nw_mean_test(y[ok])
    nz = ok & (s != 0) & (y != 0)
    return {"n": int(ok.sum()), "mean_bps": nw["mean"], "nw_se_bps": nw["se"], "nw_t": nw["t"],
            "p": nw["p"], "hit_rate": float((y[nz] > 0).mean()) if nz.any() else None,
            "n_zero_sign": int((ok & (s == 0)).sum())}


def h2_test(O, C, dates, weekdays) -> dict:
    dates = np.asarray(dates)
    weekdays = np.asarray(weekdays)
    full, sub, wk = {}, {}, {}
    for name, spec in PREDICTORS.items():
        s, y = _signal_series(O, C, name)
        full[name] = _summ(s, y)
        full[name]["n_dropped_undefined"] = int((~np.isfinite(y)).sum())
        full[name]["desc"] = spec["desc"]
        full[name]["target"] = spec["target"]
        sub[name] = {}
        for pname, (a, b) in SUBPERIODS.items():
            m = np.ones(len(dates), bool)
            if a:
                m &= dates >= a
            if b:
                m &= dates <= b
            sub[name][pname] = _summ(s[m], y[m])
            sub[name][pname]["first"] = str(dates[m].min()) if m.any() else None
            sub[name][pname]["last"] = str(dates[m].max()) if m.any() else None
        wk[name] = {d: _summ(s[weekdays == d], y[weekdays == d]) for d in WEEKDAYS}
    names = list(PREDICTORS)
    adj = holm([full[n]["p"] for n in names])
    for n, a in zip(names, adj):
        full[n]["p_holm"] = a
        late = sub[n]["2023-2026"]["mean_bps"]
        full[n]["same_sign_2023_2026"] = bool(late is not None and np.sign(late) == np.sign(full[n]["mean_bps"]))
        full[n]["passes_direction"] = bool(a < ALPHA and full[n]["same_sign_2023_2026"])
    best = max(names, key=lambda n: abs(full[n]["nw_t"]))
    at_t0 = [n for n in names if PREDICTORS[n]["entry"] == I1549]
    best0 = max(at_t0, key=lambda n: abs(full[n]["nw_t"]))
    return {"full_sample": full, "subperiods": sub, "weekday": wk,
            "best_abs_t": {"predictor": best, "nw_t": full[best]["nw_t"],
                           "trade_sign_multiplier": int(np.sign(full[best]["nw_t"]))},
            "best_abs_t_known_at_t0": {"predictor": best0, "nw_t": full[best0]["nw_t"],
                                       "trade_sign_multiplier": int(np.sign(full[best0]["nw_t"])),
                                       "candidates": at_t0}}


# ------------------------------------------------------------------------------------------------
# option P&L arithmetic (pure)
# ------------------------------------------------------------------------------------------------
def nearest_strike(s: float, step: float = STRIKE_STEP) -> float:
    return float(math.floor(s / step + 0.5) * step)


def intrinsic(kind: str, strike: float, settle: float) -> float:
    return max(settle - strike, 0.0) if kind == "call" else max(strike - settle, 0.0)


def leg_pnl(entry_mark: float, exit_value: float, half_spread: float, fee: float, sold: bool) -> dict:
    """One long contract. entry price = mark + half-spread; exit_value is either a sale price (already
    net of half-spread) or the settlement intrinsic. Fees: one side, or two if sold before expiry."""
    pts = exit_value - (entry_mark + half_spread)
    return {"pnl_points": pts, "pnl_usd": MULT * pts - (2 if sold else 1) * fee}


def straddle_pnl(strike, call_mark, put_mark, settle, half_spread, fee) -> dict:
    c = leg_pnl(call_mark, intrinsic("call", strike, settle), half_spread, fee, False)
    p = leg_pnl(put_mark, intrinsic("put", strike, settle), half_spread, fee, False)
    return {"pnl_points": c["pnl_points"] + p["pnl_points"], "pnl_usd": c["pnl_usd"] + p["pnl_usd"]}


def target_exit_leg(kind, strike, entry_mark, later_closes, settle, half_spread, fee, multiple) -> dict:
    """Long one option; sell at multiple x entry mark (minus half-spread) at the first later bar close
    that reaches it, else hold to settlement."""
    target = multiple * entry_mark
    closes = np.asarray(later_closes, dtype=float)
    hit = np.flatnonzero(np.isfinite(closes) & (closes >= target - 1e-12))
    if hit.size:
        r = leg_pnl(entry_mark, max(target - half_spread, 0.0), half_spread, fee, True)
        r.update(sold=True, hit_bar_offset=int(hit[0]))
    else:
        r = leg_pnl(entry_mark, intrinsic(kind, strike, settle), half_spread, fee, False)
        r.update(sold=False, hit_bar_offset=None)
    return r


def s2_direction(best_t: float, p_value: float):
    """+1 buy the ATM call if sign(t) x P > 0, else -1 buy the ATM put (including P = 0, as the
    pre-registration's 'else ATM put' says). None = predictor undefined: no trade, and the day is
    excluded from the S2 mean (not booked as $0)."""
    if p_value is None or not np.isfinite(p_value) or not np.isfinite(best_t):
        return None
    return 1 if np.sign(best_t) * np.sign(p_value) > 0 else -1


# ------------------------------------------------------------------------------------------------
# loading
# ------------------------------------------------------------------------------------------------
def load_d1(rule: str = "keep"):
    days = pd.read_csv(D1_DAYS, dtype={"date": str})
    keep = days.loc[days[rule].astype(bool), ["date", "weekday"]].reset_index(drop=True)
    bars = pd.read_csv(D1_FILE, dtype={"date": str, "time_et": str})
    bars = bars[bars["date"].isin(set(keep["date"]))]
    dates = keep["date"].to_numpy()
    assert set(bars["date"].unique()) == set(dates), "D1 bar file and day table disagree"
    di = pd.Index(dates).get_indexer(bars["date"])
    ti = bars["time_et"].map(mi).to_numpy()
    assert (ti >= 0).all() and (ti < N_MIN).all()
    O = np.full((len(dates), N_MIN), np.nan)
    C = np.full((len(dates), N_MIN), np.nan)
    O[di, ti] = bars["open"].to_numpy(float)
    C[di, ti] = bars["close"].to_numpy(float)
    assert np.isfinite(O[:, I1519:I1559 + 1]).all() and np.isfinite(C[:, I1519:I1559 + 1]).all(), \
        "a kept D1 day is missing a bar in 15:19-15:59"
    return dates, keep["weekday"].to_numpy(), O, C, days


def load_daily_closes():
    """Official SPX closes from every saved Robinhood daily file; interpolated rows dropped; files must
    agree where they overlap."""
    closes, sources = {}, {}
    for f in sorted(glob.glob(str(RH_RAW / "spx_daily_*.json"))):
        j = json.loads(Path(f).read_text())
        for res in j["data"]["results"]:
            assert res["symbol"] == "SPX" and res["interval"] == "day"
            for b in res["bars"]:
                if b.get("interpolated"):
                    continue
                d = b["begins_at"][:10]
                c = float(b["close_value"])
                if d in closes:
                    assert abs(closes[d] - c) < 0.005, f"daily close mismatch {d}: {closes[d]} vs {c}"
                    sources[d].append(Path(f).name)
                else:
                    closes[d], sources[d] = c, [Path(f).name]
    return closes, sources


def _minute_arrays(frame: pd.DataFrame):
    O = np.full(N_MIN, np.nan)
    C = np.full(N_MIN, np.nan)
    t = frame["time_et"].map(mi).to_numpy(dtype=int) if len(frame) else np.zeros(0, int)
    m = (t >= 0) & (t < N_MIN)
    O[t[m]] = frame["open"].to_numpy(float)[m]
    C[t[m]] = frame["close"].to_numpy(float)[m]
    return O, C


def load_d2():
    spx_files = sorted(glob.glob(str(DATA / "d2_chunk_*_spx_1m.csv")))
    opt_files = sorted(glob.glob(str(DATA / "d2_chunk_*_options_1m.csv")))
    spx = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str}) for f in spx_files])
    opt = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str}) for f in opt_files])
    sessions = sorted(spx["date"].unique())
    info = {"spx_files": [Path(f).name for f in spx_files], "option_files": [Path(f).name for f in opt_files],
            "sessions_collected": len(sessions), "first": sessions[0], "last": sessions[-1],
            "spx_bars_total": int(len(spx)), "spx_bars_interpolated_discarded": int(spx["interpolated"].sum()),
            "option_bars_total": int(len(opt)),
            "option_bars_interpolated_discarded": int(opt["interpolated"].astype(bool).sum())}
    spx = spx[~spx["interpolated"].astype(bool)]
    opt = opt[~opt["interpolated"].astype(bool)]
    assert not spx.duplicated(["date", "time_et"]).any()
    assert not opt.duplicated(["date", "occ_symbol", "time_et"]).any()
    closes, close_src = load_daily_closes()
    days = {}
    for d in sessions:
        sO, sC = _minute_arrays(spx[spx["date"] == d])
        o_day = opt[opt["date"] == d]
        options = {}
        for (kind, k), g in o_day.groupby(["type", "strike"]):
            options[(kind, float(k))] = _minute_arrays(g)
        days[d] = {"spx_O": sO, "spx_C": sC, "settle": closes.get(d), "settle_src": close_src.get(d),
                   "options": options, "weekday": pd.Timestamp(d).strftime("%a")}
    return days, info


def load_d2_10m(full: bool = False):
    """10-minute option bars (left-labelled: the 15:40 bar covers 15:40:00-15:49:59). Returns the 15:40-bar
    closes as {(date, type, strike): close}; with full=True also the whole real-bar frame."""
    files = sorted(glob.glob(str(DATA / "d2_chunk_*_options_10m.csv")))
    t = pd.concat([pd.read_csv(f, dtype={"date": str, "time_et": str}) for f in files])
    t = t[~t["interpolated"].astype(bool)]
    t40 = t[t["time_et"] == "15:40"]
    marks = {(r.date, r.type, float(r.strike)): float(r.close) for r in t40.itertuples()}
    if full:
        return marks, [Path(f).name for f in files], t
    return marks, [Path(f).name for f in files]


# ------------------------------------------------------------------------------------------------
# D2 strategy evaluation
# ------------------------------------------------------------------------------------------------
def _opt_at(day, kind, strike, k, field="O"):
    arr = day["options"].get((kind, float(strike)))
    if arr is None:
        return float("nan")
    return float(arr[0][k] if field == "O" else arr[1][k])


def d2_day_status(day) -> dict:
    sO, sC = day["spx_O"], day["spx_C"]
    st = {"spx_complete_1519_1559": bool(np.isfinite(sO[I1519:I1559 + 1]).all() and np.isfinite(sC[I1519:I1559 + 1]).all()),
          "spx_real_bars": int(np.isfinite(sO).sum()), "settle": day["settle"]}
    if st["spx_complete_1519_1559"]:
        s0 = float(sO[I1549])
        k0 = nearest_strike(s0)
        st.update(S0=s0, K0=k0, call_mark=_opt_at(day, "call", k0, I1549), put_mark=_opt_at(day, "put", k0, I1549))
        st["options_real_at_t0"] = bool(np.isfinite(st["call_mark"]) and np.isfinite(st["put_mark"]))
        st["n_contracts_real_at_t0"] = int(sum(np.isfinite(a[0][I1549]) for a in day["options"].values()))
    else:
        st["options_real_at_t0"] = False
        st["n_contracts_real_at_t0"] = 0
    st["usable_h3"] = bool(st["spx_complete_1519_1559"] and st["settle"] is not None and st["options_real_at_t0"])
    return st


def d2_decisions(day, s2_specs: dict) -> dict:
    """Every entry decision for one D2 day, computed from the info set at its entry bar only.
    s2_specs: {variant: (predictor name, trade sign multiplier)}."""
    dec = {}
    O, C = day["spx_O"], day["spx_C"]
    vO, _ = visible(O, C, I1549)
    dec["K0"] = nearest_strike(float(vO[I1549]))
    for v, (pred, t_sign) in s2_specs.items():
        spec = PREDICTORS[pred]
        k = spec["entry"]
        pO, pC = visible(O, C, k)
        pval = float(spec["fn"](pO, pC))
        dec[f"{v}_predictor"] = pred
        dec[f"{v}_entry_bar"] = k
        dec[f"{v}_predictor_value"] = pval if np.isfinite(pval) else None
        dec[f"{v}_direction"] = s2_direction(t_sign, pval)
        dec[f"{v}_strike"] = nearest_strike(float(pO[k])) if np.isfinite(pO[k]) else None
    return dec


def parity_check(day, bars=(I1549, I1550, I1551), max_offset: float = 30.0) -> dict:
    """Pre-registered data-quality check: C - P - (S - K) on bar opens (real bars only), every strike
    within ATM +/- max_offset with both legs real at that bar. Signed median, max |dev|, ATM dev."""
    out = {}
    for k in bars:
        s = float(day["spx_O"][k])
        if not np.isfinite(s):
            continue
        katm = nearest_strike(s)
        devs = {}
        for (kind, strike), arr in day["options"].items():
            if kind != "call" or abs(strike - katm) > max_offset + 1e-9:
                continue
            put = day["options"].get(("put", strike))
            if put is None or not (np.isfinite(arr[0][k]) and np.isfinite(put[0][k])):
                continue
            devs[strike] = float(arr[0][k] - put[0][k] - (s - strike))
        t = (dt.datetime(2000, 1, 1, 9, 30) + dt.timedelta(minutes=k)).strftime("%H:%M")
        v = np.array(list(devs.values()))
        out[t] = {"spx_open": s, "K_atm": katm, "n_strikes": int(len(v)),
                  "signed_dev_median": float(np.median(v)) if len(v) else None,
                  "abs_dev_max": float(np.abs(v).max()) if len(v) else None,
                  "atm_dev": devs.get(katm),
                  "option_implied_spx_median": float(s + np.median(v)) if len(v) else None}
    return out


def evaluate_d2(days, s2_specs: dict, rng) -> dict:
    status = {d: d2_day_status(v) for d, v in days.items()}
    usable = [d for d, s in status.items() if s["usable_h3"]]
    per_day = {}
    selfcheck = []
    s2_names = list(s2_specs)
    for d in usable:
        day, st = days[d], status[d]
        dec = d2_decisions(day, s2_specs)
        # look-ahead self-check: the same decisions from data truncated at the latest entry bar
        trunc = dict(day)
        last_entry = max([I1549] + [dec[f"{v}_entry_bar"] for v in s2_names])
        tO, tC = visible(day["spx_O"], day["spx_C"], last_entry)
        trunc["spx_O"], trunc["spx_C"] = tO, tC
        assert d2_decisions(trunc, s2_specs) == dec, f"{d}: D2 decision uses future data"
        assert dec["K0"] == st["K0"]
        selfcheck.append(f"{d}: K0 and every S2 variant's strike/direction identical from data truncated at entry")
        settle = float(day["settle"])
        K0 = st["K0"]
        rec = {"S0": st["S0"], "K0": K0, "settle": settle, "call_mark": st["call_mark"], "put_mark": st["put_mark"],
               "straddle_mark": st["call_mark"] + st["put_mark"],
               "realized_abs_move_pts": abs(settle - st["S0"]),
               "spx_1559_close": float(day["spx_C"][I1559]), "decisions": dec,
               "parity_check": parity_check(day)}
        grid = {}
        for hs in HALF_SPREADS:
            for fee in FEES:
                key = f"hs{hs:.2f}_fee{fee:.2f}"
                g = {"S1": straddle_pnl(K0, st["call_mark"], st["put_mark"], settle, hs, fee)}
                # S2 variants: undefined predictor or missing mark -> None (excluded from the mean)
                for v in s2_names:
                    g[v] = None
                    if dec[f"{v}_direction"] is not None and dec[f"{v}_strike"] is not None:
                        kind = "call" if dec[f"{v}_direction"] > 0 else "put"
                        m2 = _opt_at(day, kind, dec[f"{v}_strike"], dec[f"{v}_entry_bar"])
                        if np.isfinite(m2):
                            g[v] = leg_pnl(m2, intrinsic(kind, dec[f"{v}_strike"], settle), hs, fee, False)
                            g[v].update(kind=kind, strike=dec[f"{v}_strike"], entry_mark=m2)
                # S3
                legs = {}
                for kind, kk in (("call", K0 + S3_OFFSET), ("put", K0 - S3_OFFSET)):
                    mk = _opt_at(day, kind, kk, I1549)
                    arr = day["options"].get((kind, float(kk)))
                    if arr is None or not np.isfinite(mk):
                        legs = None
                        break
                    legs[kind] = target_exit_leg(kind, kk, mk, arr[1][I1549:I1558 + 1], settle, hs, fee, S3_MULTIPLE)
                    legs[kind].update(strike=kk, entry_mark=mk)
                g["S3"] = None if legs is None else {
                    "pnl_points": legs["call"]["pnl_points"] + legs["put"]["pnl_points"],
                    "pnl_usd": legs["call"]["pnl_usd"] + legs["put"]["pnl_usd"], "legs": legs}
                grid[key] = g
        rec["pnl"] = grid
        per_day[d] = rec
    summary = {}
    for strat in ["S1"] + s2_names + ["S3"]:
        summary[strat] = {}
        for key in next(iter(per_day.values()))["pnl"] if per_day else []:
            v = np.array([per_day[d]["pnl"][key][strat]["pnl_usd"] for d in per_day
                          if per_day[d]["pnl"][key][strat] is not None])
            summary[strat][key] = {"n_days": int(len(v)), "mean_usd": float(v.mean()) if len(v) else None,
                                   "t_ci95_usd": t_ci(v), "boot95_usd": boot_mean_ci(v, rng)}
    return {"status": status, "usable_days": usable, "per_day": per_day, "summary": summary,
            "lookahead_selfcheck": selfcheck}


# ------------------------------------------------------------------------------------------------
# implied vs realized
# ------------------------------------------------------------------------------------------------
def implied_vs_realized(d1_dates, O, C, d2_items, rng, n_boot: int = N_BOOT, fit_end: str | None = None,
                        block: int = BLOCK_LEN) -> dict:
    """d2_items: list of dicts with date, S0, implied (straddle mark, points).
    The model is fitted on D1 days 2023-01-01 <= date < fit_end (no D2-window day inside the fit).
    CI: D1 days resampled in moving blocks of `block` days (refit each draw), D2 days resampled iid.
    With fewer than 2 D2 days the D2 side cannot be resampled, so the pass-rule statistic is
    'not evaluable' (point values are still reported, descriptively)."""
    sel = d1_dates >= "2023-01-01"
    if fit_end is not None:
        sel &= d1_dates < fit_end
    absr = np.abs(np.exp(target_values(O[sel], C[sel], "r_close")) - 1.0)
    rv = realized_vol_to_t0(O[sel])
    ok = np.isfinite(absr) & np.isfinite(rv)
    absr, rv = absr[ok], rv[ok]
    a, b = ols(rv, absr)
    k_ratio = float(absr.sum() / rv.sum())
    rv_all = realized_vol_to_t0(O)
    date_ix = {d: i for i, d in enumerate(d1_dates)}
    items = []
    for it in d2_items:
        i = date_ix.get(it["date"])
        rvd = float(rv_all[i]) if i is not None else float("nan")
        items.append(dict(it, rv_d1=rvd,
                          pred_regression_pts=(a + b * rvd) * it["S0"],
                          pred_ratio_pts=k_ratio * rvd * it["S0"],
                          pred_unconditional_pts=float(absr.mean()) * it["S0"]))
    for it in items:
        for m in ("regression", "ratio", "unconditional"):
            it[f"diff_{m}_pts"] = it[f"pred_{m}_pts"] - it["implied_pts"]
            it[f"ratio_{m}"] = it[f"pred_{m}_pts"] / it["implied_pts"]
    valid = [it for it in items if np.isfinite(it["rv_d1"])]
    fit_dates = d1_dates[sel][ok]
    out = {"fit_sample": {"first": str(fit_dates.min()), "last": str(fit_dates.max()), "n_days": int(ok.sum()),
                          "fit_end_exclusive": fit_end},
           "regression": {"a": a, "b": b, "r2": float(1 - ((absr - (a + b * rv)) ** 2).sum() / ((absr - absr.mean()) ** 2).sum())},
           "ratio_k": k_ratio, "mean_abs_move_frac_2023_2026": float(absr.mean()),
           "mean_rv_frac_2023_2026": float(rv.mean()), "days": items, "n_d2_days": len(valid),
           "bootstrap": {"d1_block_days": block, "d2": "iid days", "n_boot": n_boot}}
    # out-of-sample calibration: D1 days on/after fit_end (the D2 window), model vs realized D1 move
    if fit_end is not None:
        post = d1_dates >= fit_end
        ar = np.abs(np.exp(target_values(O[post], C[post], "r_close")) - 1.0)
        rvp = realized_vol_to_t0(O[post])
        okp = np.isfinite(ar) & np.isfinite(rvp)
        if okp.any():
            out["calibration_out_of_sample"] = {
                "first": str(d1_dates[post][okp].min()), "last": str(d1_dates[post][okp].max()), "n_days": int(okp.sum()),
                "mean_pred_regression_bps": float((a + b * rvp[okp]).mean() * 1e4),
                "mean_realized_abs_r_close_bps": float(ar[okp].mean() * 1e4),
                "mean_rv_bps": float(rvp[okp].mean() * 1e4),
                "note": "D1 move to the 15:59 bar close; model fitted only on days before this window"}
    if not valid:
        out["stat"] = None
        out["size_premise_passes"] = None
        out["evaluable"] = False
        return out
    S0 = np.array([it["S0"] for it in valid])
    imp = np.array([it["implied_pts"] for it in valid])
    rvd = np.array([it["rv_d1"] for it in valid])
    n1, n2 = len(absr), len(valid)
    point = {m: float(np.mean([it[f"diff_{m}_pts"] for it in valid])) for m in ("regression", "ratio", "unconditional")}
    ratio = {m: float(np.mean([it[f"ratio_{m}"] for it in valid])) for m in ("regression", "ratio", "unconditional")}
    if n2 < 2:
        out["stat"] = None
        out["descriptive_single_day"] = {m: {"pred_minus_implied_pts": point[m], "pred_over_implied": ratio[m]}
                                         for m in point}
        out["size_premise_passes"] = None
        out["evaluable"] = False
        out["not_evaluable_reason"] = (f"{n2} usable D2 day: the D2 side of the bootstrap cannot be resampled, so a "
                                       "CI over D2 days does not exist (a CI from the D1 refit alone would only "
                                       "measure model uncertainty around one fixed implied value)")
        return out
    stats_ = {}
    boots = {f"{m}{s}": np.empty(n_boot) for m in ("regression", "ratio", "unconditional") for s in ("", "_iid")}
    for i in range(n_boot):
        jj = rng.integers(0, n2, n2)
        for suffix, blk in (("", block), ("_iid", 1)):
            j = block_indices(n1, blk, rng, 1)[0]
            x, y = rv[j], absr[j]
            aa, bb = ols(x, y)
            kk = y.sum() / x.sum()
            boots[f"regression{suffix}"][i] = np.mean((aa + bb * rvd[jj]) * S0[jj] - imp[jj])
            boots[f"ratio{suffix}"][i] = np.mean(kk * rvd[jj] * S0[jj] - imp[jj])
            boots[f"unconditional{suffix}"][i] = np.mean(y.mean() * S0[jj] - imp[jj])
    for m in ("regression", "ratio", "unconditional"):
        ci = [float(np.quantile(boots[m], 0.025)), float(np.quantile(boots[m], 0.975))]
        ci_iid = [float(np.quantile(boots[m + "_iid"], 0.025)), float(np.quantile(boots[m + "_iid"], 0.975))]
        # conservative: the premise passes only if BOTH the 20-day-block and the iid-D1 CI lie above zero
        stats_[m] = {"mean_pred_minus_implied_pts": point[m], "mean_ratio_pred_over_implied": ratio[m],
                     "boot95_pts": ci, "boot95_pts_iid_d1_sensitivity": ci_iid,
                     "ci_block_above_zero": bool(ci[0] > 0), "ci_iid_above_zero": bool(ci_iid[0] > 0),
                     "ci_excludes_zero_positive": bool(ci[0] > 0 and ci_iid[0] > 0)}
    out["stat"] = stats_
    out["evaluable"] = True
    out["pass_rule_model"] = "regression"
    out["size_premise_passes"] = stats_["regression"]["ci_excludes_zero_positive"]
    return out


# ------------------------------------------------------------------------------------------------
# exploratory
# ------------------------------------------------------------------------------------------------
def exploratory_otm(days, usable) -> dict:
    """(i) OTM options at 15:49: share reaching 2x/3x/5x at a bar close 15:49..15:58; P&L of
    'sell at 2x else hold to settlement' at base costs."""
    rows = []
    for d in usable:
        day = days[d]
        K0 = nearest_strike(float(day["spx_O"][I1549]))
        for off in EXPL_OFFSETS:
            for kind, k in (("call", K0 + off), ("put", K0 - off)):
                arr = day["options"].get((kind, float(k)))
                if arr is None or not np.isfinite(arr[0][I1549]):
                    continue
                mk = float(arr[0][I1549])
                closes = arr[1][I1549:I1558 + 1]
                mx = float(np.nanmax(closes)) if np.isfinite(closes).any() else float("nan")
                r = {"date": d, "offset": off, "kind": kind, "strike": k, "mark": mk, "max_close_1549_1558": mx}
                for mlt in EXPL_MULTIPLES:
                    r[f"reach_{int(mlt)}x"] = bool(np.isfinite(mx) and mx >= mlt * mk - 1e-12)
                leg = target_exit_leg(kind, k, mk, closes, float(day["settle"]), BASE_HALF_SPREAD, BASE_FEE, 2.0)
                r["pnl_usd_sell2x_else_hold"] = leg["pnl_usd"]
                r["pnl_usd_hold"] = leg_pnl(mk, intrinsic(kind, k, float(day["settle"])), BASE_HALF_SPREAD, BASE_FEE, False)["pnl_usd"]
                rows.append(r)
    table = {}
    for off in EXPL_OFFSETS:
        for kind in ("call", "put"):
            g = [r for r in rows if r["offset"] == off and r["kind"] == kind]
            if not g:
                continue
            table[f"{kind}_{off}"] = {"n": len(g), "mean_mark": float(np.mean([r["mark"] for r in g])),
                                      **{f"share_reach_{int(m)}x": float(np.mean([r[f"reach_{int(m)}x"] for r in g])) for m in EXPL_MULTIPLES},
                                      "mean_pnl_usd_sell2x_else_hold": float(np.mean([r["pnl_usd_sell2x_else_hold"] for r in g])),
                                      "mean_pnl_usd_hold": float(np.mean([r["pnl_usd_hold"] for r in g]))}
    return {"n_days": len(usable), "rows": rows, "table": table}


def exploratory_minute_profile(dates, O, C) -> dict:
    """(ii) mean |1-minute close-to-close log change| by bar, D1 2023-2026."""
    sel = dates >= "2023-01-01"
    Cs = C[sel]
    r = np.abs(lr(Cs[:, :-1], Cs[:, 1:])) * 1e4      # bar m+1 vs bar m
    by_bar = np.nanmean(r, axis=0)                     # index j -> bar j+1
    day_ref = float(np.nanmedian(by_bar[I1000 - 1:I1530 - 1]))
    prof = {}
    for m in range(I1530, I1559 + 1):
        t = (dt.datetime(2000, 1, 1, 9, 30) + dt.timedelta(minutes=m)).strftime("%H:%M")
        prof[t] = {"mean_abs_bps": float(by_bar[m - 1]), "vs_median_bar_10_00_15_29": float(by_bar[m - 1] / day_ref),
                   "n": int(np.isfinite(r[:, m - 1]).sum())}
    top = sorted(prof.items(), key=lambda kv: -kv[1]["mean_abs_bps"])[:5]
    return {"sample": {"first": str(dates[sel].min()), "last": str(dates[sel].max()), "n_days": int(sel.sum())},
            "definition": "mean over days of |ln(close bar m / close bar m-1)| in bps",
            "median_bar_10_00_15_29_bps": day_ref, "profile": prof, "top5": [k for k, _ in top]}


def exploratory_last_minute(days) -> dict:
    """(iii) move from the 15:59 bar close to the official close, D2 SPX."""
    rows = []
    for d, day in sorted(days.items()):
        c = day["spx_C"][I1559]
        o = day["spx_O"][I1549]
        if np.isfinite(c) and day["settle"] is not None and np.isfinite(o):
            gap = math.log(day["settle"] / c) * 1e4
            rc = math.log(day["settle"] / o) * 1e4
            rows.append({"date": d, "close_1559": float(c), "official": day["settle"], "gap_bps": gap, "r_close_official_bps": rc})
    g = np.array([r["gap_bps"] for r in rows])
    rc = np.array([r["r_close_official_bps"] for r in rows])
    return {"n_days": len(rows), "mean_bps": float(g.mean()), "mean_abs_bps": float(np.abs(g).mean()),
            "median_abs_bps": float(np.median(np.abs(g))), "max_abs_bps": float(np.abs(g).max()),
            "mean_abs_r_close_official_bps": float(np.abs(rc).mean()),
            "share_of_abs_move": float(np.abs(g).mean() / np.abs(rc).mean()),
            "corr_gap_with_r_1549_1559": float(np.corrcoef(g, rc - g)[0, 1]) if len(g) > 2 else None,
            "rows": rows}


def _parity_10m(marks, d, s, katm, max_offset: float = 15.0) -> dict:
    """C - P - (S - K) from 10-minute 15:40-bar closes vs the SPX 15:49-bar close (not simultaneous)."""
    devs = {}
    for off in np.arange(-max_offset, max_offset + 1e-9, STRIKE_STEP):
        k = float(katm + off)
        c, p = marks.get((d, "call", k)), marks.get((d, "put", k))
        if c is not None and p is not None:
            devs[k] = c - p - (s - k)
    v = np.array(list(devs.values()))
    return {"atm_dev": devs.get(float(katm)), "signed_dev_median_atm_pm15": float(np.median(v)) if len(v) else None,
            "n_strikes": int(len(v))}


def exploratory_10m_standin(days, d1_dates, O, C, rng, fit_end: str | None = None) -> dict:
    """(iv) NOT pre-registered: S1 with the 10-minute 15:40-bar close as the entry mark (~15:50:00,
    one minute after t0), strike nearest the SPX 15:49-bar close, every D2 day with SPX bars.
    The 10-minute closes are not simultaneous with each other or with SPX (parity is off by up to
    several points), so this stand-in cannot support or refute pass-rule condition 1; it is reported
    with and without a parity filter (|ATM C - P - (S - K)| <= PARITY_FILTER_PTS)."""
    marks, files = load_d2_10m()
    rows, items = [], []
    for d, day in sorted(days.items()):
        if not np.isfinite(day["spx_C"][I1549]) or day["settle"] is None:
            continue
        s = float(day["spx_C"][I1549])
        k = nearest_strike(s)
        c, p = marks.get((d, "call", k)), marks.get((d, "put", k))
        if c is None or p is None:
            continue
        pnl = straddle_pnl(k, c, p, float(day["settle"]), BASE_HALF_SPREAD, BASE_FEE)
        par = _parity_10m(marks, d, s, k)
        rows.append({"date": d, "S_1549_close": s, "K": k, "straddle_mark_10m": c + p, "settle": day["settle"],
                     "abs_move_pts": abs(day["settle"] - s), "pnl_usd": pnl["pnl_usd"],
                     "parity_atm_dev": par["atm_dev"], "parity_signed_median_pm15": par["signed_dev_median_atm_pm15"],
                     "passes_parity_filter": bool(par["atm_dev"] is not None and abs(par["atm_dev"]) <= PARITY_FILTER_PTS + 1e-9)})
        items.append({"date": d, "S0": s, "implied_pts": c + p})

    def block(rr, it_):
        v = np.array([r["pnl_usd"] for r in rr])
        ivr = implied_vs_realized(d1_dates, O, C, it_, rng, n_boot=2000, fit_end=fit_end)
        out = {"n_days": len(rr), "mean_pnl_usd_base": float(v.mean()) if len(v) else None,
               "t_ci95_usd": t_ci(v), "boot95_usd": boot_mean_ci(v, rng),
               "share_days_positive": float((v > 0).mean()) if len(v) else None,
               "total_pnl_usd": float(v.sum()) if len(v) else None,
               "largest_day_pnl_usd": float(v.max()) if len(v) else None,
               "largest_day": rr[int(np.argmax(v))]["date"] if len(v) else None,
               "mean_pnl_usd_excluding_largest_day": float(np.delete(v, int(np.argmax(v))).mean()) if len(v) > 1 else None,
               "median_pnl_usd": float(np.median(v)) if len(v) else None,
               "mean_straddle_mark_pts": float(np.mean([r["straddle_mark_10m"] for r in rr])) if rr else None,
               "mean_abs_move_pts": float(np.mean([r["abs_move_pts"] for r in rr])) if rr else None,
               "mean_implied_bps": float(np.mean([r["straddle_mark_10m"] / r["S_1549_close"] for r in rr]) * 1e4) if rr else None,
               "mean_realized_abs_move_official_bps": float(np.mean([r["abs_move_pts"] / r["S_1549_close"] for r in rr]) * 1e4) if rr else None,
               "mean_pred_regression_bps": float(np.mean([x["pred_regression_pts"] / x["S0"] for x in ivr["days"]
                                                          if np.isfinite(x["rv_d1"])]) * 1e4) if rr else None,
               "implied_vs_realized": {k: ivr.get(k) for k in ("stat", "n_d2_days", "evaluable")}}
        return out

    allr = block(rows, items)
    keep = [i for i, r in enumerate(rows) if r["passes_parity_filter"]]
    filt = block([rows[i] for i in keep], [items[i] for i in keep])
    return {"files": files, **allr, "parity_filtered": {"rule": f"|ATM C - P - (S - K)| <= {PARITY_FILTER_PTS} pts "
                                                                "(15:40-bar closes vs SPX 15:49-bar close)", **filt},
            "parity_abs_atm_dev_max": float(max(abs(r["parity_atm_dev"]) for r in rows)) if rows else None,
            "cannot_settle_condition_1": "10-minute closes are not simultaneous marks; this stand-in neither "
                                         "supports nor refutes the S1/S3 premise",
            "rows": rows}


def power_diagnostic(dates, O, C, s2_pred: str, s2_sign: int, fit_end: str | None) -> dict:
    """(v) design diagnostic, not a test: how many D2 days the option-P&L condition would need.
    Uses D1 2023-01-01 .. fit_end (exclusive) at the CFD's own price level (~ SPX points).
    S1: payoff |S_T - K0| of the 15:49 ATM straddle. S2: ATM option at the S2 entry bar in the
    S2 predictor's direction; its edge over a random-direction ATM option is
    mean(payoff_dir - |S_T - K| / 2) points, minus the base half-spread. Days needed for t = 2:
    (2 x SD / edge)^2; minimum detectable edge (t = 2) with n days: 2 x SD / sqrt(n)."""
    sel = dates >= "2023-01-01"
    if fit_end is not None:
        sel &= dates < fit_end
    Os, Cs = O[sel], C[sel]
    ST = Cs[:, I1559]
    s0 = Os[:, I1549]
    k0 = np.floor(s0 / STRIKE_STEP + 0.5) * STRIKE_STEP
    pay1 = np.abs(ST - k0)
    ok1 = np.isfinite(pay1)
    sd1 = float(pay1[ok1].std(ddof=1))
    spec = PREDICTORS[s2_pred]
    sig = spec["fn"](Os, Cs)
    se = Os[:, spec["entry"]]
    k2 = np.floor(se / STRIKE_STEP + 0.5) * STRIKE_STEP
    with np.errstate(invalid="ignore"):
        direction = np.where(np.sign(s2_sign) * sig > 0, 1.0, -1.0)
    pay2 = np.maximum(direction * (ST - k2), 0.0)
    rand2 = 0.5 * np.abs(ST - k2)
    ok2 = np.isfinite(pay2) & np.isfinite(sig)
    edge_gross = float((pay2 - rand2)[ok2].mean())
    edge_net = edge_gross - BASE_HALF_SPREAD
    sd2 = float(pay2[ok2].std(ddof=1))

    def need(sd, edge):
        return float((2.0 * sd / edge) ** 2) if edge > 0 else None

    return {"sample": {"first": str(dates[sel].min()), "last": str(dates[sel].max()), "n_days": int(ok1.sum())},
            "S1": {"payoff_sd_pts": sd1, "mean_payoff_pts": float(pay1[ok1].mean()),
                   "days_needed_t2": {f"edge_{e:.2f}_pts": need(sd1, e) for e in (0.25, 0.5, 1.0)},
                   "min_detectable_edge_pts_t2": {f"n_{n}": 2.0 * sd1 / math.sqrt(n) for n in (1, PLANNED_D2_DAYS, 250)}},
            "S2": {"predictor": s2_pred, "entry_bar": (dt.datetime(2000, 1, 1, 9, 30) + dt.timedelta(minutes=spec["entry"])).strftime("%H:%M"),
                   "payoff_sd_pts": sd2, "edge_over_random_direction_pts_gross": edge_gross,
                   "edge_after_base_half_spread_pts": edge_net, "days_needed_t2": need(sd2, edge_net),
                   "min_detectable_edge_pts_t2": {f"n_{n}": 2.0 * sd2 / math.sqrt(n) for n in (1, PLANNED_D2_DAYS, 250)}},
            "note": "SD of the payoff is used as the SD of per-trade P&L (entry price varies little relative to it)."}


def exploratory_p3_placebo(dates, O, C) -> dict:
    """(vi) P3 construction at every other minute: sign of the one-minute open-to-open change k -> k+1,
    target open k+1 -> close k+9 (same 9-bar horizon as P3), k = 10:00 .. 15:41. Plus P3 split at the
    NYSE 15:45 -> 15:50 switch (2019-04-01)."""
    def run_k(Os, Cs, k):
        sgn = np.sign(lr(Os[:, k], Os[:, k + 1]))
        y = sgn * lr(Os[:, k + 1], Cs[:, k + 9]) * 1e4
        return nw_mean_test(y)

    p3 = run_k(O, C, I1550)
    ts = []
    for k in range(I1000, mi("15:41") + 1):
        ts.append(run_k(O, C, k)["t"])
    ts = np.array(ts, dtype=float)
    late = dates >= "2023-01-01"
    ts_late = np.array([run_k(O[late], C[late], k)["t"] for k in range(I1000, mi("15:41") + 1)], dtype=float)
    p3_late = run_k(O[late], C[late], I1550)
    split = {}
    for lab, m in (("before_2019-04-01", dates < NYSE_1550_SWITCH),
                   ("2019-04-01_to_2022-12-31", (dates >= NYSE_1550_SWITCH) & (dates < "2023-01-01")),
                   ("2023-01-01_on", dates >= "2023-01-01")):
        r = run_k(O[m], C[m], I1550)
        split[lab] = {"n": r["n"], "mean_bps": r["mean"], "nw_t": r["t"]}
    return {"n_placebo_minutes": int(len(ts)), "p3_nw_t": p3["t"], "p3_mean_bps": p3["mean"],
            "placebo_median_t": float(np.median(ts)), "placebo_share_t_gt_2": float((ts > 2).mean()),
            "placebo_share_t_lt_minus_2": float((ts < -2).mean()), "placebo_max_t": float(ts.max()),
            "p3_rank_among_placebos_plus_p3": int((ts >= p3["t"]).sum()) + 1,
            "late_2023_2026": {"p3_nw_t": p3_late["t"], "placebo_median_t": float(np.median(ts_late)),
                               "placebo_share_t_gt_2": float((ts_late > 2).mean()),
                               "p3_rank": int((ts_late >= p3_late["t"]).sum()) + 1},
            "p3_by_nyse_regime": split}


def exploratory_yearly_spike(dates, O, C) -> dict:
    """(ii-b) by year: mean |1-minute close-to-close r| of the 15:45, 15:50, 15:55 and 15:59 bars relative to
    that year's median bar 10:00-15:29."""
    out = {}
    years = sorted(set(d[:4] for d in dates))
    r = np.abs(lr(C[:, :-1], C[:, 1:])) * 1e4
    for y in years:
        m = np.array([d[:4] == y for d in dates])
        by_bar = np.nanmean(r[m], axis=0)
        ref = float(np.nanmedian(by_bar[I1000 - 1:I1530 - 1]))
        out[y] = {"n_days": int(m.sum()), "median_bar_bps": ref,
                  **{f"x_{t.replace(':', '')}": float(by_bar[mi(t) - 1] / ref) for t in ("15:45", "15:50", "15:55", "15:59")}}
    return out


def exploratory_otm_10m(days) -> dict:
    """(vii) NOT pre-registered: on every D2 day with real 10-minute option bars, OTM calls/puts 5..30 points
    from the strike nearest the SPX 15:49-bar close. Entry = 15:40-bar close (~15:49:59). 'Reached k x' =
    the 15:50-bar HIGH (15:50:00-15:59:59) >= k x entry: an upper bound, because a bar high is a single
    print. Also the settlement multiple (intrinsic at the official close / entry) and hold-to-settlement
    P&L at base costs."""
    marks, _, t = load_d2_10m(full=True)
    hi50 = {(r.date, r.type, float(r.strike)): float(r.high) for r in t[t["time_et"] == "15:50"].itertuples()}
    rows = []
    for d, day in sorted(days.items()):
        if not np.isfinite(day["spx_C"][I1549]) or day["settle"] is None:
            continue
        s = float(day["spx_C"][I1549])
        k0 = nearest_strike(s)
        settle = float(day["settle"])
        for off in EXPL_OFFSETS:
            for kind, k in (("call", k0 + off), ("put", k0 - off)):
                mk, hi = marks.get((d, kind, float(k))), hi50.get((d, kind, float(k)))
                if mk is None or hi is None or mk <= 0:
                    continue
                val = intrinsic(kind, k, settle)
                rows.append({"date": d, "kind": kind, "offset": off, "strike": k, "entry_mark": mk, "high_1550_bar": hi,
                             **{f"reach_{int(m)}x": bool(hi >= m * mk - 1e-12) for m in EXPL_MULTIPLES},
                             "settle_multiple": val / mk,
                             "pnl_usd_hold": leg_pnl(mk, val, BASE_HALF_SPREAD, BASE_FEE, False)["pnl_usd"]})
    table = {}
    for off in EXPL_OFFSETS:
        for kind in ("call", "put"):
            g = [r for r in rows if r["offset"] == off and r["kind"] == kind]
            if not g:
                continue
            table[f"{kind}_{off}"] = {"n": len(g), "mean_entry_mark": float(np.mean([r["entry_mark"] for r in g])),
                                      **{f"share_reach_{int(m)}x_bar_high": float(np.mean([r[f"reach_{int(m)}x"] for r in g])) for m in EXPL_MULTIPLES},
                                      "share_settle_ge_2x": float(np.mean([r["settle_multiple"] >= 2.0 for r in g])),
                                      "share_settle_zero": float(np.mean([r["settle_multiple"] == 0.0 for r in g])),
                                      "mean_pnl_usd_hold": float(np.mean([r["pnl_usd_hold"] for r in g]))}
    near = [r for r in rows if r["offset"] in (5, 10)]
    return {"n_days": len(set(r["date"] for r in rows)), "n_options": len(rows), "table": table,
            "offsets_5_10_pooled": {"n": len(near),
                                    "share_reach_2x_bar_high": float(np.mean([r["reach_2x"] for r in near])) if near else None,
                                    "share_settle_ge_2x": float(np.mean([r["settle_multiple"] >= 2.0 for r in near])) if near else None,
                                    "share_settle_zero": float(np.mean([r["settle_multiple"] == 0.0 for r in near])) if near else None,
                                    "mean_pnl_usd_hold": float(np.mean([r["pnl_usd_hold"] for r in near])) if near else None},
            "rows": rows}


def recheck_validation(d1_dates, O, C, days) -> dict:
    ix = {d: i for i, d in enumerate(d1_dates)}
    a, b, agree, n3 = [], [], 0, 0
    for d, day in days.items():
        if d in ix and np.isfinite(day["spx_O"][I1549]) and np.isfinite(day["spx_C"][I1559]):
            a.append(float(target_values(O[ix[d]], C[ix[d]], "r_close")))
            b.append(math.log(day["spx_C"][I1559] / day["spx_O"][I1549]))
        if d in ix and np.isfinite(day["spx_O"][I1550]) and np.isfinite(day["spx_O"][I1551]):
            n3 += 1
            agree += int(_p3(O[ix[d]], C[ix[d]]) == _p3(day["spx_O"], day["spx_C"]))
    return {"n": len(a), "corr_r_close_d1_vs_d2_spx": float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else None,
            "p3_sign_agreement_d1_vs_d2_spx": {"n": n3, "agree": agree}}


# ------------------------------------------------------------------------------------------------
# main
# ------------------------------------------------------------------------------------------------
def verdict_row(c1, c1txt: str, sm) -> dict:
    """Pass rule with three-valued conditions (True / False / None = not evaluable). Condition 2 needs a
    reportable CI, so it is not evaluable with fewer than 2 usable D2 days."""
    n = sm["n_days"] if sm else 0
    if not sm or n < 2 or sm.get("t_ci95_usd") is None:
        c2 = None
    else:
        c2 = bool(sm["mean_usd"] > 0)
    candidate = (c1 is True) and (c2 is True)
    reasons = []
    if c1 is None:
        reasons.append("cond 1 not evaluable (fewer than 2 usable D2 days)")
    elif not c1:
        reasons.append("cond 1 not met")
    if c2 is None:
        reasons.append(f"cond 2 not evaluable ({n} of ~{PLANNED_D2_DAYS} planned D2 days; no CI possible)")
    elif not c2:
        reasons.append("cond 2 not met (mean D2 P&L <= 0)")
    if candidate:
        label = "CANDIDATE for forward paper logging"
    elif c2 is None:
        label = f"FAIL by rule; D2 test not run ({n} of ~{PLANNED_D2_DAYS} planned days)"
    else:
        label = "FAIL"
    return {"cond1": c1, "cond1_test": c1txt, "cond2": c2,
            "cond2_test": "mean D2 P&L after base costs (hs $0.10, fee $0.09) > 0, with CI",
            "d2_days": n, "d2_mean_usd_base": sm["mean_usd"] if sm else None,
            "d2_t_ci95_usd": sm.get("t_ci95_usd") if sm else None,
            "verdict": "CANDIDATE for forward paper logging" if candidate else "FAIL",
            "verdict_label": label, "reasons": reasons}


def _rng(k: int):
    return np.random.default_rng([SEED, k])


def run() -> dict:
    t_start = dt.datetime.now(dt.timezone.utc)
    res = {"meta": {"prereg": str(PREREG), "script": str(Path(__file__).resolve()),
                    "generated_utc": t_start.isoformat(timespec="seconds"), "seed": SEED, "n_boot": N_BOOT,
                    "decisions_and_interpretations": DECISIONS}}

    # ---- D1 and its validation gate
    val = json.loads(D1_VALIDATION.read_text())
    dates, wkd, O, C, day_table = load_d1("keep")
    reasons = day_table["reason"].value_counts().to_dict()
    res["d1"] = {"file": str(D1_FILE), "usable_days": int(len(dates)), "first": str(dates.min()), "last": str(dates.max()),
                 "weekday_files_by_reason": {k: int(v) for k, v in reasons.items()},
                 "note": "weekends (never downloaded) and NYSE holidays are not trading days; delayed_clock_feed = "
                         "2011-09-19..2013-02-26 dropped by build_d1.py (feed clock ~15-20 min late)",
                 "strict_rule_usable_days": int(day_table["keep_strict"].sum()),
                 "days_without_0930_bar": int((~np.isfinite(O[:, I0930])).sum()),
                 "days_without_1000_bar": int((~np.isfinite(O[:, I1000])).sum())}
    corr_ok = {k: v["r_close_1549_to_1559"]["corr"] for k, v in val["sources"].items()}
    gate = bool(val["required_checks"]["spy_bars_1m"] and val["required_checks"]["spx_robinhood_d2"]
                and corr_ok["spy_bars_1m"] >= 0.90 and corr_ok["spx_robinhood_d2"] >= 0.90)
    res["validation"] = {"file": str(D1_VALIDATION), "corr_r_close": corr_ok,
                         "n_overlap": {k: v["r_close_1549_to_1559"]["n"] for k, v in val["sources"].items()},
                         "validated_at_utc": val.get("validated_at_utc"), "d1_accepted": gate,
                         "rule": "corr >= 0.90 vs SPY data/bars_1m AND vs Robinhood SPX minute bars"}
    assert gate, "D1 failed the pre-registered correlation gate: use only where it agrees (not implemented)"

    # ---- look-ahead self-check on the real D1 matrices
    res["lookahead_selfcheck"] = {"d1": lookahead_selfcheck(O, C, _rng(1)), "passed": True}

    # ---- H1, H2 primary and strict sensitivity
    res["h1"] = {"primary_keep": h1_test(O, C, _rng(2))}
    res["h2"] = {"primary_keep": h2_test(O, C, dates, wkd)}
    sd, sw, sO, sC, _ = load_d1("keep_strict")
    res["h1"]["sensitivity_keep_strict"] = h1_test(sO, sC, _rng(3))
    res["h2"]["sensitivity_keep_strict"] = h2_test(sO, sC, sd, sw)
    del sO, sC
    # ---- D2 sessions (loaded here so the D1 look-ahead cutoff = first D2 session is known)
    days, d2info = load_d2()
    d2_first = d2info["first"]

    best = res["h2"]["primary_keep"]["best_abs_t"]
    alt = res["h2"]["primary_keep"]["best_abs_t_known_at_t0"]
    pre = dates < d2_first
    h2_pre = h2_test(O[pre], C[pre], dates[pre], wkd[pre])
    res["s2_selection"] = {**best, "rule": "largest |NW t| on full-sample D1 (primary day set), as pre-registered; "
                                           "call if sign(t) x P > 0 else put (P = 0 -> put); undefined P -> day excluded",
                           "label": "workflow clarification, made before D2 results were computed",
                           "entry_bar": "15:51" if best["predictor"] == "P3" else "15:49",
                           "check_on_d1_before_first_d2_session": {
                               "cutoff_exclusive": d2_first, "n_days": int(pre.sum()),
                               "predictor": h2_pre["best_abs_t"]["predictor"], "nw_t": h2_pre["best_abs_t"]["nw_t"],
                               "same_choice": h2_pre["best_abs_t"]["predictor"] == best["predictor"]
                               and h2_pre["best_abs_t"]["trade_sign_multiplier"] == best["trade_sign_multiplier"],
                               "alt_known_at_t0_predictor": h2_pre["best_abs_t_known_at_t0"]["predictor"]},
                           "alt_reading_known_at_t0": {**alt, "entry_bar": "15:49",
                                                       "label": "sensitivity: largest abs NW t among predictors known at t0 (audit finding 3)"}}
    s2_specs = {"S2": (best["predictor"], best["trade_sign_multiplier"]),
                "S2_alt": (alt["predictor"], alt["trade_sign_multiplier"])}

    # ---- D2
    ev = evaluate_d2(days, s2_specs, _rng(4))
    res["lookahead_selfcheck"]["d2"] = ev["lookahead_selfcheck"]
    st = ev["status"]
    no_spx = [d for d, s in st.items() if not s["spx_complete_1519_1559"]]
    no_opt = [d for d, s in st.items() if s["spx_complete_1519_1559"] and not s["options_real_at_t0"]]
    no_settle = [d for d, s in st.items() if s["settle"] is None]
    res["d2"] = {**d2info, "usable_days_h3": ev["usable_days"], "n_usable_h3": len(ev["usable_days"]),
                 "planned_days": PLANNED_D2_DAYS,
                 "dropped": {"no_real_spx_minute_bars": no_spx, "no_real_option_minute_bar_at_15_49": no_opt,
                             "no_official_close": no_settle},
                 "settlement": "SPX official daily close (Robinhood daily bars, interpolated rows dropped)",
                 "status_by_day": st}
    res["validation"]["recheck_in_analysis"] = recheck_validation(dates, O, C, days)

    # ---- implied vs realized (pre-registered, H3); fit ends the day before the first D2 session
    items = [{"date": d, "S0": ev["per_day"][d]["S0"], "implied_pts": ev["per_day"][d]["straddle_mark"]}
             for d in ev["usable_days"]]
    ivr = implied_vs_realized(dates, O, C, items, _rng(5), fit_end=d2_first)
    for it in ivr["days"]:
        it["realized_abs_move_official_pts"] = ev["per_day"][it["date"]]["realized_abs_move_pts"]
    res["h3"] = {"implied_vs_realized": ivr, "per_day": ev["per_day"], "pnl_summary": ev["summary"]}
    res["power_diagnostic"] = power_diagnostic(dates, O, C, best["predictor"], best["trade_sign_multiplier"], d2_first)

    # ---- verdicts (mechanical, three-valued conditions)
    base = f"hs{BASE_HALF_SPREAD:.2f}_fee{BASE_FEE:.2f}"
    size_ok = ivr.get("size_premise_passes")          # True / False / None (not evaluable)
    full = res["h2"]["primary_keep"]["full_sample"]
    verdicts = {}
    for strat, c1, c1txt in (
            ("S1", size_ok, "D1 realized move (regression on rv, 2023-01..pre-D2) - D2 implied straddle: "
                            "bootstrap 95% CI over D2 days > 0"),
            ("S2", full[best["predictor"]]["passes_direction"],
             f"{best['predictor']} Holm p < 0.05 and same sign in 2023-2026 (entry {res['s2_selection']['entry_bar']})"),
            ("S2_alt", full[alt["predictor"]]["passes_direction"],
             f"sensitivity: {alt['predictor']} (largest abs t among predictors known at t0) Holm p < 0.05 and same sign in 2023-2026 (entry 15:49)"),
            ("S3", size_ok, "same size premise as S1")):
        verdicts[strat] = verdict_row(c1, c1txt, ev["summary"].get(strat, {}).get(base))
    res["verdicts"] = verdicts

    # ---- exploratory (labelled; not part of pass/fail)
    res["exploratory"] = {
        "label": "EXPLORATORY - not part of the pre-registered pass/fail; counted below",
        "i_otm_multiples": exploratory_otm(days, ev["usable_days"]),
        "ii_minute_profile_d1_2023_2026": exploratory_minute_profile(dates, O, C),
        "ii_b_yearly_close_spikes": exploratory_yearly_spike(dates, O, C),
        "iii_d2_1559_close_to_official_close": exploratory_last_minute(days),
        "iv_s1_with_10m_standin_entry": exploratory_10m_standin(days, dates, O, C, _rng(6), fit_end=d2_first),
        "vi_p3_placebo_and_regimes": exploratory_p3_placebo(dates, O, C),
        "vii_otm_multiples_10m_bars": exploratory_otm_10m(days),
    }
    added = ["(iv) S1 with 10-minute 15:40-bar close as entry stand-in (22 days)",
             "(iv) the same with a parity filter |ATM dev| <= 0.5",
             "D1 strict day-rule sensitivity for H1/H2",
             "ratio and unconditional implied-vs-realized models next to the regression",
             "S2-alt: largest abs t among predictors known at 15:49 (P1/P2/P4), entry 15:49",
             "fee $1.13/contract/side (actual Robinhood SPXW fee, upper end) in the cost grid",
             "1-day-block (iid) bootstrap sensitivity next to the 20-day-block CIs",
             "S2 predictor selection repeated on D1 dates before the first D2 session",
             "(ii-b) yearly size of the 15:45/15:50/15:55/15:59 bars",
             "(vi) P3 placebo at 342 other minutes + P3 split at the 2019-04-01 NYSE switch",
             "(vii) OTM 5..30 reach 2x/3x/5x from 10-minute bar highs (22 days)"]
    res["exploratory"]["count"] = {
        "requested_by_workflow": ["(i) OTM 5..30 x call/put reach 2x/3x/5x + sell-at-2x rule (12 option "
                                  "series x 4 statistics)", "(ii) minute-of-day |r| profile", "(iii) 15:59 close -> official close"],
        "added_by_this_analysis": added,
        "n_extra_variants": 3 + len(added),
        "not_counted": "power diagnostic (design arithmetic, no new test) and the per-day parity data-quality check "
                       "(pre-registered check)"}
    res["meta"]["runtime_s"] = (dt.datetime.now(dt.timezone.utc) - t_start).total_seconds()
    return res


# ------------------------------------------------------------------------------------------------
# report
# ------------------------------------------------------------------------------------------------
def _f(x, nd=2):
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, float) and not math.isfinite(x):
        return "n/a"
    return f"{x:.{nd}f}"


def _ci(c, nd=2):
    return "n/a" if not c else f"[{c[0]:.{nd}f}, {c[1]:.{nd}f}]"


def _tri(x):
    return "not evaluable" if x is None else ("yes" if x else "no")


def _p(x):
    if x is None:
        return "n/a"
    return f"{x:.2e}" if x < 1e-3 else f"{x:.4f}"


def write_md(res: dict) -> str:
    L = []
    a = L.append
    a("# SPX 15:49 close study: raw results")
    a("")
    a(f"Generated {res['meta']['generated_utc']} by `backtests/spx_close_1549/analysis.py` from the binding "
      f"pre-registration `preregistration/spx_1549_close.md`. Seed {SEED}, {N_BOOT} bootstrap draws. "
      "Machine-generated: every number below is read from `results.json`.")
    a("")
    a("## Verdicts (pass rule applied mechanically)")
    a("")
    a("Conditions are yes / no / not evaluable. A strategy is a candidate only if both are yes.")
    a("")
    a("| strategy | cond 1 (D1 premise) | cond 2 (D2 mean P&L > 0 with CI, base costs) | D2 days | D2 mean $/trade | verdict |")
    a("|---|---|---|---|---|---|")
    for s, v in res["verdicts"].items():
        a(f"| {s} | {_tri(v['cond1'])}: {v['cond1_test']} | {_tri(v['cond2'])} | {v['d2_days']} | "
          f"{_f(v['d2_mean_usd_base'])} | **{v['verdict_label']}** |")
    a("")
    a("Reading the verdicts:")
    a("")
    for s, v in res["verdicts"].items():
        a(f"- {s}: {'; '.join(v['reasons']) or 'both conditions met'}.")
    nd2 = res["d2"]["n_usable_h3"]
    a(f"- Condition 2 was decided on {nd2} of the ~{PLANNED_D2_DAYS} planned D2 days, so the option P&L test "
      "did not run; a negative mean on that day is not evidence that the option P&L is negative in general.")
    ivr0 = res["h3"]["implied_vs_realized"]
    if not ivr0.get("evaluable"):
        a(f"- Condition 1 for S1/S3 is not evaluable: {ivr0.get('not_evaluable_reason', 'no usable D2 day')}. The "
          "22-day 10-minute stand-in (exploratory (iv)) does not support it either.")
    a("")
    a("## Data")
    a("")
    d1 = res["d1"]
    a(f"- D1: {d1['usable_days']} usable days, {d1['first']} to {d1['last']} (primary rule `keep`). "
      f"Weekday files by reason: {d1['weekday_files_by_reason']}. {d1['note']}.")
    a(f"- D1 strict-rule sensitivity: {d1['strict_rule_usable_days']} days. Days without a 09:30 bar: "
      f"{d1['days_without_0930_bar']} (P1, P4 undefined); without a 10:00 bar: {d1['days_without_1000_bar']}.")
    v = res["validation"]
    a(f"- D1 validation gate: corr(r_close) SPY bars_1m {v['corr_r_close']['spy_bars_1m']:.4f} "
      f"(n {v['n_overlap']['spy_bars_1m']}), Robinhood SPX {v['corr_r_close']['spx_robinhood_d2']:.4f} "
      f"(n {v['n_overlap']['spx_robinhood_d2']}) -> accepted = {_f(v['d1_accepted'])}. Recomputed here vs D2 "
      f"SPX minute bars: corr {_f(v['recheck_in_analysis']['corr_r_close_d1_vs_d2_spx'], 4)} "
      f"(n {v['recheck_in_analysis']['n']}).")
    d2 = res["d2"]
    a(f"- D2: {d2['sessions_collected']} sessions collected ({d2['first']}..{d2['last']}); SPX bars "
      f"{d2['spx_bars_total']} ({d2['spx_bars_interpolated_discarded']} interpolated, discarded); option bars "
      f"{d2['option_bars_total']} ({d2['option_bars_interpolated_discarded']} interpolated, discarded).")
    a(f"  - dropped, no real SPX minute bars: {len(d2['dropped']['no_real_spx_minute_bars'])} "
      f"({', '.join(d2['dropped']['no_real_spx_minute_bars'])})")
    a(f"  - dropped, SPX fine but no real option minute bar at 15:49: {len(d2['dropped']['no_real_option_minute_bar_at_15_49'])} "
      f"({', '.join(d2['dropped']['no_real_option_minute_bar_at_15_49'])})")
    a(f"  - **usable for H3: {d2['n_usable_h3']}** ({', '.join(d2['usable_days_h3']) or 'none'}). The "
      "pre-registration expected about 35.")
    rc = v["recheck_in_analysis"].get("p3_sign_agreement_d1_vs_d2_spx")
    if rc:
        a(f"- P3 sign (15:50 open -> 15:51 open) agrees between D1 and Robinhood SPX on {rc['agree']} of {rc['n']} overlap days.")
    a("- Data quality, pre-registered put-call parity check C - P - (S - K) on 1-minute bar opens (strikes ATM +/- 30 "
      "with both legs real):")
    for d, rec in res["h3"]["per_day"].items():
        for t, x in rec["parity_check"].items():
            a(f"  - {d} {t}: SPX open {_f(x['spx_open'])}, {x['n_strikes']} strikes, signed median {_f(x['signed_dev_median'])}, "
              f"max |dev| {_f(x['abs_dev_max'])}, ATM ({_f(x['K_atm'], 0)}) dev {_f(x['atm_dev'])}; option-implied SPX "
              f"{_f(x['option_implied_spx_median'])}")
    a("  - Caveat: Robinhood option bar opens look like sampled prints/marks rather than clean mids. If they are "
      "prints, the $0.10 half-spread may partly double-count the cost; the parity gap at 15:49-15:50 shows the call "
      "and put levels are not mutually consistent there (bar timing itself lines up: see audits/DISPOSITION.md "
      "finding 4). For a near-delta-neutral straddle the effect on S1/S3 is close to zero.")
    a("")
    a("## Decisions, interpretations and deviations")
    a("")
    for dd in res["meta"]["decisions_and_interpretations"]:
        kind = f" **[{dd['kind']}]**" if dd.get("kind") else ""
        a(f"- **{dd['id']}**{kind} ({dd['source']}): {dd['text']}")
    a("")
    a("## Look-ahead self-check")
    a("")
    for x in res["lookahead_selfcheck"]["d1"] + res["lookahead_selfcheck"]["d2"]:
        a(f"- PASS {x}")
    a("")
    a("## H1 size (D1)")
    a("")
    for setname, label in (("primary_keep", "primary (`keep`)"), ("sensitivity_keep_strict", "sensitivity (`keep_strict`)")):
        h = res["h1"][setname]
        a(f"### {label}")
        a("")
        a(f"| baseline | n | mean abs r_close bps | mean baseline bps | ratio of means | mean ln diff | geo ratio | t | p | "
          f"boot95 mean ln diff ({BLOCK_LEN}-day blocks) | boot95 iid (sensitivity) | share days larger | passes |")
        a("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for k in ("a_vs_1538_1549_window", "b_vs_same_day_median_window"):
            x = h[k]
            a(f"| {k} | {x['n_days']} | {_f(x['mean_abs_r_close_bps'])} | {_f(x['mean_baseline_bps'])} | {_f(x['ratio_of_means'])} | "
              f"{_f(x['mean_log_diff'], 3)} | {_f(x['geometric_ratio'])} | {_f(x['t'])} | {_p(x['p_two_sided'])} | "
              f"{_ci(x['boot95_mean_log_diff'], 3)} | {_ci(x.get('boot95_mean_log_diff_iid_sensitivity'), 3)} | "
              f"{_f(x['share_days_r_close_larger'], 3)} | {_f(x['passes'])} |")
        a("")
    a("## H2 direction (D1)")
    a("")
    for setname, label in (("primary_keep", "primary (`keep`)"), ("sensitivity_keep_strict", "sensitivity (`keep_strict`)")):
        h = res["h2"][setname]
        a(f"### {label}: full sample")
        a("")
        a("| predictor | target | n | mean bps | NW t | p | Holm p | hit rate | zero-sign days | 2023-26 same sign | passes |")
        a("|---|---|---|---|---|---|---|---|---|---|---|")
        for n, x in h["full_sample"].items():
            a(f"| {n} {x['desc']} | {x['target']} | {x['n']} | {_f(x['mean_bps'], 3)} | {_f(x['nw_t'])} | {_p(x['p'])} | "
              f"{_p(x['p_holm'])} | {_f(x['hit_rate'], 3)} | {x['n_zero_sign']} | {_f(x['same_sign_2023_2026'])} | {_f(x['passes_direction'])} |")
        a("")
        a(f"Largest |NW t|: {h['best_abs_t']['predictor']} (t = {_f(h['best_abs_t']['nw_t'])}).")
        a("")
        if setname == "primary_keep":
            a("Subperiods (descriptive): mean bps / NW t / hit rate / n")
            a("")
            a("| predictor | " + " | ".join(SUBPERIODS) + " |")
            a("|---|" + "---|" * len(SUBPERIODS))
            for n in PREDICTORS:
                cells = [f"{_f(h['subperiods'][n][p]['mean_bps'], 3)} / {_f(h['subperiods'][n][p]['nw_t'])} / "
                         f"{_f(h['subperiods'][n][p]['hit_rate'], 3)} / {h['subperiods'][n][p]['n']}" for p in SUBPERIODS]
                a(f"| {n} | " + " | ".join(cells) + " |")
            a("")
            a("Weekday (descriptive): mean bps / NW t / hit rate / n")
            a("")
            a("| predictor | " + " | ".join(WEEKDAYS) + " |")
            a("|---|" + "---|" * len(WEEKDAYS))
            for n in PREDICTORS:
                cells = [f"{_f(h['weekday'][n][w]['mean_bps'], 3)} / {_f(h['weekday'][n][w]['nw_t'])} / "
                         f"{_f(h['weekday'][n][w]['hit_rate'], 3)} / {h['weekday'][n][w]['n']}" for w in WEEKDAYS]
                a(f"| {n} | " + " | ".join(cells) + " |")
            a("")
    s2 = res["s2_selection"]
    ck = s2["check_on_d1_before_first_d2_session"]
    al = s2["alt_reading_known_at_t0"]
    a(f"S2 predictor ({s2['label']}): **{s2['predictor']}**, NW t {_f(s2['nw_t'])}, trade sign multiplier "
      f"{s2['trade_sign_multiplier']:+d}, entry {s2['entry_bar']}. Look-ahead check on D1 dates before {ck['cutoff_exclusive']} "
      f"(n {ck['n_days']}): best = {ck['predictor']} (NW t {_f(ck['nw_t'])}), same choice = {_f(ck['same_choice'])}.")
    a("")
    a(f"S2-alt ({al['label']}): **{al['predictor']}**, NW t {_f(al['nw_t'])}, trade sign multiplier "
      f"{al['trade_sign_multiplier']:+d}, entry 15:49.")
    a("")
    a("## H3 options (D2)")
    a("")
    ivr = res["h3"]["implied_vs_realized"]
    r = ivr["regression"]
    a(f"Implied vs realized. Fit on D1 {ivr['fit_sample']['first']}..{ivr['fit_sample']['last']} "
      f"(n {ivr['fit_sample']['n_days']}; ends before the first D2 session {ivr['fit_sample']['fit_end_exclusive']}): "
      f"|r_close| = {r['a']:.6f} + {r['b']:.4f} x rv (R^2 {r['r2']:.3f}); "
      f"ratio k = {ivr['ratio_k']:.4f}; mean |r_close| {ivr['mean_abs_move_frac_2023_2026'] * 1e4:.2f} bps.")
    a("")
    cal = ivr.get("calibration_out_of_sample")
    if cal:
        a(f"Out-of-sample calibration on D1 days {cal['first']}..{cal['last']} (n {cal['n_days']}, the D2 window): "
          f"model mean |r_close| {cal['mean_pred_regression_bps']:.2f} bps vs realized {cal['mean_realized_abs_r_close_bps']:.2f} bps "
          f"(mean rv {cal['mean_rv_bps']:.1f} bps vs {ivr['mean_rv_frac_2023_2026'] * 1e4:.1f} bps in the fit sample).")
        a("")
    a("| date | S0 | rv to t0 (bps) | implied straddle pts | pred regression pts | pred ratio pts | pred uncond. pts | realized abs(S_T - S0) pts |")
    a("|---|---|---|---|---|---|---|---|")
    for it in ivr["days"]:
        a(f"| {it['date']} | {_f(it['S0'])} | {_f(it['rv_d1'] * 1e4)} | {_f(it['implied_pts'])} | {_f(it['pred_regression_pts'])} | "
          f"{_f(it['pred_ratio_pts'])} | {_f(it['pred_unconditional_pts'])} | {_f(it['realized_abs_move_official_pts'])} |")
    a("")
    if ivr.get("stat"):
        a("| model | mean (pred - implied) pts | mean pred/implied | boot95 pts | boot95 iid D1 (sensitivity) | CI > 0 |")
        a("|---|---|---|---|---|---|")
        for m, x in ivr["stat"].items():
            a(f"| {m}{' (pass-rule model)' if m == 'regression' else ''} | {_f(x['mean_pred_minus_implied_pts'])} | "
              f"{_f(x['mean_ratio_pred_over_implied'], 3)} | {_ci(x['boot95_pts'])} | {_ci(x.get('boot95_pts_iid_d1_sensitivity'))} | "
              f"{_f(x['ci_excludes_zero_positive'])} |")
        a("")
    else:
        a(f"Pass-rule statistic: **not evaluable** ({ivr.get('not_evaluable_reason', 'no usable D2 day')}).")
        ds = ivr.get("descriptive_single_day")
        if ds:
            a("Descriptive only, one day: " + "; ".join(
                f"{m} pred - implied {_f(x['pred_minus_implied_pts'])} pts (pred/implied {_f(x['pred_over_implied'], 3)})"
                for m, x in ds.items()) + ".")
        a("")
    a("Per-day option P&L ($ per trade; S1 = 1 straddle, S2 = 1 contract, S3 = 1 call + 1 put):")
    a("")
    s2n = [k for k in res["h3"]["pnl_summary"] if k.startswith("S2")]
    for d, rec in res["h3"]["per_day"].items():
        a(f"- {d}: S0 {_f(rec['S0'])}, K0 {_f(rec['K0'], 0)}, call {_f(rec['call_mark'])}, put {_f(rec['put_mark'])}, "
          f"straddle {_f(rec['straddle_mark'])}, 15:59 close {_f(rec['spx_1559_close'])}, official close {_f(rec['settle'])}, "
          f"realized |settle - S0| {_f(rec['realized_abs_move_pts'])}; decisions {rec['decisions']}")
        base = rec["pnl"][f"hs{BASE_HALF_SPREAD:.2f}_fee{BASE_FEE:.2f}"]
        a(f"  - S1: straddle {_f(rec['K0'], 0)} P&L ${_f(base['S1']['pnl_usd'])}")
        s3 = base["S3"]
        if s3:
            for kind, leg in s3["legs"].items():
                a(f"  - S3 {kind} {_f(leg['strike'], 0)}: mark {_f(leg['entry_mark'])}, sold at 2x = {_f(leg['sold'])}"
                  f"{'' if leg['hit_bar_offset'] is None else ' (bar 15:' + str(49 + leg['hit_bar_offset']) + ')'}, P&L ${_f(leg['pnl_usd'])}")
        for v_ in s2n:
            if base.get(v_):
                a(f"  - {v_}: {base[v_].get('kind')} {_f(base[v_].get('strike'), 0)} at mark {_f(base[v_].get('entry_mark'))}, "
                  f"P&L ${_f(base[v_]['pnl_usd'])}")
            else:
                a(f"  - {v_}: no trade (predictor undefined); excluded from the mean")
    a("")
    a("Cost grid, mean $ per trade (n days) [t 95% CI]:")
    a("")
    keys = list(res["h3"]["pnl_summary"]["S1"].keys()) if res["h3"]["pnl_summary"].get("S1") else []
    strat_cols = ["S1"] + s2n + ["S3"]
    a("| cost case | " + " | ".join(strat_cols) + " |")
    a("|---|" + "---|" * len(strat_cols))
    base_key = f"hs{BASE_HALF_SPREAD:.2f}_fee{BASE_FEE:.2f}"
    for k in keys:
        cells = []
        for s in strat_cols:
            x = res["h3"]["pnl_summary"][s][k]
            cells.append(f"{_f(x['mean_usd'])} (n {x['n_days']}) {_ci(x['t_ci95_usd'])}")
        tag = " (base)" if k == base_key else (" (extra: actual RH fee)" if any(k.endswith(f"fee{f:.2f}") for f in EXTRA_FEES) else "")
        a(f"| {k}{tag} | " + " | ".join(cells) + " |")
    a("")
    pw = res.get("power_diagnostic")
    if pw:
        a(f"### Power diagnostic (design arithmetic, not a test; D1 {pw['sample']['first']}..{pw['sample']['last']}, n {pw['sample']['n_days']})")
        a("")
        p1, p2 = pw["S1"], pw["S2"]
        a(f"- S1 straddle payoff SD {p1['payoff_sd_pts']:.2f} pts (mean payoff {p1['mean_payoff_pts']:.2f}). Days needed for t = 2: "
          + ", ".join(f"{k.replace('edge_', '+').replace('_pts', ' pt edge')}: {_f(v_, 0)}" for k, v_ in p1["days_needed_t2"].items())
          + f". Smallest edge detectable (t = 2) with {PLANNED_D2_DAYS} days: {p1['min_detectable_edge_pts_t2'][f'n_{PLANNED_D2_DAYS}']:.2f} pts "
          f"(${100 * p1['min_detectable_edge_pts_t2'][f'n_{PLANNED_D2_DAYS}']:.0f} per straddle).")
        a(f"- S2 ({p2['predictor']}, entry {p2['entry_bar']}) payoff SD {p2['payoff_sd_pts']:.2f} pts; edge over a random-direction ATM option "
          f"{p2['edge_over_random_direction_pts_gross']:.3f} pts gross, {p2['edge_after_base_half_spread_pts']:.3f} pts after the $0.10 half-spread; "
          f"days needed for t = 2: {_f(p2['days_needed_t2'], 0)}. Smallest edge detectable with {PLANNED_D2_DAYS} days: "
          f"{p2['min_detectable_edge_pts_t2'][f'n_{PLANNED_D2_DAYS}']:.2f} pts.")
        a(f"- {pw['note']}")
        a("")
    a("## EXPLORATORY (not part of pass/fail)")
    a("")
    ex = res["exploratory"]
    e1 = ex["i_otm_multiples"]
    a(f"### (i) OTM 0DTE options at 15:49 reaching 2x/3x/5x at a bar close 15:49..15:58 (n days {e1['n_days']})")
    a("")
    a("| series | n | mean mark | reach 2x | reach 3x | reach 5x | mean $ sell-at-2x-else-hold | mean $ hold |")
    a("|---|---|---|---|---|---|---|---|")
    for k, x in e1["table"].items():
        a(f"| {k} | {x['n']} | {_f(x['mean_mark'])} | {_f(x['share_reach_2x'])} | {_f(x['share_reach_3x'])} | "
          f"{_f(x['share_reach_5x'])} | {_f(x['mean_pnl_usd_sell2x_else_hold'])} | {_f(x['mean_pnl_usd_hold'])} |")
    a("")
    e2 = ex["ii_minute_profile_d1_2023_2026"]
    a(f"### (ii) mean |1-minute r| by bar, D1 {e2['sample']['first']}..{e2['sample']['last']} (n {e2['sample']['n_days']})")
    a("")
    a(f"{e2['definition']}. Median bar 10:00-15:29 = {e2['median_bar_10_00_15_29_bps']:.3f} bps. Top 5: {', '.join(e2['top5'])}.")
    a("")
    a("| bar | mean abs bps | x median bar |")
    a("|---|---|---|")
    for t, x in e2["profile"].items():
        a(f"| {t} | {_f(x['mean_abs_bps'], 3)} | {_f(x['vs_median_bar_10_00_15_29'])} |")
    a("")
    e2b = ex["ii_b_yearly_close_spikes"]
    a("### (ii-b) added after the audit: size of selected close bars by year (x that year's median bar 10:00-15:29)")
    a("")
    a(f"NYSE moved its first imbalance publication from 15:45 to 15:50 on {NYSE_1550_SWITCH} (research file).")
    a("")
    a("| year | n days | median bar bps | 15:45 | 15:50 | 15:55 | 15:59 |")
    a("|---|---|---|---|---|---|---|")
    for y, x in e2b.items():
        a(f"| {y} | {x['n_days']} | {_f(x['median_bar_bps'], 3)} | {_f(x['x_1545'])} | {_f(x['x_1550'])} | {_f(x['x_1555'])} | {_f(x['x_1559'])} |")
    a("")
    e3 = ex["iii_d2_1559_close_to_official_close"]
    a(f"### (iii) D2 SPX: 15:59-bar close -> official close (n {e3['n_days']})")
    a("")
    a(f"Mean {e3['mean_bps']:.2f} bps, mean |.| {e3['mean_abs_bps']:.2f} bps, median |.| {e3['median_abs_bps']:.2f} bps, "
      f"max |.| {e3['max_abs_bps']:.2f} bps; mean |r_close to official| {e3['mean_abs_r_close_official_bps']:.2f} bps "
      f"(gap / move = {e3['share_of_abs_move']:.2f}).")
    a("")
    a("| date | 15:59 close | official | gap bps |")
    a("|---|---|---|---|")
    for x in e3["rows"]:
        a(f"| {x['date']} | {_f(x['close_1559'])} | {_f(x['official'])} | {_f(x['gap_bps'])} |")
    a("")
    e4 = ex["iv_s1_with_10m_standin_entry"]
    a(f"### (iv) added by this analysis, not pre-registered: S1 with the 10-minute 15:40-bar close as entry (~1 minute after t0)")
    a("")
    a(f"**{e4['cannot_settle_condition_1']}.** Max |ATM parity deviation| on these days: {_f(e4['parity_abs_atm_dev_max'])} pts.")
    a("")
    for lab, blk in (("all days", e4), (f"parity-filtered ({e4['parity_filtered']['rule']})", e4["parity_filtered"])):
        a(f"- **{lab}**: n days {blk['n_days']}; mean straddle {_f(blk['mean_straddle_mark_pts'])} pts "
          f"({_f(blk['mean_implied_bps'])} bps) vs mean |official close - S| {_f(blk['mean_abs_move_pts'])} pts "
          f"({_f(blk['mean_realized_abs_move_official_bps'])} bps); model-predicted move {_f(blk['mean_pred_regression_bps'])} bps; "
          f"mean P&L ${_f(blk['mean_pnl_usd_base'])} per straddle at base costs, t95 {_ci(blk['t_ci95_usd'])}, boot95 "
          f"{_ci(blk['boot95_usd'])}, share of days positive {_f(blk['share_days_positive'])}; total ${_f(blk['total_pnl_usd'])}, "
          f"largest day {blk['largest_day']} ${_f(blk['largest_day_pnl_usd'])}; mean without it ${_f(blk['mean_pnl_usd_excluding_largest_day'])}; "
          f"median ${_f(blk['median_pnl_usd'])}.")
        st = blk["implied_vs_realized"]["stat"]
        if st:
            a(f"  Implied vs realized (regression model): mean pred - implied {_f(st['regression']['mean_pred_minus_implied_pts'])} pts, "
              f"boot95 {_ci(st['regression']['boot95_pts'])} (iid D1: {_ci(st['regression']['boot95_pts_iid_d1_sensitivity'])}); "
              f"ratio model {_f(st['ratio']['mean_pred_minus_implied_pts'])} {_ci(st['ratio']['boot95_pts'])}; "
              f"unconditional {_f(st['unconditional']['mean_pred_minus_implied_pts'])} {_ci(st['unconditional']['boot95_pts'])}.")
    a("")
    a("| date | S 15:49 close | K | straddle (10m) | ATM parity dev | official | abs move | P&L $ |")
    a("|---|---|---|---|---|---|---|---|")
    for x in e4["rows"]:
        a(f"| {x['date']} | {_f(x['S_1549_close'])} | {_f(x['K'], 0)} | {_f(x['straddle_mark_10m'])} | {_f(x['parity_atm_dev'])} | "
          f"{_f(x['settle'])} | {_f(x['abs_move_pts'])} | {_f(x['pnl_usd'])} |")
    a("")
    e6 = ex["vi_p3_placebo_and_regimes"]
    a("### (vi) added after the audit: P3 placebo at other minutes, and P3 by NYSE regime")
    a("")
    a(f"Same construction (sign of a one-minute open-to-open change, then the next 9 bars) at {e6['n_placebo_minutes']} other "
      f"minutes 10:00..15:41: placebo median NW t {_f(e6['placebo_median_t'])}, share t > 2 {_f(e6['placebo_share_t_gt_2'], 3)}, "
      f"share t < -2 {_f(e6['placebo_share_t_lt_minus_2'], 3)}, max t {_f(e6['placebo_max_t'])}; P3 t {_f(e6['p3_nw_t'])} ranks "
      f"{e6['p3_rank_among_placebos_plus_p3']} of {e6['n_placebo_minutes'] + 1}. 2023-2026 only: P3 t {_f(e6['late_2023_2026']['p3_nw_t'])}, "
      f"placebo median t {_f(e6['late_2023_2026']['placebo_median_t'])}, share t > 2 {_f(e6['late_2023_2026']['placebo_share_t_gt_2'], 3)}, "
      f"P3 rank {e6['late_2023_2026']['p3_rank']}.")
    a("")
    a("| P3 period | n | mean bps | NW t |")
    a("|---|---|---|---|")
    for lab, x in e6["p3_by_nyse_regime"].items():
        a(f"| {lab} | {x['n']} | {_f(x['mean_bps'], 3)} | {_f(x['nw_t'])} |")
    a("")
    e7 = ex["vii_otm_multiples_10m_bars"]
    a(f"### (vii) added after the audit, not pre-registered: OTM 0DTE options from 10-minute bars ({e7['n_days']} days, {e7['n_options']} options)")
    a("")
    a("Entry = 15:40-bar close (~15:49:59); 'reach' = the 15:50-bar high (15:50:00-15:59:59) >= k x entry, an upper bound "
      "(a bar high is one print, and the last minute is included). Settlement multiple = intrinsic at the official close / entry.")
    a("")
    a("| series | n | mean entry | reach 2x (high) | reach 3x (high) | reach 5x (high) | settled >= 2x | settled at 0 | mean $ hold |")
    a("|---|---|---|---|---|---|---|---|---|")
    for k, x in e7["table"].items():
        a(f"| {k} | {x['n']} | {_f(x['mean_entry_mark'])} | {_f(x['share_reach_2x_bar_high'])} | {_f(x['share_reach_3x_bar_high'])} | "
          f"{_f(x['share_reach_5x_bar_high'])} | {_f(x['share_settle_ge_2x'])} | {_f(x['share_settle_zero'])} | {_f(x['mean_pnl_usd_hold'])} |")
    pz = e7["offsets_5_10_pooled"]
    a("")
    a(f"Pooled 5- and 10-point OTM (n {pz['n']}): reach 2x (bar high) {_f(pz['share_reach_2x_bar_high'])}, settled >= 2x "
      f"{_f(pz['share_settle_ge_2x'])}, settled at 0 {_f(pz['share_settle_zero'])}, mean hold P&L ${_f(pz['mean_pnl_usd_hold'])} per contract.")
    a("")
    a(f"Extra variants counted: {ex['count']['n_extra_variants']} "
      f"({'; '.join(ex['count']['requested_by_workflow'] + ex['count']['added_by_this_analysis'])}).")
    a("")
    return "\n".join(L)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _clean(o):
    if isinstance(o, dict):
        return {(k if isinstance(k, str) else str(k)): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def main() -> int:
    res = run()
    OUT_JSON.write_text(json.dumps(_clean(json.loads(json.dumps(res, default=_json_default))), indent=1))
    OUT_MD.write_text(write_md(res))
    print(f"wrote {OUT_JSON}\nwrote {OUT_MD}")
    for s, v in res["verdicts"].items():
        print(f"{s}: cond1={v['cond1']} cond2={v['cond2']} d2_days={v['d2_days']} mean_usd={v['d2_mean_usd_base']} -> {v['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
