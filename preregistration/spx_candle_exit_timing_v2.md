# Pre-registration draft (v2): can a take-profit, trailing-stop or give-back exit beat holding the 15:50 candle trade? Tune on 2021-2023, test once on 2024-2026

**Status: DRAFT, not locked.**
- Drafted 2026-11-10 at the user's request, after the locked plan `spx_candle_exit_timing.md` (v1) stopped at its
  coverage gate.
- To lock, the user copies this file to `preregistration/spx_candle_exit_timing_v2.md` and adds its SHA-256 to
  `preregistration/LEDGER.md`. Until then nothing here binds. `exit_timing_v2.py` was written before locking and
  has run only on synthetic data; it refuses to read real data until this plan is locked.

Research only. Nothing here is a trading recommendation.

## How this plan is written

v1 is locked (`preregistration/spx_candle_exit_timing.md`, SHA-256
`34c2c8347c7963bcdc295155de45bbd0aa65ed1e1a7b3ba35fd6df4ba82201b0`) and cannot change. **Everything in v1 applies
to v2 unless a numbered change below replaces it**: the entries, the hold baseline and its checks, the timing
(decisions 15:52-15:58, sale at the next snapshot's bid, roll-forward to 15:59, else settle), the missing-quote
rules, the tolerances, the isolation and rerun discipline, the halves, the score, eligibility, the pick and its
tie-breaks, the block sign-flip luck diagnostic (blocks of 5, 9,999 draws, seed 20261109, p ≤ 0.05), the test
(25 sales in at least 10 blocks; mean d > 0 and Newey-West t ≥ 2.0), Part 3, the text rules and the caveats.
Wherever v1 says 41 or 44 rules, read 26.

## Why v2 exists

v1 asked whether any of 44 real-time exit rules beats holding. It stopped at its first gate, before any rule was
computed on any period:
- v1 required 95% of tuning trades to be complete: a quote for the option at every minute 15:51-15:59, an
  implied index level at every minute 15:51-15:58, and a valid 15:51 straddle. Only 197 of 270 were (H1 107 of
  133; H2 90 of 137). Tuning wrote "coverage too low; no pick", and the test step wrote "no test (coverage)"
  without reading any 2024-2026 input.
- The option's own quotes were complete on all 270 tuning trades. The implied index level was the problem: it needs
  three strikes where both the call and the put have a bid, and near the close out-of-the-money bids fall to zero.
  It was missing on 70 trades at 15:58, 35 at 15:57, 18 at 15:56, 8 at 15:55, 1 at 15:54 and 1 at 15:53. One trade
  also lacked the 15:51 straddle.

Only the index-based families (SR, SRV) need the index level. The other 26 rules read only the option's bid, which
is what a sale gets. v2 keeps those 26 and asks the same question with them.

## The changes

1. **Rules.** Only three families, 26 rules, in this enumeration order:
   - **TS** trailing stop on the bid: fires at m when b_m ≤ (1 − x) × B*_m; x = 0.10, 0.20, 0.30, 0.40, 0.50 (5);
   - **PL** profit lock (give-back) on the bid: fires when G*_m ≥ g × A and b_m ≤ B*_m − h × G*_m;
     g = 0.10, 0.20, 0.30; h = 1/3, 2/3, 1 (9);
   - **TP** take-profit on the bid from minute T: fires when m ≥ T and b_m ≥ (1 + g) × A;
     T = 15:52, 15:54, 15:56, 15:58; g = 0.10, 0.20, 0.30 (12).

   Definitions, names and neighbours are v1's. SR and SRV are dropped. The luck diagnostic's matrix is n × 26, and
   all 26 rules flip together.
2. **Coverage.** An entry is complete if the option has a valid quote in every snapshot 15:51-15:59. The implied
   index level and the straddle are no longer required, because no candidate rule reads them. The gate is
   unchanged otherwise: at least 95% of tuning entries, and of each half, or tuning writes "coverage too low; no
   pick" and stops, and the test step writes "no test (coverage)".
3. **The index level is context only.** It is still computed, as in v1, for the six earlier rules re-expressed in
   Part 3 (stops at -3, -5, -8 points; targets at 5, 10; stop -5 or target 10). A minute without it is a
   no-decision minute for them. The straddle X is written to the trades file only. v1's text that presents SR or SRV
   as candidates does not apply: their rows in the rules table and their entries under "In words" and "Why these are
   new". Point 3 under "Choices fixed here" is replaced by: **Units:** TS, PL and TP in percent of the price paid
   or the peak bid. A percent of an ITM10 option's premium is close to a fixed number of SPX points, so it is a
   larger relative move when SPX is lower or calmer (much of 2021-2023); v2 accepts that, because the rules that
   would have adjusted for it need the index level. The definitions of the implied spot, u and r stay, for the six
   context rules.
4. **Files.** Folder `backtests/spx_candle_exit_timing_v2/`; code `exit_timing_v2.py`; trades file
   `data/spx_1549/databento/exit_timing_v2_trades.csv`; plan path `preregistration/spx_candle_exit_timing_v2.md`.
   Nothing from v1's output folder is read. v2's own selection file sets which later days count as fresh.
5. **Seen before drafting** (added to v1's list, which still applies):
   - v1's stop and the counts above. They are availability counts; no exit rule was computed on any period, and the
     hold figures are the ones v1 already listed;
   - this revision was chosen after seeing only those counts. The option's quote coverage on 2024-2026 has not been
     looked at;
   - the request came from the user after watching one live signal day (2026-11-10, outside both periods), as
     disclosed in v1.
6. **What the change costs.** The luck diagnostic now takes the best of 26 correlated rules instead of 44, so it is
   a little less demanding; nothing else about the bar changes. Index-based exits are not tested by this plan.

## Order of work

1. Draft (this file) and `exit_timing_v2.py` (v1's code with the changes above). One read-only review of both.
2. The user reads it and locks it.
3. `selftest`, then `tune` once, then `test` once.
4. A plain-English SUMMARY.md by hand.
