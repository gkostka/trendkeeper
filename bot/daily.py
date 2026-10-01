"""The daily job: update prices, check them, run every strategy, log the day, write the status, notify, ping.

    python -m bot.daily [CONFIG]

Every strategy is rebuilt from its start date on each run, rather than stepped from a saved state: the engine runs
the whole history in about a second, nothing saved can drift from the prices, and missed days catch up for free.
What was advised each day is kept in the decision log, which revised prices can't change.
"""
import hashlib
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from bot import config, data, engine, notify, store

NY = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
REPO = Path(__file__).resolve().parent.parent
CROSS_CHECK_TOLERANCE = 0.001
NEAR = 0.01
REFETCH_DAYS = 10


@dataclass
class Run:
    day: pd.Timestamp
    now: datetime
    alerts: dict[str, str] = field(default_factory=dict)
    held_back: str | None = None
    decisions: dict[str, dict] = field(default_factory=dict)
    closes: dict[str, float] = field(default_factory=dict)
    fx: dict[str, pd.Series] = field(default_factory=dict)  # units of each report currency per base unit
    track: dict[str, dict] = field(default_factory=dict)
    history: dict[str, pd.Series] = field(default_factory=dict)  # whole backtests, base currency  # backtest return a year in USD, by strategy and years


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "describe", "--always", "--dirty"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def next_xetra_open(day: pd.Timestamp, holidays, now: datetime | None = None) -> pd.Timestamp:
    """The first Xetra open after `day`'s US close that is still ahead of `now` (a late run skips a passed one)."""
    d = day + pd.Timedelta(days=1)
    while d.weekday() >= 5 or d.date() in holidays or (
            now and datetime.combine(d.date(), datetime.min.time(), BERLIN).replace(hour=9) <= now):
        d += pd.Timedelta(days=1)
    return d


def expected_us_day(now: datetime) -> pd.Timestamp:
    """The last US weekday whose close should be in by `now` (US holidays aren't known, so one is tolerated)."""
    d = pd.Timestamp(now.astimezone(NY).date())
    if now.astimezone(NY).hour < 17:
        d -= pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def apply_overrides(px: pd.DataFrame, path: Path) -> pd.DataFrame:
    """overrides.csv: day,series,value rows that replace a bad price by hand."""
    if not path.exists():
        return px
    px = px.copy()
    for row in pd.read_csv(path, parse_dates=["day"]).itertuples():
        px.loc[row.day, row.series] = row.value
    return px.sort_index()


def revised(cached: pd.DataFrame, fresh: pd.DataFrame, last: pd.Timestamp) -> bool:
    """Whether `fresh` changes days the cache already had before `last`. After a dividend, auto_adjust lowers
    every earlier price, so a cache patched only at its end would lose the dividend."""
    days = fresh.index[fresh.index < last].intersection(cached.index)
    cols = fresh.columns.intersection(cached.columns)
    return bool((fresh.loc[days, cols] / cached.loc[days, cols] - 1).abs().gt(1e-5).any().any())


def update_prices(db, cfg, fetch, upto: pd.Timestamp) -> pd.DataFrame:
    """Fetches the last stretch again, or the whole history if Yahoo has revised older days. Nothing after `upto`
    is kept: before the US close, Yahoo's row for today is a live price, not a close."""
    def get(start):
        px = fetch(cfg, start)
        return px[px.index <= upto]

    last = store.last_price_day(db, "SPY.close")
    cached = store.load_prices(db)
    # A series the cache has never had (a new report currency, say) needs its whole history.
    new = {f"{s}.close" for s in data.needed(cfg)} - set(cached.columns)
    fresh = get("1990-01-01" if last is None or new else f"{last - pd.Timedelta(days=REFETCH_DAYS):%Y-%m-%d}")
    if last is not None and not new and revised(cached, fresh, last):
        fresh = get("1990-01-01")
    store.save_prices(db, fresh)
    px = store.load_prices(db)
    return px[px.index <= upto]


def holiday_alert(holidays, today: date) -> str | None:
    if not any(h >= today for h in holidays):
        return "xetra_holidays lists no day ahead: add this and next year's from Deutsche Börse"
    if today.month == 12 and not any(h.year == today.year + 1 for h in holidays):
        return f"xetra_holidays has no {today.year + 1} days yet: add them from Deutsche Börse"
    return None


def check_data(run: Run, cfg, px, market, second_close) -> None:
    signals = sorted({sl.signal for s in cfg.strategies.values() for sl in s.slices if sl.rule == "trend"})
    expected = expected_us_day(run.now)
    missing = len(pd.bdate_range(run.day, expected)) - 1
    if missing > 1:
        run.alerts["stale"] = f"latest US close is {run.day:%Y-%m-%d}, expected {expected:%Y-%m-%d}"
        run.held_back = "prices are stale"
    for t in signals:
        try:
            day2, close2 = second_close(t)
        except Exception as e:  # a second source that is down is a warning, not a reason to stop
            run.alerts[f"cross-check:{t}"] = f"second source unavailable ({type(e).__name__})"
            continue
        ours = px[f"{t}.close"].get(run.day)
        if day2 != run.day:
            run.alerts[f"cross-check:{t}"] = f"second source's latest close is {day2:%Y-%m-%d}, ours {run.day:%Y-%m-%d}"
            if day2 > run.day:
                run.held_back = f"Yahoo is behind on {t}"
        elif abs(ours / close2 - 1) > CROSS_CHECK_TOLERANCE:
            run.alerts[f"cross-check:{t}"] = f"{t} close {ours:.2f} on Yahoo, {close2:.2f} on Nasdaq"
            run.held_back = f"{t} closes disagree"
    recent = set(market.dates[market.dates <= run.day][-5:])
    for fund, days in market.repaired.items():
        if hits := sorted(d for d in days if d in recent):
            run.alerts[f"repaired:{fund}"] = "model used for " + ", ".join(f"{d:%Y-%m-%d}" for d in hits)


def _advice(fund, amount, quote, reason, **extra) -> dict:
    return {"fund": fund, "action": "buy" if amount > 0 else "sell", "amount": round(abs(amount), 2),
            "shares": round(abs(amount) / quote, 2), "reason": reason, **extra}


def rebalance_advice(strategy, state, market, i, rules) -> list[dict]:
    """The trades the coming monthly rebalance makes, estimated at today's close, as the engine makes them: each
    slice back to its weight once the pending signal trades are done, sells first, buys no larger than the cash
    on hand, and trades under min_trade skipped."""
    total, amounts, after = state.value, [], {}
    cash = sum(s.cash for s in state.slices)
    for sl, s in zip(strategy.slices, state.slices):
        invested = s.held if s.pending is None else s.pending
        after[sl.fund] = invested * sl.weight
        fund = s.fund if s.pending is None else s.pending * s.value
        cash -= fund - s.fund
        amounts.append((invested * sl.weight * total - fund, sl.fund))
    out = []
    for amount, fund in sorted(amounts):
        amount = min(amount, cash)
        if abs(amount) >= max(rules.min_trade * total, 1e-9 * total):
            out.append(_advice(fund, amount, market.price[fund][i] * market.scale[fund][i], "rebalance",
                               after=after[fund]))
            cash -= amount
    return out


def money(x: float, currency: str) -> str:
    return f"€{x:,.0f}" if currency == "EUR" else f"{x:,.0f} {currency}"


def describe(a: dict, cfg) -> str:
    """One advised trade as a sentence: "Buy about 28 shares of Xtrackers S&P 500 2x (DBPG), about €9,000"."""
    text = (f"{a['action'].capitalize()} about {a['shares']:,} shares of {name_of(cfg, a['fund'])}, "
            f"about {money(a['amount'], cfg.base_currency)}")
    return text + (" (monthly rebalance)" if a["reason"] == "rebalance" else "")


def signal_view(market, sl, i) -> dict:
    lv = market.levels[sl.signal]
    windows = []
    for w in sl.windows:
        ma = lv.rolling(w).mean().iloc[i]
        windows.append({"window": w, "distance": float(lv.iloc[i] / ma - 1)})
    return {"signal": sl.signal, "fund": sl.fund, "count": float(market.above(sl.signal, sl.windows, sl.buffer)[i]),
            "windows": windows}


def since_in(run: Run, cfg, values: pd.Series) -> dict:
    """The return since the start measured in each report currency; None where the rate is missing."""
    out = {}
    for c in cfg.report_currencies or (cfg.base_currency,):
        growth = values.iloc[-1] / values.iloc[0]
        if c != cfg.base_currency:
            rate = run.fx.get(c)
            r0, r1 = (rate.asof(values.index[0]), rate.asof(values.index[-1])) if rate is not None else (None, None)
            growth = growth * r1 / r0 if r0 and r1 and pd.notna(r0) and pd.notna(r1) else None
        out[c] = None if growth is None else growth - 1
    return out


def decide(run: Run, cfg, market, strategy, rules) -> dict:
    i = market.pos(run.day)
    before_start = market.dates[market.dates < pd.Timestamp(config.start(cfg, strategy) or run.day)]
    start = min(before_start[-1] if len(before_start) else market.dates[0], market.dates[i - 1])
    # Starts in cash: the held funds are bought at the first open like any trade, since nothing is owned yet.
    values, trades, state = engine.backtest(strategy, market, rules, start=start, end=run.day + pd.Timedelta(days=1),
                                            value=config.capital(cfg, strategy), liquidate=False, invest_holds=False)
    opens = next_xetra_open(run.day, set(cfg.xetra_holidays), run.now)
    advice = []
    if run.held_back is None:
        for sl, s in zip(strategy.slices, state.slices):
            if s.pending is not None and s.pending != s.held:
                quote = market.price[sl.fund][i] * market.scale[sl.fund][i]
                advice.append(_advice(sl.fund, (s.pending - s.held) * s.value, quote, "signal",
                                      **{"from": s.held, "to": s.pending, "after": sl.weight * s.pending}))
        if strategy.rebalance == "monthly" and opens.month != run.day.month:
            advice += rebalance_advice(strategy, state, market, i, rules)
        advice.sort(key=lambda a: a["action"] != "sell")  # sells first, as the engine trades them
    last = max((t.day for t in trades), default=None)
    return {
        "name": strategy.name,
        "since": f"{pd.Timestamp(config.start(cfg, strategy)) if config.start(cfg, strategy) else values.index[0]:%Y-%m-%d}",
        "from": f"{values.index[0]:%Y-%m-%d}",
        "last_change": None if last is None else {
            "day": f"{last:%Y-%m-%d}",
            "trades": [{"fund": t.fund, "action": "bought" if t.amount > 0 else "sold", "reason": t.reason}
                       for t in trades if t.day == last]},
        "value": state.value,
        "since_start": values.iloc[-1] / values.iloc[0] - 1,
        "since_start_in": since_in(run, cfg, values),
        "drop_from_peak": values.iloc[-1] / values.max() - 1,
        "signals": [signal_view(market, sl, i) for sl in strategy.slices if sl.rule == "trend"],
        "slices": [{"fund": sl.fund, "value": s.value, "invested": s.held, "pending": s.pending, "weight": sl.weight,
                    "holding": s.fund, "cash": s.cash, "shares": s.shares * market.scale[sl.fund][i]}
                   for sl, s in zip(strategy.slices, state.slices)],
        "advice": advice,
        "trade_at": f"{opens:%Y-%m-%d}",
        "held_back": run.held_back,
        "prices": run.closes,
    }


def strategy_alerts(run: Run, strategy, history: pd.Series, decision) -> None:
    worst = engine.stats(history, "1900-01-01", "2100-01-01")["max_dd"]
    if decision["drop_from_peak"] < 1.5 * worst:
        run.alerts[f"drawdown:{strategy.id}"] = (f"{strategy.id} is {decision['drop_from_peak']:.1%} below its peak, "
                                                 f"past 1.5x its backtest worst ({worst:.1%}): stop and review")


def per_base(cfg, px, currency: str) -> pd.Series | None:
    """Units of `currency` per unit of the base currency, each day; None if the rate isn't in the data."""
    col = config.FX.get((currency, cfg.base_currency)) or config.FX.get((cfg.base_currency, currency))
    if col is None or f"{col}.close" not in px:
        return None
    rate = px[f"{col}.close"].dropna()
    return rate if (currency, cfg.base_currency) in config.FX else 1 / rate


BACKTEST_YEARS = (1, 3, 5, 10, 25)


def trailing(values: pd.Series, day, rate: pd.Series | None = None, years=BACKTEST_YEARS) -> dict:
    """Over the last 1 to 25 years to `day`: the return a year, the worst drop, and the Sharpe ratio (the
    return over `rate`, a yearly risk-free rate, per unit of volatility, both a year). None where the history
    is shorter."""
    out = {"return": {}, "drawdown": {}, "sharpe": {}}
    end = pd.Timestamp(day)
    for y in years:
        t0 = end - pd.DateOffset(years=y)
        if t0 < values.index[0]:
            for k in out:
                out[k][y] = None
            continue
        v = values[(values.index >= values.index[values.index <= t0][-1]) & (values.index <= end)]
        out["return"][y] = (v.iloc[-1] / v.iloc[0]) ** (1 / y) - 1
        out["drawdown"][y] = float((v / v.cummax() - 1).min())
        r = v.pct_change().dropna()
        per_year = len(r) / y
        free = (rate.reindex(r.index, method="ffill").fillna(0) / per_year) if rate is not None else 0.0
        excess = r - free
        out["sharpe"][y] = float(excess.mean() / r.std() * per_year ** 0.5) if r.std() > 0 else None
    return out


def _date(d) -> str:
    return f"{pd.Timestamp(d):%d-%m-%Y}"


ALERT_TITLES = {"stale": "Prices are out of date", "late": "The daily run was late", "backup": "The backup is overdue",
                "holidays": "The Xetra holiday list needs next year's days", "notify": "Messages failed to send"}


def alert_title(key: str) -> str:
    kind, _, what = key.partition(":")
    titled = {"cross-check": f"{what} price check", "repaired": f"{what} price replaced by its model",
              "drawdown": f"{what} has fallen past its stop level"}
    return titled.get(kind) or ALERT_TITLES.get(key, key)


def alert_subject(key: str, cleared: bool = False) -> str:
    return f"✅ Trendkeeper: {alert_title(key)}, resolved" if cleared else f"⚠️ Trendkeeper: {alert_title(key)}"


def name_of(cfg, fund: str) -> str:
    return cfg.instruments[fund].name or fund


@dataclass
class Table:
    """Rows of text under headers, rendered as aligned text, a Slack table block or an HTML table. `align` is
    "left" or "right" per column."""
    headers: list[str]
    align: list[str]
    rows: list[list[str]]

    def text(self) -> list[str]:
        cells = [self.headers] + self.rows
        width = [max(len(r[c]) for r in cells) for c in range(len(self.headers))]
        return ["  ".join(c.ljust(w) if a == "left" else c.rjust(w) for c, w, a in zip(r, width, self.align)).rstrip()
                for r in cells]

    def slack(self) -> dict:
        # Slack rejects the whole message over a zero-length cell.
        def cell(t, bold=False):
            return {"type": "rich_text", "elements": [{"type": "rich_text_section", "elements": [
                {"type": "text", "text": t or "–", **({"style": {"bold": True}} if bold else {})}]}]}
        return {"type": "table", "column_settings": [{"align": a} for a in self.align],
                "rows": [[cell(h, bold=True) for h in self.headers]] + [[cell(c) for c in r] for r in self.rows]}

    def html(self) -> str:
        def row(cells, tag):
            return "<tr>" + "".join(f'<{tag} style="text-align:{a};padding:2px 10px">{escape(c)}</{tag}>'
                                    for c, a in zip(cells, self.align)) + "</tr>"
        return ('<table style="border-collapse:collapse;font-family:sans-serif;font-size:14px">'
                + row(self.headers, "th") + "".join(row(r, "td") for r in self.rows) + "</table>")


def ticker(fund: str) -> str:
    return fund.split(".")[0]


def subject(run: Run) -> str:
    return f"Trendkeeper · {_date(run.day)}"


def overview_table(run: Run, cfg, follow) -> Table:
    """One row per followed strategy: its start, its value, its return since the start in each report currency
    and the trades it needs; then the benchmarks over the days of the earliest start."""
    currencies = list(cfg.report_currencies or (cfg.base_currency,))

    def pct(by, c):
        return f"{by[c]:+.1%}" if by.get(c) is not None else ""

    rows = []
    for sid in follow:
        f, n = run.decisions[sid], len(run.decisions[sid]["advice"])
        todo = "held back" if run.held_back else f"{n} trade{'s' * (n != 1)}" if n else "none"
        rows.append([f["name"], _date(f["since"]), money(f["value"], cfg.base_currency),
                     *[pct(f["since_start_in"], c) for c in currencies], todo])
    first = min((run.decisions[sid] for sid in follow), key=lambda f: f["from"])
    for k, s in cfg.strategies.items():
        if s.benchmark and k in run.history:
            v = run.history[k]
            by = since_in(run, cfg, v[(v.index >= pd.Timestamp(first["from"])) & (v.index <= run.day)])
            rows.append([s.name, _date(first["since"]), "", *[pct(by, c) for c in currencies], ""])
    return Table(["Strategy", "Since", "Value", *currencies, "Actions"],
                 ["left", "left", "right", *["right"] * len(currencies), "left"], rows)


def action_table(run: Run, cfg, follow) -> Table:
    """Every advised trade, by strategy: BUY or SELL, the ticker, about how many shares (fractional), the amount."""
    rows = [[run.decisions[sid]["name"], a["action"].upper() + (" (rebalance)" if a["reason"] == "rebalance" else ""),
             ticker(a["fund"]), f"{a['shares']:,.2f}", money(a["amount"], cfg.base_currency)]
            for sid in follow for a in run.decisions[sid]["advice"]]
    return Table(["Strategy", "Action", "Ticker", "Shares", "Amount"], ["left", "left", "left", "right", "right"], rows)


def portfolio_table(cfg, strategy, f) -> Table:
    """One row per fund: its weight in the strategy and the share each average decides, its target now, its
    weight now, the shares held and their value; then cash and the total."""
    ccy, total = cfg.base_currency, f["value"]
    windows = sorted({w for sl in strategy.slices for w in sl.windows})
    rows, targets = [], 0.0
    for sl, s in zip(strategy.slices, f["slices"]):
        target = s["weight"] * (s["invested"] if s["pending"] is None else s["pending"])
        targets += target
        split = "/".join(f"{sl.weight / len(sl.windows):.0%}" for _ in sl.windows) if sl.rule == "trend" else "-"
        rows.append([name_of(cfg, sl.fund), ticker(sl.fund), f"{sl.weight:.0%}", split, f"{target:.0%}",
                     f"{s['holding'] / total:.0%}", f"{s['shares']:,.2f}", money(s["holding"], ccy)])
    cash = sum(s["cash"] for s in f["slices"])
    rows.append(["Cash", ccy, "", "", f"{max(1 - targets, 0):.0%}", f"{cash / total:.0%}", "", money(cash, ccy)])
    rows.append(["Total", "", "", "", "", "", "", money(total, ccy)])
    return Table(["Asset", "Ticker", "Weight", f"{'/'.join(map(str, windows))}d" if windows else "Split",
                  "Target", "Now", "Shares", "Value"], ["left", "left", *["right"] * 6], rows)


def signals_of(decisions) -> dict:
    """Each signal once, across the strategies."""
    seen = {}
    for f in decisions:
        for g in f["signals"]:
            seen.setdefault(g["signal"], g)
    return seen


def market_table(cfg, decisions) -> Table:
    """Each signal: its trend against each average (▲ above, ▼ below) and the distance from it."""
    seen = signals_of(decisions)
    windows = sorted({w["window"] for g in seen.values() for w in g["windows"]})
    rows = []
    for sig, g in seen.items():
        dist = {w["window"]: w["distance"] for w in g["windows"]}
        rows.append([name_of(cfg, sig).split(" (")[0], ticker(sig), "".join("▲" if x > 0 else "▼" for x in dist.values()),
                     *[f"{dist[w]:+.1%}" if w in dist else "" for w in windows]])
    return Table(["Index", "Ticker", "Trend", *[f"vs {w}d" for w in windows]],
                 ["left", "left", "left", *["right"] * len(windows)], rows)


BACKTEST_TABLES = (("return", "USD yearly returns", "{:+.1%}"), ("drawdown", "USD max drawdown", "{:.1%}"),
                   ("sharpe", "Sharpe ratio (USD, over T-bills)", "{:.2f}"))


def track_tables(run: Run, follow) -> list[tuple[str, Table]]:
    """The backtest over the last 1 to 25 years, a table per measure: the followed strategies, then the indexes."""
    order = [k for k in follow if k in run.track] + [k for k in run.track if k not in follow]
    if not order:
        return []
    out = []
    for key, heading, fmt in BACKTEST_TABLES:
        years = list(run.track[order[0]][key])
        rows = [[run.decisions[k]["name"], *[fmt.format(x) if (x := run.track[k][key][y]) is not None else ""
                                             for y in years]] for k in order]
        out.append((heading, Table(["Strategy", *[f"{y}y" for y in years]], ["left", *["right"] * len(years)], rows)))
    return out


def next_trade(cfg, decisions) -> str:
    """The smallest move in each signal that would trade: "Next trade if S&P 500 falls about 6% (sell) ..."."""
    moves, close = [], []
    for g in signals_of(decisions).values():
        name = name_of(cfg, g["signal"]).split(" (")[0]
        dist = [w["distance"] for w in g["windows"]]
        if above := [x for x in dist if x > 0]:
            moves.append(f"{name} falls about {min(above) / (1 + min(above)):.0%} (sell)")
        if below := [x for x in dist if x <= 0]:
            moves.append(f"{name} rises about {-max(below) / (1 + max(below)):.0%} (buy)")
        if any(abs(x) < NEAR for x in dist):
            close.append(name)
    line = "Next trade if " + " or ".join(moves) + "." if moves else ""
    if close:
        line += f" {' and '.join(close)} {'is' if len(close) == 1 else 'are'} close to an average: a trade may come soon."
    return line


def summary(run: Run, cfg, follow) -> tuple[str, dict, str]:
    """One summary for all followed strategies, as plain text (status.txt and the email's text part), a Slack
    Block Kit message and the email's HTML part, in the same order: the strategies side by side, the actions
    needed, each portfolio, the market, the backtests and the alerts."""
    follow = [sid for sid in follow if sid in run.decisions]
    decisions = [run.decisions[sid] for sid in follow]
    ccy = cfg.base_currency
    overview, actions, market = overview_table(run, cfg, follow), action_table(run, cfg, follow), market_table(cfg, decisions)
    portfolios = [(f"{f['name']} · {money(f['value'], ccy)}"
                   + (" · rebalanced monthly" if cfg.strategies[sid].rebalance == "monthly" else ""),
                   portfolio_table(cfg, cfg.strategies[sid], f)) for sid, f in zip(follow, decisions)]
    tracks = track_tables(run, follow)

    n = len(actions.rows)
    when = f"on {_date(decisions[0]['trade_at'])}"
    if run.held_back:
        head = f"No action today: {run.held_back}, so the advice is held back. It runs again tomorrow."
    elif not n:
        head = f"No actions needed {when}"
    else:
        head = f"Actions needed {when}"
    nxt = next_trade(cfg, decisions)
    alerts = [f"{alert_title(k)}: {v}" for k, v in sorted(run.alerts.items())]
    title = f"Trendkeeper · {_date(run.day)} {run.day:%A}"
    strategies = "Strategies since their start"

    plain = "\n".join([
        title, "",
        f"{strategies}:", *overview.text(), "",
        head + (":" if n else ""), *(actions.text() if n else []), "",
        "Portfolios:", *[line for h, tb in portfolios for line in (h, *tb.text(), "")],
        "Market:", *market.text(), *([nxt] if nxt else []), "",
        *(["Backtests:"] + [line for h, tb in tracks for line in (f"{h}:", *tb.text(), "")] if tracks else []),
        "No alerts." if not alerts else "Alerts:", *[f"  {a}" for a in alerts]])

    def md(text):
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    def note(text):
        return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": title}},
              md(f"*{strategies}*"), overview.slack(),
              md(f"*{head}*"), *([actions.slack()] if n else []),
              md("*Portfolios*"), *[b for h, tb in portfolios for b in (md(f"_{h}_"), tb.slack())],
              md("*Market*"), market.slack(), *([note(nxt)] if nxt else []),
              *([md("*Backtests*")] + [b for h, tb in tracks for b in (md(f"_{h}_"), tb.slack())] if tracks else []),
              md("No alerts." if not alerts else "*Alerts*\n" + "\n".join(f"• {a}" for a in alerts))]
    slack = {"text": subject(run), "blocks": blocks}

    def p(text):
        return f"<p>{escape(text)}</p>"

    html = "".join([
        f"<h3>{escape(title)}</h3>",
        f"<p><b>{strategies}</b></p>", overview.html(),
        f"<p><b>{escape(head)}</b></p>", actions.html() if n else "",
        "<p><b>Portfolios</b></p>", "".join(f"<p><i>{escape(h)}</i></p>{tb.html()}" for h, tb in portfolios),
        "<p><b>Market</b></p>", market.html(), p(nxt) if nxt else "",
        "<p><b>Backtests</b></p>" + "".join(f"<p><i>{escape(h)}</i></p>{tb.html()}" for h, tb in tracks) if tracks else "",
        p("No alerts.") if not alerts else "<p><b>Alerts</b></p><ul>" + "".join(
            f"<li>{escape(a)}</li>" for a in alerts) + "</ul>"])
    return plain, slack, f'<html><body style="font-family:sans-serif">{html}</body></html>'


def ping(suffix: str = "") -> None:
    url = os.environ.get("TK_HEALTHCHECK_DAILY")
    if url:
        try:
            urllib.request.urlopen(url.rstrip("/") + suffix, timeout=15).close()
        except OSError as e:
            print(f"healthcheck ping failed: {e}", file=sys.stderr)


def write_status(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text + "\n")
    tmp.replace(path)


def run(cfg_file: Path | None = None, *, now: datetime | None = None, fetch=data.fetch,
        second_close=data.second_close, senders=notify.SENDERS, pinger=ping, data_root: Path | None = None) -> int:
    cfg_file = cfg_file or config.path()
    cfg = config.load(cfg_file)
    root = data_root or config.data_dir(cfg)
    db = store.connect(root / "tk.db")
    now = now or datetime.now(NY)
    try:
        upto = expected_us_day(now)
        px = apply_overrides(update_prices(db, cfg, fetch, upto), root / "overrides.csv")
        px = px[px.index <= upto]
        market = engine.build_market(cfg, px)
        signals = {sl.signal for s in cfg.strategies.values() for sl in s.slices if sl.rule == "trend"}
        r = Run(day=min(px[f"{t}.close"].last_valid_index() for t in signals), now=now)
        for c in set(cfg.report_currencies) | {"USD"}:
            if c != cfg.base_currency and (rate := per_base(cfg, px, c)) is not None:
                r.fx[c] = rate
        r.closes = {c[: -len('.close')]: float(v) for c, v in px.filter(like='.close').ffill().loc[r.day].items()
                    if c[: -len('.close')] in data.needed(cfg) and pd.notna(v)}
        check_data(r, cfg, px, market, second_close)
        if os.environ.get("TK_BACKUP_DIR"):
            marker = root / "backup.ok"
            last = datetime.fromisoformat(marker.read_text().strip()) if marker.exists() else None
            if last is None or (now - last).total_seconds() > 36 * 3600:
                r.alerts["backup"] = f"last good backup: {last:%Y-%m-%d %H:%M} UTC" if last else "no backup yet"
        if note := holiday_alert(cfg.xetra_holidays, now.astimezone(NY).date()):
            r.alerts["holidays"] = note
        close = datetime.combine(r.day.date(), datetime.min.time(), NY).replace(hour=16)
        # A day already logged isn't late: on a US holiday the run sees the day before's close again.
        if not store.logged(db, r.day) and (now - close).total_seconds() > 18 * 3600:
            r.alerts["late"] = f"run at {now.astimezone(NY):%Y-%m-%d %H:%M} New York for the {r.day:%Y-%m-%d} close"
        rules = engine.Rules.from_config(cfg)
        commit, digest = git_commit(), hashlib.sha256(cfg_file.read_bytes()).hexdigest()[:12]
        # The whole backtest of the followed strategies and the benchmarks: their 1-25 year record, the drop stop
        # and the benchmarks' return over each strategy's own days.
        follow = cfg.follow or (next(iter(cfg.strategies)),)
        history = {sid: engine.backtest(s, market, rules, value=config.capital(cfg, s), liquidate=False)[0]
                   for sid, s in cfg.strategies.items() if sid in follow or s.benchmark}
        r.history = history
        usd = r.fx.get("USD") if cfg.base_currency != "USD" else None
        if cfg.base_currency == "USD" or usd is not None:
            for sid, values in history.items():
                if usd is not None:
                    values = values * usd.reindex(values.index, method="ffill")
                r.track[sid] = trailing(values.dropna(), r.day, px["^IRX.close"].dropna() / 100 if "^IRX.close" in px else None)
        for sid, strategy in cfg.strategies.items():
            r.decisions[sid] = decide(r, cfg, market, strategy, rules)
            if sid in follow:
                strategy_alerts(r, strategy, history[sid], r.decisions[sid])
        for sid, d in r.decisions.items():
            store.log_decision(db, r.day, sid, now.isoformat(timespec="seconds"), commit, digest, d)
        stamp = now.isoformat(timespec="seconds")
        # A notify alert stays open until this run's messages have gone out, so it can't clear and reopen each run.
        if "notify" in (opened := store.open_alerts(db)):
            r.alerts["notify"] = opened["notify"][1]

        def send_alert_changes():
            started, cleared = store.update_alerts(db, r.alerts, stamp)
            out = []
            for key, detail in started.items():
                out += notify.send(cfg, "alerts", alert_subject(key), detail, senders)
            for key, detail in cleared.items():
                out += notify.send(cfg, "alerts", alert_subject(key, cleared=True), detail, senders)
            return out

        failures = send_alert_changes()
        text, slack, html = summary(r, cfg, follow)
        failures += notify.send(cfg, "daily", subject(r), text, senders,
                                rich={"slack": slack, "email": {"text": text, "html": html}})
        if failures:
            r.alerts["notify"] = "; ".join(dict.fromkeys(failures))
        else:
            r.alerts.pop("notify", None)
        send_alert_changes()
        text = summary(r, cfg, follow)[0]
        write_status(root / "status.txt", text)
        pinger()
        return 0
    except Exception as e:
        message = f"Trendkeeper run FAILED at {now.astimezone(NY):%Y-%m-%d %H:%M} New York: {type(e).__name__}: {e}"
        write_status(root / "status.txt", message)
        pinger("/fail")
        notify.send(cfg, "alerts", "❌ Trendkeeper: the daily run failed", message, senders)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
