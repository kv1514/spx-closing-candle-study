"""The 15:50 rule read from the SPY candle (CNBC archive), at real SPXW option prices.

Pre-registration: preregistration/spx_candle_spy.md (locked 2026-11-10T05:01:33Z; its SHA-256 is in
preregistration/LEDGER.md). This file was written after the lock. `run` refuses to join any candle with any price
unless the plan's hash is in the ledger and BOTH frozen archives (SPY and the SPX index) match their manifests.

The signal test, the trade, the statistics and the report helpers are imported from
backtests/spx_candle_realindex/realindex.py (reviewed and run for the index study) and, through it, from
backtests/spx_candle_audit/audit.py.

Commands (from the repository root):
  .venv/bin/python -I backtests/spx_candle_spy/spycandle.py selftest
  .venv/bin/python -I backtests/spx_candle_spy/spycandle.py gate
  .venv/bin/python -I backtests/spx_candle_spy/spycandle.py run          # the one registered run
  .venv/bin/python -I backtests/spx_candle_spy/spycandle.py rerun "the documented defect"
"""
import csv, hashlib, json, math, re, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backtests" / "spx_candle_realindex"))
import realindex as RI

A, BC = RI.A, RI.BC
D = ROOT / "data" / "spx_1549"
SPY_ARCH, IDX_ARCH = D / "cnbc_spy_1m", D / "cnbc_1m"
PREREG = ROOT / "preregistration" / "spx_candle_spy.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
START, END = RI.START, RI.END
B70, B60 = RI.B70, RI.B60
S60, AGREE, S70 = "S60", "AGREE", "S70"
CELLS = (S60, AGREE, S70)
MET, NOT_MET, SEC_MET, INSUFF, NA = ("retrospective criterion met", "retrospective criterion not met",
                                     "retrospective secondary criterion met", "insufficient evidence", "not assessed")


# ---------------------------------------------------------------- the gate
def open_gate(prereg=PREREG, ledger=LEDGER, spy=SPY_ARCH, idx=IDX_ARCH):
    if not prereg.exists():
        raise SystemExit(f"gate: {prereg} does not exist")
    raw = prereg.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    listed = [ln.split() for ln in ledger.read_text().splitlines() if ln.startswith("- ")]
    if not any(len(x) >= 4 and x[2] == sha and x[3] == prereg.name for x in listed):
        raise SystemExit("gate: the plan's SHA-256 is not in the ledger")
    text = raw.decode()
    m1 = re.search(r"manifest \(the SHA-256 .*? is `([0-9a-f]{64})` over ([\d,]+) files", text, flags=re.S)
    m2 = re.search(r"\(manifest `([0-9a-f]{64})`, ([\d,]+) files\)", text)
    if not m1 or not m2:
        raise SystemExit("gate: the plan does not name both manifests")
    for name, arch, m in (("SPY", spy, m1), ("index", idx, m2)):
        got, n = RI.manifest(arch)
        if got != m.group(1) or n != int(m.group(2).replace(",", "")):
            raise SystemExit(f"gate: the {name} archive differs from the frozen one ({n} files, {got[:12]}...)")
    return sha, m1.group(1), m2.group(1)


def load_archive(arch):
    """{date: bars}. Stops on unreadable JSON or a file whose name and stored date disagree."""
    out = {}
    for p in sorted(arch.glob("2*.json")):
        j = json.load(open(p))
        if j.get("date") != p.stem or not isinstance(j.get("bars"), dict):
            raise SystemExit(f"stop: {p.name} does not hold its own date or has no bars object")
        out[p.stem] = j["bars"]
    return out


def bar_ok(b):
    """Exactly four finite numbers (not booleans) with high >= max(open, close), low <= min(open, close), high >= low."""
    if not isinstance(b, (list, tuple)) or len(b) != 4:
        return False
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in b):
        return False
    o, h, l, c = b
    return not (h < max(o, c) or l > min(o, c) or h < l)


# ---------------------------------------------------------------- verdict lines
def verdicts(lines, coverage):
    out = {}
    r = lines[S60]
    out["primary"] = NA if r["t"] is None else (MET if (r["mean"] > 0 and r["t"] >= 2.0) else NOT_MET)
    ps = {k: (1 - RI.phi(lines[c]["t"]) if lines[c]["t"] is not None else None) for k, c in (("secondary_A", AGREE), ("secondary_B", S70))}
    adj = RI.holm([1.0 if ps[k] is None else ps[k] for k in ("secondary_A", "secondary_B")])
    out["p"], out["p_holm"] = ps, {"secondary_A": adj[0], "secondary_B": adj[1]}
    for k, c in (("secondary_A", AGREE), ("secondary_B", S70)):
        ln = lines[c]
        out[k] = NA if ln["t"] is None else (SEC_MET if (ln["mean"] > 0 and ln["t"] >= 2.0 and out["p_holm"][k] <= 0.05) else INSUFF)
    if coverage < 0.80:
        for k in ("primary", "secondary_A", "secondary_B"):
            out[k] = "not assessed: incomplete coverage"
    return out


def grp(trades, days=None, unpriced=None):
    """cell_stats plus the day and unpriced counts and a simple t."""
    e = RI.cell_stats(trades)
    if days is not None:
        e["days"] = days
    if unpriced is not None:
        e["unpriced"] = unpriced
    if trades:
        p = np.array([t["pnl"] for t in trades])
        sd = p.std(ddof=1) if len(p) > 2 else 0.0
        e["t_simple"] = float(p.mean() / (sd / math.sqrt(len(p)))) if sd > 0 else None
    return e


# ---------------------------------------------------------------- the analysis
def analyse(spy, idx, days_rows, closes, has_q, marker, quotes_of, feed_bars, feed_keep):
    base = sorted({r["date"] for r in days_rows if r["calendar"] == "full" and START <= r["date"] <= END})
    years = sorted({d[:4] for d in base})
    zero = lambda: {"base": 0, "no_expiry_marker": 0, "no_quote_file_no_marker": 0, "no_close": 0, "denominator": 0,
                    "no_spy_file": 0, "no_1550_bar": 0, "invalid_1550_bar": 0, "eligible": 0, "eligible_with_index_bar": 0}
    excl = {y: zero() for y in years}
    denom, eligible, sbar = [], [], {}
    ibar = {d: b["15:50"] for d, b in idx.items() if bar_ok(b.get("15:50"))}
    for d in base:
        y = excl[d[:4]]
        y["base"] += 1
        if d not in has_q:
            y["no_expiry_marker" if d in marker else "no_quote_file_no_marker"] += 1
            continue
        if not math.isfinite(closes.get(d, math.nan)):
            y["no_close"] += 1
            continue
        y["denominator"] += 1
        denom.append(d)
        if d not in spy:
            y["no_spy_file"] += 1
            continue
        if "15:50" not in spy[d]:
            y["no_1550_bar"] += 1
            continue
        b = spy[d]["15:50"]
        if not bar_ok(b):
            y["invalid_1550_bar"] += 1
            continue
        y["eligible"] += 1
        y["eligible_with_index_bar"] += d in ibar
        eligible.append(d)
        sbar[d] = b
    tot = {k: sum(v[k] for v in excl.values()) for k in zero()}
    coverage = tot["eligible"] / tot["denominator"] if tot["denominator"] else 0.0
    res = {"period": [START, END], "exclusions_by_year": excl, "exclusions_total": tot, "coverage": coverage}

    quotes = quotes_of(denom)
    scls = {d: RI.classify(sbar[d]) for d in eligible}
    icls = {d: RI.classify(ibar[d]) for d in eligible if d in ibar}

    def feed_sig(d):
        """(signals?, sign, candle) of the feed's 15:50 bar in its original binary64 test; None if no usable bar."""
        rec = (feed_bars.get(d) or {}).get("15:50")
        if not isinstance(rec, (list, tuple)) or len(rec) != 5 or not bar_ok(list(rec[:4])):
            return None
        cd = A.candle(feed_bars[d])
        return (A.fires(cd, 0.6), cd["sign"], cd)

    cache = {}

    def priced(d, sign):
        if (d, sign) not in cache:
            cache[(d, sign)] = RI.trade(quotes[d], sign, closes[d])
        return cache[(d, sign)]

    def in_cell(d, cell):
        band, sign, _ = scls[d]
        if cell == S60:
            return band is not None
        if cell == S70:
            return band == B70
        ib = icls[d]
        return band is not None and ib[0] is not None and ib[1] == sign

    # ---- registered cells
    lines, cells = {}, {}
    for cell in CELLS:
        series, trades, missing = [], [], {}
        yr = {y: {"eligible_days": 0, "signal_days": 0, "retained_days": 0, "missing": 0} for y in years}
        for d in eligible:
            e = yr[d[:4]]
            e["eligible_days"] += 1
            reason = None
            if cell == AGREE and d not in icls:
                v, reason = math.nan, "no usable index bar"
            elif not in_cell(d, cell):
                v = 0.0
            else:
                e["signal_days"] += 1
                t, why = priced(d, scls[d][1])
                if t is None:
                    v, reason = math.nan, why
                else:
                    v = t["pnl"]
                    trades.append({"date": d, "band": scls[d][0], "sign": scls[d][1], **t})
            series.append(v)
            if reason:
                missing.setdefault(reason, {}).setdefault(d[:4], 0)
                missing[reason][d[:4]] += 1
                e["missing"] += 1
            else:
                e["retained_days"] += 1
        ln = RI.nw_line(series)
        lines[cell] = ln
        by_year = {}
        for t in trades:
            by_year.setdefault(t["date"][:4], []).append(t)
        cells[cell] = {"days": ln["n"], "per_day": ln["mean"], "t": ln["t"], "signal_days": sum(v["signal_days"] for v in yr.values()),
                       "missing_by_reason_and_year": missing, **RI.cell_stats(trades),
                       "by_year": {y: {**yr[y], **RI.cell_stats(by_year.get(y, []))} for y in years}}
    res["cells"] = cells
    res["verdicts"] = verdicts(lines, coverage)

    # ================= descriptive from here on: nothing below changes a verdict line or an exclusion ============
    desc = {}
    tr_spy = {}
    for d in eligible:
        if scls[d][1] != 0:
            t, _ = priced(d, scls[d][1])
            if t is not None:
                tr_spy[d] = {"date": d, "band": scls[d][0], "sign": scls[d][1], **t}
    b60_days = [d for d in eligible if scls[d][0] == B60]
    b60 = [tr_spy[d] for d in b60_days if d in tr_spy]
    desc["spy_60_70_band"] = {"signal_days": len(b60_days), "unpriced": len(b60_days) - len(b60), **RI.cell_stats(b60),
                              "by_year": {y: {"signal_days": sum(1 for d in b60_days if d[:4] == y),
                                              "unpriced": sum(1 for d in b60_days if d[:4] == y and d not in tr_spy),
                                              **RI.cell_stats([t for t in b60 if t["date"][:4] == y])} for y in years}}
    # ---- the feed rule on the same eligible days
    ft, fd, fu = [], 0, 0
    for d in eligible:
        fs = feed_sig(d)
        if d in feed_keep and fs and fs[0]:
            fd += 1
            t, _ = priced(d, fs[1])
            if t is None:
                fu += 1
            else:
                ft.append({"date": d, **t})
    desc["feed_rule_on_the_same_days"] = grp(ft, fd, fu)

    # ---- three candles
    pop3 = [d for d in eligible if d in icls and d in feed_keep and feed_sig(d) is not None]
    combos = {f"SPY {'yes' if a else 'no'} / index {'yes' if b else 'no'} / feed {'yes' if c else 'no'}": {"days": 0, "unpriced": 0, "trades": []}
              for a in (True, False) for b in (True, False) for c in (True, False)}
    opposite = 0
    for d in pop3:
        s, i, f = scls[d], icls[d], feed_sig(d)
        flags = (s[0] is not None, i[0] is not None, bool(f[0]))
        signs = [x for x, on in zip((s[1], i[1], f[1]), flags) if on]
        if len(set(signs)) > 1:
            opposite += 1
        e = combos[f"SPY {'yes' if flags[0] else 'no'} / index {'yes' if flags[1] else 'no'} / feed {'yes' if flags[2] else 'no'}"]
        e["days"] += 1
        if signs:
            t, _ = priced(d, signs[0])                           # the first signalling candle in the order SPY, index, feed
            if t is None:
                e["unpriced"] += 1
            else:
                e["trades"].append({"date": d, **t})
    desc["three_candles"] = {"population_days": len(pop3), "days_with_signalling_candles_in_opposite_directions": opposite,
                             "definition": "eligible days with a valid index bar, a usable feed bar and feed keep = true",
                             "combinations": {k: grp(v["trades"], v["days"], v["unpriced"]) for k, v in combos.items()}}

    # ---- two-way tables
    def two_way(pop, other):
        g = {k: {"days": 0, "unpriced": 0, "trades": []} for k in ("both, same direction", "both, opposite directions", "SPY only", "other only", "neither")}
        for d in pop:
            s, (on, osign) = scls[d], other(d)
            if s[0] is not None and on:
                k, sign = ("both, same direction" if s[1] == osign else "both, opposite directions"), s[1]
            elif s[0] is not None:
                k, sign = "SPY only", s[1]
            elif on:
                k, sign = "other only", osign
            else:
                k, sign = "neither", 0
            g[k]["days"] += 1
            if sign:
                t, _ = priced(d, sign)
                if t is None:
                    g[k]["unpriced"] += 1
                else:
                    g[k]["trades"].append({"date": d, **t})
        return {k: grp(v["trades"], v["days"], v["unpriced"]) for k, v in g.items()}
    pop_f = [d for d in eligible if d in feed_keep and feed_sig(d) is not None]
    pop_i = [d for d in eligible if d in icls]
    desc["spy_vs_feed"] = {"population_days": len(pop_f), "groups": two_way(pop_f, lambda d: (bool(feed_sig(d)[0]), feed_sig(d)[1]))}
    desc["spy_vs_index"] = {"population_days": len(pop_i), "groups": two_way(pop_i, lambda d: (icls[d][0] is not None, icls[d][1]))}

    # ---- the SPY candle's ratio in tenths
    buck, flat = {k: {"days": 0, "trades": []} for k in range(10)}, 0
    for d in eligible:
        k = RI.tenth(sbar[d])
        if scls[d][1] == 0 or k is None:
            flat += 1
            continue
        buck[k]["days"] += 1
        if d in tr_spy:
            buck[k]["trades"].append(tr_spy[d])
    label = lambda k: f"[{k / 10:.1f}, {(k + 1) / 10:.1f}" + ("]" if k == 9 else ")")
    desc["spy_ratio_tenths"] = {label(k): {"days": v["days"], "unpriced": v["days"] - len(v["trades"]), **RI.cell_stats(v["trades"])}
                                for k, v in buck.items()}
    desc["flat_or_zero_range_candles_left_out"] = flat

    # ---- the SPY ratio against the other two ratios
    def relation(other_ratio_band):
        xs, ys, n_un = [], [], 0
        rows = ("SPY 70%+", "SPY 60-70%", "SPY under 60%")
        cols = ("other 70%+", "other 60-70%", "other under 60%")
        cross = {r: {c: 0 for c in cols} for r in rows}
        for d in eligible:
            o = other_ratio_band(d)
            if o is None:
                continue
            if scls[d][2] is None or o[0] is None:
                n_un += 1
                continue
            xs.append(scls[d][2]); ys.append(o[0])
            cross[f"SPY {scls[d][0]}" if scls[d][0] else "SPY under 60%"][f"other {o[1]}" if o[1] else "other under 60%"] += 1
        out = {"days": len(xs), "left_out_zero_range": n_un, "pearson": None, "intercept": None, "slope": None}
        if len(xs) >= 2 and np.std(xs) > 0:
            fit = stats.linregress(xs, ys)
            out.update({"intercept": float(fit.intercept), "slope": float(fit.slope)})
            if np.std(ys) > 0:
                out["pearson"] = float(np.corrcoef(xs, ys)[0, 1])
        out["cross_bands"] = {r: {"days": sum(v.values()), "counts": v, "shares": {c: (v[c] / sum(v.values()) if sum(v.values()) else None) for c in cols}}
                              for r, v in cross.items()}
        return out

    def feed_rb(d):
        fs = feed_sig(d)
        if fs is None:
            return None
        cd = fs[2]
        if not cd["rng"] > 0:
            return (None, None)
        return (cd["ratio"], B70 if A.fires(cd, 0.7) else B60 if A.fires(cd, 0.6) else None)
    desc["ratio_spy_vs_feed"] = relation(feed_rb)
    desc["ratio_spy_vs_index"] = relation(lambda d: (icls[d][2], icls[d][0]) if d in icls else None)

    # ---- coverage
    miss = [d for d in denom if d not in sbar]
    run = best = 0
    for d in denom:
        run = run + 1 if d not in sbar else 0
        best = max(best, run)
    fp = {"with_bar": [], "without_bar": []}
    for d in denom:
        fs = feed_sig(d)
        if d not in feed_keep or fs is None:
            continue
        v = 0.0
        if fs[0]:
            t, _ = priced(d, fs[1])
            v = t["pnl"] if t else math.nan
        fp["with_bar" if d in sbar else "without_bar"].append(v)
    desc["coverage"] = {"missing_days": miss, "missing_by_year": {y: sum(1 for d in miss if d[:4] == y) for y in years},
                        "missing_by_month": {}, "longest_run_of_missing_days": best,
                        "feed_rule_per_day": {k: {"population_days": int(len(v)), "unpriced": int(len(v) - np.isfinite(v).sum()),
                                                  "days_in_the_mean": int(np.isfinite(v).sum()),
                                                  "mean": float(np.nanmean(v)) if np.isfinite(v).any() else None}
                                              for k, v in ((k, np.array(v, float)) for k, v in fp.items())}}
    for d in miss:
        desc["coverage"]["missing_by_month"][d[:7]] = desc["coverage"]["missing_by_month"].get(d[:7], 0) + 1

    # ---- the index move after the candle, in the SPY candle's direction, by SPY band (all base dates with the bars)
    mv = {b: {"flat_candle": 0, "missing_index_bar": 0, "undefined_move": 0, "v": []} for b in (B70, B60, "under 60%")}
    no_spy = 0
    for d in base:
        b = (spy.get(d) or {}).get("15:50")
        if not bar_ok(b):
            no_spy += 1
            continue
        band, sign, _ = RI.classify(b)
        e = mv[band or "under 60%"]
        o, c = (idx.get(d) or {}).get("15:51"), (idx.get(d) or {}).get("15:59")
        if sign == 0:
            e["flat_candle"] += 1
        elif not bar_ok(o) or not bar_ok(c):
            e["missing_index_bar"] += 1
        elif o[0] == 0:
            e["undefined_move"] += 1                     # a zero open would divide by zero; counted, not used
        else:
            e["v"].append(1e4 * sign * (c[3] - o[0]) / o[0])
    desc["index_move_bps"] = {"base_dates_without_a_usable_spy_bar": no_spy}
    for band, e in mv.items():
        v = np.array(e["v"], float)
        nz = int((v != 0).sum())
        desc["index_move_bps"][band] = {"days": int(len(v)), "left_out_flat_candle": e["flat_candle"], "left_out_missing_index_bar": e["missing_index_bar"],
                                        "left_out_undefined_move": e["undefined_move"],
                                        "mean_bps": float(v.mean()) if len(v) else None, "t_newey_west": A.nw(v)["t"] if len(v) >= 8 else None,
                                        "the_candles_way": int((v > 0).sum()), "against": int((v < 0).sum()), "zero": int((v == 0).sum()),
                                        "right_way_share_of_nonzero": (float((v > 0).sum() / nz) if nz else None)}
    res["descriptive"] = desc
    return res, [tr_spy[d] for d in eligible if d in tr_spy and scls[d][0]]


# ---------------------------------------------------------------- report
def write_results(res, path):
    w = []
    v, c, d = res["verdicts"], res["cells"], res["descriptive"]
    t = res["exclusions_total"]
    money = RI.money
    f = lambda x, n=2: "n/a" if x is None else f"{x:.{n}f}"
    pc = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"
    names = ((S60, "SPY candle, body >= 60%"), (AGREE, "SPY and index candle both >= 60%, same direction"), (S70, "SPY candle, 70%+ band"))
    years = sorted(res["exclusions_by_year"])
    w.append("# The 15:50 rule on the SPY candle: results\n")
    w.append(f"Pre-registration `preregistration/spx_candle_spy.md` (SHA-256 `{res['prereg_sha256'][:16]}...`). Period {START} to {END}. "
             f"Run at {res['run_at_utc']} ({res['run_kind']}). Generated by `spycandle.py`; do not edit.\n")
    w.append("All three lines describe retrospective numerical criteria on days whose option outcomes were already known. They are not an "
             "independent confirmation, a new holdout or an established trading edge. This is CNBC's archived SPY candle only.\n")
    w.append("## Verdict lines\n")
    w.append("| Line | What | Days | $ per day | Newey-West t | p | Holm p | Reading |\n|---|---|---|---|---|---|---|---|")
    for key, (cell, name) in zip(("primary", "secondary_A", "secondary_B"), names):
        e = c[cell]
        p = "" if key == "primary" else f(v["p"][key], 4)
        hp = "" if key == "primary" else f(v["p_holm"][key], 4)
        w.append(f"| {key.replace('_', ' ').capitalize()} | {name} | {e['days']} | {money(e['per_day'], 2)} | {f(e['t'])} | {p} | {hp} | **{v[key]}** |")
    w.append("\n## Days\n")
    w.append("| Year | Full sessions | No same-day expiry | No quote file, no marker | No close | With quotes and a close | No SPY file | No 15:50 bar | Invalid bar | Eligible | Coverage | Eligible with an index bar |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for y in years + ["All"]:
        e = t if y == "All" else res["exclusions_by_year"][y]
        w.append(f"| {y} | {e['base']} | {e['no_expiry_marker']} | {e['no_quote_file_no_marker']} | {e['no_close']} | {e['denominator']} | {e['no_spy_file']} | {e['no_1550_bar']} | "
                 f"{e['invalid_1550_bar']} | {e['eligible']} | {e['eligible']}/{e['denominator']} = {pc(e['eligible'] / e['denominator'] if e['denominator'] else None)} | {e['eligible_with_index_bar']} |")
    cv = d["coverage"]
    w.append(f"\nDays with quotes and a close but no SPY 15:50 bar: {len(cv['missing_days'])}" + (f" ({', '.join(cv['missing_days'])})" if cv["missing_days"] else "")
             + ". By year: " + ", ".join(f"{y} {n}" for y, n in cv["missing_by_year"].items()) + ". By month: "
             + (", ".join(f"{m} {n}" for m, n in sorted(cv["missing_by_month"].items())) or "none") + f". Longest run: {cv['longest_run_of_missing_days']}. "
             f"The feed rule's known result per day: with a SPY bar {money(cv['feed_rule_per_day']['with_bar']['mean'], 2)} "
             f"({cv['feed_rule_per_day']['with_bar']['population_days']} days, {cv['feed_rule_per_day']['with_bar']['unpriced']} of them unpriced and left out of the mean), "
             f"without {money(cv['feed_rule_per_day']['without_bar']['mean'], 2)} ({cv['feed_rule_per_day']['without_bar']['population_days']} days, "
             f"{cv['feed_rule_per_day']['without_bar']['unpriced']} unpriced).\n")
    w.append("## Cells (one contract, ITM10 at the 15:51 ask in the SPY candle's direction, held to settlement)\n")
    head = "| Cell | Signal days | Missing | Days in the series | Trades | $/trade ask | $/trade mid | Won | Median | Worst | Avg cost |\n|---|---|---|---|---|---|---|---|---|---|---|"
    w.append(head)
    for cell, name in names:
        e = c[cell]
        w.append(f"| {name} | {e['signal_days']} | {t['eligible'] - e['days']} | {e['days']} | {e['trades']} | {money(e.get('per_trade'), 2)} | {money(e.get('per_trade_mid'), 2)} | "
                 f"{pc(e.get('won'))} | {money(e.get('median'))} | {money(e.get('worst'))} | {money(e.get('avg_cost'))} |")
    e = d["spy_60_70_band"]
    w.append(f"| SPY candle, 60-70% band (descriptive) | {e['signal_days']} | {e['unpriced']} | | {e['trades']} | {money(e.get('per_trade'), 2)} | {money(e.get('per_trade_mid'), 2)} | "
             f"{pc(e.get('won'))} | {money(e.get('median'))} | {money(e.get('worst'))} | {money(e.get('avg_cost'))} |")
    fr = d["feed_rule_on_the_same_days"]
    w.append(f"| The feed's rule on the same eligible days (descriptive) | {fr['days']} | {fr['unpriced']} | | {fr['trades']} | {money(fr.get('per_trade'), 2)} | "
             f"{money(fr.get('per_trade_mid'), 2)} | {pc(fr.get('won'))} | {money(fr.get('median'))} | {money(fr.get('worst'))} | {money(fr.get('avg_cost'))} |")
    for cell, name in names:
        e = c[cell]
        w.append(f"\n**{name}, by year.** Missing by reason and year: {json.dumps(e['missing_by_reason_and_year']) if e['missing_by_reason_and_year'] else 'none'}.\n")
        w.append("| Year | Eligible days | Signal days | Missing | Days in the series | Trades | $/trade ask | $/trade mid | Won | Median | Worst | Avg cost |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
        for y in years:
            g = e["by_year"][y]
            w.append(f"| {y} | {g['eligible_days']} | {g['signal_days']} | {g['missing']} | {g['retained_days']} | {g['trades']} | {money(g.get('per_trade'), 2)} | "
                     f"{money(g.get('per_trade_mid'), 2)} | {pc(g.get('won'))} | {money(g.get('median'))} | {money(g.get('worst'))} | {money(g.get('avg_cost'))} |")
    e = d["spy_60_70_band"]
    w.append("\n**SPY candle, 60-70% band, by year (descriptive).**\n")
    w.append("| Year | Signal days | Unpriced | Trades | $/trade ask | $/trade mid | Won | Median | Worst | Avg cost |\n|---|---|---|---|---|---|---|---|---|---|")
    for y in years:
        g = e["by_year"][y]
        w.append(f"| {y} | {g['signal_days']} | {g['unpriced']} | {g['trades']} | {money(g.get('per_trade'), 2)} | {money(g.get('per_trade_mid'), 2)} | "
                 f"{pc(g.get('won'))} | {money(g.get('median'))} | {money(g.get('worst'))} | {money(g.get('avg_cost'))} |")
    w.append("\n## Descriptive (decides nothing)\n")
    def group_table(groups, first):
        w.append(f"| {first} | Days | Unpriced | Trades | $/trade ask | $/trade mid | Won | t (simple) |\n|---|---|---|---|---|---|---|---|")
        for k, e in groups.items():
            w.append(f"| {k} | {e['days']} | {e['unpriced']} | {e['trades']} | {money(e.get('per_trade'), 2)} | {money(e.get('per_trade_mid'), 2)} | {pc(e.get('won'))} | {f(e.get('t_simple'))} |")
    t3 = d["three_candles"]
    w.append(f"### Three candles\n\nPopulation: {t3['population_days']} days ({t3['definition']}). Days on which signalling candles pointed in opposite directions: "
             f"{t3['days_with_signalling_candles_in_opposite_directions']}. ITM10 in the direction of the first signalling candle in the order SPY, index, feed.\n")
    group_table(t3["combinations"], "Which candles signal")
    for key, title, other in (("spy_vs_feed", "SPY against the feed's candle", "feed"), ("spy_vs_index", "SPY against the index candle", "index")):
        w.append(f"\n### {title}\n\nPopulation: {d[key]['population_days']} days. \"Other\" is the {other} candle. Direction: the SPY candle's when it signals, otherwise the other candle's.\n")
        group_table(d[key]["groups"], "Group")
    w.append(f"\n### The SPY candle's body-to-range ratio, in tenths\n\nTrading ITM10 in the candle's direction whatever the ratio. Flat or zero-range candles left out: {d['flat_or_zero_range_candles_left_out']}.\n")
    w.append("| Ratio | Days | Unpriced | Trades | $/trade ask | $/trade mid | Won |\n|---|---|---|---|---|---|---|")
    for k, e in d["spy_ratio_tenths"].items():
        w.append(f"| {k} | {e['days']} | {e['unpriced']} | {e['trades']} | {money(e.get('per_trade'), 2)} | {money(e.get('per_trade_mid'), 2)} | {pc(e.get('won'))} |")
    for key, other in (("ratio_spy_vs_feed", "feed"), ("ratio_spy_vs_index", "index")):
        r = d[key]
        w.append(f"\n### The SPY ratio against the {other} candle's ratio\n\n{r['days']} days with a positive range on both candles ({r['left_out_zero_range']} left out). "
                 f"Correlation {f(r['pearson'])}; {other} ratio = {f(r['intercept'], 3)} + {f(r['slope'], 3)} x SPY ratio. Share of each SPY band's days in each band of the {other} candle (count):\n")
        w.append(f"| SPY band | Days | {other} under 60% | {other} 60-70% | {other} 70%+ |\n|---|---|---|---|---|")
        for rb, e in r["cross_bands"].items():
            w.append(f"| {rb} | {e['days']} | " + " | ".join(f"{pc(e['shares'][k])} ({e['counts'][k]})" for k in ("other under 60%", "other 60-70%", "other 70%+")) + " |")
    m = d["index_move_bps"]
    w.append(f"\n### Index move after the SPY candle (frozen index archive, 15:51 open to 15:59 close, in the SPY candle's direction)\n\nBase dates without a usable SPY bar: {m['base_dates_without_a_usable_spy_bar']}.\n")
    w.append("| SPY band | Days | Mean bps | NW t | The candle's way | Against | Zero | Right, share of non-zero | Left out: flat candle | Left out: missing index bar | Left out: undefined |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for band in (B70, B60, "under 60%"):
        e = m[band]
        w.append(f"| {band} | {e['days']} | {f(e['mean_bps'])} | {f(e['t_newey_west'])} | {e['the_candles_way']} | {e['against']} | {e['zero']} | {pc(e['right_way_share_of_nonzero'])} | "
                 f"{e['left_out_flat_candle']} | {e['left_out_missing_index_bar']} | {e['left_out_undefined_move']} |")
    Path(path).write_text("\n".join(w) + "\n")


# ---------------------------------------------------------------- commands
OUTPUTS = ("results.json", "RESULTS.md")
TRADES = D / "databento" / "spycandle_trades.csv"


def started_before(log):
    return (log.exists() and "run started" in log.read_text()) or any((HERE / n).exists() for n in OUTPUTS) or TRADES.exists()


def cmd_run(kind="registered run", reason=None):
    sha, man_spy, man_idx = open_gate()
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
    code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with log.open("a") as f:
        f.write(f"{stamp} run started; plan {sha}; SPY manifest {man_spy}; index manifest {man_idx}; code {code}\n")
    spy, idx = load_archive(SPY_ARCH), load_archive(IDX_ARCH)
    days_rows, closes = BC.read_days(), BC.read_closes()
    has_q = {p.name[:10] for p in RI.QDIR.glob("*.csv.gz")}
    marker = {p.name[:10] for p in RI.QDIR.glob("*.none")}
    feed_bars, _ = BC.read_bars()
    feed_keep = {r["date"] for r in days_rows if r["keep"].strip().lower() == "true"}
    res, trades = analyse(spy, idx, days_rows, closes, has_q, marker, RI.load_quotes, feed_bars, feed_keep)
    res.update({"prereg_sha256": sha, "spy_manifest_sha256": man_spy, "index_manifest_sha256": man_idx, "run_at_utc": stamp,
                "run_kind": kind, "code_sha256": code})
    res = RI.clean(res)
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
        raise SystemExit("rerun needs the documented defect in words")
    return cmd_run("corrected rerun: " + reason, reason)


def cmd_gate():
    sha, a, b = open_gate()
    print(f"gate open: plan {sha[:16]}... is in the ledger; SPY manifest {a[:16]}... and index manifest {b[:16]}... match the plan")
    return 0


def cmd_selftest():
    # the hand-made option snapshot of realindex's selftest: spot 5001 -> ATM 5000
    book = {}
    for k in range(4970, 5035, 5):
        cc, pp = max(5001.0 - k, 0) + 1.0, max(k - 5001.0, 0) + 1.0
        book[("C", float(k))] = (cc - 0.2, cc + 0.2)
        book[("P", float(k))] = (pp - 0.2, pp + 0.2)
    # SPY bars with sub-penny prints: whole-cent conversion first
    assert RI.classify((500.004, 500.5049, 500.0, 500.30))[:2] == (B60, 1)       # 30 / 50 cents
    assert RI.classify((500.00, 500.50, 500.00, 500.3549))[:2] == (B70, 1)       # 35 / 50 cents
    assert RI.classify((500.00, 500.50, 500.00, 500.0049))[:2] == (None, 0)      # flat after rounding
    assert bar_ok([1.0, 2.0, 0.5, 1.5]) and not bar_ok([1.0, 2.0, 0.5]) and not bar_ok(None) and not bar_ok(1.0)
    assert not bar_ok([True, 2.0, 0.5, 1.5]) and not bar_ok([1.0, float("nan"), 0.5, 1.5]) and not bar_ok([1.0, 0.9, 0.5, 0.8])
    assert not bar_ok(["1.0", 2.0, 0.5, 1.5]) and bar_ok((0.0, 1.0, 0.0, 1.0))
    dts = [f"2021-{m:02d}-{dd:02d}" for m in range(1, 7) for dd in range(1, 21)]
    days_rows, closes, spy, idx, quotes, feed_bars = [], {}, {}, {}, {}, {}
    sb = {0: (500.00, 500.50, 500.00, 500.40), 1: (500.00, 500.50, 500.00, 500.32), 2: (500.00, 500.50, 500.00, 500.10), 3: (500.50, 500.50, 500.00, 500.10)}
    ib = {0: (5000.0, 5005.0, 5000.0, 5004.0), 1: (5000.0, 5005.0, 5000.0, 5001.0), 2: (5000.0, 5005.0, 5000.0, 5004.0), 3: (5005.0, 5005.0, 5000.0, 5004.5)}
    for i, d in enumerate(dts):
        days_rows.append({"date": d, "calendar": "full", "keep": "True"})
        closes[d] = 5010.0 if i % 3 else 4995.0
        k = i % 4
        if i != 5:
            spy[d] = {"15:50": list(sb[k])}
        if i not in (9, 10):                      # day 9 has a SPY signal, day 10 has none: both lack an index bar
            idx[d] = {"15:50": list(ib[k]), "15:51": [5001.0, 5002.0, 5000.0, 5001.5], "15:59": [5005.0, 5006.0, 5004.0, 5005.5]}
        quotes[d] = book
        feed_bars[d] = {"15:50": (ib[k][0], ib[k][1], ib[k][2], ib[k][3], True)}
    qf = lambda dd: {d: quotes[d] for d in dd}
    res, trades = analyse(spy, idx, days_rows, closes, set(dts) - {dts[7]}, {dts[7]}, qf, feed_bars, set(dts))
    t = res["exclusions_total"]
    assert t["base"] == 120 and t["no_expiry_marker"] == 1 and t["denominator"] == 119 and t["no_spy_file"] == 1 and t["eligible"] == 118
    assert t["eligible_with_index_bar"] == 116
    c = res["cells"]
    # kinds: 0 = SPY 80% up & index 80% up (agree); 1 = SPY 64% up & index 20% (SPY only); 2 = no SPY signal; 3 = SPY 80% down & index 10% (SPY only)
    n_k = lambda k: sum(1 for i, d in enumerate(dts) if i % 4 == k and i not in (5, 7))
    assert c[S60]["signal_days"] == n_k(0) + n_k(1) + n_k(3) and c[S70]["signal_days"] == n_k(0) + n_k(3)
    assert c[AGREE]["signal_days"] == n_k(0) and c[S60]["days"] == 118 and c[S70]["days"] == 118
    assert c[AGREE]["days"] == 116 and c[AGREE]["missing_by_reason_and_year"] == {"no usable index bar": {"2021": 2}}   # also on a no-signal day
    assert len(trades) == c[S60]["trades"] and set(res["verdicts"]) >= {"primary", "secondary_A", "secondary_B", "p", "p_holm"}
    d = res["descriptive"]
    assert d["three_candles"]["population_days"] == 116 and sum(v["days"] for v in d["three_candles"]["combinations"].values()) == 116
    assert sum(v["days"] for v in d["spy_vs_index"]["groups"].values()) == 116 and sum(v["days"] for v in d["spy_vs_feed"]["groups"].values()) == 118
    assert d["spy_vs_index"]["groups"]["both, same direction"]["days"] == n_k(0)
    assert d["spy_60_70_band"]["unpriced"] == 0 and sum(g["signal_days"] for g in d["spy_60_70_band"]["by_year"].values()) == n_k(1)
    assert all(e["days"] == e["unpriced"] + e["trades"] for e in d["spy_ratio_tenths"].values())
    # explicit null or malformed 15:50 entries are invalid bars, not missing entries; an unusable feed bar drops out of feed tables
    spy2 = dict(spy); spy2[dts[0]] = {"15:50": None}; spy2[dts[1]] = {"15:50": [True, 1.0, 0.0, 0.5]}; spy2[dts[2]] = {}
    fb2 = dict(feed_bars); fb2[dts[3]] = {"15:50": (5000.0, 4999.0, 5000.0, 5004.0, True)}        # high below the close
    r3, _ = analyse(spy2, idx, days_rows, closes, set(dts) - {dts[7]}, {dts[7]}, qf, fb2, set(dts))
    assert r3["exclusions_total"]["invalid_1550_bar"] == 2 and r3["exclusions_total"]["no_1550_bar"] == 1 and r3["exclusions_total"]["no_spy_file"] == 1
    assert r3["descriptive"]["spy_vs_feed"]["population_days"] == r3["exclusions_total"]["eligible"] - 1
    # a marker is ignored when a quote file exists
    r4, _ = analyse(spy, idx, days_rows, closes, set(dts), {dts[7]}, qf, feed_bars, set(dts))
    assert r4["exclusions_total"]["no_expiry_marker"] == 0 and r4["exclusions_total"]["denominator"] == 120
    assert len(d["spy_ratio_tenths"]) == 10 and d["spy_60_70_band"]["signal_days"] == n_k(1)
    json.dumps(RI.clean(res), allow_nan=False)
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    write_results(RI.clean(dict(res, prereg_sha256="0" * 64, run_at_utc="t", run_kind="selftest")), tmp / "R.md")
    txt = (tmp / "R.md").read_text()
    assert "Secondary a" in txt and "Secondary b" in txt and "Three candles" in txt and "[0.9, 1.0]" in txt
    # verdict wording
    L = lambda m, tt: {"n": 100, "mean": m, "t": tt}
    v = verdicts({S60: L(10, 2.5), AGREE: L(8, 2.6), S70: L(5, 1.0)}, 0.99)
    assert v["primary"] == MET and v["secondary_A"] == SEC_MET and v["secondary_B"] == INSUFF
    assert abs(v["p_holm"]["secondary_A"] - 2 * (1 - RI.phi(2.6))) < 1e-12 and abs(v["p_holm"]["secondary_B"] - (1 - RI.phi(1.0))) < 1e-12
    v = verdicts({S60: L(10, 1.99), AGREE: L(8, 2.0), S70: L(5, 2.0)}, 0.99)
    assert v["primary"] == NOT_MET and v["secondary_A"] == SEC_MET and v["secondary_B"] == SEC_MET          # 2 x 0.0228 <= 0.05
    v = verdicts({S60: L(-1, -2.5), AGREE: L(8, 1.9), S70: L(5, None)}, 0.99)
    assert v["primary"] == NOT_MET and v["secondary_A"] == INSUFF and v["secondary_B"] == NA and v["p_holm"]["secondary_B"] == 1.0
    assert verdicts({S60: L(10, 2.5), AGREE: L(8, 2.6), S70: L(5, 2.6)}, 0.79)["primary"] == "not assessed: incomplete coverage"
    assert verdicts({S60: L(10, 2.5), AGREE: L(8, 2.6), S70: L(5, 2.6)}, 0.80)["primary"] == MET
    # the gate: both manifests, the ledger entry, a changed archive
    (tmp / "s").mkdir(); (tmp / "i").mkdir()
    (tmp / "s" / "2021-01-04.json").write_text("{}"); (tmp / "i" / "2021-01-04.json").write_text("[]")
    ms, ns = RI.manifest(tmp / "s"); mi, ni = RI.manifest(tmp / "i")
    plan = tmp / "plan.md"
    plan.write_text(f"Its manifest (the SHA-256 of the list of file names\nwith each file's SHA-256) is `{ms}` over {ns} files. The index one\n(manifest `{mi}`, {ni} files).\n")
    led = tmp / "LEDGER.md"
    led.write_text("- t  " + "0" * 64 + "  plan.md\n")
    for bad in (True, False):
        if not bad:
            led.write_text(f"- t  {hashlib.sha256(plan.read_bytes()).hexdigest()}  plan.md\n")
        try:
            open_gate(plan, led, tmp / "s", tmp / "i")
            assert not bad
        except SystemExit:
            assert bad
    (tmp / "i" / "2021-01-05.json").write_text("{}")
    try:
        open_gate(plan, led, tmp / "s", tmp / "i"); raise AssertionError("gate opened on a changed index archive")
    except SystemExit:
        pass
    print("selftest passed")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"run": cmd_run, "rerun": cmd_rerun, "gate": cmd_gate, "selftest": cmd_selftest}.get(cmd, lambda: print(__doc__) or 2)())
