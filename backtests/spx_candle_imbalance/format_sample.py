"""Pre-lock check 2: download the closing-imbalance messages of two days OUTSIDE the sample (2020-12-30 with the
2021 list, 2026-11-06 with the 2026 list), 15:45:00-16:00:00 ET, to fix the field codes and timing. Approved by the
author on 2026-11-10 ("i approve", for about $0.06).

Each stock is requested from its listing exchange (venues.csv: the 2021 list's first segments, the 2026 list's last
segments). The Nasdaq request also carries two NYSE-listed controls (JPM, XOM) to see what Nasdaq's feed holds for
stocks it does not list.

Money handling (plan section 10): each request is priced with the free metadata.get_cost for its own dataset; it is
refused if the logged total in spend_log.csv would pass $120; a reservation row is appended to spend_log.csv and
flushed to disk BEFORE the request; the paid request is never retried after a network failure (HTTP 429/5xx
answers, which deliver nothing, are retried by the helper). The API key is never printed.
Saves data/spx_1549/databento/imbalance_format_sample/<dataset>_<day>.csv.gz and manifest.json.
"""
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("dbx", ROOT / "tools" / "databento_spxw.py")
dbx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbx)
ET = ZoneInfo("America/New_York")
OUT = ROOT / "data" / "spx_1549" / "databento" / "imbalance_format_sample"
CAP = 120.0
DAYS = {"2020-12-30": (2021, "first"), "2026-11-06": (2026, "last")}
CONTROLS = ["JPM", "XOM"]


def ns(d, t):
    return int(datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=ET).timestamp() * 1e9)


def symbols(year, which):
    segs = [r for r in csv.DictReader(open(HERE / "venues.csv")) if int(r["year"]) == year]
    by_isin = {}
    for r in segs:
        k = r["isin"]
        if k not in by_isin or (which == "last" and r["from"] > by_isin[k]["from"]) or \
                (which == "first" and r["from"] < by_isin[k]["from"]):
            by_isin[k] = r
    assert len(by_isin) == 50, len(by_isin)
    out = {"XNYS.PILLAR": [], "XNAS.ITCH": []}
    for r in by_isin.values():
        out[r["venue"]].append(r["raw_symbol"])
    out["XNAS.ITCH"] += [c for c in CONTROLS if c not in out["XNAS.ITCH"]]
    return {k: sorted(v) for k, v in out.items()}


def reserve(ds, day, syms, cost, f):
    new = not dbx.SPEND_LOG.exists()
    with open(dbx.SPEND_LOG, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=dbx.SPEND_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({"utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "schema": f"imbalance:{ds}", "day": day, "n_symbols": len(syms),
                    "quoted_cost_usd": f"{cost:.6f}", "rows": "reserved", "file": str(f.relative_to(ROOT))})
        fh.flush()
        os.fsync(fh.fileno())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = []
    for day, (year, which) in DAYS.items():
        for ds, syms in symbols(year, which).items():
            p = {"dataset": ds, "symbols": ",".join(syms), "schema": "imbalance", "start": ns(day, "15:45:00"),
                 "end": ns(day, "16:00:00"), "stype_in": "raw_symbol"}
            plan.append((day, ds, syms, p, float(dbx.call("metadata.get_cost", p))))
    total = sum(c for *_, c in plan)
    print(f"quoted total ${total:.4f} for {len(plan)} requests; logged so far ${dbx.spent():.4f}", flush=True)
    if total > 0.10:
        sys.exit("quote above the approved ~$0.06 (hard stop at $0.10); nothing sent")
    man = json.loads((OUT / "manifest.json").read_text()) if (OUT / "manifest.json").exists() else {}
    for day, ds, syms, p, cost in plan:
        f = OUT / f"{ds}_{day}.csv.gz"
        if f.exists():
            continue
        if dbx.spent() + cost > CAP + 1e-12:
            sys.exit(f"refused: ${dbx.spent():.4f} logged + ${cost:.4f} would pass ${CAP}")
        reserve(ds, day, syms, cost, f)
        body = dbx.call("timeseries.get_range", {**p, "encoding": "csv", "compression": "none", "pretty_px": "false",
                                                 "pretty_ts": "false", "map_symbols": "true"},
                        raw=True, retry_network=False)
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(body, 6))
        tmp.replace(f)
        man[f.name] = {"day": day, "dataset": ds, "symbols": syms, "quoted_cost_usd": cost,
                       "rows": max(0, body.count(b"\n") - 1), "sha256_uncompressed": hashlib.sha256(body).hexdigest()}
        (OUT / "manifest.json").write_text(json.dumps(man, indent=1) + "\n")
        print(f"{f.name}: {man[f.name]['rows']} rows, quoted ${cost:.4f}", flush=True)
    print(f"logged total now ${dbx.spent():.4f}")


if __name__ == "__main__":
    main()
