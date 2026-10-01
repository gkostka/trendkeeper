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
from datetime import datetime
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


def update_prices(db, cfg, fetch) -> pd.DataFrame:
    last = store.last_price_day(db, "SPY.close")
    # Yahoo revises recent days (dividends, late prints), so the last stretch is fetched again.
    start = "1990-01-01" if last is None else f"{last - pd.Timedelta(days=REFETCH_DAYS):%Y-%m-%d}"
    store.save_prices(db, fetch(cfg, start))
    return store.load_prices(db)


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


def signal_view(market, sl, i) -> dict:
    lv = market.levels[sl.signal]
    windows = []
    for w in sl.windows:
        ma = lv.rolling(w).mean().iloc[i]
        windows.append({"window": w, "distance": float(lv.iloc[i] / ma - 1)})
    return {"signal": sl.signal, "fund": sl.fund, "count": float(market.above(sl.signal, sl.windows, sl.buffer)[i]),
            "windows": windows}


def decide(run: Run, cfg, market, strategy, rules) -> dict:
    i = market.pos(run.day)
    before_start = market.dates[market.dates < pd.Timestamp(cfg.start or run.day)]
    start = min(before_start[-1] if len(before_start) else market.dates[0], market.dates[i - 1])
    values, _, state = engine.backtest(strategy, market, rules, start=start, end=run.day + pd.Timedelta(days=1),
                                       value=cfg.start_value, liquidate=False)
    opens = next_xetra_open(run.day, set(cfg.xetra_holidays), run.now)
    advice = []
    if run.held_back is None:
        for sl, s in zip(strategy.slices, state.slices):
            if s.pending is not None and s.pending != s.held:
                amount = (s.pending - s.held) * s.value
                quote = market.price[sl.fund][i] * market.scale[sl.fund][i]
                advice.append({"fund": sl.fund, "action": "buy" if amount > 0 else "sell", "amount": round(abs(amount), 2),
                               "shares": int(abs(amount) // quote), "from": s.held, "to": s.pending})
        if strategy.rebalance == "monthly" and opens.month != run.day.month:
            advice.append({"action": "rebalance", "to": [sl.weight for sl in strategy.slices]})
    return {
        "value": state.value,
        "since_start": values.iloc[-1] / values.iloc[0] - 1,
        "drop_from_peak": values.iloc[-1] / values.max() - 1,
        "signals": [signal_view(market, sl, i) for sl in strategy.slices if sl.rule == "trend"],
        "slices": [{"fund": sl.fund, "value": s.value, "invested": s.held, "pending": s.pending}
                   for sl, s in zip(strategy.slices, state.slices)],
        "advice": advice,
        "trade_at": f"{opens:%Y-%m-%d}",
        "held_back": run.held_back,
        "prices": run.closes,
    }


def strategy_alerts(run: Run, cfg, market, strategy, rules, decision) -> None:
    for sig in decision["signals"]:
        for w in sig["windows"]:
            if abs(w["distance"]) < NEAR:
                run.alerts[f"near:{sig['signal']}:{w['window']}"] = (
                    f"{sig['signal']} is {w['distance']:+.1%} from its {w['window']}-day average")
    worst = engine.stats(engine.backtest(strategy, market, rules, value=cfg.start_value)[0],
                         "1900-01-01", "2100-01-01")["max_dd"]
    if decision["drop_from_peak"] < 1.5 * worst:
        run.alerts[f"drawdown:{strategy.id}"] = (f"{strategy.id} is {decision['drop_from_peak']:.1%} below its peak, "
                                                 f"past 1.5x its backtest worst ({worst:.1%}): stop and review")


def summary(run: Run, cfg) -> str:
    lines = [f"Trendkeeper · US close {run.day:%Y-%m-%d} · run {run.now.astimezone(NY):%Y-%m-%d %H:%M} New York"]
    follow = run.decisions.get(cfg.follow) or next(iter(run.decisions.values()))
    for sig in follow["signals"]:
        dists = "  ".join(f"{w['window']}d {w['distance']:+.1%}" for w in sig["windows"])
        above = [w["distance"] for w in sig["windows"] if w["distance"] > 0]
        exit_at = f"  next exit at about {-min(above) / (1 + min(above)):.1%}" if above else ""
        lines.append(f"{sig['signal']:<4} {dists}  {round(sig['count'] * len(sig['windows']))}/{len(sig['windows'])}{exit_at}")
    if run.held_back:
        lines.append(f"Action ({cfg.follow}): none today, held back because {run.held_back}")
    elif not follow["advice"]:
        lines.append(f"Action ({cfg.follow}): no change")
    for a in follow["advice"]:
        if a["action"] == "rebalance":
            lines.append(f"Action ({cfg.follow}): monthly rebalance at the Xetra open on {follow['trade_at']}")
        else:
            lines.append(f"Action ({cfg.follow}): {a['action']} about {a['amount']:,.0f} {cfg.base_currency} of {a['fund']} "
                         f"(~{a['shares']} shares) at the Xetra open on {follow['trade_at']}")
    for sid, d in run.decisions.items():
        lines.append(f"{sid:<14} since start {d['since_start']:+.1%}  from peak {d['drop_from_peak']:+.1%}  "
                     f"value {d['value']:,.0f} {cfg.base_currency}")
    lines.append("Alerts: " + ("none" if not run.alerts else "; ".join(f"{k}: {v}" for k, v in sorted(run.alerts.items()))))
    return "\n".join(lines)


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
        px = apply_overrides(update_prices(db, cfg, fetch), root / "overrides.csv")
        market = engine.build_market(cfg, px)
        signals = {sl.signal for s in cfg.strategies.values() for sl in s.slices if sl.rule == "trend"}
        r = Run(day=min(px[f"{t}.close"].last_valid_index() for t in signals), now=now)
        r.closes = {c[: -len('.close')]: float(v) for c, v in px.filter(like='.close').ffill().loc[r.day].items()
                    if c[: -len('.close')] in data.needed(cfg) and pd.notna(v)}
        check_data(r, cfg, px, market, second_close)
        if os.environ.get("TK_BACKUP_DIR"):
            marker = root / "backup.ok"
            last = datetime.fromisoformat(marker.read_text().strip()) if marker.exists() else None
            if last is None or (now - last).total_seconds() > 36 * 3600:
                r.alerts["backup"] = f"last good backup: {last:%Y-%m-%d %H:%M} UTC" if last else "no backup yet"
        close = datetime.combine(r.day.date(), datetime.min.time(), NY).replace(hour=16)
        if (now - close).total_seconds() > 18 * 3600:
            r.alerts["late"] = f"run at {now.astimezone(NY):%Y-%m-%d %H:%M} New York for the {r.day:%Y-%m-%d} close"
        rules = engine.Rules.from_config(cfg)
        commit, digest = git_commit(), hashlib.sha256(cfg_file.read_bytes()).hexdigest()[:12]
        for sid, strategy in cfg.strategies.items():
            r.decisions[sid] = decide(r, cfg, market, strategy, rules)
            if sid == cfg.follow:
                strategy_alerts(r, cfg, market, strategy, rules, r.decisions[sid])
        for sid, d in r.decisions.items():
            store.log_decision(db, r.day, sid, now.isoformat(timespec="seconds"), commit, digest, d)
        stamp = now.isoformat(timespec="seconds")
        started, cleared = store.update_alerts(db, r.alerts, stamp)
        failures = []
        for key, detail in started.items():
            failures += notify.send(cfg, "alerts", f"Trendkeeper alert: {key}", detail, senders)
        for key, detail in cleared.items():
            failures += notify.send(cfg, "alerts", f"Trendkeeper cleared: {key}", detail, senders)
        text = summary(r, cfg)
        failures += notify.send(cfg, "daily", f"Trendkeeper {r.day:%Y-%m-%d}", text, senders)
        if failures:
            r.alerts["notify"] = "; ".join(dict.fromkeys(failures))
            store.update_alerts(db, r.alerts, stamp)
            text = summary(r, cfg)
        write_status(root / "status.txt", text)
        pinger()
        return 0
    except Exception as e:
        message = f"Trendkeeper run FAILED at {now.astimezone(NY):%Y-%m-%d %H:%M} New York: {type(e).__name__}: {e}"
        write_status(root / "status.txt", message)
        pinger("/fail")
        notify.send(cfg, "alerts", "Trendkeeper run failed", message, senders)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
