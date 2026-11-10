# Audit disposition: real-option forward log (`analysis/candle_1550_options_forward.py`)

Written 2026-10-30. This file records what was done with each finding of an audit of the forward log. The audit was run
read-only on the script, its tests, its outputs and the pre-registration
`preregistration/spx_candle_forward_options.md` (ledger hash `94d5c70c…5851`, unchanged by these fixes).

## Plain English first

- **No published trade number was wrong.** The audit recomputed all 16 traded rows and the six straddles from
  the raw Robinhood files, and they all matched. The headline totals are still exit A **+$703.73** (2 of 3
  finalized trades won) and exit B **−$173.72** (2 of 4).
- **What it found were ways bad *future* data could quietly skew the totals:** a real $0 exit counted as
  "missing", duplicate files silently overwriting each other, a 15:59 bar read before it had finished, a
  broken daily file accepted as the official close, and rounding before deciding win or loss. All are now
  refused or handled, each with a test.
- **One small real deviation:** the backtest-model column used holdout.json's unrounded prices, not the
  exact registered constants. It now uses the registered numbers; five model P&Ls moved by one cent, at
  both fee levels ($0.09 fee: strong body 10-22 112.82 → 112.83, 10-27 275.79 → 275.80, 10-29 241.68 →
  241.69, 10-30 −374.86 → −374.85; any body 10-23 3.08 → 3.09), exactly as the audit computed.
- **Re-run record.** After the fixes every real-option column of `options_log.csv` (status, contract,
  settlement, prices, all four P&L columns) is identical to the pre-audit run; the largest model-P&L change
  is $0.01. Tests: 15 → 28, all pass.

## Finding by finding

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | A real 15:59 close of 0 became `exit_bar_missing`, dropping a loss from exit B | **Fixed.** `price()` takes `allow_zero`: entry must be finite and > 0, the 15:59 exit finite and ≥ 0. Tests: `test_zero_exit_is_a_loss_not_missing` (−$370.18, the audit's example), `test_zero_or_infinite_entry_is_not_traded`. |
| 2 | Major | Conflicting bars across files were last-file-wins; duplicate log rows were accepted | **Fixed.** The same contract and minute in two files: identical bars are kept once, different bars stop the run (the error names both files). Two forward log rows for one date stop the run. Tests: `test_conflicting_duplicate_bars_stop`, `test_identical_duplicate_bars_counted_once`, `test_duplicate_log_rows_stop`. |
| 3 | Major | Exit B could use a 15:59 bar fetched before it finished | **Fixed.** Exit B needs completion evidence: the same folder's `spx_1m.json` holds a real (not gap-fill) index bar beginning at 16:01 ET or later. The collector fetches the index before the options, so options fetched after it are past 16:01. Without it, exit B is `no_completion_evidence` and exit A is unaffected. All eight live folders end at 16:04, so no current row changed. Test: `test_no_completion_evidence_blocks_exit_b_only` (no file, ends 15:59, later bars gap-fill). |
| 4 | Major | The daily-close loader did not validate its input; `inf` option prices were accepted | **Fixed.** A settlement must come from a result with the SPX instrument id, interval `day`, not interpolated, with a finite close > 0; otherwise the older valid close is kept. All option prices go through `finite()`. Tests: `test_invalid_daily_bars_are_not_a_settlement` (NaN, 0, inf, a SPY result, a minute result), `test_zero_or_infinite_entry_is_not_traded`. |
| 5 | Minor | "Newest daily file" was ambiguous | **Fixed (rule stated) + reported.** "Newest" = the `live_<date>` folder with the latest date (decisions list). Any two files that disagree on a date's close by more than 0.005 points are listed in `options_summary.json` and on the page. Currently none disagree. Test: `test_newest_daily_file_wins_and_interpolated_ignored`. |
| 6 | Minor | Model constants derived from holdout.json, not the registered ones | **Fixed.** `MODEL_HALF_BPS` is exactly 0.5 × 11.154 and 0.5 × 8.285 / 7709.58 × 1e4; holdout.json is only checked to agree within 0.0015 bps. The tests type the registered numbers in independently. Test: `test_registered_model_constants`. |
| 7 | Minor | Rounding before win/loss and totals | **Fixed.** P&L is kept at full precision through classification and aggregation; only the outputs are rounded. Test: `test_tiny_win_counts_at_full_precision` (+$0.004 counts as a win). |
| 8 | Minor | Availability decided by file names | **Fixed.** Every `options*.json` is read and classified by its own `interval` field. `no_option_files` (no file) and `no_minute_option_bars` (files, but no minute results) are now separate statuses, and the page wording follows. Tests: `test_ten_minute_file_with_a_minute_style_name`, `test_folder_without_option_files`. |
| 9 | Minor | Reporting gaps | **Fixed.** The model is tallied on each exit's own day set (A: finalized trades; B: trades with an exit B). The page shows $0.74 wins, totals and means, the exit-B status in the daily table, and both market/model ratios per day. Test: `test_model_tally_on_each_exit_day_set`. |
| 10 | Minor | Wording overstated comparability | **Fixed.** The page says "N trades with a real entry price, M of them finalized". It explains that exit A settles at the official close while the backtest model scored the 15:59 index close with strike = entry. It says the straddle ratio compares the pair, not each leg, and that the sample depends on which days were collected in time. |

The audit also noted, without a numbered finding, that the tests' fixed UTC−4 helper could not cover winter dates.
The helper now uses `zoneinfo`; `test_winter_date_uses_eastern_standard_time` runs a December (EST) day.

## Not changed, by design

- **Synchronized availability.** The strike comes from the index's 15:51 open and the price from the option's
  15:51 open, as registered. Minute bars cannot show both were available at the same instant. This stays a
  caveat on the page; it is not a code change.
- **Already-known index results.** The four strong-body index wins were known before this options addendum
  was registered. The registration and the page both say so; the log stays descriptive.
- **No observed spread.** Robinhood bars carry no bid/ask, so the $0.10 half-spread remains the backtest's
  assumption, as registered.
