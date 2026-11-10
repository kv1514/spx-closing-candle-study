"""Does an early exit beat holding to the close? Six stop / take-profit rules for the 15:50 strong-body signal.

Pre-registration: preregistration/spx_candle_exit_rules.md (an addendum to spx_close_candle_scan.md,
spx_candle_forward_options.md and spx_candle_strike_ladder.md). `run` refuses to read any data unless that file
exists and its SHA-256 is in preregistration/LEDGER.md.

  Part 1  real Robinhood 0DTE prices on forward days: each rule watches the Robinhood SPX one-minute closes
          15:51 .. 15:58 and sells at the next minute's option open; a rule that never fires holds to the
          official close (the strike ladder's exit A).
  Part 2  the backtest's 644 strong-body days (D1, 2021-01-01 .. 2026-10-20). Entry prices are the strike
          ladder's model prices; an early exit is priced by the same Bachelier model with the time left.
          A model, not observed P&L.

Usage (from /Users/kv15/trading):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_exits/exits.py selftest
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_exits/exits.py run

Outputs (rebuilt from scratch on each run): data/spx_1549/forward/exits_forward_log.csv,
backtests/spx_candle_exits/results.json, backtests/spx_candle_exits/RESULTS.md.
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

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
PREREG = ROOT / "preregistration" / "spx_candle_exit_rules.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
SPX_ROOT = ROOT / "data" / "spx_1549"
OUT_CSV = SPX_ROOT / "forward" / "exits_forward_log.csv"
OUT_JSON = HERE / "results.json"
OUT_MD = HERE / "RESULTS.md"
STRIKES_PY = ROOT / "backtests" / "spx_candle_strikes" / "strikes.py"
STRIKES_JSON = ROOT / "backtests" / "spx_candle_strikes" / "results.json"
SCAN_PY = ROOT / "backtests" / "spx_candle_scan" / "scan.py"
OPTIONS_PY = ROOT / "analysis" / "candle_1550_options_forward.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sk = load_module("spx_candle_strikes_ro", STRIKES_PY)     # importing runs nothing; its gate is in run()

OFFSETS = (10, 20, 0)                  # ITM10 is the headline; ITM20 and ATM also reported
HEADLINE_OFFSET = 10
HALF_SPREAD = sk.HALF_SPREAD           # 0.10
FEES = sk.FEES                         # (0.09, 0.74)
MULT = sk.MULT                         # 100
CHECKS = [f"15:{m:02d}" for m in range(51, 59)]   # closes watched: 15:51 .. 15:58
EXITS = [f"15:{m:02d}" for m in range(52, 60)]    # sale at the next open: 15:52 .. 15:59
N_CHECKS = len(CHECKS)                 # 8
RULES = {"H": (None, None), "S3": (3.0, None), "S5": (5.0, None), "S8": (8.0, None),
         "T5": (None, 5.0), "T10": (None, 10.0), "B5_10": (5.0, 10.0)}
EARLY = [r for r in RULES if r != "H"]
BONF_T = 2.64                          # two-sided 0.05, Bonferroni over the six rules (as registered)
CRIT_VARIANT, CRIT_ALSO = "a_calibrated", ("b_constant_vol", "c_realized_move_fair")
VARIANTS = ("a_calibrated", "b_constant_vol", "c_realized_move_fair", "a_half_spread_0.05",
            "a_half_spread_0.20", "a_no_skew")
SELF_CHECK_TOL_USD = 0.01
RULE_TEXT = {"H": "hold to the 16:00 settlement", "S3": "stop 3 points against", "S5": "stop 5 points against",
             "S8": "stop 8 points against", "T5": "take profit 5 points in favour",
             "T10": "take profit 10 points in favour", "B5_10": "stop 5 against or take profit 10 in favour"}


# ------------------------------------------------------------------------------------------------
# rule mechanics
# ------------------------------------------------------------------------------------------------
def first_fire(m, stop, target) -> np.ndarray:
    """m: trades x 8 moves (points at level L, + = in the trade's favour) at the closes 15:51 .. 15:58, NaN =
    no real bar (not checked). Returns the index of the first close where the rule fires, or -1."""
    m = np.atleast_2d(np.asarray(m, float))
    cond = np.zeros(m.shape, bool)
    with np.errstate(invalid="ignore"):
        if stop is not None:
            cond |= m <= -stop
        if target is not None:
            cond |= m >= target
    fired = cond.any(axis=1)
    return np.where(fired, cond.argmax(axis=1), -1)


def n_remaining(j):
    """Bars from the exit minute (the open after check j) through 15:59 inclusive: 8 at 15:52 .. 1 at 15:59."""
    return N_CHECKS - np.asarray(j)


# ------------------------------------------------------------------------------------------------
# Part 2: modelled 2021-2026 sample
# ------------------------------------------------------------------------------------------------
def model_exits(T: dict, C, O, L: float, sigma9, f_o: float, h: float, o: int) -> dict:
    """Per rule: arrays of P&L (both fees), return on premium, fired flag and exit index for one offset.
    C: closes 15:51 .. 15:58, O: opens 15:52 .. 15:59 (trades x 8, raw index points)."""
    S, X, d = T["S"], T["X"], T["d"]
    n = len(S)
    lam = L / S
    is_call = d > 0
    Xp = L + lam * (X - S)
    k_atm = L + lam * (sk.strike_for(S) - S)
    K = k_atm - d * o
    sigma9 = np.broadcast_to(np.asarray(sigma9, float), S.shape)
    ok = np.isfinite(sigma9)
    s9 = np.where(ok, sigma9, 1.0)
    price = f_o * sk.bachelier(is_call, L, K, s9)
    cost = price + h
    pay_hold = sk.intrinsic(is_call, K, Xp)
    m = d[:, None] * (C - S[:, None]) * lam[:, None]
    out = {"ok": ok, "price": price, "cost": cost}
    for rule, (stop, target) in RULES.items():
        j = np.full(n, -1) if rule == "H" else first_fire(m, stop, target)
        fired = j >= 0
        jj = np.where(fired, j, 0)
        Ou = O[np.arange(n), jj]
        if np.any(fired & ~np.isfinite(Ou)):
            raise SystemExit(f"{rule}: a rule fired but the next minute's D1 open is missing; the plan does not "
                             "cover this, stopping")
        Pu = L + lam * (np.where(fired, Ou, S) - S)
        su = s9 * np.sqrt(n_remaining(jj) / 9.0)
        ex = f_o * sk.bachelier(is_call, Pu, K, su)
        proceeds = np.maximum(ex - h, 0.0)
        r = {"fired": fired, "j": j, "exit_price": np.where(fired, ex, np.nan)}
        for fee in FEES:
            r[f"pnl_{fee:.2f}"] = np.where(fired, MULT * (proceeds - cost) - 2 * fee, MULT * (pay_hold - cost) - fee)
        r["ret"] = r["pnl_0.09"] / (MULT * cost + FEES[0])
        out[rule] = r
    return out


def rule_stats(res: dict, scan, mask=None) -> dict:
    base = res["H"]
    sel = res["ok"] & (mask if mask is not None else True)
    out = {}
    for rule in RULES:
        r = res[rule]
        p9 = r["pnl_0.09"][sel]
        diff = p9 - base["pnl_0.09"][sel]
        nw = scan.nw_mean_test(p9)
        nwd = scan.nw_mean_test(diff) if rule != "H" and np.any(diff != 0) else {"t": None}
        fired = r["fired"][sel]
        out[rule] = {
            "n": int(sel.sum()), "share_fired": float(fired.mean()),
            "mean_exit_minute_index": float(np.mean(r["j"][sel][fired])) if fired.any() else None,
            "mean_pnl_fee_0.09": float(p9.mean()), "mean_pnl_fee_0.74": float(r["pnl_0.74"][sel].mean()),
            "nw_t": nw["t"], "share_pnl_positive": float(np.mean(p9 > 0)),
            "median_pnl": float(np.median(p9)), "p5_pnl": float(np.percentile(p9, 5)), "worst_pnl": float(p9.min()),
            "mean_return_on_premium": float(r["ret"][sel].mean()),
            "diff_vs_hold_mean": float(diff.mean()), "diff_vs_hold_nw_t": nwd["t"]}
    return out


def load_calibration(path: Path = STRIKES_JSON) -> dict:
    r = json.loads(Path(path).read_text())
    cal = r["calibration"]
    return {"k_d1": float(cal["k_d1"]), "sigma_bps_median_c1": float(cal["sigma_bps_median_c1"]),
            "f": {o: float(cal["skew"][sk.label(o)]["f"]) for o in OFFSETS},
            "strike_ladder_part2": r["part2"]["variants"], "strike_ladder_sha256": r["prereg_sha256"]}


def variant_specs(T: dict, cal: dict, hc: dict) -> dict:
    L = hc["level"]
    n = len(T["S"])
    sig_a = cal["k_d1"] * T["rv"] * sk.SQRT_REMAINING * L
    sig_b = np.full(n, cal["sigma_bps_median_c1"] / 1e4 * L)
    sig_c = np.full(n, hc["mean_abs_move"] / (2 * sk.PHI0))
    f, f1 = cal["f"], {o: 1.0 for o in OFFSETS}
    return {"a_calibrated": (sig_a, f, HALF_SPREAD), "b_constant_vol": (sig_b, f, HALF_SPREAD),
            "c_realized_move_fair": (sig_c, f1, HALF_SPREAD), "a_half_spread_0.05": (sig_a, f, 0.05),
            "a_half_spread_0.20": (sig_a, f, 0.20), "a_no_skew": (sig_a, f1, HALF_SPREAD)}


def criterion(variants: dict) -> dict:
    lab = sk.label(HEADLINE_OFFSET)
    out = {}
    for rule in EARLY:
        a = variants[CRIT_VARIANT][lab][rule]
        t = a["diff_vs_hold_nw_t"]
        main = a["diff_vs_hold_mean"] > 0 and t is not None and t > BONF_T
        also = {v: variants[v][lab][rule]["diff_vs_hold_mean"] > 0 for v in CRIT_ALSO}
        out[rule] = {"mean_d_a": a["diff_vs_hold_mean"], "t_d_a": t, "main_condition": bool(main),
                     "positive_in": also, "better_than_holding": bool(main and all(also.values())),
                     "verdict": "better than holding" if main and all(also.values())
                     else "no evidence that it beats holding"}
    return out


def part2(scan, T: dict, C, O, cal: dict, hc: dict, self_check: bool = True) -> dict:
    L = hc["level"]
    specs = variant_specs(T, cal, hc)
    variants, checks = {}, []
    for name, (sig, f, h) in specs.items():
        variants[name] = {}
        for o in OFFSETS:
            res = model_exits(T, C, O, L, sig, f[o], h, o)
            st = rule_stats(res, scan)
            variants[name][sk.label(o)] = st
            if self_check:
                ref = cal["strike_ladder_part2"][name]["by_offset"][sk.label(o)]["mean_pnl_fee_0.09"]
                got = st["H"]["mean_pnl_fee_0.09"]
                checks.append({"variant": name, "offset": sk.label(o), "hold_mean": got, "strike_ladder_mean": ref,
                               "diff": got - ref})
                if abs(got - ref) > SELF_CHECK_TOL_USD:
                    raise SystemExit(f"self-check failed: {name} {sk.label(o)} hold {got:.4f} vs strike ladder "
                                     f"{ref:.4f}")
    sig_a, f, h = specs["a_calibrated"]
    years = np.array([int(dd[:4]) for dd in T["dates"]])
    periods = {}
    for pname, mask in (("2021_2022", years <= 2022), ("2023_2026", years >= 2023)):
        periods[pname] = {sk.label(o): rule_stats(model_exits(T, C, O, L, sig_a, f[o], h, o), scan, mask)
                          for o in OFFSETS}
    n_missing_checks = int(np.sum(~np.isfinite(C)))
    return {"level": L, "n_trades": int(len(T["S"])), "first": str(T["dates"][0]), "last": str(T["dates"][-1]),
            "n_missing_index_closes": n_missing_checks, "self_check": checks, "variants": variants,
            "periods_a": periods, "criterion": criterion(variants)}


def d1_paths(scan, P, T: dict):
    idx = np.searchsorted(P.dates, T["dates"])
    if not (np.all(idx < len(P.dates)) and np.array_equal(P.dates[idx], T["dates"])):
        raise SystemExit("strong-body trade dates do not map back into the D1 panel")
    if not (np.allclose(P.O[idx, scan.I1551], T["S"]) and np.allclose(P.C[idx, scan.I1559], T["X"])):
        raise SystemExit("D1 15:51 open / 15:59 close do not match the strike ladder's trades")
    C = P.C[idx, scan.I1551:scan.I1559]            # closes 15:51 .. 15:58
    O = P.O[idx, scan.I1551 + 1:scan.I1559 + 1]    # opens 15:52 .. 15:59
    assert C.shape[1] == N_CHECKS and O.shape[1] == N_CHECKS
    return C, O


# ------------------------------------------------------------------------------------------------
# Part 1: real prices on forward days
# ------------------------------------------------------------------------------------------------
COLUMNS = ["date", "signal_name", "signal", "offset", "rule", "status", "kind", "strike", "S_1551_open", "settle",
           "settle_source", "provisional", "entry_open_1551", "cost_incl_half_spread", "fired_at_close",
           "exit_minute", "exit_open", "exit_value", "pnl_fee_0.09", "pnl_fee_0.74", "return_on_premium"]


def part1(cfo, L: float, spx_root: Path = SPX_ROOT, spx_bars=None) -> dict:
    spx_bars = spx_bars or (lambda day: sk.rh_spx_bars(day, cfo))
    directions = cfo.load_forward_module().frozen_directions()["directions"]
    closes, conflicts = cfo.official_closes(spx_root)
    rows = []
    for lr in cfo.read_log():
        day = lr["date"]
        folder = spx_root / f"live_{day}"
        opts, avail = cfo.load_day_options(folder, day) if folder.exists() else (None, "no_option_files")
        S = float(lr["entry_1551_open"])
        k_atm = float(sk.strike_for(S))
        settle, src = closes.get(day, (None, None))
        provisional = settle is None
        settle_used = float(lr["exit_1559_close"]) if provisional else settle
        idx_bars = spx_bars(day) if opts is not None else {}
        for name, short in sk.FORWARD_SIGNALS:
            s = int(lr[f"{short}_signal"]) * directions[name]
            if s == 0:
                continue
            m = np.array([[s * (idx_bars[hm][1] - S) * L / S if hm in idx_bars else np.nan for hm in CHECKS]])
            for o in OFFSETS:
                kind, K = sk.contract_for(s, k_atm, o)
                for rule, (stop, target) in RULES.items():
                    r = {"date": day, "signal_name": name, "signal": s, "offset": sk.label(o), "rule": rule,
                         "kind": kind, "strike": K, "S_1551_open": S, "settle": settle_used,
                         "settle_source": src or "provisional_1559_close", "provisional": provisional}
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
                            cost = E + HALF_SPREAD
                            r.update({"entry_open_1551": E, "cost_incl_half_spread": cost})
                            j = -1 if rule == "H" else int(first_fire(m, stop, target)[0])
                            if j >= 0:
                                r["fired_at_close"], r["exit_minute"] = CHECKS[j], EXITS[j]
                                Xo = cfo.price(bars, EXITS[j], "open_price", allow_zero=True)
                                if Xo is None:
                                    r["status"] = "exit_bar_missing"
                                else:
                                    r["status"] = "traded"
                                    r["exit_open"] = Xo
                                    r["exit_value"] = max(Xo - HALF_SPREAD, 0.0)
                                    for fee in FEES:
                                        r[f"pnl_fee_{fee:.2f}"] = MULT * (r["exit_value"] - cost) - 2 * fee
                            else:
                                r["status"] = "traded"
                                r["exit_value"] = cfo.intrinsic(kind, K, settle_used)
                                for fee in FEES:
                                    r[f"pnl_fee_{fee:.2f}"] = MULT * (r["exit_value"] - cost) - fee
                            if r["status"] == "traded":
                                r["return_on_premium"] = r["pnl_fee_0.09"] / (MULT * cost + FEES[0])
                    rows.append(r)

    def tally(sel):
        v = [x["pnl_fee_0.09"] for x in sel]
        return {"trades": len(v), "wins": sum(1 for x in v if x > 0), "fired": sum(1 for x in sel if x.get("exit_minute")),
                "total_usd": round(sum(v), 2) if v else None, "mean_usd": round(sum(v) / len(v), 2) if v else None}

    tallies = {}
    for name, _ in sk.FORWARD_SIGNALS:
        t = {}
        for o in OFFSETS:
            for rule in RULES:
                sel = [r for r in rows if r["signal_name"] == name and r["offset"] == sk.label(o) and r["rule"] == rule
                       and r["status"] == "traded" and not r["provisional"]]
                t[f"{sk.label(o)}|{rule}"] = tally(sel)
        tallies[name] = t
    return {"rows": rows, "tallies": tallies, "directions": directions, "official_close_conflicts": conflicts,
            "forward_days": sorted({r["date"] for r in cfo.read_log()})}


def check_part1_hold(p1: dict, ladder_csv: Path) -> dict:
    """Rule H on forward days must equal the strike ladder's exit A rows (same day, signal, offset)."""
    if not Path(ladder_csv).exists():
        return {"checked": 0, "note": "strike ladder forward log not found"}
    with open(ladder_csv, newline="") as fh:
        ref = {(r["date"], r["signal_name"], r["offset"]): r for r in csv.DictReader(fh)}
    n = 0
    for r in p1["rows"]:
        if r["rule"] != "H" or r["status"] != "traded" or r["provisional"]:
            continue
        x = ref.get((r["date"], r["signal_name"], r["offset"]))
        if x is None or x["status"] != "traded" or not x["pnl_a_fee_0.09"]:
            raise SystemExit(f"part 1 self-check: no strike-ladder exit A row for {r['date']} {r['signal_name']} {r['offset']}")
        if abs(float(x["pnl_a_fee_0.09"]) - r["pnl_fee_0.09"]) > SELF_CHECK_TOL_USD:
            raise SystemExit(f"part 1 self-check failed on {r['date']} {r['signal_name']} {r['offset']}")
        n += 1
    return {"checked": n}


# ------------------------------------------------------------------------------------------------
# rendering
# ------------------------------------------------------------------------------------------------
fm = sk.fm


def render_md(res: dict) -> str:
    p1, p2 = res["part1"], res["part2"]
    V = p2["variants"]
    L = []
    w = L.append
    w("# Early exits vs holding to the close for the 15:50 strong-body signal")
    w("")
    w(f"Pre-registration `preregistration/spx_candle_exit_rules.md` (SHA-256 `{res['prereg_sha256'][:16]}…`). "
      "Rebuilt by `backtests/spx_candle_exits/exits.py`. Descriptive, with one pre-stated criterion. "
      "**Research, not a trading recommendation.**")
    w("")
    w("Rules watch the SPX one-minute closes 15:51-15:58; when one fires, the option is sold at the next minute's "
      "open (a one-minute delay). A rule that never fires holds to settlement (rule H).")
    w("")
    w("| Rule | Exits when |")
    w("|---|---|")
    for r in RULES:
        w(f"| {r} | {RULE_TEXT[r]} |")
    w("")
    w("## The criterion (ITM10, variant (a), $0.09 fee)")
    w("")
    w(f"Better than holding only if mean d (rule minus hold) > 0 with Newey-West t > {BONF_T}, and mean d > 0 in "
      "variants (b) and (c) too.")
    w("")
    w("| Rule | Mean d vs hold (a) | t | d > 0 in (b) | d > 0 in (c) | Verdict |")
    w("|---|---|---|---|---|---|")
    for rule, c in p2["criterion"].items():
        w(f"| {rule} | {fm(c['mean_d_a'], sign=True)} | {fm(c['t_d_a'])} | "
          f"{'yes' if c['positive_in']['b_constant_vol'] else 'no'} | "
          f"{'yes' if c['positive_in']['c_realized_move_fair'] else 'no'} | {c['verdict']} |")
    w("")
    w(f"## Modelled 2021-2026 ({p2['n_trades']} strong-body days, {p2['first']} .. {p2['last']}), a model, not observed P&L")
    w("")
    for o in OFFSETS:
        lab = sk.label(o)
        w(f"### {lab}, variant (a) calibrated{' (headline)' if o == HEADLINE_OFFSET else ''}")
        w("")
        w("| Rule | Fired | Mean P&L ($0.09) | t | Mean P&L ($0.74) | Profitable | Median | 5th pct | Worst | "
          "Return on premium | d vs hold | t (d) |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for rule, s in V["a_calibrated"][lab].items():
            w(f"| {rule} | {fm(s['share_fired'], pct=True)} | {fm(s['mean_pnl_fee_0.09'], sign=True)} | {fm(s['nw_t'])} | "
              f"{fm(s['mean_pnl_fee_0.74'], sign=True)} | {fm(s['share_pnl_positive'], pct=True)} | "
              f"{fm(s['median_pnl'], sign=True)} | {fm(s['p5_pnl'], sign=True)} | {fm(s['worst_pnl'], sign=True)} | "
              f"{fm(s['mean_return_on_premium'], sign=True, pct=True)} | "
              f"{'—' if rule == 'H' else fm(s['diff_vs_hold_mean'], sign=True)} | {fm(s['diff_vs_hold_nw_t'])} |")
        w("")
    w("### Mean P&L per contract ($0.09) in every variant")
    w("")
    for o in OFFSETS:
        lab = sk.label(o)
        w(f"**{lab}**")
        w("")
        w("| Variant | " + " | ".join(RULES) + " |")
        w("|---|" + "---|" * len(RULES))
        for v in VARIANTS:
            w(f"| {v} | " + " | ".join(fm(V[v][lab][r]["mean_pnl_fee_0.09"], 0, sign=True) for r in RULES) + " |")
        w("")
    w("### Subperiods, variant (a), mean P&L per contract ($0.09)")
    w("")
    w("| Period | Strike | " + " | ".join(RULES) + " |")
    w("|---|---|" + "---|" * len(RULES))
    for pname, by in p2["periods_a"].items():
        for o in OFFSETS:
            lab = sk.label(o)
            w(f"| {pname} (n={by[lab]['H']['n']}) | {lab} | " +
              " | ".join(fm(by[lab][r]["mean_pnl_fee_0.09"], 0, sign=True) for r in RULES) + " |")
    w("")
    w("### Self-check")
    w("")
    worst = max(abs(c["diff"]) for c in p2["self_check"])
    w(f"Rule H reproduces the strike ladder's mean P&L at ITM10, ITM20 and ATM in all six variants (largest "
      f"difference ${worst:.6f}). Part 1's rule H matches the strike ladder's exit A on "
      f"{res['part1_self_check']['checked']} forward rows. Index closes missing in D1 among the checked minutes: "
      f"{p2['n_missing_index_closes']}.")
    w("")
    w("## Real prices on forward days (a handful of days; supports no conclusion)")
    w("")
    for name, _ in sk.FORWARD_SIGNALS:
        t = p1["tallies"][name]
        w(f"**{name}{' (headline)' if name == sk.HEADLINE else ''}**: total P&L ($0.09), wins / trades, early exits taken")
        w("")
        w("| Strike | " + " | ".join(RULES) + " |")
        w("|---|" + "---|" * len(RULES))
        for o in OFFSETS:
            lab = sk.label(o)
            cells = []
            for r in RULES:
                x = t[f"{lab}|{r}"]
                cells.append("—" if not x["trades"] else
                             f"{fm(x['total_usd'], 0, sign=True)} ({x['wins']}/{x['trades']}, {x['fired']} early)")
            w(f"| {lab} | " + " | ".join(cells) + " |")
        w("")
    w("Per-day rows: `data/spx_1549/forward/exits_forward_log.csv`.")
    w("")
    hl = [r for r in p1["rows"] if r["signal_name"] == sk.HEADLINE and r["offset"] == "ITM10"]
    days = sorted({r["date"] for r in hl})
    if days:
        w("ITM10, headline signal, P&L by day ($0.09; `@HH:MM` = sold at that minute's open):")
        w("")
        w("| Date | Side | " + " | ".join(RULES) + " |")
        w("|---|---|" + "---|" * len(RULES))
        for dday in days:
            by = {r["rule"]: r for r in hl if r["date"] == dday}
            side = by["H"]["kind"]
            cells = []
            for r in RULES:
                x = by[r]
                if x["status"] != "traded":
                    cells.append(x["status"].replace("_", " "))
                else:
                    cells.append(fm(x["pnl_fee_0.09"], 0, sign=True) + (f" @{x['exit_minute']}" if x.get("exit_minute") else "")
                                 + (" (provisional)" if x["provisional"] else ""))
            w(f"| {dday} | {side} | " + " | ".join(cells) + " |")
        w("")
    w("## Notes on reading the plan (disclosed)")
    w("")
    for note in res["notes"]:
        w(f"- {note}")
    w("")
    w("## Caveats")
    w("")
    w("- Part 1 has only a handful of days and supports no conclusion. Part 2 is a model, not observed P&L.")
    w("- The model prices an early exit with the entry's volatility and the entry strike's skew factor, a $0.10 "
      "half-spread and a one-minute delay. Real exits in a fast move can be worse: wider spreads, slippage, and "
      "quotes that move during the minute.")
    w("- The index path is a CFD (Dukascopy US500) to 15:59, standing in for SPX and its settlement, as in the "
      "strike ladder.")
    w("- Nothing here is a trading recommendation.")
    return "\n".join(L) + "\n"


NOTES = [
    "Part 2 path: checks use the D1 closes of the bars beginning 15:51..15:58 and the sale uses the D1 open of the "
    "next bar (15:52..15:59), as the plan says. D1 bars are the CFD, not SPX.",
    "Part 1: a forward day whose official close is not yet published (provisional) is left out of every total, for "
    "every rule, even when the rule exited early and the settlement does not matter. This keeps each rule's set of "
    "days identical to rule H's, as in the strike ladder.",
    "Part 1 uses both forward signals, as the strike ladder did; F2 is the headline. Index bars come from the "
    "Robinhood SPX one-minute bars (live_*/spx_1m.json, else the d2 chunk files), real bars only.",
    "Part 1 sale price: the contract's 15:52..15:59 one-minute open with gap-fill bars discarded; an open of 0 is "
    "allowed (the plan dropped 'above 0' and floors proceeds at 0).",
    "Return on premium and the share profitable use the $0.09 fee, as in the strike ladder.",
]


def csv_value(v):
    if isinstance(v, bool):
        return str(v)
    return sk.csv_value(v)


def write_outputs(res: dict, write_atomic, out_csv: Path = OUT_CSV, out_json: Path = OUT_JSON,
                  out_md: Path = OUT_MD) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in res["part1"]["rows"]:
        w.writerow({k: csv_value(r.get(k)) for k in COLUMNS})
    write_atomic(out_csv, buf.getvalue())
    out = sk.jsonable(res)
    out["part1"] = {k: v for k, v in out["part1"].items() if k != "rows"}
    write_atomic(out_json, json.dumps(out, indent=1, allow_nan=False) + "\n")
    write_atomic(out_md, render_md(res))


def run() -> dict:
    prereg_sha = sk.check_gate(PREREG, LEDGER)
    scan = load_module("spx_candle_scan_ro", SCAN_PY)
    cfo = load_module("candle_1550_options_forward_ro", OPTIONS_PY)
    P = scan.load_panel(*sk.HOLDOUT)
    T = sk.strong_body_trades(scan, P)
    C, O = d1_paths(scan, P, T)
    cal = load_calibration()
    hc = sk.holdout_constants()
    p2 = part2(scan, T, C, O, cal, hc)
    p1 = part1(cfo, hc["level"])
    res = {"what": "Early exits vs holding for the 15:50 strong-body signal (spx_candle_exit_rules.md)",
           "prereg_sha256": prereg_sha, "strike_ladder_prereg_sha256": cal["strike_ladder_sha256"],
           "offsets": [sk.label(o) for o in OFFSETS], "rules": RULE_TEXT, "half_spread": HALF_SPREAD, "fees": FEES,
           "calibration_used": {"k_d1": cal["k_d1"], "sigma_bps_median_c1": cal["sigma_bps_median_c1"],
                                "f": {sk.label(o): v for o, v in cal["f"].items()}},
           "part2": p2, "part1": p1, "part1_self_check": check_part1_hold(p1, sk.OUT_CSV), "notes": NOTES}
    write_outputs(res, cfo.write_atomic)
    return res


# ------------------------------------------------------------------------------------------------
# self-test on synthetic data (reads no real data)
# ------------------------------------------------------------------------------------------------
def selftest() -> None:
    nan = np.nan
    # first-fire logic
    m = np.array([[-1, -3.5, -6, 0, 0, 0, 0, 0],
                  [2, 11, -6, 0, 0, 0, 0, 0],
                  [nan, nan, -9, 0, 0, 0, 0, 0],
                  [0, 0, 0, 0, 0, 0, 0, 4.99]])
    assert list(first_fire(m, 3.0, None)) == [1, 2, 2, -1]
    assert list(first_fire(m, 5.0, 10.0)) == [2, 1, 2, -1]
    assert list(first_fire(m, None, 5.0)) == [-1, 1, -1, -1]
    assert list(first_fire(m, 8.0, None)) == [-1, -1, 2, -1]
    assert int(n_remaining(0)) == 8 and int(n_remaining(7)) == 1
    assert CHECKS[0] == "15:51" and CHECKS[-1] == "15:58" and EXITS[0] == "15:52" and EXITS[-1] == "15:59"

    # one hand-computed early exit: up trade at S = L = 7700, ITM10 call 7690, S3 fires at the 15:53 close (j = 2)
    L, f_o, h, sig9 = 7700.0, 1.02, 0.10, 9.0
    T = {"S": np.array([7700.0]), "X": np.array([7690.0]), "d": np.array([1]), "rv": np.array([1e-4]),
         "dates": np.array(["2022-01-03"])}
    C = np.array([[7699.0, 7698.0, 7696.5, 7695.0, 7694.0, 7693.0, 7692.0, 7691.0]])
    O = np.array([[7699.5, 7696.0, 7696.2, 7695.0, 7694.0, 7693.0, 7692.0, 7691.0]])
    res = model_exits(T, C, O, L, sig9, f_o, h, 10)
    cost = f_o * sk.bachelier(True, 7700.0, 7690.0, sig9) + h
    ex = f_o * sk.bachelier(True, 7696.2, 7690.0, sig9 * math.sqrt(6 / 9))
    assert res["S3"]["j"][0] == 2 and res["S3"]["fired"][0]
    assert abs(res["S3"]["pnl_0.09"][0] - (100 * (ex - h - cost) - 0.18)) < 1e-9
    assert abs(res["H"]["pnl_0.09"][0] - (100 * (0.0 - cost) - 0.09)) < 1e-9        # settles at 7690: worthless
    assert not res["T5"]["fired"][0] and abs(res["T5"]["pnl_0.74"][0] - (100 * (0.0 - cost) - 0.74)) < 1e-9
    # the proceeds floor: OTM20 call 7720 after a drop sells for less than the half-spread -> proceeds 0
    r20 = model_exits(T, C, O, L, sig9, 1.0, h, -20)
    assert r20["S3"]["fired"][0] and r20["S3"]["exit_price"][0] < h
    assert abs(r20["S3"]["pnl_0.09"][0] - (100 * (0.0 - r20["cost"][0]) - 0.18)) < 1e-9

    # rule H equals the strike ladder's model for the same trades, every offset
    rng = np.random.default_rng(7)
    n = 3000
    d = rng.choice([-1, 1], n)
    S = rng.uniform(3500, 7800, n)
    steps = rng.normal(0, 3.0, (n, 9)).cumsum(axis=1) * (S / 7709.58)[:, None]
    path = S[:, None] + steps
    C = path[:, :8]
    O = path[:, :8] + rng.normal(0, 0.3, (n, 8))
    X = path[:, 8]
    T = {"S": S, "X": X, "d": d, "rv": rng.uniform(5e-5, 2e-4, n), "dates": np.array(["2022-03-01"] * n)}
    f = {o: 1.0 + 0.01 * abs(o) for o in sk.OFFSETS}
    sig = 0.9 * T["rv"] * 3.0 * 7709.58
    lad = sk.model_ladder(T, 7709.58, sig, f)
    for o in OFFSETS:
        mine = model_exits(T, C, O, 7709.58, sig, f[o], HALF_SPREAD, o)
        assert np.allclose(mine["H"]["pnl_0.09"], lad[o]["pnl_0.09"]) and np.allclose(mine["H"]["pnl_0.74"], lad[o]["pnl_0.74"])
        assert np.allclose(mine["H"]["ret"], lad[o]["ret"])
        # an early exit pays two fees: the 0.74 - 0.09 gap is 2 x 0.65 when fired, 0.65 when held
        g = mine["S3"]["pnl_0.09"] - mine["S3"]["pnl_0.74"]
        assert np.allclose(g[mine["S3"]["fired"]], 1.30) and np.allclose(g[~mine["S3"]["fired"]], 0.65)
    # zero-cost martingale sanity: f = 1, h = 0, fees 0 aside, a stop on a driftless path keeps the mean near hold
    # (not asserted tightly; only that the code runs on every rule and the stats are finite)
    scan = load_module("spx_candle_scan_ro", SCAN_PY)
    st = rule_stats(model_exits(T, C, O, 7709.58, sig, 1.0, HALF_SPREAD, 10), scan)
    assert set(st) == set(RULES) and st["H"]["diff_vs_hold_mean"] == 0.0 and st["H"]["diff_vs_hold_nw_t"] is None
    assert all(math.isfinite(st[r]["mean_pnl_fee_0.09"]) for r in RULES)

    # the gate refuses without the file or without the ledger line
    with tempfile.TemporaryDirectory() as tmp:
        pre, led = Path(tmp) / "x.md", Path(tmp) / "LEDGER.md"
        led.write_text("nothing\n")
        for setup in ("missing", "unlisted"):
            if setup == "unlisted":
                pre.write_text("plan\n")
            try:
                sk.check_gate(pre, led)
                raise AssertionError("gate did not refuse")
            except SystemExit:
                pass
    selftest_end_to_end(scan, T, C, O)
    print("selftest: all checks passed")


def selftest_end_to_end(scan, T, C, O) -> None:
    """Part 1 with a fake options module and fake index bars, Part 2 with injected data, then the outputs."""
    import types
    real = load_module("candle_1550_options_forward_ro", OPTIONS_PY)
    L = 7709.58
    S1, settle = 7701.3, 7712.0
    # index path for 2026-10-22 (up signal): dips 4 points by 15:53, then rallies to +11 by 15:57
    idx = {"15:51": (S1, S1 - 1.0), "15:52": (S1 - 1.0, S1 - 2.0), "15:53": (S1 - 2.0, S1 - 4.0),
           "15:54": (S1 - 4.0, S1 + 1.0), "15:55": (S1 + 1.0, S1 + 6.0), "15:56": (S1 + 6.0, S1 + 8.0),
           "15:57": (S1 + 8.0, S1 + 11.0), "15:58": (S1 + 11.0, S1 + 10.0)}

    def opt_bars(kind, K):
        bars = {"15:51": {"open_price": f"{max(sk.bachelier(kind == 'call', S1, K, 6.0), 0.05):.2f}"}}
        for hm in EXITS:
            bars[hm] = {"open_price": f"{max(sk.intrinsic(kind == 'call', K, S1 + 3.0), 0.0) + 0.5:.2f}"}
        return bars

    opts = {(kind, float(K)): opt_bars(kind, K) for kind in ("call", "put") for K in np.arange(7675.0, 7731.0, 5.0)}
    del opts[("call", 7680.0)]                     # up trade ITM20 -> strike_not_collected
    del opts[("call", 7690.0)]["15:54"]            # up ITM10, S3 fires at the 15:53 close -> exit_bar_missing
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
        price=real.price, intrinsic=real.intrinsic)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for r in log:
            (tmp / f"live_{r['date']}").mkdir()
        p1 = part1(fake, L, spx_root=tmp, spx_bars=lambda day: idx)
        rows = p1["rows"]
        assert len(rows) == 4 * len(OFFSETS) * len(RULES), len(rows)   # 22 F2, 22 F1, 23 F2, 26 F2
        st = {(r["date"], r["signal_name"][:2], r["offset"], r["rule"]): r for r in rows}
        assert st[("2026-10-22", "F2", "ITM20", "H")]["status"] == "strike_not_collected"
        assert st[("2026-10-22", "F2", "ITM10", "S3")]["status"] == "exit_bar_missing"
        assert st[("2026-10-22", "F2", "ITM10", "S3")]["fired_at_close"] == "15:53"
        a = st[("2026-10-22", "F2", "ATM", "T5")]                      # m = 6 x L/S at the 15:55 close
        assert a["status"] == "traded" and a["fired_at_close"] == "15:55" and a["exit_minute"] == "15:56"
        e = float(f"{max(sk.bachelier(True, S1, 7700.0, 6.0), 0.05):.2f}")
        xo = float(f"{max(S1 + 3.0 - 7700.0, 0.0) + 0.5:.2f}")
        assert abs(a["pnl_fee_0.09"] - (100 * (xo - 0.10 - e - 0.10) - 0.18)) < 1e-9
        hld = st[("2026-10-22", "F2", "ATM", "H")]
        assert abs(hld["pnl_fee_0.09"] - (100 * (12.0 - e - 0.10) - 0.09)) < 1e-9
        b = st[("2026-10-22", "F2", "ATM", "B5_10")]                   # +11 x L/S at 15:57 hits the target first
        assert b["fired_at_close"] == "15:57" and b["exit_minute"] == "15:58"
        assert st[("2026-10-22", "F2", "ATM", "S8")]["status"] == "traded" and not st[("2026-10-22", "F2", "ATM", "S8")].get("exit_minute")
        assert st[("2026-10-22", "F1", "ITM10", "H")]["kind"] == "put" and st[("2026-10-22", "F1", "ITM10", "H")]["strike"] == 7710.0
        assert st[("2026-10-23", "F2", "ATM", "H")]["status"] == "no_minute_option_bars"
        assert st[("2026-10-26", "F2", "ATM", "T5")]["provisional"] is True
        t = p1["tallies"]["F2_1m_1550_strong_body"]
        assert t["ATM|H"]["trades"] == 1 and t["ITM20|H"]["trades"] == 0 and t["ATM|T5"]["fired"] == 1

        # Part 2 with injected trades and calibration
        n = len(T["S"])
        T = dict(T, dates=np.array(["2022-03-01"] * (n // 2) + ["2024-03-01"] * (n - n // 2)))
        hc = {"level": L, "mean_abs_move": 8.6}
        cal = {"k_d1": 0.9, "sigma_bps_median_c1": 8.0, "f": {o: 1.0 + 0.01 * abs(o) for o in OFFSETS},
               "strike_ladder_part2": {}, "strike_ladder_sha256": "selftest"}
        p2 = part2(scan, T, C, O, cal, hc, self_check=False)
        assert set(p2["variants"]) == set(VARIANTS) and set(p2["criterion"]) == set(EARLY)
        for o in OFFSETS:
            lo = p2["variants"]["a_half_spread_0.05"][sk.label(o)]["H"]["mean_pnl_fee_0.09"]
            hi = p2["variants"]["a_half_spread_0.20"][sk.label(o)]["H"]["mean_pnl_fee_0.09"]
            assert abs((lo - hi) - 15.0) < 1e-9
        assert sum(p2["periods_a"][k]["ITM10"]["H"]["n"] for k in p2["periods_a"]) == n
        res = {"what": "selftest", "prereg_sha256": "selftest" * 4, "offsets": [sk.label(o) for o in OFFSETS],
               "rules": RULE_TEXT, "half_spread": HALF_SPREAD, "fees": FEES, "part2": dict(p2, self_check=[
                   {"variant": "x", "offset": "ITM10", "hold_mean": 0.0, "strike_ladder_mean": 0.0, "diff": 0.0}]),
               "part1": p1, "part1_self_check": {"checked": 0}, "notes": NOTES}
        write_outputs(res, real.write_atomic, tmp / "o.csv", tmp / "o.json", tmp / "o.md")
        with open(tmp / "o.csv", newline="") as fh:
            assert len(list(csv.DictReader(fh))) == len(rows)
        back = json.loads((tmp / "o.json").read_text())
        assert "rows" not in back["part1"] and back["part2"]["n_trades"] == n
        md = (tmp / "o.md").read_text()
        assert "## The criterion" in md and "| B5_10 |" in md and "exit bar missing" in md


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        res = run()
        V = res["part2"]["variants"]["a_calibrated"]["ITM10"]
        print("model (a), ITM10:")
        for rule, s in V.items():
            print(f"  {rule:6s} fired {s['share_fired']:5.1%}  mean {s['mean_pnl_fee_0.09']:+8.2f}  t "
                  f"{s['nw_t'] if s['nw_t'] is None else round(s['nw_t'], 2)}  d vs hold "
                  f"{s['diff_vs_hold_mean']:+8.2f}  t(d) {s['diff_vs_hold_nw_t'] if s['diff_vs_hold_nw_t'] is None else round(s['diff_vs_hold_nw_t'], 2)}"
                  f"  worst {s['worst_pnl']:+9.2f}")
        for rule, c in res["part2"]["criterion"].items():
            print(f"  criterion {rule}: {c['verdict']}")
        print(f"wrote {OUT_MD}, {OUT_JSON}, {OUT_CSV}")
    else:
        raise SystemExit("usage: exits.py selftest | run")
