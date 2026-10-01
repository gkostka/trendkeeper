import io
import runpy
import sys

import numpy as np
import pandas as pd

_out, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("mix_third.py")
sys.stdout = _out
blocks, cash, portfolio = g["blocks"], g["cash"], g["portfolio"]

STEP = 5
GRID = [(a, b, 100 - a - b) for a in range(0, 101, STEP) for b in range(0, 101 - a, STEP)]
PERIODS = {"1994-2006": ("1994-01-01", "2007-01-01"), "2007-2016": ("2007-01-01", "2016-04-01"),
           "2016-2026": ("2016-04-01", "2026-10-01"), "full": ("1994-01-01", "2026-10-01")}


def stats(r):
    r = r.fillna(0)
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    ex = r - cash[r.index]
    under = eq < eq.cummax()
    cagr = eq.iloc[-1] ** (252 / len(r)) - 1
    return {"cagr": cagr, "dd": dd, "sharpe": ex.mean() / ex.std() * np.sqrt(252),
            "calmar": cagr / -dd, "under": under.groupby((~under).cumsum()).sum().max() / 252}


rets = {w: portfolio(blocks, [x / 100 for x in w]) for w in GRID}
rows = []
for w, r in rets.items():
    row = {"sp": w[0], "nq": w[1], "bd": w[2]}
    for p, (a, b) in PERIODS.items():
        row.update({f"{p}_{k}": v for k, v in stats(r[(r.index >= a) & (r.index < b)]).items()})
    rows.append(row)
res = pd.DataFrame(rows)
subs = [p for p in PERIODS if p != "full"]
res["worst_period_calmar"] = res[[f"{p}_calmar" for p in subs]].min(axis=1)
res["worst_period_sharpe"] = res[[f"{p}_sharpe" for p in subs]].min(axis=1)


def neighbour_mean(col):
    """Average of a metric over each mix and its neighbours within one step, to favour plateaus over spikes."""
    idx = res.set_index(["sp", "nq"])[col]
    out = []
    for r in res.itertuples():
        near = [idx.get((r.sp + da, r.nq + db)) for da in (-STEP, 0, STEP) for db in (-STEP, 0, STEP)]
        out.append(np.nanmean([v for v in near if v is not None]))
    return out


res["smooth_worst_calmar"] = neighbour_mean("worst_period_calmar")
res.to_csv("fine_grid.csv", index=False)
pd.set_option("display.width", 250)
show = ["sp", "nq", "bd", "full_cagr", "full_dd", "full_sharpe", "full_under", "worst_period_calmar",
        "worst_period_sharpe", "smooth_worst_calmar"]
for col in ["full_sharpe", "full_calmar", "worst_period_calmar", "worst_period_sharpe", "smooth_worst_calmar"]:
    print(f"\n== top 5 by {col}")
    print(res.nlargest(5, col)[show].round(3).to_string(index=False))
print("\n== reference mixes")
for w in [(30, 30, 40), (35, 35, 30), (40, 30, 30), (40, 40, 20)]:
    print(res[(res.sp == w[0]) & (res.nq == w[1])][show].round(3).to_string(index=False, header=False))

# Walk-forward: choose weights on all data before each test block, hold them through it.
TESTS = [("2006-01-01", "2011-01-01"), ("2011-01-01", "2016-01-01"), ("2016-01-01", "2021-01-01"),
         ("2021-01-01", "2026-10-01")]
for objective in ["calmar", "sharpe"]:
    chained, picks = [], []
    for a, b in TESTS:
        train = {w: stats(r[(r.index >= "1994-01-01") & (r.index < a)])[objective] for w, r in rets.items()}
        best = max(train, key=train.get)
        picks.append((a[:4], best))
        chained.append(rets[best][(rets[best].index >= a) & (rets[best].index < b)])
    wf = pd.concat(chained)
    s = stats(wf)
    print(f"\nwalk-forward by {objective}: picks {picks}")
    print(f"   2006-2026: cagr {s['cagr']:.3f} dd {s['dd']:.3f} sharpe {s['sharpe']:.2f} under {s['under']:.1f}")
for w in [(30, 30, 40), (35, 35, 30), (40, 30, 30)]:
    r = rets[w]
    s = stats(r[(r.index >= "2006-01-01") & (r.index < "2026-10-01")])
    print(f"fixed {w} 2006-2026: cagr {s['cagr']:.3f} dd {s['dd']:.3f} sharpe {s['sharpe']:.2f} under {s['under']:.1f}")

assert len(GRID) == 231
