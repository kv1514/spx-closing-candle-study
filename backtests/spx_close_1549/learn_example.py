#!/usr/bin/env python
"""Teaching example for README.md (not a test, not part of the pre-registered analysis).

Uses the one D2 day with real one-minute SPXW 0DTE option bars (2026-10-20) to show what gamma and
theta do in the last 11 minutes. Every price is read from the saved Robinhood files; the only model
is a plain normal-move approximation, labelled as such.

Run:
    /Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/learn_example.py
Writes backtests/spx_close_1549/learn_example.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis as A  # noqa: E402

DAY = "2026-10-20"
OUT = HERE / "learn_example.json"


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def call_value_normal(s: float, k: float, sd: float) -> float:
    """E[max(S_T - K, 0)] when S_T - s ~ Normal(0, sd^2) (Bachelier, zero rate)."""
    d = (s - k) / sd
    return sd * norm_pdf(d) + (s - k) * norm_cdf(d)


def main() -> int:
    days, _ = A.load_d2()
    day = days[DAY]
    sO, sC, settle = day["spx_O"], day["spx_C"], float(day["settle"])
    s0 = float(sO[A.I1549])
    k0 = A.nearest_strike(s0)
    kc = k0 + A.S3_OFFSET

    def opt(kind, k, idx, field):
        arr = day["options"][(kind, float(k))]
        return float(arr[0][idx] if field == "O" else arr[1][idx])

    call0, put0, otm0 = opt("call", k0, A.I1549, "O"), opt("put", k0, A.I1549, "O"), opt("call", kc, A.I1549, "O")
    straddle0 = call0 + put0
    hs = A.BASE_HALF_SPREAD
    cost_pts = straddle0 + 2 * hs
    minutes_left = 11

    # minute-by-minute path of SPX and the options (closes of the real 1-minute bars)
    path = []
    for m in range(A.I1549, A.I1559 + 1):
        t = f"{(570 + m) // 60:02d}:{(570 + m) % 60:02d}"
        c, p, o = opt("call", k0, m, "C"), opt("put", k0, m, "C"), opt("call", kc, m, "C")
        path.append({"bar": t, "spx_close": float(sC[m]), "call_close": c, "put_close": p, "straddle_close": c + p,
                     "otm_call_close": o, "straddle_intrinsic_at_spx": abs(float(sC[m]) - k0),
                     "minutes_left_after_bar": A.I1559 - m})
    settle_straddle = abs(settle - k0)
    settle_otm = max(settle - kc, 0.0)

    # normal-move approximation implied by the straddle: E|X| = sd * sqrt(2/pi)  ->  sd = straddle * sqrt(pi/2)
    sd_move = straddle0 * math.sqrt(math.pi / 2.0)
    delta_atm = norm_cdf((s0 - k0) / sd_move)
    gamma_atm = norm_pdf((s0 - k0) / sd_move) / sd_move
    # same strike distance on a 30-calendar-day option at 15% vol, for comparison (illustration only)
    sd_30d = s0 * 0.15 * math.sqrt(30 / 365)
    gamma_30d = norm_pdf((s0 - k0) / sd_30d) / sd_30d
    time_value0 = straddle0 - abs(s0 - k0)
    sqrt_rule = {f"{m}_min_left": time_value0 * math.sqrt(m / minutes_left) for m in (11, 8, 5, 3, 1)}

    double_level = kc + 2 * otm0
    otm_table = []
    for move in (-5.0, 0.0, kc - s0, double_level - s0, 10.0, 15.0, 20.0):
        st = s0 + move
        v = max(st - kc, 0.0)
        otm_table.append({"spx_move_pts": move, "spx_at_close": st, "value": v, "multiple_of_entry": v / otm0})
    out = {
        "label": "teaching example, not a test; prices from saved Robinhood files, model = normal-move approximation",
        "day": DAY, "spx_open_1549": s0, "atm_strike": k0, "call_mark_1549": call0, "put_mark_1549": put0,
        "straddle_mark_1549": straddle0, "half_spread_per_leg": hs, "straddle_cost_with_half_spreads": cost_pts,
        "breakeven_low": k0 - cost_pts, "breakeven_high": k0 + cost_pts,
        "breakeven_move_from_s0_up": k0 + cost_pts - s0, "breakeven_move_from_s0_down": s0 - (k0 - cost_pts),
        "breakeven_move_bps_avg": ((k0 + cost_pts - s0) + (s0 - (k0 - cost_pts))) / 2 / s0 * 1e4,
        "official_close": settle, "realized_move_pts": settle - s0, "straddle_settlement_value": settle_straddle,
        "straddle_pnl_usd_base": A.straddle_pnl(k0, call0, put0, settle, hs, A.BASE_FEE)["pnl_usd"],
        "if_spx_unchanged_straddle_worth": abs(s0 - k0), "time_value_at_1549": time_value0,
        "time_value_lost_per_minute_avg": time_value0 / minutes_left,
        "sqrt_time_rule_time_value": sqrt_rule,
        "normal_approx": {"sd_move_pts_to_close": sd_move, "atm_call_delta": delta_atm, "atm_gamma_per_pt": gamma_atm,
                          "gamma_30d_15pct_same_moneyness": gamma_30d, "gamma_ratio_0dte_vs_30d": gamma_atm / gamma_30d},
        "otm_call": {"strike": kc, "mark_1549": otm0, "level_for_2x_at_close": double_level,
                     "move_needed_for_2x_pts": double_level - s0,
                     "prob_close_above_strike_normal": 1 - norm_cdf((kc - s0) / sd_move),
                     "prob_2x_or_more_normal": 1 - norm_cdf((double_level - s0) / sd_move),
                     "fair_value_normal": call_value_normal(s0, kc, sd_move),
                     "max_close_1549_1558": float(np.nanmax([x["otm_call_close"] for x in path[:-1]])),
                     "settlement_value": settle_otm,
                     "payoff_table": otm_table},
        "path": path,
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "path"}, indent=1))
    for x in path:
        print(x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
