"""The rule the alert now uses, trade by trade: SPY's 15:50 candle at 70%+ and the SPX index candle at 60%+ in the
same direction; SPXW ITM10 in that direction at the 15:51 ask, held to settlement.

Descriptive. It is the intersection of two cells of the registered SPY study (preregistration/spx_candle_spy.md),
computed after that study's run from its trade file and the frozen index archive. Days already used; not a test.

Run from the repository root:
  .venv/bin/python -I backtests/spx_candle_spy/rule_trades.py [SINCE]      (SINCE defaults to 2026-08-10)
Writes rule_trades.csv, rule_summary.json and RULE_TRADES_RECENT.md next to this file.
"""
import csv, itertools, json, sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backtests" / "spx_candle_realindex"))
import realindex as RI

D = ROOT / "data" / "spx_1549"
END = "2026-10-20"


def bars(arch):
    out = {}
    for p in sorted(arch.glob("2*.json")):
        b = json.load(open(p))["bars"].get("15:50")
        if RI.valid_bar(b):
            out[p.stem] = b
    return out


def closes():
    out = {}
    for r in csv.DictReader(open(D / "spx_official_closes_cboe.csv")):
        m, d, y = r["DATE"].split("/")
        out[f"{y}-{m}-{d}"] = float(r["SPX"])
    return out


def main(since):
    idx, spy, cl = bars(D / "cnbc_1m"), bars(D / "cnbc_spy_1m"), closes()
    src = list(csv.DictReader(open(D / "databento" / "spycandle_trades.csv")))
    rule, dropped = [], {"no index bar": 0, "index candle under 60%": 0, "index candle the other way": 0}
    for t in src:
        if t["band"] != RI.B70:
            continue
        d = t["date"]
        if d not in idx:
            dropped["no index bar"] += 1
            continue
        ib, isign, iratio = RI.classify(idx[d])
        if ib is None:
            dropped["index candle under 60%"] += 1
            continue
        if isign != int(t["sign"]):
            dropped["index candle the other way"] += 1
            continue
        k, ask = float(t["strike"]), float(t["ask"])
        settle = max(0.0, cl[d] - k) if t["kind"] == "C" else max(0.0, k - cl[d])
        rule.append({"date": d, "side": "call" if t["kind"] == "C" else "put", "strike": int(k),
                     "spy_pct": round(100 * RI.classify(spy[d])[2], 1), "spx_pct": round(100 * iratio, 1),
                     "ask": ask, "cost": round(100 * ask, 2), "spx_close": cl[d], "settle_value": round(settle, 2),
                     "pnl": round(float(t["pnl"]), 2), "price_source": "Databento OPRA, 15:51:00 ask"})
    with open(HERE / "rule_trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rule[0]))
        w.writeheader()
        w.writerows(rule)
    p = np.array([t["pnl"] for t in rule])
    cum = np.cumsum(p)
    by = {}
    for t in rule:
        by.setdefault(t["date"][:4], []).append(t["pnl"])
    base = sorted({r["date"] for r in csv.DictReader(open(D / "d1_days.csv")) if r["calendar"] == "full" and "2021-01-01" <= r["date"] <= END})
    sess = {y: sum(1 for d in base if d[:4] == y) for y in sorted(by)}
    summary = {
        "rule": "SPY 15:50 body >= 70% and SPX index 15:50 body >= 60%, same direction; ITM10 at the 15:51 ask; held to settlement",
        "period": ["2021-01-01", END], "source_trades_spy_70": sum(1 for t in src if t["band"] == RI.B70), "dropped": dropped,
        "trades": len(rule), "total": round(float(p.sum()), 2), "per_trade": round(float(p.mean()), 2), "won": round(float((p > 0).mean()), 4),
        "median": round(float(np.median(p)), 2), "best": round(float(p.max()), 2), "worst": round(float(p.min()), 2),
        "avg_win": round(float(p[p > 0].mean()), 2), "avg_loss": round(float(p[p <= 0].mean()), 2),
        "avg_cost": round(float(np.mean([t["cost"] for t in rule])), 2),
        "worst_peak_to_trough": round(float((np.maximum.accumulate(cum) - cum).max()), 2),
        "longest_losing_streak": max(len(list(g)) for k, g in itertools.groupby(p > 0) if not k),
        "by_year": {y: {"trades": len(v), "sessions": sess[y], "share_of_sessions": round(len(v) / sess[y], 4), "total": round(sum(v), 2),
                        "per_trade": round(sum(v) / len(v), 2), "won": sum(x > 0 for x in v)} for y, v in sorted(by.items())}}

    # ---- the recent listing: the backtest's trades since SINCE, then the days after the backtest's last day
    recent = [t for t in rule if t["date"] >= since]
    feeds = {r["date"]: r for r in csv.DictReader(open(D / "alerts" / "feeds_1550.csv"))}
    fwd = {r["date"]: r for r in csv.DictReader(open(D / "forward" / "strikes_forward_log.csv"))
           if r["offset"] == "ITM10" and "strong_body" in r["signal_name"]}
    later = []
    for d in sorted(x for x in feeds if x > END):
        r = feeds[d]
        on = r.get("spy_band") == "70%+" and r.get("real_band") in ("70%+", "60-70%") and r.get("spy_dir") == r.get("real_dir")
        if not on:
            continue
        side = "call" if r["spy_dir"] == "up" else "put"
        e = {"date": d, "side": side, "spy_pct": round(100 * float(r["spy_ratio"]), 1), "spx_pct": round(100 * float(r["real_ratio"]), 1),
             "strike": None, "cost": None, "spx_close": cl.get(d), "settle_value": None, "pnl": None,
             "move_pts": float(r["move_pts"]) if r.get("move_pts") else None, "price_source": "no 15:51 option price was collected"}
        f = fwd.get(d)
        if f:
            e["strike"] = int(float(f["strike"]))
            if cl.get(d) is not None:
                k = e["strike"]
                e["settle_value"] = round(max(0.0, cl[d] - k) if side == "call" else max(0.0, k - cl[d]), 2)
            if f["status"] == "traded":
                e.update({"cost": round(100 * float(f["cost_incl_half_spread"]), 2), "pnl": round(float(f["pnl_a_fee_0.09"]), 2),
                          "price_source": "broker minute bars: first 15:51 price + $0.10"})
        q = D / "databento" / "cbbo-1m_1545-1601_k60_forward" / f"{d}.csv.gz"
        if q.exists() and cl.get(d) is not None:          # OPRA quotes bought later: the backtest's own pricing rule
            book, meta = RI.BC.read_quotes(q, d)
            assert meta["conflicts_by_minute"].get("15:51", 0) == 0
            t, why = RI.trade(book["15:51"], 1 if side == "call" else -1, cl[d])
            if t is not None:
                k = int(t["strike"])
                e.update({"strike": k, "cost": round(100 * t["ask"], 2), "pnl": round(t["pnl"], 2),
                          "settle_value": round(max(0.0, cl[d] - k) if side == "call" else max(0.0, k - cl[d]), 2),
                          "price_source": "Databento OPRA, 15:51:00 ask"})
            else:
                e["price_source"] = f"Databento OPRA: {why}"
        later.append(e)
    money = lambda x: "n/a" if x is None else f"{'+' if x >= 0 else '-'}${abs(x):,.0f}"
    w = ["# Trades under the rule now in use: the last three months\n",
         f"Generated by `rule_trades.py` (since {since}). Research record, not trading advice. One contract per trade.\n",
         "**The rule:** SPY's 15:50 candle at 70% or more and the SPX candle at 60% or more, same direction; buy the 0DTE SPXW "
         "option 10 points in the money at the 15:51 ask; hold to the close.\n",
         f"## {since} to {END}: the backtest (real Databento asks)\n",
         "| Date | Side | Strike | SPY % | SPX % | Cost | SPX close | Settled at | Profit |\n|---|---|---|---|---|---|---|---|---|"]
    for t in recent:
        w.append(f"| {t['date']} | {t['side']} | {t['strike']} | {t['spy_pct']:.0f}% | {t['spx_pct']:.0f}% | ${t['cost']:,.0f} | {t['spx_close']:,.2f} | "
                 f"${100 * t['settle_value']:,.0f} | **{money(t['pnl'])}** |")
    rp = np.array([t["pnl"] for t in recent])
    w.append(f"\n**{len(recent)} trades, {int((rp > 0).sum())} won, total {money(float(rp.sum()))}, average {money(float(rp.mean()))} a trade.** "
             f"Best {money(float(rp.max()))}, worst {money(float(rp.min()))}.\n")
    w.append(f"## After {END}: signal days since the backtest's data ends\n")
    w.append("The option quotes bought for the backtest stop on " + END + ". Later days are priced from the one-minute bars the daily collector "
             "saved from the broker where it has them, and otherwise from OPRA quotes bought afterwards (the backtest's own rule: the 15:51:00 ask).\n")
    w.append("| Date | Side | Strike | SPY % | SPX % | Cost | SPX close | Settled at | Profit | Price source |\n|---|---|---|---|---|---|---|---|---|---|")
    for e in later:
        w.append(f"| {e['date']} | {e['side']} | {e['strike'] or 'n/a'} | {e['spy_pct']:.0f}% | {e['spx_pct']:.0f}% | "
                 f"{('$' + format(e['cost'], ',.0f')) if e['cost'] is not None else 'n/a'} | {e['spx_close']:,.2f} | "
                 f"{('$' + format(100 * e['settle_value'], ',.0f')) if e['settle_value'] is not None else 'n/a'} | "
                 f"{('**' + money(e['pnl']) + '**') if e['pnl'] is not None else 'not priced'} | {e['price_source']} |")
    lp = np.array([e["pnl"] for e in later if e["pnl"] is not None])
    if len(lp):
        w.append(f"\n{len(later)} signal days; {len(lp)} priced: {int((lp > 0).sum())} won, total {money(float(lp.sum()))}. "
                 f"{len(later) - len(lp)} not priced.\n")
    allp = np.concatenate([rp, lp])
    w.append(f"## All together, {since} to {later[-1]['date'] if later else END}\n")
    w.append(f"**{len(allp)} priced trades, {int((allp > 0).sum())} won, total {money(float(allp.sum()))}, average {money(float(allp.mean()))} a trade.**\n")
    Path(HERE / "RULE_TRADES_RECENT.md").write_text("\n".join(w) + "\n")
    summary["recent"] = {"since": since, "to": END, "trades": len(recent), "won": int((rp > 0).sum()), "total": round(float(rp.sum()), 2),
                         "per_trade": round(float(rp.mean()), 2), "best": round(float(rp.max()), 2), "worst": round(float(rp.min()), 2)}
    summary["after_backtest"] = {"from": later[0]["date"] if later else None, "to": later[-1]["date"] if later else None,
                                 "signal_days": len(later), "priced": int(len(lp)), "won": int((lp > 0).sum()) if len(lp) else 0,
                                 "total": round(float(lp.sum()), 2) if len(lp) else None,
                                 "by_source": {src: {"trades": len(v), "won": sum(x > 0 for x in v), "total": round(sum(v), 2)}
                                               for src, v in ((s_, [e["pnl"] for e in later if e["pnl"] is not None and e["price_source"].startswith(s_)])
                                                              for s_ in ("broker", "Databento")) if v}}
    summary["recent_plus_later"] = {"since": since, "to": later[-1]["date"] if later else END, "priced_trades": int(len(allp)),
                                    "won": int((allp > 0).sum()), "total": round(float(allp.sum()), 2), "per_trade": round(float(allp.mean()), 2)}
    json.dump(summary, open(HERE / "rule_summary.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "by_year"}, indent=1))
    print(open(HERE / "RULE_TRADES_RECENT.md").read())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-08-10")
