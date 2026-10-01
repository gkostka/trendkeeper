import io, runpy, sys
import numpy as np
import pandas as pd
import yfinance as yf

_o, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("bt6.py")
sys.stdout = _o
px, cash, level, fund, COST = (g[k] for k in ["px", "cash", "level", "fund", "COST"])
itb = yf.download("VFITX", start="1990-01-01", end="2026-10-01", auto_adjust=True,
                  progress=False)["Close"].squeeze().reindex(px.index).ffill().pct_change()


def trend(idx):
    lv = level[idx]
    sig = sum((lv > lv.rolling(w).mean()).astype(float) for w in [200, 250, 300]) / 3
    held, traded = sig.shift(1).fillna(0), sig.diff().abs().shift(1).fillna(0)
    return held * fund(idx, 2) + (1 - held) * cash - traded * COST


def portfolio(blocks, w):
    per = blocks.index.to_period("M")
    rel = (1 + blocks.fillna(0)).groupby(per).cumprod() @ np.asarray(w)
    return rel / pd.Series(rel, index=blocks.index).groupby(per).shift(1).fillna(1.0) - 1


blocks = pd.DataFrame({"sp2": trend("S&P 500"), "nq2": trend("Nasdaq-100"), "itb": itb})
END = "2026-10-01"
for name, w in [("33/33/33", [1 / 3] * 3), ("30/30/40 check", [0.3, 0.3, 0.4])]:
    r = portfolio(blocks, w)
    r = r[(r.index >= "1994-01-01") & (r.index < END)].fillna(0)
    eq = (1 + r).cumprod()
    yr = (1 + r).groupby(r.index.year).prod() - 1
    ex = r - cash[r.index]
    under = (eq < eq.cummax())
    longest = under.groupby((~under).cumsum()).sum().max() / 252
    win = lambda a, b: eq[eq.index <= b].iloc[-1] / eq[eq.index < a].iloc[-1] - 1
    ann = lambda a: (eq.iloc[-1] / eq[eq.index <= a].iloc[-1]) ** (365.25 / (eq.index[-1] - eq[eq.index <= a].index[-1]).days) - 1
    print(name, {
        "cagr": eq.iloc[-1] ** (252 / len(r)) - 1, "last10": ann("2016-09-30"), "last20": ann("2006-09-30"), "last30": ann("1996-09-30"),
        "max_dd": (eq / eq.cummax() - 1).min(), "underwater_yrs": longest, "worst_year": yr.min(),
        "y2000_02": win("2000-01-01", "2002-12-31"), "y2008": yr.loc[2008],
        "covid": eq.loc["2020-03-23"] / eq.loc["2020-02-19"] - 1, "y2020": yr.loc[2020], "y2022": yr.loc[2022],
        "sharpe": ex.mean() / ex.std() * np.sqrt(252), "growth_10k": 10000 * eq.iloc[-1],
        "beat_spy_years": None})
