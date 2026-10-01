# Trendkeeper

A daily trend-following advisor for a small ETF portfolio. After each US close it checks SPY and QQQ against their 200, 250 and 300-day moving averages. It then tells you what to buy or sell in a 30/30/40 mix: 2× S&P 500, 2× Nasdaq-100 and Treasuries, held through UCITS funds at Interactive Brokers.

It runs unattended on a home Raspberry Pi or Jetson on Tailscale. Alerts and summaries go to Slack and email, and `tk` shows the status over SSH. It only advises: you place the trades. Placing orders through IBKR is optional and comes last.

## Status

Planning is done; no bot code exists yet. Next is milestone 1: port the research into one engine, then test the strategy the way it would really be traded, against pass marks set in advance.

## Docs

| File | Contents |
| --- | --- |
| [docs/01-architecture-and-plan.md](docs/01-architecture-and-plan.md) | Architecture, config, running at home, milestones, the milestone 1 gate, open questions |
| [docs/02-framework-review.md](docs/02-framework-review.md) | Why not NautilusTrader, LEAN, Lumibot or pysystemtrade |
| [docs/03-strategy-candidates.md](docs/03-strategy-candidates.md) | Strategies tested and how 30/30/40 was chosen |
| [docs/04-strategy-rules.md](docs/04-strategy-rules.md) | The trading rule, holding periods, UCITS funds, when to stop |

The docs are exports of a live doc, which is the source of truth.

## Research

The scripts in `research/` produced the numbers in the docs. They need Python 3.12 with `pandas`, `numpy` and `yfinance`, and they download prices from Yahoo Finance. Some scripts load others, so run them from inside the folder:

```sh
cd research
python bt6.py
```

They are kept as a record and will be frozen once `engine.py` reproduces them.

## Disclaimer

This is a personal tool, not investment advice. Leveraged ETFs can lose most of their value, and backtest results don't guarantee future returns.
