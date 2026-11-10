#!/usr/bin/env python
"""Chunk B (2026-09-21 .. 2026-10-06) of dataset D2 (Robinhood): tidy CSVs + integrity checks.

Pre-registration: preregistration/spx_1549_close.md (read-only, binding).

The shared parser lives in build_robinhood.py (written by the chunk-A agent); this script reuses its
helpers so all chunks produce identical formats, and adds what chunk B needs:
  * an explicit date list (raw/spx_daily_B.json spans 2025-09..2026-10, so it cannot define the chunk);
  * a SUPPLEMENTARY, NOT PRE-REGISTERED 10-minute option dataset. For every chunk-B day, Robinhood's
    1-minute (and 5-minute, 15-second) option history for these expired 0DTE contracts is 100%
    interpolated gap-fill (no real bars at all), while 10-minute/hour/day bars are real. The 10-minute
    bars are parsed into d2_chunk_B_options_10m.csv and checked with put-call parity at the 10-minute
    boundaries around t0, so whoever runs H3 can decide whether (and how) they may be used.

Raw inputs (git-ignored) under data/spx_1549/robinhood/raw/:
  spx_daily_B.json, <D>/spx_1m.json, <D>/instruments.csv,
  <D>/options_part{1,2,3}.json      get_option_historicals(interval=minute)   13:30Z-20:01Z
  <D>/options_10m_part{1,2,3}.json  get_option_historicals(interval=10minute) part3 starts at D-3 13:30Z
                                    (so the tool result was saved to a file); rows not on D are dropped.
Outputs (nothing dropped from the 1-minute data; 'interpolated' kept):
  data/spx_1549/d2_chunk_B_spx_1m.csv
  data/spx_1549/d2_chunk_B_options_1m.csv
  data/spx_1549/d2_chunk_B_options_10m.csv   (supplementary)
  data/spx_1549/d2_chunk_B_checks.json

Usage: .venv/bin/python -B backtests/spx_close_1549/build_robinhood_B.py
"""
import glob
import json
import os
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_robinhood as br  # noqa: E402

CHUNK = "B"
DAYS = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28",
        "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"]
RAW, DATA = br.RAW, br.DATA


def parse_options_10m(day, instruments):
    rows = []
    for path in sorted(glob.glob(os.path.join(RAW, day, "options_10m_part*.json"))):
        for res in br.results_of(br.load_json(path)):
            meta = instruments[res["instrument_id"]]
            assert res.get("interval") == "10minute", (path, res.get("interval"))
            occ = br.occ_symbol("SPXW", meta["expiration"], meta["type"], meta["strike"])
            for b in res.get("bars", []):
                utc, et = br.to_et(b["begins_at"])
                if et.strftime("%Y-%m-%d") != day:
                    continue
                rows.append({
                    "date": day, "begins_at_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "time_et": et.strftime("%H:%M"), "occ_symbol": occ, "type": meta["type"],
                    "strike": float(meta["strike"]),
                    "open": br.pick(b, "open"), "high": br.pick(b, "high"),
                    "low": br.pick(b, "low"), "close": br.pick(b, "close"),
                    "interpolated": bool(b.get("interpolated", False)),
                })
    rows.sort(key=lambda r: (r["occ_symbol"], r["begins_at_utc"]))
    return rows


def parity_10m(rows, spx_real, k0, bar_et, field, spx_et, spx_field):
    """C - P - (S - K) on 10-minute option bars; S from the 1-minute SPX bar spx_et/spx_field."""
    if spx_et not in spx_real:
        return None
    s = spx_real[spx_et][spx_field]
    at = {(r["type"][0], r["strike"]): r[field] for r in rows
          if r["time_et"] == bar_et and not r["interpolated"]}
    devs = []
    for off in br.STRIKE_OFFSETS:
        k = float(k0 + off)
        if ("c", k) in at and ("p", k) in at:
            devs.append(at[("c", k)] - at[("p", k)] - (s - k))
    if not devs:
        return {"n_strikes": 0}
    a = [abs(d) for d in devs]
    return {"option_bar_et": bar_et, "option_field": field, "spx": f"{spx_et} {spx_field}", "S": s,
            "n_strikes": len(devs), "abs_dev_median": round(statistics.median(a), 4),
            "abs_dev_max": round(max(a), 4), "signed_dev_median": round(statistics.median(devs), 4)}


def main():
    daily = br.daily_map(CHUNK)
    checks = {"chunk": CHUNK, "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "notes": [
                  "1-minute option bars: every bar of every contract on every chunk-B day is "
                  "interpolated=true (constant gap-fill value), so the pre-registered 15:49-open parity "
                  "check has no data; parity_1549 reports contracts_real_at_1549 = 0.",
                  "Probes (raw/probes_B): interval minute, 5minute and auto (15second) are all "
                  "interpolated; 10minute, hour and day bars are real.",
                  "supplementary_10m is NOT pre-registered. 10-minute bars are left-labelled; the bar "
                  "beginning 15:40 ET covers 15:40:00-15:49:59, so its close is roughly the 15:49 "
                  "close / 15:50 open, not the pre-registered t0 (15:49 open).",
              ], "days": []}
    spx_all, opt_all, opt10_all = [], [], []
    for day in DAYS:
        spx = br.parse_spx(day)
        inst = br.parse_instruments(day)
        opts = br.parse_options(day, inst) if inst else []
        opts10 = parse_options_10m(day, inst) if inst else []
        cov = br.spx_coverage(spx)
        spx_real = {r["time_et"]: r for r in spx if not r["interpolated"]}
        off = daily.get(day)
        entry = {"date": day, "spx": cov, "official": off,
                 "spx_1600_bar": ({k: spx_real["16:00"][k] for k in ("open", "close")}
                                  if "16:00" in spx_real else None),
                 "spx_1559_close_minus_official_close": (
                     round(spx_real["15:59"]["close"] - off["close"], 4)
                     if off and "15:59" in spx_real else None),
                 "instruments": len(inst),
                 "option_contracts_with_bars_1m": len({r["occ_symbol"] for r in opts}),
                 "option_bars_1m_total": len(opts),
                 "option_bars_1m_real": sum(1 for r in opts if not r["interpolated"])}
        if cov["spx_open_1549"] is not None and opts:
            entry["parity_1549"] = br.parity_check(cov["spx_open_1549"], opts)
            if entry["parity_1549"]["contracts_real_at_1549"] == 0:
                entry["note"] = "all 1-minute option bars interpolated; no real option marks at 15:49"
        else:
            entry["parity_1549"] = None
            entry["note"] = ("no real SPX minute bar at 15:49; option pulls skipped"
                             if cov["spx_open_1549"] is None else "no option bars parsed")
        if cov["spx_open_1549"] is not None and opts10:
            k0 = 5 * round(cov["spx_open_1549"] / 5.0)
            entry["supplementary_10m"] = {
                "contracts": len({r["occ_symbol"] for r in opts10}),
                "bars_on_day": len(opts10),
                "bars_real_on_day": sum(1 for r in opts10 if not r["interpolated"]),
                "contracts_real_1540_bar": len({r["occ_symbol"] for r in opts10
                                                if r["time_et"] == "15:40" and not r["interpolated"]}),
                "parity_1530_close_vs_spx_1539_close": parity_10m(opts10, spx_real, k0, "15:30", "close", "15:39", "close"),
                "parity_1540_open_vs_spx_1540_open": parity_10m(opts10, spx_real, k0, "15:40", "open", "15:40", "open"),
                "parity_1540_close_vs_spx_1549_close": parity_10m(opts10, spx_real, k0, "15:40", "close", "15:49", "close"),
                "parity_1550_open_vs_spx_1550_open": parity_10m(opts10, spx_real, k0, "15:50", "open", "15:50", "open"),
            }
        checks["days"].append(entry)
        spx_all += spx
        opt_all += opts
        opt10_all += opts10

    spx_cols = ["date", "begins_at_utc", "time_et", "open", "high", "low", "close", "interpolated"]
    opt_cols = ["date", "begins_at_utc", "time_et", "occ_symbol", "type", "strike",
                "open", "high", "low", "close", "interpolated"]
    br.write_csv(os.path.join(DATA, f"d2_chunk_{CHUNK}_spx_1m.csv"), spx_all, spx_cols)
    br.write_csv(os.path.join(DATA, f"d2_chunk_{CHUNK}_options_1m.csv"), opt_all, opt_cols)
    br.write_csv(os.path.join(DATA, f"d2_chunk_{CHUNK}_options_10m.csv"), opt10_all, opt_cols)
    with open(os.path.join(DATA, f"d2_chunk_{CHUNK}_checks.json"), "w") as f:
        json.dump(checks, f, indent=1)

    print("date        spx_real 1545-59  K0    1m_real@1549  par_med par_max | 10m: 15:40open med/max  15:40close med/max  15:50open med/max")
    for e in checks["days"]:
        p = e["parity_1549"] or {}
        s = e.get("supplementary_10m") or {}

        def mm(key):
            q = s.get(key) or {}
            return f"{q.get('abs_dev_median')}/{q.get('abs_dev_max')}"
        print(f"{e['date']}  {e['spx']['bars_real']:4d}  {str(e['spx']['real_1545_1559']):5s}  "
              f"{str(p.get('K0')):5s} {str(p.get('contracts_real_at_1549')):3s}  "
              f"{str(p.get('parity_abs_dev_median')):5s} {str(p.get('parity_abs_dev_max')):5s} | "
              f"{mm('parity_1540_open_vs_spx_1540_open'):>12s}  {mm('parity_1540_close_vs_spx_1549_close'):>12s}  "
              f"{mm('parity_1550_open_vs_spx_1550_open'):>12s}")
    print(f"rows: spx={len(spx_all)} options_1m={len(opt_all)} "
          f"(real {sum(1 for r in opt_all if not r['interpolated'])}) options_10m={len(opt10_all)}")


if __name__ == "__main__":
    main()
