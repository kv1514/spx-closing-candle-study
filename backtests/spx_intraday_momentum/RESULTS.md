# Intraday momentum on D1 and the 15:50 candle trade

Rebuilt by `backtests/spx_intraday_momentum/momentum.py` from the locked plan `preregistration/spx_intraday_momentum.md` (SHA-256 `fbe4ca6028757b80...`); do not edit by hand. Research only.

- D1 is the Dukascopy US500 CFD's one-minute **bid candles**, not the index. The "16:00" price is the close of the 15:59 bar, **not the official settlement**.
- Part A is an **adapted replication** of Gao-Han-Li-Zhou (2018) and Baltussen-Da-Lammers-Martens (2021): log returns, a CFD, the 15:59 close, the prior close as the anchor.
- 2013-2020 lies **inside BDLM's sample** (to May 2020), on a different instrument; only 2021-2026 is out of sample for both papers.
- **2021-2026 was not blind for related momentum signals**: the 09:30-anchored day-so-far signal (P1, F4_day_so_far) is known to have failed on 2021-2026, and the 15:30-16:00 target contains the 15:49-15:59 target studied before.
- Part B's discovery is **retrospective, model-priced selection**: 2013-2020 trades are priced with constants calibrated on 2026 quotes. **Part B and Part C P&L comes from a model** (strikes.py), not from real prices.
- Nothing here is a trading recommendation.

## Part A: adapted replication on D1, 2013-04-01 .. 2026-10-20

**Primary (r_last on r_rod): did not replicate on D1 2013-2026.** Slope x100 +1.567 (t 1.02, p 0.3057), n 3238, R² 0.0030. Criterion: b > 0 with t >= 2.0 (the t-statistic decides). BDLM's ES value is about 6.2.

**Secondary: not shown stronger on high-volatility days (secondary, uncorrected).** d (H x r_rod) +0.002 (t 0.13, p 0.8968), n 3134, R² 0.0001; 3174 days with H defined, 1057 high-volatility days.

Descriptive (no verdicts). Slopes x100:

| Sample | n | Slope x100 | t | p | R² |
|---|---|---|---|---|---|
| r_rod, 2013-2020 | 1802 | +2.866 | 1.16 | 0.2466 | 0.0086 |
| r_rod, 2021-2026 | 1436 | -0.173 | -0.18 | 0.8579 | 0.0000 |
| r_rod, 2013 | 134 | +5.850 | 2.12 | 0.0344 | 0.0396 |
| r_rod, 2014 | 195 | +3.880 | 1.75 | 0.0809 | 0.0255 |
| r_rod, 2015 | 241 | +3.027 | 1.84 | 0.0654 | 0.0137 |
| r_rod, 2016 | 249 | -0.480 | -0.33 | 0.7444 | 0.0005 |
| r_rod, 2017 | 243 | -0.826 | -0.39 | 0.6992 | 0.0010 |
| r_rod, 2018 | 245 | +4.304 | 0.95 | 0.3397 | 0.0163 |
| r_rod, 2019 | 246 | -0.579 | -0.28 | 0.7765 | 0.0006 |
| r_rod, 2020 | 249 | +3.448 | 0.76 | 0.4497 | 0.0101 |
| r_rod, 2021 | 250 | -4.064 | -1.85 | 0.0639 | 0.0208 |
| r_rod, 2022 | 249 | +1.609 | 0.96 | 0.3390 | 0.0039 |
| r_rod, 2023 | 246 | +1.411 | 0.93 | 0.3512 | 0.0026 |
| r_rod, 2024 | 246 | -2.192 | -0.96 | 0.3373 | 0.0055 |
| r_rod, 2025 | 244 | -0.724 | -0.25 | 0.7999 | 0.0011 |
| r_rod, 2026 | 201 | -0.528 | -0.37 | 0.7092 | 0.0007 |
| simple returns | 3238 | +1.587 | 1.04 | 0.2982 | 0.0030 |
| winsorised r_rod (p1-p99) | 3238 | +1.189 | 1.08 | 0.2812 | 0.0013 |
| GHLZ r_first | 3236 | +1.517 | 0.57 | 0.5673 | 0.0014 |
| GHLZ r_12 | 3204 | +9.510 | 1.30 | 0.1947 | 0.0043 |

- GHLZ, both: r_first x100 +1.364 (t 0.53, p 0.5985), n 3156, R² 0.0054; r_12 x100 +9.238 (t 1.26, p 0.2066), n 3156, R² 0.0054.
- Decomposition: r_on x100 -0.101 (t -0.04, p 0.9644), n 3230, R² 0.0008; r_day x100 +1.107 (t 0.80, p 0.4223), n 3230, R² 0.0008.
- R² in sample 0.0030; out of sample (expanding, >= 500 days, vs the historical mean) -0.0089 over 2738 forecasts.

Timing returns (bps a day; flat days count 0) against always-long on the same days:

| Rule | Days | Traded | Mean bps | NW t | Hit | Annualised bps | Long mean | Long t | Long hit |
|---|---|---|---|---|---|---|---|---|---|
| eta(r_rod) | 3238 | 3238 | +0.63 | 1.24 | 49.8% | +160 | -0.59 | -1.23 | 49.8% |
| eta(r_first) | 3236 | 3236 | -0.17 | -0.32 | 48.8% | -42 | -0.61 | -1.27 | 49.7% |
| eta(r_first, r_12) | 3156 | 1600 | +0.37 | 0.97 | 49.7% | +92 | -0.63 | -1.27 | 49.7% |
| eta(r_first, r_rod) | 3236 | 2434 | +0.23 | 0.51 | 49.1% | +59 | -0.61 | -1.27 | 49.7% |

Days on which a quantity is undefined (they leave only the tests that need it): r_first 51, r_12 83, r_rod 49, r_on 57, r_day 9, r_last 0, rv_fh 13 (of 3287).

## Part B: does momentum add to the F2 trade? (model P&L, ITM10, $0.09)

**Discovery 2013-04-01 .. 2020-12-31 (frozen in `partb_selection.json`): pick = none.** Eligible: mean d_k > 0 with two-sided normal p <= 0.0125 (variant (a), ITM10, $0.09, per-day difference to R0 over the paired days, HAC lag 5, n >= 30), mean d_k > 0 in 2013-04-01..2016-12-31 and in 2017-01-01..2020-12-31, and the index version's mean difference > 0. Pick: the eligible rule with the highest t; a tie goes to the lower rule number. Menu: R1-R4.

| Rule | Kept | Skipped | Mean kept | Mean skipped | Mean d $/day | t | p | 2013-16 d | 2017-20 d | Index d bps | Eligible |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 905 | 0 | +133.21 | — | +0.00 | — | — | +0.00 | +0.00 | +0.000 | — |
| R1 | 490 | 415 | +198.58 | +56.02 | -12.65 | -1.39 | 0.1658 | +1.27 | -24.45 | -0.320 | no |
| R2 | 471 | 434 | +202.18 | +58.36 | -13.78 | -1.44 | 0.1495 | +1.39 | -26.64 | -0.327 | no |
| R3 | 376 | 529 | +252.84 | +48.18 | -13.87 | -1.37 | 0.1716 | +1.05 | -26.51 | -0.378 | no |
| R4 | 707 | 198 | +149.78 | +74.04 | -7.98 | -1.06 | 0.2898 | +5.86 | -19.70 | -0.200 | no |
| R5 | 1820 | 0 | +109.67 | — | +42.93 | 2.51 | 0.0121 | +23.35 | +59.48 | +0.413 | — |

**Reproduction check (2021-2026): passed.** F2 trades 644 (expected 644); variant (a) mean 166.0817 (expected 166.08169468395093); variant (c) mean 157.9123 (expected 157.91227664480985).

**Confirmation 2021-01-01 .. 2026-10-20: no momentum rule improved F2 on 2013-2020.** The confirmation test is not run; the 2021-2026 rows are not a test.

Descriptive, 2013-2020: 1838 paired days, 905 F2 trades, 3 unpriceable R0 days dropped.

| Rule | Kept | Skipped | Mean kept | Mean skipped | Kept profitable | $/day | t | $/day at $0.74 | d $/day | d t | d (c) | d index bps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 905 | 0 | +133.21 | — | 49.4% | +65.59 | 3.22 | +65.27 | +0.00 | — | +0.00 | +0.000 |
| R1 | 490 | 415 | +198.58 | +56.02 | 52.2% | +52.94 | 2.83 | +52.77 | -12.65 | -1.39 | -4.41 | -0.320 |
| R2 | 471 | 434 | +202.18 | +58.36 | 53.9% | +51.81 | 2.85 | +51.64 | -13.78 | -1.44 | -4.66 | -0.327 |
| R3 | 376 | 529 | +252.84 | +48.18 | 55.3% | +51.72 | 2.85 | +51.59 | -13.87 | -1.37 | -3.56 | -0.378 |
| R4 | 707 | 198 | +149.78 | +74.04 | 51.1% | +57.61 | 3.00 | +57.36 | -7.98 | -1.06 | -8.39 | -0.200 |
| R5 | 1820 | 0 | +109.67 | — | 49.3% | +108.60 | 3.54 | +107.95 | +42.93 | 2.51 | +23.64 | +0.413 |

Descriptive, 2021-2026 (not a test): 1446 paired days, 644 F2 trades, 0 unpriceable R0 days dropped.

| Rule | Kept | Skipped | Mean kept | Mean skipped | Kept profitable | $/day | t | $/day at $0.74 | d $/day | d t | d (c) | d index bps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 644 | 0 | +166.08 | — | 53.7% | +73.97 | 4.20 | +73.68 | +0.00 | — | +0.00 | +0.000 |
| R1 | 312 | 332 | +217.22 | +118.02 | 56.4% | +46.87 | 3.66 | +46.73 | -27.10 | -2.09 | -26.10 | -0.383 |
| R2 | 315 | 329 | +184.64 | +148.31 | 54.3% | +40.22 | 3.09 | +40.08 | -33.74 | -2.63 | -31.88 | -0.491 |
| R3 | 225 | 419 | +210.59 | +142.18 | 56.9% | +32.77 | 2.98 | +32.67 | -41.20 | -2.80 | -39.66 | -0.579 |
| R4 | 458 | 186 | +190.44 | +106.09 | 54.6% | +60.32 | 3.98 | +60.11 | -13.65 | -1.37 | -16.18 | -0.213 |
| R5 | 1440 | 0 | +75.91 | — | 49.6% | +75.59 | 2.99 | +74.94 | +1.62 | 0.09 | -14.61 | -0.204 |

R5 (add sign(r_rod) trades on non-F2 days) is reported but cannot be picked.

## Part C: dealer gamma (net gamma proxy from OPRA open interest)

**C1: not supported.** d (N x r_rod) +0.022 (t 0.95, p 0.3411), n 3238, R² 0.0044.

**C2: not supported.** g +169.113 (t 2.18, p 0.0294), n 1549, R² 0.0054; index version g +3.130 (t 2.54, p 0.0111), n 1549, R² 0.0083.

Share of negative-gamma days (N = 1) by year: 2013 12.8% (149), 2014 22.4% (201), 2015 40.0% (245), 2016 29.5% (251), 2017 11.3% (247), 2018 40.7% (248), 2019 19.7% (249), 2020 29.1% (251), 2021 17.5% (251), 2022 75.2% (250), 2023 38.3% (248), 2024 23.3% (249), 2025 31.2% (247), 2026 25.9% (201).

- table7 slope on N1 days: slope x100 +2.299 (t 1.05), n 995.
- table7 slope on N0 days: slope x100 +0.102 (t 0.14), n 2243.
- Table 8 form (NGE* per standard deviation 275,906): interaction -0.028 (t -1.63, p 0.1030), n 3238, R² 0.0100.
- Puts only: interaction -0.025 (t -3.16, p 0.0016), n 3238, R² 0.0096.
- Term structure (VIX9D/VIX/VIX3M): sign agrees with the VIX version on 99.5% of 3287 days; C1 d +0.022 (t 0.97).
- 2013-2020: C1 d +0.045 (t 1.26, n 1802); C2 g +239.71 (t 1.83, n 905).
- 2021-2026: C1 d -0.010 (t -0.57, n 1436); C2 g +83.65 (t 0.96, n 644).
- F2 trades by Part B's frozen rule (R0 (no rule was picked)) and N: N=1: kept 495 (+261.95), skipped 0 (—); N=0: kept 1054 (+92.83), skipped 0 (—).

Data checks: format passed (3287 files, median SPXW contracts 12,415); budget passed (logged $84.29, open interest $34.55, days not yet downloaded 0, days logged without open interest 0); prior-day inputs passed; coverage passed (3287 of 3287 days, 100.0%). Days on the 09:31-10:01 fallback: 1.

Counts: contracts_before_cutoff 51008966, contracts_excluded_settled_before_cutoff 277856, contracts_usable 51008966, oi_records 51008966, records 51008966.

Caveats: the positioning (dealers long all calls, short all puts) is assumed, not observed; open interest misses positions opened and closed the same day, most 0DTE trading since 2022; one VIX volatility ignores the skew and the term structure.

## Implementation choices where the plan left room

- Timing rules: a predictor x > 0 is long and x <= 0 short, as eta(x); a two-signal rule trades only when both give the same side, else it is flat (0). Hit rate = share of traded days with a positive return.
- R5 (descriptive): an added trade that cannot be priced in variant (a) is missing for R5 only; the paired days are set by R0 alone.
- Part C conflicts: two records with the same (ts_recv, sequence) and different quantities exclude the contract wherever they occur before the cutoff, not only at the last key. Identical duplicates are kept once.
- Part C quantities: empty = missing; 2147483647 and 9223372036854775807 (int32 and int64 maxima) = undefined sentinel; negative; or not an integer: each excludes the contract and is counted.
- Part C symbols: a root other than SPX or SPXW, or a strike of 0, counts as not parsing as an OSI code.
- Part C format check: 'distinct SPXW contracts with open interest' = SPXW contracts with a usable value before the 15:30 cutoff (after the last-record, conflict and quantity rules), median over day files in 2016-01-01..2026-10-20.
- Part C budget check (check 2): momentum.py does not call Databento. The spend log must exist and the pull must be finished: every D1 day has a saved file, or its final window was logged by tools/databento_spx_oi.py as '(no open interest in this window)' (the full-day window before 2023-03-28; from then both the pre-open and the 09:31-10:01 fallback windows). Then the re-quoted remaining cost is $0 and the gate is the logged total (every schema) <= $100. An unfinished pull is 'not run (download incomplete)'.
- Part C order: budget, then format (parsing only), then the prior-day inputs (official closes, VIX, VIX9D, VIX3M files; a missing or malformed file is 'not run'), and only then gamma, then coverage.
- Part C hash check (check 5): a failure stops partc with an error and writes nothing.
- Part C descriptive Table-8 and puts-only forms use NGE* divided by its standard deviation on the regression sample (numerical scaling; the coefficient is per one standard deviation). The puts-only proxy -100 x sum(puts) gamma x OI is never positive, so it is reported in the Table-8 form.
- Part C term structure: tau = T x 365 calendar days; total variance sigma^2 x tau interpolated linearly between 9, 30 and 93 days; sigma held flat outside.
- Part C t-1 for day t is the latest date in Cboe's SPX close file before t.
