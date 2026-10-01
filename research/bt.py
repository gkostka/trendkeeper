import io
import urllib.request

import numpy as np
import pandas as pd
import yfinance as yf

START, EVAL_START, END = "2005-01-01", "2007-01-01", "2026-10-01"
COST = 0.0005  # per side, on traded fraction: commission + half-spread for liquid ETFs

tickers = ["SPY", "EFA", "IEF", "VNQ", "DBC", "AGG", "^IRX"]
px = yf.download(tickers, start=START, end=END, auto_adjust=True, progress=False)["Close"]
px = px.dropna(subset=["SPY"]).ffill()
cash_d = (px["^IRX"] / 100 / 252).shift(1).fillna(0)
rets = px.drop(columns="^IRX").pct_change()
rets["CASH"] = cash_d

month_end = px.index.to_series().groupby(px.index.to_period("M")).last()
is_me = px.index.isin(month_end.values)


def run_weights(w):
    """Daily target weights decided at close t, applied to returns of t+1."""
    w = w.reindex(rets.index).ffill().fillna(0)
    held = w.shift(1).fillna(0)
    gross = (held * rets[w.columns].fillna(0)).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1).fillna(0)
    return gross - turnover.shift(1).fillna(0) * COST, turnover


def monthly_weights(fn):
    rows = {}
    for d in px.index[is_me]:
        rows[d] = fn(d)
    return pd.DataFrame(rows).T.fillna(0)


mpx = px[is_me]

GTAA = ["SPY", "EFA", "IEF", "VNQ", "DBC"]
sma10 = mpx[GTAA].rolling(10).mean()


def gtaa(d):
    w = {a: (0.2 if mpx.at[d, a] > sma10.at[d, a] else 0.0) for a in GTAA}
    w["CASH"] = 1 - sum(w.values())
    return w


cash_idx = (1 + cash_d).cumprod()
m12 = mpx[["SPY", "EFA"]].pct_change(12)
cash12 = cash_idx[is_me].pct_change(12)


def gem(d):
    best = "SPY" if m12.at[d, "SPY"] >= m12.at[d, "EFA"] else "EFA"
    return {best: 1.0} if m12.at[d, best] > cash12.at[d] else {"AGG": 1.0}


# Turn of month: hold SPY on last trading day of month + first 3 of the next.
pos_in_month = px.index.to_series().groupby(px.index.to_period("M")).cumcount()
from_end = px.index.to_series().groupby(px.index.to_period("M")).cumcount(ascending=False)
tom_day = (from_end == 0) | (pos_in_month <= 2)
tom_w = pd.DataFrame({"SPY": tom_day.astype(float).shift(-1).fillna(0)})
tom_w["CASH"] = 1 - tom_w["SPY"]

# RSI(2), Wilder smoothing; entry < 10 above 200d SMA, exit on close > 5d SMA.
spy = px["SPY"]
chg = spy.diff()
up = chg.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
dn = (-chg.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
rsi2 = 100 - 100 / (1 + up / dn)
sma200, sma5 = spy.rolling(200).mean(), spy.rolling(5).mean()
inpos, state = [], False
for t in spy.index:
    if not state and rsi2[t] < 10 and spy[t] > sma200[t]:
        state = True
    elif state and spy[t] > sma5[t]:
        state = False
    inpos.append(float(state))
rsi_w = pd.DataFrame({"SPY": inpos}, index=spy.index)
rsi_w["CASH"] = 1 - rsi_w["SPY"]

with urllib.request.urlopen("https://cdn.cboe.com/api/global/us_indices/daily_prices/PUT_History.csv") as f:
    put = pd.read_csv(io.StringIO(f.read().decode()), parse_dates=["DATE"], index_col="DATE")["PUT"]
put_r = put.reindex(px.index).ffill().pct_change()

strategies = {
    "SPY buy-and-hold": run_weights(pd.DataFrame({"SPY": 1.0}, index=px.index)),
    "60/40 SPY/IEF": run_weights(pd.DataFrame({"SPY": 0.6, "IEF": 0.4}, index=px.index)),
    "Trend-following (Faber GTAA5)": run_weights(monthly_weights(gtaa)),
    "Dual momentum (GEM)": run_weights(monthly_weights(gem)),
    "Turn-of-the-month": run_weights(tom_w),
    "RSI-2 mean reversion": run_weights(rsi_w),
    "Put writing (Cboe PUT index)": (put_r, pd.Series(0.0, index=px.index)),
}

ev = px.index >= EVAL_START
out, curves = [], {}
for name, (r, to) in strategies.items():
    r, to = r[ev].fillna(0), to[ev]
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    ex = r - cash_d[ev]
    yearly = (1 + r).groupby(r.index.year).prod() - 1

    def cagr(a, b):
        s = r[(r.index >= a) & (r.index < b)]
        return (1 + s).prod() ** (252 / len(s)) - 1

    out.append({
        "strategy": name,
        "cagr": eq.iloc[-1] ** (1 / yrs) - 1,
        "vol": r.std() * np.sqrt(252),
        "sharpe": ex.mean() / ex.std() * np.sqrt(252),
        "max_dd": (eq / eq.cummax() - 1).min(),
        "worst_year": yearly.min(),
        "y2008": yearly.get(2008),
        "y2022": yearly.get(2022),
        "cagr_07_16": cagr("2007-01-01", "2017-01-01"),
        "cagr_17_26": cagr("2017-01-01", END),
        "trades_per_year": (to > 0).sum() / yrs,
        "growth_10k": 10000 * eq.iloc[-1],
    })
    curves[name] = eq

res = pd.DataFrame(out).set_index("strategy")
pd.set_option("display.width", 250)
print(res.round(3).to_string())
print("period", r.index[0].date(), "to", r.index[-1].date())

q = pd.DataFrame(curves)
q = q[q.index.isin(q.index.to_series().groupby(q.index.to_period("Q")).last().values)] * 10000
q.round(0).to_csv("curves_quarterly.csv")
res.to_csv("results.csv")

assert abs(strategies["SPY buy-and-hold"][0][ev].fillna(0).add(1).prod()
           - px["SPY"][ev].iloc[-1] / px["SPY"][px.index < EVAL_START].iloc[-1]) < 1e-6
assert set(np.unique(rsi_w["SPY"])) <= {0.0, 1.0}
assert ((tom_w["SPY"].groupby(px.index.to_period("M")).sum()) <= 5).all()

held_rsi = rsi_w["SPY"].shift(1)[ev]
print("rsi2 time in market", round(held_rsi.mean(), 3))
gt = strategies["Trend-following (Faber GTAA5)"][0][ev]
rs = strategies["RSI-2 mean reversion"][0][ev]
print("monthly corr gtaa/rsi2", round(gt.add(1).resample("M").prod().corr(rs.add(1).resample("M").prod()), 2))
