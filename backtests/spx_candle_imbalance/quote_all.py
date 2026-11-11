"""Exact free cost quote for the planned pull (pre-lock check 4): every signal day, two requests (the day's
NYSE-listed list stocks on XNYS.PILLAR, the rest on XNAS.ITCH, from venues.csv), schema imbalance,
15:50:00-16:00:00 ET. Writes quote_manifest.json (per day and dataset: symbols, quoted cost). Metadata only, $0.
"""
import csv
import importlib.util
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dbx", HERE.parents[1] / "tools" / "databento_spxw.py")
dbx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbx)
ET = ZoneInfo("America/New_York")


def ns(d, t):
    return int(datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=ET).timestamp() * 1e9)


def day_requests():
    segs = list(csv.DictReader(open(HERE / "venues.csv")))
    days = [r["date"] for r in csv.DictReader(open(HERE / "signal_days.csv"))]
    reqs = []
    for d in days:
        by = defaultdict(list)
        for s in segs:
            if s["from"] <= d <= s["to"]:
                by[s["venue"]].append(s["raw_symbol"])
        n = sum(len(v) for v in by.values())
        assert n == 50, (d, n)
        for ds in ("XNYS.PILLAR", "XNAS.ITCH"):
            reqs.append((d, ds, sorted(by[ds])))
    return reqs


def quote(req):
    d, ds, syms = req
    if not syms:
        return d, ds, syms, 0.0
    c = float(dbx.call("metadata.get_cost", {"dataset": ds, "symbols": ",".join(syms), "schema": "imbalance",
                                              "start": ns(d, "15:50:00"), "end": ns(d, "16:00:00"),
                                              "stype_in": "raw_symbol"}))
    return d, ds, syms, c


def main():
    reqs = day_requests()
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(quote, reqs))
    man = defaultdict(dict)
    for d, ds, syms, c in res:
        man[d][ds] = {"symbols": syms, "quoted_cost_usd": c}
    tot = {ds: sum(c for _, x, _, c in res if x == ds) for ds in ("XNYS.PILLAR", "XNAS.ITCH")}
    out = {"window_et": ["15:50:00", "16:00:00"], "schema": "imbalance", "n_days": len(man),
           "total_usd": sum(tot.values()), "by_dataset_usd": tot, "days": man}
    (HERE / "quote_manifest.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "days"}, indent=1))


if __name__ == "__main__":
    main()
