# Search of the closing candles: results

## Part 1: tuning (2021-01-01 .. 2023-12-31)

Days: 625. Eligible cells: 387 of 7128. Consistency checks: R60 336 rows equal, S60 227 rows equal.

**Decision:** No candidate advanced under the prespecified rules: the pick (index 15:50 body>=0.80 with ITM20) is examined, or closely related to settings examined, on 2024-2026; it can only be checked on future days. No runner-up is substituted.
- Pick: index 15:50 body>=0.80 with ITM20; score +37.46 a day; mean +39.42 a day; 193 trades (H1 98, H2 95); coverage 100%.
- Luck diagnostic: p = 0.051 over 195 shifts (null median +20.11, 95th percentile +37.38; shifts with no eligible cell 0).
- Pick minus R60 on tuning: +21.94 a day (t +1.81, paired n 614).

Best eligible cells on tuning (score = plateau mean per day):

| # | Cell | Score | $/day | Trades | H1 $/day | H2 $/day | Coverage |
|---|---|---|---|---|---|---|---|
| 1 | index 15:50 body>=0.80 with ITM20 | +37.46 | +39.42 | 193 | +77.15 | +1.08 | 100% |
| 2 | index 15:50 body>=0.80 with ITM15 | +33.87 | +35.50 | 192 | +69.96 | +0.59 | 99% |
| 3 | index 15:54 body>=0.60 with ITM5 | +33.55 | +32.43 | 299 | +50.12 | +14.33 | 97% |
| 4 | both 15:54 body>=0.40 with ITM5 | +32.88 | +38.17 | 325 | +53.11 | +23.03 | 97% |
| 5 | index 15:54 body>=0.65 with ITM5 | +32.47 | +32.71 | 261 | +50.36 | +14.71 | 97% |
| 6 | both 15:50 body>=0.65 with ITM20 | +32.19 | +34.72 | 179 | +67.80 | +1.09 | 100% |
| 7 | index 15:54 body>=0.70 with ITM5 | +31.94 | +32.26 | 224 | +45.21 | +18.97 | 98% |
| 8 | index 15:50 body>=0.80 with ITM5 | +31.88 | +33.85 | 192 | +67.00 | +0.27 | 99% |
| 9 | SPY 15:54 body>=0.40 with ITM5 | +31.46 | +35.46 | 342 | +49.97 | +20.76 | 97% |
| 10 | both 15:54 body>=0.45 with ITM5 | +31.40 | +27.58 | 283 | +45.98 | +8.75 | 97% |
| 11 | both 15:50 body>=0.65 with ITM5 | +31.35 | +32.60 | 178 | +63.53 | +1.25 | 99% |
| 12 | index 15:54 body>=0.55 with ITM5 | +31.24 | +35.50 | 323 | +55.72 | +14.73 | 97% |
| 13 | both 15:54 body>=0.40 with ITM10 | +31.18 | +37.08 | 325 | +50.89 | +23.08 | 97% |
| 14 | SPY 15:50 body>=0.65 with ITM10 | +31.16 | +34.36 | 189 | +62.93 | +5.43 | 99% |
| 15 | both 15:54 body>=0.40 with ITM15 | +30.85 | +36.22 | 324 | +50.60 | +21.70 | 96% |

Best eligible cell per candle minute:

| Candle | Cell | Score | $/day | Trades |
|---|---|---|---|---|
| 15:45 | index 15:45 body>=0.80 with ITM20 | +21.46 | +27.65 | 166 |
| 15:46 | index 15:46 body>=0.40 with ITM5 | +1.48 | +6.81 | 430 |
| 15:47 | index 15:47 body>=0.70 with ITM5 | -0.19 | +4.25 | 235 |
| 15:48 | index 15:48 body>=0.40 with ATM | +19.30 | +19.41 | 416 |
| 15:49 | index 15:49 body>=0.90 with ATM | +5.22 | +7.75 | 104 |
| 15:50 | index 15:50 body>=0.80 with ITM20 | +37.46 | +39.42 | 193 |
| 15:51 | none eligible |  |  |  |
| 15:52 | both 15:52 body>=0.50 against ITM5 | +12.00 | +13.31 | 237 |
| 15:53 | index 15:53 body>=0.80 with ATM | +23.40 | +23.69 | 177 |
| 15:54 | index 15:54 body>=0.60 with ITM5 | +33.55 | +32.43 | 299 |
| 15:55 | none eligible |  |  |  |
## Part 2: the test (2024-01-01 .. 2026-10-20)

Not run. No candidate advanced under the prespecified rules: the pick (index 15:50 body>=0.80 with ITM20) is examined, or closely related to settings examined, on 2024-2026; it can only be checked on future days. No runner-up is substituted.

## Part 3: descriptive (decides nothing)

### Whole period 2021-2026 (looked at after the decision; in-sample; not a test)

Eligible cells: 3887. Shift benchmark of the best raw mean per day: median +17.74, 95th percentile +30.67; observed best +34.74.

| # | Cell | $/day | t | Trades | $/trade | Won |
|---|---|---|---|---|---|---|
| 1 | both 15:50 body>=0.60 with ITM20 | +34.74 | +2.71 | 505 | +89.44 | 55% |
| 2 | index 15:50 body>=0.85 with ITM20 | +34.23 | +3.23 | 365 | +122.87 | 55% |
| 3 | index 15:50 body>=0.80 with ITM20 | +34.20 | +2.92 | 438 | +102.29 | 55% |
| 4 | both 15:50 body>=0.65 with ITM20 | +33.97 | +2.85 | 429 | +102.93 | 55% |
| 5 | SPY 15:50 body>=0.65 with ITM20 | +33.44 | +2.83 | 446 | +98.37 | 55% |
| 6 | SPY 15:50 body>=0.70 with ITM20 | +33.08 | +3.11 | 369 | +117.61 | 55% |
| 7 | index 15:50 body>=0.75 with ITM20 | +32.23 | +2.67 | 500 | +84.44 | 54% |
| 8 | both 15:50 body>=0.70 with ITM20 | +32.20 | +3.01 | 357 | +117.25 | 55% |
| 9 | both 15:50 body>=0.60 with ITM15 | +32.10 | +2.53 | 503 | +82.84 | 55% |
| 10 | SPY 15:50 body>=0.60 with ITM20 | +31.92 | +2.49 | 524 | +79.92 | 54% |
| 11 | index 15:50 body>=0.80 with ITM15 | +31.73 | +2.73 | 436 | +95.20 | 55% |
| 12 | index 15:50 body>=0.85 with ITM15 | +31.60 | +3.00 | 363 | +113.87 | 55% |
| 13 | both 15:50 body>=0.65 with ITM15 | +31.30 | +2.65 | 427 | +95.15 | 56% |
| 14 | both 15:50 body>=0.60 with ITM10 | +31.21 | +2.56 | 504 | +80.44 | 54% |
| 15 | SPY 15:50 body>=0.75 with ITM20 | +31.18 | +3.06 | 304 | +134.58 | 56% |

### Index move after the candle, 2019-2020 (in the candle's direction; basis points from the next minute's open to the 15:59 close)

132 cells, 500 days. Largest t +2.90; shift benchmark of the largest t: median +3.26, 95th percentile +6.39.

| Source | Candle | Threshold | Days | bps | t | Right |
|---|---|---|---|---|---|---|
| index | 15:47 | 0.95 | 23 | +6.78 | +2.90 | 57% |
| index | 15:53 | 0.90 | 31 | +7.95 | +2.85 | 61% |
| index | 15:48 | 0.75 | 60 | +5.11 | +2.78 | 60% |
| index | 15:48 | 0.80 | 49 | +5.01 | +2.65 | 59% |
| index | 15:48 | 0.70 | 73 | +4.32 | +2.57 | 59% |
| index | 15:47 | 0.75 | 58 | +3.23 | +2.51 | 55% |
| index | 15:48 | 0.65 | 81 | +3.71 | +2.32 | 58% |
| index | 15:47 | 0.65 | 81 | +3.84 | +2.30 | 57% |
| index | 15:53 | 0.80 | 49 | +5.45 | +2.30 | 59% |
| index | 15:53 | 0.85 | 45 | +5.34 | +2.23 | 58% |

### Index move after the candle, 2021-2026 (in the candle's direction; basis points from the next minute's open to the 15:59 close)

396 cells, 1446 days. Largest t +5.21; shift benchmark of the largest t: median +3.00, 95th percentile +5.57.

| Source | Candle | Threshold | Days | bps | t | Right |
|---|---|---|---|---|---|---|
| index | 15:50 | 0.85 | 408 | +3.52 | +5.21 | 58% |
| index | 15:50 | 0.80 | 490 | +3.35 | +5.21 | 59% |
| index | 15:50 | 0.75 | 555 | +2.99 | +5.01 | 58% |
| both | 15:50 | 0.65 | 468 | +3.38 | +4.94 | 59% |
| SPY | 15:50 | 0.65 | 482 | +3.26 | +4.91 | 59% |
| both | 15:50 | 0.60 | 550 | +2.97 | +4.79 | 58% |
| SPY | 15:50 | 0.70 | 399 | +3.42 | +4.70 | 58% |
| SPY | 15:50 | 0.60 | 565 | +2.78 | +4.61 | 57% |
| both | 15:50 | 0.70 | 390 | +3.43 | +4.59 | 58% |
| both | 15:50 | 0.55 | 629 | +2.61 | +4.58 | 57% |

### Leads already seen (exclusion family)

| Cell | Tuning $/day | t | Test $/day | t | Test trades |
|---|---|---|---|---|---|
| index 15:50 body>=0.80 with ITM10 | +37.26 | +2.49 | +23.05 | +1.39 | 245 |
| index 15:50 body>=0.80 with ITM20 | +39.42 | +2.50 | +29.58 | +1.73 | 245 |
| index 15:50 body>=0.85 with ITM10 | +35.50 | +2.73 | +22.85 | +1.47 | 204 |
| index 15:50 body>=0.85 with ITM20 | +38.29 | +2.83 | +30.64 | +1.92 | 204 |
| SPY 15:50 body>=0.70 with ITM10 | +29.28 | +2.29 | +28.91 | +1.85 | 219 |
| SPY 15:50 body>=0.70 with ITM20 | +30.56 | +2.26 | +35.32 | +2.20 | 219 |
| SPY 15:50 body>=0.80 with ITM10 | +22.50 | +2.12 | +16.22 | +1.22 | 139 |
| SPY 15:50 body>=0.80 with ITM20 | +23.31 | +2.13 | +21.11 | +1.53 | 139 |
| both 15:50 body>=0.60 with ITM10 | +34.52 | +2.11 | +28.30 | +1.58 | 288 |
| both 15:50 body>=0.60 with ITM20 | +32.54 | +1.84 | +36.69 | +1.99 | 288 |

### Named cells

| Cell | Version | Period | $/day | t | Trades | $/trade | Won |
|---|---|---|---|---|---|---|---|
| pick | ask_fee_0.09 | tuning | +39.42 | +2.50 | 193 | +125.63 | 59% |
| pick | ask_fee_0.09 | test | +29.58 | +1.73 | 245 | +83.91 | 52% |
| pick | ask_fee_0.74 | tuning | +39.22 | +2.49 | 193 | +124.98 | 59% |
| pick | ask_fee_0.74 | test | +29.35 | +1.72 | 245 | +83.26 | 52% |
| pick | mid_fee_0.09 | tuning | +61.03 | +3.75 | 193 | +194.49 | 65% |
| pick | mid_fee_0.09 | test | +41.32 | +2.41 | 245 | +117.21 | 56% |
| R60 | ask_fee_0.09 | tuning | +17.54 | +0.87 | 336 | +32.06 | 53% |
| R60 | ask_fee_0.09 | test | +24.80 | +1.27 | 374 | +46.08 | 51% |
| R60 | ask_fee_0.74 | tuning | +17.19 | +0.85 | 336 | +31.41 | 53% |
| R60 | ask_fee_0.74 | test | +24.45 | +1.25 | 374 | +45.43 | 51% |
| R60 | mid_fee_0.09 | tuning | +46.79 | +2.26 | 336 | +85.51 | 57% |
| R60 | mid_fee_0.09 | test | +38.49 | +1.98 | 374 | +71.52 | 53% |
| S70 | ask_fee_0.09 | tuning | +29.28 | +2.29 | 150 | +120.82 | 58% |
| S70 | ask_fee_0.09 | test | +28.91 | +1.85 | 219 | +91.47 | 53% |
| S70 | ask_fee_0.74 | tuning | +29.12 | +2.27 | 150 | +120.17 | 58% |
| S70 | ask_fee_0.74 | test | +28.70 | +1.84 | 219 | +90.82 | 53% |
| S70 | mid_fee_0.09 | tuning | +40.65 | +3.08 | 150 | +167.75 | 62% |
| S70 | mid_fee_0.09 | test | +36.99 | +2.36 | 219 | +117.07 | 54% |

Pick minus S70 (tuning, descriptive): +11.45 a day, t +1.10, paired n 609.

Pick minus S70 (test, descriptive): +1.67 a day, t +0.23, paired n 691.

## Notes added after the registered run (not pre-registered)

- The code had no separate review before the run. It passed its own synthetic self-test
  (`selftest`, 31 checks) and an end-to-end dry run on synthetic data, and both consistency checks against the
  earlier studies' trade files passed (R60 and S60, tuning and test).
- The index-move benchmark is wide because the largest t in a shuffled table usually comes from a tiny cell: over
  118 of the shifts, the cell with the largest t had a median of 48 days (62% under 100 days). Among cells with at
  least 300 days, the shuffled largest t had median 2.17 and 95th percentile 3.40; the 15:50 cells reach 5.2 with
  400-550 days. This diagnostic was chosen after seeing the results (diag_null_sizes.py) and decides nothing.
- Disclosure added 2026-11-10 (descriptive, decides nothing): one more 15:50 cell was computed from the two
  frozen archives, the alert's current rule (SPY 15:50
  candle 70%+ AND index 15:50 candle 60%+, same direction, ITM10 with, 15:51 ask, 2021-01-01..2026-10-20): 365
  trades (the 369 S70 trades less 3 with no index bar and 1 with the index candle under 60%), +$101.33 a trade,
  total +$36,986, 54.5% won. It reads no other minute, threshold, strike or direction, and lies inside this search's
  15:50 exclusion family, so it changes nothing here. (This search's S70 count, 150 tuning + 219 test = 369,
  agrees with that session's starting point.)
