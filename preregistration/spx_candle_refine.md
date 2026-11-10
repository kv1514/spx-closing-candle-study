# Pre-registration addendum: re-tune the 15:50 rule on 2021-2023 real prices, test once on 2024-2026

**Status: locked 2026-11-09.**
- Drafted at the user's request, relayed from the fork session ("Yes, draft it").
- Revised after a Codex review: 11 points, all addressed.
- Locked by Claude at the user's explicit instruction, "lock it" (typed in this session). The user's approval
  to lock and run without reviewing the draft first was relayed from the fork.
- The four "Choices fixed here" are as drafted; the user did not change them.
- At locking, no `refine.py` code existed, and no tuning or test statistic of this plan had been computed.

Addendum to `spx_close_candle_scan.md`, `spx_candle_strike_ladder.md`, `spx_candle_exit_rules.md` and
`spx_candle_realprice.md`. Two stated criteria, both needed to adopt a new setting; everything else is
descriptive. Nothing here is a trading recommendation.

## Why this exists

The real-price study (`spx_candle_realprice.md`) tuned on 2013-2020 and changed nothing. That period was a weak
place to tune:
- spreads were about five times wider ($2.90 vs $0.60 a share at ITM10);
- 177 of the current rule's 394 signal days there had no implied spot;
- only 2 of 2,178 cells were eligible.

So it could not tell 0.60 from 0.70, or one candle from another. This study tunes the same grid on the first
three years of today's market structure (daily SPXW expiries from 2022, tight spreads) and tests the pick once
on the rest.

## The question

1. **Tuning (2021-01-01 .. 2023-12-31).** Which candle minute (15:40-15:50), body threshold (0.40-0.90),
   direction (with or against) and strike (ITM20-OTM20) made the most money per day at real prices? Does the best
   one pass a prespecified luck diagnostic?
2. **Test (2024-01-01 .. 2026-10-20, once).** Does that one pick make money on days the tuning never used? Is it
   better than the current rule (15:50, 0.60, with, ITM10) on the same days?
3. **Descriptive.** Where does 0.60 sit in the threshold profile? Is it on a plateau or at an edge?

## What was known when this was drafted (disclosed so the rules can be judged)

**What was computed, and what was looked at, at real option prices on 2021-2026.**
- `realprice.py run` (2026-11-09) internally priced every contract at every entry minute 15:41-15:51, both
  directions, all 9 offsets, on every day 2013-2026 (`day_cube`). That gives raw per-day payoffs, not cell
  statistics.
- Signal-conditioned statistics on 2021-2026 were computed and displayed **only for the current rule's family:**
  15:50, 0.60, with, at each of the 9 strikes. That covers mean, t, trades, share won, median and worst, by
  2021-22 and 2023-26, by year at ITM10, the mid and $0.74-fee versions, the fill check, and its not-priced
  counts.
- The full-grid statistics (every cell's mean, eligibility, the luck check and grid-wide not-priced counts) were
  computed only on 2013-2020. There, the best cell was 15:42, 0.60, with, ATM.
- `fills.py` (2026-11-09) used the current rule only: limit-order styles and late entry at 15:52/15:53/15:55, at
  ITM10.

**Index outcomes (D1).**
- **The candle scan** (`spx_candle_scan`):
  - It chose F2 (15:50, body ≥ 0.60, with) from 41 features on 2013-2020.
  - Its holdout read 2021-2026 for 3 frozen candidates: F2 (57.5% right, 644 trades), 15:50 direction with any
    body (54.0%), and day-so-far (48.4%).
  - Two of them are known effects, not blind tests. F1 and F2 largely reproduce P3, the 15:50→15:51 direction
    from `spx_1549_close`, and day-so-far is P1. The P3 reference row was reported on 2021-2026.
  - The holdout reports also include: the F2 economics and option-pricing sensitivity; the 2021-22 vs 2023-26
    split (strong in 2021-22, 54.7% since 2023); F2 by year; a 15:52-entry (latency) version; and
    11:49/11:51 placebos.
  - An audit (`audits/claude/recompute_out.json`) found that on 15:50 candles **without** a strong body
    (body < 0.60), trading the direction earned nothing on 2021-2026: 801 days, −0.2 bp a trade, against +2.4 bp
    for the 644 strong-body days.
- **The intraday-momentum study** (`spx_intraday_momentum`, results written 2026-11-09 01:38 PT, before this
  draft):
  - Part A regressed the last half hour on the day's earlier move, on 2013-2026 by year and half. It found no
    effect, and none in 2021-2026.
  - Part B split the current rule's trades by agreement with the day's move, at model prices, on 2013-2020 and
    (descriptively) 2021-2026. Agreeing trades did better per trade, and no filter passed on 2013-2020.
  - It also reported adding momentum trades on days with no 15:50 signal: t 2.5 on 2013-2020, t 0.09 on
    2021-2026.
- **The 15:49 close study** (`spx_close_1549`, README):
  - the size of each one-minute move from 15:40 to 15:59 by year, 2013-2026 (the 15:50 minute is 2.1-3.4× a
    normal minute every year since 2020);
  - the direction predictors P1-P4 (day so far, the 15:50→15:51 direction P3, and others) on 2013-2026, with a
    2023-2026 split.
- **Model results for the current rule on 2021-2026:**
  - the strike ladder (ITM10-ITM20 best);
  - exits (no stop beat holding), at ITM20, ITM10 and ATM, with "2023-2026 alone" figures at ITM10 and ATM.
- **Never computed:** signal-conditioned results at real prices on 2021-2026 for any cell outside the current
  rule's family. Never reported on 2021-2026 at index level: the other 38 scan features, the other candle
  minutes 15:40-15:49 as trade signals, and any threshold other than 0.60 (or "any body"). The fork session
  confirms the same (see "Fork disclosure").

**What that means for the test.**
- **The current rule's family is not fresh on 2024-2026.** A pick at 15:50, 0.60, with, at any strike gets no
  Part 2 adoption (see Part 1).
- **A pick at 15:50, with, θ > 0.60 trades on a subset of the current rule's days,** whose ITM10 trades and
  real-price P&L are listed in `realprice_trades.csv`. No such subset was computed, but it is not independent of
  known numbers.
- **A pick at θ < 0.60 adds days the weak-body audit found unprofitable at index level.**

**Other.**
- Signal counts (no prices, no outcomes) by candle and threshold on 2021-2023 and 2024-2026 were computed to set
  the minimum trades. Example: the current rule fires on 271 tuning days and 315 test days; 15:50 at 0.80 fires
  on 133 and 167.
- Quote-file dates per tuning half: 315 in H1 and 310 in H2. That is a filename count by Codex.
- Forward days (after 2026-10-20): a few real Robinhood trades of the current rule were already seen. They are
  descriptive, not fresh.
- **Fork check:** the user's fork session ("12:49 volatility experiments"; 12:49 PT is 15:49 ET) was asked what
  it computed on 2021-2026. Its answer is recorded under "Fork disclosure" below.

## Data

- **Signal:** the D1 one-minute panel (`scan.load_panel`).
- **Quotes:** `data/spx_1549/databento/cbbo-1m_1500-1601_k60/`. The row stamped HH:MM:00 in `ts_recv` is the
  quote at that minute's open. Only same-day expiries are used.
- **Settlement:** the official Cboe close in `data/spx_1549/spx_official_closes_cboe.csv`, checked against
  Robinhood within 0.01 as before.
- **Days:** days with a quote file and an official close.
- **Pricing:** the primitives are those of `realprice.py`, imported read-only. Those are the quote parsing,
  valid quote (ask > 0, 0 ≤ bid ≤ ask), the implied spot (median of K + call mid − put mid over the 3 strikes
  whose mids are closest, both bids > 0), ATM = floor(S / 5 + 0.5) × 5, and intrinsic value.
- **P&L per contract** = 100 × (intrinsic at the official close − ask at the entry minute's open) − $0.09. Every
  decision and criterion uses this. The mid and the $0.74 fee are descriptive.
- **Priced trade:** a signal day with an implied spot at the entry minute and a valid quote for the contract. A
  "trade" below always means a priced signal-day trade.
- **Coverage:** the download holds the 25 strikes within 60 points of the D1 **15:51** ATM. For an earlier entry,
  whether its strike is inside that window can depend on the move after entry, so missing prices can be
  informative. Therefore:
  - a cell is eligible only if at least 95% of its tuning signal days are priced, and in each half;
  - per-cell not-priced counts, by reason and half, are reported for the pick and the current rule;
  - inference is about priced days only.

## The grid (2,178 cells, unchanged)

Candle 15:40 ... 15:50 (11) × body threshold θ 0.40 ... 0.90 (11) × with/against (2) × strike ITM20, ITM15,
ITM10, ITM5, ATM, OTM5, OTM10, OTM15, OTM20 (9). Entry is the next minute's open.

- **Signal:** range > 0 and |body| ≥ θ × range, sign = sign(body) × (+1 with, −1 against). A missing bar gives
  a missing value.
- **Strike:** an up signal buys the call at ATM − o, and a down signal buys the put at ATM + o (o = +20 ... −20;
  positive is in the money).
- **Per-day series:** the trade's P&L on a priced signal day, 0 on a no-signal day, missing if the candle was
  missing or the trade could not be priced. "Mean per day" is the average over the non-missing days.
- **Check:** within each step, 15:50/0.60/with must equal scan.py's F2 on every kept day of that step, or the
  step stops.

## Isolation (both steps are separate processes)

**`tune`** may read only these outcome-bearing inputs dated 2021-01-01 .. 2023-12-31:
- `scan.load_panel("2021-01-01", "2023-12-31")`;
- the official closes filtered to those dates;
- quote files for those dates. Its quote loader refuses any later date.

It builds no array covering later dates and reads no cached results. File and date listings (which days have a
file or a `.none` marker) are metadata and may be read for any date. It writes:
- `backtests/spx_candle_refine/selection.json`, with the decision and the pick;
- `selection.sha256`;
- `tune_results.json` and the tuning section of `RESULTS.md`.

The selection files are written read-only.

**`test`** refuses to run unless the selection hash matches. It reads the 2024-01-01 .. 2026-10-20 panel,
closes and quotes. It prices **only** the pick's and the current rule's contracts until the Part 2 decision is
written to `results.json`. Only then does it compute the descriptive Part 3 items for the test period. If the
decision was "no test", `test` writes that decision before computing any Part 3 test-period item.

## Part 1: tuning (2021-01-01 .. 2023-12-31)

**Definitions.**
- **Days:** the kept tuning days in date order; n = their count.
- **Halves:** H1 = 2021-01-01 .. 2022-09-30 and H2 = 2022-10-01 .. 2023-12-31. That is about equal in expiry
  days, since 2021 had expiries on Monday, Wednesday and Friday only.
- **Score:** the plateau mean, the average of the cell's mean per day and its neighbours at θ ± 0.05 that exist
  on the grid.
  - Neighbours count whether eligible or not.
  - A neighbour with no finite mean is ignored.
  - The cell's own mean must be finite.

**Eligible**, all of:
- at least 100 trades;
- at least 40 trades in each half;
- a mean per day above 0 in each half;
- coverage ≥ 95% overall and in each half.

**Pick.**
- The eligible cell with the highest score.
- Exact ties go to the cell nearest the current rule. Distance is the grid-index Manhattan distance: one candle
  minute, one 0.05 threshold step, a direction flip or one 5-point strike step each cost 1.
- Remaining ties go to the first in enumeration order: candle, threshold, direction (with first), strike
  (ITM20 first).
- If no cell is eligible, there is no pick and no test, and nothing else is searched.

**Luck diagnostic (prespecified, circular shift).**
- Roll the whole signal tensor (all candles and thresholds together, zeros and missing values included) along the
  day axis, against the fixed tuning outcomes and the fixed half masks of the destination days.
- Use every shift in range(21, n − 21 + 1, 3).
- For each shift, recompute every cell's mean, score and eligibility (coverage included), and keep the best
  eligible score. A shift with nothing eligible counts as −∞.
- p = (1 + shifts with best ≥ observed best) / (1 + shifts).
- **What it does and doesn't show:** it asks whether the best score beats the best score from signals unrelated
  to the days. It is a diagnostic under the assumption that shifting the signal is a fair "no information"
  benchmark. Expiry frequency, volatility and pricing change over 2021-2023, so it is not an exact test. It does
  not test superiority over the current rule, and it does not pay for earlier studies.

**Goes to the test** only if all hold:
1. the pick is not in the current rule's family (15:50, 0.60, with, any strike);
2. p ≤ 0.05;
3. on tuning, the paired per-day difference (pick − current) has a mean above 0.

There is no t-bar on tuning, because three years have little power; Part 2 decides superiority.

**Outcomes.**
- **If the pick is in the current rule's family** (e.g. ITM20): the result is "already evaluated on 2024-2026; it
  can only be confirmed on future days". Part 2 is not run for it, and no runner-up is substituted.
- **If any condition fails:** "No candidate advanced under the prespecified rules", naming the failed gate. The
  current rule stays.

**Paired difference** (here and in Part 2): pick series − current series on the same days. A day is dropped if
either series is missing there; 0 on no-signal days is kept. The paired n and the dropped days are reported.

## Part 2: the test (2024-01-01 .. 2026-10-20, once)

Only if a pick went to the test. Statistics are Newey-West (Bartlett weights, lag 5) on the retained days in
date order. A mean or t that cannot be computed (fewer than 8 days, or zero standard error) fails its criterion.

- **(a) Works:** the pick's mean per day > 0 with t ≥ 2.0.
- **(b) Better:** the paired difference (pick − current rule) has mean > 0 with t ≥ 2.0.

**Adopt the pick** only if (a) and (b) both hold. If only (a) holds: "the pick also works but is not shown to
be better", and the current rule stays. If (a) fails: "not confirmed".

**Power, said in advance:** (b) is a hard bar. The pick may trade on far fewer days than the current rule's 315
(for example 167 at 15:50, 0.80). A pick that is truly somewhat better can easily fail (b). "Not better" does
not show that it is worse.

## Part 3: descriptive (decides nothing)

- **Tuning:**
  - the 15 best eligible cells (score, mean per day, trades, both halves, coverage);
  - the best cell for each candle minute;
  - the null's median and 95th percentile, and p;
  - not-priced counts per cell (median and maximum, and by reason and half for the pick and the current rule).
- **Threshold profile:** 15:50, with, at ITM10 and at ATM, θ 0.40 ... 0.90. For each: trades, mean per day,
  mean per trade, share won, median and worst trade.
  - On tuning.
  - On 2024-2026, computed only after the Part 2 decision (or the "no test" decision) has been written, and
    labelled as looked at after the decision.
- **Test period**, for the pick (if any) and the current rule: the mid version, the $0.74-fee version, and each
  year 2024, 2025, 2026. The current rule's numbers there are already known.
- **Days after 2026-10-20:** the current rule from the existing forward log, and the pick only if the forward
  data has its candle and entry-minute quote; otherwise "not available". Days already seen are labelled as
  previously available. Only days after the selection file was written count as fresh.

## Text rules

- Say plainly that 2024-2026 is not fresh for the current rule's family. Say that the 2021-2026 index outcomes
  were used before for the scan candidates, the P1/P3 known effects, the weak-body audit and the momentum study.
- Say that signals come from D1 (a CFD) and that a fill at the quoted ask ignores size and fast minutes. The
  fill study found that a mid limit does not capture the mid.
- If nothing goes to the test, say "no candidate advanced under the prespecified rules" and name the gate. Do
  not say the current rule is the best setting.
- No trading recommendation.

## Outputs and code

`backtests/spx_candle_refine/refine.py` builds the outputs, with commands `selftest`, `tune` and `test`:
- `selection.json` and `selection.sha256`;
- `tune_results.json`, `results.json` and `RESULTS.md`;
- `data/spx_1549/databento/refine_trades.csv`, every trade of the pick and the current rule in both periods.

How the code is built:
- It imports `realprice.py` and `scan.py` read-only and reuses only primitives: quote parsing, valid quote,
  implied spot, ATM, intrinsic, the signal and body rules, and `nw()`. All orchestration is new in `refine.py`:
  dates, halves, eligibility, coverage, score, pick, null, and both criteria.
- The selftest covers each new function on synthetic data, including the isolation guards.
- It refuses to run unless this file is in `preregistration/` and its SHA-256 is in
  `preregistration/LEDGER.md`.
- The code is written after locking and reviewed by Codex before the first `tune`.

## Choices fixed here

1. **Minimum trades:** 100 in tuning and 40 per half, with coverage ≥ 95%. That means 15:50 can potentially
   qualify up to θ = 0.80 (133 tuning signals). At 0.85 (89) and 0.90 (56) it cannot; those appear in the
   threshold profile.
2. **The head-to-head is decided on the test period at t ≥ 2.0**, not on tuning.
3. **Objective:** money per day, not per trade. Per trade would favour rare, high thresholds.
4. **Fee and price:** $0.09 at the ask for every decision.

## Fork disclosure

Answer from the fork session (2026-11-09), as reported by it: it **computed nothing** on 2021-2026 after the
fork. It only read existing results.
- **Read:** `spx_candle_realprice` RESULTS.md and SUMMARY.md, i.e. the current rule's family at real prices and
  the 2013-2020 discovery picks. It also had `spx_candle_exits/SUMMARY.md` in context. These are all listed
  above.
- **Not seen:** any other candle minute, threshold or the "against" direction on 2021-2026.
- **15:49 volatility:** no data was looked at. Its explanation to the user came from general knowledge and the
  two momentum papers.
- **Databento:** it restarted the cbbo pull (it crashed after about 600 days), and checked file integrity and
  counts, the OI manifest keys and spend sums. No quote, trade or OI contents were parsed.
- **Momentum study:** file names and timestamps only, plus the first 30 lines of its plan (the question, no
  results).

Before the fork, the fork shared this session's history, which is what "What was known" lists.
