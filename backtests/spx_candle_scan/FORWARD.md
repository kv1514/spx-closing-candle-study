# Forward log: the 15:50 candle signals (descriptive only)

This page is rebuilt by `analysis/candle_1550_forward.py` from whatever data is on disk. Do not edit it
by hand; re-run the script instead. It is a log, not a test: the pre-registration
(`preregistration/spx_close_candle_scan.md`) says the forward period is "Robinhood minute data from
2026-10-21 on (descriptive only)". Nothing here is trading advice.

## What is logged

For every full regular NYSE session, one row per data source in
`data/spx_1549/forward/candle_1550_log.csv`:

- **The 15:50 one-minute candle** (the bar from 15:50:00 to 15:50:59 ET): open, high, low, close, body
  and range.
- **Strong body**: 15:50 candle, strong body (passed the holdout test and the accuracy bar; overlaps the known P3 effect, not a blind pass). The body is at least 60% of the candle's range (and the
  range is above zero), tested exactly as `scan.py` tests it. Its direction is up if the candle closed
  above its open, down if below.
- **The move it is scored on**: from the open of the 15:51 bar to the close of the 15:59 bar, in basis
  points, `r_bps = 10,000 x ln(exit / entry)`. A **hit** means the move went the candle's way. A move of
  exactly zero is counted separately and, in a second column, as a miss.
- **Also logged**: 15:50 candle direction, any body (passed the holdout test, not the accuracy bar; overlaps the known P3 effect, not a blind pass); P3 reference (15:50 open -> 15:51 open direction; known before the scan); and
  Day so far, 09:30 open -> 15:49 open direction (failed the holdout test; this is the known P1), scored from the 15:49 open to the 15:59 close.
- **Source** and **period**. `SPX_robinhood` is Robinhood's SPX index minute bars, the pre-registered
  forward source and the headline. `SPY_recorder` is the SPY one-minute bars the daily recorder saves, a
  stand-in for SPX. The two are tallied separately. `mixed_SPX_else_SPY` (SPX when it has a full session,
  else SPY) is not pre-registered and is shown last. `FORWARD` days are 2026-10-21 or later; `OVERLAP` days
  are earlier, inside the 2021-2026 holdout, and are only used to check the data.

A session is skipped if it is a half-day (13:00 close), if any one-minute bar from 15:49 to 15:59 is
missing, if 3 or more of those bars are flat (high = low), or, for Robinhood, if the file that supplied the
15:59 bar has no later bar (it may have been saved before 16:00 ET). A session with no file gets a `no_data`
row. Robinhood bars marked as interpolated (gap-fill) and bars with impossible prices are thrown away first.
Bars beginning after 15:59 ET are discarded during ingestion and never used in signals or targets. The
directions are the frozen ones in `candidates.json`, checked against its SHA-256.

## How to run it

```
PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B analysis/candle_1550_forward.py
PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B analysis/tests/test_candle_1550_forward.py
```

It reads local files only and rebuilds every output from scratch, so running it twice gives the same
files. Run it after the recorder has saved the day's SPY bars (after about 16:30 ET), or after a new
`data/spx_1549/live_YYYY-MM-DD/spx_1m.json` has been saved. Save that file after 16:01 ET so that it holds
a bar after 15:59; otherwise the day is skipped as possibly unfinished. SPY bars are kept only if the
recorder fetched them at least 5 minutes after the bar ended.

## Current forward tally

- **SPX_robinhood** (pre-registered): 14 of 14 forward NYSE session(s) logged. On disk in all: 36 full sessions (22 overlap).
- **SPY_recorder** (stand-in): 14 of 14 forward NYSE session(s) logged. On disk in all: 35 full sessions (21 overlap).
- Forward NYSE sessions so far: 14 (2026-10-21 to 2026-11-09, the latest date on disk).

| Signal | Source | Forward days with a signal | Hits | Zero moves | Hit rate (95% CI) | Mean move in the signal's direction (bps) |
|---|---|---|---|---|---|---|
| 15:50 candle, strong body (passed the holdout test and the accuracy bar; overlaps the known P3 effect, not a blind pass) | SPX_robinhood | 8 | 7 | 0 | 87.5% (52.9-97.8%) | +6.93 |
| 15:50 candle, strong body (passed the holdout test and the accuracy bar; overlaps the known P3 effect, not a blind pass) | SPY_recorder | 7 | 6 | 0 | 85.7% (48.7-97.4%) | +5.59 |
| 15:50 candle, strong body (passed the holdout test and the accuracy bar; overlaps the known P3 effect, not a blind pass) | mixed_SPX_else_SPY (not pre-registered) | 8 | 7 | 0 | 87.5% (52.9-97.8%) | +6.93 |
| 15:50 candle direction, any body (passed the holdout test, not the accuracy bar; overlaps the known P3 effect, not a blind pass) | SPX_robinhood | 14 | 12 | 0 | 85.7% (60.1-96.0%) | +5.90 |
| 15:50 candle direction, any body (passed the holdout test, not the accuracy bar; overlaps the known P3 effect, not a blind pass) | SPY_recorder | 14 | 11 | 0 | 78.6% (52.4-92.4%) | +5.32 |
| 15:50 candle direction, any body (passed the holdout test, not the accuracy bar; overlaps the known P3 effect, not a blind pass) | mixed_SPX_else_SPY (not pre-registered) | 14 | 12 | 0 | 85.7% (60.1-96.0%) | +5.90 |
| P3 reference (15:50 open -> 15:51 open direction; known before the scan) | SPX_robinhood | 14 | 12 | 0 | 85.7% (60.1-96.0%) | +5.90 |
| P3 reference (15:50 open -> 15:51 open direction; known before the scan) | SPY_recorder | 13 | 11 | 0 | 84.6% (57.8-95.7%) | +6.08 |
| P3 reference (15:50 open -> 15:51 open direction; known before the scan) | mixed_SPX_else_SPY (not pre-registered) | 14 | 12 | 0 | 85.7% (60.1-96.0%) | +5.90 |
| Day so far, 09:30 open -> 15:49 open direction (failed the holdout test; this is the known P1) | SPX_robinhood | 14 | 5 | 0 | 35.7% (16.3-61.2%) | -4.33 |
| Day so far, 09:30 open -> 15:49 open direction (failed the holdout test; this is the known P1) | SPY_recorder | 14 | 3 | 0 | 21.4% (7.6-47.6%) | -6.84 |
| Day so far, 09:30 open -> 15:49 open direction (failed the holdout test; this is the known P1) | mixed_SPX_else_SPY (not pre-registered) | 14 | 5 | 0 | 35.7% (16.3-61.2%) | -4.33 |

So far there are **8 strong-body forward day(s) in SPX_robinhood**, the pre-registered source (7 in SPY_recorder, the stand-in). That is far too few to say anything.

Exact-decimal sensitivity (not the binding test; it counts a body of exactly 60% of the range as strong after normalising the prices): it agrees with the binding test on every forward day so far. On overlap days it differs on 1: 2026-10-05 SPY_recorder (binding test none, exact-decimal down; body/range as stored 59.9976%).

Latest forward sessions (each source, up to 15 rows):

| Date | Source | 15:50 body / range | Strong body | 15:50 direction | Move 15:51 to 15:59 close (bps) | Strong body hit | Direction hit |
|---|---|---|---|---|---|---|---|
| 2026-10-29 | SPY_recorder | 89.1% | up | up | +12.35 | yes | yes |
| 2026-10-30 | SPX_robinhood | 99.2% | up | up | +0.77 | yes | yes |
| 2026-10-30 | SPY_recorder | 97.9% | up | up | +0.13 | yes | yes |
| 2026-11-02 | SPX_robinhood | 92.4% | down | down | -6.02 | yes | yes |
| 2026-11-02 | SPY_recorder | 86.2% | down | down | -3.06 | yes | yes |
| 2026-11-03 | SPX_robinhood | 92.4% | down | down | +8.55 | no | no |
| 2026-11-03 | SPY_recorder | 85.3% | down | down | +7.29 | no | no |
| 2026-11-04 | SPX_robinhood | 58.8% | none | down | -6.70 | - | yes |
| 2026-11-04 | SPY_recorder | 47.9% | none | down | -4.17 | - | yes |
| 2026-11-05 | SPX_robinhood | 16.0% | none | down | -17.06 | - | yes |
| 2026-11-05 | SPY_recorder | 12.1% | none | down | -21.53 | - | yes |
| 2026-11-06 | SPX_robinhood | 90.8% | down | down | -14.09 | yes | yes |
| 2026-11-06 | SPY_recorder | 79.5% | down | down | -12.78 | yes | yes |
| 2026-11-09 | SPX_robinhood | 61.7% | down | down | -17.79 | yes | yes |
| 2026-11-09 | SPY_recorder | 57.5% | none | down | -17.06 | - | yes |

## How many strong-body days a firm answer would take (planning estimates)

In 2021-2026 a strong body showed up on about 112 days a year (Dukascopy data). The table gives the
number of strong-body days a one-sided 5% test would need for 80% power, with the formula and inputs of
`holdout.json`. These are illustrative planning numbers, not deadlines. Each assumes that the true hit
rate equals a past period's, that strong bodies stay as frequent, and, for the break-evens, `scan.py`'s
option-cost model (half the realized-move-fair straddle, $0.10 half-spread, $0.09 fee). The break-evens
are model outputs, not observed option prices, and this log records no option P&L.

| Question | If the 2021-2026 hit rate holds (57.5%) | If the 2023-2026 hit rate holds (54.7%) |
|---|---|---|
| Hit rate above the primary break-even (49.5%) | 244 days (about 2.2 years) | 580 days (about 5.2 years) |
| Hit rate above the size-neutral break-even (51.8%) | 483 days (about 4.3 years) | 1,916 days (about 17.1 years) |
| Mean option P&L per trade above zero | 808 days (about 7.2 years) | 2,165 days (about 19.3 years) |

The primary break-even is below 50% because moves on right days were bigger than on wrong days in
2021-2026, and the size of that pattern was not stable across periods; the size-neutral break-even does not
rely on it.
The 2023-2026 size-neutral count uses that period's own size-neutral break-even, as in
`holdout.json`. A smaller sample still carries some information, and reaching these counts would not make
a conclusion certain. Until the sample is much larger, the tally is a descriptive record, and a short run
of hits or misses is weak evidence either way.

## Does the data agree with the backtest data? (overlap days)

On days before 2026-10-21 the same signals were computed from the Dukascopy US500 data that `scan.py`
used, with `scan.py`'s own code. Agreement with each forward source:

| Check | SPX_robinhood vs Dukascopy | SPY_recorder vs Dukascopy | SPX vs SPY |
|---|---|---|---|
| Days compared | 22 | 21 | 21 |
| Strong body: same yes/no | 17/22 (77.3%) | 19/21 (90.5%) | 19/21 (90.5%) |
| Strong body: same signal (up/down/none) | 17/22 (77.3%) | 19/21 (90.5%) | 19/21 (90.5%) |
| Strong-body days: first feed / second feed | 54.5% / 31.8% | 42.9% / 33.3% | 52.4% / 42.9% |
| 15:50 direction: same | 20/22 (90.9%) | 20/21 (95.2%) | 20/21 (95.2%) |
| P3: same | 21/22 (95.5%) | 20/21 (95.2%) | 21/21 (100.0%) |
| Move 15:51 to 15:59 close: correlation | 0.972 | 0.997 | 0.979 |
| Move 15:51 to 15:59 close: same sign | 19/22 (86.4%) | 20/21 (95.2%) | 18/21 (85.7%) |
| Move: mean / median absolute difference (bps) | 1.61 / 1.06 | 0.70 / 0.65 | 1.25 / 0.92 |

The two strong-body agreement rows differ only on a day when both feeds flag a strong body in opposite
directions. The 60% cut-off is sharp, so a candle near it can be strong in one feed and not in the other.
In the "Strong-body days" row the two shares are in the order of the column title. Over 2021-2026
Dukascopy had a strong body on 44.5% of days (644 of 1,446).

Largest differences in the 15:51-to-close move, SPX_robinhood vs Dukascopy: 2026-10-05 (-1.17 vs +5.33, opposite signs); 2026-10-20 (+3.51 vs +9.83); 2026-10-02 (-2.90 vs -0.22). Median absolute difference 1.06 bps.

Largest differences in the 15:51-to-close move, SPY_recorder vs Dukascopy: 2026-10-01 (-17.26 vs -15.52); 2026-10-05 (+3.81 vs +5.33); 2026-10-16 (+6.95 vs +8.31). Median absolute difference 0.65 bps.

Code check: this script's own calculation, run on the same Dukascopy bars, reproduced every `scan.py` signal and target on all 22 overlap days.

Bar labels: every check that had data points to start-time labels, as `scan.py` uses (SPX_robinhood_vs_SPY_recorder: best lag 0 min (21 days); SPX_robinhood_vs_SPY_recorder_FORWARD: best lag 0 min (14 days); SPX_robinhood_vs_d1: best lag 0 min (22 days); SPY_recorder_vs_d1: best lag 0 min (21 days)). Timestamped SPX quotes: 7 of 7 lie inside the bar that starts in their minute (3 would fit the bar labelled one minute later).

## Caveats

- The move is measured to the close of the 15:59 bar, as in the backtest. SPX options settle on the
  official closing value, which can differ.
- **SPX_robinhood candles are shaped differently from the backtest's.** Over every minute 09:31-15:58 on 22 overlap days, 45.5% of SPX_robinhood one-minute candles have a strong body, against 37.3% of Dukascopy's on the same minutes (median body/range 0.552 vs 0.490). SPX_robinhood is higher on 21 of 22 days (mean gap +8.2 points, paired t 10.0).
  So SPX_robinhood flags strong bodies more often than the backtest data did and its strong-body days are a different selection of candles: its forward hit rate is not a like-for-like
  check of the backtest. A cut-off of 0.675 instead of 0.6 would match Dukascopy's share (descriptive only; the log keeps the frozen 0.6).
- **SPY_recorder candles are shaped differently from the backtest's.** Over every minute 09:31-15:58 on 21 overlap days, 34.5% of SPY_recorder one-minute candles have a strong body, against 37.0% of Dukascopy's on the same minutes (median body/range 0.450 vs 0.488). SPY_recorder is higher on 4 of 21 days (mean gap -2.5 points, paired t -4.1).
  So SPY_recorder flags strong bodies less often than the backtest data did and its strong-body days are a different selection of candles: its forward hit rate is not a like-for-like
  check of the backtest. A cut-off of 0.572 instead of 0.6 would match Dukascopy's share (descriptive only; the log keeps the frozen 0.6).
- SPY is a stand-in. It trades on its own and can disagree with SPX on a small candle.
- The SPX index's 15:59-bar close can lag the tradable feeds by a few seconds. On 2026-10-20 Dukascopy
  (high 7717.09) and SPY (high 769.11) rallied in the last seconds of the 15:59 bar; the Robinhood SPX bar
  topped at 7712.22 and closed at 7711.70, the index then opened its 16:00 bar at 7714.52, and the official
  close was 7712.57. This is not a data error. Index and CFD price levels also differ by a basis, so only
  moves are compared, never levels.
- Robinhood SPX minute files are saved by hand, so coverage depends on someone saving them. Every forward
  session gets a row (`no_data` if nothing was saved), so gaps are visible; a gap is not filled by SPY in the
  pre-registered tally. The mixed series does fill it, which is why it is not the headline.
- This page reports what happened. It does not recommend any trade.

## Files

| File | What it is |
|---|---|
| `analysis/candle_1550_forward.py` | Builds everything on this page. |
| `analysis/tests/test_candle_1550_forward.py` | Unit tests on hand-built sessions. |
| `data/spx_1549/forward/candle_1550_log.csv` | One row per session per source, skipped and no-data sessions included with the reason. |
| `data/spx_1549/forward/overlap_vs_dukascopy.csv` | Overlap days: each source next to `scan.py`'s Dukascopy values. |
| `data/spx_1549/forward/summary.json` | All tallies (forward and overlap kept apart), checks and the decisions made. |
