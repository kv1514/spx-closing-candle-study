"""Build each year's 50-stock list from SPY's year-end N-PORT-P filings (plan section 5).

Rule: holdings with assetCat EC, each identified by its ISIN (SPY's filings give a placeholder CUSIP 000000000 for
foreign-domiciled issuers, so CUSIP cannot be the key); entries with the same ISIN summed (valUSD, balance); a
holding without an ISIN is keyed by its CUSIP if that is not 000000000, otherwise excluded and counted. Ranked by
valUSD descending, ties by key ascending; first 50. The list for year Y comes from the report for 31 December of Y-1.
Reads data/spx_1549/spy_nport/manifest.json (and checks each file's SHA-256, fund name and report period).
Writes stock_lists_raw.csv (year, rank, key, cusip, isin, name, val_usd, balance, pct_val) and the per-year coverage into
stock_lists.json. Ticker mapping is a separate step (map_tickers.py).
"""
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path("/Users/kv15/trading")
HERE = Path(__file__).resolve().parent
NPORT = ROOT / "data" / "spx_1549" / "spy_nport"
N = 50


def local(tag):
    return tag.rsplit("}", 1)[-1]


def child(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def text(el, name):
    c = child(el, name)
    return c.text.strip() if c is not None and c.text else ""


def main():
    man = json.loads((NPORT / "manifest.json").read_text())
    rows, info = [], {}
    for rep, m in sorted(man.items()):
        f = ROOT / m["file"]
        body = f.read_bytes()
        assert hashlib.sha256(body).hexdigest() == m["sha256"], f
        root = ET.fromstring(body)
        reg = next((e.text for e in root.iter() if local(e.tag) == "regName"), None)
        per = next((e.text for e in root.iter() if local(e.tag) == "repPdDate"), None)
        assert reg and "SPDR S&P 500 ETF TRUST" in reg.upper(), (rep, reg)
        assert per == rep, (rep, per)
        agg = defaultdict(lambda: {"val": Decimal(0), "bal": Decimal(0), "pct": Decimal(0), "names": set(),
                                   "isins": set(), "cusips": set(), "n": 0})
        n_hold, cats, no_key = 0, defaultdict(int), 0
        for h in root.iter():
            if local(h.tag) != "invstOrSec":
                continue
            n_hold += 1
            cat = text(h, "assetCat")
            cats[cat] += 1
            if cat != "EC":
                continue
            cusip = text(h, "cusip")
            ids = child(h, "identifiers")
            isins = [i.get("value") for i in (ids if ids is not None else []) if local(i.tag) == "isin" and i.get("value")]
            if len(isins) > 1:
                raise SystemExit(f"{rep}: holding with several ISINs: {isins}")
            key = isins[0] if isins else (cusip if cusip and cusip != "000000000" else None)
            if key is None:
                no_key += 1
                continue
            a = agg[key]
            a["cusips"].add(cusip)
            a["val"] += Decimal(text(h, "valUSD") or "0")
            a["bal"] += Decimal(text(h, "balance") or "0")
            a["pct"] += Decimal(text(h, "pctVal") or "0")
            a["names"].add(text(h, "name"))
            a["isins"].update(isins)
            a["n"] += 1
        ranked = sorted(agg.items(), key=lambda kv: (-kv[1]["val"], kv[0]))[:N]
        year = int(rep[:4]) + 1
        for r, (key, a) in enumerate(ranked, 1):
            rows.append({"year": year, "rank": r, "key": key, "cusip": ";".join(sorted(a["cusips"])),
                         "isin": ";".join(sorted(a["isins"])),
                         "name": " | ".join(sorted(a["names"])), "val_usd": str(a["val"]), "balance": str(a["bal"]),
                         "pct_val": str(a["pct"]), "entries": a["n"]})
        info[str(year)] = {"report_date": rep, "accession": m["accession"], "file_sha256": m["sha256"],
                           "holdings": n_hold, "asset_categories": dict(cats), "ec_keys": len(agg), "no_key_excluded": no_key,
                           "duplicate_key_entries": sum(1 for a in agg.values() if a["n"] > 1),
                           "top50_pct_of_net_assets": str(sum(a["pct"] for _, a in ranked)),
                           "rank50_val_usd": str(ranked[-1][1]["val"]), "rank51_val_usd":
                               str(sorted(agg.values(), key=lambda a: -a["val"])[N]["val"])}
    with open(HERE / "stock_lists_raw.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (HERE / "stock_lists.json").write_text(json.dumps({"rule": __doc__.split("\n\n")[1], "years": info}, indent=1)
                                           + "\n")
    for y, v in info.items():
        print(y, v["report_date"], "holdings", v["holdings"], "EC keys", v["ec_keys"], "no key", v["no_key_excluded"], "dups",
              v["duplicate_key_entries"], "top50 pct", round(float(v["top50_pct_of_net_assets"]), 1),
              "cats", v["asset_categories"])


if __name__ == "__main__":
    main()
