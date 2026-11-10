# SPX "12:49" close move: what the data says

This is research, not investment advice. Nothing here recommends placing a trade.

**Short answer:**

- **The move is real.** The last 11 minutes of the US session really are bigger than the rest of the afternoon, and
  the jump at 15:50 ET is the biggest single minute of the close.
- **The direction mostly is not predictable.** The one signal with some history behind it is weak in the 0DTE era
  (2023-2026).
- **The options test did not run.** We could get real one-minute 0DTE option prices for only **1 of the ~35 planned
  days**, so the question of whether option buyers make money at 15:49 is still open. All strategies are **FAIL by the
  pre-registered rule; D2 test not run (1 of ~35 planned days)**.
- **The 22-day stand-in shows no clear edge.** A rougher 22-day stand-in, using 10-minute option bars, found that on
  average option prices matched the moves that followed.

Background reading (exchange rules, papers, fees): [research/SPX_1549_RESEARCH.md](../../research/SPX_1549_RESEARCH.md).
The binding test plan: [preregistration/spx_1549_close.md](../../preregistration/spx_1549_close.md).

---

## 1. What Tiger's "12:49" is

Tiger's Google Doc "SPX" shows 27 one-minute SPX charts with a dotted line at 12:49. There are about 11 candles from
that line to the closing bell, so the time is **Pacific: 12:49 PT = 15:49 ET**.

That minute matters because at **15:50 ET** the NYSE stops taking normal market-on-close orders and publishes its
first **closing-auction imbalance**: how many more shares are waiting to buy than to sell at the close, or the reverse.
Nasdaq also sends an early imbalance message at 15:50. So 15:49 is the last minute before that news.

- NYSE moved this release from 15:45 to 15:50 on 1 April 2019.
- Nasdaq publishes its full imbalance at 15:55.

The claim tested: *"around 12:49 PT SPX makes a sharp move one way, which makes 0DTE options skyrocket."*

## 2. What the data says, in plain English

Two data sets were used:

- **D1:** 3,307 trading days (2013-02-28 to 2026-10-20) of one-minute S&P 500 prices from Dukascopy. This is a CFD
  that tracks S&P futures, and in the close window it tracks SPX closely: correlation 0.974 with Robinhood SPX (see
  caveats).
- **D2:** Robinhood's SPX and SPXW 0DTE option minute bars since September 2026.

"bps" means basis points: 1 bp = 0.01%. At today's SPX level of about 7,700, 1 bp is about 0.77 index points.

### 2a. How big is the last-11-minute move?

From the 15:49 open to the 16:00 close, SPX moves on average **12.09 bps** (about 9 points), in one direction or the
other. For comparison:

| comparison | average size | the 15:49-close window is bigger by | days it was bigger |
|---|---|---|---|
| the 11 minutes just before (15:38-15:49) | 8.68 bps | 1.39x | 61% |
| a typical 11-minute window that same day (median of 339 windows, 10:00-15:48) | 6.31 bps | 1.92x | 67% |

- **Statistically, this is very clear** (t ≈ 13 on both comparisons), and it holds under the stricter day-cleaning rule.
- **In 2023-2026 the move averages 11.29 bps,** about 8.7 points.
- **The 15:50 minute stands out.** In 2023-2026 it is **2.40x** a normal mid-day minute; the 15:59 minute is 2.30x and
  15:55 (Nasdaq's imbalance time) is 1.69x.
- **The 15:50 spike is recent.** It grew after NYSE moved its imbalance release to 15:50. Before 2017 the 15:45 minute
  was the bigger one; since 2020 the 15:50 minute has been 2.1-3.4x a normal minute every year.

So the "sharp move" is real. It is mostly the well-known pattern that markets are busiest at the open and the close,
plus the closing auction.

### 2b. Can you tell which direction it will go?

Four pre-registered signals were tested on D1:

| signal | idea | average gain per day if you follow it | t-stat | passes (Holm p < 0.05, same sign in 2023-26)? |
|---|---|---|---|---|
| P1 | day so far, 09:30 -> 15:49 (momentum) | +0.81 bps | 2.21 | no (Holm p 0.08; it reversed in 2023-26) |
| P2 | last 30 minutes, 15:19 -> 15:49 | -0.01 bps | -0.03 | no |
| **P3** | **direction of the first minute after the 15:50 release (15:50 -> 15:51), then hold to the close** | **+1.00 bps** | **4.09** | **yes** |
| P4 | first half-hour, 09:30 -> 10:00 | -0.36 bps | -1.00 | no |

- **Only P3 passes.** Following the first reaction to the 15:50 release, from 15:51 to the close, was right 52.6% of
  the time and earned 1.00 bps (about 0.8 points) per day over 2013-2026. It beats the same trick at each of 342
  other minutes of the day (it ranks 1st of 343).
- **In the 0DTE era it is small and not significant:** 0.49 bps (about 0.4 points) with t 1.28 in 2023-2026. There it
  ranks only 30th of 343 minutes.
- **The move is priced almost instantly.** Exchange research says the imbalance news is priced within about 300
  milliseconds, so a 15:51 entry is late by design.
- **Bottom line on direction:** a weak lean, far too small to pay an option's bid-ask spread.

### 2c. What happened to real 0DTE option prices since September

Robinhood keeps real minute prices for an expired SPXW option for only about one session. After that, the history
comes back as flat filler ("interpolated").

- Of the 34 sessions collected (2026-09-02 to 10-20), only **2026-10-20** had real minute option bars at 15:49.
- 12 days had no real SPX minute bars.
- 21 days had SPX bars but only filler option bars.

**On the one real day, 2026-10-20** (SPX 7710.93 at 15:49, official close 7712.57, a move of 1.64 points). All costs
include a $0.10 half-spread per leg and a $0.09 fee:

| strategy (pre-registered) | what it does | result |
|---|---|---|
| S1 straddle | buy the 7710 call + 7710 put at 15:49 for 5.90, hold to the close | worth 2.57 at settlement: **-$353** |
| S2 directional | P3 said "down" at 15:51, so buy the 7710 put for 2.90; SPX finished up | **-$300** |
| S2-alt (other reading of the rule) | P1 said "up" at 15:49, so buy the 7710 call for 3.05 | **-$58** |
| S3 "sell the spike" | buy the 7715 call (1.13) and 7705 put (1.23); sell either if it doubles | neither doubled (the best was 1.35 and 1.05): **-$256** |

**"How often does an out-of-the-money option double?"** On 10-20: none of the 12 OTM options from 5 to 30 points out
doubled. On one day that says nothing. A rougher check on 22 days uses Robinhood's real 10-minute bars, entering at the
15:40-bar close (about 15:49:59) and looking at the highest print of the 15:50-16:00 bar:

| option, 5 points out of the money (22 days) | touched 2x at some point | finished at 2x or more | expired worthless | average P&L held to the close |
|---|---|---|---|---|
| call (average price 1.37) | 18% of days | 0% | 86% | -$101 |
| put (average price 1.28) | 45% | 23% | 64% | +$112 |

- **Pooled 5- and 10-point options:** they touched 2x 30% of the time, finished at 2x or more 9% of the time, and
  expired worthless 83% of the time. The average P&L was **+$3 per contract**, about zero.
- **Calls and puts differ because of what the market did.** It sold off into the close on several of these days. That
  is the market's path, not an edge.
- **"Touched 2x" is optimistic.** It is a single print inside a 10-minute bar, and you would have had to sell at
  exactly that moment.

**Straddle on the same 22 days** (stand-in entry 1 minute late, not simultaneous prices):

- The average straddle cost **5.99 points (7.75 bps)**, and the average move to the official close was **5.90 points
  (7.63 bps)**. Option prices matched the moves almost exactly.
- The average P&L was **+$47 per straddle**. The 95% range runs from **-$246 to +$340**, so this could easily be zero
  or negative.
- 41% of days were winners and the median day was **-$51**.
- One day (2026-09-30, SPX fell about 31 points into the close) made **+$2,491**. Without it the average is **-$69**.

## 3. Verdict (pre-registered pass rule, applied mechanically)

A strategy becomes a candidate for *paper* logging only if both conditions hold:

1. its premise passes on the long D1 history;
2. its real-option P&L on D2 has a positive mean, with confidence intervals reported.

| strategy | condition 1 (D1 premise) | condition 2 (D2 option P&L) | verdict |
|---|---|---|---|
| S1 straddle | not evaluable (needs at least 2 D2 days) | not evaluable (1 day; no CI possible) | **FAIL by rule; D2 test not run (1 of ~35 planned days)** |
| S2 directional (P3, 15:51) | yes (P3 Holm p 0.000175, same sign in 2023-26) | not evaluable | **FAIL by rule; D2 test not run** |
| S2-alt (P1, 15:49) | no (Holm p 0.08) | not evaluable | **FAIL** (condition 1 not met; D2 test not run) |
| S3 sell the spike | not evaluable | not evaluable | **FAIL by rule; D2 test not run** |

"FAIL" here means "not shown to work", not "shown to lose".

- **The -$353 / -$300 / -$256 on 10-20 is one day.** It is not evidence either way.
- **The earlier "condition 1 passes" result for S1/S3 was an artefact of having one day.** The audit fixed it (see
  section 7).

## 4. Honest caveats

- **Sample size of D2.** One usable day out of ~35 planned. Even 35 days would be weak. A straddle's payoff swings by
  about 6.5 points from day to day, so 35 days can only detect an edge of **2.19 points ($219) per straddle** or more.
  A realistic +0.5-point edge needs about **670 days**. For the directional trade, the P3 edge after the half-spread is
  about 0.03 points, which would need about **96,000 days**. Option P&L will never settle S2; only the long D1
  direction test can.
- **CFD vs SPX.** D1 is a Dukascopy CFD on S&P futures, not the SPX cash index.
  - Its 15:49-close moves correlate 0.998 with SPY (21 days) and 0.974 with Robinhood SPX (22 days).
  - The P3 direction agrees on 21 of 22 days.
  - D1 ends at the 15:59 bar close, while SPXW settles on the official close. The two differ by 1.26 bps on average,
    about 16% of the move.
- **The model of "expected move" over-predicts right now.** Fitted only on 2023 to August 2026, it predicted an average
  move of 8.82 bps for the D2 window; the realized move was 6.46 bps. September-October 2026 was calmer than the fit
  period.
- **Marks are not fills.** Robinhood option bars look like sampled prints, not clean bid/ask mids.
  - On 10-20 the call and put prices at 15:49 disagree with put-call parity by about 0.74 points, and by 1.56 at
    15:50.
  - The $0.10 half-spread is an assumption, not a measured spread; real fills could be better or worse.
  - The 10-minute stand-in is worse still: its call and put prices are up to 3.6 points out of line.
- **Fees.** The base case uses $0.09 per contract per side. Robinhood's real SPXW cost is **$0.89-$1.13 per contract
  per side** (research file, section F). That adds about $2 per straddle (-$353.18 becomes -$355.26). It is small next
  to the spread, but real.
- **Many looks at the data.** Besides the pre-registered tests, 14 extra variants are labelled exploratory and counted,
  so treat any single exploratory number with suspicion.

## 5. What forward data collection would settle it

1. **Save the minute bars every day after the close.** The pull must happen the same evening, because Robinhood's
   minute history for expired 0DTE options goes flat after about one session. It needs read-only Robinhood
   historicals: SPX one-minute bars, SPXW 0DTE one-minute bars for every 5-point strike from 30 below to 30 above the
   money (calls and puts), and the official daily close. The pulls use the read-only Robinhood tools
   `get_index_historicals` and `get_option_historicals`, and `build_robinhood_C.py` already turns the saved output
   into the tidy files `analysis.py` reads. A daily scheduled task could run it; none has been set up.
2. **Snapshot live bid/ask quotes at 15:49:00 and 15:51:00 ET** (12:49 and 12:51 PT) for the same strikes. This
   replaces the assumed $0.10 half-spread with real spreads and fixes the "marks vs fills" caveat.
3. **After 35 usable days, rerun `analysis.py` unchanged.** Conditions 1 and 2 become evaluable at 2 days, but expect
   only large edges (more than about $219 per straddle) to show up at 35 days. A fair answer for the straddle needs
   hundreds of days.
4. **TradingView is not needed.** No login or password is needed or wanted; please do not paste a password into
   chat. Its exports would add cash-index minute bars, which we already have from Dukascopy and Robinhood. As far as
   we know they do not include minute prices of expired 0DTE options or imbalance history. Imbalance history is paid
   data (NYSE TAQ, Nasdaq, Databento). The price reaction (P3) stands in for it here.

## 6. Learn: gamma and theta in the last 10 minutes

All prices below come from the saved Robinhood files for **2026-10-20** (`learn_example.json`). "Normal approximation"
means treating the next 11 minutes' move as a bell curve whose size is set by the straddle price.

**The setup at 15:49.** SPX was 7710.93. The 7710 call was 3.05 and the 7710 put was 2.85, so the straddle cost
**5.90**. At expiry a straddle pays exactly |SPX - strike|, so its price is the market's (risk-neutral) estimate of the
*average size* of the move to the close: here 5.90 points, about 0.077%, since the strike is within 1 point of SPX.

**Breakeven.** With the half-spreads, the straddle costs 6.10. It makes money only if SPX settles below **7703.90** or
above **7716.10**. That is a move of 7.03 points down or 5.17 points up, about 7.9 bps on average.

**Theta (time decay).**

- If SPX had not moved at all, the straddle would have been worth only 0.93 at the close (the call's intrinsic value).
  The other **4.97 points is pure time value**, and it all disappears in 11 minutes: about **0.45 points per minute**
  on average.
- Decay speeds up at the end. Time value shrinks roughly with the square root of the time left: about 3.35 with 5
  minutes left and about 1.50 with 1 minute left.
- The real straddle traced exactly that, while SPX barely moved:

| bar close | 15:49 | 15:52 | 15:55 | 15:58 | 15:59 |
|---|---|---|---|---|---|
| SPX | 7711.25 | 7712.22 | 7709.32 | 7710.20 | 7711.70 |
| 7710 straddle | 6.10 | 4.70 | 3.21 | 2.16 | 1.13 |

SPX settled at 7712.57, so the straddle paid 2.57: a loss of 3.33 points per unit, or **-$353** after costs.

**Gamma (how fast the bet changes).**

- With 11 minutes left, the normal approximation gives the ATM call a delta of about 0.55, meaning it moves about 0.55
  points per 1 point of SPX.
- Its gamma is about **0.054 per point**, so after a 5-point rise the delta is already much higher.
- That gamma is about **45 times** that of a 30-day option at the same strike distance (0.0012). This is why 0DTE
  options "skyrocket" on modest moves.

**The out-of-the-money call.** The 7715 call cost 1.13 at 15:49. Its value at the close is just max(SPX - 7715, 0):

| SPX at the close | 7710.93 (no move) | 7715.00 (+4.07) | 7717.26 (+6.33) | 7720.93 (+10) | 7725.93 (+15) | 7730.93 (+20) |
|---|---|---|---|---|---|---|
| 7715 call worth | 0 | 0 | 2.26 (2x) | 5.93 (5.2x) | 10.93 (9.7x) | 15.93 (14.1x) |

- **How likely the big multiples are.** Using the straddle's own pricing (a normal move with standard deviation about
  7.4 points), the call finishes in the money about 29% of the time and at 2x or more about 20% of the time. The rest
  of the time it is worth zero.
- **The fair price is roughly what it cost.** The normal approximation puts the call's fair value at about 1.35,
  against a market price of 1.13. That gap is within the roughness of the approximation, not an edge.
- **What actually happened.** The highest the call traded before 15:59 was 1.35 (1.19x), and it expired worthless
  because SPX closed at 7712.57.
- **Why the multiples are mostly arithmetic.** A 9.7x win and a total loss are both normal outcomes of the same fairly
  priced bet. What matters is whether moves are bigger than the price implies, and on the data we have, they are not.

## 7. What changed after the audits

An adversarial audit found no arithmetic errors, but it found two framing problems. Both are
fixed in the code; the pre-registration is unchanged. The full list is in `audits/DISPOSITION.md`.

- **S1/S3 condition 1 ("yes") came from a bootstrap that could not resample a single D2 day.** It is now **not
  evaluable**. Its CI [1.76, 2.67] no longer exists.
- **The verdict code would have promoted a strategy on n = 1.** Condition 2 is now "not evaluable" below 2 days, and
  the labels say "D2 test not run".
- **S2 now follows the pre-registration's "else put" when the signal is 0,** and excludes undefined days instead of
  counting them as $0. The other reading of "best predictor" (P1 at 15:49) is reported as S2-alt; it also fails.
- **No look-ahead in the expected-move model.** It is now fitted only on days before the first D2 session (n 945 ->
  911), and the 10-20 prediction moved from 8.12 to 8.19 points.
- **Bootstrap CIs on D1 use 20-day blocks.** The premise must now pass under both block and iid versions.
- **New disclosures:**
  - the parity check
  - "marks may be prints"
  - the 15:59-vs-official-close gap
  - the D1 day rule relabelled as a deviation
  - an actual-fee sensitivity ($1.13)
  - a P3 placebo test
  - a year-by-year 15:50 spike table
  - a power calculation

---

## Technical section

### Files

| path | what |
|---|---|
| `/Users/kv15/trading/preregistration/spx_1549_close.md` | binding pre-registration (read-only) |
| `/Users/kv15/trading/research/SPX_1549_RESEARCH.md` | literature, exchange rules and fee research |
| `backtests/spx_close_1549/analysis.py` | the pre-registered analysis plus labelled exploratory parts; writes `results.json` and `RESULTS_RAW.md` |
| `backtests/spx_close_1549/results.json` | every number, machine-written |
| `backtests/spx_close_1549/RESULTS_RAW.md` | machine-written tables: verdicts, decisions and deviations, H1, H2, H3, power, exploratory (i)-(vii) |
| `backtests/spx_close_1549/learn_example.py` / `learn_example.json` | the section-6 teaching example (not a test) |
| `backtests/spx_close_1549/tests/test_analysis.py` (28/28) and `tests/test_d1.py` (11/11) | tests; run with `.venv/bin/python -B <file>` |
| `backtests/spx_close_1549/audits/audit_recompute.py`, `audit_recompute_out.json` | the adversarial audit's independent recomputation |
| `backtests/spx_close_1549/audits/DISPOSITION.md` | finding-by-finding disposition, with old -> new numbers |
| `backtests/spx_close_1549/audits/results_before_audit_fixes.json` | `results.json` as it was before the audit fixes |
| `build_d1.py`, `fetch_dukascopy.py`, `validate_d1.py`, `d1_coverage.json`, `d1_validation.json` | D1 download, cleaning, calendar and validation gate |
| `build_robinhood*.py`, `assign_option_files_C.py` | D2 Robinhood read-only collection and tidy files |
| `/Users/kv15/trading/data/spx_1549/` (git-ignored) | raw and tidy data: `d1_usa500_rth_1m.csv.gz`, `d1_days.csv`, `d2_chunk_*`, `robinhood/raw/` |

Rerun everything (about 35 s):

```
/Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/analysis.py
/Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/learn_example.py
/Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/tests/test_analysis.py
/Users/kv15/trading/.venv/bin/python -B backtests/spx_close_1549/tests/test_d1.py
```

### Data

**D1**

- 3,307 usable days, 2013-02-28..2026-10-20, under the primary rule `keep`; the strict rule `keep_strict` leaves 2,933.
- Dropped weekday files: 377 with a delayed feed clock (2011-09..2013-02), 127 holidays, 80 with a missing bar
  15:19-15:59, 29 calendar half-days, 12 data-only half-days, and 5 with no ticks.
- Validation gate: corr(r_close) is 0.9976 against SPY 1-minute (n 21) and 0.9744 against Robinhood SPX (n 22), so D1
  is accepted.

**D2**

- 34 sessions.
- SPX bars: 13,294, of which 4,692 interpolated and discarded.
- Option bars: 223,080, of which 212,940 interpolated and discarded.
- Usable for H3: 1 day (2026-10-20).
- Put-call parity at the 15:49 open on 10-20: signed median -0.74 (13 strikes, max |dev| 0.82, ATM -0.73). It is -1.56
  at 15:50 and -0.08 at 15:51. Lag-0 correlation of changes 0.965, so the bars are aligned.

### H1 size (D1, primary `keep`; 20-day-block bootstrap)

| baseline | mean abs r_close | mean baseline | ratio of means | mean ln diff | t | 95% CI (block) | share of days larger |
|---|---|---|---|---|---|---|---|
| (a) 15:38-15:49 window | 12.09 bps | 8.68 bps | 1.39 | 0.353 | 13.64 | [0.300, 0.409] | 0.609 |
| (b) same-day median window | 12.09 bps | 6.31 bps | 1.92 | 0.249 | 13.24 | [0.203, 0.295] | 0.669 |

Both pass. Under the strict rule: (a) 0.355, t 13.14; (b) 0.252, t 12.71; both pass.

### H2 direction (D1, Newey-West lag 5, Holm over P1-P4)

| predictor | n | mean bps | NW t | Holm p | hit rate | 2023-26 mean / t | passes |
|---|---|---|---|---|---|---|---|
| P1 | 3298 | 0.808 | 2.21 | 0.0805 | 0.504 | -0.602 / -1.21 | no |
| P2 | 3307 | -0.009 | -0.03 | 0.977 | 0.500 | -0.088 / -0.16 | no |
| P3 (target 15:51 -> close) | 3307 | 0.998 | 4.09 | 1.75e-4 | 0.526 | 0.490 / 1.28 | yes |
| P4 | 3298 | -0.357 | -1.00 | 0.634 | 0.482 | -0.549 / -1.07 | no |

**Strict-rule sensitivity:** P3 Holm p 6.88e-4, so it still passes.

**Predictor selection for S2:**

- **S2** uses P3, entering at 15:51 (a forced deviation from 15:49). Re-selecting on D1 dates before 2026-09-02 gives
  the same choice: P3 with t 4.07.
- **S2-alt** uses P1, the largest |t| among the predictors known at 15:49.

**P3 placebo (exploratory vi):**

- Across 342 other minutes, the median t is -0.53 and 0.6% have t > 2. P3 ranks 1st of 343; in 2023-26 it ranks 30th.
- P3 by NYSE regime: before 2019-04-01, 0.89 bps (t 3.04); 2019-04..2022, 1.67 bps (t 2.68); 2023 onward, 0.49 bps
  (t 1.28).

### H3 options (D2)

**Expected-move model.** The fit runs on D1 2023-01-03..2026-09-01 (n 911):
|r_close| = 0.000280 + 0.1348 × rv, with R² 0.168.

**On 10-20:**

- rv up to 15:49 was 58.0 bps, the implied straddle 5.90 points and the predicted move 8.19 points.
- The pass statistic is **not evaluable** (one D2 day).
- Out-of-sample calibration on the 34 D1 days of the D2 window: predicted 8.82 bps, realized 6.46 bps.

**P&L on 10-20** ($ per trade):

| cost case | S1 | S2 | S2-alt | S3 |
|---|---|---|---|---|
| half-spread 0.10, fee 0.09 (base) | -353.18 | -300.09 | -58.09 | -256.18 |
| half-spread 0.10, fee 1.13 (actual RH fee, extra) | -355.26 | -301.13 | -59.13 | -258.26 |
| half-spread 0.25, fee 0.74 | -384.48 | -315.74 | -73.74 | -287.48 |

The full 9-case grid is in `RESULTS_RAW.md`.

**Power** (D1 2023-01..2026-09, n 911):

- S1: payoff SD 6.48 points. Days needed for t = 2: 2,684 for a +0.25-point edge, 671 for +0.5 and 168 for +1.0. With
  35 days the smallest detectable edge is 2.19 points.
- S2 (P3): edge 0.130 points gross and 0.030 after the half-spread, payoff SD 4.71 points, so about 95,900 days are
  needed.

### Exploratory (labelled, counted: 14 extra variants)

- **(i) OTM options on 10-20:** 0 of 12 reached 2x.
- **(ii) minute profile 2023-26:** 15:50 is 2.40x a normal minute, 15:59 is 2.30x, and 15:55 is 1.69x.
- **(ii-b) year by year:** in 2013-16 the 15:45 bar (1.52-1.62x) was larger than the 15:50 bar (1.36-1.48x). In 2019
  the 15:50 bar was 1.74x; from 2020 on it is 2.11-3.44x.
- **(iii) 15:59 close -> official close (22 days):** mean -0.56 bps, mean |.| 1.26 bps, max 3.30 bps.
- **(iv) 10-minute straddle stand-in (22 days):**
  - mean +$47.09, t95 [-246.04, 340.23], 41% of days positive, median -$51.18, -$69.28 without 2026-09-30
  - implied 7.75 bps vs realized 7.63 bps
  - regression gap +1.00 points, block CI [0.11, 1.80], iid CI [-0.10, 1.80], so it does not pass under the both-CIs
    rule
  - parity-filtered (11 days): +$309.37, t95 [-240.95, 859.68]
  - this stand-in cannot settle condition 1
- **(vii) OTM options from 10-minute bars (22 days):** the pooled 5- and 10-point options touched 2x 30% of the time
  (bar high, an upper bound), finished at 2x or more 9% of the time, expired worthless 83% of the time, and averaged
  +$3.16 held to the close.

All decisions, interpretations and the two labelled deviations (the D1 day rule and the S2 entry at 15:51) are listed
in `RESULTS_RAW.md` under "Decisions, interpretations and deviations".
