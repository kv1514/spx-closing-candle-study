"""Tests for analysis.py on synthetic data.

pytest is not installed in .venv, so this file runs with plain Python:
    .venv/bin/python -B backtests/spx_close_1549/tests/test_analysis.py
(It also works under pytest if that is installed later.)
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import analysis as A  # noqa: E402


# --------------------------------------------------------------------------------------------
# synthetic minute data: n_days x 390 open/close matrices on a continuous log-price path
# --------------------------------------------------------------------------------------------
def synth(n_days: int, seed: int, sigma: float = 2e-4, close_vol_mult: float = 1.0,
          plant: str | None = None, effect_bps: float = 0.0):
    """Bar m runs from log price b[m] (open) to b[m+1] (close). Optionally plant an effect in the
    target window: plant='P1' adds effect_bps * sign(P1) spread over bars 15:49..15:59;
    plant='P3' adds effect_bps * sign(P3) over bars 15:51..15:59 (negative = reversal)."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, sigma, (n_days, A.N_MIN))
    steps[:, A.I1549:] *= close_vol_mult

    def build(st):
        b = np.concatenate([np.full((n_days, 1), math.log(5000.0)), np.cumsum(st, axis=1) + math.log(5000.0)], axis=1)
        return np.exp(b[:, :-1]), np.exp(b[:, 1:])

    O, C = build(steps)
    if plant:
        spec = A.PREDICTORS[plant]
        s = spec["fn"](O, C)
        start = A.TARGETS[spec["target"]][0]
        nbar = A.N_MIN - start
        steps[:, start:] += (effect_bps * 1e-4 / nbar) * s[:, None]
        O2, C2 = build(steps)
        # the planted effect must not change the predictor itself (it only touches bars >= entry)
        assert np.array_equal(spec["fn"](O2, C2), s)
        O, C = O2, C2
    return O, C


def _dates(n, start="2017-01-02"):   # 2000 business days from here reach into 2023-2026
    import pandas as pd
    d = pd.bdate_range(start, periods=n)
    return d.strftime("%Y-%m-%d").to_numpy(), d.strftime("%a").to_numpy()


# --------------------------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------------------------
def test_nw_lag0_equals_iid_standard_error():
    y = np.random.default_rng(1).normal(0.3, 1.0, 500)
    r = A.nw_mean_test(y, lag=0)
    assert abs(r["se"] - y.std(ddof=0) / math.sqrt(len(y))) < 1e-12
    assert abs(r["mean"] - y.mean()) < 1e-12


def test_nw_inflates_se_for_positively_autocorrelated_series():
    rng = np.random.default_rng(2)
    e = rng.normal(size=4000)
    y = np.convolve(e, np.ones(4) / 4, mode="valid")    # MA(3): positive autocorrelation
    assert A.nw_mean_test(y, lag=5)["se"] > 1.5 * A.nw_mean_test(y, lag=0)["se"]


def test_holm_hand_computed():
    adj = A.holm([0.01, 0.04, 0.03, 0.005])
    # sorted: 0.005*4=0.02, 0.01*3=0.03, 0.03*2=0.06, 0.04*1=0.04 -> monotone 0.06
    assert np.allclose(adj, [0.03, 0.06, 0.06, 0.02]), adj


def test_bootstrap_ci_brackets_mean():
    x = np.random.default_rng(3).normal(1.0, 1.0, 400)
    lo, hi = A.boot_mean_ci(x, np.random.default_rng(4), n_boot=2000)
    assert lo < x.mean() < hi and hi - lo < 0.3


def test_ols_recovers_coefficients():
    rng = np.random.default_rng(5)
    x = rng.uniform(0, 1, 2000)
    y = 0.5 + 2.0 * x + rng.normal(0, 0.01, 2000)
    a, b = A.ols(x, y)
    assert abs(a - 0.5) < 0.01 and abs(b - 2.0) < 0.01


# --------------------------------------------------------------------------------------------
# information sets / no look-ahead
# --------------------------------------------------------------------------------------------
def test_visible_masks_the_future():
    O, C = synth(3, 6)
    Ov, Cv = A.visible(O, C, A.I1549)
    assert np.isfinite(Ov[:, :A.I1549 + 1]).all() and np.isnan(Ov[:, A.I1549 + 1:]).all()
    assert np.isfinite(Cv[:, :A.I1549]).all() and np.isnan(Cv[:, A.I1549:]).all()


def test_lookahead_selfcheck_passes_on_real_predictors():
    O, C = synth(50, 7)
    log = A.lookahead_selfcheck(O, C, np.random.default_rng(8))
    assert len(log) == len(A.PREDICTORS) + 1


def test_lookahead_selfcheck_catches_a_leaky_predictor():
    O, C = synth(50, 9)
    leaky = {"desc": "uses the 15:49 close", "fn": lambda O, C: np.sign(A.lr(O[..., A.I0930], C[..., A.I1549])),
             "entry": A.I1549, "target": "r_close"}
    A.PREDICTORS["LEAK"] = leaky
    try:
        A.lookahead_selfcheck(O, C, np.random.default_rng(10))
    except AssertionError as e:
        assert "LEAK" in str(e)
    else:
        raise AssertionError("leaky predictor was not caught")
    finally:
        del A.PREDICTORS["LEAK"]


def test_targets_start_at_or_after_entry():
    for name, spec in A.PREDICTORS.items():
        assert A.TARGETS[spec["target"]][0] >= spec["entry"], name


# --------------------------------------------------------------------------------------------
# H2 direction: planted effect detected, pure noise not
# --------------------------------------------------------------------------------------------
def test_planted_momentum_is_detected():
    n = 2000
    O, C = synth(n, 11, plant="P1", effect_bps=1.5)
    d, w = _dates(n)
    h = A.h2_test(O, C, d, w)
    p1 = h["full_sample"]["P1"]
    assert p1["mean_bps"] > 0 and p1["p_holm"] < 0.05 and p1["passes_direction"], p1
    assert abs(p1["mean_bps"] - 1.5) < 0.6, p1["mean_bps"]
    assert h["best_abs_t"]["predictor"] == "P1"
    assert p1["hit_rate"] > 0.5


def test_pure_noise_is_not_detected():
    n = 2000
    O, C = synth(n, 12)
    d, w = _dates(n)
    h = A.h2_test(O, C, d, w)
    for name, x in h["full_sample"].items():
        assert x["p_holm"] >= 0.05 and not x["passes_direction"], (name, x)


def test_noise_family_false_positive_rate_is_small():
    d, w = _dates(800)
    hits = 0
    for seed in range(100, 120):
        O, C = synth(800, seed)
        h = A.h2_test(O, C, d, w)
        hits += any(x["p_holm"] < 0.05 for x in h["full_sample"].values())
    assert hits <= 4, hits    # Holm controls the family-wise rate at 5% (expected ~1 of 20)


def test_planted_reversal_on_p3_gives_opposite_trade():
    n = 2000
    O, C = synth(n, 13, plant="P3", effect_bps=-1.5)
    d, w = _dates(n)
    h = A.h2_test(O, C, d, w)
    best = h["best_abs_t"]
    assert best["predictor"] == "P3" and best["nw_t"] < 0 and best["trade_sign_multiplier"] == -1
    # a positive P3 reading must then buy the put, a negative one the call
    assert A.s2_direction(best["nw_t"], +1.0) == -1
    assert A.s2_direction(best["nw_t"], -1.0) == +1
    # P = 0 -> the pre-registration's 'else ATM put'; undefined P -> None (no trade, excluded from the mean)
    assert A.s2_direction(best["nw_t"], 0.0) == -1
    assert A.s2_direction(+4.0, 0.0) == -1
    assert A.s2_direction(best["nw_t"], float("nan")) is None


# --------------------------------------------------------------------------------------------
# H1 size
# --------------------------------------------------------------------------------------------
def test_h1_detects_a_bigger_close_and_not_noise():
    O, C = synth(800, 14, close_vol_mult=2.0)
    h = A.h1_test(O, C, np.random.default_rng(15))
    for k in ("a_vs_1538_1549_window", "b_vs_same_day_median_window"):
        assert h[k]["passes"] and h[k]["ratio_of_means"] > 1.5, (k, h[k])
    O, C = synth(800, 16)
    h = A.h1_test(O, C, np.random.default_rng(17))
    for k in ("a_vs_1538_1549_window", "b_vs_same_day_median_window"):
        assert not h[k]["passes"], (k, h[k])
    assert h["n_days_full_339_windows"] == 800


def test_h1_window_definition():
    O, C = synth(2, 18)
    W = A.comparison_window_abs(O, C)
    assert W.shape == (2, 339)
    # first window: open 10:00 -> close 10:10; last: open 15:38 -> close 15:48
    assert np.allclose(W[:, 0], np.abs(np.log(C[:, A.mi("10:10")] / O[:, A.I1000])))
    assert np.allclose(W[:, -1], np.abs(np.log(C[:, A.I1548] / O[:, A.I1538])))


# --------------------------------------------------------------------------------------------
# option P&L arithmetic
# --------------------------------------------------------------------------------------------
def test_nearest_strike():
    assert A.nearest_strike(7710.93) == 7710.0
    assert A.nearest_strike(7712.6) == 7715.0
    assert A.nearest_strike(7712.5) == 7715.0   # tie rounds up
    assert A.nearest_strike(7707.49) == 7705.0


def test_s1_straddle_pnl_hand_computed():
    # S0 5002, K 5000, call mark 6.00, put mark 4.00, settle 5010.
    # entry = (6.00 + 0.10) + (4.00 + 0.10) = 10.20; payoff = 10 (call) + 0 (put) -> -0.20 points
    # $: 100 * -0.20 - 2 legs x $0.09 entry fee = -20.18
    r = A.straddle_pnl(5000.0, 6.0, 4.0, 5010.0, 0.10, 0.09)
    assert abs(r["pnl_points"] + 0.20) < 1e-9 and abs(r["pnl_usd"] + 20.18) < 1e-9, r
    # settle 4985: put pays 15 -> +4.80 points -> 480 - 0.18 = 479.82
    r = A.straddle_pnl(5000.0, 6.0, 4.0, 4985.0, 0.10, 0.09)
    assert abs(r["pnl_usd"] - 479.82) < 1e-9, r
    # sensitivity: half-spread 0.25 and fee 0.74 -> entry 10.50, payoff 10 -> -50 - 1.48 = -51.48
    r = A.straddle_pnl(5000.0, 6.0, 4.0, 5010.0, 0.25, 0.74)
    assert abs(r["pnl_usd"] + 51.48) < 1e-9, r


def test_s3_leg_sold_at_2x_and_held_to_settlement():
    # mark 1.00: target 2.00, reached on the second close -> sold at 2.00 - 0.10 = 1.90;
    # entry 1.10 -> +0.80 points -> $80 - 2 sides x 0.09 = 79.82
    r = A.target_exit_leg("call", 5005.0, 1.00, [1.2, 2.05, 0.4], 5000.0, 0.10, 0.09, 2.0)
    assert r["sold"] and r["hit_bar_offset"] == 1 and abs(r["pnl_usd"] - 79.82) < 1e-9, r
    # never reached: settlement intrinsic for a put K=4995 at 4990 = 5 -> 5 - 1.10 = 3.90 -> 390 - 0.09
    r = A.target_exit_leg("put", 4995.0, 1.00, [1.2, 1.9, np.nan], 4990.0, 0.10, 0.09, 2.0)
    assert not r["sold"] and abs(r["pnl_usd"] - 389.91) < 1e-9, r
    # sale price floored at zero for tiny marks
    r = A.target_exit_leg("call", 5030.0, 0.01, [0.02], 5000.0, 0.10, 0.09, 2.0)
    assert r["sold"] and abs(r["pnl_points"] + 0.11) < 1e-9, r


def test_intrinsic():
    assert A.intrinsic("call", 100.0, 103.5) == 3.5 and A.intrinsic("call", 100.0, 99.0) == 0.0
    assert A.intrinsic("put", 100.0, 96.0) == 4.0 and A.intrinsic("put", 100.0, 101.0) == 0.0


# --------------------------------------------------------------------------------------------
# implied vs realized
# --------------------------------------------------------------------------------------------
def test_implied_vs_realized_sign_and_null():
    n = 600
    rng = np.random.default_rng(19)
    O, C = synth(n, 20)
    # vary daily vol so the regression has something to fit
    scale = rng.uniform(0.5, 2.0, n)
    steps = np.log(C / O) * scale[:, None]
    b = np.concatenate([np.full((n, 1), math.log(5000.0)), np.cumsum(steps, axis=1) + math.log(5000.0)], axis=1)
    O, C = np.exp(b[:, :-1]), np.exp(b[:, 1:])
    d, _ = _dates(n, start="2023-01-02")
    test_days = list(d[-8:])
    probe = A.implied_vs_realized(d, O, C, [{"date": x, "S0": 5000.0, "implied_pts": 1.0} for x in test_days], rng,
                                  n_boot=300, fit_end=test_days[0])
    fair = {it["date"]: it["pred_regression_pts"] for it in probe["days"]}
    cheap = A.implied_vs_realized(d, O, C, [{"date": x, "S0": 5000.0, "implied_pts": 0.5 * fair[x]} for x in test_days],
                                  rng, n_boot=500, fit_end=test_days[0])
    assert cheap["size_premise_passes"], cheap["stat"]
    at_fair = A.implied_vs_realized(d, O, C, [{"date": x, "S0": 5000.0, "implied_pts": fair[x]} for x in test_days],
                                    rng, n_boot=500, fit_end=test_days[0])
    lo, hi = at_fair["stat"]["regression"]["boot95_pts"]
    assert lo < 0 < hi and not at_fair["size_premise_passes"], at_fair["stat"]


def test_realized_vol_uses_only_opens_up_to_t0():
    O, C = synth(5, 21)
    rv = A.realized_vol_to_t0(O)
    O2 = O.copy()
    O2[:, A.I1549 + 1:] *= 1.05
    assert np.array_equal(rv, A.realized_vol_to_t0(O2))
    manual = np.sqrt((np.log(O[:, 1:A.I1549 + 1] / O[:, :A.I1549]) ** 2).sum(axis=1))
    assert np.allclose(rv, manual)


# --------------------------------------------------------------------------------------------
# the written results obey the pass rule
# --------------------------------------------------------------------------------------------
def test_results_json_verdicts_follow_pass_rule():
    p = A.OUT_JSON
    if not p.exists():
        return
    res = json.loads(p.read_text())
    for s, v in res["verdicts"].items():
        expect = "CANDIDATE for forward paper logging" if (v["cond1"] is True and v["cond2"] is True) else "FAIL"
        assert v["verdict"] == expect, (s, v)
        if v["d2_days"] < 2:   # condition 2 needs a CI, impossible with fewer than 2 days
            assert v["cond2"] is None and "D2 test not run" in v["verdict_label"], (s, v)
    ivr = res["h3"]["implied_vs_realized"]
    if ivr["n_d2_days"] < 2:
        assert ivr["size_premise_passes"] is None and ivr["stat"] is None
    # the implied-vs-realized fit must end before the first D2 session (no look-ahead)
    assert ivr["fit_sample"]["last"] < res["d2"]["first"], ivr["fit_sample"]
    assert res["lookahead_selfcheck"]["passed"]


# --------------------------------------------------------------------------------------------
# audit-round additions
# --------------------------------------------------------------------------------------------
def test_block_indices_shape_and_contiguity():
    rng = np.random.default_rng(30)
    idx = A.block_indices(50, 20, rng, 7)
    assert idx.shape == (7, 50) and idx.min() >= 0 and idx.max() < 50
    # inside each block of 20 the indices are consecutive (mod n)
    for row in idx:
        for b0 in range(0, 40, 20):
            blk = row[b0:b0 + 20]
            assert np.all((np.diff(blk) % 50) == 1), blk
    iid = A.block_indices(50, 1, rng, 3)
    assert iid.shape == (3, 50)


def test_block_bootstrap_widens_ci_for_positively_autocorrelated_series():
    rng = np.random.default_rng(31)
    n = 1500
    e = rng.normal(size=n)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.6 * x[t - 1] + e[t]
    lo1, hi1 = A.boot_mean_ci(x, np.random.default_rng(32), n_boot=2000, block=1)
    lo20, hi20 = A.boot_mean_ci(x, np.random.default_rng(33), n_boot=2000, block=20)
    # long-run SD / iid SD = sqrt((1 + 0.6) / (1 - 0.6)) = 2 for an AR(1) with phi = 0.6
    assert 1.6 < (hi20 - lo20) / (hi1 - lo1) < 2.4, ((hi20 - lo20), (hi1 - lo1))


def test_implied_vs_realized_one_d2_day_is_not_evaluable():
    n = 400
    rng = np.random.default_rng(34)
    O, C = synth(n, 35)
    d, _ = _dates(n, start="2023-01-02")
    r = A.implied_vs_realized(d, O, C, [{"date": d[-1], "S0": 5000.0, "implied_pts": 0.01}], rng, n_boot=200,
                              fit_end=d[-30])
    assert r["stat"] is None and r["size_premise_passes"] is None and r["evaluable"] is False
    assert r["fit_sample"]["last"] < d[-30]
    assert "calibration_out_of_sample" in r and r["calibration_out_of_sample"]["n_days"] == 30
    r2 = A.implied_vs_realized(d, O, C, [{"date": d[-1], "S0": 5000.0, "implied_pts": 0.01},
                                         {"date": d[-2], "S0": 5000.0, "implied_pts": 0.01}], rng, n_boot=200,
                               fit_end=d[-30])
    assert r2["evaluable"] and r2["size_premise_passes"] is True   # implied far below any realized move


def test_verdict_row_is_three_valued():
    one = {"n_days": 1, "mean_usd": 500.0, "t_ci95_usd": None}
    v = A.verdict_row(True, "x", one)
    assert v["cond2"] is None and v["verdict"] == "FAIL" and "D2 test not run" in v["verdict_label"]
    many = {"n_days": 30, "mean_usd": 12.0, "t_ci95_usd": [-50.0, 74.0]}
    assert A.verdict_row(True, "x", many)["verdict"] == "CANDIDATE for forward paper logging"
    assert A.verdict_row(None, "x", many)["verdict"] == "FAIL"
    assert A.verdict_row(False, "x", many)["verdict"] == "FAIL"
    neg = {"n_days": 30, "mean_usd": -1.0, "t_ci95_usd": [-50.0, 48.0]}
    v = A.verdict_row(True, "x", neg)
    assert v["cond2"] is False and v["verdict_label"] == "FAIL"


def _synthetic_d2_day(spot=5002.0, settle=5010.0, nan_0930=False):
    sO = np.full(A.N_MIN, spot)
    sC = np.full(A.N_MIN, spot)
    sO[A.I1551] = spot - 1.0        # P3 = sign(15:50 -> 15:51) = -1
    if nan_0930:
        sO[A.I0930] = np.nan          # P1 undefined, outside the 15:19-15:59 completeness window
    else:
        sO[A.I0930] = spot - 10.0     # P1 = +1
    options = {}
    for k in np.arange(4970.0, 5035.0, 5.0):
        call = max(spot - k, 0.0) + 1.0
        put = call - (spot - k)       # exact put-call parity
        options[("call", float(k))] = (np.full(A.N_MIN, call), np.full(A.N_MIN, call))
        options[("put", float(k))] = (np.full(A.N_MIN, put), np.full(A.N_MIN, put))
    return {"spx_O": sO, "spx_C": sC, "settle": settle, "settle_src": ["synthetic"], "options": options, "weekday": "Mon"}


def test_parity_check_is_zero_on_consistent_marks():
    day = _synthetic_d2_day()
    pc = A.parity_check(day)
    x = pc["15:49"]
    assert x["n_strikes"] == 13 and abs(x["signed_dev_median"]) < 1e-9 and abs(x["abs_dev_max"]) < 1e-9


def test_undefined_s2_predictor_is_excluded_not_booked_as_zero():
    days = {"2026-10-20": _synthetic_d2_day(nan_0930=True)}
    ev = A.evaluate_d2(days, {"S2": ("P3", 1), "S2_alt": ("P1", 1)}, np.random.default_rng(36))
    base = "hs0.10_fee0.09"
    assert ev["summary"]["S1"][base]["n_days"] == 1
    assert ev["summary"]["S2"][base]["n_days"] == 1          # P3 defined -> put
    assert ev["per_day"]["2026-10-20"]["pnl"][base]["S2"]["kind"] == "put"
    assert ev["summary"]["S2_alt"][base]["n_days"] == 0      # P1 undefined -> excluded
    assert ev["summary"]["S2_alt"][base]["mean_usd"] is None


def main() -> int:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
