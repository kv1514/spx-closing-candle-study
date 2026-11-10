"""Limit-order fill simulation for the 15:50 candle rule (descriptive; decides nothing, adopts nothing).

Question: the real-price study bought at the 15:51 ask. Would a limit order near the mid have done better, once
you count the days it does NOT fill? A limit that fills mostly when the option is getting cheaper (the trade going
against you) and misses when it runs away (the trade working) is "adversely selected", and can do worse than
paying the ask even though each fill is cheaper.

Inputs (all already on disk; nothing is downloaded):
  data/spx_1549/databento/realprice_trades.csv   the current rule's priced entries (config 'current'): date,
                                                 period, contract, the 15:51 ask and mid, P&L at the ask
  data/spx_1549/databento/cbbo-1m_1500-1601_k60  quotes: the snapshot at each minute's start (15:52 ask for a chase)
  data/spx_1549/databento/ohlcv-1m_1500-1601_k60 trade bars: a bar stamped HH:MM covers that minute's trades

Policies (fixed before any result was computed; all are reported; none is selected):
  P0 ask_now            pay the 15:51 ask (the real-price study's own assumption; must reproduce it)
  P1 mid_1m_skip        limit at the 15:51 mid, rounded UP to a valid tick, for the 15:51 minute; filled only if
                        a trade printed strictly below the limit in that minute; otherwise no trade that day
  P1t mid_1m_skip_touch the same, filled if a trade printed AT or below the limit (optimistic: ignores the queue)
  P2 mid_1m_then_ask    P1; if unfilled, pay the 15:52 ask (the quote snapshot at 15:52:00)
  P3 mid_3m_skip        P1's limit left working through 15:53 (trade strictly below it in 15:51, 15:52 or 15:53)
  P4 half_1m_then_ask   limit halfway between the 15:51 mid and ask, rounded up to a tick, for the 15:51 minute;
                        if unfilled, pay the 15:52 ask
A limit at or above the 15:51 ask is marketable and fills at the ask at once.

Tick sizes (SPXW, Cboe): $0.05 below $3.00, $0.10 at $3.00 and above. A buy limit is rounded UP to a tick.
Settlement: each entry's payoff per share is recovered from the study's own P&L: (pnl_ask + fee) / 100 + ask.

Caveats (also printed in RESULTS.md):
  - Trade bars include every print, and complex-order (spread) legs can print away from the quote, so a "trade
    below the limit" is evidence of a fill, not proof. Strict "<" is the conservative rule; "<=" is optimistic.
  - Order size, queue position and the exact second are unknown; a one-contract order is assumed.
  - 2021-2026 was already used to confirm the rule. Policies here are described, not tested or chosen.

Usage (from /Users/kv15/trading):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_fills/fills.py selftest
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B backtests/spx_candle_fills/fills.py run
Outputs: backtests/spx_candle_fills/RESULTS.md, results.json; data/spx_1549/databento/fills_trades.csv.
Nothing here is a trading recommendation.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
RP_PY = ROOT / "backtests" / "spx_candle_realprice" / "realprice.py"
TRADES_IN = ROOT / "data" / "spx_1549" / "databento" / "realprice_trades.csv"
TRADES_OUT = ROOT / "data" / "spx_1549" / "databento" / "fills_trades.csv"
OUT_JSON = HERE / "results.json"
OUT_MD = HERE / "RESULTS.md"

CONFIG = "current"
ENTRY = "15:51"
CHASE = "15:52"
WORK_3M = ("15:51", "15:52", "15:53")
LATE = ("15:51", "15:52", "15:53", "15:55")                # descriptive: added after the first run
FEE = 0.09
MULT = 100.0
EXPECTED = {"confirmation": (585, 67.46), "discovery": (216, -23.14)}   # P0 must reproduce the study
PERIODS = (
    ("discovery 2013-2020", "2013-01-01", "2020-12-31"),
    ("confirmation 2021-2026", "2021-01-01", "2026-12-31"),
    ("2021-2022", "2021-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2026-12-31"),
)
POLICIES = ("P0_ask_now", "P1_mid_1m_skip", "P1t_mid_1m_skip_touch", "P2_mid_1m_then_ask", "P3_mid_3m_skip",
            "P4_half_1m_then_ask")


def load_rp():
    spec = importlib.util.spec_from_file_location("realprice", RP_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tick_up(p: float) -> float:
    """Round a buy limit up to a valid SPXW tick ($0.05 below $3.00, $0.10 from $3.00)."""
    cents = round(p * 100, 6)
    t = 5 if cents < 300 else 10
    return math.ceil(cents / t - 1e-9) * t / 100.0


def bar_of(bars: dict, minute: str, key):
    """(low, close, volume) or None when the contract did not trade in that minute."""
    b = (bars or {}).get(minute, {}).get(key)
    if b is None or not b[2] or b[2] <= 0:
        return None
    return b


NEXT_MINUTE = {"15:51": "15:52", "15:52": "15:53", "15:53": "15:54"}


def limit_fill(limit: float, ask51: float, bars: dict, quotes: dict, minutes, key, strict: bool):
    """Fill price for a buy limit placed at the 15:51 open and worked through `minutes`, else None. In each minute it
    fills if a trade printed below it (strict) or at/below it (touch), or if the quote snapshot at the minute's end
    (the next minute's HH:MM:00 row) offers at or below it: an offer that reached the limit would have hit it."""
    if limit >= ask51 - 1e-9:
        return ask51                                  # marketable: fills at the ask at once
    for m in minutes:
        b = bar_of(bars, m, key)
        if b is not None:
            lo = b[0]
            if (lo < limit - 1e-9) if strict else (lo <= limit + 1e-9):
                return limit
        q = (quotes or {}).get(NEXT_MINUTE[m], {}).get(key)
        if q is not None and q[1] <= limit + 1e-9:
            return limit
    return None


def simulate(entry: dict, bars: dict, quotes: dict) -> dict:
    """Fill price per policy (None = no trade) for one entry. `entry` has kind, strike, ask, mid."""
    key = (entry["kind"], entry["strike"])
    ask, mid = entry["ask"], entry["mid"]
    lim_mid = tick_up(mid)
    lim_half = tick_up(mid + (ask - mid) / 2)
    q52 = (quotes or {}).get(CHASE, {}).get(key)
    ask52 = q52[1] if q52 else None
    p1 = limit_fill(lim_mid, ask, bars, quotes, (ENTRY,), key, strict=True)
    p4 = limit_fill(lim_half, ask, bars, quotes, (ENTRY,), key, strict=True)
    return {
        "P0_ask_now": ask,
        "P1_mid_1m_skip": p1,
        "P1t_mid_1m_skip_touch": limit_fill(lim_mid, ask, bars, quotes, (ENTRY,), key, strict=False),
        "P2_mid_1m_then_ask": p1 if p1 is not None else ask52,
        "P3_mid_3m_skip": limit_fill(lim_mid, ask, bars, quotes, WORK_3M, key, strict=True),
        "P4_half_1m_then_ask": p4 if p4 is not None else ask52,
        "_lim_mid": lim_mid, "_lim_half": lim_half, "_ask52": ask52,
    }


def pnl(payoff: float, price):
    return 0.0 if price is None else MULT * (payoff - price) - FEE


def stats(x: list) -> dict:
    n = len(x)
    if n == 0:
        return {"n": 0, "mean": None, "t": None}
    m = sum(x) / n
    if n < 2:
        return {"n": n, "mean": m, "t": None}
    v = sum((a - m) ** 2 for a in x) / (n - 1)
    return {"n": n, "mean": m, "t": (m / math.sqrt(v / n)) if v > 0 else None}


def read_entries() -> list:
    out = []
    with open(TRADES_IN) as fh:
        for r in csv.DictReader(fh):
            if r["config"] != CONFIG or r["status"] != "priced":
                continue
            if r["entry_minute"] != ENTRY:
                raise SystemExit(f"unexpected entry minute {r['entry_minute']} on {r['date']}")
            ask, mid, p = float(r["ask"]), float(r["mid"]), float(r["pnl_fee_0.09"])
            out.append({"date": r["date"], "period": r["period"], "signal": int(float(r["signal"])),
                        "kind": r["kind"], "strike": float(r["strike"]), "ask": ask, "mid": mid,
                        "pnl_ask": p, "payoff": (p + FEE) / MULT + ask})
    return out


def run() -> dict:
    rp = load_rp()
    entries = read_entries()
    listing = rp.bar_listing()
    rows, skipped = [], {"no_bar_file": 0, "no_quote_file": 0, "ask_mismatch": 0}
    for e in entries:
        quotes, _ = rp.load_day_quotes(e["date"])
        if not isinstance(quotes, dict):
            skipped["no_quote_file"] += 1
            continue
        q51 = quotes.get(ENTRY, {}).get((e["kind"], e["strike"]))
        if q51 is None or abs(q51[1] - e["ask"]) > 1e-9:
            skipped["ask_mismatch"] += 1
            continue
        bars, status = rp.load_day_bars(e["date"], listing)
        if status != "ok":
            skipped["no_bar_file"] += 1
            continue
        sim = simulate(e, bars, quotes)
        row = dict(e)
        for p in POLICIES:
            row[f"{p}_price"] = sim[p]
            row[f"{p}_pnl"] = pnl(e["payoff"], sim[p])
        row.update({"lim_mid": sim["_lim_mid"], "lim_half": sim["_lim_half"], "ask_1552": sim["_ask52"]})
        for m in LATE:                                    # the same contract bought late, at that minute's ask
            qa = quotes.get(m, {}).get((e["kind"], e["strike"]))
            row[f"late_{m}_pnl"] = pnl(e["payoff"], qa[1]) if qa else None
        rows.append(row)

    up = json.loads((ROOT / "backtests" / "spx_candle_realprice" / "results.json").read_text())
    upstream = up["unpriced_signal_entries"]["configs"][CONFIG]
    res = {"skipped": skipped, "upstream_unpriced": upstream, "n_rows": len(rows), "periods": {}}
    for name, lo, hi in PERIODS:
        R = [r for r in rows if lo <= r["date"] <= hi]
        per = {"signal_days": len(R), "policies": {}}
        base = [r["P0_ask_now_pnl"] for r in R]
        for p in POLICIES:
            day = [r[f"{p}_pnl"] for r in R]
            filled = [r[f"{p}_pnl"] for r in R if r[f"{p}_price"] is not None]
            diff = [a - b for a, b in zip(day, base)]
            per["policies"][p] = {
                "fills": len(filled), "fill_rate": len(filled) / len(R) if R else None,
                "per_signal_day": stats(day), "per_fill": stats(filled),
                "minus_P0_per_signal_day": stats(diff) if p != "P0_ask_now" else None,
            }
        # adverse selection: P1's filled vs unfilled days, judged by what the same entry did at the ask
        sel = {}
        for tag, pick in (("filled", True), ("unfilled", False)):
            S = [r for r in R if (r["P1_mid_1m_skip_price"] is not None) == pick]
            sel[tag] = {"n": len(S), "pnl_at_ask": stats([r["pnl_ask"] for r in S]),
                        "won_at_ask": (sum(r["pnl_ask"] > 0 for r in S) / len(S)) if S else None}
        per["adverse_selection_P1"] = sel
        both = [r for r in R if all(r[f"late_{m}_pnl"] is not None for m in LATE)]
        per["late_entry"] = {"days_with_every_quote": len(both),
                             **{m: stats([r[f"late_{m}_pnl"] for r in both]) for m in LATE}}
        res["periods"][name] = per

    for key, (n_exp, m_exp) in EXPECTED.items():
        name = next(n for n, _, _ in PERIODS if n.startswith(key))
        p0 = res["periods"][name]["policies"]["P0_ask_now"]["per_fill"]
        ok = p0["n"] == n_exp and abs(p0["mean"] - m_exp) < 0.01
        res.setdefault("reproduction", {})[key] = {"n": p0["n"], "mean": round(p0["mean"], 2), "ok": ok}
        if not ok:
            raise SystemExit(f"P0 does not reproduce the real-price study ({key}): {p0} vs {n_exp}, {m_exp}")

    write_outputs(rows, res)
    return res


def fmt(x, nd=2, sign=True):
    if x is None:
        return "—"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"


def write_outputs(rows: list, res: dict) -> None:
    cols = list(rows[0].keys()) if rows else []
    with open(TRADES_OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    OUT_JSON.write_text(json.dumps(res, indent=2, default=str))
    L = ["# Limit-order fill simulation for the 15:50 rule (descriptive; decides nothing)", "",
         "Current rule (15:50 candle, body >= 0.60, with the candle, ITM10), entries priced by the real-price study. "
         "Policies are defined in `fills.py`'s header; all are reported and none is selected. $ are per contract, "
         "$0.09 fee. An unfilled order counts as $0 (no trade, no fee).", "",
         "**These are trade-low proxy scenarios, not execution estimates.** A limit counts as filled if a trade "
         "printed below it (or at it, for the touch version) in a minute it was working, or if the quote snapshot "
         "at that minute's end offered at or below it. Prints cannot show whether a resting simple order would "
         "have executed (spread legs print away from the quote), intraminute quote moves between snapshots are "
         "not seen, and orders are assumed to arrive and execute with zero latency.", "",
         f"Rows simulated: {res['n_rows']} priced signal days. Left out by this script: {res['skipped']}. "
         "Left out upstream, because the real-price study could not price them (unknown outcomes, not $0): "
         + "; ".join(f"{k} {v['signal_days'] - v['priced']} of {v['signal_days']} (no spot {v['no_spot']}, "
                     f"no quote {v['no_quote']})" for k, v in res["upstream_unpriced"].items())
         + f". P0 reproduces the study (an algebraic consistency check): {res['reproduction']}.", ""]
    for name, per in res["periods"].items():
        L += [f"## {name} ({per['signal_days']} priced signal days)", "",
              "| Policy | Filled | $/priced signal day | t | $/fill | minus P0, $/priced signal day | t |",
              "|---|---|---|---|---|---|---|"]
        for p, s in per["policies"].items():
            d = s["minus_P0_per_signal_day"] or {}
            fr = f"{s['fills']} ({100 * s['fill_rate']:.0f}%)" if s["fill_rate"] is not None else "—"
            L.append(f"| {p} | {fr} | {fmt(s['per_signal_day']['mean'])} | {fmt(s['per_signal_day']['t'])} | "
                     f"{fmt(s['per_fill']['mean'])} | {fmt(d.get('mean'))} | {fmt(d.get('t'))} |")
        a = per["adverse_selection_P1"]
        L += ["", "Adverse selection: the same entries' P&L at the ask, split by whether P1's mid limit filled:", "",
              "| P1 | Days | $/trade at the ask | t | Won at the ask |", "|---|---|---|---|---|"]
        for tag in ("filled", "unfilled"):
            s = a[tag]
            won = f"{100 * s['won_at_ask']:.0f}%" if s["won_at_ask"] is not None else "—"
            L.append(f"| {tag} | {s['n']} | {fmt(s['pnl_at_ask']['mean'])} | {fmt(s['pnl_at_ask']['t'])} | {won} |")
        le = per["late_entry"]
        L += ["", f"Late entry: the same contract bought at a later minute's ask ({le['days_with_every_quote']} days "
              "with a quote at every one of these minutes):", "", "| Buy at | $/trade | t |", "|---|---|---|"]
        for m in LATE:
            L.append(f"| {m} | {fmt(le[m]['mean'])} | {fmt(le[m]['t'])} |")
        L.append("")
    L += ["## Caveats", "",
          "- Trade bars include every print; complex-order legs can print away from the quote, so a trade below the "
          "limit is evidence of a fill, not proof. Strict trade-through (P1) is not a conservative execution "
          "estimate; touch (P1t) only adds fill frequency, and its extra fills are not cheaper winners.",
          "- Quotes are minute snapshots: an offer that dipped to the limit and recovered inside a minute is missed.",
          "- Zero latency: an order reacting to the 15:50 candle is assumed live at 15:51:00, and the 15:52 chase "
          "is assumed to execute at the 15:52:00 ask.",
          "- Queue position, order size and the exact second are unknown; one contract is assumed.",
          "- 2021-2026 already confirmed the rule; these policies are described on it, not tested or chosen.",
          "- t-statistics treat signal days as independent.", "- Nothing here is a trading recommendation.", ""]
    OUT_MD.write_text("\n".join(L))


def selftest() -> None:
    assert tick_up(2.98) == 3.0 and tick_up(2.96) == 3.0 and tick_up(2.95) == 2.95 and tick_up(2.951) == 3.0
    assert tick_up(10.55) == 10.6 and tick_up(10.5) == 10.5 and tick_up(0.03) == 0.05 and tick_up(3.0) == 3.0
    key = ("call", 100.0)
    e = {"kind": "call", "strike": 100.0, "ask": 10.70, "mid": 10.45}       # limit 10.50, half 10.60
    quotes = {"15:52": {key: (10.9, 11.2)}}
    # 15:51 low 10.40 < 10.50: P1 fills at 10.50; P4 (10.60) fills at 10.60
    s = simulate(e, {"15:51": {key: (10.40, 10.8, 5)}}, quotes)
    assert s["P1_mid_1m_skip"] == 10.5 and s["P1t_mid_1m_skip_touch"] == 10.5 and s["P4_half_1m_then_ask"] == 10.6
    assert s["P2_mid_1m_then_ask"] == 10.5 and s["P3_mid_3m_skip"] == 10.5 and s["P0_ask_now"] == 10.7
    # low exactly at the limit: strict misses, touch fills; P2 chases to the 15:52 ask 11.2
    s = simulate(e, {"15:51": {key: (10.50, 10.8, 5)}}, quotes)
    assert s["P1_mid_1m_skip"] is None and s["P1t_mid_1m_skip_touch"] == 10.5 and s["P2_mid_1m_then_ask"] == 11.2
    # no trade in 15:51, a trade below the limit in 15:53: only P3 fills there
    s = simulate(e, {"15:53": {key: (10.3, 10.4, 2)}}, quotes)
    assert s["P1_mid_1m_skip"] is None and s["P3_mid_3m_skip"] == 10.5 and s["P2_mid_1m_then_ask"] == 11.2
    # zero-volume bar is no trade; no 15:52 quote means the chase is skipped
    s = simulate(e, {"15:51": {key: (10.0, 10.0, 0)}}, {})
    assert s["P1_mid_1m_skip"] is None and s["P2_mid_1m_then_ask"] is None
    # no trade at all, but the 15:52:00 offer came down to the limit: the resting limit fills
    s = simulate(e, {}, {"15:52": {key: (10.3, 10.5)}})
    assert s["P1_mid_1m_skip"] == 10.5 and s["P2_mid_1m_then_ask"] == 10.5 and s["P4_half_1m_then_ask"] == 10.6
    # the 15:54:00 offer counts for the three-minute order only
    s = simulate(e, {}, {"15:52": {key: (10.6, 10.9)}, "15:54": {key: (10.2, 10.4)}})
    assert s["P1_mid_1m_skip"] is None and s["P3_mid_3m_skip"] == 10.5 and s["P2_mid_1m_then_ask"] == 10.9
    # one-tick spread: the rounded limit equals the ask -> marketable, fills at the ask
    e2 = {"kind": "put", "strike": 50.0, "ask": 10.5, "mid": 10.45}
    s = simulate(e2, {}, {})
    assert s["P1_mid_1m_skip"] == 10.5 and s["P3_mid_3m_skip"] == 10.5
    assert pnl(12.0, 10.5) == MULT * 1.5 - FEE and pnl(12.0, None) == 0.0
    st = stats([1.0, 3.0])
    assert st["n"] == 2 and st["mean"] == 2.0 and abs(st["t"] - 2.0 / (math.sqrt(2.0) / math.sqrt(2))) < 1e-12
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        r = run()
        print(json.dumps({k: v for k, v in r.items() if k != "periods"}, indent=1))
        print(f"wrote {OUT_MD}, {OUT_JSON}, {TRADES_OUT}")
    else:
        raise SystemExit(__doc__)
