"""Search the closing candles of the SPX index, of SPY and of the two agreeing, at real option prices, with a luck test.

Pre-registration: preregistration/spx_candle_realsearch.md (locked 2026-11-10T06:24:53Z; its SHA-256 is in
preregistration/LEDGER.md). This file was written after the lock. There is no separate code review;
`selftest` must pass before `tune`.

Reused primitives (read-only imports): the quote reader, closes/day files (build_cache.py), valid quote, implied
spot, ATM, settlement, fee and the Newey-West statistic (audit.py), all through realindex.py, plus realindex's
cents() and manifest(), and spycandle's bar_ok(). The grid, its statistics, the plateau score, eligibility, the pick,
the shift null and the orchestration are new and take this study's grid explicitly.

Commands (from the repository root):
  .venv/bin/python -I backtests/spx_candle_realsearch/realsearch.py selftest
  .venv/bin/python -I backtests/spx_candle_realsearch/realsearch.py gate
  .venv/bin/python -I backtests/spx_candle_realsearch/realsearch.py tune     # the one registered tuning run
  .venv/bin/python -I backtests/spx_candle_realsearch/realsearch.py test     # the one registered test run
  .venv/bin/python -I backtests/spx_candle_realsearch/realsearch.py rerun tune|test "the documented defect"
"""
import csv, gzip, hashlib, json, math, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backtests" / "spx_candle_realindex"))
sys.path.insert(0, str(ROOT / "backtests" / "spx_candle_spy"))
import realindex as RI          # noqa: E402  (read-only)
import spycandle as SC          # noqa: E402  (read-only)

A, BC = RI.A, RI.BC
D = ROOT / "data" / "spx_1549"
IDX_ARCH, SPY_ARCH = D / "cnbc_1m", D / "cnbc_spy_1m"
QDIR = D / "databento" / "cbbo-1m_1500-1601_k60"
CLOSES = D / "spx_official_closes_cboe.csv"
R60_CSV, S60_CSV = D / "databento" / "realindex_trades.csv", D / "databento" / "spycandle_trades.csv"
OUT_TRADES = D / "databento" / "realsearch_trades.csv"
PREREG = ROOT / "preregistration" / "spx_candle_realsearch.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
IDX_MANIFEST, IDX_FILES = "50d1fc7a3a597f19a64887149f280f5b54e0699e47f0412a3a3f2ce6ab6ca5e9", 1946
SPY_MANIFEST, SPY_FILES = "cfe31add76511c279ac30cfed6687c43103a8c635ab440768840ba1bc6b8912a", 1446
REUSED = [ROOT / "backtests" / p for p in ("spx_candle_realindex/realindex.py", "spx_candle_spy/spycandle.py",
                                            "spx_candle_audit/audit.py", "spx_candle_audit/build_cache.py")]

# ---------------------------------------------------------------- the grid (plan: "The grid (7,128 cells)")
SOURCES = ("index", "SPY", "both")
CANDLES = tuple(f"15:{m}" for m in range(45, 56))
ENTRIES = tuple(f"15:{m}" for m in range(46, 57))          # entry = the next minute's open
THRESH = tuple(range(40, 100, 5))                           # hundredths: 40 .. 95
DIRS = (1, -1)                                              # with, against
OFFSETS = (20, 15, 10, 5, 0, -5, -10, -15, -20)             # ITM20 .. OTM20
GRID = (len(SOURCES), len(CANDLES), len(THRESH), len(DIRS), len(OFFSETS))
NCELLS = int(np.prod(GRID))
assert NCELLS == 7128 and len(CANDLES) == 11 and len(THRESH) == 12
FEE, FEE_HIGH = A.FEE, 0.74
assert FEE == 0.09

C1550 = CANDLES.index("15:50")
R60 = (0, C1550, THRESH.index(60), 0, OFFSETS.index(10))
S60 = (1, C1550, THRESH.index(60), 0, OFFSETS.index(10))
S70 = (1, C1550, THRESH.index(70), 0, OFFSETS.index(10))
LEADS = [(s, C1550, THRESH.index(p), 0, OFFSETS.index(o)) for s, p in ((0, 80), (0, 85), (1, 70), (1, 80), (2, 60))
         for o in (10, 20)]

TUNE = ("2021-01-01", "2023-12-31")
H1, H2 = ("2021-01-01", "2022-09-30"), ("2022-10-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-20")
WHOLE = ("2021-01-01", "2026-10-20")
MOVE_PERIODS = (("2019-2020", ("2019-01-01", "2020-12-31")), ("2021-2026", WHOLE))
YEARS = [str(y) for y in range(2021, 2027)]
MIN_TRADES, MIN_HALF, COV = 100, 40, (95, 100)
WHOLE_MIN_TRADES = 200
ALPHA, T_BAR = 0.05, 2.0
SHIFT_GAP, SHIFT_STEP = 21, 3
CHUNK = 16
NO_ADVANCE = "No candidate advanced under the prespecified rules"
FAMILY_TEXT = ("examined, or closely related to settings examined, on 2024-2026; it can only be checked on future "
               "days")


class IsolationError(RuntimeError):
    pass


# ---------------------------------------------------------------- cells
def label(o):
    return "ATM" if o == 0 else (f"ITM{o}" if o > 0 else f"OTM{-o}")


def name(c):
    s, a, b, di, j = c
    return f"{SOURCES[s]} {CANDLES[a]} body>={THRESH[b] / 100:.2f} {'with' if DIRS[di] > 0 else 'against'} {label(OFFSETS[j])}"


def distance(c, ref=R60):
    """Grid-index Manhattan distance; a change of source (whichever two) costs 1."""
    return (int(c[0] != ref[0]) + abs(c[1] - ref[1]) + abs(c[2] - ref[2]) + int(c[3] != ref[3]) + abs(c[4] - ref[4]))


def in_family(c):
    return c[1] == C1550


# ---------------------------------------------------------------- isolation: windows and guarded loaders
class Guard:
    """The outcome-bearing date window a step may read. Every loader asks it before reading a date's content."""

    def __init__(self, lo, hi, what):
        self.lo, self.hi, self.what = lo, hi, what
        self.reads = []

    def check(self, day, kind):
        if not (self.lo <= day <= self.hi):
            raise IsolationError(f"{self.what}: refused to read {kind} for {day} outside {self.lo}..{self.hi}")
        self.reads.append((kind, day))

    def widen(self, lo, hi, what):
        self.lo, self.hi, self.what = lo, hi, what


def _no_conflicting_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out and out[k] != v:
            raise SystemExit(f"stop: conflicting duplicate record for key {k!r}")
        out[k] = v
    return out


def load_archive(arch, days, guard):
    """{date: bars} for the given dates (a date without a file is simply absent). Stops on an unreadable file,
    conflicting duplicate records, or a file whose stored date disagrees with its name."""
    out = {}
    for d in days:
        p = arch / f"{d}.json"
        if not p.exists():
            continue
        guard.check(d, f"archive {arch.name}")
        try:
            j = json.loads(p.read_text(), object_pairs_hook=_no_conflicting_dupes)
        except ValueError as e:
            raise SystemExit(f"stop: {p} is unreadable: {e}")
        if j.get("date") != d or not isinstance(j.get("bars"), dict):
            raise SystemExit(f"stop: {p.name} does not hold its own date or has no bars object")
        out[d] = j["bars"]
    return out


def day_rows():
    """d1_days.csv: dates and calendar (metadata)."""
    return BC.read_days()


def base_dates(rows, lo, hi):
    return sorted({r["date"] for r in rows if r["calendar"] == "full" and lo <= r["date"] <= hi})


def quote_listing():
    return {p.name[:10] for p in QDIR.glob("*.csv.gz")}


def load_closes(lo, hi, guard, path=CLOSES):
    """Official closes for dates inside [lo, hi] only; other rows are skipped before their value is parsed."""
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            m, dd, y = r["DATE"].split("/")
            day = f"{y}-{m}-{dd}"
            if not (lo <= day <= hi):
                continue
            guard.check(day, "close")
            v = float(r["SPX"])
            if day in out and out[day] != v:
                raise SystemExit(f"stop: two different official closes for {day}")
            out[day] = v
    return out


def option_axis(rows, has_q, closes, lo, hi):
    """The plan's day axis: calendar = full, a quote file and a finite official close (no keep or candle filter)."""
    return [d for d in base_dates(rows, lo, hi) if d in has_q and math.isfinite(closes.get(d, math.nan))]


# ---------------------------------------------------------------- signals
def bar_signals(bar):
    """Per threshold (hundredths): +1/-1/0 from the whole-cent test; None for a missing or invalid bar."""
    if bar is None or not SC.bar_ok(bar):
        return None
    o, h, l, c = (RI.cents(v) for v in bar)
    body, rng = abs(c - o), h - l
    sign = 1 if c > o else -1 if c < o else 0
    return [sign if (rng > 0 and sign != 0 and 100 * body >= p * rng) else 0 for p in THRESH]


def raw_signals(archs, days, candles=CANDLES):
    """raw[day, source (index, SPY), candle, threshold] in {+1, -1, 0, NaN}, and counts of missing files, absent
    bars and invalid bars by source, minute and year."""
    raw = np.full((len(days), len(archs), len(candles), len(THRESH)), np.nan)
    counts = {}
    for si, arch in enumerate(archs):
        for i, d in enumerate(days):
            bars = arch.get(d)
            for a, k in enumerate(candles):
                key = (SOURCES[si], k, d[:4])
                cnt = counts.setdefault(key, {"days": 0, "missing_file": 0, "absent_bar": 0, "invalid_bar": 0})
                cnt["days"] += 1
                if bars is None:
                    cnt["missing_file"] += 1
                    continue
                b = bars.get(k)
                if b is None:
                    cnt["absent_bar"] += 1
                    continue
                s = bar_signals(b)
                if s is None:
                    cnt["invalid_bar"] += 1
                    continue
                raw[i, si, a, :] = s
    return raw, counts


def with_both(raw):
    """(..., 2, C, T) -> (..., 3, C, T): adds "both" = the common sign when both candles signal in the same
    direction, 0 when both are valid otherwise, NaN when either is missing."""
    i, s = raw[..., 0, :, :], raw[..., 1, :, :]
    ok = np.isfinite(i) & np.isfinite(s)
    with np.errstate(invalid="ignore"):
        both = np.where(ok, np.where((i == s) & (i != 0), i, 0.0), np.nan)
    return np.stack([i, s, both], axis=-3)


# ---------------------------------------------------------------- pricing
def price_days(days, closes, guard, needs=None, quote_reader=None):
    """Per day and entry minute: implied spot; per offset: the call's (up) and put's (dn) P&L at the ask, ask and mid.
    `needs` None prices every contract; otherwise a list with one set of (entry index, offset index, side) per day.
    Conflicting quotes for one contract in a snapshot that is priced stop the run."""
    read = quote_reader or (lambda d: BC.read_quotes(QDIR / f"{d}.csv.gz", d))
    n, E, O = len(days), len(ENTRIES), len(OFFSETS)
    cube = {k: np.full((n, E, O), np.nan) for k in ("up", "dn", "ask_up", "ask_dn", "mid_up", "mid_dn")}
    cube["spot"] = np.full((n, E), np.nan)
    cube["dates"] = list(days)
    for i, d in enumerate(days):
        if needs is not None:
            want = {}
            for e, j, side in needs[i]:
                want.setdefault(e, {}).setdefault(j, set()).add(side)
            if not want:
                continue
        else:
            want = {e: {j: {"up", "dn"} for j in range(O)} for e in range(E)}
        guard.check(d, "quotes")
        q, meta = read(d)
        bad = {m: c for m, c in meta.get("conflicts_by_minute", {}).items() if m in {ENTRIES[e] for e in want}}
        if bad:
            raise SystemExit(f"stop: {d}: conflicting quotes in a priced snapshot {bad}")
        close = closes[d]
        for e, js in want.items():
            book = q.get(ENTRIES[e], {})
            s = A.implied_spot(book)
            if s is None:
                continue
            atm = A.atm_of(s)
            cube["spot"][i, e] = s
            for j, sides in js.items():
                o = OFFSETS[j]
                for kind, k, side in (("C", atm - o, "up"), ("P", atm + o, "dn")):
                    if side not in sides:
                        continue
                    qa = book.get((kind, float(k)))
                    if not A.valid(qa):
                        continue
                    v = A.settle(kind, k, close)
                    cube["ask_" + side][i, e, j], cube["mid_" + side][i, e, j] = qa[1], (qa[0] + qa[1]) / 2
                    cube[side][i, e, j] = 100 * (v - qa[1]) - FEE
    return cube


# ---------------------------------------------------------------- per-day series and grid statistics
def day_series(s, up, dn):
    s = np.asarray(s, float)
    with np.errstate(invalid="ignore"):
        return np.where(s > 0, up, np.where(s < 0, dn, np.where(s == 0, 0.0, np.nan)))


def cell_signal(c, sig):
    s, a, b, di, _ = c
    return sig[:, s, a, b] * DIRS[di]


def cell_series(c, sig, cube, kind=""):
    """Per-day series of a cell ('' = ask and $0.09, 'mid', 'fee74'), and its signed signal."""
    s, a, b, di, j = c
    x = sig[:, s, a, b] * DIRS[di]
    up, dn = cube["up"][:, a, j], cube["dn"][:, a, j]
    if kind == "mid":
        up = up + 100 * (cube["ask_up"][:, a, j] - cube["mid_up"][:, a, j])
        dn = dn + 100 * (cube["ask_dn"][:, a, j] - cube["mid_dn"][:, a, j])
    elif kind == "fee74":
        up, dn = up - (FEE_HIGH - FEE), dn - (FEE_HIGH - FEE)
    return day_series(x, up, dn), x


def grid_stats(sig, up, dn, masks):
    """sig: (..., n, 3, C, T); up/dn: (n, E, O) fixed. For each day mask: per cell (lead + GRID) the sum and count of
    non-missing days, priced trades and valid non-zero signals; mean per day and coverage."""
    lead = sig.shape[:-4]
    shp = lead + GRID
    out = [{"sum": np.zeros(shp), "n_days": np.zeros(shp, int), "n_trades": np.zeros(shp, int),
            "n_signal": np.zeros(shp, int)} for _ in masks]
    for a in range(len(CANDLES)):
        U, Dn = up[:, a, :], dn[:, a, :]
        for s in range(len(SOURCES)):
            for b in range(len(THRESH)):
                s0 = sig[..., s, a, b]
                with np.errstate(invalid="ignore"):
                    sigday = np.isfinite(s0) & (s0 != 0)
                for di, d in enumerate(DIRS):
                    X = day_series((s0 * d)[..., None], U, Dn)
                    fin = np.isfinite(X)
                    Xz = np.where(fin, X, 0.0)
                    tr = fin & sigday[..., None]
                    for r, m in zip(out, masks):
                        r["sum"][..., s, a, b, di, :] = Xz[..., m, :].sum(axis=-2)
                        r["n_days"][..., s, a, b, di, :] = fin[..., m, :].sum(axis=-2)
                        r["n_trades"][..., s, a, b, di, :] = tr[..., m, :].sum(axis=-2)
                        r["n_signal"][..., s, a, b, di, :] = sigday[..., m].sum(axis=-1)[..., None]
    for r in out:
        r["mean"] = np.where(r["n_days"] > 0, r["sum"] / np.maximum(r["n_days"], 1), np.nan)
        r["coverage"] = np.where(r["n_signal"] > 0, r["n_trades"] / np.maximum(r["n_signal"], 1), np.nan)
    return out


def plateau(mean):
    """Average of the cell's mean per day and its neighbours at threshold +/- 0.05 (same source, candle, direction,
    strike) that exist on the grid; a non-finite neighbour is ignored; the cell's own mean must be finite."""
    m = np.asarray(mean, float)
    ax = m.ndim - 3
    T = m.shape[ax]
    fin = np.isfinite(m)
    tot, cnt = np.where(fin, m, 0.0), fin.astype(int)
    for dst_sl, src_sl in ((slice(1, T), slice(0, T - 1)), (slice(0, T - 1), slice(1, T))):
        nb = np.full_like(m, np.nan)
        dst, src = [slice(None)] * m.ndim, [slice(None)] * m.ndim
        dst[ax], src[ax] = dst_sl, src_sl
        nb[tuple(dst)] = m[tuple(src)]
        f = np.isfinite(nb)
        tot, cnt = tot + np.where(f, nb, 0.0), cnt + f
    return np.where(fin, tot / np.maximum(cnt, 1), np.nan)


def cov_ok(r):
    return (r["n_signal"] > 0) & (r["n_trades"] * COV[1] >= COV[0] * r["n_signal"])


def eligible(full, h1, h2):
    with np.errstate(invalid="ignore"):
        return ((full["n_trades"] >= MIN_TRADES) & (h1["n_trades"] >= MIN_HALF) & (h2["n_trades"] >= MIN_HALF)
                & (h1["mean"] > 0) & (h2["mean"] > 0) & cov_ok(full) & cov_ok(h1) & cov_ok(h2)
                & np.isfinite(full["mean"]))


def whole_eligible(full):
    return np.isfinite(full["mean"]) & (full["n_trades"] >= WHOLE_MIN_TRADES) & cov_ok(full)


def ranked(score, elig, where=None):
    """Cells in pick order: score (desc), distance to R60, enumeration order (C order of GRID)."""
    s = np.where(elig & np.isfinite(score), score, -np.inf)
    ix = [tuple(int(v) for v in x) for x in np.argwhere(np.isfinite(s))]
    if where is not None:
        ix = [x for x in ix if where(x)]
    return sorted(ix, key=lambda x: (-s[x], distance(x), np.ravel_multi_index(x, GRID)))


def pick(score, elig):
    r = ranked(score, elig)
    return r[0] if r else None


def shifts_for(n):
    return list(range(SHIFT_GAP, n - SHIFT_GAP + 1, SHIFT_STEP))


def shifted(raw, shifts):
    """(len(shifts), n, ...): destination day i receives day (i - s) mod n, = np.roll(raw, s, axis=0) per shift."""
    n = raw.shape[0]
    idx = (np.arange(n)[None, :] - np.asarray(shifts)[:, None]) % n
    return raw[idx]


def null_best(raw, up, dn, masks, shifts, objective="plateau", chunk=CHUNK):
    """Per shift: the best eligible score (Part 1: plateau, eligibility on halves) or raw mean per day (whole period),
    over all cells including the exclusion family; -inf when nothing qualifies."""
    out = []
    for i in range(0, len(shifts), chunk):
        sh = shifts[i:i + chunk]
        sig = with_both(shifted(raw, sh))
        st = grid_stats(sig, up, dn, masks)
        if objective == "plateau":
            v, el = plateau(st[0]["mean"]), eligible(*st)
        else:
            v, el = st[0]["mean"], whole_eligible(st[0])
        out.extend(np.where(el & np.isfinite(v), v, -np.inf).reshape(len(sh), -1).max(axis=1).tolist())
    return np.array(out, float)


def p_value(nulls, observed):
    nulls = np.asarray(nulls, float)
    return (1 + int(np.sum(nulls >= observed))) / (1 + len(nulls))


def quantile(nulls, q):
    """Linear interpolation; unavailable when either bracketing value is not finite."""
    if len(nulls) == 0:
        return None
    v = np.sort(np.asarray(nulls, float))
    pos = q / 100 * (len(v) - 1)
    lo, hi = v[int(math.floor(pos))], v[int(math.ceil(pos))]
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return None
    return float(lo + (hi - lo) * (pos - math.floor(pos)))


# ---------------------------------------------------------------- statistics
def nw(series):
    y = np.asarray(series, float)
    y = y[np.isfinite(y)]
    r = A.nw(y)
    if r["n"] < 8:
        r["t"] = None
    return r


def paired(x, y, dates):
    x, y = np.asarray(x, float), np.asarray(y, float)
    keep = np.isfinite(x) & np.isfinite(y)
    r = nw(x[keep] - y[keep])
    return {"paired_n": int(keep.sum()), "dropped_days": int((~keep).sum()),
            "dropped_dates": [str(d) for d in np.asarray(dates, dtype=object)[~keep]], "mean": r["mean"], "t": r["t"]}


def passes(mean, t):
    return mean is not None and t is not None and math.isfinite(mean) and math.isfinite(t) and mean > 0 and t >= T_BAR


def describe(x, s, dates=None):
    """Statistics of a cell's per-day series x and signed signal s on some days."""
    x, s = np.asarray(x, float), np.asarray(s, float)
    with np.errstate(invalid="ignore"):
        sigday = np.isfinite(s) & (s != 0)
    traded = sigday & np.isfinite(x)
    tr = x[traded]
    r = nw(x)
    out = {"days": int(np.isfinite(x).sum()), "mean_per_day": r["mean"], "t": r["t"], "signal_days": int(sigday.sum()),
           "trades": int(traded.sum()), "coverage": (float(traded.sum() / sigday.sum()) if sigday.sum() else None),
           "per_trade": (float(tr.mean()) if len(tr) else None), "won": (float((tr > 0).mean()) if len(tr) else None),
           "median": (float(np.median(tr)) if len(tr) else None), "worst": (float(tr.min()) if len(tr) else None)}
    return out


def not_priced(c, sig, cube, mask=None):
    """Unpriced signal days of a cell by reason (no implied spot at the entry minute / no valid quote)."""
    x, s = cell_series(c, sig, cube)
    a = c[1]
    m = np.ones(len(x), bool) if mask is None else mask
    with np.errstate(invalid="ignore"):
        un = m & np.isfinite(s) & (s != 0) & ~np.isfinite(x)
    nospot = un & ~np.isfinite(cube["spot"][:, a])
    return {"no implied spot": int(nospot.sum()), "no valid quote": int((un & ~nospot).sum())}


# ---------------------------------------------------------------- consistency check against the earlier trade files
def read_trade_file(path, lo, hi, guard):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if not (lo <= r["date"] <= hi):
                continue
            guard.check(r["date"], path.name)
            rows.append(r)
    return rows


def band_of(raw, i, si, a):
    """The 15:50 band of source si on day i: '70%+' or '60-70%' (only called on signal days)."""
    return "70%+" if raw[i, si, a, THRESH.index(70)] != 0 else "60-70%"


def consistency(c, raw, sig, cube, days, rows, what):
    """Reconstructed priced trades of cell c (with, ITM10) must equal the file's rows: same dates, no duplicates; sign,
    band, kind and strike exactly; P&L within $0.000001. Unpriced signals are allowed and recorded with reasons."""
    x, s = cell_series(c, sig, cube)
    a, j = c[1], c[4]
    mine, unpriced = {}, {}
    for i, d in enumerate(days):
        if not (np.isfinite(s[i]) and s[i] != 0):
            continue
        if not np.isfinite(x[i]):
            unpriced[d] = "no implied spot" if not np.isfinite(cube["spot"][i, a]) else "no valid quote"
            continue
        atm = A.atm_of(cube["spot"][i, a])
        kind = "C" if s[i] > 0 else "P"
        k = atm - OFFSETS[j] if s[i] > 0 else atm + OFFSETS[j]
        mine[d] = {"sign": int(s[i]), "band": band_of(raw, i, c[0], a), "kind": kind, "strike": float(k), "pnl": float(x[i])}
    dates = [r["date"] for r in rows]
    if len(dates) != len(set(dates)):
        raise SystemExit(f"consistency ({what}): duplicate dates in the file")
    theirs = {r["date"]: r for r in rows}
    if set(theirs) != set(mine):
        extra, missing = sorted(set(mine) - set(theirs)), sorted(set(theirs) - set(mine))
        raise SystemExit(f"consistency ({what}): priced dates differ; only mine {extra[:5]} ({len(extra)}), "
                         f"only the file's {missing[:5]} ({len(missing)})")
    bad = []
    for d, m in mine.items():
        t = theirs[d]
        if (int(t["sign"]) != m["sign"] or t["band"] != m["band"] or t["kind"] != m["kind"]
                or float(t["strike"]) != m["strike"] or abs(float(t["pnl"]) - m["pnl"]) > 1e-6):
            bad.append(d)
    if bad:
        raise SystemExit(f"consistency ({what}): {len(bad)} trade(s) differ, first {bad[:5]}")
    return {"file_rows": len(rows), "equal": True, "unpriced_signals": unpriced}


# ---------------------------------------------------------------- the gate
def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def open_gate(prereg=PREREG, ledger=LEDGER, check_archives=True):
    if not prereg.exists():
        raise SystemExit(f"gate: {prereg} does not exist")
    sha = sha256(prereg)
    listed = [ln.split() for ln in ledger.read_text().splitlines() if ln.startswith("- ")]
    if not any(len(x) >= 4 and x[2] == sha and x[3] == prereg.name for x in listed):
        raise SystemExit("gate: the plan's SHA-256 is not in the ledger")
    text = prereg.read_text()
    for m in (IDX_MANIFEST, SPY_MANIFEST):
        if m not in text:
            raise SystemExit(f"gate: the plan does not name manifest {m[:12]}...")
    if check_archives:
        for what, arch, m, n in (("index", IDX_ARCH, IDX_MANIFEST, IDX_FILES), ("SPY", SPY_ARCH, SPY_MANIFEST, SPY_FILES)):
            got, k = RI.manifest(arch)
            if got != m or k != n:
                raise SystemExit(f"gate: the {what} archive differs from the frozen one ({k} files, {got[:12]}...)")
    return sha


# ---------------------------------------------------------------- outputs
def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if math.isfinite(v) else (None if v != v else ("inf" if v > 0 else "-inf"))
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def atomic_write(path, text, readonly=False):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    if path.exists():
        os.chmod(path, 0o644)
    os.replace(tmp, path)
    if readonly:
        os.chmod(path, 0o444)


def dumps(o):
    return json.dumps(clean(o), indent=1, allow_nan=False)


def cell_row(c, st, score=None):
    f, h1, h2 = st
    ix = tuple(c)
    return {"cell": name(c), "index": list(ix), "score": (None if score is None else score[ix]),
            "mean_per_day": f["mean"][ix], "trades": f["n_trades"][ix], "signal_days": f["n_signal"][ix],
            "coverage": f["coverage"][ix], "h1_mean": h1["mean"][ix], "h1_trades": h1["n_trades"][ix],
            "h2_mean": h2["mean"][ix], "h2_trades": h2["n_trades"][ix]}


def counts_table(counts):
    rows = []
    for (src, k, y), v in sorted(counts.items()):
        rows.append({"source": src, "candle": k, "year": y, **v})
    return rows


# ---------------------------------------------------------------- the tuning step
def load_period(lo, hi, guard, rows=None, has_q=None, need_spy=True):
    rows = rows if rows is not None else day_rows()
    has_q = has_q if has_q is not None else quote_listing()
    closes = load_closes(lo, hi, guard)
    days = option_axis(rows, has_q, closes, lo, hi)
    idx = load_archive(IDX_ARCH, days, guard)
    spy = load_archive(SPY_ARCH, days, guard) if need_spy else {}
    return days, closes, idx, spy


def masks_for(days, *windows):
    d = np.array(days, dtype=object)
    return [np.array([w[0] <= x <= w[1] for x in d], bool) for w in windows]


def tune(log=print):
    guard = Guard(*TUNE, "tune")
    days, closes, idx, spy = load_period(*TUNE, guard)
    raw, counts = raw_signals([idx, spy], days)
    sig = with_both(raw)
    log(f"tune: {len(days)} days; pricing every contract ...")
    cube = price_days(days, closes, guard)
    checks = {"R60": consistency(R60, raw, sig, cube, days, read_trade_file(R60_CSV, *TUNE, guard), "R60, tuning"),
              "S60": consistency(S60, raw, sig, cube, days, read_trade_file(S60_CSV, *TUNE, guard), "S60, tuning")}
    log("tune: consistency checks passed; grid ...")
    full, mh1, mh2 = masks_for(days, TUNE, H1, H2)
    st = grid_stats(sig, cube["up"], cube["dn"], [full, mh1, mh2])
    score, elig = plateau(st[0]["mean"]), eligible(*st)
    pk = pick(score, elig)
    res = {"days": len(days), "eligible_cells": int(elig.sum()), "bar_counts": counts_table(counts), "checks": checks}
    sh = shifts_for(len(days))
    if pk is None:
        res.update(pick=None, p=None, null=None, paired=None)
        decision = {"decision": "no_pick", "goes_to_test": False, "failed_gates": ["no eligible cell"],
                    "text": f"{NO_ADVANCE}: no cell was eligible, so there is no pick and no test."}
    else:
        log(f"tune: pick {name(pk)}; luck diagnostic over {len(sh)} shifts ...")
        nulls = null_best(raw, cube["up"], cube["dn"], [full, mh1, mh2], sh)
        p = p_value(nulls, score[pk])
        xp, _ = cell_series(pk, sig, cube)
        xr, _ = cell_series(R60, sig, cube)
        pr = paired(xp, xr, days)
        gates = {"not_in_exclusion_family": not in_family(pk), "p_le_0.05": p <= ALPHA,
                 "paired_mean_gt_0": pr["mean"] is not None and pr["mean"] > 0}
        failed = [k for k, ok in gates.items() if not ok]
        if in_family(pk):
            decision = {"decision": "exclusion_family", "goes_to_test": False, "gates": gates, "failed_gates": failed,
                        "text": f"{NO_ADVANCE}: the pick ({name(pk)}) is {FAMILY_TEXT}. No runner-up is substituted."}
        elif failed:
            decision = {"decision": "no_test", "goes_to_test": False, "gates": gates, "failed_gates": failed,
                        "text": f"{NO_ADVANCE}. Failed gate(s): {', '.join(failed)}."}
        else:
            decision = {"decision": "test", "goes_to_test": True, "gates": gates, "failed_gates": [],
                        "text": f"The pick ({name(pk)}) passed all three gates and goes to the test."}
        res.update(pick=cell_row(pk, st, score), p=p, paired=pr,
                   null={"shifts": len(sh), "median": quantile(nulls, 50), "q95": quantile(nulls, 95),
                         "shifts_with_no_eligible_cell": int(np.sum(~np.isfinite(nulls))), "values": nulls.tolist()})
    selection = {"pick": (list(pk) if pk is not None else None), "pick_name": (name(pk) if pk is not None else None),
                 "decision": decision, "p": res.get("p"), "observed_score": (score[pk] if pk is not None else None)}
    return res, selection, (days, raw, sig, cube, st, score, elig)


def tune_descriptions(res, days, sig, cube, st, score, elig):
    """Written after the tuning decision."""
    res["top15"] = [cell_row(c, st, score) for c in ranked(score, elig)[:15]]
    res["best_per_candle"] = {k: (cell_row(r[0], st, score) if r else None)
                              for a, k in enumerate(CANDLES) for r in [ranked(score, elig, lambda x, a=a: x[1] == a)]}
    unp = (st[0]["n_signal"] - st[0]["n_trades"]).ravel()
    res["not_priced_per_cell"] = {"median": float(np.median(unp)), "max": int(unp.max())}
    full, mh1, mh2 = masks_for(days, TUNE, H1, H2)
    named = {"R60": R60, "S70": S70}
    if res.get("pick"):
        named["pick"] = tuple(res["pick"]["index"])
    res["not_priced_named"] = {k: {"H1": not_priced(c, sig, cube, mh1), "H2": not_priced(c, sig, cube, mh2)}
                               for k, c in named.items()}
    return res


# ---------------------------------------------------------------- the test step
def needs_for(cells, sig):
    """Per day: the (entry, offset, side) contracts the given cells actually buy."""
    out = []
    for i in range(sig.shape[0]):
        s_day = set()
        for c in cells:
            v = cell_signal(c, sig)[i]
            if np.isfinite(v) and v != 0:
                s_day.add((c[1], c[4], "up" if v > 0 else "dn"))
        out.append(s_day)
    return out


def restricted_signals(raw, cells):
    """The signal tensor with only the given cells' (source, candle, threshold) columns filled (NaN elsewhere)."""
    full = with_both(raw)
    sig = np.full(full.shape, np.nan)
    for c in cells:
        sig[:, c[0], c[1], c[2]] = full[:, c[0], c[1], c[2]]
    return sig


def part2_prices(pk, days, raw, closes, guard):
    """Before the decision: only the pick's and R60's columns and contracts."""
    sig = restricted_signals(raw, [pk, R60])
    return sig, price_days(days, closes, guard, needs=needs_for([pk, R60], sig))


def part2(pk, days, sig, cube):
    xp, sp = cell_series(pk, sig, cube)
    xr, _ = cell_series(R60, sig, cube)
    a = nw(xp)
    b = paired(xp, xr, days)
    works, better = passes(a["mean"], a["t"]), passes(b["mean"], b["t"])
    if works and better:
        text = "The pick met the retrospective profitability and paired-superiority criteria on 2024-2026"
    elif works:
        text = "The profitability criterion was met; paired superiority was not established"
    else:
        text = "The profitability criterion was not met"
    return {"a_works": {"mean": a["mean"], "t": a["t"], "n": a["n"], "met": works},
            "b_better": {"mean": b["mean"], "t": b["t"], "paired_n": b["paired_n"], "dropped_days": b["dropped_days"],
                         "met": better},
            "reading": text, "pick_test": describe(xp, sp)}


def index_moves(rows, guard):
    """Part 3: which candle best predicts the index move (descriptive), per period, with its shift benchmark."""
    out = {}
    for per, (lo, hi) in MOVE_PERIODS:
        days = base_dates(rows, lo, hi)
        idx = load_archive(IDX_ARCH, days, guard)
        use_spy = lo >= "2021-01-01"
        spy = load_archive(SPY_ARCH, days, guard) if use_spy else {}
        raw, _ = raw_signals([idx, spy] if use_spy else [idx], days)
        mv = np.full((len(days), len(ENTRIES)), np.nan)
        for i, d in enumerate(days):
            bars = idx.get(d, {})
            last = bars.get("15:59")
            if last is None or not SC.bar_ok(last):
                continue
            for e, m in enumerate(ENTRIES):
                b = bars.get(m)
                if b is None or not SC.bar_ok(b) or not b[0] > 0:
                    continue
                mv[i, e] = 1e4 * (last[3] - b[0]) / b[0]
        srcs = SOURCES if use_spy else SOURCES[:1]

        def table(sig_all):
            res = {}
            for si, src in enumerate(srcs):
                for a, k in enumerate(CANDLES):
                    for b, p in enumerate(THRESH):
                        s = sig_all[:, si, a, b]
                        with np.errstate(invalid="ignore"):
                            keep = np.isfinite(s) & (s != 0) & np.isfinite(mv[:, a])
                        y = s[keep] * mv[keep, a]
                        r = nw(y)
                        nz = y[y != 0]
                        res[(src, k, p)] = {"days": int(keep.sum()), "mean_bps": r["mean"], "t": r["t"],
                                            "right_share": (float((nz > 0).mean()) if len(nz) else None)}
            return res

        sig = with_both(raw) if use_spy else raw
        obs = table(sig)
        sh = shifts_for(len(days))
        best = []
        for s_ in sh:
            rs = np.roll(raw, s_, axis=0)
            t = [v["t"] for v in table(with_both(rs) if use_spy else rs).values()]
            fin = [x for x in t if x is not None and math.isfinite(x)]
            best.append(max(fin) if fin else -np.inf)
        best = np.array(best, float)
        top = sorted(((k, v) for k, v in obs.items() if v["t"] is not None), key=lambda kv: -kv[1]["t"])
        out[per] = {"days": len(days), "cells": len(obs),
                    "table": [{"source": k[0], "candle": k[1], "threshold": k[2] / 100, **v} for k, v in obs.items()],
                    "top10_by_t": [{"source": k[0], "candle": k[1], "threshold": k[2] / 100, **v} for k, v in top[:10]],
                    "null": {"shifts": len(sh), "median": quantile(best, 50), "q95": quantile(best, 95),
                             "observed_max_t": (top[0][1]["t"] if top else None)}}
    return out


def by_year(c, sig, cube, days):
    d = np.array(days, dtype=object)
    x, s = cell_series(c, sig, cube)
    return {y: describe(x[[str(v)[:4] == y for v in d]], s[[str(v)[:4] == y for v in d]]) for y in YEARS
            if any(str(v)[:4] == y for v in d)}


def trade_rows(tag, c, sig, cube, days, period):
    x, s = cell_series(c, sig, cube)
    out = []
    for i, d in enumerate(days):
        if np.isfinite(s[i]) and s[i] != 0:
            out.append({"config": tag, "cell": name(c), "date": d, "period": period, "signal": int(s[i]),
                        "entry_minute": ENTRIES[c[1]], "implied_spot": cube["spot"][i, c[1]],
                        "pnl": (x[i] if np.isfinite(x[i]) else "")})
    return out


def test(selection, log=print):
    guard = Guard(*TEST, "test (before the decision)")
    rows, has_q = day_rows(), quote_listing()
    days, closes, idx, spy = load_period(*TEST, guard, rows, has_q)
    raw, counts = raw_signals([idx, spy], days)
    dec = selection["decision"]
    head = {"selection": selection, "test_days": len(days)}
    if dec["goes_to_test"]:
        pk = tuple(selection["pick"])
        sig_p, cube_p = part2_prices(pk, days, raw, closes, guard)
        # the R60 check precedes the Part 2 statistics
        head["check_R60_test"] = consistency(R60, raw, sig_p, cube_p, days, read_trade_file(R60_CSV, *TEST, guard),
                                             "R60, test")
        head["part2"] = part2(pk, days, sig_p, cube_p)
    else:
        head["part2"] = {"skipped": dec["text"]}
    yield "decision", head                                     # the caller writes results.json here
    guard.widen("2019-01-01", WHOLE[1], "test (after the decision)")
    log("test: decision written; Part 3 ...")
    cube_t = price_days(days, closes, guard)
    sig_t = with_both(raw)
    if not dec["goes_to_test"]:
        head["check_R60_test"] = consistency(R60, raw, sig_t, cube_t, days, read_trade_file(R60_CSV, *TEST, guard),
                                             "R60, test (after the skip decision)")
    head["check_S60_test"] = consistency(S60, raw, sig_t, cube_t, days, read_trade_file(S60_CSV, *TEST, guard),
                                         "S60, test (after the decision)")
    # the whole period
    gdays, gcloses, gidx, gspy = load_period(*WHOLE, guard, rows, has_q)
    graw, gcounts = raw_signals([gidx, gspy], gdays)
    gsig = with_both(graw)
    log(f"test: whole period, {len(gdays)} days; pricing ...")
    gcube = price_days(gdays, gcloses, guard)
    allm = np.ones(len(gdays), bool)
    gst = grid_stats(gsig, gcube["up"], gcube["dn"], [allm])[0]
    gel = whole_eligible(gst)
    mean = gst["mean"]
    order = ranked(mean, gel)
    tmask, temask = masks_for(gdays, TUNE, TEST)

    def whole_row(c):
        x, s = cell_series(c, gsig, gcube)
        return {"cell": name(c), **describe(x, s)}

    part3 = {"bar_counts_test": counts_table(counts), "bar_counts_whole": counts_table(gcounts)}
    part3["whole_ranking"] = {"label": "looked at after the decision; in-sample; not a test",
                              "eligible_cells": int(gel.sum()), "top15": [whole_row(c) for c in order[:15]],
                              "best_per_source_candle": {f"{SOURCES[s]} {k}": (whole_row(r[0]) if r else None)
                                                         for s in range(3) for a, k in enumerate(CANDLES)
                                                         for r in [[x for x in order if x[0] == s and x[1] == a][:1]]}}
    log("test: whole-period shift benchmark ...")
    sh = shifts_for(len(gdays))
    gnull = null_best(graw, gcube["up"], gcube["dn"], [allm], sh, objective="raw_mean")
    part3["whole_ranking"]["null"] = {"shifts": len(sh), "median": quantile(gnull, 50), "q95": quantile(gnull, 95),
                                      "observed_best": (float(mean[order[0]]) if order else None),
                                      "shifts_with_no_eligible_cell": int(np.sum(~np.isfinite(gnull)))}
    log("test: index-move tables ...")
    part3["index_moves"] = index_moves(rows, guard)
    named = {"R60": R60, "S70": S70}
    if selection["pick"] is not None:
        named = {"pick": tuple(selection["pick"]), **named}

    def per(c, m):
        x, s = cell_series(c, gsig, gcube)
        return describe(x[m], s[m])

    part3["leads"] = {name(c): {"tuning": per(c, tmask), "test": per(c, temask)} for c in LEADS}
    nm = {}
    for k, c in named.items():
        e = {}
        for kind in ("", "mid", "fee74"):
            x, s = cell_series(c, gsig, gcube, kind)
            e["ask_fee_0.09" if kind == "" else ("mid_fee_0.09" if kind == "mid" else "ask_fee_0.74")] = {
                "tuning": describe(x[tmask], s[tmask]), "test": describe(x[temask], s[temask])}
        e["by_year"] = by_year(c, gsig, gcube, gdays)
        e["not_priced"] = {"tuning": not_priced(c, gsig, gcube, tmask), "test": not_priced(c, gsig, gcube, temask)}
        nm[k] = e
    if "pick" in named:
        xp, _ = cell_series(named["pick"], gsig, gcube)
        xs, _ = cell_series(S70, gsig, gcube)
        d = np.array(gdays, dtype=object)
        nm["pick_minus_S70"] = {"tuning": paired(xp[tmask], xs[tmask], d[tmask]),
                                "test": paired(xp[temask], xs[temask], d[temask])}
    part3["named"] = nm
    unp = (gst["n_signal"] - gst["n_trades"]).ravel()
    part3["not_priced_per_cell_whole"] = {"median": float(np.median(unp)), "max": int(unp.max())}
    head["part3"] = part3
    trades = []
    for k, c in named.items():
        for per_name, m in (("tuning", tmask), ("test", temask)):
            idx_ = np.where(m)[0]
            sub = {kk: (v[idx_] if isinstance(v, np.ndarray) else [v[i] for i in idx_]) for kk, v in gcube.items()}
            trades += trade_rows(k, c, gsig[idx_], sub, [gdays[i] for i in idx_], per_name)
    yield "final", (head, trades)


# ---------------------------------------------------------------- report
def fm(x, nd=2, sign=True, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    if pct:
        return f"{100 * x:.0f}%"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


def md_tune(res, sel):
    w = ["## Part 1: tuning (2021-01-01 .. 2023-12-31)", ""]
    w.append(f"Days: {res['days']}. Eligible cells: {res['eligible_cells']} of {NCELLS}. "
             f"Consistency checks: R60 {res['checks']['R60']['file_rows']} rows equal, "
             f"S60 {res['checks']['S60']['file_rows']} rows equal.")
    w.append("")
    w.append(f"**Decision:** {sel['decision']['text']}")
    if res.get("pick"):
        p = res["pick"]
        w.append(f"- Pick: {p['cell']}; score {fm(p['score'])} a day; mean {fm(p['mean_per_day'])} a day; "
                 f"{p['trades']} trades (H1 {p['h1_trades']}, H2 {p['h2_trades']}); coverage {fm(p['coverage'], pct=True)}.")
        n = res["null"]
        w.append(f"- Luck diagnostic: p = {res['p']:.3f} over {n['shifts']} shifts (null median {fm(n['median'])}, "
                 f"95th percentile {fm(n['q95'])}; shifts with no eligible cell {n['shifts_with_no_eligible_cell']}).")
        w.append(f"- Pick minus R60 on tuning: {fm(res['paired']['mean'])} a day (t {fm(res['paired']['t'])}, "
                 f"paired n {res['paired']['paired_n']}).")
    if res.get("top15"):
        w += ["", "Best eligible cells on tuning (score = plateau mean per day):", "",
              "| # | Cell | Score | $/day | Trades | H1 $/day | H2 $/day | Coverage |", "|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(res["top15"], 1):
            w.append(f"| {i} | {r['cell']} | {fm(r['score'])} | {fm(r['mean_per_day'])} | {r['trades']} | "
                     f"{fm(r['h1_mean'])} | {fm(r['h2_mean'])} | {fm(r['coverage'], pct=True)} |")
        w += ["", "Best eligible cell per candle minute:", "", "| Candle | Cell | Score | $/day | Trades |", "|---|---|---|---|---|"]
        for k, r in res["best_per_candle"].items():
            w.append(f"| {k} | {r['cell'] if r else 'none eligible'} | {fm(r['score']) if r else ''} | "
                     f"{fm(r['mean_per_day']) if r else ''} | {r['trades'] if r else ''} |")
    w.append("")
    return "\n".join(w)


def md_test(head):
    w = ["## Part 2: the test (2024-01-01 .. 2026-10-20)", ""]
    p2 = head["part2"]
    if "skipped" in p2:
        w.append(f"Not run. {p2['skipped']}")
    else:
        a, b = p2["a_works"], p2["b_better"]
        w.append(f"**{p2['reading']}.**")
        w.append(f"- (a) Works: {fm(a['mean'])} a day, t {fm(a['t'])} over {a['n']} days: {'met' if a['met'] else 'not met'}.")
        w.append(f"- (b) Better than R60: {fm(b['mean'])} a day, t {fm(b['t'])}, paired n {b['paired_n']}: "
                 f"{'met' if b['met'] else 'not met'}.")
        pt = p2["pick_test"]
        w.append(f"- The pick on 2024-2026: {pt['trades']} trades, {fm(pt['per_trade'])} a trade, won {fm(pt['won'], pct=True)}.")
    p3 = head.get("part3")
    if p3:
        wr = p3["whole_ranking"]
        w += ["", "## Part 3: descriptive (decides nothing)", "",
              f"### Whole period 2021-2026 ({wr['label']})", "",
              f"Eligible cells: {wr['eligible_cells']}. Shift benchmark of the best raw mean per day: median "
              f"{fm(wr['null']['median'])}, 95th percentile {fm(wr['null']['q95'])}; observed best {fm(wr['null']['observed_best'])}.",
              "", "| # | Cell | $/day | t | Trades | $/trade | Won |", "|---|---|---|---|---|---|---|"]
        for i, r in enumerate(wr["top15"], 1):
            w.append(f"| {i} | {r['cell']} | {fm(r['mean_per_day'])} | {fm(r['t'])} | {r['trades']} | {fm(r['per_trade'])} | {fm(r['won'], pct=True)} |")
        for per, v in p3["index_moves"].items():
            w += ["", f"### Index move after the candle, {per} (in the candle's direction; basis points from the next minute's open to the 15:59 close)", "",
                  f"{v['cells']} cells, {v['days']} days. Largest t {fm(v['null']['observed_max_t'])}; shift benchmark of the "
                  f"largest t: median {fm(v['null']['median'])}, 95th percentile {fm(v['null']['q95'])}.", "",
                  "| Source | Candle | Threshold | Days | bps | t | Right |", "|---|---|---|---|---|---|---|"]
            for r in v["top10_by_t"]:
                w.append(f"| {r['source']} | {r['candle']} | {r['threshold']:.2f} | {r['days']} | {fm(r['mean_bps'])} | {fm(r['t'])} | {fm(r['right_share'], pct=True)} |")
        w += ["", "### Leads already seen (exclusion family)", "", "| Cell | Tuning $/day | t | Test $/day | t | Test trades |", "|---|---|---|---|---|---|"]
        for k, v in p3["leads"].items():
            w.append(f"| {k} | {fm(v['tuning']['mean_per_day'])} | {fm(v['tuning']['t'])} | {fm(v['test']['mean_per_day'])} | {fm(v['test']['t'])} | {v['test']['trades']} |")
        w += ["", "### Named cells", "", "| Cell | Version | Period | $/day | t | Trades | $/trade | Won |", "|---|---|---|---|---|---|---|---|"]
        for k, e in p3["named"].items():
            if k == "pick_minus_S70":
                continue
            for ver in ("ask_fee_0.09", "ask_fee_0.74", "mid_fee_0.09"):
                for per in ("tuning", "test"):
                    r = e[ver][per]
                    w.append(f"| {k} | {ver} | {per} | {fm(r['mean_per_day'])} | {fm(r['t'])} | {r['trades']} | {fm(r['per_trade'])} | {fm(r['won'], pct=True)} |")
        if "pick_minus_S70" in p3["named"]:
            for per, r in p3["named"]["pick_minus_S70"].items():
                w.append(f"\nPick minus S70 ({per}, descriptive): {fm(r['mean'])} a day, t {fm(r['t'])}, paired n {r['paired_n']}.")
    w.append("")
    return "\n".join(w)


# ---------------------------------------------------------------- commands
LOG = HERE / "run_log.txt"
TUNE_OUT = ("selection.json", "selection.sha256", "tune_results.json")
TEST_OUT = ("results.json",)


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def logline(text):
    with LOG.open("a") as f:
        f.write(f"{stamp()} {text}\n")


def started(step):
    return LOG.exists() and f"{step} started" in LOG.read_text()


def supersede(step, reason):
    keep = HERE / f"superseded_{step}_{stamp().replace(':', '')}"
    keep.mkdir()
    for n in (TUNE_OUT if step == "tune" else TEST_OUT) + ("RESULTS.md",):
        p = HERE / n
        if p.exists():
            os.chmod(p, 0o644)
            p.rename(keep / n)
    if step == "test" and OUT_TRADES.exists():
        OUT_TRADES.rename(keep / OUT_TRADES.name)
    logline(f"RERUN {step}; earlier outputs kept in {keep.name}; documented defect: {reason}")


def cmd_tune(reason=None):
    sha = open_gate()
    if reason is None and (started("tune") or (HERE / "selection.json").exists()):
        raise SystemExit("stop: tune was already started; a corrected rerun needs `rerun tune \"the defect\"`")
    if reason is not None:
        supersede("tune", reason)
    code = sha256(__file__)
    logline(f"tune started; plan {sha}; code {code}; reused " + ", ".join(f"{p.name} {sha256(p)}" for p in REUSED)
            + f"; manifests index {IDX_MANIFEST} SPY {SPY_MANIFEST}")
    res, sel, (days, raw, sig, cube, st, score, elig) = tune()
    sel.update(prereg_sha256=sha, code_sha256=code, decided_at_utc=stamp())
    txt = dumps(sel)
    atomic_write(HERE / "selection.json", txt, readonly=True)
    atomic_write(HERE / "selection.sha256", hashlib.sha256(txt.encode()).hexdigest() + "\n", readonly=True)
    logline(f"tuning decision written: {sel['decision']['decision']}; pick {sel['pick_name']}")
    res = tune_descriptions(res, days, sig, cube, st, score, elig)
    atomic_write(HERE / "tune_results.json", dumps(res))
    atomic_write(HERE / "RESULTS.md", "# Search of the closing candles: results\n\n" + md_tune(res, sel))
    logline("tune finished")
    print(md_tune(res, sel))
    return 0


def cmd_test(reason=None):
    sha = open_gate()
    sel_txt = (HERE / "selection.json").read_text()
    if hashlib.sha256(sel_txt.encode()).hexdigest() != (HERE / "selection.sha256").read_text().strip():
        raise SystemExit("stop: selection.json does not match selection.sha256")
    if reason is None and (started("test") or (HERE / "results.json").exists()):
        raise SystemExit("stop: test was already started; a corrected rerun needs `rerun test \"the defect\"`")
    if reason is not None:
        supersede("test", reason)
    sel = json.loads(sel_txt)
    logline(f"test started; plan {sha}; code {sha256(__file__)}")
    for what, payload in test(sel):
        if what == "decision":
            atomic_write(HERE / "results.json", dumps(payload))
            logline("Part 2 decision written: " + payload["part2"].get("reading", "skipped"))
        else:
            head, trades = payload
            atomic_write(HERE / "results.json", dumps(head))
            cols = ["config", "cell", "date", "period", "signal", "entry_minute", "implied_spot", "pnl"]
            with OUT_TRADES.open("w", newline="") as f:
                wr = csv.DictWriter(f, fieldnames=cols)
                wr.writeheader()
                wr.writerows(clean(trades))
    md = (HERE / "RESULTS.md").read_text() if (HERE / "RESULTS.md").exists() else ""
    md = md.split("## Part 2: the test")[0]
    atomic_write(HERE / "RESULTS.md", md + md_test(head))
    logline("test finished")
    print(md_test(head))
    return 0


# ---------------------------------------------------------------- selftest (synthetic data only)
def _check(cond, what):
    if not cond:
        raise AssertionError(what)
    print(f"  ok  {what}")


def selftest():
    rng = np.random.default_rng(20261110)
    print("selftest (synthetic data only)")
    # 1. the whole-cent signal test against a direct reading of the plan
    for _ in range(3000):
        o = round(rng.uniform(100, 110), 2)
        c = round(o + rng.normal(0, 0.3), 2)
        h = round(max(o, c) + abs(rng.normal(0, 0.2)), 2)
        l = round(min(o, c) - abs(rng.normal(0, 0.2)), 2)
        got = bar_signals([o, h, l, c])
        oc, hc, lc, cc = (int(round(v * 100)) for v in (o, h, l, c))
        for p, g in zip(THRESH, got):
            body, rr = abs(cc - oc), hc - lc
            exp = (1 if cc > oc else -1) if (rr > 0 and cc != oc and 100 * body >= p * rr) else 0
            assert g == exp
    _check(True, "whole-cent test matches the plan on 3,000 random bars and 12 thresholds")
    _check(bar_signals([1, 2, 3, float("nan")]) is None and bar_signals([1, 0.5, 0.4, 1]) is None
           and bar_signals([1, 2, 0.5]) is None and bar_signals([True, 2, 0.5, 1]) is None, "invalid bars are missing")
    bnd = bar_signals([100.00, 100.15, 99.95, 100.12])          # body 12 cents, range 20 cents = exactly 0.60
    _check(bnd[THRESH.index(60)] == 1 and bnd[THRESH.index(65)] == 0, "boundary: a 12/20-cent body signals at 0.60, not at 0.65")
    bnd = bar_signals([100.12, 100.15, 99.95, 100.00])
    _check(bnd[THRESH.index(60)] == -1, "a down candle gives -1")
    # 2. "both"
    raw = np.array([[[[1, 0]], [[1, 1]]], [[[1, -1]], [[-1, -1]]], [[[np.nan, 1]], [[1, 1]]], [[[0, 0]], [[0, 0]]]], float)
    b = with_both(raw)[:, 2, 0, :]
    _check(np.array_equal(np.nan_to_num(b, nan=9), [[1, 0], [0, -1], [9, 1], [0, 0]]), "'both' signals agree / zero / missing")
    # 3. grid statistics against brute force
    n = 60
    raw = rng.choice([1.0, -1.0, 0.0, np.nan], size=(n, 2, len(CANDLES), len(THRESH)), p=[.3, .3, .35, .05])
    sig = with_both(raw)
    up = rng.normal(0, 100, (n, len(ENTRIES), len(OFFSETS)))
    dn = rng.normal(0, 100, (n, len(ENTRIES), len(OFFSETS)))
    up[rng.random(up.shape) < 0.05] = np.nan
    m1 = np.arange(n) < 25
    st = grid_stats(sig, up, dn, [np.ones(n, bool), m1, ~m1])
    for _ in range(300):
        c = tuple(int(rng.integers(0, g)) for g in GRID)
        cube = {"up": up, "dn": dn}
        x, s = cell_series(c, sig, cube)
        for r, m in zip(st, [np.ones(n, bool), m1, ~m1]):
            xx = x[m]
            fin = np.isfinite(xx)
            assert r["n_days"][c] == fin.sum()
            assert (np.isnan(r["mean"][c]) and fin.sum() == 0) or abs(r["mean"][c] - xx[fin].mean()) < 1e-9
            ss = s[m]
            sd = np.isfinite(ss) & (ss != 0)
            assert r["n_signal"][c] == sd.sum() and r["n_trades"][c] == (sd & fin).sum()
    _check(True, "grid statistics equal a cell-by-cell computation on 300 random cells x 3 masks")
    # 4. plateau, eligibility, pick and ties
    mean = rng.normal(0, 1, GRID)
    mean[0, 0, 5, 0, 0] = np.nan
    pl = plateau(mean)
    for _ in range(200):
        c = tuple(int(rng.integers(0, g)) for g in GRID)
        vals = [mean[c]] + [mean[c[:2] + (c[2] + d,) + c[3:]] for d in (-1, 1) if 0 <= c[2] + d < len(THRESH)]
        vals = [v for v in vals if np.isfinite(v)]
        exp = np.nan if not np.isfinite(mean[c]) else np.mean(vals)
        assert (np.isnan(exp) and np.isnan(pl[c])) or abs(exp - pl[c]) < 1e-12
    _check(True, "plateau score equals the plan's definition on 200 random cells")
    sc = np.zeros(GRID)
    el = np.zeros(GRID, bool)
    a_cell, b_cell = (1, C1550, THRESH.index(60), 0, OFFSETS.index(10)), (0, C1550 + 1, THRESH.index(60), 0, OFFSETS.index(10))
    sc[a_cell] = sc[b_cell] = 5
    el[a_cell] = el[b_cell] = True
    _check(pick(sc, el) == b_cell and distance(a_cell) == 1 == distance(b_cell),
           "tie at equal distance goes to enumeration (C) order: index 15:51 before SPY 15:50")
    c_far = (0, 0, 0, 0, 0)
    sc2, el2 = np.zeros(GRID), np.zeros(GRID, bool)
    sc2[c_far] = sc2[a_cell] = 5
    el2[c_far] = el2[a_cell] = True
    _check(pick(sc2, el2) == a_cell, "exact tie goes to the cell nearest R60")
    _check(pick(np.zeros(GRID), np.zeros(GRID, bool)) is None, "nothing eligible: no pick")
    full = {"n_trades": np.full(GRID, 100), "n_signal": np.full(GRID, 105), "mean": np.ones(GRID)}
    h = {"n_trades": np.full(GRID, 40), "n_signal": np.full(GRID, 42), "mean": np.ones(GRID)}
    _check(eligible(full, h, h).all(), "eligibility boundary: 100 trades, 40 a half, 95.2% coverage")
    h_bad = dict(h, n_signal=np.full(GRID, 43))
    _check(not eligible(full, h_bad, h).any(), "coverage 40/43 = 93% in a half is not eligible")
    # 5. shifts and the null
    _check(shifts_for(60) == list(range(21, 40, 3)), "shift list = range(21, n - 21 + 1, 3)")
    rr = rng.normal(size=(30, 2, 3, 4))
    sh = [21, 24]
    _check(all(np.array_equal(shifted(rr, sh)[k], np.roll(rr, s, axis=0)) for k, s in enumerate(sh)),
           "shifted = np.roll per shift (destination day i gets day i - s)")
    _check(p_value([1, 2, 3], 2) == 3 / 4 and quantile([1.0, 2.0, 3.0], 50) == 2.0 and
           quantile([-np.inf, 1.0, 2.0], 0) is None, "p value and quantile rule")
    # planted signal: the observed best must beat every shift
    n = 150
    # nested thresholds as in real candles: a body ratio and a sign per day, source and minute
    ratio = rng.uniform(0, 1, (n, 2, len(CANDLES)))
    sgn = rng.choice([1.0, -1.0], size=(n, 2, len(CANDLES)))
    raw = sgn[..., None] * (100 * ratio[..., None] >= np.array(THRESH)[None, None, None, :])
    up = rng.normal(-5, 50, (n, len(ENTRIES), len(OFFSETS)))
    dn = rng.normal(-5, 50, (n, len(ENTRIES), len(OFFSETS)))
    a0 = 2
    s_true = sgn[:, 0, a0]                                   # the index candle's direction at 15:47 moves the price
    up[:, a0, :] += np.where(s_true > 0, 300, -300)[:, None]
    dn[:, a0, :] += np.where(s_true < 0, 300, -300)[:, None]
    m1 = np.arange(n) < 75
    masks = [np.ones(n, bool), m1, ~m1]
    global MIN_TRADES, MIN_HALF
    saved = MIN_TRADES, MIN_HALF
    MIN_TRADES, MIN_HALF = 20, 8
    try:
        st = grid_stats(with_both(raw), up, dn, masks)
        scr, el = plateau(st[0]["mean"]), eligible(*st)
        pk = pick(scr, el)
        nulls = null_best(raw, up, dn, masks, shifts_for(n))
    finally:
        MIN_TRADES, MIN_HALF = saved
    _check(pk is not None and pk[0] == 0 and pk[1] == a0 and pk[3] == 0, f"planted signal is picked ({name(pk)})")
    _check(p_value(nulls, scr[pk]) == 1 / (1 + len(nulls)), "planted signal beats every shift")
    # 6. pricing on a synthetic book
    book = {}
    spot = 5003.0
    for k in range(4900, 5105, 5):
        cm, pm = max(spot - k, 0) + 2, max(k - spot, 0) + 2
        book[("C", float(k))] = (cm - 0.5, cm + 0.5)
        book[("P", float(k))] = (pm - 0.5, pm + 0.5)
    del book[("P", 5015.0)]
    q = {m: book for m in ENTRIES}
    g = Guard("2020-01-01", "2020-12-31", "selftest")
    cube = price_days(["2020-06-01"], {"2020-06-01": 5020.0}, g, quote_reader=lambda d: (q, {"conflicts_by_minute": {}}))
    e, j = ENTRIES.index("15:51"), OFFSETS.index(10)
    _check(abs(cube["spot"][0, e] - 5003.0) < 1e-9, "implied spot from the three closest pairs")
    _check(abs(cube["up"][0, e, j] - (100 * (5020 - 4995 - (max(spot - 4995, 0) + 2.5)) - FEE)) < 1e-9,
           "ITM10 call: strike ATM - 10, P&L = 100 x (intrinsic - ask) - $0.09")
    _check(np.isnan(cube["dn"][0, e, j]), "missing put quote: not priced (no substitute strike)")
    _check(abs(cube["dn"][0, e, OFFSETS.index(5)] - (100 * (0 - (max(5010 - spot, 0) + 2.5)) - FEE)) < 1e-9,
           "ITM5 put: strike ATM + 5, expires worthless")
    try:
        price_days(["2020-06-01"], {"2020-06-01": 5020.0}, g,
                   quote_reader=lambda d: (q, {"conflicts_by_minute": {"15:51": 1}}))
        _check(False, "conflicting quotes stop the run")
    except SystemExit:
        _check(True, "conflicting quotes in a priced snapshot stop the run")
    # 7. isolation guards
    g = Guard(*TUNE, "tune")
    try:
        g.check("2024-01-02", "quotes")
        _check(False, "guard refuses a test-period date")
    except IsolationError:
        _check(True, "the tune guard refuses a 2024 date")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "closes.csv"
        p.write_text("DATE,SPX\n12/29/2023,4769.83\n01/02/2024,BOOM\n")
        got = load_closes(*TUNE, Guard(*TUNE, "tune"), path=p)
        _check(got == {"2023-12-29": 4769.83}, "closes outside the window are skipped before their value is parsed")
        f = Path(td) / "trades.csv"
        f.write_text("date,band,sign,spot,kind,strike,bid,ask,mid,pnl,pnl_mid\n2023-01-03,70%+,1,1,C,1,1,1,1,1,1\n"
                     "2024-01-02,70%+,1,1,C,1,1,1,1,1,1\n")
        got = read_trade_file(f, *TUNE, Guard(*TUNE, "tune"))
        _check([r["date"] for r in got] == ["2023-01-03"], "trade-file rows outside the window are not read")
        arch = Path(td) / "arch"
        arch.mkdir()
        (arch / "2023-01-03.json").write_text('{"date": "2023-01-03", "bars": {"15:50": [1, 2, 0.5, 1.5]}}')
        (arch / "2024-01-02.json").write_text('{"date": "2024-01-02", "bars": {}}')
        try:
            load_archive(arch, ["2023-01-03", "2024-01-02"], Guard(*TUNE, "tune"))
            _check(False, "archive guard")
        except IsolationError:
            _check(True, "the archive loader refuses a date outside the window")
        (arch / "2023-01-04.json").write_text('{"date": "2023-01-04", "bars": {"15:50": [1, 2, 0.5, 1.5], "15:50": [1, 2, 0.5, 1.6]}}')
        try:
            load_archive(arch, ["2023-01-04"], Guard(*TUNE, "tune"))
            _check(False, "duplicates")
        except SystemExit:
            _check(True, "conflicting duplicate bar records stop the run")
        (arch / "2023-01-05.json").write_text('{"date": "2023-01-06", "bars": {}}')
        try:
            load_archive(arch, ["2023-01-05"], Guard(*TUNE, "tune"))
            _check(False, "name")
        except SystemExit:
            _check(True, "a file whose date disagrees with its name stops the run")
    # 8. test step before the decision touches only the pick's and R60's columns and contracts
    raw = rng.choice([1.0, -1.0, 0.0], size=(10, 2, len(CANDLES), len(THRESH)))
    pk = (2, 3, 4, 1, 2)
    sig = restricted_signals(raw, [pk, R60])
    filled = {(s, a, b) for s in range(3) for a in range(len(CANDLES)) for b in range(len(THRESH))
              if np.isfinite(sig[:, s, a, b]).any()}
    _check(filled == {(2, 3, 4), (0, C1550, THRESH.index(60))}, "restricted signals hold only the pick and R60")
    nd = needs_for([pk, R60], sig)
    _check(all({(e, j) for e, j, _ in s_} <= {(3, 2), (C1550, OFFSETS.index(10))} for s_ in nd),
           "only the pick's and R60's contracts are priced before the decision")
    # 9. consistency check
    days = ["2023-01-03", "2023-01-04"]
    raw = np.zeros((2, 2, len(CANDLES), len(THRESH)))
    raw[0, 0, C1550, :THRESH.index(70) + 1] = 1          # day 1: index 70%+ up
    sig = with_both(raw)
    cube = {k: np.full((2, len(ENTRIES), len(OFFSETS)), np.nan) for k in ("up", "dn", "ask_up", "ask_dn", "mid_up", "mid_dn")}
    cube["spot"] = np.full((2, len(ENTRIES)), 5001.0)
    cube["up"][0, C1550, OFFSETS.index(10)] = 123.456
    rows = [{"date": "2023-01-03", "band": "70%+", "sign": "1", "kind": "C", "strike": "4990.0", "pnl": "123.4560004"}]
    _check(consistency(R60, raw, sig, cube, days, rows, "selftest")["equal"], "consistency check accepts a matching file")
    for bad in ({"pnl": "123.46"}, {"band": "60-70%"}, {"strike": "4995.0"}):
        try:
            consistency(R60, raw, sig, cube, days, [dict(rows[0], **bad)], "selftest")
            _check(False, f"mismatch {bad}")
        except SystemExit:
            pass
    _check(True, "consistency check stops on a P&L, band or strike mismatch")
    print("selftest passed")
    return 0


def cmd_gate():
    sha = open_gate()
    print(f"gate open: plan {sha} in the ledger; both archives match their frozen manifests")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "rerun":
        if len(sys.argv) < 4 or sys.argv[2] not in ("tune", "test") or len(" ".join(sys.argv[3:])) < 15:
            raise SystemExit('usage: rerun tune|test "the documented defect in words"')
        why = " ".join(sys.argv[3:])
        sys.exit(cmd_tune(why) if sys.argv[2] == "tune" else cmd_test(why))
    sys.exit({"selftest": selftest, "gate": cmd_gate, "tune": cmd_tune, "test": cmd_test}.get(cmd, lambda: print(__doc__) or 2)())
