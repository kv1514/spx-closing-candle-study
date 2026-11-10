"""Synthetic checks for scan.py.

pytest is not installed in .venv, so this file runs with plain Python:
    PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B backtests/spx_candle_scan/tests/test_scan.py

Checks
  1. a planted candle effect is found in discovery and confirmed in the holdout (in memory, and end to end
     through the real file pipeline: discover -> hash -> holdout);
  2. pure noise yields Holm passes no more often than the 5% family-wise rate (full pipeline and with 8
     forced candidates), and single one-sided tests reject at about 5%;
  3. the hash gate refuses an edited, re-whitespaced or missing candidate file, before any data is read;
  4. no holdout date reaches discovery (the streamed loader stops at the first post-2020 row and never parses
     it; the guard rejects a panel that holds a holdout date); the real discovery.json agrees.
  5. (post-audit) the option-P&L identity and markup tipping points, the vectorised NW, the zero-move hit
     rate, run archiving with old -> new, and the abort when discovery is no longer reproduced.
Temporary files go to tests/_tmp_<pid> (inside the scan folder) and are removed afterwards.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import gzip  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import scan as S  # noqa: E402

TMP = HERE / f"_tmp_{os.getpid()}"
RESULTS = {}          # every number printed below is also written to tests/test_results.json


# --------------------------------------------------------------------------------------------
# synthetic data
# --------------------------------------------------------------------------------------------
def synth_arrays(n_days: int, seed: int, sigma: float = 3e-4, plants=()):
    """Continuous log-price random walk, 390 one-minute bars a day, open of bar m = close of bar m-1 within
    the day, overnight gap between days. plants: (feature id, effect_bps) pairs; each adds
    effect_bps x signal, spread evenly over the bars from the feature's entry bar to 15:59, which does
    not change the signal itself (it only touches bars >= entry)."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, sigma, (n_days, S.N_MIN))
    gaps = rng.normal(0.0, 3e-3, n_days)
    wick_h = np.abs(rng.normal(0.0, sigma / 2, (n_days, S.N_MIN)))
    wick_l = np.abs(rng.normal(0.0, sigma / 2, (n_days, S.N_MIN)))

    def build(st):
        start = math.log(4000.0) + np.cumsum(gaps + np.r_[0.0, st.sum(axis=1)[:-1]])
        b = np.concatenate([start[:, None], start[:, None] + np.cumsum(st, axis=1)], axis=1)
        O, C = np.exp(b[:, :-1]), np.exp(b[:, 1:])
        H = np.maximum(O, C) * np.exp(wick_h)
        L = np.minimum(O, C) * np.exp(-wick_l)
        return O, H, L, C

    def panel(O, H, L, C, dates):
        po = np.r_[np.nan, O[:-1, 0]]
        pc = np.r_[np.nan, C[:-1, S.I1559]]
        return S.Panel(np.asarray(dates, dtype=object), O, H, L, C, po, pc, {})

    O, H, L, C = build(steps)
    dummy = np.array([f"2014-01-{i:02d}" for i in range(n_days)], dtype=object)
    for fid, eff in plants:
        f = S.spec_by_id(fid)
        sig = f.signal(panel(O, H, L, C, dummy))
        e = S.mi(f.entry)
        steps[:, e:] += (eff * 1e-4 / (S.N_MIN - e)) * np.nan_to_num(sig)[:, None]
        O2, H2, L2, C2 = build(steps)
        assert np.array_equal(f.signal(panel(O2, H2, L2, C2, dummy)), sig, equal_nan=True)
        O, H, L, C = O2, H2, L2, C2
    return O, H, L, C, panel


def synth_panel(n_days: int, seed: int, start: str, plants=()) -> S.Panel:
    O, H, L, C, panel = synth_arrays(n_days, seed, plants=plants)
    dates = pd.bdate_range(start, periods=n_days).strftime("%Y-%m-%d").to_numpy()
    return panel(O, H, L, C, dates)


def write_files(folder: Path, dates, O, H, L, C, corrupt_after: str | None = None, holidays=()):
    """Write a D1-style bar file (gzip CSV) and day table. If corrupt_after is given, every row dated
    after it has a non-numeric open (a loader that parses it fails)."""
    folder.mkdir(parents=True, exist_ok=True)
    dates = [str(d) for d in dates]
    holidays = [str(d) for d in holidays]
    bars = folder / "bars.csv.gz"
    days = folder / "days.csv"
    times = [S.hhmm(k) for k in range(S.N_MIN)]
    with gzip.open(bars, "wt", newline="") as f:
        f.write("date,time_et,open,high,low,close,ticked\n")
        for i, d in enumerate(dates):
            bad = corrupt_after is not None and d > corrupt_after
            for k in range(S.N_MIN):
                o = "NOT_A_NUMBER" if bad else f"{O[i, k]:.4f}"
                f.write(f"{d},{times[k]},{o},{H[i, k]:.4f},{L[i, k]:.4f},{C[i, k]:.4f},1\n")
    allrows = sorted([(d, "full", "True") for d in dates] + [(d, "nyse_holiday", "False") for d in holidays])
    with open(days, "w") as f:
        f.write("date,weekday,calendar,keep\n")
        for d, cal, k in allrows:
            f.write(f"{d},{pd.Timestamp(d).strftime('%a')},{cal},{k}\n")
    return bars, days


def _expect_raises(exc_type, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc_type as e:
        return e
    raise AssertionError(f"{fn.__name__} did not raise {exc_type.__name__}")


# --------------------------------------------------------------------------------------------
# 1. planted effect
# --------------------------------------------------------------------------------------------
def test_planted_effect_in_memory():
    plants = (("F1_1m_15:40", 3.0), ("F2_1m_1550_strong_body", -4.0))
    Pd = synth_panel(1500, 11, "2013-03-01", plants)
    Ph = synth_panel(1200, 12, "2021-01-04", plants)
    disc, cands = S.discover_core(Pd)
    got = {c["feature"]: c["direction"] for c in cands}
    assert got.get("F1_1m_15:40") == 1, got
    assert got.get("F2_1m_1550_strong_body") == -1, got
    assert len(cands) <= S.MAX_CANDIDATES
    res = S.holdout_tests(Ph, cands)
    rows = {r["feature"]: r for r in res["rows"]}
    for fid in ("F1_1m_15:40", "F2_1m_1550_strong_body"):
        assert rows[fid]["passes_holm_5pct"], rows[fid]
        assert rows[fid]["hit_rate"] > 0.5
    # the same candles rebuilt at 11:49/11:51 carry no planted effect
    for r in S.placebo(Ph, cands):
        if r["feature"] in ("F1_1m_15:40", "F2_1m_1550_strong_body"):
            assert abs(r["nw_t"]) < 3.5, r
    RESULTS["planted_in_memory"] = {"plants": plants, "candidates": got,
                                    "holdout": {k: {"nw_t": rows[k]["nw_t"], "p_holm": rows[k]["p_holm"]}
                                                for k in ("F1_1m_15:40", "F2_1m_1550_strong_body")}}
    print(f"planted (in memory): candidates {got}; holdout t "
          f"{rows['F1_1m_15:40']['nw_t']:.1f} / {rows['F2_1m_1550_strong_body']['nw_t']:.1f}, both pass Holm")


def test_planted_effect_end_to_end():
    """Real pipeline on files: discover (streamed loader, freeze, hash) then holdout (gate, tests)."""
    folder = TMP / "e2e"
    hol = ("2020-12-25", "2021-01-01")
    dates = pd.bdate_range("2018-01-02", "2023-12-29").strftime("%Y-%m-%d").to_numpy()
    dates = np.array([d for d in dates if d not in hol])
    O, H, L, C, _ = synth_arrays(len(dates), 21, plants=(("F1_1m_15:40", 4.0),))
    bars, days = write_files(folder / "data", dates, O, H, L, C, holidays=hol)
    out = folder / "out"
    d = S.run_discover(out, bars, days)
    assert d["data"]["max_date"] <= S.DISCOVERY[1] and not d["data"]["holdout_dates_present"]
    assert d["data"]["stopped_at_first_row_dated"] == "2021-01-04"
    cands = {c["feature"]: c["direction"] for c in d["candidates"]}
    assert cands.get("F1_1m_15:40") == 1, cands
    sha1 = S.sha256_file(out / S.CAND_FILE)
    # re-running discovery keeps the frozen file byte-for-byte
    d2 = S.run_discover(out, bars, days)
    assert S.sha256_file(out / S.CAND_FILE) == sha1 and d2["freeze"]["action"].startswith("existing")
    h = S.run_holdout(out, bars, days, crosscheck=False)
    rows = {r["feature"]: r for r in h["holdout_test"]["rows"]}
    assert rows["F1_1m_15:40"]["passes_holm_5pct"], rows["F1_1m_15:40"]
    assert h["data"]["holdout"]["first"] >= S.HOLDOUT[0]
    # post-audit provenance: a second holdout run archives the first and reports old -> new (nothing changes)
    assert d2.get("rerun_vs_previous_run", {}).get("same_candidates") is True
    h2 = S.run_holdout(out, bars, days, crosscheck=False)
    rr = h2["rerun_vs_previous_run"]
    assert rr is not None and rr["n_changed"] == 0 and rr["n_compared"] > 10, rr and rr["changed_keys"]
    assert Path(rr["previous_file_archived_to"]).exists()
    # ... and the holdout step aborts if the current code no longer reproduces the frozen discovery
    dj = out / S.DISC_FILE
    good = dj.read_bytes()
    j = json.loads(good)
    j["features"][0]["nw_t"] += 0.1
    dj.write_text(json.dumps(j))
    e = _expect_raises(RuntimeError, S.run_holdout, out, bars, days, False)
    assert "does not reproduce" in str(e)
    dj.write_bytes(good)
    # first holdout day gets its prior close from the last discovery day (2020-12-31)
    RESULTS["planted_end_to_end"] = {"candidates": cands, "holdout_nw_t": rows["F1_1m_15:40"]["nw_t"],
                                     "holdout_p_holm": rows["F1_1m_15:40"]["p_holm"],
                                     "discovery_stopped_at": d["data"]["stopped_at_first_row_dated"]}
    print(f"planted (end to end): candidates {cands}; holdout t {rows['F1_1m_15:40']['nw_t']:.1f}, "
          f"Holm p {rows['F1_1m_15:40']['p_holm']:.2g}")


# --------------------------------------------------------------------------------------------
# 2. pure noise
# --------------------------------------------------------------------------------------------
def test_noise_rates(n_sims: int = 200):
    rng = np.random.default_rng(7)
    feats = [f.fid for f in S.feature_specs()]
    any_pass_pipeline = 0
    n_with_cands = 0
    any_pass_forced = 0
    single_reject, single_n = 0, 0
    for i in range(n_sims):
        Pd = synth_panel(700, 1000 + i, "2013-03-01")
        Ph = synth_panel(700, 5000 + i, "2021-01-04")
        _, cands = S.discover_core(Pd)
        if cands:
            n_with_cands += 1
            res = S.holdout_tests(Ph, cands)
            any_pass_pipeline += res["n_pass_holm"] > 0
        pick = rng.choice(len(feats), 8, replace=False)
        forced = [{"feature": feats[j], "direction": int(rng.choice([-1, 1]))} for j in pick]
        res = S.holdout_tests(Ph, forced)
        any_pass_forced += res["n_pass_holm"] > 0
        single_reject += sum(r["p_one_sided"] < 0.05 for r in res["rows"])
        single_n += len(res["rows"])
    r_pipe = any_pass_pipeline / n_sims
    r_forced = any_pass_forced / n_sims
    r_single = single_reject / single_n
    RESULTS["noise"] = {"n_sims": n_sims, "panel_days_each_half": 700, "sims_with_discovery_candidates": n_with_cands,
                        "share_sims_any_holm_pass_pipeline": r_pipe, "share_sims_any_holm_pass_8_forced": r_forced,
                        "single_one_sided_rejection_rate": r_single, "n_single_tests": single_n}
    print(f"noise: {n_sims} sims; sims with >= 1 discovery candidate {n_with_cands}; any Holm pass "
          f"(pipeline) {r_pipe:.3f}; any Holm pass (8 forced) {r_forced:.3f}; single one-sided rejection "
          f"{r_single:.3f} of {single_n}")
    # binomial(200, 0.05) exceeds 16 with probability < 2%; the pipeline rate is below 5% by design
    assert r_pipe <= 0.08, r_pipe
    assert r_forced <= 0.08, r_forced
    assert 0.025 <= r_single <= 0.085, r_single


# --------------------------------------------------------------------------------------------
# 3. hash gate
# --------------------------------------------------------------------------------------------
def test_hash_gate():
    out = TMP / "gate"
    out.mkdir(parents=True, exist_ok=True)
    payload = {"candidates": [{"feature": "F1_1m_15:40", "direction": 1}], "n_candidates": 1}
    S.write_frozen(out, payload)
    assert S.verify_gate(out)["candidates"]["candidates"][0]["direction"] == 1
    cp = out / S.CAND_FILE
    original = cp.read_bytes()
    # (a) flipped direction
    cp.write_bytes(original.replace(b'"direction": 1', b'"direction": -1'))
    _expect_raises(S.HashGateError, S.verify_gate, out)
    # (b) whitespace-only edit
    cp.write_bytes(original + b"\n")
    _expect_raises(S.HashGateError, S.verify_gate, out)
    # (c) the holdout step refuses before reading any data (a missing data file would raise a different error)
    e = _expect_raises(S.HashGateError, S.run_holdout, out, TMP / "no_such_file.csv.gz", TMP / "no_days.csv", False)
    assert "refusing" in str(e)
    # (d) missing hash file
    cp.write_bytes(original)
    S.verify_gate(out)
    (out / S.SHA_FILE).unlink()
    _expect_raises(S.HashGateError, S.verify_gate, out)
    print("hash gate: edited, re-whitespaced and unhashed candidate files are refused before any data is read")


# --------------------------------------------------------------------------------------------
# 4. no holdout date in discovery
# --------------------------------------------------------------------------------------------
def test_no_holdout_in_discovery():
    folder = TMP / "split"
    dates = pd.bdate_range("2020-12-14", "2021-01-15").strftime("%Y-%m-%d").to_numpy()
    dates = np.array([d for d in dates if d not in ("2020-12-25", "2021-01-01")])
    O, H, L, C, _ = synth_arrays(len(dates), 3)
    bars, days = write_files(folder, dates, O, H, L, C, corrupt_after=S.DISCOVERY[1],
                             holidays=("2020-12-25", "2021-01-01"))
    P = S.load_panel(S.DISCOVERY[0], S.DISCOVERY[1], bars, days)    # would fail if a 2021 row were parsed
    assert len(P.dates) and P.dates.max() <= S.DISCOVERY[1]
    assert not (P.dates >= S.HOLDOUT[0]).any()
    assert P.meta["stopped_at_first_row_dated"] == "2021-01-04"
    S.assert_no_holdout(P.dates)
    # control: the holdout window does parse those rows, so the corrupt values are really there
    _expect_raises(ValueError, S.load_panel, S.HOLDOUT[0], S.HOLDOUT[1], bars, days)
    # the guard and the discovery core reject a panel that holds a holdout date
    leaked = synth_panel(30, 4, "2020-12-01")
    assert leaked.dates.max() >= S.HOLDOUT[0]
    _expect_raises(AssertionError, S.assert_no_holdout, leaked.dates)
    _expect_raises(AssertionError, S.discover_core, leaked)
    # the real discovery output (if present) was built from discovery days only
    real = HERE.parent / S.DISC_FILE
    if real.exists():
        j = json.loads(real.read_text())
        assert j["data"]["max_date"] <= S.DISCOVERY[1]
        assert j["data"]["holdout_dates_present"] is False
        assert j["data"]["stopped_at_first_row_dated"] >= S.HOLDOUT[0]
        assert all(r["n"] + r["n_undefined"] == j["data"]["n_days"] for r in j["features"])
    print("split: discovery loader stops at the first post-2020 row without parsing it; guard rejects leaks")


def test_lookahead_selfcheck_on_synthetic():
    P = synth_panel(60, 5, "2016-01-04")
    S.lookahead_selfcheck(P)
    S.lookahead_selfcheck(P, S.PLACEBO_SHIFT)
    print("look-ahead: all 42 signals depend only on data before their entry (also at the placebo shift)")


def test_stats_helpers():
    assert np.allclose(S.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
    assert np.allclose(S.bh_q([0.01, 0.04, 0.03, 0.5]), [0.04, 0.0533333333, 0.0533333333, 0.5])
    lo, hi = S.wilson(55, 100)
    assert abs(lo - 0.4524) < 1e-3 and abs(hi - 0.6438) < 1e-3
    assert S.n_needed_prop(0.5, 0.5) is None and S.n_needed_mean(-1.0, 1.0) is None
    assert S.n_needed_prop(0.55, 0.5) == 617
    m = S.min_hit_rate_accurate(644, 0.5)
    k = round(m * 644)
    assert S.wilson(k, 644)[0] > 0.5 >= S.wilson(k - 1, 644)[0]
    print("stats helpers: Holm, BH, Wilson and sample-size formulas check out")


def test_economics_identity_and_helpers():
    """Post-audit: option-P&L identity, markup tipping points, vectorised NW, zero-move hit rate."""
    P = synth_panel(400, 9, "2021-01-04", plants=(("F2_1m_1550_strong_body", 3.0),))
    f = S.spec_by_id("F2_1m_1550_strong_body")
    e = S.economics(P, f.signal(P), f.entry, 1)
    for fee in S.FEES:
        fc = e["fee_cases"][f"fee_{fee:.2f}"]
        ot = fc["option_pnl_test"]
        assert abs(ot["mean_usd"] - ot["identity_usd_0.5_x_mean_signed_move_minus_spread_and_fee"]) < 1e-9
        m0 = fc["markup_where_mean_pnl_is_zero"]
        cost0 = 0.5 * m0 * e["mean_abs_move_all"] + S.HALF_SPREAD + fee / S.MULT
        assert abs(e["share_correct_incl_zero_moves"] * e["mean_abs_move_correct_days"] - cost0) < 1e-9
        mk = S.markup_for_breakeven(e, 0.53, fee)
        be = (0.5 * mk * e["mean_abs_move_all"] + S.HALF_SPREAD + fee / S.MULT) / e["mean_abs_move_correct_days"]
        assert abs(be - 0.53) < 1e-12
    Y = np.random.default_rng(1).standard_t(4, (5, 300))
    assert np.allclose(S.nw_t_rows(Y), [S.nw_mean_test(y)["t"] for y in Y])
    st = S.summarize(np.array([1, 1, -1, 0, 1.0]), np.array([0.001, 0.0, -0.002, 0.003, -0.001]))
    assert st["n_trades"] == 4 and st["n_hit_days"] == 3 and st["n_hits"] == 2
    assert abs(st["hit_rate"] - 2 / 3) < 1e-12 and abs(st["hit_rate_zero_target_as_miss"] - 0.5) < 1e-12
    RESULTS["economics_identity"] = {"mean_pnl_usd_fee_0.09": e["fee_cases"]["fee_0.09"]["option_pnl_test"]["mean_usd"],
                                     "markup_zero_pnl_fee_0.09": e["fee_cases"]["fee_0.09"]["markup_where_mean_pnl_is_zero"]}
    print("economics: option P&L = 0.5 x signed move - extras; markup tipping points; NW rows == scalar NW")


def main() -> int:
    t0 = time.time()
    tests = [test_stats_helpers, test_economics_identity_and_helpers, test_lookahead_selfcheck_on_synthetic,
             test_no_holdout_in_discovery, test_hash_gate, test_planted_effect_in_memory,
             test_planted_effect_end_to_end, test_noise_rates]
    failed = 0
    try:
        for t in tests:
            try:
                t()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    RESULTS["summary"] = {"n_tests": len(tests), "n_failed": failed, "runtime_s": round(time.time() - t0, 1)}
    (HERE / "test_results.json").write_text(json.dumps(S._clean(RESULTS), indent=1) + "\n")
    print(f"{len(tests) - failed}/{len(tests)} passed in {time.time() - t0:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
