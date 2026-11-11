# Why 15:50? A test with the exchanges' own closing-imbalance messages

**Status: LOCKED 2026-11-10T19:37:24Z (UTC).** Locked by Claude (Opus 5.5) at the user's explicit instruction:
asked "Lock the plan so the $17.34 download and the test can run?", the user answered "Lock it". **No analysis code
existed at locking**; the only code was the pre-lock scripts named in sections 5, 8 and 10. No outcome had been
computed. The only imbalance records downloaded were the two format-sample days outside the sample (section 2a).
The file hashes fixed at the lock are in the "Lock record" at the end.

Drafted 2026-11-10 at the author's request ("Yes, draft it"). Review: `data/codex_audits/spx_candle_imbalance_plan_codex.md`
(18 points, 8 must-fix; all applied below). Companion plan: the rule-change test in
`backtests/spx_candle_rulechange/PREREG_DRAFT.md`. The two are adjudicated separately; neither verdict changes the
other.

## 1. The question

The paper suggests that the 15:50 candle predicts the close because the exchanges publish closing-auction
imbalance information at 15:50: traders act on it during the 15:50 minute, and the price keeps moving the same way
while the auction absorbs the imbalance. If that is an important channel, the candle should be right more often on
days when it points the same way as the published imbalance than on days when it points the other way.

This study measures, on each signal day of the registered rule in 2021-2026, the direction of the aggregate
closing imbalance that the NYSE and Nasdaq published between 15:50:00 and 15:51:00 for about 50 large stocks, and
compares the rule's hit rate on agreeing and disagreeing days. The claim it can support is conditional on signal
days; it cannot say why strong candles arise or whether the imbalance predicts the close on other days.

## 2. What the exchanges publish in the 15:50 minute (2021-2026)

| Exchange | In the 15:50 minute | Later | Databento dataset, schema |
|---|---|---|---|
| NYSE | Closing imbalance for NYSE-listed stocks from 15:50 (MOC/LOC cut-off and publication moved from 15:45 to 15:50 on 1 April 2019) | Updates to the close | `XNYS.PILLAR`, `imbalance` |
| Nasdaq | Early closing imbalance information (EOII) every 10 seconds from 15:50 (from about Q4 2019), in the NOII message format: paired shares, imbalance shares, imbalance direction and current reference price; near and far prices set to 0 | Full Net Order Imbalance Indicator (NOII) every second from 15:55 | `XNAS.ITCH`, `imbalance` |

Sources are those of the rule-change draft (section 2 there) and Nasdaq Equity Trader Alert 2019-20 ("Nasdaq to
Disseminate Early Closing Auction Imbalance Information", read 2026-11-10; it announced a 15 April 2019 start,
later delayed, as the rule-change draft records). Databento's free record counts cannot confirm the Nasdaq
schedule: they return a flat 330 records per requested symbol between 15:50 and 16:00, for NYSE-listed stocks and
SPY as well, so they are a pricing figure, not a count of messages. (An earlier reading of the 330 as 30 + 300
messages was withdrawn for this reason.) Pre-lock check 2 confirms the timing and Databento's mapping of these
fields on one day before and one day after the sample; the years between are assumed to use the same format.

### 2a. What the format samples showed (pre-lock check 2, done 2026-11-10)

Downloaded with the author's approval ("i approve"): 2020-12-30 (2021 list) and 2026-11-06 (2026 list), 15:45-16:00,
each stock from its listing exchange, plus JPM and XOM requested from Nasdaq as controls; quoted $0.0556, logged in
`spend_log.csv` before each request (`format_sample.py`; files in
`data/spx_1549/databento/imbalance_format_sample/`). Both days are outside the sample; no outcome was computed.
- **NYSE** (31 and 30 stocks): every stock's first record is in the 15:50 minute, the earliest at 15:50:00.001;
  none before 15:50. `auction_type` is `C` (8,861 and 10,262 records) or `R` (22 and 4, at the 15:50 publication);
  sides B, A and N; `ref_price`, `total_imbalance_qty` and `paired_qty` always defined, prices positive. About 21
  records per stock in the 15:50 minute.
- **Nasdaq** (19 and 20 listed stocks, plus the two controls): `auction_type` `C` only; records every 10 seconds from 15:50:00 (6 per stock in
  the 15:50 minute) and every second from 15:55:00, confirming the early-indicator schedule in both years;
  `ref_price`, `total_imbalance_qty` and `paired_qty` defined; the indicative-price fields are undefined
  (`UNDEF_PRICE`), as Nasdaq's notice says.
- **Controls:** Nasdaq sends JPM and XOM (NYSE-listed) 330 records each with side N, quantity 0 and `ref_price` 0.
  These are not imbalance information; the listing-exchange rule never requests them, and the usability rule
  (`ref_price` > 0) would reject them anyway.
- Prices are integers in 1e-9 dollars (`pretty_px=false`), times are nanosecond integers.

## 3. Predictions, and what a result can and cannot show

- **H1 (primary).** On signal days, the rule's hit rate is higher when the candle agrees with the published
  imbalance than when it disagrees.
- **H2 (secondary).** The candle agrees with the published imbalance on more than half of the classified signal
  days. (The 50% benchmark is descriptive; it is not an independence benchmark when up and down days are unequal.)
- **H3 (secondary).** On classified signal days, the imbalance direction by itself is right about the move from
  15:51 to the close more than half the time. H3 is mechanically related to H1: on disagreeing days its hit is the
  complement of the candle's.

**Wording of the verdict.** If H1 passes, the paper says: "Among classified signal days, the candle's hit rate was
higher when its direction agreed with the measured 15:50 imbalance; the pre-specified nominal threshold passed."
That is an association consistent with the auction explanation, not proof of it, and not a statement that the
edge is absent on disagreeing days. If H1 fails, the paper says the prediction was not confirmed, that the test has
limited power (section 9), and that a failure does not refute the auction explanation. Either way the paper reports
both hit rates, d with its bootstrap interval, and the agreement table.

**Limitations, stated in advance.**
- **Association, not cause.** The candle and the imbalance can both reflect the same orders (for example
  index-fund closing orders known earlier in the day). Agreement does not show that traders reacted to the
  publication.
- **Timing.** Records are selected by Databento's capture time (`ts_recv`) before 15:51:00. The price may already
  have moved before a record arrived, so the test cannot show that the publication came before the price response.
- **Composition.** Year, candle direction, volatility and index-rebalancing days can affect both agreement and the
  hit rate, and the rule's hit rate is known to vary by year. The year-and-direction adjusted comparison in section
  7 is descriptive.
- **Ways a real effect could be hidden:** the price adjusts within the candle so little is left after 15:51;
  imbalances change after the first publication; stock imbalances offset each other in D; the 50 stocks cover only
  part of the index; the outcome is read from the CFD feed.
- **Signal days only**, to stay inside the budget. Conditioning on a strong candle can itself select combinations
  of imbalance and other order flow that create or suppress an association.
- **The outcome is read from the CFD feed** (the Dukascopy US500 series), as in the registered rule, not from the
  official SPX close.
- **Partly seen** (section 8).

## 4. Data and days

- Candles and outcomes: Dukascopy US500 CFD one-minute bars, `data/spx_1549/d1_usa500_rth_1m.csv.gz`
  (SHA-256 `6e8219764151bbb1f761723ddbc291b66daab31472d5c37793f9f220f4153459`), keep set of
  `data/spx_1549/d1_days.csv` (SHA-256 `9c013d8a1602c88a2421374fa2ce1c836d71dc87efeb8b6c95a38ddacca04cd9`),
  loaded with `load_panel` from `backtests/spx_candle_scan/scan.py` (its SHA-256 recorded at the lock and checked at
  start-up).
- Days: 2021-01-04 .. 2026-10-20, the keep set: 1,446 days. Half days are not in the keep set. No later data.
- **Signal days:** the 15:50 candle has a strong body (section 6): **644 days** (319 up, 325 down; 111, 105, 113,
  106, 117 and 92 in 2021 to 2026), listed in `signal_days.csv`. This equals the registered rule's 644 holdout
  trades.
- Option prices (robustness 5 only): `data/spx_1549/databento/realprice_trades.csv` (SHA-256 recorded at the lock),
  rows with config `current`, period `confirmation`, cell `15:50 body>=0.60 with ITM10` and status `priced`: 585
  rows, one per date (the 586th row of that cell has status `not_priced` and is excluded). Column `pnl_fee_0.09`:
  dollars per contract, bought at the ask with a $0.09 fee, the paper's main confirmation.
- Imbalance messages: Databento `imbalance` schema, datasets `XNYS.PILLAR` and `XNAS.ITCH`, 15:50:00.000 to
  16:00:00.000 ET on each signal day, each list stock from its listing exchange's dataset that day (`venues.csv`,
  section 5), so two requests a day. Requested as CSV with `pretty_px=false` (prices as integers in units of
  1e-9 dollars) and `pretty_ts=false`. The quote bills the whole ten minutes even for a shorter window, so the ten
  minutes are saved; the tests use only records captured before 15:51:00. Files:
  `data/spx_1549/databento/imbalance_1550-1600/<dataset>/<date>.csv.gz`, with SHA-256 sums in a download manifest.

## 5. The stock list

- **Rule.** For calendar year Y (2021 .. 2026): the 50 largest common-stock positions by value in SPY's N-PORT-P
  report for the period ending 31 December of Y-1. The list holds for every signal day of year Y.
- **Hindsight.** The positions are year-end positions, chosen without any later performance, but the reports were
  filed in late February, after January trading had begun (filing dates below). The lists are therefore a
  retrospective reconstruction of year-end holdings, not information a trader held on 1 January; year-end index
  weights were public then, but not through these filings.
- **Filings** (SPDR S&P 500 ETF Trust, CIK 884394; each file's fund name and report date are checked when parsed):

  | Year used | Report date | Filed | Accession |
  |---|---|---|---|
  | 2021 | 2020-12-31 | 2021-02-26 | 0001752724-21-043869 |
  | 2022 | 2021-12-31 | 2022-02-25 | 0001752724-22-048845 |
  | 2023 | 2022-12-31 | 2023-02-28 | 0001752724-23-046862 |
  | 2024 | 2023-12-31 | 2024-02-27 | 0001752724-24-043296 |
  | 2025 | 2024-12-31 | 2025-02-27 | 0001752724-25-043826 |
  | 2026 | 2025-12-31 | 2026-02-26 | 0001410368-26-020131 |

- **Eligibility and ranking.** Holdings in the filing's XML with `assetCat` = `EC` (common equity; REIT common
  shares included); everything else is excluded (in all six filings every holding is `EC`). Each holding is
  identified by its **ISIN**: the filings give the placeholder CUSIP `000000000` to about 28 foreign-domiciled
  issuers (Accenture, Linde, Medtronic and others), so CUSIP cannot be the key. Entries with the same ISIN are
  summed (none occur); a holding without an ISIN would be keyed by a real CUSIP or excluded (none occur). Rank by
  `valUSD` descending, ties by key ascending; keep the first 50. Each share class is its own position (GOOGL and
  GOOG). Built by `build_lists.py` into `stock_lists_raw.csv` and `stock_lists.json` (filing hashes, coverage).
- **Coverage.** The 50 positions hold 54.4%, 54.9%, 51.4%, 56.0%, 60.6% and 62.5% of SPY's net assets at the
  year-ends 2020 to 2025; 74 distinct positions over the six years.
- **Tickers.** From the ISIN by OpenFIGI's free mapping (`map_tickers.py`; answers saved in `isin_figi.json` and
  `isin_tickers.csv`): 71 of 74 mapped to one US ticker. The other three are mapped from the filing's issuer name
  and confirmed by Databento symbology: Linde's pre-2023 Irish ISIN to LIN, Exxon Mobil to XOM, Honeywell to HON.
  Spellings: Berkshire Hathaway class B is `BRK B` on NYSE and `BRK.B` on Nasdaq.
- **Renames and reuse.** Facebook traded as FB until 8 June 2022 and as META from 9 June 2022 (effective date of
  Meta Platforms' ticker change); from 30 June 2021 to that date the symbol META belonged to a different security
  (an ETF), so META is never used for Facebook before 9 June 2022. Databento symbology resolves FB and META over
  both periods, so it cannot detect renames; renames come from corporate announcements. No other list position
  changed ticker in 2021-2026. After a merger or delisting a stock has no records and is not replaced. No
  discretionary substitutions.
- **Listing exchange, by day.** A stock is requested only from its listing exchange's dataset (requesting both
  would double the cost). Rule (`assign_venues.py`): NYSE's feed carries closing-imbalance records only for
  NYSE-listed stocks (free counts: JPM, XOM and BRK B have 340-480 records between 15:50 and 16:00, AAPL, MSFT and
  SPY none), so a stock is NYSE-listed on a day if its free XNYS.PILLAR record count for that window is above 0, and
  otherwise is requested from XNAS.ITCH. (Nasdaq's counts are a flat 330 per requested symbol, listed there or not,
  so they cannot show the listing.) Counts are taken on each year's first and last signal day, with a binary search
  over signal days where they differ. Result: `venues.csv`.

## 6. Definitions

Times are America/New_York, from nanosecond UTC timestamps.

- **Candle, strong body, signal.** The one-minute bar opening at 15:50:00 with open O, high H, low L, close C.
  Strong body: |C - O| >= 0.6 x (H - L), with H - L > 0 and all four finite. Signal s = +1 if C > O, -1 if C < O.
- **Outcome.** y = log(C[15:59] / O[15:51]): from the open of the 15:51 bar to the close of the 15:59 bar, the
  registered rule's target. **Outcome-eligible:** O[15:51] and C[15:59] finite and positive, and y != 0.
  **Hit:** s x y > 0.
- **Closing-imbalance record.** A record of a list stock, from its listing exchange's dataset, whose `auction_type`
  is a closing-auction code: on XNYS.PILLAR `C` (closing auction) or `R` (the regulatory imbalance published at
  15:50); on XNAS.ITCH `C` (both the 10-second early indicator from 15:50 and the NOII from 15:55 carry it). Fixed
  from the format samples (section 2a).
- **Usable record.** `side` is A, B or N; `total_imbalance_qty` is an integer other than 4294967295
  (`UNDEF_ORDER_SIZE`); `ref_price` is an integer other than 9223372036854775807 (`UNDEF_PRICE`) and greater than
  0. Blank fields or other values make the record unusable. A missing quantity is unknown, not a balanced auction.
- **The 15:50 record of a stock.** Among its closing-imbalance records with `ts_recv` in [15:50:00.000,
  15:51:00.000), the one with the earliest `ts_recv`; ties keep the first in file order. If that record is not
  usable, the stock is unusable that day (no search for a later record). Only the dataset of the stock's listing
  exchange that day (section 5) is requested and used.
- **Signed dollar imbalance.** For a usable record, D_i = side_i x Q_i x p_i, with side_i = +1 for B (buy
  imbalance), -1 for A (sell imbalance), 0 for N; Q_i = `total_imbalance_qty`; p_i = `ref_price`. Computed with
  exact integer arithmetic (units of 1e-9 dollars), so cancellation does not depend on summation order. No price
  fallback: a stock without a usable record does not enter D.
- **The day's imbalance.** D = sum of D_i over usable stocks. A day is **covered** if at least 10 distinct stocks
  are usable; genuine zero imbalances (side N, or quantity 0) count as usable. A covered day with D != 0 is
  **classified**; others are unclassified and counted.
- **Agreement.** A classified day agrees if sign(D) = s and disagrees if sign(D) = -s.

## 7. Tests

**Primary (H1).** Over classified, outcome-eligible days: h_a and h_d are the hit rates on agreeing and disagreeing
days, with n_a and n_d days. d = h_a - h_d, se = sqrt(h_a(1 - h_a)/n_a + h_d(1 - h_d)/n_d), t = d / se.
**H1 passes if d > 0 and t >= 2.0**, the same bar as the earlier studies. This is a fixed directional threshold that
treats days as independent, not a calibrated one-sided 5% test; serial dependence could make a nominal pass more
likely, which the bootstrap interval helps judge. If n_a or n_d is below 30, or se is 0, H1 is "not evaluable",
which counts as not passed.

**Secondary (H2, H3; reported, decide nothing).** H2: among classified days, the number that agree, exact binomial
test against 1/2, upper tail. H3: among classified, outcome-eligible days, the number with sign(D) x y > 0, exact
binomial against 1/2, upper tail. A test with no eligible days gets p = 1 and is reported as not evaluable. Holm
over this fixed family of two: order by p (ties: H2 first); the first must be <= 0.025, and only then is the second
compared with <= 0.05.

**Robustness (reported; none can change the H1 verdict):**
1. **Block bootstrap of d** (the interval reported with d). Classification and outcome eligibility are fixed first.
   Over the sequence of all 1,446 keep-set days, draw block starts independently and uniformly, with replacement,
   from all starts that fit (no wrap-around), take 20 consecutive days per block until 1,446 days are reached,
   then truncate. A day drawn twice counts twice. Recompute d from the drawn classified, outcome-eligible days.
   10,000 attempted draws with NumPy `default_rng(20261111)`; draws with a group below 30 are dropped and counted.
   Percentiles 2.5 and 97.5 by NumPy's default linear interpolation; if fewer than 9,000 draws remain, the
   interval is reported as unreliable.
2. **Information at entry.** The latest closing-imbalance record with `ts_recv` in [15:50:00.000, 15:51:00.000)
   (ties: last in file order) instead of the earliest; same usability rules, no carrying forward.
3. **By venue.** D from NYSE stocks only, and from Nasdaq stocks only, each with the same 10-stock coverage rule.
4. **Signed move.** Mean of s x y (in basis points) on agreeing minus disagreeing days, Welch t.
5. **Option P&L.** On the 585 priced trades (section 4) that fall on classified days: mean `pnl_fee_0.09` on
   agreeing and disagreeing days and the difference, Welch t. Not evaluable if a group has fewer than 2 trades or
   zero variance.
6. **Adjusted for year and direction.** Within each year x signal-direction cell (12 cells), the difference in hit
   rates; cells lacking either group are dropped; average weighted by n_a x n_d / (n_a + n_d). Reported with the
   number of cells used.

**Descriptive only (no test).** Agreeing, disagreeing and unclassified days by year, with hit rates, Wilson 95%
intervals and mean s x y; records per stock and day by venue; the time of the first record after 15:50:00; usable
and unusable records by reason; days lost to coverage.

## 8. What has already been seen

- **Outcomes seen before this plan** (nominal holdout results; the rule was chosen on 2013-2020): on these 644
  days the rule was right 57.5% of the time, with an average move of 1.82 index points in the signal's direction,
  and the 585 priced option trades made +$67.46 a trade at the ask (t 2.40), with breakdowns by year, strike, body
  band, real-index and SPY candles in later studies.
- **Read for this plan.** `prelock_counts.py` loads the whole candle panel through `load_panel` but uses only the
  15:50 bar to list signal days and directions; it computes no outcome. Reading the trade list parsed whole rows,
  but only these columns were used: date, config, period, and (for the 585/586 check) status, cell, kind,
  entry_minute and whether the ask was blank. No P&L column was used.
- **Free Databento metadata** (record counts, cost quotes and symbology only, no record contents): all symbols,
  current S&P 500 members and 50 large stocks, on 2019-06-14, 2021-06-15, 2023-06-14 and 2026-10-14; per-window
  counts for four stocks on 2023-06-14; per-stock counts for six symbols on 2023-06-14 and 2026-10-14; for
  `assign_venues.py`, NYSE record counts (15:50-16:00) for each list stock on the first and last signal day of each
  year and on the days of each binary search (saved in `venue_counts.json`); the exact quotes in
  `quote_manifest.json`. A count says whether NYSE published records for a stock, not what they said.
- **Seen, outside the sample:** the contents of the two format-sample days, 2020-12-30 and 2026-11-06 (section
  2a), read for field codes, timing and coverage only; no candle, return or agreement was computed on them.
- **Not seen:** any imbalance record's contents within 2021-01-04 .. 2026-10-20.

## 9. Power

These are approximations that treat days as independent and ignore coverage and outcome exclusions; fewer
classified days or serial dependence lower the power. If 60% of about 640 classified days agree (n_a = 384,
n_d = 256) and hit rates are near 0.55, se(d) is about 4.0 points, so 80% power at the t >= 2 bar needs a true d of
about 11.4 points. With 75% agreeing, about 12.9 points. For scale: if disagreeing days were at 50% and 60% agreed,
the overall 57.5% would imply d of about 12.5 points. **The test can detect a large concentration of the edge, not
a modest one, and a failure may reflect limited power.**

## 10. Cost and budget

- **Exact quote** (pre-lock check 4, free; `quote_all.py`, saved in `quote_manifest.json`): 1,288 requests (644
  days x 2 exchanges, each stock from its listing exchange), **$17.34** in all ($10.38 NYSE, $6.96 Nasdaq; $2.49 to
  $3.12 a year). All S&P 500 members would have cost about $155, over the budget.
- Spend so far (`data/spx_1549/databento/spend_log.csv`, quoted costs, including the $0.0556 format samples):
  $93.58 of the author's $120 cap. Quote plus logged spend = $110.92, under the $119 limit, so **N = 50** stands
  (no cut). N, the lists, `venues.csv` and `quote_manifest.json` are frozen at the lock; the pull requests exactly
  the manifest's symbols.
- **Download safeguards** (new code; the older helper is not reused for paid requests). Each request is priced
  with a dataset-specific free `metadata.get_cost`. Before sending, a reservation row with the quoted cost is
  appended to `spend_log.csv` and flushed to disk; the request is refused if it would take the logged total past
  $120. A paid request is never retried automatically: a failure keeps its reservation (it may have been billed),
  and the day is retried only on a later run with a new reservation. Successful downloads are recorded with row
  counts and SHA-256 in the download manifest, not as second spend rows.
- **Incomplete downloads.** If a signal day still lacks either dataset's file after three attempts, it is
  unclassified, counted and listed; the analysis never runs on a silently partial sample.

## 11. How it runs

- Code in `backtests/spx_candle_imbalance/imbalance.py`, importing `scan.py`'s loader unchanged and the key loader
  of `tools/databento_spxw.py` (hashes checked at start-up with the plan's and the data files').
- `selftest` on synthetic data runs first: side and sign handling; the two undefined sentinels, blanks and
  non-positive prices; first and last records at the 15:50:00 and 15:51:00 edges and ties; both-venue duplicates;
  exact integer cancellation; coverage and classification; d and se against a direct computation; the Holm step;
  the bootstrap's multiplicity and dropped draws; the not-evaluable paths; the reservation-before-request order.
- `pull` downloads the signal days only after checking that the locked plan's SHA-256 matches the ledger.
- `run`: one registered run; a second run is refused unless a documented defect requires it, and earlier outputs
  are kept.
- Codex (read-only) reviews the code before the pull and the run; every defect it finds is fixed first.
- Outputs: `results.json`, `RESULTS.md`, `agreement_days.csv` (date, s, D, usable stocks, agreement; no outcome
  column).

## 12. Out of scope

Non-signal days, any trading rule or change to the live alert, data after 2026-10-20, the size of imbalances as a
predictor, and the 2019 rule-change question (the companion plan). Research only; not investment advice.

## Pre-lock checks

Done on 2026-11-10:
1. ~~SPY holdings files~~: downloaded from EDGAR with the author's name and email as the SEC asks (author's OK:
   "Use my name and email"; the contact string is kept outside the repository), `fetch_nport.py`; six complete
   files, fund and report dates checked, hashes in `data/spx_1549/spy_nport/manifest.json`.
2. ~~Format samples~~: section 2a ($0.0556).
3. ~~Symbology, renames, listing exchange~~: section 5 (`check_symbology.py`, `assign_venues.py`).
4. ~~Exact cost quote~~: section 10 ($17.34; N = 50).

At the lock:
5. **True spend:** not reported by the user before the lock. The pull's hard stop uses the logged spend
   ($93.58 + $17.34 = $110.92 against the $120 cap); the possible under-count from the older SPXW pull is disclosed.
6. **Thresholds:** accepted as drafted (H1: d > 0 and t >= 2.0; 10-stock coverage; 30-day groups).
7. **Lock:** this file and the frozen files below are in `preregistration/LEDGER.md`.

## Lock record (SHA-256 at the lock)

| File | SHA-256 |
|---|---|
| `backtests/spx_candle_scan/scan.py` | `558fff90f3e7af6c657c69a6df6ae7151576580440bf20adfa2be73044090584` |
| `data/spx_1549/d1_usa500_rth_1m.csv.gz` | `6e8219764151bbb1f761723ddbc291b66daab31472d5c37793f9f220f4153459` |
| `data/spx_1549/d1_days.csv` | `9c013d8a1602c88a2421374fa2ce1c836d71dc87efeb8b6c95a38ddacca04cd9` |
| `data/spx_1549/databento/realprice_trades.csv` | `1950e61f6230999127e5ec4315d51bb26dfc93392425a250f1ab9c9eb0a00df2` |
| `tools/databento_spxw.py` (key loader and API helper only) | `bcdcb3b2076d63112b3e678b62478623bf1fed109361eb75ee3af8f0a4620780` |
| `backtests/spx_candle_imbalance/signal_days.csv` | `099a9bd124512f06f3f9329fdff9ceb71d516467bdb714252b7d40b837834a7b` |
| `backtests/spx_candle_imbalance/stock_lists_raw.csv` | `3ff27c72c2d793dcc6237453c857912faf6964db041445fee76e1dbf78ea7bc8` |
| `backtests/spx_candle_imbalance/stock_lists.json` | `d9ed1099f793a16ce7a681385267eb025c7991a40e9fa61d6ff99dd731f4e70c` |
| `backtests/spx_candle_imbalance/isin_tickers.csv` | `e4ca4674044aaa201177e28ec2a2be406a0ff752f48391c5d6be89c71af54d6e` |
| `backtests/spx_candle_imbalance/venues.csv` | `9dd2594e2d12ce859fd7f4372585ee12290c6218f6184dad2b0994f0013f746e` |
| `backtests/spx_candle_imbalance/quote_manifest.json` | `64bcb9b0d8b904a7db847441242036cde8ccab379ce4cf934a420e482050e666` |
| `data/spx_1549/spy_nport/manifest.json` (hashes of the six filings) | `5ae37dd9e20e6f6b9b5258f4f1403e3d2e96f13eddb1da0e0b61e4935f6969a9` |
