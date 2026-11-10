# Re-tuning the 15:50 rule on 2021-2023 real prices, one test on 2024-2026

Pre-registration `preregistration/spx_candle_refine.md` (SHA-256 `7b99ae6cca0f853d...`). Real Databento OPRA quotes: buy at the ask at the entry minute's open, settle at intrinsic on the official SPX close, $0.09 fee; every decision uses this. Research only; nothing here is a trading recommendation.

**Not fresh.** The 2021-2026 index outcomes were used before: for the scan candidates, the P1/P3 known effects, the weak-body audit and the intraday-momentum study. 2024-2026 is not fresh for the current rule's family (15:50, 0.60, with, any strike): its real-price results there were already computed and seen.

Runs started (attempt records in runs/): tune 1, test 1. A run is counted once it passes its start checks, before it reads any outcome-bearing input, so a run that later crashed or stopped counts too.

## Part 1: tuning, 2021-01-01 .. 2023-12-31

**Decision: No candidate advanced under the prespecified rules. Failed gate(s): luck diagnostic p <= 0.05. The current rule stays.**

Data: 625 kept days (H1 315, H2 310) with a quote file and an official close, of 749 D1 days; 124 with no same-day expiry, 0 with no official close. Official closes checked against Robinhood (robinhood_spx_daily_2021_2023.json) on 63 overlapping tuning days, largest difference 0.0000. 15:50/0.60/with equals scan.py's F2 on every kept day. Across all kept days and entry minutes: 2 day-minutes with no implied spot, 260 contract slots with no valid quote.

- Pick: **15:50 body>=0.80 with ITM20**, score +32.02 a day; mean +39.70 a day over 133 trades (coverage 100%); H1 +75.61, H2 +3.21.
- Luck diagnostic: best eligible score under 195 circular shifts (0 with nothing eligible, counted as −∞): median +23.99, 95th percentile +42.98; p = 0.209. It asks whether the best score beats the best score from signals unrelated to the days; it is not an exact test, does not test superiority over the current rule and does not pay for earlier studies.
- Paired difference, pick − current, on tuning: +10.00 a day (Newey-West t +0.89, descriptive; no t-bar on tuning), paired n 624, 1 day(s) dropped (a series missing).

| Gate | Holds |
|---|---|
| the pick is not in the current rule's family (15:50, 0.60, with, any strike) | yes |
| luck diagnostic p <= 0.05 | NO |
| on tuning, the paired per-day difference (pick - current) has a mean above 0 | yes |

| | Days | $/day | t | Signal days | Trades | Coverage | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|---|---|
| pick (15:50 body>=0.80 with ITM20) tuning | 625 | +39.70 | +2.94 | 133 | 133 | 100% | +186.55 | 62% | +135.91 | -1,687.09 |
| pick (15:50 body>=0.80 with ITM20) H1 | 315 | +75.61 | +3.60 | 70 | 70 | 100% | +340.22 | 66% | +228.41 | -1,687.09 |
| pick (15:50 body>=0.80 with ITM20) H2 | 310 | +3.21 | +0.21 | 63 | 63 | 100% | +15.80 | 59% | +71.91 | -1,433.09 |
| current (15:50 body>=0.60 with ITM10) tuning | 624 | +29.76 | +1.78 | 271 | 270 | 100% | +68.78 | 55% | +49.91 | -1,361.09 |
| current (15:50 body>=0.60 with ITM10) H1 | 314 | +63.52 | +2.31 | 134 | 133 | 99% | +149.97 | 56% | +65.91 | -1,361.09 |
| current (15:50 body>=0.60 with ITM10) H2 | 310 | -4.43 | -0.25 | 137 | 137 | 100% | -10.03 | 54% | +28.91 | -1,340.09 |

### Part 3, tuning (descriptive; decides nothing)

119 of 2,178 cells eligible. The 15 best eligible cells:

| Rank | Cell | Score $/day | Mean $/day | Trades | H1 $/day (trades) | H2 $/day (trades) | Coverage all / H1 / H2 |
|---|---|---|---|---|---|---|---|
| 1 | 15:50 body>=0.80 with ITM20 | +32.02 | +39.70 | 133 | +75.61 (70) | +3.21 (63) | 100% / 100% / 100% |
| 2 | 15:50 body>=0.80 with ITM10 | +30.60 | +37.84 | 133 | +72.26 (70) | +2.87 (63) | 100% / 100% / 100% |
| 3 | 15:50 body>=0.80 with ITM15 | +29.83 | +37.11 | 132 | +71.12 (69) | +2.66 (63) | 99% / 99% / 100% |
| 4 | 15:50 body>=0.80 with ITM5 | +29.50 | +35.97 | 132 | +65.14 (69) | +6.43 (63) | 99% / 99% / 100% |
| 5 | 15:48 body>=0.40 with ITM5 | +28.34 | +27.65 | 386 | +30.37 (191) | +24.91 (195) | 99% / 99% / 100% |
| 6 | 15:48 body>=0.40 with ATM | +22.62 | +21.86 | 388 | +31.01 (193) | +12.56 (195) | 100% / 100% / 100% |
| 7 | 15:50 body>=0.60 with ITM5 | +22.25 | +26.76 | 270 | +52.90 (133) | +0.29 (137) | 100% / 99% / 100% |
| 8 | 15:48 body>=0.45 with ITM5 | +21.69 | +29.02 | 349 | +43.66 (174) | +14.24 (175) | 99% / 99% / 100% |
| 9 | 15:50 body>=0.80 with ATM | +21.36 | +25.41 | 133 | +46.25 (70) | +4.23 (63) | 100% / 100% / 100% |
| 10 | 15:48 body>=0.45 with ATM | +17.17 | +23.38 | 351 | +41.11 (176) | +5.35 (175) | 100% / 100% / 100% |
| 11 | 15:48 body>=0.40 with ITM10 | +17.08 | +16.14 | 387 | +2.95 (192) | +29.51 (195) | 100% / 99% / 100% |
| 12 | 15:45 body>=0.65 with ITM5 | +17.05 | +15.50 | 215 | +16.03 (104) | +14.96 (111) | 100% / 100% / 100% |
| 13 | 15:45 body>=0.70 with ITM20 | +16.93 | +20.66 | 179 | +20.02 (83) | +21.31 (96) | 100% / 100% / 100% |
| 14 | 15:45 body>=0.70 with ITM5 | +16.93 | +18.90 | 179 | +18.95 (83) | +18.85 (96) | 100% / 100% / 100% |
| 15 | 15:45 body>=0.70 with ITM15 | +16.48 | +19.65 | 179 | +18.91 (83) | +20.40 (96) | 100% / 100% / 100% |

Best eligible cell for each candle minute:

| Candle | Best cell | Score $/day | Trades |
|---|---|---|---|
| 15:40 | none eligible | — | — |
| 15:41 | 15:41 body>=0.65 with OTM15 | +3.98 | 221 |
| 15:42 | 15:42 body>=0.40 against OTM10 | +5.69 | 409 |
| 15:43 | none eligible | — | — |
| 15:44 | 15:44 body>=0.40 with OTM10 | +7.31 | 393 |
| 15:45 | 15:45 body>=0.65 with ITM5 | +17.05 | 215 |
| 15:46 | none eligible | — | — |
| 15:47 | 15:47 body>=0.75 with OTM5 | +3.53 | 114 |
| 15:48 | 15:48 body>=0.40 with ITM5 | +28.34 | 386 |
| 15:49 | 15:49 body>=0.40 with ATM | +4.30 | 380 |
| 15:50 | 15:50 body>=0.80 with ITM20 | +32.02 | 133 |

Not-priced signal days per cell on tuning: median 0, at most 3 (15:46 body>=0.40 with OTM20). By reason and half:

| Config | Period | Signal days | Priced | No spot | No quote |
|---|---|---|---|---|---|
| pick (15:50 body>=0.80 with ITM20) | tuning | 133 | 133 | 0 | 0 |
| pick (15:50 body>=0.80 with ITM20) | H1 | 70 | 70 | 0 | 0 |
| pick (15:50 body>=0.80 with ITM20) | H2 | 63 | 63 | 0 | 0 |
| current (15:50 body>=0.60 with ITM10) | tuning | 271 | 270 | 0 | 1 |
| current (15:50 body>=0.60 with ITM10) | H1 | 134 | 133 | 0 | 1 |
| current (15:50 body>=0.60 with ITM10) | H2 | 137 | 137 | 0 | 0 |

Threshold profile on tuning (15:50, with):

| Strike | θ | Signal days | Trades | Coverage | $/day | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|---|
| ITM10 | 0.40 | 408 | 407 | 100% | +7.23 | +11.09 | 53% | +24.91 | -1,580.09 |
| ITM10 | 0.45 | 377 | 376 | 100% | +12.60 | +20.92 | 53% | +28.91 | -1,361.09 |
| ITM10 | 0.50 | 342 | 341 | 100% | +9.08 | +16.61 | 52% | +16.91 | -1,361.09 |
| ITM10 | 0.55 | 304 | 303 | 100% | +15.60 | +32.12 | 53% | +24.91 | -1,361.09 |
| ITM10 | 0.60 (current) | 271 | 270 | 100% | +29.76 | +68.78 | 55% | +49.91 | -1,361.09 |
| ITM10 | 0.65 | 227 | 227 | 100% | +26.38 | +72.62 | 55% | +41.91 | -1,361.09 |
| ITM10 | 0.70 | 197 | 197 | 100% | +25.90 | +82.16 | 57% | +52.91 | -1,340.09 |
| ITM10 | 0.75 | 173 | 173 | 100% | +28.43 | +102.72 | 58% | +70.91 | -1,340.09 |
| ITM10 | 0.80 | 133 | 133 | 100% | +37.84 | +177.82 | 62% | +119.91 | -1,340.09 |
| ITM10 | 0.85 | 89 | 89 | 100% | +25.51 | +179.17 | 63% | +109.91 | -1,290.09 |
| ITM10 | 0.90 | 56 | 56 | 100% | +11.19 | +124.89 | 62% | +118.91 | -1,290.09 |
| ATM | 0.40 | 408 | 406 | 100% | +3.47 | +5.32 | 37% | -105.09 | -990.09 |
| ATM | 0.45 | 377 | 375 | 99% | +3.95 | +6.56 | 38% | -105.09 | -770.09 |
| ATM | 0.50 | 342 | 340 | 99% | +3.53 | +6.47 | 37% | -105.59 | -720.09 |
| ATM | 0.55 | 304 | 302 | 99% | +11.15 | +23.01 | 39% | -92.59 | -720.09 |
| ATM | 0.60 (current) | 271 | 269 | 99% | +19.26 | +44.60 | 41% | -83.09 | -720.09 |
| ATM | 0.65 | 227 | 226 | 100% | +18.73 | +51.71 | 40% | -86.09 | -720.09 |
| ATM | 0.70 | 197 | 196 | 99% | +19.83 | +63.12 | 41% | -81.09 | -670.09 |
| ATM | 0.75 | 173 | 172 | 99% | +21.82 | +79.15 | 42% | -72.09 | -670.09 |
| ATM | 0.80 | 133 | 133 | 100% | +25.41 | +119.41 | 46% | -59.09 | -630.09 |
| ATM | 0.85 | 89 | 89 | 100% | +16.86 | +118.40 | 43% | -83.09 | -520.09 |
| ATM | 0.90 | 56 | 56 | 100% | +6.70 | +74.75 | 43% | -62.09 | -520.09 |

## Part 2: the test, 2024-01-01 .. 2026-10-20 (once)

**Part 2 was not run. No candidate advanced under the prespecified rules. Failed gate(s): luck diagnostic p <= 0.05. The current rule stays.**

This does not show that the current rule is the best setting.

Data: 697 kept test days of 697 D1 days; 0 with no same-day expiry, 0 with no official close. Official closes checked against Robinhood on 349 days (largest difference 0.0000). 15:50/0.60/with equals scan.py's F2 on every kept day.

## Part 3, test period (descriptive; computed after the decision was written)

The current rule's numbers on 2024-2026 were already known before this study.

| Config | Period | Version | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|---|---|
| pick (15:50 body>=0.80 with ITM20) | 2024-01-01..2026-10-20 | ask, $0.09 | 697 | +18.88 | +1.30 | 167 | +78.80 | 51% | +10.91 | -2,670.09 |
| pick (15:50 body>=0.80 with ITM20) | 2024-01-01..2026-10-20 | ask, $0.74 | 697 | +18.73 | +1.29 | 167 | +78.15 | 51% | +10.26 | -2,670.74 |
| pick (15:50 body>=0.80 with ITM20) | 2024-01-01..2026-10-20 | mid, $0.09 | 697 | +27.39 | +1.86 | 167 | +114.31 | 53% | +45.91 | -2,585.09 |
| pick (15:50 body>=0.80 with ITM20) | 2024 | ask, $0.09 | 249 | +26.53 | +1.07 | 60 | +110.09 | 52% | +28.41 | -1,262.09 |
| pick (15:50 body>=0.80 with ITM20) | 2024 | ask, $0.74 | 249 | +26.37 | +1.06 | 60 | +109.44 | 52% | +27.76 | -1,262.74 |
| pick (15:50 body>=0.80 with ITM20) | 2024 | mid, $0.09 | 249 | +36.09 | +1.44 | 60 | +149.76 | 55% | +78.41 | -1,222.09 |
| pick (15:50 body>=0.80 with ITM20) | 2025 | ask, $0.09 | 247 | +18.03 | +0.75 | 61 | +73.01 | 54% | +67.91 | -2,670.09 |
| pick (15:50 body>=0.80 with ITM20) | 2025 | ask, $0.74 | 247 | +17.87 | +0.74 | 61 | +72.36 | 54% | +67.26 | -2,670.74 |
| pick (15:50 body>=0.80 with ITM20) | 2025 | mid, $0.09 | 247 | +26.76 | +1.09 | 61 | +108.34 | 56% | +92.91 | -2,585.09 |
| pick (15:50 body>=0.80 with ITM20) | 2026 | ask, $0.09 | 201 | +10.45 | +0.39 | 46 | +45.67 | 46% | -94.59 | -1,615.09 |
| pick (15:50 body>=0.80 with ITM20) | 2026 | ask, $0.74 | 201 | +10.30 | +0.38 | 46 | +45.02 | 46% | -95.24 | -1,615.74 |
| pick (15:50 body>=0.80 with ITM20) | 2026 | mid, $0.09 | 201 | +17.39 | +0.65 | 46 | +76.00 | 48% | -72.09 | -1,590.09 |
| current (15:50 body>=0.60 with ITM10) | 2024-01-01..2026-10-20 | ask, $0.09 | 697 | +29.97 | +1.64 | 315 | +66.32 | 53% | +39.91 | -2,210.09 |
| current (15:50 body>=0.60 with ITM10) | 2024-01-01..2026-10-20 | ask, $0.74 | 697 | +29.68 | +1.63 | 315 | +65.67 | 53% | +39.26 | -2,210.74 |
| current (15:50 body>=0.60 with ITM10) | 2024-01-01..2026-10-20 | mid, $0.09 | 697 | +41.42 | +2.27 | 315 | +91.64 | 53% | +64.91 | -2,155.09 |
| current (15:50 body>=0.60 with ITM10) | 2024 | ask, $0.09 | 249 | +8.68 | +0.33 | 106 | +20.39 | 50% | -11.09 | -1,170.09 |
| current (15:50 body>=0.60 with ITM10) | 2024 | ask, $0.74 | 249 | +8.40 | +0.32 | 106 | +19.74 | 50% | -11.74 | -1,170.74 |
| current (15:50 body>=0.60 with ITM10) | 2024 | mid, $0.09 | 249 | +21.61 | +0.83 | 106 | +50.77 | 51% | +13.91 | -1,140.09 |
| current (15:50 body>=0.60 with ITM10) | 2025 | ask, $0.09 | 247 | +30.68 | +0.93 | 117 | +64.76 | 56% | +67.91 | -2,210.09 |
| current (15:50 body>=0.60 with ITM10) | 2025 | ask, $0.74 | 247 | +30.37 | +0.92 | 117 | +64.11 | 56% | +67.26 | -2,210.74 |
| current (15:50 body>=0.60 with ITM10) | 2025 | mid, $0.09 | 247 | +42.60 | +1.29 | 117 | +89.94 | 56% | +84.91 | -2,155.09 |
| current (15:50 body>=0.60 with ITM10) | 2026 | ask, $0.09 | 201 | +55.49 | +1.54 | 92 | +121.23 | 51% | +20.91 | -1,280.09 |
| current (15:50 body>=0.60 with ITM10) | 2026 | ask, $0.74 | 201 | +55.19 | +1.54 | 92 | +120.58 | 51% | +20.26 | -1,280.74 |
| current (15:50 body>=0.60 with ITM10) | 2026 | mid, $0.09 | 201 | +64.49 | +1.79 | 92 | +140.90 | 51% | +35.91 | -1,265.09 |

Not priced on the test period, by reason:

| Config | Period | Signal days | Priced | No spot | No quote |
|---|---|---|---|---|---|
| pick (15:50 body>=0.80 with ITM20) | 2024-01-01..2026-10-20 | 167 | 167 | 0 | 0 |
| pick (15:50 body>=0.80 with ITM20) | 2024 | 60 | 60 | 0 | 0 |
| pick (15:50 body>=0.80 with ITM20) | 2025 | 61 | 61 | 0 | 0 |
| pick (15:50 body>=0.80 with ITM20) | 2026 | 46 | 46 | 0 | 0 |
| current (15:50 body>=0.60 with ITM10) | 2024-01-01..2026-10-20 | 315 | 315 | 0 | 0 |
| current (15:50 body>=0.60 with ITM10) | 2024 | 106 | 106 | 0 | 0 |
| current (15:50 body>=0.60 with ITM10) | 2025 | 117 | 117 | 0 | 0 |
| current (15:50 body>=0.60 with ITM10) | 2026 | 92 | 92 | 0 | 0 |

Threshold profile on 2024-2026 (15:50, with), **looked at after the decision**:

| Strike | θ | Signal days | Trades | Coverage | $/day | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|---|
| ITM10 | 0.40 | 468 | 468 | 100% | +34.63 | +51.57 | 51% | +28.91 | -2,210.09 |
| ITM10 | 0.45 | 437 | 437 | 100% | +33.24 | +53.02 | 51% | +30.91 | -2,210.09 |
| ITM10 | 0.50 | 393 | 393 | 100% | +35.99 | +63.82 | 52% | +39.91 | -2,210.09 |
| ITM10 | 0.55 | 353 | 353 | 100% | +30.04 | +59.32 | 52% | +38.91 | -2,210.09 |
| ITM10 | 0.60 (current) | 315 | 315 | 100% | +29.97 | +66.32 | 53% | +39.91 | -2,210.09 |
| ITM10 | 0.65 | 281 | 281 | 100% | +26.27 | +65.15 | 53% | +44.91 | -2,210.09 |
| ITM10 | 0.70 | 238 | 238 | 100% | +32.16 | +94.20 | 55% | +62.91 | -2,210.09 |
| ITM10 | 0.75 | 207 | 207 | 100% | +24.56 | +82.71 | 53% | +39.91 | -2,210.09 |
| ITM10 | 0.80 | 167 | 167 | 100% | +13.26 | +55.33 | 50% | +10.91 | -2,210.09 |
| ITM10 | 0.85 | 130 | 130 | 100% | +8.35 | +44.77 | 48% | -42.09 | -2,210.09 |
| ITM10 | 0.90 | 95 | 95 | 100% | +16.36 | +120.02 | 55% | +64.91 | -2,210.09 |
| ATM | 0.40 | 468 | 467 | 100% | +19.77 | +29.46 | 38% | -135.09 | -1,640.09 |
| ATM | 0.45 | 437 | 436 | 100% | +19.29 | +30.79 | 38% | -132.59 | -1,640.09 |
| ATM | 0.50 | 393 | 392 | 100% | +20.52 | +36.44 | 38% | -135.09 | -1,640.09 |
| ATM | 0.55 | 353 | 352 | 100% | +17.57 | +34.74 | 37% | -140.09 | -1,640.09 |
| ATM | 0.60 (current) | 315 | 314 | 100% | +15.85 | +35.13 | 37% | -145.09 | -1,640.09 |
| ATM | 0.65 | 281 | 280 | 100% | +11.36 | +28.25 | 36% | -145.09 | -1,640.09 |
| ATM | 0.70 | 238 | 237 | 100% | +18.22 | +53.50 | 40% | -130.09 | -1,640.09 |
| ATM | 0.75 | 207 | 206 | 100% | +16.57 | +55.97 | 39% | -137.59 | -1,640.09 |
| ATM | 0.80 | 167 | 167 | 100% | +10.14 | +42.32 | 38% | -150.09 | -1,640.09 |
| ATM | 0.85 | 130 | 130 | 100% | +3.93 | +21.05 | 38% | -167.59 | -1,640.09 |
| ATM | 0.90 | 95 | 95 | 100% | +7.91 | +58.04 | 43% | -130.09 | -1,640.09 |

## Days after 2026-10-20 (descriptive)

Price basis: Robinhood one-minute option bars: the 15:51 bar open + $0.10, held to the official close (the forward log's Exit A), $0.09 fee. Not the Databento ask, so not the same price basis as Parts 1-2. Only days after the selection was written (2026-11-09, ET) count as fresh.

- current: 7 signal day(s), 4 with a price, 0 fresh; mean of the priced ones +303.41.

| Date | Status | Option | Paid | Exit A | P&L $0.09 | Provisional | Label |
|---|---|---|---|---|---|---|---|
| 2026-10-22 | traded | call 7650 | 9.75 | 13.43 | +367.91 | False | previously available |
| 2026-10-27 | traded | put 7740 | 10.10 | 17.40 | +729.91 | False | previously available |
| 2026-10-29 | traded | call 7705 | 11.00 | 15.39 | +438.91 | False | previously available |
| 2026-10-30 | traded | call 7570 | 13.30 | 10.07 | -323.09 | False | previously available |
| 2026-11-02 | no_minute_option_bars | put 7555 | — | — | — | False | previously available |
| 2026-11-03 | no_minute_option_bars | put 7570 | — | — | — | False | previously available |
| 2026-11-06 | no_minute_option_bars | put 7395 | — | — | — | False | previously available |

- pick: 7 signal day(s), 4 with a price, 0 fresh; mean of the priced ones +373.41. (the 15:50 candle direction log's contract at the pick's strike, on days the forward candle's body is at least the pick's threshold.)

| Date | Status | Option | Paid | Exit A | P&L $0.09 | Provisional | Label |
|---|---|---|---|---|---|---|---|
| 2026-10-22 | traded | call 7640 | 19.20 | 23.43 | +422.91 | False | previously available |
| 2026-10-27 | traded | put 7750 | 19.95 | 27.40 | +744.91 | False | previously available |
| 2026-10-29 | traded | call 7695 | 20.30 | 25.39 | +508.91 | False | previously available |
| 2026-10-30 | traded | call 7560 | 21.90 | 20.07 | -183.09 | False | previously available |
| 2026-11-02 | no_minute_option_bars | put 7565 | — | — | — | False | previously available |
| 2026-11-03 | no_minute_option_bars | put 7580 | — | — | — | False | previously available |
| 2026-11-06 | no_minute_option_bars | put 7405 | — | — | — | False | previously available |


## Caveats

- Signals come from D1 (a CFD). A fill at the quoted ask ignores order size and fast minutes; the fill study found that a mid limit does not capture the mid.
- The download holds the 25 strikes within 60 points of the D1 15:51 ATM, so for earlier entries a missing price can depend on the later move. Cells need 95% coverage overall and in each half; inference is about priced days only.
- Expiry frequency, volatility and pricing changed over 2021-2023, so the circular-shift luck diagnostic is not an exact test.
- No candidate advanced under the prespecified rules (failed gate: luck diagnostic p <= 0.05). That does not show that the current rule is the best setting.
- Nothing here is a trading recommendation.
