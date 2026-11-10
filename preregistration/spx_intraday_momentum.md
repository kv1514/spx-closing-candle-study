# Pre-registration addendum: market intraday momentum and the 15:50 candle trade

**Status: locked 2026-11-09.** Locked by Claude at the user's explicit instruction ("Lock it"), with the choices listed in "Choices made in this plan" as Claude recommended them. Drafted the same day and revised after three independent (Codex) reviews. While drafting, no return relationship, hit rate, P&L or gamma was computed for anything in this plan (see "What was known"). Agents may not edit this file; a change needs a new locked addendum.

Addendum to `spx_close_candle_scan.md`, `spx_candle_strike_ladder.md`, `spx_candle_exit_rules.md` and
`spx_candle_realprice.md`. Research only; nothing here is a trading recommendation.

## The question

Two published papers say the S&P 500's return earlier in the day predicts its last half hour:

- **Gao, Han, Li and Zhou (2018), "GHLZ"**: the first half hour, measured from the prior close, predicts the
  last half hour. The 15:00-15:30 half hour adds to it. The effect is stronger on volatile days.
- **Baltussen, Da, Lammers and Martens (2021), "BDLM"**: the return from the prior close to 15:30 ("rest of
  day") predicts the last half hour better. Option dealers' gamma hedging drives it: the effect shows up when
  dealers are net short gamma.

The current trade: on the 15:50 one-minute candle, if the body is at least 60% of the range (F2), buy a 0DTE
SPXW option 10 points in the money (ITM10) in the candle's direction at the 15:51 open. Hold it to settlement.
This study asks three things:

- **A. Adapted replication:** does the papers' momentum show up on D1, 2013-2026?
- **B. Does it add to the trade:** does momentum improve the F2 trade? The rules are chosen on 2013-2020 and
  get one test on 2021-2026.
- **C. Dealer gamma:** is momentum, and the F2 trade, stronger when dealers are net short gamma? This part runs
  only if the open-interest data fits the budget.

## The two papers (definitions checked 2026-11-09, paraphrased)

**GHLZ**, Journal of Financial Economics 129(2), 2018, 394-414. The definitions come from the authors' December
2015 working paper. The published abstract matches it.
- **Data:** SPY trades from TAQ, February 1993 to December 2013. Days with fewer than 500 trades are dropped.
- **Returns:** 13 half-hour simple returns a day. The first one starts at the previous trading day's 16:00
  close and ends at 10:00, so it includes the overnight move. The 12th is 15:00-15:30 and the 13th is
  15:30-16:00. A footnote says log returns give similar results.
- **Tests:**
  - regressions of the last half hour on the first, on the 12th, and on both, with Newey-West t;
  - an out-of-sample R² against the historical mean.
- **Size:** first half-hour slope about 6.9 (×100), R² about 1.6%; both predictors together reach about 2.6%.
  The 12th half hour's power comes mostly from the 2007-2009 crisis.
- **Conditionals:**
  - Volatility is the realized volatility of one-minute returns in the first half hour. Days are sorted into
    terciles over the whole sample, so the sort uses future data.
  - Volume terciles are formed within each year.
  - Predictability rises with both.
- **Timing rules:**
  - η(r1): long the last half hour if r1 > 0, else short.
  - η(r1, r12): trade only when both signs agree, else stay flat.

**BDLM**, Journal of Financial Economics 142(1), 2021, 377-403.
- **Data:** futures on more than 60 markets, 1974 to May 2020. For the S&P 500 they use futures prices between
  09:30 and 16:00 and remove early-close days.
- **Returns (simple):**
  - r_ONFH = price 30 minutes after the open / previous close − 1;
  - r_ROD = price 30 minutes before the close / previous close − 1;
  - r_LH = the last 30 minutes.
- **Main test:** the regression r_LH = α + β·r_ROD with Newey-West t. For the E-mini (ES) alone, β is about
  6.2 (×100), t about 5.0, R² about 3.4%. The timing rules are η(r_ROD) and the agreement rule
  η(r_ONFH, r_ROD).
- **Net gamma exposure (NGE):**
  - They assume option market makers are long every listed S&P 500 index call and short every put, and hedge
    their delta exactly.
  - Per option, NGE = gamma × open interest × (+100 for calls, −100 for puts) × index level.
  - The sum over all strikes and maturities is divided by the S&P 500's market value.
  - Negative NGE means dealers are net short gamma, so their hedging trades with the move.
  - Gamma comes from OptionMetrics (1996-2017) and SqueezeMetrics (to May 2020). The paper does not describe
    its own gamma calculation; OptionMetrics computes gamma from each option's implied volatility.
- **Results:**
  - Their Table 7 splits days on the sign of the previous day's NGE. The r_ROD slope is about 6.6 (t about 4.8)
    when NGE < 0, and small and insignificant when NGE ≥ 0.
  - Their Table 8 adds an indicator(NGE ≤ 0) × r_ROD term, which is positive, and a continuous NGE × r_ROD
    term, which is negative.
  - Their sample has about 2,930 negative-NGE days and 3,158 positive ones.

Sources: [GHLZ abstract (RePEc)](https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414),
[GHLZ working paper, Dec 2015](https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf),
[BDLM published version, author's site](https://academicweb.nd.edu/~zda/intramom.pdf),
[BDLM (RePEc)](https://econpapers.repec.org/RePEc:eee:jfinec:v:142:y:2021:i:1:p:377-403).

**Overlap with our data.**
- **GHLZ** ends in December 2013, so all of D1 except April-December 2013 is after its sample.
- **BDLM** runs to May 2020. 2013-2020 is therefore inside BDLM's sample, on a different instrument (ES futures
  rather than the D1 CFD). Only 2021-2026 is out of sample for both papers.

## What was known when this was drafted (disclosed so the rules can be judged)

**Earlier momentum tests on D1.** Their target was the move into the close; their predictors were anchored at
the 09:30 open.
- **P1** (`spx_1549_close.md`): sign of 09:30 open → 15:49 open, target 15:49 open → 15:59 close.
  - 2013-2026: t 2.21, hit 50.4%, Holm p 0.08, so it failed.
  - By period: t 2.35 up to 2019, 2.07 in 2020-2022, −1.21 in 2023-2026.
- **P4** (same file): sign of 09:30 open → 10:00 open. This is GHLZ's first half hour without the overnight
  move. On the same target it gave t −1.00 and hit 48.2%, negative in every sub-period.
- **P2:** sign of 15:19 → 15:49, t −0.03.
- **The candle scan** (`spx_close_candle_scan.md`, `discovery.json`, `holdout.json`):
  - F4_day_so_far, which is P1 again, made the 2013-2020 shortlist with t 2.69 and hit 52.0%. It failed on
    2021-2026: hit 48.4%, t −0.07, Holm p 0.53.
  - F4_open_gap (sign of the overnight gap) had t −0.24 on 2013-2020.
  - F4_clv (where the 15:49 price sits in the day's range) had t 2.46, just under the 2.5 bar.
  - F4_prior_day_candle had t −1.44.
  - None of the 15:20-15:45 five-minute or 15:30-15:48 one-minute candle directions reached |t| 2.5.

**So related momentum signals are not blind here.** In particular, the 09:30-anchored version is known to have
failed on 2021-2026.

**How the new tests differ from those:**
- **The anchor:** the prior close, so the overnight move is included. Earlier tests started at 09:30.
- **The predictor window:** it ends at 15:30, not 15:49.
- **The target:** 15:30 → 16:00, the papers' window. It contains the old 15:49-15:59 target, so it is not
  independent of it.
- **The statistic:** a slope on the size of the move, not only its sign.
- **The gamma conditioning:** never looked at.
- **The combination with F2:** how F2 trades split by momentum sign has never been computed.

**Known about the F2 trade itself:**
- 2013-2020 index outcomes were used to choose F2.
- 2021-2026 index outcomes: 644 trades, sign right 57.45%.
- Strike-ladder model, 2021-2026 (`backtests/spx_candle_strikes/results.json`):
  - ITM10 variant (a): +$166 a trade, NW t 4.25, 54% profitable;
  - ITM10 variant (c): +$158.
- No early exit beat holding (`backtests/spx_candle_exits/SUMMARY.md`).
- The model's ITM10 P&L on 2013-2020 has never been computed.

**Structure checks run while drafting** (the panel was loaded; only bar counts and missing values were looked
at, no returns):
- `scan.load_panel("2013-04-01", "2026-10-20")` returns 3,287 days: 1,841 in 2013-04-01..2020-12-31 and 1,446
  in 2021-01-01..2026-10-20.
- **Prior close missing on 49 days.** `prev_close` is the prior NYSE session's 15:59 close. It is NaN when that
  session is not a keep day. That covers 29 days after a 13:00 half day and 20 days after a session dropped
  for bad data.
- **Half days:** none of the 33 calendar half days is a keep day, so they never enter.
- **Missing bars:**
  - the 10:00 bar is missing on 2 days;
  - the 15:00 bar is missing on 83 days, because of a recurring D1 gap from 14:15 to 15:04 ET (38 days in
    2013, 44 in 2014, 1 in 2017);
  - some 09:30-10:00 bar is missing on 13 days;
  - the 15:30, 15:51 and 15:59 bars exist on every day.
- **F2 count:** 920 trades in the scan's 2013-02-28..2020-12-31 discovery (`discovery.json`). Slightly fewer
  fall in 2013-04-01..2020-12-31.

**Data not seen:**
- No open-interest value has been used. Two probes looked at timestamps and contract counts only (Part C).
- The VIX history (`data/cboe_indices/VIX_History.csv`, plus VIX9D and VIX3M) is on disk; only its header and
  date range were checked.

## Data and days

- **D1:** the Dukascopy US500 CFD, one-minute bid candles, via `scan.load_panel("2013-04-01", "2026-10-20")`.
  It is the same keep-day set as every earlier study. All parts start on 2013-04-01, the first OPRA date, so
  they cover the same days.
- **Bars:**
  - Bars are left-labelled; the 10:00 bar covers 10:00:00-10:00:59.
  - **"Price at HH:MM"** = the open of the HH:MM bar.
  - **The 16:00 proxy X** = the close of the 15:59 bar.
  - **The prior close PC** = `P.prev_close`.
- **Exclusions:**
  - A quantity that needs a missing price is undefined that day. The day leaves only the tests that need that
    quantity, and the counts are reported.
  - The days after a 13:00 half day have no PC, so they drop out of everything that needs it. They are not
    given the half day's 12:59 close.
- **Periods:**
  - discovery 2013-04-01..2020-12-31 (halves split at 2016-12-31 / 2017-01-01);
  - confirmation 2021-01-01..2026-10-20.

## Definitions (all times ET, log returns)

| Name | Definition | Used in |
|---|---|---|
| r_first | ln(price at 10:00 / PC) | GHLZ predictor |
| r_12 | ln(price at 15:30 / price at 15:00) | GHLZ predictor |
| r_rod | ln(price at 15:30 / PC) | BDLM predictor |
| r_on | ln(09:30 open / PC) | descriptive split of r_rod |
| r_day | ln(price at 15:30 / 09:30 open) | descriptive split of r_rod (r_rod = r_on + r_day) |
| r_last | ln(X / price at 15:30) | Part A and C target |
| y | ln(X / 15:51 open) | F2 trade's index move |
| RV_fh | sqrt of the sum of squared ln(open[m+1] / open[m]) over the 30 one-minute steps 09:30 → 10:00 | Part A conditional |
| s | F2_1m_1550_strong_body from `scan.spec_by_id(...).signal(P)` times its frozen direction (+1 in `candidates.json`) | Part B, C |

The papers use simple returns. Log returns match every earlier study here, and GHLZ report that log returns
give similar results. The simple-return slope is reported next to the primary one, as a description.

## Inference (used by every regression and mean in this plan)

**The estimator.**
- **Fit:** OLS with an intercept, on the rows where every variable is defined, in date order.
- **Variance:** a HAC sandwich, V = (X'X)⁻¹ S (X'X)⁻¹, with the score vectors u_t = x_t·e_t:
  - S = Σ_t u_t u_t' + Σ_{j=1..5} (1 − j/6) · Σ_t (u_t u_{t−j}' + u_{t−j} u_t');
  - Bartlett lags 1 to 5, weights 1 − j/6;
  - no finite-sample (degrees-of-freedom) correction.
- **Test:** t = coefficient / sqrt(diag V), with a two-sided normal p = erfc(|t|/√2).

**Lags count retained observations.** A dropped day is skipped, not filled. For C2 the observations are F2
trades in date order, so lag 5 means five trades.

**Not estimable.** Any of the following makes a test "not estimable", which is never a pass:
- X is rank-deficient, for example a dummy that never varies;
- fewer than 30 observations;
- a standard error that is not finite or not positive.

**This matches `scan.nw_mean_test` for a mean.** That function:
- drops NaNs;
- sets e = y − mean and lrv = (1/n)·[e'e + 2·Σ_{j=1..5} (1 − j/6)·Σ_t e_t e_{t−j}];
- returns se = sqrt(max(lrv, 0) / n), t = mean / se and p = erfc(|t|/√2).

A regression on a constant alone gives V = lrv / n, the same number. The only differences are rules here, not
arithmetic:
- `nw_mean_test` returns no t below n = 8 and for se = 0;
- this plan also calls fewer than 30 observations "not estimable".

Part B's means use `nw_mean_test` plus the 30-observation rule.

**Which number decides a gate.** Where a gate is stated as a p-value (Part B's selection, Part C's tests), the
two-sided normal p = erfc(|t|/√2) decides, together with the required sign; any t shown next to it is an
approximate equivalent (≈). Part A's primary gate is stated as t ≥ 2.0, and the t-statistic decides it.

## Part A: adapted replication on D1 (2013-04-01..2026-10-20)

**Why "adapted".** It is not an exact replication:
- it uses log returns, where the papers use simple ones;
- the instrument is a CFD's bid candles, where the papers use SPY (GHLZ) and ES futures (BDLM);
- "16:00" is the close of the 15:59 bar;
- GHLZ's own regressions appear here only as descriptions.

**Primary test (the one confirmatory test).** Regress r_last = a + b·r_rod + e on every day where both are
defined (about 3,238 days).
- **The criterion:** the momentum **replicates on D1** if b > 0 with t ≥ 2.0 (the t-statistic decides; two-sided p ≈ 0.0455).
  Otherwise it **does not replicate on D1 2013-2026**.
- **Scale:** b is reported ×100, next to BDLM's ES value (about 6.2).
- **2021-2026:** the window is the whole period. 2021-2026, the part out of sample for both papers, is
  reported separately as a description.

**Secondary verdict: GHLZ's volatility conditional.** This one is uncorrected, and is reported and labelled as
secondary.
- **The cut:** q_t = the 2/3 quantile (`numpy.quantile`, method "linear") of the last 250 defined RV_fh values
  strictly before day t. It needs at least 100 of them; otherwise H_t is undefined and the day is left out.
  The history starts on 2013-04-01 and runs across the 2021 boundary, using past data only.
- **High-volatility day:** H_t = 1 if RV_fh(t) > q_t (strictly), else 0. This uses no future data, unlike the
  paper's whole-sample terciles.
- **The regression:** r_last = a + b·r_rod + c·H + d·(H·r_rod).
- **The criterion:** momentum is called **stronger on high-volatility days (secondary, uncorrected)** if d > 0
  with t ≥ 2.0.

**Descriptive (no verdicts):**
- the primary regression on 2013-2020, on 2021-2026 and by calendar year;
- the primary slope in simple returns;
- GHLZ's regressions: r_last on r_first, on r_12, and on both;
- the decomposition: r_last on r_on and r_day together. This shows whether the prior-close anchor carries
  anything that the already-failed 09:30 anchor did not;
- the in-sample R² and BDLM's out-of-sample R² for r_rod (expanding window, at least 500 days, against the
  historical mean);
- timing returns in bps per day, with NW t, hit rate and annualised mean, against always-long:
  - η(r_rod), η(r_first), η(r_first, r_12) and η(r_first, r_rod);
  - η(x) = +r_last if x > 0, else −r_last;
  - the two-signal versions trade only when both signs agree;
- the primary slope with r_rod winsorised at its full-sample 1st and 99th percentiles, to show how much a few
  extreme days (for example March 2020) drive it.

Volume cannot be tested: the CFD has no market volume.

## Part B: does momentum add to the F2 trade?

### The pricing model, and what it means for discovery

**The model is frozen, and it was calibrated on 2026 data.** Variant (a) uses constants that the strike-ladder
study calibrated on 2026 quotes:
- **k_D1 = 1.065101699231275:**
  - a Robinhood SPXW implied-to-realized volatility ratio fitted on 7 one-minute days, 2026-10-20..2026-10-30;
  - multiplied by the Robinhood/D1 realized-volatility ratio on 22 days, 2026-09-21..2026-10-20.
- **ITM10 skew factor f_10 = 1.0046527466601545**, from the same 7 days.
- **The level L = 7709.58**, the 2026-10-20 price level from `holdout.json`. Every trade is rescaled to it.

Variant (c)'s volatility is fixed from 2021-2026 F2 trades: their mean |move| at level L, from `holdout.json`.

**None of these constants uses the outcomes of the rules below.** They fit option prices or a premium level,
not any split of F2 days by momentum.

**So discovery is retrospective, model-priced selection.** It is not a chronological out-of-sample trading
test: 2013-2020 trades are priced with a model built from 2026 quotes.

**How the calibration level can bias a skip rule.**
- A skip rule's gain over plain F2 is minus the P&L of the trades it skips.
- If the model's premium is too high by δ per contract, every trade's P&L is too low by 100·δ. More trades
  look like losers, and each skipped trade adds 100·δ to the rule's apparent gain. A skip rule then looks
  better than it would at fair prices.
- A premium that is too low does the reverse.

**The guards.** That is why a rule must also beat plain F2:
- in variant (c), a different premium level;
- in the index-return version, which has no premium at all.

### The trade and its P&L

- **Trade days:** F2 days, those with s finite and ≠ 0, the 15:51 open S finite and the 15:59 close X finite.
- **Pricing:** `backtests/spx_candle_strikes/strikes.py`, unchanged, loaded as a module. Its constants are read
  from `backtests/spx_candle_strikes/results.json`; at drafting its SHA-256 was `145544ca…5164cff9`.
- **The rv input:** `realized_vol(P.C[i, :I1550 + 1])`. It is the RMS of one-minute log returns between
  consecutive closes from 09:30 to 15:50, over the pairs where both bars exist. It is None below 300 returns,
  and that becomes NaN; strikes.py's `... or np.nan` also turns an rv of exactly 0 into NaN.
- **Variant (a):** `model_ladder(T, L, σ_a, f, h=0.10, use_rounding=True)` at offset 10.
  - σ_a = k_D1 × rv × 3 × L;
  - f = the skew factors in `results.json` → calibration → skew → label → f;
  - L = 7709.58.
  - Inside `model_ladder`:
    - λ = L / S;
    - X' = L + λ(X − S);
    - K_atm = L + λ(strike_for(S) − S), where strike_for(S) = floor(S/5 + 0.5) × 5;
    - K = K_atm − d × 10;
    - price = f_10 × Bachelier(L, K, σ_a);
    - P&L = 100 × (intrinsic(K, X') − price − 0.10) − $0.09.
- **Variant (c):** the same call with σ_c = 10.777818797750015 points (`part2.sigma_c_pts` in `results.json`)
  and f = 1 for every offset.
  - That number is the mean |move| from `holdout.json` (8.599455…, which strikes.py checks against 8.599455
    within 1e-5) divided by 2φ(0).
  - The script recomputes σ_c the way strikes.py does and stops if the two differ by more than 1e-9.
- **The $0.74-fee version** is reported as a description.

**The validity mask.** `model_ladder` returns `ok` = isfinite(σ). Where ok is False it still computes a price
with σ = 1.0 as a placeholder. This plan never uses those numbers:
- a trade with ok False is **unpriceable**;
- its P&L is missing (NaN), not a placeholder and not 0.

In variant (c), σ is a constant, so ok is True on every trade.

### Per-day series and paired samples

- **The series:** each rule gets a per-day series. On a day it trades, the value is the trade's P&L. On a day
  it does not trade (no F2 signal, or a skip), the value is 0.
- **Paired days:** a day whose plain-F2 (R0) trade is unpriceable in variant (a) is dropped from every rule's
  series, even a rule that would have skipped it. So all rules are compared on exactly the same days.
- **Same days for the guards:** variant (c) and the index-return version use exactly those days. In the index
  version, each trade's value is s·y in bps in place of its P&L. Non-trade days keep 0 there too.

### The rules (fixed menu)

| Rule | Trades F2 when |
|---|---|
| R0 (baseline) | always (plain F2) |
| R1 agree-ROD | the r_rod component passes: s · sign(r_rod) > 0 |
| R2 agree-FIRST | the r_first component passes: s · sign(r_first) > 0 |
| R3 agree-BOTH | the r_rod component passes AND the r_first component passes |
| R4 skip-strong-disagreement | unless s · sign(r_rod) < 0 **and** \|r_rod(t)\| ≥ m_t |

- **Missing or zero predictors:**
  - A component passes when its predictor is missing or exactly 0. So R1 and R2 take the trade then.
  - R3 ANDs the two components after that rule is applied.
  - R4 takes the trade when r_rod or m_t is missing.
- **R4's cut m_t:** the median (`numpy.quantile`, linear, 0.5) of |r_rod| over the last 250 defined values
  strictly before day t.
  - The values come from all days, not only F2 days.
  - At least 100 are needed.
  - The history starts on 2013-04-01 and runs across the 2021 boundary, past data only.
  - The skip test uses ≥.
- **One rule, two phrasings:** "take F2 only when it agrees with sign(r_rod)" and "skip F2 when it disagrees"
  are the same rule (R1).

### Discovery (2013-04-01..2020-12-31 only)

- **The difference series:** for each rule k, d_k(t) = series_k(t) − series_R0(t), over the paired days. It
  equals minus the P&L of the trades the rule skips.
- **Eligible** only if all three hold:
  1. mean d_k > 0 with two-sided normal p ≤ 0.0125 (|t| ≈ 2.50; the p-value decides). That is 5% with Bonferroni over the 4
     rules.
  2. mean d_k > 0 in each half (2013-04-01..2016-12-31 and 2017-01-01..2020-12-31).
  3. the index version's mean difference > 0.
- **Pick:** the eligible rule with the highest t; a tie goes to the lower rule number.
- **Freeze (immutable):** `momentum.py discover` writes the pick, or "none", to `partb_selection.json`, with
  the discovery numbers of every rule, and writes that file's SHA-256 to `partb_selection.sha256`.
  - **Hashes recorded in the file:**
    - the locked plan, `preregistration/spx_intraday_momentum.md`;
    - `momentum.py`;
    - `backtests/spx_candle_strikes/results.json`.
  - **The step's rules:**
    - it reads no D1 row after 2020-12-31 (the loader stops at the first 2021 row);
    - it refuses to run if either selection file already exists;
    - nothing else ever writes those files.

### Confirmation (2021-01-01..2026-10-20, the one criterion)

1. **Verify.** `momentum.py run` first checks four things:
   - `partb_selection.json` matches `partb_selection.sha256`;
   - the locked plan, `momentum.py` and the strikes `results.json` still have the hashes recorded in it;
   - the constants read from `results.json` equal the values above exactly: k_D1, f_10, σ_c and L.

   If anything differs, it stops.
2. **Reproduction check, run only after step 1.** On the panel's 2021-01-01..2026-10-20 days:
   - F2 trades, defined as above, must number exactly 644;
   - variant (a) at ITM10, $0.09: the arithmetic mean P&L over the ok trades (all 644 are expected to be ok)
     must be within $0.01 of 166.08169468395093;
   - variant (c) at ITM10, $0.09: within $0.01 of 157.91227664480985.

   Both numbers are in `results.json`. If either check fails, Part B and C2 stop with "pricing did not
   reproduce". Any fix and re-selection would be a labelled deviation, needing a new locked addendum.
3. **The criterion.** If a rule was picked, it **adds to the F2 trade** only if all hold:
   - its mean d > 0 with t ≥ 2.0 (variant (a), ITM10, $0.09);
   - its mean d is also > 0 in variant (c);
   - its mean d is also > 0 in the index version.

   Otherwise the result is "not confirmed".
4. **No pick.** If no rule was picked, the result is "no momentum rule improved F2 on 2013-2020". The
   confirmation test is not run.

### Descriptive

- For every rule, in both periods:
  - trades kept;
  - mean P&L of kept and of skipped trades;
  - share of trades profitable, mean per day, and the $0.74-fee version;
  - the number of unpriceable R0 days dropped.
- When no rule was picked, the 2021-2026 rows are labelled "not a test", and no rule can be adopted from them.
- R5 "add" is also reported but cannot be picked: on non-F2 days, buy ITM10 in sign(r_rod) at 15:51. It is
  kept out of the menu because its close relative (the 09:30-anchored day-so-far) is already known to have
  failed on 2021-2026.

### Detection thresholds (IID illustration, not a power calculation)

**Assumptions:**
- trades independent, with a normal approximation;
- a per-trade standard deviation of about $990 (ITM10 variant (a), 2021-2026: mean $166, t 4.25, 644
  trades), the same for kept and skipped trades;
- no autocorrelation;
- about half of the 644 confirmation trades skipped.

**Under these assumptions:**
- t ≥ 2.0 on the per-day difference corresponds to the skipped trades averaging about −$110 each, from
  t ≈ √k · m / √(sd² + m²) with k = 322. All F2 trades together averaged +$166.
- Only a sharp split clears the bar.

### Later, at real prices

Once `backtests/spx_candle_realprice/` has run, a separate addendum may price the frozen Part B rule at real
SPXW asks on 2021-2026, as a description. It cannot pick a different rule. Part B always uses the current rule
(15:50, 0.60, with the candle, ITM10), whatever the real-price tuning picks.

## Part C: dealer gamma (runs only if the data fits the budget)

**Data.**
- **Source:** Databento OPRA.PILLAR `statistics` schema, parent symbols SPX.OPT and SPXW.OPT, on each D1 day
  2013-04-01..2026-10-20. Window: the whole day (00:00-23:59 ET) before 2023-03-28, and 00:00-09:31 ET from
  2023-03-28, with a 09:31-10:01 fallback when that window has no open interest (listed in
  `fallback_days.txt`). Two probes run before this plan was locked looked only at timestamps and counts. On
  2013-06-03 the open-interest records are stamped 09:31 ET, with 2,486 contracts (SPX 2,028, SPXW 458). On
  2026-10-20 they are stamped 06:30 ET, with 29,138 contracts (SPXW 19,822, SPX 9,316). Before 2023-03-28 the
  whole day costs the same as the pre-open window.
- **Records:** stat_type 9 (open interest), with the value in `quantity`. OPRA publishes it before the open,
  and it reflects positions at the end of the prior session.
- **Contract details:** the symbol from `map_symbols` (the OSI code) gives the root, expiry, call or put, and
  strike. No contract-definition download is needed.
- **The pull:** `tools/databento_spx_oi.py` (`probe`, `estimate`, `pull`). Codex reviewed it read-only, and
  the accounting issues it found were fixed: every paid request is priced first, booked against the budget and
  logged before its file is published, and a broken download is not silently retried. It computes no statistic.
  It shares `tools/databento_spxw.py`'s key handling, spend log (`data/spx_1549/databento/spend_log.csv`) and
  $100 budget rule.
- **The download may finish before the lock, as data acquisition only.** No gamma, NGE or return is computed
  from it until this plan is locked.

> **[COST, from the coordinator's metadata.get_cost estimate, 2026-11-09; re-quoted before the pull]**
>
> - **Total:** about **$33** for all 3,287 days, a mean of $0.0101 a day. It rises from about $0.002 a day
>   in 2013 to about $0.02 a day in 2026. It was priced with the free `metadata.get_cost` on 15 sampled days.
> - **Why the pre-open window:** before 2023 it costs the same as the full day. From 2023 the full day costs
>   about 17 times more.
> - **Planned Databento total:** quotes ~$1 + trade bars ~$46 + open interest ~$33 = **~$80**, under the
>   **$100 cap** (of the $125 free credit).

**Pre-run data checks. Each one stops Part C, which is then reported as "not run (reason)".**
1. **Format:** done before the lock by the two probes above, which found stat_type 9 records with OSI symbols
   in 2013 and 2026. At run time, Part C stops if:
   - a saved day file has no stat_type 9 records;
   - the median day has fewer than 100 distinct SPXW contracts with open interest in 2016-2026;
   - any symbol does not parse as an OSI code.
2. **Budget:** the re-quoted cost of the full pull plus the spend already logged must be ≤ $100.
3. **Coverage:** N_t (defined below) must be computable on at least 95% of the 3,287 D1 days.
   - Days without it are left out and counted.
   - C1 also needs r_rod and r_last that day; C2 needs a priced F2 trade.
4. **Prior day's inputs:** the official SPX close and the VIX close must exist for t−1. A missing one makes
   that day undefined.
   - **t−1** is the prior NYSE session, meaning the previous date in Cboe's SPX close file (`SPX_History.csv`,
     saved as `data/spx_1549/spx_official_closes_cboe.csv`, the same file the real-price study uses). It is
     downloaded free from Cboe if absent.
5. **Hashes:** `momentum.py partc` repeats the checks of confirmation step 1. It also repeats the reproduction
   check before C2. It never writes the selection files.

### The net gamma proxy (BDLM's formula, free inputs)

For day t:

**Availability: known by 15:30 ET on day t.**
- Only records with ts_recv < 15:30 ET on day t are used. Their values describe positions at the end of the
  prior session.
- The probes found the records stamped 09:31 ET before 2023 and 06:30 ET after. So the proxy is not always
  known before the open, but it is always known before r_rod is measured and before the 15:51 entry.

**Open interest per contract.**
- **The record used:** the last record by (ts_recv, sequence) before the cutoff.
- **Valid values:** quantity must be an integer ≥ 0. A missing quantity, Databento's undefined sentinel
  (UNDEF_STAT_QUANTITY, the maximum of the field's integer type) or a negative quantity excludes the contract.
  It is counted, and never treated as 0.
- **Conflicts:** two records with the same (ts_recv, sequence) and different quantities exclude the contract.
  It is counted.

**Settlement, from the OSI code.**
- **SPXW:** 16:00 ET on the OSI date.
- **SPX root:** AM-settled, at 09:30 ET on the last NYSE session on or before the OSI date.
  - Before 2015 the OSI date was the Saturday after the third Friday; for example, SPX 130622 settles on
    Friday 2013-06-21 at 09:30.
  - The session calendar is the Cboe SPX close file. For dates beyond its end, use the last weekday on or
    before the OSI date.
- **Which contracts count:**
  - SPXW contracts that expire on day t (16:00) are kept.
  - Contracts that settle before 15:30 on day t are dropped: the AM SPX expiring that day, and anything
    already expired.

**Gamma.** Black-Scholes, r = q = 0, Γ = φ(d1) / (S σ √T), with d1 = [ln(S/K) + σ²T/2] / (σ √T).
- S = the official SPX close of t−1.
- σ = the VIX close of t−1 / 100, from `data/cboe_indices/VIX_History.csv`. This is the primary; the
  term-structure version is a description.
- T = the timezone-aware elapsed time from 16:00 ET on t−1 to the settlement, in seconds / (365 × 86,400),
  ACT/365.

**The proxy.**
- **NGE*_t** = 100 × (Σ over calls of Γ × OI − Σ over puts of Γ × OI).
- **How it relates to BDLM's measure.** BDLM's measure divides by market value, which is the index level ×
  the S&P 500 divisor. With identical contracts and identical gamma inputs, NGE*_t would be BDLM's NGE times
  that divisor, with the same sign. Ours are not identical: OPRA open interest and a VIX-based gamma replace
  OptionMetrics' contracts and per-option implied volatilities. So NGE* is a proxy, and its sign can differ
  from BDLM's on some days.
- **Dollar version:** NGE$_t = NGE*_t × S² / 100, in dollars per 1% move.
- **Negative-gamma day:** N_t = 1 if NGE*_t < 0, else 0. It is undefined when no contract survives the rules
  above, or an input is missing.
- **Timing:** this matches the paper's split on the previous session's NGE.

### Tests

**Sample:** all days with N_t defined, plus the variables each test needs. Nothing is tuned, so there is no
split. Each test is called supported only with a positive coefficient and two-sided normal p ≤ 0.025
(|t| ≈ 2.24; the p-value decides): 5% with Bonferroni over the two. A "not estimable" test is never supported.
- **C1, momentum:** r_last = a + b·r_rod + c·N + d·(N·r_rod), over days. Momentum is **stronger when dealers
  are short gamma** if d > 0 with p ≤ 0.025.
- **C2, the F2 trade:**
  - The regression: P&L_i = a + g·N_i, over the priced F2 trades (variant (a), ITM10, $0.09), in date order;
    the lags count trades.
  - The F2 trade is **better on short-gamma days** if g > 0 with p ≤ 0.025.
  - The guard: g must also be > 0 in the index version, with s·y in bps on the same trades.

### Descriptive

- the share of negative-gamma days by year;
- BDLM's Table 7 form: the r_rod slope on N = 1 and on N = 0 days separately;
- BDLM's Table 8 form: r_last on r_rod, NGE* and NGE*·r_rod;
- a version using puts only;
- a term-structure version:
  - σ by time to expiry comes from VIX9D (9 days), VIX (30) and VIX3M (93);
  - it is interpolated linearly in total variance and held flat beyond the ends;
  - it is reported with its sign agreement with the VIX version;
- C1 and C2 on 2013-2020 and on 2021-2026;
- F2 trades kept and skipped by Part B's frozen rule, split by N;
- counts: contracts excluded by each rule above, and the days on the 09:31-10:01 fallback.

### Caveats to state

- **The positioning is assumed, not observed.** The proxy assumes dealers are long all calls and short all
  puts. 0DTE flow is two-way, so this is cruder in 2022-2026.
- **Same-day trades are missing.** Open interest misses positions opened and closed on day t, which is most
  0DTE trading since 2022.
- **One volatility, no skew.** A single VIX volatility ignores the skew and the term structure. Which way that
  biases NGE* is not known in advance.
- **Detection threshold for C2 (IID illustration, not power).**
  - Assumptions: about 1,550 F2 trades over 2013-2026, split evenly by N; independent trades; a $990 standard
    deviation on both sides.
  - Under these, p ≤ 0.025 (|t| ≈ 2.24) corresponds to a difference of about $113 a trade.

## Order of work and gates

1. **Lock.** The user moves this file to `preregistration/spx_intraday_momentum.md` and adds its hash to the
   ledger. The script, `backtests/spx_intraday_momentum/momentum.py`, refuses to read data unless the locked
   file exists and its SHA-256 is in `preregistration/LEDGER.md`, as `strikes.py`'s `check_gate` does.
2. **`momentum.py selftest`**, on synthetic data. It checks:
   - a planted momentum effect is found and pure noise is not;
   - the hash gates stop a run;
   - no 2021 date reaches discovery;
   - H_t, m_t and R3's components follow the rules above, using only earlier days;
   - unpriceable trades are dropped as missing, with paired days;
   - "not estimable" triggers;
   - the HAC t matches `nw_mean_test` on a constant regression;
   - a failed reproduction check stops the run;
   - the open-interest rules (cutoff, last record, conflicts, sentinel, settlement dates) behave as stated.

   `momentum.py` must contain all three steps before `discover` runs, because its hash is frozen there.
3. **`momentum.py discover`:** D1 2013-04-01..2020-12-31 only. It writes the immutable selection and refuses if
   one exists.
4. **`momentum.py run`:** verify, then the reproduction check, then Part A and Part B's confirmation.
5. **Part C:** the data checks and the pull (data step only), then `momentum.py partc`.

## What is reported

- **Part A:**
  - the primary slope (×100), t, p, n and R², with the verdict;
  - the secondary conditional's d, t and p, with its labelled secondary verdict;
  - all the descriptive tables, by period and year.
- **Part B:**
  - the discovery table for R0-R5 (both halves, t, p, kept and skipped means) and the pick or "none";
  - the reproduction check;
  - the confirmation numbers and verdict;
  - the descriptive 2021-2026 table.
- **Part C:**
  - the data checks, the actual spend and the coverage;
  - C1 and C2 with verdicts;
  - the descriptive tables; or "not run (reason)".
- **Counts:** days and trades left out at each step, and why, including "not estimable".

## Text rules

- Say that D1 is a CFD's bid candles, that the "16:00" price is the close of the 15:59 bar and not the official
  settlement, and that Part B and Part C P&L comes from a model.
- Call Part A an adapted replication.
- Say that Part B's discovery is retrospective, model-priced selection with constants calibrated on 2026 quotes.
- Say plainly that 2021-2026 was not blind for related momentum signals, and why.
- Say that 2013-2020 lies inside BDLM's sample.
- If Part A fails, say "did not replicate on D1 2013-2026", not "the papers are wrong".
- No trading recommendation.

## Outputs

- **Written once by `discover`, never rewritten:** `partb_selection.json` and `partb_selection.sha256`.
- **Rebuilt by `run`:** `backtests/spx_intraday_momentum/results.json` and `RESULTS.md`. A later `partc` adds
  its section to them.
- **Rebuilt by `partc`:** `data/spx_1549/nge_daily.csv`.

`momentum.py` reuses `scan.py`'s panel and statistics and `strikes.py`'s pricing. Neither file is changed.

## Choices made in this plan (differences from the original brief; settled 2026-11-09)

1. **Part A's primary predictor is r_rod (BDLM), over all of 2013-04-01..2026-10-20.** 2021-2026 is reported
   descriptively. r_first and r_12 (GHLZ) are descriptive.
2. **Part A's primary statistic is the slope, as in the papers.** The sign-timing return is descriptive.
3. **The volatility conditional is applied to r_rod.** It uses a trailing 250-value cut, not whole-sample
   terciles, and it is a secondary, uncorrected verdict. Volume is impossible on a CFD.
4. **All parts start on 2013-04-01, not the scan's 2013-02-28.** That is the OPRA start, and every part starts
   from the same panel, with test-specific exclusions. Days after a half day are excluded only from tests that
   need PC; Part B keeps them, subject to pricing validity and its missing-predictor rules.
5. **Part B's criterion is the model P&L, with the variant-(c) and index-return guards.** The menu has 4 rules;
   the brief's two phrasings were one rule.
   - Selection: p ≤ 0.0125 (Bonferroni over 4), with both halves positive and the index version positive.
   - The selection is immutable.
   - The "add momentum on non-F2 days" rule is descriptive only.
6. **Part C uses BDLM's formula with free inputs.** Flat VIX is primary; the term structure is descriptive. The
   market-value scaling is dropped because only the divisor differs. The two tests are Bonferroni-corrected
   (p ≤ 0.025 each).
