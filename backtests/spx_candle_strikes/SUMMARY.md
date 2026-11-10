# Strike ladder for the 15:50 strong-body signal: plain-English summary

Hand-written on 2026-11-08 from the first run of `strikes.py` (plan: `preregistration/spx_candle_strike_ladder.md`,
ledger 2026-11-08T20:05:04Z). Full tables: [RESULTS.md](RESULTS.md). Research only, not trading advice.

## The question

The signal says which way SPX tends to drift from 15:51 to the close. Which 0DTE strike makes the most of
that: deep in the money, at the money, or out of the money?

## What the 2021-2026 model says (644 signal days, every strike priced by a model)

The signal's edge is small: on average SPX moves about 1.8 points its way in those 9 minutes (at SPX 7700),
and it is right 57% of the time. How much of that edge a contract keeps depends on how much time value it pays
for.

| | Deep in the money (10-20 pts) | At the money | Out of the money 5 | Out of the money 10-20 |
|---|---|---|---|---|
| Cost per contract | about $1,100-2,000 | about $370-440 | about $200 | about $15-200 |
| Mean P&L per contract, range over the credible variants | +$102 to +$214 | +$68 to +$239 | +$8 to +$170 | depends on the pricing assumption, positive or negative |
| Trades that make money | 52-57% | 34-46% | 24-29% | 6-16% |
| Typical (median) trade | about +3% to +10% | about -40% to -62% | -100% | -100% |
| Mean return on premium | +6% to +21% | +15% to +98% | +1% to +176% | can't tell |

- **Deep in the money held up best when the assumptions changed.** It stayed clearly positive in every
  variant: implied volatility 25% higher or lower, a different calibration, or the backtest's own
  realized-move pricing. It behaves almost like the index, with little time value to lose, so it keeps nearly
  the whole small move.
- **At the money depends on how cheap options are.** It pays about 3.7-4.4 points of time value and keeps
  about half the move. Its result ranges from +$68 to +$239 depending on the pricing assumption, and most
  single trades lose about half the premium or more.
- **Out of the money is a lottery the model can't settle.** These strikes need a bigger move than the signal
  usually gives. 84-94% of trades lose money at 10-20 points out, and whether the rare big wins pay for
  that depends on how the market prices those far strikes. The pre-registered skew rule broke here (see below).
- **Per dollar versus per contract.** Per contract, deep in the money earns as much or more, with fewer
  losing trades. Per dollar of premium, at the money has the higher average return, but it is spread over far
  more losing trades.
- **Recent years are weaker.** Over 2023-2026 the signal is right 55% of the time and every strike's
  t-statistic falls to about 1.5-2.9, against 3.3-4.4 in 2021-2022 (headline variant, 20 in the money to 5
  out).

## What 4 real forward trades showed (Oct 22-30, real Robinhood prices; far too few to conclude anything)

| Strike | Wins | Total (hold to the close) |
|---|---|---|
| 20 in the money | 3 of 4 | +$1,494 |
| 10 in the money | 3 of 4 | +$1,214 |
| At the money | 2 of 4 | -$69 |
| 5 out of the money | 1 of 4 | -$682 |
| 10-15 out of the money | 0 of 4 | -$529 / -$305 |

Three of the four signals were right, with moves of 5-8 points. That was enough for in-the-money options,
barely enough for at the money, and not enough for out of the money. On Oct 30 SPX settled 0.07 points below
the at-the-money strike, so that call expired worthless (-$773) while the 20-in-the-money call lost $183.
Strong-body signals on Nov 2, 3 and 6 have no minute option bars and are not in these totals.

## Problems found

- **The skew rule broke for far out-of-the-money strikes. The rule was set in advance, but it was a bad
  design.** On calm 2026 days the normal model prices a 20-point out-of-the-money option near $0, while the
  market charges at least $0.05. The median ratio came out at 54× (2.1× and 2.3× at 10 and 15 points).
  Applying that to volatile 2021-2022 days priced the 20-point option at $1,683 on average, which is
  nonsense. Those cells (variants a, b, d and the a_ sensitivities) are unreliable. The no-skew variant
  underprices the same strikes instead.
- **Calibration rests on 7 days of 2026 option prices and a CFD close at 15:59.** The same $0.10
  half-spread is assumed at every strike. Real in-the-money spreads are wider, which would cut into the
  deep-in-the-money advantage.

## What would firm this up

- More real forward days with minute option bars at all strikes. The collector already saves them each
  weekday.
- A separately pre-registered fix for the far out-of-the-money pricing, for example a $0.05 price floor or a
  model with fatter tails, if those strikes matter.
- Real bid/ask spreads by strike, to replace the flat $0.10.
