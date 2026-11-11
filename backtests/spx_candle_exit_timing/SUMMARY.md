# Real-time exits for the 15:50 candle trade: summary

Plan: `preregistration/spx_candle_exit_timing.md`, locked 2026-11-10T22:17:50Z (SHA-256 `34c2c834...`).
Research only; nothing here is a trading recommendation.

## The question

The rule buys an SPXW option 10 points in the money at the 15:51 ask and holds it to the 16:00 settlement. Could a
rule fixed in advance do better by selling early: a take-profit ("sell once the bid is 10%, 20% or 30% above what
was paid"), a trailing stop, a give-back rule, or a rule on the index's move? Forty-four such rules were to be tuned
on 2021-2023 and the best one tested once on 2024-2026, at real one-minute bids.

## What happened

The study stopped at its first gate, before any exit rule was computed on any period.

- The plan required at least 95% of the tuning trades to be "complete": a quote for the option at every minute
  15:51-15:59, an index level at every minute 15:51-15:58, and the 15:51 straddle.
- Only 197 of 270 tuning trades (73%) were complete: 107 of 133 in 2021-22 and 90 of 137 in 2022-23.
- Under the plan, that ends the study: tuning wrote "coverage too low; no pick", and the test step wrote
  "no test (coverage)" without reading any 2024-2026 data.

## Why (checked after the stop; availability only, no P&L)

- The option's own quotes were complete: all 270 trades had a bid at every minute from 15:51 to 15:59.
- What was missing was the index level. The plan read it from option prices (put-call parity), which needs three
  strikes where both the call and the put still have a bid. In the last minutes, options a few points out of the
  money often fall to a zero bid, so the level could not be computed: on 70 trades at 15:58, 35 at 15:57, 18 at
  15:56, 8 at 15:55 and 2 earlier. One trade also lacked the 15:51 straddle.
- So the gate caught a flaw in the plan's design, not a data error: the index-based rules (SR, SRV) depend on a
  measure that fails exactly when they need it.

## What this does and does not say

- It says nothing about whether selling early helps. No exit rule was evaluated, and holding was not shown to be the
  best exit.
- The question can be asked again under a new plan. The 26 rules that use only the option's bid (take-profits,
  trailing stops, give-back rules) have complete data on the tuning trades. A revised plan could keep those rules,
  gate coverage on the option's quotes, and disclose this stop and the counts above.

Files: `selection.json`, `tune_results.json`, `results.json`, `RESULTS.md`, `inputs_tune.json`, `inputs_test.json`,
`runs/` (one tune start, one test start).
