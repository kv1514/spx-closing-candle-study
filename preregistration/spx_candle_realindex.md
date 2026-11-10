# Pre-registration: the 15:50 rule read from the real SPX index candle, and its 60-70% band

**Status: LOCKED 2026-11-09.** Locked by Claude (Fable 5.2) at the user's explicit instruction: asked whether to lock
the plan first or just run the backtest, the user chose "Lock it, then run (Recommended)". **No analysis code existed at locking.**
- Drafted 2026-11-09 (evening) by Claude (Fable 5.2) after the user asked for "a backtest with the 60-70%".
- Revised after one read-only Codex review of the draft (9 points: 7 major, 2 minor; all applied; report in
  `data/codex_audits/spx_candle_realindex_plan_codex.md`).
- At locking, no real-index candle had been joined with any option price or P&L, and no body ratio, band or
  direction had been computed from the archive. See "What was known".

Addendum to `spx_close_candle_scan.md` and `spx_candle_realprice.md`. One primary line and three secondary
lines; everything else is descriptive. Research only. Nothing here is a trading recommendation.

## The question

Every study so far read the 15:50 candle from the Dukascopy US500 CFD ("the feed"). A trader, and the live alert,
read the real SPX index candle. The audit of 2026-11-09 found, on the 36 sessions with both, that the index candle
shows a body of 60% or more on more days than the feed (20 against 14), and estimated that the feed's 60% is about
70% on the index candle. That left the index candle's 60-70% band not evaluated: "untested" here means not
previously evaluated across this archive with the option-pricing rule below.

CNBC serves archived one-minute SPX index bars, the same source the live alert uses. This study reads the 15:50
candle from that archive and asks, at the real option prices already on disk:

1. **Primary (source check).** Does the rule make money when the signal is the **index** candle with a body of at
   least 60%?
2. **Secondary A.** Does the **70% or more** band of the index candle make money on its own?
3. **Secondary B.** Does the **60-70%** band of the index candle make money on its own, lose money, or neither?
4. **Secondary C.** Is one of the two bands better than the other?

**What this is and is not.** It is an outcome-informed, retrospective check of the signal's source. It is not an
independent confirmation and not a new holdout: the option outcomes of these days are known, and its p-values do
not adjust for the research history that came before. It estimates performance using CNBC's archived
representation of the candle and an instantaneous 15:51:00 quote. It does not establish that the archived candle
equals the candle a broker shows live, or that the trade could have been executed at that price.

## What was known when this was locked (disclosed so the rules can be judged)

- **Every option outcome is known.** The option prices, the settlements and the day-by-day P&L of the trade are the
  ones in `spx_candle_realprice` (2021-01-01 to 2026-10-20): with the feed's signal, +$29.87 a day (Newey-West t
  2.40), 585 trades, +$67.46 a trade. This study changes only which candle decides whether and which way to trade.
- **The feed's body buckets are known** (audit, `backtests/spx_candle_audit/`): below 60% no edge (-$37 a trade at
  the ask, +$2 at the mid, 733 trades); 60-70% +$6; 70-80% +$42; 80-90% +$97; 90-100% +$122 (2021-2026, ITM10).
- **The rules here were informed by the audit's** threshold sweep, resampling, walk-forward and split-period
  comparisons, and body/outcome correlations (body ratio against the next index move: r +0.06 to +0.08).
- **The two candles are known to agree mostly.** On 36 sessions (2026-09-21 to 2026-11-09): correlation of the
  ratios 0.90 at 15:50; all 14 feed signals were also index signals in the same direction. The "about 70%"
  mapping also used 1,080 candles from 15:30-15:59 on those sessions, not only the 36 at 15:50. So the primary
  result will be highly correlated with the known feed result. **The new information is on days the two candles
  disagree.**
- **Real-candle results already published.** For those 36 sessions the index candle's band and the index move
  after 15:51 were tabulated: 17 days at 70%+ averaging +1.5 index points, 3 days at 60-70% averaging +3.9, 16
  days under 60% averaging +1.1; on the 6 days where only the index candle reached 60% the index went the
  candle's way 4 times; 2026-11-09 (a 62% index candle, +$986 at the ask) was highlighted. 22 of the 36 sessions
  (2026-09-21 to 2026-10-20) lie inside this study's period. The audit also stated an expectation: the index
  60-70% band is "around break-even to slightly negative". These are prior observations, not results of this
  study.
- **The CNBC archive before the lock.** While checking that the archive exists, the 15:50 bar of 11 dates was
  printed (2019-05-15, 2021-06-15, 2022-03-15, 2024-03-15, 2025-06-13, 2025-06-17, 2026-06-15, 2026-08-12,
  2026-09-10, 2026-10-09, 2026-11-06) and the 15:59 bar of four of them (2019-05-15, 2021-06-15, 2025-06-13,
  2025-06-17). Nothing was computed from them. After the download, and before the lock, only the checks listed
  under "Checks made before the lock" were run. They use price levels and file counts. No body ratio, band,
  direction, index move or P&L was computed from the archive.
- **Power is low for the 60-70% band, and this is stated now.** It should hold very roughly 100-200 trades. With a
  per-trade spread of results near $700, its average is then only known to within about $50-70 a trade, so only
  a large edge (above roughly $100-140 a trade) or a large loss would be detected. "Insufficient evidence" is the
  likely reading of lines 3 and 4 even if a modest edge or loss exists.

## Data

- **Index candle:** CNBC one-minute SPX bars, one file per session in `data/spx_1549/cnbc_1m/` (free; downloaded
  2026-11-09 by `backtests/spx_candle_realindex/fetch_cnbc.py`, which calls the live alert's own reader,
  `tools/spx_1550_alert.py` `cnbc_bars`; endpoint `ts-api.cnbc.com/harmony/app/bars/.SPX/1M/...`; each file
  records its retrieval time). Only the bar labelled 15:50 is used for the signal.
- **The intended signal interval** is [15:50:00, 15:51:00) America/New_York on each date (the vendor labels bars
  in exchange time, so no fixed UTC offset is applied). See the alignment evidence below.
- **Frozen inputs.** The archive as downloaded on 2026-11-09 is the input. Its manifest (the SHA-256 of the list
  of file names with each file's SHA-256) is `50d1fc7a3a597f19a64887149f280f5b54e0699e47f0412a3a3f2ce6ab6ca5e9` over 1,946 files. The code recomputes it and stops if it differs. Later
  revisions or back-fills by the vendor are not part of the registered run.
- **Retry rule, fixed:** the archive was filled as described under "Checks made before the lock" and then frozen.
  Whatever has no 15:50 bar in the frozen archive is missing. No session is requested again for the registered run,
  and no other source replaces a missing candle.
- **Invalid bars:** a 15:50 bar with a non-finite value, or with high < max(open, close), low > min(open, close)
  or high < low, is treated as missing and counted.
- **Option quotes, settlement, fee:** exactly as `spx_candle_realprice.md`: Databento OPRA `cbbo-1m` snapshot
  stamped exactly 15:51:00 ET (no nearest-time substitution), same-day SPXW only; official Cboe SPX close; $0.09 a
  contract. No new data is bought. Two different quotes for the same contract in the same snapshot stop the run.
- **Period:** 2021-01-01 to 2026-10-20, inclusive.
- **Base dates:** the unique dates in `data/spx_1549/d1_days.csv` with calendar = full in the period. No `keep`
  restriction applies.
- **Eligible days:** base dates that have (i) a Databento quote file, (ii) a finite official close and (iii) a
  valid CNBC 15:50 bar. Exclusions are reported separately, overall and by year, for: a "no same-day expiry"
  marker; no quote file and no marker; no official close; no CNBC file; an empty CNBC file or no 15:50 bar; an
  invalid 15:50 bar.
- **Coverage** = eligible days / base dates that have a quote file and a finite official close, overall and by
  year, with numerator and denominator.

**Coverage at locking** (file counts only; no base date lacks both a quote file and a marker, none lacks a close, and no 15:50 bar is invalid):

| Year | Full sessions | No same-day expiry | With quotes and a close | No CNBC 15:50 bar | Eligible | Coverage |
|---|---|---|---|---|---|---|
| 2021 | 251 | 93 | 158 | 4 | 154 | 97.5% |
| 2022 | 250 | 31 | 219 | 2 | 217 | 99.1% |
| 2023 | 248 | 0 | 248 | 4 | 244 | 98.4% |
| 2024 | 249 | 0 | 249 | 2 | 247 | 99.2% |
| 2025 | 247 | 0 | 247 | 0 | 247 | 100.0% |
| 2026 | 201 | 0 | 201 | 0 | 201 | 100.0% |
| **All** | 1446 | 124 | 1322 | 12 | **1310** | **99.1%** |

## Checks made before the lock (levels and counts only)

Run on 2026-11-09 by `backtests/spx_candle_realindex/prelock_checks.py` (output:
`backtests/spx_candle_realindex/prelock_checks.json`) and by the commands named below. They compare price levels
and count files. They compute no body, ratio, band, direction, index move or P&L.

- **The endpoint is unreliable for old dates, and how the archive was filled.** For dates before March 2026 the
  endpoint often answers with no bars and, asked again minutes later, with the full session. Each session was
  requested once (15:45-16:00); sessions without a 15:50 bar were then requested up to 10 more times, alternating a
  15:45-16:00 window and a full-session window, and then in up to 8 further passes of 2 requests each, until a pass
  recovered nothing. The first answer containing a 15:50 bar was kept. 756 of the 1595 filled sessions in the
  archive (2019-2026) answered the first request. Sessions of 2019-2020 were requested once only; they are used
  only in one descriptive line. The archive was then frozen (manifest above). 12 eligible-range
  sessions still have no bar and are missing.
- **Same answer when asked twice.** 40 sessions that already had bars were downloaded again
  (`fetch_cnbc.py --recheck 40`): 25 answered, and the 15:50 bar's four prices were identical on all 25.
- **Raw responses.** For 8 sessions on both sides of clock changes (2021-03-12, 2021-03-15, 2021-11-08,
  2022-06-15, 2023-03-13, 2026-03-06, 2026-03-09, 2026-10-20) the raw response is kept in
  `data/spx_1549/cnbc_1m/raw_samples/`. In each: 15 bars, every label on the minute and dated that day, no
  duplicate label, the 15:50 bar equal to the stored file, and the bar's own epoch time (`tradeTimeinMills`)
  equal to 15:50:00 New York time, in winter and in summer.
- **Against the broker's candle.** On the 22 sessions of the period that also have the broker's SPX
  minute bars (Robinhood, bars labelled by their start; 2026-09-21 to 2026-10-20), the 15:50 bar's four prices
  are equal on 21 and differ on 1 (2026-09-22: open and high differ by up to
  1.09; low and close are equal). On 14 later sessions outside the period (2026-10-21 to
  2026-11-09, six of them after the 1 November clock change) all four prices are equal on all 14. So the archived
  candle is, with rare differences in the first tick of the minute, the candle the broker shows. Databento's
  official Cboe index bars (DBIX.CORE) exist from 2026-10-27 and were not bought.
- **Which minute.** The live alert receives the bar labelled 15:50 a few seconds after 15:51:00, which is what a
  bar labelled by its start does. Independently, the mean absolute gap between the CNBC 15:50 bar's close and the
  feed's close is smallest at the feed's 15:50 bar in every year and in the weeks around clock changes (index
  points):

| Year | Days | vs feed 15:49 close | vs feed 15:50 close | vs feed 15:51 close |
|---|---|---|---|---|
| 2019 | 83 | 0.90 | **0.25** | 0.71 |
| 2020 | 78 | 3.58 | **0.42** | 1.85 |
| 2021 | 247 | 2.16 | **0.34** | 1.26 |
| 2022 | 248 | 3.72 | **0.44** | 2.09 |
| 2023 | 244 | 2.05 | **0.31** | 1.26 |
| 2024 | 247 | 2.40 | **0.37** | 1.66 |
| 2025 | 247 | 3.87 | **0.41** | 1.96 |
| 2026 | 201 | 3.30 | **0.49** | 1.54 |
| Weeks around clock changes | 140 | 2.89 | **0.45** | 1.83 |

  The option-implied index moved with the feed's 15:50 bar and not its neighbours (audit), so the CNBC bar
  labelled 15:50 covers [15:50:00, 15:51:00) New York time.
- **What these checks cannot show:** that an archived bar equals the bar CNBC showed live on that day, or that the
  12 missing sessions are unrelated to results (that comparison is descriptive and comes after the join).

## Signal and bands (the live alert's own test)

Parse the 15:50 bar's open, high, low and close as binary64 floats and convert each to whole cents with
`int(round(x * 100))`, exactly as `cents()` in `tools/spx_1550_alert.py`. Body = |close - open| and range = high -
low, in cents. Direction = up if close > open, down if close < open. On a valid bar:
- **No signal:** range = 0, or close = open, or 10 x body < 6 x range.
- **60-70% band:** 10 x body >= 6 x range and 10 x body < 7 x range.
- **70%+ band:** 10 x body >= 7 x range.
- **R60** (the rule on the index candle) = the two bands together.
No band is ever decided from a displayed or rounded ratio.

## The trade (unchanged from `spx_candle_realprice.md`)

On a signal day, at the 15:51:00 snapshot:
- a valid quote has finite bid and ask, ask > 0 and 0 <= bid <= ask; mid = (bid + ask) / 2;
- a strike is paired if its call and its put both have a valid quote with a bid above 0;
- fewer than three paired strikes means no implied spot;
- rank the paired strikes by (|call mid - put mid|, strike) and take the first three; implied spot S = the median
  of K + call mid - put mid over those three;
- ATM = floor(S / 5 + 0.5) x 5; up buys the call at ATM - 10, down buys the put at ATM + 10, at the ask;
- held to settlement at the official close; P&L per contract = 100 x (intrinsic value - ask) - $0.09, at full
  precision.
A signal day with no implied spot or no valid quote for its contract is "not priced".

## Per-day series and the statistic

For each cell (R60, the 70%+ band, the 60-70% band) separately: the trade's P&L on an eligible day inside the
cell; 0 on every eligible day outside the cell, whether or not a trade could have been priced that day; missing
on a day inside the cell that is not priced, never 0. So the 60-70% band's series is 0 on 70%+ days and on
no-signal days. Each cell's number of days, trades and unpriced days (by reason and year) is reported.

The statistic is the mean of the non-missing days and its Newey-West t, as `nw()` in
`backtests/spx_candle_audit/audit.py`: drop non-finite values, keep date order and treat the retained days as
consecutive; with n days and residuals e = y - mean,
V = [ sum(e^2) + 2 x sum over j = 1..5 of (1 - j/6) x sum over i = j+1..n of e_i x e_(i-j) ] / n,
SE = sqrt(max(V, 0) / n), t = mean / SE, with no small-sample correction. If n < 8 or SE = 0 the t is unavailable
and that line is "not assessed".

## Verdict lines (fixed now)

1. **Primary, R60:** "source-check criterion met" if the mean per day is above 0 with t >= 2.0. Otherwise
   "source-check criterion not met".
2. **Secondary A, 70%+ band:** "has an edge" needs a mean per day above 0, t >= 2.0 and a Holm-adjusted p <= 0.05.
   p = 1 - Phi(t).
3. **Secondary B, 60-70% band:** "has an edge" needs a mean per day above 0, t >= 2.0 and a Holm-adjusted p <= 0.05;
   "loses" needs a mean per day below 0, t <= -2.0 and a Holm-adjusted p <= 0.05. p = 2 x Phi(-|t|).
4. **Secondary C, the comparison:** the difference in mean P&L per priced trade, 70%+ band minus 60-70% band, with
   Welch's t: unbiased sample variances, SE = sqrt(s1^2 / n1 + s2^2 / n2), Welch-Satterthwaite degrees of freedom,
   two-sided Student-t p. "70%+ is better" needs t >= 2.0 and a Holm-adjusted p <= 0.05; "60-70% is better" needs
   t <= -2.0 and a Holm-adjusted p <= 0.05. If either band has fewer than two priced trades or SE = 0 it is "not
   assessed". Welch's test is an approximation that ignores serial dependence.

Holm's adjustment is applied across the three secondary p-values (a line that is not assessed enters with p = 1).
A secondary line that does not meet its conditions reads **"insufficient evidence"**. The primary line is not
adjusted.

**Coverage rule.** If coverage is below 80%, the estimates are reported descriptively and every verdict line reads "not assessed: incomplete coverage". (Coverage at locking is 99.1%.)

## Descriptive (decides nothing, and never alters a verdict line or an exclusion)

- Each cell: trades, per trade at the ask and at the mid, share won, median, worst, average cost, by year.
- **The disagreement table**, the most informative part: eligible days that are also in the feed's kept set, split
  by (index: signal up, signal down, no signal) x (feed: signal up, signal down, no signal), with the number of
  days in each cell. For the groups "both, same direction", "both, opposite directions", "index only" and "feed
  only": the P&L per trade of ITM10 in the index candle's direction (in the feed candle's direction for "feed
  only"), at the ask and at the mid. No hypothetical trade is formed on a day where neither candle signals.
- The index candle's ratio in buckets of 0.10 from 0 to 1 (left-closed, right-open, 1 included in the last):
  trades and P&L per trade at the ask and the mid, trading in the candle's direction; flat candles are left out
  and counted.
- The relation between the two ratios over all days with both: correlation, least-squares line, and the share of
  days in each index band that fall in each feed band. This replaces the 36-session estimate.
- Coverage: days missing a CNBC bar by year and month, the longest run of missing days, and the feed rule's known
  P&L on days with and without a CNBC bar. This comparison is made only after the join and cannot change an
  exclusion or a verdict line.
- The index move in the candle's direction, 10,000 x sign x (15:59 close - 15:51 open) / (15:51 open) from the
  CNBC bars, by band, for 2021-2026 and, where the archive has bars, 2019-2020; a day missing either bar, or with a
  flat candle, is left out and counted.

## Rules of the run

- The code is written after the lock, checks that this plan's hash is in the ledger and that the archive's
  manifest matches, and refuses to join any candle with any price otherwise.
- Codex reviews the code read-only before the run; defects are fixed without changing this plan.
- One registered run, with its log kept. A corrected rerun needs a documented implementation defect, the earlier
  output preserved next to the new one, and no change to any rule here.
- The result is reported whatever it is. Any departure from this plan is reported as a labelled deviation next to
  the result.
