# Limit orders and late entries: plain-English summary

Hand-written on 2026-11-09 from `fills.py run`. Full tables: [RESULTS.md](RESULTS.md). Trade-by-trade:
`data/spx_1549/databento/fills_trades.csv`. Descriptive: nothing here was pre-registered, tested or chosen, and
2021-2026 had already been used to confirm the rule. Research only, not trading advice.

## The question

The real-price study bought at the 15:51 ask: +$67 a trade on 2021-2026. At the mid it would have been +$106.
So should you put in a limit order at the mid?

The catch is that a limit at the mid does not always fill, and **the days it misses are not random**. It fills
when someone sells to you below the mid, which happens most when the option is getting cheaper, meaning the trade
is going against you. When the trade works straight away, the price runs off and your limit sits there unfilled.

## How it was tested

The same entries as the real-price study (585 priced signal days in 2021-2026), with real quotes and real trade
prints from Databento. A limit order counts as **filled** in a minute it is working if either:
- a trade printed strictly below your limit price in that minute (a trade exactly at your price might have been
  someone else's order ahead of yours); or
- the quote at the end of that minute offered the option at or below your price.

Other rules:
- **Prices are rounded up to a real tick:** $0.05 under $3, $0.10 above.
- **A day with no fill counts as $0,** because you didn't trade.
- **Six order styles were set before any result was computed**, and all six are reported.

**This is a proxy, not an exact replay.** Trade prints and one-minute quote snapshots can't prove your order
would have filled, and the simulation assumes your order is live the instant the 15:50 candle closes.

## The answer: the limit at the mid doesn't beat paying the ask

2021-2026, 585 priced signal days, one contract:

| How you buy at 15:51 | Filled | $ per signal day | vs paying the ask |
|---|---|---|---|
| **Pay the ask** | 100% | **+$67** | |
| Limit at the mid for one minute, else skip | 84% | +$65 | -$3 (t -0.2) |
| Limit at the mid for three minutes, else skip | 91% | +$65 | -$3 (t -0.3) |
| **Limit at the mid for one minute, else pay the 15:52 ask** | 100% | **+$70** | +$2 (t 0.6) |
| Limit halfway between the mid and the ask, else pay the 15:52 ask | 100% | +$62 | -$5 (t -1.6) |

**Why:** look at what the same trades made at the ask, split by whether the mid limit filled:

| Mid limit, 2021-2026 | Days | Made at the ask | Won |
|---|---|---|---|
| Filled | 489 | +$43 a trade | 52% |
| **Not filled** | **96** | **+$194 a trade** | **61%** |

The mid limit saves about $35 a trade on the days it fills, and then misses the best days. Those two effects
roughly cancel.

- **The +$106 "at the mid" figure is not something you could have collected.** The realistic number is about
  what paying the ask gives: **roughly +$62 to +$70 a trade.**
- **No order style was clearly better than paying the ask.** Every difference is within noise.
- **"Limit at the mid, then pay the ask at 15:52 if it hasn't filled" was the steadiest style.** Against paying
  the ask it made +$13 a day in 2021-22 and -$2 a day in 2023-26. That makes it a reasonable way to buy, not an
  edge.
- **2013-2020 looked different.** The mid limit filled on only 32% of days, and the filled days were the better
  ones. But spreads were five times wider, the sample is small (216 priced days, after 178 signal days could not
  be priced at all), and it doesn't change the conclusion for today.

## Being late costs money

Buying the same contract at the ask a little later (2021-2026, 585 days):

| Buy at | $ per trade | t |
|---|---|---|
| **15:51** | **+$67** | 2.29 |
| 15:52 | +$56 | 2.02 |
| 15:53 | +$58 | 2.16 |
| 15:55 | +$23 | 1.11 |

**Being one minute late costs about $12 a trade. Being four minutes late costs two-thirds of the edge.** Have the
order ready before 15:51, and send it as soon as the 15:50 candle closes. In 2023-2026 alone, the 15:52 entry
made +$35 against +$50 at 15:51.

## Caveats

- **This is a proxy.** Legs of spread orders can print away from the quote, so a trade below your limit is
  strong evidence of a fill, not proof. An offer that dipped to your price and came back within the minute is
  not seen.
- **Zero delay is assumed.** A real order sent at 15:51 arrives a few seconds late.
- **Your size and place in the queue are unknown.** This assumes one contract.
- **This was not pre-registered,** and these are descriptions on data that already confirmed the rule. The
  late-entry table was added after the first run.
- Nothing here is a trading recommendation.
