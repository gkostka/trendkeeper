import io, runpy, sys
import pandas as pd
_o, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("bt6.py")
sys.stdout = _o
level, px = g["level"], g["px"]
START = "1994-01-01"
SERIES = {"S&P 500 (SPY)": level["S&P 500"], "Nasdaq-100 (QQQ)": level["Nasdaq-100"]}


def runs(flag):
    """Lengths in trading days of consecutive True and False stretches."""
    grp = (flag != flag.shift()).cumsum()
    r = flag.groupby(grp).agg(["first", "size"])
    return r[r["first"]]["size"], r[~r["first"]]["size"]


for name, lv in SERIES.items():
    for w in [200, 250, 300]:
        above = (lv > lv.rolling(w).mean())
        above = above[above.index >= START]
        ins, outs = runs(above)
        yrs = len(above) / 252
        print(f"{name} {w}d: entries/yr {len(ins)/yrs:.1f} | in: median {ins.median():.0f}d mean {ins.mean():.0f}d max {ins.max()}d, "
              f"share of in-stretches < 10d {(ins < 10).mean():.0%} | out: median {outs.median():.0f}d mean {outs.mean():.0f}d max {outs.max()}d | time in {above.mean():.0%}")
    sig = sum((lv > lv.rolling(w).mean()).astype(float) for w in [200, 250, 300]) / 3
    sig = sig[sig.index >= START].round(2)
    print(f"{name} blend exposure share of days:", sig.value_counts(normalize=True).sort_index().round(3).to_dict(),
          "| changes/yr", round((sig.diff().abs() > 0).sum() / (len(sig) / 252), 1))
    last = lv.dropna().index[-1]
    for w in [200, 250, 300]:
        ma = lv.rolling(w).mean()
        print(f"   today {last.date()} {w}d avg: price/avg {lv[last] / ma[last] - 1:+.1%}")
