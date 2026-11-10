#!/usr/bin/env python
"""Chunk C (2026-10-07 .. 2026-10-20): parse saved Robinhood tool output (dataset D2) into tidy CSVs + checks.

Pre-registration: preregistration/spx_1549_close.md (read-only, binding). Self-contained on purpose (another
agent owns build_robinhood.py); output formats match it, plus a supplementary 10-minute option file.

Raw inputs (git-ignored, data/spx_1549/robinhood/raw/):
  spx_daily_C.json                    get_index_historicals(interval=day), 2026-10-06..2026-10-20
  <D>/spx_1m.json                     get_index_historicals(interval=minute), 13:30Z-20:01Z
  <D>/instruments.csv                 id,type,strike,expiration  (written by the collection step, not included)
  <D>/options_part{1,2,3}.json        get_option_historicals(interval=minute), 13:30Z-20:01Z
  <D>/options_10m_part{1,2,3}.json    get_option_historicals(interval=10minute) - supplementary, see below

Why the 10-minute files exist: for every expired 0DTE contract older than the latest session, Robinhood
returns minute (and 5-minute / 15-second) bars that are ALL interpolated=true and flat at one value, i.e. no
minute history. 10-minute, 30-minute and hourly bars are still real. The pre-registered entry is the open of
the 15:49 one-minute bar, which 10-minute bars cannot give. The 10-minute data are collected only so the
orchestrator can decide (and label) any fallback; nothing here substitutes them into the pre-registered tests.

Outputs (nothing dropped; interpolated flag kept):
  data/spx_1549/d2_chunk_C_spx_1m.csv
  data/spx_1549/d2_chunk_C_options_1m.csv
  data/spx_1549/d2_chunk_C_options_10m.csv   (supplementary)
  data/spx_1549/d2_chunk_C_checks.json

Usage: /Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/build_robinhood_C.py
"""
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
CHUNK = "C"
DAYS = ["2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13",
        "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]
OFFSETS = list(range(-30, 31, 5))


def load(path):
    with open(path) as f:
        return json.load(f)


def results_of(obj):
    return obj["data"]["results"]


def pick(bar, field):
    for k in (f"{field}_price", f"{field}_value"):
        if bar.get(k) is not None:
            return float(bar[k])
    return None


def to_et(begins_at):
    utc = datetime.fromisoformat(begins_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    return utc, utc.astimezone(NY)


def occ_symbol(expiration, typ, strike):
    ymd = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")
    return f"SPXW{ymd}{'C' if typ.startswith('c') else 'P'}{int(round(float(strike) * 1000)):08d}"


def parse_spx(day):
    rows, seen = [], set()
    for res in results_of(load(os.path.join(RAW, day, "spx_1m.json"))):
        assert res["symbol"] == "SPX", res["symbol"]
        for b in res["bars"]:
            utc, et = to_et(b["begins_at"])
            if et.strftime("%Y-%m-%d") != day or b["begins_at"] in seen:
                continue
            seen.add(b["begins_at"])
            rows.append({"date": day, "begins_at_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "time_et": et.strftime("%H:%M"), "open": pick(b, "open"), "high": pick(b, "high"),
                         "low": pick(b, "low"), "close": pick(b, "close"),
                         "interpolated": bool(b.get("interpolated", False))})
    rows.sort(key=lambda r: r["begins_at_utc"])
    return rows


def parse_instruments(day):
    with open(os.path.join(RAW, day, "instruments.csv")) as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def parse_options(day, inst, pattern, problems):
    rows, seen_ids = [], set()
    for path in sorted(glob.glob(os.path.join(RAW, day, pattern))):
        for res in results_of(load(path)):
            iid = res["instrument_id"]
            meta = inst.get(iid)
            if meta is None:
                raise ValueError(f"{day}: {iid} in {path} not in instruments.csv")
            occ = occ_symbol(meta["expiration"], meta["type"], meta["strike"])
            rh_occ = res.get("occ_symbol", "").replace(" ", "")
            if rh_occ != occ:  # independent check of the id -> (type, strike, expiry) mapping
                problems.append(f"{day} {os.path.basename(path)}: occ mismatch {rh_occ} vs {occ}")
            seen_ids.add(iid)
            for b in res["bars"]:
                utc, et = to_et(b["begins_at"])
                if et.strftime("%Y-%m-%d") != day:
                    continue  # some 10m part3 requests span the previous session too
                rows.append({"date": day, "begins_at_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "time_et": et.strftime("%H:%M"), "occ_symbol": occ, "type": meta["type"],
                             "strike": float(meta["strike"]), "open": pick(b, "open"),
                             "high": pick(b, "high"), "low": pick(b, "low"), "close": pick(b, "close"),
                             "interpolated": bool(b.get("interpolated", False))})
    missing = set(inst) - seen_ids
    if missing:
        problems.append(f"{day} {pattern}: {len(missing)} instruments without a result")
    rows.sort(key=lambda r: (r["occ_symbol"], r["begins_at_utc"]))
    return rows


def spx_coverage(rows):
    real = {r["time_et"]: r for r in rows if not r["interpolated"]}

    def have(a, b):
        t0, t1 = int(a[:2]) * 60 + int(a[3:]), int(b[:2]) * 60 + int(b[3:])
        return all(f"{t // 60:02d}:{t % 60:02d}" in real for t in range(t0, t1 + 1))

    return {"bars_total": len(rows), "bars_real": len(real),
            "first_real_et": min(real) if real else None, "last_real_et": max(real) if real else None,
            "real_0930_1600": have("09:30", "16:00"), "real_1519_1559": have("15:19", "15:59"),
            "real_1545_1559": have("15:45", "15:59"),
            "spx_open_1549": real["15:49"]["open"] if "15:49" in real else None,
            "spx_close_1549": real["15:49"]["close"] if "15:49" in real else None,
            "spx_open_1550": real["15:50"]["open"] if "15:50" in real else None,
            "spx_close_1559": real["15:59"]["close"] if "15:59" in real else None,
            "spx_1600_open_close": [real["16:00"]["open"], real["16:00"]["close"]] if "16:00" in real else None}


def parity(spot, k0, quotes):
    """quotes: {(c|p, strike): price}. Returns per-strike C - P - (S - K)."""
    devs, per = [], []
    for off in OFFSETS:
        k = float(k0 + off)
        c, p = quotes.get(("c", k)), quotes.get(("p", k))
        d = None if c is None or p is None else c - p - (spot - k)
        if d is not None:
            devs.append(d)
        per.append({"strike": k, "call": c, "put": p, "dev": None if d is None else round(d, 4)})
    a = [abs(x) for x in devs]
    return {"spot": spot, "K0": k0, "strikes_with_both_legs": len(devs),
            "abs_dev_median": round(statistics.median(a), 4) if a else None,
            "abs_dev_max": round(max(a), 4) if a else None,
            "signed_dev_median": round(statistics.median(devs), 4) if devs else None,
            "per_strike": per}


def quotes_at(rows, time_et, field):
    return {(r["type"][0], r["strike"]): r[field] for r in rows
            if r["time_et"] == time_et and not r["interpolated"]}


def flatness(rows):
    """For all-interpolated minute series: are they a single constant value per contract?"""
    by = {}
    for r in rows:
        by.setdefault(r["occ_symbol"], set()).add((r["open"], r["high"], r["low"], r["close"]))
    return {"contracts": len(by), "contracts_single_constant_value": sum(1 for v in by.values() if len(v) == 1)}


def tenmin_vs_1m(rows1, rows10):
    """Consistency of 10m bars with the 1m bars they aggregate (only meaningful where 1m bars are real)."""
    m1 = {(r["occ_symbol"], r["time_et"]): r for r in rows1 if not r["interpolated"]}
    n = open_eq = close_eq = hi_ok = lo_ok = 0
    for r in rows10:
        h, m = int(r["time_et"][:2]), int(r["time_et"][3:])
        mins = [f"{(h * 60 + m + i) // 60:02d}:{(h * 60 + m + i) % 60:02d}" for i in range(10)]
        sub = [m1.get((r["occ_symbol"], t)) for t in mins]
        if any(s is None for s in sub):
            continue
        n += 1
        open_eq += abs(sub[0]["open"] - r["open"]) < 1e-9
        close_eq += abs(sub[-1]["close"] - r["close"]) < 1e-9
        hi_ok += abs(max(s["high"] for s in sub) - r["high"]) < 1e-9
        lo_ok += abs(min(s["low"] for s in sub) - r["low"]) < 1e-9
    return {"bars_compared": n, "open_equal": open_eq, "close_equal": close_eq,
            "high_equal": hi_ok, "low_equal": lo_ok}


def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in cols})


def main():
    daily = {b["begins_at"][:10]: b for b in results_of(load(os.path.join(RAW, "spx_daily_C.json")))[0]["bars"]
             if not b.get("interpolated")}
    spx_all, o1_all, o10_all = [], [], []
    checks = {"chunk": CHUNK, "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "notes": [
                  "parity_1549 = pre-registered check: open of the 15:49 ET one-minute bar, C - P - (S - K), "
                  "S = SPX open of the 15:49 bar; only real (non-interpolated) bars are used.",
                  "parity_10m_proxy_* = descriptive only, NOT the pre-registered t0: (a) close of the 10m option "
                  "bar 15:40-15:50 vs SPX close of the 15:49 1m bar; (b) open of the 10m bar 15:50-16:00 vs SPX "
                  "open of the 15:50 1m bar. Option bars are Robinhood prices with no volume; open of a bar is "
                  "not the previous close, so they look like sampled trade/mark prints, not a clean mid.",
                  "Minute option bars for every chunk-C day except 2026-10-20 came back 100% interpolated and "
                  "flat (one constant per contract): Robinhood keeps no minute history for these expired "
                  "contracts; 10-minute/30-minute/hour bars are real (see raw/probes_C)."],
              "problems": [], "days": []}
    for day in DAYS:
        spx = parse_spx(day)
        inst = parse_instruments(day)
        o1 = parse_options(day, inst, "options_part[0-9].json", checks["problems"])
        o10 = parse_options(day, inst, "options_10m_part[0-9].json", checks["problems"])
        cov = spx_coverage(spx)
        d = daily.get(day)
        first = next((r for r in spx if not r["interpolated"]), None)
        official = None
        if d:
            official = {"open": float(d["open_value"]), "close": float(d["close_value"]),
                        "high": float(d["high_value"]), "low": float(d["low_value"]),
                        "open_minus_first_1m_open": None if first is None else round(float(d["open_value"]) - first["open"], 4),
                        "close_minus_1600_bar_close": None if not cov["spx_1600_open_close"] else
                        round(float(d["close_value"]) - cov["spx_1600_open_close"][1], 4)}
        k0 = None if cov["spx_open_1549"] is None else 5 * round(cov["spx_open_1549"] / 5.0)
        q1549 = quotes_at(o1, "15:49", "open")
        entry = {"date": day, "spx": cov, "official": official, "K0": k0, "instruments": len(inst),
                 "option_1m": {"rows": len(o1), "rows_real": sum(not r["interpolated"] for r in o1),
                               "contracts_real_at_1549": len(q1549), **flatness([r for r in o1 if r["interpolated"]])},
                 "option_10m": {"rows": len(o10), "rows_real": sum(not r["interpolated"] for r in o10),
                                "contracts": len({r["occ_symbol"] for r in o10})}}
        entry["parity_1549"] = parity(cov["spx_open_1549"], k0, q1549) if (k0 and q1549) else None
        if k0 and cov["spx_close_1549"] is not None:
            entry["parity_10m_proxy_a_1540bar_close_vs_spx_1549_close"] = parity(
                cov["spx_close_1549"], k0, quotes_at(o10, "15:40", "close"))
        if k0 and cov["spx_open_1550"] is not None:
            entry["parity_10m_proxy_b_1550bar_open_vs_spx_1550_open"] = parity(
                cov["spx_open_1550"], k0, quotes_at(o10, "15:50", "open"))
        if entry["option_1m"]["rows_real"]:
            entry["tenmin_vs_1m_consistency"] = tenmin_vs_1m(o1, o10)
        checks["days"].append(entry)
        spx_all += spx
        o1_all += o1
        o10_all += o10

    spx_cols = ["date", "begins_at_utc", "time_et", "open", "high", "low", "close", "interpolated"]
    opt_cols = ["date", "begins_at_utc", "time_et", "occ_symbol", "type", "strike",
                "open", "high", "low", "close", "interpolated"]
    write_csv(os.path.join(DATA, "d2_chunk_C_spx_1m.csv"), spx_all, spx_cols)
    write_csv(os.path.join(DATA, "d2_chunk_C_options_1m.csv"), o1_all, opt_cols)
    write_csv(os.path.join(DATA, "d2_chunk_C_options_10m.csv"), o10_all, opt_cols)
    with open(os.path.join(DATA, "d2_chunk_C_checks.json"), "w") as f:
        json.dump(checks, f, indent=1)

    print("date        spx_real  1545-59  K0    1m_real@1549  par_med  par_max | 10m proxyA med/max | proxyB med/max")
    for e in checks["days"]:
        p = e["parity_1549"] or {}
        a = e.get("parity_10m_proxy_a_1540bar_close_vs_spx_1549_close") or {}
        b = e.get("parity_10m_proxy_b_1550bar_open_vs_spx_1550_open") or {}
        print(f"{e['date']}  {e['spx']['bars_real']:8d}  {str(e['spx']['real_1545_1559']):7s}  {e['K0']}  "
              f"{e['option_1m']['contracts_real_at_1549']:12d}  {str(p.get('abs_dev_median')):7s}  "
              f"{str(p.get('abs_dev_max')):7s} | {a.get('abs_dev_median')}/{a.get('abs_dev_max')} "
              f"| {b.get('abs_dev_median')}/{b.get('abs_dev_max')}")
    print("official:", [(e["date"], e["official"]["open_minus_first_1m_open"],
                         e["official"]["close_minus_1600_bar_close"]) for e in checks["days"]])
    print("flatness:", [(e["date"], e["option_1m"]["contracts_single_constant_value"]) for e in checks["days"]])
    print("10m vs 1m:", [(e["date"], e.get("tenmin_vs_1m_consistency")) for e in checks["days"]
                         if e.get("tenmin_vs_1m_consistency")])
    print("problems:", checks["problems"])
    print(f"rows: spx={len(spx_all)} options_1m={len(o1_all)} options_10m={len(o10_all)}")


if __name__ == "__main__":
    main()
