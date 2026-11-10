# The 15:50 candle on cheaper contracts: XSP and SPY 0DTE options at real prices

Pre-registration `preregistration/spx_candle_mini.md` (SHA-256 `4622d7f5d35e6160...`), period 2021-01-01 .. 2026-10-20. One contract at a time, real Databento OPRA quotes (the 15:51:00 and 15:59:00 snapshots). Research only; nothing here is a trading recommendation.

## The two verdicts (never combined)

- **XSP (the primary test; ITM1 at the 15:51 ask, settled at SPX close / 10, $0.09): not confirmed on XSP at real prices: -15.16 a day, Newey-West t -5.48, 1025 days, 313 trades, -49.66 a trade, 35% won, median -31.79, worst -818.29**
- **SPY (secondary; version (b): ITM1 at the 15:51 ask, sold at the 15:59 bid, $0.09 each side): not confirmed on SPY at real prices: +0.23 a day, Newey-West t +0.23, 1262 days, 560 trades, +0.51 a trade, 45% won, median -4.68, worst -176.18**

What this is and is not:

- The SPX outcomes on 2021-2026 were already known (XSP settles to SPX / 10, and SPY tracks SPX). This measures the net result of the analogous contracts (mostly their spreads and fees, plus the $1 strike grid, their own pricing and, for SPY, tracking and the 15:59 exit), not whether the signal works.
- It is a fixed one-contract price study with assumed fees ($0.09 a contract; $0.74 as a descriptive case), not a simulation of a $500 account.
- Signals come from D1, a CFD, on days chosen with bars after the entry (the D1 keep set needs every bar 15:19 to 15:59); the results are conditional on it. A fill at the quoted ask ignores order size and fast minutes, and XSP's quoted size can be small.
- For SPY, a broker may close an expiring position in a small account before 15:59, or refuse the order; this study cannot model that. Check the broker's rules. SPY (b)'s verdict is conditional on the exits that were quoted at 15:59 (the worst case below shows how much that matters).
- XSP's settlement value here is SPX close / 10, unrounded: the plan's fixed rule and a proxy for the published value (the rounded version is below).

## Checks (each would have stopped the run)

- Official SPX closes (Cboe) against Robinhood: 362 overlapping days, largest difference 0.0000 (compared in decimals; realprice's float check agrees: True).
- SPY closes: all 1270 SPY-sample days have one; SPY / official SPX close in 0.09913 .. 0.10054 (bounds 0.098 .. 0.101).
- Signal check 1: equal to scan.py's F2 on all 1446 D1 kept days. Signal check 2: the same sign as the SPX confirmation trade list on all 586 days in both (0 trade-list days not among the D1 days).
- The SPX ITM10 per-day series rebuilt from `realprice_trades.csv` reproduces the SPX confirmation: 1321 days, 585 trades, +29.87 a day, t +2.40 (expected {'days': 1321, 'trades': 585, 'mean_per_day': 29.87, 't': 2.4}).
- Downloads complete for both roots (every D1 day has a file or a no-symbol-resolved marker).

## Base case, 2021-01-01 .. 2026-10-20

Per-day series: the trade's P&L on a priced signal day, 0 on a no-signal day, missing when not priced. $ per contract.

| | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|
| XSP ITM1: 15:51 ask, settled at SPX close / 10 | 1025 | -15.16 | -5.48 | 313 | -49.66 | 35% | -31.79 | -818.29 |
|   xsp 2021-2022 | 254 | -37.49 | -5.29 | 59 | -161.38 | 14% | -120.09 | -818.29 |
|   xsp 2023-2026 | 771 | -7.81 | -3.09 | 254 | -23.70 | 40% | -18.14 | -489.09 |
| SPY ITM1 (b): 15:51 ask, sold at the 15:59 bid | 1262 | +0.23 | +0.23 | 560 | +0.51 | 45% | -4.68 | -176.18 |
|   spy_b 2021-2022 | 323 | +0.67 | +0.36 | 138 | +1.56 | 48% | -2.68 | -110.18 |
|   spy_b 2023-2026 | 939 | +0.07 | +0.07 | 422 | +0.17 | 45% | -6.68 | -176.18 |
| SPY ITM1 (a): 15:51 ask, valued at Yahoo's SPY close | 1263 | -0.99 | -0.79 | 561 | -2.23 | 48% | -3.09 | -220.09 |
|   spy_a 2021-2022 | 323 | +1.94 | +0.80 | 138 | +4.53 | 56% | +7.41 | -148.09 |
|   spy_a 2023-2026 | 940 | -2.00 | -1.37 | 423 | -4.44 | 46% | -6.09 | -220.09 |
| SPX ITM10 (rebuilt, not repriced) | 1321 | +29.87 | +2.40 | 585 | +67.46 | 54% | +44.91 | -2,210.09 |
|   SPX 2021-2022 | 376 | +48.21 | +2.01 | 157 | +115.46 | 57% | +65.91 | -1,361.09 |
|   SPX 2023-2026 | 945 | +22.58 | +1.56 | 428 | +49.85 | 53% | +35.91 | -2,210.09 |

Signal days not priced (base case):

- XSP ITM1: 15:51 ask, settled at SPX close / 10: 571 signal days, 313 priced; not priced: no spot 258, no quote 0.
- SPY ITM1 (b): 15:51 ask, sold at the 15:59 bid: 568 signal days, 560 priced; not priced: no spot 4, no quote 3, no exit quote 1.
- SPY ITM1 (a): 15:51 ask, valued at Yahoo's SPY close: 568 signal days, 561 priced; not priced: no spot 4, no quote 3.

## Descriptive (decides nothing)

### 1-3. Other strikes, the mid, the $0.74 fee

| Version | Variant | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|---|
| xsp | ITM2, ask, $0.09 | 1022 | -22.67 | -6.76 | 310 | -74.75 | 34% | -43.44 | -841.69 |
| xsp | ITM1, ask, $0.09 | 1025 | -15.16 | -5.48 | 313 | -49.66 | 35% | -31.79 | -818.29 |
| xsp | ATM, ask, $0.09 | 1024 | -3.61 | -2.32 | 312 | -11.86 | 33% | -17.49 | -918.29 |
| xsp | ITM1, mid, $0.09 | 1025 | +0.05 | +0.03 | 313 | +0.17 | 51% | +2.41 | -318.29 |
| xsp | ITM1, ask, $0.74 | 1025 | -15.36 | -5.55 | 313 | -50.31 | 35% | -32.44 | -818.94 |
| spy_b | ITM2, ask, $0.09 | 1264 | -1.36 | -1.27 | 562 | -3.05 | 45% | -5.18 | -221.18 |
| spy_b | ITM1, ask, $0.09 | 1262 | +0.23 | +0.23 | 560 | +0.51 | 45% | -4.68 | -176.18 |
| spy_b | ATM, ask, $0.09 | 1261 | +0.28 | +0.40 | 559 | +0.64 | 38% | -6.18 | -137.18 |
| spy_b | ITM1, mid, $0.09 | 1262 | +3.08 | +3.07 | 560 | +6.95 | 52% | +2.07 | -167.18 |
| spy_b | ITM1, ask, $0.74 | 1262 | -0.35 | -0.36 | 560 | -0.79 | 44% | -5.98 | -177.48 |
| spy_a | ITM2, ask, $0.09 | 1264 | +0.84 | +0.62 | 562 | +1.88 | 51% | +1.91 | -289.09 |
| spy_a | ITM1, ask, $0.09 | 1263 | -0.99 | -0.79 | 561 | -2.23 | 48% | -3.09 | -220.09 |
| spy_a | ATM, ask, $0.09 | 1263 | -4.51 | -4.81 | 561 | -10.14 | 29% | -18.09 | -162.09 |
| spy_a | ITM1, mid, $0.09 | 1263 | +0.21 | +0.17 | 561 | +0.48 | 50% | -0.59 | -212.59 |
| spy_a | ITM1, ask, $0.74 | 1263 | -1.28 | -1.02 | 561 | -2.88 | 48% | -3.74 | -220.74 |

The mid version buys at the 15:51 mid (SPY (b) also sells at the 15:59 mid); fees as in the base case ($0.09 once, or on each side for SPY (b)). $0.74 is charged per contract on each side for SPY (b).

### 4. By year (Newey-West within each slice)

| Version | Slice | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|---|
| xsp | 2021 | 100 | -32.38 | -2.84 | 9 | -359.78 | 0% | -303.49 | -818.29 |
| xsp | 2022 | 154 | -40.80 | -4.53 | 50 | -125.67 | 16% | -80.84 | -481.49 |
| xsp | 2023 | 172 | -19.22 | -3.01 | 37 | -89.34 | 19% | -47.79 | -489.09 |
| xsp | 2024 | 201 | -13.72 | -2.43 | 58 | -47.56 | 31% | -19.64 | -414.19 |
| xsp | 2025 | 224 | -1.10 | -0.32 | 94 | -2.63 | 47% | -7.44 | -242.09 |
| xsp | 2026 | 174 | +1.67 | +0.47 | 65 | +4.47 | 49% | -5.09 | -129.09 |
| xsp | 2021-2022 | 254 | -37.49 | -5.29 | 59 | -161.38 | 14% | -120.09 | -818.29 |
| xsp | 2023-2026 | 771 | -7.81 | -3.09 | 254 | -23.70 | 40% | -18.14 | -489.09 |
| spy_b | 2021 | 156 | +3.60 | +1.35 | 67 | +8.39 | 51% | +0.82 | -91.18 |
| spy_b | 2022 | 167 | -2.08 | -0.87 | 71 | -4.88 | 45% | -7.18 | -110.18 |
| spy_b | 2023 | 244 | -0.63 | -0.37 | 109 | -1.41 | 46% | -6.18 | -97.18 |
| spy_b | 2024 | 249 | +0.22 | +0.12 | 106 | +0.53 | 42% | -3.68 | -92.18 |
| spy_b | 2025 | 246 | -0.11 | -0.04 | 116 | -0.24 | 43% | -7.18 | -176.18 |
| spy_b | 2026 | 200 | +0.98 | +0.38 | 91 | +2.15 | 47% | -10.18 | -115.18 |
| spy_b | 2021-2022 | 323 | +0.67 | +0.36 | 138 | +1.56 | 48% | -2.68 | -110.18 |
| spy_b | 2023-2026 | 939 | +0.07 | +0.07 | 422 | +0.17 | 45% | -6.68 | -176.18 |
| spy_a | 2021 | 156 | +5.60 | +1.75 | 67 | +13.03 | 57% | +7.91 | -129.09 |
| spy_a | 2022 | 167 | -1.48 | -0.42 | 71 | -3.48 | 55% | +4.91 | -148.09 |
| spy_a | 2023 | 244 | -1.82 | -0.86 | 109 | -4.07 | 49% | -3.09 | -109.09 |
| spy_a | 2024 | 249 | -2.26 | -0.87 | 106 | -5.32 | 42% | -8.09 | -141.09 |
| spy_a | 2025 | 247 | -1.89 | -0.53 | 117 | -4.00 | 49% | -4.09 | -220.09 |
| spy_a | 2026 | 200 | -2.01 | -0.62 | 91 | -4.41 | 44% | -11.09 | -190.09 |
| spy_a | 2021-2022 | 323 | +1.94 | +0.80 | 138 | +4.53 | 56% | +7.41 | -148.09 |
| spy_a | 2023-2026 | 940 | -2.00 | -1.37 | 423 | -4.44 | 46% | -6.09 | -220.09 |
| spx_itm10 | 2021 | 158 | +74.05 | +2.33 | 67 | +174.63 | 57% | +52.91 | -1,210.09 |
| spx_itm10 | 2022 | 218 | +29.49 | +0.86 | 90 | +71.42 | 57% | +74.91 | -1,361.09 |
| spx_itm10 | 2023 | 248 | +1.79 | +0.09 | 113 | +3.93 | 53% | +24.91 | -1,340.09 |
| spx_itm10 | 2024 | 249 | +8.68 | +0.33 | 106 | +20.39 | 50% | -11.09 | -1,170.09 |
| spx_itm10 | 2025 | 247 | +30.68 | +0.93 | 117 | +64.76 | 56% | +67.91 | -2,210.09 |
| spx_itm10 | 2026 | 201 | +55.49 | +1.54 | 92 | +121.23 | 51% | +20.91 | -1,280.09 |
| spx_itm10 | 2021-2022 | 376 | +48.21 | +2.01 | 157 | +115.46 | 57% | +65.91 | -1,361.09 |
| spx_itm10 | 2023-2026 | 945 | +22.58 | +1.56 | 428 | +49.85 | 53% | +35.91 | -2,210.09 |

### 5. Spread as a share of the premium ((ask - bid) / mid at 15:51, the contract bought)

| Root | Slice | Entries | Mean | Median | Paired days | Root on paired days (mean / median) | SPX ITM10 on paired days (mean / median) |
|---|---|---|---|---|---|---|---|
| xsp | all | 313 | 0.665 | 0.305 | 313 | 0.665 / 0.305 | 0.065 / 0.053 |
| xsp | 2021 | 9 | 1.893 | 1.944 | 9 | 1.893 / 1.944 | 0.148 / 0.127 |
| xsp | 2022 | 50 | 1.438 | 1.470 | 50 | 1.438 / 1.470 | 0.128 / 0.110 |
| xsp | 2023 | 37 | 0.840 | 0.477 | 37 | 0.840 / 0.477 | 0.065 / 0.059 |
| xsp | 2024 | 58 | 0.729 | 0.468 | 58 | 0.729 / 0.468 | 0.059 / 0.057 |
| xsp | 2025 | 94 | 0.322 | 0.246 | 94 | 0.322 / 0.246 | 0.046 / 0.046 |
| xsp | 2026 | 65 | 0.240 | 0.241 | 65 | 0.240 / 0.241 | 0.038 / 0.042 |
| spy_entry | all | 561 | 0.048 | 0.043 | 561 | 0.048 / 0.043 | 0.071 / 0.056 |
| spy_entry | 2021 | 67 | 0.060 | 0.048 | 67 | 0.060 / 0.048 | 0.141 / 0.105 |
| spy_entry | 2022 | 71 | 0.066 | 0.059 | 71 | 0.066 / 0.059 | 0.126 / 0.105 |
| spy_entry | 2023 | 109 | 0.049 | 0.048 | 109 | 0.049 / 0.048 | 0.061 / 0.058 |
| spy_entry | 2024 | 106 | 0.051 | 0.047 | 106 | 0.051 / 0.047 | 0.059 / 0.056 |
| spy_entry | 2025 | 117 | 0.038 | 0.037 | 117 | 0.038 / 0.037 | 0.045 / 0.045 |
| spy_entry | 2026 | 91 | 0.030 | 0.028 | 91 | 0.030 / 0.028 | 0.038 / 0.038 |

SPY (b), the contract sold at 15:59 ((ask - bid) / mid at 15:59):

| Slice | Exits | Mean | Median |
|---|---|---|---|
| all | 560 | 0.065 | 0.057 |
| 2021 | 67 | 0.085 | 0.058 |
| 2022 | 71 | 0.085 | 0.074 |
| 2023 | 109 | 0.061 | 0.053 |
| 2024 | 106 | 0.066 | 0.062 |
| 2025 | 116 | 0.058 | 0.054 |
| 2026 | 91 | 0.048 | 0.041 |

### 6. Return per dollar of premium (sum of P&L / sum of 100 x ask, priced trades)

| Series | Trades | Sum P&L | Sum premium | Return per $ | Mean P&L | Mean premium |
|---|---|---|---|---|---|---|
| SPX ITM10, all trades | 585 | +39,463.35 | 643,220.00 | +0.0614 | +67.46 | 1,099.52 |
| XSP ITM1: 15:51 ask, settled at SPX close / 10 | 313 | -15,542.17 | 54,534.00 | -0.2850 | -49.66 | 174.23 |
|   xsp on the days both it and SPX traded | 313 | -15,542.17 | 54,534.00 | -0.2850 | -49.66 | 174.23 |
|   SPX ITM10 on those days | 313 | +18,809.83 | 355,080.00 | +0.0530 | +60.10 | 1,134.44 |
|   SPX ITM10 on every day in the XSP sample | 571 | +33,393.61 | 626,910.00 | +0.0533 | +58.48 | 1,097.92 |
| SPY ITM1 (b): 15:51 ask, sold at the 15:59 bid | 560 | +285.20 | 65,897.00 | +0.0043 | +0.51 | 117.67 |
|   spy_b on the days both it and SPX traded | 560 | +285.20 | 65,897.00 | +0.0043 | +0.51 | 117.67 |
|   SPX ITM10 on those days | 560 | +33,164.60 | 615,200.00 | +0.0539 | +59.22 | 1,098.57 |
|   SPX ITM10 on every day in the SPY sample | 568 | +32,576.88 | 623,490.00 | +0.0522 | +57.35 | 1,097.69 |
| SPY ITM1 (a): 15:51 ask, valued at Yahoo's SPY close | 561 | -1,250.49 | 66,037.00 | -0.0189 | -2.23 | 117.71 |
|   spy_a on the days both it and SPX traded | 561 | -1,250.49 | 66,037.00 | -0.0189 | -2.23 | 117.71 |
|   SPX ITM10 on those days | 561 | +32,682.51 | 616,170.00 | +0.0530 | +58.26 | 1,098.34 |
|   SPX ITM10 on every day in the SPY sample | 568 | +32,576.88 | 623,490.00 | +0.0522 | +57.35 | 1,097.69 |

### 7. Affordability (premium + entry fee <= $500)

| Version | Priced trades | Affordable | Share | Skipped | Affordable-only: days | $/day | t | Trades | $/trade |
|---|---|---|---|---|---|---|---|---|---|
| xsp | 313 | 301 | 96% | 12 | 1025 | -10.00 | -4.80 | 301 | -34.04 |
| spy_b | 560 | 560 | 100% | 0 | 1262 | +0.23 | +0.23 | 560 | +0.51 |
| spy_a | 561 | 561 | 100% | 0 | 1263 | -0.99 | -0.79 | 561 | -2.23 |

This still does not simulate an account that shrinks after losses, or whether a broker accepts the order.

### 8. Paired with SPX / 10 (an overall comparison of the implementations, not a spread estimate)

| Version | Days in both samples | Root - SPX/10: days | mean | t | Before fees: days | mean | t |
|---|---|---|---|---|---|---|---|
| xsp | 1283 | 1025 | -17.00 | -6.79 | 1025 | -16.97 | -6.78 |
| spy_b | 1270 | 1262 | -2.40 | -4.26 | 1262 | -2.33 | -4.13 |
| spy_a | 1270 | 1263 | -3.58 | -7.45 | 1263 | -3.54 | -7.38 |

SPY is about 0.0997 x SPX, not exactly SPX / 10; the scaling stays 1/10.

### 9. No implied spot: the same trade with ATM from D1 (ITM1; never enters a verdict)

| Version | No-spot signal days | Priced with D1 ATM | No quote | No exit quote | Fallback $/trade | Won | Series with fallback: days | $/day | t | Trades |
|---|---|---|---|---|---|---|---|---|---|---|
| xsp | 258 | 256 | 2 | 0 | -100.27 | 29% | 1281 | -32.17 | -7.31 | 569 |
| spy_b | 4 | 4 | 0 | 0 | -13.68 | 25% | 1266 | +0.18 | +0.19 | 564 |
| spy_a | 4 | 4 | 0 | 0 | -8.09 | 50% | 1267 | -1.01 | -0.81 | 565 |

### 10. SPY (b): missing exits

Worst case (each of the 1 entries with no 15:59 quote charged the full premium plus both fees):

| | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|
| SPY (b) worst case | 1263 | +0.11 | +0.12 | 561 | +0.26 | 45% | -5.18 | -176.18 |
|   2021-2022 | 323 | +0.67 | +0.36 | 138 | +1.56 | 48% | -2.68 | -110.18 |
|   2023-2026 | 940 | -0.07 | -0.06 | 423 | -0.17 | 44% | -7.18 | -176.18 |

Exits valued at a 15:59 bid of 0 (an assumption, not a shown sale): 0.

Entry cohort (every priced SPY ITM1 entry, and how many had a valid 15:59 quote):

| Slice | Priced entries | With a 15:59 quote | Share |
|---|---|---|---|
| all | 561 | 560 | 100% |
| 2021 | 67 | 67 | 100% |
| 2022 | 71 | 71 | 100% |
| 2023 | 109 | 109 | 100% |
| 2024 | 106 | 106 | 100% |
| 2025 | 117 | 116 | 99% |
| 2026 | 91 | 91 | 100% |

### 11. XSP settlement rounded half up to the cent

| | Days | $/day | t | Trades | $/trade | Won | Median | Worst |
|---|---|---|---|---|---|---|---|---|
| XSP, X rounded to the cent | 1025 | -15.16 | -5.48 | 313 | -49.65 | 35% | -32.09 | -818.09 |

Largest change of one trade's P&L against the unrounded X: 0.50.

### 12. Counts

XSP:

| Year | d1 days | file | no symbol resolved | file no official close | sample days | signal days | missing candles | priced | no spot | no quote | in sample not in spx | in spx not in sample |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021 | 251 | 158 | 93 | 0 | 158 | 67 | 0 | 9 | 58 | 0 | 0 | 0 |
| 2022 | 250 | 180 | 70 | 0 | 180 | 76 | 0 | 50 | 26 | 0 | 0 | 39 |
| 2023 | 248 | 248 | 0 | 0 | 248 | 113 | 0 | 37 | 76 | 0 | 0 | 0 |
| 2024 | 249 | 249 | 0 | 0 | 249 | 106 | 0 | 58 | 48 | 0 | 0 | 0 |
| 2025 | 247 | 247 | 0 | 0 | 247 | 117 | 0 | 94 | 23 | 0 | 0 | 0 |
| 2026 | 201 | 201 | 0 | 0 | 201 | 92 | 0 | 65 | 27 | 0 | 0 | 0 |
| all | 1446 | 1283 | 163 | 0 | 1283 | 571 | 0 | 313 | 258 | 0 | 0 | 39 |

By weekday: in the XSP sample but not the SPX sample {'Mon': 0, 'Tue': 0, 'Wed': 0, 'Thu': 0, 'Fri': 0}; in the SPX sample but not the XSP sample {'Mon': 0, 'Tue': 19, 'Wed': 0, 'Thu': 20, 'Fri': 0}.

SPY:

| Year | d1 days | file | no symbol resolved | file no official close | sample days | signal days | missing candles | priced (entry) | no spot | no quote | priced (b) | no exit quote | in sample not in spx | in spx not in sample |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021 | 251 | 156 | 95 | 0 | 156 | 67 | 0 | 67 | 0 | 0 | 67 | 0 | 0 | 2 |
| 2022 | 250 | 169 | 81 | 0 | 169 | 73 | 0 | 71 | 0 | 2 | 71 | 0 | 0 | 50 |
| 2023 | 248 | 248 | 0 | 0 | 248 | 113 | 0 | 109 | 4 | 0 | 109 | 0 | 0 | 0 |
| 2024 | 249 | 249 | 0 | 0 | 249 | 106 | 0 | 106 | 0 | 0 | 106 | 0 | 0 | 0 |
| 2025 | 247 | 247 | 0 | 0 | 247 | 117 | 0 | 117 | 0 | 0 | 116 | 1 | 0 | 0 |
| 2026 | 201 | 201 | 0 | 0 | 201 | 92 | 0 | 91 | 0 | 1 | 91 | 0 | 0 | 0 |
| all | 1446 | 1270 | 176 | 0 | 1270 | 568 | 0 | 561 | 4 | 3 | 560 | 1 | 0 | 52 |

By weekday: in the SPY sample but not the SPX sample {'Mon': 0, 'Tue': 0, 'Wed': 0, 'Thu': 0, 'Fri': 0}; in the SPX sample but not the SPY sample {'Mon': 0, 'Tue': 27, 'Wed': 0, 'Thu': 25, 'Fri': 0}.

## Fill check on XSP trade bars (descriptive; decides nothing)

Trade bars from `data/spx_1549/databento/ohlcv-1m_1500-1601_xsp_k8`: 1283 day files and 163 no-symbol-resolved markers when the run started. A bar stamped 15:51 covers the trades in that minute; "last" is the minute's last trade. Prices per share. SPX ITM10 on the same days is read from `realprice_trades.csv`'s bar columns, not recomputed.

| Series | Period | Priced entries | With a bar file (days) | No file / unreadable | Traded in 15:51 | Low <= ask (of traded) | Last - mid, mean | Last - mid, median |
|---|---|---|---|---|---|---|---|---|
| XSP ITM1 | 2021-01-01..2026-10-20 | 313 | 313 (313) | 0 / 0 | 233 (74%) | 95% | +0.016 | +0.040 |
| SPX ITM10 on the XSP days with a bar file | 2021-01-01..2026-10-20 | 313 | 313 | | 313 (100%) | 96% | +0.118 | +0.100 |
| XSP ITM1, matched days | 2021-01-01..2026-10-20 | 313 | 313 | | 233 (74%) | 95% | +0.016 | +0.040 |
| SPX ITM10, matched days | 2021-01-01..2026-10-20 | 313 | 313 | | 313 (100%) | 96% | +0.118 | +0.100 |
| XSP ITM1 | 2021-01-01..2022-12-31 | 59 | 59 (59) | 0 / 0 | 16 (27%) | 100% | -0.228 | +0.015 |
| SPX ITM10 on the XSP days with a bar file | 2021-01-01..2022-12-31 | 59 | 59 | | 59 (100%) | 95% | +0.225 | +0.020 |
| XSP ITM1, matched days | 2021-01-01..2022-12-31 | 59 | 59 | | 16 (27%) | 100% | -0.228 | +0.015 |
| SPX ITM10, matched days | 2021-01-01..2022-12-31 | 59 | 59 | | 59 (100%) | 95% | +0.225 | +0.020 |
| XSP ITM1 | 2023-01-01..2026-10-20 | 254 | 254 (254) | 0 / 0 | 217 (85%) | 94% | +0.034 | +0.045 |
| SPX ITM10 on the XSP days with a bar file | 2023-01-01..2026-10-20 | 254 | 254 | | 254 (100%) | 97% | +0.093 | +0.105 |
| XSP ITM1, matched days | 2023-01-01..2026-10-20 | 254 | 254 | | 217 (85%) | 94% | +0.034 | +0.045 |
| SPX ITM10, matched days | 2023-01-01..2026-10-20 | 254 | 254 | | 254 (100%) | 97% | +0.093 | +0.105 |

Denominators: the XSP rows use every priced XSP entry (the share traded is of those with a readable bar file). "SPX ITM10 on the XSP days with a bar file" uses the SPX entries priced on the days of XSP entries with a readable bar file. "Matched days" are the days on which both entries are priced and both have a readable bar file. SPY has no fill check (SPY trade bars were not pulled).

## Notes

- Diagnostic: the D1 centre used by the no-spot fallback equals the download's centre on XSP 1283 of 1283 sample days; SPY 1270 of 1270 sample days.
- Forward days (after 2026-10-20) are not included: their XSP and SPY quotes have not been downloaded. They will be reported in a separate table and never pooled with 2021-2026.
- The two verdicts are separate; neither supports a claim that "at least one cheaper contract works", and neither changes the SPX result.
- Nothing here is a trading recommendation.
