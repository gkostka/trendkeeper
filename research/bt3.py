import runpy, sys, io
_o = sys.stdout; sys.stdout = io.StringIO()
g = runpy.run_path("bt2.py")
sys.stdout = _o
levered_etf, trend, spy, stats, cash = g["levered_etf"], g["trend"], g["spy"], g["stats"], g["cash"]
DRAG = 0.007  # calibrated: real SSO trailed the model by ~0.7%/yr over 2007-2026
for lev, fee in [(2, 0.0089 + DRAG), (3, 0.0091 + 1.5 * DRAG)]:
    r, sw = trend(levered_etf(spy, lev, fee))
    for a, b in [("1994-01-01", "2026-10-01"), ("2007-01-01", "2026-10-01"), ("2016-04-01", "2026-10-01")]:
        m = (r.index >= a) & (r.index < b)
        s, bh = stats(r[m], sw[m]), stats(spy[m], sw[m] * 0)
        print(f"{lev}x trend {a[:4]}-2026: cagr {s['cagr']:.3f} dd {s['max_dd']:.3f} sharpe {s['sharpe']:.2f} | SPY cagr {bh['cagr']:.3f} dd {bh['max_dd']:.3f} sharpe {bh['sharpe']:.2f}")
r, sw = trend(levered_etf(spy, 2, 0.0089 + DRAG))
yr = (1 + r.fillna(0)).groupby(r.index.year).prod() - 1
by = (1 + spy.fillna(0)).groupby(spy.index.year).prod() - 1
yrs = yr.index >= 1994
print("years 2x-trend beat SPY:", int((yr[yrs] > by[yrs]).sum()), "of", int(yrs.sum()))
