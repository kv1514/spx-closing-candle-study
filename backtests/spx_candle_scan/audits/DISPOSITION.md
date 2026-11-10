# Audit disposition: SPX close candle scan

Written 2026-10-21. This file records what was done with each finding of the two audits (12 findings in the first,
4 in the second). Every number below comes from `scan.py` and is in `holdout.json`,
`discovery.json` or `tests/test_results.json`, unless the line names an audit file as its source.

## Plain English first

- **Both audits are confirmed.** I checked every finding against the code and the data. All 16 hold up. None
  of them was an arithmetic error, and none changes a test result, a candidate, a direction or a pass/fail flag.
- **What was wrong was the wording and the economics write-up, not the test.** The summary said "none of the
  other 40 features predicts", but F1 15:50 passes the pre-registered test. The "accurate" verdict for the
  strong-body candle was given without saying how fragile it is: it depends on how options are priced, and it
  comes mostly from 2021-2022.
- **What I changed.** `scan.py` now reports the missing pieces and writes them to `holdout.json`:
  - the direct test of the option P&L, and the option-price markups at which the verdict flips;
  - a 2021-2022 vs 2023-2026 split;
  - trades needed against the stricter break-even;
  - the straddle checked against its own payoff;
  - how often the CFD target agrees with the official settlement;
  - a P1 flag;
  - a chance check on the real data.

  It also keeps every earlier output in `runs/` and refuses to run the holdout if the current code no longer
  reproduces the frozen discovery.
- **Re-run record.** The discovery step was re-run first. It picked the same 3 candidates and directions, and
  the frozen file was kept byte for byte: `candidates.json` SHA-256 `20ca75f8…931f` -> `20ca75f8…931f`
  (unchanged). The holdout was then re-run after the code fix. Compared with the pre-audit run (`scan.py`
  `18ec9b43…`), all 69 headline numbers are identical (`holdout.json` -> `rerun_vs_archived_runs`). The new
  numbers are additions, not replacements.
- **One thing only you can do.** Append the candidate hash to `preregistration/LEDGER.md`. Agents must not
  edit `preregistration/`. The line to add:
  `- 2026-10-21T20:25:04Z  20ca75f8a9cf62d8f46a0eb5e6c59eae1292284c50a9319922ac2e17ee75931f  backtests/spx_candle_scan/candidates.json (frozen candidates)`.

## Run record (old -> new)

| Step | What happened | Evidence |
|---|---|---|
| Code fix | `scan.py` `18ec9b43…90e4` -> `558fff90…0584` | `holdout.json` -> `meta.scan_py_sha256` |
| Discovery re-run (re-freeze check) | Same 3 candidates and directions; every one of the 41 t-stats changed by 0.0; the frozen file was kept unchanged | `discovery.json` -> `freeze.action`, `rerun_vs_previous_run.max_abs_t_diff_all_41` |
| `candidates.json` SHA-256 | `20ca75f8…931f` -> `20ca75f8…931f` (unchanged) | `candidates.sha256`, `holdout.json` -> `hash_gate` |
| Holdout re-run after the code fix | 69 headline numbers compared with each earlier run, 0 changed | `holdout.json` -> `rerun_vs_archived_runs.runs` |
| Reproduction check | t difference 0.0 against both the frozen file and `discovery.json`; it now aborts on any difference above 1e-9 | `holdout.json` -> `discovery_reproduced_with_current_code` |
| Tests | 8 of 8 pass, including a new test of the economics identity, archiving and the abort | `tests/test_results.json` |

The 69 numbers compared, per candidate, are:
- direction, trade counts, mean, NW t, the one-sided and Holm p-values, the pass flag;
- the hit rate and its CI lower bound;
- for both fees: the primary and size-neutral break-evens, the accuracy flag, the trades needed and the mean option P&L;
- the placebo t-stats (holdout and discovery).

Then, once each: the P3 holdout t, the straddle ratio and the hash.

Several earlier runs are archived:
- `runs/holdout_20261021T203300Z_scan18ec9b4354e4.json` is the pre-audit run.
- The first holdout run (13:26 local) had already been overwritten before the audit, so it cannot be recovered.
- The intermediate post-fix runs (`c55c45af…`, `41d72b3b…`) changed only reporting code and are kept in `runs/`.

## Finding by finding

C = first audit, X = second audit. "Verdict" means a test result, Holm flag or accuracy flag.

| # | Sev. | Finding | Checked | Disposition | Verdict changes? |
|---|---|---|---|---|---|
| C1 | Med | "None of the other 40 predicts" contradicts the pass rule; F1 has 1,445 trades, not 1,444 | confirmed | wording fixed in `plain_summary` and README | no |
| C2 | Med | "Accurate" is fragile to option cost; lead with the direct option-P&L test | confirmed | added `option_pnl_test`, markup tipping points, the size-neutral verdict | no |
| C3 | Med | The pass comes mostly from 2021-2022 | confirmed | added `holdout_subperiods_NOT_TESTS` | no |
| C4 | Med | "244 trades (2.2 years)" is optimistic | confirmed | added trades against size-neutral, and at the 2023-2026 effect | no |
| C5 | Low | "Recent CI includes the break-even" is wrong for the primary break-even | confirmed | summary now states includes/excludes explicitly | no |
| C6 / X3 | Low / Med | Straddle ratio divides by \|settle - S\|, not \|settle - K\| | confirmed | added the like-for-like ratio and relabelled it a rough cross-check | no |
| C7 | Low | CFD target vs official settlement | confirmed | added `cfd_vs_settlement_target` | no |
| C8 | Low | Fully priced days quoted as a cross-regime ratio | confirmed | added the same-day payoff and a `ratio_note` label | no |
| C9 / X1 | Low / High | P1 not flagged; no holdout test was blind | confirmed (interpretation) | added `known_effects` (0 of 3 blind); wording now says "nominal pass" | no |
| C10 / X4 | Low | Audit trail: first output overwritten, source at freeze unrecoverable, hash not recorded externally | confirmed | `runs/` archive, old -> new against every run, enforcing reproduction check; LEDGER line for you | no |
| C11 | Low | The noise tests are synthetic only | confirmed | added `real_data_null_check` | no |
| C12 / X2 | Info / Med | Zero-move days dropped from the hit rate but counted in the economics; forward-test wording; last-level caveat | confirmed | zero-as-miss hit rate and verdict added, labelled DEVIATION; `forward_test.status`; `caveat` on the last-level economics | no |

### C1. Wording of "predicts" (confirmed, fixed)

- F1_1m_15:50 passes Holm in the holdout (p 0.0109; `holdout_test.rows[1].p_holm`), so under the
  pre-registered rule it predicts. It fails only the separate "accurate" bar: CI lower 51.4% against a
  break-even of 51.5%.
- It has 1,445 trades (`n_trades`) and 1,444 trades with a non-zero move (`n_hit_days`). Both are now printed.
- **Fix.** `plain_summary` now says:
  - 2 of 3 candidates pass and 1 is accurate;
  - all three are known effects;
  - the other 39 are "not shown to predict": 38 never reached the discovery bar, and F4 failed the holdout.

### C2. Fragility of "accurate" (confirmed, fixed)

**The option-P&L test.** Strong body, $0.09 fee: mean option P&L +$46.08 a trade, t 2.22 iid and 2.06 NW
(one-sided p 0.013 and 0.020). It equals 0.5 x mean signed move minus the extras exactly, as an identity
(`verdict_vs_breakeven.fee_0.09.option_pnl_test`).

**The tipping points.**
- At a straddle markup of 1.085x over realized-fair, the break-even reaches the CI lower bound of 53.6%.
- At 1.166x, the mean P&L is 0 (`markup_where_breakeven_equals_ci_lower`, `markup_where_mean_pnl_is_zero`).

**The primary break-even is below 50% only because of move size.** It is 49.5% because moves on right days
were 1.046x the average in the holdout (`ratio_abs_move_correct_to_all`). The same ratio was 1.174 in
discovery (`audits/recompute/recompute_out.json`), so it is unstable.

The verdict also holds against the size-neutral break-even of 51.8% (`accurate_vs_size_neutral_breakeven`:
true). With 644 trades, "accurate" needs a hit rate of at least 53.4% (primary) or 55.7% (size-neutral). The
observed rate is 57.5%.

### C3. 2021-2022 vs 2023-2026 (confirmed, fixed)

`holdout_subperiods_NOT_TESTS.candidates.F2_1m_1550_strong_body`:

| Period | Trades | Hit | 95% CI | NW t | Option P&L $/trade (t iid) |
|---|---|---|---|---|---|
| 2021-2022 | 216 | 63.0% | 56.3-69.1% | 3.56 | +80.7 (2.33) |
| 2023-2026 | 428 | 54.7% | 49.9-59.3% | 2.27 | +28.6 (1.11) |

By year: 64.9%, 61.0%, 54.0%, 53.8%, 57.3%, 53.3% (2021-2026).

### C4. Trades needed (confirmed, fixed)

| Test (strong body, $0.09) | Full-holdout effect | 2023-2026 effect |
|---|---|---|
| Mean return | 277 (2.5 years) | 707 (6.3 years) |
| Hit rate vs the primary break-even 49.5% | 244 (2.2 years) | n/a |
| Hit rate vs the size-neutral break-even | 483 (4.3 years) | 1,916 (17.1 years) |
| Option P&L | 808 (7.2 years) | 2,165 (19.3 years) |

The summary now leads with the option-P&L count. Years assume about 112 trades a year.

### C5. Recent CI wording (confirmed, fixed)

The 2023-2026 CI is 49.94-59.33%:
- it includes 50% and the size-neutral break-even of 51.8%;
- its lower bound is just above the primary break-even of 49.52%.

`ci_vs_full_holdout_breakevens_fee_0.09` now states this. The scan's own summary never said "includes the
break-even"; that line was in the hand-written run summary.

### C6 / X3. Straddle vs its own payoff (confirmed, fixed)

**The ratios over the 22 Robinhood days** (`straddle_cost_crosscheck.robinhood_10m_days`):
- against \|settle - S\|: 1.015 (bootstrap CI 0.68-1.65), as before;
- against the straddle's own payoff \|settle - K\|: 0.898 (CI 0.618-1.378).

The straddle cost 0.67 points less than its payoff on average, and was above its payoff on 50% of days.

**The markup sensitivity** for strong body now shows both bases. On the like-for-like basis the break-even is
44.7% at the point estimate and 31.3% to 67.6% across the bootstrap CI. On the old basis it is 50.2%, with a
range of 34.2% to 80.4%.

**Relabelled.** It is now called "an approximate cross-check on 22 days, not a validated pricing
multiplier". The marks are about 15:50 and not simultaneous; the largest parity deviation is 3.60 points.

### C7. CFD vs settlement (confirmed, fixed)

`cfd_vs_settlement_target`, on 22 overlapping days:
- D1 r(15:51 open -> 15:59 close) and SPX r(15:51 open -> official settle) have correlation 0.962 and the
  same sign on 86% of days. The mean absolute gap is 2.04 bps.
- The 15:50 candle's direction agrees on 91% of days, and the strong-body signal on 77%.

If the disagreements are unrelated to the signal, the 57.5% hit rate maps to 55.4% against the settlement,
with a CI lower bound of 52.6%. That is still above both break-evens. It is a sensitivity, not a test.

### C8. Fully priced days (confirmed, fixed)

**Same-day comparison:**

| Day | Straddle | Payoff \|settle - K0\| | Move \|settle - S0\| |
|---|---|---|---|
| 2026-10-20 | 5.90 pts | 2.57 pts | 1.64 pts |
| 2026-10-21 (settlement provisional) | 6.43 pts | 2.80 pts | 3.03 pts |

Two days cannot tell us anything about pricing. The cross-regime ratios (0.59x and 0.64x) are kept in the
JSON under a `ratio_note` that says what they measure, and they are no longer quoted in the summary.

### C9 / X1. Known effects; no blind test (confirmed, fixed in reporting)

`known_effects`:

| Candidate | Same sign as P3 | Same sign as P1 | Known effect |
|---|---|---|---|
| strong body | 97.9% | — | P3 |
| F1 15:50 | 93.1% | — | P3 |
| F4_day_so_far | — | 100% | P1 (it is P1 by definition) |

`n_blind` = 0. The flags are computed in the holdout step, and `candidates.json` was not touched.

The second audit rated this HIGH because the earlier P3 research had already used the 2021-2026 years. That is right as
interpretation: the Holm flags are correct for the 3-test family, but they are nominal passes, not
independent confirmation. No code defect was involved.

### C10 / X4. Provenance (confirmed, fixed going forward)

**Cannot be recovered:**
- the first holdout output (13:26);
- the `scan.py` source at freeze (`05fd91bb…`). A hash identifies content; it cannot restore it.

**Mitigations now in the code:**
- Every overwrite archives the previous file in `runs/`.
- `holdout.json` records old -> new against every archived run.
- The reproduction check aborts if the candidates differ or any t-stat moves by more than 1e-9. A test covers
  this: an edited `discovery.json` is refused.

The current code reproduces the frozen t-stats exactly (difference 0.0).

**Your action:** add the LEDGER line given at the top of this file.

### C11. Real-data chance check (confirmed, fixed)

All of these are in `real_data_null_check`.

**Random-sign signals against the real D1 targets** (2,000 per period and entry):
- |t| >= 2.5 happened 0.55-0.90% of the time (nominal 1.24%);
- a one-sided 5% rejection happened 4.45-5.25% of the time (nominal 5%).

So NW is not over-rejecting on real data.

**The real 41 signals, shifted as a block against the 2013-2020 targets** (304 shifts):
- on average 0.34 features reach |t| >= 2.5;
- 28.0% of shifts give at least one;
- 1.0% give three or more;
- none gives a best |t| as large as the observed 3.82.

**The 3 candidates, shifted in the holdout** (235 shifts): any Holm pass in 4.7% of shifts.

### C12 / X2. Zero moves, forward test, last level (confirmed, fixed)

**Zero-move days.** In the holdout, strong body has 0 zero-move trades and F1 has 1. With zero-move trades
counted as misses:
- F1 holdout is 780/1,445 = 53.98%, CI 51.40-56.54%;
- strong body in discovery is 494/920 = 53.70%.

The accuracy verdict is the same under both definitions (`accurate_zero_target_as_miss`). The extra
exclusion is labelled DEVIATION in `DECISIONS` (`zero-target-hit-rate`). The second audit's 2,603-trade power figure
for F1 under that definition was not recomputed here.

**Forward test.** `forward_test.status` is "not run": it is pre-registered as descriptive, and only 1 day
exists, with a provisional settlement.

**Last level.** The last-level economics now carry a `caveat`. They rescale 2021-2026 moves to today's
price level, which ignores that volatility is lower now, so they flatter the break-even. The second audit's related
point: at the last level, F1's break-even (50.9%) is below its CI lower bound (51.4%). That is a sensitivity
only; the pre-registered verdict for F1 is "not accurate".

## Not changed, by design

- Nothing under `preregistration/`. The frozen `candidates.json` and `candidates.sha256` are unchanged.
- The primary hit-rate definition stays as it was (`analysis.py` convention). The alternative is reported
  next to it.
- No feature, threshold, test or pre-registered economics number changed.
