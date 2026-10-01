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
EVENING = datetime(2026, 9, 30, 18, 5, tzinfo=daily.NY)


def fetch(cfg, start):
    return PX[PX.index >= start]


def second_close(ticker, shift=0.0):
    return DAY, float(PX[f"{ticker}.close"][DAY]) * (1 + shift)


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
    assert "US close 2026-09-30" in status and "mix_30_30_40" in status and "Action (mix_30_30_40)" in status
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
    _, outbox, _ = run(tmp_path)  # sources agree again: the alert clears, once
    assert any(s == "Trendkeeper cleared: cross-check:SPY" for _, s, _ in outbox.sent)


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
