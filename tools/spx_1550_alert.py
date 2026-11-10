#!/usr/bin/env python3
"""SPX 15:50 candle alert: watches the 15:50 ET one-minute SPX candle and pushes the call or put to your phone.

The rule (backtests/SPX_1550_ONE_PAGE.md; research, not trading advice):
  - at 15:51 ET look at the 15:50 one-minute candle;
  - body = |close - open|, range = high - low; trade only if body >= 60% of range;
  - green -> call, red -> put; strike 10 points in the money (SPX rounded to the nearest 5, call -10, put +10),
    expiring today (0DTE SPXW); limit at the mid, raise to the ask at 15:52 if unfilled; hold to the close.

Data (free, no account or key): CNBC's live SPX quote (1-4 seconds behind) for the heads-up while the candle forms,
then the first finished official 15:50 one-minute candle from CNBC or Yahoo Finance (usually 10-30 seconds after
15:51:00); the other source is a cross-check, and a push goes out only if it changes the answer. No browser,
TradingView or Robinhood login is needed. Pushes go through ntfy (https://ntfy.sh): install the ntfy app
and subscribe to the topic that `setup` prints. Nothing here places, previews or stages an order.

Two pushes a day, and only two (the rule of backtests/spx_candle_spy/SUMMARY.md: SPY's 15:50 candle at 70%+ with the
SPX chart at 60%+ in the same direction; research, not advice):
  1. about 15:50:40 ET (12:50 PT): ARM or STAND DOWN, from the two candles as they form (approximate).
  2. right after 15:51:00 ET (12:51 PT): BUY CALL/PUT <strike>, or NO TRADE, from the finished candles.
Everything else (the SPX-only reading, SPY's reading, the vendor cross-check, the after-close result and running
totals) is written to the logs without a push. `close --push` or `run --push-close` sends the result as well.

Commands:
  setup                 create a private random ntfy topic (once) and print how to subscribe to it.
  test-push             send a test notification.
  run [--no-preview]    wait for today's 15:50 candle (from 15:49:30 ET), push message 1 while it forms (about
      [--dry-run]       15:50:40) and message 2 as soon as the finished SPX and SPY candles are out (it waits up to
      [--push-close]    25 seconds for SPY after the SPX candle, then decides without it: no SPY means no trade).
                        Exits quietly on weekends, holidays and half days. --dry-run prints instead of pushing.
  close [--date D]      after the close (from 16:05:30 ET): price today's SPX-chart signal at 15:51 from Cboe's free
      [--dry-run]       15-minute-delayed quotes (read at ~16:07, so they show 15:51), settle it at the SPX close and
      [--push]          log the profit or loss to data/spx_1549/alerts/closes_1550.csv with the decision of message 2.
                        `run` does this by itself. It also logs 20 in the money to 10 out of the money from the same
                        snapshot to ladder_1550.csv (a record only). No push unless --push.
  fill PRICE [--date D] note the price you paid (or saw) for the day's alerted contract; `close` reports the
                        profit or loss at it too.
  feeds [--days N]      fill in data/spx_1549/alerts/feeds_1550.csv for the last N weekdays (default 7): the real
                        SPX 15:50 candle next to the Dukascopy feed's 15:50 candle (the feed every backtest read),
                        each one's body % and band, and SPX's move from 15:51 to the close. `run` does this by
                        itself after the alert; a day's Dukascopy file is usually out by the next run.
  replay                show the 15:50 signal for the last 7 weekdays from CNBC and Yahoo, and the forward log
                        (data/spx_1549/forward/candle_1550_log.csv, Robinhood bars) where that has the day.
  selftest              check the arithmetic and message text offline.

Bands (backtests/spx_candle_realindex/SUMMARY.md, pre-registered, 2021-2026 at real option prices): the original
backtests read the candle from a Dukascopy feed; read from the real SPX chart, as this alert does, the rule made
+$39 a trade at 60%+ (t 1.53, did not pass), +$54 at 70%+ (t 1.86) and -$24 at 60-70% (no edge found). Days when
only the real chart showed a strong body lost money. Every alert and close is tagged with its band.

SPY (backtests/spx_candle_spy/SUMMARY.md, pre-registered): right after the SPX alert a second push gives SPY's 15:50
candle (CNBC) and whether it confirms. In the 2021-2026 backtest the trade made +$80 when SPY and the SPX chart both
showed 60%+ and lost money when only the SPX chart did; SPY at 70%+ made +$103. It was the third chart tried on the
same days, so it is a lead being logged, not proof. SPY never delays the SPX alert: it is read only after that push.

Config: the topic comes from $NTFY_TOPIC, else data/spx_1549/alerts/ntfy_topic.txt (written by setup; data/ is
gitignored). $NTFY_SERVER overrides https://ntfy.sh. Each alert is appended to data/spx_1549/alerts/alerts_1550.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import lzma
import math
import os
import secrets
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
ALERT_DIR = ROOT / "data" / "spx_1549" / "alerts"
TOPIC_FILE = ALERT_DIR / "ntfy_topic.txt"
LOG_FILE = ALERT_DIR / "alerts_1550.csv"
CLOSE_FILE = ALERT_DIR / "closes_1550.csv"
CBOE_OPTIONS = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
FEE = 0.09                          # $ per contract, as in the backtests
FORWARD_LOG = ROOT / "data" / "spx_1549" / "forward" / "candle_1550_log.csv"
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
YAHOO_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
YAHOO_PATH = "/v8/finance/chart/%5EGSPC?interval=1m&range={rng}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) spx-1550-alert"
CHART_LINK = "https://www.tradingview.com/chart/?symbol=SP%3ASPX"

BODY_NUM, BODY_DEN = 6, 10          # body >= 60% of range, compared in whole cents (no float edge at exactly 60%)
STRONG_NUM, STRONG_DEN = 7, 10      # 70%+ on the real chart: about what the backtest feed's 60% caught (audit)
BAND_STRONG, BAND_BORDER, BAND_NONE = "70%+", "60-70%", "under 60%"
FEEDS_FILE = ALERT_DIR / "feeds_1550.csv"
DUKA_URL = "https://datafeed.dukascopy.com/datafeed/USA500IDXUSD/{y:04d}/{m0:02d}/{d:02d}/BID_candles_min_1.bi5"
DUKA_UA = "spx1549-research-fetcher/1.0 (personal research backtest; low request rate)"
DUKA_RECORD = struct.Struct(">iiiiif")   # seconds since 00:00 UTC, open, close, low, high, volume; prices x 1000
ITM_POINTS = 10
STRIKE_STEP = 5
WATCH_FROM = dtime(15, 49)          # start polling
PREVIEW_AT = dtime(15, 50, 40)      # heads-up while the candle forms
FINAL_AFTER = dtime(15, 51)         # the 15:50 candle has closed
GIVE_UP_AT = dtime(15, 53)          # no candle by now -> error alert


# ------------------------------------------------------------------------------------------------
# the rule
# ------------------------------------------------------------------------------------------------
def cents(x: float) -> int:
    return int(round(x * 100))


def signal(o: float, h: float, l: float, c: float) -> dict:
    """The 15:50 rule on one candle. Prices are rounded to cents first (Yahoo sends float32 noise)."""
    oc, hc, lc, cc = cents(o), cents(h), cents(l), cents(c)
    body_c, range_c = abs(cc - oc), hc - lc
    direction = "call" if cc > oc else "put" if cc < oc else None
    strong = range_c > 0 and BODY_DEN * body_c >= BODY_NUM * range_c
    trade = bool(strong and direction)
    band = "" if range_c <= 0 else BAND_NONE if not trade else (
        BAND_STRONG if STRONG_DEN * body_c >= STRONG_NUM * range_c else BAND_BORDER)
    return {"open": oc / 100, "high": hc / 100, "low": lc / 100, "close": cc / 100,
            "body": body_c / 100, "range": range_c / 100,
            "ratio": (body_c / range_c) if range_c > 0 else None,
            "color": "green" if direction == "call" else "red" if direction == "put" else "flat",
            "direction": direction, "trade": trade, "band": band}


def atm_of(spot: float) -> int:
    """Nearest 5, halves up: the backtests' floor(S / 5 + 0.5) x 5."""
    return int(math.floor(spot / STRIKE_STEP + 0.5) * STRIKE_STEP)


def strike_for(spot: float, direction: str) -> int:
    atm = atm_of(spot)
    return atm - ITM_POINTS if direction == "call" else atm + ITM_POINTS


# ------------------------------------------------------------------------------------------------
# messages
# ------------------------------------------------------------------------------------------------
def pct(r: float | None) -> str:
    return "n/a" if r is None else f"{r * 100:.0f}%"


def final_message(day: date, s: dict, spot: float) -> dict:
    """Title, body, priority and tags for the 15:51 alert."""
    ratio_line = (f"15:50 candle: {s['color'].upper()}, body {s['body']:.2f} / range {s['range']:.2f} = "
                  f"{pct(s['ratio'])} (needs 60%)")
    if not s["trade"]:
        why = "no range" if s["range"] == 0 else "flat candle" if s["direction"] is None else "body under 60%"
        return {"title": "No trade today - SPX 15:50 candle",
                "body": f"{ratio_line}\n{why}: do nothing today.",
                "priority": 2, "tags": "zzz", "kind": "no_trade", "strike": None}
    k = strike_for(spot, s["direction"])
    side = s["direction"].upper()
    atm = atm_of(spot)
    strong = s["band"] == BAND_STRONG
    band_line = ("Band 70%+ on the real chart: +$54 a trade in the 2021-2026 backtest (t 1.86, just short of the "
                 "test bar; candles of 80%+ did best, as a description only)." if strong else
                 "Band 60-70% on the real chart: BORDERLINE. No edge in the 2021-2026 backtest (-$24 a trade at the "
                 "ask, 131 trades). Logged either way.")
    body = (f"SPXW {k} {side}, expires today ({day.strftime('%b')} {day.day})\n"
            f"{ratio_line}\n"
            f"{band_line}\n"
            f"SPX {spot:.2f} -> nearest 5 = {atm} -> 10 in the money = {k}\n"
            f"Now: limit at the mid. Not filled by 15:52 -> raise to the ask. Hold to 16:00.\n"
            f"(15-20 in the money tested about the same, so a 5-point slip is fine.)")
    title = f"BUY {side} {k} - SPX 15:50 signal ({'70%+' if strong else '60-70%, borderline'})"
    return {"title": title, "body": body, "priority": 4,
            "tags": "green_circle,chart_with_upwards_trend" if side == "CALL" else "red_circle,chart_with_downwards_trend",
            "kind": "signal", "strike": k}


def preview_message(o: float, hi: float, lo: float, last: float) -> dict:
    s = signal(o, hi, lo, last)
    if s["trade"]:
        k = strike_for(last, s["direction"])
        title = f"Heads-up: likely {s['direction'].upper()} {k} (candle still forming)"
    else:
        title = "Heads-up: likely no trade (candle still forming)"
    body = (f"15:50 candle so far: {s['color']}, about {pct(s['ratio'])} body (approximate). "
            f"Not final: the real alert comes right after 15:51:00. Open the SPX 0DTE chain now.")
    return {"title": title, "body": body, "priority": 3, "tags": "hourglass_flowing_sand", "kind": "preview"}


# ------------------------------------------------------------------------------------------------
# the two messages: ARM / STAND DOWN while the candles form, then BUY / NO TRADE
# ------------------------------------------------------------------------------------------------
def decide(spx: dict, spy: dict | None) -> dict:
    """The rule: SPY's 15:50 candle at 70%+ and the SPX chart's at 60%+, same direction."""
    if spy is None:
        return {"buy": False, "direction": None, "reason": "spy_missing"}
    spy_ok, spx_ok = spy["band"] == BAND_STRONG, spx["trade"]
    if spy_ok and spx_ok and spy["direction"] == spx["direction"]:
        return {"buy": True, "direction": spy["direction"], "reason": "agree"}
    if spy["trade"] and spx_ok and spy["direction"] != spx["direction"]:
        reason = "opposite"
    elif spx_ok and not spy_ok:
        reason = "spy_weak"
    elif spy_ok and not spx_ok:
        reason = "spx_weak"
    else:
        reason = "both_weak"
    return {"buy": False, "direction": None, "reason": reason}


def reading_line(name: str, s: dict | None, needs: int) -> str:
    if s is None:
        return f"{name}: not available"
    return f"{name}: {s['color']}, body {s['body']:.2f} / range {s['range']:.2f} = {pct(s['ratio'])} (needs {needs}%)"


def arm_message(spx_bar: tuple | None, spy_bar: tuple | None) -> dict:
    """Message 1, about 15:50:40: are we looking to arm? From the candles so far, so approximate."""
    spx = signal(*spx_bar) if spx_bar else None
    spy = signal(*spy_bar) if spy_bar else None
    lines = [reading_line("SPY so far", spy, 70), reading_line("SPX chart so far", spx, 60)]
    tail = "Candles still forming, so this can change. The decision comes right after 15:51:00 ET."
    if spx is None:
        return {"title": "NO PREVIEW: live quotes unavailable", "body": "\n".join(lines + [tail]), "priority": 3,
                "tags": "grey_question", "kind": "arm"}
    d = decide(spx, spy)
    if d["buy"]:
        k = strike_for(spx["close"], d["direction"])
        return {"title": f"ARM: likely {d['direction'].upper()} {k}", "priority": 4, "tags": "rotating_light", "kind": "arm",
                "body": "\n".join(lines + ["Both look strong. Open the SPX 0DTE chain now.", tail])}
    if spy is None and spx["trade"]:
        k = strike_for(spx["close"], spx["direction"])
        return {"title": f"MAYBE: SPX chart strong, SPY quote missing ({spx['direction'].upper()} {k})", "priority": 3,
                "tags": "grey_question", "kind": "arm", "body": "\n".join(lines + [tail])}
    return {"title": "STAND DOWN: likely no trade", "priority": 2, "tags": "zzz", "kind": "arm",
            "body": "\n".join(lines + [tail])}


WHY = {"spy_missing": "SPY's candle was not available, and the rule needs it.",
       "opposite": "SPY and the SPX chart point in opposite directions.",
       "spy_weak": "the SPX chart is strong but SPY is under 70%. Those days lost money in the backtest.",
       "spx_weak": "SPY is strong but the SPX chart is under 60%.",
       "both_weak": "neither candle is strong enough."}


def decision_message(day: date, spx: dict, spy: dict | None, late: bool = False, source: str = "") -> dict:
    """Message 2, right after 15:51:00: what to buy, or not to buy."""
    d = decide(spx, spy)
    lines = [reading_line("SPY 15:50 candle", spy, 70), reading_line("SPX 15:50 candle", spx, 60)]
    src = f"Data: {source}." if source else ""
    if not d["buy"]:
        body = "\n".join(lines + [f"No trade: {WHY[d['reason']]}", src]).strip()
        return {"title": "NO TRADE today", "body": body, "priority": 3, "tags": "no_entry_sign", "kind": "decision",
                "buy": False, "reason": d["reason"], "strike": None, "direction": None}
    spot = spx["close"]
    k, atm, side = strike_for(spot, d["direction"]), atm_of(spot), d["direction"].upper()
    body = "\n".join([f"SPXW {k} {side}, expires today ({day.strftime('%b')} {day.day})"] + lines + [
        f"SPX {spot:.2f} -> nearest 5 = {atm} -> 10 in the money = {k}",
        "Limit at the mid. Not filled by 15:52 -> raise to the ask. Hold to 16:00.",
        "Backtest 2021-2026: SPY at 70%+ made +$103 a trade, 55% won, worst -$2,210. Research, not advice.",
        src] + (["LATE: entering late made much less in the backtest."] if late else [])).strip()
    return {"title": f"BUY {side} {k}", "body": body, "priority": 5,
            "tags": "green_circle,chart_with_upwards_trend" if side == "CALL" else "red_circle,chart_with_downwards_trend",
            "kind": "decision", "buy": True, "reason": "agree", "strike": k, "direction": d["direction"]}


def forming(ticks: list) -> tuple | None:
    """(o, h, l, c) of the candle so far from (time, price) ticks; None with fewer than 3 ticks."""
    if len(ticks) < 3:
        return None
    p = [x[1] for x in ticks]
    return p[0], max(p), min(p), p[-1]


# ------------------------------------------------------------------------------------------------
# ntfy
# ------------------------------------------------------------------------------------------------
def topic() -> str | None:
    t = os.environ.get("NTFY_TOPIC")
    if t:
        return t.strip()
    if TOPIC_FILE.exists():
        return TOPIC_FILE.read_text().strip() or None
    return None


def push(msg: dict, dry_run: bool = False) -> None:
    t = topic()
    if dry_run or not t:
        if not t and not dry_run:
            print("no ntfy topic: run `setup` first (printing instead)", file=sys.stderr)
        print(f"[{msg.get('priority')}] {msg['title']}\n{msg['body']}\n", flush=True)
        return
    req = urllib.request.Request(f"{NTFY_SERVER}/{t}", data=msg["body"].encode("utf-8"), method="POST",
                                 headers={"Title": msg["title"], "Priority": str(msg.get("priority", 3)),
                                          "Tags": msg.get("tags", ""), "Click": CHART_LINK})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            print(f"pushed: {msg['title']}", flush=True)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"push failed ({type(e).__name__}: {e}); attempt {attempt + 1} of 3", file=sys.stderr, flush=True)
            time.sleep(1.5)
    print(f"[NOT PUSHED] {msg['title']}\n{msg['body']}", flush=True)


# ------------------------------------------------------------------------------------------------
# live data: CNBC (quote 1-4 s behind; finished 1-minute bars ~10-30 s after the minute) and Yahoo (1-minute bars)
# ------------------------------------------------------------------------------------------------
CNBC_QUOTE = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols={sym}"
              "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1")
CNBC_BARS = "https://ts-api.cnbc.com/harmony/app/bars/{sym}/1M/{d}{a}00/{d}{b}00/adjusted/EST5EDT.json"


def http_json(url: str, timeout: float = 6) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def cnbc_quote(sym: str = ".SPX", timeout: float = 6) -> tuple[float, datetime, str]:
    """(last price, its ET timestamp, market status such as REG_MKT)."""
    q = http_json(CNBC_QUOTE.format(sym=sym), timeout)["FormattedQuoteResult"]["FormattedQuote"][0]
    t = datetime.fromisoformat(q["last_time"]).astimezone(ET)
    return float(q["last"].replace(",", "")), t, q.get("curmktstatus", "")


def cnbc_bars(day: date, a: str = "1545", b: str = "1600", sym: str = ".SPX", timeout: float = 6) -> dict:
    """{(YYYY-MM-DD, HH:MM) ET: (o, h, l, c)} for CNBC's finished one-minute SPX bars between a and b (HHMM ET)."""
    j = http_json(CNBC_BARS.format(sym=sym, d=day.strftime("%Y%m%d"), a=a, b=b), timeout)
    out = {}
    for x in (j.get("barData") or {}).get("priceBars") or []:
        t = x["tradeTime"]                                      # YYYYMMDDHHMMSS, ET, the minute's start
        out[(f"{t[:4]}-{t[4:6]}-{t[6:8]}", f"{t[8:10]}:{t[10:12]}")] = tuple(
            float(x[k]) for k in ("open", "high", "low", "close"))
    return out


def fetch_chart(rng: str = "1d") -> dict:
    last = None
    for host in YAHOO_HOSTS:
        try:
            req = urllib.request.Request(host + YAHOO_PATH.format(rng=rng), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                res = json.load(r)["chart"]["result"][0]
            if "timestamp" not in res:
                res["timestamp"] = []
            return res
        except Exception as e:                                   # try the other host, then give up
            last = e
    raise RuntimeError(f"Yahoo chart unavailable ({type(last).__name__}: {last})")


def minute_bars(res: dict) -> dict:
    """{(YYYY-MM-DD, HH:MM) ET: (o, h, l, c)} for complete, minute-aligned bars only (skips Yahoo's live tick row)."""
    out = {}
    q = res.get("indicators", {}).get("quote", [{}])[0]
    for i, ts in enumerate(res.get("timestamp") or []):
        if ts % 60:
            continue
        vals = [q.get(k, [None] * (i + 1))[i] for k in ("open", "high", "low", "close")]
        if any(v is None for v in vals):
            continue
        t = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ET)
        out[(t.strftime("%Y-%m-%d"), t.strftime("%H:%M"))] = tuple(float(v) for v in vals)
    return out


def session_today(res: dict, today: date) -> str:
    """'open' if today is a full session, 'closed' if not a session, 'half' if it ends before 16:00 ET."""
    reg = (res.get("meta", {}).get("currentTradingPeriod") or {}).get("regular") or {}
    if "start" not in reg or "end" not in reg:
        return "open"                                              # unknown: let the bar check decide
    start = datetime.fromtimestamp(reg["start"], tz=timezone.utc).astimezone(ET)
    end = datetime.fromtimestamp(reg["end"], tz=timezone.utc).astimezone(ET)
    if start.date() != today:
        return "closed"
    return "half" if end.time() < dtime(16, 0) else "open"


# ------------------------------------------------------------------------------------------------
# log
# ------------------------------------------------------------------------------------------------
LOG_FIELDS = ["date", "sent_at_et", "kind", "open", "high", "low", "close", "body", "range", "ratio", "color",
              "trade", "spot", "strike", "option", "source", "note", "band"]


def band_of_row(r: dict) -> str:
    """The band of a logged candle, from its stored prices ('' if it has none)."""
    try:
        return signal(*(float(r[k]) for k in ("open", "high", "low", "close")))["band"]
    except (KeyError, TypeError, ValueError):
        return ""


def migrate_header(path: Path, fields: list) -> None:
    """If a CSV was written with an older column list, rewrite it with the current one (old rows keep their values;
    a missing band is worked out from the row's own prices)."""
    if not path.exists():
        return
    with path.open(newline="") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames == fields:
            return
        rows = list(rd)
    for r in rows:
        if "band" in fields and not r.get("band") and r.get("kind") in ("signal", "no_trade"):
            r["band"] = band_of_row(r)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    os.replace(tmp, path)


def log_row(row: dict) -> None:
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    migrate_header(LOG_FILE, LOG_FIELDS)
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LOG_FIELDS})


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------
def now_et() -> datetime:
    return datetime.now(ET)


def sleep_until(t: dtime) -> None:
    while True:
        n = now_et()
        target = n.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
        left = (target - n).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 30))


def decision(s: dict) -> tuple:
    """What the trader does: (trade?, direction, strike)."""
    return (s["trade"], s["direction"] if s["trade"] else None,
            strike_for(s["close"], s["direction"]) if s["trade"] else None)


def reading(s: dict) -> str:
    d = decision(s)
    return f"{pct(s['ratio'])} {s['color']}" + (f" -> {d[1].upper()} {d[2]}" if d[0] else " -> no trade")


def cmd_run(args) -> int:
    n = now_et()
    today = n.date()
    if today.weekday() >= 5:
        print("weekend: nothing to watch")
        return 0
    if n.time() >= dtime(16, 0):
        print("after 16:00 ET: too late for today's 15:50 candle")
        return 0
    if n.time() < dtime(15, 49, 30):
        print(f"waiting until 15:49:30 ET (now {n:%H:%M:%S} ET)", flush=True)
        sleep_until(dtime(15, 49, 30))

    # is today a full session? CNBC's market status first, Yahoo's trading period second
    status = None
    try:
        status = cnbc_quote()[2]
    except Exception as e:
        print(f"CNBC quote failed: {type(e).__name__}: {e}", flush=True)
    if status and status != "REG_MKT":
        state = "closed"
        try:
            state = session_today(fetch_chart("1d"), today)
        except RuntimeError:
            pass
        if state != "open":
            print(f"market not open at 15:49 (CNBC status {status}, Yahoo says {state}): nothing to watch")
            return 0

    late = now_et().time() > dtime(15, 52)
    key = (today.isoformat(), "15:50")

    # 1. message 1 while the candles form: ticks of the SPX index and of SPY stamped 15:50:00-15:50:59
    ticks, sticks = [], []
    if not args.no_preview and now_et().time() < FINAL_AFTER:
        sent = False
        while now_et().time() < FINAL_AFTER:
            t0 = time.time()
            for sym, box in ((".SPX", ticks), (SPY_SYM, sticks)):
                try:
                    px, ts, _ = cnbc_quote(sym, timeout=3)
                    if ts.date() == today and dtime(15, 50) <= ts.time() < FINAL_AFTER and (not box or ts > box[-1][0]):
                        box.append((ts, px))
                except Exception:
                    pass
            if not sent and now_et().time() >= PREVIEW_AT:
                msg1 = arm_message(forming(ticks), forming(sticks))
                push(msg1, args.dry_run)
                log_row({"date": today.isoformat(), "sent_at_et": now_et().strftime("%H:%M:%S"), "kind": "arm",
                         "source": "CNBC live quotes", "note": msg1["title"] + (" (dry run)" if args.dry_run else "")})
                sent = True
            time.sleep(max(0.0, 1.0 - (time.time() - t0)))
    sleep_until(FINAL_AFTER)

    # 2. message 2 from the finished candles: the SPX bar (CNBC every second, Yahoo every other second) and SPY's
    #    bar (CNBC). It waits up to SPY_WAIT seconds for SPY after the SPX bar is in, then decides without it.
    got = {}                                       # source -> (o, h, l, c)
    first = None
    spy_bar = None
    spx_at = None
    decided = checked = False
    i = 0
    while True:
        n = now_et()
        if "CNBC" not in got:
            try:
                b = cnbc_bars(today, "1549", "1552", timeout=4)
                if key in b:
                    got["CNBC"] = b[key]
            except Exception:
                pass
        if i % 2 == 0 and "Yahoo" not in got:
            try:
                res = fetch_chart("1d")
                yb = minute_bars(res)
                mt = res.get("meta", {}).get("regularMarketTime") or 0
                past = datetime.fromtimestamp(mt, tz=timezone.utc).astimezone(ET) >= n.replace(
                    hour=15, minute=51, second=0, microsecond=0)
                if key in yb and past:                     # Yahoo's clock is past 15:51: its 15:50 bar is closed
                    got["Yahoo"] = yb[key]
            except RuntimeError:
                pass
        if spy_bar is None and not decided:
            spy_bar = spy_candle(today)
        i += 1
        n = now_et()
        if first is None and got:
            first = next(iter(got))
            spx_at = n
        waited = first is not None and ((n - spx_at).total_seconds() >= SPY_WAIT or n.time() >= dtime(15, 52))
        if first is not None and not decided and (spy_bar is not None or waited):
            decide_and_log(today, got[first], first, spy_bar, args, late)
            decided = True
        if decided and not checked and len(got) == 2:
            cross_check(today, got, first, args)
            checked = True
        if decided and (checked or n.time() >= dtime(15, 52, 30)):
            if not checked:
                log_check(today, first, got, "second source unavailable")
            return after_alert(args)
        if first is None and n.time() >= GIVE_UP_AT:
            bar = forming(ticks) if len(ticks) >= 10 else None
            if bar:
                decide_and_log(today, bar, "CNBC live quotes (no official candle)", spy_bar or spy_candle(today), args, True)
                return after_alert(args)
            push({"title": "NO DECISION: data problem",
                  "body": "Couldn't read today's 15:50 SPX candle from CNBC or Yahoo. Check the 1-minute charts yourself.",
                  "priority": 4, "tags": "warning", "kind": "error"}, args.dry_run)
            log_row({"date": today.isoformat(), "sent_at_et": now_et().strftime("%H:%M:%S"), "kind": "error",
                     "note": "no 15:50 candle from CNBC or Yahoo by 15:53"})
            return 1
        time.sleep(1.0)


SPY_WAIT = 25                       # seconds to wait for SPY's candle once the SPX candle is in


def decide_and_log(today: date, spx_bar: tuple, source: str, spy_bar: tuple | None, args, late: bool) -> None:
    """Push message 2 first, then write the three log rows (the SPX-only reading, SPY's reading, the decision)."""
    spx = signal(*spx_bar)
    spy = signal(*spy_bar) if spy_bar else None
    sent = now_et()
    msg = decision_message(today, spx, spy, late, f"{source} and CNBC SPY 1-minute candles, read at {sent:%H:%M:%S} ET")
    push(msg, args.dry_run)
    try:
        finish(today, spx_bar, source, args, late, do_push=False)
        spy_step(today, spx_bar, args, give_up=True, bar=spy_bar, do_push=False)
        opt = (f"SPXW {today:%y%m%d} {msg['strike']}{'C' if msg['direction'] == 'call' else 'P'}" if msg["buy"] else "")
        log_row({"date": today.isoformat(), "sent_at_et": sent.strftime("%H:%M:%S"), "kind": "decision",
                 "trade": msg["buy"], "strike": msg["strike"] or "", "option": opt, "spot": f"{spx['close']:.2f}",
                 "source": source + " + CNBC SPY", "band": (spy or {}).get("band", ""),
                 "note": ("buy" if msg["buy"] else "no_trade: " + msg["reason"]) + (" (dry run)" if args.dry_run else "")})
    except Exception as e:                                  # the logs are a record only
        print(f"logging after the decision failed: {type(e).__name__}: {e}", flush=True)


# SPY's 15:50 candle as a second reading (backtests/spx_candle_spy): a follow-up push, logged as kind "spy"
SPY_SYM = "SPY"


def spy_candle(day: date) -> tuple | None:
    """SPY's finished 15:50 one-minute bar (o, h, l, c) from CNBC, or None. Never raises."""
    try:
        return cnbc_bars(day, "1549", "1552", sym=SPY_SYM, timeout=4).get((day.isoformat(), "15:50"))
    except Exception:
        return None


def spy_view(spx: dict, spy_bar: tuple) -> dict:
    """SPY's reading and how it relates to the SPX signal: agree, opposite, no_confirm, spy_only or none."""
    s = signal(*spy_bar)
    if spx["trade"] and s["trade"]:
        state = "agree" if s["direction"] == spx["direction"] else "opposite"
    elif spx["trade"]:
        state = "no_confirm"
    else:
        state = "spy_only" if s["trade"] else "none"
    return {"spy": s, "state": state}


def spy_message(spx: dict, view: dict) -> dict | None:
    """The follow-up push; None when neither chart signals (nothing to add to "no trade")."""
    s, st = view["spy"], view["state"]
    line = f"SPY 15:50 candle: {s['color'].upper()}, body {s['body']:.2f} / range {s['range']:.2f} = {pct(s['ratio'])}"
    if st == "agree":
        extra = ("SPY at 70%+ made +$103 a trade (t 2.84)." if s["band"] == BAND_STRONG else
                 "SPY at 60-70% on its own made nothing (-$4 a trade).")
        return {"title": f"SPY CONFIRMS: {pct(s['ratio'])} {s['color']} ({s['band']})",
                "body": f"{line}\nBoth charts agree. In the 2021-2026 backtest that combination made +$80 a trade "
                        f"(t 2.56). {extra}", "priority": 4, "tags": "white_check_mark", "kind": "spy"}
    if st == "no_confirm":
        return {"title": f"SPY does NOT confirm: only {pct(s['ratio'])}",
                "body": f"{line}\nYour SPX chart fired but SPY's candle did not. In the 2021-2026 backtest, days when "
                        "the SPX chart fired without SPY lost money (-$59 a trade, 203 trades). Logged either way.",
                "priority": 4, "tags": "warning", "kind": "spy"}
    if st == "opposite":
        return {"title": f"SPY points the OTHER way: {pct(s['ratio'])} {s['color']}",
                "body": f"{line}\nThe SPX chart and SPY disagree on direction. That never happened in the 2021-2026 "
                        "backtest, so there is no result to go by. Logged either way.",
                "priority": 4, "tags": "warning", "kind": "spy"}
    if st == "spy_only":
        return {"title": f"Still no trade: SPY {pct(s['ratio'])}, SPX chart {pct(spx['ratio'])}",
                "body": f"{line}\nSPY shows a strong candle but the SPX chart does not. That happened on only 15 days "
                        "in the 2021-2026 backtest (-$232 a trade): too few to mean anything.",
                "priority": 2, "tags": "zzz", "kind": "spy"}
    return None


def spy_step(today: date, spx_bar: tuple, args, give_up: bool = False, bar: tuple | None = None,
             do_push: bool = True) -> bool:
    """Log SPY's candle (read once here unless `bar` is given) and, if asked, push it. True when done. Never raises."""
    try:
        bar = bar or spy_candle(today)
        if bar is None and not give_up:
            return False
        spx = signal(*spx_bar)
        row = {"date": today.isoformat(), "sent_at_et": now_et().strftime("%H:%M:%S"), "kind": "spy", "source": "CNBC SPY"}
        if bar is None:
            if spx["trade"] and do_push:
                push({"title": "SPY candle not available", "body": "CNBC had no SPY 15:50 candle by 15:52:30, so there is "
                      "no second reading today.", "priority": 2, "tags": "grey_question", "kind": "spy"}, args.dry_run)
            row["note"] = "unavailable"
        else:
            v = spy_view(spx, bar)
            s = v["spy"]
            msg = spy_message(spx, v)
            if msg and do_push:
                push(msg, args.dry_run)
            row.update({k: s[k] for k in ("open", "high", "low", "close", "body", "range", "color", "trade", "band")})
            row["ratio"] = "" if s["ratio"] is None else f"{s['ratio']:.4f}"
            row["note"] = v["state"] + (" (dry run)" if args.dry_run else "")
        log_row(row)
    except Exception as e:
        print(f"SPY step failed: {type(e).__name__}: {e}", flush=True)
    return True


def todays_spy(day: date) -> dict | None:
    """The last logged SPY reading of that day (kind "spy" with prices), if any."""
    if not LOG_FILE.exists():
        return None
    out = None
    for r in csv.DictReader(LOG_FILE.open()):
        if r["date"] == day.isoformat() and r.get("kind") == "spy" and r.get("open") and "dry run" not in (r.get("note") or ""):
            out = r
    return out


def todays_decision(day: date) -> str:
    """'buy', 'no_trade' or '' from that day's message-2 row."""
    if not LOG_FILE.exists():
        return ""
    out = ""
    for r in csv.DictReader(LOG_FILE.open()):
        if r["date"] == day.isoformat() and r.get("kind") == "decision" and "dry run" not in (r.get("note") or ""):
            out = (r.get("note") or "").split(":")[0].strip()
    return out


def after_alert(args) -> int:
    """After the alert: update the two-feed log, then close out today's trade after 16:05 (if a signal was alerted)."""
    day = now_et().date()
    feeds_safe(args.dry_run)                    # today's real candle, and earlier days still missing the feed's
    rc = 0
    if todays_signal(day) and not getattr(args, "no_close", False):
        rc = cmd_close(argparse.Namespace(date=None, dry_run=args.dry_run, push=getattr(args, "push_close", False)))
        feeds_safe(args.dry_run)                # after the close: today's move, and the feed's candle if it is out
    return rc


def finish(today: date, bar: tuple, source: str, args, late: bool, do_push: bool = True) -> None:
    s = signal(*bar)
    spot = s["close"]                         # the 15:50 close = SPX at 15:51:00, the price the backtests used
    msg = final_message(today, s, spot)
    sent = now_et()
    msg["body"] += f"\nData: {source} 1-minute candle, read at {sent:%H:%M:%S} ET."
    if late and msg["kind"] == "signal":
        msg["body"] += f"\nLATE: this ran at {sent:%H:%M} ET. Entering late made much less in the backtest."
    if do_push:
        push(msg, args.dry_run)
    opt = (f"SPXW {today:%y%m%d} {msg['strike']}{'C' if s['direction'] == 'call' else 'P'}"
           if msg["strike"] else "")
    log_row({"date": today.isoformat(), "sent_at_et": sent.strftime("%H:%M:%S"), "kind": msg["kind"],
             **{k: s[k] for k in ("open", "high", "low", "close", "body", "range", "color", "trade")},
             "ratio": "" if s["ratio"] is None else f"{s['ratio']:.4f}", "spot": f"{spot:.2f}",
             "strike": msg["strike"] or "", "option": opt, "source": source,
             "note": "dry run" if args.dry_run else "", "band": s["band"]})


def cross_check(today: date, got: dict, first: str, args) -> int:
    other = next(k for k in got if k != first)
    s1, s2 = signal(*got[first]), signal(*got[other])
    d1, d2 = decision(s1), decision(s2)
    if d1[:2] != d2[:2]:                                   # trade/no trade or call/put differs: logged, not pushed
        log_check(today, first, got, f"DISAGREE: {first} {reading(s1)} / {other} {reading(s2)}")
        print(f"cross-check: {other} DISAGREES ({reading(s2)} vs {reading(s1)})", flush=True)
        return 0
    note = "agrees" if d1 == d2 else f"agrees on side; strike {d2[2]} vs {d1[2]} (rounding)"
    log_check(today, first, got, f"{other} {note} ({reading(s2)})")
    print(f"cross-check: {other} {note}", flush=True)
    return 0


def log_check(today: date, first: str, got: dict, note: str) -> None:
    row = {"date": today.isoformat(), "sent_at_et": now_et().strftime("%H:%M:%S"), "kind": "check",
           "source": ", ".join(got), "note": note}
    for k, b in got.items():
        if k != first:
            s = signal(*b)
            row.update({kk: s[kk] for kk in ("open", "high", "low", "close", "body", "range", "color", "trade")})
            row["ratio"] = "" if s["ratio"] is None else f"{s['ratio']:.4f}"
    log_row(row)


# ------------------------------------------------------------------------------------------------
# after the close: what the alerted trade made
# ------------------------------------------------------------------------------------------------
def cboe_snapshot() -> tuple[datetime | None, dict]:
    """Cboe's delayed SPX/SPXW quotes: (as-of time ET, {OCC symbol: option row}). About 15-16 minutes behind."""
    req = urllib.request.Request(CBOE_OPTIONS, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    d = json.loads(raw)["data"]
    asof = d.get("last_trade_time")
    asof = datetime.fromisoformat(asof).replace(tzinfo=ET) if asof else None
    return asof, {o["option"]: o for o in d.get("options", [])}


def occ(day: date, direction: str, strike: int) -> str:
    return f"SPXW{day:%y%m%d}{'C' if direction == 'call' else 'P'}{strike * 1000:08d}"


def todays_signal(day: date) -> dict | None:
    if not LOG_FILE.exists():
        return None
    for r in csv.DictReader(LOG_FILE.open()):
        if r["date"] == day.isoformat() and r["kind"] == "signal" and r.get("strike"):
            return r
    return None


CLOSE_FIELDS = ["date", "option", "direction", "strike", "quote_asof_et", "bid", "ask", "mid", "spx_close",
                "close_source", "settle_value", "pnl_at_ask", "pnl_at_mid", "my_price", "pnl_at_my_price", "note",
                "ratio", "band", "spy_ratio", "spy_band", "spy_state", "decision"]
FILLS_FILE = ALERT_DIR / "my_fills.csv"


def my_price(day: date) -> float | None:
    """The price you noted for that day's alert (`fill PRICE`), if any; the last one wins."""
    if not FILLS_FILE.exists():
        return None
    p = None
    for r in csv.DictReader(FILLS_FILE.open()):
        if r["date"] == day.isoformat():
            p = float(r["price"])
    return p


def cmd_fill(args) -> int:
    day = date.fromisoformat(args.date) if args.date else now_et().date()
    sig = todays_signal(day)
    if not sig:
        print(f"{day}: no signal alert logged")
        return 1
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    new = not FILLS_FILE.exists()
    with FILLS_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "option", "price", "noted_at_et"])
        w.writerow([day.isoformat(), sig["option"], f"{args.price:.2f}", now_et().strftime("%H:%M:%S")])
    print(f"noted {sig['option']} at {args.price:.2f}")
    return 0


def pnl(settle_value: float, paid: float) -> float:
    return round(100 * (settle_value - paid) - FEE, 2)


def settle(direction: str, strike: int, spx_close: float | None) -> float | None:
    if spx_close is None:
        return None
    return round(max(0.0, spx_close - strike) if direction == "call" else max(0.0, strike - spx_close), 2)


# Other strikes on the same signal, from the same Cboe snapshot: a forward record only (the rule stays ITM10).
LADDER_FILE = ALERT_DIR / "ladder_1550.csv"
LADDER = (("ITM20", 20), ("ITM15", 15), ("ITM10", 10), ("ITM5", 5), ("ATM", 0), ("OTM5", -5), ("OTM10", -10))
LADDER_FIELDS = ["date", "quote_asof_et", "contract", "option", "strike", "bid", "ask", "mid", "spx_close",
                 "settle_value", "pnl_at_ask", "pnl_at_mid"]


def ladder_rows(day: date, direction: str, atm: int, snap: dict, asof_txt: str, spx_close: float | None) -> list:
    out = []
    for name, itm in LADDER:
        k = atm - itm if direction == "call" else atm + itm
        sym = occ(day, direction, k)
        row = snap.get(sym)
        bid = ask = mid = None
        if row and row.get("ask"):
            bid, ask = float(row.get("bid") or 0), float(row["ask"])
            mid = round((bid + ask) / 2, 2) if bid else None
        sv = settle(direction, k, spx_close)
        out.append({"date": day.isoformat(), "quote_asof_et": asof_txt, "contract": name, "option": sym, "strike": k,
                    "bid": bid, "ask": ask, "mid": mid, "spx_close": spx_close, "settle_value": sv,
                    "pnl_at_ask": pnl(sv, ask) if sv is not None and ask else "",
                    "pnl_at_mid": pnl(sv, mid) if sv is not None and mid else ""})
    return out


def write_by_date(path: Path, fields: list, day: date, new_rows: list) -> list:
    """Replace that day's rows in a CSV keyed by date; returns every row."""
    rows = [] if not path.exists() else [r for r in csv.DictReader(path.open()) if r["date"] != day.isoformat()]
    rows += new_rows
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    return rows


def cmd_close(args) -> int:
    day = date.fromisoformat(args.date) if args.date else now_et().date()
    sig = todays_signal(day)
    if not sig:
        print(f"{day}: no signal alert logged, nothing to close")
        return 0
    direction = "call" if sig["option"].endswith("C") else "put"
    strike = int(sig["strike"])
    sym = occ(day, direction, strike)
    if day == now_et().date():
        sleep_until(dtime(16, 5, 30))

    # SPX close: CNBC's last value once the market has closed
    spx_close, src = None, ""
    if day != now_et().date():                          # a past day: CNBC's 15:59 bar close is the close
        try:
            b = cnbc_bars(day, "1559", "1600").get((day.isoformat(), "15:59"))
            if b:
                spx_close, src = b[3], "CNBC 15:59 bar close"
        except Exception as e:
            src = f"CNBC failed: {type(e).__name__}"
    for _ in range(30 if spx_close is None and day == now_et().date() else 0):
        try:
            px, ts, st = cnbc_quote()
            if ts.date() == day and ts.time() >= dtime(16, 0) or st not in ("REG_MKT", ""):
                spx_close, src = px, f"CNBC last at {ts:%H:%M:%S} ET ({st})"
                break
        except Exception as e:
            src = f"CNBC failed: {type(e).__name__}"
        time.sleep(10)

    # the contract's 15:51 bid/ask: Cboe's delayed snapshot once its as-of time reaches 15:51:00
    row, asof, note, snap = None, None, "", {}
    target = datetime.combine(day, dtime(15, 51), tzinfo=ET)
    deadline = time.time() + (9 * 60 if day == now_et().date() else 0)
    while True:
        try:
            asof, opts = cboe_snapshot()
            if asof and asof >= target:
                snap = opts
                row = opts.get(sym)
                note = "" if row else f"{sym} not in Cboe's file"
                break
            note = f"Cboe as-of {asof:%H:%M:%S}" if asof else "Cboe as-of unknown"
        except Exception as e:
            note = f"Cboe failed: {type(e).__name__}: {e}"
        if time.time() >= deadline:
            break
        time.sleep(15)

    bid = ask = mid = None
    if row and row.get("ask"):
        bid, ask = float(row.get("bid") or 0), float(row["ask"])
        mid = round((bid + ask) / 2, 2) if bid else None
    settle_value = settle(direction, strike, spx_close)
    out = {"date": day.isoformat(), "option": sig["option"], "direction": direction, "strike": strike,
           "quote_asof_et": f"{asof:%H:%M:%S}" if asof else "", "bid": bid, "ask": ask, "mid": mid,
           "spx_close": spx_close, "close_source": src, "settle_value": settle_value,
           "pnl_at_ask": pnl(settle_value, ask) if settle_value is not None and ask else "",
           "pnl_at_mid": pnl(settle_value, mid) if settle_value is not None and mid else "", "note": note,
           "ratio": sig.get("ratio", ""), "band": sig.get("band") or band_of_row(sig)}
    sp = todays_spy(day)
    if sp:
        out.update({"spy_ratio": sp.get("ratio", ""), "spy_band": sp.get("band", ""),
                    "spy_state": (sp.get("note") or "").split(" ")[0]})
    out["decision"] = todays_decision(day)
    mine = my_price(day)
    if mine is not None:
        out["my_price"] = mine
        out["pnl_at_my_price"] = pnl(settle_value, mine) if settle_value is not None else ""
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    rows = write_by_date(CLOSE_FILE, CLOSE_FIELDS, day, [out])
    fill_close_bands(rows)
    ladder = []
    if snap and sig.get("spot"):
        try:
            ladder = ladder_rows(day, direction, atm_of(float(sig["spot"])), snap, out["quote_asof_et"], spx_close)
            write_by_date(LADDER_FILE, LADDER_FIELDS, day, ladder)
        except Exception as e:                        # a forward record only: never block the close message
            print(f"ladder not logged: {type(e).__name__}: {e}")
            ladder = []

    done = [r for r in rows if r.get("pnl_at_ask") not in ("", None)]
    total = sum(float(r["pnl_at_ask"]) for r in done)
    wins = sum(float(r["pnl_at_ask"]) > 0 for r in done)
    side = direction.upper()
    if out["pnl_at_ask"] != "":
        v = float(out["pnl_at_ask"])
        title = f"Closed: {side} {strike} {'+' if v >= 0 else '-'}${abs(v):,.0f}" + (f" ({out['band']})" if out["band"] else "")
        body = (f"SPX closed {spx_close:,.2f} -> the {strike} {direction} settled at {settle_value:.2f}.\n"
                f"Bought at the 15:51 ask {ask:.2f} (Cboe, as of {out['quote_asof_et']} ET): "
                f"{'+' if v >= 0 else '-'}${abs(v):,.2f} per contract after ${FEE:.2f} fees.")
        if out["pnl_at_mid"] != "":
            body += f"\nAt the mid {mid:.2f}: {float(out['pnl_at_mid']):+,.2f}."
        if out.get("pnl_at_my_price") not in ("", None):
            body += f"\nAt your price {mine:.2f}: {float(out['pnl_at_my_price']):+,.2f}."
        body += (f"\nRunning total: {'+' if total >= 0 else '-'}${abs(total):,.2f} over {len(done)} trade(s), "
                 f"{wins} won (one contract each, at the ask).")
        mine_rows = [r for r in rows if r.get("pnl_at_my_price") not in ("", None)]
        if mine_rows:
            mt = sum(float(r["pnl_at_my_price"]) for r in mine_rows)
            mw = sum(float(r["pnl_at_my_price"]) > 0 for r in mine_rows)
            body += (f"\nYour watchlist total: {'+' if mt >= 0 else '-'}${abs(mt):,.2f} over {len(mine_rows)} "
                     f"trade(s) at your prices, {mw} won.")
        by_band = band_totals(done)
        if by_band:
            body += "\nBy band: " + "; ".join(by_band) + "."
        by_spy = spy_totals(done)
        if by_spy:
            body += "\nBy SPY: " + "; ".join(by_spy) + "."
        bought = [float(r["pnl_at_ask"]) for r in done if (r.get("decision") or "") == "buy"]
        if bought:
            bt = sum(bought)
            body += (f"\nMessage-2 BUY days only: {'+' if bt >= 0 else '-'}${abs(bt):,.0f} over {len(bought)}, "
                     f"{sum(x > 0 for x in bought)} won.")
        cheap = [f"{lbl} {r['strike']} cost ${100 * r['ask']:,.0f}, {float(r['pnl_at_ask']):+,.0f}"
                 for r in ladder for c, lbl in (("ITM5", "5 in"), ("ATM", "at the money")) if r["contract"] == c
                 and r["ask"] and r["pnl_at_ask"] != ""]
        if cheap:
            body += "\nCheaper strikes (logged only, not the rule): " + "; ".join(cheap) + "."
        prio, tags = 3, "moneybag" if v >= 0 else "small_red_triangle_down"
    else:
        title = f"Closed: {side} {strike}, couldn't price it"
        body = (f"SPX close: {spx_close if spx_close is not None else 'unknown'} ({src}). "
                f"15:51 quote: {note or 'missing'}. Check the trade yourself; logged what I have.")
        prio, tags = 3, "warning"
    if getattr(args, "push", False):
        push({"title": title, "body": body, "priority": prio, "tags": tags}, args.dry_run)
    else:
        print(f"[logged, not pushed] {title}\n{body}\n", flush=True)
    print(json.dumps(out))
    return 0


def fill_close_bands(rows: list | None = None) -> None:
    """Give every row of the close log its body % and band from the alert log (older rows were written without)."""
    if not CLOSE_FILE.exists():
        return
    rows = rows if rows is not None else list(csv.DictReader(CLOSE_FILE.open()))
    changed = False
    for r in rows:
        if r.get("band"):
            continue
        sig = todays_signal(date.fromisoformat(r["date"]))
        if sig:
            r["ratio"], r["band"] = sig.get("ratio", ""), sig.get("band") or band_of_row(sig)
            changed = changed or bool(r["band"])
    if changed:
        with CLOSE_FILE.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CLOSE_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in CLOSE_FIELDS})


def band_totals(done: list) -> list:
    """['70%+ +$1,234 over 5, 3 won', ...] from priced close rows; empty if no row has a band."""
    out = []
    for b in (BAND_STRONG, BAND_BORDER):
        v = [float(r["pnl_at_ask"]) for r in done if r.get("band") == b]
        if v:
            t = sum(v)
            out.append(f"{b} {'+' if t >= 0 else '-'}${abs(t):,.0f} over {len(v)}, {sum(x > 0 for x in v)} won")
    return out


def spy_totals(done: list) -> list:
    """['SPY confirmed +$1,234 over 5, 3 won', 'SPY did not confirm ...'] from priced close rows that have a SPY state."""
    out = []
    for label, states in (("SPY confirmed", ("agree",)), ("SPY did not confirm", ("no_confirm", "opposite"))):
        v = [float(r["pnl_at_ask"]) for r in done if (r.get("spy_state") or "") in states]
        if v:
            t = sum(v)
            out.append(f"{label} {'+' if t >= 0 else '-'}${abs(t):,.0f} over {len(v)}, {sum(x > 0 for x in v)} won")
    return out


# ------------------------------------------------------------------------------------------------
# the two-feed log: the real SPX 15:50 candle next to the Dukascopy feed's (what every backtest read)
# ------------------------------------------------------------------------------------------------
FEEDS_FIELDS = ["date", "real_source", "real_open", "real_high", "real_low", "real_close", "real_ratio", "real_dir",
                "real_band", "feed_open", "feed_high", "feed_low", "feed_close", "feed_ratio", "feed_dir", "feed_band",
                "o_1551", "c_1559", "move_pts", "note",
                "spy_open", "spy_high", "spy_low", "spy_close", "spy_ratio", "spy_dir", "spy_band"]


def feed_band(o: float, h: float, l: float, c: float) -> tuple:
    """(ratio, direction, band) of a Dukascopy candle with the backtests' own test: |c - o| >= 0.6 x (h - l) in floats."""
    rng, body = h - l, abs(c - o)
    d = "up" if c > o else "down" if c < o else "flat"
    if not rng > 0:
        return None, d, ""
    band = BAND_NONE if (d == "flat" or not body >= 0.6 * rng) else BAND_STRONG if body >= 0.7 * rng else BAND_BORDER
    return body / rng, d, band


def duka_decode(payload: bytes, day: date) -> tuple | None:
    """The 15:50 ET candle (o, h, l, c) from one Dukascopy day file, or None if that minute is not in it."""
    t = datetime.combine(day, dtime(15, 50), tzinfo=ET).astimezone(timezone.utc)
    if t.date() != day or not payload:
        return None
    want = t.hour * 3600 + t.minute * 60
    for secs, o, c, lo, hi, _vol in DUKA_RECORD.iter_unpack(lzma.decompress(payload)):
        if secs == want:
            return o / 1000, hi / 1000, lo / 1000, c / 1000
    return None


def duka_candle(day: date) -> tuple:
    """((o, h, l, c) or None, note). The day's file appears once the UTC day is over, sometimes later."""
    url = DUKA_URL.format(y=day.year, m0=day.month - 1, d=day.day)
    note = ""
    for attempt in range(5):                                    # 503s and dropped connections are routine here
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": DUKA_UA}), timeout=15) as r:
                bar = duka_decode(r.read(), day)
            return bar, "" if bar else "feed file has no 15:50 bar yet"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "feed file not out yet"
            note = f"feed HTTP {e.code}"
        except Exception as e:                                  # transient: the server drops connections often
            note = f"feed fetch failed: {type(e).__name__}"
        time.sleep(2 * (attempt + 1))
    return None, note


def read_feeds() -> dict:
    if not FEEDS_FILE.exists():
        return {}
    return {r["date"]: r for r in csv.DictReader(FEEDS_FILE.open())}


def write_feeds(rows: dict) -> None:
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FEEDS_FILE.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEEDS_FIELDS)
        w.writeheader()
        for d in sorted(rows):
            w.writerow({k: rows[d].get(k, "") for k in FEEDS_FIELDS})
    os.replace(tmp, FEEDS_FILE)


def feeds_row(day: date, row: dict | None = None, real: tuple | None = None, source: str = "",
              cnbc=None, duka=None, spy=None) -> dict:
    """Fill whatever is still missing in one day's row. `cnbc`, `duka` and `spy` are the fetchers (swapped out in tests)."""
    row = dict(row or {"date": day.isoformat()})
    cnbc, duka, spy = cnbc or cnbc_bars, duka or duka_candle, spy or spy_candle
    if not row.get("spy_ratio"):
        sb = spy(day)
        if sb:
            ss = signal(*sb)
            row.update({"spy_open": ss["open"], "spy_high": ss["high"], "spy_low": ss["low"], "spy_close": ss["close"],
                        "spy_ratio": "" if ss["ratio"] is None else f"{ss['ratio']:.4f}",
                        "spy_dir": {"call": "up", "put": "down"}.get(ss["direction"], "flat"), "spy_band": ss["band"]})
    bars = None
    if not row.get("real_ratio") or not row.get("move_pts"):
        if real is None or not row.get("move_pts"):
            try:
                bars = cnbc(day, "1549", "1600")
            except Exception as e:
                row["note"] = f"CNBC failed: {type(e).__name__}"
    if not row.get("real_ratio"):
        if real is None and bars:
            real, source = bars.get((day.isoformat(), "15:50")), "CNBC"
        if real:
            s = signal(*real)
            row.update({"real_source": source, "real_open": s["open"], "real_high": s["high"], "real_low": s["low"],
                        "real_close": s["close"], "real_ratio": "" if s["ratio"] is None else f"{s['ratio']:.4f}",
                        "real_dir": {"call": "up", "put": "down"}.get(s["direction"], "flat"), "real_band": s["band"]})
    if not row.get("move_pts") and bars and row.get("real_dir"):
        a, b = bars.get((day.isoformat(), "15:51")), bars.get((day.isoformat(), "15:59"))
        if a and b:
            sign = {"up": 1, "down": -1}.get(row["real_dir"], 0)
            row.update({"o_1551": f"{a[0]:.2f}", "c_1559": f"{b[3]:.2f}", "move_pts": f"{sign * (b[3] - a[0]):.2f}"})
    if not row.get("feed_ratio"):
        bar, note = duka(day)
        if bar:
            ratio, d, band = feed_band(*bar)
            row.update({"feed_open": bar[0], "feed_high": bar[1], "feed_low": bar[2], "feed_close": bar[3],
                        "feed_ratio": "" if ratio is None else f"{ratio:.4f}", "feed_dir": d, "feed_band": band,
                        "note": ""})
        elif note:
            row["note"] = note
    return row


def feeds_update(days: int = 7, dry_run: bool = False, deadline: float | None = None) -> list:
    """Complete the last `days` weekdays (oldest first). Stops quietly at `deadline` (a time.time() value)."""
    rows = read_feeds()
    logged = {}
    if LOG_FILE.exists():
        for r in csv.DictReader(LOG_FILE.open()):
            if r.get("kind") in ("signal", "no_trade") and r.get("open") and "dry run" not in (r.get("note") or ""):
                logged.setdefault(r["date"], r)
    today, d, want = now_et().date(), now_et().date(), []
    while len(want) < days:
        if d.weekday() < 5:
            want.append(d)
        d -= timedelta(days=1)
    out = []
    for day in reversed(want):
        if deadline is not None and time.time() >= deadline:
            break
        k = day.isoformat()
        row = rows.get(k)
        if row and row.get("real_ratio") and row.get("feed_ratio") and row.get("move_pts") and row.get("spy_ratio"):
            continue
        if day == today and now_et().time() < FINAL_AFTER:
            continue                                            # today's candle is not finished yet
        lg = logged.get(k)
        real = tuple(float(lg[x]) for x in ("open", "high", "low", "close")) if lg else None
        new = feeds_row(day, row, real, (lg or {}).get("source", ""))
        if new.get("real_ratio") or new.get("feed_ratio") or new.get("spy_ratio"):
            rows[k] = new
            out.append(new)
    if out and not dry_run:
        write_feeds(rows)
    return out


def feeds_safe(dry_run: bool = False) -> None:
    """The log is a record only: it must never break or delay the alert or the close message."""
    try:
        for r in feeds_update(7, dry_run, deadline=time.time() + 90):
            print(f"feeds {r['date']}: real {r.get('real_ratio') or '-'} {r.get('real_band') or ''} | "
                  f"SPY {r.get('spy_ratio') or '-'} {r.get('spy_band') or ''} | "
                  f"feed {r.get('feed_ratio') or '-'} {r.get('feed_band') or ''} | move {r.get('move_pts') or '-'} "
                  f"{r.get('note') or ''}", flush=True)
    except Exception as e:
        print(f"feeds log not updated: {type(e).__name__}: {e}", flush=True)


def cmd_feeds(args) -> int:
    fill_close_bands()
    done = feeds_update(args.days, args.dry_run)
    rows = read_feeds()
    for r in done:
        rows.setdefault(r["date"], r)
    print(f"{'date':<11} {'real %':>7} {'band':<10} {'SPY %':>7} {'band':<10} {'feed %':>7} {'band':<10} {'move':>8}  note")
    for k in sorted(rows)[-max(args.days, 10):]:
        r = rows[k]
        f = lambda x: f"{float(x) * 100:.0f}%" if x else "-"
        print(f"{k:<11} {f(r.get('real_ratio')):>7} {r.get('real_band', ''):<10} {f(r.get('spy_ratio')):>7} "
              f"{r.get('spy_band') or '':<10} {f(r.get('feed_ratio')):>7} "
              f"{r.get('feed_band', ''):<10} {r.get('move_pts') or '-':>8}  {r.get('note', '')}")
    print(f"{len(done)} day(s) updated{' (dry run: nothing written)' if args.dry_run else ''}; {len(rows)} in the log")
    return 0


def cmd_replay(args) -> int:
    fwd = {}
    if FORWARD_LOG.exists():
        for r in csv.DictReader(FORWARD_LOG.open()):
            if r.get("source") == "SPX_robinhood" and r.get("o_1550"):
                fwd[r["date"]] = signal(*(float(r[k]) for k in ("o_1550", "h_1550", "l_1550", "c_1550")))
    try:
        yb = minute_bars(fetch_chart("7d"))
    except RuntimeError as e:
        print(f"Yahoo: {e}")
        yb = {}
    d = now_et().date()
    days = []
    while len(days) < 7:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    print(f"{'date':<11} {'CNBC':<26} {'Yahoo':<26} {'forward log (Robinhood)':<26}")
    for d in reversed(days):
        try:
            cb = cnbc_bars(d, "1549", "1552")
        except Exception as e:
            cb = {}
        k = (d.isoformat(), "15:50")
        cells = [reading(signal(*src[k])) if k in src else "-" for src in (cb, yb)]
        cells.append(reading(fwd[d.isoformat()]) if d.isoformat() in fwd else "-")
        print(f"{d.isoformat():<11} " + " ".join(f"{c:<26}" for c in cells))
    return 0


def cmd_setup(args) -> int:
    t = topic()
    if not t:
        t = "spx1550-" + secrets.token_hex(8)
        ALERT_DIR.mkdir(parents=True, exist_ok=True)
        TOPIC_FILE.write_text(t + "\n")
        print(f"created a private topic and saved it to {TOPIC_FILE.relative_to(ROOT)}")
    print(f"ntfy topic: {t}\n"
          f"1. Install the ntfy app (iPhone App Store / Google Play: 'ntfy').\n"
          f"2. Tap + and subscribe to the topic above (server {NTFY_SERVER}).\n"
          f"3. Run: tools/spx_1550_alert.py test-push\n"
          f"Anyone who knows the topic name can read it, so keep it to yourself.")
    return 0


def cmd_test_push(args) -> int:
    if not topic():
        print("no topic yet: run setup first")
        return 1
    push({"title": "Test: SPX 15:50 alerts are set up",
          "body": "On trading days you'll get two messages: ARM or STAND DOWN around 15:50:40 ET (12:50 PT), then "
                  "BUY CALL/PUT <strike> or NO TRADE right after 15:51:00. Example:\nBUY CALL 7695",
          "priority": 3, "tags": "white_check_mark"})
    return 0


def cmd_selftest(args) -> int:
    # the one-pager's example: 78% green -> call 7695
    s = signal(7700.00, 7704.00, 7699.50, 7703.50)
    assert s["trade"] and s["direction"] == "call" and abs(s["ratio"] - 3.5 / 4.5) < 1e-12
    assert strike_for(7703.50, "call") == 7695 and strike_for(7703.50, "put") == 7715
    assert atm_of(7702.49) == 7700 and atm_of(7702.50) == 7705 and atm_of(7697.50) == 7700
    # exactly 60% counts; just under does not; float32 noise is rounded away
    assert signal(100.00, 105.00, 100.00, 103.00)["trade"]
    assert not signal(100.00, 105.00, 100.00, 102.99)["trade"]
    assert signal(7572.89013671875, 7577.39013671875, 7572.72021484375, 7575.70996094)["trade"]
    # red, flat and zero-range candles
    r = signal(100.0, 100.5, 96.0, 96.5)
    assert r["trade"] and r["direction"] == "put"
    assert not signal(100.0, 101.0, 99.0, 100.0)["trade"]
    assert not signal(100.0, 100.0, 100.0, 100.0)["trade"] and signal(100, 100, 100, 100)["ratio"] is None
    # messages
    m = final_message(date(2026, 11, 9), s, 7703.50)
    assert m["kind"] == "signal" and m["title"] == "BUY CALL 7695 - SPX 15:50 signal (70%+)" and "Nov 9" in m["body"]
    assert "Band 70%+" in m["body"] and s["band"] == BAND_STRONG
    # bands: 60% up to (not including) 70% is borderline; exactly 70% is strong; under 60% and flat are no trade
    assert signal(100.00, 105.00, 100.00, 103.00)["band"] == BAND_BORDER
    assert signal(100.00, 105.00, 100.00, 103.49)["band"] == BAND_BORDER
    assert signal(100.00, 105.00, 100.00, 103.50)["band"] == BAND_STRONG
    assert signal(100.00, 105.00, 100.00, 102.99)["band"] == BAND_NONE
    assert signal(100.0, 101.0, 99.0, 100.0)["band"] == BAND_NONE and signal(100, 100, 100, 100)["band"] == ""
    bm = final_message(date(2026, 11, 9), signal(7565.54, 7565.54, 7560.48, 7562.42), 7562.42)
    assert bm["title"] == "BUY PUT 7570 - SPX 15:50 signal (60-70%, borderline)" and "BORDERLINE" in bm["body"]
    assert band_of_row({"open": "7565.54", "high": "7565.54", "low": "7560.48", "close": "7562.42"}) == BAND_BORDER
    assert band_of_row({"open": ""}) == ""
    assert band_totals([{"pnl_at_ask": "985.91", "band": BAND_BORDER}, {"pnl_at_ask": "-200", "band": BAND_STRONG},
                        {"pnl_at_ask": "50.5", "band": BAND_STRONG}, {"pnl_at_ask": "1", "band": ""}]) == \
        ["70%+ -$150 over 2, 1 won", "60-70% +$986 over 1, 1 won"]
    # the Dukascopy feed: field order is seconds, open, close, low, high; the backtests' float test
    assert feed_band(7565.9, 7566.0, 7560.0, 7562.4)[1:] == ("down", BAND_NONE)          # 58%
    assert feed_band(100.0, 105.0, 100.0, 103.0)[2] == BAND_BORDER and feed_band(100.0, 105.0, 100.0, 103.5)[2] == BAND_STRONG
    assert feed_band(1.0, 1.0, 1.0, 1.0) == (None, "flat", "")
    for dd, hh in ((date(2026, 11, 9), 20), (date(2026, 10, 30), 19)):                 # EST and EDT
        blob = lzma.compress(DUKA_RECORD.pack(hh * 3600 + 49 * 60, 1, 1, 1, 1, 0.0)
                             + DUKA_RECORD.pack(hh * 3600 + 50 * 60, 7565900, 7562400, 7560000, 7566000, 1.5))
        assert duka_decode(blob, dd) == (7565.9, 7566.0, 7560.0, 7562.4)
    assert duka_decode(lzma.compress(DUKA_RECORD.pack(60, 1, 1, 1, 1, 0.0)), date(2026, 11, 9)) is None
    assert duka_decode(b"", date(2026, 11, 9)) is None
    # one day's two-feed row, with stand-in fetchers: real 62% (borderline), feed 58% (no trade), move +13.44
    dq = date(2026, 11, 9)
    fake_cnbc = lambda day, a, b: {("2026-11-09", "15:50"): (7565.54, 7565.54, 7560.48, 7562.42),
                                   ("2026-11-09", "15:51"): (7562.40, 7563.0, 7560.0, 7561.0),
                                   ("2026-11-09", "15:59"): (7550.0, 7551.0, 7548.0, 7548.96)}
    no_spy = lambda day: None
    fr = feeds_row(dq, None, None, "", cnbc=fake_cnbc, duka=lambda day: ((7565.9, 7566.0, 7560.0, 7562.4), ""), spy=no_spy)
    assert fr["real_band"] == BAND_BORDER and fr["real_dir"] == "down" and fr["real_ratio"] == "0.6166"
    assert fr["feed_band"] == BAND_NONE and fr["feed_ratio"] == "0.5833" and fr["move_pts"] == "13.44"
    part = feeds_row(dq, None, (7565.54, 7565.54, 7560.48, 7562.42), "CNBC", cnbc=lambda *a: {},
                     duka=lambda day: (None, "feed file not out yet"), spy=no_spy)
    assert part["real_band"] == BAND_BORDER and not part.get("feed_ratio") and part["note"] == "feed file not out yet"
    assert not part.get("move_pts")
    full = feeds_row(dq, part, None, "", cnbc=fake_cnbc, duka=lambda day: ((7565.9, 7566.0, 7560.0, 7562.4), ""),
                     spy=lambda day: (756.30, 756.31, 755.80, 755.95))
    assert full["feed_band"] == BAND_NONE and full["move_pts"] == "13.44" and full["note"] == "" and full["real_source"] == "CNBC"
    assert not part.get("spy_ratio") and full["spy_ratio"] == "0.6863" and full["spy_dir"] == "down" and full["spy_band"] == BAND_BORDER
    # SPY as a second reading: the five states and their messages (sub-penny prints are rounded to cents first)
    up = signal(7700.00, 7704.00, 7699.50, 7703.50)                     # SPX 78% green
    weak = signal(7700.0, 7704.0, 7699.0, 7701.0)                       # SPX 20%: no trade
    va = spy_view(up, (770.00, 770.4049, 769.95, 770.35))               # 35 / 45 cents = 78% green
    assert va["state"] == "agree" and va["spy"]["band"] == BAND_STRONG
    ma = spy_message(up, va)
    assert ma["title"] == "SPY CONFIRMS: 78% green (70%+)" and "+$80 a trade" in ma["body"] and "+$103" in ma["body"]
    vb = spy_view(up, (770.00, 770.50, 770.00, 770.32))                 # 64%: agrees, in the 60-70% band
    assert vb["state"] == "agree" and "made nothing" in spy_message(up, vb)["body"]
    vn = spy_view(up, (770.00, 770.50, 770.00, 770.20))                 # 40%
    assert vn["state"] == "no_confirm" and spy_message(up, vn)["title"] == "SPY does NOT confirm: only 40%"
    vo = spy_view(up, (770.40, 770.50, 770.00, 770.05))                 # 70% red against a green SPX candle
    assert vo["state"] == "opposite" and "OTHER way" in spy_message(up, vo)["title"]
    vs = spy_view(weak, (770.00, 770.50, 770.00, 770.40))
    assert vs["state"] == "spy_only" and spy_message(weak, vs)["priority"] == 2
    assert spy_view(weak, (770.00, 770.50, 770.00, 770.10))["state"] == "none"
    assert spy_message(weak, spy_view(weak, (770.00, 770.50, 770.00, 770.10))) is None
    assert spy_view(weak, (770.0, 770.0, 770.0, 770.0))["state"] == "none"            # a flat SPY bar
    for mm in (ma, spy_message(up, vn), spy_message(up, vo), spy_message(weak, vs)):
        mm["title"].encode("latin-1")
    assert CNBC_BARS.format(sym="SPY", d="20261109", a="1549", b="1552").endswith("/bars/SPY/1M/20261109154900/20261109155200/adjusted/EST5EDT.json")
    assert CNBC_BARS.format(sym=".SPX", d="20261109", a="1549", b="1552").endswith("/bars/.SPX/1M/20261109154900/20261109155200/adjusted/EST5EDT.json")
    # the rule and the two messages
    spx_up, spx_border = signal(7700.00, 7704.00, 7699.50, 7703.50), signal(7600.00, 7605.00, 7600.00, 7603.10)   # 78%, 62%
    spy80, spy64 = signal(770.00, 770.50, 770.00, 770.40), signal(770.00, 770.50, 770.00, 770.32)
    spy40, spy80dn = signal(770.00, 770.50, 770.00, 770.20), signal(770.40, 770.50, 770.00, 770.00)
    assert decide(spx_up, spy80) == {"buy": True, "direction": "call", "reason": "agree"}
    assert decide(spx_border, spy80)["buy"]                                  # SPX 62% is enough when SPY is 80%
    assert decide(spx_up, spy64) == {"buy": False, "direction": None, "reason": "spy_weak"}     # SPY 60-70% is not enough
    assert decide(spx_up, spy40)["reason"] == "spy_weak" and decide(spx_up, None)["reason"] == "spy_missing"
    assert decide(weak, spy80)["reason"] == "spx_weak" and decide(weak, spy40)["reason"] == "both_weak"
    assert decide(spx_up, spy80dn)["reason"] == "opposite" and not decide(spx_up, spy80dn)["buy"]
    exact70 = signal(770.00, 770.50, 770.00, 770.35)
    assert exact70["band"] == BAND_STRONG and decide(spx_up, exact70)["buy"]
    dm = decision_message(date(2026, 11, 10), spx_up, spy80, False, "CNBC")
    assert dm["title"] == "BUY CALL 7695" and dm["buy"] and dm["strike"] == 7695 and "SPXW 7695 CALL" in dm["body"]
    assert "needs 70%" in dm["body"] and "needs 60%" in dm["body"] and "Research, not advice" in dm["body"]
    dp = decision_message(date(2026, 11, 10), signal(7705.0, 7705.0, 7700.0, 7700.5), spy80dn)
    assert dp["title"] == "BUY PUT 7710" and dp["direction"] == "put"
    dn = decision_message(date(2026, 11, 10), spx_up, spy40)
    assert dn["title"] == "NO TRADE today" and not dn["buy"] and dn["strike"] is None and "under 70%" in dn["body"]
    assert "not available" in decision_message(date(2026, 11, 10), spx_up, None)["body"]
    assert "LATE" in decision_message(date(2026, 11, 10), spx_up, spy80, True)["body"]
    am = arm_message((7700.00, 7704.00, 7699.50, 7703.50), (770.00, 770.50, 770.00, 770.40))
    assert am["title"] == "ARM: likely CALL 7695" and "SPY so far" in am["body"]
    assert arm_message((7700.00, 7704.00, 7699.50, 7703.50), (770.00, 770.50, 770.00, 770.20))["title"] == "STAND DOWN: likely no trade"
    assert arm_message((7700.0, 7704.0, 7699.0, 7701.0), (770.00, 770.50, 770.00, 770.40))["title"] == "STAND DOWN: likely no trade"
    assert arm_message((7700.00, 7704.00, 7699.50, 7703.50), None)["title"].startswith("MAYBE: SPX chart strong")
    assert arm_message(None, None)["title"].startswith("NO PREVIEW")
    for mm in (dm, dp, dn, am, arm_message(None, None), arm_message((7700.00, 7704.00, 7699.50, 7703.50), None)):
        mm["title"].encode("latin-1")
    assert forming([(1, 5.0), (2, 7.0), (3, 6.0)]) == (5.0, 7.0, 5.0, 6.0) and forming([(1, 5.0), (2, 7.0)]) is None
    assert CNBC_QUOTE.format(sym="SPY").count("symbols=SPY") == 1 and "{" not in CNBC_QUOTE.format(sym=".SPX")
    assert spy_totals([{"pnl_at_ask": "100", "spy_state": "agree"}, {"pnl_at_ask": "-50.5", "spy_state": "agree"},
                       {"pnl_at_ask": "-200", "spy_state": "no_confirm"}, {"pnl_at_ask": "5", "spy_state": ""}]) == \
        ["SPY confirmed +$50 over 2, 1 won", "SPY did not confirm -$200 over 1, 0 won"]
    m.update(final_message(date(2026, 11, 9), signal(100, 101, 99, 100.2), 100.2))
    assert m["kind"] == "no_trade" and m["strike"] is None
    for msg in (final_message(date(2026, 11, 9), s, 7703.5), preview_message(7700, 7704, 7699.5, 7703.5)):
        msg["title"].encode("latin-1")                            # HTTP headers must be latin-1
    # bar parsing keeps aligned complete bars and drops Yahoo's live tick row and empty bars
    t0 = int(datetime(2026, 11, 9, 15, 50, tzinfo=ET).timestamp())
    res = {"timestamp": [t0 - 60, t0, t0 + 60, t0 + 67],
           "indicators": {"quote": [{"open": [1, 2, None, 4], "high": [1, 3, None, 4], "low": [1, 1, None, 4],
                                     "close": [1, 2.5, None, 4]}]}}
    b = minute_bars(res)
    assert set(b) == {("2026-11-09", "15:49"), ("2026-11-09", "15:50")} and b[("2026-11-09", "15:50")][3] == 2.5
    # session states
    def per(start, end):
        return {"meta": {"currentTradingPeriod": {"regular": {"start": int(start.timestamp()),
                                                              "end": int(end.timestamp())}}}}
    d = date(2026, 11, 27)
    assert session_today(per(datetime(2026, 11, 27, 9, 30, tzinfo=ET), datetime(2026, 11, 27, 13, tzinfo=ET)), d) == "half"
    assert session_today(per(datetime(2026, 11, 25, 9, 30, tzinfo=ET), datetime(2026, 11, 25, 16, tzinfo=ET)), d) == "closed"
    assert session_today(per(datetime(2026, 11, 27, 9, 30, tzinfo=ET), datetime(2026, 11, 27, 16, tzinfo=ET)), d) == "open"
    assert occ(date(2026, 11, 9), "call", 7695) == "SPXW261109C07695000"
    assert occ(date(2026, 11, 9), "put", 7405) == "SPXW261109P07405000"
    assert pnl(21.43, 19.30) == 212.91 and pnl(0.0, 10.0) == -1000.09
    # the strike ladder: puts are in the money above the ATM strike, calls below
    snap = {occ(date(2026, 11, 9), "put", 7570): {"bid": 9.8, "ask": 10.2},
            occ(date(2026, 11, 9), "put", 7560): {"bid": 3.1, "ask": 3.3}}
    lad = {r["contract"]: r for r in ladder_rows(date(2026, 11, 9), "put", 7560, snap, "15:51:37", 7549.94)}
    assert lad["ITM10"]["strike"] == 7570 and lad["ITM10"]["pnl_at_ask"] == pnl(20.06, 10.2)
    assert lad["ATM"]["strike"] == 7560 and lad["ATM"]["settle_value"] == 10.06 and lad["ATM"]["mid"] == 3.2
    assert lad["OTM10"]["strike"] == 7550 and lad["OTM10"]["ask"] is None and lad["OTM10"]["pnl_at_ask"] == ""
    assert [r["strike"] for r in ladder_rows(date(2026, 11, 9), "call", 7700, {}, "", None)] == \
        [7680, 7685, 7690, 7695, 7700, 7705, 7710]
    assert settle("call", 7695, 7703.5) == 8.5 and settle("put", 7695, 7703.5) == 0.0 and settle("put", 1, None) is None
    print("selftest passed")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--no-preview", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-close", action="store_true")
    r.add_argument("--push-close", action="store_true", help="also push the after-close result")
    fl = sub.add_parser("fill")
    fl.add_argument("price", type=float)
    fl.add_argument("--date")
    c = sub.add_parser("close")
    c.add_argument("--date")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--push", action="store_true", help="push the result as well as logging it")
    fe = sub.add_parser("feeds")
    fe.add_argument("--days", type=int, default=7)
    fe.add_argument("--dry-run", action="store_true")
    for name in ("replay", "setup", "test-push", "selftest"):
        sub.add_parser(name)
    a = p.parse_args(argv)
    return {"run": cmd_run, "close": cmd_close, "fill": cmd_fill, "feeds": cmd_feeds, "replay": cmd_replay,
            "setup": cmd_setup, "test-push": cmd_test_push, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
