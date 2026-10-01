"""The research model (research/bt6.py, bt8.py), vectorized and unchanged, kept as the yardstick for bot.engine."""
import numpy as np
import pandas as pd

COST = 0.0005
BLEND = [200, 250, 300]
START, END = "1994-01-01", "2026-10-01"


def inputs(px: pd.DataFrame) -> dict:
    close = px.filter(like=".close").rename(columns=lambda c: c[: -len(".close")]).ffill()
    close = close[close.index >= "1992-01-01"]
    cash = (close["^IRX"] / 100 / 252).shift(1).fillna(0)
    qqq = close["QQQ"].pct_change()
    underlying = {
        "SPY": close["SPY"].pct_change(),
        "QQQ": qqq.where(close["QQQ"].shift(1).notna(), close["^NDX"].pct_change()),
    }
    level = {k: (1 + r.fillna(0)).cumprod() for k, r in underlying.items()}
    level["SPY"] = level["SPY"].where(close["SPY"].notna())
    return {"close": close, "cash": cash, "underlying": underlying, "level": level,
            "bonds": close["VFITX"].pct_change()}


def model(r, lev, cash):
    return lev * r - (lev - 1) * cash


def drag(real_close, r, lev, cash):
    real = real_close.pct_change().dropna()
    real = real[real.index >= real.index[0] + pd.Timedelta(days=30)]
    m = model(r, lev, cash)[real.index]
    return (1 + m).prod() ** (252 / len(m)) - (1 + real).prod() ** (252 / len(real))


def trend(d, signal, lev, cost_per_year):
    lv = d["level"][signal]
    sig = sum((lv > lv.rolling(w).mean()).astype(float) for w in BLEND) / len(BLEND)
    held, traded = sig.shift(1).fillna(0), sig.diff().abs().shift(1).fillna(0)
    fund = model(d["underlying"][signal], lev, d["cash"]) - cost_per_year / 252
    return held * fund + (1 - held) * d["cash"] - traded * COST


def portfolio(blocks, weights):
    per = blocks.index.to_period("M")
    rel = (1 + blocks.fillna(0)).groupby(per).cumprod() @ np.asarray(weights)
    prev = pd.Series(rel, index=blocks.index).groupby(per).shift(1).fillna(1.0)
    return rel / prev - 1


def stats(r, start=START, end=END):
    r = r[(r.index >= start) & (r.index < end)].fillna(0)
    eq = (1 + r).cumprod()
    return {"cagr": eq.iloc[-1] ** (252 / len(r)) - 1, "max_dd": (eq / eq.cummax() - 1).min()}


def mix_30_30_40(px):
    d = inputs(px)
    sso = drag(d["close"]["SSO"], d["underlying"]["SPY"], 2, d["cash"])
    qld = drag(d["close"]["QLD"], d["underlying"]["QQQ"], 2, d["cash"])
    blocks = pd.DataFrame({"sp": trend(d, "SPY", 2, sso), "nq": trend(d, "QQQ", 2, qld), "b": d["bonds"]})
    return portfolio(blocks, [0.3, 0.3, 0.4]), {"SSO": sso, "QLD": qld}, d


if __name__ == "__main__":
    from pathlib import Path
    from bot.data import load_snapshot

    px = load_snapshot(Path(__file__).parent / "data" / "prices.csv.gz")
    r, drags, d = mix_30_30_40(px)
    print("drag", {k: round(v, 4) for k, v in drags.items()})
    print("30/30/40", stats(r))
    print("SPY", stats(d["underlying"]["SPY"]))
    print("QQQ", stats(d["underlying"]["QQQ"]))
