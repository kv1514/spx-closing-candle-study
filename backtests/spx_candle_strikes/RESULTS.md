# Which strike to buy on the 15:50 strong-body signal

Rebuilt by `backtests/spx_candle_strikes/strikes.py` from `preregistration/spx_candle_strike_ladder.md`; do not edit by hand. Descriptive research, not a trading recommendation.

**How to read the strikes.** ITM20 = 20 points in the money in the trade's direction, OTM20 = 20 points out of the money. With SPX at 7700 and an up signal: ITM20 = the 7680 call, ATM = 7700, OTM20 = the 7720 call. With a down signal the same labels are puts: ITM20 = the 7720 put, OTM20 = the 7680 put.

## Modelled 2021-2026 (the backtest's strong-body days, every strike priced by a model)

644 trades, 2021-01-06 to 2026-10-19, 57% right. Moves rescaled to SPX 7709.58. Prices are a Bachelier model calibrated on Robinhood option prices from Oct-Nov 2026 (variant a), not real fills. The outcome is the CFD at 15:59, not the settlement. Every strike pays the same $0.10 half-spread and a $0.09 fee.

| Strike | Model price | Mean P&L / contract | t | Profitable | Mean return on premium | Median return | vs ATM (t) |
|---|---|---|---|---|---|---|---|
| ITM20 | $2,036 | +162.21 | 3.89 | 56% | +8% | +6% | +7.58 (0.40) |
| ITM15 | $1,580 | +142.62 | 3.50 | 55% | +9% | +6% | -12.00 (-0.71) |
| ITM10 | $1,098 | +166.08 | 4.25 | 54% | +15% | +8% | +11.45 (0.81) |
| ITM5 | $693 | +160.97 | 4.49 | 51% | +23% | +3% | +6.34 (0.75) |
| ATM | $367 | +154.63 | 4.96 | 42% | +45% | -50% | — |
| OTM5 | $205 | +92.10 | 3.59 | 27% | +53% | -100% | -62.53 (-7.11) |
| OTM10 | $204 | -34.34 | -1.47 | 14% | +7% | -100% | -188.97 (-8.71) |
| OTM15 | $120 | -21.91 | -1.11 | 9% | +13% | -100% | -176.54 (-7.23) |
| OTM20 | $1,683 | -1,628.66 | -3.62 | 1% | -74% | -100% | -1,783.29 (-3.93) |

Best by mean $ per contract and by mean return on premium, per variant (a description of the model):

| Variant | Best $ / contract | Best return on premium | ITM20 | ITM15 | ITM10 | ITM5 | ATM | OTM5 | OTM10 | OTM15 | OTM20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a_calibrated | ITM10 | OTM5 | +162 | +143 | +166 | +161 | +155 | +92 | -34 | -22 | -1,629 |
| b_constant_vol | ITM5 | OTM15 | +192 | +192 | +242 | +262 | +261 | +201 | +127 | +91 | +39 |
| c_realized_move_fair | ITM20 | OTM20 | +186 | +181 | +158 | +122 | +83 | +64 | +62 | +55 | +39 |
| d_ten_minute_k | ITM20 | ATM | +136 | +104 | +110 | +85 | +72 | +12 | -149 | -107 | -3,019 |
| a_half_spread_0.05 | ITM10 | OTM5 | +167 | +148 | +171 | +166 | +160 | +97 | -29 | -17 | -1,624 |
| a_half_spread_0.20 | ITM10 | ATM | +152 | +133 | +156 | +151 | +145 | +82 | -44 | -32 | -1,639 |
| a_k_x0.75 | ATM | OTM5 | +180 | +172 | +214 | +235 | +239 | +170 | +64 | +44 | -656 |
| a_k_x1.25 | ITM20 | ATM | +135 | +102 | +107 | +81 | +68 | +8 | -155 | -112 | -3,099 |
| a_no_skew | ITM15 | OTM10 | +172 | +174 | +171 | +166 | +143 | +106 | +72 | +45 | +23 |

Mean return on premium by variant:

| Variant | ITM20 | ITM15 | ITM10 | ITM5 | ATM | OTM5 | OTM10 | OTM15 | OTM20 |
|---|---|---|---|---|---|---|---|---|---|
| a_calibrated | +8% | +9% | +15% | +23% | +45% | +53% | +7% | +13% | -74% |
| b_constant_vol | +10% | +13% | +25% | +48% | +113% | +237% | +315% | +546% | +207% |
| c_realized_move_fair | +9% | +12% | +14% | +16% | +19% | +27% | +55% | +108% | +159% |
| d_ten_minute_k | +7% | +7% | +10% | +11% | +16% | +3% | -42% | -44% | -94% |
| a_half_spread_0.05 | +8% | +9% | +16% | +24% | +48% | +63% | +23% | +47% | -68% |
| a_half_spread_0.20 | +8% | +8% | +14% | +21% | +39% | +38% | -11% | -17% | -81% |
| a_k_x0.75 | +9% | +11% | +21% | +39% | +98% | +176% | +139% | +127% | -23% |
| a_k_x1.25 | +7% | +6% | +9% | +11% | +15% | +1% | -43% | -46% | -95% |
| a_no_skew | +9% | +11% | +16% | +24% | +41% | +63% | +84% | +76% | +34% |

Variant (a) by period (mean P&L per contract, $0.09 fee):

| Period | n | ITM20 | ITM15 | ITM10 | ITM5 | ATM | OTM5 | OTM10 | OTM15 | OTM20 |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021_2022 | 216 | +318 | +296 | +317 | +305 | +277 | +174 | -22 | -13 | -2,232 |
| 2023_2026 | 428 | +84 | +65 | +90 | +88 | +93 | +51 | -40 | -27 | -1,324 |

## Calibration

- One-minute days used: 7 (2026-10-20, 2026-10-21, 2026-10-22, 2026-10-26, 2026-10-27, 2026-10-29, 2026-10-30). Median implied move to the close 8.26 bps of SPX (one standard deviation).
- Implied / realized volatility k (Robinhood) 1.089; Robinhood / Dukascopy realized volatility c 0.978 over 22 days; k for Dukascopy 1.065. Ten-minute-day version (d): 1.319 over 22 days.
- Model move to the close, variant (a): median 10.10 bps (10th-90th percentile 5.72-19.20); variant (c) 10.78 points.
- Self-check: variant (c) at the exact entry price reproduces the backtest's ATM result (+80.89 vs +80.89 a trade).
- Skew factors (market price / model price at each strike, median over one-minute days and both sides):

| | ITM20 | ITM15 | ITM10 | ITM5 | ATM | OTM5 | OTM10 | OTM15 | OTM20 |
|---|---|---|---|---|---|---|---|---|---|
| f | 1.005 | 1.020 | 1.005 | 1.007 | 0.969 | 1.071 | 2.091 | 2.256 | 54.000 |
| ratios | 10 | 13 | 13 | 14 | 14 | 14 | 13 | 13 | 10 |

## Real prices on forward days

Forward days in the log: 13. Only days with real one-minute option bars can be priced. **This is a handful of trades and supports no conclusion.**

**F2_1m_1550_strong_body** (exit A = hold to the official close, exit B = sell at the 15:59 bar; $0.09 fee)

| Strike | Trades | Wins | Exit A total | Exit A mean | Mean return on premium | Exit B total |
|---|---|---|---|---|---|---|
| ITM20 | 4 | 3 | +1,493.64 | +373.41 | +19% | +1,329.28 |
| ITM15 | 4 | 3 | +1,193.64 | +298.41 | +21% | +1,084.28 |
| ITM10 | 4 | 3 | +1,213.64 | +303.41 | +31% | +1,164.28 |
| ITM5 | 4 | 3 | +658.64 | +164.66 | +39% | +484.28 |
| ATM | 4 | 2 | -69.36 | -17.34 | +55% | -173.72 |
| OTM5 | 4 | 1 | -682.36 | -170.59 | +19% | -763.72 |
| OTM10 | 4 | 0 | -529.36 | -132.34 | -100% | -565.72 |
| OTM15 | 4 | 0 | -305.36 | -76.34 | -100% | -341.72 |
| OTM20 | 2 | 0 | -29.18 | -14.59 | -100% | -47.36 |

**F1_1m_15:50** (exit A = hold to the official close, exit B = sell at the 15:59 bar; $0.09 fee)

| Strike | Trades | Wins | Exit A total | Exit A mean | Mean return on premium | Exit B total |
|---|---|---|---|---|---|---|
| ITM20 | 5 | 4 | +1,661.55 | +332.31 | +17% | +1,504.10 |
| ITM15 | 6 | 4 | +743.46 | +123.91 | +10% | +723.92 |
| ITM10 | 6 | 4 | +743.46 | +123.91 | +15% | +848.92 |
| ITM5 | 6 | 4 | +153.46 | +25.58 | +16% | +103.92 |
| ATM | 6 | 3 | -454.54 | -75.76 | +22% | -563.08 |
| OTM5 | 6 | 1 | -925.54 | -154.26 | -21% | -1,025.08 |
| OTM10 | 5 | 0 | -562.45 | -112.49 | -100% | -607.90 |
| OTM15 | 5 | 0 | -328.45 | -65.69 | -100% | -373.90 |
| OTM20 | 3 | 0 | -47.27 | -15.76 | -100% | -74.54 |

Strong-body rows, exit A ($0.09 fee):

| Date | Side | ITM20 | ITM15 | ITM10 | ITM5 | ATM | OTM5 | OTM10 | OTM15 | OTM20 |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-22 | call | +423 | +463 | +368 | +178 | -17 | -295 | -168 | -53 | strike not collected |
| 2026-10-27 | put | +745 | +610 | +730 | +700 | +542 | +187 | -18 | -11 | -11 |
| 2026-10-29 | call | +509 | +499 | +439 | +369 | +179 | -124 | -65 | -23 | -18 |
| 2026-10-30 | call | -183 | -378 | -323 | -588 | -773 | -450 | -278 | -218 | strike not collected |
| 2026-11-02 | put | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars |
| 2026-11-03 | put | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars |
| 2026-11-06 | put | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars |

Market check, every forward day with minute bars, signal or not: mean exit-A P&L of buying each option ($0.09 fee; negative = the market charged more than the option paid on these days).

| Side | ITM20 | ITM15 | ITM10 | ITM5 | ATM | OTM5 | OTM10 | OTM15 | OTM20 |
|---|---|---|---|---|---|---|---|---|---|
| call | -37 (5) | -161 (6) | -173 (6) | -243 (6) | -230 (6) | -186 (6) | -109 (5) | -63 (5) | -13 (3) |
| put | +116 (3) | -82 (5) | -38 (5) | -39 (6) | -86 (6) | -117 (6) | -73 (6) | -42 (6) | -28 (5) |

## Caveats

- **Note added after the first run (not in the pre-registration):** the skew factors for OTM10, OTM15, OTM20 are above 2. On the calm calibration days the normal model prices those strikes near zero while the market charges at least the $0.05 tick plus a fat-tail premium, so the ratio is large; multiplying the much higher model prices of volatile 2021-2022 days by it overstates what those options would have cost. Treat the OTM10, OTM15, OTM20 cells of every variant that uses f (a, b, d and the a_ rows except a_no_skew) as unreliable. a_no_skew and (c) use f = 1, which underprices the same strikes, so the truth for them lies between and this model cannot settle it.
- The model is calibrated on a few weeks of 2026 prices; 2021-2022 volatility and option pricing were different. Variants (b)-(d) and the cost rows show how much the answer depends on that.
- The same $0.10 half-spread is charged at every strike. Real spreads are wider in the money, and for cheap out-of-the-money options the $0.05 tick is a large share of the price.
- Robinhood bars may be trades or marks, and the forward sample is a handful of days.
- Nothing here is a trading recommendation.
