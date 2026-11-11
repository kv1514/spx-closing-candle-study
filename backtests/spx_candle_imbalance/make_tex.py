"""Write the paper fragments for the closing-imbalance test from the result files (no hand-typed numbers).

Run from the repository root, after `imbalance.py run`:
  .venv/bin/python -I backtests/spx_candle_imbalance/make_tex.py
Writes
  papers/spx_candle_1550/imbalance_section_draft.tex          the working paper's section and its two tables
  papers/spx_candle_1550_journal/imbalance_section_draft.tex  the journal version's subsection and its table
Reads results.json and stock_lists.json (this folder), the locked plan (power figures) and LEDGER.md (lock time).
The verdict wording follows section 3 of the plan ("If H1 fails ...").
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "backtests/spx_candle_imbalance"
R = json.load(open(HERE / "results.json"))
LISTS = json.load(open(HERE / "stock_lists.json"))
PLAN = (ROOT / R["plan"]).read_text()
LEDGER = (ROOT / "preregistration/LEDGER.md").read_text()
OUT_WP = ROOT / "papers/spx_candle_1550/imbalance_section_draft.tex"
OUT_J = ROOT / "papers/spx_candle_1550_journal/imbalance_section_draft.tex"

H1 = R["H1_primary"]
H2 = R["secondary"]["H2"]
H3 = R["secondary"]["H3"]
HOLM = R["secondary"]["holm"]
RB = R["robustness"]
BOOT = RB["bootstrap_d"]
DESC = R["descriptive"]
YEARS = DESC["by_year"]

# ---- checks: the run is the registered one and the numbers hang together --------------------------------------
assert R["hash_gate"]["plan_sha256"] in LEDGER, "plan hash not in the ledger"
assert R["defect_rerun_reason"] is None, "this script describes the one registered run only"
assert H1["evaluable"] and BOOT["reliable"]
lock = re.search(r"^- (\d{4}-\d\d-\d\d)T(\d\d:\d\d):\d\dZ\s+" + R["hash_gate"]["plan_sha256"], LEDGER, re.M)
assert lock, "lock line not found"
LOCK = f"{lock.group(1)} {lock.group(2)} UTC"
n_days = sum(v["signal_days"] for v in YEARS.values())
n_cls = DESC["status_counts"].get("classified", 0)
assert n_cls == H2["classified"] == n_days, "the text below assumes every signal day was classified"
assert DESC["outcome_excluded_signal_days"] == 0
hits_a = sum(v["agree"]["hits"] for v in YEARS.values())
hits_d = sum(v["disagree"]["hits"] for v in YEARS.values())
assert sum(v["agree"]["n"] for v in YEARS.values()) == H1["n_agree"] == RB["signed_move_bps"]["n_a"]
assert sum(v["disagree"]["n"] for v in YEARS.values()) == H1["n_disagree"] == RB["signed_move_bps"]["n_b"]
assert abs(hits_a / H1["n_agree"] - H1["hit_agree"]) < 1e-12 and abs(hits_d / H1["n_disagree"] - H1["hit_disagree"]) < 1e-12
assert all(v["unclassified"]["n"] == 0 for v in YEARS.values())
usable = DESC["usable_stocks_per_day"]
assert usable["min"] == usable["median"] == 50

# power figures from section 9 of the plan
sec9 = PLAN.split("## 9. Power", 1)[1].split("## 10.", 1)[0]
pow_lo = float(re.search(r"needs a true d of\s+about ([\d.]+) points", sec9).group(1))
pow_hi = float(re.search(r"With 75% agreeing, about ([\d.]+) points", sec9).group(1))
POWER = f"about {round(pow_lo)} to {round(pow_hi)} points"

N_KEEP = int(re.search(r"the keep set: ([\d,]+) days", PLAN).group(1).replace(",", ""))

cover = [float(v["top50_pct_of_net_assets"]) for v in LISTS["years"].values()]
COVER = f"between {round(min(cover))}\\% and {round(max(cover))}\\%"
first = DESC["first_closing_record_after_15_50_seconds"]
FIRST_MED = max(v["median"] for v in first.values())
FIRST_MAX = max(v["max"] for v in first.values())
assert FIRST_MED < 0.15  # "a median of about 0.1 seconds" below

WORDS = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
dis_better = [y for y, v in YEARS.items() if v["disagree"]["hit_rate"] > v["agree"]["hit_rate"]]
agr_better = [y for y, v in YEARS.items() if v["agree"]["hit_rate"] > v["disagree"]["hit_rate"]]
assert len(dis_better) + len(agr_better) == len(YEARS)
BY_YEAR = (f"disagreeing days had the higher hit rate in {WORDS[len(dis_better)]} of the {WORDS[len(YEARS)]} years"
           + (f", all but {' and '.join(agr_better)}" if 0 < len(agr_better) <= 2 else ""))


# ---- formatting -------------------------------------------------------------------------------------------------
def num(n):
    return f"{n:,}".replace(",", "{,}")


def pct(x, n=1):
    return f"{100 * x:.{n}f}\\%"


def pts(x):
    """A difference of two proportions, in percentage points, signed."""
    v = round(100 * x, 1)
    return f"${'+' if v >= 0 else '-'}{abs(v):.1f}$"


def tv(x):
    return f"${'-' if x < 0 else ''}{abs(x):.2f}$"


def usd(x):
    return f"${'+' if x >= 0 else '-'}\\dollar{abs(x):,.2f}$".replace(",", "{,}")


def bp(x):
    return f"${'-' if x < 0 else ''}{abs(x):.2f}$"


def bp_signed(x):
    return f"${'+' if x >= 0 else '-'}{abs(x):.2f}$"


def pval(p):
    if p < 1e-3:
        e = math.floor(math.log10(p))
        m = p / 10 ** e
        return f"$p = {m:.0f}\\times10^{{{e}}}$" if round(m, 1) == round(m) else f"$p = {m:.1f}\\times10^{{{e}}}$"
    return f"$p = {p:.2f}$"


def wilson(k, n, z=1.959963984540054):  # same formula as imbalance.py
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - w, c + w


def ci(lo_hi):
    lo, hi = lo_hi
    return f"({100 * lo:.0f}--{100 * hi:.0f})"


def hit_cell(h, n):
    return f"{pct(h)} ({n})"


# ---- the agreement table by year (both papers) ----------------------------------------------------------------
rows = []
for y, v in YEARS.items():
    a, d = v["agree"], v["disagree"]
    rows.append(f"{y} & {v['signal_days']} & {a['n']} & {pct(a['hit_rate'])} {ci(a['wilson95'])} & {bp(a['mean_signed_move_bps'])} & "
                f"{d['n']} & {pct(d['hit_rate'])} {ci(d['wilson95'])} & {bp(d['mean_signed_move_bps'])} \\\\")
rows.append("\\midrule")
sm = RB["signed_move_bps"]
rows.append(f"All & {n_days} & {H1['n_agree']} & {pct(H1['hit_agree'])} {ci(wilson(hits_a, H1['n_agree']))} & {bp(sm['mean_a'])} & "
            f"{H1['n_disagree']} & {pct(H1['hit_disagree'])} {ci(wilson(hits_d, H1['n_disagree']))} & {bp(sm['mean_b'])} \\\\")
YEAR_ROWS = "\n".join(rows)

TAB_YEARS = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{Signal days that agree and disagree with the 15:50 closing imbalance, by year.}}
\\label{{tab:imbyear}}
\\tabnotes{{Signal days of the rule (a 15:50 body of 60\\% or more), 2021--2026. A day agrees when the sign of the
summed dollar imbalance of the 50 largest stocks, from each stock's first closing-imbalance record received in the
15:50 minute, equals the candle's direction. Every signal day was classified, so no day is unclassified. Hit rate:
share of days on which the CFD moved from the 15:51 open to the 15:59 close in the candle's direction, with its
Wilson 95\\% interval in percent; bp: the mean of that move in the candle's direction, in basis points. Over all
days the difference in hit rates is {pts(H1['d'])} points ($t = {H1['t']:.2f}$), with a 20-day block-bootstrap 95\\%
interval from {pts(BOOT['p2_5'])} to {pts(BOOT['p97_5'])} points.}}
\\begin{{tabular}}{{@{{}}lrrlrrlr@{{}}}}
\\toprule
 & & \\multicolumn{{3}}{{c}}{{Agreeing days}} & \\multicolumn{{3}}{{c}}{{Disagreeing days}} \\\\
\\cmidrule(lr){{3-5}}\\cmidrule(l){{6-8}}
Year & Days & $n$ & Hit rate (95\\% CI) & bp & $n$ & Hit rate (95\\% CI) & bp \\\\
\\midrule
{YEAR_ROWS}
\\bottomrule
\\end{{tabular}}
\\end{{table}}"""

# ---- the test table (working paper) ---------------------------------------------------------------------------
def rob_row(label, r):
    return (f"{label} & {hit_cell(r['hit_agree'], r['n_agree'])} & {hit_cell(r['hit_disagree'], r['n_disagree'])} & "
            f"{pts(r['d'])} & $t = {r['t']:.2f}$ \\\\")


op = RB["option_pnl_usd"]
adj = RB["year_direction_adjusted_d"]
TAB_TESTS = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{The closing-imbalance test: the rule's hit rate on days that agree and disagree with the 15:50 imbalance.}}
\\label{{tab:imbtest}}
\\tabnotes{{Signal days 2021--2026; all {n_days} were classified. Cells give the value and, in brackets, the number of
days (trades for the option P\\&L). Differences of hit rates are in percentage points; $t$ uses the standard error
of two independent proportions, and the move and option P\\&L rows use Welch's $t$. The bootstrap draws 20-day blocks
of the {num(N_KEEP)} sessions, {num(BOOT['kept'])} of {num(BOOT['attempted'])} draws kept. H2 and H3 are exact one-sided binomial tests
against one half (the half benchmark is descriptive), with a Holm correction: H2 {'rejects' if HOLM['H2'] else 'does not reject'},
H3 {'rejects' if HOLM['H3'] else 'does not reject'}. Panel~B was fixed in the plan and cannot change the verdict.
Move: from the 15:51 open to the 15:59 close in the candle's direction, basis points. Option P\\&L: \\ITM{{10}} at the
15:51 ask, held to settlement, \\$0.09 fee, on the {op['n_a'] + op['n_b']} priced trades.}}
\\begin{{tabular}}{{@{{}}lrrrr@{{}}}}
\\toprule
 & Agreeing days & Disagreeing days & Difference & Statistic \\\\
\\midrule
\\multicolumn{{5}}{{@{{}}l}}{{\\textit{{Panel A: registered tests}}}} \\\\
{rob_row('H1: hit rate (primary)', H1)}
\\quad Block-bootstrap 95\\% interval & & & \\multicolumn{{2}}{{l}}{{{pts(BOOT['p2_5'])} to {pts(BOOT['p97_5'])}}} \\\\
H2: candle agrees with imbalance & \\multicolumn{{2}}{{c}}{{{H2['agree']} of {H2['classified']} ({pct(H2['share'])})}} & & {pval(H2['p_upper'])} \\\\
H3: imbalance direction right & \\multicolumn{{2}}{{c}}{{{H3['imbalance_right']} of {H3['n']} ({pct(H3['share'])})}} & & {pval(H3['p_upper'])} \\\\
\\midrule
\\multicolumn{{5}}{{@{{}}l}}{{\\textit{{Panel B: robustness}}}} \\\\
{rob_row('Latest record before 15:51', RB['h1_last'])}
{rob_row('NYSE-listed stocks only', RB['h1_nyse'])}
{rob_row('Nasdaq-listed stocks only', RB['h1_nasdaq'])}
Adjusted for year and direction & & & {pts(adj['d'])} & {adj['cells_used']} cells \\\\
Move in the candle's direction (bp) & {bp(sm['mean_a'])} ({sm['n_a']}) & {bp(sm['mean_b'])} ({sm['n_b']}) & {bp_signed(sm['diff'])} & $t = {sm['t']:.2f}$ \\\\
Option P\\&L, \\$ a trade & {usd(op['mean_a'])} ({op['n_a']}) & {usd(op['mean_b'])} ({op['n_b']}) & {usd(op['diff'])} & $t = {op['t']:.2f}$ \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}"""

VERDICT = "passed" if H1["passed"] else "did not pass"
assert not H1["passed"], "the prose below is the plan's wording for a failed H1; write the other wording if H1 passes"

# ---- the working paper's section --------------------------------------------------------------------------------
WP = f"""% GENERATED by backtests/spx_candle_imbalance/make_tex.py from backtests/spx_candle_imbalance/results.json
% (the one registered run of preregistration/spx_candle_imbalance.md). Do not edit numbers by hand; re-run the script.
% Macros used: \\dollar, \\ITM, \\tabnotes.

% =====================================================================
\\section{{Closing-auction imbalances}}
\\label{{sec:imbalance}}

From 15:50~ET the New York Stock Exchange publishes the closing-auction imbalance of the stocks it lists, and Nasdaq
disseminates an early imbalance indicator for its own stocks every ten seconds.\\footnote{{The NYSE moved its
market-on-close cut-off and imbalance publication from 15:45 to 15:50 on 1 April 2019 (SEC Release No.~34-85021).
Nasdaq's early indicator from 15:50 was scheduled for the fourth quarter of 2019 (Release No.~34-87179). Samples of
the exchanges' messages on 30 December 2020 and 6 November 2026, outside the sample, confirmed both schedules.}} The
15:50 candle is therefore the first full minute in which the market can react to the published imbalance. That
suggests an explanation of the signal: traders act on the publication during the 15:50 minute, and the index keeps
drifting the same way while the auction absorbs the imbalance. If that channel mattered, the rule should be right
more often on days when its candle points the same way as the published imbalance than on days when it points the
other way. A pre-registered study (plan locked {LOCK}, one registered run) tested this prediction on the rule's
{n_days} signal days of 2021--2026, the days of its holdout.

\\paragraph{{Design.}} For each year the study used the 50 largest common-stock positions of SPY at the previous
year-end, from the fund's N-PORT reports to the SEC; they held {COVER} of its net assets. On each signal day it
bought from Databento the imbalance messages that each stock's listing exchange sent between 15:50 and 16:00 (NYSE
Pillar for NYSE-listed stocks, Nasdaq TotalView-ITCH for Nasdaq-listed ones). For each stock it kept the first
closing-auction imbalance record received in the 15:50 minute and summed the signed dollar imbalances,
$D = \\sum_i s_i Q_i p_i$, where $s_i$ is $+1$ for a buy imbalance, $-1$ for a sell imbalance and 0 for none, $Q_i$
is the imbalance in shares and $p_i$ the reference price, in exact integer arithmetic. A day with at least 10 usable
stocks and $D \\ne 0$ is classified, and it \\emph{{agrees}} if the sign of $D$ is the candle's direction. The outcome
is the rule's own: a hit when the CFD moves from the 15:51 open to the 15:59 close in the candle's direction. The
primary test (H1) compares the hit rates on agreeing and disagreeing days, $d = h_a - h_d$, and passes if $d > 0$
and $t = d/\\mathrm{{se}} \\ge 2.0$, with the standard error of two independent proportions. Two secondary tests,
which decide nothing, ask whether the candle agrees with the imbalance on more than half of the days (H2) and
whether the imbalance direction alone predicts the move (H3), with a Holm correction. A block bootstrap gives an
interval for $d$, and the robustness checks of Table~\\ref{{tab:imbtest}} were fixed in the plan, as was the wording
of the verdict. By the plan's power calculation, which treats days as independent, 80\\% power at the bar needs a
true $d$ of {POWER}: the test can detect a large concentration of the edge on agreeing days, not a modest one.

Every signal day was classified. All 50 stocks had a usable first record on each of the {n_days} days, and the first
closing record of the minute arrived a median of about 0.1 seconds after 15:50:00 on both exchanges (at most
{FIRST_MAX:.1f} seconds). The code was reviewed three times by a second reader before the download and the run, and
every defect found was fixed first.

{TAB_TESTS}

{TAB_YEARS}

\\paragraph{{Results.}} The candle and the published imbalance usually pointed the same way: they agreed on
{H2['agree']} of the {H2['classified']} days ({pct(H2['share'])}), far more often than half (H2, {pval(H2['p_upper'])}).
Agreement did not make the candle more accurate (Table~\\ref{{tab:imbtest}}). It was right on {pct(H1['hit_agree'])} of
agreeing days and on {pct(H1['hit_disagree'])} of disagreeing days, so $d = {pts(H1['d'])[1:-1]}$ points (se
{100 * H1['se']:.1f}, $t = {H1['t']:.2f}$), and H1 {VERDICT}. The block-bootstrap interval of $d$, from
{pts(BOOT['p2_5'])} to {pts(BOOT['p97_5'])} points, lies below the {POWER[6:]} that the test was designed to detect.
The imbalance direction alone was right on {pct(H3['share'])} of days (H3, {pval(H3['p_upper'])}). The robustness
checks agree: the difference in hit rates stayed negative with the latest record of the minute, with NYSE or Nasdaq
stocks alone and within year and direction. The average move in the candle's direction was about the same on both
kinds of day ({bp(sm['mean_a'])} against {bp(sm['mean_b'])} basis points), and the option trade made more on agreeing
days ({usd(op['mean_a'])} against {usd(op['mean_b'])} a trade), but not significantly ($t = {op['t']:.2f}$). By year
(Table~\\ref{{tab:imbyear}}), {BY_YEAR}.

\\paragraph{{What the result means.}} In the words the plan fixed in advance, the prediction was not confirmed, the
test has limited power, and a failure does not refute the auction explanation. The price may adjust within the 15:50
candle itself and leave little after 15:51, imbalances change after their first publication, the stocks'
imbalances can offset one another in $D$, and 50 stocks are only part of the index. The high agreement is itself an
association, not a cause: the candle and the imbalance can both reflect the same closing orders, such as index
funds' orders known earlier in the day, and because records are timed by when Databento received them, the study
cannot show that the publication came before the price move. What it does show is narrower: on these days the
rule's edge was not concentrated on the days on which its candle agreed with the imbalance first published for the
50 largest stocks. Whether the effect changed when the NYSE moved its publication to 15:50 in 2019, and whether it
depends on the size of the imbalance, were outside the plan.
"""

# ---- the journal version's subsection ---------------------------------------------------------------------------
J = f"""% GENERATED by backtests/spx_candle_imbalance/make_tex.py from backtests/spx_candle_imbalance/results.json
% (the one registered run of preregistration/spx_candle_imbalance.md). Do not edit numbers by hand; re-run the script.

\\subsection{{A test with the published imbalances}}
\\label{{sec:imbtest}}

If traders react to the published imbalance during the 15:50 minute, the candle should be right more often on days
when it points the same way as that imbalance. A pre-registered study (plan locked {LOCK}, one registered run)
tested this prediction on the rule's {n_days} signal days of 2021--2026. For each year it took the 50 largest stocks
in SPY at the previous year-end, from the fund's N-PORT reports to the SEC ({COVER} of its net assets), and bought
from Databento the imbalance messages that each stock's listing exchange sent from 15:50. From each stock's first
closing-imbalance record received in the 15:50 minute it summed the signed dollar imbalance,
$D = \\sum_i s_i Q_i p_i$, with $s_i = +1$ for a buy imbalance, $-1$ for a sell imbalance and 0 for none, $Q_i$ the
imbalance in shares and $p_i$ the reference price. A day agrees if the sign of $D$ is the candle's direction. The
primary test compares the rule's hit rate on agreeing and disagreeing days, $d = h_a - h_d$, and passes if $d > 0$
and $t \\ge 2.0$. By the plan's power calculation it could detect a true $d$ of {POWER}, a large concentration of
the edge on agreeing days, not a modest one. All 50 stocks had a usable record on every day, so every signal day was
classified.

{TAB_YEARS}

The candle and the imbalance usually pointed the same way, on {H2['agree']} of the {H2['classified']} days
({pct(H2['share'])}). But agreement did not make the candle more accurate (Table~\\ref{{tab:imbyear}}): it was right on
{pct(H1['hit_agree'])} of agreeing days and {pct(H1['hit_disagree'])} of disagreeing days, $d = {pts(H1['d'])[1:-1]}$
points ($t = {H1['t']:.2f}$), with a block-bootstrap interval from {pts(BOOT['p2_5'])} to {pts(BOOT['p97_5'])} points,
and {BY_YEAR}. The imbalance direction alone was right on {pct(H3['share'])} of days. The robustness checks fixed in
the plan agree: the difference in hit rates stayed negative with the latest record of the minute, with NYSE or
Nasdaq stocks alone and within year and direction, and the differences in the average move and in the option P\\&L
were small against their noise ($t = {sm['t']:.2f}$ and ${op['t']:.2f}$; Internet Appendix). The prediction was
therefore not confirmed. The test has limited power, and a failure does not refute the auction explanation: the
price may adjust within the 15:50 candle itself, imbalances change after their first publication, and 50 stocks are
only part of the index. The high agreement is an association, not a cause, since the candle and the imbalance can
reflect the same closing orders. What the test does show is that the rule's edge was not concentrated on the days on
which its candle agreed with the imbalance first published at 15:50.
"""

OUT_WP.write_text(WP)
OUT_J.write_text(J)
print(f"wrote {OUT_WP.relative_to(ROOT)} and {OUT_J.relative_to(ROOT)}")
