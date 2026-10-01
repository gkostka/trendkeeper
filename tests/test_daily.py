import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from bot import cli, daily, store
from bot.data import load_snapshot

HERE = Path(__file__).parent
CONFIG = HERE.parent / "bot" / "config.toml"
PX = load_snapshot(HERE / "data" / "prices.csv.gz", HERE / "data" / "eur.csv.gz")
DAY = pd.Timestamp("2026-09-30")
PREV = pd.Timestamp("2026-09-29")
EVENING = datetime(2026, 9, 30, 18, 5, tzinfo=daily.NY)
LATER = datetime(2026, 9, 30, 19, 30, tzinfo=daily.NY)


def fetch(cfg, start):
    return PX[PX.index >= start]


def second_close(ticker, shift=0.0):
    return second_close_on(ticker, DAY, shift)


def second_close_on(ticker, day, shift=0.0):
    return day, float(PX[f"{ticker}.close"][day]) * (1 + shift)


class Outbox:
    def __init__(self, failing=()):
        self.sent, self.failing = [], set(failing)
        self.senders = {ch: self._sender(ch) for ch in ("slack", "email")}

    def _sender(self, ch):
        def send(cfg, subject, text):
            if ch in self.failing:
                raise ConnectionError(f"{ch} down")
            self.sent.append((ch, subject, text))
        return send


def run(tmp_path, outbox=None, now=EVENING, second=second_close):
    outbox = outbox or Outbox()
    pings = []
    code = daily.run(CONFIG, now=now, fetch=fetch, second_close=second, senders=outbox.senders,
                     pinger=lambda suffix="": pings.append(suffix), data_root=tmp_path)
    return code, outbox, pings


def test_a_run_logs_the_day_writes_the_status_and_pings(tmp_path):
    code, outbox, pings = run(tmp_path)
    assert code == 0 and pings == [""]
    status = (tmp_path / "status.txt").read_text()
    assert "US close 2026-09-30" in status and "mix_30_30_40" in status and "Paper action (mix_30_30_40)" in status
    db = store.connect(tmp_path / "tk.db")
    logged = {s: store.decisions(db, s, 1)[0] for s in ("mix_30_30_40", "spy", "qqq")}
    assert all(d["day"] == "2026-09-30" and d["held_back"] is None for d in logged.values())
    assert [ch for ch, subject, _ in outbox.sent if subject.startswith("Trendkeeper 2026")] == ["slack"]


def test_running_twice_logs_once_and_does_not_repeat_alerts(tmp_path):
    run(tmp_path)
    _, outbox, _ = run(tmp_path)
    db = store.connect(tmp_path / "tk.db")
    assert len(store.decisions(db, "mix_30_30_40")) == 1
    assert not [s for _, s, _ in outbox.sent if "alert" in s]


def test_closes_that_disagree_hold_back_the_advice_and_alert(tmp_path):
    _, outbox, _ = run(tmp_path, second=lambda t: second_close(t, 0.01))
    d = store.decisions(store.connect(tmp_path / "tk.db"), "mix_30_30_40", 1)[0]
    assert d["held_back"] and d["advice"] == []
    assert any(s == "Trendkeeper alert: cross-check:SPY" for _, s, _ in outbox.sent)
    _, outbox, _ = run(tmp_path, now=LATER)  # sources agree again: the alert clears, once
    assert any(s == "Trendkeeper cleared: cross-check:SPY" for _, s, _ in outbox.sent)
    # The log keeps both runs, and the latest says what was advised in the end.
    both = store.decisions(store.connect(tmp_path / "tk.db"), "mix_30_30_40")
    assert [bool(d["held_back"]) for d in both] == [False, True] and both[0]["advice"]


def test_a_late_run_says_so(tmp_path):
    run(tmp_path, now=datetime(2026, 10, 1, 15, 0, tzinfo=daily.NY))
    assert "late" in store.open_alerts(store.connect(tmp_path / "tk.db"))


def test_a_failed_channel_falls_back_and_is_reported(tmp_path):
    _, outbox, _ = run(tmp_path, Outbox(failing={"slack"}))
    assert [ch for ch, s, _ in outbox.sent if s.startswith("Trendkeeper 2026")] == ["email"]
    assert "notify" in store.open_alerts(store.connect(tmp_path / "tk.db"))


def test_a_crash_writes_the_failure_and_pings_fail(tmp_path):
    def broken(cfg, start):
        raise ConnectionError("Yahoo is down")
    pings, outbox = [], Outbox()
    with pytest.raises(ConnectionError):
        daily.run(CONFIG, now=EVENING, fetch=broken, second_close=second_close, senders=outbox.senders,
                  pinger=lambda suffix="": pings.append(suffix), data_root=tmp_path)
    assert pings == ["/fail"] and "FAILED" in (tmp_path / "status.txt").read_text()
    assert any(s == "Trendkeeper run failed" for _, s, _ in outbox.sent)


def test_overrides_replace_a_bad_price(tmp_path):
    (tmp_path / "overrides.csv").write_text("day,series,value\n2026-09-30,SPY.close,1.0\n")
    px = daily.apply_overrides(PX, tmp_path / "overrides.csv")
    assert px.loc[DAY, "SPY.close"] == 1.0 and PX.loc[DAY, "SPY.close"] != 1.0


def test_the_decision_log_is_append_only(tmp_path):
    run(tmp_path)
    db = store.connect(tmp_path / "tk.db")
    for sql in ("UPDATE decisions SET data = '{}'", "DELETE FROM decisions"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(sql)


def test_next_xetra_open_skips_weekends_and_holidays():
    holidays = {pd.Timestamp("2026-12-24").date(), pd.Timestamp("2026-12-25").date()}
    assert daily.next_xetra_open(pd.Timestamp("2026-12-23"), holidays) == pd.Timestamp("2026-12-28")
    assert daily.next_xetra_open(pd.Timestamp("2026-10-02"), set()) == pd.Timestamp("2026-10-05")


def test_tk_prints_the_status_and_why(tmp_path, monkeypatch, capsys):
    run(tmp_path)
    monkeypatch.setenv("TK_DATA_DIR", str(tmp_path))
    assert cli.main([]) == 0 and "US close 2026-09-30" in capsys.readouterr().out
    assert cli.main(["why"]) == 0 and "200-day average" in capsys.readouterr().out


def test_tk_check_names_missing_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TK_DATA_DIR", str(tmp_path))
    for v in ("TK_SLACK_WEBHOOK", "TK_SMTP_HOST", "TK_SMTP_USER", "TK_SMTP_PASSWORD", "TK_HEALTHCHECK_DAILY"):
        monkeypatch.delenv(v, raising=False)
    assert cli.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "TK_SLACK_WEBHOOK" in out and "TK_HEALTHCHECK_DAILY" in out


def test_backup_copies_the_database_and_personal_files(tmp_path):
    from bot.backup import backup
    root, dest = tmp_path / "data", tmp_path / "backups"
    run(root)
    (root / "transactions.csv").write_text("date,type\n")
    out = backup(root, dest)
    copy = store.connect(out / "tk.db")
    assert store.decisions(copy, "mix_30_30_40") and (out / "transactions.csv").exists()
    assert (root / "backup.ok").exists()


def test_an_old_or_missing_backup_raises_an_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("TK_BACKUP_DIR", str(tmp_path / "backups"))
    run(tmp_path)
    assert store.open_alerts(store.connect(tmp_path / "tk.db"))["backup"][1] == "no backup yet"
    (tmp_path / "backup.ok").write_text(EVENING.isoformat() + "\n")
    run(tmp_path)
    assert "backup" not in store.open_alerts(store.connect(tmp_path / "tk.db"))


def test_a_late_run_advises_the_next_open_still_ahead():
    late = datetime(2026, 10, 1, 12, 46, tzinfo=daily.NY)  # 18:46 in Frankfurt: the 1 Oct open has passed
    assert daily.next_xetra_open(DAY, set(), EVENING) == pd.Timestamp("2026-10-01")
    assert daily.next_xetra_open(DAY, set(), late) == pd.Timestamp("2026-10-02")


def test_a_rebalance_that_would_not_trade_is_not_advised(tmp_path):
    # Day one: the pending buys already bring every slice to its weight, so no rebalance line.
    run(tmp_path)
    d = store.decisions(store.connect(tmp_path / "tk.db"), "mix_30_30_40", 1)[0]
    assert {a["action"] for a in d["advice"]} == {"buy"}


def test_a_drifted_portfolio_is_advised_to_rebalance():
    from bot import config, engine
    cfg = config.load(CONFIG)
    strategy, rules = cfg.strategies["mix_30_30_40"], engine.Rules.from_config(cfg)
    market = engine.build_market(cfg, PX)
    i = market.pos(DAY)
    s = [engine.SliceState(fund=12000, cash=0, held=1.0), engine.SliceState(fund=9000, cash=0, held=1.0),
         engine.SliceState(fund=9000, cash=0, held=1.0)]
    advice = daily.rebalance_advice(strategy, engine.State(DAY, tuple(s)), market, i, rules)
    assert [(a["fund"], a["action"], a["amount"]) for a in advice] == [("DBPG.DE", "sell", 3000), ("SXRM.DE", "buy", 3000)]
    s[0] = engine.SliceState(fund=9000, cash=0, held=1.0)
    s[2] = engine.SliceState(fund=12000, cash=0, held=1.0)
    assert not daily.rebalance_advice(strategy, engine.State(DAY, tuple(s)), market, i, rules)


def test_rebalance_advice_matches_what_the_engine_trades():
    # The last month the engine rebalanced: the advice at the close before against its trades at the open.
    # The open moves the portfolio overnight, so amounts agree to within 1% of its value, not exactly.
    from bot import config, engine
    cfg = config.load(CONFIG)
    strategy = cfg.strategies["mix_30_30_40"]
    rules = engine.Rules.from_config(cfg, whole_shares=False)
    market = engine.build_market(cfg, PX)
    _, trades, _ = engine.backtest(strategy, market, rules, start="2016-01-04", value=30000)
    day = max(t.day for t in trades if t.reason == "rebalance")
    done = {t.fund: t.amount for t in trades if t.reason == "rebalance" and t.day == day}
    _, _, state = engine.backtest(strategy, market, rules, start="2016-01-04", end=day, value=30000, liquidate=False)
    advice = daily.rebalance_advice(strategy, state, market, market.pos(day) - 1, rules)
    assert {a["fund"] for a in advice} == set(done)
    for a in advice:
        assert (a["amount"] if a["action"] == "buy" else -a["amount"]) == pytest.approx(done[a["fund"]],
                                                                                         abs=0.01 * state.value)


def test_a_run_before_the_close_ignores_todays_live_price(tmp_path):
    run(tmp_path, now=datetime(2026, 9, 30, 11, 0, tzinfo=daily.NY), second=lambda t: second_close_on(t, PREV))
    db = store.connect(tmp_path / "tk.db")
    assert store.decisions(db, "mix_30_30_40", 1)[0]["day"] == f"{PREV:%Y-%m-%d}"
    assert store.last_price_day(db, "SPY.close") == PREV


def test_a_dividend_that_rescales_history_is_fetched_in_full(tmp_path):
    run(tmp_path)
    # Yahoo after an ex-dividend day: every earlier SPY price lowered by the dividend.
    adjusted = PX.copy()
    adjusted.loc[adjusted.index < DAY, "SPY.close"] *= 0.99
    daily.run(CONFIG, now=LATER, fetch=lambda cfg, start: adjusted[adjusted.index >= start], second_close=second_close,
              senders=Outbox().senders, pinger=lambda suffix="": None, data_root=tmp_path)
    cached = store.load_prices(store.connect(tmp_path / "tk.db"))
    assert cached.loc["2020-01-02", "SPY.close"] == pytest.approx(PX.loc["2020-01-02", "SPY.close"] * 0.99)


def test_tk_why_works_for_a_user_who_can_only_read(tmp_path, monkeypatch, capsys):
    run(tmp_path)
    monkeypatch.setenv("TK_DATA_DIR", str(tmp_path))
    files = list(tmp_path.iterdir())
    try:
        for p in files:
            p.chmod(0o444)
        tmp_path.chmod(0o555)
        assert cli.main(["why"]) == 0 and "Paper action" in capsys.readouterr().out
    finally:
        tmp_path.chmod(0o755)
        for p in files:
            p.chmod(0o644)


def test_a_us_holiday_is_not_a_late_run(tmp_path):
    def upto(day):
        return lambda cfg, start: PX[(PX.index >= start) & (PX.index <= day)]
    for now in (datetime(2026, 9, 29, 18, 5, tzinfo=daily.NY), EVENING):  # no US close on the 30th
        daily.run(CONFIG, now=now, fetch=upto(PREV), second_close=lambda t: second_close_on(t, PREV),
                  senders=Outbox().senders, pinger=lambda suffix="": None, data_root=tmp_path)
    assert "late" not in store.open_alerts(store.connect(tmp_path / "tk.db"))


def test_an_empty_holiday_list_raises_an_alert():
    holidays = (pd.Timestamp("2026-12-24").date(), pd.Timestamp("2026-12-31").date())
    assert daily.holiday_alert(holidays, pd.Timestamp("2026-10-01").date()) is None
    assert "2027" in daily.holiday_alert(holidays, pd.Timestamp("2026-12-01").date())
    assert "no day ahead" in daily.holiday_alert(holidays, pd.Timestamp("2027-01-04").date())
