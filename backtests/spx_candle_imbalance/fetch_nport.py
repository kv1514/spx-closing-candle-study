"""Download SPY's six year-end N-PORT-P filings (raw XML) from SEC EDGAR for the stock lists.

The SEC asks automated clients to identify themselves. The identifying string (name and email, as the author
approved) is read from the file named by the environment variable SEC_CONTACT_FILE, kept outside this repository,
and is never printed or stored here. Saves data/spx_1549/spy_nport/<report_date>_<accession>.xml and
data/spx_1549/spy_nport/manifest.json (URL, SHA-256, bytes, fund name and report period found in each file).
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/Users/kv15/trading")
OUT = ROOT / "data" / "spx_1549" / "spy_nport"
CIK = "884394"
FILINGS = [("2020-12-31", "0001752724-21-043869"), ("2021-12-31", "0001752724-22-048845"),
           ("2022-12-31", "0001752724-23-046862"), ("2023-12-31", "0001752724-24-043296"),
           ("2024-12-31", "0001752724-25-043826"), ("2025-12-31", "0001410368-26-020131")]


def main():
    path = os.environ.get("SEC_CONTACT_FILE", "")
    contact = Path(path).read_text().strip() if path and Path(path).exists() else ""
    if not contact:
        sys.exit("SEC_CONTACT_FILE must name a file holding the contact string")
    OUT.mkdir(parents=True, exist_ok=True)
    man = {}
    for rep, acc in FILINGS:
        url = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{acc.replace('-', '')}/primary_doc.xml"
        f = OUT / f"{rep}_{acc}.xml"
        if not f.exists():
            req = urllib.request.Request(url, headers={"User-Agent": contact, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            f.write_bytes(body)
            time.sleep(0.5)
        body = f.read_bytes()
        txt = body[:20000].decode("utf-8", "replace")
        name = re.search(r"<(?:\w+:)?regName>([^<]+)<", txt)
        period = re.search(r"<(?:\w+:)?repPdDate>([^<]+)<", txt)
        man[rep] = {"accession": acc, "url": url, "file": str(f.relative_to(ROOT)),
                    "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                    "fund_name_in_file": name.group(1) if name else None,
                    "report_period_in_file": period.group(1) if period else None}
        print(rep, man[rep]["bytes"], man[rep]["fund_name_in_file"], man[rep]["report_period_in_file"], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1) + "\n")


if __name__ == "__main__":
    main()
