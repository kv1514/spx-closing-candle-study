# Intraday momentum and the 15:50 candle: plain-English summary

Hand-written on 2026-11-09 from the first `run` of `momentum.py`. Plan: `preregistration/spx_intraday_momentum.md`
(ledger 2026-11-09T09:04:38Z). Full tables: [RESULTS.md](RESULTS.md). Research only, not trading advice.

## The questions

Two well-known papers say the S&P 500's move earlier in the day predicts its last half hour:
- Gao, Han, Li and Zhou (2018): the first half hour, from the prior close to 10:00.
- Baltussen, Da, Lammers and Martens (2021): the whole day up to 15:30. They say the cause is option dealers
  hedging when they are "short gamma".

We asked three things:
- **A.** Does that show up in our 2013-2026 one-minute data?
- **B.** Does it make the 15:50 candle trade better? For example, by skipping the trade when the candle goes
  against the day's move.
- **C.** Is the effect, or the trade, stronger when dealers are short gamma?

Every rule was written and locked before any of these numbers were computed.

## A. The papers' effect does not show up in our data

| | Slope (×100) | t | Verdict |
|---|---|---|---|
| Day up to 15:30 predicting 15:30-16:00, 2013-2026 (the one pre-set test) | +1.6 | 1.02 | **did not replicate** (needed t ≥ 2.0) |
| The same, 2013-2020 | +2.9 | 1.16 | description |
| The same, 2021-2026 | -0.2 | -0.18 | description |
| The paper's own futures result, for scale | about +6.2 | about 5 | |

- **It faded.** It was mildly positive in 2013-2015 (t 1.8-2.1 in single years) and has been about zero since.
- **The first-half-hour version is weaker still**, at t 0.57.
- **High-volatility days are no different** (t 0.13).
- **Out of sample it predicts worse than guessing the average move** (R² -0.9%).
- **Trading it alone** (long or short the last half hour by the day's direction) averaged +0.6 basis points a
  day, t 1.24. That is not distinguishable from zero.

This does not say the papers are wrong. Their main samples are 1993-2013 and 1974-2020, on SPY and futures.
It says the effect is not visible on this data since 2013.

## B. No momentum filter improved the 15:50 trade, and filtering made it worse

Four filters were tested on 2013-2020. A filter needed a clear win (p ≤ 0.0125, both halves and the index
version positive) to be carried forward to 2021-2026. **None came close: all four lost money compared with
taking every trade (t -1.1 to -1.4), so none was carried forward**, and there was no confirmation test.

Why: the trades a filter skips were still profitable on average. ITM10, model prices, $0.09 fee:

| | All trades | Trades that agree with the day's move | Trades that go against it |
|---|---|---|---|
| 2013-2020, average per trade | +$133 (905 trades) | +$199 (490) | +$56 (415) |
| 2021-2026, average per trade | +$166 (644 trades) | +$217 (312) | +$118 (332) |

- **Agreeing trades did better per trade in both periods**, by about $100-$140.
- **Disagreeing trades still made money**, so skipping them lowers the total. Over 2021-2026, taking only the
  agreeing trades would have earned about $47 a day against $74 for taking all of them.
- **The 2021-2026 split is a description, not a test.** The rule had to win on 2013-2020 first, and it did not.
  Nothing can be adopted from it under this plan.
- **Adding momentum trades on days with no 15:50 signal** (reported, not testable) looked good on 2013-2020
  (t 2.5) and did nothing on 2021-2026 (t 0.09), like the older "day so far" signal.
- **A check passed:** the script reproduced the strike study's 2021-2026 numbers exactly (644 trades, +$166.08,
  and +$157.91 in the realized-move version).
- **New number:** under the same model, the 15:50 trade at ITM10 also made +$133 a trade in 2013-2020 (t 3.2 on
  the daily series). Two cautions: that period was used to choose the 15:50 signal, and the model's prices are
  calibrated on 2026 quotes.

## C. Dealer gamma: neither test passed

Run on 2026-11-09 with every day's open interest for all SPX and SPXW options (3,287 of 3,287 days, from
Databento; $34.55 of the free credit, $84.29 in all of the $100 cap). A day counts as **short gamma** when the
proxy, which assumes dealers are long every call and short every put, is below zero. That was 30% of days
(75% in 2022).

- **C1, does momentum get stronger on short-gamma days? No.** The interaction was +0.022 (t 0.95, p 0.34).
  The papers' claim did not show up here either.
- **C2, does the 15:50 trade do better on short-gamma days? Not by the bar.**
  - Under the model prices it made **+$262 a trade on short-gamma days and +$93 on the others** (495 and
    1,054 trades). The difference, +$169, had p 0.029; the bar was 0.025 (two tests, so 5% split in two).
  - It was mostly 2013-2020 (+$240, t 1.83). On 2021-2026 it was +$84 (t 0.96).
- **At real asks the gap is gone** (descriptive, not in the plan; Databento asks, 2021-2026): +$58 a trade on
  short-gamma days (232 trades) and +$74 on the others (353), t −0.25. It flips from year to year: short-gamma
  days were better in 2021, 2022, 2024 and 2025 and worse in 2023 and 2026.
- **Descriptive only:** a puts-only version of the papers' Table 8 form showed momentum stronger when put
  gamma is large (t −3.16). It was not a planned test and was one of several descriptive forms; the planned
  full-proxy version was t −1.63.
- **Caveats:** the dealer positioning is assumed, not observed; open interest misses 0DTE positions opened
  and closed the same day, which is most 0DTE trading since 2022; one VIX volatility ignores skew.

**So:** don't use dealer gamma to skip or add 15:50 trades. The one promising number came from model prices,
missed the bar, faded after 2020 and disappeared at real asks.

## What this means for the 15:50 rule

Nothing changes. Momentum is not a reason to skip a 15:50 trade, and it is not a separate signal worth adding,
on this data. The candle rule stands on its own. The real-price study (`backtests/spx_candle_realprice/`)
decides whether its exact settings should change.
