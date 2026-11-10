# Pre-registration: does any candle predict the SPX close move? (candle scan)

Fixed 2026-10-21 before any number in this scan was computed. Known before writing: from
`spx_1549_close.md`, the 15:50 one-minute candle's direction (P3) predicts r(15:51 -> close) on 2013-2026
(52.6% hit, NW t 4.09) and ranks 1st of 343 minute placebos, but only 30th in 2023-2026; P1, P2 and P4 fail.
Because P3 is known, it is included only as a reference row, never as a "discovery".

## Data and split

- D1 = `data/spx_1549/d1_usa500_rth_1m.csv.gz` with the `keep` day set from `data/spx_1549/d1_days.csv`
  (2013-02-28 .. 2026-10-20).
- DISCOVERY = 2013-02-28 .. 2020-12-31. HOLDOUT = 2021-01-01 .. 2026-10-20. The code must write and hash the
  frozen candidate list (features + direction) BEFORE it reads any holdout return; the holdout step refuses
  to run if the hash file is missing or changed.
- Forward = Robinhood minute data from 2026-10-21 on (descriptive only).

## Targets (all times ET, bars left-labelled)

- Entry 15:49 (features use candles that close by 15:48:59): target r(15:49 open -> 15:59 close).
- Entry 15:51 (features may use the 15:49 and 15:50 candles): target r(15:51 open -> 15:59 close).

## Feature family (each a direction signal in {-1, 0, +1}; the full list is fixed in the params block)

F1 single 1-minute candle direction, sign(close - open), for each minute 15:30 .. 15:50 (21).
F2 candle shapes on the 15:50 1-minute candle and on the 15:45-15:49 five-minute candle (2 x 5 = 10):
   strong body (|body| >= 0.6 range) sign; hammer (lower wick >= 2 body and >= 0.6 range) = +1;
   shooting star (upper wick >= 2 body and >= 0.6 range) = -1; bullish/bearish engulfing vs the prior
   candle of the same size; big candle (|body| >= 2 x the day's median 1-minute range so far) sign.
F3 five-minute candle direction for 15:20, 15:25, 15:30, 15:35, 15:40, 15:45 (6).
F4 day level at entry: close-location value sign(CLV - 0.5), CLV = (P - day low)/(day high - day low);
   opening-gap direction vs the prior close; prior-day candle direction; day-so-far direction (= P1) (4).
Total 41 features (+ P3 as the reference row).

## Tests

Statistic per feature: mean of signal x target in bps, Newey-West t (lag 5), hit rate (zero signals
excluded and counted).
1. Discovery: candidates = features with |t| >= 2.5 in DISCOVERY, at most the 8 largest |t|; direction =
   sign of the discovery mean. Also report Benjamini-Hochberg q-values over all 41 in discovery.
2. Holdout: each candidate with its frozen direction; one-sided test of mean > 0; Holm across candidates at
   5%. A candle "predicts" only if it passes Holm in the holdout.
3. Placebo (descriptive): each candidate rebuilt at 11:49 / 11:51 with target to 11:59 close.
4. Economics: hit rate needed for buying the at-the-money 0DTE call/put at entry to break even, from the
   D1 distribution of |move| on correct vs wrong days and an option cost of half the realized-move-fair
   straddle, with $0.10 half-spread and $0.09 and $0.74 fee cases; and the number of trades needed to
   detect each candidate's holdout edge at 5% with 80% power. Cross-check the straddle-cost assumption on
   the 22 Robinhood 10-minute days and the 2 fully priced days.

## Pass rule

A candle is reported as predictive only if it passes step 2. "Accurate" in plain English means a holdout
hit rate whose 95% CI lower bound exceeds the break-even hit rate from step 4. Everything else is
reported as not predictive, with its numbers.

```toml tradelab-params
data = "data/spx_1549/d1_usa500_rth_1m.csv.gz"
day_set = "keep"
discovery = ["2013-02-28", "2020-12-31"]
holdout = ["2021-01-01", "2026-10-20"]
entries = ["15:49", "15:51"]
target_end = "15:59 close"
n_features = 41
f1_minutes = ["15:30", "15:50"]
f2_candles = ["1m 15:50", "5m 15:45-15:49"]
f2_shapes = ["strong_body_0.6", "hammer_2x_0.6", "shooting_star_2x_0.6", "engulfing", "big_candle_2x_median_range"]
f3_5m_starts = ["15:20", "15:25", "15:30", "15:35", "15:40", "15:45"]
f4 = ["clv_vs_0.5", "open_gap", "prior_day_candle", "day_so_far"]
nw_lag = 5
discovery_abs_t = 2.5
max_candidates = 8
holdout_test = "one-sided, Holm 5%"
half_spread = 0.10
fees = [0.09, 0.74]
placebo_entries = ["11:49", "11:51"]
```
