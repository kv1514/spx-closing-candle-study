"""Assign each list stock's listing exchange on each signal day from free NYSE record counts (pre-lock check 3).

NYSE's XNYS.PILLAR imbalance feed carries records only for NYSE-listed stocks (free counts: JPM, XOM and BRK B have
hundreds of records between 15:50 and 16:00; AAPL, MSFT and SPY have none). Nasdaq's XNAS.ITCH counts are a flat
330 per requested symbol, listed there or not, so they cannot show the listing. Rule: a stock is NYSE-listed on a
day if its XNYS.PILLAR record count for 15:50-16:00 that day is above 0, otherwise it is requested from Nasdaq.
Counts are taken on the first and last signal day of each year; if they disagree, a binary search over that year's
signal days finds the switch. Tickers: isin_tickers.csv, '/' as '.', NAME_MAP for the three ISINs OpenFIGI did not
map, Facebook as FB before 2022-06-09 and META from then (META was a different security, an ETF, from 2021-06-30
until then). NYSE spells Berkshire's class B 'BRK B', Nasdaq 'BRK.B'.
Writes venues.csv (year, isin, name, from, to, venue, raw_symbol) and venue_counts.json. Metadata only, $0.
"""
import csv
import importlib.util
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dbx", HERE.parents[1] / "tools" / "databento_spxw.py")
dbx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbx)
ET = ZoneInfo("America/New_York")
NAME_MAP = {"IE00BZ12WP82": "LIN", "US30231G1022": "XOM", "US4385161066": "HON"}
FB_ISIN, META_FROM = "US30303M1027", "2022-06-09"


def ns(d, t):
    return int(datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=ET).timestamp() * 1e9)


def ticker(isin, day, figi):
    if isin == FB_ISIN:
        return "FB" if day < META_FROM else "META"
    return (figi[isin] or NAME_MAP[isin]).replace("/", ".")


def raw(sym, venue):
    return sym.replace(".", " ") if venue == "XNYS.PILLAR" else sym


cache = {}


def nyse_count(sym, day):
    k = (sym, day)
    if k not in cache:
        cache[k] = int(dbx.call("metadata.get_record_count", {
            "dataset": "XNYS.PILLAR", "symbols": raw(sym, "XNYS.PILLAR"), "schema": "imbalance",
            "start": ns(day, "15:50:00"), "end": ns(day, "16:00:00"), "stype_in": "raw_symbol"}))
    return cache[k]


def main():
    figi = {r["isin"]: r["tickers"] for r in csv.DictReader(open(HERE / "isin_tickers.csv"))}
    lists = defaultdict(list)
    for r in csv.DictReader(open(HERE / "stock_lists_raw.csv")):
        lists[int(r["year"])].append((r["isin"], r["name"]))
    sig = defaultdict(list)
    for r in csv.DictReader(open(HERE / "signal_days.csv")):
        sig[int(r["date"][:4])].append(r["date"])
    out = []
    for y in sorted(lists):
        days = sig[y]
        for isin, name in lists[y]:
            def is_nyse(i):
                return nyse_count(ticker(isin, days[i], figi), days[i]) > 0
            first, last = is_nyse(0), is_nyse(len(days) - 1)
            segs = []
            if first == last and not (isin == FB_ISIN and y == 2022):
                segs.append((days[0], days[-1], first))
            elif isin == FB_ISIN and y == 2022:          # rename inside the year: check each side separately
                for part in ([d for d in days if d < META_FROM], [d for d in days if d >= META_FROM]):
                    i0, i1 = days.index(part[0]), days.index(part[-1])
                    a, b = is_nyse(i0), is_nyse(i1)
                    assert a == b, (isin, part[0], part[-1])
                    segs.append((part[0], part[-1], a))
            else:                                       # listing switch: first index where the answer changes
                lo, hi = 0, len(days) - 1
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if is_nyse(mid) == first:
                        lo = mid
                    else:
                        hi = mid
                segs += [(days[0], days[lo], first), (days[hi], days[-1], last)]
            for a, b, nyse in segs:
                v = "XNYS.PILLAR" if nyse else "XNAS.ITCH"
                out.append({"year": y, "isin": isin, "name": name, "from": a, "to": b, "venue": v,
                            "raw_symbol": raw(ticker(isin, a, figi), v)})
        print(y, "NYSE", sum(1 for o in out if o["year"] == y and o["venue"] == "XNYS.PILLAR"), "Nasdaq",
              sum(1 for o in out if o["year"] == y and o["venue"] == "XNAS.ITCH"), "segments", flush=True)
    with open(HERE / "venues.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    (HERE / "venue_counts.json").write_text(json.dumps({f"{s}|{d}": n for (s, d), n in sorted(cache.items())},
                                                       indent=0) + "\n")
    multi = defaultdict(list)
    for o in out:
        multi[(o["year"], o["isin"])].append(o)
    for k, v in multi.items():
        if len(v) > 1:
            print("split:", k, [(o["from"], o["to"], o["venue"], o["raw_symbol"]) for o in v])


if __name__ == "__main__":
    main()
