# Pre-registration: the "12:49" SPX close move (Tiger's doc)

Fixed 2026-10-21 before any historical result for this window was computed. Source of the idea: Tiger's
Google Doc "SPX" (27 one-minute SPX screenshots, grouped by weekday, dotted line at 12:49). Candle count
from the line to the closing-bell shading is about 11 bars, so 12:49 is Pacific time = **15:49 ET**, one
minute before NYSE/Nasdaq publish the first closing-auction (MOC/LOC) imbalance at 15:50 ET.

Claim to test: "around 12:49 PT SPX makes a sharp move one way, which makes 0DTE options skyrocket."

## Definitions (all times America/New_York)

- t0 = open of the 1-minute bar that begins 15:49:00. Window end = close of the bar that begins 15:59:00
  (D1) or the SPX official close (D2, from daily bars). r_close = ln(P_end / P_t0).
- Full regular sessions only; half-days (13:00 close) and days with any missing bar 15:19-15:59 are dropped
  and counted.
- Comparison windows: every 11-minute window starting on the minute grid 10:00..15:38 on the same day.

## Data

- D1: Dukascopy USA500.IDX/USD 1-minute BID candles (a CFD that tracks S&P 500 futures), earliest available
  date through 2026-10-20. Converted from UTC with DST handled by zoneinfo. Accepted for use only if, on
  overlap days, corr(r_close D1, r_close SPY 1-min from data/bars_1m) >= 0.90 and the same for Robinhood SPX
  minute bars; otherwise D1 is used only where it agrees and that is reported.
- D2: Robinhood (read-only historicals) SPX 1-minute bars and SPXW 0DTE option 1-minute bars (marks, no
  volume, interpolated bars discarded) for every session with real minute data (about 2026-09-02 onward),
  strikes from ATM-30 to ATM+30 in 5-point steps, calls and puts.

## Hypotheses and tests

H1 size (descriptive anchor, expected true, not tradable by itself): mean |r_close| exceeds (a) the mean |r|
of the 15:38-15:49 window and (b) the same-day median |r| of all comparison windows. Day-level paired test
on ln(|r_close| + eps) - ln(baseline + eps), eps = 1e-5, two-sided t, plus a day-block bootstrap CI.

H2 direction, D1, target r(15:51 -> end) for P3 and r_close for the others. Predictors known at entry:
- P1 sign of r(09:30 open -> 15:49 open)   (intraday momentum)
- P2 sign of r(15:19 open -> 15:49 open)   (last-30-minute momentum)
- P3 sign of r(15:50 open -> 15:51 open)   (chase the first reaction to the 15:50 imbalance release)
- P4 sign of r(09:30 open -> 10:00 open)   (Gao-Han-Li-Zhou first half-hour)
Statistic: mean of sign(P) x r_target in bps, Newey-West t (lag 5), Holm over P1-P4 at 5%. Also hit rate.
Subperiods (descriptive): start-2019, 2020-2022, 2023-2026 (daily 0DTE era), and by weekday.

H3 options, D2 (low power, descriptive with CIs):
- S1 long ATM straddle at t0 (strike nearest SPX at t0), entry = 15:49 bar open mark + half-spread,
  hold to settlement value (intrinsic at the SPX official close).
- S2 long ATM call if the H2 predictor with the best full-sample D1 t-stat is positive, else ATM put; same
  entry/exit. (Predictor chosen on D1 only, never on D2.)
- S3 "sell the spike": long the 5-point OTM call and 5-point OTM put at t0; each leg is sold at 2x entry mark
  (minus half-spread) if any later bar's close reaches it before 15:59, else held to settlement.
- Implied vs realized: implied move at t0 = straddle mark; compare with D1's 2023-2026 mean |P_end - P_t0|
  scaled to the day's SPX level, conditioned on the day's realized vol up to 15:49 (ratio and regression).
Costs: half-spread $0.10 per leg base case; sensitivity $0.05 and $0.25; Robinhood fee $0.09/contract per
side (index options: add the $0.65-ish exchange fee estimate as a second sensitivity).

## Pass rule (decided now)

A strategy is a candidate for paper trading only if BOTH:
1. its direction or size premise passes in D1 (H2 predictor Holm-adjusted p < 0.05 with the same sign in
   2023-2026; or, for S1/S3, the D1 realized-move distribution exceeds the D2 implied move with a day-block
   bootstrap 95% CI excluding zero), and
2. its D2 option P&L after base costs has a positive mean (CIs reported; with ~35 days this is weak
   evidence, so a pass here only promotes the idea to forward paper logging, never to live money).
Anything else is FAIL. No parameter (time, strike offset, target multiple) is tuned after seeing results;
any extra variant is labelled exploratory and counted.
