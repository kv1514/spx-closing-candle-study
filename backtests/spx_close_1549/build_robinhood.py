#!/usr/bin/env python
"""Parse saved Robinhood tool output (dataset D2) into tidy CSVs + integrity checks.

Pre-registration: preregistration/spx_1549_close.md (read-only, binding).

Raw layout (git-ignored), written by the collection agents:
  data/spx_1549/robinhood/raw/spx_daily_<CHUNK>.json        get_index_historicals(interval=day)
  data/spx_1549/robinhood/raw/<D>/spx_1m.json               get_index_historicals(interval=minute)
  data/spx_1549/robinhood/raw/<D>/instruments.csv           id,type,strike,expiration (0DTE SPXW)
  data/spx_1549/robinhood/raw/<D>/options_part{1,2,3}.json  get_option_historicals(interval=minute)

Outputs (nothing is dropped; the 'interpolated' flag is kept):
  data/spx_1549/d2_chunk_<CHUNK>_spx_1m.csv
  data/spx_1549/d2_chunk_<CHUNK>_options_1m.csv
  data/spx_1549/d2_chunk_<CHUNK>_checks.json

Usage:
  python -B backtests/spx_close_1549/build_robinhood.py --chunk A
  python -B backtests/spx_close_1549/build_robinhood.py --chunk B --dates 2026-09-21,2026-09-22
Without --dates, the chunk's trading days are the non-interpolated dates in raw/spx_daily_<CHUNK>.json
that also have a raw/<D>/ folder.
"""
import argparse
import csv
import glob
import json
import os
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = "/Users/kv15/trading"
DATA = os.path.join(ROOT, "data", "spx_1549")
RAW = os.path.join(DATA, "robinhood", "raw")
NY = ZoneInfo("America/New_York")
STRIKE_OFFSETS = list(range(-30, 31, 5))  # K0-30 .. K0+30, 13 strikes


def load_json(path):
    with open(path) as f:
        return json.load(f)


def results_of(obj):
    """Return the list of per-instrument result dicts from a saved tool output."""
    if isinstance(obj, dict) and "data" in obj:
        obj = obj["data"]
    if isinstance(obj, dict) and "results" in obj:
        return obj["results"]
    if isinstance(obj, list):
        return obj
    raise ValueError("unrecognised tool-output structure")


def pick(bar, field):
    for k in (f"{field}_price", f"{field}_value", field):
        if k in bar and bar[k] is not None:
            return float(bar[k])
    return None


def to_et(begins_at):
    t = datetime.fromisoformat(begins_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    return t, t.astimezone(NY)


def occ_symbol(root, expiration, typ, strike):
    ymd = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")
    cp = "C" if typ.lower().startswith("c") else "P"
    return f"{root}{ymd}{cp}{int(round(float(strike) * 1000)):08d}"


def chunk_dates(chunk):
    daily = os.path.join(RAW, f"spx_daily_{chunk}.json")
    bars = results_of(load_json(daily))[0]["bars"]
    days = sorted({b["begins_at"][:10] for b in bars if not b.get("interpolated")})
    return [d for d in days if os.path.isdir(os.path.join(RAW, d))]


def daily_map(chunk):
    out = {}
    path = os.path.join(RAW, f"spx_daily_{chunk}.json")
    if os.path.exists(path):
        for b in results_of(load_json(path))[0]["bars"]:
            if not b.get("interpolated"):
                out[b["begins_at"][:10]] = {"open": pick(b, "open"), "close": pick(b, "close")}
    return out


def parse_spx(day):
    path = os.path.join(RAW, day, "spx_1m.json")
    if not os.path.exists(path):
        return []
    rows = []
    for res in results_of(load_json(path)):
        for b in res["bars"]:
            utc, et = to_et(b["begins_at"])
            if et.strftime("%Y-%m-%d") != day:
                continue  # spans covering two days: keep only D
            rows.append({
                "date": day,
                "begins_at_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "time_et": et.strftime("%H:%M"),
                "open": pick(b, "open"), "high": pick(b, "high"),
                "low": pick(b, "low"), "close": pick(b, "close"),
                "interpolated": bool(b.get("interpolated", False)),
            })
    rows.sort(key=lambda r: r["begins_at_utc"])
    # de-duplicate identical timestamps (overlapping requests)
    seen, out = set(), []
    for r in rows:
        if r["begins_at_utc"] not in seen:
            seen.add(r["begins_at_utc"])
            out.append(r)
    return out


def parse_instruments(day):
    path = os.path.join(RAW, day, "instruments.csv")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def parse_options(day, instruments):
    rows = []
    for path in sorted(glob.glob(os.path.join(RAW, day, "options_part*.json"))):
        for res in results_of(load_json(path)):
            iid = res.get("instrument_id") or res.get("instrument") or res.get("id")
            meta = instruments.get(iid)
            if meta is None:
                raise ValueError(f"{day}: instrument {iid} in {path} missing from instruments.csv")
            occ = occ_symbol("SPXW", meta["expiration"], meta["type"], meta["strike"])
            for b in res.get("bars", []):
                utc, et = to_et(b["begins_at"])
                if et.strftime("%Y-%m-%d") != day:
                    continue
                rows.append({
                    "date": day,
                    "begins_at_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "time_et": et.strftime("%H:%M"),
                    "occ_symbol": occ,
                    "type": meta["type"],
                    "strike": float(meta["strike"]),
                    "open": pick(b, "open"), "high": pick(b, "high"),
                    "low": pick(b, "low"), "close": pick(b, "close"),
                    "interpolated": bool(b.get("interpolated", False)),
                })
    rows.sort(key=lambda r: (r["occ_symbol"], r["begins_at_utc"]))
    return rows


def spx_coverage(rows):
    real = {r["time_et"]: r for r in rows if not r["interpolated"]}

    def have(h0, m0, h1, m1):
        t, end = h0 * 60 + m0, h1 * 60 + m1
        while t <= end:
            if f"{t // 60:02d}:{t % 60:02d}" not in real:
                return False
            t += 1
        return True

    distinct_vals = sorted({r["open"] for r in rows if r["interpolated"]})
    return {
        "bars_total": len(rows),
        "bars_real": len(real),
        "first_real_et": min(real) if real else None,
        "last_real_et": max(real) if real else None,
        "real_1545_1559": have(15, 45, 15, 59),
        "real_1519_1559": have(15, 19, 15, 59),  # pre-reg drop rule
        "real_0930_1600": have(9, 30, 16, 0),
        "interpolated_distinct_values": distinct_vals[:5],
        "spx_open_1549": real["15:49"]["open"] if "15:49" in real else None,
    }


def parity_check(spx_open_1549, opt_rows):
    k0 = 5 * round(spx_open_1549 / 5.0)
    at = {}
    for r in opt_rows:
        if r["time_et"] == "15:49" and not r["interpolated"]:
            at[(r["type"].lower()[0], r["strike"])] = r["open"]
    devs, per_strike = [], []
    for off in STRIKE_OFFSETS:
        k = float(k0 + off)
        c, p = at.get(("c", k)), at.get(("p", k))
        dev = None if c is None or p is None else c - p - (spx_open_1549 - k)
        if dev is not None:
            devs.append(abs(dev))
        per_strike.append({"strike": k, "call_open": c, "put_open": p,
                           "dev": None if dev is None else round(dev, 4)})
    return {
        "K0": k0,
        "contracts_real_at_1549": len(at),
        "strikes_with_both_legs": len(devs),
        "parity_abs_dev_median": round(statistics.median(devs), 4) if devs else None,
        "parity_abs_dev_max": round(max(devs), 4) if devs else None,
        "per_strike": per_strike,
    }


def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in cols})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", required=True)
    ap.add_argument("--dates", default=None, help="comma-separated YYYY-MM-DD; default from spx_daily_<chunk>.json")
    a = ap.parse_args()
    days = a.dates.split(",") if a.dates else chunk_dates(a.chunk)
    daily = daily_map(a.chunk)

    spx_all, opt_all, checks = [], [], {"chunk": a.chunk, "generated_utc":
                                         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                         "days": []}
    for day in days:
        spx = parse_spx(day)
        inst = parse_instruments(day)
        opts = parse_options(day, inst) if inst else []
        cov = spx_coverage(spx)
        entry = {"date": day, "spx": cov, "official": daily.get(day),
                 "instruments": len(inst),
                 "option_contracts_with_bars": len({r["occ_symbol"] for r in opts})}
        if cov["spx_open_1549"] is not None and opts:
            entry["parity_1549"] = parity_check(cov["spx_open_1549"], opts)
        else:
            entry["parity_1549"] = None
            entry["note"] = ("no real SPX minute bar at 15:49; option pulls skipped"
                             if cov["spx_open_1549"] is None else "no option bars parsed")
        checks["days"].append(entry)
        spx_all += spx
        opt_all += opts

    spx_cols = ["date", "begins_at_utc", "time_et", "open", "high", "low", "close", "interpolated"]
    opt_cols = ["date", "begins_at_utc", "time_et", "occ_symbol", "type", "strike",
                "open", "high", "low", "close", "interpolated"]
    write_csv(os.path.join(DATA, f"d2_chunk_{a.chunk}_spx_1m.csv"), spx_all, spx_cols)
    write_csv(os.path.join(DATA, f"d2_chunk_{a.chunk}_options_1m.csv"), opt_all, opt_cols)
    with open(os.path.join(DATA, f"d2_chunk_{a.chunk}_checks.json"), "w") as f:
        json.dump(checks, f, indent=1)

    print("date        real_1m  real1545-59  K0     n@1549  par_med  par_max")
    for e in checks["days"]:
        p = e["parity_1549"] or {}
        print(f"{e['date']}  {e['spx']['bars_real']:7d}  {str(e['spx']['real_1545_1559']):11s}  "
              f"{str(p.get('K0')):5s}  {str(p.get('contracts_real_at_1549')):6s}  "
              f"{str(p.get('parity_abs_dev_median')):7s}  {p.get('parity_abs_dev_max')}")
    print(f"rows: spx={len(spx_all)} options={len(opt_all)}")


if __name__ == "__main__":
    main()
