# Early exits vs holding to the close: plain-English summary

Hand-written on 2026-11-08 from the first run of `exits.py` (plan: `preregistration/spx_candle_exit_rules.md`,
ledger 2026-11-09T07:40:05Z). Full tables: [RESULTS.md](RESULTS.md). Research only, not trading advice.

## The question

The strike study bought at 15:51 and held to the 16:00 settlement. Would it do better to get out early, with a
stop when SPX moves against the trade or a take-profit when it moves in favour? Six rules were fixed in advance.
Each watches SPX at every minute's close from 15:51 to 15:58 and sells the option at the next minute's open.

## The answer: no rule beat holding

The pre-stated test: a rule counts as better only if, at 10 points in the money in the main model, it beats
holding by a clear margin (t above 2.64), and it is also ahead in two other pricing versions. **None of the six
came close. Every rule made less money than holding, in every pricing version and at every strike tested.**

10 points in the money, main model, 644 signal days from 2021 to 2026:

| Rule | How often it sold early | Average per contract | vs holding | Trades that made money | Worst trade |
|---|---|---|---|---|---|
| Hold to the close | never | +$166 | | 54% | -$3,601 |
| Stop at 3 points against | 51% | +$87 | -$79 | 38% | -$1,192 |
| Stop at 5 points against | 35% | +$111 | -$55 | 46% | -$1,481 |
| Stop at 8 points against | 20% | +$137 | -$30 | 50% | -$1,481 |
| Take profit at 5 points | 44% | +$84 | -$82 | 63% | -$3,601 |
| Take profit at 10 points | 19% | +$101 | -$65 | 56% | -$3,601 |
| Stop 5 or target 10 | 51% | +$63 | -$104 | 48% | -$1,481 |

What the trade-offs look like:

- **Stops cut the worst days but cost money on average.** The worst trade shrinks from about -$3,600 to about
  -$1,200 to -$1,500. That costs $30-$80 a trade on average, and fewer trades end up making money. The signal's
  edge is a small drift over 9 minutes, and a lot of dips come back before the close. Every early sale also pays
  the spread and a fee a second time.
- **Take-profits win more often but make less.** At 5 points, 63% of trades made money, against 54% for holding,
  but the average fell by $82. A take-profit sells the trades that were working before they finish working, and
  it does nothing for the trades that go wrong.
- **The wider the stop, the less it costs.** A stop at 8 points costs the least ($30 a trade) and still cuts the
  worst trade by more than half. In 2023-2026 alone its average was close to holding: +$83 against +$90 at 10 in
  the money, and +$96 against +$93 at the money. That is a description, not a test, and it did not meet the
  criterion.
- **Every rule loses money against holding at every strike tested:** 20 in the money, 10 in the money and at the
  money. That holds in all six pricing versions.

## Selling at a fixed minute, at real bids (descriptive, added 2026-11-09)

Not pre-registered: computed on the 585 real-price confirmation trades (2021-2026, Databento quotes), which
had already been used. Each trade bought at the 15:51 ask, then sold at the bid at the start of each later minute,
paying the $0.09 fee twice, against holding to the 16:00 settlement.

| Sell at | Average per contract | vs holding | t of the difference | Trades that made money |
|---|---|---|---|---|
| **Hold to 16:00** | **+$67** | | | 54% |
| 15:52 bid | -$60 | -$128 | -4.8 | 38% |
| 15:53 bid | -$64 | -$131 | -5.1 | 39% |
| 15:54 bid | -$60 | -$128 | -5.3 | 40% |
| 15:55 bid | -$69 | -$136 | -6.3 | 41% |
| 15:56 bid | -$35 | -$102 | -5.8 | 45% |
| 15:57 bid | -$12 | -$79 | -5.4 | 48% |
| 15:58 bid | -$19 | -$87 | -6.4 | 45% |
| 15:59 bid | -$38 | -$105 | -7.8 | 44% |
| Best minute in hindsight | +$341 | +$273 | | 77% |

- **Every fixed exit time lost money, and holding beat each one by $79-$136 a trade.** Selling early pays the
  spread a second time and gives up the move into the close.
- **The "best minute" row is not a strategy:** it sells at whichever minute turned out best, which nobody knows
  in advance. It only shows how much the price wiggles after entry.
- No year favoured an early exit clearly: 2026 was the only year where selling at 15:56-15:59 made money, and
  even there holding made more (+$121).

## What the real forward trades showed (4 trades; far too few to conclude anything)

At 10 in the money, holding made +$1,214 over the 4 trades.
- **A take-profit at 5 points made +$1,591.** On Oct 30 SPX rose 5 points by 15:53 and then fell, so it sold
  before the drop.
- **Every stop made +$592.** On Oct 30 SPX dropped about 10 points in the 15:56 minute, the stop sold the
  option at $3.95, and SPX bounced back by the close (the option settled at $10.07).

One real day can go either way; the model's 644 days are the better guide, and they say hold.

## What this does and doesn't say

- It is a model, not observed P&L. Early sales are priced with the entry's volatility and skew, a $0.10
  half-spread and a one-minute delay. Real exits in a fast move are usually worse, which would make the early
  rules look even worse.
- It says nothing about risk tolerance. If a -$3,600 day on one contract is unacceptable, a stop or a smaller
  position limits it, at a cost of roughly $30-$80 a trade on average in this model.
- Real option quotes for 2013-2026 are now being downloaded from Databento, which can replace the model's
  pricing with real prices, under a new pre-registration.
