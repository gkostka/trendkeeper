> Exported on 2026-10-01 from the live doc: https://claude.ai/code/artifact/df7763ce-b0ee-4664-a103-bdbfa843d65e
> Diagrams and charts appear here only as placeholders; see the live doc for them. The live doc is the source of truth.

# Trendkeeper — Architecture & Implementation Plan

Sep 30, 2026 · @Grzegorz Kostka

## Goals and scope

v1 is an advisor, not a trader. Once a day after the US close, it checks the signals for every strategy you define and tracks how each would have done since your start date. It compares them with buying and holding the S&P 500 and Nasdaq-100, and sends you a summary of what to do with your own holdings. A small UI shows how it reached each recommendation. IBKR order execution stays optional and comes last.

In scope for v1:

- Define any number of strategies in one config file: slices of funds, each either held or trend-following, with weights and rebalancing
- Benchmarks (SPY and QQQ buy-and-hold) are ordinary strategies, so every strategy is compared on the same footing
- One engine runs both the historical backtest and the daily update, so live numbers match the research
- A daily summary by Telegram or email: signals, each strategy's target, what to buy or sell, and performance against the benchmarks
- A local web UI: today's signals and why, equity curves against the benchmarks, your holdings against the target, and a log of every decision
- Your holdings entered by hand (or read from IBKR later), so recommendations are sized to your real portfolio

Later, each switched on separately:

- Read-only IBKR connection: import positions and prices automatically
- IBKR paper trading, then live trading, with the risk controls below
- Intraday strategies, multiple accounts, a hosted server

Not planned: microservices, message queues, a user system. It's a single-user tool.

## Architecture overview

The bot is a daily job plus a local UI. On each US trading day after the close, it catches up any missed days, updates and checks prices, and runs the strategy engine for every strategy. It backtests each one over history and since your start date, and logs what it saw and recommended. Then it compares your holdings with the strategy you follow and sends you a summary. The UI only reads that database.

&#91;embedded content: advisory bot · daily job, local UI, IBKR optional\]

Only the optional broker adapter knows IBKR exists. Switching it on first replaces the hand-written holdings file with real positions, and only much later lets the advisor's trade list become orders.

## Components

Each component is one Python module. The engine is the core: the backtest, the daily run and the UI all call it, so they can't disagree.

| Component | Responsibility | Notes |
| --- | --- | --- |
| Config | `config.toml`: base currency, execution timing, instruments, strategies, benchmarks, the strategy you follow | Built-in `tomllib`; secrets (Telegram token, IBKR login) only in environment variables |
| Instruments | Each fund's currency; for leveraged funds also what it tracks, its leverage, its measured cost and how EUR/USD enters its price | Lets the backtest build a fund's history before its launch, and value UCITS funds correctly |
| Market data | Daily opens and closes for signal ETFs, funds and EUR/USD, cached in SQLite; fetches only what's missing | Sanity checks: rejects one-day moves above 25% that its index doesn't explain, flags stale prices. A bad day is skipped and alerted, never acted on |
| Strategy engine | Turns slices into target weights for any day: trend slices from their moving averages, hold slices fixed, monthly rebalance, plus a trade delay (same close, next open or next close) | Pure functions; the same code for backtest, daily run and UI |
| Backtester | Every strategy over history and since your start date, with fund costs, 0.05% per trade and the chosen trade delay | Must reproduce the research on a saved price snapshot. "Since start" replaces separate shadow portfolios |
| Decision log | What the bot saw and recommended each day: prices used, signals, targets, trade list | Never changed after writing, so later data revisions can't rewrite history |
| Holdings and advisor | Your positions (`holdings.toml`, IBKR later) against the followed strategy's target, as a trade list in your base currency with sells before buys | Skips trades below a threshold, for example 2% of the portfolio |
| Daily job | On US trading days after the close: catch up missed days, update data, run the engine, log, recommend, notify | Safe to re-run; uses the last price for funds whose exchange was closed |
| Notifications | Daily summary and alerts through one channel, Telegram or email | Add a second channel only if needed |
| UI | Streamlit app reading SQLite: today, strategies against SPY and QQQ in your currency, your portfolio, decision log | Read-only, reachable only from your own machine (localhost) |
| Storage | SQLite: prices, decision log, backtest results, recommendations | One file, easy to back up |
| Broker adapter (optional) | `ib_async` with IB Gateway: read positions (milestone 5), place orders (milestone 6, which also adds paper and live modes) | The IBKR and risk sections below apply from then |

## Defining strategies

A strategy is a list of slices. Each slice has a weight and a fund, and either holds the fund (`hold`) or follows the trend rule on a signal ETF (`trend`). Benchmarks are strategies with a single `hold` slice. Every strategy in the research, and new ones, fits this shape:

```toml
base_currency = "EUR"     # portfolio, benchmarks and trade amounts in this currency
follow = "mix_30_30_40"   # the strategy your holdings are compared against
start = 2026-10-01        # "since start" results begin here
execution = "next_open"   # same_close | next_open | next_close
trade_cost = 0.0005       # per side, as in the research
min_trade = 0.02          # skip trades under 2% of the portfolio

[instrument.SPY]
currency = "USD"

[instrument.QQQ]
currency = "USD"

[instrument."DBPG.DE"]    # Xtrackers S&P 500 2x
currency = "EUR"
tracks = "SPY"
leverage = 2
cost = 0.020              # measured, beyond a plain 2x model
fx = "converted"          # converted: EUR/USD counts once; leveraged: twice (CL2)

[instrument."LQQ.PA"]     # Amundi Nasdaq-100 2x
currency = "EUR"
tracks = "QQQ"
leverage = 2
cost = 0.022
fx = "converted"

[instrument."SXRM.DE"]    # iShares $ Treasury 7-10yr
currency = "USD"

[[strategy]]
id = "mix_30_30_40"
name = "Mix 30/30/40"
rebalance = "monthly"

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

  [[strategy.slice]]
  weight = 1.0
  fund = "SPY"
  rule = "hold"
```

Three rules make the config reproduce the research:

- **Signals come from the US ETFs** (SPY or QQQ in USD), even when the fund held is a UCITS one, so they match the backtest.
- **Before a fund's price history begins,** the backtester builds it from what the fund tracks, its leverage and its measured cost. That is how the research reached back to 1994.
- **`execution` sets when a signal becomes a trade.** `next_open` matches a European account trading the morning after the US close; `same_close` is what the research assumed.

What the daily summary contains:

- **Signals:** SPY and QQQ against their 200/250/300-day averages, the distance to the next crossing, and any change since yesterday
- **Action for you:** for the strategy you follow, "no change" or a short list such as "sell €3,200 of DBPG at tomorrow's open"
- **Every strategy:** today's target; return month-to-date, year-to-date and since start; current drop from peak. All in your base currency, against SPY and QQQ converted to it
- **Alerts:** missing, stale or rejected prices; a missed run; a 2× fund drifting from 2× its index over a week (not daily, since European funds close 4.5 hours earlier); a drop beyond 1.5× the strategy's backtest worst

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

- Kill switch: a file flag or Telegram command that cancels open orders and blocks new ones
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

1. **Backtest.** Every strategy from 1994 to today, with calibrated fund costs, 0.05% per trade and your execution setting. Keep a period you never tune on.
2. **Advisory.** The bot recommends; you place the orders by hand at small size. The decision log shows what it advised and when.
3. **IBKR read-only.** Real positions replace `holdings.toml`; the bot still only recommends.
4. **Paper trading.** The bot places orders on IBKR's paper account for 2–4 weeks, to prove restarts, partial fills and data gaps are handled. Paper fills are optimistic.
5. **Live, small.** Same config on the live account at a fraction of the target size; scale up once live results track paper.

The engine's core stays one function, so every step above runs the same code:

```python
def target_weights(strategy: Strategy, prices: pd.DataFrame, day: date) -> dict[str, float]:
    """Fund weights the strategy wants after the close of `day`, using only prices up to `day`."""
```

## Tech stack and deployment

Python on your own machine to start: a daily scheduled job plus a local UI, no server and no broker. Docker and a small VM come only when IBKR is switched on.

| Concern | Choice | Why |
| --- | --- | --- |
| Language | Python 3.12 | The research code is already Python |
| Data and maths | `pandas`, `numpy` | Standard; the backtests already use them |
| Market data | `yfinance` daily closes, cached in SQLite | Free and enough for daily signals, but unreliable for some UCITS funds, so every price passes the sanity checks; swap for IBKR data in milestone 5 |
| Config | TOML via built-in `tomllib` | No extra dependency |
| Storage | SQLite (built-in `sqlite3`) | One file, zero setup |
| UI | Streamlit | A local web app from one Python file, with charts and tables; read-only and bound to localhost (\`server.address = "localhost"\`) |
| Notifications | One channel to start: a Telegram bot over HTTPS, or email via built-in `smtplib` | No extra service |
| Scheduling | cron (Linux) or launchd (macOS) after the US close; the job catches up missed days itself (launchd runs a missed job on wake, cron doesn't) | No scheduler library needed |
| Tests | `pytest` on the engine | One test reproduces the research on a saved price snapshot, so data revisions can't break it |
| Broker (later) | `ib_async` with IB Gateway in Docker (`gnzsnz/ib-gateway-docker`) | Only from milestone 5 |

Suggested layout:

```
bot/
  config.toml      # currency, execution, instruments, strategies, benchmarks
  holdings.toml    # your positions (until IBKR read-only)
  data.py          # prices and EUR/USD: download, sanity checks, SQLite cache
  engine.py        # instruments, slices, signals, target weights, backtest
  advisor.py       # your holdings vs target -> trade list in your currency
  daily.py         # the daily job: catch up, update, run, log, recommend, notify
  notify.py        # one channel: Telegram or email
  app.py           # Streamlit UI, localhost only
  broker.py        # IBKR via ib_async, added in milestone 5
research/          # the backtest scripts behind this doc
tests/
  data/            # saved price snapshot
  test_engine.py   # reproduces the research numbers on the snapshot
```

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

Six milestones, each closed by a gate. The first four give you a working advisor that you follow by hand. The last two connect IBKR and are optional. Dates depend on your time per week, so none are set here.

&#91;embedded content: roadmap · 6 milestones, 2 optional\]

Milestone 1 ends with the strategy re-tested the way you will really trade it: the day after the signal, and with a small buffer around the averages. If those results fall well short of the research, the plan is revised before anything else is built. Milestone 4 is where real money starts, placed by you.

## Open questions

These answers about the strategy can change the design, so settle them before milestone 2.

- [x] Strategy: trend + bonds mixes on 2× S&P 500 and 2× Nasdaq-100 (Strategy candidates tab); 30/30/40 recommended
- [x] Instruments: daily ETFs only, no options or futures; UCITS funds for an EU account (Strategy rules tab)
- [ ] Where it runs: your laptop (simplest; misses days when it's off) or an always-on machine such as a home server or a small VM
- [ ] Daily summary channel: Telegram or email (one is enough for milestone 2)
- [ ] Holdings input: edit `holdings.toml` by hand, or a form in the UI
- [ ] Account type and currency: EUR or USD reporting, and the tax wrapper (affects whether trading costs or taxes dominate)
- [ ] Which strategies to track from day one, besides the one you follow (for example 25/25/50, 33/33/33, 40/40/20)
