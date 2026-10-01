import io, runpy, sys
_o, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("bt4.py")
sys.stdout = _o
px, spy, cash, stats, sso, COST, PERIODS = (g[k] for k in ["px", "spy", "cash", "stats", "sso", "COST", "PERIODS"])

WINDOWS = [200, 250, 300]
sig = sum((px["SPY"] > px["SPY"].rolling(w).mean()).astype(float) for w in WINDOWS) / len(WINDOWS)
held = sig.shift(1).fillna(0)
traded = sig.diff().abs().shift(1).fillna(0)
r = held * sso + (1 - held) * cash - traded * COST
for a, b in PERIODS:
    m = (r.index >= a) & (r.index < b)
    s = stats(r[m], (traded[m] > 0).astype(float))
    print(f"ensemble 200/250/300 {a[:4]}-{b[:4]}: cagr {s['cagr']:.3f} dd {s['max_dd']:.3f} sharpe {s['sharpe']:.2f} worst_yr {s['worst_year']:.3f} trades/yr {s['switches_yr']:.1f}")

res = g["res"]
spy_c = res[res.window == 0].set_index("period")["cagr"]
sub = res[(res.window > 0) & (res.period != "1994-2026")].copy()
sub["excess"] = sub.cagr - sub.period.map(spy_c)
sub[["window", "period", "excess"]].round(4).to_csv("ma_excess.csv", index=False)
beat_all = sub.groupby("window").excess.apply(lambda e: (e > 0).all())
print("windows beating SPY in all 3 sub-periods:", list(beat_all[beat_all].index))
