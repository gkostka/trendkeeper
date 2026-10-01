import numpy as np
import pandas as pd
import yfinance as yf

COST = 0.0005
WINDOWS = list(range(25, 301, 25))
BLEND = [200, 250, 300]
PERIODS = [("1994-01-01", "2007-01-01"), ("2007-01-01", "2016-04-01"),
           ("2016-04-01", "2026-10-01"), ("1994-01-01", "2026-10-01")]

px = yf.download(["SPY", "QQQ", "^NDX", "^IRX", "SSO", "UPRO", "QLD", "TQQQ"], start="1990-01-01",
                 end="2026-10-01", auto_adjust=True, progress=False)["Close"].ffill()
px = px[px.index >= "1992-01-01"]
cash = (px["^IRX"] / 100 / 252).shift(1).fillna(0)

# Nasdaq-100: QQQ total return from inception, index price return before it (dividends then ~0.3%/yr).
qqq_r = px["QQQ"].pct_change().where(px["QQQ"].shift(1).notna(), px["^NDX"].pct_change())
underlying = {"S&P 500": px["SPY"].pct_change(), "Nasdaq-100": qqq_r}
level = {k: (1 + r.fillna(0)).cumprod() for k, r in underlying.items()}
level["S&P 500"] = level["S&P 500"].where(px["SPY"].notna())


def model(r, lev):
    return lev * r - (lev - 1) * cash


FUNDS = {("S&P 500", 2): "SSO", ("S&P 500", 3): "UPRO", ("Nasdaq-100", 2): "QLD", ("Nasdaq-100", 3): "TQQQ"}
drag = {}
for (idx, lev), tkr in FUNDS.items():
    real = px[tkr].pct_change().dropna()
    real = real[real.index >= real.index[0] + pd.Timedelta(days=30)]
    m = model(underlying[idx], lev)[real.index]
    drag[tkr] = (1 + m).prod() ** (252 / len(m)) - (1 + real).prod() ** (252 / len(real))
    print(f"{tkr}: since {real.index[0].date()}, model beats real by {drag[tkr]:.4f}/yr")


def fund(idx, lev):
    return model(underlying[idx], lev) - drag[FUNDS[(idx, lev)]] / 252


def strat(idx, lev, windows):
    lv = level[idx]
    sig = sum((lv > lv.rolling(w).mean()).astype(float) for w in windows) / len(windows)
    held, traded = sig.shift(1).fillna(0), sig.diff().abs().shift(1).fillna(0)
    return held * fund(idx, lev) + (1 - held) * cash - traded * COST, traded


def stats(r, traded):
    r = r.fillna(0)
    eq = (1 + r).cumprod()
    ex = r - cash[r.index]
    return {"cagr": eq.iloc[-1] ** (252 / len(r)) - 1, "max_dd": (eq / eq.cummax() - 1).min(),
            "sharpe": ex.mean() / ex.std() * np.sqrt(252),
            "worst_year": ((1 + r).groupby(r.index.year).prod() - 1).min(),
            "trades_yr": (traded > 0).sum() * 252 / len(r)}


rows = []
for (idx, lev) in FUNDS:
    for label, ws in [(str(w), [w]) for w in WINDOWS] + [("blend", BLEND)]:
        r, tr = strat(idx, lev, ws)
        for a, b in PERIODS:
            m = (r.index >= a) & (r.index < b)
            rows.append({"fund": f"{lev}x {idx}", "window": label, "period": f"{a[:4]}-{b[:4]}", **stats(r[m], tr[m])})
for idx in underlying:
    r = underlying[idx]
    for a, b in PERIODS:
        m = (r.index >= a) & (r.index < b)
        rows.append({"fund": f"1x {idx}", "window": "buy-hold", "period": f"{a[:4]}-{b[:4]}",
                     **stats(r[m], r[m] * 0)})

res = pd.DataFrame(rows)
res.to_csv("sweep25.csv", index=False)
pd.set_option("display.width", 250)
full = res[res.period == "1994-2026"].set_index(["fund", "window"]).drop(columns="period")
print(full.round(3).to_string())
sub = res[res.period != "1994-2026"]
spy_c = sub[sub.fund == "1x S&P 500"].set_index("period").cagr
sub = sub[sub.window != "buy-hold"].assign(beat=lambda d: d.cagr > d.period.map(spy_c))
print("\nbeat SPY in all 3 sub-periods:")
print(sub.groupby(["fund", "window"]).beat.all().unstack(0).to_string())

assert abs(drag["SSO"]) < 0.02 and res.fund.nunique() == 6
