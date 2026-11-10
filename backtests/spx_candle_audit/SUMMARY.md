# Independent re-check of the 15:50 rule: plain-English summary

Written 2026-11-09. Research only, not trading advice.

**What this is.** A second pair of eyes on everything behind the rule:
- new code that shares nothing with the earlier studies, run on the same raw files;
- no new data bought (Databento spend unchanged at $93.52);
- 14 more days of the free Dukascopy feed downloaded, to compare it with the real SPX chart.

**What this is not.** A fresh test. Every day here was already used by an earlier study, so nothing below can
"prove" a new setting. It can only check the old work and show how sure anyone can be.

Full numbers: [results.json](results.json). Code: `build_cache.py`, `audit.py`, `threshold.py`, `feeds.py`.

## 1. Is the data sound? Yes

| Check | Result |
|---|---|
| 1,286,750 one-minute bars | no duplicates, none out of order, no bar with an impossible high or low |
| Calendar, April 2013 to October 2026 | 3,537 weekdays: 126 holidays and 29 half days removed, 95 more dropped for gaps in the feed, 3,287 kept |
| Holidays, checked a second way | the 126 weekdays with no Cboe close are exactly the 126 listed holidays |
| Every kept day | has option quotes or a "no same-day expiry" marker, and an official Cboe close |
| Official closes against the broker's closes | identical on all 716 days that have both (2024 to 2026) |
| 6,537,660 option quote rows | all stamped exactly on the minute, no duplicates |
| Feed level against the real options market at 15:51 | 0.46 points apart on average; 1.2 points at the 95th percentile |
| Is the 15:50 bar really the 15:50 minute? | Yes. Its move matches the real options market's move in that same minute (correlation 0.98), and not the minute before (-0.01) or after (0.08). So no clock error and no peeking ahead |
| Direction of the candle on signal days, 2021-2026 | the same as the real options market on 585 of 586 days |

One thing to know: **the feed was coarser in its early years.** In 2013-2014, 21-31% of 15:50 candles had a body
equal to the whole range, because the feed ticked rarely. Since 2021 that is 1-4%. So "60%" was a looser test back
then. The 2021-2026 results are the ones on a consistent feed.

## 2. Do the published numbers reproduce? Yes, exactly

| 2021-2026, real asks, 10 in the money | Published | Rebuilt from scratch |
|---|---|---|
| Trades | 585 | 585, the same days |
| Average per trade | +$67.46 | +$67.46 |
| t-statistic | 2.40 | 2.40 |
| Trades that won | 54% | 53.8% |
| Worst trade | -$2,210 | -$2,210 |
| Trades whose strike, price or result differ | | **0** |

"Per day" always means per day that had a same-day expiry and prices: 1,321 of the 1,446 sessions in 2021-2026
(SPXW only had daily expiries from 2022).

Also matching to the dollar:
- 2013-2020: 216 trades, -$23 a trade at the ask, +$145 at the mid;
- every strike in the ladder (20 in the money +$77 down to 10 out of the money +$1);
- each year (2021 +$175, 2022 +$71, 2023 +$4, 2024 +$20, 2025 +$65, 2026 +$121);
- buying late (15:52 +$56, 15:55 +$23);
- selling early at the bid (15:52 -$60; every minute to 15:59 was $79-$136 worse than holding);
- the re-tuning study's 40%-90% table.

**How wide is the uncertainty?** Resampling the days 5,000 times, the average for the rule lands between **+$21
and +$115 a trade** nine times out of ten. It is positive, but its size is not pinned down.

**One gap in the older period.** In 2013-2020 only **216 of 394** signal days could be priced. The pricing rule
needs three strikes quoted on both sides, and calm days often lacked that (2017: 71 of 80 signal days missing). So
the pre-2021 result describes the livelier days of that era. Pricing the 177 missing days a simpler way (the
feed's own index level) gives the same picture, only worse at the ask: -$89 a trade at the ask, +$68 at the mid.
In 2021-2026 the gap does not exist: 585 of 586 priced.

**One assumption to keep in mind.** The backtest buys at the quote standing at 15:51:00, the instant the candle
finishes. Nobody is that fast. A minute's delay cost about $12 a trade, so a real result sits a little below
+$67.

## 3. What is the best body %?

All in the backtest feed's own readings, 2021-2026, real asks, 10 in the money.

**By body size, one bucket at a time:**

| Body, as % of range | Trades | Per trade at the ask | Won |
|---|---|---|---|
| under 20% | 220 | -$53 | 44% |
| 20-40% | 223 | -$21 | 49% |
| 40-50% | 141 | -$15 | 50% |
| 50-60% | 149 | -$59 | 46% |
| **60-70%** | 150 | **+$6** | 48% |
| **70-80%** | 135 | **+$42** | 56% |
| **80-90%** | 149 | **+$97** | 54% |
| **90-100%** | 151 | **+$122** | 58% |

- **Below 60% there is nothing.** Every bucket lost money after costs.
- **The index itself says the same, in both periods.** With a body under 60%, SPX moved about 0 further in the
  candle's direction by the close (-0.5 hundredths of a percent in 2013-2020, -0.2 in 2021-2026). With a body of
  60% or more it moved +2.4 in both periods (t 3.6 and 4.2). That is 3,230 days of evidence that the effect starts
  at about 60%.
- **Bigger bodies did better per trade,** but each single bucket is too noisy to be sure of (no bucket has t ≥ 2).
- One trade sits exactly on the 80% line. Counting it in the higher bucket changes those two rows to +$45 and
  +$94. Nothing else moves.

**By threshold ("trade when the body is at least X"):**

| At least | Trades | Per trade | Per day | t |
|---|---|---|---|---|
| 50% | 734 | +$42 | +$23 | 1.70 |
| **60% (the rule)** | 585 | +$67 | **+$30** | 2.40 |
| 65% | 508 | +$68 | +$26 | 2.27 |
| **70%** | 435 | +$89 | **+$29** | 2.65 |
| 75% | 380 | +$92 | +$26 | 2.56 |
| 80% | 300 | +$110 | +$25 | 2.58 |
| 90% | 151 | +$122 | +$14 | 2.09 |

- **60% and 70% made about the same money per day.** 70% does it with a quarter fewer trades, so more per trade.
- **The data can't pick between them.** Resampling the days 5,000 times:
  - 60% came out best 32% of the time, 70% 22%, 75% and 80% about 7-8% each;
  - 70% beat 60% in 45% of resamples, a coin flip;
  - the gap between them could be anywhere from 70% being $11 a day worse to $9 a day better;
  - nine times out of ten the "best" number landed somewhere between 25% and 80%.
  - These shares show how unstable "the best number" is on this sample. They are not the chance that 60% is
    truly the best setting.
- **Chasing the best past number did worse.** Each year, using whichever threshold had been best on the earlier
  years made +$16 a day in 2022-2026 if "earlier" starts in 2021, and +$20 if it starts in 2013. Staying at 60%
  made +$24. (Five years is a small sample; the difference is not significant. With the full history, the
  best-so-far number was 60% itself in four of the five years.)
- **The two halves disagree above 75%.** 80% was the best in 2021-2023 (+$38 a day) and poor in 2024-2026 (+$13).
  Only 60-75% made roughly $25-$32 a day in both halves.

**Answer:** in the backtest's readings, the edge starts at 60% and anything from 60% to about 75% is equally well
supported. There is no "most optimal" number inside that band that the data can identify. 60% is not wrong; 70% is
not better in a way that can be shown. None of this is a fresh test: the same days chose the rule.

## 4. New and important: your chart is not the backtest's chart

> **Superseded in part (2026-11-09, later the same evening).** A pre-registered backtest on 1,310 days of real SPX
> candles has since measured this directly: see [the real-index study](../spx_candle_realindex/SUMMARY.md). The
> frequency mapping below held up (the feed's 60% is about 69% on the real chart). The suggestion in sections 4-5
> that "70%+ on your chart is the tested signal" did not: on the real chart the rule made +$39 a trade at 60%+
> (not confirmed), 60-70% lost $24 a trade, and days when only the real chart fired lost money even at 70%+.

Every backtest reads the candle from a **Dukascopy feed** (a stand-in that tracks SPX). You, and the live alert,
read the **real SPX candle**. They move together, but the candle's shape differs, and the body % is a shape.

On the 36 days where both exist (21 September to 9 November 2026):

| At 15:50 | Real SPX chart | Backtest feed |
|---|---|---|
| Days with body ≥ 60% | **20** | **14** |
| Typical body % | 65% | 54% |

- **All 14 backtest signals also fired on the real chart, same direction.** Nothing is missed.
- **The real chart fired on 6 extra days** that the backtest would not have traded (today, 9 November, was one:
  62% on the real chart, 58% on the feed).
- Over all 1,080 candles from 15:30 to 15:59 on those days, the real chart read ≥ 60% on 45% of candles and the
  feed on 35%.
- **A real-chart candle reading 60-70% was a backtest signal only 42% of the time.** At 70-80% it was 61%, and
  above 80% it was 82-87%.
- With a **70%** cut-off on the real chart, 15:50 fired on 17 days: all 14 backtest days plus 3 extras. With 75%:
  all 14 plus 2.

**What this means.** "60% on your chart" is a looser rule than the one that was backtested. Roughly, **the
backtested 60% corresponds to about 70% on the real chart.**

**What it does not mean.** It does not show the extra days are bad. On the 6 extra days SPX went the candle's way
4 times. Six days say nothing either way. Those days are simply **untested**.

Caveats: 36 days, all from autumn 2026. The gap between the feeds may differ in other years.

## 5. The procedure the evidence supports

Unchanged, and now checked twice by independent code:

1. Watch the **15:50 one-minute SPX candle**. At 15:51:00 measure body ÷ range.
2. **Signal:** body at least 60% of the range, in the backtest's terms. On the real SPX chart:
   - **70% or more: this is the tested signal.** These are almost always days the backtest traded.
   - **60-70%: borderline.** More often than not the backtest would not have traded it. Untested, not proven bad.
   - **Under 60%: no trade.** No edge anywhere in 13 years.
3. **Direction:** with the candle. Green → call, red → put.
4. **Contract:** 0DTE SPXW, **10 points in the money** (15-20 in the money did about the same and cost more;
   at the money is cheaper, weaker and unconfirmed; out of the money did not work; XSP and SPY did not work).
5. **Entry:** at 15:51, quickly. A minute late cost about $12 a trade and four minutes late about $44.
6. **Exit:** none. Hold to the 16:00 settlement. Every earlier exit tested made less.

What to expect has not changed either: about +$67 a trade at the ask on roughly $1,100 at risk, 54% winners, a
worst trade of -$2,210, and two weak years (2023 +$4, 2024 +$20).

## 6. Correlations: how strongly does body % go with what happens next?

Added 2026-11-09 (evening). Numbers: [correlations.json](correlations.json); code: `correlations.py`. Descriptive,
on days already used, so nothing here is a new test.

A correlation runs from -1 to +1. 0 means no link; +1 means the two always move together.

| What against what | Correlation | In plain words |
|---|---|---|
| Body % vs SPX's move after 15:51, every day, 2013-2020 | +0.06 | real, but faint |
| The same, 2021-2026 | +0.08 | real, but faint |
| Body % vs the option trade's result, every day, 2021-2026 | +0.08 | real, but faint |
| Body % vs the option result, **signal days only** (60%+) | +0.06 | not distinguishable from zero |
| Candle size in points vs SPX's move, signal days | +0.19 and +0.13 | a bigger candle is followed by a bigger move |
| Candle size vs "did SPX go the candle's way", signal days | +0.02 to +0.05 | no: it was not right more often |
| **Real chart % vs backtest feed %, at 15:50** (36 days) | **+0.90** | they agree closely; the real chart just reads higher |
| Real chart % vs SPX's move, the new log (36 days) | +0.01 | nothing visible yet: far too few days |

What that means:

- **Body % works like a switch, not a dial.** Under about 60% there is nothing; above it there is an edge. But once
  a candle is past 60%, a higher % did not reliably mean a better trade. Splitting the signal days into thirds by
  body %, the option trade made +$19, +$102 and +$80 a trade in 2021-2026 (lowest to highest third), while in
  2013-2020 the lowest third had the biggest index move. No steady slope.
- **Body % explains under 1% of what SPX does next.** That is normal for a real trading edge: almost all of any one
  day is noise, and the edge only shows over hundreds of trades. It is also why one good or bad week says nothing.
- **Bigger candles had bigger follow-through, but were not right more often.** This is a new angle, not something
  any study tested. Most of it is simply that wild minutes are followed by wild minutes, so both the wins and the
  losses get bigger, and a few large days drive the number. Treat it as an idea for the new log, not a finding.
- **The two charts agree strongly (+0.90) but with an offset.** The best straight line through the 1,080 late-day
  candles is: feed % ≈ 10 + 0.72 × real %. So a real-chart 60% is about 53% on the backtest's feed, and the
  feed's 60% is about **70% on the real chart** (69.5). This is a second method reaching the same "about 70%".

**The new log so far** (36 days, 21 September to 9 November 2026; only the 14 days after 20 October are outside
every backtest), by the band on the real chart:

| Band on your chart | Days | SPX went the candle's way | Average move that way |
|---|---|---|---|
| 70%+ | 17 | 11 | +1.5 points |
| 60-70% | 3 | 2 | +3.9 points (one big day: 9 November) |
| under 60% | 16 | 10 | +1.1 points |

Even the no-signal days went the candle's way 10 times in 16 here. That is what 36 days of noise looks like. With
a true link as faint as the history shows, it takes on the order of a thousand days to see it in a correlation,
and a few hundred signals to compare the bands. This table is a running record, not evidence yet.

## What is logged automatically from now on

Set up 2026-11-09 in `tools/spx_1550_alert.py` (the launchd alert that already runs every weekday):

- **Every alert is tagged** with its band on the real chart. A 70%+ signal says so; a 60-70% signal is titled
  "borderline" and says why.
- **Every closing message** shows the band and a running total for each band.
- **`data/spx_1549/alerts/feeds_1550.csv`** gets one row a day, signal or not: the real 15:50 candle and its %,
  the backtest feed's 15:50 candle and its %, both bands, and SPX's move from 15:51 to the close. The feed's file
  usually appears the next day, so each day's row is completed on the following run.
- To refresh every table in section 6 as the log grows:

      .venv/bin/python -I backtests/spx_candle_audit/build_cache.py /tmp/audit_cache.pkl
      .venv/bin/python -I backtests/spx_candle_audit/correlations.py /tmp/audit_cache.pkl

## What would actually settle the open questions

Only new days can. Past data has been searched three times now.
- The log above is that record. It needs months, not days.
- A longer history of real SPX one-minute candles would answer the chart question at once, but none is on file
  and buying one is a new, paid study that would need its own locked plan.
