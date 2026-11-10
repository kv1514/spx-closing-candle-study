# SPX debit spreads for the 15:50 rule: planning note (2026-11-09)

Not a pre-registration, and nothing new was run. This note is why a formal spread backtest on 2021-2026 would not
be a real test, and what the numbers already on file imply. Research only, not trading advice.

## Why a backtest on 2021-2026 can't be a fresh test

Take a debit spread: buy one option at the ask, sell a second at the bid, and both settle at the 16:00 close. Its
result on any day is exactly:

    spread P&L = (long leg bought at the ask) − (short leg bought at the ask) − (short leg's bid-ask gap) − one extra fee

The real-price study (`spx_candle_realprice`, 2021-2026) already published the result of buying every strike from
20 in the money to 20 out of the money at the 15:51 ask. The only missing piece is each strike's bid-ask gap, and
that is just a price, not an outcome. So the spread's average is already determined. A locked plan would only redo
the arithmetic.

## What the numbers on file imply (rough: averages over slightly different day sets, within a few dollars)

Signal days 2021-01-01 to 2026-10-20, entry at the 15:51 quotes, one contract, $0.09 fee per leg. Costs and bid-ask
gaps are averages from the Databento quotes on those days. Results per trade come from `realprice/results.json`
(single options) or the formula above (spreads).

| Position | Cost | Average per trade | Per $1 of cost | Note |
|---|---|---|---|---|
| **Buy 10 in the money (the rule)** | $1,100 | **+$67** | 6.1¢ | t 2.40, 54% won |
| Buy 5 in the money | $658 | +$54 | 8.2¢ | t 2.07, 50% won |
| Buy at the money | $323 | +$40 | 12.2¢ | t 1.87 (below 2), 39% won, median −$110 |
| 10 in / sell 10 out (20 wide) | $1,038 | ≈ +$57 | ≈ 5.5¢ | barely cheaper |
| 10 in / sell 5 out (15 wide) | $967 | ≈ +$42 | ≈ 4.4¢ | |
| 10 in / sell at the money (10 wide) | $799 | ≈ +$7 | ≈ 0.8¢ | edge gone |
| 10 in / sell 5 in (5 wide) | $488 | ≈ −$33 | negative | it can win at most $12 |
| At the money / sell 10 out (10 wide) | $261 | ≈ +$29 | ≈ 11¢ | about the same as at the money alone |
| At the money / sell 5 out (5 wide) | $190 | ≈ +$14 | ≈ 7.4¢ | |

Average bid-ask gap at 15:51, per contract:
- 10 in: $77
- 5 in: $46
- at the money: $21
- 5 out: $13
- 10 out: $10

## What this says

- **A spread never beat simply buying its long leg on its own, per dollar of cost.**
  - The leg you sell gives away its own share of the signal's edge. Selling the at-the-money option gives up
    +$40 of the +$67.
  - You also pay that leg's bid-ask gap.
  - The spreads that keep most of the edge (selling far out of the money) barely lower the cost.
- **The cheaper choice already in the data is a closer SPX strike, not a spread.**
  - At the money cost about $323 and made +$40 a trade, 12 cents per dollar.
  - The catch: it is noisier. Only 39% of trades won, the median trade lost $110, and on its own it fell short of
    the t ≥ 2 bar (1.87).
  - These strikes were measured on the same data that picked 10 in the money. They are descriptive, not
    separately confirmed.
- **What the data can't show:** SPX spreads are usually sent as one combo order, which can fill better than buying
  and selling each leg at the quotes. Databento's quote data has no combo order book, so this can't be tested here.

## A genuinely fresh test would have to be forward

New days after 2026-10-20 are untouched. The alert's close job already reads the Cboe option snapshot at 15:51. It
could also log the asks and bids of 5 in, at the money and 10 out each signal day, at no cost. At about 2 signals
a week this takes years to reach the 2021-2026 sample size. It would be a running record, not a quick answer.
