# Forward log: real 0DTE option outcomes of the 15:50 candle signals (descriptive only)

Rebuilt by `analysis/candle_1550_options_forward.py`; do not edit by hand. Rules: `preregistration/spx_candle_forward_options.md` (hashed in `LEDGER.md` before any option P&L was computed; the index results of the first four strong-body days were already known then, so this is a descriptive record, not an untouched test). It shows what real Robinhood SPXW 0DTE option bars would have given with the backtest's cost assumptions. It is not a recommendation.

## The trade being logged

When a signal fires, buy one 0DTE SPXW call (signal up) or put (signal down) at the strike nearest the SPX 15:51 open, paying that contract's 15:51 one-minute bar open plus $0.10. **Exit A**: hold to expiry; the option settles at its intrinsic value on the official SPX close. (The backtest's model instead scored |move| to the 15:59 index close with an idealised strike equal to the entry price.) **Exit B**: sell at the 15:59 bar close minus $0.10. P&L is per contract (x100), for a $0.09 and a $0.74 fee per side (no fee at expiry).

## Totals so far

| Signal | Exit | Trades | Wins ($0.09 / $0.74) | Win share, $0.09 (95% CI) | Total, $0.09 | Mean, $0.09 | Total, $0.74 | Mean, $0.74 | Backtest model on the same days, mean ($0.09) |
|---|---|---|---|---|---|---|---|---|---|
| 15:50 candle, strong body (headline) | A: hold to expiry (finalized) | 4 | 2 / 2 | 50% (15%-85%) | -69.36 | -17.34 | -71.96 | -17.99 | +63.87 |
| 15:50 candle, strong body (headline) | B: sell 15:59 | 5 | 3 / 3 | 60% (23%-88%) | +556.10 | +111.22 | +549.60 | +109.92 | +233.52 |
| 15:50 candle direction, any body | A: hold to expiry (finalized) | 6 | 3 / 3 | 50% (19%-81%) | -454.54 | -75.76 | -458.44 | -76.41 | -69.80 |
| 15:50 candle direction, any body | B: sell 15:59 | 7 | 4 / 4 | 57% (25%-84%) | +166.74 | +23.82 | +157.64 | +22.52 | +72.68 |
| P3 reference (15:50 open -> 15:51 open direction) | A: hold to expiry (finalized) | 6 | 3 / 3 | 50% (19%-81%) | -454.54 | -75.76 | -458.44 | -76.41 | - |
| P3 reference (15:50 open -> 15:51 open direction) | B: sell 15:59 | 7 | 4 / 4 | 57% (25%-84%) | +166.74 | +23.82 | +157.64 | +22.52 | - |

The headline signal has **5 trade(s) with a real entry price, 4 of them finalized** (official close known). That is far too few to say anything about whether it makes money; one big day dominates a total this small. The model column is scan.py's cost model on exactly the same days (its idealised option, its cost). Only days with saved one-minute option bars can be priced, so the sample also depends on which days were collected in time.

Provisional (official close not saved yet, valued at the 15:59 bar close and left out of the exit-A totals): 2026-11-09.

## Every forward day

| Date | Signal | Status | Option | Paid (incl. $0.10) | Exit A value | P&L A ($0.09) | Exit B 15:59 | P&L B ($0.09) | Model P&L ($0.09) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-21 | strong body | no_signal | - | - | - | - | - | - | - |
| 2026-10-21 | direction | traded | call 7760 | 4.25 | 0.00 | -425.09 | 0.01 | -434.18 | -427.17 |
| 2026-10-21 | P3 | traded | call 7760 | 4.25 | 0.00 | -425.09 | 0.01 | -434.18 | - |
| 2026-10-22 | strong body | traded | call 7660 | 3.60 | 3.43 | -17.09 | 2.80 | -90.18 | +112.83 |
| 2026-10-22 | direction | traded | call 7660 | 3.60 | 3.43 | -17.09 | 2.80 | -90.18 | +128.43 |
| 2026-10-22 | P3 | traded | call 7660 | 3.60 | 3.43 | -17.09 | 2.80 | -90.18 | - |
| 2026-10-23 | strong body | no_signal | - | - | - | - | - | - | - |
| 2026-10-23 | direction | no_minute_option_bars | put 7625 | - | - | - | - | - | +3.09 |
| 2026-10-23 | P3 | no_minute_option_bars | put 7625 | - | - | - | - | - | - |
| 2026-10-26 | strong body | no_signal | - | - | - | - | - | - | - |
| 2026-10-26 | direction | traded | put 7680 | 2.83 | 3.23 | +39.91 | 3.38 | +44.82 | -309.63 |
| 2026-10-26 | P3 | traded | put 7680 | 2.83 | 3.23 | +39.91 | 3.38 | +44.82 | - |
| 2026-10-27 | strong body | traded | put 7730 | 1.98 | 7.40 | +541.91 | 7.15 | +506.82 | +275.80 |
| 2026-10-27 | direction | traded | put 7730 | 1.98 | 7.40 | +541.91 | 7.15 | +506.82 | +291.55 |
| 2026-10-27 | P3 | traded | put 7730 | 1.98 | 7.40 | +541.91 | 7.15 | +506.82 | - |
| 2026-10-28 | strong body | no_signal | - | - | - | - | - | - | - |
| 2026-10-28 | direction | no_minute_option_bars | call 7745 | - | - | - | - | - | -207.29 |
| 2026-10-28 | P3 | no_minute_option_bars | call 7745 | - | - | - | - | - | - |
| 2026-10-29 | strong body | traded | call 7715 | 3.60 | 5.39 | +178.91 | 4.60 | +89.82 | +241.69 |
| 2026-10-29 | direction | traded | call 7715 | 3.60 | 5.39 | +178.91 | 4.60 | +89.82 | +257.41 |
| 2026-10-29 | P3 | traded | call 7715 | 3.60 | 5.39 | +178.91 | 4.60 | +89.82 | - |
| 2026-10-30 | strong body | traded | call 7580 | 7.80 | 0.07 | -773.09 | 1.10 | -680.18 | -374.85 |
| 2026-10-30 | direction | traded | call 7580 | 7.80 | 0.07 | -773.09 | 1.10 | -680.18 | -359.40 |
| 2026-10-30 | P3 | traded | call 7580 | 7.80 | 0.07 | -773.09 | 1.10 | -680.18 | - |
| 2026-11-02 | strong body | no_minute_option_bars | put 7545 | - | - | - | - | - | +23.02 |
| 2026-11-02 | direction | no_minute_option_bars | put 7545 | - | - | - | - | - | +38.40 |
| 2026-11-02 | P3 | no_minute_option_bars | put 7545 | - | - | - | - | - | - |
| 2026-11-03 | strong body | no_minute_option_bars | put 7560 | - | - | - | - | - | -431.83 |
| 2026-11-03 | direction | no_minute_option_bars | put 7560 | - | - | - | - | - | -416.42 |
| 2026-11-03 | P3 | no_minute_option_bars | put 7560 | - | - | - | - | - | - |
| 2026-11-04 | strong body | no_signal | - | - | - | - | - | - | - |
| 2026-11-04 | direction | no_minute_option_bars | put 7695 | - | - | - | - | - | +91.50 |
| 2026-11-04 | P3 | no_minute_option_bars | put 7695 | - | - | - | - | - | - |
| 2026-11-05 | strong body | no_signal | - | - | - | - | - | - | - |
| 2026-11-05 | direction | no_minute_option_bars | put 7370 | - | - | - | - | - | +849.94 |
| 2026-11-05 | P3 | no_minute_option_bars | put 7370 | - | - | - | - | - | - |
| 2026-11-06 | strong body | no_minute_option_bars | put 7385 | - | - | - | - | - | +618.03 |
| 2026-11-06 | direction | no_minute_option_bars | put 7385 | - | - | - | - | - | +633.09 |
| 2026-11-06 | P3 | no_minute_option_bars | put 7385 | - | - | - | - | - | - |
| 2026-11-09 | strong body | traded | put 7560 | 2.25 | 10.99 (prov.) | +873.91 | 9.65 | +729.82 | +912.15 |
| 2026-11-09 | direction | traded | put 7560 | 2.25 | 10.99 (prov.) | +873.91 | 9.65 | +729.82 | +927.57 |
| 2026-11-09 | P3 | traded | put 7560 | 2.25 | 10.99 (prov.) | +873.91 | 9.65 | +729.82 | - |

## Is the backtest's option price realistic? (every day with minute option bars)

The backtest assumed an at-the-money option costs half the realized-move-fair straddle: 11.154 bps of SPX for the full straddle with the strong-body value and 10.746 bps with the any-body value (2021-2026). Real call + put at the strike nearest the 15:51 open, from their 15:51 bar opens:

| Date | SPX 15:51 | Strike | Call | Put | Straddle (pts) | Straddle (bps) | Market / model, strong body | Market / model, any body |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 | 7762.17 | 7760 | 4.15 | 1.18 | 5.33 | 6.87 | 0.62x | 0.64x |
| 2026-10-22 | 7657.95 | 7660 | 3.50 | 3.65 | 7.15 | 9.34 | 0.84x | 0.87x |
| 2026-10-23 | 7627.22 | 7625 | - | - | - | - | only 10-minute (or other non-minute) option bars saved | - |
| 2026-10-26 | 7677.74 | 7680 | 1.38 | 2.73 | 4.11 | 5.35 | 0.48x | 0.50x |
| 2026-10-27 | 7730.15 | 7730 | 1.85 | 1.88 | 3.73 | 4.83 | 0.43x | 0.45x |
| 2026-10-28 | 7745.84 | 7745 | - | - | - | - | only 10-minute (or other non-minute) option bars saved | - |
| 2026-10-29 | 7714.20 | 7715 | 3.50 | 3.15 | 6.65 | 8.62 | 0.77x | 0.80x |
| 2026-10-30 | 7580.37 | 7580 | 7.70 | 5.40 | 13.10 | 17.28 | 1.55x | 1.61x |
| 2026-11-02 | 7546.87 | 7545 | - | - | - | - | only 10-minute (or other non-minute) option bars saved | - |
| 2026-11-03 | 7562.11 | 7560 | - | - | - | - | only 10-minute (or other non-minute) option bars saved | - |
| 2026-11-04 | 7693.88 | 7695 | - | - | - | - | only 10-minute (or other non-minute) option bars saved | - |
| 2026-11-05 | 7369.29 | 7370 | - | - | - | - | only 10-minute (or other non-minute) option bars saved | - |
| 2026-11-06 | 7385.25 | 7385 | - | - | - | - | only 10-minute (or other non-minute) option bars saved | - |
| 2026-11-09 | 7562.45 | 7560 | 4.55 | 2.15 | 6.70 | 8.86 | 0.79x | 0.82x |

Over 7 day(s) the market straddle averaged 8.73 bps, 0.78x the strong-body model price (0.81x the any-body one). This compares the call + put pair with twice the model option; on a given day the call or the put alone can be cheaper or dearer than the model. A pair above 1x means options cost more than the backtest assumed that day.

## Caveats

- Robinhood's option bars carry no bid/ask and it does not say whether they are trades or marks. The $0.10 half-spread is the backtest's assumption, not an observed spread; a real fill can be worse.
- The strike is chosen from the index's 15:51 bar open and paid at the option's 15:51 bar open; one-minute bars cannot show that both were available at the same instant. A person reacting to the 15:50 candle would trade a few seconds later.
- Robinhood keeps one-minute option bars for about a day; days collected later have only 10-minute bars and cannot be priced at 15:51. They are listed with their status.
- This page reports what happened. It does not recommend any trade.
