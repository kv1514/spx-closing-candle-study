# The 15:50 rule on the real SPX chart, and its 60-70% band: plain-English summary

Hand-written on 2026-11-09 from the one registered run of `realindex.py`. Plan: `preregistration/spx_candle_realindex.md`
(locked 2026-11-10T03:49:10Z, before any result existed). Full tables:
[RESULTS.md](RESULTS.md). Research only, not trading
advice.

## What was tested

Every earlier backtest read the 15:50 candle from a stand-in feed (Dukascopy). This one reads it from the **real SPX
chart** (CNBC's archive, the same source as the live alert) and trades it at the same real option prices as before
(Databento): 10 points in the money at the 15:51 ask, held to the close, 2021 to October 2026. No new data was
bought.

The real candle was on file for 1,310 of 1,322 days (99%). On the 36 days where the broker's own candle is also on
file, the two matched on all four prices on 35.

**What kind of test this is.** The plan was locked first, so the rules could not bend to the result. But the days
and their option results were already known, so this is a check on *which candle to read*, not fresh proof.

## The answer

| Signal on the real chart | Trades | Per trade at the ask | Per day | t | Verdict (fixed in advance) |
|---|---|---|---|---|---|
| **Body 60% or more** (the rule as you'd read it) | 710 | **+$39** | +$21 | 1.53 | **did not pass** (needed t >= 2) |
| Body 70% or more | 579 | +$54 | +$24 | 1.86 | not enough evidence |
| **Body 60-70%** | 131 | **-$24** | -$2 | -0.41 | not enough evidence either way |
| 70%+ compared with 60-70% | | $77 a trade apart | | 1.20 | can't tell them apart |

For comparison, the same rule read from the backtest's feed made +$67 a trade (t 2.40) on these days.

- **The rule is weaker on the real chart.** Positive, but it missed the bar it had to clear.
- **The 60-70% band made nothing.** It lost $24 a trade at the ask (131 trades, 49% winners) and made $20 at the
  mid, and SPX moved the candle's way only 51% of the time. By year it swung from -$179 to +$285 a trade with no
  pattern. Formally "not enough evidence either way": no edge was found, and it wasn't proven to lose.
- **70%+ came close but did not pass either** (t 1.86 against a bar of 2).

## Why the real chart is weaker: the two candles disagree, and the feed's candle was the better guide

This part is a description, not a test.

| Which candle showed a strong body | Trades | Per trade at the ask |
|---|---|---|
| **Both** the real chart and the feed | 520 | **+$81** |
| **Only the real chart** | 190 | **-$74** |
| Only the feed | 63 | -$46 |

- **The edge sat on days when both candles agreed.** Those 520 trades made +$81 each.
- **Days when only the real chart showed a strong body lost money**, and that includes real-chart candles of 70%
  or more (98 trades, -$107 each). Reading the real chart adds about 190 such days, and they drag the average from
  +$67 down to +$39.
- **So "70% on your chart" is not a safe translation of the rule.** The audit said the feed's 60% is about 70% on
  the real chart. As a matter of how often each fires that still holds (69% on 1,310 days). But the candles are
  not interchangeable: about 1 in 6 real-chart candles of 70%+ was under 60% on the feed, and those days lost.
- A likely reason, not tested: the feed tracks futures, which move first. The index is an average of 500 stock
  prices and catches up a moment later, so a strong index candle is sometimes just the index catching up.

By size of the real-chart candle (description; trading in the candle's direction whatever its size):

| Body on the real chart | Trades | Per trade at the ask |
|---|---|---|
| under 60% | 594 | -$16 |
| 60-70% | 131 | -$24 |
| 70-80% | 141 | -$56 |
| 80-90% | 160 | +$67 |
| 90-100% | 278 | +$102 |

On the real chart the money was in candles of 80% or more (438 trades, +$89 each). That cut was not planned and was
chosen by looking, so it is a lead for the forward log, not a rule.

The index itself tells a calmer story: after a real-chart candle of 70%+, SPX moved the candle's way by 2.6
hundredths of a percent on average (t 4.6, 57% of days). After a 60-70% candle: nothing (51%). So the direction
signal is real at 70%+ on the real chart; it is the option trade's result that falls short of the bar.

## What this changes

- **Earlier today I wrote that 70%+ on your chart "is the tested signal". That was too strong.** The tested signal
  is the feed's candle. On your chart, 70%+ is the better band, but it did not pass its own test, and the days your
  chart fires alone were losers.
- **60-70% on your chart: no edge found.** This is now measured directly (131 trades), not inferred.
- **The original result stands as it was:** read from the feed's candle, the rule made +$67 a trade (t 2.40). What
  is new is that reading it from the real SPX chart, which is what a person actually does, gave a weaker and
  unconfirmed result.
- **The practical gap:** the feed's candle is not available live for free, and the alert reads the real chart. The
  daily two-feed log now records both, so over time it will show whether "both agree" keeps beating "chart only".

## Honest limits

- Same days and option results as before; only the candle changed. Not a fresh test.
- The "both / only one" table and the 80%+ cut are descriptions made after seeing the result.
- The backtest buys at the quote the instant the candle closes. A real order is seconds later.
- 12 days had no archived candle; on those days the feed rule's known result was ordinary (+$22 a day against
  +$30 on the rest).
