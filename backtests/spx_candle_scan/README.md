# Is there a candle that accurately predicts the SPX close move?

## The answer in one sentence

Only one candle passed, the 15:50 one-minute candle with a strong body, which is the effect we already knew
as P3. Out of sample it called the move from 15:51 to the close right 57.5% of the time. That is just enough
to pay for buying an at-the-money 0DTE option. But the margin depends on how options are priced, and most of
it comes from 2021-2022 (54.7% since 2023). So it is a lead to forward-test, not a proven edge.

## The question, and how it was tested

The question was whether any candle in the last 30 minutes says which way SPX will move into the close, well
enough to make money buying a 0DTE option. The rules were written down and frozen before any number was
computed, in `preregistration/spx_close_candle_scan.md`. The test had four steps:

1. **Build 41 candle "signals".** Each says up, down or nothing, using only candles finished before the trade.
   They cover:
   - the direction of each one-minute candle from 15:30 to 15:50;
   - candle shapes (strong body, hammer, shooting star, engulfing, big candle) on the 15:50 candle and on the
     15:45-15:49 five-minute candle;
   - five-minute candle directions;
   - four "whole day" signals.
2. **Look only at 2013-2020 (1,861 days) to pick candidates.** A signal qualified if its t-stat was at least
   2.5. Three did. Their list and direction were saved and hashed (SHA-256 `20ca75f8…931f`) before any
   2021-2026 data was read. The code stops reading the data file at the first 2021 row.
3. **Test the three on 2021-2026 (1,446 days) they had never been fitted to.** The test was one-sided and
   corrected for testing three things at once (Holm, 5%). A signal "predicts" only if it passes this test.
4. **Ask whether it pays.** A signal is "accurate" only if its out-of-sample hit rate, at the low end of its
   95% confidence interval, is above the hit rate needed to break even buying the at-the-money 0DTE option.

The data is the Dukascopy US500 CFD, one-minute bars, measured to the close of the 15:59 bar.

## The candidates

| Candidate (plain name) | 2013-2020 hit rate (95% CI) | 2021-2026 hit rate (95% CI) | 2021-2026 trades | Holm p | Predicts? | Accurate? |
|---|---|---|---|---|---|---|
| 15:50 candle, strong body (body at least 60% of the candle's range), trade its direction | 54.1% (50.9-57.3%) | **57.5% (53.6-61.2%)** | 644 | 0.00006 | yes | **yes, just** |
| 15:50 candle direction, any body | 52.2% (49.9-54.5%) | 54.0% (51.4-56.6%) | 1,445 | 0.011 | yes | no |
| Day so far (09:30 to 15:49 direction, = P1) | 52.0% (49.7-54.3%) | 48.4% (45.8-51.0%) | 1,446 | 0.53 | no | no |
| *Reference only, not tested: P3 (15:50 to 15:51 direction)* | *51.8% (49.5-54.1%)* | *53.6% (51.1-56.2%)* | *1,442* | — | — | — |

- **Two features predict and one is accurate.** Both are on the 15:50 one-minute candle and both are really
  P3: they agree with P3's sign on 98% and 93% of days. So their 2021-2026 pass is nominal. P3's 2013-2026
  result was known before the scan, so 2021-2026 was not a blind test for them.
- **The third candidate is P1 under a new name**, and P1 was already known to fail. It failed again.
- **The other 38 features never reached the 2013-2020 bar.** They are not shown to predict.
- **"Sharper form" is fair.** On 15:50 candles without a strong body, trading the direction earned nothing
  (audit, `audits/recompute/recompute_out.json`).
- **How to read the counts.** Hit rates count days with a non-zero move. F1 had 1 zero-move day, which is why
  its 1,445 trades show 1,444 in the hit rate. Counting it as a miss changes nothing.

## Break-even hit rate for the 0DTE option, and what counts as "accurate"

**The trade.** At 15:51, buy the at-the-money 0DTE call (signal up) or put (signal down) and hold it to the
close.

**The pre-registered cost.** You pay half of a "fair" straddle, meaning the average size of the move, plus a
$0.10 half-spread and a fee. You win the move if you are right and lose the premium if you are wrong.

| Candidate | Break-even ($0.09 fee) | Break-even, size-neutral | With a $0.74 fee | Needed to count as accurate, at 2021-2026's trade count | ... in one year of trades |
|---|---|---|---|---|---|
| Strong-body 15:50 | 49.5% | 51.8% | 49.6% | **53.4%** (55.7% size-neutral), 644 trades | 58.9% (61.6%), 112 trades |
| 15:50 direction | 51.5% | 51.9% | 51.7% | 54.2% (54.5%), 1,444 trades | 57.9% (58.3%), 252 trades |
| Day so far | 51.0% | 51.6% | 51.1% | 53.7% (54.1%), 1,446 trades | 57.5% (57.9%), 252 trades |

**How to read it:**
- **Break-even is the hit rate at which the option trade makes $0 on average.** The plain break-even is a
  little above 50%, because the spread and the fee have to be paid.
- **The primary break-even for strong body is below 50%.** In 2021-2026 the moves on right days were 4.6%
  bigger than average. That pattern was not stable: the ratio was 1.17 in 2013-2020 (audit, `audits/recompute/recompute_out.json`). The "size-neutral"
  column ignores it, so it is the safer number. For any signal it is about 51.6% (15:49 entry) to 51.9%
  (15:51 entry).
- **"Accurate" means the bottom of the 95% CI is above the break-even.** With 644 trades that needs an
  observed hit rate of at least 53.4%, or 55.7% to be safe. Strong body's 57.5% clears both. In a single year
  of about 112 trades, you would need 58.9% or more before the result meant anything.
- **The direct test of the money.** The mean option P&L for strong body was +$46 a trade (t 2.2; 2.1 allowing
  for clustering). For the 15:50 direction it was +$13 (t 1.1, not significant), and for day-so-far −$17.

**Why "just".** The verdict rests on options being priced at the realized-move-fair value:
- It flips if the market charges more than 1.085x that fair price.
- The average P&L reaches $0 at 1.166x.
- On the 22 Robinhood days we have, the straddle cost 0.90x its own payoff. The 95% CI of 0.62-1.38 is too
  wide to say which side of 1.085x the market is on.

## Placebo: the same candles at 11:49/11:51

The same candle rules were moved four hours earlier, with the target ending at 11:59. Nothing works there,
which is what you would expect if the effect belongs to the close (the closing auction imbalance at 15:50).

| Candidate | 2021-2026 t (hit rate) | 2013-2020 t |
|---|---|---|
| Strong body | 0.61 (50.7%) | -1.19 |
| 15:50 direction | -1.09 (48.6%) | -1.65 |
| Day so far | 0.48 (51.1%) | -0.46 |

## The 2023-2026 picture

These numbers are descriptive, not tests.

| Strong-body 15:50 | Trades | Hit rate (95% CI) | t | Option P&L a trade (t) |
|---|---|---|---|---|
| 2021-2022 | 216 | 63.0% (56.3-69.1%) | 3.56 | +$80.7 (2.33) |
| 2023-2026 | 428 | 54.7% (49.9-59.3%) | 2.27 | +$28.6 (1.11) |

- **By year:** 64.9%, 61.0%, 54.0%, 53.8%, 57.3%, 53.3% (2021 to 2026).
- **The 2023-2026 CI includes 50% and the size-neutral break-even.** It only just clears the primary 49.5%.
  Its option P&L is not significant.
- **The plain 15:50 direction gives 53.2% since 2023, and P3 itself 53.2% (t 1.28).** The effect may be
  fading.
- **How long to confirm going forward**, at about 112 trades a year (5% test, 80% power):

  | Test | At the full 2021-2026 effect | At the 2023-2026 effect |
  |---|---|---|
  | Option P&L | 808 trades (about 7 years) | 2,165 trades (about 19 years) |
  | Hit rate vs the size-neutral break-even | 483 trades (about 4 years) | 1,916 trades (about 17 years) |

  A single year cannot settle it.

## Caveats

- **Not the settlement.** D1 is a CFD measured to the 15:59 bar. The option pays on the official SPX
  settlement.
  - On 22 overlapping days, the two moves from 15:51 to the close had the same sign on only 86% of days.
  - If the disagreements are random, 57.5% becomes about 55.4% against the settlement, with a CI lower bound
    of about 52.6%. That is still above both break-evens, but closer.
  - Any forward test must score against the official settlement.
- **Option pricing is assumed, not observed.**
  - The strike is assumed to be exactly the entry price; real strikes are 5 points apart.
  - The straddle cross-check has only 22 days, with marks from about 15:50 that are not simultaneous.
  - The break-even "at today's price level" (48.5%) rescales old moves without allowing for today's lower
    volatility, so it is flattering.
- **No blind test.** All three candidates were known effects: P3 twice, P1 once. The pass is "the known P3
  effect survived a stricter, sharper test", not a discovery.
- **Execution.** The audit found that entering one minute late (15:52) still gives a hit rate of 56.1% (t 3.94)
  (`audits/recompute/recompute_out.json`). Real fills, partial fills and spread changes at the close are not
  modelled.
- **Audit trail.**
  - The first holdout output (13:26) was overwritten before the audits, and the exact code at freeze cannot
    be recovered. The current code reproduces the frozen numbers exactly, and every later run is kept in
    `runs/`.
  - The candidate hash still has to be added to `preregistration/LEDGER.md`. That is your step; agents may
    not edit that folder. The exact line is in `audits/DISPOSITION.md`.
- **The forward test is not run.** It was pre-registered as descriptive, and only 1 day of data exists, with
  a provisional settlement.
- **Small, disclosed changes from the pre-registration** (all labelled DEVIATION in `scan.py`):
  - zero-move days are also dropped from the primary hit rate, with the other version reported next to it;
  - after seeing the holdout, the straddle-cost sensitivity and the plain summary were rewritten, and the
    audit additions were made.

  None changes a test, a candidate or a verdict.

> **Learn: why data-mined candle patterns usually fail out of sample**
>
> - **Multiple testing.** Test 41 random signals and, by luck alone, about 1 in 80 will reach |t| 2.5.
>   This scan checked luck on the real data: it slid the 41 real signals out of line with the real
>   2013-2020 closes and re-ran the scan 304 times. On average 0.34 signals passed, and 28% of the runs found
>   at least one "winner". Ours found 3, and the best had t 3.82. That happened in 1% and 0% of the shuffles,
>   so the 15:50 result is unlikely to be pure luck. But a single "winner" usually would be. The fixes are
>   to pick in one period, freeze the pick, test it in a later period, and correct for the number of tests
>   (BH, Holm).
> - **Winner's curse.** The signal that tops a list of 41 is usually there partly by luck, so its edge
>   shrinks out of sample. Day-so-far went from t 2.69 in 2013-2020 to t -0.07 in 2021-2026.
> - **Look-ahead.** A candle is only known once it closes. The 15:50 candle closes at 15:50:59, so it can
>   only be traded from 15:51. Backtests that "enter at the close of the signal candle" quietly use the
>   future. Here every signal was re-computed with all later data hidden or scrambled, and nothing changed.
> - **Regimes change.** Market structure moves: closing-auction rules, 0DTE volume, volatility. An edge that
>   was 63% in 2021-2022 was 55% after.
> - **Costs.** A 54% hit rate sounds good, but after the spread and the fee the break-even on an option is
>   about 52%. Many "predictive" patterns predict, but not by enough to pay.

## The 15:49 study (`backtests/spx_close_1549`): what a second audit found

A second audit of the earlier close study rebuilt the daily data from the raw Dukascopy files and
matched every kept day, drop count and headline number.

**It raised 7 findings, none HIGH, and all 7 were confirmed.** None changes a verdict, a mean, a t-stat or a
Holm p.

| Finding | What it means |
|---|---|
| The "about $7" parity error bound in `DISPOSITION.md` is wrong | On 2026-10-20 the call and put marks break put-call parity by 0.73 points. If one leg is the bad price, the straddle cost 6.63 or 5.17 instead of 5.90, and the S1 loss is −$280 to −$426 instead of −$353. It is negative either way. |
| S2's predictor choice is called "as pre-registered" | It is a reading of the wording (largest \|t\|, traded in the sign of t). Both readings pick P3 with t 4.09, so the trades are identical. |
| Two bootstrap reporting gaps | The "both CIs must pass" rule is disclosed but not labelled a deviation. One exploratory test used 2,000 resamples, not 10,000. |
| Uncounted exclusions | Hit rates also drop zero-return days. P3 is 52.60% as reported, 52.33% with them counted as misses. Three far-out-of-the-money contracts are missing from the 10-minute option table. |
| Two README labels | "11.29 bps in 2023-2026" is the model-fitting sample; all 945 days give 11.12. "15:50 is the biggest minute" is true from 2023 but not over 2013-2026. |
| Wording goes further than the numbers | P3's edge (0.130 points) is a bit more than the 0.10 half-spread, not "far too small". "Never settle" means about 380 years. The "95% range" is a CI for the mean. |
| "14 extra variants" | These are 14 families of variants; the placebo family alone has 342 minutes. |

**Verdicts, unchanged.**
- S1 (straddle), S2 (P3 direction trade) and S3 (sell the spike) are "FAIL by rule; D2 test not run". Only 1
  of about 35 planned days of real option prices exists.
- S2-alt fails, because P1 does not pass.
- P3 still passes on 2013-2026.

## Files

| File | What it is |
|---|---|
| `scan.py` | The whole scan. `discover` reads 2013-2020 only, then freezes and hashes the candidates. `holdout` refuses to run unless the hash matches, then tests and writes everything. |
| `candidates.json`, `candidates.sha256` | The frozen candidate list and its hash. Unchanged since 2026-10-21T20:25:04Z. |
| `discovery.json` | All 41 features on 2013-2020, with BH q-values and the P3 reference row. |
| `holdout.json` | The 2021-2026 tests, economics, placebo, sub-periods, straddle and settlement checks, chance check and known-effect flags. It opens with `summary_plain_english`. |
| `runs/` | Every earlier `discovery.json` and `holdout.json`, named by time and code hash. `holdout.json` -> `rerun_vs_archived_runs` shows old -> new (0 of 69 headline numbers changed). |
| `tests/test_scan.py`, `tests/test_results.json` | 8 checks, all passing. They cover planted effects, pure noise, the hash gate, no-2021-in-discovery, look-ahead, the economics identity, archiving and the abort when discovery no longer reproduces. |
| `audits/recompute/` | The audits' recomputation scripts and their outputs. |
| `audits/DISPOSITION.md` | What was done about each audit finding, with old -> new. |

To re-run (one process; about 10 seconds for each scan step, about a minute for the tests):

```
PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B scan.py discover
PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B scan.py holdout
PYTHONDONTWRITEBYTECODE=1 /Users/kv15/trading/.venv/bin/python -B tests/test_scan.py
```
