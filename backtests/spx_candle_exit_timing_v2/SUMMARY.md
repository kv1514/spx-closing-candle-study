# Exit-timing v2 in plain English

**Question.** After buying the 15:50 candle option at 15:51, can a rule that watches the option's own bid and sells
early (a trailing stop, a stop from the peak, or a take-profit) beat simply holding to the 16:00 settlement?

**What was done.** The v2 plan (26 rules, all reading only the option's bid) was locked on 2026-11-11 at 00:01 UTC
(SHA-256 `46ec5be8...`) and run once. Tuning used 2021-2023 (270 trades); every trade had full quotes, so the
coverage problem that stopped v1 did not come up.

**Result: no rule advanced.** To advance, a rule had to beat holding in both halves of 2021-2023. None did. All 26
lost to holding on tuning, from about $9 to $120 a trade. So the one-time test on 2024-2026 did not happen: "no test".

**What the numbers say (descriptive, not a test):**
- Take-profits did worst. Selling once the bid is up 10%, 20% or 30% cost $49 to $107 a trade against holding on
  2021-2023, and $39 to $108 on 2024-2026. The trades that pop and keep going pay for the ones that fade, and an
  early sale cuts them off.
- Selling at any fixed minute from 15:52 to 15:59 also lost: $112 to $168 a trade on 2021-2023, $51 to $120 on
  2024-2026. Part of that is the spread: a sale gets the bid, while holding settles at the index value with no spread.
- A few loose stops were near zero on 2024-2026 (within about $9 a trade, t under 1). That is noise, and they lost
  on 2021-2023.
- With perfect hindsight, the best minute would have added $224 a trade on 2021-2023. No rule here captured any of it.

**Limits.** One-minute snapshots, one contract, a firm bid and a one-minute delay. Only the 15:51 entries of this
rule were studied; this says nothing about other entries, like an option bought at midday. "No rule advanced" does
not prove holding is the best possible exit, only that none of these 26 beat it. Research only; not a
recommendation.

Files: `RESULTS.md` (all tables), `selection.json`, `results.json`, and the plan at
`preregistration/spx_candle_exit_timing_v2.md`.
