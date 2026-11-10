# Disposition of audit findings: SPX 15:49 close study

Written 2026-10-21, after an adversarial audit. The pre-registration
`preregistration/spx_1549_close.md` was not changed. All fixes are in `analysis.py`; `tests/test_analysis.py` gained 6
tests and 2 existing tests were updated. Both scripts were rerun:

- `analysis.py` regenerated `results.json` and `RESULTS_RAW.md`.
- `tests/test_analysis.py` now passes 28/28 (it was 22/22).
- `tests/test_d1.py` passes 11/11.

The pre-fix outputs are saved in `audits/results_before_audit_fixes.json`.

**Bottom line:** all four verdicts are still FAIL. The labels are now honest: **"FAIL by rule; D2 test not run (1 of
~35 planned days)"**. Before the fixes, condition 1 for S1/S3 read as a degenerate "yes", and condition 2 read as a
"no" decided on a single day.

## Audits received

| audit | status |
|---|---|
| Adversarial audit (`audit_recompute.py`, `audit_recompute_out.json`) | 11 findings. Each one was checked again here and is dispositioned below |
| Literature review (`research/SPX_1549_RESEARCH.md`) | Not an audit, but two of its points were acted on: an actual-fee sensitivity (finding L1 below) and the NYSE 2019-04-01 regime split (part of finding 10) |

## Findings

### 1. MAJOR: the condition-1 "pass" for S1/S3 was degenerate. FIXED

**Checked:** confirmed. With one D2 day, the old line `jj = ... if n2 > 1 else np.zeros(1, int)` never resampled the D2
side, so the CI measured only how uncertain the D1 refit is, around one fixed implied value of 5.90.

**Fix:**

- `implied_vs_realized` now returns `stat = None`, `size_premise_passes = None` and `evaluable = False` when there are
  fewer than 2 D2 days. The single-day numbers are still printed, marked descriptive.
- The verdicts use three-valued conditions (yes / no / not evaluable).
- The sentence "in every case the D1 premise passes" is not used anywhere; README.md says what is true instead.

**Old -> new:**

- S1/S3 condition 1: yes (CI [1.76, 2.67]) -> **not evaluable**.
- 10-20 regression prediction minus implied: 2.22 -> 2.29 points (the change comes from the finding-5 fit window).

**Supporting evidence, recomputed here:**

- **Out of sample, the model over-predicts the move.** The model is now fitted only on days before 2026-09-02. On the
  34 D1 days from 09-02 to 10-20 it predicts a mean |r_close| of 8.82 bps; the realized value is 6.46 bps (the audit
  had 8.95 vs 7.44 on 22 days, using an in-sample fit).
- **On the 22-day stand-in, realized roughly equals implied.** The 10-minute straddle priced the move at 7.75 bps on
  average; the realized move to the official close was 7.63 bps.

### 2. MAJOR: the verdict code could promote a strategy on one day, and condition 2 has no power. FIXED

**Checked:** confirmed. The old `c2 = n > 0 and mean > 0` would have produced "CANDIDATE" on n = 1 after a large-move
day, even though the pre-registration requires CIs, and a CI needs n >= 2.

**Fix:**

- The new `verdict_row()` sets `cond2 = None` (not evaluable) when n < 2 or no t-CI exists.
- `verdict = CANDIDATE` only if both conditions are `True`.
- `verdict_label` says "FAIL by rule; D2 test not run (n of ~35 planned days)".
- The new test `test_verdict_row_is_three_valued` covers this.

**Old -> new:**

- condition 2: no -> **not evaluable**.
- label: FAIL -> FAIL by rule; D2 test not run (1 of ~35 planned days).

**Power, recomputed here.** The new `power_diagnostic` uses D1 data from 2023-01-03 to 2026-09-01, n = 911:

- **S1:** payoff SD 6.48 points. Detecting a +0.5-point edge at t = 2 needs 671 days. With 35 days, the smallest
  detectable edge is 2.19 points ($219 per straddle).
- **S2 (P3):** the edge over a random-direction ATM option is 0.130 points gross and 0.030 after the $0.10 half-spread.
  The payoff SD is 4.71 points, so about 96,000 days are needed.

The audit's figures (665 and about 78,000 days) differ only because its sample was slightly different. The conclusion
is the same.

### 3. MINOR: S2 departs from the pre-registration in two places. FIXED

**Checked:** confirmed.

- When P was 0, the old `s2_direction` returned 0 and the code booked "no trade, $0" into the mean. The
  pre-registration says "else ATM put".
- The P1-at-15:49 reading was not reported.

**Fix:**

- **Zero and undefined predictors.** P = 0 now buys the ATM put. An undefined predictor (missing bar) now means no
  trade, and the day is **excluded** from the mean instead of being averaged in as $0. Tests:
  `test_planted_reversal_on_p3_gives_opposite_trade` (updated) and
  `test_undefined_s2_predictor_is_excluded_not_booked_as_zero` (new).
- **S2-alt.** A new variant takes the largest |t| among the predictors known at 15:49 (P1, P2, P4) and enters at 15:49.
  It has its own pass-rule row.
- **Entry time.** The 15:51 entry for P3 is now labelled a DEVIATION (forced by no-look-ahead) in DECISIONS.

**Old -> new:**

- S2 on 10-20 is unchanged at -$300.09, because P3 = -1, not 0.
- New S2-alt: P1, condition 1 **no** (Holm p 0.0805, and the 2023-2026 sign is the opposite), 10-20 P&L -$58.09 (call
  7710 bought at 3.05). FAIL.

### 4. MINOR: 15:49 marks fail put-call parity, and this was not disclosed. FIXED

**Checked:** confirmed with a separate implementation (`parity_check` in `analysis.py`).

- On 10-20 the signed median C - P - (S - K) is -0.74 at the 15:49 open (ATM -0.73, max |dev| 0.82, 13 strikes),
  -1.56 at 15:50 and -0.08 at 15:51.
- Bar timing is not the problem. The correlation between changes in the option-implied SPX and the SPX opens is 0.965
  at lag 0, against 0.15 and 0.20 at lags of -1 and +1, so the bars are not mislabelled.

**Fix:**

- The per-day parity check (15:49, 15:50, 15:51) is now in `results.json` and printed as a data-quality line in
  `RESULTS_RAW.md`.
- A new DECISIONS entry `option-marks` and the README caveats say the marks may be prints, not mids, so the $0.10
  half-spread may partly double-count costs.

**Not done:** the optional "parity-adjusted S1" sensitivity. It would require assuming which leg is mispriced. The bound
is small: net straddle delta × parity gap = 0.10 × 0.74 ≈ 0.07 points (about $7 per straddle).

**Old -> new:** no P&L number changed.

### 5. MINOR: small look-ahead in the implied-vs-realized fit and the S2 selection. FIXED (fit) / CHECKED (selection)

**Checked:** confirmed. The fit window had no upper bound, so 10-20 and the whole D2 window were inside the regression
that predicts them.

**Fix:**

- The fit now runs from 2023-01-01 to the day before the **first D2 session collected** (2026-09-02). This is stricter
  than the audit's 09-21 cutoff.
- The model's out-of-sample calibration on the D2 window is reported (see finding 1).
- The S2 selection stays "full-sample D1", because that wording is binding. It is repeated on D1 dates before
  2026-09-02 as a check: P3 is still chosen (t 4.07 against 4.09), so nothing depends on it. A test asserts that the fit
  ends before the first D2 session.

**Old -> new:**

- fit 2023-01-03..2026-10-20, n 945 -> 2023-01-03..2026-09-01, n 911.
- a 0.000266 -> 0.000280; b 0.1357 -> 0.1348.
- 10-20 predicted move: 8.12 -> **8.19 points** (ratio model 7.98 -> 8.02; unconditional 8.57 -> 8.71).
- (iv) regression gap: 0.93 -> 1.00 points.

### 6. MINOR: the "day-block" bootstrap used 1-day blocks. FIXED, with a caveat on the audit's premise

**Checked:** confirmed that the old blocks were one day long.

**Fix:**

- A new `block_indices()` builds circular moving blocks. Every D1 resample now uses 20-day blocks: the H1 CIs and the
  D1 refit inside implied-vs-realized.
- The 1-day (iid) version is reported next to each one as a sensitivity.
- D2 trade samples (22 days or fewer) stay iid, because a 20-day block on 22 days leaves almost nothing to resample.
- The block code is tested against AR(1) theory (`test_block_bootstrap_widens_ci_for_positively_autocorrelated_series`).

**Caveat on the audit's premise:**

- **For H1,** blocks widen the CIs as expected.
- **For the implied-vs-realized regression,** the 20-day-block CI is *narrower* than the iid one. The regression score
  (rv - mean) × residual has a lag-1 autocorrelation of -0.76, driven by back-to-back extreme-volatility days (the
  largest rv days are 562 and 501 bps, consecutive). The HAC standard error of the slope is 0.0155, against 0.0351 for
  HC, so this is a property of the data, not a bug.
- **Conservative rule.** Blocks therefore do not make the premise test harder to pass here. The premise now passes only
  if **both** the 20-day-block and the iid CI lie above zero. No current verdict depends on this, because condition 1
  is not evaluable.

**Old -> new:**

- H1(a) CI of the mean ln diff: [0.304, 0.404] -> [0.300, 0.409].
- H1(b): [0.212, 0.286] -> [0.203, 0.295].
- H1 strict rule: (a) [0.302, 0.408] -> [0.299, 0.413]; (b) [0.214, 0.290] -> [0.205, 0.299].
- (iv) regression gap CI: [-0.19, 1.70] -> [0.11, 1.80] with blocks, [-0.10, 1.80] iid. "CI > 0" stays **no** under the
  both-CIs rule.

### 7. MINOR: the primary D1 day rule is looser than the pre-registration's wording. FIXED (relabelled; audit option B)

**Checked:** confirmed. `keep` treats runs of 1-4 no-update minutes as valid bars. The strict reading drops 374 more
days, concentrated in the sparse-feed years (2014: 126, 2017: 102, 2013: 47), and gives P3 Holm p 6.88e-4.

**Fix:** the `D1-day-rule` entry is now marked **DEVIATION from the literal pre-registration wording**, with the reason
and the 374-day count.

**Rejected alternative:** making `keep_strict` primary. That rule was fixed before any H1/H2 number was computed, and
switching after seeing both results would itself be a post-hoc choice. Both rules are reported in full and give the
same H1/H2 conclusions.

**Old -> new:** no number changed.

### 8. MINOR: exploratory (iv) uses 10-minute prints that are not simultaneous. FIXED

**Checked:** confirmed.

- The ATM parity deviation from 15:40-bar closes against the SPX 15:49 close reaches 3.60 points (10-14; its signed
  median over strikes is 3.33).
- 09-30 contributes $2,491 of the $1,036 total, and 41% of days are positive.

**Fix:**

- Each (iv) row now carries its ATM parity deviation.
- (iv) is reported twice: on all 22 days, and with the filter |ATM dev| <= 0.5 (11 days).
- `RESULTS_RAW.md` states that (iv) "neither supports nor refutes the S1/S3 premise".

**New numbers:** the filtered set has mean +$309 per straddle (t95 [-241, 860]) and a regression gap of 0.73 points
(CI [-0.38, 1.73]). The ratio-model CI includes zero in both versions.

### 9. MINOR: the realized-move model and the straddle use different end points. FIXED (documented)

**Checked:** confirmed. The gap between the 15:59 close and the official close averages 1.26 bps in absolute value, 16%
of the mean move to the official close (8.08 bps).

**Fix:** a new DECISIONS entry `settlement-gap` notes that this understates the move the option pays on, which works
against the S1/S3 premise.

**Not done:** the optional gap-variance inflation. Condition 1 is not evaluable anyway.

**Old -> new:** no number changed.

### 10. INFO: P3 survives a placebo test. ADOPTED as exploratory (vi)

**Recomputed independently** in `exploratory_p3_placebo`, at 342 other minutes from 10:00 to 15:41:

- The placebo median t is -0.53, 0.6% of placebos have t > 2, and the largest is 2.18.
- On the full sample, P3 (t 4.09) **ranks 1st of 343**, matching the audit.
- **New:** in 2023-2026 alone, P3 (t 1.28) ranks **30th of 343**. In the daily-0DTE era it is not special among
  minutes.
- P3 by NYSE regime:
  - before 2019-04-01: 0.89 bps, t 3.04
  - 2019-04-01..2022: 1.67 bps, t 2.68
  - 2023 onward: 0.49 bps, t 1.28
- The P3 sign agrees between D1 and Robinhood SPX on 21 of 22 days. This is now in the Data section.

These count as extra variants.

### 11. INFO: the 15:50 spike depends on the period. ADOPTED as exploratory (ii-b), one detail corrected

**Recomputed** by year:

- In 2013-2016 the 15:45 bar (1.52-1.62x the median bar) was larger than the 15:50 bar (1.36-1.48x). Confirmed.
- **Correction:** the audit's "15:50 reaches 2.0-3.4x from 2017" holds for every year except 2019, where it is 1.74x.
- In 2018 the 15:45 bar (2.22x) was still larger than the 15:50 bar (2.03x).
- From 2020 the 15:50 bar is 2.1-3.4x and the 15:45 bar falls to about 1.0-1.7x.

This fits NYSE's move from 15:45 to 15:50 on 2019-04-01.

### L1. Literature: Robinhood's real SPXW fee is $0.89-$1.13 per contract per side. ADOPTED as an extra sensitivity

**Fix:** a fee of $1.13 was added to the cost grid, labelled "extra: actual RH fee".

**10-20 at the base half-spread:**

- S1: -353.18 -> -355.26
- S2: -300.09 -> -301.13
- S3: -256.18 -> -258.26

The fee is small next to the half-spread.

## Rejected findings

None was rejected outright. Three points were partly rejected, with reasons given above:

- **Finding 6:** its premise that 1-day blocks made the finding-1 CI too narrow does not hold for the regression
  statistic. The fix was implemented anyway, plus the stricter both-CIs rule.
- **Finding 7:** the strict day rule was not made primary.
- **Finding 4:** the optional parity-adjusted sensitivity was not done.

## Variant count

Extra variants counted went from 6 to 14 (listed at the end of `RESULTS_RAW.md`). The power diagnostic and the
pre-registered parity check are not counted, because they add no new test.
