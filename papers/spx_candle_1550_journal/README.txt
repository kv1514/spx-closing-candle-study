The 15:50 Candle: journal version
=================================

A shorter manuscript cut from the working paper in
../spx_candle_1550/ (10 November 2026). The working paper (43 pages)
stays the full record and serves as the Internet Appendix this
version cites. 15 pages, about 8,500 words against about 19,500;
10 tables and 1 figure.

Layout (10 November 2026, later the same day): the standard LaTeX
article format, with the title, abstract and introduction on page 1,
Latin Modern type at 11 pt, single spacing, numbered sections (1, 1.1),
tables placed where they fit, and every full page ending on the same
line. Only the preamble and title block changed; no word of the text.

Files
  main.tex         the source (bibliography inline; no bibtex pass)
  main.pdf         with the author's name
  main_blind.pdf   the same with the name removed, for double-blind
                   review (set \blindtrue on line 10 of main.tex)
  figures/         cumulative.csv and by_year.csv, copied from the
                   working paper for Figure 1
  ../spx_candle_1550_journal_overleaf.zip
                   main.tex, this README and figures/ for Overleaf
                   (New Project -> Upload Project); checked to build
                   to the same text as main.pdf

Build: it compiles as-is with tectonic or XeLaTeX/pdfLaTeX, e.g.
  tectonic main.tex

What changed from the working paper
  Kept: the scan, the real-price confirmation, the spread, the
  strike table, the order-style and late-entry tables, the
  pre-registered studies table, and one figure (the running total,
  yearly totals and spread).
  New table 9: the index-candle and SPY-candle registered lines side
  by side with the confirmation, plus the three-candle breakdown.
  Every row is copied from the working paper's tables; the first row
  joins Table 4 with the mid price from the spread table.
  Summarised in prose (full detail in the working paper): the model
  strike ladder and exits, re-tuning, the threshold analysis, the
  momentum and gamma study, XSP and SPY contracts, the re-validation,
  forward evidence.
  Dropped: the model calibration appendix, the additional tables,
  the "rule now in use" paragraph about the live alert.
  New prose: Section VIII "Why 15:50?", a hypothesis (not tested)
  tying the signal to the closing-auction imbalance published at
  15:50; a 0DTE and closing-auction literature paragraph; a short
  abstract (about 150 words); a data statement at the end.

Checks
  Every number in main.tex was checked by script against the working
  paper's main.tex. The only numbers not found there are
  bibliographic (SSRN ids 4404704 and 4692190, article 100852) and
  the SEC release numbers 34-85021, 34-84454 and 34-87179, which come
  from the sources below.
  Every table row was matched to the working paper's rows.

Sources for the new facts and citations (checked on 10 November 2026)
  NYSE MOC/LOC cut-off and regulatory imbalance at 15:50: NYSE fact
    sheets "NYSE Opening and Closing Auctions" and "NYSE Auctions
    Closing Process"; cut-off and publication moved from 15:45 to
    15:50 on 1 April 2019 (NYSE notice "MOC/LOC Cutoff Time Change";
    SEC Release 34-85021, 31 January 2019).
  Nasdaq: cut-off and the start of the Net Order Imbalance Indicator
    moved from 15:50 to 15:55 in Q4 2018 (SEC Release 34-84454,
    SR-NASDAQ-2018-068, approved October 2018); an abbreviated Early
    Order Imbalance Indicator from 15:50 was added later, scheduled
    for Q4 2019 (Releases 34-85292 and 34-87179). Nasdaq Closing
    Cross FAQ; Nasdaq article "Automation and information produce
    efficient price discovery in Nasdaq's auction process".
  Bogousslavsky and Muravyev (2023), Journal of Financial Markets 66,
    100852 (RePEc listing).
  Beckmeyer, Branger and Gayda (2023), SSRN 4404704.
  Dim, Eraker and Vilkov (2024), SSRN 4692190 (year from the SSRN id;
    confirm on SSRN before submission).

Before submitting
  - Pick the journal and apply its format (spacing, abstract length,
    blind copy, separate title page).
  - Open the three new citations and confirm the exchange facts in
    the current NYSE and Nasdaq rulebooks.

Research, not a trading recommendation.
