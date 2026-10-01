import numpy as np
import pandas as pd
import yfinance as yf

COST = 0.0005
MARGIN_SPREAD = 0.015  # IBKR-style margin rate: T-bill + ~1.5%

px = yf.download(["SPY", "IEF", "SSO", "^IRX"], start="1993-01-01", end="2026-10-01",
                 auto_adjust=True, progress=False)["Close"].dropna(subset=["SPY"]).ffill()
cash = (px["^IRX"] / 100 / 252).shift(1).fillna(0)
spy = px["SPY"].pct_change()
ief = px["IEF"].pct_change()


def levered_etf(r, lev, fee):
    """Daily-reset leveraged fund: lev x return, pays (lev-1) x cash financing plus expense ratio."""
    return lev * r - (lev - 1) * cash - fee / 252


above = (px["SPY"] > px["SPY"].rolling(200).mean()).astype(float)


def trend(r_on):
    held = above.shift(1).fillna(0)
    switches = above.diff().abs().shift(1).fillna(0)
    return held * r_on + (1 - held) * cash - switches * COST, switches


sso_sim = levered_etf(spy, 2, 0.0089)
upro_sim = levered_etf(spy, 3, 0.0091)
r6040 = 0.6 * spy + 0.4 * ief
L = 1.7
lev6040 = L * r6040 - (L - 1) * (cash + MARGIN_SPREAD / 252)
zero = pd.Series(0.0, index=px.index)

strategies = {
    "SPY buy-and-hold": (spy, zero),
    "SPY 2x, always": (sso_sim, zero),
    "SPY 3x, always": (upro_sim, zero),
    "SPY 1x above 200-day, else cash": trend(spy),
    "SPY 2x above 200-day, else cash": trend(sso_sim),
    "SPY 3x above 200-day, else cash": trend(upro_sim),
    "60/40 levered 1.7x on margin": (lev6040, zero),
}


def stats(r, sw):
    r = r.fillna(0)
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    ex = r - cash[r.index]
    return {
        "cagr": eq.iloc[-1] ** (1 / yrs) - 1,
        "max_dd": (eq / eq.cummax() - 1).min(),
        "sharpe": ex.mean() / ex.std() * np.sqrt(252),
        "worst_year": ((1 + r).groupby(r.index.year).prod() - 1).min(),
        "switches_yr": sw.sum() / yrs,
        "growth_10k": 10000 * eq.iloc[-1],
    }


pd.set_option("display.width", 250)
for start in ["2007-01-01", "1994-01-01"]:
    rows = {}
    for name, (r, sw) in strategies.items():
        if name.startswith("60/40") and start < "2003-01-01":
            continue
        m = r.index >= start
        rows[name] = stats(r[m], sw[m])
    print(f"\n== {start} to 2026-09-30")
    print(pd.DataFrame(rows).T.round(3).to_string())

m = (px.index >= "2007-01-01") & px["SSO"].notna()
real = px["SSO"][m].iloc[-1] / px["SSO"][m].iloc[0]
sim = (1 + sso_sim[m].iloc[1:]).prod()
print(f"\nSSO check 2007-2026: real growth {real:.2f}x, simulated {sim:.2f}x")

yearly = pd.DataFrame({n: (1 + strategies[n][0][px.index >= "1994-01-01"].fillna(0)).groupby(
    px.index[px.index >= "1994-01-01"].year).prod() - 1 for n in
    ["SPY buy-and-hold", "SPY 2x above 200-day, else cash", "SPY 3x, always"]})
print("\nyearly returns\n", yearly.round(3).to_string())

assert abs(sim / real - 1) < 0.15, "leveraged ETF model drifts from real SSO"
