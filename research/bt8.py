import io
import itertools
import runpy
import sys

import numpy as np
import pandas as pd
import yfinance as yf

_out, sys.stdout = sys.stdout, io.StringIO()
g = runpy.run_path("bt6.py")
sys.stdout = _out
px, cash, underlying, level, fund, COST, BLEND, drag, model = (
    g[k] for k in ["px", "cash", "underlying", "level", "fund", "COST", "BLEND", "drag", "model"])

bonds = yf.download(["VFITX", "VUSTX", "TMF"], start="1990-01-01", end="2026-10-01",
                    auto_adjust=True, progress=False)["Close"].reindex(px.index).ffill()
itb, ltb = bonds["VFITX"].pct_change(), bonds["VUSTX"].pct_change()

tmf_real = bonds["TMF"].pct_change().dropna()
tmf_real = tmf_real[tmf_real.index >= tmf_real.index[0] + pd.Timedelta(days=30)]
tmf_m = model(ltb, 3)[tmf_real.index]
tmf_drag = (1 + tmf_m).prod() ** (252 / len(tmf_m)) - (1 + tmf_real).prod() ** (252 / len(tmf_real))
print(f"TMF model beats real by {tmf_drag:.4f}/yr")
tmf = model(ltb, 3) - tmf_drag / 252


def trend(idx, out):
    lv = level[idx]
    sig = sum((lv > lv.rolling(w).mean()).astype(float) for w in BLEND) / len(BLEND)
    held, traded = sig.shift(1).fillna(0), sig.diff().abs().shift(1).fillna(0)
    return held * fund(idx, 2) + (1 - held) * out - traded * COST


IS, OOS, FULL = ("1994-01-01", "2011-01-01"), ("2011-01-01", "2026-10-01"), ("1994-01-01", "2026-10-01")


def portfolio(blocks, weights, freq="M"):
    """Rebalanced to target weights at the start of each period; weights drift within it."""
    per = blocks.index.to_period(freq)
    cg = (1 + blocks.fillna(0)).groupby(per).cumprod()
    rel = cg @ np.asarray(weights)
    prev = pd.Series(rel, index=blocks.index).groupby(per).shift(1).fillna(1.0)
    return rel / prev - 1


def stats(r, span):
    r = r[(r.index >= span[0]) & (r.index < span[1])].fillna(0)
    eq = (1 + r).cumprod()
    ex = r - cash[r.index]
    cagr = eq.iloc[-1] ** (252 / len(r)) - 1
    dd = (eq / eq.cummax() - 1).min()
    return {"cagr": cagr, "dd": dd, "sharpe": ex.mean() / ex.std() * np.sqrt(252),
            "worst_year": ((1 + r).groupby(r.index.year).prod() - 1).min(), "calmar": cagr / -dd}


NAMES = ["sp2", "nq2", "itb", "ltb"]
rows = []
for out_name, out in [("cash", cash), ("bonds", itb)]:
    blocks = pd.DataFrame({"sp2": trend("S&P 500", out), "nq2": trend("Nasdaq-100", out),
                           "itb": itb, "ltb": ltb})
    for w in itertools.product(range(0, 11), repeat=4):
        if sum(w) != 10:
            continue
        r = portfolio(blocks, [x / 10 for x in w])
        row = {"out": out_name, **dict(zip(NAMES, w))}
        for tag, span in [("is", IS), ("oos", OOS), ("full", FULL)]:
            row.update({f"{tag}_{k}": v for k, v in stats(r, span).items()})
        rows.append(row)

refs = {
    "SPY": underlying["S&P 500"], "QQQ": underlying["Nasdaq-100"],
    "60/40 SPY/VFITX": portfolio(pd.DataFrame({"a": underlying["S&P 500"], "b": itb}), [0.6, 0.4]),
    "HFEA 55/45 UPRO/TMF": portfolio(pd.DataFrame({"a": fund("S&P 500", 3), "b": tmf}), [0.55, 0.45], "Q"),
}
for name, r in refs.items():
    row = {"out": "ref", "name": name}
    for tag, span in [("is", IS), ("oos", OOS), ("full", FULL)]:
        row.update({f"{tag}_{k}": v for k, v in stats(r, span).items()})
    rows.append(row)

res = pd.DataFrame(rows)
res.to_csv("mix_grid.csv", index=False)
grid = res[res.out != "ref"]
pd.set_option("display.width", 250)
cols = ["out"] + NAMES + [f"{t}_{k}" for t in ["is", "oos", "full"] for k in ["cagr", "dd", "sharpe"]]

print("\n== references")
print(res[res.out == "ref"][["name"] + cols[5:]].round(3).to_string(index=False))

print("\n== chosen on 1994-2010: highest in-sample return within a drawdown limit")
picks = []
for lim in [-0.20, -0.25, -0.30, -0.35, -0.40, -0.50]:
    ok = grid[grid.is_dd >= lim]
    if len(ok):
        p = ok.loc[ok.is_cagr.idxmax()].copy()
        p["limit"] = lim
        picks.append(p)
print(pd.DataFrame(picks)[["limit"] + cols].round(3).to_string(index=False))

print("\n== top 10 by in-sample return/drawdown (Calmar)")
print(grid.nlargest(10, "is_calmar")[cols + ["is_calmar", "oos_calmar"]].round(3).to_string(index=False))

print("\nrank corr in-sample vs out-of-sample calmar:",
      round(grid.is_calmar.rank().corr(grid.oos_calmar.rank()), 2))
assert len(grid) == 2 * 286
