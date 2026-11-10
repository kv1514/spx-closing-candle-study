# Pre-registration addendum: does an early exit beat holding to the close?

**Status: locked 2026-11-08.** Locked by Claude at the user's explicit instruction ("Lock it, build it"). It was
locked before `exits.py` existed and before any exit-rule result was computed.

Addendum to `spx_close_candle_scan.md`, `spx_candle_forward_options.md` and `spx_candle_strike_ladder.md`.
Drafted 2026-11-08. Descriptive with one stated criterion; nothing here is a trading recommendation.

## The question

The strike-ladder study held every trade from the 15:51 entry to the 16:00 settlement, or sold at 15:59.
It never tried getting out early. This study asks whether a simple rule that exits early beats holding to
the close. The rules are: a stop when SPX moves against the trade, a take-profit when it moves in favour, or
both. It also asks what each rule does to the bad days: the worst trades, the 5th percentile and the share of
losing trades.

## What was known when this was drafted (disclosed so the rules can be judged)

- Everything in `backtests/spx_candle_strikes/RESULTS.md` (run 2026-11-08), including its headline that 10-20
  points in the money held up best, and the per-day forward P&L at 15:59 (exit B) and at settlement (exit A).
  The choice of ITM10 as the headline strike below was made after seeing those results.
- The calibration constants that run produced, reused here unchanged: k_D1 = 1.065101699231275 and the skew
  factors f_o in `backtests/spx_candle_strikes/results.json`.
- The backtest's mean |move| from 15:51 to 15:59 is 8.60 points at level 7709.58, and the signal is right
  57.45% of the time (`holdout.json`).
- No statistic of the 15:51-15:59 path between the entry and the 15:59 close has been computed for this study:
  no maximum adverse or favourable excursion, no minute-by-minute option price and no stop or target hit rate.

## Signal, entry and strikes (unchanged from the strike ladder)

- Signal `F2_1m_1550_strong_body`. Entry at the 15:51 one-minute bar open S, K_atm = floor(S / 5 + 0.5) x 5.
- Strikes: **ITM10 is the headline**, and ITM20 and ATM are also reported. Out-of-the-money strikes are left
  out because the strike ladder's skew factors for them are unreliable.
- Costs: $0.10 half-spread on every entry and every early exit. The fee is $0.09 per contract per side
  (primary) or $0.74; there is no fee at expiry. Multiplier 100.

## Exit rules (fixed in advance)

Every rule watches the SPX one-minute **closes** from 15:51 through 15:58. The move in points at level
L = 7709.58 is m(t) = direction x (close(t) - S) x L / S, in both parts. A minute with no real index bar is
not checked. When a rule fires on the close of minute t, the option is sold at the **open of minute t+1**,
which leaves a minute to act. The sale proceeds are max(price - half-spread, 0) per unit, and the exit fee is
charged. A rule that never fires holds to settlement.

| Rule | Exits when |
|---|---|
| H (baseline) | never: hold to the 16:00 settlement |
| S3 | m(t) <= -3 |
| S5 | m(t) <= -5 |
| S8 | m(t) <= -8 |
| T5 | m(t) >= +5 |
| T10 | m(t) >= +10 |
| B5_10 | m(t) <= -5 or m(t) >= +10, whichever comes first |

## Part 1: real prices on forward days (descriptive)

- The forward signal days with minute option bars, as in the strike ladder's Part 1. The index path comes from
  that day's Robinhood SPX one-minute bars (`live_*/spx_1m.json`).
- The early-exit price is the contract's one-minute bar `open_price` at minute t+1 (not gap-fill), minus $0.10,
  floored at 0. If that bar is missing, the status is `exit_bar_missing` and the trade gets no P&L. The hold
  baseline is exit A from the strike ladder.
- Report per day, rule and strike: whether and when the rule fired, the exit price and the P&L. There are only
  a handful of days, so this supports no conclusion.

## Part 2: modelled 2021-2026 (the 644 strong-body days)

- The index path is the D1 one-minute bars 15:51-15:59, rescaled to L as in the strike ladder. Settlement is
  the D1 15:59 close, as before.
- The early-exit option price at the open of minute u = t+1 is f_o x Bachelier(P'_open(u), K', sigma'_u),
  where P'_open(u) is the index open rescaled to L. Here sigma'_u = sigma'_9 x sqrt(n_u / 9), where sigma'_9
  is the variant's 9-minute sigma from the strike ladder and n_u is the number of one-minute bars from u
  through 15:59 inclusive (8 at 15:52, down to 1 at 15:59). For (a) this is k_D1 x RV_D1 x sqrt(n_u) x L.
  f_o stays at the strike's entry offset; this is a simplification and is said so. Entry prices are the
  strike ladder's.
- Variants:
  - (a) calibrated, the headline.
  - (b) constant volatility (the strike ladder's sigma_bps_median_c1 x L for 9 minutes).
  - (c) realized-move-fair (sigma'_9 = 8.599455 / (2 n(0)), f_o = 1).
  - Half-spread $0.05 and $0.20 on (a), charged on entry and on an early exit.
  - f_o = 1 on (a).

## What is reported

For each variant, strike and rule:
- the share of trades where the rule fired;
- mean P&L per contract with its Newey-West (lag 5) t;
- the share profitable;
- the median, 5th percentile and worst trade;
- the mean return on premium;
- the paired difference from H, d_r = P&L(rule) - P&L(H) trade by trade, with its mean and Newey-West t.

For variant (a) the 2021-2022 and 2023-2026 results are also reported separately.

## The one criterion

A rule is called **better than holding** only if all of these hold:
- at ITM10, variant (a), $0.09 fee, its mean d_r > 0 with t > 2.64 (two-sided 0.05, Bonferroni over the six
  rules);
- its mean d_r is also > 0 in variants (b) and (c).

Otherwise the result is "no evidence that it beats holding". A rule that lowers the mean but shrinks the bad
days is reported as that trade-off and is not judged.

## Text rules

- Say plainly that Part 1 has only a handful of days and Part 2 is a model.
- Say that the model prices early exits with the entry's volatility and skew, a $0.10 half-spread and a
  one-minute delay. Real exits in a fast move can be worse.
- No trading recommendation.

## Outputs

`data/spx_1549/forward/exits_forward_log.csv`, `backtests/spx_candle_exits/results.json` and
`backtests/spx_candle_exits/RESULTS.md`. They are rebuilt on each run by `backtests/spx_candle_exits/exits.py`
(not yet written). It reuses `strikes.py`'s loaders and pricing, and refuses to run on real data unless the
locked file is in `preregistration/` and its SHA-256 is in `preregistration/LEDGER.md`.
