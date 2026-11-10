# Re-tuning the 15:50 rule on 2021-2023: plain-English summary

Hand-written on 2026-11-09 from `refine.py tune` and `refine.py test`, run once each. Plan:
`preregistration/spx_candle_refine.md` (locked 2026-11-09T16:39:33Z, before any code existed). Full tables:
[RESULTS.md](RESULTS.md). Research only,
not trading advice.

## The question

The first real-price study tuned on 2013-2020 and found nothing better than your rule. But spreads were five
times wider then, so it couldn't tell 60% from 70%, or one candle from another. This study re-ran the same
search on **2021-2023**, which has today's tight spreads and daily expiries:
- every candle from 15:40 to 15:50;
- body 40% to 90%;
- with or against the candle;
- strikes from 20 in the money to 20 out of the money (2,178 versions).

Whatever won would then be tested **once** on 2024-2026.

## The answer: nothing beat your rule, so it stays

**The best version on 2021-2023 was: 15:50 candle, body at least 80%, 20 points in the money.**

| 2021-2023, real asks | Per day | Per trade | Trades | Won |
|---|---|---|---|---|
| Best version (80%, ITM20) | +$40 | +$187 | 133 | 62% |
| Your rule (60%, ITM10) | +$30 | +$69 | 270 | 55% |

**It failed the luck check (p = 0.21).** When the signals were shuffled so they had nothing to do with the days,
the best of the 2,178 versions scored this well about one time in five. The bar was one in twenty. So under the
locked rules it never went to the test, and **your rule stays.**

**The 2024-2026 numbers agree.** They were computed after the decision was written, and they decide nothing:

| 2024-2026, real asks | Per day | t | Per trade | Trades |
|---|---|---|---|---|
| The 80% / ITM20 version | +$19 | 1.30 | +$79 | 167 |
| **Your rule** | **+$30** | 1.64 | +$66 | 315 |

The version that won 2021-2023 did worse than yours afterwards. That's what a lucky winner looks like.

## Should the 60% be bigger or smaller? (15:50 candle, with, 10 in the money)

| Body at least | 2021-23 $/day | 2021-23 $/trade | 2024-26 $/day | 2024-26 $/trade |
|---|---|---|---|---|
| 40% | +7 | +11 | +35 | +52 |
| 50% | +9 | +17 | +36 | +64 |
| **60% (yours)** | **+30** | **+69** | **+30** | **+66** |
| 70% | +26 | +82 | +32 | +94 |
| 80% | +38 | +178 | +13 | +55 |
| 90% | +11 | +125 | +16 | +120 |

- **60% sits in a broad, safe middle.** It made about $30 a day in both periods. No threshold beat it in both.
- **Lower** (40-50%) was weak in 2021-23 and fine in 2024-26.
- **Higher** (80%+) was great in 2021-23 and weak in 2024-26.
- **A higher bar usually means more per trade but fewer trades.** Per day it is a wash.
- **There is no evidence for moving the number.** If anything, 60-70% looks like the stable zone.

## Other findings (descriptive, not tested)

- **The 15:50 candle is still the one.** In 2021-2023 the best candles were 15:50, then 15:48, then 15:45. Every
  version from 15:40-15:44 or 15:46-15:47 was weak or not eligible.
- **At the money is cheaper but weaker.** At 60% it made +$19 a day in 2021-23 and +$16 a day in 2024-26, and only
  about 37-41% of trades won. Each trade costs about $320 instead of about $1,090.
- **Late 2022 to 2023 was flat for everything at 15:50.** Your rule made -$4 a day from October 2022 to December
  2023. That matches the weak 2023 in the earlier study.
- **The forward days (after 2026-10-20)** were already known, so they are not fresh. All 7 signal days had very
  strong bodies (86-99%). The 4 with prices made +$303 a trade on your rule.

## What this means

**The rule does not change:**
- the 15:50 one-minute candle;
- body at least 60% of its range;
- with the candle;
- 10 points in the money;
- buy at 15:51 and hold to the close.

This is now the second honest search that failed to find anything clearly better. That does **not** prove 60% /
ITM10 is the best possible setting. It means the data can't tell the nearby settings apart, and chasing the best
past number would most likely pick a lucky one.

Nothing here is a trading recommendation.
