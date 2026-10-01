"""Milestone 1 gate: the pass marks in docs/01, run against one strategy and its neighbours.

    python -m bot.gate CONFIG SNAPSHOT[,SNAPSHOT] STRATEGY BENCHMARK EXECUTION [START]
"""
import sys
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path

from bot import config, engine
from bot.data import load_snapshot

END = "2026-10-01"
PERIOD_STARTS = ["1994-01-01", "2007-01-01", "2016-04-01"]
NEIGHBOUR_WEIGHTS = [0.20, 0.25, 0.30, 0.35, 0.40]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def spans(start: str):
    """The full span and the three periods; a later start shortens the first period."""
    starts = [max(start, PERIOD_STARTS[0])] + PERIOD_STARTS[1:]
    return (starts[0], END), list(zip(starts, starts[1:] + [END]))


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


def _values(cfg, market, strategy, rules, full):
    return engine.backtest(strategy, market, rules, start=full[0], value=cfg.start_value)[0]


def run(cfg, market, strategy_id, benchmark_id, rules: engine.Rules, start="1994-01-01") -> list[Check]:
    full, periods = spans(start)
    strategy = cfg.strategies[strategy_id]
    v, bench = (_values(cfg, market, s, rules, full) for s in (strategy, cfg.strategies[benchmark_id]))
    s, b = engine.stats(v, *full), engine.stats(bench, *full)
    bench_periods = [risk_adjusted(bench, p) for p in periods]

    def beats_in_periods(vals):
        return all(risk_adjusted(vals, p) > bp for p, bp in zip(periods, bench_periods))

    near = list(neighbours(strategy))
    near_ok = sum(beats_in_periods(_values(cfg, market, n, rules, full)) for n in near)
    return [
        Check("Return over the full period", s["cagr"] >= b["cagr"] + 0.01,
              f"{s['cagr']:.2%} against {b['cagr']:.2%} for {benchmark_id}, {full[0][:4]}-{full[1][:4]}"),
        Check("Worst drop", s["max_dd"] >= -0.40, f"{s['max_dd']:.1%}"),
        Check("Each period", beats_in_periods(v),
              ", ".join(f"{a[:4]}-{z[:4]} {risk_adjusted(v, (a, z)):.2f} vs {bp:.2f}"
                        for (a, z), bp in zip(periods, bench_periods))),
        Check("The neighbourhood", near_ok == len(near), f"{near_ok} of {len(near)} pass"),
    ]


def records(cfg, market, strategy_id, benchmark_id, rules, start="1994-01-01") -> list[str]:
    """The buffer and tax results the gate records alongside its pass marks."""
    full, periods = spans(start)
    strategy = cfg.strategies[strategy_id]
    out = []
    for b in (0.0, 0.01, 0.02):
        s = replace(strategy, slices=tuple(replace(sl, buffer=b) if sl.rule == "trend" else sl for sl in strategy.slices))
        v = _values(cfg, market, s, rules, full)
        out.append(f"buffer {b:.0%}: " + ", ".join(f"{risk_adjusted(v, p):.2f}" for p in periods)
                   + f" return/worst drop by period; {engine.stats(v, *full)['cagr']:.2%} a year")
    for rate in (0.0, 0.2, 0.3):
        v, b = (_values(cfg, market, replace(s, tax_rate=rate), rules, full)
                for s in (strategy, cfg.strategies[benchmark_id]))
        out.append(f"tax {rate:.0%}: {engine.stats(v, *full)['cagr']:.2%} a year after tax, "
                   f"{benchmark_id} {engine.stats(b, *full)['cagr']:.2%} (sold at the end, taxed once)")
    return out


def main(argv):
    cfg_path, snapshots, strategy_id, benchmark_id, execution, *rest = argv
    start = rest[0] if rest else "1994-01-01"
    cfg = config.load(Path(cfg_path))
    market = engine.build_market(cfg, load_snapshot(*(Path(p) for p in snapshots.split(","))))
    rules = engine.Rules.from_config(cfg, execution=execution)
    checks = run(cfg, market, strategy_id, benchmark_id, rules, start)
    for c in checks:
        print(f"{'PASS' if c.passed else 'FAIL'}  {c.name}: {c.detail}")
    passed = all(c.passed for c in checks)
    print("Gate:", "PASSED" if passed else "FAILED")
    print("\nRecorded, not deciding:")
    for line in records(cfg, market, strategy_id, benchmark_id, rules, start):
        print(" ", line)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["tests/research.toml", "tests/data/prices.csv.gz", "mix_30_30_40", "spy", "next_open"]))
