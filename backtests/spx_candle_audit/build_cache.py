"""Independent re-read of the raw files for the 15:50 audit (2026-11-09). Shares no code with the earlier studies.

Reads, and never writes to, the raw inputs:
  data/spx_1549/d1_usa500_rth_1m.csv.gz, d1_days.csv      Dukascopy US500 one-minute bars and the day list
  data/spx_1549/spx_official_closes_cboe.csv              Cboe official SPX closes
  data/spx_1549/databento/cbbo-1m_1500-1601_k60/*.csv.gz  OPRA one-minute quotes (SPXW, same-day expiry)
Writes one pickle (path given as argv[1]) with what the audit needs.

Run from the repository root:  .venv/bin/python -I backtests/spx_candle_audit/build_cache.py OUT.pkl
"""
import csv, gzip, hashlib, math, pickle, sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "spx_1549"
NY = ZoneInfo("America/New_York")
MINUTES = [f"15:{m:02d}" for m in range(40, 60)] + ["16:00"]


def fnum(s):
    try:
        return float(s)
    except ValueError:
        return math.nan


def read_bars():
    """date -> {time_et: (o, h, l, c, ticked)} plus raw integrity counts over the whole file."""
    bars, bad_hl, dup, unsorted, n = {}, 0, 0, 0, 0
    last = ("", "")
    with gzip.open(D / "d1_usa500_rth_1m.csv.gz", "rt", newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        assert head == ["date", "time_et", "open", "high", "low", "close", "ticked"], head
        for d, t, o, h, l, c, tk in rd:
            n += 1
            key = (d, t)
            if key == last:
                dup += 1
            elif key < last:
                unsorted += 1
            last = key
            o, h, l, c = float(o), float(h), float(l), float(c)
            if h < max(o, c) - 1e-9 or l > min(o, c) + 1e-9 or h < l:
                bad_hl += 1
            bars.setdefault(d, {})[t] = (o, h, l, c, tk == "1")
    return bars, {"rows": n, "duplicate_rows": dup, "out_of_order_rows": unsorted, "bars_with_impossible_high_low": bad_hl}


def read_days():
    with open(D / "d1_days.csv", newline="") as f:
        return list(csv.DictReader(f))


def read_closes():
    out = {}
    with open(D / "spx_official_closes_cboe.csv", newline="") as f:
        for r in csv.DictReader(f):
            m, d, y = r["DATE"].split("/")
            out[f"{y}-{m}-{d}"] = float(r["SPX"])
    return out


def read_quotes(path, day):
    """minute 'HH:MM' ET -> {(kind, strike): (bid, ask)} for contracts expiring `day`; plus counts."""
    want = day[2:4] + day[5:7] + day[8:10]
    out = {m: {} for m in MINUTES}
    other_expiry = other_root = rows = off_minute = dup = dup_conflict = 0
    conflict_minutes = {}
    same = lambda a, b: a == b or (a != a and b != b)             # equal, or both NaN
    with gzip.open(path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            rows += 1
            sym = r["symbol"]
            root, exp, kind, strike = sym[:6].strip(), sym[6:12], sym[12], int(sym[13:21]) / 1000.0
            if root != "SPXW":
                other_root += 1
                continue
            if exp != want:
                other_expiry += 1
                continue
            ts = r["ts_recv"]
            if ts[19:] != ".000000000Z":          # only stamps exactly on a second are snapshots
                off_minute += 1
                continue
            utc = datetime(int(ts[0:4]), int(ts[5:7]), int(ts[8:10]), int(ts[11:13]), int(ts[14:16]), int(ts[17:19]),
                           tzinfo=timezone.utc)
            et = utc.astimezone(NY)
            if et.strftime("%Y-%m-%d") != day or et.second != 0:
                continue
            m = et.strftime("%H:%M")
            if m in out:
                q = (fnum(r["bid_px_00"]), fnum(r["ask_px_00"]))
                if (kind, strike) in out[m]:
                    dup += 1
                    prev = out[m][(kind, strike)]
                    if not (same(prev[0], q[0]) and same(prev[1], q[1])):
                        dup_conflict += 1
                        conflict_minutes[m] = conflict_minutes.get(m, 0) + 1
                out[m][(kind, strike)] = q
    return out, {"rows": rows, "other_root": other_root, "other_expiry": other_expiry, "off_second_rows": off_minute,
                 "duplicate_keys": dup, "duplicate_keys_with_different_quotes": dup_conflict,
                 "conflicts_by_minute": conflict_minutes}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(out_path):
    bars, bar_checks = read_bars()
    days = read_days()
    closes = read_closes()
    qdir = D / "databento" / "cbbo-1m_1500-1601_k60"
    quotes, qmeta, none_days = {}, {}, []
    for p in sorted(qdir.iterdir()):
        name = p.name
        if name.endswith(".none"):
            none_days.append(name[:10])
        elif name.endswith(".csv.gz"):
            day = name[:10]
            quotes[day], qmeta[day] = read_quotes(p, day)
    listing = "\n".join(f"{p.name}:{p.stat().st_size}" for p in sorted(qdir.iterdir()))
    inputs = {"d1_usa500_rth_1m.csv.gz": sha(D / "d1_usa500_rth_1m.csv.gz"), "d1_days.csv": sha(D / "d1_days.csv"),
              "spx_official_closes_cboe.csv": sha(D / "spx_official_closes_cboe.csv"),
              "quote_dir_names_and_sizes": hashlib.sha256(listing.encode()).hexdigest()}
    tot = {k: sum(m[k] for m in qmeta.values()) for k in next(iter(qmeta.values())) if k != "conflicts_by_minute"}
    with open(out_path, "wb") as f:
        pickle.dump({"bars": bars, "bar_checks": bar_checks, "days": days, "closes": closes, "quotes": quotes,
                     "quote_meta": qmeta, "quote_totals": tot, "inputs_sha256": inputs, "none_days": none_days},
                    f, protocol=pickle.HIGHEST_PROTOCOL)
    print("quote rows", tot)
    print("bar checks", bar_checks)
    print("bar days", len(bars), "quote days", len(quotes), "none markers", len(none_days), "closes", len(closes))


if __name__ == "__main__":
    main(sys.argv[1])
