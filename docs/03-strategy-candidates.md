> Exported on 2026-10-01 from the live doc: https://claude.ai/code/artifact/df7763ce-b0ee-4664-a103-bdbfa843d65e
> Diagrams and charts appear here only as placeholders; see the live doc for them. The live doc is the source of truth.

# Strategy candidates

The bot as designed fits slow strategies best: daily or monthly decisions on a handful of liquid ETFs. Start with a monthly trend or momentum rotation. It trades a few times a year, is well documented, and lets you prove the bot itself with little at stake. Faster intraday ideas look great in papers but mostly disappear after real trading costs.

None of these is a promise of profit. All numbers on this tab come from the research scripts (US funds, traded at the same close) and are replaced by the engine's results once milestone 1 passes. Each is a starting point to backtest on your own data before risking money.

## Shortlist

All six shortlisted options beat buying and holding the S&P 500 over 1994–2026, and three (40/40/20, 50/50/0 and 2× Nasdaq trend) also beat the Nasdaq-100. The 30/30/40 mix is the recommended choice. It had the smallest worst drop (−30% vs SPY's −55% and QQQ's −83%) and the shortest time below a previous peak, while ending with twice SPY's money. 2× Nasdaq trend ended with the most but fell 72% along the way.

&#91;embedded content: own backtest · quarterly values, Jan 1994–Sep 2026 · shortlist\_growth\_long.csv\]

|  | SPY buy-and-hold | QQQ buy-and-hold | **Mix 30/30/40** | Mix 40/30/30 | Mix 40/40/20 | Mix 50/50/0 | 100% 2× S&P trend | 100% 2× Nasdaq trend |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Annual return, 1994–2026 | 10.9% | 14.7% | **13.4%** | 14.3% | 15.9% | 18.1% | 13.9% | 20.8% |
| Annual return, last 10 years | 15.2% | 20.9% | **15.0%** | 16.8% | 19.4% | 23.5% | 19.1% | 27.1% |
| Annual return, last 20 years | 11.1% | 16.5% | **12.4%** | 13.4% | 15.1% | 17.5% | 14.2% | 19.9% |
| Annual return, last 30 years | 10.2% | 13.7% | **12.9%** | 13.7% | 15.3% | 17.3% | 13.0% | 20.2% |
| Worst drop | −55% | −83% | **−30%** | −33% | −43% | −55% | −38% | −72% |
| Longest time below a previous peak | 6.6 yrs | 14.9 yrs | **3.8 yrs** | 6.6 yrs | 7.3 yrs | 9.9 yrs | 4.5 yrs | 13.6 yrs |
| Worst year | −36.8% | −41.7% | **−22.4%** | −24.1% | −26.3% | −33.8% | −28.8% | −43.9% |
| 2000–2002 (dot-com crash) | −37.5% | −73.3% | **−11.4%** | −17.5% | −25.5% | −38.0% | −29.1% | −50.9% |
| 2008 (financial crisis) | −36.8% | −41.7% | **−7.3%** | −8.9% | −13.5% | −19.5% | −4.2% | −33.6% |
| COVID crash (Feb 19 – Mar 23, 2020) | −33.7% | −27.9% | **−24.0%** | −27.3% | −32.0% | −39.5% | −32.1% | −46.6% |
| 2020 full year | +18.3% | +48.4% | **+26.0%** | +26.1% | +30.3% | +33.4% | +13.3% | +52.1% |
| 2022 | −18.2% | −32.6% | **−22.4%** | −24.1% | −26.3% | −30.1% | −27.6% | −32.9% |
| Sharpe ratio | 0.51 | 0.56 | **0.66** | 0.65 | 0.64 | 0.63 | 0.55 | 0.63 |
| Years ahead of SPY (of 33) | — | 22 | **16** | 20 | 21 | 21 | 19 | 21 |
| $10k became | $292k | $881k | **$606k** | $782k | $1.24M | $2.30M | $701k | $4.77M |

Mixes are % in 2× S&P trend / 2× Nasdaq trend / intermediate Treasuries, rebalanced monthly. "Trend" means the 200/250/300-day blend on SSO or QLD, with cash when out.

How to read it:

- **In slow crashes the trend rule did its job.** In the dot-com crash and 2008, every trend option lost far less than buy-and-hold. The COVID crash was too fast: the market fell 34% in five weeks, before the averages could react. Only the bond-heavier mixes lost less than SPY (−24% to −27% vs −34%). 2× S&P trend lost about as much, and 2× Nasdaq trend lost 47%.
- **In 2022 it didn't.** Prices chopped around the averages and bonds fell with stocks, so every trend option lost more than SPY that year.
- **Over the last 10 years, a strong and steady bull market,** the recommended mix only matched SPY. Its edge over 1994–2026 came from losing less in 2000–02 and 2008.
- **Higher-return options trade safety for return.** 40/40/20, 50/50/0 and 2× Nasdaq trend made more money, but each spent over 7 years below a previous peak at some point. That is the test most people fail in practice.
- **Pick by the worst drop you would sit through without selling:** about −30% → 30/30/40, about −40% → 40/40/20, about −55% (the same as SPY's) → 50/50/0, which returned 18.1% a year but spent almost 10 years below a previous peak; more than that → consider just holding QQQ.

### Rating

Each option is ranked 1–8 on six measures, all weighted equally: return 1994–2026, worst drop, longest time below a previous peak, average loss across the four crashes (2000–02, 2008, COVID, 2022), Sharpe ratio and worst year. Five of the six measure risk, so the rating favours safety.

| Rating | Option | Avg rank | Return | Worst drop | Avg crash loss | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Mix 30/30/40** | 2.0 | 13.4% | −30% | −16% | Best on every risk measure; return 7th of 8. The best all-round choice. |
| 2 | Mix 40/30/30 | 2.7 | 14.3% | −33% | −20% | Nearly as safe, about 1 point more return a year. |
| 3 | Mix 40/40/20 | 3.7 | 15.9% | −43% | −24% | Good balance if you can sit through a −43% drop. |
| 4 | 100% 2× S&P trend | 4.2 | 13.9% | −38% | −23% | Simplest active option and the best in 2008, but the worst Sharpe of the active options and weak in fast crashes. |
| 5 | Mix 50/50/0 | 4.7 | 18.1% | −55% | −32% | SPY-level risk for 7 points more return a year; nearly 10 years below a previous peak. |
| 6 | 100% 2× Nasdaq trend | 5.7 | 20.8% | −72% | −41% | Highest return by far, but 13.6 years below a previous peak and the worst worst-year. A bet, not a plan. |
| 7 | SPY buy-and-hold | 5.8 | 10.9% | −55% | −32% | Lowest return; no bot, no costs, no decisions. The benchmark everything above has to beat. |
| 8 | QQQ buy-and-hold | 6.8 | 14.7% | −83% | −44% | Good return but the deepest drop and longest recovery (14.9 years). |

If return matters most, the order flips: 2× Nasdaq trend, then 50/50/0, then 40/40/20, then QQQ. Each step up that list adds return and adds depth to the worst drop.

Same method as the sections below: calibrated fund costs, 0.05% per trade, signals traded at the close, Nasdaq-100 before 1999 from the index. Past results, not a forecast.

## Candidates

Sorted by how well each fits the v1 bot, best first.

| Strategy | The rule in one line | Instruments | Decisions | Fit with v1 bot | Evidence | Main risk |
| --- | --- | --- | --- | --- | --- | --- |
| Trend-following asset allocation | Hold each asset only while it is above its 10-month moving average, else cash | 5 ETFs (US stocks, foreign stocks, bonds, REITs, commodities) | Monthly, a few trades a year | Excellent | [Faber 2007](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461): equity-like returns with bond-like drawdowns since 1972; most downloaded SSRN paper | Lags at turning points; whipsaws in sideways markets |
| Dual momentum | Each month hold US or foreign stocks, whichever has the higher 12-month return, but switch to bonds if that return is below T-bills | 3 ETFs | Monthly | Excellent | [Antonacci](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2042750): absolute momentum cuts drawdowns; won the 2012 NAAIM award | All-in on one asset; long flat stretches |
| Turn-of-the-month | Hold an index ETF from the last trading day of the month through the third day of the next | 1 ETF (e.g. SPY) | 12 trades a year | Excellent | [McConnell & Xu 2008](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1135217): 1926–2005 excess return came almost entirely in this window; found in 31 of 35 countries | Edge may have weakened since publication; out of the market \~80% of days |
| Short-term mean reversion (RSI-2) | Buy SPY/QQQ when 2-day RSI < 10 and price is above its 200-day average; sell on a bounce | 1–2 ETFs | Daily, holds 3–5 days | Excellent | Practitioner rule by Larry Connors, widely reproduced ([StockCharts](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2)); no academic paper | Very crowded; rare big losses in crashes; sensitive to parameters |
| Time-series momentum (managed futures) | Go long or short each market by the sign of its 12-month return, sized by volatility | 20+ futures | Daily or weekly | Medium: futures rolls, larger account | [Moskowitz, Ooi & Pedersen 2012](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf); pysystemtrade implements it | Needs capital to diversify; contract sizes; roll handling |
| Put writing / the wheel | Sell monthly cash-secured puts on an index ETF; if assigned, sell covered calls | ETF options | Monthly | Medium: option chains, assignment | [Cboe PUT index](https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf): implied vol averaged 19.3% vs 15.1% realized (1990–2018); [thetagang](https://github.com/brndnmtthws/thetagang) implements it on IBKR | Short volatility: steady gains, sharp losses in crashes |
| Pairs trading | Trade two related stocks when their price spread stretches, bet it closes | 2 stocks per pair | Daily | Medium: shorting, two legs at once | [Gatev, Goetzmann & Rouwenhorst 2006](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=141615): up to 11% a year excess, 1962–2002 | Pairs break apart; check later studies for decay |
| Opening range breakout (intraday) | Trade the direction of the first 5-minute candle with a tight stop | QQQ or stocks | Several a day | Low: needs 5-min bars, intraday execution, PDT rule | [Zarattini & Aziz](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622) report 33% alpha a year, but an [independent replication](https://www.mql5.com/en/blogs/post/776235) found it nets about zero after spread and slippage | Costs eat the edge |

## Return history

Over Jan 2007 to Sep 2026, nothing beat buying and holding SPY: $10k grew to about $77k, against $28k–$49k for the strategies. What the strategies bought was smaller losses. Trend-following and RSI-2 never fell more than 15%, while SPY fell 55% in 2008–09.

&#91;embedded content: own backtest · daily total-return prices from Yahoo Finance, Cboe PUT index, Jan 2007–Sep 2026\]

Sorted by risk-adjusted return (Sharpe ratio, excess over T-bills):

| Strategy | Sharpe | Worst year | 2008 | 2022 | CAGR 2007–16 | CAGR 2017–26 | Trades a year | $10k became |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 60/40 SPY/IEF | 0.63 | −16.7% | −16.7% | −16.4% | 7.0% | 9.7% | rebalance only | $48.6k |
| SPY buy-and-hold | 0.55 | −36.8% | −36.8% | −18.2% | 6.9% | 15.2% | 0 | $77.2k |
| Trend-following (Faber GTAA5) | 0.50 | −4.6% | −2.7% | −4.6% | 4.2% | 6.6% | \~7 rebalance days | $28.0k |
| Put writing (Cboe PUT index) | 0.46 | −26.8% | −26.8% | −7.7% | 6.1% | 8.4% | 12 option rolls | $39.7k |
| Dual momentum (GEM) | 0.43 | −16.5% | −2.9% | −16.5% | 5.8% | 9.0% | \~2 switches | $40.3k |
| RSI-2 mean reversion | 0.39 | −9.4% | +1.4% | −1.4% | 2.2% | 5.6% | \~8 round trips | $21.1k |
| Turn-of-the-month | 0.01 | −10.5% | −10.5% | −3.2% | −0.5% | 3.2% | 12 round trips | $12.8k |

What the numbers say:

- **Best risk-adjusted: plain 60/40**, which needs no bot at all. No strategy beat it on Sharpe ratio.
- **Best crash protection: trend-following.** It lost 2.7% in 2008 while SPY lost 36.8%, and its worst year was −4.6%. The cost is lagging badly in bull markets.
- **Dual momentum** dodged 2008 (−2.9%) but not 2022 (−16.5%), when stocks and bonds fell together.
- **RSI-2** was in the market only 11% of days, so its return is low but steady. Its monthly correlation with trend-following is 0.36, which makes it a candidate to run alongside it (not tested as a combination).
- **Turn-of-the-month has stopped working:** about the same as holding cash over 20 years, and negative in 2007–16. That fits the paper's sample ending in 2005.
- **Put writing** looks good on paper, but this is an index with no trading costs, and it still fell 27% in 2008.

How this was run:

- Rules as published, with no parameter tuning. Daily total-return ETF prices from Yahoo Finance; cash earns the 13-week T-bill rate.
- Signals are taken at the close and traded at that close, which a market-on-close order makes realistic. Each trade pays 0.05% per side for commission and spread.
- Put writing uses Cboe's published PUT index, which has no costs. Taxes are ignored throughout.
- Not tested here: managed futures (needs futures data), pairs trading (no single standard rule) and opening range breakout (needs intraday data; see the replication in the table above).
- One historical path with a strong US bull market after 2009. A different decade could rank these differently.

## Beating the market

You can beat SPY's return, but almost only by taking more risk. The strategies above trade return for safety. Leverage trades it back, and a trend filter keeps the leverage survivable. The best version tested, 2× SPY when SPY is above its 200-day average and cash otherwise, beat buy-and-hold in every period below with a similar worst drop. It did not beat it on risk-adjusted return after its paper was published.

For scale: 79% of active US large-cap funds trailed the S&P 500 in 2025 ([SPIVA via InvestmentNews](https://www.investmentnews.com/equities/active-managers-stumble-again-in-2025-as-large-caps-dominate/265541)). A small bot is unlikely to find what most professionals miss.

**Why the earlier strategies still matter:** a strategy with smaller drops can carry leverage that SPY can't. In 2007–2026, plain 60/40 had a higher Sharpe ratio than SPY (0.63 vs 0.55), and levering it 1.7× on IBKR margin edged past SPY: 11.3% a year vs 10.9%, worst drop −51% vs −55%.

Leverage plus a trend filter ([Gayed & Bilello 2016](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2741701)). Each cell shows annual return / worst drop / Sharpe ratio:

| Strategy | 1994–2026 | 2007–2026 | Apr 2016–2026 (after the paper) |
| --- | --- | --- | --- |
| SPY buy-and-hold | 10.9% / −55% / 0.51 | 10.9% / −55% / 0.55 | 15.2% / −34% / 0.76 |
| 2× SPY above 200-day, else cash | 12.8% / −52% / 0.52 | 13.9% / −39% / 0.61 | 19.3% / −37% / 0.76 |
| 3× SPY above 200-day, else cash | 16.3% / −71% / 0.53 | 18.6% / −54% / 0.62 | 26.6% / −51% / 0.77 |

What this shows:

- **The filter makes leverage survivable.** Always-on 2× and 3× SPY fell 84–98% at their worst. The 200-day filter stepped aside in slow bear markets: 2× trend made 3.4% in 2001 and lost only 6.7% in 2008, against SPY's −11.8% and −36.8%. It failed in choppy ones: in 2022 it lost 27.5% against SPY's 18.2%.
- **Most of the edge is leverage, not skill.** Since publication, the Sharpe ratio matches SPY's. The filter mainly keeps the leverage from blowing up.
- **It is hard to live with.** 2× trend beat SPY in only 17 of 33 calendar years. It lost 19.5% in 2011 while SPY gained 1.9%, and 15.5% in 2007 while SPY gained 5.1%. Those are whipsaw years, when the price crossed the average back and forth.
- **Risks the backtest can't show:** a one-day crash like Oct 1987's −20% would cost a 2× fund about 40% before the filter could react. About 6.5 switches a year also mean short-term capital gains taxes in a taxable account.

This fits the bot well: one check a day at the close (SPY vs its 200-day average), one instrument (SSO for 2×), about 6 trades a year. It is a reasonable first live strategy if you accept the drawdowns above.

How this was run: daily-reset leveraged funds modelled as 2×/3× SPY's daily return, minus financing at the T-bill rate and the fund's fee. The model was calibrated to the real SSO, which trailed the raw model by about 0.7% a year over 2007–2026. Same 0.05% cost per trade, and signals traded at the close, as above. The table uses the calibrated model. The always-on 2×/3× drawdowns use the raw model, so they are slightly optimistic. Levered 60/40 borrows on margin at the T-bill rate plus 1.5%.

## Moving-average length

The 200-day average isn't magic, but it sits at the start of a stable range. Every length from 200 to 300 days except 260 beat SPY in all three periods tested. Lengths under about 150 days lost to SPY in most periods: they switch 10–30 times a year and get whipsawed, losing on false signals when the price crosses back and forth. The 100-day average did well after 2016 but lost 6.9 points a year to SPY in 1994–2006, and fell 78% at its worst.

&#91;embedded content: own backtest · lengths 20–300 days in steps of 10, Jan 1994–Sep 2026, calibrated 2× model\]

Full period, Jan 1994 to Sep 2026:

| Moving average | Annual return | Worst drop | Sharpe | Worst year | Trades a year |
| --- | --- | --- | --- | --- | --- |
| SPY buy-and-hold | 10.9% | −55% | 0.51 | −36.8% | 0 |
| 100-day | 9.6% | −78% | 0.41 | −50.5% | 10.9 |
| 150-day | 10.9% | −61% | 0.45 | −36.9% | 8.9 |
| 200-day | 12.8% | −52% | 0.52 | −35.1% | 6.5 |
| 250-day | 12.8% | −45% | 0.51 | −32.5% | 5.3 |
| 300-day | 16.2% | −43% | 0.62 | −27.9% | 3.2 |
| Blend of 200, 250 and 300 | 14.1% | −38% | 0.56 | −28.6% | 12.7 (each a third of the position) |

What to take from it:

- **Pick a range, not the backtest winner.** 300 days looks best, but mostly because of 1994–2006 (+7.8 points a year). Choosing the best-scoring setting after the fact is overfitting, and it rarely repeats.
- **The blend is the most robust choice.** Hold 2× exposure in thirds: one third for each average (200, 250, 300) that SPY is above. That means SSO at 0%, 33%, 67% or 100% of the account, with cash for the rest. It beat SPY in every period (14.1% vs 10.8% in 1994–2006, 8.5% vs 6.3% in 2007–2016, 19.2% vs 15.2% since Apr 2016). It also had the smallest worst drop of any version, −38%.
- **Avoid short averages** for this strategy: under \~150 days, whipsaws cost more than the protection is worth.

Caveat: SPY's data starts in Jan 1993, so the 250- and 300-day averages didn't exist until early 1994. Those versions sat in cash until then, which cost little because SPY was flat that year (+0.4%). Still untested: trading at the next day's open instead of the close, and a small buffer around the average to cut whipsaws.

## More funds: 3× S&P 500, 2× and 3× Nasdaq-100

The Nasdaq-100 versions returned the most, 20–27% a year for averages of 225 days or more. But at their worst they lost 63–99%, mostly in 2000 before the signal got out. 2× S&P 500 with an average of 200–300 days is the only version that beat SPY while keeping its worst drop below SPY's −55%.

&#91;embedded content: own backtest · lengths 25–300 days in steps of 25, Jan 1994–Sep 2026, fund costs calibrated to SSO, UPRO, QLD, TQQQ\]

200-day average and the 200/250/300 blend, Jan 1994 to Sep 2026:

| Version | Annual return | Worst drop | Sharpe | Worst year | Fund cost vs model |
| --- | --- | --- | --- | --- | --- |
| SPY buy-and-hold | 10.9% | −55% | 0.51 | −36.8% | — |
| QQQ buy-and-hold | 14.7% | −83% | 0.56 | −41.7% | — |
| 2× S&P 500 (SSO), 200-day | 12.6% | −52% | 0.51 | −35.2% | 1.8%/yr |
| 2× S&P 500 (SSO), blend | 13.9% | −38% | 0.55 | −28.8% | 1.8%/yr |
| 3× S&P 500 (UPRO), 200-day | 15.5% | −71% | 0.51 | −51.8% | 2.9%/yr |
| 3× S&P 500 (UPRO), blend | 17.4% | −56% | 0.56 | −44.7% | 2.9%/yr |
| 2× Nasdaq-100 (QLD), 200-day | 18.6% | −84% | 0.58 | −49.5% | 2.0%/yr |
| 2× Nasdaq-100 (QLD), blend | 20.8% | −72% | 0.63 | −43.9% | 2.0%/yr |
| 3× Nasdaq-100 (TQQQ), 200-day | 21.2% | −95% | 0.58 | −73.5% | 2.9%/yr |
| 3× Nasdaq-100 (TQQQ), blend | 24.5% | −88% | 0.63 | −69.8% | 2.9%/yr |

What to take from it:

- **Every version from 200 to 300 days, and every blend, beat SPY in all three periods** (1994–2006, 2007–2016, 2016–2026). Among the shorter averages, only the Nasdaq versions at 50, 100 and 125 days did, plus 3× Nasdaq at 75.
- **The Nasdaq versions' higher return is mostly the Nasdaq itself.** QQQ alone returned 14.7% with an 83% crash. The filter lifted the Sharpe ratio from 0.56 to 0.63, but did not prevent near-wipeouts. 2× lost 45% and 3× lost 72% in 2000, before the signal got out.
- **Hindsight warning:** the Nasdaq-100 was the best major index of this era. Choosing it now is a bet that the next 30 years look like the last.
- **3× funds cost about 2.9% a year** beyond the leverage and crash faster than any average can react. 3× S&P 500 (300-day) fell 58% between July and October 1998. A 1987-style −20% day would cost a 3× fund about 60%.
- **Only 2× S&P 500 with 200–300 days beat SPY with a smaller worst drop than SPY.** That makes the 2× S&P blend the sensible core. If you want more, put a small slice into the 2× Nasdaq blend, sized so that a 70% drop on that slice is survivable.

How this was run: each fund's cost is measured from its real price history since launch (SSO and QLD 2006, UPRO 2009, TQQQ 2010), as the yearly gap between a plain 2×/3× model and the real fund. For SSO that is 1.8% a year, slightly higher than the earlier estimate, which started in 2007. Nasdaq-100 before QQQ's launch in Mar 1999 uses the index without dividends, about 0.3% a year, so it is slightly understated. Signals use each index's own moving average. Costs, cash and timing are as in the sections above.

## Best mix

The most robust mix found is about 30% 2× S&P 500 trend, 30% 2× Nasdaq-100 trend and 40% intermediate Treasuries, rebalanced monthly. Over 1994–2026 it returned 13.4% a year with a worst drop of −30%, against SPY's 10.9% and −55%. It held up in both halves of the test. Moving along the blue line trades a smaller drop for less return.

&#91;embedded content: own backtest · 286 mixes rebalanced monthly, Jan 1994–Sep 2026; trend legs are the 200/250/300 blends on 2× funds, cash when out\]

The blue-line mixes in both halves, against the alternatives. Mix = % in 2× S&P trend / 2× Nasdaq trend / intermediate Treasuries; half columns show annual return / worst drop:

| Mix | 1994–2010 | 2011–2026 | Worst year | Sharpe | Profile |
| --- | --- | --- | --- | --- | --- |
| 10/10/80 | 9.1% / −11% | 5.7% / −17% | −14.5% | 0.72 | Conservative |
| 20/20/60 | 11.6% / −21% | 9.4% / −22% | −18.5% | 0.70 | Cautious |
| **30/30/40** | **13.7% / −30%** | **13.0% / −27%** | **−22.4%** | **0.66** | **Balanced, recommended** |
| 40/30/30 | 14.1% / −33% | 14.4% / −29% | −24.1% | 0.65 | Growth |
| 40/40/20 | 15.5% / −43% | 16.3% / −33% | −26.3% | 0.64 | Aggressive |
| 50/50/0 | 16.9% / −55% | 19.4% / −40% | −33.8% | 0.63 | All trend, no bonds |
| 100/0/0 (2× S&P trend alone) | 11.7% / −38% | 16.2% / −37% | −28.8% | 0.55 | Earlier pick |
| SPY | 7.9% / −55% | 14.1% / −34% | −36.8% | 0.51 | Benchmark |
| QQQ | 10.8% / −83% | 19.1% / −35% | −41.7% | 0.55 | Benchmark |
| 60/40 SPY/Treasuries | 7.6% / −34% | 9.3% / −20% | −19.4% | 0.57 | Classic |
| UPRO/TMF 55/45 | 10.9% / −68% | 17.9% / −70% | −63.4% | 0.51 | Popular 3× mix |

What the search found:

- **The best mix on paper was the worst bet.** Mixes that scored best on 1994–2010 tended to score worst on 2011–2026 (rank correlation −0.84). 1994–2010 was a bond boom, so bond-heavy mixes topped it, then 2022 hit them. Long-term Treasuries never earned a reliable place.
- **Splitting across two trend strategies plus bonds is what works.** The likely reason (not measured separately): the two indexes don't cross their averages on the same days, and intermediate Treasuries cushion whipsaw stretches. 30/30/40 nearly matched the 2× S&P strategy alone (13.4% vs 13.9% a year) with a worst drop of −30% instead of −38%.
- **Holding bonds instead of cash when a trend leg is out** helped only in 1994–2010, so keep cash: it's simpler and doesn't depend on a bond rally.
- **UPRO/TMF 55/45, a popular 3× stocks plus 3× long bonds mix,** lost 63% in 2022 alone, when stocks and bonds fell together. TMF also trails a plain 3× bond model by about 3.8% a year.

Running the recommended mix: three ETFs (SSO, QLD and an intermediate Treasury ETF such as IEF), rebalanced to 30/30/40 once a month. Each trend leg checks its index against the 200/250/300-day averages every day. It holds the 2× fund at 0, 33, 67 or 100% of its slice, with cash for the rest.

Caveats:

- The blue line was chosen after seeing both halves, so it is not a clean out-of-sample result. It is the area that held up in both, not a forecast.
- The bond leg uses Vanguard's intermediate Treasury fund (VFITX), which has history back to 1991; IEF is the ETF equivalent.
- Gold, commodities and foreign stocks weren't tested; gold data only starts in 2004.
- Monthly rebalancing costs are left out; they are small next to the trend trades.

## Finer proportions

A finer search found no mix clearly better than 30/30/40, and re-optimizing the weights from past data would have cut returns in half. The scores are flat across a wide area: anything from about 15–30% S&P trend, 25–35% Nasdaq trend and 40–55% bonds behaves much the same. The best single cell, 20/30/50, trades about 1 point of return a year for 2 points less worst drop.

&#91;embedded content: own backtest · 231 mixes in 5% steps, scored on 1994–2006, 2007–2016 and 2016–2026\]

The best cells by each measure, 1994–2026 (mix = % S&P trend / Nasdaq trend / bonds):

| Mix | Why it's here | Annual return | Worst drop | Sharpe | Longest below a previous peak | Weakest-decade score |
| --- | --- | --- | --- | --- | --- | --- |
| 5/15/80 | Highest Sharpe | 7.9% | −17% | 0.73 | 2.6 yrs | 0.35 |
| 10/20/70 | Highest Sharpe in its weakest decade | 9.5% | −19% | 0.72 | 3.1 yrs | 0.43 |
| 15/30/55 | Plateau centre (score averaged with neighbours) | 11.9% | −27% | 0.69 | 3.6 yrs | 0.51 |
| 25/25/50 | Near the top, equal trend split | 12.0% | −26% | 0.68 | 3.6 yrs | 0.51 |
| **20/30/50** | **Top weakest-decade score** | **12.4%** | **−28%** | **0.68** | **3.7 yrs** | **0.52** |
| 30/30/40 | Current pick | 13.4% | −30% | 0.66 | 3.8 yrs | 0.44 |
| 35/35/30 | Closest to 33/33/33 | 14.7% | −36% | 0.65 | 6.9 yrs | 0.39 |

The weakest-decade score is a mix's annual return divided by its worst drop, taken in its worst of the three decades (1994–2006, 2007–2016, 2016–2026).

**Walk-forward test: would re-optimizing the weights have helped?** Starting in 2006, every five years I picked the mix with the best score using only earlier data, then held it for the next five years. It kept choosing about 85% bonds, because each training period was dominated by the 1994–2006 bond rally.

| 2006–2026 | Annual return | Worst drop | Sharpe |
| --- | --- | --- | --- |
| Re-optimized by return / drop | 6.0% | −17% | 0.75 |
| Re-optimized by Sharpe | 5.2% | −16% | 0.68 |
| Fixed 30/30/40 | 11.9% | −27% | 0.69 |
| Fixed 35/35/30 | 13.2% | −30% | 0.68 |

What this means:

- **There's no meaningfully better proportion.** Across the plateau the differences are about 1 point of return against 2–3 points of worst drop. That's a preference, not an improvement.
- **"Best Sharpe" means more bonds and less return,** which defeats the goal of beating the market. The Sharpe-optimal mixes returned less than SPY.
- **Don't re-optimize the weights from recent data.** Done honestly, it cut returns roughly in half compared with simply holding a fixed mix.
- **The top area tilts towards Nasdaq** (30% Nasdaq vs 15–20% S&P). That may just reflect the Nasdaq's exceptional run since 1994, so treat equal splits like 30/30/40 or 25/25/50 as the safer reading.
- **Choice:** keep 30/30/40, or use 20/30/50 or 25/25/50 if you'd trade about 1 point of return for a slightly smaller drop.

## Where to start

1. **First: trend-following asset allocation or dual momentum.** Free daily ETF data is enough, the rules have one or two parameters, and a monthly rebalance gives the bot time to prove itself on paper. A bug costs little when the bot trades a few times a year.
2. **Second: RSI-2 or turn-of-the-month on SPY.** Still daily ETF bars, but more trades, which exercises execution, fills and reconciliation. Both can run alongside the monthly strategy later.
3. **If you want options: the wheel.** Read thetagang's code first, since it already runs this on IBKR with ib\_async. It adds option chains and assignment handling to the bot.
4. **Park for later:** managed futures (better done in pysystemtrade), pairs trading (needs shorting) and anything intraday.

For each candidate, the deeper research is the same:

- [ ] Reproduce the published result on your own data
- [ ] Re-run it on the years after the paper came out
- [ ] Add IBKR commissions plus at least one tick of slippage per trade
- [ ] Check the worst drawdown and longest losing stretch, and ask whether you would keep running it through those

## Reality check

- **Costs decide most strategies.** The opening-range breakout is the clearest case: an edge of about 0.1 R per trade gross, which is about what a round trip costs ([replication](https://www.mql5.com/en/blogs/post/776235)). The fewer trades a strategy makes, the less this bites.
- **Published edges tend to shrink** once they're widely known. Test on the years after publication, not only the paper's sample.
- **Overfitting:** every parameter you tune makes the backtest look better and live results worse. Prefer rules with one or two parameters, and keep a period you never tune on.
- **Pattern-day-trader rule:** US margin accounts under $25k are limited in day trades. Check FINRA's current rule before choosing anything intraday.
- **Behaviour:** trend and momentum strategies spend long stretches losing to buy-and-hold. The strategy you can stick with beats the one with the best backtest.

## Sources

Papers and pages behind the table:

- [Faber, A Quantitative Approach to Tactical Asset Allocation](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)
- [Antonacci, Risk Premia Harvesting Through Dual Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2042750)
- [McConnell & Xu, Equity Returns at the Turn of the Month](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1135217)
- [StockCharts, RSI(2)](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2)
- [Moskowitz, Ooi & Pedersen, Time Series Momentum](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)
- [Bondarenko, Historical Performance of Put-Writing Strategies (Cboe)](https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf)
- [Gatev, Goetzmann & Rouwenhorst, Pairs Trading](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=141615)
- [Zarattini & Aziz, Can Day Trading Really Be Profitable?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622) and its [independent replication](https://www.mql5.com/en/blogs/post/776235)
- [thetagang](https://github.com/brndnmtthws/thetagang), an open-source IBKR wheel bot

Places to find more ideas: SSRN (search a strategy name plus "out of sample"), and Rob Carver's book *Systematic Trading* for position sizing and risk.

Links found on 2026-09-30. Figures come from the papers' abstracts and search summaries; only the opening-range replication was read in full, so check each paper before relying on its numbers.
