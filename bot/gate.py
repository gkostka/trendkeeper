"""Milestone 1 gate: the pass marks in docs/01, run against one strategy and its neighbours."""
import sys
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path

from bot import config, engine
from bot.data import load_snapshot

FULL = ("1994-01-01", "2026-10-01")
PERIODS = [("1994-01-01", "2007-01-01"), ("2007-01-01", "2016-04-01"), ("2016-04-01", "2026-10-01")]
NEIGHBOUR_WEIGHTS = [0.20, 0.25, 0.30, 0.35, 0.40]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def risk_adjusted(values, span):
    s = engine.stats(values, *span)
    return s["cagr"] / -s["max_dd"]


def neighbours(strategy):
    trend = [k for k, sl in enumerate(strategy.slices) if sl.rule == "trend"]
    hold = [k for k, sl in enumerate(strategy.slices) if sl.rule == "hold"]
    hold_total = sum(strategy.slices[k].weight for k in hold)
    for ws in product(NEIGHBOUR_WEIGHTS, repeat=len(trend)):
        rest = 1 - sum(ws)
        if rest < 0 or (rest > 1e-9 and not hold):
            continue
        weights = dict(zip(trend, ws)) | {k: rest * strategy.slices[k].weight / hold_total for k in hold}
        yield replace(strategy, slices=tuple(replace(sl, weight=weights[k]) for k, sl in enumerate(strategy.slices)))


def run(cfg, market, strategy_id, benchmark_id, execution) -> list[Check]:
    def values(s):
        return engine.backtest(s, market, execution, cfg.trade_cost)[0]

    strategy, bench = cfg.strategies[strategy_id], values(cfg.strategies[benchmark_id])
    v = values(strategy)
    s, b = engine.stats(v, *FULL), engine.stats(bench, *FULL)
    bench_periods = [risk_adjusted(bench, p) for p in PERIODS]

    def beats_in_periods(vals):
        return all(risk_adjusted(vals, p) > bp for p, bp in zip(PERIODS, bench_periods))

    near = [n for n in neighbours(strategy)]
    near_ok = sum(beats_in_periods(values(n)) for n in near)
    return [
        Check("Return over the full period", s["cagr"] >= b["cagr"] + 0.01,
              f"{s['cagr']:.2%} against {b['cagr']:.2%} for {benchmark_id}"),
        Check("Worst drop", s["max_dd"] >= -0.40, f"{s['max_dd']:.1%}"),
        Check("Each period", beats_in_periods(v),
              ", ".join(f"{risk_adjusted(v, p):.2f} vs {bp:.2f}" for p, bp in zip(PERIODS, bench_periods))),
        Check("The neighbourhood", near_ok == len(near), f"{near_ok} of {len(near)} pass"),
    ]


def main(argv):
    cfg_path, snapshot, strategy_id, benchmark_id, execution = argv
    cfg = config.load(Path(cfg_path))
    checks = run(cfg, engine.build_market(cfg, load_snapshot(Path(snapshot))), strategy_id, benchmark_id, execution)
    for c in checks:
        print(f"{'PASS' if c.passed else 'FAIL'}  {c.name}: {c.detail}")
    passed = all(c.passed for c in checks)
    print("Gate:", "PASSED" if passed else "FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["tests/research.toml", "tests/data/prices.csv.gz", "mix_30_30_40", "spy", "next_open"]))
