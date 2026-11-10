# Pre-registration: search the closing candles of the SPX index and of SPY at real option prices, with a luck test

**Status: LOCKED 2026-11-10 (UTC).** Locked by Claude (Opus 5.5) at the user's instruction: asked "Lock the
two-chart search plan and run it?", the user wrote "Screw reviewing the code just keep going and more tests".
**No analysis code for this study existed at locking.** No further report from the parent session had arrived.

Drafted 2026-11-10 (UTC) by Claude (Opus 5.5) at the user's request. After the
real-index result, the user asked "can you just perform all the tests you want, tell me which one is the most
predictive and the best". Told that picking the best of many tests on the same data produces a false winner, the
user chose "Plan the search". At drafting, no code for
this study existed, and no candle other than 15:50 had been read from the CNBC archive as a body ratio, band or
direction, nor joined with any price or index move. See "What was known".
- Revised after one read-only Codex review of the draft (10 points: 8 major, 2 minor; all applied; report in
  `data/codex_audits/spx_candle_realsearch_plan_codex.md`).
- Extended to a second candle source after the SPY study reported: asked whether the search should also cover SPY's
  candle, the user first answered "Keep SPX only", interrupted, and then wrote "do both charts". A second Codex
  review covered the extension (1 major and 3 minor points, all applied; report in
  `data/codex_audits/spx_candle_realsearch_plan2_codex.md`).
- Asked "Lock the two-chart search plan and run it?", the user wrote "Screw reviewing the code just keep going and
  more tests". Two changes followed, neither reviewed by Codex: the Codex code review was dropped (the selftest
  remains), and a third signal source was added: the index and SPY candles agreeing ("both"), at every minute,
  threshold, direction and strike. The grid grew from 4,752 to 7,128 cells; the luck diagnostic covers all of them,
  so the added cells raise the bar a pick must clear.

Addendum to `spx_candle_refine.md`, `spx_candle_realindex.md` and `spx_candle_realprice.md`. It repeats the
re-tuning study's design on candles a trader can see live: the SPX index and SPY. Two stated criteria decide; everything else is
descriptive. Research only. Nothing here is a trading recommendation.

## Why this exists

Every confirmed result so far reads the candle from the Dukascopy US500 CFD ("the feed"). The feed's candle is
published in daily history files after the session, so it cannot be read at 15:51. Read from the real SPX index
candle, which the live alert uses, the current rule did not meet its criterion (`spx_candle_realindex`: +$39.44 a
trade, t 1.53). Read from SPY's candle, which can also be seen live, it met its criterion (`spx_candle_spy`: +$71.74
a trade, t 2.35). The only re-tuning so far (`spx_candle_refine`) searched the feed's candles. Nobody has asked which
source, closing candle, threshold, direction and strike works best when the signal is read from a candle that can be
seen at the time.

A search of thousands of settings always finds a winner, so the answer has to come in two steps:
1. a pick from the first three years, judged against the best result of the same search with the signals
   shifted to other days;
2. one test of that pick on the later years.

## The question

1. **Tuning (2021-01-01 .. 2023-12-31).** Which candle source (SPX index, SPY, or both agreeing), candle minute (15:45-15:55), body
   threshold (0.40-0.95), direction (with or against) and strike (ITM20-OTM20) made the most money per day at real
   prices? Does the best one beat the luck diagnostic?
2. **Test (2024-01-01 .. 2026-10-20, once).** Does that one pick make money on days the tuning never used? Is it
   better than the reference rule on the same days?
3. **Descriptive.** After the decision is written: the whole-period ranking, which candle best predicts the index
   move to the close, and where 15:50 at 0.80 sits.

**What this is and is not.** The raw quotes and settlements of every day were used by earlier studies, and the
15:50 candles of both sources have already been examined against them; SPY was the third candle source tried on these
outcomes, chosen after the first two had been seen. The tuning step is a search, so its winner is biased
upward; the luck diagnostic asks only whether it beats the best of the same search with the signals shifted to
other days. The later period is held out from this study's numerical selection, but not from the research history
that motivated its design. All Part 2 results are retrospective numerical checks, not independent confirmation, and
no minute is described as clean or fresh. Any result is a candidate for the forward record, not an established
edge. The study uses CNBC's
archived bars and an instantaneous quote at the entry minute's open; it does not establish that the archived bar
equals the bar shown live, or that the trade could have been filled at that price.

**Reference rule.** R60: the index candle at 15:50, body at least 60% of the range, with the candle, ITM10. It is
the fixed historical index reference and the primary line of `spx_candle_realindex`, and it remains this study's
decision comparator despite later changes to the live alert. **Descriptive comparator.** S70: the SPY candle at
15:50, body at least 70%, with the candle, ITM10. S70 was pre-registered as Secondary B of `spx_candle_spy`, but it
was chosen as this study's descriptive comparator after its results were seen. For pick - S70, only dates on which
both daily series are non-missing are kept, valid no-signal zeros are kept, and the paired n and the dropped dates
are reported for each period. S70 comparisons cannot change the selection, the advancement or either Part 2
verdict.

## What was known when this was drafted (disclosed so the rules can be judged)

**From the index candle (CNBC archive), 2021-01-01 .. 2026-10-20 (`spx_candle_realindex`, run 2026-11-10T03:56Z).**
- 15:50 only, with the candle, ITM10 at the 15:51 ask:
  - by band: 60%+ 710 trades, +$39.44 a trade, +$21.39 a day, t 1.53; 70%+ 579, +$53.73, t 1.86; 60-70% 131,
    -$23.69, t -0.41;
  - by tenth of the ratio over 2021-2026, from 0.0-0.1 to 0.9-1.0 (80%+ made +$89 a trade over 438 trades);
  - by year (2021-2026) for the 60%+, 70%+ and 60-70% bands;
  - the disagreement table against the feed's candle (both strong +$80.95 over 520 trades; index only -$74.14 over
    190; feed only -$45.92 over 63);
  - the index move from 15:51 open to 15:59 close after 15:50 index candles, by band, for 2021-2026 and 2019-2020
    (70%+: +2.63 bps, t 4.55; 60-70%: +0.14 bps; under 60%: +0.23 bps).
- By year for 15:50, with, ITM10 (so its 2024-2026 results are known): 60%+ 2024 +$7, 2025 +$51, 2026 +$83 a
  trade; 70%+ +$32, +$19, +$104; 60-70% -$104, +$285, -$16.
- Separately, from the broker's (Robinhood) index bars, not this archive: the 15:50 candle and the 1,080 candles of
  15:30-15:59 on 36 sessions (2026-09-21 .. 2026-11-09), their ratios against the feed's, and the 15:50 forward
  record's index moves.
- Nothing else: no other candle minute of the index archive has been turned into a ratio, band or direction, or
  joined with any price, P&L or index move. The archive's other bars were used only as price levels (the alignment
  check of `spx_candle_realindex`) and counted (below).

**From the feed's candle (D1), at real option prices.**
- `spx_candle_refine` computed the full grid on 2021-2023 (candles 15:40-15:50, thresholds 0.40-0.90, both
  directions, nine strikes). Its pick, 15:50 at 0.80, with, ITM20, failed the luck diagnostic (p 0.21); on
  2024-2026 it made +$19 a day against +$30 for the current rule. Its descriptive threshold profile covered 15:50,
  with, at ITM10 and ATM, on 2021-2023 and 2024-2026.
- `spx_candle_realprice` priced every contract at entries 15:41-15:51, both directions, all nine strikes, on every
  day (raw payoffs); full-grid statistics only on 2013-2020, where the best cell was 15:42, 0.60, with, ATM.
- `spx_candle_refine`'s report also displayed previously available forward results (after 2026-10-20) for its
  pick and the current rule.
- `spx_candle_fills` priced the current rule entering late at 15:52, 15:53 and 15:55: being late cost money.
- Availability of raw quotes and settlements is not the same as a computed strategy outcome: entries at
  15:52-15:56 were not covered by the earlier full payoff grid (15:41-15:51), only by the late-entry check of the
  current rule's ITM10 contract.
- The feed's 15:50 bucket table, threshold sweep, walk-forward and correlations (`spx_candle_audit`).
- The feed and index candles are related (ratio correlation 0.78 at 15:50 over 1,310 days from the archive; 0.76
  across 1,080 candles from 15:30-15:59 on 36 sessions of the broker's bars), so the feed's results partly predict
  the index candle's, at 15:50 and probably at the other minutes.

**Index-level results on the feed (2013-2026).** The candle scan (41 features on 2013-2020; three candidates on
2021-2026), the 15:49-close study (the size of each minute 15:40-15:59 by year; the 15:50 minute is 2-3 times a
normal minute; the 15:50-to-15:51 direction P3), the momentum study, and the weak-body audit.

**The SPY candle (`spx_candle_spy.md`, locked 2026-11-10T05:01Z; one registered run 2026-11-10T05:06:20Z, reported
after this draft was written and before any lock).** Signal = SPY's 15:50 candle from CNBC's SPY archive
(`data/spx_1549/cnbc_spy_1m`, 1,312 of 1,322 days), same whole-cent test, same trade (ITM10 in the SPY candle's
direction at the 15:51 ask), 2021-01-01 .. 2026-10-20, as reported by the parent session:
- SPY body 60%+: 523 trades, +$71.74 a trade, +$28.62 a day, t 2.35 (its retrospective criterion met);
- SPY and index candles both 60%+ in the same direction: 504 trades, +$80.44, t 2.56 (met);
- SPY 70%+: 369 trades, +$103.40, t 2.84 (met), positive in each year 2021-2026;
- descriptive: SPY 60-70% -$4.14 (154 trades); SPY tenths 0.7-0.8 +$90, 0.8-0.9 +$137, 0.9-1.0 +$81; all three
  candles (feed, index, SPY) signal: 435 trades at +$112.78; SPY and index but not the feed: 69 at -$123; index and
  feed but not SPY: 82 at -$78; index only: 121 at -$46; feed only: 54 at -$34; SPY ratio against the feed's r 0.81
  and the index's r 0.90; index move after SPY 70%+ candles +3.42 bps (t 4.70); by-year tables for all three cells.
- From the SPY archive, as from the index archive, only the 15:50 candle has been classified, and only ITM10 "with"
  priced.

**Other.** Coverage counts below were computed before drafting from file contents only: which minute labels exist
in each archive file, and which minute stamps exist in each quote file. No price was read as a value. After the SPY
result, the SPY archive's minute labels were also counted (every one of 15:45-15:59 present in 1,435 of its 1,446
files for 2021-01-01 .. 2026-10-20); nothing else was read from it.

**What that means for the test.**
- **The exclusion family:** every 15:50 setting on any source (index, SPY or both), either direction, any threshold and strike. These
  settings are directly examined (with, ITM10, by year and by tenth or band) or closely related to examined settings
  (other strikes and the opposite direction trade on the same days); they were not necessarily individually
  evaluated. A pick in this family gets no Part 2 check.
- **Candles 15:45-15:49 and 15:51-15:55 on either archive have never been joined with an outcome.** The feed's
  2021-2023 results for 15:45-15:49 inform expectations for those minutes, and the three sources' candles are
  correlated (SPY against the index r 0.90 and against the feed r 0.81 at 15:50), but this does not alone
  disqualify them from the later-period check.
- Before locking, any SPY result or other outcome inspection that happened after this draft is recorded under "Fork
  disclosure". After locking, such results cannot alter this study's rules or reporting.

## Data

- **Signal candles, source "index":** the frozen CNBC .SPX archive `data/spx_1549/cnbc_1m/` (manifest
  `50d1fc7a3a597f19a64887149f280f5b54e0699e47f0412a3a3f2ce6ab6ca5e9`, 1,946 files, as frozen by
  `spx_candle_realindex`).
- **Signal candles, source "SPY":** the frozen CNBC SPY archive `data/spx_1549/cnbc_spy_1m/` (manifest
  `cfe31add76511c279ac30cfed6687c43103a8c635ab440768840ba1bc6b8912a`, 1,446 files, as frozen by `spx_candle_spy`).
  `spx_candle_spy.md` showed, from price levels, that its bars are traded prices, not dividend-adjusted, and that
  the bar labelled 15:50 covers the same minute as the index bar labelled 15:50.
- **Source "both":** derived, not read: at a given minute and threshold it signals when the index candle and the SPY
  candle both signal in the same direction (at p = 60 and 15:50 this is `spx_candle_spy`'s Secondary A). It is
  missing when either candle is missing or invalid, and zero when both are valid but do not both signal in the same
  direction.
- For both archives: the code recomputes each manifest and stops if either differs. Bars labelled 15:45 .. 15:55 are signal
  candles; the bar labelled HH:MM covers [HH:MM:00, HH:MM+1:00) New York time (alignment evidence in
  `spx_candle_realindex.md` and `spx_candle_spy.md`). Invalid bars (non-finite, high < max(open, close), low >
  min(open, close), high < low) are missing. The option traded is SPXW whichever source gives the signal.
- **Index moves (descriptive only):** the .SPX archive's bars 15:46 .. 15:59, for signals from any source.
- **Quotes, settlement, fee:** as `spx_candle_realprice.md`: Databento OPRA `cbbo-1m_1500-1601_k60`, the snapshot
  stamped exactly HH:MM:00 at the entry minute (no nearest-time substitution), same-day SPXW only; the official
  Cboe close; $0.09 a contract. No new data is bought.
- **Day axis (option analysis):** for each period, the sorted unique dates in `data/spx_1549/d1_days.csv` with
  calendar = full that have a quote file and a finite official close, with no `keep` restriction and no
  candle-availability restriction. n is its length. A missing or invalid candle gives a missing signal only for its
  own source and minute; a valid candle without a signal gives zero. Missing files, absent bars and invalid bars are
  reported separately by source, minute and year. No retry, back-fill or substitute source is allowed.
- **Bar validation:** each bar must have exactly four finite numbers (open, high, low, close), checked before
  rounding; then the invalid-bar rule above applies; direction and flatness are decided after rounding.
  Unreadable files, conflicting duplicate records or a file whose date disagrees with its name stop the run.
- **Coverage before drafting (counts only).** Every archive file that has a 15:50 bar has all bars 15:45 .. 15:59:
  2021 247, 2022 248, 2023 244, 2024 247, 2025 247, 2026 201 files, of which 154, 217, 244, 247, 247 and 201 are
  eligible days with quotes and a close (1,310 of 1,322, as in `spx_candle_realindex`). Every quote file of
  2021-01-01 .. 2026-10-20 (1,322) has a snapshot at each entry minute 15:46 .. 15:56. In the SPY archive, every one
  of the minute labels 15:45 .. 15:59 is present in 1,435 of its 1,446 files (2021-01-01 .. 2026-10-20, all full
  sessions, with and without a same-day expiry); `spx_candle_spy` found a valid 15:50 SPY bar on 1,312 of the 1,322
  days with quotes and a close.
- **Strike window.** The quote download holds the 25 strikes within 60 points of the feed's 15:51 ATM, at every
  entry minute; it is not re-centred or replenished. Earlier entries can have availability that depends on the
  later move, and later entries can move outside the window. The coverage gate limits this but does not remove the
  bias. Estimates concern retained days.

## Signal, trade and series

- **Signal** (the live alert's whole-cent test, generalised): convert open, high, low and close to whole cents with
  `int(round(x * 100))`; body = |close - open|, range = high - low. For a threshold of p hundredths (40, 45, ...,
  95) there is a signal if range > 0, close != open and 100 x body >= p x range. Its sign is +1 if close > open and
  -1 otherwise, times +1 for "with" and -1 for "against". At p = 60 this is exactly R60's test. For source "both",
  the candle's sign is the common sign of the two candles (definition under "Data").
- **Entry:** the next minute's open (candle 15:45 enters at 15:46:00, ..., candle 15:55 at 15:56:00).
- **Trade:** at each cell's exact entry snapshot, use only same-day SPXW quotes. A valid quote has finite bid and
  ask, ask > 0 and 0 <= bid <= ask; mid = (bid + ask) / 2. Pair strikes whose call and put are both valid with bids
  above 0; fewer than three pairs means no implied spot. Sort the pairs by (|call mid - put mid|, strike), take the
  first three, and let S = the median of K + call mid - put mid. ATM = floor(S / 5 + 0.5) x 5. An up signal buys the
  call at ATM - o and a down signal the put at ATM + o, o in (20, 15, 10, 5, 0, -5, -10, -15, -20), at the ask, with
  no substitute strike or snapshot. Conflicting quotes for one contract in one snapshot stop the run. P&L per
  contract = 100 x (intrinsic value at the official close - ask) - $0.09, at full precision. A signal with no spot
  or no valid quote for its contract is "not priced".
- **Per-day series of a cell:** the trade's P&L on a priced signal day; 0 on a day with a valid candle and no
  signal; missing if the candle is missing or invalid, or the trade could not be priced. "Mean per day" is the
  average of the non-missing days. **Coverage** of a cell = priced signals / valid non-zero signals; missing
  candles are outside that denominator and reported separately. "Share won" = trades with positive net P&L / priced
  trades.
- **Consistency check:** `realindex_trades.csv` lists priced R60
  trades only, and `spycandle_trades.csv` (same folder, same columns) priced S60 trades only (the SPY candle at
  15:50, 60%+, with, ITM10). For each file separately, within the step's date window (only those rows are read), the
  reconstructed set of priced dates must equal the file's date set, with no duplicates; sign, band, option kind and
  strike must match exactly, and P&L within an absolute $0.000001. A signal absent from its file is allowed only when
  the reconstruction finds no spot or no valid quote; its date and reason are recorded. The file cannot check unpriced or no-signal dates.
  **Timing.** During tuning, both the R60 and the S60 checks precede any statistic. During testing, the R60 check
  precedes the Part 2 statistics; the S60 check, and any pricing of SPY contracts other than the pick's, take place
  only after the Part 2 or skip decision is written (this overrides "before any statistic" for test-period S60). When
  Part 2 is skipped, the test-period R60 check also runs only after the skip decision is written. A failure before
  the decision stops the step. A test-period S60 mismatch found after the decision stops further reporting and marks
  the run invalid pending a documented implementation correction; it does not authorise reselection.

## The grid (7,128 cells)

Source index, SPY, both (3) x candle 15:45 ... 15:55 (11) x threshold 0.40 ... 0.95 in steps of 0.05 (12) x with/against
(2) x strike ITM20, ITM15, ITM10, ITM5, ATM, OTM5, OTM10, OTM15, OTM20 (9).

## Isolation (two separate processes, as `spx_candle_refine.md`)

**`tune`** reads only outcome-bearing inputs dated 2021-01-01 .. 2023-12-31: those files of both CNBC archives, those
official closes, those quote files (the loader refuses any other date) and the rows of `realindex_trades.csv` and
`spycandle_trades.csv` with those dates. File and date listings are metadata and may be read for any date. It writes `selection.json` and
`selection.sha256` (read-only), `tune_results.json` and the tuning section of `RESULTS.md`.

**`test`** refuses to run unless the selection hash matches. It reads 2024-01-01 .. 2026-10-20 and prices **only**
the pick's and R60's contracts until the Part 2 decision is written to `results.json`; it does not read the
test-period rows of `spycandle_trades.csv` before then. Only then does it compute
the Part 3 items. If the decision is "no test" or "exclusion family", that decision is written before any test-period
item is computed.

## Part 1: tuning (2021-01-01 .. 2023-12-31)

Definitions, eligibility, score, pick and ties exactly as `spx_candle_refine.md` Part 1, with this grid:
- **Halves:** H1 = 2021-01-01 .. 2022-09-30, H2 = 2022-10-01 .. 2023-12-31.
- **Score:** the plateau mean, the average of the cell's mean per day and its neighbours at threshold +/- 0.05 (same
  source, candle, direction and strike) that exist on the grid (neighbours count whether eligible or not; a neighbour with no finite mean is ignored; the
  cell's own mean must be finite).
- **Eligible**, all of: at least 100 trades; at least 40 in each half; a mean per day above 0 in each half;
  priced on at least 95% of its signal days overall and in each half.
- **Pick:** the eligible cell with the highest score. Exact ties go to the cell nearest R60 by grid-index Manhattan
  distance (a change of source, whichever two sources, one candle minute, one threshold step, a direction flip or
  one strike step each cost 1), then to the first in enumeration order (source in the order index, SPY, both;
  candle, threshold, with first, ITM20 first). No eligible cell: no pick and no test.

**Luck diagnostic (circular shift).** For each shift s in range(21, n - 21 + 1, 3), destination day i receives the
entire signal vector of day (i - s) mod n (the index and SPY candles, all 11 minutes and 12 thresholds together,
zeros and missing values included; the "both" signals are derived from the shifted index and SPY signals). Destination-day option payoffs, quote availability and half masks stay fixed. The direction ("against"
reverses the sign) is applied after shifting; realised trade P&L is never shifted. For each shift, recompute
eligibility (coverage included) and plateau scores over all 7,128 cells, including the exclusion family, and keep the
maximum eligible score (-infinity if none). p = (1 + shifts with maximum >= observed best) / (1 + shifts). If no
observed cell is eligible, the diagnostic is "not run". Quantiles of the shift maxima use linear interpolation and are
unavailable when either bracketing value is not finite; the number of shifts with no eligible cell is reported.

The benchmark keeps the dependence between cells and compares the whole registered search with shifted alignments.
It is not an exact no-predictability test: changes in expiry frequency, volatility and pricing, calendar effects and
serial dependence can upset its calibration. The reported p is a diagnostic tail fraction, not a research-wide
false-positive probability, and it does not pay for earlier studies.

**Goes to the test** only if all hold:
1. the pick is not in the exclusion family (every 15:50 setting on any source, either direction, any threshold
   and strike);
2. p <= 0.05;
3. on tuning, the paired per-day difference (pick - R60) has a mean above 0.

**Outcomes.** A pick in the exclusion family: "examined, or closely related to settings examined, on 2024-2026; it
can only be checked on future days", with no runner-up substituted. Any other failed condition: "No candidate
advanced under the prespecified rules", naming the failed gate.

**Paired difference** (here and in Part 2): pick series - R60 series on the same days; a day is dropped if either is
missing; 0 on no-signal days is kept. The paired n and dropped days are reported.

## Part 2: the test (2024-01-01 .. 2026-10-20, once)

Only if a pick went to the test. Statistics are the mean of the retained days and its Newey-West t exactly as
`spx_candle_realindex.md` (lag 5, Bartlett weights, retained days treated as consecutive, no small-sample
correction; fewer than 8 days or SE = 0 fails the line).
- **(a) Works:** the pick's mean per day > 0 with t >= 2.0.
- **(b) Better:** the paired difference (pick - R60) has mean > 0 with t >= 2.0.

Readings, with both criteria reported separately (including unavailable statistics):
- both met: "The pick met the retrospective profitability and paired-superiority criteria on 2024-2026";
- only (a): "The profitability criterion was met; paired superiority was not established";
- otherwise: "The profitability criterion was not met".

**Power.** Power has not been established. Detectability depends on signal frequency, retained days, variance,
serial dependence and, for the paired comparison, covariance with R60. R60's full-period t (1.53 over 1,309 days)
does not determine a candidate's power on the later period. Failing a criterion does not show that there is no
effect, or that the pick is worse.

## Part 3: descriptive (decides nothing)

**Timing.** Tuning descriptions may be written after the tuning decision. Every later-period and whole-period
description waits until the Part 2 decision (or the skip decision) is written. No Part 3 winner replaces the pick or
changes a verdict. "Best" in Part 3 means highest on the stated sample metric, not most predictive or best to trade.
Per-day t uses the daily series. Cost versions and yearly tables name their periods.

- **Tuning:** the 15 best eligible cells (score, mean per day, trades, both halves, coverage), the best cell for
  each candle minute, the null's median and 95th percentile, and p.
- **The whole-period ranking, 2021-01-01 .. 2026-10-20, labelled "looked at after the decision; in-sample; not a
  test":** whole-period eligibility requires only a finite mean per day, at least 200 priced trades and at least 95%
  coverage overall; there are no half-period conditions. Cells are ranked by raw mean per day (ties: distance to R60,
  then enumeration order); reported are mean per day, mean per trade, trades, share won and t, for the 15 best and
  the best per source and candle minute under the same rules. For comparison, a whole-period shift benchmark on its own day axis
  and shift list (range(21, n - 21 + 1, 3)) recomputes this eligibility and keeps the maximum raw mean per day over
  all cells, including the exclusion family (-infinity if none); its median and 95th percentile use the Part 1
  quantile rule.
- **Which candle best predicts the index move (descriptive):** for 2019-01-01 .. 2020-12-31 and 2021-01-01 ..
  2026-10-20 separately, on the sorted calendar = full base dates, without requiring quotes or a close. For each
  source, candle minute and threshold, with the candle, keep only non-zero signals with valid .SPX entry-minute and
  15:59 bars and an entry open above 0; no-signal days are left out, not set to zero. The SPY archive starts in 2021,
  so 2019-2020 has the index source only; 2021-2026 has all three. The move is 10,000 x sign x (15:59 close -
  entry-minute open) / entry-minute open, from unrounded price levels. Reported: signal days, mean signed bps, share
  of positive among non-zero signed moves, and the lag-5 Newey-West t on the retained days (zero moves stay in the
  mean and t). For comparison, for each shift s, destination date i receives the entire signal vector of date
  (i - s) mod N: every available source (the index only in 2019-2020; in 2021-2026 the index and SPY candles shifted
  together, with "both" derived from them), every
  minute and threshold, including zeros and missing signals, where N is the length of the period's full base-date
  axis. Destination-date SPX unsigned moves and their availability masks stay fixed (shifts range(21, N - 21 + 1,
  3)). The t of every cell is recomputed (n < 8 or SE = 0: unavailable), and the largest finite signed t over the period's cells
  (396 for 2021-2026, 132 for 2019-2020) is kept (-infinity if none); its median and 95th percentile use the Part 1 quantile rule. This does not establish a
  winning predictor.
- **The leads already seen:** the index cells 15:50, 0.80 and 0.85, the SPY cells 15:50, 0.70 and 0.80, and the
  "both" cell 15:50, 0.60, with, ITM10 and ITM20, on tuning and on the test period, labelled exclusion family.
- **For the pick (if any), R60 and S70:** the mid version, the $0.74-fee version, each year, and the paired per-day
  difference pick - S70 on each period (descriptive; S70 was chosen after its results were seen).
- **Not-priced counts** per cell (median and maximum), and by reason and half for the pick, R60 and S70.

## Text rules

- Say plainly that the outcomes were known, that 15:50 was already examined on both sources, that SPY was the third
  source tried, and that the whole-period ranking is in-sample.
- Never call the top of a ranking "the best rule"; call it the best-scoring setting on that period.
- If nothing goes to the test, say "no candidate advanced under the prespecified rules" and name the gate.
- Say that signals come from CNBC's archives, that a fill at the quoted ask ignores size and fast minutes, and that
  later entries were costly for the current rule (`spx_candle_fills`).
- No trading recommendation. Whether the live alert should log any setting is a separate decision for the user.

## Outputs and code

`backtests/spx_candle_realsearch/realsearch.py`, with commands `selftest`, `tune` and `test`, writes
`selection.json`, `selection.sha256`, `tune_results.json`, `results.json`, `RESULTS.md` and
`data/spx_1549/databento/realsearch_trades.csv` (every trade of the pick, R60 and S70 in both periods).
- It imports `refine.py`, `realprice.py`, `realindex.py` and `spycandle.py` read-only and reuses only primitives:
  quote parsing, valid quote, implied spot, ATM, intrinsic, `nw()`, the eligibility and plateau-score functions, the
  shift null, the archive manifest checks, `cents()` and bar validity. Reused grid functions must take this study's grid
  explicitly; inherited module constants and orchestration are not authoritative. The SHA-256 of every reused source
  file and of `realsearch.py` is recorded in the run log at the first `tune`. Orchestration is new.
- It refuses to run unless this file is in `preregistration/`, its SHA-256 is in `preregistration/LEDGER.md` and
  both archive manifests match.
- Runs, attempt records, input manifests and atomic writes as `refine.py`; one registered `tune` and one `test`; a
  corrected rerun needs a documented implementation defect and keeps the earlier output.
- The code is written after locking. At the user's instruction there is no Codex code review; this is a departure
  from the earlier studies, and errors that a review would have caught may remain. The selftest covers each new
  function on synthetic data, including the isolation guards, and must pass before `tune`.

## Choices fixed here (the user may change them before the lock)

1. **The grid:** three sources (index, SPY, both agreeing), candles 15:45-15:55, thresholds 0.40-0.95, both
   directions, nine strikes (7,128 cells). Wider grids find a higher best score by luck; the luck diagnostic accounts for the grid's size.
2. **Minimum trades:** 100 in tuning and 40 per half, with 95% coverage.
3. **Objective:** money per day at the ask, $0.09 fee. Per trade would favour rare, high thresholds.
4. **Split:** tune 2021-2023, test 2024-2026 once, as `spx_candle_refine`.
5. **Exclusion family:** every 15:50 setting on any source, both directions, all thresholds and strikes, gets no
   Part 2 check.

## Fork disclosure

Answer from the parent session ("SPX 12:49 volatility experiments", which ran `spx_candle_realindex` and owns
`spx_candle_spy`), 2026-11-10, as reported by it:
- **Computed from the archive:** only `realindex.py`'s one registered run: the 15:50 candle's bands in whole cents;
  ITM10 in the candle's direction at the 15:51:00 ask; the three cells overall and by year, so the 2024-2026 results
  of 15:50 "with" ITM10 are known (60%+: 2024 +$7, 2025 +$51, 2026 +$83 a trade; 70%+: +$32, +$19, +$104; 60-70%:
  -$104, +$285, -$16); the tenths table for 2021-2026 pooled; the both / index-only / feed-only table; the ratio
  relation; and the index move by 15:50 band for 2021-2026 and 2019-2020.
- **Level-only checks:** the 15:50 close against the feed's 15:49, 15:50 and 15:51 closes and against the broker's
  bar; for the SPY study, the index closes at 15:45, 15:49, 15:50 and 15:51 to align SPY.
- **Not computed from the archive:** any other candle minute's body, band or direction; any strike other than ITM10;
  "against"; any entry other than 15:51. The audit's 36-session comparison and its correlations used Robinhood bars,
  not this archive. The alert's two-feed log used live CNBC bars only from 2026-10-30, outside the period.
- **SPY:** `spx_candle_spy.md` ran once at 2026-11-10T05:06:20Z, covering the SPY 15:50 candle only; its result is
  under "What was known". From the SPY archive (manifest `cfe31add...`, 1,446 files, frozen), as from the index
  archive, only the 15:50 candle has been classified and only ITM10 "with" priced. The user then chose to include
  SPY's candle in this search.
- **After the SPY result, at the user's request, the live alert began reading SPY's 15:50 candle.** To fill the
  two-feed log's 36 sessions (2026-09-21 .. 2026-11-09), the parent took SPY's 15:50 bar from the frozen SPY archive
  for the 22 sessions up to 2026-10-20 (inside this study's period) and from live CNBC for the 14 after, classified
  it with the whole-cent test, and printed one tally: of the 20 sessions on which the index candle signalled, SPY
  signalled in the same direction on 18 (the index moved the candle's way on 12 of them, mean +1.47 points from the
  15:51 open to the 15:59 close) and did not on 2 (2026-10-02 and 2026-11-09). This is 15:50 only, with, joined with
  the index move only; no option price, other minute, threshold, strike or direction was computed. The parent will
  report anything further it computes from either archive before the lock.
- **Earlier SPY inspections (disclosed in `spx_candle_spy.md`).** Before the CNBC SPY study, Yahoo SPY one-minute
  bars had been analysed, including a 15:50 signal and index-move log covering 21 sessions (2026-09-22 ..
  2026-10-20) inside this study's period. Raw CNBC SPY bars had also been printed (15:45-15:49 on 2026-10-20, and the
  15:50 bars of 2026-06-15 and 2026-11-06), with no signal or outcome derived from them. The SPY report also showed
  that days without a SPY candle had worse feed-rule outcomes than days with one (-$60.43 against +$30.56 a day), so
  missing candles are not assumed to be independent of outcomes. These inspections, the outcome-informed choice of
  SPY as the third source and its favourable reported result are part of this search's research history, and the
  joint shift does not correct for that history. No SPY minute is a fresh, independent confirmation; the exclusion
  family nevertheless stays at 15:50, because the record does not justify excluding SPY's other minutes from the
  explicitly retrospective Part 2 check.
- `fetch_cnbc.py` refuses to write into `cnbc_1m`, so the archive cannot change during this study.
