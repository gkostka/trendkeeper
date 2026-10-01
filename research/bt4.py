import io
import runpy
import sys

import pandas as pd

_out, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("bt2.py")
sys.stdout = _out
px, spy, cash, stats, levered_etf, COST = (g[k] for k in ["px", "spy", "cash", "stats", "levered_etf", "COST"])

DRAG = 0.007  # calibrated against real SSO, see bt3.py
sso = levered_etf(spy, 2, 0.0089 + DRAG)
PERIODS = [("1994-01-01", "2007-01-01"), ("2007-01-01", "2016-04-01"), ("2016-04-01", "2026-10-01"),
           ("1994-01-01", "2026-10-01")]


def trend(window):
    above = (px["SPY"] > px["SPY"].rolling(window).mean()).astype(float)
    held = above.shift(1).fillna(0)
    switches = above.diff().abs().shift(1).fillna(0)
    return held * sso + (1 - held) * cash - switches * COST, switches


rows = []
for w in range(20, 301, 10):
    r, sw = trend(w)
    for a, b in PERIODS:
        m = (r.index >= a) & (r.index < b)
        rows.append({"window": w, "period": f"{a[:4]}-{b[:4]}", **stats(r[m], sw[m])})
for a, b in PERIODS:
    m = (spy.index >= a) & (spy.index < b)
    rows.append({"window": 0, "period": f"{a[:4]}-{b[:4]}", **stats(spy[m], spy[m] * 0)})

res = pd.DataFrame(rows)
res.to_csv("ma_sweep.csv", index=False)
pd.set_option("display.width", 250)
for p, d in res.groupby("period"):
    print(f"\n== {p} (window 0 = SPY buy-and-hold)")
    print(d.drop(columns="period").set_index("window").round(3).to_string())

assert res["window"].nunique() == 30
