# Pre-registration draft: can a real-time exit rule beat holding the 15:50 candle trade? Tune on 2021-2023, test once on 2024-2026

**Status: DRAFT, not locked.**
- Drafted 2026-11-09 at the user's request. Revised after one read-only review: 11 points (3 major, 8 minor), all
  addressed (see the end).
- Revised 2026-11-10 at the user's request: three plain take-profit rules from 15:52 (TP1552_10/20/30) were added,
  making 44 rules. See "Added on 2026-11-10" under "What was known".
- To lock, the user copies this file to `preregistration/spx_candle_exit_timing.md` and adds its SHA-256 to
  `preregistration/LEDGER.md`. Until then nothing here binds. `exit_timing.py` was written before locking and has
  run only on synthetic data; it refuses to read real data until this plan is locked.
- At drafting, no rule in this plan had been computed on any period. See "What was known".

Addendum to `spx_candle_exit_rules.md`, `spx_candle_realprice.md` and `spx_candle_refine.md`. One stated criterion
decides; everything else is descriptive. Research only. Nothing here is a trading recommendation.

## Why this exists

The current rule buys at the 15:51 ask and holds to the 16:00 cash settlement. Two checks say early exits cost
money:
- The exit-rules study (model prices, 2021-2026) tried six SPX stops and targets. Every one made less than holding.
- A descriptive check today (real bids, 585 trades) sold at one fixed minute, 15:52 to 15:59. Every minute lost
  $79-$136 a trade against holding.

Both are blunt. A stop fires on a level set at entry. A fixed minute sells every trade, good or bad. Neither looks
at how the trade has gone so far. A real-time rule can: sell when a gain starts to fade, or when the index gives
back part of its move. The hindsight "best minute" averaged +$341 a trade, so the option's price does wander after
entry. Nobody can sell at the best minute in advance. This study asks whether a simple rule that only uses what is
known at the time captures any of it, at real bids, with a proper tune/test split.

**What a winning rule must do.** Selling at bid b instead of holding changes the trade's P&L by
100 × (b − V) − $0.09, where V is what the option settles at. The ask paid cancels out. So a rule wins only if it
sells, on average, when the bid is above what the option will end up worth, by more than the fee. The bid sits
about half a spread (about $30 a contract in 2021-2026) below the mid. The rule must pick moments when the rest of
the move goes against the trade by more than that.

## The question

1. **Tuning (2021-01-01 .. 2023-12-31).** Of 44 real-time exit rules fixed below, which one improved most on
   holding, per trade, at real bids? Does it pass a prespecified luck diagnostic?
2. **Test (2024-01-01 .. 2026-10-20, once).** Does that one rule beat holding on trades the tuning never used?
   These trades are historical and partly examined already (see "What was known").
3. **Descriptive.** How do all 44 rules, the six earlier rules and the hindsight ceiling look at real bids?

## What was known when this was drafted (disclosed so the rules can be judged)

**Exit results already computed on these trades or this period.**
- **The exit-rules study** (`preregistration/spx_candle_exit_rules.md`, `backtests/spx_candle_exits/`), model
  prices, 644 signal days 2021-2026:
  - six rules on the D1 index path (stop 3, 5 or 8 points; target 5 or 10 points; stop 5 or target 10), checked at
    each minute close 15:51-15:58, sold at the next minute's open;
  - every rule made less than holding at ITM20, ITM10 and ATM, in all six pricing versions (at ITM10 the
    difference was −$30 to −$104 a trade);
  - the 8-point stop cost least, and in 2023-2026 alone it was close to holding (+$83 vs +$90 at ITM10);
  - stops cut the worst trade from about −$3,600 to about −$1,200 to −$1,500.
- **The 4 real forward trades** in that study (2026-10-22 .. 2026-10-30, Robinhood minute bars): the 5-point
  target sold early twice and made more than holding (+$1,591 vs +$1,214); every stop made less.
- **The fixed-minute check** (today, 2026-11-09; the section "Selling at a fixed minute, at real bids" in
  `backtests/spx_candle_exits/SUMMARY.md`). Not pre-registered. On all 585 real-price trades, 2021-2026, so it
  covers this study's tuning **and** test periods:
  - buy at the 15:51 ask, sell at the bid at the start of one fixed minute 15:52 .. 15:59, fee paid twice;
  - every minute lost against holding: −$79 to −$136 a trade, Newey-West t −4.8 to −7.8;
  - the per-trade averages were −$12 to −$69, against +$67 for holding;
  - the hindsight best of those minutes and holding averaged +$341 a trade (+$273 against holding; 77% won);
  - it was also computed by year. The 2024, 2025 and 2026 rows were seen in the session that asked for this
    plan. This plan treats every year's rows as seen. One line of it is in the summary: 2026 was the only year in
    which selling at 15:56-15:59 made money, and holding made more there (+$121).
- This plan was drafted after reading that summary section, including the 585-trade table and the 2026 sentence,
  but not the by-year table.

**The hold baseline is known on every period.**
- Real-price study (`backtests/spx_candle_realprice/`), per trade at the ask: 2021 +$175 (67 trades), 2022 +$71
  (90), 2023 +$4 (113), 2024 +$20 (106), 2025 +$65 (117), 2026 +$121 (92). All 585: +$67.46.
- Re-tuning study (`backtests/spx_candle_refine/`): tuning +$68.78 a trade (270); H1 +$149.97 (133); H2 −$10.03
  (137); test +$66.32 (315), and +$91.64 at the mid.

**Other path facts already known.**
- Fills study (`backtests/spx_candle_fills/`), all 585:
  - buying the same contract at the 15:52, 15:53 or 15:55 ask made +$56, +$58 and +$23 a trade (against +$67 at
    15:51). That reveals the average ask at those minutes against settlement;
  - hold outcomes split by an early path event: when a 15:51 mid limit would have filled (489 trades; it fills
    mostly when the option is getting cheaper), holding made +$43 a trade (52% won); when it would not (96
    trades; the price ran away), +$194 (61% won). So trades that ran away in the first minute held better;
  - that split was also reported by period (2013-2020, 2021-2026, 2021-22, 2023-26) in its RESULTS.md.
- Real-price fill check: the 15:51 minute's last trade was above the 15:51 ask 46% of the time. The full spread
  averaged about $0.60 a share in 2021-2026 ($0.40 in 2026).
- Strike ladder: the mean |move| from 15:51 to 15:59 is 8.60 points at level L = 7,709.58. The point values of
  the rules below were set from it. No exit outcome was used to set them.
- The forward signal days after 2026-10-20 (7 by 2026-11-06) and the 4 priced forward trades were seen.
- Index-level results on 2021-2026 from earlier studies (the 15:50→15:51 direction, the weak-body audit, the
  intraday-momentum study) are about direction at entry, not about exits. They are listed in
  `preregistration/spx_candle_refine.md` and were known.
- The re-tuning study's test-period results were seen, after its decision: the 15:50 / 80% / ITM20 version on
  2024-2026 (+$79 a trade, 167 trades), and the threshold profile 0.40-0.90 at ITM10 and ATM on 2024-2026.
  These are entry-side settings, not exits.

**Added on 2026-11-10.** The three TP1552 rules (sell as soon as the bid is 10%, 20% or 30% above the price paid,
from the first decision minute) were added at the user's request after watching one live signal day, 2026-11-10,
outside both periods: the option rose several dollars within minutes of entry and was well below the price paid by
15:55. No rule in this plan had been computed on any period, before or after the addition.

**Never computed, on any period:** any rule in this plan's grid. No trailing stop, give-back, retrace or
time-gated rule has been run on real quotes. Path-conditioned results on real quotes that were computed: the
hindsight best minute (the maximum of the bid over the fixed minutes), and the fills study's split of hold
outcomes by whether the 15:51 minute traded below the mid. SPX path rules were computed only at model prices, on
D1 closes, in the exit-rules study.

**Computed for this draft** (no outcomes): the number of priced entries per period, from their dates (H1 133, H2
137, test 315); the column names and minute stamps of one quote file (61 snapshots, 15:00:00 .. 16:00:00 ET).

**What that means for the test.** 2024-2026 is not fresh for holding. It is partly known for exits: every fixed
minute lost there. A conditional rule sells on a subset of trades and minutes, which was never computed, but its
result is not independent of those known numbers. The grid was drafted knowing that early exits lose on average,
and those results helped motivate it. Process isolation cannot undo that. So a pass on 2024-2026 is a pass on
already-examined historical data, not independent confirmation, and its nominal level does not account for that
reuse. Only days after the selection file is written can confirm it.

## Data

- **Entries:** the current rule's priced entries from `data/spx_1549/databento/realprice_trades.csv`, read as
  `fills.read_entries()` reads them: config `current`, status `priced`, entry minute 15:51. Columns used: date,
  signal, kind, strike, ask, mid, implied_spot, pnl_fee_0.09. Entries from 2013-2020 are not used (spreads were
  five times wider).
- **Quotes:** `data/spx_1549/databento/cbbo-1m_1500-1601_k60/<date>.csv.gz`, parsed by `realprice.parse_quotes`.
  The row stamped HH:MM:00 in `ts_recv` is the quote at the **start** of minute HH:MM. Only same-day expiries
  and valid quotes (ask > 0, 0 ≤ bid ≤ ask) are kept. A file holds the 25 strikes within 60 points of the D1 15:51
  ATM, both calls and puts.
- **Settlement:** the official Cboe close in `data/spx_1549/spx_official_closes_cboe.csv`.
- **Primitives** (imported read-only from `realprice.py`): `parse_quotes` / `load_day_quotes`, `valid_quote`,
  `implied_spot` (median of K + call mid − put mid over the 3 strikes whose mids are closest, both bids > 0),
  `atm_of`, `intrinsic`, `nw` and `check_gate`.
- **The D1 panel is not used.** It set the entries (via the real-price study). No rule reads it.

## Entries and the hold baseline

For each entry i:
- side s = +1 (call) or −1 (put); contract (kind, K); A = the 15:51 ask, per share;
- S0 = the implied spot in the 15:51 snapshot;
- V = intrinsic(kind, K, official close), per share;
- **hold P&L** H = 100 × (V − A) − 0.09.

Checks, each of which stops the step if it fails. Each step runs only its own window's checks:
- `tune`: 270 entries (H1 133, H2 137); the mean of H is +68.78 (H1 +149.97, H2 −10.03), to $0.01;
- `test`: 315 entries; the mean of H is +66.32, to $0.01;
- both: the 15:51 snapshot's ask for the contract equals the CSV's ask, and S0 equals the CSV's implied_spot
  (1e-9); V equals (pnl_fee_0.09 + 0.09) / 100 + ask from the CSV (1e-6).

**No entry is dropped** because a later quote is missing. Missing later quotes are handled by the rules below.

## Timing: what a rule sees, and when it sells

- **Snapshots** t = 15:51, 15:52, ..., 15:59 (the HH:MM:00 rows). For each: the contract's bid b_t and ask a_t,
  and the implied spot S_t over the whole snapshot. The 16:00:00 row is never used.
- **Decision minutes** m = 15:52, 15:53, ..., 15:58. At m a rule may use only the snapshots t ≤ m, the entry's A,
  S0 and side, and X (below). Nothing later.
- **Sale.** If a rule fires at m, it sells at the bid in the **next** snapshot, m + 1 (15:53 .. 15:59). That is a
  one-minute delay. There is no decision at 15:59: its sale would fall at 16:00:00, when expiring SPXW stop
  trading. A rule that never fires holds to settlement.
- **Rule P&L** if it sells at snapshot e: R = 100 × (b_e − A) − 0.18 (the $0.09 fee on each side). Otherwise
  R = H (no fee at settlement).
- **Paired difference** d = R − H. It is 0 when the rule holds, and 100 × (b_e − V) − 0.09 when it sells.
- **Index path.** The implied spot from the same snapshots, not D1. It is an option-parity proxy for SPX, on the
  same clock as the quotes. It is built from option mids, so spread changes, stale quotes and a change in which
  3 strikes are used can move it a little without the cash index moving. The move in favour, in points at the
  earlier study's level L = 7,709.58, is u_t = s × (S_t − S0) × L / S0. The raw move is r_t = s × (S_t − S0).
- **Scale X** (for SRV only): the 15:51 ATM straddle mid, mid(call) + mid(put) at strike atm_of(S0), from the
  15:51 snapshot. X is valid only if both the call and the put at that strike have a valid quote in the 15:51
  snapshot. It is a straddle-price scale known at entry, not a forecast of the realized move.

## Missing quotes

- At a decision minute m, a rule needs only the quantities its own family reads at m:
  - TS, PL and TP need a valid quote for the contract in snapshot m;
  - SR needs the implied spot in snapshot m;
  - SRV needs the implied spot in snapshot m and a valid X.

  If one is missing, that rule **makes no decision at m**. Another family may still decide at m. Running peaks
  are updated only from snapshots that have the value. With no valid X, SRV never fires on that entry.
- **The first trigger is final.** Once a rule fires at m, the sale is scheduled. It is never cancelled, and the rule
  is not checked again.
- If snapshot m + 1 has no valid quote for the contract, the sale happens at the bid of the first later snapshot
  that has one, up to 15:59. If there is none, the trade settles (d = 0). Both cases are counted and reported per
  rule.
- Every d is finite by construction. Before any mean or `nw` call, the code checks that every expected d value is
  finite and stops if not (`nw` would otherwise drop non-finite values silently).
- **Coverage.** An entry is *complete* if the contract has a valid quote in every snapshot 15:51 .. 15:59, the
  implied spot exists in every snapshot 15:51 .. 15:58, and X is valid. Before any rule is evaluated, `tune` counts
  complete entries. If fewer than 95% of tuning entries, or of either half, are complete, `tune` writes
  `selection.json` with the decision "coverage too low; no pick" and the counts, and stops. It evaluates no rule
  and computes no Part 3 item. `test` then writes "no test (coverage)" and computes nothing else. A new plan would
  be needed. The test period's coverage is reported, not gated. Coverage uses later quote availability, but it
  only decides whether the study runs. It never removes an individual entry.

## The rules (44)

Running quantities at decision minute m, over snapshots t = 15:51 .. m that have the value. All start at 15:51:
- B*_m = the highest bid so far, starting from the 15:51 bid (which always exists for a priced entry);
- G*_m = B*_m − A, the best bid gain so far;
- U*_m = the highest u_t so far, starting from u = 0 at 15:51; R*_m = the highest r_t so far, starting from 0.

A rule fires at the first decision minute m at which its condition holds. Comparisons allow 1e-9 toward firing
(≤ means ≤ + 1e-9, ≥ means ≥ − 1e-9).

| Family | Fires at m when | Grid | Rules |
|---|---|---|---|
| **TS** trailing stop on the bid | b_m ≤ (1 − x) × B*_m | x = 0.10, 0.20, 0.30, 0.40, 0.50 | 5 |
| **PL** profit lock (give-back) on the bid | G*_m ≥ g × A, and b_m ≤ B*_m − h × G*_m | g = 0.10, 0.20, 0.30; h = 1/3, 2/3, 1 | 9 |
| **SR** SPX retrace, points at L | U*_m ≥ a, and u_m ≤ U*_m − b | a = 3, 5, 8; b = 2, 3, 5 | 9 |
| **TP** take-profit on the bid, from minute T | m ≥ T, and b_m ≥ (1 + g) × A | T = 15:52, 15:54, 15:56, 15:58; g = 0.10, 0.20, 0.30 | 12 |
| **SRV** SPX retrace scaled by the straddle | X valid, R*_m ≥ α × X, and r_m ≤ R*_m − β × X | α = 0.35, 0.60, 0.95; β = 0.25, 0.35, 0.60 | 9 |

In words:
- **TS:** sell when the bid falls x below its highest point since entry. This includes a stop from entry.
- **PL:** once the bid has been g above the price paid, sell if it gives back a share h of that best gain. h = 1
  means "sell if it falls back to the price paid".
- **SR:** once SPX has moved a points in the trade's favour, sell if it gives back b points from its best.
- **TP:** from minute T on, sell as soon as the bid is g above the price paid. Before T, never. With T = 15:52 it is
  a plain take-profit from the first decision minute.
- **SRV:** SR with both thresholds in units of the day's 15:51 straddle. On a day at level L with a straddle of
  8.6 points (the mean 15:51-15:59 move at L), it gives about SR's thresholds. It adapts to the day's volatility
  and to the index level.

Names: TS10 .. TS50; PL{g}_{h} as PL10_33, PL10_67, PL10_100, ...; SR{a}_{b}; TP{HHMM}_{g} as TP1554_10;
SRV{α}_{β} as SRV35_25. **Enumeration order:** TS, PL, SR, TP, SRV; within a family, the first parameter
ascending, then the second ascending.

**Neighbours** (for the plateau score): within the same family, one step along one axis with the other fixed.
TS has up to 2; the others up to 4. Families are not neighbours of each other.

**Why these are new.** The earlier six rules fired on fixed SPX levels set at entry, on model prices. None of
these do: TS and PL trail a running peak of the real bid, SR and SRV trail the index's best point, and TP acts on
the real bid's gain over the price paid, from a set minute.

## Isolation (both steps are separate processes)

**`tune`** may read only these outcome-bearing inputs dated 2021-01-01 .. 2023-12-31:
- rows of `realprice_trades.csv` in that window. The reader checks each row's date first and drops an
  out-of-window row before converting any other field;
- the official closes in that window, filtered the same way;
- quote files for those dates. The quote loader refuses any other date.

It builds nothing covering later dates and reads no cached results. File and date listings are metadata and may
be read for any date. It writes, in this order:
- `inputs_tune.json` (read-only), before computing anything: the SHA-256 of this plan, of `exit_timing.py` and of
  `realprice.py`, and a digest of each input it read (the tuning CSV rows, the tuning closes, each quote file);
- `backtests/spx_candle_exit_timing/selection.json` and `selection.sha256`, both read-only. `selection.json` holds
  the decision, the failed gates (if any), the pick, its score and p. When there is no pick, `pick`, `score` and `p`
  are `null`;
- `tune_results.json`, the tuning rows of the trades CSV, and the tuning section of `RESULTS.md` (from its heading
  to the next `## ` heading);
- last, `tune_complete.json`: the SHA-256 of `inputs_tune.json`, `selection.json`, `selection.sha256`,
  `tune_results.json`, the tuning rows of the trades CSV and the tuning section of `RESULTS.md`. Shared files are
  hashed by their tuning part only, as in `refine.py`, so `test` can append to them.

**`test`** refuses to run unless the plan gate passes, `selection.sha256` matches `selection.json` and
`tune_complete.json` matches the tuning artifacts. These are checked before any test-period input is read. It
writes `inputs_test.json` the same way, then reads the 2024-01-01 .. 2026-10-20 rows, closes and quotes. Until the
Part 2 decision is written to `results.json`, it computes **only** the hold series and the pick's d series. Only
then does it compute the Part 3 test-period items. If the decision was "no test", it writes that first.

**Reruns.** Each step holds an exclusive lock and writes an attempt record before reading any outcome-bearing
input; `RESULTS.md` reports how many times each was started. A step that completed refuses to run again. After a
crash, a rerun must reproduce the frozen input manifest exactly, recompute everything, and continue only if what
is already written (the selection and tuning files, or the decision block) is reproduced exactly. It then writes
only the missing outputs. Otherwise it stops. Every write is atomic (temp file, fsync, rename).

## Part 1: tuning (2021-01-01 .. 2023-12-31)

**Definitions.**
- **Entries:** the 270 tuning entries in date order. n = 270.
- **Halves:** H1 = 2021-01-01 .. 2022-09-30 (133 entries) and H2 = 2022-10-01 .. 2023-12-31 (137), as in the
  re-tuning study.
- **Mean d:** the average of d over all entries in the set, with 0 where the rule held. It is the improvement on
  holding per trade, not per early sale.
- **Sold early:** the rule sold at a bid before settlement (a rule that fired but found no bid through 15:59 does
  not count).
- **Score:** the plateau mean, the average of the rule's mean d and its neighbours' mean d. Neighbours count whether
  eligible or not.

**Eligible**, all of:
- sold early on at least 25 tuning entries, and at least 10 in each half;
- mean d above 0 in each half.

(Coverage is a study-wide gate, checked before any rule; see "Missing quotes".)

**Pick.**
- The eligible rule with the highest score.
- Exact ties go to the rule that sold early on fewer tuning entries (closer to holding), then to the first in
  enumeration order.
- If no rule is eligible: no pick, no test, and nothing else is searched.

**Luck diagnostic (prespecified, block sign-flip).** The refine study's circular shift does not fit here: an exit
and its outcome belong to the same trade. Instead:
- Make the n × 44 matrix D of d values (entries in date order, rules in enumeration order).
- Cut the entries into consecutive blocks of 5 in date order (270 gives 54 blocks). Blocks run across the half
  boundary: block 27 holds entries 131-135, which span H1 and H2. Blocks do not restart at H2.
- Draw B = 9,999 sign vectors: `numpy.random.default_rng(20261109).integers(0, 2, size=(9999, 54)) * 2 − 1`.
  In draw k, every entry in block j has its whole row of D multiplied by sign[k, j]. All 44 rules flip together.
- In each draw, recompute every rule's mean d, half means, score and eligibility, and keep the best eligible score.
  The early-sale counts do not change. A draw with nothing eligible counts as −∞.
- p = (1 + draws with best ≥ observed best) / (1 + B). The observed best is the pick's score. The diagnostic runs
  only if a pick exists. In the outputs a −∞ draw is written as `null`, and the number of such draws is reported.

**What the diagnostic does and doesn't show.** It is a heuristic benchmark. It asks whether the best score beats
the best score that 44 correlated rules reach when each block's exit gains and losses are as likely to have the
opposite sign. The flips keep the zeros, the size of each trade's d and the links between rules, and the whole
selection (eligibility and the half signs included) is re-run in each draw. But its p is exact only if the block
vectors of d are symmetric about zero, and they need not be: d is sparse and can be skewed. So p can be too small
(anti-conservative) as well as too large. Blocks of 5 keep some short-run dependence within a block but none
across block boundaries; a block spans at most four lags, in trade order, not calendar days. Markets also changed
over 2021-2023. It does not pay for the earlier studies. That is why p is only a gate to the test; Part 2
decides.

**Goes to the test** only if all hold:
1. the coverage gate passed;
2. some rule is eligible;
3. p ≤ 0.05.

The pick's tuning mean d is above 0 by eligibility. There is no t-bar on tuning; Part 2 decides.

**Outcomes.** If any condition fails: "No rule advanced under the prespecified rules", naming the failed gate.
Holding stays.

## Part 2: the test (2024-01-01 .. 2026-10-20, once)

Only if a pick went to the test.
- **Series:** the pick's d on the 315 test entries, in date order (0 where it held).
- **Enough information:** the pick must sell early on at least 25 test entries, falling in at least 10 distinct
  blocks of 5 consecutive test entries (315 entries give 63 blocks). Otherwise the result is "insufficient
  information": neither confirmed nor rejected, and holding stays.
- **Statistic:** Newey-West t (Bartlett weights, lag 5, in entry order), as `realprice.nw`. It is an approximate
  statistic: with sparse, skewed d its level is not guaranteed. A mean or t that cannot be computed (zero standard
  error) fails.
- **Criterion: the pick beats holding** only if mean d > 0 **and** t ≥ 2.0. This is one-sided: only an improvement
  counts. Under a normal approximation, t ≥ 2.0 is about a 2.3% one-sided level. That level does not account for
  the earlier looks at 2024-2026 (see "What was known").
- If it holds: "the pick beat holding on 2024-2026 under the prespecified test, on historical data that had
  already been examined; this is not independent confirmation". If not: "not confirmed", and holding stays.
- Independent confirmation can only come from days after the selection file is written (Part 3, "Days after
  2026-10-20"). This plan sets no criterion for them; a separate locked plan would.

**Power, said in advance (an illustration, not an estimate).** The fixed-minute check gives a feel for the noise:
selling every trade at 15:56 had a standard error of about $18 a trade on 585 trades. Assume a rule's d, on the
trades it sells, varies about as much as that, and the rest are 0. Then a rule that sells on 40% of the 315 test
trades would have a standard error of roughly $15. It would need to beat holding by about $30 a trade just to
reach t = 2, and by about $45 for an 80% chance of passing. A conditional rule may sell exactly on the most
volatile trades, which would make the noise larger. A rule that is truly $10-$20 better would usually fail.
"Not confirmed" does not show that the rule is worse.

## Part 3: descriptive (decides nothing)

- **Tuning:**
  - all 44 rules: score, mean d and its Newey-West t, mean d in each half, share sold early, exit-minute counts,
    rule P&L per trade, share won, median, 5th percentile and worst trade, and the missing-quote counts (no
    decision, rolled to a later bid, fired but settled);
  - the 10 best eligible rules;
  - the null's median and 95th percentile, and p;
  - the hindsight ceiling and the fixed-minute exits (context).
- **Test period**, computed only after the Part 2 decision (or "no test") is written, and labelled as looked at
  after the decision:
  - for the pick (if any): mean d and t by year (2024, 2025, 2026); share sold early and the exit-minute counts;
    rule P&L per trade, share won, median, 5th percentile and worst trade, against holding's;
  - **versions of the pick**, each also for tuning:
    - *mid:* the same triggers and the same sale snapshot as the primary (roll-forward included), but the sale is
      at that snapshot's mid. The entry stays at the 15:51 ask;
    - *zero delay:* decisions at m = 15:52 .. 15:59, and the sale at the same snapshot's bid; if that snapshot has
      no valid quote for the contract, the primary roll-forward applies, else settle. Optimistic;
    - *$0.74 fee:* the fee is $0.74 per side for both the pick and holding, so d = 100 × (b − V) − 0.74 on a sale;
  - all 44 rules on 2024-2026 (mean d, t, share sold early);
  - the test period's coverage.
- **Context, both periods** (the 585-trade versions were already seen):
  - **the hindsight ceiling:** per entry, the best of holding and selling at the bid in any snapshot 15:52 ..
    15:59 that has a valid quote for the contract. Not tradable;
  - **the fixed-minute exits** 15:52 .. 15:59 at the bid, split into tuning and test. An entry with no valid quote
    at that minute is left out of that minute's row, and the count left out is shown;
  - **the six earlier rules re-expressed here:** stop at u ≤ −3, −5, −8; target at u ≥ 5, 10; stop −5 or target
    10. Same decision minutes, implied spot, missing-quote rules and sale timing as SR. They are not candidates.
- **Statistics used in Part 3:** means, Newey-West t as in Part 2, share won (P&L > 0), the median, and the 5th
  percentile by `numpy.percentile` with its default linear interpolation.
- **Days after 2026-10-20.** No quote file of this schema exists for them at drafting; the forward Robinhood bars
  have no bid and are not used. If cbbo-1m files for later days are downloaded, the frozen pick (or, with no pick,
  the 44 rules) is scored on them and reported. Only dates after the selection file was written can count as
  fresh. Earlier dates stay historical, whenever their files are downloaded. With no pick, the 44 rules' forward
  results are descriptive, not confirmation.

## Text rules

- Say plainly that 2024-2026 is not fresh for holding, and that fixed-minute exits were already seen there. A pass
  there is "on historical data that had already been examined", never "confirmed out of sample".
- Call the luck diagnostic a heuristic benchmark, not an exact test.
- Say that quotes are one-minute snapshots, that a sale at the bid assumes one contract and a firm bid, and that
  the one-minute delay is a modelling choice.
- If nothing goes to the test, say "no rule advanced under the prespecified rules" and name the gate. Do not say
  holding is the best possible exit.
- No trading recommendation.

## Outputs and code

`backtests/spx_candle_exit_timing/exit_timing.py`, with commands `selftest`, `tune` and `test`, builds:
- `selection.json` and `selection.sha256`;
- `tune_results.json`, `tune_complete.json`, `results.json` and `RESULTS.md`;
- `data/spx_1549/databento/exit_timing_trades.csv`, one row per entry: date, period (tuning or test), half,
  side, contract, A, S0, X, V, H, completeness; then for each of the 44 rules its fire minute, sale snapshot,
  sale bid, R and d; then the pick's columns. The tuning rows are written by `tune`. The test rows are written by
  `test`, after the decision. With no pick, the pick's columns are empty.

How the code is built:
- It imports `realprice.py` read-only and reuses only the primitives listed under "Data". Everything else is new:
  the windowed readers, the path quantities, the rules, the missing-quote handling, the score, eligibility, pick,
  the null, the gates and the test.
- It follows `refine.py`'s run discipline, as set out under "Reruns" above.
- It refuses to run `tune` or `test` unless this file is in `preregistration/` and its SHA-256 is in
  `preregistration/LEDGER.md` (a `check_gate` like `refine.py`'s).
- The selftest uses synthetic data only, and writes only to a temp folder. It covers: each family firing at the
  right minute on hand-made paths; no decision at 15:59; the one-minute sale; the family-specific missing-quote
  rules (no decision, roll forward, settle, no retrigger); the d algebra; plateau, eligibility and tie-breaks; the
  sign-flip null (a planted edge gives a small p, no edge does not); the test's minimum-information rule; the
  coverage stop; the reproduction checks; the isolation guards; and crash recovery.
- The code was written before locking and run only on synthetic data. It is reviewed read-only against this plan
  before the first `tune`.

## Choices fixed here (the user may change any of them before locking)

1. **Delay:** sell at the next snapshot's bid (one minute). Last decision 15:58. Zero delay is descriptive only.
2. **Triggers on the bid** for TS, PL and TP, because the bid is what a sale gets. A mid trigger would ignore
   spread blips but was not chosen.
3. **Units:** TS, PL and TP in percent of the price paid or the peak bid; SR in points at L; SRV in straddles. For
   an ITM10 option, a percent of the premium is close to a fixed number of SPX points, so it is a larger relative
   move when SPX is lower or calmer (much of 2021-2023). SRV is in the grid for that reason.
4. **Objective:** mean d per trade, counting 0 where the rule holds. Per early sale would favour rules that rarely
   fire.
5. **Minimum:** 25 early sales on tuning, 10 per half.
6. **Luck diagnostic:** block sign-flip, blocks of 5, 9,999 draws, seed 20261109, p ≤ 0.05.
7. **Test bar:** one-sided, mean d > 0 with Newey-West t ≥ 2.0, and at least 25 test sales in at least 10 of the
   63 test blocks (else "insufficient information").
8. **A missing sale quote** rolls to the next snapshot through 15:59, else the trade settles.

## Order of work

1. Draft (this file).
2. One read-only review; revise for every substantive point.
3. The user reads it and locks it: copy to `preregistration/spx_candle_exit_timing.md`, add its SHA-256 to
   `preregistration/LEDGER.md`.
4. `exit_timing.py` with its `check_gate` (written before locking; synthetic data only). A read-only review of the
   code against this plan.
5. `selftest`.
6. `tune`, once.
7. `test`, once.
8. A plain-English SUMMARY.md by hand.

## Caveats

- **One-minute snapshots miss what happens inside a minute.** A real stop could fire and fill mid-minute, at a
  better or worse price. A bid can dip and recover between snapshots and never be seen.
- **A sale at the bid assumes one contract and a firm bid.** Size, queue and the exact second are unknown. In a
  fast minute the bid can move before an order arrives.
- **The one-minute delay** is slower than an automated order and about right for a manual one. The earlier exit
  study checked a bar's close and sold at the next bar's open, about the same instant. This plan's sale is a real
  minute later, so the two are not directly comparable.
- **Entry is at the 15:51:00 ask with zero delay,** as in every earlier study. The fills study found one minute late
  costs about $12 a trade.
- **Quotes cover only 25 strikes within 60 points of the D1 15:51 ATM.** The traded contract is always inside it.
  The implied spot can fail after a very large move; that minute is then skipped by the index rules.
- **The entries come from D1,** a CFD standing in for SPX, as in every earlier study. No rule here reads D1.
- **2024-2026 is not fresh** for holding, and fixed-minute exits there were seen.
- Nothing here is a trading recommendation.

## Review points (2026-11-09) and what changed

| # | Point | Change |
|---|---|---|
| 1 | [major] The sign-flip null was oversold as the boundary case and conservative. | Now called a heuristic benchmark that is exact only under block-sign symmetry and can be anti-conservative. |
| 2 | [major] A pass on 2024-2026 was worded as confirmation. | Now "on historical data that had already been examined; not independent confirmation". Only days after the selection file can confirm. |
| 3 | [major] The test had no guard against very few sales. | At least 25 test sales in at least 10 of 63 blocks, else "insufficient information". |
| 4 | [minor] Blocks of 5 do not "match" lag 5. | Wording fixed; limits stated; blocks run across the H1/H2 boundary. |
| 5 | [minor] Missing data was not family-specific. | Each family's inputs listed; X validity defined; peaks start at 15:51; the first trigger is final; d checked finite before `nw`. |
| 6 | [minor] Isolation and completion rules were loose. | Each step runs only its own checks; `tune_complete.json` hashes tuning parts of shared files; manifests, rerun refusal, crash recovery and the coverage-failure files defined. |
| 7 | [minor] Descriptive versions were underspecified. | Mid, zero-delay and $0.74 versions defined (same triggers, roll-forward, fee on both legs); missing quotes for fixed minutes and the ceiling; percentiles; −∞ as `null`; CSV columns. |
| 8 | [minor] The power figure was presented as established. | Now an illustration with its assumption; $30 to reach t = 2 vs about $45 for 80% power. |
| 9 | [minor] Disclosure missed conditional outcomes already seen. | Added the fills study's filled/unfilled hold split and refine's test-period results; narrowed "the only path statistic". |
| 10 | [minor] "Real SPX" overstated the implied spot. | Now an option-parity proxy; X is a straddle-price scale, not a forecast. |
| 11 | [minor] Forward freshness was weaker than refine's. | Only dates after the selection file can be fresh; with no pick, forward results are descriptive. |

The review found the core timing sound: start-of-minute snapshots, next-snapshot sales, X known at entry, running
peaks, and excluding a 15:59 decision.
