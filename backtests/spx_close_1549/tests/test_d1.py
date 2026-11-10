"""Tests for dataset D1 (fetch_dukascopy.py, build_d1.py).

pytest is not installed in .venv, so this file runs with plain Python:
    .venv/bin/python -B backtests/spx_close_1549/tests/test_d1.py
(It also works under pytest if that is installed later.)
"""

from __future__ import annotations

import lzma
import struct
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import build_d1 as b  # noqa: E402
import fetch_dukascopy as fd  # noqa: E402


def _pack(records) -> bytes:
    """Make a Dukascopy-style candle file: '>iiiiif' records (secs, open, close, low, high, vol),
    integer prices x1000, LZMA 'alone' container (what the datafeed serves)."""
    blob = b"".join(struct.pack(">iiiiif", *r) for r in records)
    return lzma.compress(blob, format=lzma.FORMAT_ALONE)


# --------------------------------------------------------------------------------------------
# decoding
# --------------------------------------------------------------------------------------------

def test_decode_known_record():
    # 14:29:00 UTC; open 6584.125, close 6584.250, low 6583.875, high 6584.500, volume 1.5
    payload = _pack([(52140, 6584125, 6584250, 6583875, 6584500, 1.5)])
    (secs, o, h, lo, c, v), = fd.decode_bi5_bytes(payload)
    assert secs == 52140
    assert (o, h, lo, c) == (6584.125, 6584.5, 6583.875, 6584.25), (o, h, lo, c)  # file order is O,C,L,H
    assert v == 1.5


def test_decode_with_day_gives_utc_datetime():
    payload = _pack([(0, 1000, 1000, 1000, 1000, 0.0), (86340, 2000, 2000, 2000, 2000, 0.0)])
    recs = fd.decode_bi5_bytes(payload, date(2025, 9, 15))
    assert recs[0][0] == datetime(2025, 9, 15, 0, 0, tzinfo=timezone.utc)
    assert recs[1][0] == datetime(2025, 9, 15, 23, 59, tzinfo=timezone.utc)
    assert recs[1][1] == 2.0


def test_decode_empty_and_bad_length():
    assert fd.decode_bi5_bytes(b"") == []
    bad = lzma.compress(b"x" * 25, format=lzma.FORMAT_ALONE)
    try:
        fd.decode_bi5_bytes(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("a payload that is not a multiple of 24 bytes must be rejected")


def test_url_month_is_zero_based_and_path_one_based():
    assert fd.url_for(date(2024, 1, 5)).endswith("/USA500IDXUSD/2024/00/05/BID_candles_min_1.bi5")
    assert fd.url_for(date(2024, 12, 31)).endswith("/2024/11/31/BID_candles_min_1.bi5")
    assert fd.raw_path(date(2024, 1, 5)).parts[-3:] == ("2024", "01", "05.bi5")


def test_real_file_structure_if_present():
    """Any downloaded file: 24-byte records on a 60-second grid starting at 00:00 UTC."""
    files = sorted(p for p in fd.RAW_DIR.glob("*/*/*.bi5") if p.stat().st_size > 0)
    if not files:
        print("  (no raw files on disk; skipped)")
        return
    for path in (files[0], files[len(files) // 2], files[-1]):
        recs = fd.decode_bi5_bytes(path.read_bytes())
        secs = [r[0] for r in recs]
        assert secs == sorted(secs) and len(set(secs)) == len(secs), path
        assert all(s % 60 == 0 and 0 <= s < 86400 for s in secs), path
        assert all(r[3] <= min(r[1], r[4]) and r[2] >= max(r[1], r[4]) for r in recs), path


# --------------------------------------------------------------------------------------------
# time zone / DST
# --------------------------------------------------------------------------------------------

def test_dst_january_and_july():
    # winter (EST, UTC-5): 09:30 ET = 14:30Z ; summer (EDT, UTC-4): 09:30 ET = 13:30Z
    assert b.utc_to_et_label(date(2024, 1, 10), 14 * 3600 + 30 * 60) == (date(2024, 1, 10), "09:30")
    assert b.utc_to_et_label(date(2024, 7, 10), 13 * 3600 + 30 * 60) == (date(2024, 7, 10), "09:30")
    assert b.utc_to_et_label(date(2024, 1, 10), 20 * 3600 + 59 * 60) == (date(2024, 1, 10), "15:59")
    assert b.utc_to_et_label(date(2024, 7, 10), 19 * 3600 + 59 * 60) == (date(2024, 7, 10), "15:59")
    # first trading day after the March 2024 switch (Sun 2024-03-10)
    assert b.utc_to_et_label(date(2024, 3, 11), 13 * 3600 + 30 * 60) == (date(2024, 3, 11), "09:30")


def _records_for(utc_minutes, price=5000000, vol=1.0):
    """Decoded-style records (secs, o, h, l, c, v) for the given UTC minutes after midnight."""
    out = []
    for i, m in enumerate(utc_minutes):
        p = (price + i * 250) / 1000.0
        out.append((m * 60, p, p + 0.25, p - 0.25, p, vol))
    return out


def test_rth_cut_uses_cash_clock_in_both_seasons():
    all_minutes = range(0, 1440)
    jan = b.rth_frame(date(2024, 1, 10), _records_for(all_minutes))
    jul = b.rth_frame(date(2024, 7, 10), _records_for(all_minutes))
    for frame, first_utc in ((jan, 14 * 60 + 30), (jul, 13 * 60 + 30)):
        assert len(frame) == 390, len(frame)
        assert frame["time_et"].iloc[0] == "09:30" and frame["time_et"].iloc[-1] == "15:59"
        # the 09:30 ET bar is the record that started at first_utc minutes after 00:00 UTC
        expected_open = (5000000 + first_utc * 250) / 1000.0
        assert frame["open"].iloc[0] == expected_open, (frame["open"].iloc[0], expected_open)


# --------------------------------------------------------------------------------------------
# NYSE calendar and half-day exclusion
# --------------------------------------------------------------------------------------------

def test_calendar_half_days_and_holidays():
    for d in ["2024-11-29", "2024-12-24", "2024-07-03", "2019-07-03", "2013-07-03", "2018-12-24",
              "2012-11-23", "2025-07-03", "2026-11-27", "2026-12-24"]:
        assert b.calendar_status(date.fromisoformat(d))[0] == "half_day_calendar", d
    for d in ["2026-07-03", "2021-12-24", "2022-06-20", "2012-10-29", "2012-10-30", "2018-12-05",
              "2025-01-09", "2015-07-03", "2016-12-26", "2017-01-02", "2024-03-29", "2023-06-19"]:
        assert b.calendar_status(date.fromisoformat(d))[0] == "nyse_holiday", d
    for d in ["2026-07-02", "2015-07-02", "2021-06-18", "2010-12-31", "2021-12-31", "2016-07-01",
              "2020-07-02", "2024-12-23", "2024-11-26"]:
        assert b.calendar_status(date.fromisoformat(d))[0] == "full", d
    assert b.calendar_status(date(2024, 11, 30))[0] == "weekend"


def _full_frame(day: date, drop_times=(), flat_after=None) -> pd.DataFrame:
    """A synthetic RTH frame with ticks on every bar, optionally removing or flattening bars."""
    rows = []
    for i, t in enumerate(b.RTH_GRID):
        if t in drop_times:
            continue
        ticked = not (flat_after is not None and t >= flat_after)
        rows.append({"date": day.isoformat(), "time_et": t, "open": 100 + i, "high": 101 + i, "low": 99 + i,
                     "close": 100 + i, "volume": 1.0 if ticked else 0.0, "ticked": ticked})
    return pd.DataFrame(rows)


def test_half_day_exclusion():
    # calendar half-day with a full set of bars is still dropped
    d = date(2024, 11, 29)
    row = b.classify_day(d, _full_frame(d), "data")
    assert not row["keep"] and row["reason"] == "half_day_calendar"
    # calendar half-day whose afternoon is empty in the data: both detectors agree
    row = b.classify_day(d, _full_frame(d, flat_after="13:15"), "data")
    assert not row["keep"] and row["reason"] == "half_day_calendar" and row["data_half_day_signature"] is True
    # a normal day is kept
    d = date(2024, 11, 26)
    row = b.classify_day(d, _full_frame(d), "data")
    assert row["keep"] and row["reason"] == "usable" and row["data_half_day_signature"] is False
    # a normal calendar day whose afternoon has no ticks is dropped by the data detector
    row = b.classify_day(d, _full_frame(d, flat_after="13:00"), "data")
    assert not row["keep"] and row["reason"] == "half_day_data_only"
    # one missing bar inside 15:19-15:59 drops the day (pre-registration rule) ...
    row = b.classify_day(d, _full_frame(d, drop_times={"15:30"}), "data")
    assert not row["keep"] and row["reason"] == "missing_bar_1519_1559" and row["missing_1519_1559"] == 1
    # ... but a missing bar outside that window does not
    row = b.classify_day(d, _full_frame(d, drop_times={"11:00"}), "data")
    assert row["keep"]
    # holiday and weekend
    assert b.classify_day(date(2024, 12, 25), _full_frame(date(2024, 12, 25)), "data")["reason"] == "nyse_holiday"
    assert b.classify_day(date(2024, 11, 26), None, "nodata")["reason"] == "no_data"


def test_outage_rule_for_no_update_minutes():
    import numpy as np
    n = len(b.RTH_GRID)
    present = np.ones(n, bool)
    ticked = np.ones(n, bool)
    i1530 = b.RTH_GRID.index("15:30")
    # a 4-minute quiet stretch is a carry-forward run (valid), 5 minutes is an outage (missing)
    t4 = ticked.copy(); t4[i1530:i1530 + 4] = False
    t5 = ticked.copy(); t5[i1530:i1530 + 5] = False
    assert b.valid_bars(t4, present)[i1530:i1530 + 4].all()
    assert not b.valid_bars(t5, present)[i1530:i1530 + 5].any()
    # a quiet run that starts the session is never trusted (price may be from before 09:30)
    t0 = ticked.copy(); t0[0] = False
    assert not b.valid_bars(t0, present)[0] and b.valid_bars(t0, present)[1:].all()
    # an absent record is missing
    p2 = present.copy(); p2[i1530] = False
    assert not b.valid_bars(ticked, p2)[i1530]

    d = date(2024, 11, 26)
    frame = _full_frame(d)
    frame.loc[frame["time_et"].between("15:30", "15:33"), "ticked"] = False
    row = b.classify_day(d, frame, "data")
    assert row["keep"] and not row["keep_strict"] and row["noupdate_1519_1559"] == 4
    frame.loc[frame["time_et"] == "15:34", "ticked"] = False
    row = b.classify_day(d, frame, "data")
    assert not row["keep"] and row["reason"] == "missing_bar_1519_1559" and row["missing_1519_1559"] == 5


def test_built_d1_has_no_half_days_or_holidays_if_present():
    if not b.D1_CSV.exists():
        print("  (D1 not built yet; skipped)")
        return
    d1 = pd.read_csv(b.D1_CSV, dtype={"date": str, "time_et": str}, usecols=["date", "time_et", "ticked"])
    assert set(d1["ticked"].unique()) <= {0, 1}
    # the delayed-clock feed (through 2013-02-26) is not part of D1
    assert d1["date"].min() > b.DELAYED_FEED_LAST_DAY.isoformat()
    days = pd.to_datetime(pd.Series(d1["date"].unique()))
    assert (days.dt.weekday < 5).all()
    statuses = {b.calendar_status(x.date())[0] for x in days}
    assert statuses == {"full"}, statuses
    assert d1["time_et"].min() >= "09:30" and d1["time_et"].max() <= "15:59"
    assert not d1.duplicated(["date", "time_et"]).any()
    # every kept day has all 41 bars 15:19..15:59
    close = d1[d1["time_et"].between("15:19", "15:59")].groupby("date").size()
    assert (close == 41).all() and len(close) == len(days)


def main() -> int:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
