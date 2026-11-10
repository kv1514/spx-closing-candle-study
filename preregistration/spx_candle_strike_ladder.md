# Pre-registration addendum: which strike to buy on a 15:50 strong-body signal (strike ladder, descriptive)

Addendum to `spx_close_candle_scan.md` and `spx_candle_forward_options.md`. Written 2026-11-07 before any
option profit or loss at a strike other than the at-the-money one was computed, and before any volatility fit,
skew ratio or realized-volatility figure used below was computed. Descriptive only: no test, no pass/fail rule,
and nothing here is a trading recommendation.

## The question

The 15:50 strong-body signal says which way SPX tends to move from 15:51 to the close. Both the backtest and
the forward log buy the at-the-money (ATM) 0DTE option. This study asks how the result changes with the strike:
deeper in the money (more expensive, behaves more like the index) or further out of the money (cheaper, needs a
bigger move). It reports dollars per contract and return on the premium paid, for each strike.

## What was known when this was written (disclosed so the rules can be judged)

- Forward ATM option results (`backtests/spx_candle_scan/FORWARD_OPTIONS.md`, rebuilt 2026-11-07): strong body
  4 finalized exit-A trades (10-22 call 7660, 10-27 put 7730, 10-29 call 7715, 10-30 call 7580), 2 wins,
  total -$69.36 at the $0.09 fee; exit B total -$173.72. Each ATM row's prices are in
  `data/spx_1549/forward/options_log.csv`. Model check: 6 days, mean ATM straddle 8.71 bps, market/model
  0.78 (strong-body model) and 0.81 (any-candle model).
- The backtest's strong-body economics at level 7709.58 (`holdout.json`, `at_last_level`): 644 trades
  2021-01-01 .. 2026-10-20, 57.45% right, mean |move| 8.60 points, 9.07 on right days and 7.97 on wrong days,
  mean signed move +1.82 points; idealised ATM at half the realized-move-fair straddle: +$80.89 a trade
  ($0.09 fee). Subperiods: 63.0% right in 2021-2022, 54.7% in 2023-2026.
- The 22-day 10-minute straddle cross-check (`holdout.json`, `straddle_cost_crosscheck`): market straddle
  about 7.75 bps, 0.90x its own payoff (95% CI 0.62-1.38).
- During the 2026-11-07 backfill I checked the Nov 2-6 option files only for gap-fill flags (all of Nov 6's
  minute bars were gap-fill). No option price away from ATM was read for any purpose, and no implied
  volatility, skew ratio or realized volatility in this file has been computed.
- Before this file was hashed, `strikes.py`'s loaders were run on the real files to count days and contracts
  only (no price, fit or P&L was printed): C1 = 7 days (2026-10-20 from chunk C; 2026-10-21 with 10 contracts;
  2026-10-22, 10-26, 10-27, 10-29, 10-30 with 26 each); 22 days in both D1 and the Robinhood SPX chunk files;
  22 ten-minute days; forward days with minute option bars: 10-21, 10-22, 10-26, 10-27, 10-29, 10-30 (none
  for 10-23, 10-28 or 11-02 .. 11-06). The script's `selftest` runs on synthetic data only.

## Strike ladder

- S = the SPX 15:51 one-minute bar open. ATM strike K_atm = floor(S / 5 + 0.5) x 5 (scan.py's rounding).
- Offsets o = +20, +15, +10, +5, 0, -5, -10, -15, -20 index points. **Positive o = in the money (ITM) in the
  trade's direction, negative = out of the money (OTM).** Signal up: buy the call at K = K_atm - o. Signal
  down: buy the put at K = K_atm + o. Example: signal up, K_atm 7700, o = -10 (OTM10) is the 7710 call.
- Costs as before: $0.10 half-spread added to the entry price (and subtracted from a sale), fee $0.09 per
  contract per side (primary) or $0.74; no fee at expiry. Multiplier 100.
- Return on premium = P&L / (100 x entry price incl. half-spread + entry fee).

## Part 1: real prices on forward days (descriptive)

- Days and signals: as in `spx_candle_forward_options.md`: every forward date (>= 2026-10-21) with an
  `SPX_robinhood` row of status `ok` in `data/spx_1549/forward/candle_1550_log.csv`; headline
  `F2_1m_1550_strong_body`, also logged `F1_1m_15:50`. Signal, S and the 15:59 close are taken from that log.
- For each day, signal and offset: entry = the contract's 15:51 one-minute bar `open_price` (not gap-fill,
  above 0) + $0.10; exit A = intrinsic value at the official SPX close (newest `live_*/spx_daily.json` that has
  it, else the 15:59 bar close and the row is `provisional`, left out of totals); exit B = the contract's 15:59
  one-minute bar `close_price` - $0.10, fee on both sides. Statuses instead of P&L: `no_minute_option_bars`,
  `strike_not_collected`, `entry_bar_missing`, `exit_bar_missing` (exit B only). Contract ids from `ids.json`
  with the OCC-symbol check of the existing options script.
- Report per signal and offset: trades, wins (P&L > 0), total and mean P&L for both exits and both fees, mean
  return on premium (exit A, $0.09). Also the per-day rows.
- Market check, every forward day with minute option bars, signal or not: for each offset, the mean exit-A P&L
  of buying the call and of buying the put (what the market charged against what the options paid).

## Part 2: modelled 2021-2026 strong-body sample

The backtest has no option prices, so each strike is priced with a simple model calibrated to the Robinhood
option prices that exist. This is a model, not observed P&L, and every table must say so.

### Days and outcome

- D1 (Dukascopy US500 one-minute bars, `keep` days) from 2021-01-01 to 2026-10-20 where the frozen
  `F2_1m_1550_strong_body` signal is +1 or -1, computed with `scan.py`'s own functions. The script stops
  unless this gives exactly the backtest's 644 trades.
- S = D1 15:51 open, X = D1 15:59 close (the CFD proxy for the settlement, as in the backtest). Everything is
  rescaled to the level L = 7709.58 (the backtest's `at_last_level`): with lambda = L / S, S' = L,
  X' = L + lambda (X - S), K_atm' = L + lambda (floor(S / 5 + 0.5) x 5 - S), and the strike for offset o is
  K_atm' - o (call) or K_atm' + o (put), o in points at level L.
- Payoff = intrinsic value at X' (exit A only; no exit B in the model).

### Pricing model

- Bachelier (normal) price with no rates: call = (S - K) N(d) + sigma n(d), put = (K - S) N(-d) + sigma n(d),
  d = (S - K) / sigma, where sigma is the standard deviation in index points of the move from entry to the
  close.
- Realized volatility RV of a day: the root mean square of the one-minute log returns close-to-close between
  consecutive bars beginning 09:30 .. 15:50 (returns for bars 09:31 .. 15:50), using only pairs where both
  bars exist and are real; a day with fewer than 300 such returns is left out (D1 keep days are complete).
- Model sigma for a D1 day: sigma' = k_D1 x RV_D1 x 3 x L (3 = sqrt of the 9 minutes 15:51 .. 15:59).
- Model price at offset o: f_o x Bachelier(S', K', sigma'), where f_o is the skew factor below.

### Calibration (fixed rules; the values come from the data)

1. **Implied sigma on one-minute days.** Calibration days C1 = every date with real (not gap-fill) 15:51
   one-minute option bars: the forward `live_*` folders with minute files and 2026-10-20 from
   `d2_chunk_C_options_1m.csv`. S = that day's Robinhood SPX 15:51 one-minute open. Using the contracts with a
   real 15:51 bar and open above 0, among calls with K >= K_atm and puts with K <= K_atm (out of the money,
   both legs at K_atm), within K_atm +- 30: sigma_d = the value in [0.1, 100] points minimizing the sum of
   squared differences between the 15:51 opens and the Bachelier prices. A day needs at least 6 such contracts.
2. **Volatility ratio.** k_RH_d = sigma_d / (RV_RH_d x 3 x S_d), with RV_RH from that day's Robinhood SPX
   one-minute bars (`live_*/spx_1m.json`, or `d2_chunk_*_spx_1m.csv`). k_RH = the median over C1.
3. **Robinhood vs Dukascopy realized volatility.** c = the median over the days in both D1 (keep) and the
   Robinhood SPX one-minute files `d2_chunk_B_spx_1m.csv` / `d2_chunk_C_spx_1m.csv` (real bars) of
   RV_RH / RV_D1. Then k_D1 = k_RH x c.
4. **Skew factors.** For each C1 day, side (call for an up trade, put for a down trade) and offset o, the
   ratio of the contract's 15:51 open to Bachelier(S, K, sigma_d). f_o = the median of the ratios over all
   day-side pairs with a real bar (at least 5 ratios; otherwise f_o = 1, reported).

### Variants (all reported; (a) is the headline)

- (a) Calibrated: as above.
- (b) Constant volatility: sigma' = median over C1 of (sigma_d / S_d) x L for every day (no RV scaling), with f_o.
- (c) Realized-move-fair, the backtest's assumption: constant sigma' with an ATM straddle (K = S) equal to the
  backtest's mean |move| 8.599455 points, i.e. sigma' = 8.599455 / (2 n(0)), and f_o = 1. Self-check: with
  K = S exactly, offset 0, $0.10 and the $0.09 fee, (c) must reproduce the backtest's +$80.89 a trade to
  within $0.01, or the run stops.
- (d) 10-minute calibration of the volatility ratio, instead of steps 1-3: days in both D1 (keep) and
  `d2_chunk_B/C_options_10m.csv` (2026-09-21 .. 2026-10-20); price = the 10-minute bar beginning 15:40's
  close (the last trade before about 15:50, as in the backtest's cross-check), S = Robinhood SPX 15:49
  one-minute close, sigma_d fitted as in step 1; k10_d = sigma_d / (RV_D1_d x sqrt(10) x S_d); k = median.
  Used with f_o.
- Cost sensitivities on (a): half-spread $0.05 and $0.20 instead of $0.10; k_D1 x 0.75 and x 1.25; f_o = 1.

### Reporting for Part 2

For each variant and offset: mean model price, mean P&L per contract ($0.09 and $0.74 fees), Newey-West
(lag 5) t of the mean, share of trades with P&L > 0, mean and median return on premium, and the paired
difference from ATM (mean and Newey-West t). For (a) also 2021-2022 and 2023-2026 separately. A line per
variant names the offset with the highest mean P&L per contract and the one with the highest mean return on
premium; this is a description of the model, not a test.

## Text rules

- Say plainly that Part 1 has only a handful of signal days and supports no conclusion.
- Say plainly that Part 2 prices options with a model calibrated on a few weeks of 2026 data, measures the
  outcome on a CFD to 15:59 rather than the settlement, and assumes the same half-spread at every strike
  (real spreads are wider in the money and the minimum tick matters most for cheap OTM options).
- No trading recommendation.

## Outputs

`data/spx_1549/forward/strikes_forward_log.csv`, `backtests/spx_candle_strikes/results.json` and
`backtests/spx_candle_strikes/RESULTS.md`, rebuilt from scratch on each run by
`backtests/spx_candle_strikes/strikes.py`, which refuses to run on real data unless this file is in
`preregistration/` and its SHA-256 is in `preregistration/LEDGER.md`.
