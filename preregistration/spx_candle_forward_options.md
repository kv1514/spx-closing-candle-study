# Pre-registration addendum: real 0DTE option outcomes of the 15:50 candle signals (forward, descriptive)

Addendum to `spx_close_candle_scan.md`. Fixed 2026-10-30 before any option profit or loss in it was
computed. Descriptive only: no test, no pass/fail rule, and nothing here is a trading recommendation.

## What was known when this was written (disclosed so the rules can be judged)

- The SPX-index forward log (`backtests/spx_candle_scan/FORWARD.md`) for 2026-10-21 .. 2026-10-30: 8 full
  sessions; the frozen strong-body signal fired on 4 (10-22 up, 10-27 down, 10-29 up, 10-30 up) and the
  15:51-to-15:59 index move went its way on all 4 (+7.18, +9.28, +8.84, +0.77 bps in the signal's direction).
- While checking the saved files I saw a few option bar values: the 15:49 bars of all 26 contracts on
  2026-10-30, and the 15:45-15:59 minute bars of the 2026-10-29 7705 call. No option P&L, no straddle price
  and no comparison with the model was computed before this file was hashed.
- The backtest's option-cost model (scan.py `economics`): idealised ATM option bought at entry, cost = half
  the realized-move-fair straddle (strong body: 0.5 x 8.599 points at the 7709.58 level, i.e. 0.5 x 11.154
  bps of the entry price), + $0.10 half-spread + a $0.09 or $0.74 fee; payoff = |move| to the 15:59 close.

## Days

Every FORWARD date (>= 2026-10-21) with a `SPX_robinhood` row of status `ok` in
`data/spx_1549/forward/candle_1550_log.csv` (that log's signals, entry and exit prices are used as is).
Every such day gets one row per signal. A day without real one-minute option bars for the needed contract
gets a status instead of a P&L: `no_minute_option_bars` (only 10-minute bars saved, e.g. 2026-10-23 and
2026-10-28), `strike_not_collected` (the strike is outside the 13 saved), `entry_bar_missing` (no real,
non-gap-fill 15:51 bar with a price above 0) or `exit_bar_missing` (for exit B only).

## Signals

- Headline: `F2_1m_1550_strong_body` (frozen direction +1, so the trade is in the candle's direction).
- Also logged, never the headline: `F1_1m_15:50` (direction of any 15:50 candle) and `P3_reference`.
- A day with signal 0 has no trade for that signal.

## Trade rule

1. S = the SPX 15:51 bar open (`entry_1551_open`). Strike K = floor(S / 5 + 0.5) x 5 (scan.py's rounding).
2. Signal +1: buy the 0DTE SPXW call at K; signal -1: buy the put at K. Contract ids come from that day's
   `ids.json`; each contract's OCC symbol in the bar file must match its date, type and strike.
3. Entry price E = the contract's 15:51 one-minute bar `open_price`, plus the $0.10 half-spread.
4. Exit A (primary, as the backtest: hold to expiry): value = intrinsic value at the official SPX close,
   taken from the newest `data/spx_1549/live_*/spx_daily.json` that has a non-gap-fill daily bar for that
   date. If no file has it yet, the 15:59 bar close is used and the row is marked `provisional`; provisional
   rows are shown but left out of the exit-A totals. No fee at expiry.
5. Exit B (sensitivity: sell before the close): the contract's 15:59 one-minute bar `close_price`, minus the
   $0.10 half-spread; a fee on both sides.
6. P&L per contract in USD = 100 x (exit value - entry price) - fees, for the $0.09 and the $0.74 fee cases.

## Model check (every day with minute option bars, signal or not)

- Market ATM straddle = call + put 15:51-bar opens at K, in points and in bps of S.
- Model ATM option price = 0.5 x 11.154 bps x S (the strong-body realized-move-fair half straddle) and the
  same with the F1 value (0.5 x 8.285 / 7709.58 x 1e4 bps); report the ratio market straddle / (2 x model
  option) per day and its mean. The bars may be marks or trades (Robinhood does not say); this is noted.

## Reporting

Per-day table; per signal and exit: number of trades, wins (P&L > 0), total and mean P&L per contract for
both fee cases, with a Wilson 95% interval on the win share. The backtest-model P&L for the same days
(100 x (|move| if right else 0, minus model option price, half-spread and fee)) is shown next to the real
one. Text must say the sample is far too small to support any conclusion. Outputs:
`data/spx_1549/forward/options_log.csv`, `data/spx_1549/forward/options_summary.json` and
`backtests/spx_candle_scan/FORWARD_OPTIONS.md`, all rebuilt from scratch on each run.
