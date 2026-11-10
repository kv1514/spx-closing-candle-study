# Limit-order fill simulation for the 15:50 rule (descriptive; decides nothing)

Current rule (15:50 candle, body >= 0.60, with the candle, ITM10), entries priced by the real-price study. Policies are defined in `fills.py`'s header; all are reported and none is selected. $ are per contract, $0.09 fee. An unfilled order counts as $0 (no trade, no fee).

**These are trade-low proxy scenarios, not execution estimates.** A limit counts as filled if a trade printed below it (or at it, for the touch version) in a minute it was working, or if the quote snapshot at that minute's end offered at or below it. Prints cannot show whether a resting simple order would have executed (spread legs print away from the quote), intraminute quote moves between snapshots are not seen, and orders are assumed to arrive and execute with zero latency.

Rows simulated: 801 priced signal days. Left out by this script: {'no_bar_file': 0, 'no_quote_file': 0, 'ask_mismatch': 0}. Left out upstream, because the real-price study could not price them (unknown outcomes, not $0): discovery 178 of 394 (no spot 177, no quote 1); confirmation 1 of 586 (no spot 0, no quote 1). P0 reproduces the study (an algebraic consistency check): {'confirmation': {'n': 585, 'mean': 67.46, 'ok': True}, 'discovery': {'n': 216, 'mean': -23.14, 'ok': True}}.

## discovery 2013-2020 (216 priced signal days)

| Policy | Filled | $/priced signal day | t | $/fill | minus P0, $/priced signal day | t |
|---|---|---|---|---|---|---|
| P0_ask_now | 216 (100%) | -23.14 | -0.50 | -23.14 | — | — |
| P1_mid_1m_skip | 69 (32%) | +58.72 | +1.47 | +183.82 | +81.86 | +3.09 |
| P1t_mid_1m_skip_touch | 72 (33%) | +62.37 | +1.56 | +187.12 | +85.51 | +3.24 |
| P2_mid_1m_then_ask | 216 (100%) | -26.98 | -0.55 | -26.98 | -3.84 | -0.32 |
| P3_mid_3m_skip | 121 (56%) | +78.66 | +1.79 | +140.41 | +101.79 | +5.25 |
| P4_half_1m_then_ask | 216 (100%) | -19.71 | -0.41 | -19.71 | +3.43 | +0.37 |

Adverse selection: the same entries' P&L at the ask, split by whether P1's mid limit filled:

| P1 | Days | $/trade at the ask | t | Won at the ask |
|---|---|---|---|---|
| filled | 69 | +44.11 | +0.37 | 46% |
| unfilled | 147 | -54.70 | -1.42 | 40% |

Late entry: the same contract bought at a later minute's ask (216 days with a quote at every one of these minutes):

| Buy at | $/trade | t |
|---|---|---|
| 15:51 | -23.14 | -0.50 |
| 15:52 | -68.04 | -1.49 |
| 15:53 | -58.09 | -1.26 |
| 15:55 | -128.97 | -3.45 |

## confirmation 2021-2026 (585 priced signal days)

| Policy | Filled | $/priced signal day | t | $/fill | minus P0, $/priced signal day | t |
|---|---|---|---|---|---|---|
| P0_ask_now | 585 (100%) | +67.46 | +2.29 | +67.46 | — | — |
| P1_mid_1m_skip | 489 (84%) | +64.57 | +2.37 | +77.24 | -2.89 | -0.24 |
| P1t_mid_1m_skip_touch | 501 (86%) | +61.04 | +2.23 | +71.28 | -6.42 | -0.56 |
| P2_mid_1m_then_ask | 585 (100%) | +69.63 | +2.38 | +69.63 | +2.17 | +0.55 |
| P3_mid_3m_skip | 534 (91%) | +64.89 | +2.31 | +71.09 | -2.57 | -0.26 |
| P4_half_1m_then_ask | 585 (100%) | +62.23 | +2.13 | +62.23 | -5.23 | -1.63 |

Adverse selection: the same entries' P&L at the ask, split by whether P1's mid limit filled:

| P1 | Days | $/trade at the ask | t | Won at the ask |
|---|---|---|---|---|
| filled | 489 | +42.52 | +1.31 | 52% |
| unfilled | 96 | +194.49 | +2.80 | 61% |

Late entry: the same contract bought at a later minute's ask (585 days with a quote at every one of these minutes):

| Buy at | $/trade | t |
|---|---|---|
| 15:51 | +67.46 | +2.29 |
| 15:52 | +55.75 | +2.02 |
| 15:53 | +57.89 | +2.16 |
| 15:55 | +23.01 | +1.11 |

## 2021-2022 (157 priced signal days)

| Policy | Filled | $/priced signal day | t | $/fill | minus P0, $/priced signal day | t |
|---|---|---|---|---|---|---|
| P0_ask_now | 157 (100%) | +115.46 | +2.08 | +115.46 | — | — |
| P1_mid_1m_skip | 122 (78%) | +93.15 | +1.84 | +119.88 | -22.31 | -0.84 |
| P1t_mid_1m_skip_touch | 122 (78%) | +93.15 | +1.84 | +119.88 | -22.31 | -0.84 |
| P2_mid_1m_then_ask | 157 (100%) | +128.52 | +2.33 | +128.52 | +13.06 | +1.20 |
| P3_mid_3m_skip | 140 (89%) | +121.91 | +2.27 | +136.71 | +6.44 | +0.32 |
| P4_half_1m_then_ask | 157 (100%) | +113.11 | +2.04 | +113.11 | -2.36 | -0.27 |

Adverse selection: the same entries' P&L at the ask, split by whether P1's mid limit filled:

| P1 | Days | $/trade at the ask | t | Won at the ask |
|---|---|---|---|---|
| filled | 122 | +52.42 | +0.82 | 53% |
| unfilled | 35 | +335.22 | +3.28 | 69% |

Late entry: the same contract bought at a later minute's ask (157 days with a quote at every one of these minutes):

| Buy at | $/trade | t |
|---|---|---|
| 15:51 | +115.46 | +2.08 |
| 15:52 | +111.07 | +2.05 |
| 15:53 | +128.30 | +2.41 |
| 15:55 | +51.10 | +1.30 |

## 2023-2026 (428 priced signal days)

| Policy | Filled | $/priced signal day | t | $/fill | minus P0, $/priced signal day | t |
|---|---|---|---|---|---|---|
| P0_ask_now | 428 (100%) | +49.85 | +1.44 | +49.85 | — | — |
| P1_mid_1m_skip | 367 (86%) | +54.08 | +1.68 | +63.07 | +4.23 | +0.32 |
| P1t_mid_1m_skip_touch | 379 (89%) | +49.26 | +1.51 | +55.63 | -0.59 | -0.05 |
| P2_mid_1m_then_ask | 428 (100%) | +48.03 | +1.39 | +48.03 | -1.82 | -0.50 |
| P3_mid_3m_skip | 394 (92%) | +43.98 | +1.33 | +47.77 | -5.87 | -0.52 |
| P4_half_1m_then_ask | 428 (100%) | +43.56 | +1.27 | +43.56 | -6.29 | -2.08 |

Adverse selection: the same entries' P&L at the ask, split by whether P1's mid limit filled:

| P1 | Days | $/trade at the ask | t | Won at the ask |
|---|---|---|---|---|
| filled | 367 | +39.23 | +1.04 | 52% |
| unfilled | 61 | +113.75 | +1.25 | 57% |

Late entry: the same contract bought at a later minute's ask (428 days with a quote at every one of these minutes):

| Buy at | $/trade | t |
|---|---|---|
| 15:51 | +49.85 | +1.44 |
| 15:52 | +35.46 | +1.11 |
| 15:53 | +32.06 | +1.04 |
| 15:55 | +12.71 | +0.52 |

## Caveats

- Trade bars include every print; complex-order legs can print away from the quote, so a trade below the limit is evidence of a fill, not proof. Strict trade-through (P1) is not a conservative execution estimate; touch (P1t) only adds fill frequency, and its extra fills are not cheaper winners.
- Quotes are minute snapshots: an offer that dipped to the limit and recovered inside a minute is missed.
- Zero latency: an order reacting to the 15:50 candle is assumed live at 15:51:00, and the 15:52 chase is assumed to execute at the 15:52:00 ask.
- Queue position, order size and the exact second are unknown; one contract is assumed.
- 2021-2026 already confirmed the rule; these policies are described on it, not tested or chosen.
- t-statistics treat signal days as independent.
- Nothing here is a trading recommendation.
