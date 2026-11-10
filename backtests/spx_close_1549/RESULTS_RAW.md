# SPX 15:49 close study: raw results

Generated 2026-10-21T19:37:13+00:00 by `backtests/spx_close_1549/analysis.py` from the binding pre-registration `preregistration/spx_1549_close.md`. Seed 20261021, 10000 bootstrap draws. Machine-generated: every number below is read from `results.json`.

## Verdicts (pass rule applied mechanically)

Conditions are yes / no / not evaluable. A strategy is a candidate only if both are yes.

| strategy | cond 1 (D1 premise) | cond 2 (D2 mean P&L > 0 with CI, base costs) | D2 days | D2 mean $/trade | verdict |
|---|---|---|---|---|---|
| S1 | not evaluable: D1 realized move (regression on rv, 2023-01..pre-D2) - D2 implied straddle: bootstrap 95% CI over D2 days > 0 | not evaluable | 1 | -353.18 | **FAIL by rule; D2 test not run (1 of ~35 planned days)** |
| S2 | yes: P3 Holm p < 0.05 and same sign in 2023-2026 (entry 15:51) | not evaluable | 1 | -300.09 | **FAIL by rule; D2 test not run (1 of ~35 planned days)** |
| S2_alt | no: sensitivity: P1 (largest abs t among predictors known at t0) Holm p < 0.05 and same sign in 2023-2026 (entry 15:49) | not evaluable | 1 | -58.09 | **FAIL by rule; D2 test not run (1 of ~35 planned days)** |
| S3 | not evaluable: same size premise as S1 | not evaluable | 1 | -256.18 | **FAIL by rule; D2 test not run (1 of ~35 planned days)** |

Reading the verdicts:

- S1: cond 1 not evaluable (fewer than 2 usable D2 days); cond 2 not evaluable (1 of ~35 planned D2 days; no CI possible).
- S2: cond 2 not evaluable (1 of ~35 planned D2 days; no CI possible).
- S2_alt: cond 1 not met; cond 2 not evaluable (1 of ~35 planned D2 days; no CI possible).
- S3: cond 1 not evaluable (fewer than 2 usable D2 days); cond 2 not evaluable (1 of ~35 planned D2 days; no CI possible).
- Condition 2 was decided on 1 of the ~35 planned D2 days, so the option P&L test did not run; a negative mean on that day is not evidence that the option P&L is negative in general.
- Condition 1 for S1/S3 is not evaluable: 1 usable D2 day: the D2 side of the bootstrap cannot be resampled, so a CI over D2 days does not exist (a CI from the D1 refit alone would only measure model uncertainty around one fixed implied value). The 22-day 10-minute stand-in (exploratory (iv)) does not support it either.

## Data

- D1: 3307 usable days, 2013-02-28 to 2026-10-20 (primary rule `keep`). Weekday files by reason: {'usable': 3307, 'delayed_clock_feed': 377, 'nyse_holiday': 127, 'missing_bar_1519_1559': 80, 'half_day_calendar': 29, 'half_day_data_only': 12, 'no_ticks_in_session': 5}. weekends (never downloaded) and NYSE holidays are not trading days; delayed_clock_feed = 2011-09-19..2013-02-26 dropped by build_d1.py (feed clock ~15-20 min late).
- D1 strict-rule sensitivity: 2933 days. Days without a 09:30 bar: 9 (P1, P4 undefined); without a 10:00 bar: 2.
- D1 validation gate: corr(r_close) SPY bars_1m 0.9976 (n 21), Robinhood SPX 0.9744 (n 22) -> accepted = yes. Recomputed here vs D2 SPX minute bars: corr 0.9744 (n 22).
- D2: 34 sessions collected (2026-09-02..2026-10-20); SPX bars 13294 (4692 interpolated, discarded); option bars 223080 (212940 interpolated, discarded).
  - dropped, no real SPX minute bars: 12 (2026-09-02, 2026-09-03, 2026-09-04, 2026-09-08, 2026-09-09, 2026-09-10, 2026-09-11, 2026-09-14, 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18)
  - dropped, SPX fine but no real option minute bar at 15:49: 21 (2026-09-21, 2026-09-22, 2026-09-23, 2026-09-24, 2026-09-25, 2026-09-28, 2026-09-29, 2026-09-30, 2026-10-01, 2026-10-02, 2026-10-05, 2026-10-06, 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-19)
  - **usable for H3: 1** (2026-10-20). The pre-registration expected about 35.
- P3 sign (15:50 open -> 15:51 open) agrees between D1 and Robinhood SPX on 21 of 22 overlap days.
- Data quality, pre-registered put-call parity check C - P - (S - K) on 1-minute bar opens (strikes ATM +/- 30 with both legs real):
  - 2026-10-20 15:49: SPX open 7710.93, 13 strikes, signed median -0.74, max |dev| 0.82, ATM (7710) dev -0.73; option-implied SPX 7710.19
  - 2026-10-20 15:50: SPX open 7711.31, 13 strikes, signed median -1.56, max |dev| 3.15, ATM (7710) dev -0.01; option-implied SPX 7709.75
  - 2026-10-20 15:51: SPX open 7708.99, 13 strikes, signed median -0.08, max |dev| 2.90, ATM (7710) dev -0.11; option-implied SPX 7708.91
  - Caveat: Robinhood option bar opens look like sampled prints/marks rather than clean mids. If they are prints, the $0.10 half-spread may partly double-count the cost; the parity gap at 15:49-15:50 shows the call and put levels are not mutually consistent there (bar timing itself lines up: see audits/DISPOSITION.md finding 4). For a near-delta-neutral straddle the effect on S1/S3 is close to zero.

## Decisions, interpretations and deviations

- **D1-day-rule** **[DEVIATION from the literal pre-registration wording]** (this analysis; relabelled from 'interpretation' to 'deviation' after audit finding 7): The pre-registration says 'days with any missing bar 15:19-15:59 are dropped'. Primary D1 day set = build_d1.py default `keep`, which treats a run of 1-4 no-update (flat, zero-volume) Dukascopy minutes as a valid carry-forward bar (runs >= 5 or starting 09:30 are missing). This is looser than the literal wording: the strict reading (`keep_strict`: any no-update minute in 15:19-15:59 counts as missing) drops 374 more days (mostly the sparse-feed years 2013-14 and 2017). Kept as primary because it was fixed before any H1/H2 number was computed and switching after seeing both results would itself be a post-hoc choice; the strict reading is reported in full for H1/H2 and gives the same H1/H2 conclusions.
- **S2-best-predictor** (workflow clarification (labelled); zero/undefined handling changed after audit finding 3): S2 'best full-sample D1 t-stat' = the H2 predictor with the largest |Newey-West t| on the full D1 sample (as pre-registered); trade direction: buy the ATM call if sign(t) x P > 0, else (including P = 0) buy the ATM put, as the pre-registration's 'else ATM put' says. If the predictor is undefined (a bar it needs is missing) the day is excluded from the S2 mean, not booked as $0. Look-ahead check: the same selection repeated on D1 dates before the first D2 session is reported next to it.
- **S2-P3-entry** **[DEVIATION forced by the no-look-ahead rule]** (this analysis; S2-alt added after audit finding 3): If P3 is the selected predictor its value is only known at the 15:51 open, so S2 enters at the 15:51 bar open (strike nearest SPX then) instead of the pre-registered t0 = 15:49 ('same entry/exit'). The other reading of the rule (best |t| among the predictors known at t0, i.e. P1/P2/P4, entering at 15:49) is reported next to it as 'S2-alt' with its own pass rule evaluation.
- **lookahead-cutoff** (this analysis; added after audit finding 5 (before: fit ran through 2026-10-20)): The implied-vs-realized model is fitted on D1 days from 2023-01-01 up to the day before the first D2 session collected, so no D2 test day (or any day in the D2 window) is inside the fit that predicts it. Its out-of-sample calibration on D1 days inside the D2 window is reported.
- **evaluability** (this analysis; added after audit findings 1 and 2): Pass-rule conditions are three-valued: yes / no / not evaluable. Condition 1 for S1/S3 needs a bootstrap CI over D2 days, so it is not evaluable with fewer than 2 usable D2 days. Condition 2 requires CIs to be reported, so it is not evaluable with fewer than 2 usable D2 days. A strategy is a candidate only if both are 'yes'; anything else is FAIL, and a FAIL caused by 'not evaluable' is labelled 'D2 test not run'.
- **settlement-gap** (this analysis; added after audit finding 9): The realized-move model is fitted to the D1 move to the 15:59 bar close (16:00:00), while the straddle settles on the SPX official close. In D2 the 15:59-close -> official-close gap averages about 1.3 bps in absolute value (exploratory (iii)), so the model slightly understates the move the option actually pays on; this works against the S1/S3 premise.
- **option-marks** (this analysis; added after audit finding 4): Robinhood option bar opens look like sampled prints/marks, not clean bid-ask mids (bar open is not the previous close; put-call parity is off by up to ~1.6 points at 15:49-15:50 on the one real day). If they are trade prints, adding a $0.10 half-spread may double-count part of the cost; if they are mids it is the right charge. Parity per usable day is reported as a data-quality line.
- **windows** (this analysis (reading of 'every 11-minute window')): 11-minute window starting at bar s = open of bar s to close of bar s+10 (same length as r_close: 15:49:00-16:00:00). The 15:38 window is open 15:38 -> close 15:48. Same-day median uses every available window starting 10:00..15:38 (339 when no bar is missing).
- **strike** (this analysis): Strike nearest SPX = nearest point on the 5-point grid, ties rounded up; the contract must have a real (non-interpolated) 1-minute bar at entry or the day is not usable.
- **fees** (this analysis (reading of '$0.09/contract per side')): Fees are charged per executed trade: entry always; exit only when a leg is sold before expiry (cash settlement is not a trade). Half-spread is added to the entry mark and subtracted from a sale price; settlement value is intrinsic at the SPX official close.
- **S3-trigger** (this analysis (reading of 'any later bar's close ... before 15:59')): S3 / exploratory (i): a leg is sold at multiple x entry mark minus half-spread (floored at 0) if the close of any real bar beginning 15:49..15:58 is >= multiple x entry mark (the 15:49 bar's close at 15:49:59 is later than the 15:49:00 entry).
- **implied-vs-realized** (this analysis (pre-registration says 'ratio and regression'; workflow asked for the regression)): Realized vol to t0 = sqrt(sum of squared 1-minute log changes of bar opens 09:30..15:49, rescaled for missing pairs), from D1 on the D2 date. Model fitted on D1 2023-01-01 .. the day before the first D2 session: |P_end/P_t0 - 1| = a + b*rv (OLS). Predicted move (points) = prediction x SPX at t0; compared with the D2 15:49 ATM straddle mark (C+P open). Pass-rule statistic = mean over usable D2 days of (predicted - implied); 95% CI from a day bootstrap that resamples D1 days (refitting, 20-day moving blocks) and D2 days (iid). The ratio model (sum|r|/sum rv) and the unconditional mean are reported as descriptive alternatives.
- **bootstrap** (this analysis; block length changed 1 -> 20 after audit finding 6): Day-block bootstrap for every D1 resample = circular moving-block bootstrap with blocks of 20 consecutive trading days (keeps volatility clustering), 10000 replications, percentile 95% CI, seed 20261021; the 1-day-block (iid) version is reported as a sensitivity. Samples of D2 trades (<= ~35 days) are resampled iid, since a 20-day block on 22 days would leave almost nothing to resample. For the implied-vs-realized premise the CI must lie above zero under BOTH the 20-day-block and the iid D1 resample (conservative: for the regression the block CI is narrower than the iid one, because the regression score has lag-1 autocorrelation of about -0.76, driven by back-to-back extreme-volatility days).
- **fees-actual** (this analysis; added after the literature review): An extra fee case of $1.13 per contract per side (upper end of Robinhood's actual SPXW fee: contract fee + exchange fee + regulatory, research/SPX_1549_RESEARCH.md section F) is added to the cost grid as a labelled, not pre-registered sensitivity.
- **nw** (this analysis): Newey-West: Bartlett weights, lag 5, p-value from the normal distribution; days where the predictor or target is undefined are dropped from that predictor's series.

## Look-ahead self-check

- PASS P1: entry bar 379 (r_close starts bar 379); masked == full, scrambled-future == full
- PASS P2: entry bar 379 (r_close starts bar 379); masked == full, scrambled-future == full
- PASS P3: entry bar 381 (r_1551 starts bar 381); masked == full, scrambled-future == full
- PASS P4: entry bar 379 (r_close starts bar 379); masked == full, scrambled-future == full
- PASS rv(09:30..15:49 opens): masked at t0 == full
- PASS 2026-10-20: K0 and every S2 variant's strike/direction identical from data truncated at entry

## H1 size (D1)

### primary (`keep`)

| baseline | n | mean abs r_close bps | mean baseline bps | ratio of means | mean ln diff | geo ratio | t | p | boot95 mean ln diff (20-day blocks) | boot95 iid (sensitivity) | share days larger | passes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_vs_1538_1549_window | 3307 | 12.09 | 8.68 | 1.39 | 0.353 | 1.42 | 13.64 | 2.84e-41 | [0.300, 0.409] | [0.304, 0.404] | 0.609 | yes |
| b_vs_same_day_median_window | 3307 | 12.09 | 6.31 | 1.92 | 0.249 | 1.28 | 13.24 | 5.02e-39 | [0.203, 0.295] | [0.211, 0.285] | 0.669 | yes |

### sensitivity (`keep_strict`)

| baseline | n | mean abs r_close bps | mean baseline bps | ratio of means | mean ln diff | geo ratio | t | p | boot95 mean ln diff (20-day blocks) | boot95 iid (sensitivity) | share days larger | passes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_vs_1538_1549_window | 2933 | 12.88 | 9.17 | 1.40 | 0.355 | 1.43 | 13.14 | 2.41e-38 | [0.299, 0.413] | [0.301, 0.408] | 0.612 | yes |
| b_vs_same_day_median_window | 2933 | 12.88 | 6.70 | 1.92 | 0.252 | 1.29 | 12.71 | 4.49e-36 | [0.205, 0.299] | [0.213, 0.291] | 0.671 | yes |

## H2 direction (D1)

### primary (`keep`): full sample

| predictor | target | n | mean bps | NW t | p | Holm p | hit rate | zero-sign days | 2023-26 same sign | passes |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 sign r(09:30 open -> 15:49 open)  intraday momentum | r_close | 3298 | 0.808 | 2.21 | 0.0268 | 0.0805 | 0.504 | 1 | no | no |
| P2 sign r(15:19 open -> 15:49 open)  last-30-minute momentum | r_close | 3307 | -0.009 | -0.03 | 0.9770 | 0.9770 | 0.500 | 14 | yes | no |
| P3 sign r(15:50 open -> 15:51 open)  first reaction to the 15:50 imbalance | r_1551 | 3307 | 0.998 | 4.09 | 4.36e-05 | 1.75e-04 | 0.526 | 39 | yes | yes |
| P4 sign r(09:30 open -> 10:00 open)  first half-hour | r_close | 3298 | -0.357 | -1.00 | 0.3168 | 0.6336 | 0.482 | 2 | yes | no |

Largest |NW t|: P3 (t = 4.09).

Subperiods (descriptive): mean bps / NW t / hit rate / n

| predictor | start-2019 | 2020-2022 | 2023-2026 |
|---|---|---|---|
| P1 | 0.779 / 2.35 / 0.512 / 1603 | 2.649 / 2.07 / 0.530 / 750 | -0.602 / -1.21 / 0.471 / 945 |
| P2 | -0.320 / -0.96 / 0.492 / 1610 | 0.754 / 0.76 / 0.520 / 752 | -0.088 / -0.16 / 0.498 / 945 |
| P3 | 0.888 / 3.27 / 0.517 / 1610 | 1.871 / 2.47 / 0.538 / 752 | 0.490 / 1.28 / 0.532 / 945 |
| P4 | -0.103 / -0.32 / 0.503 / 1603 | -0.658 / -0.53 / 0.457 / 750 | -0.549 / -1.07 / 0.468 / 945 |

Weekday (descriptive): mean bps / NW t / hit rate / n

| predictor | Mon | Tue | Wed | Thu | Fri |
|---|---|---|---|---|---|
| P1 | -0.543 / -0.78 / 0.474 / 617 | 0.953 / 1.12 / 0.523 / 686 | 0.901 / 1.03 / 0.500 / 673 | 0.839 / 1.00 / 0.497 / 666 | 1.801 / 1.77 / 0.525 / 656 |
| P2 | 0.964 / 1.34 / 0.535 / 621 | -0.331 / -0.47 / 0.500 / 686 | 0.942 / 1.38 / 0.506 / 678 | -0.976 / -1.41 / 0.480 / 666 | -0.595 / -0.77 / 0.483 / 656 |
| P3 | 1.647 / 2.32 / 0.540 / 621 | 1.460 / 2.56 / 0.534 / 686 | 1.174 / 1.71 / 0.530 / 678 | 0.381 / 0.62 / 0.511 / 666 | 0.346 / 0.54 / 0.515 / 656 |
| P4 | -1.085 / -1.52 / 0.469 / 617 | 0.026 / 0.04 / 0.485 / 686 | 0.225 / 0.25 / 0.483 / 673 | -0.199 / -0.25 / 0.487 / 666 | -0.831 / -1.03 / 0.488 / 656 |

### sensitivity (`keep_strict`): full sample

| predictor | target | n | mean bps | NW t | p | Holm p | hit rate | zero-sign days | 2023-26 same sign | passes |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 sign r(09:30 open -> 15:49 open)  intraday momentum | r_close | 2924 | 0.919 | 2.25 | 0.0243 | 0.0729 | 0.507 | 0 | no | no |
| P2 sign r(15:19 open -> 15:49 open)  last-30-minute momentum | r_close | 2933 | 0.093 | 0.26 | 0.7924 | 0.7924 | 0.502 | 13 | no | no |
| P3 sign r(15:50 open -> 15:51 open)  first reaction to the 15:50 imbalance | r_1551 | 2933 | 1.035 | 3.76 | 1.72e-04 | 6.88e-04 | 0.522 | 26 | yes | yes |
| P4 sign r(09:30 open -> 10:00 open)  first half-hour | r_close | 2924 | -0.405 | -1.02 | 0.3096 | 0.6192 | 0.483 | 2 | yes | no |

Largest |NW t|: P3 (t = 3.76).

S2 predictor (workflow clarification, made before D2 results were computed): **P3**, NW t 4.09, trade sign multiplier +1, entry 15:51. Look-ahead check on D1 dates before 2026-09-02 (n 3273): best = P3 (NW t 4.07), same choice = yes.

S2-alt (sensitivity: largest abs NW t among predictors known at t0 (audit finding 3)): **P1**, NW t 2.21, trade sign multiplier +1, entry 15:49.

## H3 options (D2)

Implied vs realized. Fit on D1 2023-01-03..2026-09-01 (n 911; ends before the first D2 session 2026-09-02): |r_close| = 0.000280 + 0.1348 x rv (R^2 0.168); ratio k = 0.1794; mean |r_close| 11.29 bps.

Out-of-sample calibration on D1 days 2026-09-02..2026-10-20 (n 34, the D2 window): model mean |r_close| 8.82 bps vs realized 6.46 bps (mean rv 44.6 bps vs 63.0 bps in the fit sample).

| date | S0 | rv to t0 (bps) | implied straddle pts | pred regression pts | pred ratio pts | pred uncond. pts | realized abs(S_T - S0) pts |
|---|---|---|---|---|---|---|---|
| 2026-10-20 | 7710.93 | 58.01 | 5.90 | 8.19 | 8.02 | 8.71 | 1.64 |

Pass-rule statistic: **not evaluable** (1 usable D2 day: the D2 side of the bootstrap cannot be resampled, so a CI over D2 days does not exist (a CI from the D1 refit alone would only measure model uncertainty around one fixed implied value)).
Descriptive only, one day: regression pred - implied 2.29 pts (pred/implied 1.388); ratio pred - implied 2.12 pts (pred/implied 1.360); unconditional pred - implied 2.81 pts (pred/implied 1.476).

Per-day option P&L ($ per trade; S1 = 1 straddle, S2 = 1 contract, S3 = 1 call + 1 put):

- 2026-10-20: S0 7710.93, K0 7710, call 3.05, put 2.85, straddle 5.90, 15:59 close 7711.70, official close 7712.57, realized |settle - S0| 1.64; decisions {'K0': 7710.0, 'S2_predictor': 'P3', 'S2_entry_bar': 381, 'S2_predictor_value': -1.0, 'S2_direction': -1, 'S2_strike': 7710.0, 'S2_alt_predictor': 'P1', 'S2_alt_entry_bar': 379, 'S2_alt_predictor_value': 1.0, 'S2_alt_direction': 1, 'S2_alt_strike': 7710.0}
  - S1: straddle 7710 P&L $-353.18
  - S3 call 7715: mark 1.13, sold at 2x = no, P&L $-123.09
  - S3 put 7705: mark 1.23, sold at 2x = no, P&L $-133.09
  - S2: put 7710 at mark 2.90, P&L $-300.09
  - S2_alt: call 7710 at mark 3.05, P&L $-58.09

Cost grid, mean $ per trade (n days) [t 95% CI]:

| cost case | S1 | S2 | S2_alt | S3 |
|---|---|---|---|---|
| hs0.05_fee0.09 | -343.18 (n 1) n/a | -295.09 (n 1) n/a | -53.09 (n 1) n/a | -246.18 (n 1) n/a |
| hs0.05_fee0.74 | -344.48 (n 1) n/a | -295.74 (n 1) n/a | -53.74 (n 1) n/a | -247.48 (n 1) n/a |
| hs0.05_fee1.13 (extra: actual RH fee) | -345.26 (n 1) n/a | -296.13 (n 1) n/a | -54.13 (n 1) n/a | -248.26 (n 1) n/a |
| hs0.10_fee0.09 (base) | -353.18 (n 1) n/a | -300.09 (n 1) n/a | -58.09 (n 1) n/a | -256.18 (n 1) n/a |
| hs0.10_fee0.74 | -354.48 (n 1) n/a | -300.74 (n 1) n/a | -58.74 (n 1) n/a | -257.48 (n 1) n/a |
| hs0.10_fee1.13 (extra: actual RH fee) | -355.26 (n 1) n/a | -301.13 (n 1) n/a | -59.13 (n 1) n/a | -258.26 (n 1) n/a |
| hs0.25_fee0.09 | -383.18 (n 1) n/a | -315.09 (n 1) n/a | -73.09 (n 1) n/a | -286.18 (n 1) n/a |
| hs0.25_fee0.74 | -384.48 (n 1) n/a | -315.74 (n 1) n/a | -73.74 (n 1) n/a | -287.48 (n 1) n/a |
| hs0.25_fee1.13 (extra: actual RH fee) | -385.26 (n 1) n/a | -316.13 (n 1) n/a | -74.13 (n 1) n/a | -288.26 (n 1) n/a |

### Power diagnostic (design arithmetic, not a test; D1 2023-01-03..2026-09-01, n 911)

- S1 straddle payoff SD 6.48 pts (mean payoff 6.38). Days needed for t = 2: +0.25 pt edge: 2684, +0.50 pt edge: 671, +1.00 pt edge: 168. Smallest edge detectable (t = 2) with 35 days: 2.19 pts ($219 per straddle).
- S2 (P3, entry 15:51) payoff SD 4.71 pts; edge over a random-direction ATM option 0.130 pts gross, 0.030 pts after the $0.10 half-spread; days needed for t = 2: 95899. Smallest edge detectable with 35 days: 1.59 pts.
- SD of the payoff is used as the SD of per-trade P&L (entry price varies little relative to it).

## EXPLORATORY (not part of pass/fail)

### (i) OTM 0DTE options at 15:49 reaching 2x/3x/5x at a bar close 15:49..15:58 (n days 1)

| series | n | mean mark | reach 2x | reach 3x | reach 5x | mean $ sell-at-2x-else-hold | mean $ hold |
|---|---|---|---|---|---|---|---|
| call_5 | 1 | 1.13 | 0.00 | 0.00 | 0.00 | -123.09 | -123.09 |
| put_5 | 1 | 1.23 | 0.00 | 0.00 | 0.00 | -133.09 | -133.09 |
| call_10 | 1 | 0.33 | 0.00 | 0.00 | 0.00 | -43.09 | -43.09 |
| put_10 | 1 | 0.48 | 0.00 | 0.00 | 0.00 | -58.09 | -58.09 |
| call_15 | 1 | 0.13 | 0.00 | 0.00 | 0.00 | -23.09 | -23.09 |
| put_15 | 1 | 0.23 | 0.00 | 0.00 | 0.00 | -33.09 | -33.09 |
| call_20 | 1 | 0.01 | 0.00 | 0.00 | 0.00 | -11.09 | -11.09 |
| put_20 | 1 | 0.08 | 0.00 | 0.00 | 0.00 | -18.09 | -18.09 |
| call_25 | 1 | 0.01 | 0.00 | 0.00 | 0.00 | -11.09 | -11.09 |
| put_25 | 1 | 0.08 | 0.00 | 0.00 | 0.00 | -18.09 | -18.09 |
| call_30 | 1 | 0.01 | 0.00 | 0.00 | 0.00 | -11.09 | -11.09 |
| put_30 | 1 | 0.01 | 0.00 | 0.00 | 0.00 | -11.09 | -11.09 |

### (ii) mean |1-minute r| by bar, D1 2023-01-03..2026-10-20 (n 945)

mean over days of |ln(close bar m / close bar m-1)| in bps. Median bar 10:00-15:29 = 2.136 bps. Top 5: 15:50, 15:59, 15:55, 15:54, 15:51.

| bar | mean abs bps | x median bar |
|---|---|---|
| 15:30 | 2.589 | 1.21 |
| 15:31 | 2.193 | 1.03 |
| 15:32 | 2.243 | 1.05 |
| 15:33 | 2.126 | 0.99 |
| 15:34 | 1.980 | 0.93 |
| 15:35 | 2.415 | 1.13 |
| 15:36 | 2.189 | 1.02 |
| 15:37 | 2.154 | 1.01 |
| 15:38 | 2.068 | 0.97 |
| 15:39 | 2.003 | 0.94 |
| 15:40 | 2.343 | 1.10 |
| 15:41 | 2.154 | 1.01 |
| 15:42 | 2.232 | 1.04 |
| 15:43 | 2.067 | 0.97 |
| 15:44 | 2.163 | 1.01 |
| 15:45 | 2.495 | 1.17 |
| 15:46 | 2.274 | 1.06 |
| 15:47 | 2.284 | 1.07 |
| 15:48 | 2.198 | 1.03 |
| 15:49 | 2.172 | 1.02 |
| 15:50 | 5.138 | 2.40 |
| 15:51 | 2.797 | 1.31 |
| 15:52 | 2.460 | 1.15 |
| 15:53 | 2.507 | 1.17 |
| 15:54 | 3.205 | 1.50 |
| 15:55 | 3.604 | 1.69 |
| 15:56 | 2.312 | 1.08 |
| 15:57 | 2.324 | 1.09 |
| 15:58 | 2.266 | 1.06 |
| 15:59 | 4.904 | 2.30 |

### (ii-b) added after the audit: size of selected close bars by year (x that year's median bar 10:00-15:29)

NYSE moved its first imbalance publication from 15:45 to 15:50 on 2019-04-01 (research file).

| year | n days | median bar bps | 15:45 | 15:50 | 15:55 | 15:59 |
|---|---|---|---|---|---|---|
| 2013 | 169 | 1.651 | 1.52 | 1.40 | 1.44 | 2.00 |
| 2014 | 201 | 1.753 | 1.62 | 1.36 | 1.19 | 1.83 |
| 2015 | 245 | 2.303 | 1.56 | 1.36 | 1.42 | 2.31 |
| 2016 | 251 | 2.070 | 1.60 | 1.48 | 1.34 | 2.20 |
| 2017 | 247 | 1.122 | 1.73 | 2.21 | 1.38 | 2.60 |
| 2018 | 248 | 2.677 | 2.22 | 2.03 | 1.56 | 2.21 |
| 2019 | 249 | 1.776 | 1.61 | 1.74 | 2.34 | 2.74 |
| 2020 | 251 | 3.781 | 1.72 | 3.44 | 1.83 | 2.67 |
| 2021 | 251 | 1.872 | 1.45 | 2.71 | 2.00 | 2.72 |
| 2022 | 250 | 3.820 | 1.35 | 2.40 | 1.65 | 1.83 |
| 2023 | 248 | 2.276 | 1.25 | 2.11 | 1.79 | 2.12 |
| 2024 | 249 | 1.848 | 1.17 | 2.41 | 1.94 | 3.02 |
| 2025 | 247 | 2.493 | 1.14 | 2.65 | 1.49 | 1.95 |
| 2026 | 201 | 1.971 | 1.04 | 2.33 | 1.47 | 2.13 |

### (iii) D2 SPX: 15:59-bar close -> official close (n 22)

Mean -0.56 bps, mean |.| 1.26 bps, median |.| 1.03 bps, max |.| 3.30 bps; mean |r_close to official| 8.08 bps (gap / move = 0.16).

| date | 15:59 close | official | gap bps |
|---|---|---|---|
| 2026-09-21 | 7764.22 | 7764.70 | 0.62 |
| 2026-09-22 | 7764.27 | 7764.64 | 0.48 |
| 2026-09-23 | 7708.55 | 7706.03 | -3.27 |
| 2026-09-24 | 7703.83 | 7704.13 | 0.39 |
| 2026-09-25 | 7742.32 | 7743.41 | 1.41 |
| 2026-09-28 | 7684.50 | 7683.69 | -1.05 |
| 2026-09-29 | 7671.85 | 7670.84 | -1.32 |
| 2026-09-30 | 7653.56 | 7651.54 | -2.64 |
| 2026-10-01 | 7668.82 | 7666.45 | -3.09 |
| 2026-10-02 | 7723.49 | 7722.72 | -1.00 |
| 2026-10-05 | 7774.22 | 7773.95 | -0.35 |
| 2026-10-06 | 7819.83 | 7818.93 | -1.15 |
| 2026-10-07 | 7800.26 | 7801.77 | 1.94 |
| 2026-10-08 | 7765.70 | 7765.36 | -0.44 |
| 2026-10-09 | 7811.09 | 7811.54 | 0.58 |
| 2026-10-12 | 7807.79 | 7807.24 | -0.70 |
| 2026-10-13 | 7805.59 | 7805.45 | -0.18 |
| 2026-10-14 | 7721.49 | 7718.94 | -3.30 |
| 2026-10-15 | 7743.88 | 7744.06 | 0.23 |
| 2026-10-16 | 7658.74 | 7659.44 | 0.91 |
| 2026-10-19 | 7691.92 | 7690.73 | -1.55 |
| 2026-10-20 | 7711.70 | 7712.57 | 1.13 |

### (iv) added by this analysis, not pre-registered: S1 with the 10-minute 15:40-bar close as entry (~1 minute after t0)

**10-minute closes are not simultaneous marks; this stand-in neither supports nor refutes the S1/S3 premise.** Max |ATM parity deviation| on these days: 3.60 pts.

- **all days**: n days 22; mean straddle 5.99 pts (7.75 bps) vs mean |official close - S| 5.90 pts (7.63 bps); model-predicted move 9.05 bps; mean P&L $47.09 per straddle at base costs, t95 [-246.04, 340.23], boot95 [-186.54, 355.19], share of days positive 0.41; total $1036.04, largest day 2026-09-30 $2490.82; mean without it $-69.28; median $-51.18.
  Implied vs realized (regression model): mean pred - implied 1.00 pts, boot95 [0.11, 1.80] (iid D1: [-0.10, 1.80]); ratio model 0.43 [-0.30, 1.18]; unconditional 2.75 [1.74, 3.95].
- **parity-filtered (|ATM C - P - (S - K)| <= 0.5 pts (15:40-bar closes vs SPX 15:49-bar close))**: n days 11; mean straddle 5.92 pts (7.65 bps) vs mean |official close - S| 8.41 pts (10.89 bps); model-predicted move 8.60 bps; mean P&L $309.37 per straddle at base costs, t95 [-240.95, 859.68], boot95 [-76.09, 849.02], share of days positive 0.55; total $3403.02, largest day 2026-09-30 $2490.82; mean without it $91.22; median $91.82.
  Implied vs realized (regression model): mean pred - implied 0.73 pts, boot95 [-0.38, 1.73] (iid D1: [-0.74, 1.76]); ratio model 0.04 [-0.95, 1.11]; unconditional 2.83 [1.69, 4.01].

| date | S 15:49 close | K | straddle (10m) | ATM parity dev | official | abs move | P&L $ |
|---|---|---|---|---|---|---|---|
| 2026-09-21 | 7772.73 | 7775 | 6.93 | 0.30 | 7764.70 | 8.03 | 316.82 |
| 2026-09-22 | 7777.36 | 7775 | 5.30 | 0.04 | 7764.64 | 12.72 | 485.82 |
| 2026-09-23 | 7709.14 | 7710 | 5.85 | 0.11 | 7706.03 | 3.11 | -208.18 |
| 2026-09-24 | 7704.29 | 7705 | 6.35 | -0.74 | 7704.13 | 0.16 | -568.18 |
| 2026-09-25 | 7746.40 | 7745 | 6.28 | 0.52 | 7743.41 | 2.99 | -489.18 |
| 2026-09-28 | 7681.86 | 7680 | 6.63 | 0.61 | 7683.69 | 1.83 | -314.18 |
| 2026-09-29 | 7671.20 | 7670 | 6.08 | 0.72 | 7670.84 | 0.36 | -544.18 |
| 2026-09-30 | 7682.61 | 7685 | 8.35 | -0.06 | 7651.54 | 31.07 | 2490.82 |
| 2026-10-01 | 7676.95 | 7675 | 6.98 | 0.37 | 7666.45 | 10.50 | 136.82 |
| 2026-10-02 | 7724.11 | 7725 | 5.73 | 0.02 | 7722.72 | 1.39 | -365.18 |
| 2026-10-05 | 7778.44 | 7780 | 5.85 | -0.09 | 7773.95 | 4.49 | -0.18 |
| 2026-10-06 | 7823.09 | 7825 | 4.95 | 0.26 | 7818.93 | 4.16 | 91.82 |
| 2026-10-07 | 7796.65 | 7795 | 5.28 | 0.77 | 7801.77 | 5.12 | 128.82 |
| 2026-10-08 | 7763.16 | 7765 | 6.30 | -0.86 | 7765.36 | 2.20 | -614.18 |
| 2026-10-09 | 7813.25 | 7815 | 4.30 | 0.45 | 7811.54 | 1.71 | -104.18 |
| 2026-10-12 | 7805.88 | 7805 | 3.70 | 0.72 | 7807.24 | 1.36 | -166.18 |
| 2026-10-13 | 7810.38 | 7810 | 4.13 | 0.65 | 7805.45 | 4.93 | 21.82 |
| 2026-10-14 | 7712.10 | 7710 | 8.90 | 3.60 | 7718.94 | 6.84 | -16.18 |
| 2026-10-15 | 7748.49 | 7750 | 6.60 | 1.21 | 7744.06 | 4.43 | -86.18 |
| 2026-10-16 | 7652.49 | 7650 | 6.43 | -3.16 | 7659.44 | 6.95 | 280.82 |
| 2026-10-19 | 7704.76 | 7705 | 4.75 | -0.01 | 7690.73 | 14.03 | 931.82 |
| 2026-10-20 | 7711.25 | 7710 | 6.10 | -0.05 | 7712.57 | 1.32 | -373.18 |

### (vi) added after the audit: P3 placebo at other minutes, and P3 by NYSE regime

Same construction (sign of a one-minute open-to-open change, then the next 9 bars) at 342 other minutes 10:00..15:41: placebo median NW t -0.53, share t > 2 0.006, share t < -2 0.070, max t 2.18; P3 t 4.09 ranks 1 of 343. 2023-2026 only: P3 t 1.28, placebo median t -0.21, share t > 2 0.029, P3 rank 30.

| P3 period | n | mean bps | NW t |
|---|---|---|---|
| before_2019-04-01 | 1422 | 0.888 | 3.04 |
| 2019-04-01_to_2022-12-31 | 940 | 1.675 | 2.68 |
| 2023-01-01_on | 945 | 0.490 | 1.28 |

### (vii) added after the audit, not pre-registered: OTM 0DTE options from 10-minute bars (22 days, 261 options)

Entry = 15:40-bar close (~15:49:59); 'reach' = the 15:50-bar high (15:50:00-15:59:59) >= k x entry, an upper bound (a bar high is one print, and the last minute is included). Settlement multiple = intrinsic at the official close / entry.

| series | n | mean entry | reach 2x (high) | reach 3x (high) | reach 5x (high) | settled >= 2x | settled at 0 | mean $ hold |
|---|---|---|---|---|---|---|---|---|
| call_5 | 22 | 1.37 | 0.18 | 0.09 | 0.00 | 0.00 | 0.86 | -101.27 |
| put_5 | 22 | 1.28 | 0.45 | 0.32 | 0.18 | 0.23 | 0.64 | 112.41 |
| call_10 | 22 | 0.48 | 0.18 | 0.09 | 0.00 | 0.00 | 1.00 | -58.14 |
| put_10 | 22 | 0.59 | 0.36 | 0.23 | 0.18 | 0.14 | 0.82 | 59.64 |
| call_15 | 22 | 0.21 | 0.09 | 0.05 | 0.00 | 0.00 | 1.00 | -31.45 |
| put_15 | 22 | 0.22 | 0.27 | 0.18 | 0.14 | 0.05 | 0.95 | 51.73 |
| call_20 | 22 | 0.09 | 0.14 | 0.09 | 0.05 | 0.00 | 1.00 | -19.45 |
| put_20 | 22 | 0.12 | 0.23 | 0.23 | 0.14 | 0.05 | 0.95 | 39.50 |
| call_25 | 22 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | -15.00 |
| put_25 | 22 | 0.08 | 0.18 | 0.18 | 0.18 | 0.05 | 0.95 | 20.82 |
| call_30 | 21 | 0.02 | 0.10 | 0.10 | 0.10 | 0.00 | 1.00 | -12.57 |
| put_30 | 20 | 0.05 | 0.10 | 0.10 | 0.10 | 0.05 | 0.95 | 2.11 |

Pooled 5- and 10-point OTM (n 88): reach 2x (bar high) 0.30, settled >= 2x 0.09, settled at 0 0.83, mean hold P&L $3.16 per contract.

Extra variants counted: 14 ((i) OTM 5..30 x call/put reach 2x/3x/5x + sell-at-2x rule (12 option series x 4 statistics); (ii) minute-of-day |r| profile; (iii) 15:59 close -> official close; (iv) S1 with 10-minute 15:40-bar close as entry stand-in (22 days); (iv) the same with a parity filter |ATM dev| <= 0.5; D1 strict day-rule sensitivity for H1/H2; ratio and unconditional implied-vs-realized models next to the regression; S2-alt: largest abs t among predictors known at 15:49 (P1/P2/P4), entry 15:49; fee $1.13/contract/side (actual Robinhood SPXW fee, upper end) in the cost grid; 1-day-block (iid) bootstrap sensitivity next to the 20-day-block CIs; S2 predictor selection repeated on D1 dates before the first D2 session; (ii-b) yearly size of the 15:45/15:50/15:55/15:59 bars; (vi) P3 placebo at 342 other minutes + P3 split at the 2019-04-01 NYSE switch; (vii) OTM 5..30 reach 2x/3x/5x from 10-minute bar highs (22 days)).
