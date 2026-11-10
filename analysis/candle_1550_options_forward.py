#!/usr/bin/env python
"""Real 0DTE option outcomes of the 15:50 candle signals, forward (descriptive only).

Pre-registration: preregistration/spx_candle_forward_options.md (an addendum to spx_close_candle_scan.md),
hashed in preregistration/LEDGER.md before any option P&L was computed; this script refuses to run if the
file's SHA-256 is not in the ledger. For every FORWARD SPX_robinhood session that the forward log
(analysis/candle_1550_forward.py) marked `ok`, and for each of its 15:51 signals, it buys the 0DTE SPXW call
(signal +1) or put (signal -1) at the strike nearest the SPX 15:51 bar open, at that contract's 15:51 bar open
plus a $0.10 half-spread, and values it two ways:

  * exit A (primary): held to expiry, worth its intrinsic value at the official SPX close (a validated daily
    bar from the newest live_*/spx_daily.json that has one); until it is published the 15:59 bar close is used
    and the row is marked provisional and left out of the exit-A totals. No fee at expiry. (The backtest's
    model scored |move| to the 15:59 index close with an idealised strike equal to the entry price.)
  * exit B (sensitivity): sold at the contract's 15:59 bar close minus the $0.10 half-spread; fee both sides.

It also compares the market ATM straddle at 15:51 with the backtest's assumed option price (half the
realized-move-fair straddle, the registered constants) on every day with minute option bars, signal or not.

Run (after analysis/candle_1550_forward.py; rebuilds every output from scratch, byte-identical on re-run):

    PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B analysis/candle_1550_options_forward.py

Inputs (local files only, read-only): data/spx_1549/forward/candle_1550_log.csv, data/spx_1549/live_*/
{ids.json, options*.json, spx_1m.json, spx_daily.json}, backtests/spx_candle_scan/{candidates.json,
candidates.sha256, holdout.json}. Option bars flagged interpolated=true are gap-fill and are discarded.

Outputs:
  data/spx_1549/forward/options_log.csv         one row per forward day per signal (statuses included)
  data/spx_1549/forward/options_summary.json    tallies, the model check and the decisions
  backtests/spx_candle_scan/FORWARD_OPTIONS.md  plain-English page

Nothing here is trading advice; the log is descriptive, as pre-registered.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------------------------------------
# paths and constants
# ------------------------------------------------------------------------------------------------
ROOT = Path("/Users/kv15/trading")
SPX_ROOT = ROOT / "data" / "spx_1549"
OUT_DIR = SPX_ROOT / "forward"
LOG_CSV = OUT_DIR / "candle_1550_log.csv"
OUT_CSV_NAME = "options_log.csv"
OUT_JSON_NAME = "options_summary.json"
SCAN_DIR = ROOT / "backtests" / "spx_candle_scan"
OUT_MD = SCAN_DIR / "FORWARD_OPTIONS.md"
HOLDOUT_JSON = SCAN_DIR / "holdout.json"
PREREG = ROOT / "preregistration" / "spx_candle_forward_options.md"
LEDGER = ROOT / "preregistration" / "LEDGER.md"
FORWARD_PY = ROOT / "analysis" / "candle_1550_forward.py"

ET = ZoneInfo("America/New_York")
FORWARD_START = "2026-10-21"
SOURCE = "SPX_robinhood"
SPX_ID = "432fbbb8-b82c-454a-852d-eb85382c7066"
HALF_SPREAD = 0.10          # $ per option = index points, as scan.py
FEES = (0.09, 0.74)         # $ per contract per side, as scan.py
MULT = 100.0
STRIKE_STEP = 5.0
Z95 = 1.959963984540054
LEVEL = 7709.58             # holdout.json at_last_level units: "index points at level 7709.58"
SIGNALS = (("F2_1m_1550_strong_body", "sb"), ("F1_1m_15:50", "f1"), ("P3_reference", "p3"))
HEADLINE = "F2_1m_1550_strong_body"
# The registered model prices (preregistration, "Model check"): half the realized-move-fair straddle, bps of S.
MODEL_HALF_BPS = {"F2_1m_1550_strong_body": 0.5 * 11.154, "F1_1m_15:50": 0.5 * 8.285 / LEVEL * 1e4}
MODEL_SANITY_BPS = 0.0015   # holdout.json must agree with the registered constants to this (it does: 0.0003)
COMPLETE_AFTER = "16:01"    # an index bar beginning at/after this shows the folder's files were fetched after 16:01
CLOSE_CONFLICT_PTS = 0.005  # two daily files whose closes for a date differ by more are reported

LABEL = {"F2_1m_1550_strong_body": "15:50 candle, strong body (headline)",
         "F1_1m_15:50": "15:50 candle direction, any body",
         "P3_reference": "P3 reference (15:50 open -> 15:51 open direction)"}

DECISIONS = [
    "Days, trade rule, exits, costs and the model check are those of preregistration/"
    "spx_candle_forward_options.md; the script refuses to run unless that file's SHA-256 is in LEDGER.md.",
    "Signals, the SPX 15:51 open and the 15:59 close are read from candle_1550_log.csv as written by "
    "candle_1550_forward.py (its checks and day filters apply); directions are the frozen ones in "
    "candidates.json, read through that script's frozen_directions() (which checks candidates.sha256). Two "
    "log rows for the same date stop the run.",
    "Model prices are the registered constants (0.5 x 11.154 bps for the strong body; 0.5 x 8.285 / 7709.58 "
    "x 1e4 bps for any body); holdout.json is only checked to agree with them within 0.0015 bps.",
    "Every live_<date>/options*.json file is read; each result is classified by its own `interval` field. "
    "Only interval 'minute' results are priced; a day whose files hold only other intervals is "
    "`no_minute_option_bars`, a day with no option file `no_option_files`. Every contract's OCC symbol must "
    "match its date, type and strike from ids.json, or the run stops. The same contract and minute in two "
    "files: identical bars are kept once, different bars stop the run.",
    "Prices must be finite numbers; the entry must be above 0, the 15:59 exit may be 0.",
    "Exit B needs evidence that the 15:59 option bar had finished when the files were fetched: the folder's "
    "spx_1m.json holds a real index bar beginning at 16:01 ET or later (the collector fetches the index file "
    "before the option files). Without it exit B is `no_completion_evidence`.",
    "Official close: a daily bar whose result is the SPX index (instrument id 432fbbb8-...), interval 'day', "
    "not interpolated, with a finite close above 0. 'Newest' = the live_<date> folder with the latest date; "
    "if two files disagree on a date's close by more than 0.005 points the disagreement is listed.",
    "P&L is computed and classified (win = P&L > 0) at full precision; only the outputs are rounded.",
    "The model P&L uses the forward log's own |move| (15:51 open to 15:59 close) and right/wrong, as scan.py "
    "does; it is tallied on the same days as each exit (A: finalized trades; B: trades with an exit B).",
    "Bars carry no bid/ask and Robinhood does not say whether they are trades or marks; the $0.10 "
    "half-spread is the backtest's assumption, not an observed spread.",
    "Audit of 2026-10-30: the rules above on finite and "
    "zero prices, duplicates, completion evidence, daily-bar validation, the registered model constants, "
    "full-precision tallies, file classification and the reporting were added or tightened after it. None "
    "changed a real-option P&L or total; the model P&L moved by at most one cent per row.",
]


# ------------------------------------------------------------------------------------------------
# small helpers
# ------------------------------------------------------------------------------------------------
def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def wilson(k: int, n: int, z: float = Z95):
    if n <= 0:
        return None
    ph = k / n
    den = 1.0 + z * z / n
    centre = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return [centre - half, centre + half]


def strike_for(s: float) -> float:
    """scan.py's rounding: floor(S / 5 + 0.5) x 5."""
    return math.floor(s / STRIKE_STEP + 0.5) * STRIKE_STEP


def intrinsic(kind: str, strike: float, settle: float) -> float:
    return max(0.0, settle - strike) if kind == "call" else max(0.0, strike - settle)


def et_hhmm(begins_at: str) -> tuple[str, str]:
    t = datetime.fromisoformat(begins_at.replace("Z", "+00:00")).astimezone(ET)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def occ_expected(day: str, kind: str, strike: float) -> str:
    return f"SPXW{day[2:4]}{day[5:7]}{day[8:10]}{'C' if kind == 'call' else 'P'}{round(strike * 1000):08d}"


def finite(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def rnd(x, nd=2):
    return None if x is None else round(x, nd)


def check_prereg(prereg: Path = PREREG, ledger: Path = LEDGER) -> str:
    h = sha256_file(prereg)
    if h not in Path(ledger).read_text():
        raise SystemExit(f"refusing to run: SHA-256 of {prereg.name} ({h}) is not in {ledger}")
    return h


def load_forward_module():
    spec = importlib.util.spec_from_file_location("candle_1550_forward_ro", FORWARD_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def check_model_constants(holdout_json: Path = HOLDOUT_JSON) -> dict:
    """The registered model prices; holdout.json must agree with them (a guard against a changed holdout)."""
    eco = json.loads(Path(holdout_json).read_text())["economics"]["candidates"]
    for name, half_bps in MODEL_HALF_BPS.items():
        lvl = eco[name]["at_last_level"]
        if f"{LEVEL}" not in lvl["units"]:
            raise SystemExit(f"holdout.json at_last_level units changed: {lvl['units']!r}")
        full_bps = lvl["realized_move_fair_straddle"] / LEVEL * 1e4
        if abs(full_bps - 2 * half_bps) > MODEL_SANITY_BPS:
            raise SystemExit(f"holdout.json model straddle for {name} is {full_bps:.4f} bps, not the registered "
                             f"{2 * half_bps:.4f}")
    return dict(MODEL_HALF_BPS)


# ------------------------------------------------------------------------------------------------
# inputs
# ------------------------------------------------------------------------------------------------
def read_log(log_csv: Path = LOG_CSV) -> list[dict]:
    rows = [r for r in csv.DictReader(io.StringIO(Path(log_csv).read_text()))
            if r["source"] == SOURCE and r["date"] >= FORWARD_START and r["status"] == "ok"]
    dates = [r["date"] for r in rows]
    if len(dates) != len(set(dates)):
        raise SystemExit(f"{log_csv}: more than one {SOURCE} row for a date")
    return sorted(rows, key=lambda r: r["date"])


def load_day_options(folder: Path, day: str) -> tuple[dict | None, str]:
    """({(kind, strike): {HH:MM: bar}} from the day's minute results or None, availability).

    availability: 'minute', 'no_minute_option_bars' (files exist, none holds minute results) or 'no_option_files'.
    Raises on an id or OCC-symbol mismatch, or on two different bars for the same contract and minute.
    """
    files = sorted(Path(folder).glob("options*.json"))
    if not files:
        return None, "no_option_files"
    ids = json.loads((Path(folder) / "ids.json").read_text())
    by_id = {v: (t, float(k)) for k, legs in ids.items() for t, v in legs.items()}
    out: dict = {}
    seen_minute = False
    for p in files:
        for res in json.loads(p.read_text())["data"]["results"]:
            iid = res["instrument_id"]
            if iid not in by_id:
                raise SystemExit(f"{p}: contract {iid} is not in ids.json")
            kind, strike = by_id[iid]
            occ = res.get("occ_symbol", "").replace(" ", "")
            if occ != occ_expected(day, kind, strike):
                raise SystemExit(f"{p}: {iid} has OCC symbol {occ!r}, ids.json says {kind} {strike} {day}")
            if res.get("interval") != "minute":
                continue
            seen_minute = True
            bars = out.setdefault((kind, strike), {})
            for b in res["bars"]:
                if b.get("interpolated"):
                    continue
                d, hm = et_hhmm(b["begins_at"])
                if d != day:
                    continue
                keep = {k: b.get(k) for k in ("open_price", "high_price", "low_price", "close_price")}
                if hm in bars and bars[hm][0] != keep:
                    raise SystemExit(f"{p}: {occ} {hm} differs from the same bar in {bars[hm][1]}")
                bars.setdefault(hm, (keep, p.name))
    if not seen_minute:
        return None, "no_minute_option_bars"
    return {key: {hm: v[0] for hm, v in bars.items()} for key, bars in out.items()}, "minute"


def completion_evidence(folder: Path, day: str) -> bool:
    """True if the folder's index file holds a real bar beginning at/after 16:01 ET on `day`."""
    p = Path(folder) / "spx_1m.json"
    if not p.exists():
        return False
    try:
        bars = json.loads(p.read_text())["data"]["results"][0]["bars"]
    except (ValueError, KeyError, IndexError):
        return False
    for b in bars:
        if b.get("interpolated"):
            continue
        d, hm = et_hhmm(b["begins_at"])
        if d == day and hm >= COMPLETE_AFTER:
            return True
    return False


def official_closes(spx_root: Path = SPX_ROOT) -> tuple[dict, list]:
    """({date: (close, source file)} from the newest valid live_*/spx_daily.json holding each date, conflicts)."""
    found: dict = {}
    for p in sorted(Path(spx_root).glob("live_*/spx_daily.json")):     # folder date order: oldest first
        try:
            results = json.loads(p.read_text())["data"]["results"]
        except (ValueError, KeyError):
            continue
        for res in results:
            if res.get("instrument_id") != SPX_ID or res.get("interval") != "day":
                continue
            for b in res.get("bars", []):
                close = finite(b.get("close_value"))
                if b.get("interpolated") or close is None or close <= 0:
                    continue
                found.setdefault(b["begins_at"][:10], []).append((close, str(p.relative_to(spx_root))))
    closes = {d: v[-1] for d, v in found.items()}
    conflicts = [{"date": d, "values": v} for d, v in sorted(found.items())
                 if max(c for c, _ in v) - min(c for c, _ in v) > CLOSE_CONFLICT_PTS]
    return closes, conflicts


def price(bars: dict | None, hm: str, field: str, *, allow_zero: bool) -> float | None:
    b = bars.get(hm) if bars else None
    v = finite(b[field]) if b is not None else None
    if v is None or v < 0 or (v == 0 and not allow_zero):
        return None
    return v


# ------------------------------------------------------------------------------------------------
# per-day rows
# ------------------------------------------------------------------------------------------------
def day_rows(row: dict, opts: dict | None, availability: str, complete: bool, directions: dict, model_bps: dict,
             closes: dict) -> tuple[list, dict]:
    day = row["date"]
    S = float(row["entry_1551_open"])
    S_exit = float(row["exit_1559_close"])
    K = strike_for(S)
    settle, settle_src = closes.get(day, (None, None))
    provisional = settle is None
    settle_used = S_exit if provisional else settle
    move_pts = S_exit - S

    check = {"date": day, "S_1551_open": S, "strike": K, "availability": availability}
    if opts is not None:
        c = price(opts.get(("call", K)), "15:51", "open_price", allow_zero=False)
        p = price(opts.get(("put", K)), "15:51", "open_price", allow_zero=False)
        if c is not None and p is not None:
            straddle = c + p
            check.update({"call_1551_open": c, "put_1551_open": p, "straddle_pts": straddle,
                          "straddle_bps": straddle / S * 1e4})
            for name, half_bps in model_bps.items():
                check[f"market_over_model_{name}"] = straddle / (2 * half_bps * S / 1e4)
        else:
            check["availability"] = "atm_bar_missing"

    out = []
    for name, short in SIGNALS:
        s = int(row[f"{short}_signal"]) * directions[name]
        r = {"date": day, "signal_name": name, "signal": s, "S_1551_open": S, "S_1559_close": S_exit,
             "strike": K if s else None, "kind": ("call" if s > 0 else "put") if s else None,
             "settle": settle_used if s else None,
             "settle_source": (settle_src or "provisional_1559_close") if s else None,
             "provisional": provisional if s else None}
        if s == 0:
            r["status"] = "no_signal"
        elif opts is None:
            r["status"] = availability
        elif (r["kind"], K) not in opts:
            r["status"] = "strike_not_collected"
        else:
            bars = opts[(r["kind"], K)]
            E = price(bars, "15:51", "open_price", allow_zero=False)
            if E is None:
                r["status"] = "entry_bar_missing"
            else:
                r["status"] = "traded"
                cost = E + HALF_SPREAD
                val_a = intrinsic(r["kind"], K, settle_used)
                r.update({"entry_open_1551": E, "cost_incl_half_spread": cost, "exit_a_value": val_a})
                for fee in FEES:
                    r[f"pnl_a_fee_{fee:.2f}"] = MULT * (val_a - cost) - fee
                X = price(bars, "15:59", "close_price", allow_zero=True)
                if not complete:
                    r["exit_b_status"] = "no_completion_evidence"
                elif X is None:
                    r["exit_b_status"] = "exit_bar_missing"
                else:
                    r["exit_b_status"] = "ok"
                    r["exit_b_close_1559"] = X
                    for fee in FEES:
                        r[f"pnl_b_fee_{fee:.2f}"] = MULT * (X - HALF_SPREAD - cost) - 2 * fee
        if s and name in model_bps:
            right = move_pts * s > 0
            opt = model_bps[name] * S / 1e4
            r["model_option_price"] = opt
            for fee in FEES:
                r[f"model_pnl_fee_{fee:.2f}"] = MULT * ((abs(move_pts) if right else 0.0) - opt - HALF_SPREAD) - fee
        out.append(r)
    return out, check


COLUMNS = ["date", "signal_name", "signal", "status", "kind", "strike", "S_1551_open", "S_1559_close", "settle",
           "settle_source", "provisional", "entry_open_1551", "cost_incl_half_spread", "exit_a_value",
           "pnl_a_fee_0.09", "pnl_a_fee_0.74", "exit_b_status", "exit_b_close_1559", "pnl_b_fee_0.09",
           "pnl_b_fee_0.74", "model_option_price", "model_pnl_fee_0.09", "model_pnl_fee_0.74"]


def exit_rows(rows: list, name: str, ex: str) -> list:
    """The rows that count for an exit: A = traded and not provisional; B = traded with an exit B."""
    if ex == "a":
        return [r for r in rows if r["signal_name"] == name and r["status"] == "traded" and not r["provisional"]]
    return [r for r in rows if r["signal_name"] == name and r["status"] == "traded" and r.get("exit_b_status") == "ok"]


def tally(vals: list) -> dict:
    wins = sum(v > 0 for v in vals)
    return {"trades": len(vals), "wins": wins, "win_share": wins / len(vals) if vals else None,
            "win_share_wilson95": wilson(wins, len(vals)), "total_usd": rnd(sum(vals)) if vals else None,
            "mean_usd": rnd(sum(vals) / len(vals)) if vals else None}


# ------------------------------------------------------------------------------------------------
# outputs
# ------------------------------------------------------------------------------------------------
def fmt(x, nd=2, sign=False):
    if x is None:
        return "-"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


def pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"


AVAIL_TEXT = {"no_minute_option_bars": "only 10-minute (or other non-minute) option bars saved",
              "no_option_files": "no option file saved", "atm_bar_missing": "a 15:51 call or put bar is missing"}


def render_md(rows: list, checks: list, summary: dict) -> str:
    L = ["# Forward log: real 0DTE option outcomes of the 15:50 candle signals (descriptive only)", "",
         "Rebuilt by `analysis/candle_1550_options_forward.py`; do not edit by hand. Rules: "
         "`preregistration/spx_candle_forward_options.md` (hashed in `LEDGER.md` before any option P&L was "
         "computed; the index results of the first four strong-body days were already known then, so this is a "
         "descriptive record, not an untouched test). It shows what real Robinhood SPXW 0DTE option bars would "
         "have given with the backtest's cost assumptions. It is not a recommendation.", "",
         "## The trade being logged", "",
         "When a signal fires, buy one 0DTE SPXW call (signal up) or put (signal down) at the strike nearest "
         "the SPX 15:51 open, paying that contract's 15:51 one-minute bar open plus $0.10. **Exit A**: hold to "
         "expiry; the option settles at its intrinsic value on the official SPX close. (The backtest's model "
         "instead scored |move| to the 15:59 index close with an idealised strike equal to the entry price.) "
         "**Exit B**: sell at the 15:59 bar close minus $0.10. P&L is per contract (x100), for a $0.09 and a "
         "$0.74 fee per side (no fee at expiry).", "",
         "## Totals so far", "",
         "| Signal | Exit | Trades | Wins ($0.09 / $0.74) | Win share, $0.09 (95% CI) | Total, $0.09 | "
         "Mean, $0.09 | Total, $0.74 | Mean, $0.74 | Backtest model on the same days, mean ($0.09) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for name, _ in SIGNALS:
        t = summary["tallies"][name]
        for ex, lab in (("a", "A: hold to expiry (finalized)"), ("b", "B: sell 15:59")):
            a, b = t[f"exit_{ex}_fee_0.09"], t[f"exit_{ex}_fee_0.74"]
            ci = a["win_share_wilson95"]
            cis = f"{pct(a['win_share'])} ({pct(ci[0])}-{pct(ci[1])})" if ci else "-"
            m = t.get(f"model_exit_{ex}_fee_0.09")
            mtxt = fmt(m["mean_usd"], sign=True) if (m and m["mean_usd"] is not None) else "-"
            L.append(f"| {LABEL[name]} | {lab} | {a['trades']} | {a['wins']} / {b['wins']} | {cis} | "
                     f"{fmt(a['total_usd'], sign=True)} | {fmt(a['mean_usd'], sign=True)} | "
                     f"{fmt(b['total_usd'], sign=True)} | {fmt(b['mean_usd'], sign=True)} | {mtxt} |")
    ta = summary["tallies"][HEADLINE]
    n_a, n_entry = ta["exit_a_fee_0.09"]["trades"], ta["status_counts"].get("traded", 0)
    L += ["", f"The headline signal has **{n_entry} trade(s) with a real entry price, {n_a} of them finalized** "
          "(official close known). That is far too few to say anything about whether it makes money; one big day "
          "dominates a total this small. The model column is scan.py's cost model on exactly the same days "
          "(its idealised option, its cost). Only days with saved one-minute option bars can be priced, so the "
          "sample also depends on which days were collected in time.", ""]
    prov = sorted({r["date"] for r in rows if r["status"] == "traded" and r["provisional"]})
    if prov:
        L += [f"Provisional (official close not saved yet, valued at the 15:59 bar close and left out of the "
              f"exit-A totals): {', '.join(prov)}.", ""]
    if summary["official_close_conflicts"]:
        L += ["Daily files that disagree on an official close (the newest folder's value is used): " + "; ".join(
            f"{c['date']}: " + ", ".join(f"{v:.2f} ({src})" for v, src in c["values"])
            for c in summary["official_close_conflicts"]) + ".", ""]
    L += ["## Every forward day", "",
          "| Date | Signal | Status | Option | Paid (incl. $0.10) | Exit A value | P&L A ($0.09) | "
          "Exit B 15:59 | P&L B ($0.09) | Model P&L ($0.09) |", "|---|---|---|---|---|---|---|---|---|---|"]
    short = {"F2_1m_1550_strong_body": "strong body", "F1_1m_15:50": "direction", "P3_reference": "P3"}
    for r in rows:
        opt = f"{r['kind']} {r['strike']:.0f}" if r.get("kind") else "-"
        b_status = r.get("exit_b_status")
        b_txt = fmt(r.get("exit_b_close_1559")) if b_status in (None, "ok") else b_status
        L.append(f"| {r['date']} | {short[r['signal_name']]} | {r['status']} | {opt} | "
                 f"{fmt(r.get('cost_incl_half_spread'))} | {fmt(r.get('exit_a_value'))}"
                 f"{' (prov.)' if r['provisional'] and r['status'] == 'traded' else ''} | "
                 f"{fmt(r.get('pnl_a_fee_0.09'), sign=True)} | {b_txt} | "
                 f"{fmt(r.get('pnl_b_fee_0.09'), sign=True)} | {fmt(r.get('model_pnl_fee_0.09'), sign=True)} |")
    mc = summary["model_check"]
    L += ["", "## Is the backtest's option price realistic? (every day with minute option bars)", "",
          "The backtest assumed an at-the-money option costs half the realized-move-fair straddle: "
          f"{2 * MODEL_HALF_BPS[HEADLINE]:.3f} bps of SPX for the full straddle with the strong-body value and "
          f"{2 * MODEL_HALF_BPS['F1_1m_15:50']:.3f} bps with the any-body value (2021-2026). Real call + put at the "
          "strike nearest the 15:51 open, from their 15:51 bar opens:", "",
          "| Date | SPX 15:51 | Strike | Call | Put | Straddle (pts) | Straddle (bps) | Market / model, strong body "
          "| Market / model, any body |", "|---|---|---|---|---|---|---|---|---|"]
    for c in checks:
        if "straddle_pts" in c:
            L.append(f"| {c['date']} | {c['S_1551_open']:.2f} | {c['strike']:.0f} | {c['call_1551_open']:.2f} | "
                     f"{c['put_1551_open']:.2f} | {c['straddle_pts']:.2f} | {c['straddle_bps']:.2f} | "
                     f"{c[f'market_over_model_{HEADLINE}']:.2f}x | {c['market_over_model_F1_1m_15:50']:.2f}x |")
        else:
            L.append(f"| {c['date']} | {c['S_1551_open']:.2f} | {c['strike']:.0f} | - | - | - | - | "
                     f"{AVAIL_TEXT.get(c['availability'], c['availability'])} | - |")
    if mc["days"]:
        L += ["", f"Over {mc['days']} day(s) the market straddle averaged {mc['mean_straddle_bps']:.2f} bps, "
              f"{mc['mean_market_over_model'][HEADLINE]:.2f}x the strong-body model price "
              f"({mc['mean_market_over_model']['F1_1m_15:50']:.2f}x the any-body one). This compares the call + "
              "put pair with twice the model option; on a given day the call or the put alone can be cheaper or "
              "dearer than the model. A pair above 1x means options cost more than the backtest assumed that day."]
    L += ["", "## Caveats", "",
          "- Robinhood's option bars carry no bid/ask and it does not say whether they are trades or marks. The "
          "$0.10 half-spread is the backtest's assumption, not an observed spread; a real fill can be worse.",
          "- The strike is chosen from the index's 15:51 bar open and paid at the option's 15:51 bar open; one-"
          "minute bars cannot show that both were available at the same instant. A person reacting to the 15:50 "
          "candle would trade a few seconds later.",
          "- Robinhood keeps one-minute option bars for about a day; days collected later have only 10-minute "
          "bars and cannot be priced at 15:51. They are listed with their status.",
          "- This page reports what happened. It does not recommend any trade.", ""]
    return "\n".join(L)


def csv_value(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    return v


def run(log_csv: Path = LOG_CSV, spx_root: Path = SPX_ROOT, out_dir: Path = OUT_DIR, out_md: Path = OUT_MD,
        holdout_json: Path = HOLDOUT_JSON, prereg: Path = PREREG, ledger: Path = LEDGER,
        directions: dict | None = None) -> dict:
    prereg_sha = check_prereg(prereg, ledger)
    if directions is None:
        directions = load_forward_module().frozen_directions()["directions"]
    model_bps = check_model_constants(holdout_json)
    closes, conflicts = official_closes(spx_root)
    rows, checks = [], []
    for row in read_log(log_csv):
        folder = Path(spx_root) / f"live_{row['date']}"
        opts, availability = load_day_options(folder, row["date"]) if folder.exists() else (None, "no_option_files")
        r, c = day_rows(row, opts, availability, completion_evidence(folder, row["date"]), directions, model_bps,
                        closes)
        rows += r
        checks.append(c)

    tallies = {}
    for name, _ in SIGNALS:
        t = {}
        for ex in ("a", "b"):
            sel = exit_rows(rows, name, ex)
            for fee in FEES:
                t[f"exit_{ex}_fee_{fee:.2f}"] = tally([r[f"pnl_{ex}_fee_{fee:.2f}"] for r in sel])
                if name in model_bps:
                    t[f"model_exit_{ex}_fee_{fee:.2f}"] = tally([r[f"model_pnl_fee_{fee:.2f}"] for r in sel])
        t["status_counts"] = {s: sum(1 for r in rows if r["signal_name"] == name and r["status"] == s)
                              for s in sorted({r["status"] for r in rows})}
        tallies[name] = t
    priced = [c for c in checks if "straddle_pts" in c]
    mean = (lambda key: sum(c[key] for c in priced) / len(priced)) if priced else (lambda key: None)
    model_check = {
        "model_half_straddle_bps": model_bps,
        "days": len(priced),
        "mean_straddle_bps": rnd(mean("straddle_bps"), 4),
        "mean_market_over_model": {k: rnd(mean(f"market_over_model_{k}"), 4) for k in model_bps},
        "per_day": [{k: (rnd(v, 6) if isinstance(v, float) else v) for k, v in c.items()} for c in checks]}
    summary = {"what": "Real 0DTE option outcomes of the frozen 15:50 candle signals, forward, descriptive only "
                       "(preregistration/spx_candle_forward_options.md).",
               "prereg_sha256": prereg_sha, "directions": directions,
               "inputs_sha256": {"candle_1550_log.csv": sha256_file(log_csv),
                                 "holdout.json": sha256_file(holdout_json)},
               "forward_days": len(checks), "tallies": tallies, "model_check": model_check,
               "official_close_conflicts": conflicts, "decisions": DECISIONS}

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in rows:
        w.writerow({k: csv_value(r.get(k)) for k in COLUMNS})
    out_dir = Path(out_dir)
    write_atomic(out_dir / OUT_CSV_NAME, buf.getvalue())
    write_atomic(out_dir / OUT_JSON_NAME, json.dumps(summary, indent=1, sort_keys=False) + "\n")
    write_atomic(Path(out_md), render_md(rows, checks, summary))
    return summary


if __name__ == "__main__":
    s = run()
    for name, _ in SIGNALS:
        a = s["tallies"][name]["exit_a_fee_0.09"]
        b = s["tallies"][name]["exit_b_fee_0.09"]
        print(f"{name}: exit A {a['trades']} finalized trades, {a['wins']} wins, total {a['total_usd']}, mean "
              f"{a['mean_usd']} | exit B {b['trades']} trades, total {b['total_usd']}")
    mc = s["model_check"]
    print(f"model check: {mc['days']} days, mean straddle {mc['mean_straddle_bps']} bps, market/model "
          f"{mc['mean_market_over_model']}")
