"""Map each list position's ISIN to its US ticker with OpenFIGI (free public API; only ISINs are sent).

Writes isin_figi.json (the raw OpenFIGI answers) and isin_tickers.csv (isin, name in the filing, US composite
ticker(s) OpenFIGI returns, security type). OpenFIGI returns today's ticker for an ISIN; dated spellings and renames
are checked against Databento symbology in check_symbology.py.
"""
import csv
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = "https://api.openfigi.com/v3/mapping"


def main():
    rows = list(csv.DictReader(open(HERE / "stock_lists_raw.csv")))
    names = {}
    for r in rows:
        names.setdefault(r["isin"], r["name"])
    isins = sorted(names)
    out = {}
    for i in range(0, len(isins), 5):
        chunk = isins[i:i + 5]
        jobs = [{"idType": "ID_ISIN", "idValue": x, "exchCode": "US"} for x in chunk]
        req = urllib.request.Request(URL, data=json.dumps(jobs).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "spx-research/1.0"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    ans = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(20)
                    continue
                raise
        for x, a in zip(chunk, ans):
            out[x] = a
        time.sleep(3)
    (HERE / "isin_figi.json").write_text(json.dumps(out, indent=1) + "\n")
    with open(HERE / "isin_tickers.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["isin", "name_in_filing", "tickers", "security_types", "figi_names"])
        for x in isins:
            data = out[x].get("data", [])
            w.writerow([x, names[x], ";".join(sorted({d.get("ticker", "") for d in data})),
                        ";".join(sorted({d.get("securityType", "") for d in data})),
                        ";".join(sorted({d.get("name", "") for d in data}))])
    bad = [x for x in isins if len({d.get("ticker") for d in out[x].get("data", [])}) != 1]
    print(len(isins), "ISINs;", len(bad), "without exactly one ticker:", [(x, names[x], out[x]) for x in bad])


if __name__ == "__main__":
    main()
