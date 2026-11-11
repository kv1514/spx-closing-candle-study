# The 15:50 Candle

**A pre-registered study of an end-of-day signal in same-day (0DTE) SPX options.**
Kausthubh Veldanda, November 2026.

- Paper: [`papers/spx_candle_1550_journal/main.pdf`](papers/spx_candle_1550_journal/main.pdf) (16 pages)
- Full working paper with every study: [`papers/spx_candle_1550/main.pdf`](papers/spx_candle_1550/main.pdf) (37 pages)

> Research only. Nothing here is investment advice, and no live trading results are claimed.

## The question

Does a one-minute candle near the close predict where the S&P 500 index (SPX) closes, and does that
prediction survive the real cost of trading same-day-expiry SPX options?

## What I found

- A scan of 41 candle features on 2013-2020 picked one: the **15:50 ET candle whose body is at least 60%
  of its range**. On the 2021-2026 holdout, traded in its own direction, it was right on 57.5% of 644 trades.
- At **real OPRA option quotes** (an SPXW option 10 points in the money, bought at the ask at 15:51 and held to
  settlement), it earned **$67 a trade (Newey-West t = 2.40)** over 2021-2026. That is about two-thirds of what
  a pricing model implied. It lost money before 2021, when bid-ask spreads were about five times wider.
- **Nothing improved it:** early exits, limit orders, intraday-momentum and dealer-gamma filters, and smaller
  contracts (XSP, SPY).
- **The data source matters.** The backtests read the candle from a CFD price feed. Read from the real SPX
  index candle instead, the rule made $39 a trade (t = 1.53) and **missed its criterion**. Read from the SPY
  candle, it made $72 (t = 2.35) and met a retrospective criterion. Since that was the third source tried on
  the same days, it is a lead, not a confirmation.
- A final search over 7,128 settings (candle minute, body cut, direction, strike) picked the 15:50 candle again,
  with a luck diagnostic of p = 0.051.
- **Is it the closing auction?** From 15:50 the NYSE and Nasdaq publish the imbalance of orders waiting
  for the closing auction. In a pre-registered test with those messages for SPY's 50 largest holdings, the
  candle pointed the same way as the summed imbalance on 72.8% of the 644 signal days, but it was **not more
  accurate** on those days (55.9% against 61.7%). That explanation was not confirmed, though the test could
  detect only a large difference.
- **Selling early at real bids** did not help either: 26 pre-registered trailing-stop, profit-lock and
  take-profit rules all earned less than holding to settlement on 2021-2023 ($9 to $120 a trade), so none
  went on to the 2024-2026 test.

**Conclusion:** the evidence supports a small edge that depends heavily on execution, not an established one.
Every test that failed is reported alongside the ones that passed.

## How it was done

- **Pre-registration.** Each confirmatory study was written up as a plan *before* the data it governs was read.
  The plan's SHA-256 hash and a UTC timestamp were appended to
  [`preregistration/LEDGER.md`](preregistration/LEDGER.md). Each study's code recomputes the hash at start-up
  and refuses to read real data unless it matches. Results that were not planned are labelled *descriptive*.
- **One run per plan.** The registered scripts refuse a second run. A rerun is allowed only for a documented
  defect, and it keeps the earlier outputs.
- **Statistics.** Newey-West t-statistics (5 lags) on daily P&L series, Holm corrections for multiple
  candidates, Welch tests for comparisons, and a circular-shift "luck" diagnostic for searches over many
  settings.

## What's in this repository

| Folder | Contents |
|---|---|
| `papers/spx_candle_1550_journal/` | The paper (LaTeX source, PDF, figure data) |
| `papers/spx_candle_1550/` | The full working paper and the commands that reproduce each study (`README.txt`) |
| `preregistration/` | The locked plans and the hash ledger |
| `backtests/spx_close_1549/` | First study: the 15:49 close and the data pipeline (CFD feed, validation) |
| `backtests/spx_candle_scan/` | The 41-feature candle scan (discovery 2013-2020, holdout 2021-2026) |
| `backtests/spx_candle_strikes/`, `spx_candle_exits/` | Strike choice and early-exit rules (pricing model) |
| `backtests/spx_candle_realprice/`, `spx_candle_fills/` | Real OPRA option prices; limit orders and late entries |
| `backtests/spx_candle_refine/`, `spx_intraday_momentum/` | Re-tuning on 2021-2023; momentum and dealer-gamma filters |
| `backtests/spx_candle_mini/` | XSP and SPY options at real quotes |
| `backtests/spx_candle_audit/` | A re-validation written from scratch (descriptive) |
| `backtests/spx_candle_realindex/`, `spx_candle_spy/` | The rule read from the real SPX index candle and from the SPY candle |
| `backtests/spx_candle_realsearch/` | The search over 7,128 closing-candle settings |
| `backtests/spx_candle_imbalance/` | The closing-auction imbalance test (NYSE and Nasdaq messages from 15:50) |
| `backtests/spx_candle_exit_timing/`, `spx_candle_exit_timing_v2/` | Real-time exit rules at real bids (the first plan stopped at its coverage gate; the second ran once) |
| `analysis/`, `tools/` | Forward logs, the data downloaders and the live 15:50 alert used to log new signals |

Each study folder has a `RESULTS.md` / `SUMMARY.md` and a machine-readable `results.json`.

## Data

The raw data is **not included**. It is licensed and cannot be redistributed. The studies used:

- Dukascopy US500 CFD one-minute bars (the candle in the original backtests)
- Databento OPRA quotes and trade bars for SPXW, XSP and SPY options, and SPXW open interest
- Cboe official SPX closes
- CNBC's archive of SPX index and SPY one-minute bars
- Databento closing-auction imbalance messages from the NYSE (XNYS.PILLAR) and Nasdaq (XNAS.ITCH),
  15:50-16:00 ET, for SPY's 50 largest holdings
- SEC N-PORT filings (SPY's holdings) and OpenFIGI (to map them to tickers), both public
- Robinhood option minute bars (seven days, used only to calibrate the early pricing model)

Trade-by-trade files that list individual option quotes are also left out for the same reason; the scripts that
write them are included.
The imbalance study's day file (`agreement_days.csv`) holds only each day's summed dollar imbalance, not
the exchange messages.

## Reproducing

Python 3.13 with `pip install -r requirements.txt`. The commands for every study are at the end of
[`papers/spx_candle_1550/README.txt`](papers/spx_candle_1550/README.txt). Downloading the option data needs
your own Databento API key; each request is priced first and refused past a spending cap.

The scripts are the versions that produced the results, apart from edits to a few comments; each result file
records the SHA-256 of the script version that ran. Some scripts still set `ROOT` to the original machine's
path; point it at your copy to run them. Many have a `selftest` mode that runs on synthetic data.

To check a plan against the ledger:

```bash
shasum -a 256 preregistration/spx_candle_spy.md
```

The ledger lists only this project's plans; the working repository's ledger also held unrelated studies.
That repository is private, and this one starts its own history, so the lock timestamps are as recorded
there. The plans are reproduced unedited, since editing them would change their hashes.
