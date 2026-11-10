# Pre-registration addendum: real SPXW prices to tune the candle, the threshold, the direction and the strike

**Status: locked 2026-11-09.** Locked by Claude at the user's explicit instruction ("Lock it"), with the five
open questions answered as Claude recommended and the user accepted (see "Decisions made at locking"). It was
locked before any option price, implied spot or P&L had been computed from the Databento quotes. Drafted
2026-11-09.

Addendum to `spx_close_candle_scan.md`, `spx_candle_forward_options.md`, `spx_candle_strike_ladder.md` and
`spx_candle_exit_rules.md`. One stated criterion; everything else is descriptive. Nothing here is a trading
recommendation.

## The question

The current rule is: on the 15:50 one-minute candle, if the body is at least 60% of the range, buy a 0DTE SPXW
option in the candle's direction at 15:51. Buy a call if the candle was up, a put if it was down, 10 points in
the money (ITM10), and hold it to settlement. Every result so far priced the options with a model. This study
uses real quotes from Databento OPRA to ask three things:

1. **Tuning (2013-04-01 .. 2020-12-31, discovery).** Which candle minute (15:40 to 15:50), which body threshold
   (40% to 90%), which direction (with or against the candle) and which strike (ITM20 to OTM20) did best at real
   prices? And is the best one clearly better than the current rule, or just the luckiest of 2,178 tries?
2. **Confirmation (2021-01-01 .. 2026-10-20, one test).** Does ONE configuration make money at real prices on
   days the tuning never saw? It is the tuned pick if the pick clearly beat the current rule on discovery, else
   the current rule.
3. **Model check (2021-2026, descriptive).** How close were the strike ladder's model prices and model P&L to
   the real ask and the real P&L on the same days?

After this, the forward collector stays the real test.

## What was known when this was drafted (disclosed so the rules can be judged)

- **Index outcomes 2013-2020.** The candle scan used the D1 (Dukascopy US500) one-minute outcomes of 2013-2020
  to choose F2 (15:50 strong body at 0.6, with the candle) from its list of features. The discovery period
  here is therefore not fresh for index moves. That is acceptable for tuning; the luck check below is what
  guards the pick.
- **Index outcomes 2021-2026.** These were already used to test F2 at 0.6 (`holdout.json`: 644 trades, the
  sign right 57.45% of the time, mean |move| 15:51-15:59 of 8.60 points at level 7709.58). **The confirmation
  is therefore fresh for real option prices and for any changed setting, but not for the current rule's index
  outcomes.**
- **Model results.** Everything in `backtests/spx_candle_strikes/RESULTS.md`: 10-20 points in the money held up
  best in the model, and ITM10 was made the headline after seeing that. Also the calibration it produced, reused
  here unchanged for the model check: k_D1 = 1.065101699231275 and the skew factors f_o in
  `backtests/spx_candle_strikes/results.json`.
- **Exits.** `backtests/spx_candle_exits/RESULTS.md`: in the model, none of six stop or take-profit rules beat
  holding to the close. This study therefore only holds to settlement.
- **Real option prices.** The Databento download (`cbbo-1m`, 15:00-16:01 ET, the 25 strikes within 60 points of
  the D1 15:51 ATM, calls and puts, one file per day, a `.none` marker on days with no same-day expiry) was
  still running when this was drafted (388 of about 3,287 day files). Only the file header, the
  timestamp/symbol format and a few rows of early-2013 files have been looked at, to learn the format: the
  `price` field can be empty and a bid can be 0. No implied spot, option P&L, price-to-model ratio or any other
  statistic has been computed from these quotes on any day. The cost estimate used Databento's metadata cost
  call, which returns no prices.
- **Forward days.** The real Robinhood quotes for the 4 forward trades (after 2026-10-20) are known. They are
  outside both periods here.

## Data

- **Signal:** the D1 one-minute panel (`scan.load_panel`), the same days the scan used.
- **Option quotes:** `data/spx_1549/databento/cbbo-1m_1500-1601_k60/`. A row stamped HH:MM:00 ET in `ts_recv`
  is the consolidated best bid and offer at that instant, the open of minute HH:MM. Only contracts expiring
  that day are used.
- **Settlement:** Cboe's official SPX daily close (`SPX_History.csv` from cdn.cboe.com), downloaded once to
  `data/spx_1549/spx_official_closes_cboe.csv`. No other source is used. Before any option is priced, the Cboe
  closes are checked against the Robinhood closes in `data/spx_1549/live_*/spx_daily.json`. They must agree
  within 0.01 on every overlapping day (at least 3 days), or the run stops.
- **Days:** a D1 day enters only if it has a quote file (not `.none`) and an official close. If any D1 day in
  2013-04-01 .. 2026-10-20 has neither a file nor a `.none` marker, the download is incomplete and the run
  stops. Before 2016 SPXW had a same-day expiry only on Fridays (and some month-ends), then on Monday,
  Wednesday and Friday, and daily from 2022. So discovery has far fewer days than confirmation, and those days
  fall on different weekdays.

## The grid (2,178 cells, fixed)

| Setting | Values |
|---|---|
| Candle (D1 one-minute) | 15:40, 15:41, ..., 15:50 (11) |
| Entry | the next minute's open: 15:41 ... 15:51 |
| Body threshold θ | 0.40, 0.45, ..., 0.90 (11) |
| Direction | with the candle, against the candle (2) |
| Strike | ITM20, ITM15, ITM10, ITM5, ATM, OTM5, OTM10, OTM15, OTM20 (9) |

- **Signal:** with body = close − open and range = high − low on the chosen candle, the signal fires when range
  > 0 and |body| ≥ θ × range. Its sign is sign(body), multiplied by +1 (with) or −1 (against). A candle with a
  missing bar gives no value that day. At 15:50, 0.60, with, this is exactly scan.py's F2. The run checks that
  on every day and stops if any day differs.
- **Spot and strike:** at the entry minute, take the strikes where both the call and the put have a valid quote
  with a bid above 0. Pick the 3 strikes where call mid and put mid are closest. Implied spot S = the median of
  K + call mid − put mid over those 3. ATM = floor(S / 5 + 0.5) × 5. An up signal buys the call at ATM − o and
  a down signal buys the put at ATM + o (o = +20 ... −20; positive is in the money).
- **Valid quote:** ask > 0 and 0 ≤ bid ≤ ask.
- **Price and P&L:** buy at the ask at the entry minute's open and hold to settlement. P&L per contract = 100 ×
  (intrinsic value at the official close − ask) − $0.09. Every decision and the criterion use this. Two
  descriptive versions are also reported for the chosen configuration and the current rule, and decide nothing:
  the $0.74 fee, and buying at the mid instead of the ask.
- **Not priced:** no implied spot at that minute, or no valid quote for that contract (including a strike
  outside the downloaded ±60 points). That trade day is left out of that cell, and the counts are reported.

## Per-day series

For each cell and day: the trade's P&L on a signal day, 0 on a day with no signal, and missing if the candle
was missing or the trade could not be priced. "Mean per day" is the average over the non-missing days. It
counts how often a cell trades as well as how well, so a rare cell with large trades and a frequent cell with
small ones are compared on money per day.

## Part 1: tuning on discovery (2013-04-01 .. 2020-12-31)

- **Score:** the plateau mean, the average of a cell's mean per day and its neighbours at θ ± 0.05 (those that
  exist on the grid). This favours a setting whose neighbours also work over a single sharp peak.
- **Eligible:** at least 150 trades in discovery, at least 50 in each half (2013-04-01 .. 2016-12-31 and
  2017-01-01 .. 2020-12-31), and a mean per day above 0 in both halves.
- **Pick:** the eligible cell with the highest score. A tie goes to the cell nearest the current rule (fewest
  grid steps). If nothing is eligible, the current rule goes to confirmation.
- **Luck check:** shift the signal's day order circularly against the outcome days, by every shift from 21 days
  to n − 21 days in steps of 3. For each shift, recompute every cell, its score and its eligibility, and keep
  the best eligible score. p = (1 + number of shifts whose best ≥ the observed best) / (1 + number of shifts).
- **Switch rule:** the pick replaces the current rule for confirmation only if all three hold:
  1. it differs from the current rule;
  2. p ≤ 0.05;
  3. on discovery, the per-day difference (pick − current) has a mean > 0 with Newey-West t ≥ 2.0 (lag 5).

  Otherwise the current rule (15:50, 0.60, with, ITM10) is what gets confirmed.

## Part 2: confirmation on 2021-01-01 .. 2026-10-20 (the one criterion)

The chosen configuration is **confirmed** only if its per-day P&L on 2021-01-01 .. 2026-10-20 has a mean > 0
with Newey-West t ≥ 2.0 (lag 5). Otherwise the result is "not confirmed at real prices".

If the chosen configuration is not the current rule, the per-day difference (chosen − current) is also
reported. The chosen configuration is called **better than the current rule** only if that mean is > 0 with
t ≥ 2.0.

No other cell is evaluated on 2021-2026, except the descriptive table below.

## Part 3: model check (descriptive, no criterion)

On the strike study's 644 strong-body trades (D1 15:51 open as S, the D1-based ATM, the same contract as the
model), for each strike, on the days with a 15:51 quote for that contract and an official close:
- model price (variant (a): f_o × Bachelier(S, K, k_D1 × RV × 3 × S)) against the real mid and ask: the means
  and the medians of mid/model and ask/model;
- model P&L (settled on the D1 15:59 close, $0.10 half-spread, $0.09 fee) against the real P&L (the ask, the
  official close, $0.09): the mean difference with Newey-West t;
- the gap between the official close and the D1 15:59 close the model settled on (mean and 95th percentile).

## Part 4: fill check (descriptive, no criterion)

The ask in the quote file is only a price that was offered; Part 4 asks whether trading actually happened near
it. Trade bars come from Databento OPRA `ohlcv-1m`: the same 50 symbols and the same 15:00-16:01 ET window, in
`data/spx_1549/databento/ohlcv-1m_1500-1601_k60/`. A bar stamped HH:MM covers the trades in that minute.

For every priced entry of the chosen configuration and of the current rule, in each period, report:
- the share of entries where the contract traded in the entry minute (a bar with volume > 0);
- among those entries, the share where the minute's lowest trade was at or below the ask;
- among those entries, the mean and median of (the minute's last trade − the mid).

This part uses the trade-bar files that exist when the run starts and reports how many days had them. If none
exist, it says so. It never stops the run and changes no decision.

## What is reported

- **Discovery:**
  - the 15 best eligible cells (score, mean per day, trades, both halves);
  - the best cell for each candle minute;
  - the current rule's discovery numbers;
  - the null's median and 95th percentile, p, the luck-adjusted score (best minus null median), the pick
    minus current, and the decision.
- **Confirmation:**
  - for the chosen configuration and the current rule: mean per day and t, trades, mean per trade, share of
    trades that made money, median and worst trade;
  - the same for 2021-2022 and 2023-2026.
- **The current rule at all 9 strikes on 2021-2026 at real prices.** This is descriptive, not a second test.
  Choosing a strike from it would be choosing on the confirmation period.
- **The model-check table.**
- **Counts:** priced days, no-expiry days, and unpriced entries by reason.

## Text rules

- Say plainly that the 2021-2026 index outcomes were already used to test the current rule.
- Say that signals come from D1, a CFD, and that a fill at the quoted ask ignores size and fast minutes.
- Say that discovery has few days before 2016 and they fall on different weekdays than 2022-2026.
- If the current rule is what gets confirmed, say it confirms the current rule at real prices, not that it is
  the best setting.
- No trading recommendation.

## Outputs

`backtests/spx_candle_realprice/results.json`, `backtests/spx_candle_realprice/RESULTS.md` and
`data/spx_1549/databento/realprice_trades.csv` (every trade of the chosen and the current configuration). They
are rebuilt on each run by `backtests/spx_candle_realprice/realprice.py`, which reuses `scan.py`'s panel and
`strikes.py`'s pricing helpers. It refuses to run unless the locked file is in `preregistration/` and its
SHA-256 is in `preregistration/LEDGER.md`.

## Decisions made at locking

1. **Candle range:** 15:40-15:50, as above. Earlier candles are not tried, which keeps the number of tries the
   luck check has to pay for at 2,178.
2. **Fee:** $0.09 for every decision and the criterion; the $0.74 fee is reported descriptively.
3. **Bars:** t ≥ 2.0 for the switch and for the confirmation. There is one confirmation test here, and the
   grid search is paid for by the luck check.
4. **Price:** buy at the ask for every decision and the criterion; buying at the mid is reported
   descriptively.
5. **Minimum trades:** 150 overall and 50 in each half, as above, even though this may rule out the highest
   thresholds.
6. **Added at locking:** Part 4, the descriptive fill check on trade bars.
