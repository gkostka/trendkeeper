"""tk: the terminal view of Trendkeeper, made to be run over SSH.

    tk                 the status the last daily run wrote (instant: reads one file, loads no pandas)
    tk why [ID]        how today's target was reached for a strategy (default: the one you follow)
    tk check           config, secrets and data, without running anything
    tk daily           run the daily job now
"""
import os
import sqlite3
import sys
from pathlib import Path

from bot import config


def _cfg():
    return config.load(config.path())


def status(data_dir: Path) -> int:
    path = data_dir / "status.txt"
    if not path.exists():
        print(f"No status yet: the daily job hasn't run ({path} is missing).")
        return 1
    print(path.read_text(), end="")
    return 0


def why(strategy_id: str | None) -> int:
    from bot import store

    cfg = _cfg()
    sid = strategy_id or cfg.follow
    db = store.connect(config.data_dir(cfg) / "tk.db")
    rows = store.decisions(db, sid, limit=1)
    if not rows:
        print(f"No decision logged for {sid} yet.")
        return 1
    d = rows[0]
    print(f"{sid}: decision for the US close of {d['day']}, run {d['run_at']}, commit {d['git_commit']}, "
          f"config {d['config_hash']}")
    for sig in d["signals"]:
        print(f"  {sig['signal']} for {sig['fund']}: above {sig['count']:.0%} of its averages")
        for w in sig["windows"]:
            print(f"    {w['window']:>3}-day average: {w['distance']:+.2%} {'above' if w['distance'] > 0 else 'below'}")
    for s in d["slices"]:
        pending = "" if s["pending"] is None else f", moving to {s['pending']:.0%} at the next open"
        print(f"  {s['fund']}: {s['value']:,.0f} {cfg.base_currency}, invested {s['invested']:.0%}{pending}")
    if d["held_back"]:
        print(f"  Held back: {d['held_back']}")
    for a in d["advice"]:
        print(f"  Advice: {a}")
    print("  Closes used (each in its own currency): " + ", ".join(f"{k} {v:,.4g}" for k, v in sorted(d["prices"].items())))
    return 0


def check() -> int:
    from bot import store

    problems = []
    try:
        cfg = _cfg()
        print(f"config: ok ({config.path()})")
    except config.ConfigError as e:
        print(f"config: {e}")
        return 1
    used = set(cfg.notify.alerts + cfg.notify.daily + cfg.notify.weekly)
    need = {"slack": ["TK_SLACK_WEBHOOK"], "email": ["TK_SMTP_HOST", "TK_SMTP_USER", "TK_SMTP_PASSWORD"]}
    for ch in sorted(used):
        missing = [v for v in need[ch] if not os.environ.get(v)]
        problems += [f"secret {v} is not set (needed for {ch})" for v in missing]
    if not os.environ.get("TK_HEALTHCHECK_DAILY"):
        problems.append("secret TK_HEALTHCHECK_DAILY is not set: a dead device would go unnoticed")
    root = config.data_dir(cfg)
    try:
        db = store.connect(root / "tk.db")
        last = store.last_price_day(db, "SPY.close")
        print(f"data: {root} writable, latest SPY close {last:%Y-%m-%d}" if last else f"data: {root} writable, no prices yet")
    except (OSError, sqlite3.Error) as e:
        problems.append(f"data dir {root}: {e}")
    for p in problems:
        print(f"problem: {p}")
    print("check: ok" if not problems else f"check: {len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        try:
            root = config.data_dir(_cfg())
        except (OSError, ValueError):  # a broken config must not hide the last status
            root = Path(os.environ.get("TK_DATA_DIR", config.Config.__dataclass_fields__["data_dir"].default))
        return status(root)
    if cmd == "why":
        return why(argv[1] if len(argv) > 1 else None)
    if cmd == "check":
        return check()
    if cmd == "daily":
        from bot import daily

        return daily.run()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
