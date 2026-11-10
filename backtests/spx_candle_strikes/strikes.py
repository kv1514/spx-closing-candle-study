"""Which strike to buy on a 15:50 strong-body signal: a strike ladder, descriptive only.

Pre-registration: preregistration/spx_candle_strike_ladder.md (an addendum to spx_close_candle_scan.md and
spx_candle_forward_options.md). `run` refuses to read any data unless that file exists and its SHA-256 is in
preregistration/LEDGER.md.

  Part 1  real Robinhood 0DTE prices on forward days: the 15:51 entry and the official close (exit A) or the
          15:59 bar (exit B), for 9 strikes from 20 points in the money to 20 points out of the money.
  Part 2  the backtest's 644 strong-body days (D1, 2021-01-01 .. 2026-10-20) with every strike priced by a
          Bachelier model calibrated on the Robinhood option prices that exist. A model, not observed P&L.

Usage (from /Users/kv15/trading):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_strikes/strikes.py selftest
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_strikes/strikes.py run

Outputs (rebuilt from scratch on each run): data/spx_1549/forward/strikes_forward_log.csv,
backtests/spx_candle_strikes/results.json, backtests/spx_candle_strikes/RESULTS.md.
Nothing here is a trading recommendation.
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import norm

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
PREREG = ROOT / "preregistration" / "spx_candle_strike_ladder.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
SPX_ROOT = ROOT / "data" / "spx_1549"
OUT_CSV = SPX_ROOT / "forward" / "strikes_forward_log.csv"
OUT_JSON = HERE / "results.json"
OUT_MD = HERE / "RESULTS.md"
SCAN_PY = ROOT / "backtests" / "spx_candle_scan" / "scan.py"
HOLDOUT_JSON = ROOT / "backtests" / "spx_candle_scan" / "holdout.json"
CANDIDATES_JSON = ROOT / "backtests" / "spx_candle_scan" / "candidates.json"
OPTIONS_PY = ROOT / "analysis" / "candle_1550_options_forward.py"
CHUNK_SPX = [SPX_ROOT / f"d2_chunk_{c}_spx_1m.csv" for c in "BC"]
CHUNK_OPT_1M = [SPX_ROOT / f"d2_chunk_{c}_options_1m.csv" for c in "BC"]
CHUNK_OPT_10M = [SPX_ROOT / f"d2_chunk_{c}_options_10m.csv" for c in "BC"]

OFFSETS = (20, 15, 10, 5, 0, -5, -10, -15, -20)    # + = in the money in the trade's direction
HALF_SPREAD = 0.10
FEES = (0.09, 0.74)
MULT = 100.0
STEP = 5.0
HOLDOUT = ("2021-01-01", "2026-10-20")
HEADLINE = "F2_1m_1550_strong_body"
FORWARD_SIGNALS = (("F2_1m_1550_strong_body", "sb"), ("F1_1m_15:50", "f1"))
EXPECTED_TRADES = 644
PREREG_MEAN_ABS_MOVE = 8.599455
PREREG_LEVEL = 7709.58
SELF_CHECK_TOL_USD = 0.01
MIN_RETURNS = 300
MIN_FIT_CONTRACTS = 6
MIN_SKEW_RATIOS = 5
SIGMA_BOUNDS = (0.1, 100.0)
WIDTH = 30.0
SQRT_REMAINING = 3.0          # sqrt(9 one-minute bars, 15:51 .. 15:59)
SQRT_REMAINING_10M = math.sqrt(10.0)
PHI0 = 1.0 / math.sqrt(2.0 * math.pi)


def label(o: int) -> str:
    return "ATM" if o == 0 else (f"ITM{o}" if o > 0 else f"OTM{-o}")


def strike_for(s):
    """scan.py's rounding: floor(S / 5 + 0.5) x 5 (works on floats and arrays)."""
    return np.floor(np.asarray(s, float) / STEP + 0.5) * STEP


def contract_for(direction: int, k_atm: float, o: int) -> tuple[str, float]:
    """Up trade: call at K_atm - o. Down trade: put at K_atm + o. o > 0 is in the money."""
    return ("call", k_atm - o) if direction > 0 else ("put", k_atm + o)


def bachelier(is_call, S, K, sigma):
    """Normal-model option price, no rates; sigma = std (index points) of the move to expiry."""
    is_call, S, K, sigma = np.broadcast_arrays(np.asarray(is_call, bool), np.asarray(S, float),
                                               np.asarray(K, float), np.asarray(sigma, float))
    d = (S - K) / sigma
    call = (S - K) * norm.cdf(d) + sigma * norm.pdf(d)
    out = np.where(is_call, call, call - (S - K))
    return out if out.ndim else float(out)


def intrinsic(is_call, K, X):
    is_call, K, X = np.broadcast_arrays(np.asarray(is_call, bool), np.asarray(K, float), np.asarray(X, float))
    out = np.where(is_call, np.maximum(X - K, 0.0), np.maximum(K - X, 0.0))
    return out if out.ndim else float(out)


def realized_vol(closes) -> tuple[float | None, int]:
    """RMS of one-minute log returns between consecutive bar closes (bars 09:30 .. 15:50 -> returns 09:31 ..
    15:50), only where both bars exist. Returns (rv, n_returns); rv is None below MIN_RETURNS."""
    c = np.asarray(closes, float)
    ok = np.isfinite(c[1:]) & np.isfinite(c[:-1]) & (c[1:] > 0) & (c[:-1] > 0)
    r = np.log(c[1:][ok] / c[:-1][ok])
    n = int(r.size)
    return (float(np.sqrt(np.mean(r * r))) if n >= MIN_RETURNS else None), n


def fit_sigma(S: float, quotes: list) -> float | None:
    """quotes: [(is_call, K, price)]. Least-squares Bachelier sigma in SIGMA_BOUNDS."""
    if len(quotes) < MIN_FIT_CONTRACTS:
        return None
    ic = np.array([q[0] for q in quotes], bool)
    K = np.array([q[1] for q in quotes], float)
    P = np.array([q[2] for q in quotes], float)
    res = minimize_scalar(lambda s: float(np.sum((bachelier(ic, S, K, s) - P) ** 2)),
                          bounds=SIGMA_BOUNDS, method="bounded", options={"xatol": 1e-7})
    return float(res.x)


def otm_quotes(S: float, prices: dict) -> list:
    """prices: {(kind, K): price}. Calls K >= K_atm and puts K <= K_atm, within K_atm +- 30."""
    k_atm = float(strike_for(S))
    out = []
    for (kind, K), p in sorted(prices.items()):
        if p is None or not p > 0 or abs(K - k_atm) > WIDTH + 1e-9:
            continue
        if (kind == "call" and K >= k_atm - 1e-9) or (kind == "put" and K <= k_atm + 1e-9):
            out.append((kind == "call", float(K), float(p)))
    return out


def minutes_0930_1550() -> list[str]:
    return [f"{(570 + i) // 60:02d}:{(570 + i) % 60:02d}" for i in range(381)]


def wilson_free_share(x) -> float | None:
    x = np.asarray(x, float)
    return float(np.mean(x > 0)) if x.size else None


# ------------------------------------------------------------------------------------------------
# gate and module loading
# ------------------------------------------------------------------------------------------------
def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def check_gate(prereg: Path = PREREG, ledger: Path = LEDGER) -> str:
    import hashlib
    if not Path(prereg).exists():
        raise SystemExit(f"refusing to run: {prereg} does not exist (move PREREG_DRAFT.md there and add its "
                         f"SHA-256 to {ledger} first)")
    h = hashlib.sha256(Path(prereg).read_bytes()).hexdigest()
    if h not in Path(ledger).read_text():
        raise SystemExit(f"refusing to run: SHA-256 of {Path(prereg).name} ({h}) is not in {ledger}")
    return h


# ------------------------------------------------------------------------------------------------
# Robinhood data
# ------------------------------------------------------------------------------------------------
def rh_spx_bars(day: str, cfo) -> dict:
    """{HH:MM: (open, close)} of real Robinhood SPX one-minute bars on `day` (live_* file, else chunk CSVs)."""
    out = {}
    p = SPX_ROOT / f"live_{day}" / "spx_1m.json"
    if p.exists():
        for b in json.loads(p.read_text())["data"]["results"][0]["bars"]:
            if b.get("interpolated"):
                continue
            d, hm = cfo.et_hhmm(b["begins_at"])
            if d == day:
                out[hm] = (float(b["open_value"]), float(b["close_value"]))
        return out
    for f in CHUNK_SPX:
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["date"] == day and r["interpolated"] != "True":
                    out[r["time_et"]] = (float(r["open"]), float(r["close"]))
    return out


def chunk_options(files, interval_minutes: int) -> dict:
    """{date: {(kind, K): {HH:MM: {open_price, close_price}}}} of real bars from the d2 chunk CSVs."""
    out: dict = {}
    for f in files:
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["interpolated"] == "True":
                    continue
                kind, K = r["type"], float(r["strike"])
                occ = r["occ_symbol"].replace(" ", "")
                d = r["date"]
                if occ != f"SPXW{d[2:4]}{d[5:7]}{d[8:10]}{'C' if kind == 'call' else 'P'}{round(K * 1000):08d}":
                    raise SystemExit(f"{f}: {occ} does not match {d} {kind} {K}")
                out.setdefault(d, {}).setdefault((kind, K), {})[r["time_et"]] = {
                    "open_price": r["open"], "close_price": r["close"]}
    return out


def one_minute_days(cfo) -> dict:
    """{date: opts} for every date with real 15:51 one-minute option bars (live_* minute files and the d2
    chunk one-minute CSVs; a live_* folder wins if both exist)."""
    days = {}
    for d, opts in chunk_options(CHUNK_OPT_1M, 1).items():
        if any("15:51" in bars for bars in opts.values()):
            days[d] = opts
    for folder in sorted(SPX_ROOT.glob("live_*")):
        day = folder.name[5:]
        if not list(folder.glob("options*.json")):
            continue
        opts, avail = cfo.load_day_options(folder, day)
        if avail == "minute" and any("15:51" in bars for bars in opts.values()):
            days[day] = opts
    return dict(sorted(days.items()))


# ------------------------------------------------------------------------------------------------
# calibration
# ------------------------------------------------------------------------------------------------
def calibrate(cfo, P, scan) -> dict:
    mins = minutes_0930_1550()
    d1_index = {d: i for i, d in enumerate(P.dates)}

    def rv_d1(day):
        i = d1_index.get(day)
        return realized_vol(P.C[i, :scan.I1550 + 1]) if i is not None else (None, 0)

    # steps 1, 2, 4: one-minute days
    c1, ratios = [], {(o, side): [] for o in OFFSETS for side in ("call", "put")}
    for day, opts in one_minute_days(cfo).items():
        bars = rh_spx_bars(day, cfo)
        if "15:51" not in bars:
            c1.append({"date": day, "used": False, "why": "no real SPX 15:51 bar"})
            continue
        S = bars["15:51"][0]
        prices = {key: cfo.price(b, "15:51", "open_price", allow_zero=False) for key, b in opts.items()}
        q = otm_quotes(S, prices)
        sigma = fit_sigma(S, q)
        rv, n_ret = realized_vol([bars.get(m, (np.nan, np.nan))[1] for m in mins])
        row = {"date": day, "S_1551_open": S, "n_fit_contracts": len(q), "sigma_pts": sigma,
               "sigma_bps": sigma / S * 1e4 if sigma else None, "rv_rh": rv, "n_returns": n_ret,
               "k_rh": sigma / (rv * SQRT_REMAINING * S) if sigma and rv else None,
               "used": sigma is not None}
        if sigma is None:
            row["why"] = f"only {len(q)} out-of-the-money contracts with a real 15:51 bar"
        else:
            k_atm = float(strike_for(S))
            fit_rmse = math.sqrt(np.mean([(bachelier(ic, S, K, sigma) - p) ** 2 for ic, K, p in q]))
            row["fit_rmse_pts"] = fit_rmse
            for o in OFFSETS:
                for side, dirn in (("call", 1), ("put", -1)):
                    kind, K = contract_for(dirn, k_atm, o)
                    p = prices.get((kind, K))
                    if p:
                        ratios[(o, side)].append(p / bachelier(kind == "call", S, K, sigma))
        c1.append(row)
    used = [r for r in c1 if r["used"] and r["k_rh"] is not None]
    k_rh = float(np.median([r["k_rh"] for r in used])) if used else None
    fitted = [r for r in c1 if r["used"]]
    sigma_bps_c1 = float(np.median([r["sigma_bps"] for r in fitted])) if fitted else None

    # step 3: Robinhood vs D1 realized volatility on overlap days
    overlap = []
    chunk_days = set()
    for f in CHUNK_SPX:
        with open(f, newline="") as fh:
            chunk_days |= {r["date"] for r in csv.DictReader(fh) if r["interpolated"] != "True"}
    for day in sorted(chunk_days):
        rv1, n1 = rv_d1(day)
        if rv1 is None:
            continue
        bars = rh_spx_bars(day, cfo)
        rv2, n2 = realized_vol([bars.get(m, (np.nan, np.nan))[1] for m in mins])
        if rv2 is None:
            continue
        overlap.append({"date": day, "rv_rh": rv2, "rv_d1": rv1, "ratio": rv2 / rv1})
    c = float(np.median([r["ratio"] for r in overlap])) if overlap else None

    # step 4: skew factors
    skew = {}
    for o in OFFSETS:
        vals = ratios[(o, "call")] + ratios[(o, "put")]
        skew[o] = {"f": float(np.median(vals)) if len(vals) >= MIN_SKEW_RATIOS else 1.0, "n": len(vals),
                   "set_to_1": len(vals) < MIN_SKEW_RATIOS,
                   "median_call": float(np.median(ratios[(o, "call")])) if ratios[(o, "call")] else None,
                   "median_put": float(np.median(ratios[(o, "put")])) if ratios[(o, "put")] else None}

    # variant (d): 10-minute days, price = the 15:40 bar's close, S = SPX 15:49 close
    tenmin = []
    for day, opts in chunk_options(CHUNK_OPT_10M, 10).items():
        rv1, _ = rv_d1(day)
        bars = rh_spx_bars(day, cfo)
        if rv1 is None or "15:49" not in bars:
            continue
        S = bars["15:49"][1]
        prices = {key: cfo.price(b, "15:40", "close_price", allow_zero=False) for key, b in opts.items()}
        q = otm_quotes(S, prices)
        sigma = fit_sigma(S, q)
        if sigma is None:
            continue
        tenmin.append({"date": day, "S_1549_close": S, "n_fit_contracts": len(q), "sigma_pts": sigma,
                       "rv_d1": rv1, "k10": sigma / (rv1 * SQRT_REMAINING_10M * S)})
    k10 = float(np.median([r["k10"] for r in tenmin])) if tenmin else None
    return {"one_minute_days": c1, "k_rh": k_rh, "sigma_bps_median_c1": sigma_bps_c1,
            "rv_overlap_days": overlap, "c_rv_rh_over_d1": c,
            "k_d1": k_rh * c if k_rh is not None and c is not None else None,
            "skew": {label(o): v for o, v in skew.items()}, "skew_f": {o: v["f"] for o, v in skew.items()},
            "ten_minute_days": tenmin, "k10_d1": k10}


# ------------------------------------------------------------------------------------------------
# Part 2: modelled 2021-2026 sample
# ------------------------------------------------------------------------------------------------
def holdout_constants() -> dict:
    eco = json.loads(HOLDOUT_JSON.read_text())["economics"]["candidates"][HEADLINE]["at_last_level"]
    level = float(eco["units"].rsplit(" ", 1)[-1])
    if abs(level - PREREG_LEVEL) > 1e-9:
        raise SystemExit(f"holdout.json level {level} is not the registered {PREREG_LEVEL}")
    mam = float(eco["realized_move_fair_straddle"])
    if abs(mam - PREREG_MEAN_ABS_MOVE) > 1e-5:
        raise SystemExit(f"holdout.json mean |move| {mam} is not the registered {PREREG_MEAN_ABS_MOVE}")
    return {"level": level, "mean_abs_move": mam, "n_trades": int(eco["n_trades"]),
            "atm_pnl_fee_0.09": float(eco["fee_cases"]["fee_0.09"]["mean_pnl_usd_per_trade_at_observed_hits"])}


def strong_body_trades(scan, P) -> dict:
    cands = json.loads(CANDIDATES_JSON.read_text())["candidates"]
    dirn = next(c["direction"] for c in cands if c["feature"] == HEADLINE)
    sig = dirn * np.asarray(scan.spec_by_id(HEADLINE).signal(P), float)
    S = P.O[:, scan.I1551]
    X = P.C[:, scan.I1559]
    trade = np.isfinite(sig) & np.isfinite(S) & np.isfinite(X) & (sig != 0)
    n = int(trade.sum())
    if n != EXPECTED_TRADES:
        raise SystemExit(f"strong-body trades: {n}, the backtest has {EXPECTED_TRADES}; stopping")
    rv = np.array([realized_vol(P.C[i, :scan.I1550 + 1])[0] or np.nan for i in np.flatnonzero(trade)])
    return {"dates": P.dates[trade], "d": sig[trade].astype(int), "S": S[trade], "X": X[trade], "rv": rv}


def model_ladder(T: dict, L: float, sigma, f: dict, h: float = HALF_SPREAD, use_rounding: bool = True) -> dict:
    """Per-offset arrays of model price, P&L (both fees) and return on premium for the trades in T."""
    lam = L / T["S"]
    Xp = L + lam * (T["X"] - T["S"])
    k_atm = L + lam * (strike_for(T["S"]) - T["S"]) if use_rounding else np.full_like(Xp, L)
    is_call = T["d"] > 0
    sigma = np.broadcast_to(np.asarray(sigma, float), Xp.shape)
    ok = np.isfinite(sigma)
    out = {}
    for o in OFFSETS:
        K = k_atm - T["d"] * o
        price = f[o] * bachelier(is_call, L, K, np.where(ok, sigma, 1.0))
        cost = price + h
        pay = intrinsic(is_call, K, Xp)
        r = {"ok": ok, "price": price, "cost": cost}
        for fee in FEES:
            r[f"pnl_{fee:.2f}"] = MULT * (pay - cost) - fee
        r["ret"] = r["pnl_0.09"] / (MULT * cost + FEES[0])
        out[o] = r
    return out


def ladder_stats(lad: dict, scan, mask=None) -> dict:
    base = lad[0]
    out = {}
    for o in OFFSETS:
        r = lad[o]
        sel = r["ok"] & base["ok"] & (mask if mask is not None else True)
        p9 = r["pnl_0.09"][sel]
        diff = p9 - base["pnl_0.09"][sel]
        nw = scan.nw_mean_test(p9) if p9.size > 2 else {"t": None}
        nwd = scan.nw_mean_test(diff) if o != 0 and diff.size > 2 else {"t": None}
        out[label(o)] = {
            "n": int(sel.sum()), "mean_price": float(r["price"][sel].mean()),
            "mean_pnl_fee_0.09": float(p9.mean()), "mean_pnl_fee_0.74": float(r["pnl_0.74"][sel].mean()),
            "nw_t": nw["t"], "share_pnl_positive": wilson_free_share(p9),
            "mean_return_on_premium": float(r["ret"][sel].mean()),
            "median_return_on_premium": float(np.median(r["ret"][sel])),
            "diff_vs_atm_mean": float(diff.mean()) if o != 0 else 0.0, "diff_vs_atm_nw_t": nwd["t"]}
    best_usd = max(out, key=lambda k: out[k]["mean_pnl_fee_0.09"])
    best_ret = max(out, key=lambda k: out[k]["mean_return_on_premium"])
    return {"by_offset": out, "best_mean_pnl": best_usd, "best_mean_return_on_premium": best_ret}


def part2(scan, P, cal: dict, T: dict | None = None, hc: dict | None = None) -> dict:
    """T and hc are injected only by the self-test; a real run computes them from D1 and holdout.json."""
    hc = hc or holdout_constants()
    L = hc["level"]
    T = T if T is not None else strong_body_trades(scan, P)
    f = cal["skew_f"]
    f1 = {o: 1.0 for o in OFFSETS}
    sig_c = hc["mean_abs_move"] / (2 * PHI0)

    # self-check: variant (c) with K = S exactly, offset 0, $0.10 and the $0.09 fee = the backtest's ATM P&L
    chk = model_ladder(T, L, sig_c, f1, use_rounding=False)[0]["pnl_0.09"].mean()
    if abs(chk - hc["atm_pnl_fee_0.09"]) > SELF_CHECK_TOL_USD:
        raise SystemExit(f"self-check failed: variant (c) ATM {chk:.4f} vs backtest {hc['atm_pnl_fee_0.09']:.4f}")

    k = cal["k_d1"]
    sig_a = k * T["rv"] * SQRT_REMAINING * L if k is not None else np.full(len(T["S"]), np.nan)
    variants = {
        "a_calibrated": (sig_a, f, HALF_SPREAD),
        "b_constant_vol": (np.full(len(T["S"]), cal["sigma_bps_median_c1"] / 1e4 * L)
                           if cal["sigma_bps_median_c1"] else np.full(len(T["S"]), np.nan), f, HALF_SPREAD),
        "c_realized_move_fair": (np.full(len(T["S"]), sig_c), f1, HALF_SPREAD),
        "d_ten_minute_k": (cal["k10_d1"] * T["rv"] * SQRT_REMAINING * L if cal["k10_d1"] else
                           np.full(len(T["S"]), np.nan), f, HALF_SPREAD),
        "a_half_spread_0.05": (sig_a, f, 0.05),
        "a_half_spread_0.20": (sig_a, f, 0.20),
        "a_k_x0.75": (sig_a * 0.75, f, HALF_SPREAD),
        "a_k_x1.25": (sig_a * 1.25, f, HALF_SPREAD),
        "a_no_skew": (sig_a, f1, HALF_SPREAD),
    }
    res = {}
    for name, (sig, ff, h) in variants.items():
        res[name] = ladder_stats(model_ladder(T, L, sig, ff, h), scan)
    lad_a = model_ladder(T, L, sig_a, f)
    years = np.array([int(d[:4]) for d in T["dates"]])
    periods = {"2021_2022": ladder_stats(lad_a, scan, years <= 2022),
               "2023_2026": ladder_stats(lad_a, scan, years >= 2023)}
    sig_bps = sig_a / L * 1e4
    return {"level": L, "n_trades": int(len(T["S"])), "n_with_rv": int(np.isfinite(T["rv"]).sum()),
            "first": str(T["dates"][0]), "last": str(T["dates"][-1]),
            "share_right": float(np.mean(T["d"] * (T["X"] - T["S"]) > 0)),
            "self_check_c_atm_pnl": float(chk), "backtest_atm_pnl": hc["atm_pnl_fee_0.09"],
            "sigma_c_pts": sig_c,
            "sigma_a_bps": {"median": float(np.nanmedian(sig_bps)), "p10": float(np.nanpercentile(sig_bps, 10)),
                            "p90": float(np.nanpercentile(sig_bps, 90))},
            "variants": res, "periods_a": periods}


# ------------------------------------------------------------------------------------------------
# Part 1: real prices on forward days
# ------------------------------------------------------------------------------------------------
COLUMNS = ["date", "signal_name", "signal", "offset", "status", "kind", "strike", "S_1551_open", "settle",
           "settle_source", "provisional", "entry_open_1551", "cost_incl_half_spread", "exit_a_value",
           "pnl_a_fee_0.09", "pnl_a_fee_0.74", "return_on_premium_a", "exit_b_status", "exit_b_close_1559",
           "pnl_b_fee_0.09", "pnl_b_fee_0.74"]


def part1(cfo, spx_root: Path = SPX_ROOT) -> dict:
    directions = cfo.load_forward_module().frozen_directions()["directions"]
    closes, conflicts = cfo.official_closes(spx_root)
    rows, market = [], []
    for lr in cfo.read_log():
        day = lr["date"]
        folder = spx_root / f"live_{day}"
        opts, avail = cfo.load_day_options(folder, day) if folder.exists() else (None, "no_option_files")
        complete = cfo.completion_evidence(folder, day)
        S = float(lr["entry_1551_open"])
        k_atm = float(strike_for(S))
        settle, src = closes.get(day, (None, None))
        provisional = settle is None
        settle_used = float(lr["exit_1559_close"]) if provisional else settle
        if opts is not None and not provisional:
            for o in OFFSETS:
                for side, dirn in (("call", 1), ("put", -1)):
                    kind, K = contract_for(dirn, k_atm, o)
                    E = cfo.price(opts.get((kind, K)), "15:51", "open_price", allow_zero=False)
                    if E is not None:
                        market.append({"date": day, "offset": o, "side": side,
                                       "pnl_a_fee_0.09": MULT * (cfo.intrinsic(kind, K, settle_used) - E -
                                                                 HALF_SPREAD) - FEES[0]})
        for name, short in FORWARD_SIGNALS:
            s = int(lr[f"{short}_signal"]) * directions[name]
            if s == 0:
                continue
            for o in OFFSETS:
                kind, K = contract_for(s, k_atm, o)
                r = {"date": day, "signal_name": name, "signal": s, "offset": label(o), "kind": kind, "strike": K,
                     "S_1551_open": S, "settle": settle_used, "settle_source": src or "provisional_1559_close",
                     "provisional": provisional}
                if opts is None:
                    r["status"] = avail
                elif (kind, K) not in opts:
                    r["status"] = "strike_not_collected"
                else:
                    bars = opts[(kind, K)]
                    E = cfo.price(bars, "15:51", "open_price", allow_zero=False)
                    if E is None:
                        r["status"] = "entry_bar_missing"
                    else:
                        r["status"] = "traded"
                        cost = E + HALF_SPREAD
                        va = cfo.intrinsic(kind, K, settle_used)
                        r.update({"entry_open_1551": E, "cost_incl_half_spread": cost, "exit_a_value": va})
                        for fee in FEES:
                            r[f"pnl_a_fee_{fee:.2f}"] = MULT * (va - cost) - fee
                        r["return_on_premium_a"] = r["pnl_a_fee_0.09"] / (MULT * cost + FEES[0])
                        X = cfo.price(bars, "15:59", "close_price", allow_zero=True)
                        if not complete:
                            r["exit_b_status"] = "no_completion_evidence"
                        elif X is None:
                            r["exit_b_status"] = "exit_bar_missing"
                        else:
                            r["exit_b_status"] = "ok"
                            r["exit_b_close_1559"] = X
                            for fee in FEES:
                                r[f"pnl_b_fee_{fee:.2f}"] = MULT * (X - HALF_SPREAD - cost) - 2 * fee
                rows.append(r)

    def tally(vals):
        v = [x for x in vals if x is not None]
        return {"trades": len(v), "wins": sum(1 for x in v if x > 0), "total_usd": round(sum(v), 2) if v else None,
                "mean_usd": round(sum(v) / len(v), 2) if v else None}

    tallies = {}
    for name, _ in FORWARD_SIGNALS:
        t = {}
        for o in OFFSETS:
            sel = [r for r in rows if r["signal_name"] == name and r["offset"] == label(o) and r["status"] == "traded"
                   and not r["provisional"]]
            selb = [r for r in sel if r.get("exit_b_status") == "ok"]
            t[label(o)] = {"exit_a_fee_0.09": tally([r["pnl_a_fee_0.09"] for r in sel]),
                           "exit_a_fee_0.74": tally([r["pnl_a_fee_0.74"] for r in sel]),
                           "exit_b_fee_0.09": tally([r["pnl_b_fee_0.09"] for r in selb]),
                           "mean_return_on_premium_a": (round(float(np.mean([r["return_on_premium_a"] for r in sel])), 4)
                                                        if sel else None)}
        tallies[name] = t
    mk = {}
    for o in OFFSETS:
        for side in ("call", "put"):
            v = [m["pnl_a_fee_0.09"] for m in market if m["offset"] == o and m["side"] == side]
            mk[f"{label(o)}_{side}"] = {"days": len(v), "mean_pnl_a_fee_0.09": round(float(np.mean(v)), 2) if v else None}
    return {"rows": rows, "tallies": tallies, "market_check": mk, "directions": directions,
            "official_close_conflicts": conflicts,
            "forward_days": sorted({r["date"] for r in cfo.read_log()})}


# ------------------------------------------------------------------------------------------------
# rendering
# ------------------------------------------------------------------------------------------------
def fm(x, nd=2, sign=False, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if pct:
        return f"{x * 100:+.0f}%" if sign else f"{x * 100:.0f}%"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


def render_md(res: dict) -> str:
    p1, p2, cal = res["part1"], res["part2"], res["calibration"]
    a = p2["variants"]["a_calibrated"]
    L = []
    w = L.append
    w("# Which strike to buy on the 15:50 strong-body signal")
    w("")
    w("Rebuilt by `backtests/spx_candle_strikes/strikes.py` from `preregistration/spx_candle_strike_ladder.md`; "
      "do not edit by hand. Descriptive research, not a trading recommendation.")
    w("")
    w("**How to read the strikes.** ITM20 = 20 points in the money in the trade's direction, OTM20 = 20 points "
      "out of the money. With SPX at 7700 and an up signal: ITM20 = the 7680 call, ATM = 7700, OTM20 = the 7720 "
      "call. With a down signal the same labels are puts: ITM20 = the 7720 put, OTM20 = the 7680 put.")
    w("")
    w("## Modelled 2021-2026 (the backtest's strong-body days, every strike priced by a model)")
    w("")
    w(f"{p2['n_trades']} trades, {p2['first']} to {p2['last']}, {fm(p2['share_right'], pct=True)} right. Moves "
      f"rescaled to SPX {p2['level']:.2f}. Prices are a Bachelier model calibrated on Robinhood option prices "
      f"from Oct-Nov 2026 (variant a), not real fills. The outcome is the CFD at 15:59, not the settlement. "
      f"Every strike pays the same $0.10 half-spread and a $0.09 fee.")
    w("")
    w("| Strike | Model price | Mean P&L / contract | t | Profitable | Mean return on premium | Median return | vs ATM (t) |")
    w("|---|---|---|---|---|---|---|---|")
    for k, v in a["by_offset"].items():
        w(f"| {k} | ${fm(v['mean_price'] * 100, 0)} | {fm(v['mean_pnl_fee_0.09'], 2, True)} | {fm(v['nw_t'])} | "
          f"{fm(v['share_pnl_positive'], pct=True)} | {fm(v['mean_return_on_premium'], sign=True, pct=True)} | "
          f"{fm(v['median_return_on_premium'], sign=True, pct=True)} | "
          f"{'—' if k == 'ATM' else fm(v['diff_vs_atm_mean'], 2, True) + ' (' + fm(v['diff_vs_atm_nw_t']) + ')'} |")
    w("")
    w("Best by mean $ per contract and by mean return on premium, per variant (a description of the model):")
    w("")
    w("| Variant | Best $ / contract | Best return on premium | " + " | ".join(label(o) for o in OFFSETS) + " |")
    w("|---|---|---|" + "---|" * len(OFFSETS))
    for name, v in p2["variants"].items():
        w(f"| {name} | {v['best_mean_pnl']} | {v['best_mean_return_on_premium']} | "
          + " | ".join(fm(v["by_offset"][label(o)]["mean_pnl_fee_0.09"], 0, True) for o in OFFSETS) + " |")
    w("")
    w("Mean return on premium by variant:")
    w("")
    w("| Variant | " + " | ".join(label(o) for o in OFFSETS) + " |")
    w("|---|" + "---|" * len(OFFSETS))
    for name, v in p2["variants"].items():
        w(f"| {name} | " + " | ".join(fm(v["by_offset"][label(o)]["mean_return_on_premium"], sign=True, pct=True)
                                       for o in OFFSETS) + " |")
    w("")
    w("Variant (a) by period (mean P&L per contract, $0.09 fee):")
    w("")
    w("| Period | n | " + " | ".join(label(o) for o in OFFSETS) + " |")
    w("|---|---|" + "---|" * len(OFFSETS))
    for per, v in p2["periods_a"].items():
        w(f"| {per} | {v['by_offset']['ATM']['n']} | "
          + " | ".join(fm(v["by_offset"][label(o)]["mean_pnl_fee_0.09"], 0, True) for o in OFFSETS) + " |")
    w("")
    w("## Calibration")
    w("")
    used = [r for r in cal["one_minute_days"] if r["used"]]
    w(f"- One-minute days used: {len(used)} ({', '.join(r['date'] for r in used)}). Median implied move to the "
      f"close {fm(cal['sigma_bps_median_c1'])} bps of SPX (one standard deviation).")
    w(f"- Implied / realized volatility k (Robinhood) {fm(cal['k_rh'], 3)}; Robinhood / Dukascopy realized "
      f"volatility c {fm(cal['c_rv_rh_over_d1'], 3)} over {len(cal['rv_overlap_days'])} days; k for Dukascopy "
      f"{fm(cal['k_d1'], 3)}. Ten-minute-day version (d): {fm(cal['k10_d1'], 3)} over "
      f"{len(cal['ten_minute_days'])} days.")
    w(f"- Model move to the close, variant (a): median {fm(p2['sigma_a_bps']['median'])} bps "
      f"(10th-90th percentile {fm(p2['sigma_a_bps']['p10'])}-{fm(p2['sigma_a_bps']['p90'])}); variant (c) "
      f"{fm(p2['sigma_c_pts'])} points.")
    w(f"- Self-check: variant (c) at the exact entry price reproduces the backtest's ATM result "
      f"({fm(p2['self_check_c_atm_pnl'], 2, True)} vs {fm(p2['backtest_atm_pnl'], 2, True)} a trade).")
    w("- Skew factors (market price / model price at each strike, median over one-minute days and both sides):")
    w("")
    w("| | " + " | ".join(label(o) for o in OFFSETS) + " |")
    w("|---|" + "---|" * len(OFFSETS))
    w("| f | " + " | ".join(fm(cal["skew"][label(o)]["f"], 3) for o in OFFSETS) + " |")
    w("| ratios | " + " | ".join(str(cal["skew"][label(o)]["n"]) for o in OFFSETS) + " |")
    w("")
    w("## Real prices on forward days")
    w("")
    w(f"Forward days in the log: {len(p1['forward_days'])}. Only days with real one-minute option bars can be "
      "priced. **This is a handful of trades and supports no conclusion.**")
    w("")
    for name, _ in FORWARD_SIGNALS:
        t = p1["tallies"][name]
        w(f"**{name}** (exit A = hold to the official close, exit B = sell at the 15:59 bar; $0.09 fee)")
        w("")
        w("| Strike | Trades | Wins | Exit A total | Exit A mean | Mean return on premium | Exit B total |")
        w("|---|---|---|---|---|---|---|")
        for o in OFFSETS:
            v = t[label(o)]
            ea, eb = v["exit_a_fee_0.09"], v["exit_b_fee_0.09"]
            w(f"| {label(o)} | {ea['trades']} | {ea['wins']} | {fm(ea['total_usd'], 2, True)} | "
              f"{fm(ea['mean_usd'], 2, True)} | {fm(v['mean_return_on_premium_a'], sign=True, pct=True)} | "
              f"{fm(eb['total_usd'], 2, True)} |")
        w("")
    w("Strong-body rows, exit A ($0.09 fee):")
    w("")
    w("| Date | Side | " + " | ".join(label(o) for o in OFFSETS) + " |")
    w("|---|---|" + "---|" * len(OFFSETS))
    for day in p1["forward_days"]:
        rs = {r["offset"]: r for r in p1["rows"] if r["date"] == day and r["signal_name"] == HEADLINE}
        if not rs:
            continue
        any_r = next(iter(rs.values()))
        cells = []
        for o in OFFSETS:
            r = rs.get(label(o))
            cells.append(fm(r.get("pnl_a_fee_0.09"), 0, True) if r and r["status"] == "traded" else
                         (r["status"].replace("_", " ") if r else "—"))
        w(f"| {day} | {any_r['kind']} | " + " | ".join(cells) + " |")
    w("")
    w("Market check, every forward day with minute bars, signal or not: mean exit-A P&L of buying each option "
      "($0.09 fee; negative = the market charged more than the option paid on these days).")
    w("")
    w("| Side | " + " | ".join(label(o) for o in OFFSETS) + " |")
    w("|---|" + "---|" * len(OFFSETS))
    for side in ("call", "put"):
        w(f"| {side} | " + " | ".join(
            fm(p1["market_check"][f"{label(o)}_{side}"]["mean_pnl_a_fee_0.09"], 0, True) + f" ({p1['market_check'][f'{label(o)}_{side}']['days']})"
            for o in OFFSETS) + " |")
    w("")
    w("## Caveats")
    w("")
    big = [k for k, v in cal["skew"].items() if v["f"] > 2]
    if big:
        w(f"- **Note added after the first run (not in the pre-registration):** the skew factors for {', '.join(big)} "
          f"are above 2. On the calm calibration days the normal model prices those strikes near zero while the "
          f"market charges at least the $0.05 tick plus a fat-tail premium, so the ratio is large; multiplying the "
          f"much higher model prices of volatile 2021-2022 days by it overstates what those options would have "
          f"cost. Treat the {', '.join(big)} cells of every variant that uses f (a, b, d and the a_ rows except "
          f"a_no_skew) as unreliable. a_no_skew and (c) use f = 1, which underprices the same strikes, so the "
          f"truth for them lies between and this model cannot settle it.")
    w("- The model is calibrated on a few weeks of 2026 prices; 2021-2022 volatility and option pricing were "
      "different. Variants (b)-(d) and the cost rows show how much the answer depends on that.")
    w("- The same $0.10 half-spread is charged at every strike. Real spreads are wider in the money, and for cheap "
      "out-of-the-money options the $0.05 tick is a large share of the price.")
    w("- Robinhood bars may be trades or marks, and the forward sample is a handful of days.")
    w("- Nothing here is a trading recommendation.")
    return "\n".join(L) + "\n"


def csv_value(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    return v


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def run() -> dict:
    prereg_sha = check_gate()
    scan = load_module("spx_candle_scan_ro", SCAN_PY)
    cfo = load_module("candle_1550_options_forward_ro", OPTIONS_PY)
    P = scan.load_panel(*HOLDOUT)
    cal = calibrate(cfo, P, scan)
    if cal["k_d1"] is None:
        raise SystemExit("calibration failed: no usable one-minute day or overlap day")
    res = {"what": "Strike ladder for the 15:50 strong-body signal, descriptive (spx_candle_strike_ladder.md)",
           "prereg_sha256": prereg_sha, "offsets": [label(o) for o in OFFSETS],
           "half_spread": HALF_SPREAD, "fees": FEES,
           "calibration": {k: v for k, v in cal.items() if k != "skew_f"},
           "part2": part2(scan, P, cal), "part1": part1(cfo)}
    write_outputs(res, cfo.write_atomic)
    return res


def write_outputs(res: dict, write_atomic, out_csv: Path = OUT_CSV, out_json: Path = OUT_JSON,
                  out_md: Path = OUT_MD) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in res["part1"]["rows"]:
        w.writerow({k: csv_value(r.get(k)) for k in COLUMNS})
    write_atomic(out_csv, buf.getvalue())
    out = jsonable(res)
    out["part1"] = {k: v for k, v in out["part1"].items() if k != "rows"}
    write_atomic(out_json, json.dumps(out, indent=1, allow_nan=False) + "\n")
    write_atomic(out_md, render_md(res))


# ------------------------------------------------------------------------------------------------
# self-test on synthetic data (reads no real data)
# ------------------------------------------------------------------------------------------------
def selftest() -> None:
    S, sig = 7700.0, 8.0
    for K in (7680.0, 7700.0, 7712.5, 7720.0):
        c, p = bachelier(True, S, K, sig), bachelier(False, S, K, sig)
        assert abs((c - p) - (S - K)) < 1e-9, "put-call parity"
    assert abs(bachelier(True, S, S, sig) - sig * PHI0) < 1e-12, "ATM price = sigma x n(0)"
    assert contract_for(1, 7700.0, -10) == ("call", 7710.0) and contract_for(1, 7700.0, 20) == ("call", 7680.0)
    assert contract_for(-1, 7700.0, 20) == ("put", 7720.0) and contract_for(-1, 7700.0, -15) == ("put", 7685.0)
    assert float(strike_for(7702.5)) == 7705.0 and float(strike_for(7702.49)) == 7700.0
    # fit recovers sigma from exact prices
    prices = {}
    for K in np.arange(7670.0, 7731.0, 5.0):
        prices[("call", K)] = bachelier(True, 7701.3, K, 6.4)
        prices[("put", K)] = bachelier(False, 7701.3, K, 6.4)
    q = otm_quotes(7701.3, prices)
    assert len(q) == 14, len(q)
    assert abs(fit_sigma(7701.3, q) - 6.4) < 1e-4
    assert fit_sigma(7701.3, q[:3]) is None
    # realized vol on a known series
    rng = np.random.default_rng(1)
    r = rng.normal(0, 2e-4, 380)
    closes = 7000 * np.exp(np.concatenate([[0], np.cumsum(r)]))
    rv, n = realized_vol(closes)
    assert n == 380 and abs(rv - math.sqrt(np.mean(r * r))) < 1e-12
    closes[5:200] = np.nan
    assert realized_vol(closes)[0] is None
    # ladder identity: K = S, f = 1, realized-fair sigma -> mean P&L = 100 (0.5 mean signed move - h) - fee
    n = 4000
    d = rng.choice([-1, 1], n)
    Sx = rng.uniform(3500, 7800, n)
    X = Sx + rng.normal(0.4, 9.0, n) * d * (Sx / 7709.58)
    T = {"S": Sx, "X": X, "d": d, "rv": np.full(n, 1e-4), "dates": np.array(["2022-01-03"] * n)}
    lam = 7709.58 / Sx
    m = lam * (X - Sx)
    sig_c = np.mean(np.abs(m)) / (2 * PHI0)
    lad = model_ladder(T, 7709.58, sig_c, {o: 1.0 for o in OFFSETS}, use_rounding=False)
    expect = MULT * (0.5 * np.mean(d * m) - HALF_SPREAD) - FEES[0]
    assert abs(lad[0]["pnl_0.09"].mean() - expect) < 1e-9, (lad[0]["pnl_0.09"].mean(), expect)
    # deeper ITM costs more, further OTM costs less
    pr = [lad[o]["price"].mean() for o in OFFSETS]
    assert all(pr[i] > pr[i + 1] for i in range(len(pr) - 1))
    # the gate refuses without the file or without the ledger line
    with tempfile.TemporaryDirectory() as tmp:
        pre, led = Path(tmp) / "x.md", Path(tmp) / "LEDGER.md"
        led.write_text("nothing\n")
        for setup in ("missing", "unlisted"):
            if setup == "unlisted":
                pre.write_text("plan\n")
            try:
                check_gate(pre, led)
                raise AssertionError("gate did not refuse")
            except SystemExit:
                pass
        import hashlib
        led.write_text(f"- t  {hashlib.sha256(pre.read_bytes()).hexdigest()}  x.md\n")
        assert check_gate(pre, led)
    selftest_end_to_end(T, d, m)
    print("selftest: all checks passed")


def selftest_end_to_end(T: dict, d, m) -> None:
    """Part 1 with a fake options module, Part 2 with injected trades, then the three outputs in a temp folder."""
    import types
    scan = load_module("spx_candle_scan_ro", SCAN_PY)
    real = load_module("candle_1550_options_forward_ro", OPTIONS_PY)
    S1, settle = 7701.3, 7712.0

    def bars_for(kind, K):
        e = max(bachelier(kind == "call", S1, K, 6.0), 0.05)
        x = intrinsic(kind == "call", K, 7710.0) + 0.3
        return {"15:51": {"open_price": f"{e:.2f}", "close_price": f"{e:.2f}"},
                "15:59": {"open_price": f"{x:.2f}", "close_price": f"{x:.2f}"}}

    opts = {(kind, float(K)): bars_for(kind, K) for kind in ("call", "put") for K in np.arange(7675.0, 7726.0, 5.0)}
    del opts[("call", 7720.0)]                     # up trade OTM20 -> strike_not_collected
    del opts[("call", 7715.0)]["15:51"]            # up trade OTM15 -> entry_bar_missing
    log = [{"date": "2026-10-22", "entry_1551_open": str(S1), "exit_1559_close": "7710.0", "sb_signal": "1",
            "f1_signal": "-1"},
           {"date": "2026-10-23", "entry_1551_open": "7650.2", "exit_1559_close": "7640.0", "sb_signal": "-1",
            "f1_signal": "0"},
           {"date": "2026-10-26", "entry_1551_open": str(S1), "exit_1559_close": "7690.0", "sb_signal": "1",
            "f1_signal": "0"}]
    fake = types.SimpleNamespace(
        load_forward_module=lambda: types.SimpleNamespace(
            frozen_directions=lambda: {"directions": {"F2_1m_1550_strong_body": 1, "F1_1m_15:50": 1}}),
        official_closes=lambda root: ({"2026-10-22": (settle, "live_x/spx_daily.json"),
                                       "2026-10-23": (7641.0, "live_y/spx_daily.json")}, []),
        read_log=lambda: log,
        load_day_options=lambda folder, day: (None, "no_minute_option_bars") if day == "2026-10-23" else (opts, "minute"),
        completion_evidence=lambda folder, day: True,
        price=real.price, intrinsic=real.intrinsic)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for r in log:
            (tmp / f"live_{r['date']}").mkdir()
        p1 = part1(fake, spx_root=tmp)
        rows = p1["rows"]
        assert len(rows) == 36, len(rows)
        st = {(r["date"], r["signal_name"][:2], r["offset"]): r for r in rows}
        atm = st[("2026-10-22", "F2", "ATM")]
        e = float(f"{max(bachelier(True, S1, 7700.0, 6.0), 0.05):.2f}")
        assert atm["kind"] == "call" and atm["strike"] == 7700.0 and atm["status"] == "traded"
        assert abs(atm["pnl_a_fee_0.09"] - (100 * (12.0 - e - 0.10) - 0.09)) < 1e-9
        x = float(f"{10.0 + 0.3:.2f}")
        assert abs(atm["pnl_b_fee_0.74"] - (100 * (x - 0.10 - e - 0.10) - 1.48)) < 1e-9
        assert st[("2026-10-22", "F2", "OTM20")]["status"] == "strike_not_collected"
        assert st[("2026-10-22", "F2", "OTM15")]["status"] == "entry_bar_missing"
        assert st[("2026-10-22", "F1", "ITM20")]["kind"] == "put" and st[("2026-10-22", "F1", "ITM20")]["strike"] == 7720.0
        assert st[("2026-10-23", "F2", "ATM")]["status"] == "no_minute_option_bars"
        assert st[("2026-10-26", "F2", "ATM")]["provisional"] is True
        t = p1["tallies"]["F2_1m_1550_strong_body"]
        assert t["ATM"]["exit_a_fee_0.09"]["trades"] == 1 and t["OTM20"]["exit_a_fee_0.09"]["trades"] == 0
        assert p1["market_check"]["ATM_call"]["days"] == 1 and p1["market_check"]["OTM20_call"]["days"] == 0

        n = len(T["S"])
        T = dict(T, dates=np.array(["2022-03-01"] * (n // 2) + ["2024-03-01"] * (n - n // 2)))
        hc = {"level": PREREG_LEVEL, "mean_abs_move": float(np.mean(np.abs(m))),
              "atm_pnl_fee_0.09": float(MULT * (0.5 * np.mean(d * m) - HALF_SPREAD) - FEES[0])}
        f = {o: 1.0 + 0.02 * abs(o) for o in OFFSETS}
        cal = {"one_minute_days": [{"date": "2026-10-22", "used": True}], "k_rh": 0.9, "sigma_bps_median_c1": 8.0,
               "rv_overlap_days": [{}], "c_rv_rh_over_d1": 1.0, "k_d1": 0.9, "ten_minute_days": [{}], "k10_d1": 1.1,
               "skew": {label(o): {"f": f[o], "n": 7, "set_to_1": False} for o in OFFSETS}, "skew_f": f}
        p2 = part2(scan, None, cal, T=T, hc=hc)
        v = p2["variants"]
        assert len(v) == 9 and all(len(x["by_offset"]) == 9 for x in v.values())
        for o in OFFSETS:
            lo = v["a_half_spread_0.05"]["by_offset"][label(o)]["mean_pnl_fee_0.09"]
            hi = v["a_half_spread_0.20"]["by_offset"][label(o)]["mean_pnl_fee_0.09"]
            assert abs((lo - hi) - 15.0) < 1e-9
        assert sum(x["by_offset"]["ATM"]["n"] for x in p2["periods_a"].values()) == n
        res = {"what": "selftest", "prereg_sha256": "selftest", "offsets": [label(o) for o in OFFSETS],
               "half_spread": HALF_SPREAD, "fees": FEES,
               "calibration": {k: v for k, v in cal.items() if k != "skew_f"}, "part2": p2, "part1": p1}
        write_outputs(res, real.write_atomic, tmp / "o.csv", tmp / "o.json", tmp / "o.md")
        with open(tmp / "o.csv", newline="") as fh:
            assert len(list(csv.DictReader(fh))) == 36
        back = json.loads((tmp / "o.json").read_text())
        assert "rows" not in back["part1"] and back["part2"]["n_trades"] == n
        md = (tmp / "o.md").read_text()
        assert "## Calibration" in md and "| ITM20 |" in md and "strike not collected" in md


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        res = run()
        a = res["part2"]["variants"]["a_calibrated"]
        print(f"model (a): best mean $/contract {a['best_mean_pnl']}, best mean return on premium "
              f"{a['best_mean_return_on_premium']}")
        for k, v in a["by_offset"].items():
            print(f"  {k:6s} price ${v['mean_price'] * 100:7.0f}  mean P&L {v['mean_pnl_fee_0.09']:+8.2f}  "
                  f"t {v['nw_t'] if v['nw_t'] is None else round(v['nw_t'], 2)}  return {v['mean_return_on_premium']:+.1%}")
        print(f"wrote {OUT_MD}, {OUT_JSON}, {OUT_CSV}")
    else:
        raise SystemExit("usage: strikes.py selftest | run")
