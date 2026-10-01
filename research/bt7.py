import io, runpy, sys
_o, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("bt6.py")
sys.stdout = _o
for idx, lev, w in [("Nasdaq-100", 2, 250), ("Nasdaq-100", 3, 250), ("S&P 500", 3, 300), ("S&P 500", 2, 200)]:
    r, _ = g["strat"](idx, lev, [w])
    r = r[r.index >= "1994-01-01"].fillna(0)
    eq = (1 + r).cumprod(); dd = eq / eq.cummax() - 1
    trough = dd.idxmin(); peak = eq[:trough].idxmax()
    yr = (1 + r).groupby(r.index.year).prod() - 1
    print(f"{lev}x {idx} {w}d: worst drop {dd.min():.3f} from {peak.date()} to {trough.date()}; 2000-02: {yr.loc[2000]:.2f} {yr.loc[2001]:.2f} {yr.loc[2002]:.2f}; 2022: {yr.loc[2022]:.2f}")
q = g["underlying"]["Nasdaq-100"]; yq = (1 + q.fillna(0)).groupby(q.index.year).prod() - 1
print("QQQ 2000-02:", yq.loc[[2000, 2001, 2002]].round(2).tolist(), "2022:", round(yq.loc[2022], 2))
