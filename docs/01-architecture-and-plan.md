> Exported on 2026-10-01 from the live doc: https://claude.ai/code/artifact/df7763ce-b0ee-4664-a103-bdbfa843d65e
> Diagrams and charts appear here only as placeholders; see the live doc for them. The live doc is the source of truth.

# Trendkeeper — Architecture & Implementation Plan

Sep 30, 2026 · @Grzegorz Kostka

## Goals and scope

v1 is an advisor, not a trader. Once a day after the US close, it checks the signals for every strategy you define and tracks how each would have done since your start date. It compares them with buying and holding the S&P 500 and Nasdaq-100, and sends you a summary of what to do with your own holdings. A local HTML report shows how it reached each recommendation. IBKR order execution stays optional and comes last.

In scope for v1:

- Define any number of strategies in one config file: slices of funds, each either held or trend-following, with weights and rebalancing
- Benchmarks (SPY and QQQ buy-and-hold) are ordinary strategies, so every strategy is compared on the same footing
- One engine runs both the historical backtest and the daily update, so live numbers match the research
- Alerts at once, a daily summary and a weekly summary, by Slack and email: signals, each strategy's target, what to buy or sell, and performance against the benchmarks
- A local HTML report: today's signals and why, equity curves against the benchmarks, your holdings against the target, and a log of every decision
- Your holdings entered by hand (or read from IBKR later), so recommendations are sized to your real portfolio
- A terminal command, `tk`, with the same views as the report, reachable over SSH from anywhere
- Runs on a home Raspberry Pi or NVIDIA Jetson on your Tailscale network, unattended

Built in this order, so nothing extra is built before the strategy has proven itself. Milestones 2 and 3 are the core: the daily job, Slack and email alerts with the daily summary, and `tk`, `tk why`, `tk check`, `tk trade` and `tk portfolio`. The HTML report, the weekly summary and the other `tk` views come in milestone 4, and only if a month of daily use shows you miss them.

Later, each switched on separately:

- Read-only IBKR connection: import positions and prices automatically
- IBKR paper trading, then live trading, with the risk controls below
- Intraday strategies, multiple accounts

Not planned: microservices, message queues, a user system. It's a single-user tool.

## Architecture overview

The bot is a daily job plus a local report. On each US trading day after the close, it catches up any missed days, updates and checks prices, and runs the strategy engine for every strategy. It backtests each one over history and since your start date, and logs what it saw and recommended. Then it compares your holdings with the strategy you follow and sends you a summary. The report and the tk terminal command read that database. It all runs on a home Pi or Jetson that you reach over Tailscale.

&#91;embedded content: advisory bot · daily job on a home Pi, report and tk, IBKR optional\]

Only the optional broker adapter knows IBKR exists. Switching it on first replaces the hand-written holdings file with real positions, and only much later lets the advisor's trade list become orders.

## Components

Each component is one Python module. The engine is the core: the backtest, the daily run and the report all call it, so they can't disagree.

| Component | Responsibility | Notes |
| --- | --- | --- |
| Config | `config.toml`: base currency, execution timing, instruments, strategies, benchmarks, the strategy you follow. Checked at the start of every run and by tk check: weights add up to 1, every strategy has a tax_rate, every fund is an instrument, windows are valid, secrets are present | Built-in `tomllib`; secrets (Slack webhook, SMTP password, IBKR login) only in /etc/trendkeeper.env, readable by the bot's user alone |
| Instruments | Each fund's currency; for leveraged funds also what it tracks, its leverage, its measured cost and how EUR/USD enters its price | Lets the backtest build a fund's history before its launch, and value UCITS funds correctly. Each leveraged fund also names its financing rate (T-bill or ECB deposit rate), the one its cost was calibrated with. Cash is an instrument too: a rate series (ECB deposit rate minus IBKR's spread for EUR, T-bill for USD) |
| Market data | Daily opens and closes for signal ETFs, funds and EUR/USD, cached in SQLite; fetches only what's missing. SPY and QQQ closes are cross-checked with a second free source (Stooq CSV); if they differ by more than 0.1%, the day is alerted and not acted on | Sanity checks: rejects one-day moves above 25% that its index doesn't explain, flags stale prices. A bad day is skipped and alerted, never acted on. A hand-edited overrides file fixes a bad price; US trading days come from SPY's own rows, so no calendar library |
| Strategy engine | Steps the portfolio forward one day: from yesterday's state (shares per slice, and cash per currency) and prices up to today, returns today's targets and trades. Trend slices from their moving averages, hold slices fixed, monthly rebalance, plus a trade delay (same close, next open or next close) | Pure functions with state passed in, because slices drift between rebalances; the backtest is a loop over the same step the daily run calls once |
| Backtester | Every strategy over history and since your start date, with fund costs, cash interest, the measured trade cost and the chosen trade delay. Applies the live rules too: whole shares, the minimum trade size, after-tax results with FIFO lots at each strategy's own rate | Must reproduce the research on a saved price snapshot. Buying a USD fund with euros pays the currency conversion cost. "Since start" replaces separate shadow portfolios. Recomputed on demand (seconds), not stored |
| Decision log | What the bot saw and recommended each day: prices used, signals, targets, trade list, plus the git commit and a hash of the config | Never changed after writing, so later data revisions can't rewrite history. SQLite triggers reject UPDATE and DELETE on it |
| Holdings and advisor | Your trades, fees and deposits (`transactions.csv`, IBKR later); holdings, time-weighted returns and tax lots are derived from it. Your target is the followed strategy's weights times your portfolio value; the gap becomes a trade list in your base currency, sells before buys, with any EUR/USD conversion it needs. Entered with tk trade, which checks each row | Rounds to whole shares (UCITS ETFs at IBKR EU have no fractions) and skips trades below a threshold, for example 2% of the portfolio; the backtest applies both |
| Daily job | On US trading days after the close: catch up missed days, update data, run the engine, log, recommend, notify | Safe to re-run; uses the last price for funds whose exchange was closed. Pings a healthcheck service on success, so a run that never happened is alerted from outside. A late run recommends from today's state and says it's late; it never replays old trades |
| Notifications | Alerts, daily and weekly summaries to Slack (incoming webhook) and email (SMTP); the config routes each kind of message to its channels | Standard library only (urllib, smtplib). If one channel fails, the message goes to the other and the failure shows in the next report. An alert is sent when a problem starts and when it clears, not every day; open ones stay listed in the daily summary |
| UI | A static HTML report the daily job writes, and the tk terminal command with the same views: today, strategies against SPY and QQQ in your currency, your portfolio, decision log | No server: the report is served inside the tailnet by tailscale serve, tk runs over SSH. Move to Streamlit only if you want interactive filters |
| Storage | SQLite: prices, decision log, recommendations, open alerts. Lives with your transactions in /var/lib/trendkeeper, outside the repo | One file, easy to back up |
| Broker adapter (optional) | `ib_async` with IB Gateway: read positions (milestone 5), place orders (milestone 6, which also adds paper and live modes) | The IBKR and risk sections below apply from then |

## Defining strategies

A strategy is a list of slices. Each slice has a weight and a fund, and either holds the fund (`hold`) or follows the trend rule on a signal ETF (`trend`). Benchmarks are strategies with a single `hold` slice. Every strategy in the research, and new ones, fits this shape:

```toml
base_currency = "EUR"     # portfolio, benchmarks and trade amounts in this currency
follow = "mix_30_30_40"   # the strategy your holdings are compared against
start = 2026-10-01        # "since start" results begin here
execution = "next_open"   # same_close | next_open | next_close
trade_cost = 0.0005       # per side; research value until milestone 1 measures commission + half spread
fx_cost = 0.00002         # IBKR manual EUR/USD conversion: 0.002% per conversion
fx_min = 2.0              # ...with a minimum of USD 2 per conversion
min_trade = 0.02          # skip trades under 2% of the portfolio, live and in the backtest
whole_shares = true       # UCITS ETFs at IBKR EU have no fractional shares
cash = { EUR = "EUR_CASH", USD = "USD_CASH" }   # what uninvested money earns, per currency
xetra_holidays = [        # weekdays Xetra is shut (Deutsche Börse); add the next year each December
  2026-12-24, 2026-12-25, 2026-12-31,
  2027-01-01, 2027-03-26, 2027-03-29, 2027-12-24, 2027-12-31,
]
data_dir = "/var/lib/trendkeeper"   # transactions, overrides, database: outside the repo

[instrument.EUR_CASH]
currency = "EUR"
rate = "ecb_dfr"          # research/ecb_dfr.csv
spread = 0.005            # IBKR Pro pays the benchmark rate minus 0.5%
free = 10000              # nothing on roughly the first USD 10,000 equivalent
full_rate_nav = 100000    # below this account size (USD) the rate scales down in proportion

[instrument.USD_CASH]
currency = "USD"
rate = "tbill"
spread = 0.005
free = 10000
full_rate_nav = 100000

[instrument.SPY]
currency = "USD"

[instrument.QQQ]
currency = "USD"

[instrument."DBPG.DE"]    # Xtrackers S&P 500 2x
currency = "EUR"
tracks = "SPY"
leverage = 2
cost = 0.0094             # yearly, applied daily; measured with bot.calibrate
financing = "tbill"       # the rate that cost was measured against
fx = "converted"          # converted: EUR/USD counts once; leveraged: twice (CL2)

[instrument."LQQ.PA"]     # Amundi Nasdaq-100 2x
currency = "EUR"
tracks = "QQQ"
leverage = 2
cost = 0.0139
financing = "tbill"
fx = "converted"

[instrument."SXRM.DE"]    # iShares $ Treasury 7-10yr, unhedged, USD line (hedged IBB1 or a EUR line: open question)
currency = "USD"

[[strategy]]
id = "mix_30_30_40"       # never edit the rules of an id in use; add a new id instead
name = "Mix 30/30/40"
rebalance = "monthly"
tax_rate = 0.0            # tax on realized gains for the account it runs in; lots matched FIFO

  [[strategy.slice]]
  weight = 0.30
  fund = "DBPG.DE"
  rule = "trend"
  signal = "SPY"
  windows = [200, 250, 300]

  [[strategy.slice]]
  weight = 0.30
  fund = "LQQ.PA"
  rule = "trend"
  signal = "QQQ"
  windows = [200, 250, 300]

  [[strategy.slice]]
  weight = 0.40
  fund = "SXRM.DE"
  rule = "hold"

[[strategy]]
id = "spy"
name = "S&P 500 buy-and-hold"
benchmark = true
tax_rate = 0.0            # same rate as the strategies it is compared with

  [[strategy.slice]]
  weight = 1.0
  fund = "SPY"
  rule = "hold"
```

These rules tie the config to the research and to real trading:

- **Signals come from the US ETFs** (SPY or QQQ in USD), even when the fund held is a UCITS one, so they match the backtest.
- **Before a fund's price history begins,** the backtester builds it from what the fund tracks, its leverage, its measured cost and its financing rate. That is how the research reached back to 1994. In EUR this needs EUR/USD before the euro existed: use the DEM rate converted at the fixed 1.95583 for 1994–1998, or start EUR backtests in 1999.
- **`execution` sets when a signal becomes a trade.** `next_open` matches a European account trading the morning after the US close; `same_close` is what the research assumed and is used only to reproduce it. Market-on-close in the Strategy rules tab describes that research setting, not a European account.
- **The backtest applies the live rules.** Whole shares, `min_trade`, cash interest and each strategy's own `tax_rate` all apply in the backtest too, so its numbers are what you could really have earned.
- **The trade cost is measured, not assumed.** Spreads on Xetra and Paris leveraged ETFs are wide in the first 15–30 minutes. Measure them, and trade after 09:30 CET if that halves the cost.
- **Your target is the strategy's weights applied to your money.** Each day the engine gives the followed strategy's slice weights (from the counts and the last rebalance). Your target is those weights times your real portfolio value; the advisor turns the gap into trades. The drawdown stop compares the simulated strategy with its backtest worst, since that is the like-for-like number; your real account's drop is reported next to it.
- **Changing a strategy's rules means a new `id`.** "Since start" is recomputed from the config, so editing a strategy in place would rewrite its past. Keep the old one, add the new one with its own `id`, and switch `follow`; the config hash in the decision log shows when.
- **Trades wait for the European market.** Advice says "at the next Xetra open", which skips the days in `xetra_holidays`; US trading days alone can't tell you when Xetra is shut.
- **Tax is set per strategy.** Each `[[strategy]]` carries its own `tax_rate`, so one can model a taxable account and another a tax-free wrapper. It is required: `tk check` fails if a strategy has none, rather than silently assuming 0%. After-tax results value every strategy, benchmarks included, as if sold at the end, so a buy-and-hold that never sells isn't flattered.

What the daily summary contains:

- **Signals:** SPY and QQQ against their 200/250/300-day averages, the distance to the next crossing, and any change since yesterday
- **Action for you:** for the strategy you follow, "no change" or a short list such as "sell €3,200 of DBPG at tomorrow's open"
- **Every strategy:** today's target; return month-to-date, year-to-date and since start; current drop from peak. All in your base currency, against SPY and QQQ converted to it
- **Alerts:** missing, stale or rejected prices; a late run (a run that never happened is caught by the outside healthcheck); a 2× fund drifting from 2× its index over a week (not daily, since European funds close 4.5 hours earlier); a drop beyond 1.5× the strategy's backtest worst; a signal ETF within 1% of one of its averages, the day before a likely trade
- **Waiting for you:** advice from earlier days with no matching row in your transactions yet

What the weekly summary contains (Saturday morning):

- **The week:** each strategy's return against SPY and QQQ in your base currency, and every signal change
- **Advised against done:** the decision log compared with `transactions.csv`, so you see whether you followed it
- **Health:** data problems, tracking drift, drop from peak against the backtest's worst, failed notifications
- **Attached:** the HTML report. The database is backed up every night to another machine on your tailnet; attaching it here is optional, since it holds your full financial history

The transactions file (`/var/lib/trendkeeper/transactions.csv`) has one row per event, written by `tk trade` or by hand. Types: buy, sell, deposit, withdrawal, dividend, interest, fee, fx (a currency conversion: quantity in the currency bought, price in euros per unit). Example rows:

```csv
date,type,fund,quantity,price,currency,fees,note
2026-10-02,deposit,,,10000,EUR,0,
2026-10-02,fx,USD,4600,0.8700,EUR,2.00,for SXRM
2026-10-02,buy,DBPG.DE,35,85.40,EUR,3.00,
2026-10-02,buy,SXRM.DE,24,190.10,USD,2.50,
2026-12-15,dividend,IBB1.DE,,12.40,EUR,0,distributing class only
```

## Interactive Brokers specifics

*Applies from milestone 5, when the IBKR connection is switched on. The advisory bot doesn't need any of it.*

The bot never talks to IBKR servers directly. It talks over a local socket to IB Gateway (or TWS), which holds the login session. Most operational pain with IBKR comes from that Gateway, so plan for it from day one.

- **Gateway, not TWS.** IB Gateway is the headless, lighter app meant for API use. TWS works too but is heavier and easier to break by clicking around.
- **API library: `ib_async`.** The maintained successor of `ib_insync`, an asyncio wrapper over the official TWS API. Much less boilerplate than IBKR's raw `ibapi` callbacks. The Client Portal Web API exists but is a worse fit for a long-running bot.
- **Ports.** Gateway defaults: 4002 paper, 4001 live (TWS: 7497 paper, 7496 live). Keep paper and live as separate config profiles so you cannot point live code at the wrong one by accident.
- **Login and daily restart.** Gateway requires a login with 2FA and restarts itself daily; there is also a forced re-auth roughly weekly. Use IBC (IB Controller) to automate login and restarts, and make the bot reconnect and resync automatically. IBC was retired on 1 Sep 2026 and now gets bug fixes only (see Existing open-source projects).
- **Client IDs.** Each API connection uses a client ID; orders are tied to it. Use a fixed ID for the bot so it can see and manage its own open orders after a restart.
- **Market data.** A daily strategy needs only end-of-day prices, so paid real-time subscriptions are optional. Delayed data is enough to check prices before placing market-on-close or opening orders.
- **Pacing limits.** IBKR throttles API messages and historical data requests, which barely matters for a handful of daily requests. Cache history in SQLite and backfill only the gap.
- **Contracts.** Always qualify contracts (`qualifyContracts`) and store the `conId`. Ambiguous symbols are a classic source of wrong-instrument orders.
- **Paper account limits.** Paper fills are simulated and optimistic, so treat paper P&L as an upper bound.

Limits above are approximate and from memory; check IBKR's current API docs before relying on exact numbers.

## Risk controls and safety

*Applies once the bot places orders (milestone 6). In advisory mode, you are the risk control: the bot only recommends.*

Risk is the one part not to keep minimal. A bug in the strategy should cost a rejected order, not the account.

Pre-trade checks (every order, in the risk manager):

- Only funds listed under `[instrument]` in the config
- No single order above a set share of the portfolio (for example 40%); the strategy never needs more
- At most a few orders a day; the strategy needs three or four at most
- No orders when prices are stale or failed the data checks
- Order types that match the backtest: market-on-close for US funds, opening orders for UCITS funds

Circuit breakers:

- Kill switch: a file flag (plus a Slack command only if the bot by then runs as a long-lived process) that cancels open orders and blocks new ones
- Gateway disconnected: no new orders until reconnected and positions match IBKR
- Drop beyond 1.5× the strategy's backtest worst: stop trading and alert (see the Strategy rules tab)
- No daily-loss limit that sells everything: a 2× fund can fall 10% on an ordinary bad day, and selling then would break the strategy

Reconciliation:

- On start and after every reconnect, pull positions, open orders and executions from IBKR and overwrite local state
- If local and IBKR state disagree mid-session, alert and halt rather than guess

Backstops outside the bot:

- Set maximum order value and size in IBKR's own order precautions settings
- No stop-loss orders: the moving averages are the exit, and a stop would turn it into a different, untested strategy

## Strategy lifecycle

A strategy reaches real money in steps, with the same engine and config at every step. Only where the orders come from changes.

1. **Backtest.** Every strategy from 1994 to today, with calibrated fund costs, the measured trade cost, cash interest, whole shares, taxes and your execution setting. Keep a period you never tune on.
2. **Advisory.** The bot recommends; you place the orders by hand at small size. The decision log shows what it advised and when.
3. **IBKR read-only.** IBKR's positions and executions replace `transactions.csv`; the bot still only recommends.
4. **Paper trading.** The bot places orders on IBKR's paper account for 2–4 weeks, to prove restarts, partial fills and data gaps are handled. Paper fills are optimistic.
5. **Live, small.** Same config on the live account at a fraction of the target size; scale up once live results track paper.

The engine's core stays one function, so every step above runs the same code:

```python
def step(strategy: Strategy, state: State, prices: pd.DataFrame, day: date) -> tuple[State, list[Trade]]:
    """The strategy's holdings and trades after `day`, from yesterday's state and prices up to `day` only."""
```

The backtest is a loop over `step` from 1994; the daily run is one `step` from yesterday's saved state. Targets can't be a function of prices alone: slices drift between rebalances, and each signal trade moves a third of the slice's current value.

## Tech stack and deployment

Python on a home Raspberry Pi or NVIDIA Jetson that is always on and joined to your Tailscale network: two scheduled jobs, a report and a terminal command, no server and no broker. Docker comes only when IBKR is switched on.

| Concern | Choice | Why |
| --- | --- | --- |
| Language | Python 3.12, installed with uv (Raspberry Pi OS ships 3.11, JetPack 6 ships 3.10); dependencies pinned in pyproject.toml and uv.lock | The research code is already Python |
| Data and maths | `pandas`, `numpy` | Standard; the backtests already use them |
| Market data | `yfinance` daily closes, cached in SQLite; SPY and QQQ cross-checked against Stooq | Free and enough for daily signals, but unreliable for some UCITS funds, so every price passes the sanity checks; pin its version and its auto\_adjust setting, since adjusted closes are revised after each dividend; swap for IBKR data in milestone 5 |
| Config | TOML via built-in `tomllib` | No extra dependency |
| Storage | SQLite (built-in `sqlite3`) | One file, zero setup. WAL mode, on a USB SSD if possible (SD cards wear out), and backed up off the device nightly |
| UI | Static HTML written by the daily job, plus tk, a terminal command on argparse (Streamlit later, if wanted) | No server and no extra dependency; pandas prints tk's tables. The report is served inside the tailnet with tailscale serve, tk runs over Tailscale SSH. Streamlit, if added, stays read-only and bound to localhost (\`server.address = "localhost"\`) |
| Notifications | Slack through an incoming webhook (built-in urllib), and email via built-in `smtplib` | No extra service |
| Scheduling | systemd timers in New York time, after the US close, with Persistent=true: a missed run starts after a reboot or power cut, the job still catches up missed days itself, and it pings a free healthcheck service, which alerts you if no ping arrives | No scheduler library needed |
| Tests | `pytest` on the engine | One test reproduces the research on a saved price snapshot, so data revisions can't break it. A look-ahead test appends future prices and checks that no earlier day's result changes. test_advisor covers whole-share rounding, sells before buys, currency conversion and the 2% threshold; test_data covers the sanity checks and the cross-check |
| Broker (later) | `ib_async` with IB Gateway in Docker (`gnzsnz/ib-gateway-docker`) | Only from milestone 5 |

Suggested layout:

```
pyproject.toml, uv.lock   # pinned dependencies
bot/
  config.toml       # currency, execution, cash, tax, holidays, notify routing, instruments, strategies, benchmarks
  data.py           # prices, EUR/USD and rates: download, cross-check, sanity checks, overrides, SQLite cache
  engine.py         # instruments, slices, signals, step(), backtest
  advisor.py        # your holdings vs target -> whole-share trade list in your currency
  daily.py          # the daily job: check config, catch up, update, run, log, recommend, notify, ping
  weekly.py         # the weekly summary
  notify.py         # Slack and email: routing, fallback, start and clear of alerts
  report.py         # writes the static HTML report and the status text
  cli.py            # tk: status, strategies, why, portfolio, log, now, trade, check, daily --dry-run
  broker.py         # IBKR via ib_async, added in milestone 5
deploy/
  tk-daily.service, tk-daily.timer
  tk-weekly.service, tk-weekly.timer
  tk-backup.service, tk-backup.timer
  trendkeeper.env.example   # secrets template; the real file lives in /etc
research/           # the backtest scripts behind this doc, frozen once engine.py reproduces them
tests/
  data/             # saved price snapshot
  test_engine.py    # reproduces the research numbers; look-ahead check
  test_advisor.py   # rounding, order, conversion, threshold
  test_data.py      # sanity checks, cross-check, overrides

/var/lib/trendkeeper/   # on the device, never in git
  transactions.csv, overrides.csv, tk.db, status.txt, report/
```

## Running at home

The bot runs unattended on a Raspberry Pi or NVIDIA Jetson at home, joined to your Tailscale network. You check it from anywhere with `ssh pi tk`, open the HTML report on any of your devices, and get alerts and summaries by Slack and email.

| Need | How | Why |
| --- | --- | --- |
| Status from anywhere | `tk` over Tailscale SSH (`tailscale up --ssh`) | No open router ports and no SSH keys to manage; Tailscale's access rules decide which of your devices can log in |
| Status on login | `tk` from `~/.bashrc` prints `status.txt`, which the daily job writes | Instant: importing pandas on a Pi takes about 2 seconds, so only the other subcommands compute |
| Report on your phone | `tailscale serve` on the report folder, HTTPS inside the tailnet only | Never `tailscale funnel`, which makes it public; check `tailscale serve --help`, the syntax changed between versions |
| Daily run | `tk-daily.timer`: weekdays 18:00 America/New_York, `Persistent=true` | Two hours after the US close, when the day's close is final, and still before the European open (00:00 CET). Holds through both daylight-saving switches; reruns after a power cut. US holidays come from SPY's rows |
| Weekly summary | `tk-weekly.timer`: Saturday 09:00 in your time zone | Sent by email with the report attached, and a short version to Slack |
| Nightly backup | `tk-backup.timer`: `sqlite3 tk.db ".backup …"` and the transactions file, copied to another tailnet machine | The decision log and your transactions can't be rebuilt |
| A dead device | Two healthcheck checks, one for the daily run and one for the weekly; the service emails you when a ping is missing | The Pi is your alarm system, so its own failure must be caught from outside |
| Logs and health | journald (`journalctl -u tk-daily`), and `tk`: last run and its result, last ping and backup, open alerts | One command answers "is it working?" |
| Code updates | `git pull && uv sync --frozen && pytest -q`; roll back with `git checkout <previous tag>` | Tag each version you deploy; the decision log records the commit |
| Secrets | `/etc/trendkeeper.env`, mode 600, loaded by systemd's `EnvironmentFile` | Slack webhook URL, SMTP login, healthcheck URLs, later IBKR; never in the repo or config |

The terminal command, on `argparse` with pandas printing the tables:

| Command | Shows or does | Milestone |
| --- | --- | --- |
| `tk` | Alerts, today's signals and the distance to each crossing, your action, one line per strategy, and the last run, ping and backup | 2 |
| `tk why <id>` | How today's target was reached: prices, averages, count, target, trades, commit | 2 |
| `tk check` | Validates the config and the secrets without running anything | 2 |
| `tk trade buy DBPG.DE 35 @ 85.40 [--fees 3]` | Checks the row (known fund, sensible price, enough cash) and appends it to the transactions file | 3 |
| `tk portfolio` | Your holdings against the target, the drift, and advice not yet acted on | 3 |
| `tk strategies` | Every strategy against SPY and QQQ: month-to-date, year-to-date, since start, drop from peak, a text sparkline | 4 |
| `tk log [--days 30]` | The decision log, newest first | 4 |
| `tk now` | A delayed live quote: what the count would be if the market closed now | 4 |
| `tk daily --date 2026-09-15 --dry-run` | Replays a past day's decision from the saved prices: no writes, no messages | 4 |

Signals change once a day, so a full-screen interface that refreshes itself isn't worth its code. Plain text also works from a phone SSH client; `rich` can add colour later in a few lines.

Notification routing in the config:

```toml
[notify]
alerts = ["slack", "email"]   # when a problem starts and when it clears
daily  = ["slack"]            # signals, action, open alerts, advice waiting for you
weekly = ["email", "slack"]   # email carries the report
attach_db = false             # the nightly backup already copies it off the device
email_to = "you@example.com"
timezone = ""                 # for the weekly summary, for example "Europe/Berlin"
# secrets in /etc/trendkeeper.env: TK_SLACK_WEBHOOK, TK_SMTP_HOST, TK_SMTP_USER, TK_SMTP_PASSWORD,
# TK_HEALTHCHECK_DAILY, TK_HEALTHCHECK_WEEKLY
```

Alerts are sent for the strategy you follow; the summaries cover every strategy. If one channel fails, the message goes to the other.

Device notes:

- **Python:** Raspberry Pi OS (Bookworm) ships 3.11 and JetPack 6 ships 3.10, so install 3.12 with `uv python install 3.12`. pandas and numpy have ARM64 wheels.
- **Storage:** SD cards wear out and can corrupt on power loss. Run SQLite in WAL mode, preferably on a USB SSD. The decision log and your transactions can't be rebuilt, so the backup timer copies them off the device every night (`sqlite3 tk.db ".backup …"` to another tailnet machine).
- **Clock and power:** NTP keeps the clock right; a small UPS or a clean shutdown on power loss protects the database.
- **IBKR later:** IB Gateway is a Java app. Check that the `gnzsnz/ib-gateway-docker` image runs on ARM64 before milestone 5; nothing earlier depends on it.

## Existing open-source projects

NautilusTrader already does most of what this doc plans: one engine for backtest and live, a risk engine, and a maintained IBKR adapter that can manage IB Gateway in Docker. But its v2 is still a release candidate with open IBKR reconciliation bugs, so the plan stays: build the lean `ib_async` version, and keep the strategy portable so it can move to NautilusTrader later.

Detailed review and recommendation: Framework review

| Project | What it is | IBKR support | Stars | License | Last push | Fit |
| --- | --- | --- | --- | --- | --- | --- |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Event-driven trading engine, Rust core with Python API | Native adapter for TWS/Gateway; can run the gnzsnz Gateway container ([docs](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/integrations/interactive_brokers.md)) | 29.5k | LGPL-3.0 | 2026-10 | Best match: same architecture as this doc, production-grade. Steeper learning curve |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | Algorithmic trading engine (C#, strategies in Python or C#) | Via [IB brokerage plugin](https://github.com/QuantConnect/Lean.Brokerages.InteractiveBrokers) | 21.8k | Apache-2.0 | 2026-09 | Mature and broad, but heavy; built around QuantConnect's CLI and cloud |
| [pysystemtrade](https://github.com/pst-group/pysystemtrade) | Rob Carver's systematic futures framework | Live trading via `ib_async` | 3.5k | GPL-3.0 | 2026-09 | Only if your strategy is systematic futures in Carver's style |
| [Lumibot](https://github.com/Lumiwealth/lumibot) | Multi-broker Python bot framework | IBKR (TWS API and REST) among 12 brokers | 2.1k | GPL-3.0 | 2026-09 | Simplest start for daily stock/options strategies; now pushes its hosted, AI-agent features |
| [mmr](https://github.com/9600dev/mmr) | Python algo-trading platform for IBKR | IBKR only | 132 | unclear | 2026-09 | Small, one maintainer; useful to read, risky to depend on |
| [High-Frequency-Trading-Model-with-IB](https://github.com/jamesmawm/High-Frequency-Trading-Model-with-IB) | Example pairs / mean-reversion bot | IBKR API | 2.9k | MIT | 2025-05 | Learning example, not a framework |
| [backtrader](https://github.com/mementum/backtrader) | Backtesting library with an old IB store | Outdated | 23.4k | GPL-3.0 | 2024-08 | Unmaintained; avoid for live trading |

Building blocks you will use either way:

| Project | Role | Stars | License | Last push | Notes |
| --- | --- | --- | --- | --- | --- |
| [ib\_async](https://github.com/ib-api-reloaded/ib_async) | Python wrapper for the TWS API | 1.7k | BSD-2 | 2026-08 | Successor to [ib\_insync](https://github.com/erdewit/ib_insync), which is archived |
| [ib-gateway-docker](https://github.com/gnzsnz/ib-gateway-docker) | IB Gateway + IBC in a Docker image | 1.3k | MIT | 2026-09 | Used by NautilusTrader; bundles IBC |
| [IBC](https://github.com/IbcAlpha/IBC) | Automates Gateway login and restarts | 1.6k | GPL-3.0 | archived | Retired on 1 Sep 2026: bug fixes only, no new development, no named successor |
| [vectorbt](https://github.com/polakowo/vectorbt) | Fast vectorized backtesting for research | 9.2k | custom | 2026-09 | Research only, no live trading |

IBC's retirement is the biggest risk found. Gateway auto-login still works today, but a future IBKR login change may break it with no upstream fix. Watch the ib-gateway-docker repo for a replacement, and keep the alerting on disconnects so a broken login is caught the same day.

Stars and dates read from GitHub on 2026-09-30.

## Implementation milestones

Six milestones, each closed by a gate. The first three give you a working advisor that you follow by hand; the fourth adds the report and weekly summary, only if you miss them. The last two connect IBKR and are optional. Dates depend on your time per week, so none are set here.

&#91;embedded content: roadmap · 6 milestones, 2 optional\]

Milestone 1 starts by porting the final research logic (spread over `bt.py` to `bt9.py`) into `engine.py`, until the snapshot test reproduces the research numbers. From then on the engine, not the scripts, is the source of truth. The milestone ends with the strategy re-tested on that engine the way you will really trade it: the day after the signal, with a small buffer around the averages, with the measured spread at the open, and after tax. If those results fall well short of the research, the plan is revised before anything else is built. Milestone 2's gate includes failure drills on the device: pull the power during a run, cut the network, break the Slack webhook. The run must catch up, the outside healthcheck must fire, and messages must fall back to email. Milestone 3 is where real money starts, placed by you.

## Milestone 1 gate, fixed in advance

The pass marks are set now, before the next-day test runs, so the result can't be argued into a pass afterwards. The test runs 30/30/40 on the engine with `next_open`, the measured trade cost, cash at IBKR's real rate, whole shares on your planned portfolio size, and tax at your rate. It runs in EUR from 1999 and in USD from 1994.

| Test | Pass mark | Research (US funds, same close, no tax) | Milestone 1 run (UCITS in EUR, next open, from 1999, no tax) |
| --- | --- | --- | --- |
| Return over the full period | At least 1 point a year above SPY buy-and-hold, in the same currency | 13.4% against 10.9% | 12.36% against 8.80%: passes |
| Worst drop | No worse than −40% | −30% | −30.7%: passes |
| Each period: 1994 (or 1999)–2006, 2007–2016, 2016–2026 | Return divided by worst drop above SPY's in all three | Not measured this way | 0.26, 0.58, 0.62 against 0.03, 0.16, 0.45: passes |
| The neighbourhood | Every mix with 20–40% in each trend slice and bonds for the rest beats SPY on return divided by worst drop in all three periods | Not run | 25 of 25: passes |

Run on 1 Oct 2026 with `python -m bot.gate bot/config.toml … next_open 1999-01-04`: IBKR cash interest on a €30,000 start, whole shares counted at the exchange quote, the 2% minimum trade, monthly rebalances at the open after the month ends, no buy larger than the cash on hand, currency conversion costs, and the cost of selling at the end. Annual returns are over calendar years. Re-run after the milestone 1 review on 1 Oct 2026; the first run (12.15% against 8.66%) rebalanced at the month's last close and let small trades borrow. Still provisional on three inputs: the trade cost is the research's 0.05% until measured, the tax rate is 0%, and the start size is a placeholder. The same gate on the research's US setup from 1994 also passes (13.18% against 10.86%). A start before the data, such as the EUR setup from 1994, is refused rather than run on flat prices.

The neighbourhood test answers the overfitting worry: 30/30/40 was picked after seeing the data, so it only counts if the mixes around it pass too. That shows a plateau, not a lucky peak. Changed on 1 Oct 2026 after an engine preview: the first wording asked every neighbour to clear the return and drop marks. Mixes with more bonds earn less by design, so 6 of 25 missed the 1-point return mark and 40/40/20 fell 41.4%; that measured leverage, not overfitting. The risk-adjusted wording tests what the neighbourhood check is for. The preview also isn't the gate: that runs with measured costs, tax, whole shares and the UCITS funds in EUR.

Two more results are recorded but don't decide the gate:

- **Buffer around the averages** at 0%, 1% and 2%. A buffer is adopted only if it improves the result in all three periods; otherwise it stays at 0. Result: 1% and 2% each raise the full-period return (12.63% and 12.96%) but worsen at least one period, so the buffer stays at 0.
- **Tax sensitivity** at 0%, 20% and 30%, so the size of the tax drag is known before your rate is settled. Result: 10.20% against SPY's 8.02% at 20%, and 9.10% against 7.57% at 30%, both valued as if sold at the end.
- **Trading at the next close instead of the next open**, because about 10 of the 27 years use modelled UCITS prices from before DBPG, LQQ and SXRM listed (2009–10), and their modelled open is 2× SPY's opening gap, not the real 09:00 open. Result: the gate passes either way, 12.08% against SPY's 8.80% at the next close with a −26.5% worst drop. In 1999–2007 the next open scores lower (0.26 against 0.34), so the modelled open doesn't flatter the result.

If it fails:

1. **Fails only on costs or tax:** retest once with the 300-day average alone, which trades about half as often. One retest only, so the gate isn't tuned until it passes.
2. **Fails again, or fails on the drop or the periods:** don't trade the strategy. Hold a plain UCITS S&P 500 and bond mix, and keep the bot as a tracker that compares it with the trend mixes.

## Values to measure

Every number the config can't know yet has a source and a deadline. Three are settled from IBKR's and Deutsche Börse's published terms and two by milestone 1's runs; the trade cost still needs measuring, and two are yours to give.

| Value | Setting | Source or method | Status |
| --- | --- | --- | --- |
| Currency conversion (`fx_cost`) | 0.002% per conversion, minimum USD 2 | IBKR's manual conversion fee; automatic conversion adds about 0.03% to the rate, so convert by hand | Settled |
| Cash interest | Benchmark rate minus 0.5%, nothing on the first USD 10,000 or equivalent, scaled down by NAV / USD 100,000 below that size | IBKR Pro's interest terms | Settled; the backtest uses it, which matters for small accounts |
| `xetra_holidays` | 2026 and 2027 filled in | Deutsche Börse's non-trading days | Settled; add the next year each December |
| Fund costs (`cost`) | DBPG 0.94%, LQQ 1.39% a year, applied daily | `python -m bot.calibrate` on each fund's own prices: the cost that makes its model grow like the fund. The higher of two clean spans is kept (from listing, and from 2012 after DBPG's bad 2010–11 prints); repaired days are left out of the measurement | Settled in milestone 1. The research's 2.0% and 2.2% were measured on other listings and as a gap in annual return, which the daily charge compounds into a larger one |
| Trade cost (`trade_cost`) | 0.05% per side until measured | IBKR's commission plus half the bid-ask spread, noted at 09:05, 09:30 and 10:00 for DBPG, LQQ and SXRM on 10 trading days | Milestone 1, before the gate is final |
| Buffer around the averages | 0% | Tested at 0%, 1% and 2% in the gate | Settled: no buffer improves all three periods |
| `tax_rate` | Unknown | Set per strategy: your country's rate on realized gains, or 0 for a strategy run in a tax wrapper | Yours, before milestone 1 ends; the gate also shows 0%, 20% and 30% |
| Start size (`start_value`) | €30,000 placeholder | Your planned portfolio size; it sets how much cash interest IBKR pays and how much whole shares round | Yours |

Sources: [IBKR currency conversion fees](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php), [IBKR interest rates](https://www.interactivebrokers.com/en/accounts/fees/pricing-interest-rates.php), [Xetra non-trading days](https://www.xetra.com/xetra-en/newsroom/trading-calendar/non-trading-days). Checked on Oct 1, 2026.

## Open questions

These answers about the strategy can change the design, so settle them before milestone 2 (tax before milestone 1 ends).

- [x] Strategy: trend + bonds mixes on 2× S&P 500 and 2× Nasdaq-100 (Strategy candidates tab); 30/30/40 recommended
- [x] Instruments: daily ETFs only, no options or futures; UCITS funds for an EU account (Strategy rules tab)
- [ ] Tax: your country's rate on realized gains and any tax wrapper. About 13 position changes a year can erase the edge over SPY in a taxable account, so this sets each strategy's `tax_rate` for milestone 1's after-tax test
- [x] Where it runs: a home Raspberry Pi or NVIDIA Jetson on Tailscale (Running at home)
- [x] Channels: Slack and email, routed per kind of message (Running at home)
- [ ] Transactions input: edit `transactions.csv` by hand, or paste in IBKR's activity statement
- [ ] Bonds: unhedged SXRM or EUR-hedged IBB1 for the 40% bond slice; if unhedged, the USD line (SXRM, needs EUR/USD conversions) or a EUR-quoted line of the same fund, if one exists
- [ ] Portfolio size: decides whether whole-share rounding of the higher-priced funds outweighs the 2% minimum trade
- [ ] Contributions: invest new deposits at once, or at the next monthly rebalance
- [ ] Benchmark: SPY converted to EUR, or a UCITS S&P 500 fund such as CSPX that you could actually buy
- [ ] Which strategies to track from day one, besides the one you follow (for example 25/25/50, 33/33/33, 40/40/20)
- [ ] Follow one strategy or several: alerts go out for followed strategies only, so several means `follow` becomes a list
- [ ] Pi or Jetson, and whether the database lives on a USB SSD
- [ ] Your time zone, for the weekly summary
- [ ] Healthcheck service and its two checks (daily and weekly); healthchecks.io's free plan is enough
- [x] Fill `xetra_holidays` for 2026 and 2027 from Deutsche Börse's trading calendar (done; see Values to measure)
