"""Real-price study of the close candle signal: tune on 2013-2020, confirm once on 2021-2026, validate the model.

Pre-registration: preregistration/spx_candle_realprice.md (drafted as backtests/spx_candle_realprice/PREREG_DRAFT.md).
`run` refuses to read option prices unless that file exists and its SHA-256 is in preregistration/LEDGER.md.

  Discovery (2013-04-01 .. 2020-12-31). Every cell of a grid is scored with real SPXW 0DTE prices (buy at the ask at
      the entry minute, settle at intrinsic on the official SPX close). Grid: candle minute x body threshold x
      direction x strike offset. One cell is picked by a fixed rule, with a luck check (a circular-shift null of
      the best score over the whole grid).
  Confirmation (2021-01-01 .. 2026-10-20). ONE configuration is tested once: the discovery pick if it clearly beat
      the current rule on discovery, else the current rule (15:50 candle, body 0.60, with the candle, ITM10).
  Model validation (2021-2026, descriptive). The strike ladder's model price and P&L against the real ask and
      real P&L on the same days and strikes.
  Descriptive, deciding nothing: the chosen configuration and the current rule with a $0.74 fee and bought at the
      mid, in each period; and the Part 4 fill check on OPRA ohlcv-1m trade bars (did the contract trade in the
      entry minute, was the low at or below the ask, the last trade minus the mid), from the bar files that exist
      when the run starts.

Usage (from /Users/kv15/trading):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_realprice/realprice.py selftest
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_realprice/realprice.py run

Outputs (rebuilt on each run): backtests/spx_candle_realprice/results.json, backtests/spx_candle_realprice/RESULTS.md,
data/spx_1549/databento/realprice_trades.csv. Nothing here is a trading recommendation.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
PREREG = ROOT / "preregistration" / "spx_candle_realprice.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
SPX_ROOT = ROOT / "data" / "spx_1549"
DB_DIR = SPX_ROOT / "databento" / "cbbo-1m_1500-1601_k60"
BARS_DIR = SPX_ROOT / "databento" / "ohlcv-1m_1500-1601_k60"          # Part 4 trade bars (descriptive)
CLOSES_CSV = SPX_ROOT / "spx_official_closes_cboe.csv"
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/SPX_History.csv"
OUT_JSON = HERE / "results.json"
OUT_MD = HERE / "RESULTS.md"
OUT_TRADES = SPX_ROOT / "databento" / "realprice_trades.csv"
SCAN_PY = ROOT / "backtests" / "spx_candle_scan" / "scan.py"
STRIKES_PY = ROOT / "backtests" / "spx_candle_strikes" / "strikes.py"
STRIKES_JSON = ROOT / "backtests" / "spx_candle_strikes" / "results.json"
CANDIDATES_JSON = ROOT / "backtests" / "spx_candle_scan" / "candidates.json"
OPTIONS_PY = ROOT / "analysis" / "candle_1550_options_forward.py"
ET = ZoneInfo("America/New_York")

DISCOVERY = ("2013-04-01", "2020-12-31")
HALVES = (("2013-04-01", "2016-12-31"), ("2017-01-01", "2020-12-31"))
HOLDOUT = ("2021-01-01", "2026-10-20")
HOLDOUT_SUB = (("2021-01-01", "2022-12-31"), ("2023-01-01", "2026-10-20"))

CANDLES = [f"15:{m:02d}" for m in range(40, 51)]                       # 11 one-minute candles 15:40 .. 15:50
ENTRIES = [f"15:{m:02d}" for m in range(41, 52)]                       # entry at the next minute's open
THRESHOLDS = [round(0.40 + 0.05 * i, 2) for i in range(11)]            # 0.40 .. 0.90
DIRECTIONS = (1, -1)                                                    # +1 with the candle, -1 against it
OFFSETS = (20, 15, 10, 5, 0, -5, -10, -15, -20)                         # + = in the money in the trade's direction
N_CELLS = len(CANDLES) * len(THRESHOLDS) * len(DIRECTIONS) * len(OFFSETS)   # 2,178
CURRENT = ("15:50", 0.60, 1, 10)

FEE = 0.09                                                              # every decision and the criterion
FEE_HIGH = 0.74                                                         # descriptive version only
MULT = 100.0
STEP = 5.0
PARITY_STRIKES = 3
MIN_TRADES = 150
MIN_TRADES_HALF = 50
T_BAR = 2.0
NULL_ALPHA = 0.05
SHIFT_MIN_GAP = 21
SHIFT_STEP = 3
NW_LAG = 5
CLOSE_CHECK_TOL = 0.01
MIN_CLOSE_OVERLAP = 3
EXPECTED_HOLDOUT_TRADES = 644


def label(o: int) -> str:
    return "ATM" if o == 0 else (f"ITM{o}" if o > 0 else f"OTM{-o}")


def cell_name(c) -> str:
    k, th, d, o = c
    return f"{k} body>={th:.2f} {'with' if d > 0 else 'against'} {label(o)}"


# ------------------------------------------------------------------------------------------------
# quotes
# ------------------------------------------------------------------------------------------------
def et_minute(ts: str) -> str:
    t = datetime.fromisoformat(ts[:19]).replace(tzinfo=timezone.utc).astimezone(ET)
    return t.strftime("%H:%M")


def on_minute_of_day(ts: str, day: str) -> bool:
    """True when a pretty ts_recv (YYYY-MM-DDTHH:MM:SS.fffffffffZ, UTC) is exactly on a minute boundary and falls on
    `day` in ET, so a cbbo-1m row is the snapshot at that minute's start and not a later or other-day row."""
    t = datetime.fromisoformat(ts[:19]).replace(tzinfo=timezone.utc).astimezone(ET)
    frac = ts[20:-1] if len(ts) > 20 and ts[19] == "." else ""
    return t.strftime("%Y-%m-%d") == day and t.second == 0 and frac.strip("0") == ""


def parse_symbol(sym: str) -> tuple[str, str, float]:
    if not (sym.startswith("SPXW  ") and len(sym) == 21):
        raise ValueError(sym)
    day = f"20{sym[6:8]}-{sym[8:10]}-{sym[10:12]}"
    kind = {"C": "call", "P": "put"}[sym[12]]
    return day, kind, int(sym[13:21]) / 1000.0


def fnum(x: str):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def valid_quote(bid, ask) -> bool:
    return ask is not None and bid is not None and ask > 0 and 0 <= bid <= ask


def parse_quotes(text: str, day: str) -> tuple[dict, dict]:
    """{HH:MM: {(kind, K): (bid, ask)}} of valid quotes for contracts expiring on `day`, plus row counts."""
    out: dict = {}
    n = {"rows": 0, "invalid": 0, "other_expiry": 0, "off_minute": 0}
    for r in csv.DictReader(io.StringIO(text)):
        n["rows"] += 1
        d, kind, K = parse_symbol(r["symbol"])
        if d != day:
            n["other_expiry"] += 1
            continue
        if not on_minute_of_day(r["ts_recv"], day):
            n["off_minute"] += 1
            continue
        bid, ask = fnum(r["bid_px_00"]), fnum(r["ask_px_00"])
        if not valid_quote(bid, ask):
            n["invalid"] += 1
            continue
        out.setdefault(et_minute(r["ts_recv"]), {})[(kind, K)] = (bid, ask)
    return out, n


def load_day_quotes(day: str, folder: Path = DB_DIR):
    """(quotes, counts) for a day with a file, ('none', None) for a day with no expiry, (None, None) if missing."""
    f = folder / f"{day}.csv.gz"
    if f.exists():
        return parse_quotes(gzip.decompress(f.read_bytes()).decode(), day)
    if (folder / f"{day}.none").exists():
        return "none", None
    return None, None


def implied_spot(q: dict) -> float | None:
    """Median of K + mid(call) - mid(put) over the PARITY_STRIKES strikes where the two mids are closest;
    both legs need a bid above 0."""
    rows = []
    for (kind, K), (b, a) in q.items():
        if kind != "call" or b <= 0:
            continue
        p = q.get(("put", K))
        if p is None or p[0] <= 0:
            continue
        mc, mp = (b + a) / 2, (p[0] + p[1]) / 2
        rows.append((abs(mc - mp), K + mc - mp))
    if len(rows) < PARITY_STRIKES:                       # the plan picks 3 strikes; fewer -> no implied spot
        return None
    rows.sort()
    return float(np.median([v for _, v in rows[:PARITY_STRIKES]]))


def atm_of(s: float) -> float:
    return float(math.floor(s / STEP + 0.5) * STEP)


def intrinsic(kind: str, K: float, X: float) -> float:
    return max(0.0, X - K) if kind == "call" else max(0.0, K - X)


def day_cube(quotes: dict, close: float):
    """Per entry minute and offset: P&L of buying the call (up) and the put (down) at the ask, settled at `close`.
    Returns arrays up, dn, ask_up, ask_dn, mid_up, mid_dn (len(ENTRIES) x len(OFFSETS)), spot and atm
    (len(ENTRIES)), and reasons. The mid only feeds the descriptive mid-price version and the fill check."""
    shape = (len(ENTRIES), len(OFFSETS))
    up, dn = np.full(shape, np.nan), np.full(shape, np.nan)
    au, ad = np.full(shape, np.nan), np.full(shape, np.nan)
    mu, md = np.full(shape, np.nan), np.full(shape, np.nan)
    spot, atm = np.full(len(ENTRIES), np.nan), np.full(len(ENTRIES), np.nan)
    reasons = {"no_spot": 0, "no_quote": 0}
    for i, m in enumerate(ENTRIES):
        q = quotes.get(m, {})
        s = implied_spot(q)
        if s is None:
            reasons["no_spot"] += 1
            continue
        spot[i], atm[i] = s, atm_of(s)
        for j, o in enumerate(OFFSETS):
            for kind, K, P, A, M in (("call", atm[i] - o, up, au, mu), ("put", atm[i] + o, dn, ad, md)):
                qa = q.get((kind, K))
                if qa is None:
                    reasons["no_quote"] += 1
                    continue
                A[i, j], M[i, j] = qa[1], (qa[0] + qa[1]) / 2
                P[i, j] = MULT * (intrinsic(kind, K, close) - qa[1]) - FEE
    return up, dn, au, ad, mu, md, spot, atm, reasons


# ------------------------------------------------------------------------------------------------
# signals
# ------------------------------------------------------------------------------------------------
def body_signal(o, h, l_, c, theta):
    o, h, l_, c = (np.asarray(x, float) for x in (o, h, l_, c))
    body, rng = c - o, h - l_
    with np.errstate(invalid="ignore"):
        s = np.where((rng > 0) & (np.abs(body) >= theta * rng), np.sign(body), 0.0)
    bad = ~(np.isfinite(o) & np.isfinite(h) & np.isfinite(l_) & np.isfinite(c))
    s[bad] = np.nan
    return s


def signals(P, rows, scan) -> np.ndarray:
    """sig[n_days, candle, threshold] in {-1, 0, +1, NaN} for the panel rows `rows` (-1 = day not in the panel)."""
    rows = np.asarray(rows)
    sig = np.full((len(rows), len(CANDLES), len(THRESHOLDS)), np.nan)
    ok = rows >= 0
    for a, k in enumerate(CANDLES):
        i = scan.mi(k)
        o, h, l_, c = (X[rows[ok], i] for X in (P.O, P.H, P.L, P.C))
        for b, th in enumerate(THRESHOLDS):
            sig[ok, a, b] = body_signal(o, h, l_, c, th)
    return sig


def day_series(s, up_k, dn_k):
    """Per-day P&L of one contract for a signal column s (already times the direction): the call's P&L on +1, the
    put's on -1, 0 on 0 (no trade), NaN when the signal is missing or the trade could not be priced."""
    s = np.asarray(s, float)
    sh = s.shape + (1,) * (up_k.ndim - 1) if s.ndim < up_k.ndim else s.shape
    s2 = s.reshape(sh) if s.ndim < up_k.ndim else s
    with np.errstate(invalid="ignore"):
        return np.where(s2 > 0, up_k, np.where(s2 < 0, dn_k, np.where(s2 == 0, 0.0, np.nan)))


# ------------------------------------------------------------------------------------------------
# grid statistics, selection, null
# ------------------------------------------------------------------------------------------------
def grid_means(sig, up, dn, masks: list) -> dict:
    """For each mask: mean per-day P&L and trade count of every cell, arrays [candle, threshold, direction, offset].
    sig: (n, C, T) or (S, n, C, T) for shifted copies; up/dn: (n, E, O)."""
    shifted = sig.ndim == 4
    lead = (sig.shape[0],) if shifted else ()
    out = [{"mean": np.full(lead + (len(CANDLES), len(THRESHOLDS), 2, len(OFFSETS)), np.nan),
            "n_trades": np.zeros(lead + (len(CANDLES), len(THRESHOLDS), 2, len(OFFSETS)), int)} for _ in masks]
    for a in range(len(CANDLES)):
        U, D = up[:, a, :], dn[:, a, :]                                  # (n, O)
        for b in range(len(THRESHOLDS)):
            s0 = sig[..., a, b]                                          # (n,) or (S, n)
            for di, d in enumerate(DIRECTIONS):
                s = s0 * d
                X = day_series(s[..., None], U, D)                       # (n, O) or (S, n, O)
                traded = np.isfinite(X) & (s[..., None] != 0)
                for r, m in zip(out, masks):
                    Xm, Tm = X[..., m, :], traded[..., m, :]
                    cnt = np.isfinite(Xm).sum(axis=-2)
                    with np.errstate(invalid="ignore", divide="ignore"):
                        mean = np.where(cnt > 0, np.nansum(Xm, axis=-2) / np.maximum(cnt, 1), np.nan)
                    r["mean"][..., a, b, di, :] = mean
                    r["n_trades"][..., a, b, di, :] = Tm.sum(axis=-2)
    return out


def plateau(mean: np.ndarray) -> np.ndarray:
    """Score = average of a cell's mean and its threshold neighbours (+-0.05) that exist on the grid."""
    m = np.asarray(mean, float)
    ax = m.ndim - 3                                                       # threshold axis
    stack = [m]
    for sh in (1, -1):
        r = np.roll(m, sh, axis=ax)
        idx = [slice(None)] * m.ndim
        idx[ax] = 0 if sh == 1 else -1
        r[tuple(idx)] = np.nan
        stack.append(r)
    with np.errstate(invalid="ignore"):
        st = np.stack(stack)
        cnt = np.isfinite(st).sum(axis=0)
        return np.where(np.isfinite(m) & (cnt > 0), np.nansum(st, axis=0) / np.maximum(cnt, 1), np.nan)


def eligible(full, h1, h2) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return ((full["n_trades"] >= MIN_TRADES) & (h1["n_trades"] >= MIN_TRADES_HALF) &
                (h2["n_trades"] >= MIN_TRADES_HALF) & (h1["mean"] > 0) & (h2["mean"] > 0))


def idx_of(c) -> tuple:
    k, th, d, o = c
    return CANDLES.index(k), THRESHOLDS.index(round(th, 2)), DIRECTIONS.index(d), OFFSETS.index(o)


def cell_of(ix) -> tuple:
    a, b, di, j = (int(x) for x in ix)
    return CANDLES[a], THRESHOLDS[b], DIRECTIONS[di], OFFSETS[j]


def distance_to_current(ix) -> float:
    a, b, di, j = ix
    ca, cb, cdi, cj = idx_of(CURRENT)
    return abs(a - ca) + abs(b - cb) + (di != cdi) + abs(j - cj)


def pick(score, elig):
    """Best eligible cell by score; ties go to the cell nearest the current rule. None if nothing is eligible."""
    s = np.where(elig, score, -np.inf)
    best = np.nanmax(s) if np.isfinite(s).any() else -np.inf
    if not np.isfinite(best):
        return None
    ties = [tuple(int(v) for v in ix) for ix in np.argwhere(s == best)]
    return min(ties, key=distance_to_current)


def shifts_for(n: int, step: int = SHIFT_STEP) -> list[int]:
    return list(range(SHIFT_MIN_GAP, n - SHIFT_MIN_GAP + 1, step))


def null_max(sig, up, dn, masks, step: int = SHIFT_STEP, chunk: int = 32) -> np.ndarray:
    """Best eligible plateau score over the whole grid when the signal is circularly shifted against the outcome days
    (all admissible shifts); -inf when no cell is eligible under a shift."""
    n = sig.shape[0]
    shifts = shifts_for(n, step)
    out = []
    for i in range(0, len(shifts), chunk):
        sh = np.array(shifts[i:i + chunk])
        idx = (np.arange(n)[None, :] + sh[:, None]) % n
        S = sig[idx]                                                     # (s, n, C, T)
        full, h1, h2 = grid_means(S, up, dn, masks)
        sc = plateau(full["mean"])
        el = eligible(full, h1, h2)
        flat = np.where(el, sc, -np.inf).reshape(len(sh), -1)
        out.extend(np.max(flat, axis=1).tolist())
    return np.array(out)


def nw(y) -> dict:
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    n = int(len(y))
    if n < NW_LAG + 3:
        return {"n": n, "mean": float(np.mean(y)) if n else None, "t": None}
    mu = float(y.mean())
    e = y - mu
    lrv = float(e @ e) / n
    for j in range(1, NW_LAG + 1):
        lrv += 2.0 * (1.0 - j / (NW_LAG + 1.0)) * float(e[j:] @ e[:-j]) / n
    se = math.sqrt(max(lrv, 0.0) / n)
    return {"n": n, "mean": mu, "t": mu / se if se > 0 else None}


def series(c, sig, up, dn) -> np.ndarray:
    a, b, di, j = idx_of(c)
    return day_series(sig[:, a, b] * DIRECTIONS[di], up[:, a, j], dn[:, a, j])


def describe(x, s_col=None) -> dict:
    """Per-day series stats plus per-trade stats (trades = days with a priced trade)."""
    x = np.asarray(x, float)
    tr = np.isfinite(x) & (s_col != 0) if s_col is not None else np.isfinite(x) & (x != 0)
    t = x[tr]
    d = nw(x)
    return {"days": d["n"], "mean_per_day": d["mean"], "nw_t_per_day": d["t"], "trades": int(tr.sum()),
            "mean_per_trade": float(t.mean()) if t.size else None,
            "share_trades_won": float(np.mean(t > 0)) if t.size else None,
            "median_trade": float(np.median(t)) if t.size else None,
            "worst_trade": float(t.min()) if t.size else None}


def null_quantile(nulls: np.ndarray, q: float):
    """Quantile of the WHOLE null, a shift with no eligible cell counting as -inf (worst). None when the quantile
    falls on or next to such a shift, so the summary never silently drops part of the null."""
    if len(nulls) == 0:
        return None
    v = np.sort(np.asarray(nulls, float))
    pos = q / 100 * (len(v) - 1)
    lo, hi = v[int(np.floor(pos))], v[int(np.ceil(pos))]
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return None
    return float(np.percentile(v, q))


def discovery(sig, up, dn, dates, step: int = SHIFT_STEP) -> dict:
    disc = (dates >= DISCOVERY[0]) & (dates <= DISCOVERY[1])
    d_sig, d_up, d_dn, d_dates = sig[disc], up[disc], dn[disc], dates[disc]
    masks = [np.ones(len(d_dates), bool)] + [(d_dates >= a) & (d_dates <= b) for a, b in HALVES]
    full, h1, h2 = grid_means(d_sig, d_up, d_dn, masks)
    score = plateau(full["mean"])
    el = eligible(full, h1, h2)
    best = pick(score, el)
    nulls = null_max(d_sig, d_up, d_dn, masks, step)
    obs = float(score[best]) if best is not None else None
    p_max = (1 + int(np.sum(nulls >= obs))) / (1 + len(nulls)) if obs is not None else None
    cur = idx_of(CURRENT)
    res = {"days": int(len(d_dates)), "n_cells": N_CELLS, "n_eligible": int(el.sum()), "n_shifts": int(len(nulls)),
           "n_shifts_nothing_eligible": int(np.sum(~np.isfinite(nulls))),
           "null_max_median": null_quantile(nulls, 50), "null_max_p95": null_quantile(nulls, 95),
           "current": {"cell": cell_name(CURRENT), "score": float(score[cur]), "eligible": bool(el[cur]),
                       "mean_per_day": float(full["mean"][cur]), "trades": int(full["n_trades"][cur]),
                       "half_means": [float(h1["mean"][cur]), float(h2["mean"][cur])]}}
    flat = np.where(el, score, -np.inf).ravel()
    order = [np.unravel_index(i, score.shape) for i in np.argsort(-flat)[:15] if np.isfinite(flat[i])]
    res["top"] = [{"cell": cell_name(cell_of(ix)), "score": float(score[ix]), "mean_per_day": float(full["mean"][ix]),
                   "trades": int(full["n_trades"][ix]), "half_means": [float(h1["mean"][ix]), float(h2["mean"][ix])]}
                  for ix in order]
    res["best_by_candle"] = {}
    for a, k in enumerate(CANDLES):
        s = np.where(el[a], score[a], -np.inf)
        if np.isfinite(s).any():
            ix = (a,) + tuple(int(v) for v in np.unravel_index(np.argmax(s), s.shape))
            res["best_by_candle"][k] = {"cell": cell_name(cell_of(ix)), "score": float(score[ix])}
        else:
            res["best_by_candle"][k] = None
    if best is None:
        res.update({"best": None, "best_score": None, "p_max": None, "decision": "nothing eligible: test the current rule",
                    "chosen": CURRENT})
        return res
    bc = cell_of(best)
    diff = series(bc, d_sig, d_up, d_dn) - series(CURRENT, d_sig, d_up, d_dn)
    dd = nw(diff)
    checks = {"differs_from_current": bc != CURRENT, "p_max_le_alpha": p_max <= NULL_ALPHA,
              "beats_current_on_discovery": bool(dd["mean"] is not None and dd["mean"] > 0 and dd["t"] is not None
                                                 and dd["t"] >= T_BAR)}
    chosen = bc if all(checks.values()) else CURRENT
    res.update({"best": cell_name(bc), "best_cell": bc, "best_score": obs, "p_max": p_max,
                "luck_adjusted": obs - res["null_max_median"] if res["null_max_median"] is not None else None,
                "best_vs_current_per_day": dd, "checks": checks, "chosen": chosen,
                "decision": ("the discovery pick clearly beat the current rule: confirm the pick"
                             if chosen != CURRENT else "no clear win over the current rule: confirm the current rule")})
    return res


def confirmation(chosen, sig, up, dn, dates) -> dict:
    hold = (dates >= HOLDOUT[0]) & (dates <= HOLDOUT[1])
    h_sig, h_up, h_dn, h_dates = sig[hold], up[hold], dn[hold], dates[hold]

    def stats(c, mask=None):
        a, b, di, _ = idx_of(c)
        m = mask if mask is not None else np.ones(len(h_dates), bool)
        return describe(series(c, h_sig, h_up, h_dn)[m], (h_sig[:, a, b] * DIRECTIONS[di])[m])

    xc = series(chosen, h_sig, h_up, h_dn)
    d = nw(xc)
    res = {"days": int(len(h_dates)), "chosen": cell_name(chosen), "chosen_stats": stats(chosen),
           "confirmed": bool(d["mean"] is not None and d["mean"] > 0 and d["t"] is not None and d["t"] >= T_BAR),
           "current_stats": stats(CURRENT),
           "subperiods": {f"{a}..{b}": {"chosen": stats(chosen, (h_dates >= a) & (h_dates <= b)),
                                        "current": stats(CURRENT, (h_dates >= a) & (h_dates <= b))}
                          for a, b in HOLDOUT_SUB},
           "current_rule_all_offsets": {label(o): stats((CURRENT[0], CURRENT[1], CURRENT[2], o)) for o in OFFSETS}}
    if chosen != CURRENT:
        dd = nw(xc - series(CURRENT, h_sig, h_up, h_dn))
        res["chosen_vs_current_per_day"] = dd
        res["beats_current"] = bool(dd["mean"] is not None and dd["mean"] > 0 and dd["t"] is not None and dd["t"] >= T_BAR)
    return res


PERIODS = (("discovery", DISCOVERY), ("confirmation", HOLDOUT))
VERSIONS = ("ask_fee_0.09", "ask_fee_0.74", "mid_fee_0.09")


def cost_versions(cells: dict, sig, cube: dict) -> dict:
    """Descriptive, decides nothing: each configuration's per-day and per-trade stats in each period at the
    criterion's prices (the ask, $0.09), with the $0.74 fee instead, and buying at the mid instead of the ask
    ($0.09). The same trade days in all three: a trade is priced only when its ask (and so its mid) exists."""
    dates = cube["dates"]
    out = {}
    for name, c in cells.items():
        a, b, di, j = idx_of(c)
        s = sig[:, a, b] * DIRECTIONS[di]
        x = day_series(s, cube["up"][:, a, j], cube["dn"][:, a, j])
        traded = np.isfinite(x) & (s != 0)
        x74 = np.where(traded, x - (FEE_HIGH - FEE), x)
        up_mid = cube["up"][:, a, j] + MULT * (cube["ask_up"][:, a, j] - cube["mid_up"][:, a, j])
        dn_mid = cube["dn"][:, a, j] + MULT * (cube["ask_dn"][:, a, j] - cube["mid_dn"][:, a, j])
        xm = day_series(s, up_mid, dn_mid)
        out[name] = {"cell": cell_name(c), "periods": {}}
        for per, (lo, hi) in PERIODS:
            m = (dates >= lo) & (dates <= hi)
            out[name]["periods"][per] = {v: describe(y[m], s[m]) for v, y in zip(VERSIONS, (x, x74, xm))}
    return out


# ------------------------------------------------------------------------------------------------
# Part 4: fill check on trade bars (descriptive)
# ------------------------------------------------------------------------------------------------
def parse_bars(text: str, day: str) -> tuple[dict, dict]:
    """{HH:MM: {(kind, K): (low, close, volume)}} from an ohlcv-1m file, columns found by the header; a bar stamped
    HH:MM (ts_event = the bar's start) covers the trades in that minute. Only contracts expiring on `day`."""
    out: dict = {}
    n = {"rows": 0, "other_expiry": 0, "bad": 0}
    for r in csv.DictReader(io.StringIO(text)):
        n["rows"] += 1
        d, kind, K = parse_symbol(r["symbol"])
        if d != day:
            n["other_expiry"] += 1
            continue
        lo, cl, vol = fnum(r.get("low")), fnum(r.get("close")), fnum(r.get("volume"))
        if lo is None or cl is None or vol is None:
            n["bad"] += 1
            continue
        out.setdefault(et_minute(r["ts_event"]), {})[(kind, K)] = (lo, cl, vol)
    return out, n


def bar_listing(folder: Path = BARS_DIR) -> dict:
    """The trade-bar files that exist now (taken once, when the run starts): {day: 'file' | 'none'}."""
    if not folder.is_dir():
        return {}
    out = {f.name[:-len(".none")]: "none" for f in folder.glob("*.none")}
    out.update({f.name[:-len(".csv.gz")]: "file" for f in folder.glob("*.csv.gz")})
    return out


def load_day_bars(day: str, listing: dict, folder: Path = BARS_DIR):
    """(bars, status): status is 'ok', 'none' (no expiry), 'missing' (no file when the run started) or
    'unreadable' (the file did not parse; never stops the run)."""
    kind = listing.get(day)
    if kind is None:
        return None, "missing"
    if kind == "none":
        return None, "none"
    try:
        bars, _ = parse_bars(gzip.decompress((folder / f"{day}.csv.gz").read_bytes()).decode(), day)
    except Exception:                                                    # descriptive part: report, never stop
        return None, "unreadable"
    return bars, "ok"


def fill_check(rows: list, listing: dict, loader) -> dict:
    """For every priced entry in `rows` (trade_rows output; filled in place with the bar's values), per configuration
    and period: entries with a bar file that day, the share that traded in the entry minute (volume > 0), among those
    the share whose low was <= the ask, and the mean and median of (the minute's last trade - the mid), $/share."""
    cache: dict = {}
    acc: dict = {}
    for r in rows:
        r.update({"bar_file": "", "bar_volume": np.nan, "bar_low": np.nan, "bar_close": np.nan})
        if r["status"] != "priced":
            continue
        day = r["date"]
        if day not in cache:
            cache[day] = loader(day)
        bars, status = cache[day]
        r["bar_file"] = status
        st = acc.setdefault(r["config"], {}).setdefault(r["period"], {
            "entries_priced": 0, "entries_with_bar_file": 0, "days": set(), "no_bar_file": 0, "unreadable": 0,
            "traded": 0, "low_le_ask": 0, "last_minus_mid": []})
        st["entries_priced"] += 1
        if status != "ok":
            st["unreadable" if status == "unreadable" else "no_bar_file"] += 1
            continue
        st["entries_with_bar_file"] += 1
        st["days"].add(day)
        b = bars.get(r["entry_minute"], {}).get((r["kind"], float(r["strike"])))
        if b is None or not b[2] > 0:
            r["bar_volume"] = 0.0
            continue
        lo, cl, vol = b
        r["bar_volume"], r["bar_low"], r["bar_close"] = vol, lo, cl
        st["traded"] += 1
        st["low_le_ask"] += int(lo <= r["ask"] + 1e-9)
        st["last_minus_mid"].append(cl - r["mid"])
    out = {}
    for name, pers in acc.items():
        out[name] = {}
        for per, st in pers.items():
            w, t = st["entries_with_bar_file"], st["traded"]
            lm = np.array(st["last_minus_mid"], float)
            out[name][per] = {"entries_priced": st["entries_priced"], "entries_with_bar_file": w,
                              "days_with_bar_file": len(st["days"]), "entries_no_bar_file": st["no_bar_file"],
                              "entries_unreadable_file": st["unreadable"], "entries_traded": t,
                              "share_traded": t / w if w else None,
                              "share_low_le_ask_of_traded": st["low_le_ask"] / t if t else None,
                              "mean_last_minus_mid": float(lm.mean()) if t else None,
                              "median_last_minus_mid": float(np.median(lm)) if t else None}
    files = sum(1 for v in listing.values() if v == "file")
    return {"folder": str(BARS_DIR.relative_to(ROOT)), "bar_files_at_start": files,
            "none_markers_at_start": sum(1 for v in listing.values() if v == "none"),
            "note": None if files else "no trade-bar files existed when the run started: Part 4 was not computed",
            "by_config": out}


# ------------------------------------------------------------------------------------------------
# official closes
# ------------------------------------------------------------------------------------------------
def parse_cboe(text: str) -> dict:
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        m, d, y = r["DATE"].split("/")
        v = fnum(r["SPX"])
        if v and v > 0:
            out[f"{y}-{m}-{d}"] = v
    return out


def fetch_closes(path: Path = CLOSES_CSV) -> tuple[dict, str]:
    """Cboe's official SPX daily closes, downloaded once and kept; no other source is used."""
    if not path.exists():
        req = urllib.request.Request(CBOE_URL, headers={"User-Agent": "spx-research/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:            # follows Cboe's 307 redirect
            text = r.read().decode()
        if len(parse_cboe(text)) < 3000:
            raise SystemExit("Cboe SPX_History.csv did not parse; stopping (no other close source is allowed)")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return parse_cboe(path.read_text()), "cboe"


def check_closes(closes: dict, rh: dict) -> dict:
    over = sorted(set(closes) & set(rh))
    bad = [(d, closes[d], rh[d][0]) for d in over if abs(closes[d] - rh[d][0]) > CLOSE_CHECK_TOL]
    if len(over) < MIN_CLOSE_OVERLAP or bad:
        raise SystemExit(f"official-close check failed: {len(over)} overlap days, mismatches {bad[:5]}")
    return {"overlap_days": len(over), "max_abs_diff": max(abs(closes[d] - rh[d][0]) for d in over)}


# ------------------------------------------------------------------------------------------------
# model validation (descriptive)
# ------------------------------------------------------------------------------------------------
def model_validation(strikes, scan, P_hold, closes, quotes_at_1551: dict) -> dict:
    cal = json.loads(STRIKES_JSON.read_text())["calibration"]
    k_d1 = cal["k_d1"]
    f = {o: cal["skew"][label(o)]["f"] for o in OFFSETS}
    T = strikes.strong_body_trades(scan, P_hold)
    out, gap_by_day = {}, {}                         # official close - D1 15:59 close, on the days the table uses
    for o in OFFSETS:
        rows = []
        for i, day in enumerate(T["dates"]):
            day = str(day)
            q = quotes_at_1551.get(day)
            if q is None or day not in closes or not np.isfinite(T["rv"][i]):
                continue
            S, d = float(T["S"][i]), int(T["d"][i])
            kind, K = strikes.contract_for(d, float(strikes.strike_for(S)), o)
            qa = q.get((kind, K))
            if qa is None:
                continue
            model = f[o] * strikes.bachelier(kind == "call", S, K, k_d1 * T["rv"][i] * strikes.SQRT_REMAINING * S)
            real_pnl = MULT * (intrinsic(kind, K, closes[day]) - qa[1]) - FEE
            model_pnl = MULT * (intrinsic(kind, K, float(T["X"][i])) - model - strikes.HALF_SPREAD) - FEE
            rows.append((model, (qa[0] + qa[1]) / 2, qa[1], model_pnl, real_pnl))
            gap_by_day[day] = closes[day] - float(T["X"][i])
        if not rows:
            out[label(o)] = {"n": 0}
            continue
        a = np.array(rows)
        with np.errstate(divide="ignore", invalid="ignore"):
            mid_r, ask_r = a[:, 1] / a[:, 0], a[:, 2] / a[:, 0]
        dd = nw(a[:, 4] - a[:, 3])
        fin = np.isfinite(mid_r) & np.isfinite(ask_r)
        out[label(o)] = {"n": len(rows), "mean_model_price": float(a[:, 0].mean()), "mean_real_mid": float(a[:, 1].mean()),
                         "mean_real_ask": float(a[:, 2].mean()),
                         "mean_mid_over_model": float(mid_r[fin].mean()) if fin.any() else None,
                         "mean_ask_over_model": float(ask_r[fin].mean()) if fin.any() else None,
                         "median_mid_over_model": float(np.nanmedian(mid_r)),
                         "median_ask_over_model": float(np.nanmedian(ask_r)),
                         "mean_model_pnl": float(a[:, 3].mean()), "mean_real_pnl": float(a[:, 4].mean()),
                         "mean_real_minus_model_pnl": dd["mean"], "nw_t_diff": dd["t"]}
    g = np.array(list(gap_by_day.values()))
    return {"trades": int(len(T["dates"])), "by_offset": out,
            "settle_gap_official_vs_d1_1559": {"days": int(len(g)),
                                               "mean": float(g.mean()) if len(g) else None,
                                               "mean_abs": float(np.abs(g).mean()) if len(g) else None,
                                               "p95_abs": float(np.percentile(np.abs(g), 95)) if len(g) else None}}


# ------------------------------------------------------------------------------------------------
# assembling the data, the run, outputs
# ------------------------------------------------------------------------------------------------
def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def check_gate(prereg: Path = PREREG, ledger: Path = LEDGER) -> str:
    if not Path(prereg).exists():
        raise SystemExit(f"refusing to run: {prereg} does not exist (lock PREREG_DRAFT.md there and add its SHA-256 "
                         f"to {ledger} first)")
    h = hashlib.sha256(Path(prereg).read_bytes()).hexdigest()
    if h not in Path(ledger).read_text():
        raise SystemExit(f"refusing to run: SHA-256 of {Path(prereg).name} ({h}) is not in {ledger}")
    return h


def assemble(days: list, closes: dict, loader) -> dict:
    """Stack day cubes for the days that have a quote file and an official close. loader(day) -> (quotes|'none'|None, n)."""
    keep, U, Dn, AU, AD, MU, MD, SP, AT = [], [], [], [], [], [], [], [], []
    drops = {"no_expiry": 0, "missing_file": [], "no_close": 0}
    reasons = {"no_spot": 0, "no_quote": 0}
    q1551 = {}
    for day in days:
        q, _ = loader(day)
        if q == "none":
            drops["no_expiry"] += 1
            continue
        if q is None:
            drops["missing_file"].append(day)
            continue
        if day not in closes:
            drops["no_close"] += 1
            continue
        up, dn, au, ad, mu, md, sp, at, r = day_cube(q, closes[day])
        for k in reasons:
            reasons[k] += r[k]
        keep.append(day)
        U.append(up), Dn.append(dn), AU.append(au), AD.append(ad), MU.append(mu), MD.append(md)
        SP.append(sp), AT.append(at)
        q1551[day] = q.get("15:51", {})
    return {"dates": np.array(keep), "up": np.array(U), "dn": np.array(Dn), "ask_up": np.array(AU),
            "ask_dn": np.array(AD), "mid_up": np.array(MU), "mid_dn": np.array(MD), "spot": np.array(SP),
            "atm": np.array(AT), "drops": drops, "reasons": reasons, "q1551": q1551}


def trade_rows(cells: dict, cube: dict, sig) -> list:
    rows = []
    for name, c in cells.items():
        a, b, di, j = idx_of(c)
        s = sig[:, a, b] * DIRECTIONS[di]
        for i, day in enumerate(cube["dates"]):
            if not np.isfinite(s[i]) or s[i] == 0:
                continue
            up = s[i] > 0
            pnl = float((cube["up"] if up else cube["dn"])[i, a, j])
            ask = float((cube["ask_up"] if up else cube["ask_dn"])[i, a, j])
            mid = float((cube["mid_up"] if up else cube["mid_dn"])[i, a, j])
            atm = float(cube["atm"][i, a])
            rows.append({"config": name, "cell": cell_name(c), "date": str(day),
                         "period": "discovery" if day <= DISCOVERY[1] else "confirmation",
                         "signal": int(s[i]), "entry_minute": ENTRIES[a], "implied_spot": float(cube["spot"][i, a]),
                         "kind": "call" if up else "put",
                         "strike": (atm - OFFSETS[j]) if up else (atm + OFFSETS[j]),
                         "ask": ask, "mid": mid, "pnl_fee_0.09": pnl, "pnl_fee_0.74": pnl - (FEE_HIGH - FEE),
                         "pnl_mid_fee_0.09": pnl + MULT * (ask - mid),
                         "status": "priced" if np.isfinite(pnl) else "not_priced"})
    return rows


def unpriced_signal_entries(cells: dict, sig, cube: dict) -> dict:
    """Signal days left out because the trade could not be priced, by reason: no implied spot at the entry minute,
    or no valid quote for the contract. Per period for the named configurations, and per cell (discovery) for the
    whole grid. Days with no quote file (no expiry) are not in the cube and are counted separately."""
    dates = cube["dates"]
    spot_ok = np.isfinite(cube["spot"])                                              # (n, E)

    def counts(s, a, j, m):
        with np.errstate(invalid="ignore"):
            trade = np.isfinite(s) & (s != 0) & m
            pnl = np.where(s > 0, cube["up"][:, a, j], cube["dn"][:, a, j])
        priced = trade & np.isfinite(pnl)
        no_spot = trade & ~spot_ok[:, a]
        return {"signal_days": int(trade.sum()), "priced": int(priced.sum()), "no_spot": int(no_spot.sum()),
                "no_quote": int((trade & ~priced & ~no_spot).sum())}

    out = {"configs": {}}
    for name, c in cells.items():
        a, b, di, j = idx_of(c)
        s = sig[:, a, b] * DIRECTIONS[di]
        out["configs"][name] = {p: counts(s, a, j, (dates >= lo) & (dates <= hi)) for p, (lo, hi) in PERIODS}
    disc = (dates >= DISCOVERY[0]) & (dates <= DISCOVERY[1])
    left_out = np.zeros((len(CANDLES), len(THRESHOLDS), 2, len(OFFSETS)), int)
    for a in range(len(CANDLES)):
        for b in range(len(THRESHOLDS)):
            for di, d in enumerate(DIRECTIONS):
                for j in range(len(OFFSETS)):
                    r = counts(sig[:, a, b] * d, a, j, disc)
                    left_out[a, b, di, j] = r["signal_days"] - r["priced"]
    out["grid_discovery_left_out"] = {"median": float(np.median(left_out)), "max": int(left_out.max()),
                                      "cell_with_max": cell_name(cell_of(np.unravel_index(left_out.argmax(),
                                                                                          left_out.shape)))}
    return out


def run() -> dict:
    sha = check_gate()
    bars_at_start = bar_listing()                                          # Part 4 uses only the files there now
    scan = load_module("spx_candle_scan_ro", SCAN_PY)
    strikes = load_module("spx_candle_strikes_ro", STRIKES_PY)
    cfo = load_module("candle_1550_options_forward_ro", OPTIONS_PY)
    cands = json.loads(CANDIDATES_JSON.read_text())["candidates"]
    if next(c["direction"] for c in cands if c["feature"] == "F2_1m_1550_strong_body") != CURRENT[2]:
        raise SystemExit("frozen F2 direction is not the registered current direction")
    closes, src = fetch_closes()
    rh, _ = cfo.official_closes(SPX_ROOT)
    close_check = check_closes(closes, rh)
    P = scan.load_panel(DISCOVERY[0], HOLDOUT[1])
    days = [str(d) for d in P.dates]
    cube = assemble(days, closes, load_day_quotes)
    if cube["drops"]["missing_file"]:
        raise SystemExit(f"download incomplete: {len(cube['drops']['missing_file'])} days have no file, first "
                         f"{cube['drops']['missing_file'][:3]}")
    row = {d: i for i, d in enumerate(days)}
    sig = signals(P, [row[d] for d in cube["dates"]], scan)
    # self-check: the 0.60 / 15:50 / with column is the backtest's own F2 signal on every kept day
    f2 = np.asarray(scan.spec_by_id("F2_1m_1550_strong_body").signal(P), float)
    a, b, _, _ = idx_of(CURRENT)
    mine, theirs = sig[:, a, b], f2[[row[d] for d in cube["dates"]]]
    if not np.array_equal(np.nan_to_num(mine, nan=9), np.nan_to_num(theirs, nan=9)):
        raise SystemExit("self-check failed: the grid's current-rule signal differs from scan.py's F2")
    disc = discovery(sig, cube["up"], cube["dn"], cube["dates"])
    conf = confirmation(disc["chosen"], sig, cube["up"], cube["dn"], cube["dates"])
    P_hold = scan.load_panel(*HOLDOUT)
    mv = model_validation(strikes, scan, P_hold, closes, cube["q1551"])
    files = sorted(DB_DIR.glob("*"))
    manifest_sha = hashlib.sha256("\n".join(f"{f.name} {f.stat().st_size}" for f in files).encode()).hexdigest()
    res = {"what": "Real-price tuning, confirmation and model validation (spx_candle_realprice.md)",
           "prereg_sha256": sha, "data": {"folder": str(DB_DIR.relative_to(ROOT)), "files": len(files),
                                          "listing_sha256": manifest_sha, "closes_source": src, "close_check": close_check,
                                          "d1_days": len(days), "priced_days": int(len(cube["dates"])),
                                          "no_expiry_days": cube["drops"]["no_expiry"],
                                          "no_close_days": cube["drops"]["no_close"], "unpriced": cube["reasons"]},
           "grid": {"candles": CANDLES, "thresholds": THRESHOLDS, "directions": ["with", "against"],
                    "offsets": [label(o) for o in OFFSETS], "n_cells": N_CELLS},
           "discovery": disc, "confirmation": conf, "model_validation": mv}
    cells = {"chosen": disc["chosen"], "current": CURRENT}
    res["unpriced_signal_entries"] = unpriced_signal_entries(cells, sig, cube)
    res["cost_versions"] = cost_versions(cells, sig, cube)
    rows = trade_rows(cells, cube, sig)
    res["fill_check"] = fill_check(rows, bars_at_start, lambda d: load_day_bars(d, bars_at_start))
    write_outputs(res, rows, cfo.write_atomic)
    return res


def fm(x, nd=2, sign=True, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if pct:
        return f"{x * 100:.0f}%"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


def render_md(res: dict) -> str:
    L = []
    w = L.append
    d, c, mv, data = res["discovery"], res["confirmation"], res["model_validation"], res["data"]
    w("# Real SPXW prices: tuning on 2013-2020, one confirmation on 2021-2026, model check\n")
    w(f"Pre-registration `preregistration/spx_candle_realprice.md` (SHA-256 `{res['prereg_sha256'][:16]}...`). Real "
      "Databento OPRA quotes: buy at the ask at the entry minute, settle at intrinsic on the official SPX close, $0.09 fee. "
      "Research only, not a trading recommendation.\n")
    w(f"Data: {data['priced_days']} days with a same-day expiry and an official close, {data['no_expiry_days']} days "
      f"with no expiry. Closes from {data['closes_source']} ({data['close_check']['overlap_days']} days checked against "
      f"Robinhood, largest difference {data['close_check']['max_abs_diff']:.4f}). Across all kept days and entry "
      f"minutes: {data['unpriced']['no_spot']} day-minutes with no implied spot, {data['unpriced']['no_quote']} "
      "contract slots with no valid quote.\n")
    ups = res.get("unpriced_signal_entries")
    if ups:
        for name, per in ups["configs"].items():
            w(f"- Signal days left out (not priced), {name}: " + "; ".join(
                f"{p} {v['signal_days'] - v['priced']} of {v['signal_days']} (no spot {v['no_spot']}, "
                f"no quote {v['no_quote']})" for p, v in per.items()) + ".")
        g = ups["grid_discovery_left_out"]
        w(f"- Whole grid, discovery: median {g['median']:.0f} signal days left out per cell, at most {g['max']} "
          f"({g['cell_with_max']}).\n")
    w(f"## Discovery 2013-04-01 .. 2020-12-31 ({d['days']} days, {d['n_cells']:,} cells, {d['n_eligible']} eligible)\n")
    w(f"**Decision: {d['decision']}.**\n")
    if d.get("best"):
        ch = d["checks"]
        w(f"- Best eligible cell: **{d['best']}**, score {fm(d['best_score'])} a day. The best score under "
          f"{d['n_shifts']} circular shifts ({d.get('n_shifts_nothing_eligible', 0)} with no eligible cell, counted "
          f"as the worst): median {fm(d['null_max_median'])}, 95th percentile {fm(d['null_max_p95'])}; "
          f"p = {d['p_max']:.3f}. Luck-adjusted: {fm(d['luck_adjusted'])} a day.")
        bv = d["best_vs_current_per_day"]
        w(f"- Best minus current, per day: {fm(bv['mean'])} (Newey-West t {fm(bv['t'])}).")
        w(f"- Checks: differs from current {ch['differs_from_current']}, p <= {NULL_ALPHA} {ch['p_max_le_alpha']}, "
          f"beats current with t >= {T_BAR} {ch['beats_current_on_discovery']}.")
    cu = d["current"]
    w(f"- Current rule ({cu['cell']}): {fm(cu['mean_per_day'])} a day over {cu['trades']} trades, halves "
      f"{fm(cu['half_means'][0])} / {fm(cu['half_means'][1])}, eligible {cu['eligible']}.\n")
    w("| Rank | Cell | Score $/day | Mean $/day | Trades | 2013-16 | 2017-20 |")
    w("|---|---|---|---|---|---|---|")
    for i, t in enumerate(d["top"], 1):
        w(f"| {i} | {t['cell']} | {fm(t['score'])} | {fm(t['mean_per_day'])} | {t['trades']} | "
          f"{fm(t['half_means'][0])} | {fm(t['half_means'][1])} |")
    w("\nBest eligible cell for each candle minute:\n")
    w("| Candle | Best cell | Score $/day |")
    w("|---|---|---|")
    for k, v in d["best_by_candle"].items():
        w(f"| {k} | {v['cell'] if v else 'none eligible'} | {fm(v['score']) if v else '—'} |")
    w(f"\n## Confirmation 2021-01-01 .. 2026-10-20 ({c['days']} days): {c['chosen']}\n")
    cs = c["chosen_stats"]
    w(f"**{'CONFIRMED' if c['confirmed'] else 'NOT CONFIRMED'}** (per-day mean > 0 with Newey-West t >= {T_BAR}): "
      f"{fm(cs['mean_per_day'])} a day, t {fm(cs['nw_t_per_day'])}; {cs['trades']} trades, {fm(cs['mean_per_trade'])} "
      f"a trade, {fm(cs['share_trades_won'], pct=True)} won, worst {fm(cs['worst_trade'])}.\n")
    if "beats_current" in c:
        bc = c["chosen_vs_current_per_day"]
        w(f"Against the current rule: {fm(bc['mean'])} a day (t {fm(bc['t'])}): "
          f"{'better' if c['beats_current'] else 'not shown better'}.\n")
    else:
        w("The configuration tested is the current rule, so this result is about the current rule at real prices. "
          "It does not show that the current rule is the best setting.\n")
    w("| | Days | $/day | t | Trades | $/trade | Won | Median | Worst |")
    w("|---|---|---|---|---|---|---|---|---|")
    for name, s in (("chosen", cs), ("current", c["current_stats"])):
        w(f"| {name} | {s['days']} | {fm(s['mean_per_day'])} | {fm(s['nw_t_per_day'])} | {s['trades']} | "
          f"{fm(s['mean_per_trade'])} | {fm(s['share_trades_won'], pct=True)} | {fm(s['median_trade'])} | {fm(s['worst_trade'])} |")
    for per, v in c["subperiods"].items():
        for name in ("chosen", "current"):
            s = v[name]
            w(f"| {name} {per} | {s['days']} | {fm(s['mean_per_day'])} | {fm(s['nw_t_per_day'])} | {s['trades']} | "
              f"{fm(s['mean_per_trade'])} | {fm(s['share_trades_won'], pct=True)} | {fm(s['median_trade'])} | "
              f"{fm(s['worst_trade'])} |")
    w("\nThe current rule at every strike, real prices, 2021-2026 (descriptive; not a second test):\n")
    w("| Strike | Trades | $/trade | Won | Median | Worst | $/day | t |")
    w("|---|---|---|---|---|---|---|---|")
    for k, s in c["current_rule_all_offsets"].items():
        w(f"| {k} | {s['trades']} | {fm(s['mean_per_trade'])} | {fm(s['share_trades_won'], pct=True)} | "
          f"{fm(s['median_trade'])} | {fm(s['worst_trade'])} | {fm(s['mean_per_day'])} | {fm(s['nw_t_per_day'])} |")
    cv = res.get("cost_versions")
    if cv:
        w("\n## Fee and fill price (descriptive; decides nothing)\n")
        w(f"Every decision above used the ask and a ${FEE:.2f} fee. The same trades with a ${FEE_HIGH:.2f} fee, and "
          f"bought at the mid instead of the ask (${FEE:.2f} fee):\n")
        w("| Config | Period | Version | Days | $/day | t | Trades | $/trade | Won | Median | Worst |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        vname = {"ask_fee_0.09": f"ask, ${FEE:.2f}", "ask_fee_0.74": f"ask, ${FEE_HIGH:.2f}",
                 "mid_fee_0.09": f"mid, ${FEE:.2f}"}
        for name, v in cv.items():
            for per, vers in v["periods"].items():
                for vk, s in vers.items():
                    w(f"| {name} ({v['cell']}) | {per} | {vname.get(vk, vk)} | {s['days']} | {fm(s['mean_per_day'])} | "
                      f"{fm(s['nw_t_per_day'])} | {s['trades']} | {fm(s['mean_per_trade'])} | "
                      f"{fm(s['share_trades_won'], pct=True)} | {fm(s['median_trade'])} | {fm(s['worst_trade'])} |")
    w(f"\n## Model check: the strike ladder's model against real prices ({mv['trades']} strong-body trades, 2021-2026)\n")
    g = mv["settle_gap_official_vs_d1_1559"]
    w(f"Official close minus the D1 15:59 close the model settled on, on the {g.get('days', 0)} days in the table: "
      f"mean {fm(g.get('mean'))} points, mean size {fm(g['mean_abs'], sign=False)}, 95th percentile of the size "
      f"{fm(g['p95_abs'], sign=False)}.\n")
    w("Ratios are mean / median over the trades.\n")
    w("| Strike | n | Model price | Real mid | Real ask | Mid / model | Ask / model | Model $/trade | Real $/trade | "
      "Real - model | t |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, v in mv["by_offset"].items():
        if not v.get("n"):
            w(f"| {k} | 0 | | | | | | | | | |")
            continue
        w(f"| {k} | {v['n']} | {fm(v['mean_model_price'], sign=False)} | {fm(v.get('mean_real_mid'), sign=False)} | "
          f"{fm(v['mean_real_ask'], sign=False)} | {fm(v.get('mean_mid_over_model'), sign=False)} / "
          f"{fm(v['median_mid_over_model'], sign=False)} | {fm(v.get('mean_ask_over_model'), sign=False)} / "
          f"{fm(v['median_ask_over_model'], sign=False)} | {fm(v['mean_model_pnl'])} | "
          f"{fm(v['mean_real_pnl'])} | {fm(v['mean_real_minus_model_pnl'])} | {fm(v['nw_t_diff'])} |")
    fc = res.get("fill_check")
    if fc:
        w("\n## Fill check: did trading happen near the ask? (trade bars, descriptive; decides nothing)\n")
        w(f"Trade bars from `{fc['folder']}`: {fc['bar_files_at_start']} day files and {fc['none_markers_at_start']} "
          "no-expiry markers when the run started. A bar covers the trades in the entry minute; \"last\" is the "
          "minute's last trade. Prices are per share (x100 per contract).\n")
        if fc.get("note"):
            w(f"**{fc['note'][0].upper() + fc['note'][1:]}.**\n")
        if fc["by_config"]:
            w("| Config | Period | Priced entries | With a bar file (days) | Traded in the entry minute | "
              "Low <= ask (of traded) | Last - mid, mean | Last - mid, median |")
            w("|---|---|---|---|---|---|---|---|")
            for name, pers in fc["by_config"].items():
                for per, s in pers.items():
                    w(f"| {name} | {per} | {s['entries_priced']} | {s['entries_with_bar_file']} "
                      f"({s['days_with_bar_file']}) | {s['entries_traded']} ({fm(s['share_traded'], pct=True)}) | "
                      f"{fm(s['share_low_le_ask_of_traded'], pct=True)} | {fm(s['mean_last_minus_mid'])} | "
                      f"{fm(s['median_last_minus_mid'])} |")
    w("\n## Caveats\n")
    w("- The 2021-2026 index outcomes were already used to test the current rule; the confirmation is fresh for "
      "option prices and for any changed setting, not fully independent.")
    w("- Signals come from D1 (a CFD), entries from real quotes at the minute's open; a fill at the quoted ask "
      "ignores order size and fast minutes, and a real order may fill worse.")
    w("- Before 2016 SPXW had a same-day expiry only on Fridays (and some month-ends), then Monday, Wednesday and "
      "Friday, and daily from 2022. Days without one are not in the sample, so discovery has few days before 2016, "
      "and its days fall on different weekdays than 2022-2026.")
    w("- Nothing here is a trading recommendation.")
    return "\n".join(L) + "\n"


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.floating):
        o = float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


TRADE_COLUMNS = ["config", "cell", "date", "period", "signal", "entry_minute", "implied_spot", "kind", "strike", "ask",
                 "mid", "pnl_fee_0.09", "pnl_fee_0.74", "pnl_mid_fee_0.09", "status", "bar_file", "bar_volume",
                 "bar_low", "bar_close"]


def write_outputs(res: dict, rows: list, write_atomic, out_json: Path = OUT_JSON, out_md: Path = OUT_MD,
                  out_trades: Path = OUT_TRADES) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TRADE_COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if (isinstance(v, float) and not math.isfinite(v)) else
                        (f"{v:.6f}".rstrip("0").rstrip(".") if isinstance(v, float) else v)) for k, v in r.items()})
    write_atomic(out_trades, buf.getvalue())
    write_atomic(out_json, json.dumps(jsonable(res), indent=1, allow_nan=False) + "\n")
    write_atomic(out_md, render_md(jsonable(res)))


# ------------------------------------------------------------------------------------------------
# self-test on synthetic data only
# ------------------------------------------------------------------------------------------------
def _bach(is_call, S, K, sig):
    from scipy.stats import norm
    d = (S - K) / sig
    c = (S - K) * norm.cdf(d) + sig * norm.pdf(d)
    return c if is_call else c - (S - K)


def _synthetic_day_text(day: str, S: float, minute_list, drop=(), crossed=()):
    lines = ["ts_recv,ts_event,rtype,publisher_id,instrument_id,side,price,size,flags,bid_px_00,ask_px_00,bid_sz_00,"
             "ask_sz_00,bid_pb_00,ask_pb_00,symbol"]
    y, mo, dd = int(day[:4]), int(day[5:7]), int(day[8:10])
    for hm in minute_list:
        t = datetime(y, mo, dd, int(hm[:2]), int(hm[3:]), tzinfo=ET).astimezone(timezone.utc)
        ts = t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        for K in np.arange(atm_of(S) - 60, atm_of(S) + 61, 5.0):
            for kind in ("call", "put"):
                if (hm, kind, K) in drop:
                    continue
                mid = _bach(kind == "call", S, K, 5.0)
                bid, ask = max(mid - 0.1, 0.0), mid + 0.1
                if (hm, kind, K) in crossed:
                    bid, ask = ask + 1, ask
                sym = f"{'SPXW':<6}{day[2:4]}{day[5:7]}{day[8:10]}{'C' if kind == 'call' else 'P'}{round(K * 1000):08d}"
                lines.append(f"{ts},,193,30,1,N,,0,200,{bid:.9f},{ask:.9f},10,10,0,0,{sym}")
    return "\n".join(lines) + "\n"


def selftest() -> None:
    scan = load_module("spx_candle_scan_ro", SCAN_PY)
    assert N_CELLS == 2178 and len(CANDLES) == 11 and len(THRESHOLDS) == 11 and THRESHOLDS[4] == 0.60
    assert parse_symbol("SPXW  130405P01495000") == ("2013-04-05", "put", 1495.0)
    assert et_minute("2013-04-05T19:51:00.000000000Z") == "15:51"              # EDT
    assert et_minute("2013-12-06T20:51:00.000000000Z") == "15:51"              # EST
    assert valid_quote(0.0, 0.05) and not valid_quote(1.2, 1.1) and not valid_quote(0.1, 0.0) and not valid_quote(None, 1)
    # Review fixes: exact-minute same-day rows only; 3 parity strikes required; the whole null in quantiles
    assert on_minute_of_day("2013-04-05T19:51:00.000000000Z", "2013-04-05")
    assert not on_minute_of_day("2013-04-05T19:51:30.000000000Z", "2013-04-05")
    assert not on_minute_of_day("2013-04-05T19:51:00.000000001Z", "2013-04-05")
    assert not on_minute_of_day("2013-04-06T19:51:00.000000000Z", "2013-04-05")
    two = {("call", 4000.0): (5.0, 7.0), ("put", 4000.0): (3.0, 5.0),
           ("call", 4005.0): (2.0, 4.0), ("put", 4005.0): (5.0, 7.0)}
    assert implied_spot(two) is None
    assert null_quantile(np.array([1.0, 2.0, 3.0]), 50) == 2.0
    assert null_quantile(np.array([-np.inf, 1.0, 2.0]), 50) == 1.0
    assert null_quantile(np.array([-np.inf, -np.inf, 1.0, 2.0]), 50) is None
    assert null_quantile(np.array([-np.inf, 1.0, 2.0, 3.0]), 95) is not None
    late = ("2019-06-14T19:51:30.000000000Z,2019-06-14T19:51:29.000000000Z,193,30,1,N,1.0,1,0,"
            "1.000000000,2.000000000,1,1,0,0,SPXW  190614C02890000\n")
    tq = _synthetic_day_text("2019-06-14", 2891.3, ["15:51"])
    q_late, n_late = parse_quotes(tq + late, "2019-06-14")
    assert n_late["off_minute"] == 1 and q_late["15:51"][("call", 2890.0)][1] != 2.0
    # quotes, implied spot and the day cube
    day, S, X = "2019-06-14", 2891.3, 2899.0
    text = _synthetic_day_text(day, S, ["15:50", "15:51"],
                               drop={("15:51", "call", 2880.0)}, crossed={("15:51", "put", 2905.0)})
    q, n = parse_quotes(text, day)
    assert n["invalid"] == 1 and ("call", 2880.0) not in q["15:51"] and ("put", 2905.0) not in q["15:51"]
    assert abs(implied_spot(q["15:51"]) - S) < 1e-9
    up, dn, au, ad, mu, md, sp, at, r = day_cube(q, X)
    i, j = ENTRIES.index("15:51"), OFFSETS.index(10)
    assert at[i] == 2890.0 and abs(sp[i] - S) < 1e-9
    assert np.isnan(up[i, j]) and np.isnan(mu[i, j]) and r["no_quote"] >= 2    # 2880 call dropped -> not priced
    ja = OFFSETS.index(0)
    ask = _bach(True, S, 2890.0, 5.0) + 0.1
    assert abs(up[i, ja] - (100 * (9.0 - ask) - FEE)) < 1e-6
    assert abs(au[i, ja] - ask) < 1e-9 and abs(mu[i, ja] - (ask - 0.1)) < 1e-9     # mid = (bid + ask) / 2
    askp = _bach(False, S, 2900.0, 5.0) + 0.1                                  # down, ITM10 = put 2900
    assert abs(dn[i, j] - (100 * (1.0 - askp) - FEE)) < 1e-6
    assert abs(md[i, j] - (askp - 0.1)) < 1e-9
    assert np.isnan(dn[i, OFFSETS.index(15)])                                  # crossed 2905 put
    assert np.all(np.isnan(up[ENTRIES.index("15:41")]))                        # no quotes at 15:41 -> no spot
    assert r["no_spot"] == len(ENTRIES) - 2                                    # only 15:50 and 15:51 have quotes
    # signals: the 0.60 column equals scan.py's strong body
    rng = np.random.default_rng(3)
    o = rng.normal(100, 1, 500)
    c = o + rng.normal(0, 1, 500)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.5, 500))
    l_ = np.minimum(o, c) - np.abs(rng.normal(0, 0.5, 500))
    c[7] = np.nan
    a1, a2 = body_signal(o, h, l_, c, 0.60), scan.shape_strong_body(o, h, l_, c)
    assert np.array_equal(np.nan_to_num(a1, nan=9), np.nan_to_num(a2, nan=9))
    assert np.all(np.abs(body_signal(o, h, l_, c, 0.9)[np.isfinite(a1)]) <= np.abs(a1[np.isfinite(a1)]))
    # day_series
    s = np.array([1, -1, 0, np.nan, 1])
    U, D = np.array([10., 20, 30, 40, np.nan]), np.array([-1., -2, -3, -4, -5])
    assert np.array_equal(np.nan_to_num(day_series(s, U, D), nan=9), [10, -2, 0, 9, 9])
    # plateau
    m = np.zeros((1, 3, 1, 1))
    m[0, :, 0, 0] = [1.0, 4.0, np.nan]
    p = plateau(m)
    assert abs(p[0, 0, 0, 0] - 2.5) < 1e-12 and abs(p[0, 1, 0, 0] - 2.5) < 1e-12 and np.isnan(p[0, 2, 0, 0])
    selftest_grid()
    selftest_cost_versions()
    fc = selftest_fill_check()
    selftest_gate_and_outputs(scan, fc)
    print("selftest: all checks passed")


def _synthetic_grid(seed: int, plant: bool, n_disc: int = 900, n_hold: int = 500):
    rng = np.random.default_rng(seed)
    d1 = np.datetime64("2013-04-01") + np.sort(rng.choice(np.arange(0, 2830), n_disc, replace=False))
    d2 = np.datetime64("2021-01-04") + np.sort(rng.choice(np.arange(0, 2100), n_hold, replace=False))
    dates = np.array([str(x) for x in np.concatenate([d1, d2])])
    n = len(dates)
    body = rng.uniform(0, 1, (n, len(CANDLES)))
    sgn = rng.choice([-1.0, 1.0], (n, len(CANDLES)))
    sig = np.zeros((n, len(CANDLES), len(THRESHOLDS)))
    for b, th in enumerate(THRESHOLDS):
        sig[:, :, b] = np.where(body >= th, sgn, 0.0)
    up = rng.normal(-10, 250, (n, len(ENTRIES), len(OFFSETS)))
    dn = rng.normal(-10, 250, (n, len(ENTRIES), len(OFFSETS)))
    up[rng.uniform(size=up.shape) < 0.01] = np.nan                               # a few unpriced entries
    if plant:                                                                    # an edge only in 15:45, body >= 0.70, with, ITM5
        a, b, j = CANDLES.index("15:45"), THRESHOLDS.index(0.70), OFFSETS.index(5)
        on = sig[:, a, b]
        up[on > 0, a, j] += 240.0
        dn[on < 0, a, j] += 240.0
    return dates, sig, up, dn


def selftest_grid():
    # a planted edge is found, beats the current rule and survives the null
    dates, sig, up, dn = _synthetic_grid(11, plant=True)
    d = discovery(sig, up, dn, dates, step=40)
    assert d["best_cell"][0] == "15:45" and d["best_cell"][2] == 1 and d["best_cell"][3] == 5, d["best"]
    assert abs(d["best_cell"][1] - 0.70) <= 0.051, d["best"]
    assert d["p_max"] <= NULL_ALPHA and d["chosen"] == d["best_cell"], (d["p_max"], d["checks"])
    c = confirmation(d["chosen"], sig, up, dn, dates)
    assert c["confirmed"] and c.get("beats_current") is True
    assert set(c["current_rule_all_offsets"]) == {label(o) for o in OFFSETS}
    # pure noise: the pick does not survive, the current rule is what gets confirmed
    dates, sig, up, dn = _synthetic_grid(12, plant=False)
    d = discovery(sig, up, dn, dates, step=40)
    assert d["chosen"] == CURRENT, d.get("checks")
    c = confirmation(d["chosen"], sig, up, dn, dates)
    assert "beats_current" not in c and c["chosen"] == cell_name(CURRENT)
    # grid_means agrees with a direct computation for one cell
    full = grid_means(sig[:300], up[:300], dn[:300], [np.ones(300, bool)])[0]
    x = series(("15:43", 0.55, -1, -10), sig[:300], up[:300], dn[:300])
    a, b, di, j = idx_of(("15:43", 0.55, -1, -10))
    assert abs(full["mean"][a, b, di, j] - np.nanmean(x)) < 1e-9
    assert full["n_trades"][a, b, di, j] == int((np.isfinite(x) & (sig[:300, a, b] != 0)).sum())
    # null with shift 0 equals the observed grid (sanity of the roll)
    S = sig[None, :300]
    g0 = grid_means(S, up[:300], dn[:300], [np.ones(300, bool)])[0]
    assert np.allclose(np.nan_to_num(g0["mean"][0]), np.nan_to_num(full["mean"]))


def _fake_cube(dates, up, dn, spread: float = 0.05, seed: int = 5) -> dict:
    rng = np.random.default_rng(seed)
    au, ad = rng.uniform(0.5, 30, up.shape), rng.uniform(0.5, 30, dn.shape)
    au[np.isnan(up)], ad[np.isnan(dn)] = np.nan, np.nan
    return {"dates": dates, "up": up, "dn": dn, "ask_up": au, "ask_dn": ad, "mid_up": au - spread,
            "mid_dn": ad - spread, "spot": np.full(up.shape[:2], 4000.0), "atm": np.full(up.shape[:2], 4000.0)}


def selftest_cost_versions():
    assert abs((FEE_HIGH - FEE) - 0.65) < 1e-12
    dates, sig, up, dn = _synthetic_grid(13, plant=False, n_disc=400, n_hold=300)
    cube = _fake_cube(dates, up, dn)
    cells = {"chosen": ("15:45", 0.70, -1, 5), "current": CURRENT}
    cv = cost_versions(cells, sig, cube)
    assert set(cv) == {"chosen", "current"} and cv["current"]["cell"] == cell_name(CURRENT)
    for name, c in cells.items():
        a, b, di, _ = idx_of(c)
        for per, (lo, hi) in PERIODS:
            m = (dates >= lo) & (dates <= hi)
            v = cv[name]["periods"][per]
            base, high, mid = v["ask_fee_0.09"], v["ask_fee_0.74"], v["mid_fee_0.09"]
            assert base == describe(series(c, sig[m], up[m], dn[m]), sig[m, a, b] * DIRECTIONS[di])   # = criterion
            assert base["days"] == high["days"] == mid["days"] == int(np.isfinite(series(c, sig, up, dn)[m]).sum())
            assert base["trades"] == high["trades"] == mid["trades"] > 20
            assert abs(high["mean_per_trade"] - (base["mean_per_trade"] - (FEE_HIGH - FEE))) < 1e-9
            assert abs(high["mean_per_day"] - (base["mean_per_day"]
                                               - (FEE_HIGH - FEE) * base["trades"] / base["days"])) < 1e-9
            assert abs(mid["mean_per_trade"] - (base["mean_per_trade"] + MULT * 0.05)) < 1e-9
            assert abs(mid["mean_per_day"] - (base["mean_per_day"] + MULT * 0.05 * base["trades"] / base["days"])) < 1e-9


def _occ(expiry: str, kind: str, K: float) -> str:
    return f"{'SPXW':<6}{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{'C' if kind == 'call' else 'P'}{round(K * 1000):08d}"


def _synthetic_bars_text(day: str, bars) -> str:
    """bars: (HH:MM ET, kind, K, low, close, volume, expiry). Columns deliberately not in Databento's order."""
    lines = ["symbol,volume,close,low,high,open,instrument_id,publisher_id,rtype,ts_event"]
    y, mo, dd = int(day[:4]), int(day[5:7]), int(day[8:10])
    for hm, kind, K, lo, cl, vol, exp in bars:
        t = datetime(y, mo, dd, int(hm[:2]), int(hm[3:]), tzinfo=ET).astimezone(timezone.utc)
        ts = t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        lines.append(f"{_occ(exp, kind, K)},{vol},{cl:.9f},{lo:.9f},{max(lo, cl):.9f},{cl:.9f},1,30,33,{ts}")
    return "\n".join(lines) + "\n"


def selftest_fill_check() -> dict:
    """Synthetic quote and trade-bar files: traded at or below the ask, traded above it, not traded (no bar, and a
    bar with volume 0), a missing file, an unreadable file, a no-expiry marker; then the case with no files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        qdir, bdir = tmp / "q", tmp / "b"
        qdir.mkdir(), bdir.mkdir()
        days = ["2019-06-14", "2019-06-17", "2019-06-18", "2019-06-19", "2021-06-21"]
        closes = {d: 2899.0 for d in days}
        for d in days:
            (qdir / f"{d}.csv.gz").write_bytes(gzip.compress(_synthetic_day_text(d, 2891.3, ENTRIES).encode()))
        cube = assemble(days, closes, lambda d: load_day_quotes(d, qdir))
        assert list(cube["dates"]) == days and cube["mid_up"].shape == cube["up"].shape
        chosen = ("15:45", 0.70, -1, 5)
        sig = np.zeros((len(days), len(CANDLES), len(THRESHOLDS)))
        for c in (CURRENT, chosen):
            a, b, _, _ = idx_of(c)
            sig[:, a, b] = 1.0
        rows = trade_rows({"chosen": chosen, "current": CURRENT}, cube, sig)
        assert len(rows) == 10 and all(r["status"] == "priced" for r in rows)
        R = {(r["config"], r["date"]): r for r in rows}
        cur, cho = R[("current", "2019-06-14")], R[("chosen", "2019-06-14")]
        assert (cur["kind"], cur["strike"], cur["entry_minute"], cur["period"]) == ("call", 2880.0, "15:51", "discovery")
        assert (cho["kind"], cho["strike"], cho["entry_minute"]) == ("put", 2895.0, "15:46")
        assert R[("current", "2021-06-21")]["period"] == "confirmation"
        assert abs(cur["mid"] - (cur["ask"] - 0.1)) < 1e-9
        assert abs(cur["pnl_fee_0.74"] - (cur["pnl_fee_0.09"] - (FEE_HIGH - FEE))) < 1e-9
        assert abs(cur["pnl_mid_fee_0.09"] - (MULT * (2899.0 - 2880.0 - cur["mid"]) - FEE)) < 1e-6
        # day 1: the current rule's call traded at or below the ask, the chosen put traded only above it
        b1 = [("15:51", "call", 2880.0, cur["ask"] - 0.3, cur["mid"] + 0.05, 7, "2019-06-14"),
              ("15:46", "put", 2895.0, cho["ask"] + 0.2, cho["mid"] + 0.30, 3, "2019-06-14"),
              ("15:50", "call", 2880.0, 0.01, 99.0, 5, "2019-06-14"),             # another minute: not the entry
              ("15:51", "call", 2880.0, 0.01, 99.0, 5, "2019-06-21")]             # another expiry: dropped
        # day 2: no bar for the current rule's call; the chosen put has a bar with volume 0
        cho2 = R[("chosen", "2019-06-17")]
        b2 = [("15:46", "put", 2895.0, cho2["ask"] - 1.0, cho2["mid"], 0, "2019-06-17"),
              ("15:51", "call", 2885.0, 0.5, 0.5, 4, "2019-06-17")]                # a neighbouring strike
        (bdir / "2019-06-14.csv.gz").write_bytes(gzip.compress(_synthetic_bars_text("2019-06-14", b1).encode()))
        (bdir / "2019-06-17.csv.gz").write_bytes(gzip.compress(_synthetic_bars_text("2019-06-17", b2).encode()))
        (bdir / "2019-06-19.csv.gz").write_bytes(b"not a gzip file")                # unreadable
        (bdir / "2021-06-21.none").write_text("x\n")                                 # 2019-06-18: no file at all
        listing = bar_listing(bdir)
        assert listing == {"2019-06-14": "file", "2019-06-17": "file", "2019-06-19": "file", "2021-06-21": "none"}
        assert bar_listing(tmp / "no_such_folder") == {}
        bars, st = load_day_bars("2019-06-14", listing, bdir)
        assert st == "ok" and bars["15:51"][("call", 2880.0)][2] == 7 and ("call", 2880.0) in bars["15:50"]
        assert load_day_bars("2019-06-19", listing, bdir) == (None, "unreadable")
        assert load_day_bars("2019-06-18", listing, bdir) == (None, "missing")
        assert load_day_bars("2021-06-21", listing, bdir) == (None, "none")
        fc = fill_check(rows, listing, lambda d: load_day_bars(d, listing, bdir))
        assert fc["bar_files_at_start"] == 3 and fc["none_markers_at_start"] == 1 and fc["note"] is None
        c = fc["by_config"]["current"]["discovery"]
        assert (c["entries_priced"], c["entries_with_bar_file"], c["days_with_bar_file"], c["entries_no_bar_file"],
                c["entries_unreadable_file"], c["entries_traded"]) == (4, 2, 2, 1, 1, 1), c
        assert c["share_traded"] == 0.5 and c["share_low_le_ask_of_traded"] == 1.0
        assert abs(c["mean_last_minus_mid"] - 0.05) < 1e-8 and abs(c["median_last_minus_mid"] - 0.05) < 1e-8
        h = fc["by_config"]["chosen"]["discovery"]
        assert h["entries_traded"] == 1 and h["share_traded"] == 0.5 and h["share_low_le_ask_of_traded"] == 0.0
        assert abs(h["mean_last_minus_mid"] - 0.30) < 1e-8
        for name in ("chosen", "current"):
            k = fc["by_config"][name]["confirmation"]
            assert (k["entries_priced"], k["entries_with_bar_file"], k["entries_no_bar_file"]) == (1, 0, 1)
            assert k["share_traded"] is None and k["mean_last_minus_mid"] is None
        assert R[("current", "2019-06-14")]["bar_volume"] == 7 and R[("current", "2019-06-14")]["bar_file"] == "ok"
        assert R[("chosen", "2019-06-17")]["bar_volume"] == 0 and R[("current", "2019-06-17")]["bar_volume"] == 0
        assert R[("current", "2019-06-18")]["bar_file"] == "missing" and np.isnan(R[("current", "2019-06-18")]["bar_low"])
        assert R[("current", "2019-06-19")]["bar_file"] == "unreadable"
        # no trade-bar files at all: it says so and does not stop
        fc0 = fill_check([dict(r) for r in rows], {}, lambda d: load_day_bars(d, {}, bdir))
        assert fc0["bar_files_at_start"] == 0 and "not computed" in fc0["note"]
        assert all(v["entries_with_bar_file"] == 0 and v["share_traded"] is None
                   for p in fc0["by_config"].values() for v in p.values())
        assert fill_check([], {}, lambda d: (None, "missing"))["by_config"] == {}
        return fc


def selftest_gate_and_outputs(scan, fc_computed: dict):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pre, led = tmp / "x.md", tmp / "LEDGER.md"
        led.write_text("nothing\n")
        for setup in ("missing", "unlisted"):
            if setup == "unlisted":
                pre.write_text("plan\n")
            try:
                check_gate(pre, led)
                raise AssertionError("gate did not refuse")
            except SystemExit:
                pass
        led.write_text(f"- t  {hashlib.sha256(pre.read_bytes()).hexdigest()}  x.md\n")
        assert check_gate(pre, led)
        # closes: parse, check against a fake Robinhood dict
        cl = parse_cboe("DATE,SPX\n06/14/2019,2899.000000\n06/17/2019,2889.670000\n06/18/2019,2917.750000\n")
        assert cl == {"2019-06-14": 2899.0, "2019-06-17": 2889.67, "2019-06-18": 2917.75}
        assert check_closes(cl, {k: (v, "x") for k, v in cl.items()})["overlap_days"] == 3
        try:
            check_closes(cl, {"2019-06-14": (2899.5, "x"), "2019-06-17": (2889.67, "x"), "2019-06-18": (2917.75, "x")})
            raise AssertionError("close check did not refuse")
        except SystemExit:
            pass
        # assemble from files in a temp folder: one priced day, one no-expiry day, one missing
        folder = tmp / "db"
        folder.mkdir()
        (folder / "2019-06-14.csv.gz").write_bytes(gzip.compress(_synthetic_day_text("2019-06-14", 2891.3, ENTRIES).encode()))
        (folder / "2019-06-17.none").write_text("x\n")
        cube = assemble(["2019-06-14", "2019-06-17", "2019-06-18"], cl, lambda d: load_day_quotes(d, folder))
        assert list(cube["dates"]) == ["2019-06-14"] and cube["drops"]["no_expiry"] == 1
        assert cube["drops"]["missing_file"] == ["2019-06-18"] and cube["up"].shape == (1, len(ENTRIES), len(OFFSETS))
        assert np.isfinite(cube["up"]).all() and np.isfinite(cube["dn"]).all()
        # model validation on one synthetic trade (real strikes.py pricing helpers, fake trade list)
        import types
        strikes = load_module("spx_candle_strikes_ro", STRIKES_PY)
        fake = types.SimpleNamespace(**{k: getattr(strikes, k) for k in
                                        ("bachelier", "contract_for", "strike_for", "SQRT_REMAINING", "HALF_SPREAD")})
        fake.strong_body_trades = lambda scan_, P_: {"dates": np.array(["2019-06-14", "2019-06-17"]),
                                                     "d": np.array([1, -1]), "S": np.array([2891.3, 2890.0]),
                                                     "X": np.array([2899.5, 2889.17]), "rv": np.array([2e-4, 2e-4])}
        mv = model_validation(fake, scan, None, cl, cube["q1551"])
        atm_m = mv["by_offset"]["ATM"]
        ask = _bach(True, 2891.3, 2890.0, 5.0) + 0.1
        assert atm_m["n"] == 1 and abs(atm_m["mean_real_pnl"] - (100 * (9.0 - ask) - FEE)) < 1e-6
        assert abs(atm_m["mean_real_ask"] - ask) < 1e-9
        sg = mv["settle_gap_official_vs_d1_1559"]
        assert sg["days"] == 1 and abs(sg["mean"] + 0.5) < 1e-9 and abs(sg["mean_abs"] - 0.5) < 1e-9 and mv["trades"] == 2
        # outputs from a synthetic result
        dates, sig, up, dn = _synthetic_grid(11, plant=True, n_disc=400, n_hold=200)
        d = discovery(sig, up, dn, dates, step=60)
        c = confirmation(d["chosen"], sig, up, dn, dates)
        mv = {"trades": 0, "by_offset": {label(o): {"n": 0} for o in OFFSETS},
              "settle_gap_official_vs_d1_1559": {"mean_abs": None, "p95_abs": None}}
        res = {"prereg_sha256": "0" * 64, "data": {"priced_days": len(dates), "no_expiry_days": 0, "closes_source": "cboe",
                                                    "close_check": {"overlap_days": 3, "max_abs_diff": 0.0},
                                                    "unpriced": {"no_spot": 0, "no_quote": 0}},
               "discovery": d, "confirmation": c, "model_validation": mv}
        fake_cube = _fake_cube(dates, up, dn)
        cells = {"chosen": d["chosen"], "current": CURRENT}
        res["cost_versions"] = cost_versions(cells, sig, fake_cube)
        rows = trade_rows(cells, fake_cube, sig)
        res["fill_check"] = fill_check(rows, {}, lambda d_: (None, "missing"))          # no trade-bar files
        cfo = load_module("candle_1550_options_forward_ro", OPTIONS_PY)
        write_outputs(res, rows, cfo.write_atomic, tmp / "r.json", tmp / "r.md", tmp / "t.csv")
        md = (tmp / "r.md").read_text()
        assert "## Discovery" in md and "## Confirmation" in md and "CONFIRMED" in md and "| ITM10 |" in md
        assert "## Fee and fill price" in md and "| ask, $0.74 |" in md and "| mid, $0.09 |" in md
        assert "## Fill check" in md and "Part 4 was not computed" in md
        assert "different weekdays" in md
        back = json.loads((tmp / "r.json").read_text())
        assert back["discovery"]["n_cells"] == N_CELLS and back["fill_check"]["bar_files_at_start"] == 0
        assert set(back["cost_versions"]["current"]["periods"]) == {"discovery", "confirmation"}
        with open(tmp / "t.csv", newline="") as fh:
            rd = csv.DictReader(fh)
            got = list(rd)
            assert rd.fieldnames == TRADE_COLUMNS
        assert len(got) == len(rows) and {r["config"] for r in got} == {"chosen", "current"}
        assert {r["period"] for r in got} == {"discovery", "confirmation"}
        g = next(r for r in got if r["status"] == "priced")
        assert abs(float(g["pnl_fee_0.74"]) - (float(g["pnl_fee_0.09"]) - (FEE_HIGH - FEE))) < 1e-5
        assert abs(float(g["pnl_mid_fee_0.09"]) - (float(g["pnl_fee_0.09"]) + MULT * 0.05)) < 1e-5
        assert g["bar_file"] == "missing" and g["bar_low"] == ""
        # the computed fill check renders its table; the current-rule-confirmed text appears when chosen == current
        res["fill_check"] = fc_computed
        res["confirmation"] = confirmation(CURRENT, sig, up, dn, dates)
        md2 = render_md(jsonable(res))
        assert "| current | discovery | 4 | 2 (2) | 1 (50%) | 100% | +0.05 | +0.05 |" in md2, md2
        assert "| chosen | discovery | 4 | 2 (2) | 1 (50%) | 0% | +0.30 | +0.30 |" in md2
        assert "| current | confirmation | 1 | 0 (0) | 0 (—) | — | — | — |" in md2
        assert "3 day files and 1 no-expiry markers" in md2 and "not computed" not in md2
        assert "It does not show that the current rule is the best setting" in md2


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        r = run()
        print(f"discovery: {r['discovery']['decision']}; confirmation of {r['confirmation']['chosen']}: "
              f"{'CONFIRMED' if r['confirmation']['confirmed'] else 'NOT CONFIRMED'}")
        print(f"wrote {OUT_MD}, {OUT_JSON}, {OUT_TRADES}")
    else:
        raise SystemExit("usage: realprice.py selftest | run")
