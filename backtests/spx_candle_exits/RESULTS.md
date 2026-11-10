# Early exits vs holding to the close for the 15:50 strong-body signal

Pre-registration `preregistration/spx_candle_exit_rules.md` (SHA-256 `db034c5c3b43dc14…`). Rebuilt by `backtests/spx_candle_exits/exits.py`. Descriptive, with one pre-stated criterion. **Research, not a trading recommendation.**

Rules watch the SPX one-minute closes 15:51-15:58; when one fires, the option is sold at the next minute's open (a one-minute delay). A rule that never fires holds to settlement (rule H).

| Rule | Exits when |
|---|---|
| H | hold to the 16:00 settlement |
| S3 | stop 3 points against |
| S5 | stop 5 points against |
| S8 | stop 8 points against |
| T5 | take profit 5 points in favour |
| T10 | take profit 10 points in favour |
| B5_10 | stop 5 against or take profit 10 in favour |

## The criterion (ITM10, variant (a), $0.09 fee)

Better than holding only if mean d (rule minus hold) > 0 with Newey-West t > 2.64, and mean d > 0 in variants (b) and (c) too.

| Rule | Mean d vs hold (a) | t | d > 0 in (b) | d > 0 in (c) | Verdict |
|---|---|---|---|---|---|
| S3 | -79.32 | -3.35 | no | no | no evidence that it beats holding |
| S5 | -55.06 | -2.80 | no | no | no evidence that it beats holding |
| S8 | -29.54 | -2.15 | no | no | no evidence that it beats holding |
| T5 | -82.29 | -2.78 | no | no | no evidence that it beats holding |
| T10 | -64.72 | -2.89 | no | no | no evidence that it beats holding |
| B5_10 | -103.56 | -3.79 | no | no | no evidence that it beats holding |

## Modelled 2021-2026 (644 strong-body days, 2021-01-06 .. 2026-10-19), a model, not observed P&L

### ITM10, variant (a) calibrated (headline)

| Rule | Fired | Mean P&L ($0.09) | t | Mean P&L ($0.74) | Profitable | Median | 5th pct | Worst | Return on premium | d vs hold | t (d) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H | 0% | +166.08 | 4.25 | +165.43 | 54% | +87.55 | -1,186.06 | -3,601.34 | +15% | — | — |
| S3 | 51% | +86.76 | 2.65 | +85.78 | 38% | -313.47 | -694.60 | -1,191.94 | +7% | -79.32 | -3.35 |
| S5 | 35% | +111.02 | 3.14 | +110.14 | 46% | -110.28 | -823.02 | -1,480.76 | +10% | -55.06 | -2.80 |
| S8 | 20% | +136.54 | 3.45 | +135.77 | 50% | +20.21 | -1,037.42 | -1,480.76 | +12% | -29.54 | -2.15 |
| T5 | 44% | +83.79 | 3.23 | +82.86 | 63% | +341.35 | -1,119.55 | -3,601.34 | +9% | -82.29 | -2.78 |
| T10 | 19% | +101.36 | 3.39 | +100.58 | 56% | +131.02 | -1,186.06 | -3,601.34 | +10% | -64.72 | -2.89 |
| B5_10 | 51% | +62.52 | 2.34 | +61.54 | 48% | -42.48 | -810.27 | -1,480.76 | +6% | -103.56 | -3.79 |

### ITM20, variant (a) calibrated

| Rule | Fired | Mean P&L ($0.09) | t | Mean P&L ($0.74) | Profitable | Median | 5th pct | Worst | Return on premium | d vs hold | t (d) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H | 0% | +162.21 | 3.89 | +161.56 | 56% | +124.98 | -1,638.61 | -4,207.47 | +8% | — | — |
| S3 | 51% | +85.04 | 2.45 | +84.05 | 40% | -331.49 | -823.27 | -1,643.19 | +4% | -77.17 | -2.86 |
| S5 | 35% | +107.92 | 2.87 | +107.04 | 48% | -64.75 | -986.66 | -1,643.19 | +5% | -54.30 | -2.34 |
| S8 | 20% | +130.04 | 3.04 | +129.27 | 52% | +49.82 | -1,264.57 | -1,815.17 | +6% | -32.17 | -1.78 |
| T5 | 44% | +85.90 | 2.91 | +84.97 | 64% | +401.75 | -1,495.40 | -4,207.47 | +4% | -76.31 | -2.48 |
| T10 | 19% | +96.92 | 2.95 | +96.14 | 58% | +149.57 | -1,638.61 | -4,207.47 | +5% | -65.30 | -2.87 |
| B5_10 | 51% | +59.86 | 2.04 | +58.88 | 50% | -7.55 | -977.83 | -1,643.19 | +3% | -102.35 | -3.42 |

### ATM, variant (a) calibrated

| Rule | Fired | Mean P&L ($0.09) | t | Mean P&L ($0.74) | Profitable | Median | 5th pct | Worst | Return on premium | d vs hold | t (d) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H | 0% | +154.63 | 4.96 | +153.98 | 42% | -98.05 | -583.35 | -2,942.87 | +45% | — | — |
| S3 | 51% | +96.89 | 3.54 | +95.91 | 31% | -162.37 | -447.46 | -1,018.94 | +27% | -57.74 | -3.41 |
| S5 | 35% | +116.60 | 4.12 | +115.72 | 37% | -146.65 | -496.52 | -1,313.68 | +34% | -38.03 | -2.64 |
| S8 | 20% | +138.59 | 4.42 | +137.82 | 40% | -122.56 | -553.94 | -1,313.68 | +41% | -16.03 | -1.69 |
| T5 | 44% | +50.84 | 3.24 | +49.91 | 56% | +106.12 | -542.68 | -2,942.87 | +26% | -103.79 | -3.95 |
| T10 | 19% | +79.85 | 3.92 | +79.08 | 45% | -74.55 | -570.67 | -2,942.87 | +30% | -74.77 | -3.49 |
| B5_10 | 51% | +58.14 | 3.21 | +57.16 | 39% | -131.32 | -482.29 | -1,313.68 | +23% | -96.49 | -4.12 |

### Mean P&L per contract ($0.09) in every variant

**ITM10**

| Variant | H | S3 | S5 | S8 | T5 | T10 | B5_10 |
|---|---|---|---|---|---|---|---|
| a_calibrated | +166 | +87 | +111 | +137 | +84 | +101 | +63 |
| b_constant_vol | +242 | +110 | +139 | +179 | +146 | +174 | +88 |
| c_realized_move_fair | +158 | +74 | +91 | +115 | +62 | +88 | +39 |
| a_half_spread_0.05 | +171 | +94 | +118 | +143 | +91 | +107 | +70 |
| a_half_spread_0.20 | +156 | +72 | +98 | +125 | +69 | +89 | +47 |
| a_no_skew | +171 | +90 | +115 | +141 | +85 | +104 | +65 |

**ITM20**

| Variant | H | S3 | S5 | S8 | T5 | T10 | B5_10 |
|---|---|---|---|---|---|---|---|
| a_calibrated | +162 | +85 | +108 | +130 | +86 | +97 | +60 |
| b_constant_vol | +192 | +87 | +111 | +134 | +110 | +125 | +61 |
| c_realized_move_fair | +186 | +90 | +114 | +138 | +99 | +117 | +62 |
| a_half_spread_0.05 | +167 | +93 | +115 | +136 | +93 | +103 | +67 |
| a_half_spread_0.20 | +152 | +70 | +94 | +118 | +72 | +85 | +45 |
| a_no_skew | +172 | +91 | +115 | +139 | +90 | +104 | +65 |

**ATM**

| Variant | H | S3 | S5 | S8 | T5 | T10 | B5_10 |
|---|---|---|---|---|---|---|---|
| a_calibrated | +155 | +97 | +117 | +139 | +51 | +80 | +58 |
| b_constant_vol | +261 | +159 | +192 | +229 | +120 | +175 | +124 |
| c_realized_move_fair | +83 | +33 | +38 | +57 | -17 | +8 | -20 |
| a_half_spread_0.05 | +160 | +104 | +123 | +144 | +58 | +86 | +65 |
| a_half_spread_0.20 | +145 | +82 | +104 | +127 | +36 | +68 | +44 |
| a_no_skew | +143 | +88 | +106 | +127 | +50 | +76 | +55 |

### Subperiods, variant (a), mean P&L per contract ($0.09)

| Period | Strike | H | S3 | S5 | S8 | T5 | T10 | B5_10 |
|---|---|---|---|---|---|---|---|---|
| 2021_2022 (n=216) | ITM10 | +317 | +135 | +175 | +243 | +158 | +209 | +116 |
| 2021_2022 (n=216) | ITM20 | +318 | +131 | +167 | +229 | +170 | +210 | +109 |
| 2021_2022 (n=216) | ATM | +277 | +135 | +167 | +223 | +100 | +158 | +96 |
| 2023_2026 (n=428) | ITM10 | +90 | +62 | +79 | +83 | +46 | +47 | +35 |
| 2023_2026 (n=428) | ITM20 | +84 | +62 | +78 | +80 | +44 | +40 | +35 |
| 2023_2026 (n=428) | ATM | +93 | +78 | +91 | +96 | +26 | +40 | +39 |

### Self-check

Rule H reproduces the strike ladder's mean P&L at ITM10, ITM20 and ATM in all six variants (largest difference $0.000000). Part 1's rule H matches the strike ladder's exit A on 29 forward rows. Index closes missing in D1 among the checked minutes: 0.

## Real prices on forward days (a handful of days; supports no conclusion)

**F2_1m_1550_strong_body (headline)**: total P&L ($0.09), wins / trades, early exits taken

| Strike | H | S3 | S5 | S8 | T5 | T10 | B5_10 |
|---|---|---|---|---|---|---|---|
| ITM10 | +1,214 (3/4, 0 early) | +592 (3/4, 1 early) | +592 (3/4, 1 early) | +592 (3/4, 1 early) | +1,591 (4/4, 2 early) | +1,214 (3/4, 0 early) | +592 (3/4, 1 early) |
| ITM20 | +1,494 (3/4, 0 early) | +642 (3/4, 1 early) | +642 (3/4, 1 early) | +642 (3/4, 1 early) | +1,866 (4/4, 2 early) | +1,494 (3/4, 0 early) | +642 (3/4, 1 early) |
| ATM | -69 (2/4, 0 early) | -21 (2/4, 1 early) | -21 (2/4, 1 early) | -21 (2/4, 1 early) | +553 (3/4, 2 early) | -69 (2/4, 0 early) | -21 (2/4, 1 early) |

**F1_1m_15:50**: total P&L ($0.09), wins / trades, early exits taken

| Strike | H | S3 | S5 | S8 | T5 | T10 | B5_10 |
|---|---|---|---|---|---|---|---|
| ITM10 | +743 (4/6, 0 early) | +121 (4/6, 1 early) | +121 (4/6, 1 early) | +121 (4/6, 1 early) | +1,121 (5/6, 2 early) | +743 (4/6, 0 early) | +121 (4/6, 1 early) |
| ITM20 | +1,662 (4/5, 0 early) | +809 (4/5, 1 early) | +809 (4/5, 1 early) | +809 (4/5, 1 early) | +2,034 (5/5, 2 early) | +1,662 (4/5, 0 early) | +809 (4/5, 1 early) |
| ATM | -455 (3/6, 0 early) | -407 (3/6, 1 early) | -407 (3/6, 1 early) | -407 (3/6, 1 early) | +168 (4/6, 2 early) | -455 (3/6, 0 early) | -407 (3/6, 1 early) |

Per-day rows: `data/spx_1549/forward/exits_forward_log.csv`.

ITM10, headline signal, P&L by day ($0.09; `@HH:MM` = sold at that minute's open):

| Date | Side | H | S3 | S5 | S8 | T5 | T10 | B5_10 |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 | call | +368 | +368 | +368 | +368 | +368 | +368 | +368 |
| 2026-10-27 | put | +730 | +730 | +730 | +730 | +395 @15:57 | +730 | +730 |
| 2026-10-29 | call | +439 | +439 | +439 | +439 | +439 | +439 | +439 |
| 2026-10-30 | call | -323 | -945 @15:57 | -945 @15:57 | -945 @15:57 | +390 @15:54 | -323 | -945 @15:57 |
| 2026-11-02 | put | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars |
| 2026-11-03 | put | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars |
| 2026-11-06 | put | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars | no minute option bars |

## Notes on reading the plan (disclosed)

- Part 2 path: checks use the D1 closes of the bars beginning 15:51..15:58 and the sale uses the D1 open of the next bar (15:52..15:59), as the plan says. D1 bars are the CFD, not SPX.
- Part 1: a forward day whose official close is not yet published (provisional) is left out of every total, for every rule, even when the rule exited early and the settlement does not matter. This keeps each rule's set of days identical to rule H's, as in the strike ladder.
- Part 1 uses both forward signals, as the strike ladder did; F2 is the headline. Index bars come from the Robinhood SPX one-minute bars (live_*/spx_1m.json, else the d2 chunk files), real bars only.
- Part 1 sale price: the contract's 15:52..15:59 one-minute open with gap-fill bars discarded; an open of 0 is allowed (the plan dropped 'above 0' and floors proceeds at 0).
- Return on premium and the share profitable use the $0.09 fee, as in the strike ladder.

## Caveats

- Part 1 has only a handful of days and supports no conclusion. Part 2 is a model, not observed P&L.
- The model prices an early exit with the entry's volatility and the entry strike's skew factor, a $0.10 half-spread and a one-minute delay. Real exits in a fast move can be worse: wider spreads, slippage, and quotes that move during the minute.
- The index path is a CFD (Dukascopy US500) to 15:59, standing in for SPX and its settlement, as in the strike ladder.
- Nothing here is a trading recommendation.
