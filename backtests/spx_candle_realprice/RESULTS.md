# Real SPXW prices: tuning on 2013-2020, one confirmation on 2021-2026, model check

Pre-registration `preregistration/spx_candle_realprice.md` (SHA-256 `bc7f4f498aa2ea3d...`). Real Databento OPRA quotes: buy at the ask at the entry minute, settle at intrinsic on the official SPX close, $0.09 fee. Research only, not a trading recommendation.

Data: 2149 days with a same-day expiry and an official close, 1138 days with no expiry. Closes from cboe (362 days checked against Robinhood, largest difference 0.0000). Across all kept days and entry minutes: 2985 day-minutes with no implied spot, 2943 contract slots with no valid quote.

- Signal days left out (not priced), chosen: discovery 178 of 394 (no spot 177, no quote 1); confirmation 1 of 586 (no spot 0, no quote 1).
- Signal days left out (not priced), current: discovery 178 of 394 (no spot 177, no quote 1); confirmation 1 of 586 (no spot 0, no quote 1).
- Whole grid, discovery: median 106 signal days left out per cell, at most 252 (15:50 body>=0.40 with ITM15).

## Discovery 2013-04-01 .. 2020-12-31 (827 days, 2,178 cells, 2 eligible)

**Decision: no clear win over the current rule: confirm the current rule.**

- Best eligible cell: **15:42 body>=0.60 with ATM**, score +25.61 a day. The best score under 262 circular shifts (142 with no eligible cell, counted as the worst): median —, 95th percentile +21.92; p = 0.034. Luck-adjusted: — a day.
- Best minus current, per day: +40.17 (Newey-West t +1.56).
- Checks: differs from current True, p <= 0.05 True, beats current with t >= 2.0 False.
- Current rule (15:50 body>=0.60 with ITM10): -7.70 a day over 216 trades, halves -21.57 / -3.82, eligible False.

| Rank | Cell | Score $/day | Mean $/day | Trades | 2013-16 | 2017-20 |
|---|---|---|---|---|---|---|
| 1 | 15:42 body>=0.60 with ATM | +25.61 | +26.24 | 250 | +0.29 | +34.29 |
| 2 | 15:50 body>=0.40 with ATM | +4.62 | +5.34 | 302 | +0.02 | +6.77 |

Best eligible cell for each candle minute:

| Candle | Best cell | Score $/day |
|---|---|---|
| 15:40 | none eligible | — |
| 15:41 | none eligible | — |
| 15:42 | 15:42 body>=0.60 with ATM | +25.61 |
| 15:43 | none eligible | — |
| 15:44 | none eligible | — |
| 15:45 | none eligible | — |
| 15:46 | none eligible | — |
| 15:47 | none eligible | — |
| 15:48 | none eligible | — |
| 15:49 | none eligible | — |
| 15:50 | 15:50 body>=0.40 with ATM | +4.62 |

## Confirmation 2021-01-01 .. 2026-10-20 (1322 days): 15:50 body>=0.60 with ITM10

**CONFIRMED** (per-day mean > 0 with Newey-West t >= 2.0): +29.87 a day, t +2.40; 585 trades, +67.46 a trade, 54% won, worst -2,210.09.

The configuration tested is the current rule, so this result is about the current rule at real prices. It does not show that the current rule is the best setting.

| | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|
| chosen | 1321 | +29.87 | +2.40 | 585 | +67.46 | 54% | +44.91 | -2,210.09 |
| current | 1321 | +29.87 | +2.40 | 585 | +67.46 | 54% | +44.91 | -2,210.09 |
| chosen 2021-01-01..2022-12-31 | 376 | +48.21 | +2.01 | 157 | +115.46 | 57% | +65.91 | -1,361.09 |
| current 2021-01-01..2022-12-31 | 376 | +48.21 | +2.01 | 157 | +115.46 | 57% | +65.91 | -1,361.09 |
| chosen 2023-01-01..2026-10-20 | 945 | +22.58 | +1.56 | 428 | +49.85 | 53% | +35.91 | -2,210.09 |
| current 2023-01-01..2026-10-20 | 945 | +22.58 | +1.56 | 428 | +49.85 | 53% | +35.91 | -2,210.09 |

The current rule at every strike, real prices, 2021-2026 (descriptive; not a second test):

| Strike | Trades | $/trade | Won | Median | Worst | $/day | t |
|---|---|---|---|---|---|---|---|
| ITM20 | 586 | +77.15 | 54% | +51.91 | -2,670.09 | +34.20 | +2.61 |
| ITM15 | 584 | +71.00 | 55% | +52.41 | -2,330.09 | +31.41 | +2.43 |
| ITM10 | 585 | +67.46 | 54% | +44.91 | -2,210.09 | +29.87 | +2.40 |
| ITM5 | 585 | +53.90 | 50% | +2.91 | -1,900.09 | +23.87 | +2.07 |
| ATM | 583 | +39.50 | 39% | -110.09 | -1,640.09 | +17.46 | +1.87 |
| OTM5 | 585 | +12.18 | 19% | -65.09 | -1,390.09 | +5.40 | +0.78 |
| OTM10 | 581 | +1.04 | 11% | -25.09 | -1,180.09 | +0.46 | +0.10 |
| OTM15 | 566 | -6.96 | 5% | -15.09 | -1,000.09 | -3.02 | -1.03 |
| OTM20 | 529 | -10.02 | 3% | -10.09 | -840.09 | -4.19 | -2.34 |

## Fee and fill price (descriptive; decides nothing)

Every decision above used the ask and a $0.09 fee. The same trades with a $0.74 fee, and bought at the mid instead of the ask ($0.09 fee):

| Config | Period | Version | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|---|---|
| chosen (15:50 body>=0.60 with ITM10) | discovery | ask, $0.09 | 649 | -7.70 | -0.47 | 216 | -23.14 | 42% | -111.59 | -1,892.09 |
| chosen (15:50 body>=0.60 with ITM10) | discovery | ask, $0.74 | 649 | -7.92 | -0.48 | 216 | -23.79 | 42% | -112.24 | -1,892.74 |
| chosen (15:50 body>=0.60 with ITM10) | discovery | mid, $0.09 | 649 | +48.19 | +2.87 | 216 | +144.78 | 56% | +66.91 | -1,737.09 |
| chosen (15:50 body>=0.60 with ITM10) | confirmation | ask, $0.09 | 1321 | +29.87 | +2.40 | 585 | +67.46 | 54% | +44.91 | -2,210.09 |
| chosen (15:50 body>=0.60 with ITM10) | confirmation | ask, $0.74 | 1321 | +29.59 | +2.37 | 585 | +66.81 | 54% | +44.26 | -2,210.74 |
| chosen (15:50 body>=0.60 with ITM10) | confirmation | mid, $0.09 | 1321 | +46.90 | +3.71 | 585 | +105.90 | 56% | +85.91 | -2,155.09 |
| current (15:50 body>=0.60 with ITM10) | discovery | ask, $0.09 | 649 | -7.70 | -0.47 | 216 | -23.14 | 42% | -111.59 | -1,892.09 |
| current (15:50 body>=0.60 with ITM10) | discovery | ask, $0.74 | 649 | -7.92 | -0.48 | 216 | -23.79 | 42% | -112.24 | -1,892.74 |
| current (15:50 body>=0.60 with ITM10) | discovery | mid, $0.09 | 649 | +48.19 | +2.87 | 216 | +144.78 | 56% | +66.91 | -1,737.09 |
| current (15:50 body>=0.60 with ITM10) | confirmation | ask, $0.09 | 1321 | +29.87 | +2.40 | 585 | +67.46 | 54% | +44.91 | -2,210.09 |
| current (15:50 body>=0.60 with ITM10) | confirmation | ask, $0.74 | 1321 | +29.59 | +2.37 | 585 | +66.81 | 54% | +44.26 | -2,210.74 |
| current (15:50 body>=0.60 with ITM10) | confirmation | mid, $0.09 | 1321 | +46.90 | +3.71 | 585 | +105.90 | 56% | +85.91 | -2,155.09 |

## Model check: the strike ladder's model against real prices (644 strong-body trades, 2021-2026)

Official close minus the D1 15:59 close the model settled on, on the 586 days in the table: mean +0.03 points, mean size 1.33, 95th percentile of the size 3.58.

Ratios are mean / median over the trades.

| Strike | n | Model price | Real mid | Real ask | Mid / model | Ask / model | Model $/trade | Real $/trade | Real - model | t |
|---|---|---|---|---|---|---|---|---|---|---|
| ITM20 | 586 | 20.09 | 20.07 | 20.58 | 1.00 / 1.00 | 1.02 / 1.02 | +94.34 | +77.16 | -17.18 | -2.01 |
| ITM15 | 584 | 15.37 | 15.22 | 15.68 | 0.99 / 0.99 | 1.02 / 1.01 | +73.45 | +71.82 | -1.63 | -0.18 |
| ITM10 | 585 | 10.29 | 10.51 | 10.89 | 1.02 / 1.02 | 1.06 / 1.05 | +100.70 | +67.77 | -32.93 | -3.87 |
| ITM5 | 585 | 5.85 | 6.28 | 6.51 | 1.08 / 1.07 | 1.12 / 1.11 | +96.90 | +51.57 | -45.33 | -5.63 |
| ATM | 583 | 2.40 | 3.08 | 3.18 | 1.45 / 1.29 | 1.50 / 1.33 | +92.67 | +35.15 | -57.52 | -7.37 |
| OTM5 | 585 | 0.93 | 1.37 | 1.44 | 84.49 / 1.80 | 100.89 / 1.87 | +45.59 | +9.32 | -36.27 | -5.52 |
| OTM10 | 581 | 0.69 | 0.66 | 0.71 | 425,940,760.37 / 2.36 | 851,825,868.86 / 2.65 | -9.04 | +2.31 | +11.35 | +1.27 |
| OTM15 | 564 | 0.34 | 0.37 | 0.41 | 78,481,719,025,752,473,600.00 / 11.38 | 156,963,438,051,450,257,408.00 / 15.31 | -13.42 | -7.07 | +6.35 | +0.84 |
| OTM20 | 524 | 4.77 | 0.23 | 0.27 | 2,822,027,014,337,296,606,753,550,130,741,248.00 / 7.48 | 5,644,054,028,674,593,213,507,100,261,482,496.00 / 10.82 | -470.67 | -10.83 | +459.84 | +1.79 |

## Fill check: did trading happen near the ask? (trade bars, descriptive; decides nothing)

Trade bars from `data/spx_1549/databento/ohlcv-1m_1500-1601_k60`: 2149 day files and 1138 no-expiry markers when the run started. A bar covers the trades in the entry minute; "last" is the minute's last trade. Prices are per share (x100 per contract).

| Config | Period | Priced entries | With a bar file (days) | Traded in the entry minute | Low <= ask (of traded) | Last - mid, mean | Last - mid, median |
|---|---|---|---|---|---|---|---|
| chosen | discovery | 216 | 216 (216) | 122 (56%) | 95% | +0.58 | +0.57 |
| chosen | confirmation | 585 | 585 (585) | 580 (99%) | 95% | +0.16 | +0.25 |
| current | discovery | 216 | 216 (216) | 122 (56%) | 95% | +0.58 | +0.57 |
| current | confirmation | 585 | 585 (585) | 580 (99%) | 95% | +0.16 | +0.25 |

## Caveats

- The 2021-2026 index outcomes were already used to test the current rule; the confirmation is fresh for option prices and for any changed setting, not fully independent.
- Signals come from D1 (a CFD), entries from real quotes at the minute's open; a fill at the quoted ask ignores order size and fast minutes, and a real order may fill worse.
- Before 2016 SPXW had a same-day expiry only on Fridays (and some month-ends), then Monday, Wednesday and Friday, and daily from 2022. Days without one are not in the sample, so discovery has few days before 2016, and its days fall on different weekdays than 2022-2026.
- Nothing here is a trading recommendation.
