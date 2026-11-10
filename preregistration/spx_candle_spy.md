# Pre-registration: the 15:50 rule read from the SPY candle, a candle a trader can see live

**Status: LOCKED 2026-11-10 (UTC).** Locked by Claude (Fable 5.2) at the user's explicit instruction: asked "Lock the plan in the
ledger and run the test once?", the user chose "Lock it and run (Recommended)". **No analysis code existed at locking.**
- Drafted 2026-11-09 (late evening) by Claude (Fable 5.2). The user, shown the real-index result, was asked "Test
  whether SPY's candle, which you can see live, works like the backtest's feed?" and answered "Yes, test it".
- Revised after one read-only Codex review of the draft (8 points: 6 major, 2 minor; all applied; report in
  `data/codex_audits/spx_candle_spy_plan_codex.md`).
- At locking, no SPY candle had been joined with any option price, P&L or later index bar, and no body ratio, band
  or direction had been computed from the SPY archive. See "What was known".

Addendum to `spx_candle_realprice.md` and `spx_candle_realindex.md`. One primary line and two secondary lines;
everything else is descriptive. Research only. Nothing here is a trading recommendation.

## The question

The rule met its earlier numerical criterion when its signal is read from the Dukascopy US500 CFD candle ("the
feed"): +$67.46 a trade, Newey-West t 2.40, 2021-2026. That candle cannot be seen live for free. Read from the real
SPX index candle, which can, the rule did not meet its criterion (`spx_candle_realindex`: +$39.44 a trade, t 1.53),
and the gain sat on days when the feed's candle and the index candle both showed a strong body.

The feed follows the futures; SPY, the ETF, trades live and also follows them closely. This study reads the 15:50
candle from archived one-minute **SPY** bars and asks, at the same SPXW option prices:

1. **Primary.** Does the rule make money when the signal is the **SPY** candle with a body of at least 60%?
2. **Secondary A, the agreement rule.** Does it make money on days when the **SPY candle and the SPX index candle
   both** show a body of at least 60%, in the same direction? Both can be seen live.
3. **Secondary B.** Does the **70% or more** band of the SPY candle make money on its own?

**What this is and is not.** This third-source analysis and Secondary A were selected after examining the same
outcomes, including the favourable subgroup in which the feed's candle and the index candle agreed. Locking now
prevents further adaptation but does not remove that selection. All three verdict lines describe retrospective
numerical criteria, not an independent confirmation, a new holdout or an established trading edge. Holm's
adjustment covers only the two secondary lines, not the research search that came before. The study estimates
performance from one vendor's archived SPY bars (CNBC's "adjusted" bars, see below) and an instantaneous 15:51:00
quote. It does not establish that the archived bar equals the bar another vendor shows live, or the bar CNBC
showed on the day, or that the trade could have been executed at that price.

## What was known when this was locked (disclosed so the rules can be judged)

- **Every option outcome is known**, by day, as in `spx_candle_realprice` and `spx_candle_realindex`.
- **The real-index study's results** (2021-01-01 to 2026-10-20, ITM10 at the 15:51 ask): index candle 60%+ +$39.44
  a trade (710 trades, t 1.53, criterion not met); 70%+ +$53.73 (t 1.86); 60-70% -$23.69. Descriptive: both the
  feed's and the index candle strong, 520 trades at +$80.95; index candle only, 190 at -$74.14; feed only, 63 at
  -$45.92; index candles of 80%+ made +$89 over 438 trades; the feed's and the index candle never signalled
  opposite directions. The feed's bucket results, threshold sweeps and correlations from the audit are also known.
- **The motive is itself a hypothesis formed from those results:** that a futures-following candle carries the
  signal and the index candle adds days without it. Secondary A was chosen because "both candles agree" did well
  for the feed and the index candle. That choice is outcome-informed.
- **Earlier SPY minute bars from another vendor were inspected and analysed before this draft.** A recorder kept
  Yahoo SPY one-minute bars for September to November 2026 (`data/bars_1m/SPY_1m_2026-*.csv`,
  `data/yahoo_1m/SPY_1m.csv`). They were used to validate the feed (correlation of its returns with SPY's) and in
  the candle-scan forward log (`data/spx_1549/forward/candle_1550_log.csv`), which holds, for 21 sessions
  (2026-09-22 to 2026-10-20) inside this study's period and more after it, the recorded SPY 15:50 candle, its
  strong-body flag and whether the index then moved its way. On those 21 sessions the SPY candle and the feed's
  candle gave the same strong-body reading on 19 (SPY signalled on 9, the feed on 7).
- **SPY option results** (`spx_candle_mini`: SPY 0DTE options broke even) are about SPY's options, not its candle.
- **The SPY archive before the lock.** While checking that the archive exists, four bar printouts covering three
  distinct dates were made (the 15:50 bar of 2026-06-15 and 2026-11-06, and the 15:45-15:49 bars of 2026-10-20).
  Nothing was computed from them. After the download, and before the lock, only the checks listed under "Checks
  made before the lock" were run. They use price levels and file counts. No body ratio, band, direction, index
  move or P&L was computed from the SPY archive.

## Data

- **SPY candle:** CNBC one-minute SPY bars, one file per session in `data/spx_1549/cnbc_spy_1m/`, downloaded
  2026-11-09/10 by `backtests/spx_candle_realindex/fetch_cnbc.py --symbol SPY --out cnbc_spy_1m` (endpoint
  `ts-api.cnbc.com/harmony/app/bars/SPY/1M/.../adjusted/EST5EDT.json`, the same parser as the index archive; each
  file records its retrieval time, the number of requests and the window that answered). Only the bar labelled
  15:50 is used for the signal. The response names the listing exchange (NYSE Arca); which trades CNBC builds the
  bar from (odd lots, sub-penny prints, late or corrected trades, auction prints) is **not documented and is
  unknown**.
- **This is a study of CNBC's frozen "adjusted" SPY archive.** What "adjusted" does is examined under "Checks made
  before the lock" and stated there. No claim is made that the archive reconstructs the candle shown live on the
  day.
- **The intended signal interval** is [15:50:00, 15:51:00) America/New_York on each date.
- **Frozen inputs.** The SPY archive as downloaded is the input. Its manifest (the SHA-256 of the list of file names
  with each file's SHA-256) is `cfe31add76511c279ac30cfed6687c43103a8c635ab440768840ba1bc6b8912a` over 1,446 files. The SPX index archive is the one frozen by `spx_candle_realindex.md`
  (manifest `50d1fc7a3a597f19a64887149f280f5b54e0699e47f0412a3a3f2ce6ab6ca5e9`, 1,946 files). The code recomputes
  both and stops if either differs. A recheck response never replaces a frozen file.
- **Retry rule, fixed:** the archive was filled as described under "Checks made before the lock" and then frozen.
  Whatever has no 15:50 bar in the frozen archive is missing. No session is requested again for the registered run,
  and no other source replaces a missing candle.
- **Option quotes, settlement, fee:** Databento OPRA `cbbo-1m` snapshot stamped exactly 15:51:00 ET (no
  nearest-time substitution), same-day SPXW only; official Cboe SPX close; $0.09 a contract. No new data is bought.
  Two different quotes for the same contract in the 15:51:00 snapshot stop the run.
- **Period:** 2021-01-01 to 2026-10-20, inclusive.
- **Base dates:** the unique dates in `data/spx_1549/d1_days.csv` with calendar = full in the period. No `keep`
  restriction applies.
- **Eligible days and exclusions**, mutually exclusive and applied in this order: if no quote file exists, the day
  is excluded as "no same-day expiry" when a marker exists and as "no quote file, no marker" otherwise (a marker is
  ignored when a quote file exists); then no finite official close; then no SPY file; then no 15:50 entry (an
  empty `bars` object means no 15:50 bar); then an invalid bar. A valid bar has exactly four finite numbers with
  high >= max(open, close), low <= min(open, close) and high >= low, judged before rounding. The run stops on
  unreadable JSON or on a file whose name and stored date disagree.
- **Coverage** = eligible days / base dates that have a quote file and a finite official close, overall and by
  year, with numerator and denominator. Only overall coverage controls the 80% rule.

**Coverage at locking** (file counts only; no base date lacks both a quote file and a marker, none lacks a close, no SPY file is missing and 0 15:50 bars are invalid):

| Year | Full sessions | No same-day expiry | With quotes and a close | No SPY 15:50 bar | Eligible | Coverage | Eligible with an index bar |
|---|---|---|---|---|---|---|---|
| 2021 | 251 | 93 | 158 | 2 | 156 | 156/158 = 98.7% | 152 |
| 2022 | 250 | 31 | 219 | 2 | 217 | 217/219 = 99.1% | 215 |
| 2023 | 248 | 0 | 248 | 2 | 246 | 246/248 = 99.2% | 242 |
| 2024 | 249 | 0 | 249 | 0 | 249 | 249/249 = 100.0% | 247 |
| 2025 | 247 | 0 | 247 | 3 | 244 | 244/247 = 98.8% | 244 |
| 2026 | 201 | 0 | 201 | 1 | 200 | 200/201 = 99.5% | 200 |
| **All** | 1446 | 124 | 1322 | 10 | **1312** | **1312/1322 = 99.2%** | 1300 |

## Checks made before the lock (levels and counts only)

These checks were specified here before they were run. They compare price levels and count files; they compute no
body, ratio, band, direction, index move or P&L, and they cannot be used to prefer one vendor because it later
performs better.

1. **Download record:** the commands, the retry limits, the stopping rule and the counts; the first response
   containing a 15:50 bar is the one kept.
2. **Raw responses** for 2021-03-12, 2021-03-15, 2021-11-08, 2022-06-15, 2023-03-13, 2026-03-06, 2026-03-09 and
   2026-10-20 (kept in `data/spx_1549/cnbc_spy_1m/raw_samples/` when the endpoint answers): symbol, date, every
   label on the minute, no duplicate label, the 15:50 bar equal to the stored file, and the bar's own epoch time
   converted with America/New_York.
3. **Labels denote interval starts** (an epoch equal to the label does not show this by itself): the close of the
   SPY bar labelled 15:50, scaled by that day's ratio of the index bar's close to the SPY bar's close at 15:45, is
   compared with the index archive's close at 15:49, 15:50 and 15:51, by year. The same offsets are compared against
   each earlier SPY archive.
4. **Recheck:** 40 sessions that already have bars are downloaded again (seed 20261109); unanswered requests, exact
   equality of the four prices and equality after the whole-cent conversion are reported separately.
5. **Against the earlier SPY archives** (`data/bars_1m/SPY_1m_2026-*.csv` and `data/yahoo_1m/SPY_1m.csv`, each
   separately), on every overlapping session, for the 15:50 bar: overlap count, exact matches, whole-cent matches,
   and the median and largest absolute difference of each of the four prices.
6. **What "adjusted" does:** the archive's 15:59 close is compared with the unadjusted SPY daily close
   (`data/spx_1549/spy_daily_closes.csv`, Yahoo, split-adjusted only) by year. A ratio near 1 in every year means
   the bars are not dividend-adjusted; a ratio that falls for older years means they are, in which case the
   whole-cent rounding acts on scaled prices and this is stated.

Results (run 2026-11-10 UTC by `backtests/spx_candle_spy/prelock_checks.py`, output in
`backtests/spx_candle_spy/prelock_checks.json`, and by the commands named):

1. **Download record.** `fetch_cnbc.py --symbol SPY --out cnbc_spy_1m` asked for each session once (15:45-16:00);
   `fill_passes.sh START END 10 SPY cnbc_spy_1m` then made up to 10 passes of 2 requests each over the sessions
   still without a 15:50 bar (alternating a 15:45-16:00 and a full-session window), stopping at the first pass that
   recovered nothing (pass 10 for 2023-12-01 to 2026-10-20, pass 9 for 2021-01-01 to 2023-11-30). The first answer
   containing a 15:50 bar was kept. 587 of the 1435 filled sessions answered the first request. The archive was
   then frozen (manifest above); 10 sessions of the coverage denominator still have no bar and are
   missing.
2. **Raw responses.** The endpoint answered for 5 of the 8 named dates (2021-03-15, 2023-03-13, 2026-03-06, 2026-03-09, 2026-10-20); 2021-03-12,
   2021-11-08 and 2022-06-15 gave no answer in 10 requests. In each kept response: symbol SPY, 15 bars, every label
   on the minute and dated that day, no duplicate label, the 15:50 bar equal to the stored file: all true.
   The 15:50 bar's own epoch time in New York: 2021-03-15: 2021-03-15 15:50:00 EDT; 2023-03-13: 2023-03-13 15:50:00 EDT; 2026-03-06: 2026-03-06 15:50:00 EST; 2026-03-09: 2026-03-09 15:50:00 EDT; 2026-10-20: 2026-10-20 15:50:00 EDT.
3. **Labels denote interval starts.** Mean absolute gap, in index points, between the SPY 15:50 close (scaled by
   that day's 15:45 index/SPY ratio) and the index archive's close:

   | Year | Days | vs index 15:49 close | vs index 15:50 close | vs index 15:51 close |
   |---|---|---|---|---|
   | 2021 | 244 | 2.17 | **0.28** | 1.18 |
   | 2022 | 246 | 3.79 | **0.37** | 2.03 |
   | 2023 | 242 | 2.06 | **0.27** | 1.20 |
   | 2024 | 247 | 2.43 | **0.34** | 1.53 |
   | 2025 | 244 | 3.96 | **0.41** | 1.89 |
   | 2026 | 200 | 3.33 | **0.39** | 1.61 |

   The 15:50 column is the smallest in every year. The index bar labelled 15:50 was itself shown to cover
   [15:50:00, 15:51:00) in `spx_candle_realindex.md`, so the SPY bar labelled 15:50 covers the same minute.
4. **Recheck** (`fetch_cnbc.py --symbol SPY --out cnbc_spy_1m --recheck 40`, seed 20261109): 25 sessions answered and
   15 did not; the four prices were exactly equal on all 25 (so also equal in whole cents); none differed.
5. **Against the earlier SPY archives** (Yahoo bars; the two files hold largely the same recorded data):
   - `data/bars_1m/SPY_1m_2026-*.csv`: 21 overlapping sessions (2026-09-22 to 2026-10-20); exactly equal on 0 (the other file stores 32-bit floats, so exact equality cannot occur); equal after the whole-cent conversion on 13; median absolute difference 0 for each of the four prices; largest differences open 0.0200, high 0.0075, low 0.0050, close 0.0100. The CNBC 15:50 close is 0.0014 from the other archive's 15:50 close on average, against 0.3340 for its 15:49 and 0.1494 for its 15:51 close.
   - `data/yahoo_1m/SPY_1m.csv`: 22 overlapping sessions (2026-09-21 to 2026-10-20); exactly equal on 0 (the other file stores 32-bit floats, so exact equality cannot occur); equal after the whole-cent conversion on 14; median absolute difference 0 for each of the four prices; largest differences open 0.0200, high 0.0075, low 0.0050, close 0.0100. The CNBC 15:50 close is 0.0014 from the other archive's 15:50 close on average, against 0.3343 for its 15:49 and 0.1435 for its 15:51 close.
   So the two vendors' SPY candles are the same minute, and on about a third of sessions they differ by a cent or
   two in at least one price. That is more disagreement than between two vendors' index candles (equal on 35 of 36
   sessions), and it can move a borderline candle across a band edge. **The SPY candle is therefore
   vendor-dependent, and this study speaks for CNBC's archived candle only.**
6. **What "adjusted" does.** Ratio of the archive's 15:59 close to the unadjusted daily close: 2021: median 0.99994 (range 0.9991 to 1.0017, 248 days); 2022: median 1.00000 (range 0.9989 to 1.0018, 248 days); 2023: median 1.00000 (range 0.9995 to 1.0003, 246 days); 2024: median 0.99996 (range 0.9992 to 1.0008, 249 days); 2025: median 1.00000 (range 0.9903 to 1.0017, 244 days); 2026: median 0.99993 (range 0.9977 to 1.0045, 200 days). The
   median is 1 in every year, so these bars are **not dividend-adjusted**: they are traded prices, and the
   whole-cent conversion acts on real prices. (The day-to-day range reflects the last minute and the closing
   auction, not an adjustment.) 927 of the 5740 prices in the valid 15:50 bars are not on a
   whole cent (sub-penny prints) and are rounded as specified.

**What these checks cannot show:** which trades CNBC includes in a bar; that an archived bar equals the bar shown
live on the day; or that the missing sessions are unrelated to results (that comparison is descriptive and comes
after the join).

## Signal and bands

Parse the SPY 15:50 bar's open, high, low and close as binary64 floats and convert each to whole cents with
Python's `int(round(x * 100))` (binary64 multiplication, ties to even), exactly as `cents()` in
`tools/spx_1550_alert.py`. Direction and flatness are judged after the conversion. Body = |close - open|, range =
high - low, in cents. Direction = up if close > open, down if close < open. On a valid bar:
- **No signal:** range = 0, or close = open, or 10 x body < 6 x range.
- **60-70% band:** 10 x body >= 6 x range and 10 x body < 7 x range.
- **70%+ band:** 10 x body >= 7 x range.
The **index candle's** signal and direction are computed in the same way from the frozen index archive's 15:50 bar
(valid by the same rule). The **feed's** signal, used only in descriptive tables, keeps its original test in
binary64 without cent rounding: range > 0 and |close - open| >= 0.6 x range, direction = sign(close - open).

## The trade (unchanged from `spx_candle_realindex.md`)

On a signal day, at the 15:51:00 snapshot:
- a valid quote has finite bid and ask, ask > 0 and 0 <= bid <= ask; mid = (bid + ask) / 2;
- a strike is paired if its call and its put both have a valid quote with a bid above 0;
- fewer than three paired strikes means no implied spot;
- rank the paired strikes by (|call mid - put mid|, strike) and take the first three; implied spot S = the median
  of K + call mid - put mid over those three;
- ATM = floor(S / 5 + 0.5) x 5; up buys the call at ATM - 10, down buys the put at ATM + 10, at the ask;
- held to settlement at the official close; P&L per contract = 100 x (intrinsic value - ask) - $0.09, at full
  precision.
The direction is the **SPY candle's**. A signal day with no implied spot or no valid quote for its contract is
"not priced".

## Cells, per-day series and the statistic

- **S60 (primary):** the SPY candle signals (either band).
- **AGREE (Secondary A):** the SPY candle signals, the index candle signals, and their directions are the same.
- **S70 (Secondary B):** the SPY candle is in its 70%+ band.

For S60 and S70: the trade's P&L on an eligible day inside the cell; 0 on every eligible day outside the cell,
whether or not a trade could have been priced that day; missing on a day inside the cell that is not priced, never
0. For AGREE: a missing or invalid index bar takes precedence over every other assignment, so such a day is missing
even when the SPY candle does not signal; otherwise the same rules apply. The number of eligible days with a usable
index bar is reported. Each cell's days, signal days, trades and missing days (by reason and year) are reported.

The statistic is the mean of the non-missing days and its Newey-West t, as `nw()` in
`backtests/spx_candle_audit/audit.py`: drop non-finite values, keep date order and treat the retained days as
consecutive; with n days and residuals e = y - mean,
V = [ sum(e^2) + 2 x sum over j = 1..5 of (1 - j/6) x sum over i = j+1..n of e_i x e_(i-j) ] / n,
SE = sqrt(max(V, 0) / n), t = mean / SE, with no small-sample correction. If n < 8 or SE = 0 the t is unavailable
and that line is "not assessed".

## Verdict lines (fixed now)

1. **Primary, S60:** "retrospective criterion met" if the mean per day is above 0 with t >= 2.0. Otherwise
   "retrospective criterion not met".
2. **Secondary A, AGREE:** "retrospective secondary criterion met" needs a mean per day above 0, t >= 2.0 and a
   Holm-adjusted p <= 0.05.
3. **Secondary B, S70:** "retrospective secondary criterion met" needs a mean per day above 0, t >= 2.0 and a
   Holm-adjusted p <= 0.05.

For both secondary lines p = 1 - Phi(t), with Phi the standard normal distribution function. With the two p-values
sorted as p1 <= p2, the Holm-adjusted values are min(1, 2 x p1) and min(1, max(2 x p1, p2)), mapped back to their
lines; a line that is not assessed enters with p = 1. A secondary line that does not meet its conditions reads
**"insufficient evidence"**. The primary line is not adjusted.

**Coverage rule.** If overall coverage is below 80%, the estimates are reported descriptively and every verdict
line reads "not assessed: incomplete coverage". This overrides everything else; otherwise a line whose statistic is
unavailable reads "not assessed".

## Descriptive (decides nothing, and never alters a verdict line or an exclusion)

Conventions for every descriptive table: P&L is at the ask unless "mid" is stated, and "mid" changes only the entry
cost; "won" means a net P&L above 0; average cost is 100 x ask, without the fee; an empty group is reported as not
available; a count of days is taken before any trade is dropped for being unpriced, and unpriced trades are
counted separately.

- Each cell, and the SPY 60-70% band: trades, per trade at the ask and at the mid, share won, median, worst,
  average cost, by year.
- **The feed rule on the same eligible days**, for comparison: trades and per trade (feed kept set, usable feed
  bar).
- **Three candles.** Population: eligible days with a valid index bar, a usable feed bar and feed `keep` = true.
  Split by which of the three candles (SPY, index, feed) signal: the number of days in each of the 8
  combinations; the number of days on which any two signalling candles point in opposite directions (each such day
  counted once); and, for each combination with a signal, the P&L per trade of ITM10 in the direction of the first
  signalling candle in the order SPY, index, feed, with no fallback to another candle when that trade is unpriced.
- SPY against the feed (population: eligible days, feed `keep` = true, usable feed bar) and SPY against the index
  (population: eligible days with a valid index bar): both in the same direction, both in opposite directions, SPY
  only, the other only, neither, with days and P&L per trade (in the SPY candle's direction when it signals,
  otherwise the other candle's).
- The SPY candle's ratio in tenths, `min((10 x body) // range, 9)` in whole cents for a positive range, so [0, 0.1)
  ... [0.9, 1.0]: trades and P&L per trade in the candle's direction whatever the ratio; candles that are flat
  after rounding, or have a zero range, are left out and counted.
- The relation between the SPY ratio and each of the other two ratios, on days with a valid bar and a positive
  range on both candles (no feed `keep` restriction; a flat candle with a positive range has ratio 0): Pearson
  correlation and the least-squares line of the other candle's ratio on the SPY ratio, with intercept; and the
  share of each SPY band's days in each band of the other candle on that same population. Undefined statistics are
  reported as not available.
- Coverage: days missing a SPY bar by year and month, the longest run of consecutive missing dates among the
  denominator days, and the feed rule's known P&L on days with and without a SPY bar (made only after the join; it
  cannot change an exclusion or a verdict line).
- The index move 10,000 x sign x (15:59 close - 15:51 open) / (15:51 open) from the frozen index archive's bars, in
  the SPY candle's direction, by SPY band, on all base dates with the required valid bars (whether or not the day
  is eligible for the option lines); days missing either index bar, or with a flat SPY candle, are left out and
  counted.

## Rules of the run

- The code is written after the lock, checks that this plan's hash is in the ledger and that both archives'
  manifests match, and refuses to join any candle with any price otherwise.
- Codex reviews the code read-only before the run; defects are fixed without changing this plan.
- One registered run, with its log kept. `run` refuses if a run was already started. A corrected rerun needs a
  documented implementation defect, the earlier output preserved next to the new one, and no change to any rule.
- The result is reported whatever it is. Any departure from this plan is reported as a labelled deviation.
