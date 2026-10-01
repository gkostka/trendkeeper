"""Nightly backup: the database and your personal files, copied off the device.

    python -m bot.backup

TK_BACKUP_DIR is a folder to copy into (a mounted share, or a local folder); TK_BACKUP_SCP, if set, is an
scp target such as `nas:/backups/trendkeeper/` that the copy is sent to as well. backup.ok records the time
of the last good backup, which the daily job alerts on when it gets old.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from bot import config

KEEP = 14
PERSONAL = ("transactions.csv", "overrides.csv")


def backup(root: Path, dest: Path, scp: str | None = None, now: datetime | None = None) -> Path:
    stamp = f"{now or datetime.now(timezone.utc):%Y-%m-%d}"
    out = dest / stamp
    out.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(root / "tk.db")
    with sqlite3.connect(out / "tk.db") as copy:
        src.backup(copy)  # consistent even while the daily job writes
    src.close()
    for name in PERSONAL:
        if (root / name).exists():
            shutil.copy2(root / name, out / name)
    for old in sorted(p for p in dest.iterdir() if p.is_dir())[:-KEEP]:
        shutil.rmtree(old)
    if scp:
        subprocess.run(["scp", "-q", "-r", str(out), scp], check=True, timeout=600)
    (root / "backup.ok").write_text(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
    return out


if __name__ == "__main__":
    cfg = config.load(config.path())
    dest = os.environ.get("TK_BACKUP_DIR")
    if not dest:
        sys.exit("TK_BACKUP_DIR is not set")
    print(backup(config.data_dir(cfg), Path(dest), os.environ.get("TK_BACKUP_SCP")))
