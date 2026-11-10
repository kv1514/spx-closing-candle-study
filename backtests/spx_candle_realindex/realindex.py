"""The 15:50 rule read from the real SPX index candle (CNBC archive), and its 60-70% band, at real option prices.

Pre-registration: preregistration/spx_candle_realindex.md (locked 2026-11-09; its SHA-256 is in
preregistration/LEDGER.md). This file was written after the lock. `run` refuses to join any candle with any price
unless the plan's hash is in the ledger and the candle archive's manifest equals the one written in the plan.

The trade (implied spot, strike, ask, settlement, fee) and the Newey-West statistic are imported from
backtests/spx_candle_audit/audit.py, the independent re-implementation that reproduced the published real-price
study trade for trade. The raw quote, close and bar readers are imported from build_cache.py in the same folder.

Commands (from the repository root):
  .venv/bin/python -I backtests/spx_candle_realindex/realindex.py selftest
  .venv/bin/python -I backtests/spx_candle_realindex/realindex.py gate       # hashes only: is the lock in place?
  .venv/bin/python -I backtests/spx_candle_realindex/realindex.py run        # the one registered run
  .venv/bin/python -I backtests/spx_candle_realindex/realindex.py rerun "the documented defect"
`run` refuses if a run was already started. `rerun` needs the defect in words, moves every earlier output into
superseded_<time>/ and logs the reason; no rule of the plan may change.
"""
import csv, hashlib, json, math, re, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backtests" / "spx_candle_audit"))
import audit as A
import build_cache as BC

D = ROOT / "data" / "spx_1549"
ARCH = D / "cnbc_1m"
QDIR = D / "databento" / "cbbo-1m_1500-1601_k60"
PREREG = ROOT / "preregistration" / "spx_candle_realindex.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
START, END = "2021-01-01", "2026-10-20"
B70, B60, R60 = "70%+", "60-70%", "R60"
CELLS = (R60, B70, B60)


# ---------------------------------------------------------------- the gate
def manifest(arch=ARCH):
    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(arch.glob("2*.json"))]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), len(lines)


def open_gate(prereg=PREREG, ledger=LEDGER, arch=ARCH):
    """SystemExit unless the plan is in the ledger and the archive is the frozen one. Returns (plan sha, manifest sha)."""
    if not prereg.exists():
        raise SystemExit(f"gate: {prereg} does not exist")
    text = prereg.read_bytes()
    sha = hashlib.sha256(text).hexdigest()
    listed = [ln.split() for ln in ledger.read_text().splitlines() if ln.startswith("- ")]
    if not any(len(x) >= 4 and x[2] == sha and x[3] == prereg.name for x in listed):
        raise SystemExit("gate: the plan's SHA-256 is not in the ledger")
    m = re.search(r"manifest .*? is `([0-9a-f]{64})` over ([\d,]+) files", text.decode(), flags=re.S)
    if not m:
        raise SystemExit("gate: no manifest hash found in the plan")
    got, n = manifest(arch)
    if got != m.group(1) or n != int(m.group(2).replace(",", "")):
        raise SystemExit(f"gate: the candle archive differs from the frozen one ({n} files, {got[:12]}...)")
    return sha, got


# ---------------------------------------------------------------- the signal (the live alert's whole-cent test)
def cents(x):
    return int(round(x * 100))


def valid_bar(bar):
    if bar is None or len(bar) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bar):
        return False
    o, h, l, c = bar
    return not (h < max(o, c) or l > min(o, c) or h < l)


def classify(bar):
    """(band, sign, ratio) of a valid bar. band is B70, B60 or None (no signal); sign is +1, -1 or 0;
    ratio is body / range in cents (None when the range is 0) and is used for descriptive output only."""
    oc, hc, lc, cc = (cents(v) for v in bar)
    body, rng = abs(cc - oc), hc - lc
    sign = 1 if cc > oc else -1 if cc < oc else 0
    ratio = body / rng if rng > 0 else None
    if rng == 0 or sign == 0 or 10 * body < 6 * rng:
        return None, sign, ratio
    return (B70 if 10 * body >= 7 * rng else B60), sign, ratio


def tenth(bar):
    """Which tenth of [0, 1] the body-to-range ratio falls in, in exact whole-cent arithmetic: 0..9, with a
    ratio of exactly 1 in the last one. None for a zero range."""
    oc, hc, lc, cc = (cents(v) for v in bar)
    body, rng = abs(cc - oc), hc - lc
    return None if rng <= 0 else min((10 * body) // rng, 9)


def in_cell(band, cell):
    return band is not None and (cell == R60 or band == cell)


# ---------------------------------------------------------------- the trade (audit.py's pieces)
def trade(book, sign, close):
    """ITM10 in direction `sign` at the 15:51:00 snapshot `book`. Returns (dict or None, reason)."""
    s = A.implied_spot(book)
    if s is None:
        return None, "no implied spot"
    atm = A.atm_of(s)
    kind = "C" if sign > 0 else "P"
    k = atm - 10 if sign > 0 else atm + 10
    q = book.get((kind, float(k)))
    if not A.valid(q):
        return None, "no valid quote"
    v = A.settle(kind, k, close)
    mid = (q[0] + q[1]) / 2
    return {"spot": s, "kind": kind, "strike": k, "bid": q[0], "ask": q[1], "mid": mid,
            "pnl": 100 * (v - q[1]) - A.FEE, "pnl_mid": 100 * (v - mid) - A.FEE}, ""


# ---------------------------------------------------------------- statistics
def phi(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))


def holm(ps):
    """Holm-adjusted p-values, in the input order."""
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def welch(x, y):
    """Welch's t for mean(x) - mean(y): unbiased variances, Welch-Satterthwaite df, two-sided Student-t p."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2 or len(y) < 2:
        return None
    vx, vy = x.var(ddof=1) / len(x), y.var(ddof=1) / len(y)
    se = math.sqrt(vx + vy)
    if not se > 0:
        return None
    t = (x.mean() - y.mean()) / se
    df = (vx + vy) ** 2 / (vx ** 2 / (len(x) - 1) + vy ** 2 / (len(y) - 1))
    return {"diff": float(x.mean() - y.mean()), "t": float(t), "df": float(df), "p": float(2 * stats.t.sf(abs(t), df))}


def nw_line(series):
    """Mean and Newey-West t of a per-day series (audit.nw); t is None when n < 8 or the SE is 0."""
    y = np.asarray(series, float)
    y = y[np.isfinite(y)]
    r = A.nw(y)
    if r["n"] < 8:
        r["t"] = None
    return r


def cell_stats(trades):
    p = np.array([t["pnl"] for t in trades])
    m = np.array([t["pnl_mid"] for t in trades])
    if not len(p):
        return {"trades": 0}
    return {"trades": int(len(p)), "per_trade": float(p.mean()), "per_trade_mid": float(m.mean()),
            "won": float((p > 0).mean()), "median": float(np.median(p)), "worst": float(p.min()),
            "avg_cost": float(np.mean([100 * t["ask"] for t in trades]))}


def verdicts(lines, w, coverage):
    """The four verdict lines of the plan. `lines` maps cell -> nw_line result; `w` is welch() or None."""
    out = {}
    r = lines[R60]
    if r["t"] is None:
        out["primary"] = "not assessed"
    else:
        out["primary"] = "source-check criterion met" if (r["mean"] > 0 and r["t"] >= 2.0) else "source-check criterion not met"
    a, b = lines[B70], lines[B60]
    pa = 1 - phi(a["t"]) if a["t"] is not None else None
    pb = 2 * phi(-abs(b["t"])) if b["t"] is not None else None
    pc = w["p"] if w else None
    adj = holm([1.0 if p is None else p for p in (pa, pb, pc)])
    out["p"] = {"secondary_A": pa, "secondary_B": pb, "secondary_C": pc}
    out["p_holm"] = {"secondary_A": adj[0], "secondary_B": adj[1], "secondary_C": adj[2]}
    if a["t"] is None:
        out["secondary_A"] = "not assessed"
    else:
        out["secondary_A"] = "has an edge" if (a["mean"] > 0 and a["t"] >= 2.0 and adj[0] <= 0.05) else "insufficient evidence"
    if b["t"] is None:
        out["secondary_B"] = "not assessed"
    elif b["mean"] > 0 and b["t"] >= 2.0 and adj[1] <= 0.05:
        out["secondary_B"] = "has an edge"
    elif b["mean"] < 0 and b["t"] <= -2.0 and adj[1] <= 0.05:
        out["secondary_B"] = "loses"
    else:
        out["secondary_B"] = "insufficient evidence"
    if w is None:
        out["secondary_C"] = "not assessed"
    elif w["t"] >= 2.0 and adj[2] <= 0.05:
        out["secondary_C"] = "70%+ is better"
    elif w["t"] <= -2.0 and adj[2] <= 0.05:
        out["secondary_C"] = "60-70% is better"
    else:
        out["secondary_C"] = "insufficient evidence"
    if coverage < 0.80:
        for k in ("primary", "secondary_A", "secondary_B", "secondary_C"):
            out[k] = "not assessed: incomplete coverage"
    return out


# ---------------------------------------------------------------- inputs
def load_archive(arch=ARCH):
    out = {}
    for p in sorted(arch.glob("2*.json")):
        j = json.load(open(p))
        out[j["date"]] = j["bars"]
    return out


def load_quotes(dates):
    quotes, conflicts = {}, 0
    for d in dates:
        q, meta = BC.read_quotes(QDIR / f"{d}.csv.gz", d)
        conflicts += meta["conflicts_by_minute"].get("15:51", 0)
        quotes[d] = q["15:51"]
    if conflicts:
        raise SystemExit(f"stop: {conflicts} contracts have two different quotes in the 15:51:00 snapshot")
    return quotes


# ---------------------------------------------------------------- the analysis
def analyse(arch, days_rows, closes, has_q, marker, quotes_of, feed_bars, feed_keep):
    """Everything after the gate. `quotes_of(dates)` returns {date: 15:51 book}."""
    base = sorted({r["date"] for r in days_rows if r["calendar"] == "full" and START <= r["date"] <= END})
    excl = {}
    denom, eligible, bars = [], [], {}
    for d in base:
        y = excl.setdefault(d[:4], {"base": 0, "no_expiry_marker": 0, "no_quote_file_no_marker": 0, "no_close": 0,
                                    "denominator": 0, "no_cnbc_file": 0, "no_1550_bar": 0, "invalid_1550_bar": 0, "eligible": 0})
        y["base"] += 1
        if d not in has_q:
            y["no_expiry_marker" if d in marker else "no_quote_file_no_marker"] += 1
            continue
        if not math.isfinite(closes.get(d, math.nan)):
            y["no_close"] += 1
            continue
        y["denominator"] += 1
        denom.append(d)
        if d not in arch:
            y["no_cnbc_file"] += 1
            continue
        b = arch[d].get("15:50")
        if b is None:
            y["no_1550_bar"] += 1
            continue
        if not valid_bar(b):
            y["invalid_1550_bar"] += 1
            continue
        y["eligible"] += 1
        eligible.append(d)
        bars[d] = b
    tot = {k: sum(v[k] for v in excl.values()) for k in next(iter(excl.values()))}
    coverage = tot["eligible"] / tot["denominator"] if tot["denominator"] else 0.0
    res = {"period": [START, END], "exclusions_by_year": excl, "exclusions_total": tot, "coverage": coverage,
           "coverage_by_year": {y: (v["eligible"] / v["denominator"] if v["denominator"] else None) for y, v in excl.items()}}

    quotes = quotes_of(denom)
    cls = {d: classify(bars[d]) for d in eligible}

    # ---- priced trade for every eligible day with a direction (used by the cells and the descriptive tables)
    tr, why = {}, {}
    for d in eligible:
        band, sign, _ = cls[d]
        if sign == 0:
            continue
        t, reason = trade(quotes[d], sign, closes[d])
        if t is None:
            why[d] = reason
        else:
            tr[d] = {"date": d, "band": band or "", "sign": sign, **t}

    # ---- per-day series, statistics and verdict lines
    lines, cells = {}, {}
    for cell in CELLS:
        series, trades, unpriced = [], [], {}
        for d in eligible:
            if not in_cell(cls[d][0], cell):
                series.append(0.0)
            elif d in tr:
                series.append(tr[d]["pnl"])
                trades.append(tr[d])
            else:
                series.append(math.nan)
                unpriced.setdefault(why[d], {}).setdefault(d[:4], 0)
                unpriced[why[d]][d[:4]] += 1
        ln = nw_line(series)
        lines[cell] = ln
        by_year = {}
        for t in trades:
            by_year.setdefault(t["date"][:4], []).append(t)
        years = sorted({d[:4] for d in base})
        yr = {y: {"eligible_days": 0, "signal_days": 0, "retained_days": 0, "unpriced": 0} for y in years}
        for d, v in zip(eligible, series):
            e = yr[d[:4]]
            e["eligible_days"] += 1
            e["signal_days"] += in_cell(cls[d][0], cell)
            e["retained_days"] += math.isfinite(v)
            e["unpriced"] += not math.isfinite(v)
        cells[cell] = {"days": ln["n"], "per_day": ln["mean"], "t": ln["t"], "signal_days": int(sum(in_cell(cls[d][0], cell) for d in eligible)),
                       "unpriced_by_reason_and_year": unpriced, **cell_stats(trades),
                       "by_year": {y: {**yr[y], **cell_stats(by_year.get(y, []))} for y in years}}
    p70 = [tr[d]["pnl"] for d in eligible if cls[d][0] == B70 and d in tr]
    p60 = [tr[d]["pnl"] for d in eligible if cls[d][0] == B60 and d in tr]
    w = welch(p70, p60)
    res["cells"] = cells
    res["comparison_70_minus_6070_per_trade"] = w
    res["comparison_trades"] = {B70: len(p70), B60: len(p60)}
    res["verdicts"] = verdicts(lines, w, coverage)

    # ================= descriptive from here on: nothing below changes a verdict line or an exclusion ============
    desc = {}
    # ---- the disagreement table against the feed's candle
    def feed_class(d):
        cd = A.candle(feed_bars[d]) if d in feed_bars else None
        if cd is None:
            return None, 0
        return ("signal" if A.fires(cd, 0.6) else "none"), cd["sign"]
    cnt = {f"index {i} / feed {f}": 0 for i in ("up", "down", "none") for f in ("up", "down", "none")}
    groups = {"both, same direction": [], "both, opposite directions": [], "index only": [], "feed only": []}
    both_days = [d for d in eligible if d in feed_keep and d in feed_bars and "15:50" in feed_bars[d]]
    for d in both_days:
        band, sign, _ = cls[d]
        fc, fs = feed_class(d)
        i = ("up" if sign > 0 else "down") if band else "none"
        f = ("up" if fs > 0 else "down") if fc == "signal" else "none"
        cnt[f"index {i} / feed {f}"] += 1
        if band and fc == "signal":
            g = "both, same direction" if sign == fs else "both, opposite directions"
            if d in tr:
                groups[g].append(tr[d])
        elif band:
            if d in tr:
                groups["index only"].append(tr[d])
        elif fc == "signal":
            t, _ = trade(quotes[d], fs, closes[d])
            if t is not None:
                groups["feed only"].append({"date": d, **t})
    desc["disagreement_population"] = {"days": len(both_days), "definition": "eligible days in the feed's kept set with a feed 15:50 bar"}
    desc["disagreement_counts"] = cnt
    desc["disagreement_groups"] = {}
    for g, v in groups.items():
        e = cell_stats(v)
        if v:
            p = np.array([t["pnl"] for t in v])
            sd = p.std(ddof=1) if len(p) > 2 else 0.0
            e["t_simple"] = float(p.mean() / (sd / math.sqrt(len(p)))) if sd > 0 else None
            e["by_index_band"] = {b: cell_stats([t for t in v if t.get("band") == b]) for b in (B70, B60)}
        desc["disagreement_groups"][g] = e
    # ---- the index candle's ratio in tenths (exact whole-cent edges; a ratio of exactly 1 is in the last one)
    buck, flat = {k: {"days": 0, "trades": []} for k in range(10)}, 0
    for d in eligible:
        band, sign, ratio = cls[d]
        k = tenth(bars[d])
        if sign == 0 or k is None:
            flat += 1
            continue
        buck[k]["days"] += 1
        if d in tr:
            buck[k]["trades"].append(tr[d])
    label = lambda k: f"[{k / 10:.1f}, {(k + 1) / 10:.1f}" + ("]" if k == 9 else ")")
    desc["index_ratio_buckets"] = {label(k): {"days": v["days"], **cell_stats(v["trades"])} for k, v in buck.items()}
    desc["flat_or_zero_range_candles_left_out"] = flat
    # ---- the two ratios against each other: every eligible day with a feed 15:50 bar (no kept-set restriction)
    pair_days, xs, ys, undefined = [], [], [], 0
    ib_names, fb_names = ("index 70%+", "index 60-70%", "index under 60%"), ("feed 70%+", "feed 60-70%", "feed under 60%")
    cross = {i: {f: 0 for f in fb_names} for i in ib_names}
    for d in eligible:
        if d not in feed_bars or "15:50" not in feed_bars[d]:
            continue
        band, sign, ratio = cls[d]
        cd = A.candle(feed_bars[d])
        if ratio is None or cd is None or not cd["rng"] > 0:
            undefined += 1
            continue
        pair_days.append(d)
        xs.append(ratio); ys.append(cd["ratio"])
        fb = "feed 70%+" if A.fires(cd, 0.7) else "feed 60-70%" if A.fires(cd, 0.6) else "feed under 60%"
        cross[f"index {band}" if band else "index under 60%"][fb] += 1
    rel = {"days": len(xs), "left_out_undefined_ratio": undefined,
           "definition": "eligible days with a feed 15:50 bar and a positive range on both candles",
           "index_signal_days": int(sum(1 for d in pair_days if cls[d][0])),
           "feed_signal_days": int(sum(1 for d in pair_days if A.fires(A.candle(feed_bars[d]), 0.6))),
           "pearson": None, "intercept": None, "slope": None, "index_ratio_where_feed_is_0.60": None, "mean_index_minus_feed": None}
    if len(xs) >= 3 and np.std(xs) > 0 and np.std(ys) > 0:
        fit = stats.linregress(xs, ys)
        rel.update({"pearson": float(np.corrcoef(xs, ys)[0, 1]), "intercept": float(fit.intercept), "slope": float(fit.slope),
                    "index_ratio_where_feed_is_0.60": float((0.6 - fit.intercept) / fit.slope) if fit.slope != 0 else None,
                    "mean_index_minus_feed": float(np.mean(np.array(xs) - np.array(ys)))})
    desc["ratio_relation"] = rel
    desc["cross_bands"] = {i: {"days": sum(row.values()), "counts": row,
                               "shares": {f: (row[f] / sum(row.values()) if sum(row.values()) else None) for f in fb_names}}
                           for i, row in cross.items()}
    # ---- coverage: where the holes are, and the feed rule's known result with and without a CNBC bar
    miss = [d for d in denom if d not in bars]
    run = best = 0
    for d in denom:
        run = run + 1 if d not in bars else 0
        best = max(best, run)
    feed_pnl = {"with_bar": [], "without_bar": []}
    for d in denom:
        if d not in feed_keep or d not in feed_bars:
            continue
        cd = A.candle(feed_bars[d])
        v = 0.0
        if A.fires(cd, 0.6):
            t, _ = trade(quotes[d], cd["sign"], closes[d])
            v = t["pnl"] if t else math.nan
        feed_pnl["with_bar" if d in bars else "without_bar"].append(v)
    desc["coverage"] = {"missing_days": miss, "missing_by_month": {}, "longest_run_of_missing_days": best,
                        "feed_rule_per_day": {k: {"days": int(np.isfinite(v).sum()),
                                                  "mean": float(np.nanmean(v)) if np.isfinite(v).any() else None}
                                              for k, v in ((k, np.array(v, float)) for k, v in feed_pnl.items())}}
    for d in miss:
        desc["coverage"]["missing_by_month"][d[:7]] = desc["coverage"]["missing_by_month"].get(d[:7], 0) + 1
    desc["coverage"]["missing_by_year"] = {y: sum(1 for d in miss if d[:4] == y) for y in sorted({d[:4] for d in base})}
    # ---- the index move after the candle, from the CNBC bars, by band
    mv, unbanded = {}, {"2019-2020": 0, "2021-2026": 0}
    for d, b in sorted(arch.items()):
        if not ("2019-01-01" <= d <= END):
            continue
        per = "2019-2020" if d < START else "2021-2026"
        if not valid_bar(b.get("15:50")):
            unbanded[per] += 1                          # a file with no usable 15:50 bar: no band can be assigned
            continue
        band, sign, _ = classify(b["15:50"])
        e = mv.setdefault(per, {}).setdefault(band or "under 60%", {"flat_candle": 0, "missing_1551_or_1559_bar": 0, "v": []})
        o, c = b.get("15:51"), b.get("15:59")
        if sign == 0:
            e["flat_candle"] += 1
        elif not valid_bar(o) or not valid_bar(c):
            e["missing_1551_or_1559_bar"] += 1
        else:
            e["v"].append(1e4 * sign * (c[3] - o[0]) / o[0])
    desc["index_move_bps"] = {}
    for per in ("2019-2020", "2021-2026"):
        desc["index_move_bps"][per] = {"sessions_without_a_usable_1550_bar": unbanded[per]}
        for band in (B70, B60, "under 60%"):
            e = mv.get(per, {}).get(band, {"flat_candle": 0, "missing_1551_or_1559_bar": 0, "v": []})
            v = np.array(e["v"], float)
            nz = int((v != 0).sum())
            desc["index_move_bps"][per][band] = {
                "days": int(len(v)), "left_out_flat_candle": e["flat_candle"], "left_out_missing_bar": e["missing_1551_or_1559_bar"],
                "mean_bps": float(v.mean()) if len(v) else None, "t_newey_west": A.nw(v)["t"] if len(v) >= 8 else None,
                "up_the_candles_way": int((v > 0).sum()), "against": int((v < 0).sum()), "zero": int((v == 0).sum()),
                "right_way_share_of_nonzero": (float((v > 0).sum() / nz) if nz else None)}
    res["descriptive"] = desc
    trades_out = [tr[d] for d in eligible if d in tr and cls[d][0]]
    return res, trades_out


# ---------------------------------------------------------------- report
def money(x, n=0):
    return "n/a" if x is None else f"{'+' if x >= 0 else '-'}${abs(x):,.{n}f}"


def clean(o):
    """NaN and infinities become None so the JSON is standard."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def write_results(res, path):
    w = []
    v, c, d = res["verdicts"], res["cells"], res["descriptive"]
    t = res["exclusions_total"]
    f = lambda x, n=2: "n/a" if x is None else f"{x:.{n}f}"
    pc = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"
    names = ((R60, "Index candle, body >= 60%"), (B70, "70%+ band"), (B60, "60-70% band"))
    years = sorted(res["exclusions_by_year"])
    w.append("# The 15:50 rule on the real SPX index candle: results\n")
    w.append(f"Pre-registration `preregistration/spx_candle_realindex.md` (SHA-256 `{res['prereg_sha256'][:16]}...`). "
             f"Period {START} to {END}. Run at {res['run_at_utc']} ({res['run_kind']}). Generated by `realindex.py`; do not edit.\n")
    w.append("This is an outcome-informed, retrospective check of the signal's source. It is not an independent confirmation "
             "and not a new holdout. \"Per day\" means per eligible day of that cell that could be priced or had no signal.\n")
    w.append("## Verdict lines\n")
    w.append("| Line | What | n | Estimate | Unit | Statistic | p | Holm p | Reading |\n|---|---|---|---|---|---|---|---|---|")
    for key, (cell, name) in zip(("primary", "secondary_A", "secondary_B"), names):
        e = c[cell]
        p = "" if key == "primary" else f(v["p"][key], 4)
        hp = "" if key == "primary" else f(v["p_holm"][key], 4)
        w.append(f"| {key.replace('_', ' ').capitalize()} | {name} | {e['days']} days | {money(e['per_day'], 2)} | $ per day | Newey-West t {f(e['t'])} | {p} | {hp} | **{v[key]}** |")
    cm, ct = res["comparison_70_minus_6070_per_trade"], res["comparison_trades"]
    w.append(f"| Secondary C | 70%+ band minus 60-70% band | {ct[B70]} and {ct[B60]} trades | {money(cm['diff'], 2) if cm else 'n/a'} | $ per priced trade | "
             f"{('Welch t ' + f(cm['t']) + ', df ' + f(cm['df'], 0)) if cm else 'n/a'} | {f(v['p']['secondary_C'], 4)} | {f(v['p_holm']['secondary_C'], 4)} | **{v['secondary_C']}** |")
    w.append("\n## Days\n")
    w.append("| Year | Full sessions | No same-day expiry | No quote file, no marker | No close | With quotes and a close | No CNBC file | No 15:50 bar | Invalid bar | Eligible | Coverage |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for y in years + ["All"]:
        e = t if y == "All" else res["exclusions_by_year"][y]
        w.append(f"| {y} | {e['base']} | {e['no_expiry_marker']} | {e['no_quote_file_no_marker']} | {e['no_close']} | {e['denominator']} | {e['no_cnbc_file']} | "
                 f"{e['no_1550_bar']} | {e['invalid_1550_bar']} | {e['eligible']} | {e['eligible']}/{e['denominator']} = {pc(e['eligible'] / e['denominator'] if e['denominator'] else None)} |")
    cv = d["coverage"]
    w.append(f"\nDays with quotes and a close but no CNBC 15:50 bar: {len(cv['missing_days'])}"
             + (f" ({', '.join(cv['missing_days'])})" if cv["missing_days"] else "") + f". By year: "
             + ", ".join(f"{y} {n}" for y, n in cv["missing_by_year"].items()) + ". By month: "
             + (", ".join(f"{m} {n}" for m, n in sorted(cv["missing_by_month"].items())) or "none") + f". Longest run: {cv['longest_run_of_missing_days']}.\n")
    w.append("## Cells (one contract, ITM10 at the 15:51 ask, held to settlement)\n")
    w.append("| Cell | Eligible days | Signal days | Unpriced | Days in the series | Trades | $/trade ask | $/trade mid | Won | Median | Worst | Avg cost |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for cell, name in names:
        e = c[cell]
        w.append(f"| {name} | {t['eligible']} | {e['signal_days']} | {e['signal_days'] - e['trades']} | {e['days']} | {e['trades']} | {money(e.get('per_trade'), 2)} | "
                 f"{money(e.get('per_trade_mid'), 2)} | {pc(e.get('won'))} | {money(e.get('median'))} | {money(e.get('worst'))} | {money(e.get('avg_cost'))} |")
    for cell, name in names:
        e = c[cell]
        w.append(f"\n**{name}, by year.** Unpriced by reason and year: {json.dumps(e['unpriced_by_reason_and_year']) if e['unpriced_by_reason_and_year'] else 'none'}.\n")
        w.append("| Year | Eligible days | Signal days | Unpriced | Days in the series | Trades | $/trade ask | $/trade mid | Won | Median | Worst | Avg cost |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
        for y in years:
            g = e["by_year"][y]
            w.append(f"| {y} | {g['eligible_days']} | {g['signal_days']} | {g['unpriced']} | {g['retained_days']} | {g['trades']} | {money(g.get('per_trade'), 2)} | "
                     f"{money(g.get('per_trade_mid'), 2)} | {pc(g.get('won'))} | {money(g.get('median'))} | {money(g.get('worst'))} | {money(g.get('avg_cost'))} |")
    w.append("\n## Descriptive (decides nothing)\n")
    w.append("### Where the index candle and the feed's candle disagree\n")
    dp = d["disagreement_population"]
    w.append(f"Population: {dp['days']} days ({dp['definition']}). Days in each cell (index candle down the side, feed candle across):\n")
    w.append("| Index \\ Feed | feed up | feed down | feed none |\n|---|---|---|---|")
    for i in ("up", "down", "none"):
        w.append(f"| index {i} | " + " | ".join(str(d["disagreement_counts"][f"index {i} / feed {x}"]) for x in ("up", "down", "none")) + " |")
    w.append("\nITM10 in the index candle's direction (in the feed candle's direction for \"feed only\"), priced trades:\n")
    w.append("| Group | Trades | $/trade ask | $/trade mid | Won | t (simple) | of which 70%+ | of which 60-70% |\n|---|---|---|---|---|---|---|---|")
    for g, e in d["disagreement_groups"].items():
        bb = e.get("by_index_band", {})
        cellf = lambda x: f"{x['trades']} at {money(x.get('per_trade'), 2)}" if x and x.get("trades") else "0"
        w.append(f"| {g} | {e['trades']} | {money(e.get('per_trade'), 2)} | {money(e.get('per_trade_mid'), 2)} | {pc(e.get('won'))} | {f(e.get('t_simple'))} | {cellf(bb.get(B70))} | {cellf(bb.get(B60))} |")
    w.append("\n### The index candle's body-to-range ratio, in tenths\n")
    w.append(f"Trading ITM10 in the candle's direction whatever the ratio. Flat or zero-range candles left out: {d['flat_or_zero_range_candles_left_out']}.\n")
    w.append("| Ratio | Days | Trades | $/trade ask | $/trade mid | Won |\n|---|---|---|---|---|---|")
    for k, e in d["index_ratio_buckets"].items():
        w.append(f"| {k} | {e['days']} | {e['trades']} | {money(e.get('per_trade'), 2)} | {money(e.get('per_trade_mid'), 2)} | {pc(e.get('won'))} |")
    r = d["ratio_relation"]
    w.append(f"\n### The two ratios\n\nPopulation: {r['days']} days ({r['definition']}); {r['left_out_undefined_ratio']} left out for an undefined ratio. "
             f"Signal days in it: index {r['index_signal_days']}, feed {r['feed_signal_days']}. Correlation {f(r['pearson'])}; "
             f"feed ratio = {f(r['intercept'], 3)} + {f(r['slope'], 3)} x index ratio; the feed's 0.60 corresponds to {f(r['index_ratio_where_feed_is_0.60'], 3)} "
             f"on the index candle; the index ratio is higher by {f(r['mean_index_minus_feed'], 3)} on average.\n")
    w.append("Share of each index band's days in each feed band (count):\n")
    w.append("| Index band | Days | feed under 60% | feed 60-70% | feed 70%+ |\n|---|---|---|---|---|")
    for ib, e in d["cross_bands"].items():
        w.append(f"| {ib} | {e['days']} | " + " | ".join(f"{pc(e['shares'][k])} ({e['counts'][k]})" for k in ("feed under 60%", "feed 60-70%", "feed 70%+")) + " |")
    fr = cv["feed_rule_per_day"]
    w.append(f"\n### Are the missing days different?\n\nThe feed rule's known result per day: on days with a CNBC bar {money(fr['with_bar']['mean'], 2)} "
             f"({fr['with_bar']['days']} days); on days without {money(fr['without_bar']['mean'], 2)} ({fr['without_bar']['days']} days).\n")
    w.append("### Index move after the candle (CNBC bars, 15:51 open to 15:59 close, in the candle's direction)\n")
    w.append("| Period | Band | Days | Mean bps | NW t | The candle's way | Against | Zero | Right, share of non-zero | Left out: flat candle | Left out: missing bar |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for per in ("2019-2020", "2021-2026"):
        for band in (B70, B60, "under 60%"):
            e = d["index_move_bps"][per][band]
            w.append(f"| {per} | {band} | {e['days']} | {f(e['mean_bps'])} | {f(e['t_newey_west'])} | {e['up_the_candles_way']} | {e['against']} | {e['zero']} | "
                     f"{pc(e['right_way_share_of_nonzero'])} | {e['left_out_flat_candle']} | {e['left_out_missing_bar']} |")
        w.append(f"| {per} | no usable 15:50 bar | {d['index_move_bps'][per]['sessions_without_a_usable_1550_bar']} | | | | | | | | |")
    Path(path).write_text("\n".join(w) + "\n")


# ---------------------------------------------------------------- commands
OUTPUTS = ("results.json", "RESULTS.md")
TRADES = D / "databento" / "realindex_trades.csv"


def started_before(log):
    return (log.exists() and "run started" in log.read_text()) or any((HERE / n).exists() for n in OUTPUTS) or TRADES.exists()


def cmd_run(kind="registered run", reason=None):
    sha, man = open_gate()
    log = HERE / "run_log.txt"
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if reason is None:
        if started_before(log):
            raise SystemExit("stop: a run was already started. A corrected rerun needs `rerun \"the documented defect\"`.")
    else:
        keep = HERE / ("superseded_" + stamp.replace(":", "").replace("+", "Z")[:17])
        keep.mkdir()
        for n in OUTPUTS:
            if (HERE / n).exists():
                (HERE / n).rename(keep / n)
        if TRADES.exists():
            TRADES.rename(keep / TRADES.name)
        with log.open("a") as f:
            f.write(f"{stamp} RERUN, earlier outputs kept in {keep.name}; documented defect: {reason}\n")
    with log.open("a") as f:
        f.write(f"{stamp} run started; plan {sha}; manifest {man}; code {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}\n")
    arch = load_archive()
    days_rows = BC.read_days()
    closes = BC.read_closes()
    has_q = {p.name[:10] for p in QDIR.glob("*.csv.gz")}
    marker = {p.name[:10] for p in QDIR.glob("*.none")}
    feed_bars, _ = BC.read_bars()
    feed_keep = {r["date"] for r in days_rows if r["keep"].strip().lower() == "true"}
    res, trades = analyse(arch, days_rows, closes, has_q, marker, load_quotes, feed_bars, feed_keep)
    res.update({"prereg_sha256": sha, "archive_manifest_sha256": man, "run_at_utc": stamp, "run_kind": kind,
                "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    res = clean(res)
    json.dump(res, open(HERE / "results.json", "w"), indent=1, allow_nan=False)
    write_results(res, HERE / "RESULTS.md")
    with TRADES.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["date", "band", "sign", "spot", "kind", "strike", "bid", "ask", "mid", "pnl", "pnl_mid"])
        wr.writeheader()
        wr.writerows(trades)
    with log.open("a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} run finished; results {hashlib.sha256((HERE / 'results.json').read_bytes()).hexdigest()}\n")
    print(open(HERE / "RESULTS.md").read())
    return 0


def cmd_rerun():
    reason = " ".join(sys.argv[2:]).strip()
    if len(reason) < 15:
        raise SystemExit("rerun needs the documented defect in words, for example: rerun \"the report dropped line C\"")
    return cmd_run("corrected rerun: " + reason, reason)


def cmd_gate():
    sha, man = open_gate()
    print(f"gate open: plan {sha[:16]}... is in the ledger; archive manifest {man[:16]}... matches the plan")
    return 0


def cmd_selftest():
    # bands: whole cents; 60% and 70% are inclusive lower edges
    assert classify((100.00, 105.00, 100.00, 103.00))[:2] == (B60, 1)
    assert classify((100.00, 105.00, 100.00, 103.49))[:2] == (B60, 1)
    assert classify((100.00, 105.00, 100.00, 103.50))[:2] == (B70, 1)
    assert classify((100.00, 105.00, 100.00, 102.99))[:2] == (None, 1)
    assert classify((105.00, 105.00, 100.00, 101.00))[:2] == (B70, -1)
    assert classify((100.0, 101.0, 99.0, 100.0))[:2] == (None, 0) and classify((1.0, 1.0, 1.0, 1.0)) == (None, 0, None)
    assert classify((7572.89013671875, 7577.39013671875, 7572.72021484375, 7575.70996094))[0] == B60     # float32 noise
    assert classify((7565.54, 7565.54, 7560.48, 7562.42))[:2] == (B60, -1)                               # 2026-11-09
    assert valid_bar((1.0, 2.0, 0.5, 1.5)) and not valid_bar((1.0, 0.9, 0.5, 0.8)) and not valid_bar((1.0, 2.0, 1.2, 1.5))
    assert not valid_bar((1.0, float("nan"), 0.5, 1.5)) and not valid_bar(None) and not valid_bar((1.0, 2.0, 0.5))
    assert in_cell(B60, R60) and in_cell(B70, R60) and in_cell(B60, B60) and not in_cell(B60, B70) and not in_cell(None, R60)
    assert valid_bar([1.0, 2.0, 0.5, 1.5])                                                       # JSON gives lists
    # tenths, exact edges: 60% is in [0.6, 0.7), 70% in [0.7, 0.8), a full body in the last one
    assert tenth((100.00, 105.00, 100.00, 103.00)) == 6 and tenth((100.00, 105.00, 100.00, 103.50)) == 7
    assert tenth((100.00, 105.00, 100.00, 105.00)) == 9 and tenth((100.00, 105.00, 100.00, 100.49)) == 0 and tenth((1.0, 1.0, 1.0, 1.0)) is None
    assert tenth((100.00, 110.00, 100.00, 102.90)) == 2 and tenth((100.00, 110.00, 100.00, 103.00)) == 3
    # Holm and Welch
    assert holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06] and holm([1.0, 1.0, 1.0]) == [1.0, 1.0, 1.0]
    w = welch([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0, 10.0])
    ref = stats.ttest_ind([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0, 10.0], equal_var=False)
    assert abs(w["t"] - ref.statistic) < 1e-12 and abs(w["p"] - ref.pvalue) < 1e-12 and welch([1.0], [1.0, 2.0]) is None
    assert abs(phi(0) - 0.5) < 1e-15 and abs(phi(1.959963984540054) - 0.975) < 1e-12
    # the trade on a hand-made snapshot: spot 5001 -> ATM 5000 -> call 4990 at the ask
    book = {}
    for k in range(4970, 5035, 5):
        c = max(5001.0 - k, 0) + 1.0
        p = max(k - 5001.0, 0) + 1.0
        book[("C", float(k))] = (c - 0.2, c + 0.2)
        book[("P", float(k))] = (p - 0.2, p + 0.2)
    t, why = trade(book, 1, 5010.0)
    assert why == "" and t["strike"] == 4990 and t["kind"] == "C" and abs(t["ask"] - 12.2) < 1e-9 and abs(t["pnl"] - (100 * (20 - 12.2) - 0.09)) < 1e-9
    t, _ = trade(book, -1, 5010.0)
    assert t["strike"] == 5010 and t["kind"] == "P" and abs(t["pnl"] - (100 * (0 - 10.2) - 0.09)) < 1e-9
    assert trade({k: v for k, v in list(book.items())[:4]}, 1, 5010.0) == (None, "no implied spot")
    b2 = dict(book); b2[("C", 4990.0)] = (5.0, 0.0)
    assert trade(b2, 1, 5010.0) == (None, "no valid quote")
    # a small synthetic study: 3 cells, the series semantics, the verdict lines and the coverage rule
    days_rows, closes, arch, quotes, feed_bars = [], {}, {}, {}, {}
    import random
    rnd = random.Random(7)
    dts = [f"2021-{m:02d}-{d:02d}" for m in range(1, 7) for d in range(1, 21)]
    for i, d in enumerate(dts):
        days_rows.append({"date": d, "calendar": "full", "keep": "True"})
        closes[d] = 5010.0 if i % 3 else 4995.0
        kind = i % 4
        bar = {0: (5000.0, 5005.0, 5000.0, 5004.0), 1: (5000.0, 5005.0, 5000.0, 5003.2), 2: (5000.0, 5005.0, 5000.0, 5001.0),
               3: (5005.0, 5005.0, 5000.0, 5001.0)}[kind]
        if i != 5:
            arch[d] = {"15:50": list(bar), "15:51": [5001.0, 5002.0, 5000.0, 5001.5], "15:59": [5005.0, 5006.0, 5004.0, 5005.5]}
        quotes[d] = book
        feed_bars[d] = {"15:50": (bar[0], bar[1], bar[2], bar[3], True)}
    res, trades = analyse(arch, days_rows, closes, set(dts) - {dts[7]}, {dts[7]}, lambda dd: {d: quotes[d] for d in dd}, feed_bars, set(dts))
    t = res["exclusions_total"]
    assert t["base"] == 120 and t["no_expiry_marker"] == 1 and t["denominator"] == 119 and t["no_cnbc_file"] == 1 and t["eligible"] == 118
    c = res["cells"]
    assert c[R60]["days"] == 118 and c[B70]["days"] == 118 and c[B60]["days"] == 118               # zeros outside the cell
    assert c[R60]["trades"] == c[B70]["trades"] + c[B60]["trades"] and c[B60]["trades"] > 0 and c[B70]["trades"] > 0
    assert abs(c[R60]["per_day"] - (c[B70]["per_day"] + c[B60]["per_day"])) < 1e-9
    assert set(res["verdicts"]) >= {"primary", "secondary_A", "secondary_B", "secondary_C", "p", "p_holm"}
    assert sum(res["descriptive"]["disagreement_counts"].values()) == 118 and len(trades) == c[R60]["trades"]
    assert len(res["descriptive"]["disagreement_counts"]) == 9 and len(res["descriptive"]["index_ratio_buckets"]) == 10
    assert res["descriptive"]["ratio_relation"]["days"] == sum(e["days"] for e in res["descriptive"]["cross_bands"].values())
    yy = c[B60]["by_year"]["2021"]
    assert yy["eligible_days"] == 118 and yy["retained_days"] + yy["unpriced"] == 118 and yy["signal_days"] == c[B60]["signal_days"]
    # a signal day that cannot be priced is missing in its own cell and 0 in the other band's cell
    bad = dict(book); bad[("C", 4990.0)] = (5.0, 0.0)
    target = next(d for d in dts if d in arch and classify(arch[d]["15:50"])[0] == B60)
    r2, _ = analyse(arch, days_rows, closes, set(dts) - {dts[7]}, {dts[7]}, lambda dd: {d: (bad if d == target else quotes[d]) for d in dd}, feed_bars, set(dts))
    assert r2["cells"][B60]["days"] == 117 and r2["cells"][B70]["days"] == 118 and r2["cells"][R60]["days"] == 117
    assert r2["cells"][B60]["unpriced_by_reason_and_year"] == {"no valid quote": {"2021": 1}} and r2["cells"][B70]["unpriced_by_reason_and_year"] == {}
    json.dumps(clean(res), allow_nan=False)                                                    # standard JSON
    import io, contextlib, tempfile as _tf
    rr = clean(dict(res, prereg_sha256="0" * 64, run_at_utc="t", run_kind="selftest"))
    tmpf = Path(_tf.mkdtemp()) / "R.md"
    write_results(rr, tmpf)
    txt = tmpf.read_text()
    assert "Secondary C" in txt and "$ per priced trade" in txt and "index none" in txt and "[0.9, 1.0]" in txt and "By month" in txt
    rr["comparison_70_minus_6070_per_trade"] = None
    write_results(rr, tmpf)
    assert "Secondary C" in tmpf.read_text()                                                   # the line is always printed
    low, _ = analyse({d: arch[d] for d in list(arch)[:60]}, days_rows, closes, set(dts), set(), lambda dd: {d: quotes[d] for d in dd}, feed_bars, set(dts))
    assert low["coverage"] < 0.8 and all(low["verdicts"][k] == "not assessed: incomplete coverage" for k in ("primary", "secondary_A", "secondary_B", "secondary_C"))
    # verdict wording on hand-made lines
    L = lambda m, tt: {"n": 100, "mean": m, "t": tt}
    v = verdicts({R60: L(10, 2.5), B70: L(8, 2.6), B60: L(-1, -0.3)}, {"diff": 50.0, "t": 1.0, "df": 50.0, "p": 0.32}, 0.99)
    assert v["primary"] == "source-check criterion met" and v["secondary_A"] == "has an edge" and v["secondary_B"] == "insufficient evidence" and v["secondary_C"] == "insufficient evidence"
    v = verdicts({R60: L(10, 1.9), B70: L(8, 2.05), B60: L(-9, -3.0)}, {"diff": 90.0, "t": 3.2, "df": 50.0, "p": 0.002}, 0.99)
    assert v["primary"] == "source-check criterion not met" and v["secondary_B"] == "loses" and v["secondary_C"] == "70%+ is better"
    assert v["secondary_A"] == "has an edge"            # t 2.05 -> p 0.0202, Holm 0.0202 (largest of three)
    v = verdicts({R60: L(1, None), B70: L(8, None), B60: L(1, None)}, None, 0.99)
    assert v["primary"] == v["secondary_A"] == v["secondary_B"] == v["secondary_C"] == "not assessed"
    v = verdicts({R60: L(10, 2.5), B70: L(1, 0.2), B60: L(9, 3.5)}, {"diff": -90.0, "t": -3.2, "df": 50.0, "p": 0.002}, 0.80)
    assert v["secondary_B"] == "has an edge" and v["secondary_C"] == "60-70% is better" and v["primary"] == "source-check criterion met"   # 80% exactly is assessed
    assert verdicts({R60: L(10, 2.5), B70: L(1, 0.2), B60: L(9, 3.5)}, None, 0.7999)["primary"] == "not assessed: incomplete coverage"
    # a t of 2.0 that fails Holm reads "insufficient evidence": p 0.0228 x 3 > 0.05 when the other two are larger
    v = verdicts({R60: L(10, 2.5), B70: L(8, 2.0), B60: L(1, 0.1)}, {"diff": 1.0, "t": 0.1, "df": 50.0, "p": 0.9}, 0.99)
    assert v["secondary_A"] == "insufficient evidence" and abs(v["p_holm"]["secondary_A"] - 3 * (1 - phi(2.0))) < 1e-12
    # the conflict stop looks only at the 15:51:00 snapshot; identical repeats and NaN repeats are not conflicts
    import gzip as _gz
    tq = Path(_tf.mkdtemp())
    head = "ts_recv,ts_event,rtype,publisher_id,instrument_id,side,price,size,flags,bid_px_00,ask_px_00,bid_sz_00,ask_sz_00,bid_pb_00,ask_pb_00,symbol"
    row = lambda hhmm, bid, ask: f"2024-03-11T{hhmm}:00.000000000Z,x,1,1,1,N,,1,0,{bid},{ask},1,1,0,0,SPXW  240311C05055000"
    def meta_of(rows):
        with _gz.open(tq / "q.csv.gz", "wt") as f:
            f.write("\n".join([head] + rows) + "\n")
        return BC.read_quotes(tq / "q.csv.gz", "2024-03-11")[1]
    assert meta_of([row("19:50", 1.0, 1.2), row("19:50", 1.1, 1.3)])["conflicts_by_minute"] == {"15:50": 1}
    assert meta_of([row("19:51", 1.0, 1.2), row("19:51", 1.0, 1.2)])["conflicts_by_minute"] == {}
    assert meta_of([row("19:51", "", 1.2), row("19:51", "", 1.2)])["conflicts_by_minute"] == {}
    assert meta_of([row("19:51", 1.0, 1.2), row("19:51", 1.0, 1.25)])["conflicts_by_minute"] == {"15:51": 1}
    # the gate: a plan that is not in the ledger, and an archive that changed
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "a").mkdir()
    (tmp / "a" / "2021-01-04.json").write_text("{}")
    man, n = manifest(tmp / "a")
    plan = tmp / "plan.md"
    plan.write_text(f"The manifest of the archive is `{man}` over {n} files.\n")
    led = tmp / "LEDGER.md"
    led.write_text("- t  " + "0" * 64 + "  plan.md\n")
    try:
        open_gate(plan, led, tmp / "a"); raise AssertionError("gate opened without a ledger entry")
    except SystemExit:
        pass
    led.write_text(f"- t  {hashlib.sha256(plan.read_bytes()).hexdigest()}  plan.md\n")
    assert open_gate(plan, led, tmp / "a")[1] == man
    (tmp / "a" / "2021-01-05.json").write_text("{}")
    try:
        open_gate(plan, led, tmp / "a"); raise AssertionError("gate opened on a changed archive")
    except SystemExit:
        pass
    print("selftest passed")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"run": cmd_run, "rerun": cmd_rerun, "gate": cmd_gate, "selftest": cmd_selftest}.get(cmd, lambda: print(__doc__) or 2)())
