# The 15:50 rule read from SPY's candle: plain-English summary

Hand-written on 2026-11-09 (late evening) from the one registered run of `spycandle.py`. Plan:
`preregistration/spx_candle_spy.md` (locked 2026-11-10T05:01:33Z before any result
existed). Full tables: [RESULTS.md](RESULTS.md). 
Research only, not trading advice.

## What was tested

The rule passed its test when the signal was read from a stand-in feed you can't see live, and did not pass when
read from the real SPX chart. That feed follows futures. SPY trades live and follows them too, so this test reads
the 15:50 candle from **SPY** (CNBC's archive, 1,312 of 1,322 days, 2021 to October 2026) and trades the same SPX
option as before at the same real prices: 10 points in the money, in the SPY candle's direction, at the 15:51 ask,
held to the close. No new data was bought.

## The answer: SPY's candle passed all three lines

| Signal | Trades | Per trade at the ask | Per day | t | Result (bars fixed in advance) |
|---|---|---|---|---|---|
| **SPY candle, body 60% or more** (main question) | 523 | **+$72** | +$29 | 2.35 | **met** (needed t >= 2) |
| SPY candle **and** the SPX chart both 60%+, same direction | 504 | +$80 | +$31 | 2.56 | met |
| **SPY candle, body 70% or more** | 369 | **+$103** | +$29 | 2.84 | met |

For comparison on the same days: the backtest's feed made +$69 a trade, and the SPX chart alone made +$39 and did
not pass.

- **SPY's candle did the job the feed did.** Same size of result, from a candle you can watch.
- **SPY at 70%+ was the strongest version**, and it made money in every one of the six years (2021 +$281, 2022
  +$141, 2023 +$30, 2024 +$94, 2025 +$95, 2026 +$84 a trade).
- **SPY at 60-70% made nothing** (-$4 a trade, 154 trades). As on the other two charts, the 60-70% band adds trades
  without adding profit.

## How SPY's candle relates to the other two (description, not a test)

- **A strong SPY candle is nearly always a strong feed candle.** Of SPY candles at 70%+, 94% were signals on the
  backtest's feed, and 97.5% were also 70%+ on the SPX chart. So SPY is a good live stand-in for the feed.
- **The money was where all three charts agreed.**

| Which candles showed a strong body | Trades | Per trade at the ask |
|---|---|---|
| SPY, SPX chart and feed: all three | 435 | **+$113** |
| SPY and SPX chart, not the feed | 69 | -$123 |
| SPX chart and feed, not SPY | 82 | -$78 |
| SPX chart only | 121 | -$46 |
| Feed only | 54 | -$34 |

  Every kind of disagreement lost money on average. None of those single rows is statistically firm on its own;
  together they say the same thing as the last study: a strong candle on only some charts is not the signal.
- **SPX itself moved the candle's way after a strong SPY candle:** by 3.4 hundredths of a percent on average after
  SPY candles of 70%+ (t 4.7, right 58% of the time), against 1.3 after 60-70% and 0.4 after weaker candles.

By size of SPY's candle (trading in its direction whatever its size):

| SPY body | Trades | Per trade at the ask |
|---|---|---|
| under 60% | 765 | -$32 |
| 60-70% | 154 | -$4 |
| 70-80% | 145 | +$90 |
| 80-90% | 125 | +$137 |
| 90-100% | 99 | +$81 |

On SPY the edge starts at 70%, not 80% as it did on the SPX chart.

## Why to stay careful

- **This is the third chart tried on the same days.** The feed, then the SPX chart, now SPY. Try enough charts and
  one will look good by luck. The plan was locked before the result, which rules out bending the rules, but it
  does not make these fresh days. Both side questions were also chosen after seeing that "charts agreeing" had
  done well. So this is weaker evidence than t = 2.35 to 2.84 would be on new data.
- **SPY candles differ between data vendors.** On about a third of days CNBC's SPY candle and Yahoo's differ by a
  cent or two in at least one price, enough to move a borderline candle across the 60% or 70% line. This result is
  for CNBC's SPY candle. Your broker's SPY chart may read slightly differently.
- **The 10 days with no SPY candle on file were poor days** for the feed's rule (about -$60 a day against +$31 on
  the rest). Had they been on file, the result would likely be a touch lower. It is unlikely to change the verdict.
- **The backtest buys at the quote the instant the candle closes.** A real order is seconds later, and a minute's
  delay cost about $12 a trade in the earlier study.
- **Same risk as before:** about $1,100 a contract, the worst trade lost $2,210, and nearly half of trades lose.

## What this means

- **Among candles you can actually watch, SPY's 15:50 candle is the one with support.** At 70% or more it matched
  or beat the original feed result in this data.
- **The SPX chart alone is the weakest of the three.** It fires on about 200 extra days that lost money.
- **60-70% is not worth separating out on any chart.** No edge was found there on the feed (about break-even), on
  the SPX chart (-$24) or on SPY (-$4).
- What would turn this from a strong lead into evidence: the same thing on new days. Since 2026-11-09 (late) the
  live alert follows this rule and sends two messages a day: "ARM" or "STAND DOWN" at about 15:50:40 ET, then "BUY
  CALL/PUT <strike>" or "NO TRADE" right after 15:51:00 (BUY needs SPY at 70%+ and the SPX chart at 60%+ in the same
  direction). The daily log `data/spx_1549/alerts/feeds_1550.csv` records SPY's candle next to the other two, and
  the close log records what each day's SPX-chart signal made together with the message-2 decision.
