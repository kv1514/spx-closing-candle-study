# The 15:50 candle on cheaper contracts (XSP, SPY): plain-English summary

Hand-written on 2026-11-09 from the single run of `mini.py` (plan: `preregistration/spx_candle_mini.md`, ledger
2026-11-09T22:53:16Z; run log in [run_log.txt](run_log.txt); full tables in [RESULTS.md](RESULTS.md)). Real
Databento quotes, 2021-01-01 to 2026-10-20, one contract at a time. Research only, not trading advice.

## The question

The SPX rule costs about $1,100 a contract. XSP (mini-SPX, one tenth the size, cash-settled to SPX / 10) and SPY
(the ETF, about one tenth of SPX) have 0DTE options that cost about a tenth as much. Does the same signal, traded
the same way on those, still make money at the prices actually quoted?

## The answer: no, on both

| | SPX, 10 in the money (the rule) | XSP, 1 in the money | SPY, 1 in the money |
|---|---|---|---|
| How it was traded | buy at the 15:51 ask, hold to the close | buy at the 15:51 ask, hold to the close | buy at the 15:51 ask, **sell at the 15:59 bid** |
| Average cost | $1,100 | $174 | $118 |
| Average per trade | **+$67** | **-$50** | **+$0.51** |
| Return per $1 of premium | **+6.1 cents** | **-28.5 cents** | **+0.4 cents** |
| Trades that made money | 54% | 35% | 45% |
| Worst trade | -$2,210 | -$818 | -$176 |
| Pre-registered test (t ≥ 2.0) | passed, t 2.40 | **failed, t -5.48** | **failed, t +0.23** |

- **XSP lost money, and clearly.** The t of -5.48 is not "no edge": it is a reliable loss.
- **SPY broke even.** Zero, within noise, in every year.
- SPY has to be sold at 15:59 because it settles into shares, not cash. Holding SPY to its close instead
  (descriptive only) lost $2.23 a trade.

## Why: the edge is about 6% of the premium, and the cheaper contracts cost more than that to trade

**The signal's edge is small relative to what you pay.** On SPX it is about 6 cents per dollar of premium. That
survives on SPX because the bid-ask spread is about 5% of the price and the cash settlement is free.

- **XSP's spread is huge for its price.** The median gap between bid and ask was 31% of the option's price, against
  5% for SPX on the same days.
  - It was worse early: about 190% of the price in 2021 and 150% in 2022. It has narrowed to about 24% in 2026.
  - Paying the ask on XSP gives away several times the edge before the trade starts.
- **XSP is also thin.** On 45% of signal days there weren't enough live quotes to price the trade at all (the
  plan required that). Those excluded days were worse still: -$100 a trade.
- **SPY's spread is fine, but you pay it twice.** SPY's spread is about 4% to get in and 6% to get out, and selling
  at 15:59 gives up the last minute.
  - That round trip costs about as much as the edge. At the mid price on both sides (which you usually can't get)
    SPY would have made +$6.95 a trade; at the real ask and bid, +$0.51.

## Does it get better recently?

XSP is improving as its spreads tighten, but it still trails a tenth of SPX:

| Year | XSP per trade | XSP trades | SPX per trade ÷ 10 (same idea, scaled) |
|---|---|---|---|
| 2021 | -$360 | 9 | +$17 |
| 2022 | -$126 | 50 | +$7 |
| 2023 | -$89 | 37 | +$0.39 |
| 2024 | -$48 | 58 | +$2 |
| 2025 | -$2.63 | 94 | +$6 |
| 2026 | +$4.47 | 65 | +$12 |

SPY was flat in both 2021-2022 and 2023-2026.

## Things that might have rescued it, and didn't

- **Buying XSP at the mid:** +$0.17 a trade, still zero. XSP's mid was usually above SPX's ask divided by 10, so
  even the mid was a worse price than the big contract's ask.
- **Only trades under $500:** XSP -$34 a trade (96% of trades qualified).
- **Other strikes:** XSP at the money -$12 a trade, 2 in the money -$75. SPY at the money +$0.64, 2 in -$3.05.
- **Fills:** XSP's real trades in the 15:51 minute printed near the mid, not the ask. Only 27% of signal days had
  any trade in that minute in 2021-2022 (85% since 2023), against 100% for SPX.

## Checks that passed

- The signal matches the SPX study on every day.
- The SPX result was rebuilt exactly: +$29.87 a day, t 2.40, 585 trades.
- The official closes match to the cent.

## What this does and doesn't say

- **The signal still works on SPX.** This test is about the cost of trading it on smaller contracts, and that cost
  ate the whole edge.
- It is one contract at fixed quoted prices. It does not simulate a small account or a broker closing an expiring
  SPY position early.
- XSP spreads are still narrowing. A future re-test on XSP after 2026 is possible, but it would be new data and a
  new plan, not this one.
