"""Validate D1 (Dukascopy USA500 CFD, cut to 09:30-15:59 ET) against SPY 1-minute bars on disk.

Pre-registration (preregistration/spx_1549_close.md): D1 is accepted only if, on overlap days,
corr(r_close D1, r_close SPY 1-min from data/bars_1m) >= 0.90 and the same for Robinhood SPX minute
bars. r_close = ln(close of the 15:59 bar / open of the 15:49 bar).

Sources compared (all labelled by ET bar START time, 09:30..15:59):
  spy_bars_1m      data/bars_1m/SPY_1m_2026-09.csv + SPY_1m_2026-10.csv   (required by the pre-reg)
  spy_yahoo_1m     data/yahoo_1m/SPY_1m.csv                               (extra check)
  spx_robinhood    data/spx_1549/d2_chunk_*_spx_1m.csv, interpolated bars removed (required by the
                   pre-reg; these files are written by the D2 workflow and read here only)
Also reported: corr of r(09:30 open -> 15:49 open), mean absolute difference in bps, and a
lead/lag check of 1-minute returns (lag 0 must be the best match, otherwise the bar clock is off).

Usage: .venv/bin/python -B backtests/spx_close_1549/validate_d1.py
"""

from __future__ import annotations

import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = Path("/Users/kv15/trading")
D1_CSV = ROOT / "data" / "spx_1549" / "d1_usa500_rth_1m.csv.gz"
OUT_JSON = HERE / "d1_validation.json"
NY = "America/New_York"
THRESHOLD = 0.90


def load_d1() -> pd.DataFrame:
    d = pd.read_csv(D1_CSV, dtype={"date": str, "time_et": str})
    return d[["date", "time_et", "open", "high", "low", "close"]]


def _from_ny_stamp(frame: pd.DataFrame, col: str) -> pd.DataFrame:
    ts = pd.to_datetime(frame[col], utc=True).dt.tz_convert(NY)
    out = pd.DataFrame({"date": ts.dt.strftime("%Y-%m-%d"), "time_et": ts.dt.strftime("%H:%M"),
                        "open": frame["open"].astype(float), "close": frame["close"].astype(float)})
    return out


def load_spy_bars_1m() -> tuple[pd.DataFrame, list[str]]:
    files = [ROOT / "data" / "bars_1m" / "SPY_1m_2026-09.csv", ROOT / "data" / "bars_1m" / "SPY_1m_2026-10.csv"]
    parts = []
    for f in files:
        raw = pd.read_csv(f)
        # timestamp_utc and timestamp_ny must agree; use the UTC column and convert
        a = pd.to_datetime(raw["timestamp_utc"], utc=True)
        b = pd.to_datetime(raw["timestamp_ny"], utc=True)
        if not (a == b).all():
            raise ValueError(f"{f}: timestamp_utc and timestamp_ny disagree")
        parts.append(_from_ny_stamp(raw, "timestamp_utc"))
    out = pd.concat(parts).drop_duplicates(["date", "time_et"], keep="last")
    return out, [str(f) for f in files]


def load_spy_yahoo() -> tuple[pd.DataFrame, list[str]]:
    f = ROOT / "data" / "yahoo_1m" / "SPY_1m.csv"
    raw = pd.read_csv(f)
    return _from_ny_stamp(raw, "timestamp_ny").drop_duplicates(["date", "time_et"], keep="last"), [str(f)]


def load_spx_robinhood() -> tuple[pd.DataFrame | None, list[str], int]:
    files = sorted(glob.glob(str(ROOT / "data" / "spx_1549" / "d2_chunk_*_spx_1m.csv")))
    if not files:
        return None, [], 0
    parts = []
    for f in files:
        raw = pd.read_csv(f, dtype={"date": str, "time_et": str})
        parts.append(raw)
    raw = pd.concat(parts, ignore_index=True)
    # cross-check the ET label against the UTC start time
    et = pd.to_datetime(raw["begins_at_utc"], utc=True).dt.tz_convert(NY)
    if not ((et.dt.strftime("%Y-%m-%d") == raw["date"]) & (et.dt.strftime("%H:%M") == raw["time_et"])).all():
        raise ValueError("Robinhood SPX: date/time_et disagree with begins_at_utc")
    interp = raw["interpolated"].astype(str).str.lower().eq("true")
    n_interp = int(interp.sum())
    real = raw.loc[~interp, ["date", "time_et", "open", "close"]].drop_duplicates(["date", "time_et"], keep="last")
    return real, files, n_interp


def day_returns(bars: pd.DataFrame) -> pd.DataFrame:
    """Per day: r_close = ln(close 15:59 / open 15:49), r_day = ln(open 15:49 / open 09:30)."""
    piv_open = bars.pivot(index="date", columns="time_et", values="open")
    piv_close = bars.pivot(index="date", columns="time_et", values="close")
    need = ["09:30", "15:49"]
    out = pd.DataFrame(index=piv_open.index)
    o0930 = piv_open.get("09:30")
    o1549 = piv_open.get("15:49")
    c1559 = piv_close.get("15:59")
    out["r_close"] = np.log(c1559 / o1549) if c1559 is not None and o1549 is not None else np.nan
    out["r_day"] = np.log(o1549 / o0930) if o0930 is not None and o1549 is not None else np.nan
    del need
    return out


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) < 3:
        return None
    return _corr(a.rank(), b.rank())


def compare_returns(d1r: pd.DataFrame, refr: pd.DataFrame, col: str) -> dict:
    j = d1r[[col]].join(refr[[col]], lsuffix="_d1", rsuffix="_ref", how="inner").dropna()
    a, b = j[f"{col}_d1"], j[f"{col}_ref"]
    if len(j) == 0:
        return {"n": 0}
    beta = float(np.polyfit(b, a, 1)[0]) if len(j) >= 3 and b.std() > 0 else None
    return {
        "n": int(len(j)),
        "corr": None if _corr(a, b) is None else round(_corr(a, b), 4),
        "spearman": None if _spearman(a, b) is None else round(_spearman(a, b), 4),
        "mean_abs_diff_bps": round(float((a - b).abs().mean() * 1e4), 3),
        "max_abs_diff_bps": round(float((a - b).abs().max() * 1e4), 3),
        "mean_abs_ref_bps": round(float(b.abs().mean() * 1e4), 3),
        "mean_abs_d1_bps": round(float(a.abs().mean() * 1e4), 3),
        "sign_agreement": round(float((np.sign(a) == np.sign(b)).mean()), 4),
        "slope_d1_on_ref": None if beta is None else round(beta, 4),
        "first_day": j.index.min(), "last_day": j.index.max(),
    }


def lead_lag(d1: pd.DataFrame, ref: pd.DataFrame, days: list[str], lags=(-2, -1, 0, 1, 2)) -> dict:
    """corr of 1-minute close-to-close log returns, D1 shifted by `lag` minutes vs the reference.
    lag = +1 means D1 bar t is compared with reference bar t+1."""
    out = {}
    a = d1[d1["date"].isin(days)].set_index(["date", "time_et"])["close"]
    b = ref[ref["date"].isin(days)].set_index(["date", "time_et"])["close"]
    j = pd.concat({"d1": a, "ref": b}, axis=1).dropna().reset_index()
    j = j.sort_values(["date", "time_et"])
    j["r_d1"] = np.log(j["d1"]).groupby(j["date"]).diff()
    j["r_ref"] = np.log(j["ref"]).groupby(j["date"]).diff()
    for lag in lags:
        shifted = j.groupby("date")["r_ref"].shift(-lag)
        k = pd.concat([j["r_d1"], shifted], axis=1).dropna()
        out[str(lag)] = None if len(k) < 10 else round(float(np.corrcoef(k.iloc[:, 0], k.iloc[:, 1])[0, 1]), 4)
    best = max((v, int(k)) for k, v in out.items() if v is not None)[1] if any(v is not None for v in out.values()) else None
    return {"corr_by_lag_minutes": out, "best_lag": best, "n_minutes_lag0": int(len(j.dropna(subset=["r_d1", "r_ref"])))}


def clock_check(d1: pd.DataFrame) -> dict:
    """Internal check of the bar clock in years with no reference data: scheduled US data releases
    at 10:00:00 ET (ISM, consumer sentiment, ...) should make the 10:00 bar the widest bar of
    09:45-10:15 on average, and the 09:30 bar should be wide at the cash open.
    Measure: mean (high - low) / close in bps per ET minute, by year."""
    d = d1.copy()
    d["range_bps"] = (d["high"] - d["low"]) / d["close"] * 1e4
    d["year"] = d["date"].str[:4]
    out = {}
    for year, grp in d.groupby("year"):
        prof = grp.groupby("time_et")["range_bps"].mean()
        win = prof.loc["09:45":"10:15"]
        others = win.drop("10:00", errors="ignore")
        top = prof.sort_values(ascending=False).head(3)
        out[year] = {
            "days": int(grp["date"].nunique()),
            "widest_bar_0945_1015": None if win.empty else win.idxmax(),
            "bar_1000_vs_median_0945_1015": None if "10:00" not in win or others.empty
            else round(float(win["10:00"] / others.median()), 2),
            "bar_0930_vs_median_0931_0959": None if "09:30" not in prof
            else round(float(prof["09:30"] / prof.loc["09:31":"09:59"].median()), 2),
            "widest_3_bars_of_day": {k: round(float(v), 2) for k, v in top.items()},
        }
    return out


def main() -> int:
    d1 = load_d1()
    d1r = day_returns(d1)
    results, required = {}, {}
    sources = {}
    spy, f1 = load_spy_bars_1m()
    sources["spy_bars_1m"] = (spy, f1, {"required_by_prereg": True})
    yah, f2 = load_spy_yahoo()
    sources["spy_yahoo_1m"] = (yah, f2, {"required_by_prereg": False})
    rh, f3, n_interp = load_spx_robinhood()
    if rh is not None:
        sources["spx_robinhood_d2"] = (rh, f3, {"required_by_prereg": True,
                                                 "interpolated_bars_removed": n_interp,
                                                 "note": "D2 chunk files written by the D2 workflow; "
                                                         "re-run this script once D2 is final."})
    for name, (bars, files, meta) in sources.items():
        refr = day_returns(bars)
        rc = compare_returns(d1r, refr, "r_close")
        rd = compare_returns(d1r, refr, "r_day")
        overlap = sorted(set(d1r.dropna().index) & set(refr.dropna().index))
        ll = lead_lag(d1, bars, overlap)
        passed = rc.get("corr") is not None and rc["corr"] >= THRESHOLD
        results[name] = {"files": files, **meta, "ref_days_complete": int(refr.dropna().shape[0]),
                         "r_close_1549_to_1559": rc, "r_0930_to_1549": rd,
                         "minute_return_lead_lag": ll, "passes_corr_0.90": bool(passed)}
        if meta["required_by_prereg"]:
            required[name] = bool(passed)
    if "spx_robinhood_d2" not in sources:
        required["spx_robinhood_d2"] = None
    accepted = all(v is True for v in required.values())
    report = {
        "rule": "D1 accepted only if corr(r_close D1, r_close ref) >= 0.90 for SPY (data/bars_1m) "
                "AND Robinhood SPX minute bars (preregistration/spx_1549_close.md)",
        "definitions": {"r_close": "ln(close of 15:59 ET bar / open of 15:49 ET bar)",
                        "r_0930_to_1549": "ln(open of 15:49 ET bar / open of 09:30 ET bar)"},
        "d1_file": str(D1_CSV),
        "d1_days": int(d1r.dropna().shape[0]),
        "sources": results,
        "required_checks": required,
        "d1_accepted": bool(accepted),
        "clock_check_by_year": clock_check(d1),
        "clock_check_note": "years without reference data: if the bar clock is right, the 10:00 bar "
                            "(10:00 ET data releases) is the widest bar of 09:45-10:15",
        "validated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))
    summary = {k: {"r_close": v["r_close_1549_to_1559"], "r_day_corr": v["r_0930_to_1549"].get("corr"),
                   "best_lag": v["minute_return_lead_lag"]["best_lag"]} for k, v in results.items()}
    print(json.dumps({"summary": summary, "required": required, "d1_accepted": accepted}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
