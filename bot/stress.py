"""Stress test: how a strategy holds up against variants of itself, tax, and a one-day crash. Recorded, not a gate.

    python -m bot.stress CONFIG SNAPSHOT[,SNAPSHOT] STRATEGY BENCHMARK [START]
"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from bot import config, engine
from bot.data import load_snapshot
from bot.gate import data_end

CRASH = -0.20  # SPY's 19 Oct 1987, the worst day since 1950


def always_invested(strategy):
    """The same mix with every trend slice held all the time: what the trend filter adds."""
    return replace(strategy, id=f"{strategy.id}:always", slices=tuple(
        replace(sl, rule="hold", signal=None, windows=(), buffer=0.0, vol_window=0) for sl in strategy.slices))


def holds_as_cash(market, strategy):
    """The market with every held fund earning the cash rate: the strategy without its bond rally."""
    held = {sl.fund for sl in strategy.slices if sl.rule == "hold"}
    m = replace(market, close_r=dict(market.close_r), open_r=dict(market.open_r), price=dict(market.price),
                scale=dict(market.scale), _above={})
    for f in held:
        m.close_r[f], m.open_r[f] = market.cash.copy(), np.zeros_like(market.cash)
        m.price[f], m.scale[f] = market.price[f][0] * np.cumprod(1 + market.cash), np.ones_like(market.cash)
    return m


def crash_day(cfg, strategy) -> float:
    """The portfolio's loss on a day both indexes fall by CRASH while every trend slice is fully invested."""
    return sum(sl.weight * cfg.instruments[sl.fund].leverage * CRASH for sl in strategy.slices if sl.rule == "trend")


def longest_underwater(values: pd.Series) -> float:
    """The longest time, in years, from a peak until the value is back above it (or the data ends)."""
    peaks = values.index[values >= values.cummax()].append(values.index[-1:])
    return float(peaks.to_series().diff().max().days / 365.25)


def measure(values: pd.Series, bench: pd.Series, span) -> dict:
    s = engine.stats(values, *span)
    yearly, bench_yearly = (v.resample("YE").last().pct_change().dropna() for v in (values, bench))
    five, bench_five = ((v / v.shift(252 * 5)) ** (1 / 5) - 1 for v in (values, bench))
    ok = five.notna() & bench_five.notna()
    return {"cagr": s["cagr"], "max_dd": s["max_dd"], "underwater": longest_underwater(values),
            "beat": int((yearly > bench_yearly).sum()), "years": len(yearly),
            "worst_year": float(yearly.min()), "worst_year_at": yearly.idxmin().year,
            "five_min": float(five[ok].min()), "five_trailing": float((five[ok] < bench_five[ok]).mean())}


def run(cfg, market, strategy_id, benchmark_id, rules, start="1994-01-01") -> list[tuple[str, dict]]:
    span = (start, data_end(market))
    strategy, benchmark = cfg.strategies[strategy_id], cfg.strategies[benchmark_id]

    def values(s, m=market, tax=0.0):
        return engine.backtest(replace(s, tax_rate=tax), m, rules, start=start, value=cfg.start_value)[0]

    bench = values(benchmark)
    rows = [(benchmark.name, measure(bench, bench, span)),
            (strategy.name, measure(values(strategy), bench, span))]
    for rate in sorted({strategy.tax_rate, 0.2, 0.3} - {0.0}):
        # The benchmark pays the same rate, but only once, when it is sold at the end.
        rows.append((f"after {rate:.0%} tax", measure(values(strategy, tax=rate), values(benchmark, tax=rate), span)))
    rows.append(("always invested", measure(values(always_invested(strategy)), bench, span)))
    rows.append(("held funds as cash", measure(values(strategy, holds_as_cash(market, strategy)), bench, span)))
    return rows


def main(argv):
    cfg_path, snapshots, strategy_id, benchmark_id, *rest = argv
    start = rest[0] if rest else "1994-01-01"
    cfg = config.load(Path(cfg_path))
    market = engine.build_market(cfg, load_snapshot(*(Path(p) for p in snapshots.split(","))))
    rules = engine.Rules.from_config(cfg)
    print(f"{'':30} {'return':>7} {'worst':>7} {'under':>6} {'beat':>6} {'worst year':>15} {'5y min':>7} {'5y behind':>9}")
    for name, r in run(cfg, market, strategy_id, benchmark_id, rules, start):
        print(f"{name[:30]:30} {r['cagr']:7.2%} {r['max_dd']:7.1%} {r['underwater']:5.1f}y {r['beat']:>2}/{r['years']:<3} "
              f"{r['worst_year']:+7.1%} ({r['worst_year_at']}) {r['five_min']:+7.1%} {r['five_trailing']:9.0%}")
    print(f"\nA {CRASH:.0%} day in both indexes while fully invested: {crash_day(cfg, cfg.strategies[strategy_id]):+.0%} "
          "in one day, before any signal can act.")
    print("under: longest time below a previous peak. beat: calendar years ahead of the benchmark. "
          "5y behind: share of 5-year spans behind it.")


if __name__ == "__main__":
    main(sys.argv[1:])
