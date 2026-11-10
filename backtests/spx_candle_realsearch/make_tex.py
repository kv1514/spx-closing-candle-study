"""Write the paper section for the closing-candle search straight from the result files (no hand-typed numbers).

Run from the repository root:
  .venv/bin/python -I backtests/spx_candle_realsearch/make_tex.py
Reads selection.json, tune_results.json, results.json and diag_null_sizes.json (the post-hoc diagnostic) in
backtests/spx_candle_realsearch/; writes papers/spx_candle_1550/search_section_draft.tex.
Every sentence that states a pattern (which minute leads, which settings reach t >= 2, ...) is asserted against the
data first, so the script stops instead of writing a sentence that the results no longer support.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
H = ROOT / "backtests" / "spx_candle_realsearch"
SEL = json.load(open(H / "selection.json"))
TU = json.load(open(H / "tune_results.json"))
RE = json.load(open(H / "results.json"))
DG = json.load(open(H / "diag_null_sizes.json"))
OUT = ROOT / "papers" / "spx_candle_1550" / "search_section_draft.tex"
P3 = RE["part3"]
NCELLS = 3 * 11 * 12 * 2 * 9


def usd(x, n=2):
    return f"${'+' if x >= 0 else '-'}\\dollar{abs(x):,.{n}f}$".replace(",", "{,}")


def num(x, n=2):
    return f"${x:+.{n}f}$"


def pct(x, n=0):
    return f"{100 * x:.{n}f}\\%"


def n_(x):
    return f"{x:,}".replace(",", "{,}")


SRC = {"index": "Index", "SPY": "SPY", "both": "Both"}


def strike(s):
    if s == "ATM":
        return "\\ATM"
    return f"\\{s[:3]}{{{s[3:]}}}"


def parts(name):
    """'index 15:50 body>=0.80 with ITM20' -> (Index, 15:50, $\\ge 80\\%$, With, \\ITM{20})"""
    src, cand, body, side, k = name.split()
    cut = round(100 * float(body.split(">=")[1]))
    return SRC[src], cand, f"$\\ge {cut}\\%$", side.capitalize(), strike(k)


def short(name):
    s, c, b, d, k = parts(name)
    return f"{s} {c}, {b}, {d.lower()}, {k}"


# ---------------------------------------------------------------- facts, each checked
pick, null, paired = TU["pick"], TU["null"], TU["paired"]
p, shifts = TU["p"], null["shifts"]
k_at_least = round(p * (shifts + 1)) - 1
assert abs((1 + k_at_least) / (1 + shifts) - p) < 1e-12
dec = SEL["decision"]
assert dec["decision"] == "exclusion_family" and not dec["goes_to_test"] and "skipped" in RE["part2"]
assert pick["cell"].split()[1] == "15:50" and p > 0.05 and paired["mean"] > 0
assert pick["h1_mean"] > 10 * pick["h2_mean"] > 0
chk = {"tune_R60": TU["checks"]["R60"]["file_rows"], "tune_S60": TU["checks"]["S60"]["file_rows"],
       "test_R60": RE["check_R60_test"]["file_rows"], "test_S60": RE["check_S60_test"]["file_rows"]}
assert TU["checks"]["R60"]["equal"] and TU["checks"]["S60"]["equal"]
assert RE["check_R60_test"]["equal"] and RE["check_S60_test"]["equal"]

bpc = TU["best_per_candle"]
none_minutes = [m for m, r in bpc.items() if r is None]
ranked_minutes = sorted((m for m, r in bpc.items() if r), key=lambda m: -bpc[m]["score"])
assert ranked_minutes[0] == "15:50" and ranked_minutes[1] == "15:54" and none_minutes == ["15:51", "15:55"]
gap = bpc["15:54"]["score"]
others_below = [m for m in ranked_minutes[2:] if bpc[m]["score"] < gap]
assert len(others_below) == len(ranked_minutes) - 2

wr = P3["whole_ranking"]
top = wr["top15"]
assert all(r["cell"].split()[1] == "15:50" and r["cell"].split()[3] == "with" for r in top)
n_itm20 = sum(r["cell"].endswith("ITM20") for r in top)
assert n_itm20 > len(top) / 2
best = top[0]
assert wr["null"]["observed_best"] > wr["null"]["q95"]

leads = P3["leads"]
named = P3["named"]
r60 = named["R60"]["ask_fee_0.09"]
lead_rows = [("Index $\\ge 60\\%$, \\ITM{10} (Section~\\ref{sec:realindex})", r60["tuning"], r60["test"])]
for k, v in leads.items():
    lead_rows.append((short(k).replace("15:50, ", "").replace(", with", ""), v["tuning"], v["test"]))
test_t2 = [k for k, v in leads.items() if (v["test"]["t"] or 0) >= 2]
assert test_t2 == ["SPY 15:50 body>=0.70 with ITM20"]
assert all(v["tuning"]["mean_per_day"] > 0 and v["test"]["mean_per_day"] > 0 for v in leads.values())
assert r60["tuning"]["mean_per_day"] > 0 and r60["test"]["mean_per_day"] > 0
assert all(r60["tuning"]["mean_per_day"] < v["tuning"]["mean_per_day"] for v in leads.values())
pk = named["pick"]
pmid, pask = pk["mid_fee_0.09"], pk["ask_fee_0.09"]

im = P3["index_moves"]
a, b = im["2019-2020"], im["2021-2026"]
assert all(r["candle"] == "15:50" for r in b["top10_by_t"])
assert not any(r["candle"] == "15:50" for r in a["top10_by_t"])
assert b["null"]["observed_max_t"] < b["null"]["q95"] and a["null"]["observed_max_t"] < a["null"]["median"]
b0, a0 = b["top10_by_t"][0], a["top10_by_t"][0]
assert (b0["source"], b0["candle"], round(100 * b0["threshold"])) == ("index", "15:50", 85)
assert pick["cell"] == "index 15:50 body>=0.80 with ITM20"
test_means = [v["test"]["mean_per_day"] for v in leads.values()]
assert DG["large_cells_null_max_t_q95"] < b0["t"]
assert all(r["days"] >= DG["min_days_large"] for r in b["top10_by_t"])


# ---------------------------------------------------------------- tables
def tune_rows(rows):
    out = []
    for r in rows:
        s, c, bb, d, k = parts(r["cell"])
        out.append(f"{s} & {c} & {bb} & {d} & {k} & {usd(r['score'])} & {usd(r['mean_per_day'])} & {r['trades']} & "
                   f"{usd(r['h1_mean'])} & {usd(r['h2_mean'])} \\\\")
    return "\n".join(out)


minute_rows = []
for m, r in bpc.items():
    if r is None:
        minute_rows.append(f"{m} & \\multicolumn{{4}}{{l}}{{No eligible setting}} & & & \\\\")
    else:
        s, c, bb, d, k = parts(r["cell"])
        minute_rows.append(f"{m} & {s} & {bb} & {d} & {k} & {usd(r['score'])} & {usd(r['mean_per_day'])} & {r['trades']} \\\\")
minute_rows = "\n".join(minute_rows)

whole_rows = []
for r in top[:10]:
    s, c, bb, d, k = parts(r["cell"])
    whole_rows.append(f"{s} & {bb} & {k} & {usd(r['mean_per_day'])} & {num(r['t'])} & {n_(r['trades'])} & "
                      f"{usd(r['per_trade'])} & {pct(r['won'])} \\\\")
whole_rows = "\n".join(whole_rows)

lrows = []
for i, (lab, tu, te) in enumerate(lead_rows):
    lrows.append(f"{lab} & {usd(tu['mean_per_day'])} & {num(tu['t'])} & {tu['trades']} & "
                 f"{usd(te['mean_per_day'])} & {num(te['t'])} & {te['trades']} \\\\")
    if i == 0:
        lrows.append("\\addlinespace")
lead_rows_tex = "\n".join(lrows)


def move_rows(v, n):
    out = []
    for r in v["top10_by_t"][:n]:
        out.append(f"{SRC[r['source']]} & {r['candle']} & $\\ge {round(100 * r['threshold'])}\\%$ & {r['days']} & "
                   f"{num(r['mean_bps'])} & {num(r['t'])} & {pct(r['right_share'])} \\\\")
    return "\n".join(out)


# ---------------------------------------------------------------- the section
tex = f"""% Section for main.tex: the pre-registered search over closing candles (run 2026-11-10 UTC).
% GENERATED by backtests/spx_candle_realsearch/make_tex.py from selection.json, tune_results.json, results.json and
% diag_null_sizes.json. Do not edit numbers by hand; re-run the script. Macros used: \\dollar, \\ITM, \\OTM, \\ATM.
% Pre-registered: preregistration/spx_candle_realsearch.md, SHA-256 {SEL['prereg_sha256'][:8]}..., locked 2026-11-10T06:24:53Z.

\\section{{A search over closing candles}}
\\label{{sec:search}}

The studies so far fixed the candle and its cut and asked whether that rule
worked. A last pre-registered study asked the broader question: among the
closing candles, cuts, directions and strikes near the rule, which setting does
best on real asks, and is the best one better than luck? The plan was locked
after every earlier study, and two of its three candle sources, the SPY candle
and the agreement of the SPY and index candles, were chosen after their results
had been seen. It therefore guards against further selection but not against
that history, and it set aside in advance every 15:50 setting, because those had
already been examined on the later years and could not be tested on them afresh.

\\paragraph{{Design.}} The search covers {n_(NCELLS)} settings: three candle
sources (the index candle, the SPY candle, and the two agreeing in direction),
the eleven one-minute candles from 15:45 to 15:55, twelve body cuts from 40\\% to
95\\%, trading with or against the candle, and nine strikes from \\ITM{{20}} to
\\OTM{{20}}. Each trade buys one SPXW contract at the ask in the snapshot that
opens the next minute and holds it to settlement. A setting is scored on
2021--2023 by its mean profit per day averaged with the settings one cut above
and below, so that an isolated spike does not win. To be eligible it needs at
least 100 trades, at least 40 in each half of the period, a positive mean in each
half, and prices for at least 95\\% of its signals; {n_(TU['eligible_cells'])} settings
qualified. The best one would be tested once on 2024--2026 only if it was not a
15:50 setting, if a luck diagnostic gave $p \\le 0.05$, and if it beat the
index-candle rule of Section~\\ref{{sec:realindex}} on the tuning days. The luck
diagnostic repeats the whole search {shifts} times with every candle signal
moved by a whole number of sessions against fixed outcomes, which keeps each
signal's own pattern but breaks its link to the outcome. Before any statistic,
the code reproduced the trades of the two candle studies exactly
({chk['tune_R60']} and {chk['tune_S60']} on the tuning days, {chk['test_R60']}
and {chk['test_S60']} on the test days). Unlike the earlier studies, its code was
not reviewed by a second reader before the run; it passed synthetic self-tests
and a full trial on synthetic data.

\\begin{{table}}[t]
\\centering
\\small
\\caption{{The best settings on 2021--2023.}}
\\label{{tab:searchtune}}
\\begin{{tabular}}{{@{{}}llllrrrrrr@{{}}}}
\\toprule
Source & Candle & Body & Side & Strike & Score & \\$/day & Trades & First half & Second half \\\\
\\midrule
{tune_rows(TU['top15'][:10])}
\\bottomrule
\\end{{tabular}}
\\tabnotes{{The ten eligible settings with the highest score, of {n_(TU['eligible_cells'])}
eligible among {n_(NCELLS)}. Score is the mean profit per day averaged with the
same setting one cut above and below; \\$/day is the setting's own mean over
{TU['days']} sessions. The halves are 2021-01-01 to 2022-09-30 and 2022-10-01 to
2023-12-31. One contract at the ask, held to settlement, \\$0.09 in fees.
Pre-registered.}}
\\end{{table}}

\\paragraph{{Result.}} The search chose a 15:50 setting: the index candle with a
body of 80\\% or more, traded in its direction with \\ITM{{20}}
(Table~\\ref{{tab:searchtune}}). Because 15:50 settings were set aside, nothing
went to the test, and this choice can be checked only on later sessions. It also
missed the luck bar: the shifted searches reached its score in {k_at_least} of
{shifts} cases ($p = {p:.3f}$; median best score {usd(null['median'])}, 95th
percentile {usd(null['q95'])}). Its gain came almost entirely in the first half
of the tuning period ({usd(pick['h1_mean'])} a day against {usd(pick['h2_mean'])}).
By candle minute (Table~\\ref{{tab:searchminutes}}), 15:50 led and 15:54 came
second, every other minute scored below both, and two minutes had no eligible
setting at all.

\\begin{{table}}[t]
\\centering
\\small
\\caption{{The best eligible setting for each candle, 2021--2023.}}
\\label{{tab:searchminutes}}
\\begin{{tabular}}{{@{{}}llllrrrr@{{}}}}
\\toprule
Candle & Source & Body & Side & Strike & Score & \\$/day & Trades \\\\
\\midrule
{minute_rows}
\\bottomrule
\\end{{tabular}}
\\tabnotes{{As in Table~\\ref{{tab:searchtune}}, the highest-scoring eligible
setting among those that read the given candle. Entry is at the next minute.
Pre-registered.}}
\\end{{table}}

\\paragraph{{The whole period.}} This part is descriptive. After the decision,
the grid was ranked on all of 2021--2026 by mean profit per day, among settings
with at least 200 trades and prices for 95\\% of their signals. All fifteen
leading settings were 15:50 candles traded in their direction, {n_itm20} of them
with \\ITM{{20}} (Table~\\ref{{tab:searchwhole}}). The first, {short(best['cell'])},
made {usd(best['mean_per_day'])} a day ({usd(best['per_trade'])} a trade,
$t = {best['t']:.2f}$, {best['trades']} trades), above the 95th percentile of the
same ranking repeated on {wr['null']['shifts']} shifted signals
({usd(wr['null']['q95'])}). The ranking reuses days already seen and is not a
test. Table~\\ref{{tab:searchleads}} follows the 15:50 settings examined in
earlier sections across the two periods. Every one made money in both, the
60\\% rule least on the tuning days, and on 2024--2026 only the SPY candle at
70\\% with \\ITM{{20}} reached $t = 2$. Paying the ask was costly throughout: at
the mid, the search's choice made {usd(pmid['tuning']['mean_per_day'])} a day on
2021--2023 and {usd(pmid['test']['mean_per_day'])} on 2024--2026, against
{usd(pask['tuning']['mean_per_day'])} and {usd(pask['test']['mean_per_day'])} at the
ask.

\\begin{{table}}[t]
\\centering
\\small
\\caption{{The leading settings over 2021--2026, all on the 15:50 candle.}}
\\label{{tab:searchwhole}}
\\begin{{tabular}}{{@{{}}lllrrrrr@{{}}}}
\\toprule
Source & Body & Strike & \\$/day & $t$ & Trades & \\$/trade & Won \\\\
\\midrule
{whole_rows}
\\bottomrule
\\end{{tabular}}
\\tabnotes{{The ten settings with the highest mean profit per day on 2021-01-01 to
2026-10-20 among {n_(wr['eligible_cells'])} with at least 200 trades and prices
for 95\\% of their signals; all trade in the candle's direction. $t$ is
Newey--West, lag 5. Ranked after the tuning decision on days already seen.
Descriptive.}}
\\end{{table}}

\\begin{{table}}[t]
\\centering
\\small
\\caption{{The 15:50 settings examined earlier, by period.}}
\\label{{tab:searchleads}}
\\begin{{tabular}}{{@{{}}lrrrrrr@{{}}}}
\\toprule
 & \\multicolumn{{3}}{{c}}{{2021--2023}} & \\multicolumn{{3}}{{c}}{{2024--2026}} \\\\
\\cmidrule(lr){{2-4}}\\cmidrule(l){{5-7}}
Setting & \\$/day & $t$ & Trades & \\$/day & $t$ & Trades \\\\
\\midrule
{lead_rows_tex}
\\bottomrule
\\end{{tabular}}
\\tabnotes{{The 15:50 candle traded in its direction, one contract at the ask,
held to settlement. The first row is the index-candle rule; the rest are the
settings the plan set aside as examined. ``Both'' requires the index and SPY
candles to pass the cut in the same direction. $t$ is Newey--West, lag 5.
Descriptive.}}
\\end{{table}}

\\paragraph{{Which candle predicts the index.}} This part is descriptive. Without
options, the same signals can be scored on the index move itself, from the next
minute's open to the 15:59 close in the candle's direction
(Table~\\ref{{tab:searchmove}}). On 2021--2026 the ten largest $t$-statistics all
belonged to 15:50 candles, led by the index candle at 85\\%
({num(b0['mean_bps'])} basis points over {b0['days']} sessions, $t = {b0['t']:.2f}$).
On 2019--2020, with the index candle alone, no 15:50 setting was among the ten
largest, and the largest $t$ ({a0['t']:.2f}, on {a0['days']} sessions) was below
the median of its shifted benchmark. The registered benchmark for this table,
the 95th percentile of the largest $t$ on shifted signals ({b['null']['q95']:.2f}
on 2021--2026), was not cleared. A check chosen after the run shows why the bar
is high: in {pct(DG['share_of_max_t_cells_under_100_days'])} of the shifted
tables the largest $t$ came from a setting with fewer than 100 sessions, and
among settings with at least {DG['min_days_large']} sessions the shifted 95th
percentile was {DG['large_cells_null_max_t_q95']:.2f}. The 15:50 result is
therefore strong for its sample size, but it did not pass the bar fixed in
advance.

\\begin{{table}}[t]
\\centering
\\small
\\caption{{The index move after each closing candle.}}
\\label{{tab:searchmove}}
\\begin{{tabular}}{{@{{}}lllrrrr@{{}}}}
\\toprule
Source & Candle & Body & Sessions & bps & $t$ & Right \\\\
\\midrule
\\multicolumn{{7}}{{@{{}}l}}{{\\emph{{Panel A: 2019--2020, index candle only}}}} \\\\
{move_rows(a, 5)}
\\addlinespace
\\multicolumn{{7}}{{@{{}}l}}{{\\emph{{Panel B: 2021--2026, all three sources}}}} \\\\
{move_rows(b, 10)}
\\bottomrule
\\end{{tabular}}
\\tabnotes{{The settings with the largest $t$, of {a['cells']} on 2019--2020 and
{b['cells']} on 2021--2026: the index move from the open of the minute after the
candle to the 15:59 close, in the candle's direction, in basis points, on
sessions on which the candle passed the cut. $t$ is Newey--West, lag 5;
``Right'' is the share of non-zero moves in the candle's direction. Shifted
benchmark for the largest $t$: median {a['null']['median']:.2f} and 95th percentile
{a['null']['q95']:.2f} on 2019--2020, {b['null']['median']:.2f} and
{b['null']['q95']:.2f} on 2021--2026. Descriptive.}}
\\end{{table}}

\\paragraph{{Limits.}} The search reuses the 2021--2026 outcomes of the earlier
studies, and two of its candle sources were chosen with knowledge of them, so
its luck diagnostic corrects for the {n_(NCELLS)} settings but not for that
history. Its choice was not clearly beyond luck and earned almost all of its
tuning gain before October 2022. What it adds is comparative: no other closing minute, cut,
direction or strike beat the 15:50 candle on 2021--2023, and settings that ask
for a cleaner candle (80\\% or more on the index, 70\\% or more on SPY, or the
two candles agreeing) made more than the 60\\% rule on 2021--2023 and between
{usd(min(test_means))} and {usd(max(test_means))} a day on 2024--2026, against its
{usd(r60['test']['mean_per_day'])}. Those are hypotheses that only sessions after
November 2026 can test.
"""
OUT.write_text(tex)
print("wrote", OUT, len(tex), "chars")
