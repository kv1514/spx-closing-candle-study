# Real option prices, 2013-2026: plain-English summary

Hand-written on 2026-11-09 from `realprice.py run`. Plan: `preregistration/spx_candle_realprice.md` (ledger
2026-11-09T08:22:44Z). Full tables: [RESULTS.md](RESULTS.md). Trade-by-trade:
`data/spx_1549/databento/realprice_trades.csv`. Research only, not trading advice.

## What was tested

Every earlier result priced the option with a model. This study uses **real SPXW quotes** from Databento (OPRA):
- **Entry:** buy at the real ask at the entry minute.
- **Exit:** settle at Cboe's official close.
- **Fee:** $0.09.

In 2013-2020 it searched **2,178 versions** of the rule, combining:
- which candle (15:40 to 15:50);
- how strong a body (40% to 90% of the range);
- trade with the candle or against it;
- which strike (20 in the money to 20 out of the money).

A new version could replace the current rule only if three things held:
- it beat a luck test (p ≤ 0.05);
- it beat the current rule by a clear margin (t ≥ 2);
- it was positive in both halves of 2013-2020.

Whatever survived then got **one** test on 2021-2026. The rules were locked before any price was looked at.

## The answer: the current rule stands, and it is confirmed at real prices

**Nothing beat the current rule clearly in 2013-2020**, so the current rule was the one tested on 2021-2026: the
15:50 candle, body at least 60%, trade with it, 10 points in the money. **It passed.**

| 2021-2026, real asks | Result |
|---|---|
| Trades | 585 (1 more signal day had no usable quote) |
| Average per trade | **+$67** per contract |
| Trades that made money | 54% |
| Median trade | +$45 |
| Worst trade | -$2,210 |
| Per-day t-statistic | **2.40** (the bar was 2.0), so **CONFIRMED** |

By year, average per trade at the ask:

| 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| +$175 (67 trades) | +$71 (90) | +$4 (113) | +$20 (106) | +$65 (117) | +$121 (92) |

- **The edge is smaller than the model said.** The model's +$166 a trade was in today's dollars (SPX at 7,710).
  At the real prices and index levels of the time, the same trades made +$67.
- **It is weaker since 2023:** +$50 a trade, t 1.56. That is not significant on its own; 2021-2022 carries
  much of the result.
- **The worst day lost $2,210 on one contract.**

## The biggest lesson: the bid-ask spread decides whether it pays

| | Bought at the ask | Bought at the mid | Typical full spread (per share) |
|---|---|---|---|
| 2013-2020 (216 trades) | **-$23** a trade | +$145 a trade | $2.90 |
| 2021-2026 (585 trades) | **+$67** a trade | +$106 a trade | $0.60 (2026: $0.40) |

- **The signal itself worked in both periods.** At the mid, it made money both before and after 2021.
- **Before 2021 the spread ate all of it.** Spreads on these options were about five times wider than now.
- **Since 2021 the spread still costs about $39 a trade** at 10 in the money, a third of the edge at the mid.
- **How you fill matters.** A limit order between the mid and the ask keeps more of the edge than paying the
  ask. Whether it would fill is the open question (see the fill check below).

## Other candles, thresholds and strikes

- **The best 2013-2020 alternative** was the 15:42 candle, body at least 60%, at the money.
  - It beat the luck test (p 0.034).
  - It did not beat the current rule by a clear margin (t 1.56).
  - So under the rules it was not adopted.
- **Few versions qualified at all.** Only 2 of 2,178 were positive in both halves of 2013-2020 with enough
  trades, mostly because of the wide spreads then. **The 15:50 candle is still the one to watch.**
- **All strikes at real prices, 2021-2026** (a description, not a second test; choosing a strike from this
  would be choosing on the test period):

| Strike | $/trade | Won | Worst | t | Ask (≈ cost) |
|---|---|---|---|---|---|
| 20 in the money | +$77 | 54% | -$2,670 | 2.61 | ~$2,060 |
| 15 in the money | +$71 | 55% | -$2,330 | 2.43 | ~$1,570 |
| **10 in the money** | **+$67** | **54%** | **-$2,210** | **2.40** | **~$1,090** |
| 5 in the money | +$54 | 50% | -$1,900 | 2.07 | ~$650 |
| at the money | +$40 | 39% | -$1,640 | 1.87 | ~$320 |
| 5 out of the money | +$12 | 19% | -$1,390 | 0.78 | ~$140 |
| 10-20 out of the money | about $0 or losing | 3-11% | | | |

  - **In the money is more consistent; out of the money does not work.** The real prices give the same ranking
    as the model.
  - **10, 15 and 20 in the money are about equally good.** 10 in the money needs about half the cash of 20.

## How good was the model?

| | 10 in the money | At the money | Far out of the money |
|---|---|---|---|
| Real ask vs model price | about 6% higher (~$33 a trade less profit) | about 33-50% higher (~$58 a trade less) | the model is unusable |
| Real mid vs model price | about the model's price | | |

- **Settlement:** the official close and the model's close differ by 1.3 points on average (3.6 at the 95th
  percentile) and by +0.03 on average with sign. Settling on the 15:59 close was fine.
- **Why the model fails far out of the money:** its skew correction there is up to 54×, which gives absurd
  prices on crash days such as April 2025.

## Fill check (did trades actually happen near the ask?)

Rerun on 2026-11-09 with every trade bar downloaded. Every decision and every trade above came out identical;
only this section changed. Descriptive only.

| Entry minute (15:51) | 2013-2020 | 2021-2026 |
|---|---|---|
| Entries with any trade in that minute | 56% (median 10 contracts) | **99%** (median 75 contracts) |
| ...with a trade at or below the 15:51 ask | 95% | **95%** |
| ...with a trade at or below the 15:51 mid | 52% | **83%** |
| Minute's last trade minus the mid (per share) | +$0.58 (half-spread $1.64) | +$0.16 (half-spread $0.38) |

- **Since 2021 these options trade every day in the entry minute, and usually somewhere at or below the mid.**
  That is encouraging for a limit order near the mid. It does not prove your order would fill: someone else's
  trade at the mid may have been ahead of you, or a different size.
- **The price tends to rise during the minute.** The minute's last trade was above the 15:51 ask 46% of the
  time, as you would expect when the move keeps going in the signal's direction. Waiting costs money.
- **On the 580 traded 2021-2026 entries:** at the ask +$73 a trade, at the minute's last trade +$95, at the
  mid +$111.
- **Still untested:** whether a limit at the mid fills less often on the best days.

## What this means for the 15:50 rule

The rule does not change:
- the 15:50 one-minute candle, body at least 60% of its range;
- buy the 0DTE SPXW option in the candle's direction at 15:51, 10 points in the money;
- hold to the close.

What is new is that it is now confirmed at real prices: smaller than the model said, real, and sensitive to how
the order is filled.
