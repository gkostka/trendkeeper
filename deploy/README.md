# Running Trendkeeper on a Pi or Jetson

One always-on device on your Tailscale network runs the daily job; you read it from anywhere with `ssh pi tk`.

## Set up

```sh
# Tailscale, with Tailscale SSH: no router ports open, no SSH keys to manage
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh

# A user for the bot, and its data folder outside the repo
sudo useradd --system --home /var/lib/trendkeeper --shell /usr/sbin/nologin trendkeeper
sudo install -d -o trendkeeper -g trendkeeper -m 750 /var/lib/trendkeeper
sudo usermod -aG trendkeeper "$USER"   # so `tk` can read the status

# The code, Python 3.12 and the locked dependencies
sudo git clone https://github.com/gkostka/trendkeeper /opt/trendkeeper
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /opt/trendkeeper && sudo -E ~/.local/bin/uv python install 3.12 && sudo -E ~/.local/bin/uv sync --frozen
sudo chown -R trendkeeper: /opt/trendkeeper/.venv

# Your own config (email, portfolio size, tax rate) outside the repo, so `git pull` never touches it
sudo install -o trendkeeper -g trendkeeper -m 640 bot/config.toml /var/lib/trendkeeper/config.toml
sudoedit /var/lib/trendkeeper/config.toml
# The bot reads the commit it runs on; git refuses a repo owned by another user unless told it is safe
sudo git config --system --add safe.directory /opt/trendkeeper

# Secrets, readable by the bot only
sudo cp deploy/trendkeeper.env.example /etc/trendkeeper.env
sudo chown trendkeeper: /etc/trendkeeper.env && sudo chmod 600 /etc/trendkeeper.env
sudoedit /etc/trendkeeper.env

# tk, the timers, a first run
sudo install -m 755 deploy/tk /usr/local/bin/tk
echo 'export TK_CONFIG=/var/lib/trendkeeper/config.toml' >> ~/.bashrc
sudo cp deploy/tk-*.service deploy/tk-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo -u trendkeeper sh -c 'set -a; . /etc/trendkeeper.env; tk check'
sudo systemctl start tk-daily.service && tk
sudo systemctl enable --now tk-daily.timer tk-backup.timer
```

The first run downloads the full price history (a few minutes); later runs fetch the last ten days.
Run `tk` from `~/.bashrc` for interactive shells to see the status on every login.

The healthcheck (for example healthchecks.io) needs one check, "daily", with a period of 1 day and a grace
time of a few hours. It emails you when no ping arrives, which is how a dead device is caught.

## Update and roll back

```sh
cd /opt/trendkeeper && sudo git pull && sudo -E ~/.local/bin/uv sync --frozen && sudo .venv/bin/python -m pytest -q
sudo git checkout <previous tag>   # to roll back; each decision records the commit it ran on
```

## Logs

`journalctl -u tk-daily` for the runs, `tk` for the last status, `tk why` for how today's advice was reached.

## Milestone 2 gate: failure drills

Run each on the device and tick it off. Two weeks of on-time summaries, plus all four, close the milestone.

- [ ] **Power cut during a run:** `sudo systemctl start tk-daily.service`, pull the plug within a minute, power up.
      The missed run starts on its own (`Persistent=true`), `tk` shows today's status, and the decision is logged once.
- [ ] **No network:** take the device offline at 17:55 New York time. The run fails, `tk` says FAILED, and the
      healthcheck emails you. Back online, `sudo systemctl start tk-daily.service` recovers.
- [ ] **Broken Slack webhook:** set a wrong TK_SLACK_WEBHOOK. The daily summary arrives by email instead, and the
      next run lists a `notify` alert.
- [ ] **Dead device:** shut it down for a day. The healthcheck emails you before you notice.
