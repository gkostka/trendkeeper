"""Measures a leveraged fund's yearly cost: the `cost` that makes its model grow like the real fund.

    python -m bot.calibrate CONFIG SNAPSHOT[,SNAPSHOT] FUND [FUND ...]
"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from bot import config, engine
from bot.config import Slice, Strategy
from bot.data import load_snapshot


def measured_cost(cfg: config.Config, px, fund: str, start=None, end=None) -> float:
    model = f"{fund}~model"
    inst = cfg.instruments[fund]
    probe = Strategy(id="probe", name="probe", tax_rate=0.0,
                     slices=(Slice(0.5, fund, "hold"), Slice(0.5, model, "hold")))
    cfg = replace(cfg, instruments=cfg.instruments | {model: replace(inst, id=model, cost=0.0)},
                  strategies={"probe": probe})
    market = engine.build_market(cfg, px)
    listed = px[f"{fund}.close"].first_valid_index()
    d = market.dates
    sel = (d > (start or listed + np.timedelta64(30, "D"))) & (d < (end or d[-1]))
    real, zero = market.close_r[fund][sel], market.close_r[model][sel]
    target = np.log1p(real).sum()
    lo, hi = -0.2, 0.2
    for _ in range(60):
        c = (lo + hi) / 2
        lo, hi = (c, hi) if np.log1p(zero - c / 252).sum() > target else (lo, c)
    return (lo + hi) / 2


if __name__ == "__main__":
    cfg_path, snapshots, *funds = sys.argv[1:]
    cfg = config.load(Path(cfg_path))
    px = load_snapshot(*(Path(p) for p in snapshots.split(",")))
    for f in funds:
        print(f"{f}: cost = {measured_cost(cfg, px, f):.4f}  (config has {cfg.instruments[f].cost})")
