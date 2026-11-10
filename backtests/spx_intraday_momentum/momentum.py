"""Market intraday momentum on D1 and the 15:50 candle trade (Part A, Part B, Part C).

Pre-registration: preregistration/spx_intraday_momentum.md, locked, SHA-256 fbe4ca60...cd76ecd, listed in
preregistration/LEDGER.md. Every command except `selftest` refuses to read data unless that file exists with that
hash and the hash is in the ledger.

  Part A  adapted replication of Gao-Han-Li-Zhou (2018) and Baltussen-Da-Lammers-Martens (2021) on D1,
          2013-04-01 .. 2026-10-20: r_last = a + b r_rod (primary, t >= 2.0), the trailing-volatility conditional
          (secondary, uncorrected) and descriptive tables.
  Part B  do momentum filters (R1-R4) improve the F2 15:50-candle ITM10 trade under strikes.py's model? Chosen on
          2013-04-01 .. 2020-12-31 (`discover`, frozen in partb_selection.json), tested once on 2021-01-01 ..
          2026-10-20 (`run`).
  Part C  a dealer net-gamma proxy (BDLM's formula) from OPRA open interest, Black-Scholes gamma with the prior
          day's VIX: C1 (momentum on short-gamma days) and C2 (the F2 trade on short-gamma days).

Commands (from /Users/kv15/trading):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_intraday_momentum/momentum.py selftest
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_intraday_momentum/momentum.py discover
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_intraday_momentum/momentum.py run
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_intraday_momentum/momentum.py partc

  selftest  synthetic data only (no D1, quote, open-interest or index file is read).
  discover  D1 2013-04-01 .. 2020-12-31 only (scan.load_panel stops at the first 2021 row). Writes
            partb_selection.json and partb_selection.sha256 once: it refuses if either exists, and nothing else
            writes them. The hashes of the plan, this file and strikes' results.json are recorded in it.
  run       checks the selection and the recorded hashes and the frozen pricing constants, then the reproduction
            check, then Part A and Part B's confirmation. Rebuilds results.json and RESULTS.md here.
  partc     repeats run's checks, then Part C's data checks (budget, format, the prior-day inputs; no gamma is
            computed before these pass; then coverage); adds its section to results.json and RESULTS.md and
            rebuilds data/spx_1549/nge_daily.csv, or reports "not run (reason)".

Reused read-only, loaded by path: backtests/spx_candle_scan/scan.py (panel, F2 signal, nw_mean_test),
backtests/spx_candle_strikes/strikes.py (pricing) and its results.json (constants), and
backtests/spx_candle_realprice/realprice.py (Cboe's official SPX closes, `partc` only).

D1 is a CFD's bid candles; the "16:00" price is the close of the 15:59 bar. Part B and Part C P&L comes from a model.
Research only; nothing here is a trading recommendation.
"""
from __future__ import annotations

import ast
import bisect
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from functools import lru_cache
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
PLAN = ROOT / "preregistration" / "spx_intraday_momentum.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
PLAN_SHA256 = "fbe4ca6028757b80d0e3b649610fd81e8aeca27c109be3ef7c554ccc3cd76ecd"
SCAN_PY = ROOT / "backtests" / "spx_candle_scan" / "scan.py"
CANDIDATES_JSON = ROOT / "backtests" / "spx_candle_scan" / "candidates.json"
STRIKES_PY = ROOT / "backtests" / "spx_candle_strikes" / "strikes.py"
STRIKES_JSON = ROOT / "backtests" / "spx_candle_strikes" / "results.json"
REALPRICE_PY = ROOT / "backtests" / "spx_candle_realprice" / "realprice.py"
OI_TOOL_PY = ROOT / "tools" / "databento_spx_oi.py"           # read as text by the selftest, never imported or run
SPX_ROOT = ROOT / "data" / "spx_1549"
OI_DIR = SPX_ROOT / "databento" / "statistics_oi_spx_spxw"
SPEND_LOG = SPX_ROOT / "databento" / "spend_log.csv"
CLOSES_CSV = SPX_ROOT / "spx_official_closes_cboe.csv"
NGE_CSV = SPX_ROOT / "nge_daily.csv"
VIX_DIR = ROOT / "data" / "cboe_indices"
SEL_JSON = "partb_selection.json"
SEL_SHA = "partb_selection.sha256"
OUT_JSON = "results.json"
OUT_MD = "RESULTS.md"
ET = ZoneInfo("America/New_York")

FULL = ("2013-04-01", "2026-10-20")
DISCOVERY = ("2013-04-01", "2020-12-31")
HALVES = (("2013-04-01", "2016-12-31"), ("2017-01-01", "2020-12-31"))
CONFIRMATION = ("2021-01-01", "2026-10-20")
PERIODS = {"2013-2020": DISCOVERY, "2021-2026": CONFIRMATION}

NW_LAG = 5                       # Bartlett lags 1..5, weights 1 - j/6
MIN_OBS = 30                     # fewer observations: "not estimable"
T_PART_A = 2.0                   # Part A primary and secondary: b > 0 (d > 0) with t >= 2.0
P_SELECT = 0.0125                # Part B selection: 5% Bonferroni over 4 rules, two-sided normal p
T_CONFIRM = 2.0                  # Part B confirmation: mean d > 0 with t >= 2.0
P_PART_C = 0.025                 # Part C: 5% Bonferroni over C1 and C2, two-sided normal p
TRAIL_N, TRAIL_MIN = 250, 100    # trailing windows for q_t (H_t) and m_t (R4)
Q_HIGH_VOL = 2.0 / 3.0
OOS_MIN = 500
WINSOR = (1, 99)
DAYS_PER_YEAR = 252

F2 = "F2_1m_1550_strong_body"
F2_DIRECTION = 1
OFFSET = 10                      # ITM10
HALF_SPREAD = 0.10
FEE, FEE_HIGH = 0.09, 0.74
K_D1 = 1.065101699231275
F_10 = 1.0046527466601545
SIGMA_C = 10.777818797750015
LEVEL = 7709.58
SIGMA_C_TOL = 1e-9
EXPECTED_TRADES = 644
EXPECTED_MEAN_A = 166.08169468395093
EXPECTED_MEAN_C = 157.91227664480985
REPRO_TOL = 0.01
RULES = ("R1", "R2", "R3", "R4")                   # the menu; R0 is the baseline, R5 is descriptive only
ALL_RULES = ("R0",) + RULES + ("R5",)
VERSIONS = ("a", "a74", "c", "idx")                # model (a) $0.09, (a) $0.74, model (c) $0.09, index s*y bps

OI_STAT = "9"
UNDEF_QTY = {2 ** 31 - 1, 2 ** 63 - 1}             # Databento's UNDEF_STAT_QUANTITY (int32 and int64 maxima)
CUTOFF_ET = "15:30"
PREV_CLOSE_ET = "16:00"
MIN_SPXW_CONTRACTS = 100
SPXW_CHECK_FROM = "2016-01-01"
COVERAGE_MIN = 0.95
BUDGET_USD = 100.0
MIN_DISCOVERY_DAYS = 100
# tools/databento_spx_oi.py's spend-log conventions (download_day / log_spend; checked against its source in selftest)
OI_PILLAR_LIVE = "2023-03-28"                      # before: one full-day window; from: pre-open, then the fallback
OI_SCHEMA_FULL_DAY = "statistics_oi_0000-2359"
OI_SCHEMA_PREOPEN = "statistics_oi_0000-0931"
OI_SCHEMA_FALLBACK = "statistics_oi_0931-1001"
OI_EMPTY_LABEL = "(no open interest in this window)"
TS_TENORS = (9.0, 30.0, 93.0)                      # VIX9D, VIX, VIX3M (calendar days)
YEAR_SECONDS = 365 * 86400

SELECTION_RULE = ("Eligible: mean d_k > 0 with two-sided normal p <= 0.0125 (variant (a), ITM10, $0.09, per-day "
                  "difference to R0 over the paired days, HAC lag 5, n >= 30), mean d_k > 0 in 2013-04-01..2016-12-31 "
                  "and in 2017-01-01..2020-12-31, and the index version's mean difference > 0. Pick: the eligible "
                  "rule with the highest t; a tie goes to the lower rule number. Menu: R1-R4.")

IMPLEMENTATION_CHOICES = [
    "Timing rules: a predictor x > 0 is long and x <= 0 short, as eta(x); a two-signal rule trades only when both "
    "give the same side, else it is flat (0). Hit rate = share of traded days with a positive return.",
    "R5 (descriptive): an added trade that cannot be priced in variant (a) is missing for R5 only; the paired days "
    "are set by R0 alone.",
    "Part C conflicts: two records with the same (ts_recv, sequence) and different quantities exclude the contract "
    "wherever they occur before the cutoff, not only at the last key. Identical duplicates are kept once.",
    "Part C quantities: empty = missing; 2147483647 and 9223372036854775807 (int32 and int64 maxima) = undefined "
    "sentinel; negative; or not an integer: each excludes the contract and is counted.",
    "Part C symbols: a root other than SPX or SPXW, or a strike of 0, counts as not parsing as an OSI code.",
    "Part C format check: 'distinct SPXW contracts with open interest' = SPXW contracts with a usable value "
    "before the 15:30 cutoff (after the last-record, conflict and quantity rules), median over day files in "
    "2016-01-01..2026-10-20.",
    "Part C budget check (check 2): momentum.py does not call Databento. The spend log must exist and the pull must "
    "be finished: every D1 day has a saved file, or its final window was logged by tools/databento_spx_oi.py as "
    "'(no open interest in this window)' (the full-day window before 2023-03-28; from then both the pre-open and "
    "the 09:31-10:01 fallback windows). Then the re-quoted remaining cost is $0 and the gate is the logged total "
    "(every schema) <= $100. An unfinished pull is 'not run (download incomplete)'.",
    "Part C order: budget, then format (parsing only), then the prior-day inputs (official closes, VIX, VIX9D, "
    "VIX3M files; a missing or malformed file is 'not run'), and only then gamma, then coverage.",
    "Part C hash check (check 5): a failure stops partc with an error and writes nothing.",
    "Part C descriptive Table-8 and puts-only forms use NGE* divided by its standard deviation on the regression "
    "sample (numerical scaling; the coefficient is per one standard deviation). The puts-only proxy "
    "-100 x sum(puts) gamma x OI is never positive, so it is reported in the Table-8 form.",
    "Part C term structure: tau = T x 365 calendar days; total variance sigma^2 x tau interpolated linearly between "
    "9, 30 and 93 days; sigma held flat outside.",
    "Part C t-1 for day t is the latest date in Cboe's SPX close file before t.",
]


# ------------------------------------------------------------------------------------------------
# modules, gate, hashes
# ------------------------------------------------------------------------------------------------
def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scan = load_module("spx_candle_scan_ro", SCAN_PY)
strikes = load_module("spx_candle_strikes_ro", STRIKES_PY)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_gate(prereg: Path = PLAN, ledger: Path = LEDGER) -> str:
    if not Path(prereg).exists():
        raise SystemExit(f"refusing to run: {prereg} does not exist")
    h = sha256_file(prereg)
    if h not in Path(ledger).read_text():
        raise SystemExit(f"refusing to run: SHA-256 of {Path(prereg).name} ({h}) is not in {ledger}")
    return h


def check_plan(prereg: Path, ledger: Path, expected: str = PLAN_SHA256) -> str:
    """check_gate, and the plan must be the locked version itself."""
    h = check_gate(prereg, ledger)
    if h != expected:
        raise SystemExit(f"refusing to run: {Path(prereg).name} has SHA-256 {h}, the locked plan is {expected}")
    return h


@dataclass
class Ctx:
    """Where everything lives. The commands use the defaults; the self-test points every path at a temp folder."""
    out_dir: Path = HERE
    plan: Path = PLAN
    ledger: Path = LEDGER
    plan_sha: str = PLAN_SHA256
    script: Path = SCRIPT
    strikes_json: Path = STRIKES_JSON
    d1_file: Path = scan.D1_FILE
    days_file: Path = scan.D1_DAYS
    oi_dir: Path = OI_DIR
    vix_dir: Path = VIX_DIR
    spend_log: Path = SPEND_LOG
    nge_csv: Path = NGE_CSV
    repro_expected: tuple = (EXPECTED_TRADES, EXPECTED_MEAN_A, EXPECTED_MEAN_C)
    sigma_c_recomputed: float | None = None     # None: recomputed from holdout.json the way strikes.py does
    closes_loader: object = None                # None: realprice.fetch_closes (Cboe file, downloaded once if absent)


def sigma_c_now(ctx: Ctx) -> float:
    if ctx.sigma_c_recomputed is not None:
        return ctx.sigma_c_recomputed
    return strikes.holdout_constants()["mean_abs_move"] / (2 * strikes.PHI0)


def check_constants(path: Path, sigma_c_recomputed: float) -> dict:
    """The frozen pricing constants read from strikes' results.json must equal the plan's values exactly, and
    sigma_c recomputed as strikes.py does must be within 1e-9 of the stored one."""
    rj = json.loads(Path(path).read_text())
    cal, p2 = rj["calibration"], rj["part2"]
    f = {o: float(cal["skew"][strikes.label(o)]["f"]) for o in strikes.OFFSETS}
    got = {"k_d1": cal["k_d1"], "f_10": cal["skew"][strikes.label(OFFSET)]["f"], "sigma_c": p2["sigma_c_pts"],
           "level": p2["level"]}
    want = {"k_d1": K_D1, "f_10": F_10, "sigma_c": SIGMA_C, "level": LEVEL}
    bad = [f"{k} {got[k]!r} != {want[k]!r}" for k in want if got[k] != want[k]]
    if bad:
        raise SystemExit("refusing to run: strikes results.json constants differ from the plan: " + "; ".join(bad))
    if not abs(sigma_c_recomputed - p2["sigma_c_pts"]) <= SIGMA_C_TOL:
        raise SystemExit(f"refusing to run: sigma_c recomputed {sigma_c_recomputed!r} differs from results.json "
                         f"{p2['sigma_c_pts']!r} by more than {SIGMA_C_TOL}")
    return {"k_d1": K_D1, "f": f, "f_10": F_10, "sigma_c": SIGMA_C, "level": LEVEL,
            "sigma_c_recomputed": float(sigma_c_recomputed)}


# ------------------------------------------------------------------------------------------------
# the selection file (written once by discover, verified by run and partc)
# ------------------------------------------------------------------------------------------------
def refuse_if_selection_exists(out_dir: Path) -> None:
    for name in (SEL_JSON, SEL_SHA):
        if (Path(out_dir) / name).exists():
            raise SystemExit(f"refusing to run: {Path(out_dir) / name} already exists; the selection is written "
                             "once and never rewritten")


def write_selection(out_dir: Path, payload: dict) -> str:
    """Exclusive create (never overwrites), then both files are made read-only."""
    out_dir = Path(out_dir)
    refuse_if_selection_exists(out_dir)
    b = (json.dumps(jsonable(payload), indent=1, allow_nan=False) + "\n").encode()
    h = hashlib.sha256(b).hexdigest()
    with open(out_dir / SEL_JSON, "xb") as fh:
        fh.write(b)
    with open(out_dir / SEL_SHA, "x") as fh:
        fh.write(f"{h}  {SEL_JSON}\n")
    for name in (SEL_JSON, SEL_SHA):
        os.chmod(out_dir / name, 0o444)
    return h


def verify_selection(ctx: Ctx) -> dict:
    """Confirmation step 1 (part 1): the selection matches its .sha256 and the plan, this script and strikes'
    results.json still have the hashes recorded in it."""
    pj, ps = Path(ctx.out_dir) / SEL_JSON, Path(ctx.out_dir) / SEL_SHA
    for p in (pj, ps):
        if not p.exists():
            raise SystemExit(f"refusing to run: {p} is missing (run `momentum.py discover` first)")
    expected = ps.read_text().split()[0].strip().lower()
    actual = sha256_file(pj)
    if actual != expected:
        raise SystemExit(f"refusing to run: {SEL_JSON} SHA-256 {actual} != frozen {expected}")
    sel = json.loads(pj.read_text())
    for key, path in (("plan_sha256", ctx.plan), ("momentum_py_sha256", ctx.script),
                      ("strikes_results_json_sha256", ctx.strikes_json)):
        now = sha256_file(path)
        if sel["hashes"][key] != now:
            raise SystemExit(f"refusing to run: {path} has SHA-256 {now}, the selection recorded "
                             f"{sel['hashes'][key]}")
    return sel


# ------------------------------------------------------------------------------------------------
# inference
# ------------------------------------------------------------------------------------------------
def two_sided_p(t: float) -> float:
    return float(math.erfc(abs(t) / math.sqrt(2.0)))


def ols_hac(y, regressors: dict, lag: int = NW_LAG) -> dict:
    """OLS with an intercept on the rows where y and every regressor are defined, in date order (a dropped row is
    skipped, so lags count retained rows). V = (X'X)^-1 S (X'X)^-1 with u_t = x_t e_t and
    S = sum u_t u_t' + sum_{j=1..lag} (1 - j/(lag+1)) sum_t (u_t u_{t-j}' + u_{t-j} u_t'), no finite-sample
    correction; t = b / sqrt(diag V), p = erfc(|t| / sqrt 2). Not estimable: n < 30, X rank-deficient, or a
    standard error not finite or not positive."""
    names = ["const"] + list(regressors)
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(y))] + [np.asarray(c, float) for c in regressors.values()])
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X = y[ok], X[ok]
    n, k = X.shape
    out = {"n": int(n), "estimable": False, "why": None, "coef": {}, "r2": None}
    if n < MIN_OBS:
        out["why"] = f"not estimable: fewer than {MIN_OBS} observations"
        return out
    if np.linalg.matrix_rank(X) < k:
        out["why"] = "not estimable: the regressors are rank-deficient"
        return out
    A = np.linalg.inv(X.T @ X)
    b = A @ (X.T @ y)
    e = y - X @ b
    U = X * e[:, None]
    S = U.T @ U
    for j in range(1, lag + 1):
        G = U[j:].T @ U[:-j]
        S += (1.0 - j / (lag + 1.0)) * (G + G.T)
    V = A @ S @ A
    with np.errstate(invalid="ignore"):
        se = np.sqrt(np.diag(V))
    if not (np.isfinite(se).all() and (se > 0).all()):
        out["why"] = "not estimable: a standard error is not finite or not positive"
        return out
    tss = float(np.sum((y - y.mean()) ** 2))
    out.update(estimable=True, r2=1.0 - float(e @ e) / tss if tss > 0 else None,
               coef={nm: {"b": float(b[i]), "se": float(se[i]), "t": float(b[i] / se[i]),
                          "p": two_sided_p(b[i] / se[i])} for i, nm in enumerate(names)})
    return out


def coef(res: dict, name: str):
    return res["coef"].get(name) if res.get("estimable") else None


def positive_with_t(res: dict, name: str, bar: float) -> bool:
    c = coef(res, name)
    return bool(c is not None and c["b"] > 0 and c["t"] >= bar)


def positive_with_p(res: dict, name: str, alpha: float) -> bool:
    c = coef(res, name)
    return bool(c is not None and c["b"] > 0 and c["p"] <= alpha)


def mean_test(y) -> dict:
    """scan.nw_mean_test plus the plan's 30-observation rule (and no t for se = 0)."""
    r = dict(scan.nw_mean_test(y))
    r["estimable"] = r["t"] is not None and r["n"] >= MIN_OBS
    r["why"] = None
    if not r["estimable"]:
        r["why"] = (f"not estimable: fewer than {MIN_OBS} observations" if r["n"] < MIN_OBS else
                    "not estimable: the standard error is zero or undefined")
        r["t"] = r["p"] = None
    return r


def mean_or_none(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x.mean()) if x.size else None


def share_positive(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.mean(x > 0)) if x.size else None


def in_period(dates, per) -> np.ndarray:
    d = np.asarray(dates).astype(str)
    return (d >= per[0]) & (d <= per[1])


def only(a, mask) -> np.ndarray:
    return np.where(mask, np.asarray(a, float), np.nan)


# ------------------------------------------------------------------------------------------------
# Part A
# ------------------------------------------------------------------------------------------------
def rv_first_half_hour(O) -> np.ndarray:
    """sqrt of the sum of squared ln(open[m+1] / open[m]) over the 30 steps 09:30 -> 10:00; NaN if any open is
    missing."""
    op = np.asarray(O, float)[:, :31]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(op[:, 1:] / op[:, :-1])
    return np.sqrt(np.sum(r * r, axis=1))


def day_vars(P) -> dict:
    """The plan's definitions (all log returns, times ET; "price at HH:MM" = the open of that bar; X = the close of
    the 15:59 bar; PC = P.prev_close, NaN after a session that is not a keep day)."""
    lr = scan.lr
    O, pc = P.O, P.prev_close
    p0930, p1000, p1500, p1530 = (O[:, scan.mi(h)] for h in ("09:30", "10:00", "15:00", "15:30"))
    S, X = O[:, scan.I1551], P.C[:, scan.I1559]
    with np.errstate(divide="ignore", invalid="ignore"):
        return {"r_first": lr(pc, p1000), "r_12": lr(p1500, p1530), "r_rod": lr(pc, p1530), "r_on": lr(pc, p0930),
                "r_day": lr(p0930, p1530), "r_last": lr(p1530, X), "y": lr(S, X),
                "rod_simple": p1530 / pc - 1.0, "last_simple": X / p1530 - 1.0, "rv_fh": rv_first_half_hour(O),
                "S": S, "X": X}


def trailing_quantile(x, q: float, window: int = TRAIL_N, min_n: int = TRAIL_MIN) -> np.ndarray:
    """For each day t: numpy.quantile (linear) of the last `window` defined values strictly before t; NaN when
    fewer than `min_n` exist."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    hist: list = []
    for i in range(len(x)):
        if len(hist) >= min_n:
            out[i] = np.quantile(np.array(hist[-window:]), q, method="linear")
        if np.isfinite(x[i]):
            hist.append(float(x[i]))
    return out


def high_vol_flag(rv, q) -> np.ndarray:
    """H_t = 1 if RV_fh(t) > q_t (strictly), 0 otherwise; NaN when either is undefined."""
    rv, q = np.asarray(rv, float), np.asarray(q, float)
    with np.errstate(invalid="ignore"):
        return np.where(np.isfinite(rv) & np.isfinite(q), (rv > q).astype(float), np.nan)


def side_one(x) -> np.ndarray:
    """eta(x): +1 (long) if x > 0, else -1; NaN when x is undefined."""
    x = np.asarray(x, float)
    with np.errstate(invalid="ignore"):
        return np.where(np.isfinite(x), np.where(x > 0, 1.0, -1.0), np.nan)


def side_two(a, b) -> np.ndarray:
    """The agreement rule: the common side when both eta sides agree, else 0 (flat); NaN when either is undefined."""
    sa, sb = side_one(a), side_one(b)
    return np.where(np.isfinite(sa) & np.isfinite(sb), np.where(sa == sb, sa, 0.0), np.nan)


def timing_stats(side, r_last) -> dict:
    side, r_last = np.asarray(side, float), np.asarray(r_last, float)
    ok = np.isfinite(side) & np.isfinite(r_last)
    ret, lng = (side * r_last)[ok] * 1e4, r_last[ok] * 1e4
    traded = side[ok] != 0
    t, tl = mean_test(ret), mean_test(lng)
    return {"days": int(ok.sum()), "days_traded": int(traded.sum()), "mean_bps_per_day": t["mean"], "nw_t": t["t"],
            "hit_rate": share_positive(ret[traded]),
            "annualised_bps": t["mean"] * DAYS_PER_YEAR if t["mean"] is not None else None,
            "always_long": {"mean_bps_per_day": tl["mean"], "nw_t": tl["t"], "hit_rate": share_positive(lng),
                            "annualised_bps": tl["mean"] * DAYS_PER_YEAR if tl["mean"] is not None else None}}


def oos_r2(y, x, min_train: int = OOS_MIN) -> dict:
    """BDLM's out-of-sample R^2: expanding-window OLS forecast (at least min_train days) against the historical mean,
    over the days where both are defined, in date order."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    if len(y) <= min_train:
        return {"n_predictions": 0, "r2_oos": None}
    sse_model = sse_mean = 0.0
    for t in range(min_train, len(y)):
        b1, b0 = np.polyfit(x[:t], y[:t], 1)
        sse_model += (y[t] - b0 - b1 * x[t]) ** 2
        sse_mean += (y[t] - y[:t].mean()) ** 2
    return {"n_predictions": int(len(y) - min_train), "r2_oos": 1.0 - sse_model / sse_mean if sse_mean > 0 else None}


def summary(res: dict, name: str, scale: float = 1.0) -> dict:
    """One coefficient of an ols_hac result, flattened for tables."""
    c = coef(res, name)
    return {"n": res["n"], "estimable": res["estimable"], "why": res["why"], "r2": res["r2"],
            "b": c["b"] * scale if c else None, "t": c["t"] if c else None, "p": c["p"] if c else None}


def part_a(dates, v: dict) -> dict:
    dates = np.asarray(dates).astype(str)
    years = np.array([d[:4] for d in dates])
    y, x = v["r_last"], v["r_rod"]

    prim = ols_hac(y, {"r_rod": x})
    replicates = positive_with_t(prim, "r_rod", T_PART_A)
    q = trailing_quantile(v["rv_fh"], Q_HIGH_VOL)
    H = high_vol_flag(v["rv_fh"], q)
    sec = ols_hac(y, {"r_rod": x, "H": H, "H_x_r_rod": H * x})
    stronger = positive_with_t(sec, "H_x_r_rod", T_PART_A)

    xs = x[np.isfinite(x)]
    lo, hi = np.percentile(xs, WINSOR) if xs.size else (np.nan, np.nan)
    desc = {
        "by_period": {name: summary(ols_hac(only(y, in_period(dates, per)), {"r_rod": x}), "r_rod", 100)
                      for name, per in PERIODS.items()},
        "by_year": {yr: summary(ols_hac(only(y, years == yr), {"r_rod": x}), "r_rod", 100)
                    for yr in sorted(set(years))},
        "simple_returns": summary(ols_hac(v["last_simple"], {"rod_simple": v["rod_simple"]}), "rod_simple", 100),
        "ghlz_r_first": summary(ols_hac(y, {"r_first": v["r_first"]}), "r_first", 100),
        "ghlz_r_12": summary(ols_hac(y, {"r_12": v["r_12"]}), "r_12", 100),
        "ghlz_both": ols_hac(y, {"r_first": v["r_first"], "r_12": v["r_12"]}),
        "decomposition_r_on_r_day": ols_hac(y, {"r_on": v["r_on"], "r_day": v["r_day"]}),
        "r2_in_sample": prim["r2"],
        "r2_out_of_sample": oos_r2(y, x),
        "timing": {"eta(r_rod)": timing_stats(side_one(x), y),
                   "eta(r_first)": timing_stats(side_one(v["r_first"]), y),
                   "eta(r_first, r_12)": timing_stats(side_two(v["r_first"], v["r_12"]), y),
                   "eta(r_first, r_rod)": timing_stats(side_two(v["r_first"], x), y)},
        "winsorised": {"r_rod_p1": float(lo), "r_rod_p99": float(hi),
                       **summary(ols_hac(y, {"r_rod": np.clip(x, lo, hi)}), "r_rod", 100)},
    }
    c = coef(prim, "r_rod")
    return {
        "n_days": int(len(dates)),
        "undefined_days": {k: int(np.sum(~np.isfinite(v[k])))
                           for k in ("r_first", "r_12", "r_rod", "r_on", "r_day", "r_last", "rv_fh")},
        "primary": {"regression": prim, "b_x100": c["b"] * 100 if c else None,
                    "criterion": "b > 0 with t >= 2.0 (the t-statistic decides)",
                    "verdict": "replicates on D1" if replicates else "did not replicate on D1 2013-2026"},
        "secondary": {"label": "secondary, uncorrected", "regression": sec,
                      "days_with_H": int(np.isfinite(H).sum()), "high_vol_days": int(np.nansum(H)),
                      "criterion": "d (H x r_rod) > 0 with t >= 2.0",
                      "verdict": ("stronger on high-volatility days (secondary, uncorrected)" if stronger else
                                  "not shown stronger on high-volatility days (secondary, uncorrected)")},
        "descriptive": desc,
    }


# ------------------------------------------------------------------------------------------------
# Part B
# ------------------------------------------------------------------------------------------------
def f2_signal(P) -> np.ndarray:
    """s = the F2 signal times its frozen direction (+1 in candidates.json)."""
    cands = json.loads(CANDIDATES_JSON.read_text())["candidates"]
    dirn = next(c["direction"] for c in cands if c["feature"] == F2)
    if dirn != F2_DIRECTION:
        raise SystemExit(f"frozen F2 direction {dirn} is not the registered +1")
    return dirn * np.asarray(scan.spec_by_id(F2).signal(P), float)


def rv_or_nan(closes) -> float:
    """strikes.py's rv input: realized_vol(...) or NaN (None below 300 returns, and an rv of exactly 0, become NaN)."""
    return strikes.realized_vol(closes)[0] or np.nan


def trade_values(S, X, d, rv, y, consts: dict) -> dict:
    """Per-day values of an ITM10 trade in direction d (+1 / -1; 0 = no trade): model (a) and (c) P&L at $0.09 and
    $0.74 from strikes.model_ladder (unchanged), NaN where the model's ok is False, and the index value d*y in bps."""
    S, X, d, rv, y = (np.asarray(a, float) for a in (S, X, d, rv, y))
    n = len(d)
    out = {k: np.full(n, np.nan) for k in ("a", "a74", "c", "c74", "idx")}
    out["ok"] = np.zeros(n, bool)
    with np.errstate(invalid="ignore"):
        sel = np.isfinite(d) & (d != 0) & np.isfinite(S) & np.isfinite(X)
    out["traded"] = sel
    if not sel.any():
        return out
    T = {"S": S[sel], "X": X[sel], "d": d[sel].astype(int), "rv": rv[sel]}
    L = consts["level"]
    sig_a = consts["k_d1"] * T["rv"] * strikes.SQRT_REMAINING * L
    la = strikes.model_ladder(T, L, sig_a, consts["f"], h=HALF_SPREAD, use_rounding=True)[OFFSET]
    lc = strikes.model_ladder(T, L, consts["sigma_c"], {o: 1.0 for o in strikes.OFFSETS}, h=HALF_SPREAD,
                              use_rounding=True)[OFFSET]
    out["a"][sel] = np.where(la["ok"], la["pnl_0.09"], np.nan)
    out["a74"][sel] = np.where(la["ok"], la["pnl_0.74"], np.nan)
    out["c"][sel] = np.where(lc["ok"], lc["pnl_0.09"], np.nan)
    out["c74"][sel] = np.where(lc["ok"], lc["pnl_0.74"], np.nan)
    out["ok"][sel] = la["ok"]
    out["idx"][sel] = T["d"] * y[sel] * 1e4
    return out


def rule_takes(s, r_rod, r_first, m, f2) -> dict:
    """Which F2 trades each rule takes. A component passes when its predictor is missing or exactly 0; R3 ANDs the
    two components; R4 takes the trade unless s*sign(r_rod) < 0 and |r_rod| >= m_t (and takes it when either is
    missing)."""
    s, r_rod, r_first, m = (np.asarray(a, float) for a in (s, r_rod, r_first, m))
    with np.errstate(invalid="ignore"):
        rod = ~np.isfinite(r_rod) | (r_rod == 0) | (s * np.sign(r_rod) > 0)
        first = ~np.isfinite(r_first) | (r_first == 0) | (s * np.sign(r_first) > 0)
        strong = np.isfinite(r_rod) & np.isfinite(m) & (s * np.sign(r_rod) < 0) & (np.abs(r_rod) >= m)
    return {"R0": f2.copy(), "R1": f2 & rod, "R2": f2 & first, "R3": f2 & rod & first, "R4": f2 & ~strong}


def partb_arrays(P, v: dict, consts: dict) -> dict:
    s = f2_signal(P)
    S, X, r_rod = v["S"], v["X"], v["r_rod"]
    f2 = np.isfinite(s) & (s != 0) & np.isfinite(S) & np.isfinite(X)
    rv = np.array([rv_or_nan(P.C[i, :scan.I1550 + 1]) for i in range(len(P.dates))], float)
    m = trailing_quantile(np.abs(r_rod), 0.5)
    with np.errstate(invalid="ignore"):
        add = ~f2 & np.isfinite(r_rod) & (r_rod != 0) & np.isfinite(S) & np.isfinite(X)
    return {"dates": np.asarray(P.dates).astype(str), "s": s, "f2": f2, "rv": rv, "m": m,
            "takes": rule_takes(s, r_rod, v["r_first"], m, f2), "add": add,
            "vals": trade_values(S, X, np.where(f2, s, 0.0), rv, v["y"], consts),
            "vals_add": trade_values(S, X, np.where(add, np.sign(r_rod), 0.0), rv, v["y"], consts)}


def tsum(r: dict) -> dict:
    return {k: r.get(k) for k in ("n", "mean", "se", "t", "p", "estimable", "why")}


def rule_table(pb: dict, mask) -> dict:
    """Every rule's per-day series over the paired days in `mask`: the trade's value on a day it trades, 0 on a day it
    does not. A day whose R0 trade is unpriceable in variant (a) is dropped from every rule. d = series - R0's."""
    f2, vals, va = pb["f2"], pb["vals"], pb["vals_add"]
    unpriceable = f2 & ~vals["ok"]
    m = np.asarray(mask, bool) & ~unpriceable
    base = {k: np.where(f2, vals[k], 0.0)[m] for k in VERSIONS}
    rows = {}
    for name in ALL_RULES:
        if name == "R5":
            take = f2 | pb["add"]
            tv = {k: np.where(f2, vals[k], va[k]) for k in VERSIONS}
        else:
            take, tv = pb["takes"][name], vals
        ser = {k: np.where(take, tv[k], 0.0)[m] for k in VERSIONS}
        kept, skipped = take[m], (f2 & ~take)[m]
        pa, pa74 = tv["a"][m], tv["a74"][m]
        per_day = mean_test(ser["a"])
        rows[name] = {
            "trades_kept": int(kept.sum()), "trades_skipped": int(skipped.sum()),
            "mean_pnl_kept": mean_or_none(pa[kept]), "mean_pnl_skipped": mean_or_none(pa[skipped]),
            "share_kept_profitable": share_positive(pa[kept]),
            "mean_per_day": per_day["mean"], "nw_t_per_day": per_day["t"],
            "mean_per_day_fee_0.74": mean_test(ser["a74"])["mean"], "mean_pnl_kept_fee_0.74": mean_or_none(pa74[kept]),
            "mean_per_day_c": mean_test(ser["c"])["mean"], "mean_per_day_idx_bps": mean_test(ser["idx"])["mean"],
            "d_a": tsum(mean_test(ser["a"] - base["a"])), "d_c": tsum(mean_test(ser["c"] - base["c"])),
            "d_idx": tsum(mean_test(ser["idx"] - base["idx"]))}
        if name == "R5":
            rows[name]["trades_added"] = int((pb["add"] & m).sum())
            rows[name]["added_unpriceable"] = int((pb["add"] & m & ~va["ok"]).sum())
    return {"days": int(m.sum()), "f2_trades": int((f2 & m).sum()),
            "unpriceable_r0_days_dropped": int((np.asarray(mask, bool) & unpriceable).sum()), "rules": rows}


def select_rule(full: dict, h1: dict, h2: dict):
    """Discovery: eligibility of R1-R4 and the pick (highest t; a tie goes to the lower rule number)."""
    elig = {}
    for k in RULES:
        d = full[k]["d_a"]
        m1, m2 = h1[k]["d_a"]["mean"], h2[k]["d_a"]["mean"]
        crit = {"mean_d_positive_p_le_0.0125": bool(d["estimable"] and d["mean"] > 0 and d["p"] <= P_SELECT),
                "both_halves_mean_d_positive": bool(m1 is not None and m1 > 0 and m2 is not None and m2 > 0),
                "index_mean_d_positive": bool(full[k]["d_idx"]["mean"] is not None and full[k]["d_idx"]["mean"] > 0)}
        elig[k] = {"criteria": crit, "eligible": all(crit.values()), "t": d["t"], "p": d["p"]}
    cands = [k for k in RULES if elig[k]["eligible"]]
    pick = max(cands, key=lambda k: (elig[k]["t"], -RULES.index(k))) if cands else None
    return pick, elig


def confirm(pick, conf_rules: dict) -> dict:
    if pick is None:
        return {"tested": False, "rule": None, "verdict": "no momentum rule improved F2 on 2013-2020",
                "note": "The confirmation test is not run; the 2021-2026 rows are not a test"}
    r = conf_rules[pick]
    crit = {"mean_d_a_positive_t_ge_2": bool(r["d_a"]["estimable"] and r["d_a"]["mean"] > 0
                                            and r["d_a"]["t"] >= T_CONFIRM),
            "mean_d_c_positive": bool(r["d_c"]["mean"] is not None and r["d_c"]["mean"] > 0),
            "mean_d_idx_positive": bool(r["d_idx"]["mean"] is not None and r["d_idx"]["mean"] > 0)}
    return {"tested": True, "rule": pick, "criteria": crit, "d_a": r["d_a"], "d_c": r["d_c"], "d_idx": r["d_idx"],
            "verdict": "adds to the F2 trade" if all(crit.values()) else "not confirmed"}


def repro_numbers(pb: dict) -> dict:
    tr = pb["f2"] & in_period(pb["dates"], CONFIRMATION)
    a, c = pb["vals"]["a"][tr], pb["vals"]["c"][tr]
    return {"trades": int(tr.sum()), "ok_trades_a": int(np.isfinite(a).sum()), "mean_a": mean_or_none(a),
            "mean_c": mean_or_none(c)}


def repro_check(num: dict, expected: tuple = (EXPECTED_TRADES, EXPECTED_MEAN_A, EXPECTED_MEAN_C),
                tol: float = REPRO_TOL) -> dict:
    n, ea, ec = expected
    fails = []
    if num["trades"] != n:
        fails.append(f"F2 trades {num['trades']} != {n}")
    for key, e, lab in (("mean_a", ea, "variant (a)"), ("mean_c", ec, "variant (c)")):
        x = num[key]
        if x is None or not math.isfinite(x) or not abs(x - e) <= tol:
            fails.append(f"{lab} mean ITM10 P&L {x} is not within ${tol} of {e}")
    return {**num, "expected": {"trades": n, "mean_a": ea, "mean_c": ec, "tol_usd": tol},
            "passed": not fails, "failures": fails}


def part_b_run(pb: dict, sel: dict, repro: dict) -> dict:
    out = {"pick": sel["pick"], "reproduction_check": repro}
    if not repro["passed"]:
        out["status"] = "pricing did not reproduce"
        return out
    tables = {name: rule_table(pb, in_period(pb["dates"], per)) for name, per in PERIODS.items()}
    pick = None if sel["pick"] == "none" else sel["pick"]
    out.update(status="run", confirmation=confirm(pick, tables["2021-2026"]["rules"]), tables=tables,
               label_2021_2026="the confirmation test" if pick else "not a test")
    frozen = sel["tables"]["full"]["rules"]
    out["discovery_recomputed_matches_frozen"] = all(
        (frozen[k]["d_a"]["mean"] is None and tables["2013-2020"]["rules"][k]["d_a"]["mean"] is None) or
        (frozen[k]["d_a"]["mean"] is not None and tables["2013-2020"]["rules"][k]["d_a"]["mean"] is not None and
         abs(frozen[k]["d_a"]["mean"] - tables["2013-2020"]["rules"][k]["d_a"]["mean"]) <= 1e-9)
        for k in ALL_RULES)
    return out


# ------------------------------------------------------------------------------------------------
# Part C: OSI codes, sessions, open interest, gamma
# ------------------------------------------------------------------------------------------------
@lru_cache(maxsize=500_000)
def parse_osi(sym: str):
    """'SPXW  261020C06700000' -> ('SPXW', '2026-10-20', True, 6700.0). ValueError if it is not an OSI code of the
    SPX or SPXW root."""
    if len(sym) != 21 or sym[12] not in "CP" or not re.fullmatch(r"[0-9]{6}", sym[6:12]) \
            or not re.fullmatch(r"[0-9]{8}", sym[13:21]):
        raise ValueError(f"not an OSI code: {sym!r}")
    root = sym[:6].rstrip(" ")
    if root not in ("SPX", "SPXW") or sym[:6] != root.ljust(6):
        raise ValueError(f"not an SPX or SPXW OSI code: {sym!r}")
    expiry = date(2000 + int(sym[6:8]), int(sym[8:10]), int(sym[10:12])).isoformat()   # ValueError on a bad date
    K = int(sym[13:21]) / 1000.0
    if not K > 0:
        raise ValueError(f"strike 0 in {sym!r}")
    return root, expiry, sym[12] == "C", K


def et_utc(day: str, hhmm: str) -> datetime:
    """HH:MM ET on `day`, as an aware UTC datetime (subtracting UTC datetimes gives the true elapsed time)."""
    h, m = map(int, hhmm.split(":"))
    return datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), h, m, tzinfo=ET).astimezone(timezone.utc)


def et_ns(day: str, hhmm: str) -> int:
    return int(et_utc(day, hhmm).timestamp()) * 10 ** 9


_SECONDS: dict = {}


def ts_ns(ts: str) -> int:
    """Databento pretty ts ('2026-10-20T10:30:00.557940498Z', UTC) -> integer nanoseconds."""
    if len(ts) < 20 or ts[-1] != "Z" or ts[10] != "T":
        raise ValueError(f"bad timestamp {ts!r}")
    head = ts[:19]
    sec = _SECONDS.get(head)
    if sec is None:
        sec = int(datetime.fromisoformat(head).replace(tzinfo=timezone.utc).timestamp())
        _SECONDS[head] = sec
    frac = ts[20:-1] if ts[19] == "." else ""
    if ts[19] not in ".Z" or (frac and not frac.isdigit()):
        raise ValueError(f"bad timestamp {ts!r}")
    return sec * 10 ** 9 + (int(frac.ljust(9, "0")[:9]) if frac else 0)


def prev_session(day: str, sessions: list):
    i = bisect.bisect_left(sessions, day)
    return sessions[i - 1] if i > 0 else None


def last_weekday_on_or_before(day: str) -> str:
    d = date.fromisoformat(day)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def spx_am_session(expiry: str, sessions: list) -> str:
    """The last NYSE session on or before the OSI date (Cboe's SPX close file is the calendar); beyond its end, the
    last weekday on or before the OSI date."""
    if not sessions or expiry > sessions[-1]:
        return last_weekday_on_or_before(expiry)
    i = bisect.bisect_right(sessions, expiry)
    return sessions[i - 1] if i > 0 else last_weekday_on_or_before(expiry)


def settlement(root: str, expiry: str, sessions: list) -> datetime:
    if root == "SPXW":
        return et_utc(expiry, "16:00")
    if root == "SPX":
        return et_utc(spx_am_session(expiry, sessions), "09:30")
    raise ValueError(root)


def parse_qty(raw: str):
    s = (raw or "").strip()
    if s == "":
        return ("missing", None)
    if not re.fullmatch(r"-?[0-9]+", s):
        return ("non_integer", s)
    q = int(s)
    if q in UNDEF_QTY:
        return ("sentinel", q)
    if q < 0:
        return ("negative", q)
    return ("ok", q)


def parse_oi(text: str, day: str):
    """Open interest per contract known before 15:30 ET on `day`: records with ts_recv < the cutoff; per contract the
    last record by (ts_recv, sequence); a conflict (same key, different quantities) or a bad quantity excludes the
    contract (counted, never 0). Returns (contracts [(symbol, root, expiry, is_call, K, oi)], counts, bad symbols)."""
    cut = et_ns(day, CUTOFF_ET)
    c, bad, recs = Counter(), [], {}
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    if header is None:
        return [], c, bad
    ix = {k: header.index(k) for k in ("ts_recv", "sequence", "stat_type", "quantity", "symbol")}
    for row in rd:
        if not row:
            continue
        c["records"] += 1
        if row[ix["stat_type"]] != OI_STAT:
            c["records_other_stat_type"] += 1
            continue
        c["oi_records"] += 1
        sym = row[ix["symbol"]]
        try:
            parts = parse_osi(sym)
        except ValueError:
            bad.append(sym)
            c["oi_records_bad_symbol"] += 1
            continue
        t = ts_ns(row[ix["ts_recv"]])
        if t >= cut:
            c["oi_records_at_or_after_cutoff"] += 1
            continue
        key = (t, int(row[ix["sequence"]]))
        recs.setdefault(sym, (parts, {}))[1].setdefault(key, set()).add(parse_qty(row[ix["quantity"]]))
    contracts = []
    for sym, (parts, by_key) in recs.items():
        if any(len(q) > 1 for q in by_key.values()):
            c["contracts_excluded_conflict"] += 1
            continue
        (status, q), = by_key[max(by_key)]
        if status != "ok":
            c[f"contracts_excluded_{status}"] += 1
            continue
        contracts.append((sym,) + parts + (q,))
    c["contracts_before_cutoff"] += len(recs)
    c["contracts_usable"] += len(contracts)
    return contracts, c, bad


def bs_gamma(S, K, sigma, T):
    """Black-Scholes gamma, r = q = 0: phi(d1) / (S sigma sqrt T), d1 = [ln(S/K) + sigma^2 T / 2] / (sigma sqrt T)."""
    S, K, sigma, T = np.broadcast_arrays(*(np.asarray(a, float) for a in (S, K, sigma, T)))
    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * sigma * sigma * T) / sq
    return np.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi) / (S * sq)


def ts_sigma(tau_days, v9: float, v30: float, v93: float):
    """Volatility by time to expiry from VIX9D, VIX and VIX3M (index points): linear in total variance between 9, 30
    and 93 days, flat beyond the ends."""
    ten = np.array(TS_TENORS)
    w = (np.array([v9, v30, v93], float) / 100.0) ** 2 * ten
    tau = np.clip(np.asarray(tau_days, float), ten[0], ten[-1])
    return np.sqrt(np.interp(tau, ten, w) / tau)


def nge_for_day(contracts: list, day: str, prev: str, S: float, vix: float, ts_vols, sessions: list,
                cache: dict) -> dict:
    """NGE*_t = 100 x (sum calls gamma x OI - sum puts gamma x OI) over the contracts settling at or after 15:30 ET
    on day t; S and sigma = VIX / 100 from t-1; T = elapsed time from 16:00 ET on t-1 to settlement, ACT/365."""
    cut, t0 = et_utc(day, CUTOFF_ET), et_utc(prev, PREV_CLOSE_ET)
    years = {}
    for key in {(c[1], c[2]) for c in contracts}:
        if key not in cache:
            cache[key] = settlement(key[0], key[1], sessions)
        st = cache[key]
        years[key] = (st - t0).total_seconds() / YEAR_SECONDS if st >= cut else None
    use = [c for c in contracts if years[(c[1], c[2])] is not None]
    out = {"contracts_used": len(use), "contracts_settled_before_cutoff": len(contracts) - len(use),
           "nge_star": np.nan, "nge_star_puts": np.nan, "nge_star_ts": np.nan}
    if not use:
        return out
    is_call = np.array([c[3] for c in use], bool)
    K = np.array([c[4] for c in use], float)
    q = np.array([c[5] for c in use], float)
    T = np.array([years[(c[1], c[2])] for c in use], float)
    sign = np.where(is_call, 1.0, -1.0)
    g = bs_gamma(S, K, vix / 100.0, T)
    out["nge_star"] = float(100.0 * np.sum(sign * g * q))
    out["nge_star_puts"] = float(-100.0 * np.sum(np.where(is_call, 0.0, g * q)))
    if ts_vols is not None:
        g_ts = bs_gamma(S, K, ts_sigma(T * 365.0, *ts_vols), T)
        out["nge_star_ts"] = float(100.0 * np.sum(sign * g_ts * q))
    return out


def load_index_csv(path: Path) -> dict:
    """{YYYY-MM-DD: CLOSE} from a Cboe index history file (DATE as MM/DD/YYYY). ValueError when the file is missing,
    has no DATE and CLOSE columns, has a DATE that does not parse, or has no usable close (Part C is then not run).
    A row whose CLOSE is empty or not a positive number is skipped: that day's input is missing (check 4)."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"{path.name} is missing")
    out = {}
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        if rd.fieldnames is None or not {"DATE", "CLOSE"} <= set(rd.fieldnames):
            raise ValueError(f"{path.name} has no DATE and CLOSE columns ({rd.fieldnames})")
        for r in rd:
            try:
                m, d, y = r["DATE"].split("/")
                day = date(int(y), int(m), int(d)).isoformat()
            except (AttributeError, TypeError, ValueError):
                raise ValueError(f"{path.name}: a DATE does not parse ({r.get('DATE')!r})") from None
            try:
                v = float(r["CLOSE"])
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v > 0:
                out[day] = v
    if not out:
        raise ValueError(f"{path.name} has no usable close")
    return out


def check_closes_dict(closes) -> dict:
    """The official closes must be a non-empty {YYYY-MM-DD: positive close}; ValueError otherwise."""
    if not isinstance(closes, dict) or not closes:
        raise ValueError("no official SPX closes")
    for k, val in closes.items():
        if not (isinstance(k, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", k)):
            raise ValueError(f"an official-close date is not YYYY-MM-DD: {k!r}")
        try:
            date.fromisoformat(k)                       # a real calendar date (rejects e.g. 2016-02-30)
        except ValueError:
            raise ValueError(f"an official-close date is not a calendar date: {k!r}") from None
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not val > 0:
            raise ValueError(f"the official close on {k} is not a positive number: {val!r}")
    return closes


def read_spend_log(path: Path) -> list:
    """The rows of the shared Databento spend log; ValueError if a column is missing or a cost is not a number."""
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        need = {"schema", "day", "quoted_cost_usd", "file"}
        if rd.fieldnames is None or not need <= set(rd.fieldnames):
            raise ValueError(f"columns {rd.fieldnames} lack {sorted(need)}")
        rows = list(rd)
    for r in rows:
        try:
            c = float(r["quoted_cost_usd"])
        except (TypeError, ValueError):
            raise ValueError(f"cost {r['quoted_cost_usd']!r} on {r['day']} is not a number") from None
        if not (math.isfinite(c) and c >= 0):
            raise ValueError(f"cost {c} on {r['day']} is not a non-negative number")
    return rows


def oi_day_finished(day: str, oi_dir: Path, empty: set) -> bool:
    """A day of the open-interest pull is finished when its file is saved, or when its final window was logged with
    no open interest: the full-day window before 2023-03-28; from then both the pre-open and the 09:31-10:01
    fallback windows (tools/databento_spx_oi.py tries the fallback only after an empty pre-open window)."""
    if (Path(oi_dir) / f"{day}.csv.gz").exists():
        return True
    if day < OI_PILLAR_LIVE:
        return (OI_SCHEMA_FULL_DAY, day) in empty
    return (OI_SCHEMA_PREOPEN, day) in empty and (OI_SCHEMA_FALLBACK, day) in empty


def budget_check(spend_log: Path, dates: list, oi_dir: Path) -> dict:
    """Check 2: the re-quoted cost of the full pull plus the logged spend must be <= $100. momentum.py does not call
    Databento, so the pull must be finished (then the re-quoted remaining cost is $0); an unfinished pull, a missing
    or unreadable spend log, or a logged total (every schema) over $100 fails the check."""
    out = {"spend_log": str(spend_log), "budget_usd": BUDGET_USD, "passed": False, "reason": None}
    if not Path(spend_log).exists():
        out["reason"] = "no spend log"
        return out
    try:
        rows = read_spend_log(spend_log)
    except (OSError, ValueError, csv.Error) as e:
        out["reason"] = f"spend log unreadable ({e})"
        return out
    empty = {(r["schema"], r["day"]) for r in rows if (r["file"] or "").startswith(OI_EMPTY_LABEL)}
    left = [d for d in dates if not oi_day_finished(d, oi_dir, empty)]
    total = sum(float(r["quoted_cost_usd"]) for r in rows)
    out.update(logged_usd=total, rows=len(rows),
               open_interest_usd=sum(float(r["quoted_cost_usd"]) for r in rows
                                     if (r["schema"] or "").startswith("statistics_oi")),
               d1_days=len(dates), days_not_downloaded=len(left), first_days_not_downloaded=left[:5],
               days_logged_without_open_interest=sum(1 for d in dates if not (Path(oi_dir) / f"{d}.csv.gz").exists()
                                                     and d not in left),
               requoted_remaining_usd=0.0 if not left else None)
    if left:
        out["reason"] = f"download incomplete: {len(left)} days not yet downloaded (first {left[0]})"
    elif total > BUDGET_USD + 1e-12:
        out["reason"] = f"logged spend ${total:.2f} + re-quoted remaining $0.00 > ${BUDGET_USD:.2f}"
    else:
        out["passed"] = True
    return out


def official_closes():
    rp = load_module("spx_candle_realprice_ro", REALPRICE_PY)
    return rp.fetch_closes(CLOSES_CSV)


def read_oi_file(f: Path, day: str):
    return parse_oi(gzip.decompress(Path(f).read_bytes()).decode(), day)


def scan_oi_files(oi_dir: Path, dates: list):
    """Check 1's pass over the open-interest files: parsing and the record rules only, no gamma. Returns the
    format-check inputs and the record and contract exclusion counts."""
    counts = Counter()
    fmt = {"files": 0, "files_without_oi_records": [], "unreadable_files": [], "bad_symbols": [],
           "spxw_contracts_by_day": {}}
    for day in dates:
        f = Path(oi_dir) / f"{day}.csv.gz"
        if not f.exists():
            counts["days_without_oi_file"] += 1
            continue
        fmt["files"] += 1
        try:
            contracts, c, bad = read_oi_file(f, day)
        except Exception as e:                                     # a broken file is a format failure, not a crash
            fmt["unreadable_files"].append(f"{day}: {type(e).__name__}: {e}")
            continue
        counts.update(c)
        if c["oi_records"] == 0:
            fmt["files_without_oi_records"].append(day)
        fmt["bad_symbols"].extend(f"{day}: {s!r}" for s in bad)
        if day >= SPXW_CHECK_FROM:
            fmt["spxw_contracts_by_day"][day] = sum(1 for x in contracts if x[1] == "SPXW")
    return fmt, counts


def nge_daily(oi_dir: Path, dates: list, closes: dict, vols: dict, fallback: set):
    """The gamma pass, run only after the format, budget and prior-day-input checks passed: per-day rows (N, NGE*
    and its variants) and the day-level counts."""
    sessions = sorted(closes)
    rows, counts, cache = [], Counter(), {}
    for day in dates:
        prev = prev_session(day, sessions)
        S = closes.get(prev) if prev else None
        vix = vols["VIX"].get(prev) if prev else None
        tv = [vols[k].get(prev) if prev else None for k in ("VIX9D", "VIX", "VIX3M")]
        r = {"date": day, "prev_session": prev, "spx_close_prev": S, "vix_close_prev": vix, "oi_file": False,
             "fallback_day": day in fallback, "contracts_usable": None, "contracts_used": None,
             "nge_star": np.nan, "nge_dollar": np.nan, "N": np.nan, "nge_star_puts": np.nan, "nge_star_ts": np.nan,
             "N_ts": np.nan}
        rows.append(r)
        f = Path(oi_dir) / f"{day}.csv.gz"
        if not f.exists():
            continue
        r["oi_file"] = True
        try:
            contracts, _, _ = read_oi_file(f, day)
        except Exception:                                          # passed the format pass; changed since
            counts["days_file_unreadable_in_gamma_pass"] += 1
            continue
        r["contracts_usable"] = len(contracts)
        if S is None or vix is None:
            counts["days_missing_prior_close_or_vix"] += 1
            continue
        g = nge_for_day(contracts, day, prev, S, vix, tuple(tv) if all(x is not None for x in tv) else None,
                        sessions, cache)
        counts["contracts_excluded_settled_before_cutoff"] += g["contracts_settled_before_cutoff"]
        r.update(contracts_used=g["contracts_used"], nge_star=g["nge_star"], nge_star_puts=g["nge_star_puts"],
                 nge_star_ts=g["nge_star_ts"])
        if math.isfinite(g["nge_star"]):
            r["nge_dollar"] = g["nge_star"] * S * S / 100.0
            r["N"] = 1.0 if g["nge_star"] < 0 else 0.0
        else:
            counts["days_no_contract_survives"] += 1
        if math.isfinite(g["nge_star_ts"]):
            r["N_ts"] = 1.0 if g["nge_star_ts"] < 0 else 0.0
    return rows, counts


def format_check(fmt: dict) -> dict:
    med = float(np.median(list(fmt["spxw_contracts_by_day"].values()))) if fmt["spxw_contracts_by_day"] else None
    reasons = []
    if fmt["unreadable_files"]:
        reasons.append(f"{len(fmt['unreadable_files'])} unreadable file(s), first {fmt['unreadable_files'][0]}")
    if fmt["files_without_oi_records"]:
        reasons.append(f"{len(fmt['files_without_oi_records'])} day file(s) without stat_type 9 records, first "
                       f"{fmt['files_without_oi_records'][0]}")
    if fmt["bad_symbols"]:
        reasons.append(f"{len(fmt['bad_symbols'])} symbol(s) do not parse as SPX/SPXW OSI codes, first "
                       f"{fmt['bad_symbols'][0]}")
    if med is None or med < MIN_SPXW_CONTRACTS:
        reasons.append(f"median distinct SPXW contracts with open interest in 2016-2026 is {med} "
                       f"(< {MIN_SPXW_CONTRACTS} or no file)")
    return {"files": fmt["files"], "median_spxw_contracts_2016_2026": med,
            "days_in_median": len(fmt["spxw_contracts_by_day"]),
            "passed": not reasons, "reason": "; ".join(reasons) or None}


def part_c_tests(dates, nd: dict, v: dict, pb: dict, sel: dict, repro: dict) -> dict:
    """C1, C2 and the descriptive tables, given the per-day N, NGE* and NGE*-variants arrays in `nd`."""
    dates = np.asarray(dates).astype(str)
    N, nge = nd["N"], nd["nge_star"]
    y, x = v["r_last"], v["r_rod"]
    c1 = ols_hac(y, {"r_rod": x, "N": N, "N_x_r_rod": N * x})
    out = {"C1": {"regression": c1, "criterion": "d (N x r_rod) > 0 with two-sided normal p <= 0.025",
                  "supported": positive_with_p(c1, "N_x_r_rod", P_PART_C)}}
    out["C1"]["verdict"] = ("momentum stronger when dealers are short gamma" if out["C1"]["supported"] else
                            "not supported")
    priced = pb["f2"] & np.isfinite(pb["vals"]["a"])
    pnl, idx = only(pb["vals"]["a"], priced), only(pb["vals"]["idx"], priced)
    if repro["passed"]:
        c2 = ols_hac(pnl, {"N": N})
        c2i = ols_hac(idx, {"N": N})
        guard = coef(c2i, "N") is not None and coef(c2i, "N")["b"] > 0
        sup = positive_with_p(c2, "N", P_PART_C) and guard
        out["C2"] = {"regression": c2, "index_regression": c2i, "index_guard_g_positive": bool(guard),
                     "criterion": "g > 0 with two-sided normal p <= 0.025, and g > 0 in the index version",
                     "supported": bool(sup),
                     "verdict": "the F2 trade is better on short-gamma days" if sup else "not supported"}
    else:
        out["C2"] = {"status": "pricing did not reproduce", "supported": False,
                     "verdict": "not run: pricing did not reproduce"}

    def sd_scaled(a, rows):
        a = np.asarray(a, float)
        s = np.nanstd(a[rows]) if np.isfinite(a[rows]).sum() > 1 else np.nan
        return a / s if s and math.isfinite(s) and s > 0 else np.full(len(a), np.nan), (float(s) if s else None)

    c1_rows = np.isfinite(y) & np.isfinite(x) & np.isfinite(N)
    z, z_sd = sd_scaled(nge, c1_rows)
    zp, zp_sd = sd_scaled(nd["nge_star_puts"], c1_rows)
    years = np.array([d[:4] for d in dates])
    both = np.isfinite(N) & np.isfinite(nd["N_ts"])
    desc = {
        "share_negative_gamma_by_year": {yr: {"days": int(np.isfinite(N[years == yr]).sum()),
                                              "share_N_1": mean_or_none(N[years == yr])}
                                         for yr in sorted(set(years))},
        "table7_slope_on_N1_days": summary(ols_hac(only(y, N == 1), {"r_rod": x}), "r_rod", 100),
        "table7_slope_on_N0_days": summary(ols_hac(only(y, N == 0), {"r_rod": x}), "r_rod", 100),
        "table8_nge_sd_scaled": {"nge_sd": z_sd, "regression": ols_hac(y, {"r_rod": x, "nge_z": z,
                                                                          "nge_z_x_r_rod": z * x})},
        "puts_only_sd_scaled": {"nge_puts_sd": zp_sd, "share_negative": share_positive(-nd["nge_star_puts"]),
                                "regression": ols_hac(y, {"r_rod": x, "nge_puts_z": zp, "nge_puts_z_x_r_rod": zp * x})},
        "term_structure": {"days_both": int(both.sum()),
                           "sign_agreement_with_vix": (float(np.mean(N[both] == nd["N_ts"][both])) if both.any()
                                                       else None),
                           "C1": summary(ols_hac(y, {"r_rod": x, "N": nd["N_ts"], "N_x_r_rod": nd["N_ts"] * x}),
                                         "N_x_r_rod"),
                           "C2": summary(ols_hac(pnl, {"N": nd["N_ts"]}), "N") if repro["passed"] else None},
        "by_period": {},
    }
    for name, per in PERIODS.items():
        m = in_period(dates, per)
        desc["by_period"][name] = {
            "C1": summary(ols_hac(only(y, m), {"r_rod": x, "N": N, "N_x_r_rod": N * x}), "N_x_r_rod"),
            "C2": summary(ols_hac(only(pnl, m), {"N": N}), "N") if repro["passed"] else None,
            "C2_index": summary(ols_hac(only(idx, m), {"N": N}), "N") if repro["passed"] else None}
    pick = None if sel["pick"] == "none" else sel["pick"]
    take = pb["takes"][pick] if pick else pb["takes"]["R0"]
    split = {}
    for n_val in (1.0, 0.0):
        on = priced & (N == n_val)
        split[f"N={int(n_val)}"] = {"kept": int((on & take).sum()), "mean_pnl_kept": mean_or_none(pnl[on & take]),
                                    "skipped": int((on & ~take).sum()),
                                    "mean_pnl_skipped": mean_or_none(pnl[on & ~take])}
    desc["f2_by_frozen_rule_and_N"] = {"rule": pick or "R0 (no rule was picked)", "split": split,
                                      "pricing_reproduced": repro["passed"]}
    out["descriptive"] = desc
    return out


def part_c(ctx: Ctx, P, v: dict, pb: dict, sel: dict, repro: dict) -> tuple[dict, list]:
    """The data checks, then the tests. Returns (section, nge rows); the rows are empty when Part C is not run."""
    dates = [str(d) for d in P.dates]
    checks: dict = {}
    fb_file = Path(ctx.oi_dir) / "fallback_days.txt"
    fallback = set(fb_file.read_text().split()) if fb_file.exists() else set()
    base = {"checks": checks, "fallback_days_in_panel": sum(1 for d in dates if d in fallback),
            "hashes_and_constants": "verified (as run's confirmation step 1)", "reproduction_check": repro}

    def not_run(name, label=None):
        return {"status": "not run", "reason": f"{label or name}: {checks[name]['reason']}", **base}, []

    # no gamma or NGE is computed until the budget, format and prior-day-input checks have passed
    checks["budget"] = budget_check(ctx.spend_log, dates, ctx.oi_dir)                 # check 2 (cheapest first)
    if not checks["budget"]["passed"]:
        return not_run("budget")
    fmt, counts = scan_oi_files(ctx.oi_dir, dates)                                     # check 1: parsing only
    base["counts"] = counts
    checks["format"] = format_check(fmt)
    if not checks["format"]["passed"]:
        return not_run("format")
    try:                                                                               # check 4's inputs
        closes, src = (ctx.closes_loader or official_closes)()
        check_closes_dict(closes)
        vols = {k: load_index_csv(Path(ctx.vix_dir) / f"{k}_History.csv") for k in ("VIX9D", "VIX", "VIX3M")}
    except (Exception, SystemExit) as e:
        checks["prior_day_inputs"] = {"passed": False, "reason": f"{type(e).__name__}: {e}"}
        return not_run("prior_day_inputs", "prior-day inputs")
    checks["prior_day_inputs"] = {"passed": True, "reason": None, "closes_source": src, "closes_days": len(closes),
                                  "index_days": {k: len(x) for k, x in vols.items()}}
    base["closes_source"] = src
    rows, gamma_counts = nge_daily(ctx.oi_dir, dates, closes, vols, fallback)          # the gamma pass
    counts.update(gamma_counts)
    N = np.array([r["N"] for r in rows], float)
    share = float(np.mean(np.isfinite(N))) if len(N) else 0.0
    checks["coverage"] = {"d1_days": len(dates), "days_with_N": int(np.isfinite(N).sum()), "share": share,
                          "required": COVERAGE_MIN, "passed": share >= COVERAGE_MIN,
                          "reason": None if share >= COVERAGE_MIN else
                          f"N_t computable on {np.isfinite(N).sum()} of {len(dates)} D1 days ({share:.1%} < 95%)"}
    if not checks["coverage"]["passed"]:                                               # check 3
        return not_run("coverage")
    nd = {k: np.array([r[k] for r in rows], float) for k in ("N", "nge_star", "nge_star_puts", "nge_star_ts", "N_ts")}
    return {"status": "run", **base, **part_c_tests(dates, nd, v, pb, sel, repro)}, rows


# ------------------------------------------------------------------------------------------------
# rendering and outputs
# ------------------------------------------------------------------------------------------------
TEXT_RULES = [
    "D1 is the Dukascopy US500 CFD's one-minute **bid candles**, not the index. The \"16:00\" price is the close of "
    "the 15:59 bar, **not the official settlement**.",
    "Part A is an **adapted replication** of Gao-Han-Li-Zhou (2018) and Baltussen-Da-Lammers-Martens (2021): log "
    "returns, a CFD, the 15:59 close, the prior close as the anchor.",
    "2013-2020 lies **inside BDLM's sample** (to May 2020), on a different instrument; only 2021-2026 is out of "
    "sample for both papers.",
    "**2021-2026 was not blind for related momentum signals**: the 09:30-anchored day-so-far signal (P1, "
    "F4_day_so_far) is known to have failed on 2021-2026, and the 15:30-16:00 target contains the 15:49-15:59 "
    "target studied before.",
    "Part B's discovery is **retrospective, model-priced selection**: 2013-2020 trades are priced with constants "
    "calibrated on 2026 quotes. **Part B and Part C P&L comes from a model** (strikes.py), not from real prices.",
    "Nothing here is a trading recommendation.",
]


def fm(x, nd=2, sign=False, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if pct:
        return f"{x * 100:.1f}%"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


def reg_line(r: dict, name: str, scale: float = 1.0) -> str:
    c = r["coef"].get(name) if r.get("estimable") else None
    if not c:
        return f"n {r['n']}, {r.get('why') or 'not estimable'}"
    return f"{fm(c['b'] * scale, 3, True)} (t {fm(c['t'])}, p {fm(c['p'], 4)}), n {r['n']}, R² {fm(r['r2'], 4)}"


def render_md(res: dict) -> str:
    L = []
    w = L.append
    w("# Intraday momentum on D1 and the 15:50 candle trade")
    w("")
    w(f"Rebuilt by `backtests/spx_intraday_momentum/momentum.py` from the locked plan "
      f"`preregistration/spx_intraday_momentum.md` (SHA-256 `{str(res.get('plan_sha256', ''))[:16]}...`); do not edit "
      "by hand. Research only.")
    w("")
    for t in TEXT_RULES:
        w(f"- {t}")
    w("")
    a = res.get("part_a")
    if a:
        p = a["primary"]
        w("## Part A: adapted replication on D1, 2013-04-01 .. 2026-10-20")
        w("")
        w(f"**Primary (r_last on r_rod): {p['verdict']}.** Slope x100 {reg_line(p['regression'], 'r_rod', 100)}. "
          f"Criterion: {p['criterion']}. BDLM's ES value is about 6.2.")
        w("")
        s = a["secondary"]
        w(f"**Secondary: {s['verdict']}.** d (H x r_rod) {reg_line(s['regression'], 'H_x_r_rod')}; "
          f"{s['days_with_H']} days with H defined, {s['high_vol_days']} high-volatility days.")
        w("")
        d = a["descriptive"]
        w("Descriptive (no verdicts). Slopes x100:")
        w("")
        w("| Sample | n | Slope x100 | t | p | R² |")
        w("|---|---|---|---|---|---|")
        rows = [(f"r_rod, {k}", v) for k, v in d["by_period"].items()] + \
               [(f"r_rod, {k}", v) for k, v in d["by_year"].items()] + \
               [("simple returns", d["simple_returns"]), ("winsorised r_rod (p1-p99)", d["winsorised"]),
                ("GHLZ r_first", d["ghlz_r_first"]), ("GHLZ r_12", d["ghlz_r_12"])]
        for name, v in rows:
            w(f"| {name} | {v['n']} | {fm(v['b'], 3, True)} | {fm(v['t'])} | {fm(v['p'], 4)} | {fm(v['r2'], 4)} |")
        w("")
        for key, label, names in (("ghlz_both", "GHLZ, both", ("r_first", "r_12")),
                                  ("decomposition_r_on_r_day", "Decomposition", ("r_on", "r_day"))):
            r = d[key]
            w(f"- {label}: " + "; ".join(f"{nm} x100 {reg_line(r, nm, 100)}" for nm in names) + ".")
        o = d["r2_out_of_sample"]
        w(f"- R² in sample {fm(d['r2_in_sample'], 4)}; out of sample (expanding, >= {OOS_MIN} days, vs the historical "
          f"mean) {fm(o['r2_oos'], 4)} over {o['n_predictions']} forecasts.")
        w("")
        w("Timing returns (bps a day; flat days count 0) against always-long on the same days:")
        w("")
        w("| Rule | Days | Traded | Mean bps | NW t | Hit | Annualised bps | Long mean | Long t | Long hit |")
        w("|---|---|---|---|---|---|---|---|---|---|")
        for k, t in d["timing"].items():
            lg = t["always_long"]
            w(f"| {k} | {t['days']} | {t['days_traded']} | {fm(t['mean_bps_per_day'], 2, True)} | {fm(t['nw_t'])} | "
              f"{fm(t['hit_rate'], pct=True)} | {fm(t['annualised_bps'], 0, True)} | "
              f"{fm(lg['mean_bps_per_day'], 2, True)} "
              f"| {fm(lg['nw_t'])} | {fm(lg['hit_rate'], pct=True)} |")
        w("")
        w("Days on which a quantity is undefined (they leave only the tests that need it): " +
          ", ".join(f"{k} {n}" for k, n in a["undefined_days"].items()) + f" (of {a['n_days']}).")
        w("")
    b = res.get("part_b")
    sel = res.get("selection")
    if b:
        w("## Part B: does momentum add to the F2 trade? (model P&L, ITM10, $0.09)")
        w("")
        if sel:
            w(f"**Discovery 2013-04-01 .. 2020-12-31 (frozen in `{SEL_JSON}`): pick = {sel['pick']}.** "
              f"{SELECTION_RULE}")
            w("")
            w("| Rule | Kept | Skipped | Mean kept | Mean skipped | Mean d $/day | t | p | 2013-16 d | 2017-20 d | "
              "Index d bps | Eligible |")
            w("|---|---|---|---|---|---|---|---|---|---|---|---|")
            for k in ALL_RULES:
                f, h1, h2 = (sel["tables"][x]["rules"][k] for x in ("full", "half1", "half2"))
                el = sel["eligibility"].get(k, {}).get("eligible")
                w(f"| {k} | {f['trades_kept']} | {f['trades_skipped']} | {fm(f['mean_pnl_kept'], 2, True)} | "
                  f"{fm(f['mean_pnl_skipped'], 2, True)} | {fm(f['d_a']['mean'], 2, True)} | {fm(f['d_a']['t'])} | "
                  f"{fm(f['d_a']['p'], 4)} | {fm(h1['d_a']['mean'], 2, True)} | {fm(h2['d_a']['mean'], 2, True)} | "
                  f"{fm(f['d_idx']['mean'], 3, True)} | {'—' if el is None else ('yes' if el else 'no')} |")
            w("")
        rc = b["reproduction_check"]
        w(f"**Reproduction check (2021-2026): {'passed' if rc['passed'] else 'FAILED'}.** F2 trades {rc['trades']} "
          f"(expected {rc['expected']['trades']}); variant (a) mean {fm(rc['mean_a'], 4)} (expected "
          f"{rc['expected']['mean_a']}); variant (c) mean {fm(rc['mean_c'], 4)} (expected {rc['expected']['mean_c']}).")
        w("")
        if b["status"] != "run":
            w(f"**Part B: {b['status']}.** Any fix and re-selection would be a labelled deviation needing a new "
              "locked addendum.")
            w("")
        else:
            c = b["confirmation"]
            w(f"**Confirmation 2021-01-01 .. 2026-10-20: {c['verdict']}.**" +
              (f" Rule {c['rule']}: mean d {fm(c['d_a']['mean'], 2, True)} a day (t {fm(c['d_a']['t'])}); variant (c) "
               f"{fm(c['d_c']['mean'], 2, True)}; index {fm(c['d_idx']['mean'], 3, True)} bps." if c["tested"] else
               " " + c["note"] + "."))
            w("")
            for per, tab in b["tables"].items():
                lab = f" ({b['label_2021_2026']})" if per == "2021-2026" else ""
                w(f"Descriptive, {per}{lab}: {tab['days']} paired days, {tab['f2_trades']} F2 trades, "
                  f"{tab['unpriceable_r0_days_dropped']} unpriceable R0 days dropped.")
                w("")
                w("| Rule | Kept | Skipped | Mean kept | Mean skipped | Kept profitable | $/day | t | $/day at $0.74 | "
                  "d $/day | d t | d (c) | d index bps |")
                w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
                for k, r in tab["rules"].items():
                    w(f"| {k} | {r['trades_kept']} | {r['trades_skipped']} | {fm(r['mean_pnl_kept'], 2, True)} | "
                      f"{fm(r['mean_pnl_skipped'], 2, True)} | {fm(r['share_kept_profitable'], pct=True)} | "
                      f"{fm(r['mean_per_day'], 2, True)} | {fm(r['nw_t_per_day'])} | "
                      f"{fm(r['mean_per_day_fee_0.74'], 2, True)} | {fm(r['d_a']['mean'], 2, True)} | "
                      f"{fm(r['d_a']['t'])} | {fm(r['d_c']['mean'], 2, True)} | {fm(r['d_idx']['mean'], 3, True)} |")
                w("")
            w("R5 (add sign(r_rod) trades on non-F2 days) is reported but cannot be picked.")
            w("")
    c = res.get("part_c")
    if c:
        w("## Part C: dealer gamma (net gamma proxy from OPRA open interest)")
        w("")
        if c["status"] != "run":
            w(f"**Part C not run ({c['reason']}).**")
        else:
            w(f"**C1: {c['C1']['verdict']}.** d (N x r_rod) {reg_line(c['C1']['regression'], 'N_x_r_rod')}.")
            w("")
            c2 = c["C2"]
            if "regression" in c2:
                w(f"**C2: {c2['verdict']}.** g {reg_line(c2['regression'], 'N')}; index version g "
                  f"{reg_line(c2['index_regression'], 'N')}.")
            else:
                w(f"**C2: {c2['verdict']}.**")
            w("")
            dsc = c["descriptive"]
            w("Share of negative-gamma days (N = 1) by year: " + ", ".join(
                f"{y} {fm(v['share_N_1'], pct=True)} ({v['days']})"
                for y, v in dsc["share_negative_gamma_by_year"].items()) + ".")
            w("")
            for k in ("table7_slope_on_N1_days", "table7_slope_on_N0_days"):
                v = dsc[k]
                w(f"- {k.replace('_', ' ')}: slope x100 {fm(v['b'], 3, True)} (t {fm(v['t'])}), n {v['n']}.")
            t8 = dsc["table8_nge_sd_scaled"]
            w(f"- Table 8 form (NGE* per standard deviation {fm(t8['nge_sd'], 0)}): interaction "
              f"{reg_line(t8['regression'], 'nge_z_x_r_rod')}.")
            po = dsc["puts_only_sd_scaled"]
            w(f"- Puts only: interaction {reg_line(po['regression'], 'nge_puts_z_x_r_rod')}.")
            ts = dsc["term_structure"]
            w(f"- Term structure (VIX9D/VIX/VIX3M): sign agrees with the VIX version on "
              f"{fm(ts['sign_agreement_with_vix'], pct=True)} of {ts['days_both']} days; C1 d "
              f"{fm(ts['C1']['b'], 3, True)} "
              f"(t {fm(ts['C1']['t'])}).")
            for per, v in dsc["by_period"].items():
                w(f"- {per}: C1 d {fm(v['C1']['b'], 3, True)} (t {fm(v['C1']['t'])}, n {v['C1']['n']})" +
                  (f"; C2 g {fm(v['C2']['b'], 2, True)} (t {fm(v['C2']['t'])}, n {v['C2']['n']})" if v["C2"] else "")
                  + ".")
            sp = dsc["f2_by_frozen_rule_and_N"]
            w(f"- F2 trades by Part B's frozen rule ({sp['rule']}) and N: " + "; ".join(
                f"{k}: kept {v['kept']} ({fm(v['mean_pnl_kept'], 2, True)}), skipped {v['skipped']} "
                f"({fm(v['mean_pnl_skipped'], 2, True)})" for k, v in sp["split"].items()) + ".")
        ch = c["checks"]
        parts = []
        if "format" in ch:
            parts.append(f"format {'passed' if ch['format']['passed'] else 'FAILED'} ({ch['format']['files']} files, "
                         f"median SPXW contracts {fm(ch['format']['median_spxw_contracts_2016_2026'], 0)})")
        if "budget" in ch:
            bc = ch["budget"]
            parts.append(f"budget {'passed' if bc['passed'] else 'FAILED'} (logged ${fm(bc.get('logged_usd'))}, open "
                         f"interest ${fm(bc.get('open_interest_usd'))}, days not yet downloaded "
                         f"{bc.get('days_not_downloaded', '—')}, days logged without open interest "
                         f"{bc.get('days_logged_without_open_interest', '—')})")
        if "prior_day_inputs" in ch:
            parts.append(f"prior-day inputs {'passed' if ch['prior_day_inputs']['passed'] else 'FAILED'}")
        if "coverage" in ch:
            parts.append(f"coverage {'passed' if ch['coverage']['passed'] else 'FAILED'} "
                         f"({ch['coverage']['days_with_N']} of {ch['coverage']['d1_days']} days, "
                         f"{fm(ch['coverage']['share'], pct=True)})")
        w("")
        w("Data checks: " + "; ".join(parts) + "." +
          (f" Days on the 09:31-10:01 fallback: {c['fallback_days_in_panel']}." if "fallback_days_in_panel" in c
           else ""))
        w("")
        if c.get("counts"):
            w("Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(c["counts"].items())) + ".")
            w("")
        w("Caveats: the positioning (dealers long all calls, short all puts) is assumed, not observed; open interest "
          "misses positions opened and closed the same day, most 0DTE trading since 2022; one VIX volatility ignores "
          "the skew and the term structure.")
        w("")
    w("## Implementation choices where the plan left room")
    w("")
    for t in IMPLEMENTATION_CHOICES:
        w(f"- {t}")
    return "\n".join(L) + "\n"


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
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


def write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def write_outputs(ctx: Ctx, res: dict) -> None:
    clean = jsonable(res)
    write_atomic(Path(ctx.out_dir) / OUT_JSON, json.dumps(clean, indent=1, allow_nan=False) + "\n")
    write_atomic(Path(ctx.out_dir) / OUT_MD, render_md(clean))


NGE_COLUMNS = ["date", "prev_session", "spx_close_prev", "vix_close_prev", "oi_file", "fallback_day",
               "contracts_usable", "contracts_used", "nge_star", "nge_dollar", "N", "nge_star_puts", "nge_star_ts",
               "N_ts"]


def write_nge_csv(path: Path, rows: list) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=NGE_COLUMNS, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r[k] is None or (isinstance(r[k], float) and not math.isfinite(r[k])) else
                        (repr(r[k]) if isinstance(r[k], float) else r[k])) for k in NGE_COLUMNS})
    write_atomic(path, buf.getvalue())


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------
def assert_discovery_only(P) -> None:
    dates = np.asarray(P.dates).astype(str)
    stop = P.meta.get("stopped_at_first_row_dated")
    if (dates > DISCOVERY[1]).any() or (dates < DISCOVERY[0]).any() or (stop is not None and stop <= DISCOVERY[1]):
        raise SystemExit(f"refusing to continue: a date outside {DISCOVERY} reached discovery")


def discover(ctx: Ctx | None = None) -> dict:
    ctx = ctx or Ctx()
    plan_sha = check_plan(ctx.plan, ctx.ledger, ctx.plan_sha)
    refuse_if_selection_exists(ctx.out_dir)                       # before any data is read
    hashes = {"plan_sha256": plan_sha, "momentum_py_sha256": sha256_file(ctx.script),
              "strikes_results_json_sha256": sha256_file(ctx.strikes_json)}
    consts = check_constants(ctx.strikes_json, sigma_c_now(ctx))
    P = scan.load_panel(DISCOVERY[0], DISCOVERY[1], ctx.d1_file, ctx.days_file)
    assert_discovery_only(P)
    if len(P.dates) < MIN_DISCOVERY_DAYS:
        raise SystemExit(f"refusing to freeze: the discovery sample has {len(P.dates)} days (< {MIN_DISCOVERY_DAYS}); "
                         "no selection was written")
    v = day_vars(P)
    pb = partb_arrays(P, v, consts)
    tabs = {"full": rule_table(pb, in_period(pb["dates"], DISCOVERY))}
    for name, per in zip(("half1", "half2"), HALVES):
        tabs[name] = rule_table(pb, in_period(pb["dates"], per))
    pick, elig = select_rule(tabs["full"]["rules"], tabs["half1"]["rules"], tabs["half2"]["rules"])
    payload = {
        "what": "Part B's frozen selection (preregistration/spx_intraday_momentum.md). Written once by "
                "`momentum.py discover` from D1 2013-04-01 .. 2020-12-31 only; never rewritten.",
        "hashes": hashes,
        "files": {"plan": str(ctx.plan), "momentum_py": str(ctx.script), "strikes_results_json": str(ctx.strikes_json)},
        "frozen_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "discovery_window": list(DISCOVERY), "halves": [list(h) for h in HALVES],
        "discovery_sample": {"first": str(pb["dates"][0]) if len(pb["dates"]) else None,
                             "last": str(pb["dates"][-1]) if len(pb["dates"]) else None,
                             "n_days": int(len(pb["dates"])),
                             "loader_stopped_at_first_row_dated": P.meta.get("stopped_at_first_row_dated")},
        "constants": {k: consts[k] for k in ("k_d1", "f_10", "sigma_c", "level", "sigma_c_recomputed")},
        "selection_rule": SELECTION_RULE,
        "implementation_choices": IMPLEMENTATION_CHOICES,
        "tables": tabs, "eligibility": elig, "pick": pick or "none",
    }
    write_selection(ctx.out_dir, payload)
    return payload


def load_all(ctx: Ctx):
    """run and partc: the gate, the selection and recorded hashes, the constants, then the full panel."""
    plan_sha = check_plan(ctx.plan, ctx.ledger, ctx.plan_sha)
    sel = verify_selection(ctx)
    consts = check_constants(ctx.strikes_json, sigma_c_now(ctx))
    P = scan.load_panel(FULL[0], FULL[1], ctx.d1_file, ctx.days_file)
    if len(P.dates) == 0:
        raise SystemExit(f"refusing to run: the D1 panel {FULL[0]} .. {FULL[1]} has no days")
    for name, per in PERIODS.items():
        if not in_period(P.dates, per).any():
            raise SystemExit(f"refusing to run: the {name} sample ({per[0]} .. {per[1]}) of the D1 panel has no days")
    v = day_vars(P)
    pb = partb_arrays(P, v, consts)
    repro = repro_check(repro_numbers(pb), ctx.repro_expected)        # an empty 2021-2026 sample fails it (0 trades)
    return plan_sha, sel, consts, P, v, pb, repro


def run(ctx: Ctx | None = None) -> dict:
    ctx = ctx or Ctx()
    plan_sha, sel, consts, P, v, pb, repro = load_all(ctx)
    res = {"what": "Intraday momentum study (preregistration/spx_intraday_momentum.md): Part A and Part B",
           "plan_sha256": plan_sha, "selection_sha256": sha256_file(Path(ctx.out_dir) / SEL_JSON),
           "momentum_py_sha256": sha256_file(ctx.script), "constants": {k: consts[k] for k in
                                                                       ("k_d1", "f_10", "sigma_c", "level")},
           "data": {"d1_days": int(len(P.dates)), "first": str(P.dates[0]) if len(P.dates) else None,
                    "last": str(P.dates[-1]) if len(P.dates) else None,
                    "days_by_period": {k: int(in_period(P.dates, per).sum()) for k, per in PERIODS.items()},
                    "days_without_prior_close": int(np.sum(~np.isfinite(P.prev_close)))},
           "selection": sel,
           "part_a": part_a(P.dates, v),
           "part_b": part_b_run(pb, sel, repro),
           "implementation_choices": IMPLEMENTATION_CHOICES}
    write_outputs(ctx, res)
    return res


def partc(ctx: Ctx | None = None) -> dict:
    ctx = ctx or Ctx()
    plan_sha, sel, consts, P, v, pb, repro = load_all(ctx)          # check 5: as run's confirmation step 1
    section, rows = part_c(ctx, P, v, pb, sel, repro)
    out_json = Path(ctx.out_dir) / OUT_JSON
    res = json.loads(out_json.read_text()) if out_json.exists() else {"plan_sha256": plan_sha}
    res["part_c"] = section
    write_outputs(ctx, res)
    if section["status"] == "run":
        write_nge_csv(ctx.nge_csv, rows)
    return res


# ------------------------------------------------------------------------------------------------
# self-test (synthetic data only)
# ------------------------------------------------------------------------------------------------
def _raises(fn, *args, **kw) -> str:
    try:
        fn(*args, **kw)
    except SystemExit as e:
        return str(e)
    raise AssertionError(f"{getattr(fn, '__name__', fn)} did not refuse")


def _value_error(fn, *args) -> str:
    try:
        fn(*args)
    except ValueError as e:
        return str(e)
    raise AssertionError(f"{getattr(fn, '__name__', fn)} accepted {args!r}")


def _st_inference() -> str:
    rng = np.random.default_rng(1)
    e = rng.normal(0, 1, 600)
    y = 0.15 + e + 0.5 * np.concatenate([[0.0], e[:-1]])           # autocorrelated
    r, nw = ols_hac(y, {}), scan.nw_mean_test(y)
    c = r["coef"]["const"]
    assert abs(c["b"] - nw["mean"]) < 1e-12 and abs(c["se"] - nw["se"]) < 1e-12 and abs(c["t"] - nw["t"]) < 1e-9
    assert abs(c["p"] - nw["p"]) < 1e-12
    # a regression: OLS coefficients, and the sandwich against a hand-coded loop
    x1, x2 = rng.normal(size=600), rng.normal(size=600)
    y2 = 0.3 + 2.0 * x1 - 1.0 * x2 + e
    r2 = ols_hac(y2, {"x1": x1, "x2": x2})
    X = np.column_stack([np.ones(600), x1, x2])
    b = np.linalg.lstsq(X, y2, rcond=None)[0]
    res_ = y2 - X @ b
    S = np.zeros((3, 3))
    for t in range(600):
        S += np.outer(X[t] * res_[t], X[t] * res_[t])
    for j in range(1, 6):
        for t in range(j, 600):
            u, v = X[t] * res_[t], X[t - j] * res_[t - j]
            S += (1 - j / 6) * (np.outer(u, v) + np.outer(v, u))
    A = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(A @ S @ A))
    for i, nm in enumerate(("const", "x1", "x2")):
        assert abs(r2["coef"][nm]["b"] - b[i]) < 1e-10 and abs(r2["coef"][nm]["se"] - se[i]) < 1e-10
    # dropped rows are skipped, not filled: lags count retained rows
    yn, x1n = y2.copy(), x1.copy()
    yn[[10, 200]], x1n[[11, 300]] = np.nan, np.nan
    keep = np.isfinite(yn) & np.isfinite(x1n)
    ra, rb = ols_hac(yn, {"x1": x1n, "x2": x2}), ols_hac(y2[keep], {"x1": x1[keep], "x2": x2[keep]})
    assert ra["n"] == 596 and all(abs(ra["coef"][k]["t"] - rb["coef"][k]["t"]) < 1e-12 for k in ra["coef"])
    # not estimable
    assert ols_hac(y[:29], {})["why"].endswith("fewer than 30 observations") and ols_hac(y[:30], {})["estimable"]
    assert "rank-deficient" in ols_hac(y, {"x": x1, "H": np.zeros(600)})["why"]
    assert "rank-deficient" in ols_hac(y, {"x": x1, "H": np.ones(600)})["why"]
    assert "not finite or not positive" in ols_hac(np.full(100, 3.0), {})["why"]
    assert not positive_with_t(ols_hac(y[:20], {"x": x1[:20]}), "x", 2.0)
    mt29, mt30 = mean_test(y[:29]), mean_test(y[:30])
    assert scan.nw_mean_test(y[:29])["t"] is not None and mt29["t"] is None and not mt29["estimable"]
    assert mt30["estimable"] and abs(mt30["t"] - scan.nw_mean_test(y[:30])["t"]) < 1e-12
    assert mean_test(np.zeros(100))["t"] is None
    return (f"HAC sandwich on a constant = scan.nw_mean_test (t {c['t']:.6f} vs {nw['t']:.6f}); = a hand-coded "
            "sandwich with two regressors; NaN rows skipped; not estimable for n < 30, a dummy that never varies, a "
            "dummy equal to the intercept, se = 0; nw_mean_test + the 30-observation rule")


def _st_rolling_and_rules() -> str:
    rng = np.random.default_rng(2)
    x = rng.lognormal(0, 0.5, 700)
    x[[3, 60, 400, 401]] = np.nan
    q = trailing_quantile(x, Q_HIGH_VOL)
    defined_before = np.cumsum(np.concatenate([[0], np.isfinite(x[:-1]).astype(int)]))
    assert np.all(np.isnan(q[defined_before < 100])) and np.all(np.isfinite(q[defined_before >= 100]))
    for i in (150, 420, 699):
        hist = x[:i][np.isfinite(x[:i])][-250:]
        assert abs(q[i] - np.quantile(hist, 2 / 3, method="linear")) < 1e-15
    x2 = x.copy()
    x2[500:] = 1e6                                               # changing the future leaves the past unchanged
    assert np.array_equal(trailing_quantile(x2, Q_HIGH_VOL)[:501], q[:501], equal_nan=True)
    H = high_vol_flag(np.array([1.0, 2.0, 2.0000001, np.nan, 3.0]), np.array([2.0, 2.0, 2.0, 1.0, np.nan]))
    assert np.array_equal(H, [0.0, 0.0, 1.0, np.nan, np.nan], equal_nan=True)            # strictly above
    m = trailing_quantile(np.abs(x), 0.5)
    assert abs(m[300] - np.quantile(np.abs(x[:300][np.isfinite(x[:300])][-250:]), 0.5, method="linear")) < 1e-15
    # the rules, case by case: s, r_rod, r_first, m_t
    cases = [  # s, r_rod, r_first, m, expected R1 R2 R3 R4
        (1, 0.01, 0.01, 0.005, (1, 1, 1, 1)),
        (1, -0.01, 0.01, 0.005, (0, 1, 0, 0)),          # strong disagreement: R4 skips
        (1, -0.01, 0.01, 0.01, (0, 1, 0, 0)),           # |r_rod| == m: R4 skips (>=)
        (1, -0.01, 0.01, 0.0100001, (0, 1, 0, 1)),      # below m: R4 takes
        (1, -0.01, 0.01, np.nan, (0, 1, 0, 1)),         # m missing: R4 takes
        (-1, np.nan, 0.01, 0.005, (1, 0, 0, 1)),        # r_rod missing: R1 and R4 take
        (-1, 0.0, -0.02, 0.005, (1, 1, 1, 1)),          # r_rod exactly 0 passes
        (-1, 0.01, 0.0, 0.005, (0, 1, 0, 0)),           # r_first 0 passes, R3 = AND
        (1, 0.01, np.nan, 0.005, (1, 1, 1, 1)),         # r_first missing passes
        (-1, -0.02, 0.03, 0.005, (1, 0, 0, 1)),
        (0, -0.02, 0.03, 0.005, (0, 0, 0, 0)),          # not an F2 day
    ]
    s = np.array([c[0] for c in cases], float)
    tk = rule_takes(s, np.array([c[1] for c in cases]), np.array([c[2] for c in cases]),
                    np.array([c[3] for c in cases]), s != 0)
    for i, c in enumerate(cases):
        got = tuple(int(tk[k][i]) for k in RULES)
        assert got == c[4], (i, got, c)
    assert np.array_equal(tk["R0"], s != 0)
    return ("q_t (2/3) and m_t (median) use only the last 250 defined values strictly before t, >= 100 needed, "
            "future changes leave them unchanged; H_t strict; R1-R4 incl. missing/zero predictors and R4's >=")


def _synthetic_vars(rng, n, plant_b=0.0, plant_h=0.0):
    r_on, r_day = rng.normal(0, 0.006, n), rng.normal(0, 0.008, n)
    r_rod = r_on + r_day
    rv = rng.lognormal(-6, 0.4, n)
    q = trailing_quantile(rv, Q_HIGH_VOL)
    H = np.nan_to_num(high_vol_flag(rv, q))
    r_last = plant_b * r_rod + plant_h * H * r_rod + rng.normal(0, 0.003, n)
    r_first = r_on + rng.normal(0, 0.003, n)
    v = {"r_first": r_first, "r_12": rng.normal(0, 0.002, n), "r_rod": r_rod, "r_on": r_on, "r_day": r_day,
         "r_last": r_last, "y": rng.normal(0, 0.001, n), "rod_simple": np.expm1(r_rod),
         "last_simple": np.expm1(r_last), "rv_fh": rv, "S": np.full(n, 4000.0), "X": np.full(n, 4000.0)}
    v["r_rod"][[5, 9]] = np.nan                                     # days after a half day: no prior close
    v["r_first"][[5, 9]] = np.nan
    return v


def _bdays(start: str, n: int) -> np.ndarray:
    d = np.busday_offset(np.datetime64(start), np.arange(n), roll="forward")
    return np.array([str(x) for x in d])


def _st_part_a() -> str:
    rng = np.random.default_rng(3)
    n = 3200
    dates = _bdays("2013-04-01", n)
    planted = part_a(dates, _synthetic_vars(rng, n, plant_b=0.06))
    noise = part_a(dates, _synthetic_vars(np.random.default_rng(4), n))
    assert planted["primary"]["verdict"] == "replicates on D1", planted["primary"]["regression"]
    assert noise["primary"]["verdict"] == "did not replicate on D1 2013-2026"
    assert abs(planted["primary"]["b_x100"] - 6.0) < 1.0
    sec = part_a(dates, _synthetic_vars(np.random.default_rng(5), n, plant_h=0.1))
    assert sec["secondary"]["verdict"].startswith("stronger"), sec["secondary"]["regression"]
    assert noise["secondary"]["verdict"].startswith("not shown")
    d = planted["descriptive"]
    assert set(d["by_period"]) == set(PERIODS) and len(d["by_year"]) >= 13
    assert d["r2_out_of_sample"]["n_predictions"] > 2000
    assert d["timing"]["eta(r_rod)"]["mean_bps_per_day"] > 0 and planted["undefined_days"]["r_rod"] == 2
    t2 = d["timing"]["eta(r_first, r_12)"]
    assert 0 < t2["days_traded"] < t2["days"]                      # the agreement rule is flat on some days
    assert np.array_equal(side_two([0.1, -0.1, 0.1, 0.0, np.nan], [0.2, -0.3, -0.1, -0.2, 1]),
                          [1, -1, 0, -1, np.nan], equal_nan=True)
    return (f"planted r_rod slope found (b x100 {planted['primary']['b_x100']:.2f}), pure noise not "
            f"(t {coef(noise['primary']['regression'], 'r_rod')['t']:.2f}); planted high-volatility interaction found; "
            "descriptive tables built")


def _synthetic_pb(rng, n_disc, n_conf, plant: bool, unpriceable=()):
    dates = np.concatenate([_bdays("2013-04-01", n_disc), _bdays("2021-01-04", n_conf)])
    n = len(dates)
    s = np.where(rng.uniform(size=n) < 0.4, rng.choice([-1.0, 1.0], n), 0.0)
    r_rod, r_first = rng.normal(0, 0.01, n), rng.normal(0, 0.01, n)
    r_rod[[7, 8]] = np.nan
    m = trailing_quantile(np.abs(r_rod), 0.5)
    f2 = s != 0
    pnl = 150 + rng.normal(0, 900, n)
    if plant:
        with np.errstate(invalid="ignore"):
            pnl = np.where(s * np.sign(r_rod) < 0, pnl - 550, pnl)
    a = np.where(f2, pnl, np.nan)
    ok = f2.copy()
    ok[list(unpriceable)] = False
    a[~ok] = np.nan
    idx = np.where(f2, pnl / 20 + rng.normal(0, 5, n), np.nan)
    vals = {"a": a, "a74": a - 0.65, "c": np.where(f2, pnl - 8, np.nan), "c74": np.where(f2, pnl - 8.65, np.nan),
            "idx": idx, "ok": ok, "traded": f2}
    add = ~f2 & np.isfinite(r_rod) & (r_rod != 0)
    va = {k: np.where(add, rng.normal(0, 900, n), np.nan) for k in ("a", "a74", "c", "c74", "idx")}
    va["ok"] = add.copy()
    va["ok"][np.flatnonzero(add)[:3]] = False
    va["a"][np.flatnonzero(add)[:3]] = np.nan
    return {"dates": dates, "s": s, "f2": f2, "m": m, "takes": rule_takes(s, r_rod, r_first, m, f2), "add": add,
            "vals": vals, "vals_add": va}


def _st_part_b_core() -> str:
    out = []
    for plant, seed in ((True, 6), (False, 7)):
        rng = np.random.default_rng(seed)
        pb = _synthetic_pb(rng, 2000, 1450, plant, unpriceable=())
        tabs = {"full": rule_table(pb, in_period(pb["dates"], DISCOVERY))}
        for name, per in zip(("half1", "half2"), HALVES):
            tabs[name] = rule_table(pb, in_period(pb["dates"], per))
        pick, elig = select_rule(tabs["full"]["rules"], tabs["half1"]["rules"], tabs["half2"]["rules"])
        conf = confirm(pick, rule_table(pb, in_period(pb["dates"], CONFIRMATION))["rules"])
        if plant:
            assert pick == "R1", (pick, elig)
            assert conf["verdict"] == "adds to the F2 trade", conf
            out.append(f"planted (skipped trades lose $550 more) -> pick {pick} (t {elig['R1']['t']:.2f}), confirmed")
        else:
            assert pick is None, elig
            assert conf["verdict"] == "no momentum rule improved F2 on 2013-2020" and not conf["tested"]
            out.append("noise -> pick none, confirmation not run")
    # d = minus the P&L of the skipped trades; R0's d is 0 and never estimable
    rng = np.random.default_rng(8)
    pb = _synthetic_pb(rng, 600, 0, True, unpriceable=(20, 21, 22, 23, 24, 25))
    mask = in_period(pb["dates"], DISCOVERY)
    tab = rule_table(pb, mask)
    up = pb["f2"] & ~pb["vals"]["ok"]
    assert tab["unpriceable_r0_days_dropped"] == int(up.sum()) > 0 and tab["days"] == int(mask.sum() - up.sum())
    m = mask & ~up
    for k in ("R1", "R4"):
        skipped = pb["f2"] & ~pb["takes"][k] & m
        expect = -np.sum(pb["vals"]["a"][skipped]) / m.sum()
        assert abs(tab["rules"][k]["d_a"]["mean"] - expect) < 1e-9
        assert tab["rules"][k]["d_a"]["n"] == tab["days"]           # every rule on exactly the same days
        assert tab["rules"][k]["trades_kept"] + tab["rules"][k]["trades_skipped"] == tab["f2_trades"]
    assert tab["rules"]["R0"]["d_a"]["t"] is None and not tab["rules"]["R0"]["d_a"]["estimable"]
    assert tab["rules"]["R5"]["added_unpriceable"] == 3 and tab["rules"]["R5"]["d_a"]["n"] == tab["days"] - 3
    # an unpriceable F2 day leaves every rule's series, even a rule that would have skipped it
    u = 20 + int(np.argmax(pb["f2"][20:26]))
    small = {**pb, "takes": {k: v.copy() for k, v in pb["takes"].items()}}
    small["takes"]["R1"][u] = False
    assert rule_table(small, mask)["rules"]["R1"]["d_a"]["mean"] == tab["rules"]["R1"]["d_a"]["mean"]
    # a tie goes to the lower rule number
    fake = {k: {"d_a": {"estimable": True, "mean": 1.0, "p": 0.001, "t": 3.0}, "d_idx": {"mean": 1.0}} for k in RULES}
    assert select_rule(fake, fake, fake)[0] == "R1"
    fake["R3"]["d_a"]["t"] = 3.1
    assert select_rule(fake, fake, fake)[0] == "R3"
    fake["R3"]["d_idx"]["mean"] = -0.1                               # the index guard
    assert select_rule(fake, fake, fake)[0] == "R1"
    return "; ".join(out) + ("; unpriceable R0 days dropped from every rule (paired days), d = -(skipped P&L), "
                             "tie -> lower rule, index guard")


def _st_pricing() -> str:
    consts = {"k_d1": K_D1, "f": {o: (F_10 if o == OFFSET else 1.0 + 0.01 * o) for o in strikes.OFFSETS},
              "f_10": F_10, "sigma_c": SIGMA_C, "level": LEVEL}
    S = np.array([3001.3, 4502.6, 2500.0, 3700.0, 3900.0])
    X = np.array([3011.0, 4490.0, 2500.0, 3712.0, 3905.0])
    d = np.array([1.0, -1.0, 0.0, 1.0, -1.0])
    rv = np.array([1.2e-4, 2.0e-4, 1e-4, np.nan, 1.5e-4])
    y = np.log(X / S)
    tv = trade_values(S, X, d, rv, y, consts)
    for i in (0, 1, 4):
        lam = LEVEL / S[i]
        Xp = LEVEL + lam * (X[i] - S[i])
        k_atm = LEVEL + lam * (float(strikes.strike_for(S[i])) - S[i])
        K = k_atm - d[i] * 10
        sig = K_D1 * rv[i] * 3.0 * LEVEL
        price = F_10 * strikes.bachelier(d[i] > 0, LEVEL, K, sig)
        pay = max(Xp - K, 0.0) if d[i] > 0 else max(K - Xp, 0.0)
        assert abs(tv["a"][i] - (100 * (pay - price - 0.10) - 0.09)) < 1e-8
        assert abs(tv["a74"][i] - (100 * (pay - price - 0.10) - 0.74)) < 1e-8
        pc = strikes.bachelier(d[i] > 0, LEVEL, K, SIGMA_C)
        assert abs(tv["c"][i] - (100 * (pay - pc - 0.10) - 0.09)) < 1e-8
        assert abs(tv["idx"][i] - d[i] * y[i] * 1e4) < 1e-12
    assert np.isnan(tv["a"][2]) and np.isnan(tv["c"][2]) and not tv["traded"][2]          # no trade
    assert np.isnan(tv["a"][3]) and not tv["ok"][3] and np.isfinite(tv["c"][3])          # unpriceable in (a) only
    assert np.isnan(rv_or_nan(np.full(390, 4000.0)))                                       # rv exactly 0 -> NaN
    c = np.full(381, 4000.0)
    c[10:200] = np.nan
    assert np.isnan(rv_or_nan(c))                                                          # < 300 returns -> NaN
    assert repro_check({"trades": 644, "mean_a": EXPECTED_MEAN_A + 0.009, "mean_c": EXPECTED_MEAN_C - 0.009,
                        "ok_trades_a": 644})["passed"]
    fails = [
        {"trades": 643, "mean_a": EXPECTED_MEAN_A, "mean_c": EXPECTED_MEAN_C},
        {"trades": 644, "mean_a": EXPECTED_MEAN_A + 0.011, "mean_c": EXPECTED_MEAN_C},
        {"trades": 644, "mean_a": EXPECTED_MEAN_A, "mean_c": EXPECTED_MEAN_C - 0.011},
        {"trades": 644, "mean_a": None, "mean_c": EXPECTED_MEAN_C},
        {"trades": 644, "mean_a": EXPECTED_MEAN_A, "mean_c": float("nan")}]
    for f in fails:
        r = repro_check({**f, "ok_trades_a": 0})
        assert not r["passed"] and len(r["failures"]) == 1, r
    fake_sel = {"pick": "R1", "tables": {"full": {"rules": {}}}}
    st = part_b_run({}, fake_sel, repro_check({**fails[0], "ok_trades_a": 0}))
    assert st["status"] == "pricing did not reproduce" and "confirmation" not in st
    return ("strikes.model_ladder ITM10 P&L = the plan's formula for (a) and (c); unpriceable (a) is NaN, not 0; "
            "rv 0 or < 300 returns -> NaN; reproduction check fails on the count, on (a) or (c) off by > $0.01, on "
            "a missing mean, and stops Part B with 'pricing did not reproduce'")


def _results_json(path: Path, **override) -> None:
    rj = {"calibration": {"k_d1": K_D1, "skew": {strikes.label(o): {"f": F_10 if o == OFFSET else 1.0}
                                                 for o in strikes.OFFSETS}},
          "part2": {"level": LEVEL, "sigma_c_pts": SIGMA_C}}
    for k, v in override.items():
        if k == "k_d1":
            rj["calibration"]["k_d1"] = v
        elif k == "f_10":
            rj["calibration"]["skew"]["ITM10"]["f"] = v
        else:
            rj["part2"][{"sigma_c": "sigma_c_pts", "level": "level"}[k]] = v
    path.write_text(json.dumps(rj))


def _st_gates_and_selection() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        plan, led = tmp / "plan.md", tmp / "LEDGER.md"
        led.write_text("nothing\n")
        assert "does not exist" in _raises(check_plan, plan, led, "0" * 64)
        plan.write_text("locked plan\n")
        assert "is not in" in _raises(check_plan, plan, led, "0" * 64)
        h = sha256_file(plan)
        led.write_text(f"- t  {h}  plan.md\n")
        assert "the locked plan is" in _raises(check_plan, plan, led, "0" * 64)
        assert check_plan(plan, led, h) == h
        # constants: exact, and sigma_c recomputed within 1e-9
        rj = tmp / "results.json"
        _results_json(rj)
        c = check_constants(rj, SIGMA_C + 5e-10)
        assert c["f"][OFFSET] == F_10 and c["level"] == LEVEL
        for k, v in (("k_d1", np.nextafter(K_D1, 2)), ("f_10", np.nextafter(F_10, 2)),
                     ("sigma_c", np.nextafter(SIGMA_C, 20)), ("level", 7709.59)):
            _results_json(rj, **{k: float(v)})
            assert k in _raises(check_constants, rj, SIGMA_C)
        _results_json(rj)
        assert "recomputed" in _raises(check_constants, rj, SIGMA_C + 2e-9)
        assert "recomputed" in _raises(check_constants, rj, float("nan"))
        # the selection: written once, read-only, verified against the recorded hashes
        script = tmp / "momentum_copy.py"
        script.write_text("# v1\n")
        out = tmp / "out"
        out.mkdir()
        ctx = Ctx(out_dir=out, plan=plan, ledger=led, plan_sha=h, script=script, strikes_json=rj)
        assert "is missing" in _raises(verify_selection, ctx)
        payload = {"hashes": {"plan_sha256": h, "momentum_py_sha256": sha256_file(script),
                              "strikes_results_json_sha256": sha256_file(rj)}, "pick": "none", "x": np.float64(1.5)}
        write_selection(out, payload)
        assert not os.access(out / SEL_JSON, os.W_OK) and not os.access(out / SEL_SHA, os.W_OK)
        assert "already exists" in _raises(write_selection, out, payload)
        assert verify_selection(ctx)["pick"] == "none"
        original = (out / SEL_JSON).read_bytes()
        os.chmod(out / SEL_JSON, 0o644)
        (out / SEL_JSON).write_bytes(original.replace(b'"none"', b'"R1"'))
        assert "!= frozen" in _raises(verify_selection, ctx)
        (out / SEL_JSON).write_bytes(original)
        assert verify_selection(ctx)
        for path in (plan, script, rj):
            before = path.read_bytes()
            path.write_bytes(before + b" ")
            assert "the selection recorded" in _raises(verify_selection, ctx)
            path.write_bytes(before)
        os.chmod(out / SEL_SHA, 0o644)
        (out / SEL_SHA).unlink()
        assert "is missing" in _raises(verify_selection, ctx)
        assert "already exists" in _raises(refuse_if_selection_exists, out)          # the .json alone blocks
        (out / SEL_JSON).unlink()
        (out / SEL_SHA).write_text("x\n")
        assert "already exists" in _raises(refuse_if_selection_exists, out)          # the .sha256 alone blocks
    return ("plan gate refuses missing / unlisted / not the locked hash; constants must be exact (k_D1, f_10, "
            "sigma_c, L) and sigma_c recomputed within 1e-9; selection written once (exclusive create, read-only), "
            "either file blocks a rewrite; verify refuses a missing file, an edited selection, and a changed plan, "
            "script or results.json")


def _oi_text(rows) -> str:
    head = ("ts_recv,ts_event,rtype,publisher_id,instrument_id,ts_ref,price,quantity,sequence,ts_in_delta,"
            "stat_type,channel_id,update_action,stat_flags,symbol")
    body = [f"{ts},{ts},24,30,1,,,{q},{seq},0,{st},1,1,0,{sym}" for ts, seq, q, st, sym in rows]
    return "\n".join([head] + body) + "\n"


def _st_osi_settlement_oi() -> str:
    assert parse_osi("SPXW  261020C06700000") == ("SPXW", "2026-10-20", True, 6700.0)
    assert parse_osi("SPX   130622P01600000") == ("SPX", "2013-06-22", False, 1600.0)
    assert parse_osi("SPX   150918C02012500")[3] == 2012.5
    for bad in ("SPXW 261020C06700000", "SPXPM 261020C06700000", "SPXW  261320C06700000", "SPXW  261020X06700000",
                "SPXW  26102OC06700000", "SPXW  261020C0670000O", "SPXW  261020C00000000", "", "SPY   261020C00500000",
                " SPXW 261020C06700000"):
        try:
            parse_osi(bad)
            raise AssertionError(f"parsed {bad!r}")
        except ValueError:
            pass
    sessions = ["2013-06-19", "2013-06-20", "2013-06-21", "2013-06-24", "2022-04-13", "2022-04-14", "2022-04-18",
                "2026-11-06"]
    utc = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)          # noqa: E731
    assert settlement("SPX", "2013-06-22", sessions) == utc("2013-06-21T13:30:00")       # Saturday OSI -> Fri 09:30 EDT
    assert settlement("SPX", "2022-04-15", sessions) == utc("2022-04-14T13:30:00")       # Good Friday -> Thursday
    assert settlement("SPX", "2013-06-21", sessions) == utc("2013-06-21T13:30:00")
    assert settlement("SPXW", "2026-10-20", sessions) == utc("2026-10-20T20:00:00")      # 16:00 EDT
    assert settlement("SPXW", "2013-12-06", sessions) == utc("2013-12-06T21:00:00")      # 16:00 EST
    assert settlement("SPX", "2031-12-20", sessions) == utc("2031-12-19T14:30:00")       # beyond the file: weekday rule
    assert prev_session("2013-06-24", sessions) == "2013-06-21" and prev_session("2013-06-19", sessions) is None
    assert prev_session("2013-06-22", sessions) == "2013-06-21"
    # the 15:30 ET cutoff in EDT and EST
    assert et_ns("2013-06-03", "15:30") == int(utc("2013-06-03T19:30:00").timestamp()) * 10 ** 9
    assert et_ns("2013-12-02", "15:30") == int(utc("2013-12-02T20:30:00").timestamp()) * 10 ** 9
    assert ts_ns("2013-06-03T19:29:59.999999999Z") == et_ns("2013-06-03", "15:30") - 1
    assert ts_ns("2013-06-03T19:30:00Z") == et_ns("2013-06-03", "15:30")
    # open-interest records on 2013-06-03 (cutoff 19:30:00Z)
    a, b, c_ = "SPXW  130607C01600000", "SPXW  130607P01600000", "SPX   130622C01650000"
    rows = [
        ("2013-06-03T13:31:00.000000000Z", 1, "100", "9", a),
        ("2013-06-03T19:29:59.999999999Z", 2, "150", "9", a),              # later record wins
        ("2013-06-03T19:30:00.000000000Z", 3, "999", "9", a),              # at the cutoff: not used
        ("2013-06-03T13:31:00.000000000Z", 7, "70", "9", b),               # same ts, higher sequence wins
        ("2013-06-03T13:31:00.000000000Z", 5, "50", "9", b),
        ("2013-06-03T13:31:00.000000000Z", 4, "40", "9", c_),              # an exact duplicate is fine
        ("2013-06-03T13:31:00.000000000Z", 4, "40", "9", c_),
        ("2013-06-03T13:31:00.000000000Z", 4, "41", "9", "SPXW  130607C01605000"),   # conflict
        ("2013-06-03T13:31:00.000000000Z", 4, "42", "9", "SPXW  130607C01605000"),
        ("2013-06-03T13:31:00.000000000Z", 4, "", "9", "SPXW  130607C01610000"),     # missing
        ("2013-06-03T13:31:00.000000000Z", 4, "2147483647", "9", "SPXW  130607C01615000"),   # sentinels
        ("2013-06-03T13:31:00.000000000Z", 4, "9223372036854775807", "9", "SPXW  130607C01620000"),
        ("2013-06-03T13:31:00.000000000Z", 4, "-3", "9", "SPXW  130607C01625000"),   # negative
        ("2013-06-03T13:31:00.000000000Z", 4, "12.5", "9", "SPXW  130607C01630000"),  # not an integer
        ("2013-06-03T13:31:00.000000000Z", 4, "50", "9", "SPXW  130607C01635000"),    # valid, then a missing last
        ("2013-06-03T14:00:00.000000000Z", 5, "", "9", "SPXW  130607C01635000"),
        ("2013-06-03T13:31:00.000000000Z", 4, "30", "9", "SPXW  130607C01640000"),    # an early conflict excludes
        ("2013-06-03T13:31:00.000000000Z", 4, "31", "9", "SPXW  130607C01640000"),
        ("2013-06-03T14:00:00.000000000Z", 5, "32", "9", "SPXW  130607C01640000"),
        ("2013-06-03T13:31:00.000000000Z", 4, "0", "9", "SPXW  130607C01645000"),     # zero is valid
        ("2013-06-03T13:31:00.000000000Z", 4, "5", "3", "SPXW  130607C01650000"),     # another stat type
        ("2013-06-03T13:31:00.000000000Z", 4, "5", "9", "SPXW  130607Q01650000"),     # bad symbol
    ]
    contracts, cnt, bad = parse_oi(_oi_text(rows), "2013-06-03")
    got = {x[0]: x[5] for x in contracts}
    assert got == {a: 150, b: 70, c_: 40, "SPXW  130607C01645000": 0}, got
    assert bad == ["SPXW  130607Q01650000"]
    assert (cnt["contracts_excluded_conflict"], cnt["contracts_excluded_missing"], cnt["contracts_excluded_sentinel"],
            cnt["contracts_excluded_negative"], cnt["contracts_excluded_non_integer"]) == (2, 2, 2, 1, 1), cnt
    assert cnt["oi_records_at_or_after_cutoff"] == 1 and cnt["records_other_stat_type"] == 1
    assert cnt["contracts_usable"] == 4 and cnt["contracts_before_cutoff"] == 12
    assert parse_oi("", "2013-06-03")[0] == []
    rp = load_module("spx_candle_realprice_ro", REALPRICE_PY)             # loaded, not called: partc's close source
    assert callable(rp.fetch_closes) and callable(rp.parse_cboe) and rp.CBOE_URL.endswith("SPX_History.csv")
    return ("OSI parsing (SPX/SPXW only, bad dates, letters, zero strike); SPXW settles 16:00 ET on the OSI date, SPX "
            "AM 09:30 ET on the last session on or before it (130622 -> Fri 2013-06-21, Good Friday -> Thursday, "
            "beyond the file -> last weekday); 15:30 ET cutoff in EDT/EST to the nanosecond; last record by "
            "(ts_recv, sequence); duplicates kept once, conflicts, missing, int32/int64 sentinels, negative and "
            "non-integer quantities excluded and counted, never 0")


def _st_gamma_nge() -> str:
    g = float(bs_gamma(100.0, 100.0, 0.2, 1.0))
    assert abs(g - math.exp(-0.5 * 0.01) / math.sqrt(2 * math.pi) / 20.0) < 1e-15            # d1 = 0.1
    Phi = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))                                          # noqa: E731
    delta = lambda S_: Phi((math.log(S_ / 4010.0) + 0.5 * 0.18 ** 2 * 0.01) / (0.18 * 0.1))      # noqa: E731
    fd = (delta(4000.0 + 0.01) - delta(4000.0 - 0.01)) / 0.02
    assert abs(float(bs_gamma(4000.0, 4010.0, 0.18, 0.01)) - fd) < 1e-7
    for tau, want in ((9.0, 0.12), (30.0, 0.15), (93.0, 0.18), (2.0, 0.12)):
        assert abs(float(ts_sigma(tau, 12, 15, 18)) - want) < 1e-15
    assert abs(float(ts_sigma(400.0, 12, 15, 18)) - 0.18) < 1e-15
    w9, w30 = 0.12 ** 2 * 9, 0.15 ** 2 * 30
    assert abs(float(ts_sigma(19.5, 12, 15, 18)) - math.sqrt((w9 + (w30 - w9) * 0.5) / 19.5)) < 1e-15
    # day t = Monday 2013-11-04 (EST), t-1 = Friday 2013-11-01 (EDT): 73 hours to the 16:00 SPXW settlement
    sessions = ["2013-10-31", "2013-11-01", "2013-11-04", "2013-11-15"]
    S, vix = 1761.64, 13.0
    con = [("x", "SPXW", "2013-11-04", True, 1760.0, 1000),            # expires today 16:00: kept
           ("x", "SPXW", "2013-11-04", False, 1750.0, 800),
           ("x", "SPX", "2013-11-04", False, 1700.0, 5000),            # AM today: settles before 15:30, dropped
           ("x", "SPXW", "2013-11-01", True, 1700.0, 9000),            # already expired: dropped
           ("x", "SPX", "2013-11-16", False, 1650.0, 3000)]            # Saturday OSI: Friday 2013-11-15 09:30
    r = nge_for_day(con, "2013-11-04", "2013-11-01", S, vix, (11.0, 13.0, 15.0), sessions, {})
    T0 = 73 * 3600 / YEAR_SECONDS
    T1 = ((datetime(2013, 11, 15, 14, 30, tzinfo=timezone.utc) - datetime(2013, 11, 1, 20, 0, tzinfo=timezone.utc))
          .total_seconds() / YEAR_SECONDS)
    gc, gp, gm = (float(bs_gamma(S, K, 0.13, T)) for K, T in ((1760.0, T0), (1750.0, T0), (1650.0, T1)))
    assert r["contracts_used"] == 3 and r["contracts_settled_before_cutoff"] == 2
    assert abs(r["nge_star"] - 100 * (gc * 1000 - gp * 800 - gm * 3000)) < 1e-9 * max(1.0, abs(r["nge_star"]))
    assert abs(r["nge_star_puts"] - (-100 * (gp * 800 + gm * 3000))) < 1e-9 * abs(r["nge_star_puts"])
    sig_ts = ts_sigma(np.array([T0, T0, T1]) * 365, 11.0, 13.0, 15.0)
    gts = bs_gamma(S, np.array([1760.0, 1750.0, 1650.0]), sig_ts, np.array([T0, T0, T1]))
    assert abs(r["nge_star_ts"] - 100 * (gts[0] * 1000 - gts[1] * 800 - gts[2] * 3000)) < 1e-9 * abs(r["nge_star_ts"])
    only_calls = nge_for_day(con[:1], "2013-11-04", "2013-11-01", S, vix, None, sessions, {})
    assert only_calls["nge_star"] > 0 and math.isnan(only_calls["nge_star_ts"])
    none_left = nge_for_day(con[2:4], "2013-11-04", "2013-11-01", S, vix, None, sessions, {})
    assert none_left["contracts_used"] == 0 and math.isnan(none_left["nge_star"])
    return ("Black-Scholes gamma = closed form and = a finite difference of delta; term-structure sigma linear in "
            "total variance, flat outside 9-93 days; NGE* sums calls minus puts with T measured tz-aware across the "
            "DST change (73 h), drops AM-today and expired contracts, undefined when nothing survives")


def _st_part_c_core() -> str:
    rng = np.random.default_rng(9)
    n = 3000
    dates = _bdays("2013-04-01", n)
    N = (rng.uniform(size=n) < 0.45).astype(float)
    N[:40] = np.nan
    x = rng.normal(0, 0.01, n)
    v = {"r_rod": x, "r_last": 0.10 * N * x + rng.normal(0, 0.003, n)}
    s = np.where(rng.uniform(size=n) < 0.4, rng.choice([-1.0, 1.0], n), 0.0)
    f2 = s != 0
    pnl = np.where(f2, 100 + 450 * np.nan_to_num(N) + rng.normal(0, 900, n), np.nan)
    pb = {"f2": f2, "takes": {"R0": f2, "R1": f2 & (rng.uniform(size=n) < 0.6)},
          "vals": {"a": pnl, "idx": np.where(f2, pnl / 20, np.nan)}}
    nd = {"N": N, "nge_star": np.where(N == 1, -1e6, 1e6) * rng.uniform(0.5, 1.5, n),
          "nge_star_puts": -rng.uniform(1e5, 1e6, n), "nge_star_ts": np.where(N == 1, -1.0, 1.0), "N_ts": N.copy()}
    ok_repro = {"passed": True}
    sel = {"pick": "R1"}
    r = part_c_tests(dates, nd, v, pb, sel, ok_repro)
    assert r["C1"]["supported"] and r["C2"]["supported"], (r["C1"]["regression"]["coef"], r["C2"]["regression"]["coef"])
    assert r["descriptive"]["term_structure"]["sign_agreement_with_vix"] == 1.0
    assert r["descriptive"]["f2_by_frozen_rule_and_N"]["rule"] == "R1"
    pb_guard = {**pb, "vals": {"a": pnl, "idx": np.where(f2, -pnl / 20, np.nan)}}
    assert not part_c_tests(dates, nd, v, pb_guard, sel, ok_repro)["C2"]["supported"]          # the index guard
    v0 = {"r_rod": x, "r_last": rng.normal(0, 0.003, n)}
    pb0 = {**pb, "vals": {"a": np.where(f2, 100 + rng.normal(0, 900, n), np.nan), "idx": np.where(f2, 1.0, np.nan)}}
    r0 = part_c_tests(dates, nd, v0, pb0, {"pick": "none"}, ok_repro)
    assert not r0["C1"]["supported"] and not r0["C2"]["supported"]
    assert r0["descriptive"]["f2_by_frozen_rule_and_N"]["rule"].startswith("R0")
    rf = part_c_tests(dates, nd, v, pb, sel, {"passed": False})
    assert rf["C2"]["status"] == "pricing did not reproduce" and "regression" in rf["C1"]
    return ("planted short-gamma interaction (C1) and P&L gap (C2) supported, noise not; the index guard blocks C2; "
            "a failed reproduction stops C2 only")


def _st_budget_and_inputs() -> str:
    # the spend-log conventions match tools/databento_spx_oi.py (its source text is read, not imported)
    src = OI_TOOL_PY.read_text()
    lit = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                lit[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    schema = lambda w: f"{lit['SCHEMA']}_oi_{w[0].replace(':', '')}-{w[1].replace(':', '')}"   # noqa: E731
    assert '''"schema": f"{SCHEMA}_oi_{window[0].replace(':', '')}-{window[1].replace(':', '')}"''' in src
    assert (schema(lit["FULL_DAY_ET"]), schema(lit["WINDOW_ET"]), schema(lit["FALLBACK_ET"])) == (
        OI_SCHEMA_FULL_DAY, OI_SCHEMA_PREOPEN, OI_SCHEMA_FALLBACK)
    assert lit["PILLAR_LIVE"] == OI_PILLAR_LIVE and f'log_spend(d, c, 0, "{OI_EMPTY_LABEL}", w_)' in src
    assert "return FULL_DAY_ET if day < PILLAR_LIVE else WINDOW_ET" in src
    assert "tries = [win] + ([FALLBACK_ET] if win != FULL_DAY_ET else [])" in src
    E, FAIL = OI_EMPTY_LABEL, "(failed: may be billed; retried next run)"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        oi, log = tmp / "oi", tmp / "spend.csv"
        oi.mkdir()
        days = ["2015-06-01", "2015-06-02", "2023-03-27", "2023-03-28", "2024-01-02", "2026-10-20"]
        for d in ("2015-06-01", "2023-03-28", "2026-10-20"):
            (oi / f"{d}.csv.gz").write_bytes(gzip.compress(b"saved"))

        def log_rows(*rows):
            log.write_text("utc_time,schema,day,n_symbols,quoted_cost_usd,rows,file\n" +
                           "".join(f"t,{sc},{d},0,{c},0,{f}\n" for sc, d, c, f in rows))
        paid = ("cbbo-1m", "2021-01-04", "40.0", "x")
        b = budget_check(log, days, oi)                                                   # a missing log
        assert not b["passed"] and b["reason"] == "no spend log", b
        log_rows(paid)                                                                    # an incomplete pull
        b = budget_check(log, days, oi)
        assert not b["passed"] and b["reason"].startswith("download incomplete: 3 days not yet downloaded"), b
        assert b["first_days_not_downloaded"] == ["2015-06-02", "2023-03-27", "2024-01-02"]
        assert b["requoted_remaining_usd"] is None and b["logged_usd"] == 40.0
        log_rows(paid, (OI_SCHEMA_FULL_DAY, "2015-06-02", "0.01", E),
                 (OI_SCHEMA_PREOPEN, "2023-03-27", "0.01", E),                          # pre-2023-03-28: wrong window
                 (OI_SCHEMA_PREOPEN, "2024-01-02", "0.01", E),                          # the fallback not yet logged
                 (OI_SCHEMA_FALLBACK, "2024-01-02", "0.01", FAIL))                      # a failed request
        b = budget_check(log, days, oi)
        assert b["reason"].startswith("download incomplete: 2 days") and b["first_days_not_downloaded"] == [
            "2023-03-27", "2024-01-02"], b
        empties = [(OI_SCHEMA_FULL_DAY, "2015-06-02", "0.01", E), (OI_SCHEMA_FULL_DAY, "2023-03-27", "0.01", E),
                   (OI_SCHEMA_PREOPEN, "2024-01-02", "0.01", E), (OI_SCHEMA_FALLBACK, "2024-01-02", "0.01", E)]
        log_rows(paid, *empties)                                                          # complete, with empty days
        b = budget_check(log, days, oi)
        assert b["passed"] and b["reason"] is None and b["days_not_downloaded"] == 0, b
        assert b["days_logged_without_open_interest"] == 3 and b["requoted_remaining_usd"] == 0.0
        assert abs(b["logged_usd"] - 40.04) < 1e-12 and abs(b["open_interest_usd"] - 0.04) < 1e-12
        log_rows(paid, *empties, ("cbbo-1m", "2021-01-05", "59.96", "x"))                # exactly $100 passes
        assert budget_check(log, days, oi)["passed"]
        log_rows(paid, *empties, ("cbbo-1m", "2021-01-05", "60.0", "x"))                 # spend over $100
        b = budget_check(log, days, oi)
        assert not b["passed"] and b["reason"].startswith("logged spend $100.04"), b
        for bad_cost in ("abc", "", "-1", "nan"):
            log_rows(paid, ("cbbo-1m", "2021-01-05", bad_cost, "x"))
            assert budget_check(log, days, oi)["reason"].startswith("spend log unreadable"), bad_cost
        log.write_text("utc_time,schema,day,quoted_cost_usd\nt,cbbo-1m,2021-01-04,1.0\n")   # no file column
        assert budget_check(log, days, oi)["reason"].startswith("spend log unreadable")
        # the Cboe index files: missing or malformed -> ValueError (Part C not run); a bad CLOSE cell -> that day only
        f = tmp / "VIX_History.csv"
        assert "is missing" in _value_error(load_index_csv, f)
        f.write_text("DATE,OPEN,HIGH,LOW,CLOSE\n06/03/2013,1,1,1,14.5\n06/04/2013,1,1,1,\n06/05/2013,1,1,1,x\n"
                     "06/06/2013,1,1,1,-2\n06/07/2013,1,1,1\n")
        assert load_index_csv(f) == {"2013-06-03": 14.5}
        for text, why in (("", "no DATE and CLOSE"),
                          ("DATE,OPEN,HIGH,LOW,LAST\n06/03/2013,1,1,1,14\n", "no DATE and CLOSE"),
                          ("DATE,CLOSE\n2013-06-03,14\n", "does not parse"),
                          ("DATE,CLOSE\n13/45/2013,14\n", "does not parse"),
                          ("DATE,CLOSE\n06/03/2013,\n", "no usable close")):
            f.write_text(text)
            assert why in _value_error(load_index_csv, f), text
        # the official closes
        assert check_closes_dict({"2013-06-03": 1640.42, "2013-06-04": 1631})
        try:
            check_closes_dict({"2016-02-30": 1900.0})
            raise AssertionError("an impossible calendar date was accepted")
        except ValueError as e:
            assert "calendar date" in str(e)
        for bad in ({}, [], None, {"2013/06/03": 1640.0}, {"2013-06-03": 0.0}, {"2013-06-03": float("nan")},
                    {"2013-06-03": "1640"}, {"2013-06-03": True}):
            _value_error(check_closes_dict, bad)
    return ("the spend-log label, schema names and windows match tools/databento_spx_oi.py; the budget gate refuses "
            "a missing log, an unfinished pull (wrong window, only the pre-open window, a failed request), an "
            "unreadable log and spend over $100, and passes a finished pull with empty days (re-quote $0); index "
            "files and official closes: missing or malformed -> error, a bad CLOSE cell -> that day undefined")


def _write_synthetic_files(tmp: Path, rng):
    """A small D1 file (bars 09:30-15:59 for ~120 days 2015-2021), its days file, Cboe-style closes and VIX files.
    Day 25 is not a keep day (so day 26 has no prior close); day 40 has no 10:00-14:59 bars (no r_first, rv below 300
    returns) and a forced strong 15:50 body; day 50 lacks its 09:45 bar."""
    days = [str(d) for d in _bdays("2015-06-01", 1600)[::13]]
    keep = {d: (i != 25) for i, d in enumerate(days)}
    lines = ["date,time_et,open,high,low,close,ticked"]
    p = 2000.0
    for i, d in enumerate(days):
        p *= math.exp(rng.normal(0, 0.006))
        for k in range(390):
            if (i == 40 and 30 <= k < 330) or (i == 50 and k == 15):
                continue
            o = p
            c = o * math.exp(rng.normal(0, 4e-4))
            if i == 40 and k == scan.I1550:
                c = o + 2.0
            h, lo = max(o, c) + abs(rng.normal(0, 0.05)), min(o, c) - abs(rng.normal(0, 0.05))
            lines.append(f"{d},{scan.hhmm(k)},{o:.3f},{h:.3f},{lo:.3f},{c:.3f},1")
            p = c
    d1 = tmp / "d1.csv.gz"
    d1.write_bytes(gzip.compress(("\n".join(lines) + "\n").encode()))
    days_file = tmp / "days.csv"
    days_file.write_text("date,calendar,keep\n" + "".join(f"{d},full,{keep[d]}\n" for d in days))
    sessions = ["2015-05-29"] + days
    closes = {d: 2000.0 + 3 * i for i, d in enumerate(sessions)}
    vix = tmp / "vix"
    vix.mkdir()
    for name, lvl in (("VIX9D", 14.0), ("VIX", 16.0), ("VIX3M", 18.0)):
        (vix / f"{name}_History.csv").write_text("DATE,OPEN,HIGH,LOW,CLOSE\n" + "".join(
            f"{d[5:7]}/{d[8:10]}/{d[:4]},{lvl},{lvl},{lvl},{lvl + rng.normal(0, 1):.2f}\n" for d in sessions))
    return d1, days_file, days, keep, closes, vix


def _write_oi_files(oi_dir: Path, days: list, keep: dict, rng, bad_symbol_day=None) -> None:
    oi_dir.mkdir(exist_ok=True)
    for d in days:
        if not keep[d]:
            continue
        ts = f"{d}T13:31:00.000000000Z" if d < "2023-03-28" else f"{d}T10:30:00.000000000Z"
        late = f"{d}T20:15:00.000000000Z"
        nxt = (date.fromisoformat(d) + timedelta(days=7)).isoformat()
        rows, seq = [], 0
        for K in range(1800, 2400, 10):
            for kind in "CP":
                for exp in (d, nxt):
                    seq += 1
                    sym = f"SPXW  {exp[2:4]}{exp[5:7]}{exp[8:10]}{kind}{K * 1000:08d}"
                    rows.append((ts, seq, str(int(rng.integers(0, 5000))), "9", sym))
        rows.append((late, seq + 1, "123", "9", f"SPX   {d[2:4]}{d[5:7]}{d[8:10]}P01900000"))
        if d == bad_symbol_day:
            rows.append((ts, seq + 2, "1", "9", "BADSYMBOL"))
        (oi_dir / f"{d}.csv.gz").write_bytes(gzip.compress(_oi_text(rows).encode()))
    (oi_dir / "fallback_days.txt").write_text(days[60] + "\n")


def _st_end_to_end() -> str:
    rng = np.random.default_rng(10)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        d1, days_file, days, keep, closes, vix = _write_synthetic_files(tmp, rng)
        plan, led = tmp / "plan.md", tmp / "LEDGER.md"
        plan.write_text("locked plan (synthetic)\n")
        h = sha256_file(plan)
        led.write_text(f"- t  {h}  plan.md\n")
        script = tmp / "script.py"
        script.write_text("# the script whose hash is frozen\n")
        rj = tmp / "results.json"
        _results_json(rj)
        out = tmp / "out"
        out.mkdir()
        spend = tmp / "spend.csv"
        spend.write_text("utc_time,schema,day,n_symbols,quoted_cost_usd,rows,file\n"
                         "t,cbbo-1m,2021-01-04,34,40.0,1,x\nt,statistics_oi_0000-0931,2026-10-20,0,0.02,1,y\n")
        ctx = Ctx(out_dir=out, plan=plan, ledger=led, plan_sha=h, script=script, strikes_json=rj, d1_file=d1,
                  days_file=days_file, oi_dir=tmp / "oi", vix_dir=vix, spend_log=spend, nge_csv=tmp / "nge.csv",
                  sigma_c_recomputed=SIGMA_C, closes_loader=lambda: (closes, "synthetic"))
        assert "is missing" in _raises(run, ctx)                                    # run needs the selection
        # an empty or tiny (< 100 days) discovery sample: refused, nothing written; exactly 100 days is accepted
        head, *rows = days_file.read_text().splitlines()

        def days_where(name, ok):
            f = tmp / name
            f.write_text(head + "\n" + "".join(f"{r.rsplit(',', 1)[0]},{r.endswith('True') and ok(r[:10])}\n"
                                               for r in rows))
            return f
        disc = [d for d in days if keep[d] and d <= DISCOVERY[1]]
        for name, cut, n_want in (("none", "", 0), ("tiny", disc[98], 99)):
            out_x = tmp / f"out_{name}"
            out_x.mkdir()
            msg = _raises(discover, replace(ctx, out_dir=out_x, days_file=days_where(f"days_{name}.csv",
                                                                                      lambda d: d <= cut)))
            assert f"discovery sample has {n_want} days (< 100)" in msg and not any(out_x.iterdir()), msg
        out_x = tmp / "out_100"
        out_x.mkdir()
        p100 = discover(replace(ctx, out_dir=out_x, days_file=days_where("days_100.csv", lambda d: d <= disc[99])))
        assert p100["discovery_sample"]["n_days"] == 100 and (out_x / SEL_JSON).exists()
        # discover: D1 up to 2020-12-31 only, written once
        payload = discover(ctx)
        ds = payload["discovery_sample"]
        assert ds["last"] <= "2020-12-31" and ds["loader_stopped_at_first_row_dated"] >= "2021-01-01", ds
        assert ds["n_days"] == sum(1 for d in days if keep[d] and d <= "2020-12-31")
        assert payload["hashes"]["momentum_py_sha256"] == sha256_file(script) and payload["pick"] in ("none",) + RULES
        assert (out / SEL_JSON).exists() and (out / SEL_SHA).exists()
        missing_d1 = replace(ctx, d1_file=tmp / "no_such_file.csv.gz")
        assert "already exists" in _raises(discover, missing_d1)                     # refuses before reading data
        fake = scan.Panel(np.array(["2020-12-31", "2021-01-04"], dtype=object), *(np.zeros((2, 390)),) * 4,
                          np.zeros(2), np.zeros(2), {"stopped_at_first_row_dated": None})
        assert "reached discovery" in _raises(assert_discovery_only, fake)
        fake.dates, fake.meta = np.array(["2020-12-30", "2020-12-31"], dtype=object), {
            "stopped_at_first_row_dated": "2020-12-31"}
        assert "reached discovery" in _raises(assert_discovery_only, fake)
        # run: the synthetic panel does not reproduce the real 644 trades -> Part B stops, Part A still runs
        res = run(ctx)
        assert res["part_b"]["status"] == "pricing did not reproduce" and "verdict" in res["part_a"]["primary"]
        assert res["part_a"]["undefined_days"]["r_first"] >= 2 and res["part_a"]["undefined_days"]["rv_fh"] >= 2
        assert res["data"]["days_without_prior_close"] >= 1
        md = (out / OUT_MD).read_text()
        for phrase in ("bid candles", "not the official settlement", "adapted replication", "inside BDLM's sample",
                       "not blind for related momentum signals", "retrospective, model-priced selection",
                       "comes from a model", "Nothing here is a trading recommendation", "pricing did not reproduce"):
            assert phrase in md, phrase
        # with expectations equal to the synthetic numbers the check passes and the confirmation is computed
        P = scan.load_panel(FULL[0], FULL[1], d1, days_file)
        pb = partb_arrays(P, day_vars(P), check_constants(rj, SIGMA_C))
        num = repro_numbers(pb)
        up = pb["f2"] & ~pb["vals"]["ok"]
        assert up[list(P.dates).index(days[40])], "day 40 should be an unpriceable F2 day"
        ctx2 = replace(ctx, repro_expected=(num["trades"], num["mean_a"], num["mean_c"]))
        res2 = run(ctx2)
        b2 = res2["part_b"]
        assert b2["status"] == "run" and b2["discovery_recomputed_matches_frozen"], b2.get("status")
        assert b2["confirmation"]["verdict"] in ("no momentum rule improved F2 on 2013-2020", "adds to the F2 trade",
                                                 "not confirmed")
        assert b2["tables"]["2013-2020"]["unpriceable_r0_days_dropped"] >= 1
        back = json.loads((out / OUT_JSON).read_text())
        assert back["part_b"]["status"] == "run" and "## Part B" in (out / OUT_MD).read_text()
        # run and partc on an empty panel or an empty sample: a clear refusal, not an IndexError
        last_disc, first_hold = disc[-1], next(d for d in days if keep[d] and d > DISCOVERY[1])
        for name, ok, want in (("days_none.csv", lambda d: False, "D1 panel 2013-04-01 .. 2026-10-20 has no days"),
                               ("days_disc_only.csv", lambda d: d <= last_disc, "the 2021-2026 sample"),
                               ("days_hold_only.csv", lambda d: d >= first_hold, "the 2013-2020 sample")):
            c_x = replace(ctx2, days_file=days_where(name, ok))
            assert want in _raises(run, c_x) and want in _raises(partc, c_x)
        one = run(replace(ctx2, days_file=days_where("days_one_hold.csv", lambda d: d <= first_hold)))
        assert one["data"]["days_by_period"]["2021-2026"] == 1
        assert one["part_b"]["status"] == "pricing did not reproduce"
        res2 = run(ctx2)                                                           # restore the full outputs
        # a changed script stops run before any data is read
        script.write_text("# edited\n")
        assert "the selection recorded" in _raises(run, ctx2)
        script.write_text("# the script whose hash is frozen\n")
        # partc: while the budget, format or prior-day-input checks fail, no gamma or NGE may be computed
        n_days = len(P.dates)
        real = {k: globals()[k] for k in ("nge_daily", "nge_for_day", "bs_gamma")}

        def no_gamma(*a, **k):
            raise AssertionError("gamma computed before the checks passed")
        globals().update(dict.fromkeys(real, no_gamma))
        try:
            r = partc(ctx2)["part_c"]                                      # no files, no empty-window rows logged
            assert r["status"] == "not run" and r["reason"].startswith(
                f"budget: download incomplete: {n_days} days not yet downloaded"), r["reason"]
            assert "format" not in r["checks"] and not (tmp / "nge.csv").exists()
            assert partc(replace(ctx2, spend_log=tmp / "no_log.csv"))["part_c"]["reason"] == "budget: no spend log"
            spend_empty = tmp / "spend_empty.csv"                            # finished: every day logged empty
            spend_empty.write_text(spend.read_text() + "".join(f"t,{OI_SCHEMA_FULL_DAY},{d},0,0.01,0,{OI_EMPTY_LABEL}\n"
                                                               for d in P.dates))
            r = partc(replace(ctx2, spend_log=spend_empty))["part_c"]
            bc = r["checks"]["budget"]
            assert bc["passed"] and bc["days_logged_without_open_interest"] == n_days, bc
            assert r["status"] == "not run" and r["reason"].startswith("format"), r["reason"]   # no file -> no median
            _write_oi_files(tmp / "oi", days, keep, rng, bad_symbol_day=days[30])
            r = partc(ctx2)["part_c"]
            assert r["status"] == "not run" and r["reason"].startswith("format") and "OSI" in r["reason"]
            _write_oi_files(tmp / "oi", days, keep, rng)
            over = tmp / "spend_over.csv"
            over.write_text(spend.read_text() + "t,cbbo-1m,2021-01-05,34,60.5,1,x\n")
            r = partc(replace(ctx2, spend_log=over))["part_c"]
            assert r["status"] == "not run" and r["reason"].startswith("budget: logged spend $100.52"), r["reason"]

            def no_closes():
                raise SystemExit("Cboe SPX_History.csv did not parse")
            for loader in (no_closes, lambda: ({}, "empty"), lambda: ({"2015/06/01": 2000.0}, "bad date"),
                           lambda: ({**closes, days[3]: float("nan")}, "nan"), lambda: None):
                r = partc(replace(ctx2, closes_loader=loader))["part_c"]
                assert r["status"] == "not run" and r["reason"].startswith("prior-day inputs"), r["reason"]
                assert r["checks"]["budget"]["passed"] and r["checks"]["format"]["passed"]
            for name, text in (("VIX3M", None), ("VIX", "DATE,OPEN,HIGH,LOW\n06/01/2015,1,1,1\n"),
                               ("VIX9D", "DATE,CLOSE\n2015-06-01,14\n"), ("VIX", "DATE,CLOSE\n06/01/2015,n/a\n")):
                f = vix / f"{name}_History.csv"
                saved = f.read_text()
                f.unlink() if text is None else f.write_text(text)
                r = partc(ctx2)["part_c"]
                assert r["status"] == "not run" and r["reason"].startswith("prior-day inputs") and \
                    f"{name}_History.csv" in r["reason"], r["reason"]
                f.write_text(saved)
        finally:
            globals().update(real)
        assert not (tmp / "nge.csv").exists()
        r = partc(ctx2)
        pc = r["part_c"]
        assert pc["status"] == "run", pc.get("reason")
        assert "part_a" in r and "part_b" in r and "## Part C" in (out / OUT_MD).read_text()
        assert pc["checks"]["coverage"]["share"] >= 0.95 and pc["counts"]["oi_records_at_or_after_cutoff"] > 0
        assert pc["fallback_days_in_panel"] == 1 and pc["C2"]["verdict"] and pc["C1"]["regression"]["n"] > 30
        with open(tmp / "nge.csv", newline="") as fh:
            nge = list(csv.DictReader(fh))
        assert len(nge) == len(P.dates) and {x["N"] for x in nge} <= {"0.0", "1.0", ""}
        assert sum(1 for x in nge if x["N"] == "") == len(P.dates) - pc["checks"]["coverage"]["days_with_N"]
        # coverage below 95%: drop 10% of the files (logged as empty, so the pull counts as finished)
        dropped = [d for d in days if keep[d]][::10]
        for d in dropped:
            (tmp / "oi" / f"{d}.csv.gz").unlink()
        (tmp / "nge.csv").unlink()
        r = partc(ctx2)["part_c"]
        assert r["reason"] == (f"budget: download incomplete: {len(dropped)} days not yet downloaded "
                               f"(first {dropped[0]})"), r["reason"]
        spend.write_text(spend.read_text() + "".join(f"t,{OI_SCHEMA_FULL_DAY},{d},0,0.01,0,{OI_EMPTY_LABEL}\n"
                                                     for d in dropped))
        r = partc(ctx2)["part_c"]
        assert r["status"] == "not run" and r["reason"].startswith("coverage") and not (tmp / "nge.csv").exists()
        assert r["checks"]["budget"]["days_logged_without_open_interest"] == len(dropped)
        assert "Part C not run (coverage" in (out / OUT_MD).read_text()
        assert not (out / SEL_JSON).stat().st_mode & 0o222                      # partc never touched the selection
        assert sha256_file(out / SEL_JSON) == (out / SEL_SHA).read_text().split()[0]
    return ("synthetic D1/days/OI/VIX files: discover reads no 2021 row, refuses an empty or < 100-day sample "
            "without writing, freezes once and refuses again before reading data; run without a selection refuses; "
            "run/partc refuse an empty panel or an empty 2013-2020 or 2021-2026 sample, a one-day holdout runs; a "
            "failed reproduction stops Part B (Part A runs); a matching reproduction runs the confirmation and "
            "recomputes the frozen discovery; an edited script refuses; partc is not run, with gamma never "
            "computed, for an unfinished pull, a missing log, no files (pull finished), a bad symbol, spend over "
            "$100, bad or missing closes and VIX/VIX9D/VIX3M files or columns; not run for coverage < 95%; runs "
            "(C1, C2, nge_daily.csv) when the checks pass")


def selftest() -> None:
    print("selftest (synthetic data only)")
    for name, fn in (("inference", _st_inference), ("rolling windows and rules", _st_rolling_and_rules),
                     ("Part A", _st_part_a), ("Part B selection", _st_part_b_core), ("pricing and reproduction",
                                                                                    _st_pricing),
                     ("gates and selection file", _st_gates_and_selection), ("OSI, settlement, open interest",
                                                                             _st_osi_settlement_oi),
                     ("gamma and NGE*", _st_gamma_nge), ("budget gate and Part C inputs", _st_budget_and_inputs),
                     ("Part C tests", _st_part_c_core),
                     ("end to end", _st_end_to_end)):
        print(f"  {name}: {fn()}")
    print("selftest: all checks passed")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "discover":
        p = discover()
        print(f"discovery 2013-04-01 .. 2020-12-31 ({p['discovery_sample']['n_days']} days): pick {p['pick']}")
        for k in RULES:
            e = p["eligibility"][k]
            print(f"  {k}: eligible {e['eligible']}  t {e['t']}  p {e['p']}  {e['criteria']}")
        print(f"wrote {HERE / SEL_JSON} and {HERE / SEL_SHA} (read-only, never rewritten)")
    elif cmd == "run":
        r = run()
        print(f"Part A: {r['part_a']['primary']['verdict']}; secondary: {r['part_a']['secondary']['verdict']}")
        b = r["part_b"]
        print(f"Part B: {b['status']}" + (f"; {b['confirmation']['verdict']}" if b["status"] == "run" else ""))
        print(f"wrote {HERE / OUT_JSON} and {HERE / OUT_MD}")
    elif cmd == "partc":
        c = partc()["part_c"]
        if c["status"] != "run":
            print(f"Part C not run ({c['reason']})")
        else:
            print(f"Part C: C1 {c['C1']['verdict']}; C2 {c['C2']['verdict']}")
            print(f"wrote {NGE_CSV}, {HERE / OUT_JSON}, {HERE / OUT_MD}")
    else:
        raise SystemExit("usage: momentum.py selftest | discover | run | partc")
