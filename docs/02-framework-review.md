> Exported on 2026-10-01 from the live doc: https://claude.ai/code/artifact/df7763ce-b0ee-4664-a103-bdbfa843d65e
> Diagrams and charts appear here only as placeholders; see the live doc for them. The live doc is the source of truth.

# Framework review

## Recommendation

For a first bot, build the lean version on `ib_async` as the main tab describes. Run IB Gateway with the `gnzsnz/ib-gateway-docker` image, and keep the strategy a pure `on_bar` function so it can move to NautilusTrader later. None of the frameworks is a safe drop-in for live IBKR trading today.

Which to pick depends on the strategy:

| If your strategy is… | Use | Why |
| --- | --- | --- |
| Stocks/ETFs on minute or daily bars, a few symbols | DIY on ib\_async | Least code to trust; you own the risk layer anyway |
| Options, futures, spreads, or tick/order-book driven | NautilusTrader v2 | Best IBKR adapter and risk engine; paper-trade until 2.0.0 final ships and the reconciliation bugs are fixed |
| Diversified daily futures, trend/carry style | pysystemtrade | A complete system for exactly that |
| An idea you just want to backtest this week | Lumibot (backtest only) | 12-line strategies, free Yahoo data |
| Happy to pay and run in someone's cloud | QuantConnect LEAN (cloud) | Mature, with data and hosting handled |

What changed since the main tab was written: NautilusTrader's v2 is still a release candidate. `ib_async` has had no commits since Dec 2025, and IBC was retired in Sep 2026. So pin versions (Python 3.12, `ib_async==2.1.0`), and keep the alerts on disconnects and login failures.

All facts checked on GitHub and official docs on 2026-09-30.

## Scorecard

| Option | Best for | IBKR live today | Same code backtest + live | Built-in risk | Setup effort | Cost | Health (Sep 2026) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DIY on ib\_async | Simple stock/ETF strategy on bars | Solid API; you build reconnect + reconcile | Only if you build it | None; you write it | Medium | Free | Stalled: no commits since Dec 2025 |
| NautilusTrader | Serious event-driven trading, options, futures | Rich adapter, but v2 is a release candidate with open reconcile bugs | Yes | Strong (notional, rate limits, halt) | High | Free (LGPL) | Very active; v2 in rc |
| QuantConnect LEAN | Paying QC users, multi-asset | Mature, but needs a QC paid plan and licence check | Yes | Good (risk models) | High | $10–48/mo + data | Very active |
| Lumibot | Quick tests of simple stock/option ideas | Weak: TWS path deprecated, REST is a proof of concept | Yes | Basic | Low | Free (GPL) | Very active, AI-focused |
| pysystemtrade | Carver-style daily futures portfolios | Proven, futures only | Yes | Carver position sizing | Very high (Mongo, cron) | Free (GPL) | Active, rare releases |

## NautilusTrader

The strongest design, but it is caught between two versions. Stable v1 (1.231.0, Aug 2026) now gets only security backports. v2 (2.0.0rc5, 15 Sep 2026) is a release candidate the README says not to use in production. All current docs describe v2.

What you get:

- **IBKR adapter** covering stocks, options, futures, FX, bonds and funds. It supports option and futures chains, combo spreads, bracket and OCA orders, and IB conditional orders. Data includes real-time, delayed and historical bars and ticks.
- **Same strategy class in backtest and live**, with a Parquet data catalog for backtests. You can download IB history into it yourself.
- **Built-in risk engine:** max notional per order, rate limits on submits and modifies, cash-balance checks, and a HALTED / REDUCING trading state.
- **Reconnects** with backoff (1–60 s) and re-subscribes. It can start the gnzsnz Gateway container.

Watch out for:

- About 20 open IB-related issues, mostly from the last month, including ones that matter for real money:
  - [#5057](https://github.com/nautechsystems/nautilus_trader/issues/5057): working orders from a previous session can't be managed after a restart
  - [#4970](https://github.com/nautechsystems/nautilus_trader/issues/4970): lost order-ID mapping creates a duplicate reconciliation order
  - [#4796](https://github.com/nautechsystems/nautilus_trader/issues/4796): the historical client can wedge IB Gateway until it is restarted
- A heavy concept load: nodes, message bus, instrument IDs. rc5 alone had 7 breaking changes, and the v2 migration guide runs to 971 lines.
- Python 3.12–3.14. Install with `pip install -U nautilus_trader --pre`; without `--pre` you get v1, which does not match the docs.
- LGPL-3.0: no obligations for a private bot you don't distribute.

Verdict: worth it if you want event-driven backtests that match live, options or futures, or order-book data. Paper-trade only until 2.0.0 final ships and the reconciliation issues are closed.

Sources: [repo and releases](https://github.com/nautechsystems/nautilus_trader/releases), [IB integration docs](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/integrations/interactive_brokers.md), [IB examples](https://github.com/nautechsystems/nautilus_trader/tree/develop/examples/live/interactive_brokers), [v2 migration guide](https://github.com/nautechsystems/nautilus_trader/blob/develop/MIGRATION_V2.md).

## Lumibot

The easiest to start with, but its IBKR support is its weakest part. Both IBKR connectors have serious gaps, and the project's focus has moved to AI agents and its hosted BotSpot service.

- **TWS connector:** marked deprecated in the docs and pinned to `ibapi==9.81.1.post1`, a very old build. It supports market, limit, stop, stop-limit and trailing orders, plus brackets / OCO (entry must be a limit). Order modify is not implemented.
- **REST connector (Client Portal API):** their own doc calls it a "paper proof of concept". It logs in through an IBeam container, 2FA and re-auth are left to you, and it allows one session per user. It has no brackets and no modify.
- **Backtesting:** easy, and the same `Strategy` runs live. Free data covers Yahoo daily and your own pandas data; Polygon, ThetaData and Databento need keys. IBKR data for backtests goes through a downloader service outside the repo.
- **Risk:** basic only (`sell_all`, cancel open orders, crash hooks). No position limits, drawdown stop or kill switch.
- **Self-hosting:** fully possible with no account. Data goes to Lumiwealth only if you set `LUMIWEALTH_API_KEY`.
- **Health:** very active (v4.6.2 on 27 Sep 2026, several releases a month), 67 open issues. GPL-3.0 is fine for private use.

Verdict: good for quickly testing simple stock or option ideas on daily data. Not the tool to rely on for live IBKR trading.

Sources: [repo](https://github.com/Lumiwealth/lumibot), [IBKR broker docs](https://lumibot.lumiwealth.com/brokers.interactive_brokers.html), [backtesting docs](https://lumibot.lumiwealth.com/backtesting.html).

## QuantConnect LEAN

A mature engine, but not free or truly self-hosted for live IBKR trading. The engine is Apache-2.0, yet its IBKR plugin checks your QuantConnect licence at startup.

- **Paid plan required:** the CLI docs state "To use the CLI, you must be a member in an organization on a paid tier", and IB live needs the Interactive Brokers module. Plans run $10–48/month. The pricing page lists live trading for those tiers as "Cloud", so ask QuantConnect which tier allows on-premises live trading before you pay.
- **Building from source doesn't avoid it:** the IB plugin's startup calls `ValidateSubscription()`, which sends your QC user and machine details to QC's licence API and stops if the check fails. You could patch it out (Apache-2.0 allows that), but then you maintain a fork.
- **Data costs:** local backtests on QC's US equity data need the Security Master ($600/year) plus per-file fees. IB historical data works only on a paid tier.
- **Strengths:** IBKR coverage for US stocks, options, futures, FX, indices and CFDs. Realistic fill and fee models. Built-in risk models (max drawdown per security, sector exposure, trailing stop). Large docs with Python and C# side by side.
- **Weaknesses:**
  - A heavy stack: .NET, Docker, pythonnet and IB Gateway.
  - The Docker image for ARM machines doesn't support IB, so Apple Silicon Macs are out unless you build from source.
  - IBKR PRO accounts only.
  - Open plugin bugs include [#249](https://github.com/QuantConnect/Lean.Brokerages.InteractiveBrokers/issues/249) (fills lost during a disconnect) and [#262](https://github.com/QuantConnect/Lean.Brokerages.InteractiveBrokers/issues/262) (2FA timeout leaves the connection dead).

Verdict: a good choice if you are happy to pay QuantConnect and run live in their cloud. A poor fit for a free bot on your own server.

Sources: [LEAN](https://github.com/QuantConnect/Lean), [IB plugin](https://github.com/QuantConnect/Lean.Brokerages.InteractiveBrokers), [CLI getting started](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started), [CLI IB live trading](https://www.quantconnect.com/docs/v2/lean-cli/live-trading/brokerages/interactive-brokers), [pricing](https://www.quantconnect.com/pricing/).

## pysystemtrade

A complete production system, but only for one style of trading: diversified daily futures in Rob Carver's framework. Skip it for stocks, options or intraday.

- **Runs on:** Python 3.10+ with tightly pinned dependencies (pandas 2.1.3, pymongo 3.11.3), MongoDB for state, Parquet for prices, a supplied Linux crontab and long-running processes. IB Gateway runs under IBC, and IB access goes through `ib_async`.
- **Setup effort is high:** install Mongo, write private config, backfill futures contract prices from your own data source, and build adjusted price series. The bot first trades the next day.
- **Custom strategies** can be plugged in, but they have to fit its futures and data model.
- **Health:** about 64 commits in the last 6 months, maintained by Andy Geach with Rob Carver as original author. Releases are rare: 1.8.3 on 30 Sep 2026, the one before in Nov 2024. 29 open issues. GPL-3.0.

Verdict: excellent if you are running a Carver-style futures portfolio on a dedicated Linux box, and the wrong tool otherwise.

Sources: [repo](https://github.com/pst-group/pysystemtrade), [production guide](https://github.com/pst-group/pysystemtrade/blob/develop/docs/production.md).

## Build your own on ib\_async

The lightest path and the one the main tab describes. The API is complete and productive, but upstream maintenance has stalled, so you own the bugs you hit.

What ib\_async gives you:

- Sync and async APIs, contract qualification, bracket orders, real-time bars, and historical data with `keepUpToDate`
- Its own implementation of the TWS protocol (no `ibapi` dependency)
- A `Watchdog` helper that restarts the Gateway through IBC and reconnects after errors. Plain `connect` does not reconnect by itself.

What you write yourself: reconnect and state resync, order reconciliation, risk checks, scheduling, persistence and the backtest broker. That is roughly milestones 1–3 on the main tab.

Health:

- Last release 2.1.0 on 8 Dec 2025, and no commits on the main branch since 6 Dec 2025. 74 open issues and 21 open PRs.
- Python 3.10–3.13; reports say it does not work on 3.14 ([#200](https://github.com/ib-api-reloaded/ib_async/issues/200)). Pin Python 3.12 or 3.13 and `ib_async==2.1.0`.
- Open bugs worth knowing about:
  - [#216](https://github.com/ib-api-reloaded/ib_async/issues/216): concurrent requests can hang
  - [#230](https://github.com/ib-api-reloaded/ib_async/issues/230): execution times are shifted by the host's UTC offset
  - [#89](https://github.com/ib-api-reloaded/ib_async/issues/89): `openTrades()` misses the profit-taker leg of a bracket

Code worth reading before you start:

| Project | What it is | Stars | License | Last push |
| --- | --- | --- | --- | --- |
| [thetagang](https://github.com/brndnmtthws/thetagang) | Options wheel bot on ib\_async; clean config and main-loop pattern | 2.7k | AGPL-3.0 | 2026-09 |
| [icli](https://github.com/mattsta/icli) | Trading CLI by the ib\_async maintainer; good API usage reference | 223 | — | 2025-10 |
| [mmr](https://github.com/9600dev/mmr) | Full algo platform on ib\_async 2.1 | 132 | unclear | 2026-09 |

Verdict: moderate effort and full control. The best fit for a simple stock or ETF strategy on bars, if you are happy to own a few hundred lines of plumbing.

Source: [ib\_async repo](https://github.com/ib-api-reloaded/ib_async).
