# Closing-imbalance test: results of the registered run

Plan: `preregistration/spx_candle_imbalance.md` (SHA-256 `c5c5131c31dd4865d1e132723c219eb12406a0cb20782c28b63a9014747d913c`). Run 2026-11-10T21:09:41Z.

## Primary (H1)

- Agreeing days: 469, hit rate 55.9%; disagreeing days: 175, hit rate 61.7%.
- d = -5.9 points, se 4.3, t = -1.35.
- **H1 NOT PASSED** (bar: d > 0 and t >= 2.0).
- Block bootstrap of d (20-day blocks, 10000 of 10000 draws kept): -14.8 to 4.0 points.

## Secondary (decide nothing)

- H2 agreement: 469 of 644 classified days (72.8%), one-sided p = 3.137e-32.
- H3 imbalance direction alone right: 329 of 644 (51.1%), one-sided p = 0.3042.
- Holm: H2 rejects 1/2, H3 does not reject 1/2.

## Robustness (reported only)

- Last record before 15:51: 55.6% vs 62.2% (n 459 / 185), d -6.6 points, t -1.55.
- NYSE stocks only: 56.2% vs 59.2% (n 372 / 272), d -3.0 points, t -0.76.
- Nasdaq stocks only: 57.3% vs 57.9% (n 499 / 145), d -0.6 points, t -0.13.
- Signed move to the close: agree 2.41, disagree 2.24 bps (n 469 / 175), difference 0.16, Welch t 0.13.
- Option P&L at the ask (ITM10, $0.09 fee): agree 80.43, disagree 33.58 $ per trade (n 423 / 162), difference 46.85, Welch t 0.79.
- Year-and-direction adjusted d: -6.4 points (12 cells).

## Descriptive

- Day status: {'classified': 644}; signal days without an eligible outcome: 0.
- Usable stocks per day: median 50, minimum 50. Stock-days by status of the first record: {'usable': 32200}.

| Year | Signal days | Agree n | Agree hit (95% CI) | Disagree n | Disagree hit (95% CI) | Unclassified n | Unclassified hit (95% CI) |
|---|---|---|---|---|---|---|---|
| 2021 | 111 | 92 | 62.0% (52-71) | 19 | 78.9% (57-91) | 0 | n/a |
| 2022 | 105 | 76 | 57.9% (47-68) | 29 | 69.0% (51-83) | 0 | n/a |
| 2023 | 113 | 73 | 53.4% (42-64) | 40 | 55.0% (40-69) | 0 | n/a |
| 2024 | 106 | 69 | 59.4% (48-70) | 37 | 43.2% (29-59) | 0 | n/a |
| 2025 | 117 | 91 | 53.8% (44-64) | 26 | 69.2% (50-83) | 0 | n/a |
| 2026 | 92 | 68 | 47.1% (36-59) | 24 | 70.8% (51-85) | 0 | n/a |

Classified signal days by year, whatever the outcome (the table above counts only days with an eligible outcome):

| Year | Signal days | Classified, agree | Classified, disagree | Status counts |
|---|---|---|---|---|
| 2021 | 111 | 92 | 19 | {'classified': 111} |
| 2022 | 105 | 76 | 29 | {'classified': 105} |
| 2023 | 113 | 73 | 40 | {'classified': 113} |
| 2024 | 106 | 69 | 37 | {'classified': 106} |
| 2025 | 117 | 91 | 26 | {'classified': 117} |
| 2026 | 92 | 68 | 24 | {'classified': 92} |

All closing-imbalance records of list stocks with ts_recv in the 15:50 minute, by status (every record, not only the first per stock): {'XNYS.PILLAR': {'usable': 541781}, 'XNAS.ITCH': {'usable': 75788}}.
Stocks with at least one closing record in the 15:50 minute (stock-days): {'XNYS.PILLAR': {'closing_record_in_15_50_minute': 19569}, 'XNAS.ITCH': {'closing_record_in_15_50_minute': 12631}}.

Research only; not investment advice.
