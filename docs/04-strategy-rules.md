> Exported on 2026-10-01 from the live doc: https://claude.ai/code/artifact/df7763ce-b0ee-4664-a103-bdbfa843d65e
> Diagrams and charts appear here only as placeholders; see the live doc for them. The live doc is the source of truth.

# Strategy rules

Every strategy here follows one rule. Hold the 2× fund while its index closes above its moving averages, and step out to cash as it closes below them. There is no fixed holding period and no price target: you hold for as long as the trend lasts. In the backtest that ranged from a few days to over three years. The mixes add a fixed slice of Treasury bonds and rebalance once a month. The numbers on this tab come from the research scripts (US funds, traded at the same close); they are replaced by the engine's results once milestone 1 passes.

## Daily decision

&#91;embedded content: daily trend rule · one loop per trend slice, plus the monthly rebalance\]

The bot does nothing on most days. It trades only on the 13 or so days a year when the count changes, plus the monthly rebalance.

## Each strategy

| Strategy | ETFs and target weights | Trend signal | Monthly rebalance |
| --- | --- | --- | --- |
| **Mix 30/30/40** | 30% S&P slice (SSO or cash), 30% Nasdaq slice (QLD or cash), 40% IEF | SPY for the S&P slice, QQQ for the Nasdaq slice | Yes, back to 30/30/40 |
| Mix 40/30/30 | 40% S&P slice, 30% Nasdaq slice, 30% IEF | Same | Yes, back to 40/30/30 |
| Mix 40/40/20 | 40% S&P slice, 40% Nasdaq slice, 20% IEF | Same | Yes, back to 40/40/20 |
| Mix 50/50/0 | 50% S&P slice, 50% Nasdaq slice, no bonds | Same | Yes, back to 50/50 |
| 100% 2× S&P trend | 100% S&P slice (SSO or cash) | SPY | Not needed |
| 100% 2× Nasdaq trend | 100% Nasdaq slice (QLD or cash) | QQQ | Not needed |
| SPY / QQQ buy-and-hold | 100% SPY or QQQ | None | None: buy once, never sell |

The tables use the US funds the research tested; the UCITS version below maps each to its European equivalent. The rule for every trend slice, checked each trading day at the US close:

1. Take the adjusted closing price of the signal ETF (SPY or QQQ) and its 200, 250 and 300-day simple moving averages.
2. Count how many of the three averages the price is above: 0, 1, 2 or 3.
3. That count sets the slice's target: 0, 33, 67 or 100% in the 2× fund (SSO or QLD), with the rest in cash.
4. **Enter:** the count rises, so buy one third of the slice for each average crossed upward.
5. **Exit:** the count falls, so sell one third of the slice for each average crossed downward. At a count of 0 the slice is all cash.
6. **Otherwise, hold.** There is no stop-loss, no profit target and no time limit. The averages are the exit.
7. Trade when the config's execution setting says. The research assumed market-on-close orders on US funds; a European account trades the UCITS funds at the next European open (UCITS version below).

Other rules:

- **Bonds (IEF)** are never traded on a signal. They change only at the monthly rebalance.
- **Cash** should earn interest. The backtest assumed T-bill rates, which IBKR pays on idle cash above a minimum, or hold a T-bill ETF such as BIL. A EUR account earns roughly the ECB deposit rate minus IBKR's spread; the main tab's config models that.
- **Monthly rebalance:** on the first trading day of each month, reset the slices to their target weights. A slice's value includes its cash, so the rebalance doesn't change the trend positions, only their size.

## How long you hold

Most entries end within days; a few last years and make the money. Over 1994–2026 the median stretch above an average was just 4–6 trading days. Over half of all entries were reversed within two weeks, when the price fell back below the average. The average stretch was 2–6 months, and the longest ran 2.3–3.7 years.

| Signal | Entries a year | Median time in | Average time in | Longest time in | Average time out | Longest time out | Share of days in |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SPY, 200-day | 3.3 | 5 days | 59 days | 577 days (2.3 yrs) | 18 days | 313 days | 77% |
| SPY, 250-day | 2.7 | 5 days | 74 days | 937 days (3.7 yrs) | 20 days | 388 days | 79% |
| SPY, 300-day | 1.6 | 6 days | 126 days | 937 days (3.7 yrs) | 32 days | 621 days | 80% |
| QQQ, 200-day | 3.4 | 4 days | 58 days | 665 days (2.6 yrs) | 17 days | 308 days | 77% |
| QQQ, 250-day | 2.7 | 5 days | 74 days | 665 days (2.6 yrs) | 21 days | 614 days | 79% |
| QQQ, 300-day | 2.3 | 6 days | 87 days | 766 days (3.0 yrs) | 22 days | 623 days | 80% |

Days are trading days (about 252 a year). For the blend of all three averages, each trend slice was fully invested 75% of the time and fully in cash 18% of the time; the rest was partial. Its position changed about 13 times a year.

What this means in practice:

- **Expect many small losing trades.** Most entries are reversed within days, each costing trading fees and usually a small loss. That's the cost of being in for the long trends, not a sign the bot is broken.
- **Long exits are where the protection comes from.** The longest stretches out of the market were late 2000 to spring 2003 (up to 2.5 years) and 2008 to mid-2009, the two crashes the strategy mostly avoided. The next longest was Apr 2022 to early 2023.
- **Untested idea:** a small buffer (for example, exit only 1–2% below the average) would cut the quick reversals. It hasn't been backtested yet.

## Today

At the 30 Sep 2026 close, both indexes were above all three averages, so every trend slice was fully invested.

| Signal ETF | vs 200-day | vs 250-day | vs 300-day | Count | Slice holds |
| --- | --- | --- | --- | --- | --- |
| SPY | +6.5% | +8.0% | +9.7% | 3 of 3 | 100% SSO |
| QQQ | +11.1% | +13.0% | +15.3% | 3 of 3 | 100% QLD |

| Strategy | Holdings today |
| --- | --- |
| Mix 30/30/40 | 30% SSO, 30% QLD, 40% IEF |
| Mix 40/30/30 | 40% SSO, 30% QLD, 30% IEF |
| Mix 40/40/20 | 40% SSO, 40% QLD, 20% IEF |
| Mix 50/50/0 | 50% SSO, 50% QLD |
| 100% 2× S&P trend | 100% SSO |
| 100% 2× Nasdaq trend | 100% QLD |

The first exit (selling a third of the S&P slice) would come if SPY fell about 6% from here and closed below its 200-day average. For QQQ it would take a fall of about 10%. The averages rise slowly while prices stay high, so the real trigger levels creep up over time. The bot recalculates them every day.

## UCITS version (EU accounts)

EU retail accounts at IBKR usually can't buy US-listed ETFs such as SSO, QLD and IEF, because those funds don't publish the EU key information document. Each part of the strategy has a UCITS equivalent. All of these are 2× or less, which is as far as UCITS leveraged ETFs normally go. Checked on Oct 1, 2026:

| Role | US fund | UCITS equivalent | ISIN | Tickers | TER | Size |
| --- | --- | --- | --- | --- | --- | --- |
| S&P slice | SSO | [Xtrackers S&P 500 2x Leveraged Daily Swap UCITS ETF 1C](https://www.justetf.com/en/etf-profile.html?isin=LU0411078552) | LU0411078552 | DBPG (Xetra, EUR), XS2D (LSE, USD), XS2L (Milan, EUR) | 0.60% | €543m |
| S&P slice, alternative | SSO | [Amundi MSCI USA Daily (2x) Leveraged UCITS ETF Acc](https://www.justetf.com/en/etf-profile.html?isin=FR0010755611): MSCI USA (\~600 stocks), moves almost exactly with the S&P 500, but doubles EUR/USD moves (see cost table) | FR0010755611 | CL2 (Paris and Milan, EUR), 18MF (Xetra, EUR) | 0.50% | €1,150m |
| Nasdaq slice | QLD | [Amundi Nasdaq-100 Daily (2x) Leveraged UCITS ETF Acc](https://www.justetf.com/en/etf-profile.html?isin=FR0010342592) | FR0010342592 | LQQ (Paris and Milan, EUR), L8I7 (Xetra, EUR) | 0.60% | €1,358m |
| Bonds, unhedged | IEF | [iShares $ Treasury Bond 7-10yr UCITS ETF (Acc)](https://www.justetf.com/en/etf-profile.html?isin=IE00B3VWN518) | IE00B3VWN518 | SXRM (Xetra, USD), CBU0 (LSE, USD) | 0.07% | €4,354m |
| Bonds, EUR-hedged | — | [iShares $ Treasury Bond 7-10yr UCITS ETF EUR Hedged](https://www.justetf.com/en/etf-profile.html?isin=IE00BGPP6697) | IE000K1VI152 (Acc), IE00BGPP6697 (Dist) | IBB1 (Xetra, EUR) for the Dist class | 0.10% | €143m (Acc), €1,505m (Dist) |

All four are accumulating except the EUR-hedged Dist class. Both 2× funds are swap-based: they hold a swap with a bank instead of the stocks, which is normal for UCITS leveraged ETFs.

What changes when you run it from Europe:

- **Keep the signal on US data.** Compare SPY and QQQ (in USD) with their 200/250/300-day averages, exactly as in the backtest. The EUR price of DBPG or LQQ mixes in EUR/USD moves and would give different signals.
- **The European markets close before the US.** Xetra, Paris and Milan close at 17:30 CET, about 4.5 hours before the US close, so the trade can't happen at the same close the signal uses. The practical rule is: read the signal at the US close, then trade at the next European open. That is the "trade next day" version of the backtest, which is still untested. Run it before going live.
- **Currency:** the backtest was in USD. In EUR, every USD asset also carries the EUR/USD move. The EUR-hedged bond class removes that from the 40% bond leg. The price history shows how each fund handles currency. Xtrackers and LQQ apply the 2× in USD and convert, so EUR/USD moves count once. CL2 applies the 2× to the index measured in EUR, so EUR/USD moves count twice (see the cost table below).
- **Costs:** the TERs are lower than SSO's and QLD's, but the measured all-in cost is slightly higher (table below).
- **Taxes** for these funds depend on your country, including how accumulating funds and frequent sales are taxed. Check locally.

Measured cost of each 2× fund, May 2010 to Sep 2026. Cost is the yearly gap between the fund's real price and a plain daily 2× model with no fees, financed at the T-bill rate (USD) or the ECB deposit rate (EUR). It includes the TER, swap costs and, for CL2, the difference between the MSCI USA and S&P 500 indexes. Currency effect is how strongly the EUR price responds to EUR/USD moves.

| Fund | TER | Measured all-in cost | Currency effect in EUR |
| --- | --- | --- | --- |
| SSO (US) | 0.87% | 1.8% a year | — (USD) |
| QLD (US) | 0.95% | 1.9% a year | — (USD) |
| Xtrackers S&P 500 2x (XS2D / DBPG) | 0.60% | 2.0% a year | 1×, like holding a US fund |
| Amundi Nasdaq-100 2x (LQQ) | 0.60% | 2.2% a year | 1×, like holding a US fund |
| Amundi MSCI USA 2x (CL2) | 0.50% | about 1.7% a year | 2×: EUR/USD moves are doubled |

Read it as roughly ±0.3 points: European prices close 4.5 hours before the US, and one split day each in LQQ and CL2 was repaired. In the strategy the extra 0.2–0.4 points apply only to the trend slices, and only while they are invested. That costs a 30/30/40 portfolio about 0.1–0.2% a year compared with the US funds. Prefer Xtrackers for the S&P slice: its cost is close to CL2's, and its currency behaviour matches the backtest.

## When to stop

The moving averages handle normal exits. These rules cover the cases where the strategy itself may be broken. They are suggestions, not backtested.

| Trigger | Action |
| --- | --- |
| Drop exceeds 1.5× the backtest's worst (30/30/40: −45%, 40/40/20: −64%, 2× S&P trend: −58%) | Move to cash and review before restarting |
| A 2× fund's weekly move strays far from 2× its index's (for example, more than 1 point off). Weekly, because European funds close 4.5 hours before the US and daily gaps are noise | Halt trading on that fund and check the data and the fund |
| Market data stale, IBKR disconnected, or positions don't match the bot's records | The bot's kill switch (main tab): no new orders until reconciled |
| A fund announces closure, a merger or a change of objective | Switch to the nearest equivalent (for example, SSO to a 2× S&P 500 fund from another provider) |

What isn't a reason to stop: trailing SPY for a year or two. The recommended mix spent up to 3.8 years below a previous peak in the backtest, and every option trailed SPY in many calendar years. Judge it over a full market cycle, roughly 5–10 years, against its own backtest, not against last year's best index.
