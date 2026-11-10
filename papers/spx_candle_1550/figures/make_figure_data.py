"""Write the CSV files the paper's figures plot, straight from the studies' result files (no hand-copied numbers).

Run from /Users/kv15/trading:
  .venv/bin/python -I papers/spx_candle_1550/figures/make_figure_data.py

Inputs (read only):
  data/spx_1549/databento/realprice_trades.csv        trade-by-trade real-price P&L (realprice.py run)
  backtests/spx_candle_realprice/results.json         current rule at every strike, 2021-2026
  backtests/spx_candle_refine/tune_results.json       threshold profile on 2021-2023 (tuning)
  backtests/spx_candle_refine/results.json            threshold profile on 2024-2026 (after the decision)
  backtests/spx_candle_exits/results.json             exit rules, model variant a, ITM10
Outputs: cumulative.csv, by_year.csv, strikes.csv, threshold.csv, exits.csv next to this file.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TRADES = ROOT / "data/spx_1549/databento/realprice_trades.csv"
REALPRICE = ROOT / "backtests/spx_candle_realprice/results.json"
REFINE_TUNE = ROOT / "backtests/spx_candle_refine/tune_results.json"
REFINE_TEST = ROOT / "backtests/spx_candle_refine/results.json"
EXITS = ROOT / "backtests/spx_candle_exits/results.json"


def frac_year(iso: str) -> float:
    d = date.fromisoformat(iso)
    start, end = date(d.year, 1, 1), date(d.year + 1, 1, 1)
    return d.year + (d - start).days / (end - start).days


def write(name: str, header: list[str], rows: list[list]) -> None:
    with open(OUT / name, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {name}: {len(rows)} rows")


def trades_figures() -> None:
    with open(TRADES, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["config"] == "current" and r["status"] == "priced"]
    rows.sort(key=lambda r: r["date"])
    assert rows, "no priced current-rule trades"
    cum_ask = cum_mid = 0.0
    out = [[f"{frac_year(rows[0]['date']) - 0.001:.4f}", "0.00", "0.00"]]
    years: dict[str, dict] = {}
    for r in rows:
        a, m = float(r["pnl_fee_0.09"]), float(r["pnl_mid_fee_0.09"])
        ask, mid = float(r["ask"]), float(r["mid"])
        cum_ask += a
        cum_mid += m
        out.append([f"{frac_year(r['date']):.4f}", f"{cum_ask:.2f}", f"{cum_mid:.2f}"])
        y = years.setdefault(r["date"][:4], {"n": 0, "ask": 0.0, "mid": 0.0, "won": 0, "spread": []})
        y["n"] += 1
        y["ask"] += a
        y["mid"] += m
        y["won"] += a > 0
        y["spread"].append(2 * (ask - mid))                      # full quoted spread, $ a share
    write("cumulative.csv", ["t", "ask_cum", "mid_cum"], out)
    write("by_year.csv", ["year", "trades", "ask_total", "mid_total", "ask_per_trade", "won_pct", "median_spread"],
          [[y, v["n"], f"{v['ask']:.2f}", f"{v['mid']:.2f}", f"{v['ask'] / v['n']:.2f}",
            f"{100 * v['won'] / v['n']:.1f}", f"{statistics.median(v['spread']):.3f}"] for y, v in years.items()])


def strike_figure() -> None:
    r = json.loads(REALPRICE.read_text())
    offs = r["confirmation"]["current_rule_all_offsets"]
    order = ["ITM20", "ITM15", "ITM10", "ITM5", "ATM", "OTM5", "OTM10", "OTM15", "OTM20"]
    assert set(order) == set(offs), sorted(offs)
    write("strikes.csv", ["idx", "label", "per_trade", "won_pct", "per_day", "t"],
          [[i, k, f"{offs[k]['mean_per_trade']:.2f}", f"{100 * offs[k]['share_trades_won']:.1f}",
            f"{offs[k]['mean_per_day']:.2f}", f"{offs[k]['nw_t_per_day']:.2f}"] for i, k in enumerate(order)])


def _profile(rows: list, period_key: str) -> dict:
    out = {}
    for row in rows:
        theta = float(row["cell"][1])
        s = row[period_key]
        out[round(theta, 2)] = (s["mean_per_day"], s["mean_per_trade"], s["trades"])
    return out


def threshold_figure() -> None:
    tune = json.loads(REFINE_TUNE.read_text())["part3_tuning"]["threshold_profile"]["ITM10"]
    test = json.loads(REFINE_TEST.read_text())["part3_test"]["threshold_profile"]["rows"]["ITM10"]
    a, b = _profile(tune, "tuning"), _profile(test, "test")
    assert sorted(a) == sorted(b) and len(a) == 11, (sorted(a), sorted(b))
    for row in tune + test:
        assert row["cell"][0] == "15:50" and row["cell"][2] == 1 and row["cell"][3] == 10, row["cell"]
    write("threshold.csv", ["theta", "tune_per_day", "tune_per_trade", "tune_trades",
                            "test_per_day", "test_per_trade", "test_trades"],
          [[f"{t:.2f}", f"{a[t][0]:.2f}", f"{a[t][1]:.2f}", a[t][2], f"{b[t][0]:.2f}", f"{b[t][1]:.2f}", b[t][2]]
           for t in sorted(a)])


def exits_figure() -> None:
    v = json.loads(EXITS.read_text())["part2"]["variants"]["a_calibrated"]["ITM10"]
    labels = {"H": "Hold to the close", "S8": "Stop at 8 points", "S5": "Stop at 5 points", "S3": "Stop at 3 points",
              "T10": "Target at 10 points", "T5": "Target at 5 points", "B5_10": "Stop 5 or target 10"}
    order = ["B5_10", "T5", "T10", "S3", "S5", "S8", "H"]               # bottom to top in a horizontal bar chart
    assert set(order) == set(v), sorted(v)
    write("exits.csv", ["idx", "rule", "label", "per_trade", "won_pct", "worst"],
          [[i, k, labels[k], f"{v[k]['mean_pnl_fee_0.09']:.2f}", f"{100 * v[k]['share_pnl_positive']:.1f}",
            f"{v[k]['worst_pnl']:.2f}"] for i, k in enumerate(order)])


if __name__ == "__main__":
    if sys.flags.isolated == 0:
        print("note: run with python -I", file=sys.stderr)
    trades_figures()
    strike_figure()
    threshold_figure()
    exits_figure()
