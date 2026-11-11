#!/usr/bin/env python3
"""v2: can a take-profit, trailing-stop or give-back exit beat holding the 15:50 candle trade?

Plan: preregistration/spx_candle_exit_timing_v2.md (draft: backtests/spx_candle_exit_timing_v2/PREREG_DRAFT.md),
an addendum to the locked preregistration/spx_candle_exit_timing.md (v1). This is v1's exit_timing.py with v2's
changes: only the 26 bid-based rules (TS, PL, TP), coverage on the option's quotes only, v2 file paths.

  python3 -B exit_timing_v2.py selftest   synthetic data only, written to a temp folder
  python3 -B exit_timing_v2.py tune       2021-01-01 .. 2023-12-31, once (needs the locked plan)
  python3 -B exit_timing_v2.py test       2024-01-01 .. 2026-10-20, once, after tune

Research only. Nothing here places an order or is a trading recommendation.
"""
from __future__ import annotations

import contextlib
import csv
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
RP_PY = ROOT / "backtests" / "spx_candle_realprice" / "realprice.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rp = _load_module("realprice_readonly", RP_PY)      # primitives only: parse_quotes, valid_quote, implied_spot, ...

ET = ZoneInfo("America/New_York")

# The plan text this code implements. tune and test refuse a locked plan with any other SHA-256.
PLAN_SHA256 = "46ec5be8281db521eff8bde3ec16e1831ad0771102eaa2412b8098feedcbf301"

TUNE = ("2021-01-01", "2023-12-31")
H1 = ("2021-01-01", "2022-09-30")
H2 = ("2022-10-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-20")
YEARS = ("2024", "2025", "2026")
CONFIG, ENTRY_MIN = "current", "15:51"

SNAPS = [f"15:{m}" for m in range(51, 60)]          # snapshots 15:51 .. 15:59 (start of each minute)
DECIDE = SNAPS[1:-1]                                # decision minutes 15:52 .. 15:58
DECIDE_ZERO = SNAPS[1:]                             # zero-delay version only: 15:52 .. 15:59
L_REF = 7709.58                                     # index level the SR points are expressed at
FEE, FEE_HIGH, MULT = 0.09, 0.74, 100.0
TOL = 1e-9                                          # comparisons allow 1e-9 toward firing
MIN_SALES, MIN_SALES_HALF = 25, 10
BLOCK, N_DRAWS, SEED, ALPHA = 5, 9999, 20261109, 0.05
T_BAR, TEST_MIN_SALES, TEST_MIN_BLOCKS = 2.0, 25, 10
COVERAGE_MIN = 0.95
EXPECT_TUNE = {"n": 270, "h1": 133, "h2": 137, "mean": 68.78, "mean_h1": 149.97, "mean_h2": -10.03}
EXPECT_TEST = {"n": 315, "mean": 66.32}

TUNE_HEAD = "## Part 1: tuning (2021-01-01 .. 2023-12-31)"
PART2_HEAD = "## Part 2: test (2024-01-01 .. 2026-10-20)"
PART3_HEAD = "## Part 3: test period, looked at after the decision"
NOTES_HEAD = "## Notes"
RUNS_HEAD = "## Runs"


class IsolationError(RuntimeError):
    pass


class SimulatedCrash(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------
# rules
# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    name: str
    fam: str            # TS, PL, SR, TP, SRV; OLD for the six earlier rules (context only)
    p1: object
    p2: object
    i1: int = 0
    i2: int | None = None


def _pct(x: float) -> str:
    return str(int(round(x * 100)))


def build_rules() -> list:
    out = []
    for i, x in enumerate((0.10, 0.20, 0.30, 0.40, 0.50)):
        out.append(Rule(f"TS{_pct(x)}", "TS", x, None, i, None))
    for i, g in enumerate((0.10, 0.20, 0.30)):
        for j, (h, hn) in enumerate(((1 / 3, "33"), (2 / 3, "67"), (1.0, "100"))):
            out.append(Rule(f"PL{_pct(g)}_{hn}", "PL", g, h, i, j))
    for i, a in enumerate((3.0, 5.0, 8.0)):
        for j, b in enumerate((2.0, 3.0, 5.0)):
            out.append(Rule(f"SR{int(a)}_{int(b)}", "SR", a, b, i, j))
    for i, t in enumerate(("15:52", "15:54", "15:56", "15:58")):
        for j, g in enumerate((0.10, 0.20, 0.30)):
            out.append(Rule(f"TP{t.replace(':', '')}_{_pct(g)}", "TP", t, g, i, j))
    for i, al in enumerate((0.35, 0.60, 0.95)):
        for j, be in enumerate((0.25, 0.35, 0.60)):
            out.append(Rule(f"SRV{_pct(al)}_{_pct(be)}", "SRV", al, be, i, j))
    return out


V1_RULES = build_rules()                                # v1's 44 (SR and SRV kept only for the selftest)
assert len(V1_RULES) == 44
RULES = [r for r in V1_RULES if r.fam in ("TS", "PL", "TP")]      # v2: the 26 bid-based rules
assert len(RULES) == 26
RULE_INDEX = {r.name: i for i, r in enumerate(RULES)}
EARLIER = [Rule("S3", "OLD", -3.0, None), Rule("S5", "OLD", -5.0, None), Rule("S8", "OLD", -8.0, None),
           Rule("T5", "OLD", None, 5.0), Rule("T10", "OLD", None, 10.0), Rule("S5_T10", "OLD", -5.0, 10.0)]


def neighbours(rules: list) -> list:
    """Same family, one step along one axis with the other fixed."""
    out = []
    for a, ra in enumerate(rules):
        out.append([b for b, rb in enumerate(rules) if b != a and rb.fam == ra.fam and
                    abs(ra.i1 - rb.i1) + abs((ra.i2 or 0) - (rb.i2 or 0)) == 1])
    return out


def plateau_matrix(rules: list) -> np.ndarray:
    """W with score = W @ mean: the average of a rule's mean d and its neighbours' mean d."""
    nb = neighbours(rules)
    W = np.zeros((len(rules), len(rules)))
    for a, lst in enumerate(nb):
        for b in [a] + lst:
            W[a, b] = 1.0 / (1 + len(lst))
    return W


W_PLATEAU = plateau_matrix(RULES)


# ------------------------------------------------------------------------------------------------
# trades and paths
# ------------------------------------------------------------------------------------------------
@dataclass
class Trade:
    date: str
    period: str          # tuning | test
    half: str            # H1 | H2 | "" (test)
    side: int            # +1 call, -1 put
    kind: str
    K: float
    A: float             # 15:51 ask, per share
    S0: float            # implied spot in the 15:51 snapshot
    X: float | None      # 15:51 ATM straddle mid, or None if not valid
    V: float             # settlement value per share
    bid: dict            # minute -> bid of the contract, or None
    mid: dict
    spot: dict           # minute -> implied spot, or None
    complete: bool = False

    @property
    def H(self) -> float:
        return MULT * (self.V - self.A) - FEE

    def u(self, t: str):
        s = self.spot.get(t)
        return None if s is None else self.side * (s - self.S0) * L_REF / self.S0

    def r(self, t: str):
        s = self.spot.get(t)
        return None if s is None else self.side * (s - self.S0)


@dataclass
class Outcome:
    fire: str | None
    sale: str | None
    px: float | None
    R: float
    d: float
    status: str          # held | sold | rolled | fired_settled
    skipped: int         # decision minutes with no decision (a missing input)

    @property
    def sold(self) -> bool:
        return self.sale is not None


def _ge(a: float, b: float) -> bool:
    return a >= b - TOL


def _le(a: float, b: float) -> bool:
    return a <= b + TOL


def first_fire(rule: Rule, tr: Trade, decide=DECIDE) -> tuple:
    """(first decision minute at which the rule fires, or None; decision minutes skipped for a missing input)."""
    b_star = tr.bid[SNAPS[0]]                      # a priced entry always has its 15:51 bid
    u_star = r_star = 0.0
    skipped = 0
    for t in SNAPS[1:]:
        b, u, r = tr.bid.get(t), tr.u(t), tr.r(t)
        if b is not None:                          # peaks use only snapshots t <= m that have the value
            b_star = max(b_star, b)
        if u is not None:
            u_star = max(u_star, u)
        if r is not None:
            r_star = max(r_star, r)
        if t not in decide:
            continue
        f = rule.fam
        if f in ("TS", "PL", "TP"):
            if b is None:
                skipped += 1
                continue
        elif f in ("SR", "OLD"):
            if u is None:
                skipped += 1
                continue
        elif f == "SRV":
            if tr.X is None or r is None:
                skipped += 1
                continue
        if f == "TS":
            hit = _le(b, (1.0 - rule.p1) * b_star)
        elif f == "PL":
            g_star = b_star - tr.A
            hit = _ge(g_star, rule.p1 * tr.A) and _le(b, b_star - rule.p2 * g_star)
        elif f == "SR":
            hit = _ge(u_star, rule.p1) and _le(u, u_star - rule.p2)
        elif f == "TP":
            hit = t >= rule.p1 and _ge(b, (1.0 + rule.p2) * tr.A)
        elif f == "SRV":
            hit = _ge(r_star, rule.p1 * tr.X) and _le(r, r_star - rule.p2 * tr.X)
        elif f == "OLD":
            hit = ((rule.p1 is not None and _le(u, rule.p1)) or (rule.p2 is not None and _ge(u, rule.p2)))
        else:
            raise ValueError(f)
        if hit:
            return t, skipped                      # the first trigger is final
    return None, skipped


def evaluate(rule: Rule, tr: Trade, mode: str = "primary") -> Outcome:
    """mode: primary (next snapshot's bid) | mid (same sale snapshot, at its mid) | zero (same snapshot, decisions to
    15:59) | fee74 (primary with the $0.74 fee on every leg, holding included)."""
    decide, delay = (DECIDE_ZERO, 0) if mode == "zero" else (DECIDE, 1)
    fire, skipped = first_fire(rule, tr, decide)
    sale, status = None, ("held" if fire is None else "fired_settled")
    if fire is not None:
        i = SNAPS.index(fire) + delay
        for k, t in enumerate(SNAPS[i:]):          # a missing sale quote rolls forward to 15:59 at the latest
            if tr.bid.get(t) is not None:
                sale, status = t, ("sold" if k == 0 else "rolled")
                break
    fee = FEE_HIGH if mode == "fee74" else FEE
    hold = MULT * (tr.V - tr.A) - fee
    if sale is None:
        return Outcome(fire, None, None, hold, 0.0, status, skipped)
    px = tr.mid[sale] if mode == "mid" else tr.bid[sale]
    R = MULT * (px - tr.A) - 2 * fee
    d = R - hold
    if mode in ("primary", "zero", "fee74") and abs(d - (MULT * (px - tr.V) - fee)) > 1e-6:
        raise AssertionError("d algebra")
    return Outcome(fire, sale, px, R, d, status, skipped)


def run_rules(trades: list, rules: list, mode: str = "primary") -> list:
    return [[evaluate(r, tr, mode) for r in rules] for tr in trades]


def matrices(outs: list) -> tuple:
    D = np.array([[o.d for o in row] for row in outs], float)
    S = np.array([[o.sold for o in row] for row in outs], bool)
    if D.size and not np.all(np.isfinite(D)):
        raise SystemExit("stopping: a non-finite d value")
    return D, S


# ------------------------------------------------------------------------------------------------
# selection, null, test
# ------------------------------------------------------------------------------------------------
def selection_stats(D: np.ndarray, sold: np.ndarray, h1: np.ndarray, h2: np.ndarray, signs_e: np.ndarray) -> dict:
    """Means, half means, scores and eligibility for each sign vector (rows of signs_e, one sign per entry).
    The observed values are the all-plus row, computed the same way."""
    n, n1, n2 = D.shape[0], int(h1.sum()), int(h2.sum())
    M = (signs_e @ D) / n
    M1 = (signs_e[:, h1] @ D[h1]) / n1
    M2 = (signs_e[:, h2] @ D[h2]) / n2
    S = M @ W_PLATEAU.T if D.shape[1] == len(RULES) else M
    cnt = sold.sum(0)
    cnt_ok = (cnt >= MIN_SALES) & (sold[h1].sum(0) >= MIN_SALES_HALF) & (sold[h2].sum(0) >= MIN_SALES_HALF)
    E = cnt_ok[None, :] & (M1 > 0) & (M2 > 0)
    return {"mean": M, "mean_h1": M1, "mean_h2": M2, "score": S, "eligible": E, "count": cnt}


def pick_index(score: np.ndarray, elig: np.ndarray, count: np.ndarray):
    idx = [i for i in range(len(score)) if elig[i]]
    if not idx:
        return None
    best = max(score[i] for i in idx)
    tied = [i for i in idx if score[i] == best]                    # exact ties only
    return min(tied, key=lambda i: (int(count[i]), i))            # fewer early sales, then enumeration order


def block_signs(n: int, n_draws: int, seed: int = SEED) -> np.ndarray:
    nb = math.ceil(n / BLOCK)
    signs = np.random.default_rng(seed).integers(0, 2, size=(n_draws, nb)) * 2 - 1
    return np.repeat(signs, BLOCK, axis=1)[:, :n].astype(float)


def null_best(D, sold, h1, h2, n_draws: int = N_DRAWS, seed: int = SEED) -> np.ndarray:
    st = selection_stats(D, sold, h1, h2, block_signs(D.shape[0], n_draws, seed))
    return np.where(st["eligible"], st["score"], -np.inf).max(1)


def p_value(nulls: np.ndarray, observed: float) -> float:
    return float((1 + int((nulls >= observed).sum())) / (1 + len(nulls)))


def quantile_inf(x: np.ndarray, q: float):
    """numpy's default linear percentile, or None when it would interpolate with a -inf draw."""
    x = np.sort(np.asarray(x, float))
    pos = q / 100.0 * (len(x) - 1)
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if not (np.isfinite(x[lo]) and np.isfinite(x[hi])):
        return None
    return float(x[lo] + (x[hi] - x[lo]) * (pos - lo))


def part2_from(d: np.ndarray, sold_idx: list) -> dict:
    d = np.asarray(d, float)
    if not np.all(np.isfinite(d)):
        raise SystemExit("stopping: a non-finite test d value")
    n_sold, blocks = len(sold_idx), len({i // BLOCK for i in sold_idx})
    out = {"entries": int(len(d)), "sold_early": n_sold, "blocks_with_sales": blocks,
           "blocks": math.ceil(len(d) / BLOCK)}
    st = rp.nw(d)
    out.update({"mean_d": st["mean"], "nw_t": st["t"]})
    if n_sold < TEST_MIN_SALES or blocks < TEST_MIN_BLOCKS:
        out.update({"result": "insufficient information",
                    "text": "insufficient information: neither confirmed nor rejected; holding stays"})
        return out
    ok = st["mean"] is not None and st["t"] is not None and st["mean"] > 0 and st["t"] >= T_BAR
    out["result"] = "beat holding" if ok else "not confirmed"
    out["text"] = ("the pick beat holding on 2024-2026 under the prespecified test, on historical data that had "
                   "already been examined; this is not independent confirmation") if ok else \
        "not confirmed; holding stays"
    return out


# ------------------------------------------------------------------------------------------------
# reading inputs (window first)
# ------------------------------------------------------------------------------------------------
def in_window(day, window) -> bool:
    if not (isinstance(day, str) and len(day) == 10 and day[4] == "-" and day[7] == "-"):
        return False
    return window[0] <= day <= window[1]


def half_of(day: str) -> str:
    return "H1" if in_window(day, H1) else ("H2" if in_window(day, H2) else "")


def _fin(x: str, what: str, day: str) -> float:
    v = rp.fnum(x)                                                     # None for text, NaN or infinity
    if v is None:
        raise SystemExit(f"stopping: {day}: {what} is not a finite number ({x!r})")
    return v


def read_entries(path: Path, window, log: list | None = None) -> tuple:
    """Priced 15:51 entries of the current rule in `window`. Each row's date is checked first; a row outside the
    window is dropped before any other field is converted."""
    if log is not None:
        log.append(("entries", window))
    out, dig = [], hashlib.sha256()
    with open(path, newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        ix = {h: i for i, h in enumerate(header)}
        dig.update(("\x1f".join(header) + "\n").encode())
        for rec in rd:
            day = rec[ix["date"]] if len(rec) > ix["date"] else ""
            if not in_window(day, window):
                continue
            dig.update(("\x1f".join(rec) + "\n").encode())
            if rec[ix["config"]] != CONFIG or rec[ix["status"]] != "priced":
                continue
            if rec[ix["entry_minute"]] != ENTRY_MIN:
                raise SystemExit(f"stopping: unexpected entry minute {rec[ix['entry_minute']]} on {day}")
            f = lambda k: _fin(rec[ix[k]], k, day)                          # noqa: E731
            sig = f("signal")
            if sig not in (1.0, -1.0):
                raise SystemExit(f"stopping: {day}: signal {rec[ix['signal']]!r} is not +1 or -1")
            out.append({"date": day, "signal": int(sig), "kind": rec[ix["kind"]],
                        "strike": f("strike"), "ask": f("ask"), "spot": f("implied_spot"), "pnl": f("pnl_fee_0.09")})
    days = [e["date"] for e in out]
    if len(set(days)) != len(days):
        raise SystemExit("stopping: two priced entries on one date")
    out.sort(key=lambda e: e["date"])
    return out, {"rows_sha256": dig.hexdigest(), "entries": len(out)}


def _csv_day(s: str):
    parts = s.split("/")
    if len(parts) != 3:
        return None
    m, d, y = parts
    return f"{y}-{m.zfill(2)}-{d.zfill(2)}"


def load_closes(path: Path, window, log: list | None = None) -> tuple:
    """Official Cboe closes in `window`; a record's DATE is parsed first and an out-of-window SPX field is never
    converted. Never downloads."""
    if log is not None:
        log.append(("closes", window))
    if not Path(path).exists():
        raise SystemExit(f"stopping: official closes file {path} is missing; this code never downloads it")
    out, dig = {}, hashlib.sha256()
    with open(path, newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        i_d, i_s = header.index("DATE"), header.index("SPX")
        for rec in rd:
            if len(rec) <= max(i_d, i_s):
                continue
            day = _csv_day(rec[i_d])
            if day is None or not in_window(day, window):
                continue
            dig.update(f"{day} {rec[i_s]}\n".encode())
            v = rp.fnum(rec[i_s])
            if v and v > 0:
                out[day] = v
    return out, {"rows_sha256": dig.hexdigest(), "closes": len(out)}


def window_loader(folder: Path, window, digests: dict, log: list | None = None):
    def load(day: str):
        if not in_window(day, window):
            raise IsolationError(f"quote file for {day} is outside the step's window {window}")
        if log is not None:
            log.append(("quotes", day))
        f = Path(folder) / f"{day}.csv.gz"
        if not f.exists():
            raise SystemExit(f"stopping: priced entry on {day} has no quote file {f}")
        raw = f.read_bytes()
        digests[day] = hashlib.sha256(raw).hexdigest()
        q, _ = rp.parse_quotes(gzip.decompress(raw).decode(), day)
        return q
    return load


def build_trade(e: dict, q: dict, close: float, period: str) -> Trade:
    kind, K = e["kind"], e["strike"]
    side = {"call": 1, "put": -1}.get(kind)
    if side is None or side != int(np.sign(e["signal"])):
        raise SystemExit(f"stopping: {e['date']}: kind {kind} does not match signal {e['signal']}")
    bid, mid, spot = {}, {}, {}
    for t in SNAPS:
        snap = q.get(t) or {}
        bq = snap.get((kind, K))
        bid[t] = bq[0] if bq else None
        mid[t] = (bq[0] + bq[1]) / 2 if bq else None
        spot[t] = rp.implied_spot(snap) if snap else None
    q51 = (q.get(SNAPS[0]) or {}).get((kind, K))
    if q51 is None or abs(q51[1] - e["ask"]) > 1e-9:
        raise SystemExit(f"stopping: {e['date']}: the 15:51 ask does not match the trades CSV")
    S0 = spot[SNAPS[0]]
    if S0 is None or abs(S0 - e["spot"]) > 1e-9:
        raise SystemExit(f"stopping: {e['date']}: the 15:51 implied spot does not match the trades CSV")
    V = rp.intrinsic(kind, K, close)
    if abs(V - ((e["pnl"] + FEE) / MULT + e["ask"])) > 1e-6:
        raise SystemExit(f"stopping: {e['date']}: settlement value does not match the trades CSV")
    snap51 = q.get(SNAPS[0]) or {}
    atm = rp.atm_of(S0)
    c, p = snap51.get(("call", atm)), snap51.get(("put", atm))
    X = (c[0] + c[1]) / 2 + (p[0] + p[1]) / 2 if (c and p) else None
    return Trade(e["date"], period, half_of(e["date"]) if period == "tuning" else "", side, kind, K, e["ask"], S0, X,
                 V, bid, mid, spot)


def set_complete(trades: list) -> None:
    """v2: complete = a valid quote for the option in every snapshot 15:51 .. 15:59 (no index level, no straddle)."""
    for tr in trades:
        tr.complete = all(tr.bid[t] is not None for t in SNAPS)


def hold_checks(trades: list, expect: dict | None, step: str) -> dict:
    H = np.array([t.H for t in trades])
    out = {"n": len(trades), "mean": float(H.mean()) if len(H) else None}
    if step == "tune":
        h1 = np.array([t.half == "H1" for t in trades])
        out.update({"h1": int(h1.sum()), "h2": int((~h1).sum()),
                    "mean_h1": float(H[h1].mean()) if h1.any() else None,
                    "mean_h2": float(H[~h1].mean()) if (~h1).any() else None})
    if expect is not None:
        for k, v in expect.items():
            got = out[k]
            ok = (got == v) if isinstance(v, int) else (got is not None and abs(got - v) <= 0.005 + 1e-9)
            if not ok:
                raise SystemExit(f"stopping: {step} hold check {k}: expected {v}, got {got}")
    return out


def coverage(trades: list) -> dict:
    def share(sel):
        sel = list(sel)
        return {"entries": len(sel), "complete": sum(t.complete for t in sel),
                "share": (sum(t.complete for t in sel) / len(sel)) if sel else None}
    return {"all": share(trades), "H1": share(t for t in trades if t.half == "H1"),
            "H2": share(t for t in trades if t.half == "H2")}


def coverage_ok(cov: dict) -> bool:
    return all(cov[k]["share"] is not None and cov[k]["share"] >= COVERAGE_MIN for k in ("all", "H1", "H2"))


# ------------------------------------------------------------------------------------------------
# descriptive statistics
# ------------------------------------------------------------------------------------------------
def pnl_stats(R) -> dict:
    R = np.asarray(R, float)
    if not len(R):
        return {"n": 0}
    return {"n": int(len(R)), "mean": float(R.mean()), "won": float((R > 0).mean()), "median": float(np.median(R)),
            "p5": float(np.percentile(R, 5)), "worst": float(R.min())}


def d_stats(d) -> dict:
    d = np.asarray(d, float)
    if not np.all(np.isfinite(d)):
        raise SystemExit("stopping: a non-finite d value")
    st = rp.nw(d)
    return {"n": st["n"], "mean_d": st["mean"], "nw_t": st["t"]}


def rule_summary(col: list, trades: list) -> dict:
    d = [o.d for o in col]
    out = d_stats(d)
    sold = [o.sold for o in col]
    out["sold_early"] = int(sum(sold))
    out["share_sold"] = float(np.mean(sold)) if col else None
    out["exit_minutes"] = {t: sum(1 for o in col if o.sale == t) for t in SNAPS[1:]}
    out["pnl"] = pnl_stats([o.R for o in col])
    out["no_decision_minutes"] = int(sum(o.skipped for o in col))
    out["rolled"] = int(sum(o.status == "rolled" for o in col))
    out["fired_settled"] = int(sum(o.status == "fired_settled" for o in col))
    return out


def context(trades: list) -> dict:
    H = np.array([t.H for t in trades])
    ceil, fixed = [], {}
    for t in trades:
        best = t.H
        for m in SNAPS[1:]:
            if t.bid[m] is not None:
                best = max(best, MULT * (t.bid[m] - t.A) - 2 * FEE)
        ceil.append(best)
    for m in SNAPS[1:]:
        keep = [t for t in trades if t.bid[m] is not None]
        R = [MULT * (t.bid[m] - t.A) - 2 * FEE for t in keep]
        d = [r - t.H for r, t in zip(R, keep)]
        fixed[m] = {"left_out": len(trades) - len(keep), "pnl": pnl_stats(R), **d_stats(d)}
    earlier = {r.name: rule_summary([evaluate(r, t) for t in trades], trades) for r in EARLIER}
    return {"hold": pnl_stats(H), "hold_nw": d_stats(H), "ceiling": pnl_stats(ceil),
            "ceiling_minus_hold": float(np.mean(np.array(ceil) - H)) if len(H) else None,
            "fixed_minute": fixed, "earlier_rules": earlier}


def versions(rule: Rule, trades: list) -> dict:
    return {m: rule_summary([evaluate(rule, t, m) for t in trades], trades) for m in ("primary", "mid", "zero", "fee74")}


# ------------------------------------------------------------------------------------------------
# files and run discipline
# ------------------------------------------------------------------------------------------------
@dataclass
class Env:
    trades_in: Path
    closes: Path
    quotes: Path
    prereg: Path
    ledger: Path
    out: Path
    trades_out: Path
    code_files: tuple
    plan_sha256: str
    expect_tune: dict | None = None
    expect_test: dict | None = None
    n_draws: int = N_DRAWS
    hook: object = None
    read_log: list = field(default_factory=list)

    def p(self, name: str) -> Path:
        return self.out / name


def default_env() -> Env:
    return Env(trades_in=rp.OUT_TRADES, closes=rp.CLOSES_CSV, quotes=rp.DB_DIR,
               prereg=ROOT / "preregistration" / "spx_candle_exit_timing_v2.md", ledger=rp.LEDGER, out=HERE,
               trades_out=ROOT / "data" / "spx_1549" / "databento" / "exit_timing_v2_trades.csv",
               code_files=(Path(__file__).resolve(), RP_PY), plan_sha256=PLAN_SHA256,
               expect_tune=EXPECT_TUNE, expect_test=EXPECT_TEST)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode())


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(float(o)) else None          # -inf draws are written as null
    return o


def dumps(o) -> str:
    return json.dumps(jsonable(o), indent=1, allow_nan=False) + "\n"


def _fsync_dir(d: Path) -> None:
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, text: str, readonly: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if readonly:
            os.chmod(tmp, 0o444)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    _fsync_dir(path.parent)


def put(path: Path, text: str, what: str, readonly: bool = False) -> None:
    """Write once. After a crash, an existing file must be reproduced exactly, else stop."""
    path = Path(path)
    if path.exists():
        if path.read_text() != text:
            raise SystemExit(f"stopping: {what} exists and the rerun did not reproduce it exactly ({path})")
        return
    atomic_write(path, text, readonly)


def _hook(env: Env, stage: str) -> None:
    if env.hook is not None:
        env.hook(stage)


@contextlib.contextmanager
def run_lock(env: Env, command: str):
    env.out.mkdir(parents=True, exist_ok=True)
    fd = os.open(env.p(".exit_timing_v2.lock"), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f"refusing to run {command}: another exit_timing_v2 run holds the lock")
        yield
    finally:
        os.close(fd)


def record_attempt(env: Env, command: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    atomic_write(env.p("runs") / f"{command}-{stamp}-{os.getpid()}.json",
                 dumps({"command": command, "started_utc": stamp, "pid": os.getpid()}))


def run_counts(env: Env) -> dict:
    d = env.p("runs")
    names = [p.name for p in d.glob("*.json")] if d.exists() else []
    return {c: sum(1 for n in names if n.startswith(c + "-")) for c in ("tune", "test")}


def gate(env: Env) -> str:
    if Path(env.prereg).parent.name != "preregistration":
        raise SystemExit(f"refusing to run: {env.prereg} is not in a preregistration/ folder")
    if not Path(env.ledger).exists():
        raise SystemExit(f"refusing to run: the ledger {env.ledger} is missing")
    h = rp.check_gate(env.prereg, env.ledger)
    if h != env.plan_sha256:
        raise SystemExit(f"refusing to run: the locked plan ({h}) is not the version this code implements "
                         f"({env.plan_sha256}); update and re-review the code first")
    return h


def freeze(path: Path, manifest: dict, what: str) -> None:
    put(path, dumps(manifest), what, readonly=True)


# -- shared files: hash the tuning part only ----------------------------------------------------------------
def md_sections(text: str) -> dict:
    """Preamble ('') and each '## ' section, keyed by its heading line."""
    out, key, buf = {}, "", []
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            if line.rstrip("\n") in out or line.rstrip("\n") == key:
                raise SystemExit(f"stopping: RESULTS.md has a duplicate heading: {line.strip()}")
            out[key] = "".join(buf)
            key, buf = line.rstrip("\n"), [line]
        else:
            buf.append(line)
    out[key] = "".join(buf)
    return out


def md_tuning_part(text: str) -> str:
    return md_sections(text).get(TUNE_HEAD, "")


def put_results_md(env: Env, text: str) -> None:
    """RESULTS.md: every section already written (Runs aside) must be reproduced exactly; new sections are added."""
    p = env.p("RESULTS.md")
    if p.exists():
        old, new = md_sections(p.read_text()), md_sections(text)
        for k, v in old.items():
            if k == RUNS_HEAD:
                continue
            if new.get(k) != v:
                raise SystemExit(f"stopping: RESULTS.md section {k or '(preamble)'} was not reproduced exactly")
    atomic_write(p, text)


def csv_lines(path: Path) -> list:
    return Path(path).read_text().splitlines(keepends=True) if Path(path).exists() else []


def csv_tuning_part(path: Path) -> str:
    lines = csv_lines(path)
    if not lines:
        return ""
    i = next(csv.reader([lines[0]])).index("period")
    return lines[0] + "".join(l for l in lines[1:] if next(csv.reader([l]))[i] == "tuning")


def tune_artifact_hashes(env: Env) -> dict:
    def fh(name):
        p = env.p(name)
        return sha256_bytes(p.read_bytes()) if p.exists() else None
    return {"inputs_tune.json": fh("inputs_tune.json"), "selection.json": fh("selection.json"),
            "selection.sha256": fh("selection.sha256"), "selection_time.json": fh("selection_time.json"),
            "tune_results.json": fh("tune_results.json"),
            "trades_csv_tuning_rows": sha256_text(csv_tuning_part(env.trades_out)),
            "RESULTS_md_tuning_section": sha256_text(md_tuning_part(env.p("RESULTS.md").read_text())
                                                     if env.p("RESULTS.md").exists() else "")}


def verify_before_test(env: Env) -> dict:
    sel_p, sha_p, done_p = env.p("selection.json"), env.p("selection.sha256"), env.p("tune_complete.json")
    if not (sel_p.exists() and sha_p.exists() and done_p.exists()):
        raise SystemExit("refusing to run test: tune has not completed")
    if sha_p.read_text().split()[0] != sha256_bytes(sel_p.read_bytes()):
        raise SystemExit("refusing to run test: selection.sha256 does not match selection.json")
    done = json.loads(done_p.read_text())
    now = tune_artifact_hashes(env)
    bad = [k for k, v in now.items() if done.get(k) != v]
    if bad:
        raise SystemExit(f"refusing to run test: tuning artifacts changed since tune completed: {bad}")
    return json.loads(sel_p.read_text())


# -- trades CSV -----------------------------------------------------------------------------------
BASE_COLS = ["date", "period", "half", "side", "kind", "strike", "A", "S0", "X", "V", "H", "complete"]
RULE_COLS = [f"{r.name}_{c}" for r in RULES for c in ("fire", "sale", "bid", "R", "d")]
PICK_COLS = ["pick", "pick_fire", "pick_sale", "pick_bid", "pick_R", "pick_d"]
ALL_COLS = BASE_COLS + RULE_COLS + PICK_COLS


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (bool, np.bool_)):
        return "1" if v else "0"
    if isinstance(v, (float, np.floating)):
        return repr(float(v))
    return str(v)


def trade_rows(trades: list, outs: list | None, pick: str | None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for k, t in enumerate(trades):
        row = [t.date, t.period, t.half, t.side, t.kind, t.K, t.A, t.S0, t.X, t.V, t.H, t.complete]
        if outs is None:
            row += [None] * len(RULE_COLS)
        else:
            for o in outs[k]:
                row += [o.fire, o.sale, o.px, o.R, o.d]
        if pick is not None and outs is not None:
            o = outs[k][RULE_INDEX[pick]]
            row += [pick, o.fire, o.sale, o.px, o.R, o.d]
        else:
            row += [None] * len(PICK_COLS)
        w.writerow([_cell(v) for v in row])
    return buf.getvalue()


def header_line() -> str:
    return ",".join(ALL_COLS) + "\n"


# ------------------------------------------------------------------------------------------------
# tune
# ------------------------------------------------------------------------------------------------
def load_window(env: Env, window, period: str) -> tuple:
    entries, e_dig = read_entries(env.trades_in, window, env.read_log)
    closes, c_dig = load_closes(env.closes, window, env.read_log)
    q_dig: dict = {}
    load = window_loader(env.quotes, window, q_dig, env.read_log)
    raw = []
    for e in entries:
        if e["date"] not in closes:
            raise SystemExit(f"stopping: no official close for entry {e['date']}")
        raw.append((e, load(e["date"]), closes[e["date"]]))
    manifest = {"window": list(window), "entries": e_dig, "closes": c_dig,
                "quote_files": {d: q_dig[d] for d in sorted(q_dig)}}
    return raw, manifest


def manifest_for(env: Env, step: str, plan_sha: str, inputs: dict) -> dict:
    return {"step": step, "plan_sha256": plan_sha,
            "code_sha256": {Path(f).name: sha256_bytes(Path(f).read_bytes()) for f in env.code_files},
            "inputs": inputs}


def run_tune(env: Env) -> dict:
    plan_sha = gate(env)
    with run_lock(env, "tune"):
        record_attempt(env, "tune")                                  # every start is recorded, refused ones too
        try:
            return _run_tune(env, plan_sha)
        except SystemExit:
            refresh_runs(env)                                        # the report's Runs line counts refused starts
            raise


def _run_tune(env: Env, plan_sha: str) -> dict:
    if env.p("tune_complete.json").exists():
        raise SystemExit("refusing to run tune: it already completed (tune_complete.json exists)")
    raw, inputs = load_window(env, TUNE, "tuning")
    freeze(env.p("inputs_tune.json"), manifest_for(env, "tune", plan_sha, inputs), "inputs_tune.json")
    _hook(env, "tune:after_inputs")
    trades = [build_trade(e, q, c, "tuning") for e, q, c in raw]
    set_complete(trades)
    hold = hold_checks(trades, env.expect_tune, "tune")
    cov = coverage(trades)
    res = {"plan_sha256": plan_sha, "hold": hold, "coverage": cov}
    h1 = np.array([t.half == "H1" for t in trades])
    h2 = np.array([t.half == "H2" for t in trades])
    if not coverage_ok(cov):
        sel = {"decision": "coverage too low; no pick", "goes_to_test": False, "failed_gates": ["coverage"],
               "pick": None, "score": None, "p": None, "coverage": cov}
        outs = None
    else:
        outs = run_rules(trades, RULES)
        D, S = matrices(outs)
        st = selection_stats(D, S, h1, h2, np.ones((1, len(trades))))
        score, elig, count = st["score"][0], st["eligible"][0], st["count"]
        k = pick_index(score, elig, count)
        sel = {"decision": None, "goes_to_test": False, "failed_gates": [], "pick": None, "score": None,
               "p": None, "coverage": cov, "eligible": [RULES[i].name for i in range(len(RULES)) if elig[i]]}
        nulls = None
        if k is None:
            sel["failed_gates"] = ["no eligible rule"]
        else:
            nulls = null_best(D, S, h1, h2, env.n_draws)
            p = p_value(nulls, float(score[k]))
            sel.update({"pick": RULES[k].name, "score": float(score[k]), "p": p,
                        "null": {"draws": int(len(nulls)), "seed": SEED, "block": BLOCK,
                                 "minus_inf_draws": int(np.isneginf(nulls).sum()),
                                 "median": quantile_inf(nulls, 50), "p95": quantile_inf(nulls, 95)}})
            res["null_best_draws"] = nulls                       # -inf (no eligible rule) is written as null
            if p > ALPHA:
                sel["failed_gates"] = ["p > 0.05"]
        sel["goes_to_test"] = not sel["failed_gates"]
        sel["decision"] = ("goes to the test" if sel["goes_to_test"] else
                           "No rule advanced under the prespecified rules (failed: "
                           + ", ".join(sel["failed_gates"]) + ")")
        res["rules"] = {}
        for i, r in enumerate(RULES):
            s = rule_summary([row[i] for row in outs], trades)
            s.update({"score": float(score[i]), "mean_h1": float(st["mean_h1"][0][i]),
                      "mean_h2": float(st["mean_h2"][0][i]), "eligible": bool(elig[i]),
                      "sold_h1": int(S[h1, i].sum()), "sold_h2": int(S[h2, i].sum())})
            res["rules"][r.name] = s
        res["top10"] = [RULES[i].name for i in sorted([i for i in range(len(RULES)) if elig[i]],
                                                       key=lambda i: (-score[i], int(count[i]), i))[:10]]
        if sel["pick"]:
            res["pick_versions"] = versions(RULES[RULE_INDEX[sel["pick"]]], trades)
        res["context"] = context(trades)
    sel_text = dumps(sel)
    sel_sha = sha256_text(sel_text)
    tp = env.p("selection_time.json")                  # written before the selection, bound to its hash, and kept
    if tp.exists():                                    # as first written across crash reruns
        if json.loads(tp.read_text()).get("selection_sha256") != sel_sha:
            raise SystemExit("stopping: selection_time.json belongs to a different selection")
    else:
        atomic_write(tp, dumps({"selection_written_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "selection_sha256": sel_sha}), readonly=True)
    put(env.p("selection.json"), sel_text, "selection.json", readonly=True)
    put(env.p("selection.sha256"), f"{sel_sha}  selection.json\n", "selection.sha256", readonly=True)
    _hook(env, "tune:after_selection")
    res["selection"] = sel
    put(env.p("tune_results.json"), dumps(res), "tune_results.json")
    put(env.trades_out, header_line() + trade_rows(trades, outs, sel.get("pick")), "trades CSV (tuning rows)")
    put_results_md(env, render_md(res, None, run_counts(env)))
    _hook(env, "tune:after_results")
    done = tune_artifact_hashes(env)
    done["completed_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    atomic_write(env.p("tune_complete.json"), dumps(done), readonly=True)
    return res


# ------------------------------------------------------------------------------------------------
# test
# ------------------------------------------------------------------------------------------------
def commit_decision(env: Env, decision: dict) -> None:
    p = env.p("results.json")
    if p.exists():
        old = json.loads(p.read_text())
        if dumps(old.get("decision")) != dumps(decision):
            raise SystemExit("stopping: results.json holds a different decision than the rerun reproduced")
        return
    atomic_write(p, dumps({"decision": decision, "complete": False}))


FORWARD = ("2026-10-21", "2099-12-31")


def _event(env: Env, name: str) -> None:
    env.read_log.append(("event", name))


def forward_part(env: Env, sel: dict) -> dict:
    """Days after 2026-10-20: the frozen pick (if one went to the test), else all the rules. Only dates after the day
    the selection was written (selection_time.json) are fresh. Inputs are frozen before anything is scored."""
    sel_day = json.loads(env.p("selection_time.json").read_text())["selection_written_utc"][:10]
    entries, e_dig = read_entries(env.trades_in, FORWARD, env.read_log)
    closes, c_dig = load_closes(env.closes, FORWARD, env.read_log)
    q_dig: dict = {}
    load = window_loader(env.quotes, FORWARD, q_dig, env.read_log)
    out = {"selection_written_date": sel_day, "priced_entries": len(entries), "no_close": [], "no_quote_file": [],
           "digests": {"entries": e_dig, "closes": c_dig}}
    raw = []
    for e in entries:
        if e["date"] not in closes:
            out["no_close"].append(e["date"])
        elif not (Path(env.quotes) / f"{e['date']}.csv.gz").exists():
            out["no_quote_file"].append(e["date"])
        else:
            raw.append((e, load(e["date"]), closes[e["date"]]))
    out["digests"]["quote_files"] = {d: q_dig[d] for d in sorted(q_dig)}
    freeze(env.p("inputs_forward.json"), {"step": "test (forward, after the decision)", "window": list(FORWARD),
                                          "inputs": out["digests"], "no_close": out["no_close"],
                                          "no_quote_file": out["no_quote_file"]}, "inputs_forward.json")
    trades = [build_trade(e, q, c, "forward") for e, q, c in raw]
    rules = [RULES[RULE_INDEX[sel["pick"]]]] if sel.get("goes_to_test") else RULES
    out["scored"] = "the pick" if sel.get("goes_to_test") else f"all {len(RULES)} rules (descriptive)"
    for g, sub in (("fresh", [t for t in trades if t.date > sel_day]),
                   ("historical", [t for t in trades if t.date <= sel_day])):
        out[g] = {"entries": len(sub), "hold": pnl_stats([t.H for t in sub]),
                  "rules": {r.name: {k: v for k, v in rule_summary([evaluate(r, t) for t in sub], sub).items()
                                     if k in ("n", "mean_d", "nw_t", "sold_early")} for r in rules} if sub else {}}
    return out


def refresh_runs(env: Env) -> None:
    p = env.p("RESULTS.md")
    if p.exists():
        text = p.read_text()
        i = text.find(RUNS_HEAD)
        atomic_write(p, (text[:i] if i >= 0 else text) + runs_section(run_counts(env)))


def run_test(env: Env) -> dict:
    plan_sha = gate(env)
    with run_lock(env, "test"):
        record_attempt(env, "test")
        try:
            return _run_test(env, plan_sha)
        except SystemExit:
            refresh_runs(env)                                        # the report's Runs line counts refused starts
            raise


def _run_test(env: Env, plan_sha: str) -> dict:
    rp_ = env.p("results.json")
    if rp_.exists() and json.loads(rp_.read_text()).get("complete"):
        raise SystemExit("refusing to run test: it already completed")
    sel = verify_before_test(env)                                # before any test-period input is read
    tune_res = json.loads(env.p("tune_results.json").read_text())
    if sel["failed_gates"] == ["coverage"]:
        put(env.p("inputs_test.json"), dumps({"step": "test", "plan_sha256": plan_sha, "inputs": None,
                                              "note": "nothing read: tune stopped on coverage"}),
            "inputs_test.json", readonly=True)
        decision = {"result": "no test (coverage)", "pick": None}
        commit_decision(env, decision)
        _event(env, "decision_written")
        res = {"decision": decision, "complete": False}
        put_results_md(env, render_md(tune_res, res, run_counts(env)))
        _hook(env, "test:after_md")
        res["complete"] = True                                    # completion is committed last
        atomic_write(rp_, dumps(res))
        return res
    if not sel["goes_to_test"]:                                  # decided by the selection alone: write it first
        decision = {"result": "no test", "pick": None, "reason": sel["decision"]}
        commit_decision(env, decision)
        _event(env, "decision_written")
    raw, inputs = load_window(env, TEST, "test")
    freeze(env.p("inputs_test.json"), manifest_for(env, "test", plan_sha, inputs), "inputs_test.json")
    _hook(env, "test:after_inputs")
    trades = [build_trade(e, q, c, "test") for e, q, c in raw]
    hold = hold_checks(trades, env.expect_test, "test")
    if sel["goes_to_test"]:
        rule = RULES[RULE_INDEX[sel["pick"]]]
        col = [evaluate(rule, t) for t in trades]                # only the pick until the decision is written
        decision = part2_from(np.array([o.d for o in col]), [i for i, o in enumerate(col) if o.sold])
        decision["pick"] = rule.name
        commit_decision(env, decision)
        _event(env, "decision_written")
    _hook(env, "test:after_decision")
    # Part 3: looked at after the decision
    _event(env, "part3_start")
    set_complete(trades)
    outs = run_rules(trades, RULES)
    part3 = {"hold": hold, "coverage": coverage(trades),
             "rules": {r.name: {k: v for k, v in rule_summary([row[i] for row in outs], trades).items()
                                if k in ("n", "mean_d", "nw_t", "sold_early", "share_sold")}
                       for i, r in enumerate(RULES)},
             "context": context(trades)}
    if sel["pick"]:
        i = RULE_INDEX[sel["pick"]]
        col = [row[i] for row in outs]
        part3["pick"] = rule_summary(col, trades)
        part3["pick_by_year"] = {y: d_stats([o.d for o, t in zip(col, trades) if t.date.startswith(y)])
                                 for y in YEARS}
        part3["pick_versions"] = versions(RULES[i], trades)
    part3["forward"] = forward_part(env, sel)
    res = {"decision": decision, "part3": part3, "complete": False}
    _hook(env, "test:after_part3")
    lines = csv_lines(env.trades_out)
    tuning_part = csv_tuning_part(env.trades_out)
    new_csv = tuning_part + trade_rows(trades, outs, sel.get("pick"))
    if len(lines) > tuning_part.count("\n") and "".join(lines) != new_csv:
        raise SystemExit("stopping: the trades CSV holds test rows the rerun did not reproduce")
    atomic_write(env.trades_out, new_csv)
    _hook(env, "test:after_csv")
    put_results_md(env, render_md(tune_res, res, run_counts(env)))
    _hook(env, "test:after_md")
    res["complete"] = True                                        # completion is committed last
    atomic_write(rp_, dumps(res))
    return res


# ------------------------------------------------------------------------------------------------
# RESULTS.md
# ------------------------------------------------------------------------------------------------
def fm(x, nd=2, sign=True, pct=False) -> str:
    if x is None:
        return "n/a"
    if pct:
        return f"{100 * x:.0f}%"
    s = f"{abs(x):,.{nd}f}"
    return (("+" if x >= 0 else "−") if sign else ("" if x >= 0 else "−")) + "$" + s


def ft(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def _rule_line(name: str, s: dict) -> str:
    ex = " ".join(f"{m[3:]}:{c}" for m, c in s["exit_minutes"].items() if c)
    p = s["pnl"]
    return (f"| {name} | {s.get('score') is not None and fm(s['score']) or 'n/a'} | {fm(s['mean_d'])} | "
            f"{ft(s['nw_t'])} | {fm(s.get('mean_h1'))} | {fm(s.get('mean_h2'))} | {s['sold_early']} "
            f"({s.get('sold_h1', '')}/{s.get('sold_h2', '')}) | {'yes' if s.get('eligible') else ''} | "
            f"{fm(p['mean'])} | {fm(p['won'], pct=True)} | {fm(p['median'])} | {fm(p['p5'])} | {fm(p['worst'])} | "
            f"{s['no_decision_minutes']}/{s['rolled']}/{s['fired_settled']} | {ex} |\n")


def _context_md(c: dict) -> str:
    w = []
    h = c["hold"]
    w.append(f"- Holding to settlement: {fm(h['mean'])} a trade, won {fm(h['won'], pct=True)}, median "
             f"{fm(h['median'])}, worst {fm(h['worst'])} ({h['n']} trades).\n")
    ce = c["ceiling"]
    w.append(f"- Hindsight ceiling (best of holding and any minute's bid; not tradable): {fm(ce['mean'])} a trade, "
             f"{fm(c['ceiling_minus_hold'])} against holding.\n\n")
    w.append("| Sell at the bid at | Trades (left out) | P&L / trade | Won | Against holding | t |\n|---|---|---|---|---|---|\n")
    for m, s in c["fixed_minute"].items():
        w.append(f"| {m} | {s['pnl']['n']} ({s['left_out']}) | {fm(s['pnl'].get('mean'))} | "
                 f"{fm(s['pnl'].get('won'), pct=True)} | {fm(s['mean_d'])} | {ft(s['nw_t'])} |\n")
    w.append("\nThe six earlier rules (SPX stops and targets, re-expressed at real bids; not candidates):\n\n")
    w.append("| Rule | Against holding | t | Sold early | P&L / trade |\n|---|---|---|---|---|\n")
    for n, s in c["earlier_rules"].items():
        w.append(f"| {n} | {fm(s['mean_d'])} | {ft(s['nw_t'])} | {s['sold_early']} | {fm(s['pnl']['mean'])} |\n")
    return "".join(w)


def _versions_md(v: dict) -> str:
    names = {"primary": "Primary (next minute's bid)", "mid": "Sold at the mid", "zero": "Zero delay (optimistic)",
             "fee74": "$0.74 fee"}
    w = ["| Version | Against holding | t | Sold early |\n|---|---|---|---|\n"]
    for k, s in v.items():
        w.append(f"| {names[k]} | {fm(s['mean_d'])} | {ft(s['nw_t'])} | {s['sold_early']} |\n")
    return "".join(w)


def render_md(tune: dict, test: dict | None, counts: dict) -> str:
    w = ["# Real-time exits for the 15:50 candle trade (v2: bid-based rules): results\n\n",
         "Plan: `preregistration/spx_candle_exit_timing_v2.md` (SHA-256 `" + tune["plan_sha256"] + "`), an addendum "
         "to the locked `spx_candle_exit_timing.md`. Research only; nothing here is a trading recommendation.\n\n"]
    sel = tune["selection"]
    w.append(TUNE_HEAD + "\n\n")
    cov = tune["coverage"]
    w.append(f"Coverage (complete entries): all {cov['all']['complete']}/{cov['all']['entries']}, "
             f"H1 {cov['H1']['complete']}/{cov['H1']['entries']}, H2 {cov['H2']['complete']}/{cov['H2']['entries']}. "
             f"Holding: {fm(tune['hold']['mean'])} a trade (H1 {fm(tune['hold'].get('mean_h1'))}, "
             f"H2 {fm(tune['hold'].get('mean_h2'))}).\n\n")
    w.append(f"**Decision: {sel['decision']}.**")
    if sel["failed_gates"] == ["coverage"]:
        w.append(" No rule advanced under the prespecified rules (failed gate: coverage).")
    if sel.get("pick"):
        nl = sel["null"]
        w.append(f" Pick {sel['pick']}, score {fm(sel['score'])}, luck diagnostic p = {sel['p']:.4f} "
                 f"(block sign-flip, a heuristic benchmark, not an exact test; null median "
                 f"{fm(nl['median'])}, 95th percentile {fm(nl['p95'])}, {nl['minus_inf_draws']} draws with no "
                 f"eligible rule).")
    w.append("\n\n")
    if "rules" in tune:
        w.append("Ten best eligible rules by score: " + (", ".join(tune["top10"]) or "none") + ".\n\n")
        w.append(f"All {len(RULES)} rules. \"Against holding\" is the mean of d over all tuning trades (0 where the rule held). "
                 "Sold early: total (H1/H2). Missing: no-decision minutes / rolled to a later bid / fired but "
                 "settled. Exits: sale minute:count.\n\n")
        w.append("| Rule | Score | Against holding | t | H1 | H2 | Sold early | Eligible | P&L / trade | Won | "
                 "Median | 5th pct | Worst | Missing | Exits |\n|" + "---|" * 15 + "\n")
        for n, s in tune["rules"].items():
            w.append(_rule_line(n, s))
        w.append("\n")
        if tune.get("pick_versions"):
            w.append(f"Versions of the pick on tuning:\n\n{_versions_md(tune['pick_versions'])}\n")
        w.append("Context on tuning (the 585-trade versions were already seen):\n\n" + _context_md(tune["context"]) + "\n")
    if test is not None:
        dec = test["decision"]
        w.append(PART2_HEAD + "\n\n")
        if dec["result"] in ("beat holding", "not confirmed", "insufficient information"):
            w.append(f"**{dec['text'][0].upper() + dec['text'][1:]}.** Pick {dec['pick']}: against holding "
                     f"{fm(dec['mean_d'])} a trade, Newey-West t {ft(dec['nw_t'])}, sold early on "
                     f"{dec['sold_early']} of {dec['entries']} trades in {dec['blocks_with_sales']} of "
                     f"{dec['blocks']} blocks. 2024-2026 is not fresh for holding, and fixed-minute exits were "
                     f"already seen there.\n\n")
        else:
            w.append(f"**{dec['result']}.** {dec.get('reason', '')}\n\n")
        if "part3" in test:
            p3 = test["part3"]
            w.append(PART3_HEAD + "\n\n")
            c = p3["coverage"]["all"]
            w.append(f"Coverage: {c['complete']}/{c['entries']} complete. Holding: {fm(p3['hold']['mean'])} a trade "
                     f"({p3['hold']['n']} trades).\n\n")
            if p3.get("pick"):
                s = p3["pick"]
                w.append(f"The pick on 2024-2026: P&L {fm(s['pnl']['mean'])} a trade (holding "
                         f"{fm(p3['context']['hold']['mean'])}), won {fm(s['pnl']['won'], pct=True)}, median "
                         f"{fm(s['pnl']['median'])}, 5th percentile {fm(s['pnl']['p5'])}, worst "
                         f"{fm(s['pnl']['worst'])}. By year: " +
                         "; ".join(f"{y} {fm(v['mean_d'])} (t {ft(v['nw_t'])}, {v['n']})"
                                   for y, v in p3["pick_by_year"].items()) + ".\n\n")
                w.append(_versions_md(p3["pick_versions"]) + "\n")
            w.append(f"All {len(RULES)} rules on 2024-2026:\n\n| Rule | Against holding | t | Sold early |\n|---|---|---|---|\n")
            for n, s in p3["rules"].items():
                w.append(f"| {n} | {fm(s['mean_d'])} | {ft(s['nw_t'])} | {s['sold_early']} |\n")
            w.append("\nContext on 2024-2026:\n\n" + _context_md(p3["context"]) + "\n")
            f = p3["forward"]
            w.append(f"Days after 2026-10-20: {f['priced_entries']} priced entries in the trades file "
                     f"({f['fresh']['entries']} after the selection was written on {f['selection_written_date']}, "
                     f"fresh; {f['historical']['entries']} historical; skipped for no close "
                     f"{len(f['no_close'])}, for no quote file {len(f['no_quote_file'])}). Scored: {f['scored']}.\n\n")
            for g in ("fresh", "historical"):
                if f[g]["rules"]:
                    w.append(f"| {g.capitalize()} days: rule | Against holding | t | Sold early |\n|---|---|---|---|\n")
                    for n, s in f[g]["rules"].items():
                        w.append(f"| {n} | {fm(s['mean_d'])} | {ft(s['nw_t'])} | {s['sold_early']} |\n")
                    w.append("\n")
    w.append(NOTES_HEAD + "\n\n"
             "- Quotes are one-minute snapshots; a sale at the bid assumes one contract and a firm bid; the "
             "one-minute delay is a modelling choice.\n"
             "- A pass on 2024-2026 would be on historical data that had already been examined, not independent "
             "confirmation. If nothing goes to the test, that does not show holding is the best possible exit.\n"
             "- No trading recommendation.\n\n")
    w.append(runs_section(counts))
    return "".join(w)


def runs_section(counts: dict) -> str:
    return (RUNS_HEAD + f"\n\nStarted: tune {counts.get('tune', 0)} time(s), test {counts.get('test', 0)} time(s) "
            "(refused starts included).\n")


# ------------------------------------------------------------------------------------------------
# selftest: synthetic data only, in a temp folder
# ------------------------------------------------------------------------------------------------
def _expect_exit(fn, text: str, exc=(SystemExit,)):
    try:
        fn()
    except exc as e:                                                    # noqa: PERF203
        if text not in str(e):
            raise AssertionError(f"expected '{text}' in: {e}")
        return
    raise AssertionError(f"expected a stop containing '{text}'")


def _mk(bids, spots=None, A=10.0, V=10.0, side=1, X=8.6, half="H1") -> Trade:
    S0 = L_REF                                         # so u is in plain points
    spot = {t: (S0 if spots is None else (None if s is None else S0 + side * s)) for t, s in
            zip(SNAPS, spots or [0] * len(SNAPS))}
    bid = dict(zip(SNAPS, bids))
    mid = {t: (None if b is None else b + 0.1) for t, b in bid.items()}
    return Trade("2021-03-01", "tuning", half, side, "call" if side > 0 else "put", 7700.0, A, S0, X, V, bid, mid, spot,
                 True)


def _r(name: str) -> Rule:
    return next(r for r in V1_RULES + EARLIER if r.name == name)


def selftest_rules() -> None:
    #           51    52    53    54    55    56    57    58    59
    t = _mk([9.9, 10.5, 12.0, 11.5, 10.7, 10.6, 10.5, 10.4, 10.3])
    o = evaluate(_r("TS10"), t)                         # peak 12.0; 10.7 <= 10.8 at 15:55
    assert (o.fire, o.sale, o.px, o.status) == ("15:55", "15:56", 10.6, "sold"), o
    assert abs(o.R - (100 * (10.6 - 10.0) - 0.18)) < 1e-9 and abs(o.d - (100 * (10.6 - 10.0) - 0.09)) < 1e-9
    assert abs(o.d - (o.R - t.H)) < 1e-9
    t = _mk([9.9, 11.0, 11.5, 10.0, 10.0, 11.2, 10.0, 10.0, 10.0])
    o = evaluate(_r("TP1552_10"), t)
    assert (o.fire, o.sale, o.px) == ("15:52", "15:53", 11.5), o
    o = evaluate(_r("TP1556_10"), t)                    # waits for 15:56 although 11.0 was reached earlier
    assert (o.fire, o.sale) == ("15:56", "15:57"), o
    t = _mk([9.9, 11.2, 10.5, 9.95, 9.0, 9.0, 9.0, 9.0, 9.0])
    assert evaluate(_r("PL10_100"), t).fire == "15:54"  # back to the price paid
    assert evaluate(_r("PL10_33"), t).fire == "15:53"   # 10.5 <= 11.2 - 0.4
    assert evaluate(_r("PL20_33"), t).fire is None      # G* = 1.2 < 2.0
    t = _mk([9.9] * 9, spots=[0, 1.0, 3.5, 1.4, 0, 0, 0, 0, 0])
    assert evaluate(_r("SR3_2"), t).fire == "15:54"
    assert evaluate(_r("SR5_2"), t).fire is None
    t = _mk([9.9] * 9, spots=[0, -1.0, -3.0, 0, 0, 0, 0, 0, 0])
    assert evaluate(_r("S3"), t).fire == "15:53" and evaluate(_r("S5"), t).fire is None
    assert evaluate(_r("T5"), _mk([9.9] * 9, spots=[0, 2, 5.0, 0, 0, 0, 0, 0, 0])).fire == "15:53"
    # SRV: X = 8.6 -> thresholds 3.01 and 2.15 (in raw points; with S0 = L, r = u)
    t = _mk([9.9] * 9, spots=[0, 3.1, 0.9, 0, 0, 0, 0, 0, 0])
    assert evaluate(_r("SRV35_25"), t).fire == "15:53"
    t.X = None
    o = evaluate(_r("SRV35_25"), t)
    assert o.fire is None and o.skipped == len(DECIDE)
    # no decision at 15:59; zero delay decides there and sells at the same snapshot
    t = _mk([9.9, 10, 10, 10, 10, 10, 10, 10, 11.5])
    assert evaluate(_r("TP1552_10"), t).status == "held"
    o = evaluate(_r("TP1552_10"), t, "zero")
    assert (o.fire, o.sale, o.px) == ("15:59", "15:59", 11.5)
    # missing quotes: no decision for bid families, while SR still decides; roll forward; settle; no retrigger
    t = _mk([9.9, 10.5, 12.0, 11.5, None, 10.6, 10.5, 10.4, 10.3], spots=[0, 1, 3.5, 3.5, 1.0, 0, 0, 0, 0])
    o = evaluate(_r("TS10"), t)
    assert (o.fire, o.skipped, o.sale) == ("15:56", 1, "15:57"), o
    o = evaluate(_r("SR3_2"), t)
    assert o.fire == "15:55" and o.sale == "15:56" and o.skipped == 0
    # a missing spot with a bid: SR makes no decision at 15:54 while TS decides there
    t = _mk([9.9, 10.5, 12.0, 10.7, 10.6, 10.5, 10.4, 10.3, 10.2], spots=[0, 1, 3.5, None, 1.0, 0, 0, 0, 0])
    assert evaluate(_r("TS10"), t).fire == "15:54"
    o = evaluate(_r("SR3_2"), t)
    assert (o.fire, o.skipped) == ("15:55", 1), o
    t = _mk([9.9, 11.0, None, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0])
    o = evaluate(_r("TP1552_10"), t)
    assert (o.fire, o.sale, o.status, o.px) == ("15:52", "15:54", "rolled", 12.0), o
    t = _mk([9.9, 10, 10, 10, 10, 10, 11.5, None, None], V=11.0)
    o = evaluate(_r("TP1552_10"), t)
    assert (o.fire, o.sale, o.status, o.d) == ("15:57", None, "fired_settled", 0.0) and o.R == t.H
    # versions: mid at the same sale snapshot; $0.74 on every leg
    t = _mk([9.9, 11.0, 11.5, 10, 10, 10, 10, 10, 10], V=9.0)
    o_mid, o_74 = evaluate(_r("TP1552_10"), t, "mid"), evaluate(_r("TP1552_10"), t, "fee74")
    assert o_mid.sale == "15:53" and abs(o_mid.R - (100 * (11.6 - 10.0) - 0.18)) < 1e-9
    assert abs(o_74.d - (100 * (11.5 - 9.0) - 0.74)) < 1e-9
    # v2 completeness: only the option's quotes count; a missing index level or straddle does not
    t = _mk([9.9] * 9, spots=[0, 0, 0, 0, 0, 0, 0, None, 0])
    t.X = None
    set_complete([t])
    assert t.complete
    t = _mk([9.9, 10, 10, None, 10, 10, 10, 10, 10])
    set_complete([t])
    assert not t.complete
    assert [r.fam for r in RULES].count("TP") == 12 and {r.fam for r in RULES} == {"TS", "PL", "TP"}
    print("selftest: rules ok")


def selftest_selection() -> None:
    nb = neighbours(RULES)
    by = {r.name: [RULES[j].name for j in nb[i]] for i, r in enumerate(RULES)}
    assert sorted(by["TS10"]) == ["TS20"] and len(by["TS30"]) == 2
    assert sorted(by["PL20_67"]) == ["PL10_67", "PL20_100", "PL20_33", "PL30_67"]
    assert sorted(by["TP1552_10"]) == ["TP1552_20", "TP1554_10"] and len(by["TP1554_20"]) == 4
    assert all(RULES[j].fam == r.fam for i, r in enumerate(RULES) for j in nb[i])
    e = np.zeros(len(RULES)); k = RULE_INDEX["PL20_67"]; e[k] = 1.0
    sc = W_PLATEAU @ e
    assert abs(sc[k] - 1 / 5) < 1e-12 and abs(sc[RULE_INDEX["PL10_67"]] - 1 / 4) < 1e-12
    n = 60
    h1 = np.arange(n) < 30
    h2 = ~h1
    D = np.zeros((n, len(RULES)))
    S = np.zeros((n, len(RULES)), bool)
    for j, pattern in ((0, 13), (1, 12), (2, 13)):                  # sales per half
        for half in (h1, h2):
            idx = np.where(half)[0][:pattern]
            S[idx, j] = True
            D[idx, j] = 1.0
    D[np.where(h2)[0][:13], 2] = -1.0                              # rule 2 loses in H2
    st = selection_stats(D, S, h1, h2, np.ones((1, n)))
    el = st["eligible"][0]
    assert el[0] and not el[1] and not el[2]                         # 24 sales < 25; H2 mean < 0
    score = np.array([1.0, 1.0, 1.0] + [0.0] * (len(RULES) - 3))
    elig = np.array([True, True, True] + [False] * (len(RULES) - 3))
    cnt = np.array([30, 26, 26] + [0] * (len(RULES) - 3))
    assert pick_index(score, elig, cnt) == 1                         # fewer sales, then enumeration order
    assert pick_index(score, np.zeros(len(RULES), bool), cnt) is None
    print("selftest: plateau, eligibility, ties ok")


def selftest_null() -> None:
    rng = np.random.default_rng(7)
    n = 270
    h1 = np.arange(n) < 133
    h2 = ~h1
    S = rng.random((n, len(RULES))) < 0.4
    D = np.where(S, rng.normal(0, 30, (n, len(RULES))), 0.0)
    obs = selection_stats(D, S, h1, h2, np.ones((1, n)))
    k = pick_index(obs["score"][0], obs["eligible"][0], obs["count"])
    p0 = p_value(null_best(D, S, h1, h2, 1999), float(obs["score"][0][k])) if k is not None else 1.0
    assert p0 > 0.05, p0
    D2 = D.copy()
    j = RULE_INDEX["PL20_67"]
    for jj in [j] + neighbours(RULES)[j]:                            # a planted edge on a plateau
        D2[:, jj] = np.where(S[:, jj], rng.normal(25, 30, n), 0.0)
    obs = selection_stats(D2, S, h1, h2, np.ones((1, n)))
    k = pick_index(obs["score"][0], obs["eligible"][0], obs["count"])
    nulls = null_best(D2, S, h1, h2, 1999)
    p1 = p_value(nulls, float(obs["score"][0][k]))
    assert RULES[k].fam == "PL" and p1 < 0.01, (RULES[k].name, p1)
    x = np.array([-np.inf, -np.inf, 1.0, 2.0, 3.0])
    assert quantile_inf(x, 10) is None and abs(quantile_inf(x, 75) - 2.0) < 1e-12
    assert abs(quantile_inf(np.arange(5.0), 37) - np.percentile(np.arange(5.0), 37)) < 1e-12
    print(f"selftest: sign-flip null ok (no edge p = {p0:.3f}, planted edge p = {p1:.4f})")


def selftest_part2() -> None:
    rng = np.random.default_rng(3)
    d = np.zeros(315)
    few = list(range(0, 40, 1))                                      # 40 sales in 8 blocks
    d[few] = 50.0 + rng.normal(0, 5, len(few))
    assert part2_from(d, few)["result"] == "insufficient information"
    d = np.zeros(315)
    spread = list(range(0, 315, 15))                                 # 21 sales in 21 blocks: too few sales
    d[spread] = 80.0 + rng.normal(0, 5, len(spread))
    assert part2_from(d, spread)["result"] == "insufficient information"
    d = np.zeros(315)
    many = list(range(0, 315, 9))                                    # 35 sales in 35 blocks
    d[many] = 60.0 + rng.normal(0, 20, len(many))
    assert part2_from(d, many)["result"] == "beat holding"
    d[many] = rng.normal(0, 20, len(many))
    d[many] -= d[many].mean() - 0.5
    assert part2_from(d, many)["result"] == "not confirmed"
    print("selftest: test minimum-information rule ok")


# -- synthetic worlds -----------------------------------------------------------------------------
QUOTE_MINUTES = [f"15:{m}" for m in range(50, 60)] + ["16:00"]


def _bdays(lo: str, hi: str) -> list:
    d, end, out = datetime.strptime(lo, "%Y-%m-%d"), datetime.strptime(hi, "%Y-%m-%d"), []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _ts(day: str, hhmm: str) -> str:
    y, m, d = map(int, day.split("-"))
    hh, mm = map(int, hhmm.split(":"))
    t = datetime(y, m, d, hh, mm, tzinfo=ET).astimezone(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + ".000000000Z"


def _sym(day: str, kind: str, K: float) -> str:
    return f"SPXW  {day[2:4]}{day[5:7]}{day[8:10]}{'C' if kind == 'call' else 'P'}{int(round(K * 1000)):08d}"


def _syn_day(rng, day: str, mode: str, gap: bool) -> tuple:
    S0 = float(rng.uniform(3800, 4800))
    side = int(rng.choice([1, -1]))
    path = {}
    if mode == "edge" and rng.random() < 0.65:
        up, down = float(rng.uniform(5, 9)), float(rng.uniform(1, 4))
        shape = {"15:50": 0, "15:51": 0, "15:52": 0.6, "15:53": 1.0, "15:54": 0.7, "15:55": 0.3, "15:56": 0.0,
                 "15:57": -0.4, "15:58": -0.7, "15:59": -0.9, "16:00": -1.0}
        for t, v in shape.items():
            path[t] = S0 + side * (up * v if v >= 0 else down * v) + float(rng.normal(0, 0.2))
        path["15:51"] = S0
    else:
        s = S0
        for t in QUOTE_MINUTES:
            path[t] = s if t in ("15:50", "15:51") else s + float(rng.normal(0, 1.2))
            if t not in ("15:50",):
                s = path[t]
        path["15:51"] = S0
    atm = rp.atm_of(S0)
    kind = "call" if side > 0 else "put"
    K = atm - 10 * side
    rows = ["ts_recv,bid_px_00,ask_px_00,symbol\n"]
    for i, t in enumerate(QUOTE_MINUTES):
        St = path[t]
        rem = max(0.0, (len(QUOTE_MINUTES) - 1 - i) / 10.0)
        for k in range(-12, 13):
            Kk = atm + 5 * k
            tv = 0.15 + 1.5 * math.exp(-((Kk - St) / 12.0) ** 2) * math.sqrt(rem)
            for kd in ("call", "put"):
                if kd == kind and Kk == K:
                    mid = rp.intrinsic(kd, Kk, St) + 0.30 * math.sqrt(rem)
                    if gap and t == "15:55":
                        continue
                    b, a = max(0.05, mid - 0.35), mid + 0.35
                else:
                    mid = rp.intrinsic(kd, Kk, St) + tv
                    b, a = mid - 0.05, mid + 0.05
                rows.append(f"{_ts(day, t)},{b:.9f},{a:.9f},{_sym(day, kd, Kk)}\n")
    text = "".join(rows)
    close_str = f"{path['16:00']:.6f}"
    return text, side, kind, K, close_str


SYN_FORWARD = ("2026-10-21", "2026-12-31")


def syn_world(tmp: Path, seed: int, mode: str = "edge", gappy: bool = False,
              n_half: int = 60, n_test: int = 80, n_forward: int = 8) -> Env:
    tmp = Path(tmp)
    assert not str(tmp.resolve()).startswith(str(ROOT)), "selftest must stay outside the project"
    rng = np.random.default_rng(seed)
    qdir, pre = tmp / "quotes", tmp / "preregistration"
    qdir.mkdir(parents=True)
    pre.mkdir()
    days = []
    for (lo, hi), n, per in ((H1, n_half, "tuning"), (H2, n_half, "tuning"), (TEST, n_test, "test"),
                             (SYN_FORWARD, n_forward, "forward")):
        days += sorted(rng.choice(_bdays(lo, hi), size=n, replace=False).tolist())
    header = ["config", "cell", "date", "period", "signal", "entry_minute", "implied_spot", "kind", "strike", "ask",
              "mid", "pnl_fee_0.09", "pnl_fee_0.74", "pnl_mid_fee_0.09", "status", "bar_file", "bar_volume",
              "bar_low", "bar_close"]
    ent = [header, ["current", "c", "2020-06-01", "discovery", "x", "15:51", "junk", "call", "junk", "junk", "junk",
                    "junk", "", "", "priced", "", "", "", ""]]
    closes = [("06/01/2020", "junk")]
    H_by = {"tuning": [], "H1": [], "H2": [], "test": []}
    for i, day in enumerate(days):
        gap = gappy and in_window(day, H1) and rng.random() < 0.3
        text, side, kind, K, close_str = _syn_day(rng, day, mode, gap)
        (qdir / f"{day}.csv.gz").write_bytes(gzip.compress(text.encode(), mtime=0))
        q, _ = rp.parse_quotes(text, day)
        bq = q["15:51"][(kind, K)]
        S0 = rp.implied_spot(q["15:51"])
        V = rp.intrinsic(kind, K, float(close_str))
        pnl = MULT * (V - bq[1]) - FEE
        period = "test" if in_window(day, TEST) else "confirmation"
        row = ["current", "c", day, period, str(side), "15:51", repr(S0), kind, repr(K), repr(bq[1]),
               repr((bq[0] + bq[1]) / 2), repr(pnl), "", "", "priced", "", "", "", ""]
        ent.append(row)
        ent.append(["chosen"] + row[1:])
        if i % 17 == 0:
            ent.append(["current", "c", day, period, "x", "15:51", "junk", kind, "junk", "junk", "junk", "junk", "",
                        "", "not_priced", "", "", "", ""])
        y, m, d = day.split("-")
        closes.append((f"{m}/{d}/{y}", close_str))
        H = MULT * (V - bq[1]) - FEE
        if in_window(day, TEST):
            H_by["test"].append(H)
        elif in_window(day, TUNE):
            H_by["tuning"].append(H)
            H_by["H1" if in_window(day, H1) else "H2"].append(H)
    with open(tmp / "trades.csv", "w", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(ent)
    with open(tmp / "closes.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["DATE", "SPX"])
        w.writerows(sorted(closes, key=lambda r: r[0][-4:] + r[0][:5]))
    plan = "# synthetic plan for the selftest\n"
    (pre / "spx_candle_exit_timing.md").write_text(plan)
    (pre / "LEDGER.md").write_text("| other study | " + "a" * 64 + " |\n")
    r2 = lambda xs: round(float(np.mean(xs)), 2)                    # noqa: E731
    return Env(trades_in=tmp / "trades.csv", closes=tmp / "closes.csv", quotes=qdir,
               prereg=pre / "spx_candle_exit_timing.md", ledger=pre / "LEDGER.md", out=tmp / "out",
               trades_out=tmp / "out" / "exit_timing_trades.csv", code_files=(Path(__file__).resolve(), RP_PY),
               plan_sha256=sha256_text(plan), n_draws=1999,
               expect_tune={"n": len(H_by["tuning"]), "h1": len(H_by["H1"]), "h2": len(H_by["H2"]),
                            "mean": r2(H_by["tuning"]), "mean_h1": r2(H_by["H1"]), "mean_h2": r2(H_by["H2"])},
               expect_test={"n": len(H_by["test"]), "mean": r2(H_by["test"])})


def _lock_plan(env: Env) -> None:
    env.ledger.write_text(f"| synthetic | {sha256_bytes(env.prereg.read_bytes())} |\n")


def _artifacts(env: Env) -> dict:
    out = {}
    for name in ("selection.json", "selection.sha256", "tune_results.json", "results.json", "inputs_tune.json",
                 "inputs_test.json", "inputs_forward.json"):
        p = env.p(name)
        out[name] = p.read_text() if p.exists() else None
    out["trades"] = env.trades_out.read_text() if env.trades_out.exists() else None
    md = md_sections(env.p("RESULTS.md").read_text()) if env.p("RESULTS.md").exists() else {}
    md.pop(RUNS_HEAD, None)
    out["RESULTS.md"] = md
    return out


def _crash_at(stage: str):
    def hook(s):
        if s == stage:
            raise SimulatedCrash(stage)
    return hook


def selftest_worlds(tmp: Path) -> None:
    # gate
    env = syn_world(tmp / "gate", 11)
    _expect_exit(lambda: run_tune(env), "is not in")                # no ledger line yet
    _lock_plan(env)
    bad = Env(**{**env.__dict__, "plan_sha256": "0" * 64, "read_log": []})
    _expect_exit(lambda: run_tune(bad), "not the version this code implements")
    assert not bad.read_log and not env.p("selection.json").exists()
    # an edge world: a pick goes to the test and passes
    env = syn_world(tmp / "edge", 21)
    _lock_plan(env)
    res = run_tune(env)
    sel = res["selection"]
    assert sel["goes_to_test"] and sel["p"] <= 0.05, sel
    assert all(k == "quotes" and in_window(d, TUNE) or k != "quotes" for k, d in env.read_log)
    assert oct(env.p("selection.json").stat().st_mode)[-3:] == "444"
    _expect_exit(lambda: run_tune(env), "already completed")
    env.read_log.clear()
    res2 = run_test(env)
    assert res2["decision"]["result"] == "beat holding", res2["decision"]
    ev = [x for _, x in env.read_log]
    assert ev.index("decision_written") < ev.index("part3_start")
    assert not any(k == "quotes" and d > TEST[1] for k, d in env.read_log[:ev.index("decision_written")])
    assert all(in_window(d, TEST) or in_window(d, FORWARD) for k, d in env.read_log if k == "quotes")
    _expect_exit(lambda: run_test(env), "already completed")
    lines = env.trades_out.read_text().splitlines()
    assert len(lines) == 1 + env.expect_tune["n"] + env.expect_test["n"]
    md = md_sections(env.p("RESULTS.md").read_text())
    assert all(h in md for h in (TUNE_HEAD, PART2_HEAD, PART3_HEAD, NOTES_HEAD, RUNS_HEAD))
    assert "tune 2 time(s), test 2 time(s)" in md[RUNS_HEAD], md[RUNS_HEAD]
    fw = res2["part3"]["forward"]
    assert fw["priced_entries"] == 8 and fw["fresh"]["entries"] + fw["historical"]["entries"] == 8, fw
    assert fw["scored"] == "the pick" and list(fw["fresh"]["rules"] or fw["historical"]["rules"]) == [sel["pick"]]
    clean = _artifacts(env)
    print(f"selftest: edge world ok (pick {sel['pick']}, p = {sel['p']:.4f}, test t = "
          f"{res2['decision']['nw_t']:.2f})")
    # hold checks stop on a mismatch
    envh = syn_world(tmp / "hold", 21)
    _lock_plan(envh)
    envh.expect_tune = {**envh.expect_tune, "mean": envh.expect_tune["mean"] + 0.02}
    _expect_exit(lambda: run_tune(envh), "hold check mean")
    # crash recovery at each stage reproduces the clean run exactly
    for stage in ("tune:after_inputs", "tune:after_selection", "tune:after_results", "test:after_inputs",
                  "test:after_decision", "test:after_part3", "test:after_csv", "test:after_md"):
        e = syn_world(tmp / ("crash_" + stage.replace(":", "_")), 21)
        _lock_plan(e)
        e.hook = _crash_at(stage)
        try:
            run_tune(e)
            run_test(e)
            raise AssertionError(f"no crash at {stage}")
        except SimulatedCrash:
            pass
        e.hook = None
        if not e.p("tune_complete.json").exists():
            run_tune(e)
        run_test(e)
        got = _artifacts(e)
        for k in clean:
            if k in ("inputs_tune.json", "inputs_test.json", "inputs_forward.json", "selection.sha256",
                     "selection.json", "tune_results.json", "results.json", "trades", "RESULTS.md"):
                a, b = got[k], clean[k]
                if k == "RESULTS.md":
                    a = {h: v for h, v in a.items() if h != ""}
                    b = {h: v for h, v in b.items() if h != ""}
                if k.startswith("inputs_"):
                    a = json.loads(a)["inputs"] if a else a
                    b = json.loads(b)["inputs"] if b else b
                assert a == b, (stage, k)
    print("selftest: crash recovery ok at 8 stages")
    # the selection's timestamp survives a crash rerun; changed forward inputs after a crash stop the rerun
    e = syn_world(tmp / "crash_time", 21)
    _lock_plan(e)
    e.hook = _crash_at("tune:after_selection")
    _expect_exit(lambda: run_tune(e), "tune:after_selection", exc=(SimulatedCrash,))
    t0 = e.p("selection_time.json").read_text()
    e.hook = _crash_at("test:after_part3")
    run_tune(e)
    _expect_exit(lambda: run_test(e), "test:after_part3", exc=(SimulatedCrash,))
    assert e.p("selection_time.json").read_text() == t0
    assert json.loads(t0)["selection_sha256"] == sha256_text(e.p("selection.json").read_text())
    e2 = syn_world(tmp / "crash_time_other", 22)                     # a timestamp left by another selection stops
    _lock_plan(e2)
    e2.out.mkdir(parents=True, exist_ok=True)
    atomic_write(e2.p("selection_time.json"), dumps({"selection_written_utc": "2026-01-01T00:00:00Z",
                                                     "selection_sha256": "0" * 64}), readonly=True)
    _expect_exit(lambda: run_tune(e2), "belongs to a different selection")
    assert not e2.p("selection.json").exists()
    e.hook = None
    f = sorted(e.quotes.glob("2026-1[12]-*.csv.gz"))[-1]
    lines = gzip.decompress(f.read_bytes()).decode().splitlines(keepends=True)
    ts, b, a, sym = lines[1].rstrip("\n").split(",")
    lines[1] = f"{ts},{float(b) + 0.01:.9f},{a},{sym}\n"
    f.write_bytes(gzip.compress("".join(lines).encode(), mtime=0))
    _expect_exit(lambda: run_test(e), "inputs_forward.json exists and the rerun did not reproduce it")
    # a changed input after a crash stops the rerun
    e = syn_world(tmp / "crash_tamper", 21)
    _lock_plan(e)
    e.hook = _crash_at("tune:after_selection")
    _expect_exit(lambda: run_tune(e), "tune:after_selection", exc=(SimulatedCrash,))
    e.hook = None
    f = sorted(e.quotes.glob("2021-*.csv.gz"))[0]
    lines = gzip.decompress(f.read_bytes()).decode().splitlines(keepends=True)
    ts, b, a, sym = lines[1].rstrip("\n").split(",")
    lines[1] = f"{ts},{float(b) + 0.01:.9f},{a},{sym}\n"
    f.write_bytes(gzip.compress("".join(lines).encode(), mtime=0))
    _expect_exit(lambda: run_tune(e), "inputs_tune.json exists and the rerun did not reproduce it")
    # isolation: test checks the tuning artifacts before reading any test input
    e = syn_world(tmp / "iso", 21)
    _lock_plan(e)
    run_tune(e)
    p = e.p("RESULTS.md")
    p.write_text(p.read_text().replace("Ten best eligible rules", "Ten best eligible ruleZ"))
    e.read_log.clear()
    _expect_exit(lambda: run_test(e), "tuning artifacts changed")
    assert not e.read_log, e.read_log
    e2 = syn_world(tmp / "iso2", 21)
    _lock_plan(e2)
    run_tune(e2)
    s = e2.p("selection.json")
    os.chmod(s, 0o644)
    s.write_text(s.read_text().replace('"goes_to_test": true', '"goes_to_test": false'))
    e2.read_log.clear()
    _expect_exit(lambda: run_test(e2), "selection.sha256 does not match")
    assert not [x for x in e2.read_log if x[0] != "event"]
    assert "test 1 time(s)" in e2.p("RESULTS.md").read_text()      # refused starts are counted in the report
    e4 = syn_world(tmp / "iso3", 21)
    _lock_plan(e4)
    run_tune(e4)
    p4 = e4.p("RESULTS.md")
    secs = md_sections(p4.read_text())
    p4.write_text(secs[""] + secs[TUNE_HEAD].replace("Ten best", "Eleven best") + p4.read_text()[len(secs[""]):])
    _expect_exit(lambda: run_test(e4), "duplicate heading")
    _expect_exit(lambda: window_loader(e2.quotes, TUNE, {})("2024-03-01"), "outside the step's window",
                 exc=(IsolationError,))
    # the lock refuses a second run
    e3 = syn_world(tmp / "lock", 21)
    _lock_plan(e3)
    e3.out.mkdir(parents=True)
    fd = os.open(e3.p(".exit_timing_v2.lock"), os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        _expect_exit(lambda: run_tune(e3), "holds the lock")
    finally:
        os.close(fd)
    # non-finite entry fields stop the reader
    bad_csv = tmp / "nan_trades.csv"
    rows = list(csv.reader(open(e3.trades_in)))
    k = next(i for i, r in enumerate(rows) if r[0] == "current" and r[14] == "priced" and in_window(r[2], TUNE))
    rows[k][6] = "nan"
    with open(bad_csv, "w", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    _expect_exit(lambda: read_entries(bad_csv, TUNE), "implied_spot is not a finite number")
    print("selftest: isolation guards, tamper checks, the lock and finite checks ok")
    # a null world: nothing advances, the test step reports "no test" and still writes Part 3
    e = syn_world(tmp / "null", 31, mode="null")
    _lock_plan(e)
    sel = run_tune(e)["selection"]
    assert not sel["goes_to_test"], sel
    e.read_log.clear()
    r = run_test(e)
    assert r["decision"]["result"] == "no test" and "part3" in r
    ev = [x for _, x in e.read_log]
    assert ev.index("decision_written") < min(i for i, (k, _) in enumerate(e.read_log) if k in ("entries", "quotes"))
    assert r["part3"]["forward"]["scored"] == "all 26 rules (descriptive)"
    print(f"selftest: null world ok ({sel['decision']})")
    # coverage: too many missing quotes stops tune before any rule; test reads nothing
    e = syn_world(tmp / "gappy", 41, gappy=True)
    _lock_plan(e)
    sel = run_tune(e)["selection"]
    assert sel["decision"] == "coverage too low; no pick" and sel["pick"] is None
    assert "No rule advanced under the prespecified rules (failed gate: coverage)" in e.p("RESULTS.md").read_text()
    tr = json.loads(e.p("tune_results.json").read_text())
    assert "rules" not in tr
    e.read_log.clear()
    r = run_test(e)
    assert r["decision"]["result"] == "no test (coverage)"
    assert not [x for x in e.read_log if x[0] != "event"], e.read_log
    print("selftest: coverage stop ok")


def selftest() -> None:
    selftest_rules()
    selftest_selection()
    selftest_null()
    selftest_part2()
    with tempfile.TemporaryDirectory() as d:
        selftest_worlds(Path(d))
    print("selftest: all passed")


def main(argv: list) -> None:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "tune":
        print(run_tune(default_env())["selection"]["decision"])
    elif cmd == "test":
        print(run_test(default_env())["decision"]["result"])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
