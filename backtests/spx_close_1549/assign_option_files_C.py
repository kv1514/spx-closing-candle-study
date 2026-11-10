"""Copy saved get_option_historicals tool-result files into raw/<D>/ with the right name, matched by content.

Each saved file is identified by its instrument_ids (matched against raw/<D>/options_parts_plan.json) and its
interval ('minute' -> options_part<k>.json, '10minute' -> options_10m_part<k>.json). Nothing is hand-assigned.
Usage: python -B assign_option_files_C.py <file> [<file> ...]
"""
import json, os, shutil, sys
RAW = "/Users/kv15/trading/data/spx_1549/robinhood/raw"
DAYS = ["2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13",
        "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]
plans = {d: [set(p) for p in json.load(open(f"{RAW}/{d}/options_parts_plan.json"))] for d in DAYS}
for f in sys.argv[1:]:
    d = json.load(open(f))
    res = d["data"]["results"]
    ids = {r["instrument_id"] for r in res}
    ivs = {r["interval"] for r in res}
    assert len(ivs) == 1, (f, ivs)
    iv = ivs.pop()
    hit = [(day, k + 1) for day in DAYS for k, p in enumerate(plans[day]) if p == ids]
    assert len(hit) == 1, (f, hit)
    day, k = hit[0]
    name = {"minute": f"options_part{k}.json", "10minute": f"options_10m_part{k}.json"}[iv]
    dst = os.path.join(RAW, day, name)
    shutil.copyfile(f, dst)
    print(os.path.basename(f), "->", day, name)
