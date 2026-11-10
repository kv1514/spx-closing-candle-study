"""Build dataset D1 (preregistration/spx_1549_close.md): Dukascopy USA500.IDX/USD 1-minute BID
candles cut to the NYSE cash-session clock.

Input : data/spx_1549/dukascopy/raw/YYYY/MM/DD.bi5 (one file per UTC day, see fetch_dukascopy.py)
Output: data/spx_1549/d1_usa500_rth_1m.csv.gz   columns date, time_et, open, high, low, close, ticked
        data/spx_1549/d1_days.csv                one row per weekday in range: status, reason, bar counts
        backtests/spx_close_1549/d1_coverage.json counts of kept / dropped days and why

Rules (applied in this order; the first that matches is the day's drop reason):
  1. weekend                     Saturday/Sunday (never fetched).
  2. nyse_holiday                full NYSE closure (rules below, plus one-off closures).
  3. half_day_calendar           NYSE 13:00 ET early close by the holiday rules.
  4. no_file / no_data           the UTC-day file could not be fetched / the server has no data.
     no_ticks_in_session         the file exists but no 09:30-15:59 ET bar has a tick (the oldest
                                 files are flat placeholders with zero volume all day).
  5. half_day_data_only          the calendar says full day, but the CFD has no normal afternoon
                                 bars (fewer than half of the 150 bars 13:30-15:59 ET have ticks);
                                 i.e. the half-day/closure signature seen in the data itself.
  6. missing_bar_1519_1559       any of the 41 bars 15:19..15:59 ET is missing (pre-registration).
Kept days ("usable") are written to the CSV with all their 09:30-15:59 ET bars that have ticks.

Excluded feed period (before the rules above are counted): Dukascopy's oldest USA500 data,
2011-09-19 .. 2013-02-26 (DELAYED_FEED_LAST_DAY), runs on a clock that is about 15-20 minutes late:
quotes start at 09:45/09:50 ET and stop at about 16:20 ET, 10:00 ET data releases show up in the
10:20 bar, and FOMC statements (12:30 / 14:15 ET in 2012) show up 17-20 minutes late. From
2013-02-27 quotes start at 09:30 and the 10:00 / 14:00 ET events land on their own bars. A 15:49
-> 15:59 window in the old feed would really be about 15:29 -> 15:39, so those days are reported
as "delayed_clock_feed" and are not part of D1. Evidence numbers are in d1_coverage.json. (Flat
zero-volume placeholder files before 2011-09-19 are "before_first_ticked_session".)

Bars: a Dukascopy candle file has one record per UTC minute (start time). A minute with no price
update is stored as a flat zero-volume candle at the previous close (checked: 14152 of 14157 such
bars in the dropped days equal the previous close). What "missing bar" means for this feed:
  * ticked bar            the minute had at least one quote update.
  * carry-forward bar     no update, inside a run of at most OUTAGE_MIN_RUN-1 = 4 such minutes. In
                          the sparse years (2013-14, 2017, 2019) these are common and their run
                          lengths fall off geometrically (2014: 2983 / 579 / 167 / 63 runs of 1 / 2 /
                          3 / 4 minutes), i.e. a quiet quote stream; the price is the last real BID.
                          Written to D1 with ticked = 0.
  * missing bar           no update inside a run of >= 5 minutes (feed outage: runs of exactly 5
                          and 15 minutes are far above that geometric trend, e.g. a recurring
                          15:15-15:29 ET gap in Sep-Oct 2013), or a no-update run that starts at
                          09:30 (the carried price could be from before the session). Not written.
The pre-registration's "any missing bar 15:19-15:59" rule uses this definition. The stricter
reading (any no-update minute counts as missing) is reported as a sensitivity count, and can be
applied to D1 directly with the ticked column.
Times: UTC -> America/New_York with zoneinfo; a bar is labelled by its ET START time, and kept if
09:30 <= time_et <= 15:59 (the 15:59 bar ends at the 16:00 bell). The CFD trades nearly 24 hours,
so everything outside that clock is cut.

NYSE calendar (written out here because no calendar package is installed; the rules match the
FairVal audited backtest rules used elsewhere in this repo, extended with the one-off closures
2012-10-29/30 Hurricane Sandy, 2018-12-05 President G.H.W. Bush, 2025-01-09 President Carter, and
Juneteenth only from 2022):
  full closures: New Year (Sat -> not observed, Sun -> Mon), MLK (3rd Mon Jan), Washington's
  Birthday (3rd Mon Feb), Good Friday, Memorial Day (last Mon May), Juneteenth (2022+, observed),
  Independence Day (observed), Labor Day (1st Mon Sep), Thanksgiving (4th Thu Nov), Christmas
  (observed).
  13:00 early closes: day after Thanksgiving; Dec 24 when it is a weekday and not a holiday; Jul 3
  when it is Mon-Thu and not a holiday.

Usage: .venv/bin/python -B backtests/spx_close_1549/build_d1.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch_dukascopy as fd  # noqa: E402

ROOT = Path("/Users/kv15/trading")
OUT_DIR = ROOT / "data" / "spx_1549"
D1_CSV = OUT_DIR / "d1_usa500_rth_1m.csv.gz"
DAYS_CSV = OUT_DIR / "d1_days.csv"
COVERAGE_JSON = HERE / "d1_coverage.json"

NY = ZoneInfo("America/New_York")
RTH_FIRST = time(9, 30)
RTH_LAST = time(15, 59)          # start time of the last regular-session bar
AFTERNOON_FIRST = time(13, 30)   # half-day detector window 13:30..15:59 (150 bars)
AFTERNOON_MIN_FRACTION = 0.5
CLOSE_WINDOW = (time(15, 19), time(15, 59))   # pre-registration: no missing bar allowed here
N_RTH_BARS = 390
OUTAGE_MIN_RUN = 5               # >= this many consecutive no-update minutes = feed outage
# Last day of the old Dukascopy feed whose clock is ~15-20 minutes late (see module docstring).
DELAYED_FEED_LAST_DAY = date(2013, 2, 26)
# bars the pre-registered predictors need (09:30 open, 10:00 open, 15:19 open, 15:49-15:51 opens)
KEY_BARS = ("09:30", "10:00", "15:19", "15:49", "15:50", "15:51", "15:59")


# ---------------------------------------------------------------------------------------------
# NYSE calendar
# ---------------------------------------------------------------------------------------------

SPECIAL_CLOSURES = {
    date(2012, 10, 29): "Hurricane Sandy",
    date(2012, 10, 30): "Hurricane Sandy",
    date(2018, 12, 5): "National Day of Mourning (G.H.W. Bush)",
    date(2025, 1, 9): "National Day of Mourning (Carter)",
}


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th given weekday (Monday=0) of a month; n=-1 means the last one."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> dict:
    """{date: name} of full-day NYSE closures in a calendar year."""
    out = {}
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:  # Jan 1 on Saturday: no Friday closure
        out[_observed(new_year)] = "New Year's Day"
    out[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    out[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    out[_easter(year) - timedelta(days=2)] = "Good Friday"
    out[_nth_weekday(year, 5, 0, -1)] = "Memorial Day"
    if year >= 2022:
        out[_observed(date(year, 6, 19))] = "Juneteenth"
    out[_observed(date(year, 7, 4))] = "Independence Day"
    out[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    out[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    out[_observed(date(year, 12, 25))] = "Christmas Day"
    for day, name in SPECIAL_CLOSURES.items():
        if day.year == year:
            out[day] = name
    return out


@lru_cache(maxsize=None)
def nyse_early_closes(year: int) -> dict:
    """{date: name} of 13:00 ET early closes in a calendar year."""
    hol = nyse_holidays(year)
    out = {_nth_weekday(year, 11, 3, 4) + timedelta(days=1): "day after Thanksgiving"}
    dec24 = date(year, 12, 24)
    if dec24.weekday() < 5 and dec24 not in hol:
        out[dec24] = "Christmas Eve"
    jul3 = date(year, 7, 3)
    if jul3.weekday() < 4 and jul3 not in hol:
        out[jul3] = "day before Independence Day"
    return out


def calendar_status(day: date) -> tuple[str, str]:
    """('weekend'|'nyse_holiday'|'half_day_calendar'|'full', detail)."""
    if day.weekday() >= 5:
        return "weekend", day.strftime("%A")
    name = nyse_holidays(day.year).get(day)
    if name:
        return "nyse_holiday", name
    name = nyse_early_closes(day.year).get(day)
    if name:
        return "half_day_calendar", name
    return "full", ""


# ---------------------------------------------------------------------------------------------
# Time conversion and per-day processing
# ---------------------------------------------------------------------------------------------

def utc_to_et_label(utc_day: date, seconds: int) -> tuple[date, str]:
    """(ET date, 'HH:MM' ET start time) of a bar starting `seconds` after 00:00 UTC of utc_day."""
    stamp = datetime(utc_day.year, utc_day.month, utc_day.day, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    local = stamp.astimezone(NY)
    return local.date(), local.strftime("%H:%M")


def rth_frame(utc_day: date, records) -> pd.DataFrame:
    """Cut decoded records (from fd.decode_bi5_bytes with day=None) to the 09:30-15:59 ET bars of
    the ET session on the same calendar date, on the full 390-minute grid. Adds boolean columns
    'present' (record exists), 'ticked' (quote update in that minute) and 'valid' (usable price)."""
    cols = ["date", "time_et", "open", "high", "low", "close", "volume", "ticked"]
    if not records:
        return pd.DataFrame(columns=cols + ["present", "valid"])
    arr = np.array(records, dtype=float)
    secs = arr[:, 0].astype(np.int64)
    utc = pd.to_datetime(pd.Timestamp(utc_day).tz_localize("UTC").value + secs * 1_000_000_000, utc=True)
    et = utc.tz_convert(NY)
    t = et.strftime("%H:%M")
    keep = (et.date == utc_day) & (t >= RTH_FIRST.strftime("%H:%M")) & (t <= RTH_LAST.strftime("%H:%M"))
    frame = pd.DataFrame({
        "date": utc_day.isoformat(),
        "time_et": np.asarray(t)[keep],
        "open": arr[keep, 1], "high": arr[keep, 2], "low": arr[keep, 3], "close": arr[keep, 4],
        "volume": arr[keep, 5],
    })
    flat = (frame["open"] == frame["high"]) & (frame["high"] == frame["low"]) & (frame["low"] == frame["close"])
    frame["ticked"] = ~((frame["volume"] <= 0) & flat)
    frame = frame.set_index("time_et").reindex(RTH_GRID)          # absent records -> NaN rows
    frame["date"] = utc_day.isoformat()
    frame["present"] = frame["open"].notna()
    frame["ticked"] = frame["ticked"].fillna(False).astype(bool) & frame["present"]
    frame["valid"] = valid_bars(frame["ticked"].to_numpy(), frame["present"].to_numpy())
    frame.index.name = "time_et"
    return frame.reset_index()[cols + ["present", "valid"]]


def valid_bars(ticked: np.ndarray, present: np.ndarray, min_run: int = None) -> np.ndarray:
    """Which bars of a 390-bar session carry a usable price (see module docstring):
    ticked bars, plus no-update bars in a run shorter than min_run that does not start at 09:30."""
    min_run = OUTAGE_MIN_RUN if min_run is None else min_run
    valid = ticked & present
    n = len(ticked)
    i = 0
    while i < n:
        if ticked[i] or not present[i]:
            i += 1
            continue
        j = i
        while j < n and present[j] and not ticked[j]:
            j += 1
        if (j - i) < min_run and i > 0:
            valid[i:j] = True
        i = j
    return valid


def _minute_grid(first: time, last: time) -> list[str]:
    out, cur = [], datetime.combine(date(2000, 1, 3), first)
    end = datetime.combine(date(2000, 1, 3), last)
    while cur <= end:
        out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=1)
    return out


AFTERNOON_GRID = _minute_grid(AFTERNOON_FIRST, RTH_LAST)
CLOSE_GRID = _minute_grid(*CLOSE_WINDOW)
RTH_GRID = _minute_grid(RTH_FIRST, RTH_LAST)


def classify_day(day: date, frame: pd.DataFrame | None, file_state: str) -> dict:
    """Decide keep/drop for one weekday. file_state: 'data' | 'nodata' | 'missing'."""
    status, detail = calendar_status(day)
    row = {"date": day.isoformat(), "weekday": day.strftime("%a"), "calendar": status,
           "calendar_detail": detail, "file": file_state, "n_rth_records": 0, "n_rth_ticked": 0,
           "n_rth_valid": 0, "afternoon_ticked": 0, "missing_1519_1559": None,
           "noupdate_1519_1559": None, "data_half_day_signature": None,
           "keep": False, "keep_strict": False, "reason": ""}
    row.update({"has_" + t.replace(":", ""): False for t in KEY_BARS})
    if frame is not None and len(frame):
        if "valid" not in frame:   # plain frame (tests): every listed bar is a record
            frame = frame.copy()
            frame["present"] = True
            frame = frame.set_index("time_et").reindex(RTH_GRID)
            frame.index.name = "time_et"
            frame = frame.reset_index()
            frame["present"] = frame["present"].fillna(False).astype(bool)
            frame["ticked"] = frame["ticked"].fillna(False).astype(bool) & frame["present"]
            frame["valid"] = valid_bars(frame["ticked"].to_numpy(), frame["present"].to_numpy())
        ticked = set(frame.loc[frame["ticked"], "time_et"])
        valid = set(frame.loc[frame["valid"], "time_et"])
        row["n_rth_records"] = int(frame["present"].sum())
        row["n_rth_ticked"] = int(len(ticked))
        row["n_rth_valid"] = int(len(valid))
        row["afternoon_ticked"] = int(sum(t in ticked for t in AFTERNOON_GRID))
        row["missing_1519_1559"] = int(sum(t not in valid for t in CLOSE_GRID))
        row["noupdate_1519_1559"] = int(sum(t not in ticked for t in CLOSE_GRID))
        row["data_half_day_signature"] = bool(row["afternoon_ticked"] < AFTERNOON_MIN_FRACTION * len(AFTERNOON_GRID))
        for t in KEY_BARS:
            row["has_" + t.replace(":", "")] = t in valid
    elif file_state == "data":
        row["afternoon_ticked"] = 0
        row["missing_1519_1559"] = row["noupdate_1519_1559"] = len(CLOSE_GRID)
        row["data_half_day_signature"] = True
    if status != "full":
        row["reason"] = status
    elif file_state == "missing":
        row["reason"] = "no_file"
    elif file_state == "nodata":
        row["reason"] = "no_data"
    elif row["n_rth_ticked"] == 0:
        row["reason"] = "no_ticks_in_session"
    elif row["data_half_day_signature"]:
        row["reason"] = "half_day_data_only"
    elif row["missing_1519_1559"]:
        row["reason"] = "missing_bar_1519_1559"
    else:
        row["keep"] = True
        row["reason"] = "usable"
    row["keep_strict"] = bool(row["keep"] and row["noupdate_1519_1559"] == 0)
    return row


# ---------------------------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------------------------

def first_data_day() -> date | None:
    files = sorted(fd.RAW_DIR.glob("*/*/*.bi5"))
    for path in files:
        if path.stat().st_size > 0:
            y, m, d = path.parts[-3], path.parts[-2], path.stem
            return date(int(y), int(m), int(d))
    return None


def build(start: date, end: date) -> dict:
    rows, frames = [], []
    weekend_days = 0
    day = start
    while day <= end:
        if day.weekday() >= 5:
            weekend_days += 1
            day += timedelta(days=1)
            continue
        if fd.raw_path(day).exists():
            state = "data"
            records = fd.decode_bi5_bytes(fd.raw_path(day).read_bytes())
            frame = rth_frame(day, records)
        elif fd.nodata_path(day).exists():
            state, frame = "nodata", None
        else:
            state, frame = "missing", None
        row = classify_day(day, frame, state)
        rows.append(row)
        if row["keep"]:
            keep_rows = frame.loc[frame["valid"], ["date", "time_et", "open", "high", "low", "close", "ticked"]].copy()
            keep_rows["ticked"] = keep_rows["ticked"].astype(int)
            frames.append(keep_rows)
        day += timedelta(days=1)

    days = pd.DataFrame(rows)
    # The oldest files are flat zero-volume placeholders; then comes the delayed-clock feed.
    # Both periods are reported separately, not as dropped sessions of D1.
    ticked_days = days.loc[days["n_rth_ticked"] > 0, "date"]
    first_ticked = ticked_days.min() if len(ticked_days) else None
    placeholder = days["date"] < first_ticked if first_ticked else pd.Series(True, index=days.index)
    delayed = ~placeholder & (days["date"] <= DELAYED_FEED_LAST_DAY.isoformat())
    days["calendar_or_data_reason"] = days["reason"]  # what the day would have been without the feed rule
    days.loc[placeholder, "reason"] = "before_first_ticked_session"
    days.loc[delayed, "reason"] = "delayed_clock_feed"
    days["would_be_usable"] = days["keep"]
    before = placeholder | delayed
    days.loc[before, "keep"] = False
    days.loc[before, "keep_strict"] = False
    days.to_csv(DAYS_CSV, index=False)
    keep_dates = set(days.loc[days["keep"], "date"])
    old_feed_dates = set(days.loc[delayed & days["would_be_usable"], "date"])
    old_feed = [f for f in frames if f["date"].iloc[0] in old_feed_dates]
    frames = [f for f in frames if f["date"].iloc[0] in keep_dates]
    d1 = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "time_et", "open", "high", "low", "close", "ticked"])
    d1.to_csv(D1_CSV, index=False, float_format="%.3f", compression="gzip")
    evidence = _clock_evidence(pd.concat(old_feed, ignore_index=True) if old_feed else None,
                               d1[d1["date"] <= "2013-12-31"] if len(d1) else None)
    del old_feed

    inrange = days[~before]
    kept = inrange[inrange["keep"]]
    data_start = inrange["date"].min() if len(inrange) else None
    weekend_in_range = 0
    if data_start:
        d = date.fromisoformat(data_start)
        while d <= end:
            weekend_in_range += d.weekday() >= 5
            d += timedelta(days=1)
    dropped = {k: int(v) for k, v in inrange.loc[~inrange["keep"], "reason"].value_counts().items()}
    dropped["weekend"] = int(weekend_in_range)
    full_cal = inrange[inrange["calendar"] == "full"]
    half_cal = inrange[inrange["calendar"] == "half_day_calendar"]
    # agreement between the two half-day detectors (only where the file has session ticks)
    half_cal_with_data = half_cal[half_cal["n_rth_ticked"] > 0]
    full_with_data = full_cal[full_cal["n_rth_ticked"] > 0]
    sig = lambda frame: frame["data_half_day_signature"].fillna(False).astype(bool)  # noqa: E731
    per_year = {}
    for year, grp in inrange.groupby(inrange["date"].str[:4]):
        k = grp[grp["keep"]]
        per_year[year] = {
            "usable": int(len(k)),
            "dropped": {r: int(v) for r, v in grp.loc[~grp["keep"], "reason"].value_counts().items()},
            "usable_missing_0930": int((~k["has_0930"]).sum()),
            "usable_missing_1000": int((~k["has_1000"]).sum()),
            "usable_median_rth_bars": float(k["n_rth_valid"].median()) if len(k) else None,
            "usable_if_strict_rule": int(k["keep_strict"].sum()),
        }
    rth_per_kept = kept["n_rth_valid"]
    # largest 1-minute close-to-close move inside kept sessions (sanity check for bad ticks)
    big = None
    if len(d1):
        lr = np.log(d1["close"]).groupby(d1["date"]).diff().abs()
        idx = lr.idxmax()
        big = {"date": d1.loc[idx, "date"], "time_et": d1.loc[idx, "time_et"],
               "abs_log_return_bps": round(float(lr.max() * 1e4), 2),
               "n_bars_abs_ret_over_100bps": int((lr > 0.01).sum())}
    coverage = {
        "dataset": "D1 Dukascopy USA500.IDX/USD 1-minute BID, NYSE regular session 09:30-15:59 ET bars",
        "files": {"d1_csv": str(D1_CSV), "days_csv": str(DAYS_CSV)},
        "raw_files_scanned_from": start.isoformat(),
        "first_weekday_with_session_ticks": first_ticked,
        "excluded_before_range": {
            "before_first_ticked_session": {"weekdays": int(placeholder.sum()),
                                            "note": "flat zero-volume placeholder files"},
            "delayed_clock_feed": {
                "first_day": days.loc[delayed, "date"].min() if delayed.any() else None,
                "last_day": DELAYED_FEED_LAST_DAY.isoformat(),
                "weekdays": int(delayed.sum()),
                "would_have_been_usable": int((delayed & days["would_be_usable"]).sum()),
                "evidence": evidence,
            },
        },
        "range": [data_start, end.isoformat()],
        "first_usable_day": kept["date"].min() if len(kept) else None,
        "last_usable_day": kept["date"].max() if len(kept) else None,
        "weekdays_in_range": int(len(inrange)),
        "usable_days": int(len(kept)),
        "dropped_by_reason": dict(sorted(dropped.items())),
        "drop_order": ["weekend", "nyse_holiday", "half_day_calendar", "no_file", "no_data",
                       "no_ticks_in_session", "half_day_data_only", "missing_bar_1519_1559"],
        "half_day_detection": {
            "calendar_half_days_in_range": int(len(half_cal)),
            "calendar_half_days_with_session_ticks": int(len(half_cal_with_data)),
            "calendar_half_days_also_flagged_by_data": int(sig(half_cal_with_data).sum()),
            "calendar_half_days_NOT_flagged_by_data": half_cal_with_data.loc[~sig(half_cal_with_data), "date"].tolist(),
            "calendar_full_days_flagged_by_data": full_with_data.loc[sig(full_with_data), "date"].tolist(),
            "rule": f"data signature = fewer than {AFTERNOON_MIN_FRACTION:.0%} of the {len(AFTERNOON_GRID)} bars "
                    f"13:30-15:59 ET have ticks",
        },
        "holidays_with_session_ticks_dropped": int(((inrange["calendar"] == "nyse_holiday") & (inrange["n_rth_ticked"] > 0)).sum()),
        "missing_bar_1519_1559_days": inrange.loc[inrange["reason"] == "missing_bar_1519_1559", "date"].tolist(),
        "no_ticks_in_session_days": inrange.loc[inrange["reason"] == "no_ticks_in_session", "date"].tolist(),
        "no_file_days": inrange.loc[inrange["reason"] == "no_file", "date"].tolist(),
        "no_data_days": inrange.loc[inrange["reason"] == "no_data", "date"].tolist(),
        "strict_rule_sensitivity": {
            "rule": "any no-update (flat zero-volume) minute in 15:19-15:59 counts as missing",
            "usable_days": int(kept["keep_strict"].sum()),
            "extra_days_dropped_vs_primary": int(len(kept) - kept["keep_strict"].sum()),
            "how_to_apply": "keep a date only if all its D1 rows 15:19-15:59 have ticked == 1 "
                            "(or keep_strict in d1_days.csv)",
        },
        "carry_forward_bars_in_d1": int((d1["ticked"] == 0).sum()) if len(d1) else 0,
        "usable_day_bar_counts": {
            "rth_bars_expected": N_RTH_BARS,
            "min": int(rth_per_kept.min()) if len(kept) else None,
            "median": float(rth_per_kept.median()) if len(kept) else None,
            "days_with_all_390": int((rth_per_kept == N_RTH_BARS).sum()),
            "days_missing_0930_bar": int((~kept["has_0930"]).sum()),
            "days_missing_1000_bar": int((~kept["has_1000"]).sum()),
            "days_missing_1550_or_1551_bar": int((~(kept["has_1550"] & kept["has_1551"])).sum()),
        },
        "largest_1m_move_in_usable_days": big,
        "n_rows_d1": int(len(d1)),
        "by_year": per_year,
        "notes": [
            "No-update minutes: runs of 1-4 are kept as carry-forward bars (ticked = 0); runs of >= 5, "
            "or a run starting at 09:30, are missing (not written). See build_d1.py docstring.",
            "Bars are labelled by ET start time (zoneinfo America/New_York); 15:59 bar ends at 16:00.",
            "Only Monday-Friday UTC files are fetched; weekends are counted from the calendar.",
            "Usable = full NYSE session with all 41 bars 15:19-15:59 ET; other bars may be missing "
            "(see has_0930 / has_1000 etc. in d1_days.csv).",
            "Prices are the Dukascopy CFD BID, not the SPX index; see d1_validation.json.",
        ],
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    COVERAGE_JSON.write_text(json.dumps(coverage, indent=2, default=str))
    return coverage


def _clock_evidence(old: pd.DataFrame | None, new: pd.DataFrame | None) -> dict:
    """Why the old feed is excluded: where each session's quotes start, and where the 10:00 ET
    data-release spike lands (mean bar range in bps), old feed vs the kept 2013 data."""
    out = {}
    for name, frame in (("delayed_feed_2011_2013", old), ("kept_feed_2013", new)):
        if frame is None or not len(frame):
            continue
        rng = (frame["high"] - frame["low"]) / frame["close"] * 1e4
        prof = rng.groupby(frame["time_et"]).mean()
        first = frame.groupby("date")["time_et"].min().value_counts().head(3)
        out[name] = {
            "days": int(frame["date"].nunique()),
            "most_common_first_bar_et": {k: int(v) for k, v in first.items()},
            "mean_range_bps": {t: round(float(prof[t]), 2) for t in ("09:59", "10:00", "10:01", "10:19", "10:20", "10:21")
                               if t in prof},
        }
    out["fomc_check_2012"] = ("FOMC statements at 12:30 ET (2012-01-25, 04-25, 06-20, 09-13, 12-12) had their widest "
                              "bar at 12:47-12:56; at 14:15 ET (2012-08-01) at 14:34. In kept data (2013-03-20, "
                              "2013-12-18, 2019-07-31, 2024-09-18) the widest bar is 14:00.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", help="default: first day with a data file")
    ap.add_argument("--end", default=fd.END_DEFAULT.isoformat())
    args = ap.parse_args(argv)
    start = date.fromisoformat(args.start) if args.start else first_data_day()
    if start is None:
        print("no raw files found", file=sys.stderr)
        return 1
    cov = build(start, date.fromisoformat(args.end))
    print(json.dumps({k: cov[k] for k in ("first_weekday_with_session_ticks", "excluded_before_range", "range", "first_usable_day",
                                          "last_usable_day", "weekdays_in_range", "usable_days",
                                          "dropped_by_reason", "half_day_detection",
                                          "strict_rule_sensitivity", "carry_forward_bars_in_d1",
                                          "usable_day_bar_counts")},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
