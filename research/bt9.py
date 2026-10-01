import io
import runpy
import sys

import numpy as np
import pandas as pd

_out, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("bt8.py")
sys.stdout = _out
trend, portfolio, cash, underlying, itb = (g[k] for k in ["trend", "portfolio", "cash", "underlying", "itb"])

sp2, nq2 = trend("S&P 500", cash), trend("Nasdaq-100", cash)
blocks = pd.DataFrame({"sp2": sp2, "nq2": nq2, "itb": itb})
CANDIDATES = {
    "spy": ("S&P 500 buy-and-hold (SPY)", underlying["S&P 500"]),
    "qqq": ("Nasdaq-100 buy-and-hold (QQQ)", underlying["Nasdaq-100"]),
    "sp2": ("2× S&P 500 trend (SSO)", sp2),
    "m303040": ("Mix 30/30/40", portfolio(blocks, [0.3, 0.3, 0.4])),
    "m403030": ("Mix 40/30/30", portfolio(blocks, [0.4, 0.3, 0.3])),
    "m404020": ("Mix 40/40/20", portfolio(blocks, [0.4, 0.4, 0.2])),
    "m505000": ("Mix 50/50/0", portfolio(blocks, [0.5, 0.5, 0.0])),
    "nq2": ("2× Nasdaq-100 trend (QLD)", nq2),
}
START, END = "1994-01-01", "2026-10-01"


def longest_underwater_years(eq):
    peak = eq.cummax()
    under = eq < peak
    run = best = 0
    for u in under:
        run = run + 1 if u else 0
        best = max(best, run)
    return best / 252


spy_y = None
rows, curves = [], {}
for key, (name, r) in CANDIDATES.items():
    r = r[(r.index >= START) & (r.index < END)].fillna(0)
    eq = (1 + r).cumprod()
    yr = (1 + r).groupby(r.index.year).prod() - 1
    if key == "spy":
        spy_y = yr
    ex = r - cash[r.index]
    period = lambda a, b: (1 + r[(r.index >= a) & (r.index < b)]).prod() - 1
    cagr = lambda a, b: (1 + period(a, b)) ** (252 / len(r[(r.index >= a) & (r.index < b)])) - 1
    rows.append({
        "key": key, "name": name,
        "cagr": eq.iloc[-1] ** (252 / len(r)) - 1,
        "max_dd": (eq / eq.cummax() - 1).min(),
        "sharpe": ex.mean() / ex.std() * np.sqrt(252),
        "worst_year": yr.min(),
        "y2000_02": period("2000-01-01", "2003-01-01"),
        "y2008": yr.loc[2008], "y2022": yr.loc[2022],
        "cagr_last10": cagr("2016-10-01", END),
        "cagr_last20": cagr("2006-10-01", END),
        "cagr_last30": cagr("1996-10-01", END),
        "underwater_yrs": longest_underwater_years(eq),
        "beat_spy_years": int((yr > spy_y).sum()) if key != "spy" else None,
        "growth_10k": 10000 * eq.iloc[-1],
    })
    curves[key] = eq * 10000

res = pd.DataFrame(rows).set_index("key")
pd.set_option("display.width", 250)
print(res.round(3).to_string())
print("years:", len(spy_y))

q = pd.DataFrame(curves)
q = q[q.index.isin(q.index.to_series().groupby(q.index.to_period("Q")).last().values)]
start = pd.DataFrame({k: [10000.0] for k in curves}, index=[pd.Timestamp("1993-12-31")])
q = pd.concat([start, q])
q.to_csv("curves_shortlist.csv")
long = q.stack().reset_index()
long.columns = ["t", "s", "v"]
long["t"] = long.t.dt.year + (long.t.dt.month) / 12
long["v"] = (long.v / 1000).round(1)
long["t"] = long.t.round(2)
long[["s", "t", "v"]].to_csv("shortlist_growth_long.csv", index=False)
assert abs(res.loc["spy", "cagr"] - 0.109) < 0.002
