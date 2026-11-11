"""Free Databento symbology checks for the stock lists (plan section 5, pre-lock check 3).

For each year, each list position and each dataset (XNYS.PILLAR, XNAS.ITCH), resolve the candidate raw symbol over
the year's signal days (first to last signal day of the year). Candidate tickers: OpenFIGI's (isin_tickers.csv),
with '/' written as '.', plus the name-based mappings in NAME_MAP and the dated renames in RENAMES. Writes
symbology.json (raw answers) and prints every symbol that does not resolve on every signal day of its year.
Metadata only: nothing is billed.
"""
import csv
import importlib.util
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dbx", HERE.parents[1] / "tools" / "databento_spxw.py")
dbx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbx)
DATASETS = ["XNYS.PILLAR", "XNAS.ITCH"]
# ISINs OpenFIGI did not map (filing name -> ticker)
NAME_MAP = {"IE00BZ12WP82": "LIN", "US30231G1022": "XOM", "US4385161066": "HON"}


def candidates():
    t = {}
    for r in csv.DictReader(open(HERE / "isin_tickers.csv")):
        t[r["isin"]] = (r["tickers"] or NAME_MAP.get(r["isin"], "")).replace("/", ".")
    return t


def main():
    tick = candidates()
    lists = defaultdict(list)
    for r in csv.DictReader(open(HERE / "stock_lists_raw.csv")):
        lists[int(r["year"])].append((r["isin"], r["name"]))
    sig = defaultdict(list)
    for r in csv.DictReader(open(HERE / "signal_days.csv")):
        sig[int(r["date"][:4])].append(r["date"])
    out = {}
    for y in sorted(lists):
        a, b = min(sig[y]), max(sig[y])
        b1 = (date.fromisoformat(b) + timedelta(days=1)).isoformat()
        syms = sorted({tick[i] for i, _ in lists[y]})
        for ds in DATASETS:
            ans = dbx.call("symbology.resolve", {"dataset": ds, "symbols": ",".join(syms), "stype_in": "raw_symbol",
                                                 "stype_out": "instrument_id", "start_date": a, "end_date": b1})
            out[f"{y}|{ds}"] = {"start": a, "end": b1, "symbols": syms, "answer": ans}
            res = ans.get("result", {})
            for s in syms:
                iv = res.get(s, [])
                days = set()
                for seg in iv:
                    d0, d1 = date.fromisoformat(seg["d0"]), date.fromisoformat(seg["d1"])
                    while d0 < d1:
                        days.add(d0.isoformat())
                        d0 += timedelta(days=1)
                miss = [d for d in sig[y] if d not in days]
                if miss:
                    print(f"{y} {ds:12s} {s:6s} not resolved on {len(miss)} of {len(sig[y])} signal days "
                          f"({miss[0]} .. {miss[-1]})", flush=True)
    (HERE / "symbology.json").write_text(json.dumps(out, indent=1) + "\n")
    print("done; not_found/partial per request:",
          {k: (len(v["answer"].get("not_found", [])), len(v["answer"].get("partial", []))) for k, v in out.items()})


if __name__ == "__main__":
    main()
