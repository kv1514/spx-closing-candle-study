# Pre-registration draft: the 15:50 candle on cheaper contracts (XSP and SPY 0DTE options, real prices)

**Status: DRAFT, not locked.**
- Drafted 2026-11-09 by Claude (a subagent) at the user's request, relayed from the main session.
- Revised after one read-only Codex review: 12 points (8 major, 4 minor), all addressed. See "Review log".
- Then, at the user's request, the XSP trade-bar fill check and the spend disclosure were added. Codex has not
  reviewed those two additions.
- To lock, the user copies this file to `preregistration/spx_candle_mini.md` and adds its SHA-256 to
  `preregistration/LEDGER.md`. Until then nothing here binds, and no analysis code for it exists.
- At drafting, no option price, implied spot, spread or P&L had been computed from any XSP or SPY quote. See
  "What was known".

Addendum to `spx_close_candle_scan.md` and `spx_candle_realprice.md`. XSP is the one primary test. SPY gets a
separate, secondary verdict line. Everything else is descriptive. Research only. Nothing here is a trading
recommendation.

## The question

The 15:50 rule was confirmed at real SPXW asks on 2021-2026: +$67.46 a trade, 585 trades, Newey-West t 2.40 on
the per-day series. One SPXW contract 10 points in the money costs about $1,100. That is too much for a $500
account. Two cheaper contracts follow the same index:

- **XSP (Mini-SPX), the primary question.** One tenth of SPX. Cash-settled, European, with same-day expiries.
  It settles to the official SPX close divided by 10. An XSP option 1 point in the money is close to the SPX
  trade at one tenth of the size: about $110.
- **SPY, the secondary question.** An ETF that tracks SPX at about one tenth. Its options are American and
  settle in shares. An ITM SPY option held to expiry turns into 100 shares (a long or a short position worth
  about $75,000 today), so a small account must sell it before the close. The realistic SPY trade therefore
  sells at the bid before 16:00.

**What this measures.** Both contracts follow the same index as SPXW, so the index side of every trade is
already known (see "What was known"). The test measures the net result of the analogous contract, one
contract at a time, at real quotes. That net result mixes:
- the contract's own bid-ask spread (the main expected difference);
- the fee, which does not shrink with the contract;
- the strike grid: XSP and SPY strikes are $1 apart, ten SPX points, against the SPX study's five, so
  "1 in the money" lies 5 to 15 SPX points in the money instead of 7.5 to 12.5;
- the contract's own implied spot and pricing;
- for SPY, its tracking of SPX, dividends, American exercise and, in version (b), giving up the last minute.

It is a fixed one-contract price study. It does not simulate a $500 account (see the affordability series under
"Descriptive"), and it is not a fresh test of the signal.

## What was known when this was drafted (disclosed so the rules can be judged)

**The SPX outcomes are fully known.** XSP settles to the official SPX close / 10. Every 2021-2026 signal day's
SPX move, settlement and SPXW result has been computed and read. SPY's own daily closes were also looked at
(below); SPY's intraday path and option prices were not.

**Known results that touch 2021-2026:**
- **Candle scan** (`backtests/spx_candle_scan/`, `holdout.json`): F2 (15:50, body ≥ 0.60, with) on 2021-2026:
  644 trades, the sign right 57.45% of the time, mean |move| 15:51-15:59 of 8.60 points at level 7,709.58.
- **Strike ladder** (`backtests/spx_candle_strikes/`, model prices): deep in the money held up best; ITM10
  made +$166 a trade in the model on 2021-2026 (644 trades).
- **Real SPXW prices** (`backtests/spx_candle_realprice/`, the study this one mirrors), ITM10 at the 15:51 ask,
  settled at the official close, $0.09 fee:
  - +$29.87 a day (t 2.40) over 1,321 days, 585 trades, +$67.46 a trade, 54% won, median +$44.91, worst
    −$2,210.09; 1 more signal day had no usable quote;
  - by year, per trade: 2021 +$175 (67), 2022 +$71 (90), 2023 +$4 (113), 2024 +$20 (106), 2025 +$65 (117),
    2026 +$121 (92); 2021-2022 +$115.46 (t 2.01), 2023-2026 +$49.85 (t 1.56);
  - at the mid +$105.90 a trade; with a $0.74 fee +$66.81;
  - every strike from ITM20 to OTM20 (ITM20 +$77, ITM5 +$54, ATM +$40, OTM5 +$12, OTM10-20 about $0 or less);
  - mean ITM10 ask 10.89 points (about $1,089) and a typical full spread of about $0.60 a share (2026: $0.40);
  - the fill check on trade bars: 99% of 2021-2026 entries traded in the 15:51 minute, 95% at or below the ask.
- **Fills** (`backtests/spx_candle_fills/`, descriptive): a limit at the mid did not beat paying the ask (+$65
  against +$67 a signal day); entering later cost money (15:52 ask +$56, 15:55 ask +$23).
- **Exits** (`backtests/spx_candle_exits/`): no stop or target beat holding in the model. **Selling at a fixed
  minute at real SPXW bids** (descriptive, 585 trades): every minute 15:52-15:59 lost against holding. **Selling
  at the 15:59 bid averaged −$38 a trade, −$105 against holding (t −7.8), 44% won.** This is the SPX analogue of
  SPY version (b) below, so version (b) is expected to do badly.
- **Exit timing** (`backtests/spx_candle_exit_timing/PREREG_DRAFT.md`): a draft only; nothing computed.
- **Re-tuning** (`backtests/spx_candle_refine/`): nothing beat 15:50 / 0.60 / ITM10 on 2021-2023 (best 80% /
  ITM20, luck p 0.21); on 2024-2026 the current rule made +$30 a day (t 1.64), +$66 a trade (315 trades).
- **Momentum and dealer gamma** (`backtests/spx_intraday_momentum/`): no filter helped; at real asks,
  short-gamma days made +$58 a trade against +$74 on other days.
- **Forward days** (`data/spx_1549/forward/`, 2026-10-21 .. 2026-11-06): the signals and their SPXW outcomes
  are known. They are outside 2021-2026.

**What was seen of XSP and SPY:**
- **Cost only.** Databento's free `metadata.get_cost` priced `cbbo-1m` 15:00-16:01 ET at about $0.0003 a day
  for 34 XSP symbols and $0.0004 a day for 42 SPY symbols, and `ohlcv-1m` (trade bars): XSP about $7.38 for all
  days; SPY, centre ± 3 strikes on the 586 F2 signal days, about $60.92 for 15:00-16:01 and about $2.15 for the
  15:51 and 15:59 minutes alone. It returns no prices.
- **Spend** (the shared log `data/spx_1549/databento/spend_log.csv`, every schema; the user raised the cap from
  $100 to $120 of the $125 free credit): $84.29 logged before these downloads; XSP quotes +$0.42; SPY quotes
  +$0.55; XSP trade bars +$8.26 (including 5 days fetched twice where two download processes met, and a $0.002
  conservative row for a stopped process). Total logged after: **$93.52**. SPY trade bars were not pulled.
- **The download.** `tools/databento_mini.py` saved the quote files described under "Data". Its `status`
  command decompressed and parsed every saved file. It checked the header, that every symbol has the right root
  and that day's expiry, and that a 15:51:00 row exists, and it counted the distinct symbols per file. The price
  fields were present in the parsed rows but were not converted, analysed or displayed. No implied spot, spread
  or P&L was computed. Everything `status` printed is under "Data" (the day table and "Thin or empty files").
  To find the five thin XSP files and the empty one, a one-off check listed each XSP file's row count and
  distinct symbols; nothing else was read. The same `status` check was run on the XSP trade bars (below).
- **XSP trade bars.** `status` on `data/spx_1549/databento/ohlcv-1m_1500-1601_xsp_k8/`: 1,283 files and 163
  "no symbol resolved" days, the same days as the XSP quotes; no day missing; no format problem. Files hold 3 to
  34 distinct symbols (a bar exists only for a contract that traded). The 2026-03-16 file has bars, although
  that day's quote file is empty.
- **SPY daily closes** (Yahoo; see "Data"). Only one check was run on them: the ratio SPY close / official SPX
  close stayed between 0.0991 and 0.1005 on 2020-12-01 .. 2026-10-20, the highest on 2025-04-09 (0.10054).
  That day first broke the downloader's sanity bound of 0.1005, which was then widened to 0.102. The check
  interval in this plan (0.098 .. 0.101) was chosen after seeing that range.
- **General knowledge.** XSP and SPY options are commonly quoted in pennies and nickels. The drafter had no
  measured XSP or SPY spread for these strikes and minutes.

## Data

- **Signal panel:** the D1 one-minute panel (`scan.load_panel`), the same panel the SPX confirmation used. Its
  days are D1's `keep` set (`data/spx_1549/d1_days.csv`): full sessions with no missing D1 bar from 15:19 to
  15:59. **This eligibility uses bars after the 15:51 entry.** It is a data-quality restriction inherited from
  the SPX studies and kept here so the samples match; the results are conditional on it.
- **XSP quotes:** `data/spx_1549/databento/cbbo-1m_1500-1601_xsp_k8/`. OPRA `cbbo-1m`, 15:00-16:01 ET. The
  contracts expiring that day at strikes c − 8 .. c + 8 in $1 steps, calls and puts (34 symbols), with
  c = floor(S / 10 + 0.5) and S = D1's 15:51 open. A `<day>.none` marker means **none of the requested symbols
  resolved** at Databento. That is almost surely a day with no XSP expiry, but the marker cannot rule out a
  symbol or coverage problem, so it is reported as "no requested symbol resolved".
- **SPY quotes:** `data/spx_1549/databento/cbbo-1m_1500-1601_spy_k10/`. The same, with strikes c − 10 .. c + 10
  (42 symbols) and c = floor(S × r + 0.5), where r = SPY close / official SPX close on the previous session.
- **Quote rows:** parsed as `realprice.py`'s `parse_quotes` does, with the root as a parameter (see "Code"). A
  row whose `ts_recv` is exactly HH:MM:00.000000000 ET on that day is the consolidated best bid and offer at
  that instant, the open of minute HH:MM. So "the 15:51 ask" is the ask in the 15:51:00 row, and "the 15:59
  bid" is the bid in the 15:59:00 row. Rows off the minute, or for another expiry, are ignored. If one contract
  has two rows at the same instant, the later row in the file wins (as in `parse_quotes`). A **valid quote** has
  ask > 0 and 0 ≤ bid ≤ ask.
- **SPX settlement:** Cboe's official SPX close in `data/spx_1549/spx_official_closes_cboe.csv`, the same file
  and the same check as the SPX study: before any option is priced, it must agree with the Robinhood closes in
  `data/spx_1549/live_*/spx_daily.json` within 0.01 on every overlapping day (at least 3), or the run stops.
- **SPY close:** `data/spx_1549/spy_daily_closes.csv`, fetched once by `tools/databento_mini.py closes` from
  Yahoo's chart API: the raw daily close, split-adjusted only, not dividend-adjusted (SPY has not split), so
  ex-dividend drops stay in the prices. No other source is used. It is a stand-in for the official closing
  price; it was not checked against the price used for exercise. Before any option is priced, every day in
  the SPY sample must have a close in this file and SPY close / official SPX close must lie in 0.098 .. 0.101,
  or the run stops.
- **Days:** the D1 days 2021-01-04 .. 2026-10-20. A day enters a root's sample only if it has that root's quote
  file (not `.none`) and an official SPX close. If any of these D1 days has neither a file nor a `.none` marker
  for a root, that root's download is incomplete and the run stops. Days by year (from `status`):

  | Year | D1 days | XSP file | XSP no symbol resolved | SPY file | SPY no symbol resolved |
  |---|---|---|---|---|---|
  | 2021 | 251 | 158 | 93 | 156 | 95 |
  | 2022 | 250 | 180 | 70 | 169 | 81 |
  | 2023 | 248 | 248 | 0 | 248 | 0 |
  | 2024 | 249 | 249 | 0 | 249 | 0 |
  | 2025 | 247 | 247 | 0 | 247 | 0 |
  | 2026 (to 10-20) | 201 | 201 | 0 | 201 | 0 |
  | **All** | **1,446** | **1,283** | **163** | **1,270** | **176** |

  Every "no symbol resolved" day is a Tuesday or a Thursday (XSP 78 and 85, SPY 86 and 90), all in 2021-2022,
  as expected before daily expiries. No day is missing. For comparison, the SPX confirmation had 1,322 days
  with an SPXW file in 2021-01-01 .. 2026-10-20.
- **Thin or empty files.** One XSP file has no rows: 2026-03-16 (a Monday). Databento resolved the symbols
  but quoted $0 and returned only the header, twice. It stays a file day: a signal that day counts as "no
  spot". 1,252 XSP files have all 34 symbols, and 30 have fewer (6 to 32; under 20 on 2021-07-23, 2021-08-31,
  2021-11-24, 2022-09-16 and 2022-10-25). 1,231 SPY files have all 42 symbols, and 39 have 26 to 40. A strike
  without rows counts as "no quote" if a trade needs it.

## The signal

Exactly the SPX study's current rule, F2. On the D1 15:50 one-minute candle, body = close − open and range =
high − low. The signal fires when range > 0 and |body| ≥ 0.60 × range. Its sign is sign(body): +1 buys a call,
−1 buys a put (with the candle). A missing bar gives no value that day.

Two checks, each stopping the run if it fails:
1. The signal equals `scan.py`'s F2 on every kept day.
2. On every day that is in both this study and the SPX confirmation trade list
   (`data/spx_1549/databento/realprice_trades.csv`, config `current`, period `confirmation`), the signal has
   the same sign.

## XSP, the primary test

- **Implied spot.** At 15:51 (the 15:51:00 row), take the strikes where both the call and the put have a valid
  quote with a bid above 0. Pick the 3 strikes where the call mid and the put mid are closest. The implied XSP
  spot S_x = the median of K + call mid − put mid over those 3 (`realprice.py`'s `implied_spot`, unchanged).
  ATM = floor(S_x + 0.5), the nearest $1.
- **No implied spot.** If fewer than 3 strikes qualify, the trade is **not priced**. That day is missing from
  the per-day series and is counted as "no spot". There is no fallback in the test.
- **Strike: ITM1.** An up signal buys the call at ATM − 1. A down signal buys the put at ATM + 1. One XSP point
  is ten SPX points, so this is the analogue of the SPX rule's ITM10.
- **No quote.** If that contract has no valid quote at 15:51 (including a strike outside the downloaded band),
  the trade is not priced and is counted as "no quote".
- **Price and P&L.** Buy at the 15:51 ask and hold to settlement. P&L per contract =
  100 × (intrinsic value at X − ask) − $0.09.
- **Settlement value X.** X = official SPX close / 10, not rounded. XSP's standard and weekly contracts are
  PM-settled to one tenth of the SPX close. **The exact precision and rounding of the published XSP exercise
  settlement value was not verified** (no network access at review), so X is this plan's fixed rule and a
  proxy for the published value. Rounding to the cent changes a contract's value by at most $0.50. A contract
  quoted at 15:51 on its expiry day is trading that afternoon, so it is PM-settled (an AM-settled contract
  stops trading the day before).

### Per-day series

As in the SPX study: on each XSP-sample day, the trade's P&L on a priced signal day, 0 on a day with no
signal, and missing if the candle was missing or the trade was not priced. "Mean per day" is the average over
the non-missing days.

### The criterion (the one primary test)

**XSP is confirmed** only if its per-day series on 2021-01-01 .. 2026-10-20 has a mean > 0 with Newey-West
t ≥ 2.0 (lag 5, Bartlett weights 1 − j/6; `realprice.py`'s `nw`). A t that cannot be computed (fewer than 8
days, or a zero standard error) does not pass. Otherwise the result is "not confirmed on XSP at real prices".

## SPY, the secondary test (its own verdict line)

- **Implied spot and strike.** The same method on SPY's 15:51:00 quotes gives S_y. ATM = floor(S_y + 0.5).
  ITM1: an up signal buys the call at ATM − 1, a down signal the put at ATM + 1. SPY options are American, so
  put-call parity is only approximate. It is used only to pick the strike. No implied spot or no quote: not
  priced, counted, as for XSP.
- **Entry.** Buy at the 15:51 ask.
- **Version (b), the realistic one. It carries SPY's verdict.** Sell at the 15:59 bid. P&L per contract =
  100 × (15:59 bid − 15:51 ask) − 2 × $0.09 (the fee on both sides). A valid quote with a bid of 0 is valued
  as an exit at 0; that is an assumption, not a shown sale. If the contract has no valid quote at 15:59, the
  trade is not priced for (b) and is counted as "no exit quote". The 15:59 exit is this plan's choice, not a
  claim about the last trading time of expiring SPY options.
- **Version (a), descriptive.** A hypothetical value at the close: P&L per contract =
  100 × (intrinsic value at X_y − ask) − $0.09, where X_y is Yahoo's unadjusted SPY close for that day. It
  assumes the shares a call delivers (or the short a put creates) are sold or covered at exactly X_y. It
  ignores exercise processing, exercise fees, after-hours moves and the cash needed to take the position, which
  a small account does not have.
- **SPY verdict.** Version (b)'s per-day series is built as for XSP, on SPY-sample days. **SPY is confirmed
  (selling at the 15:59 bid)** only if its mean on 2021-01-01 .. 2026-10-20 is > 0 with Newey-West t ≥ 2.0
  (lag 5); a t that cannot be computed does not pass. Otherwise "not confirmed on SPY at real prices". Because
  trades without a 15:59 quote are left out, the verdict is conditional on the exits that were quoted. The
  worst-case version under "Descriptive" shows how much that matters. Version (a) gets the same statistics and
  decides nothing.

**XSP is the sole primary test.** SPY's verdict uses the same, unadjusted bar. Neither result supports a claim
that "at least one cheaper contract works". Both verdicts are always reported, whatever they are. Neither
changes the SPX result.

## Descriptive (decides nothing)

Each item is a separate change from the base case (ITM1, bought at the ask, $0.09). They are not crossed with
each other unless stated. None of them enters a verdict. Each is computed for XSP, SPY (b) and SPY (a) on
2021-01-01 .. 2026-10-20, with the same per-day construction (0 on no-signal days, missing on unpriced days).
1. **Other strikes**, at the ask, $0.09: ATM (call and put at ATM) and ITM2 (call at ATM − 2, put at ATM + 2).
2. **Mid price**, ITM1: buy at the 15:51 mid instead of the ask; for SPY (b) also sell at the 15:59 mid. The
   fee convention stays: $0.09 once for XSP and SPY (a), $0.09 on each side for SPY (b).
3. **Higher fee**, ITM1, at the ask: $0.74 a contract instead of $0.09 (on each side for SPY (b)). These are the
   SPX study's two fee levels, and both are assumptions, not a verified broker tariff. For SPY, which pays no
   index-option fee, $0.74 is a stress case.
4. **By year**, base case: 2021, 2022, 2023, 2024, 2025 and 2026 (to 2026-10-20), and 2021-2022 and 2023-2026.
   Each slice is computed on its own days (Newey-West within the slice): days, mean per day, t, trades, mean per
   trade, share won, median and worst trade.
5. **Spread as a share of the premium**, base case: for each priced entry, (ask − bid) / mid at 15:51 for the
   contract bought; mean and median, overall and by year. The same for SPX ITM10 on the same days, from
   `realprice_trades.csv` as 2 × (ask − mid) / mid. For SPY (b), also the 15:59 spread share of the contract
   sold.
6. **Return per dollar of premium**, base case: the sum of P&L over the sum of 100 × ask, over priced trades.
   For XSP ITM1, SPY ITM1 (a) and (b), and SPX ITM10 (all 585 trades, and the days shared with each root). Also
   the mean premium (100 × ask). For scale, SPX ITM10 made +$67.46 on a mean premium of about $1,089.
7. **Affordability**, base case: the share of trades whose premium plus entry fee is at most $500, and an
   "affordable only" per-day series in which a trade costing more than that is skipped (0 that day) and every
   other day is unchanged. Even this does not simulate an account that shrinks after losses, or whether a
   broker accepts the order.
8. **Paired with SPX**, base case. This is an overall comparison of the two implementations, not an estimate
   of the spread cost. The SPX per-day series is rebuilt without repricing: its calendar is every D1 keep day in
   2021-01-01 .. 2026-10-20 that has a file in `data/spx_1549/databento/cbbo-1m_1500-1601_k60/` and an official
   close; on each such day the value is the `pnl_fee_0.09` of the `realprice_trades.csv` row (config `current`,
   period `confirmation`) if the signal fired, missing if that row is `not_priced` or the signal is missing, and
   0 if the signal is 0. Every calendar day with a signal must have a row, and the rebuilt series must
   reproduce the SPX confirmation (1,321 days, 585 trades, +$29.87 a day, t 2.40, to the cent and 0.01), or the
   run stops. Then, on the days in both samples, the per-day difference = root − SPX / 10 (missing if either is
   missing); mean and Newey-West t. Also before fees: on traded days the difference is
   (root P&L + its fees) − (SPX P&L + $0.09) / 10, and 0 on no-signal days. For SPY, both (a) and (b). SPY is
   about 0.0997 × SPX, not exactly SPX / 10; the scaling stays 1/10.
9. **No implied spot**, ITM1 only, shown separately: on days where the trade was not priced for lack of an
   implied spot, the same trade with ATM taken from D1 instead (XSP: floor(S / 10 + 0.5); SPY:
   floor(S × r + 0.5)); its count and P&L. It shows whether leaving those days out matters and never enters a
   verdict.
10. **SPY (b) worst case for missing exits**: the base series with every "no exit quote" trade charged the full
    premium plus both fees. Also the entry cohort: every priced SPY entry, with how many had a 15:59 quote, by
    year.
11. **Settlement rounding (XSP)**: the base series with X rounded half up to the cent.
12. **Counts**, by year and by root: D1 days; days with a file; days with no requested symbol resolved; days
    without an official close; signal days; missing candles; priced trades; unpriced trades by reason (no
    spot, no quote, no exit quote); days in each root's sample that are not in the SPX sample and the reverse,
    by weekday.

## Fill check on XSP trade bars (descriptive, decides nothing)

This mirrors Part 4 of the SPX real-price study. The ask in a quote file is only a price that was offered; this
part asks whether XSP actually traded near it.
- **Trade bars:** Databento OPRA `ohlcv-1m`, the same 34 symbols and the same 15:00-16:01 ET window as the XSP
  quotes, in `data/spx_1549/databento/ohlcv-1m_1500-1601_xsp_k8/`. A bar stamped HH:MM (`ts_event`, the bar's
  start) covers the trades in that minute. Bars are parsed as `realprice.py`'s `parse_bars` does, with the root
  as a parameter: contracts expiring that day only, and a row with a missing low, close or volume is skipped.
- **Entries:** every priced XSP entry of the base case (ITM1, 15:51 ask), on 2021-01-01 .. 2026-10-20, and
  separately on 2021-2022 and 2023-2026.
- **Reported:**
  - the entries with a bar file that day, and the number of such days;
  - the share of entries where the contract traded in the 15:51 minute (a bar with volume > 0);
  - among those, the share where the minute's lowest trade was at or below the 15:51 ask;
  - among those, the mean and median of (the minute's last trade − the 15:51 mid), per share;
  - the same four numbers for SPX ITM10 on the same days, read from `realprice_trades.csv`'s `bar_volume`,
    `bar_low` and `bar_close` columns (not recomputed).
- It uses the bar files that exist when the run starts and reports how many days had them. A file that does not
  parse is counted as unreadable. This part never stops the run and changes no decision.

**SPY has no fill check.** SPY trade bars were estimated, not pulled: the centre ± 3 strikes (14 symbols),
15:00-16:01 ET, on the 586 F2 signal days of the SPX confirmation came to about $60.92, which would take the
logged spend past the $120 cap.

**Forward days** (after 2026-10-20) are reported later in a separate table, once their XSP and SPY quotes are
downloaded with the same strike rule. The signal comes from the forward log
(`data/spx_1549/forward/candle_1550_log.csv`, rows `SPX_robinhood` with status `ok`), and S is that log's SPX
15:51 open. They are never pooled with 2021-2026 and decide nothing.

## What is reported

- **The two verdict lines:** XSP (confirmed or not) and SPY (b) (confirmed or not). For each: mean per day and
  t, days, trades, mean per trade, share won, median and worst trade, and 2021-2022 and 2023-2026 separately.
- **The descriptive tables above.**
- **The SPX ITM10 line for comparison**, rebuilt from `realprice_trades.csv`, not repriced.

## Text rules

- Say plainly that the SPX outcomes on 2021-2026 were already known (XSP is SPX / 10, and SPY tracks it). This
  measures the net result of the analogous contracts (mostly their spreads and fees, plus strike grid, pricing
  and, for SPY, tracking and exit time), not whether the signal works.
- Say it is a fixed one-contract price study, with assumed fees, and not a simulation of a $500 account.
- Say that signals come from D1, a CFD, on days chosen with bars after the entry, and that a fill at the quoted
  ask ignores size and fast minutes. XSP's quoted size can be small.
- For SPY, say that a broker may close an expiring position in a small account before 15:59, or refuse the
  order, and that this study cannot model that. The user should check the broker's rules.
- If XSP is confirmed, say it confirms the 15:50 rule at XSP's real asks, with known index outcomes. It is not
  a fresh test of the signal.
- Do not combine the two verdicts into one claim.
- No trading recommendation.

## Outputs and code

`backtests/spx_candle_mini/results.json`, `backtests/spx_candle_mini/RESULTS.md` and
`data/spx_1549/databento/mini_trades.csv` (every XSP and SPY entry at every reported strike and version, with its
status). They are rebuilt on each run by `backtests/spx_candle_mini/mini.py`.
- It reuses `scan.py`'s panel and `realprice.py`'s `on_minute_of_day`, `valid_quote`, `implied_spot`,
  `intrinsic`, `nw` and `check_gate` logic, imported, not copied.
- `realprice.py`'s `parse_symbol` accepts only the `SPXW` root, so `mini.py` has its own symbol and quote parser
  with the root as a parameter. It must keep `parse_quotes`' rules (same day, exact minute, validity, later row
  wins), and its self-test must show it gives the same result as `parse_quotes` on an SPXW file.
- ATM rounding to $1 is done separately: floor(S + 0.5).
- Like `realprice.py`'s `check_gate`, it refuses to read any option price unless
  `preregistration/spx_candle_mini.md` exists and its SHA-256 is in `preregistration/LEDGER.md`.

## Order of work

1. This draft.
2. One read-only Codex review; every substantive point fixed (done; see "Review log").
3. The user locks it: copies it to `preregistration/spx_candle_mini.md` and adds its SHA-256 to
   `preregistration/LEDGER.md`.
4. `mini.py` is written, with the gate.
5. `mini.py selftest` on synthetic files with XSP and SPY symbols: the parser against `parse_quotes`, parity,
   the $1 ATM, ITM1 for calls and puts, the 15:51 and 15:59 rows, settlement at SPX / 10, the SPY fee on both
   sides, the missing-quote counts, the SPX series rebuild, the XSP bar parser and fill check, the stop rules
   and the gate.
6. `mini.py run`, once. Its results are reported as they come out.

## Review log (Codex, read-only, 2026-11-09)

| # | Point | Fix |
|---|---|---|
| 1 | [major] "SPX close / 10, not rounded" was asserted as XSP's settlement without support. | Called a fixed rule and a proxy; the exchange's rounding is flagged as unverified; a rounded-to-the-cent version added (descriptive 11). |
| 2 | [major] A `.none` marker does not prove there was no expiry. | Relabelled "no requested symbol resolved"; counts by year and weekday against the SPX sample (descriptive 12). |
| 3 | [major] The inherited D1 keep set uses bars after 15:51. | Disclosed under "Data" and in the text rules; results stated as conditional on it; counts split by cause. |
| 4 | [major] SPY (b) drops entries whose 15:59 quote is missing, which is not known at entry. | Verdict labelled conditional on quoted exits; worst-case version and entry-cohort coverage added (descriptive 10); a zero bid is a valuation, not a sale. |
| 5 | [major] "Only spreads and fees" was wrong: the strike grid, pricing and tracking also differ. | "What this measures" rewritten; paired comparison called an overall implementation comparison. |
| 6 | [major] SPY (a) mixed intrinsic value with exercise proceeds; Yahoo's close is a proxy. | (a) renamed a hypothetical value at Yahoo's unadjusted close, with its assumptions; 15:59 stated as a choice, not the last trading time. |
| 7 | [major] The SPX per-day series cannot be read from the trade CSV alone; the before-fee formula added fees to no-trade days. | SPX calendar rebuilt from files, closes and signals; must reproduce the SPX confirmation or stop; fee add-back only on traded days (descriptive 8). |
| 8 | [minor] `parse_symbol` accepts only SPXW; the $1 step is not part of `implied_spot`. | Root-parameterized parser required, tested against `parse_quotes`; `implied_spot` reused unchanged; ATM rounding separate. |
| 9 | [minor] Descriptive variants and missing-data cases were underspecified. | Variants enumerated as separate perturbations; fee conventions for the mid case; missing SPY close stops the run; uncomputable t fails; slices recomputed within the slice. |
| 10 | [minor] The disclosure understated what `status` parsed and showed; the ratio interval was chosen after seeing the data. | Both disclosed under "What was seen". |
| 11 | [major] The verdict does not show the rule works in a $500 account. | Labelled a fixed one-contract price study; "affordable only" series added (descriptive 7); fees called assumptions. |
| 12 | [minor] Two verdicts invite a combined claim. | XSP stated as the sole primary test; no combined claim; both always reported. |

## Choices made at lock (2026-11-09, on the user's go-ahead: "ok run ur experiment and see if it worjs on xsp", "ok cool go")

1. **Fees:** $0.09 per contract is primary and $0.74 descriptive, mirroring the SPX study.
2. **SPY's verdict version:** (b), selling at the 15:59 bid.
3. **SPY trade bars:** not pulled. SPY has no fill check; the about-$2.15 two-minute option was not taken.
4. **Settlement precision:** the unrounded SPX close / 10 stays the base case; the rounded-to-the-cent version
   stays descriptive (descriptive 11).
