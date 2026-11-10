"""Download CNBC's archived one-minute SPX index bars for 15:45-16:00 ET, one small JSON file per session.

This is the same free endpoint the live alert reads (tools/spx_1550_alert.py). For dates before March 2026 the
endpoint often answers with no bars and then, asked again, with the full session, so one request is not enough.
`--fill N` asks again, up to N times a session, alternating a 15:45-16:00 window and a full-session window, and
keeps the first answer that contains a 15:50 bar. Each file records how many requests it took and which window
answered. `--recheck K` re-downloads K sessions that already have bars and reports whether the 15:50 bar's four
prices came back the same (a consistency check on levels only; it writes nothing).

`--symbol SPY --out cnbc_spy_1m` downloads another symbol into its own folder. The SPX archive in cnbc_1m/ is
frozen by preregistration/spx_candle_realindex.md, so the script refuses to write there again.

Run from the repository root:
  .venv/bin/python -B backtests/spx_candle_realindex/fetch_cnbc.py --start 2019-01-01 --end 2026-10-20
Output: data/spx_1549/cnbc_1m/YYYY-MM-DD.json  ->  {"date":..., "fetched_at_utc":..., "bars": {"15:50": [o,h,l,c], ...}}
"""
import argparse, csv, importlib.util, json, sys, time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "spx_1549" / "cnbc_1m"
spec = importlib.util.spec_from_file_location("alert", ROOT / "tools" / "spx_1550_alert.py")
alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alert)


def sessions(start, end):
    with open(ROOT / "data/spx_1549/d1_days.csv", newline="") as f:
        return [r["date"] for r in csv.DictReader(f) if start <= r["date"] <= end and r["calendar"] == "full"]


WINDOWS = (("1545", "1600"), ("0930", "1600"))


SYMBOL = ".SPX"
URL = "https://ts-api.cnbc.com/harmony/app/bars/{sym}/1M/{d}{a}00/{d}{b}00/adjusted/EST5EDT.json"


def ask(d, a, b):
    """{HH:MM: [o, h, l, c]} for 15:45-15:59 of session d, parsed exactly as the live alert parses its bars."""
    j = alert.http_json(URL.format(sym=SYMBOL, d=d.replace("-", ""), a=a, b=b))
    out = {}
    for x in (j.get("barData") or {}).get("priceBars") or []:
        t = x["tradeTime"]                                      # YYYYMMDDHHMMSS, exchange time, the minute's start
        if f"{t[:4]}-{t[4:6]}-{t[6:8]}" == d and "1545" <= t[8:12] <= "1559":
            out[f"{t[8:10]}:{t[10:12]}"] = [float(x[k]) for k in ("open", "high", "low", "close")]
    return out


def fill(start, end, attempts, gap):
    """Ask again for every session that has no 15:50 bar yet."""
    days = sessions(start, end)
    need = []
    for d in days:
        p = OUT / f"{d}.json"
        if not p.exists() or "15:50" not in json.load(open(p))["bars"]:
            need.append(d)
    print(f"fill: {len(need)} of {len(days)} sessions lack a 15:50 bar", flush=True)
    filled = still = 0
    for i, d in enumerate(need):
        p = OUT / f"{d}.json"
        prior = json.load(open(p)).get("requests", 1) if p.exists() else 0
        bars, used, n = {}, None, 0
        for n in range(1, attempts + 1):
            a, b = WINDOWS[n % 2]
            try:
                bars = ask(d, a, b)
            except Exception:
                bars = {}
            if "15:50" in bars:
                used = f"{a}-{b}"
                break
            time.sleep(gap)
        json.dump({"date": d, "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "requests": prior + n, "window": used, "bars": bars if used else {}}, open(p, "w"))
        filled += bool(used)
        still += not used
        if (i + 1) % 100 == 0:
            print(f"fill {i + 1}/{len(need)} filled {filled} still empty {still}", flush=True)
        time.sleep(gap)
    print(f"fill done: needed {len(need)} filled {filled} still empty {still}", flush=True)


def recheck(start, end, k, gap, seed=20261109):
    """Download k sessions that already have a 15:50 bar again and compare that bar's four prices."""
    import random
    have = [d for d in sessions(start, end) if (OUT / f"{d}.json").exists() and "15:50" in json.load(open(OUT / f"{d}.json"))["bars"]]
    random.Random(seed).shuffle(have)
    same = diff = unanswered = exact = 0
    for d in sorted(have[:k]):
        old = json.load(open(OUT / f"{d}.json"))["bars"]["15:50"]
        new = None
        for n in range(1, 9):
            try:
                new = ask(d, *WINDOWS[n % 2]).get("15:50")
            except Exception:
                new = None
            if new:
                break
            time.sleep(gap)
        if new is not None and list(new) == list(old):
            exact += 1
        if new is None:
            unanswered += 1
        elif [int(round(x * 100)) for x in new] == [int(round(x * 100)) for x in old]:
            same += 1
        else:
            diff += 1
            print("DIFFERENT", d, old, new, flush=True)
        time.sleep(gap)
    print(f"recheck: sessions {min(k, len(have))} equal in whole cents {same} (exactly equal {exact}) different {diff} "
          f"unanswered {unanswered}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--retry-empty", action="store_true")
    ap.add_argument("--gap", type=float, default=0.35)
    ap.add_argument("--fill", type=int, default=0, help="ask up to N times for sessions without a 15:50 bar")
    ap.add_argument("--recheck", type=int, default=0, help="re-download K sessions and compare the 15:50 bar")
    ap.add_argument("--symbol", default=".SPX")
    ap.add_argument("--out", default="cnbc_1m", help="folder under data/spx_1549/")
    a = ap.parse_args()
    global SYMBOL, OUT
    SYMBOL, OUT = a.symbol, ROOT / "data" / "spx_1549" / a.out
    if (a.symbol == ".SPX") != (a.out == "cnbc_1m"):
        raise SystemExit("the SPX archive lives in cnbc_1m and nothing else does")
    if a.out == "cnbc_1m" and not a.recheck and (ROOT / "preregistration" / "spx_candle_realindex.md").exists():
        raise SystemExit("cnbc_1m is frozen by preregistration/spx_candle_realindex.md; it is not downloaded again")
    OUT.mkdir(parents=True, exist_ok=True)
    if a.fill:
        return fill(a.start, a.end, a.fill, a.gap)
    if a.recheck:
        return recheck(a.start, a.end, a.recheck, a.gap)
    days = sessions(a.start, a.end)
    got = empty = failed = skipped = 0
    for i, d in enumerate(days):
        p = OUT / f"{d}.json"
        if p.exists():
            old = json.load(open(p))
            if old["bars"] or not a.retry_empty:
                skipped += 1
                continue
        bars = None
        for attempt in range(3):
            try:
                bars = ask(d, "1545", "1600")
                break
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
        if bars is None:
            failed += 1
            print(d, "FAILED", err, flush=True)
            continue
        json.dump({"date": d, "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "bars": bars},
                  open(p, "w"))
        got += bool(bars)
        empty += not bars
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(days)} got {got} empty {empty} failed {failed} skipped {skipped}", flush=True)
        time.sleep(a.gap)
    print(f"done: sessions {len(days)} got {got} empty {empty} failed {failed} skipped {skipped}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
