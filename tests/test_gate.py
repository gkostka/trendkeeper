from pathlib import Path

import pytest

from bot import config, engine, gate
from bot.data import load_snapshot

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def cfg():
    return config.load(HERE / "research.toml")


def test_neighbours_span_the_grid_and_keep_weights_whole(cfg):
    near = list(gate.neighbours(cfg.strategies["mix_30_30_40"]))
    assert len(near) == 25
    assert all(abs(sum(sl.weight for sl in n.slices) - 1) < 1e-9 for n in near)
    assert {(n.slices[0].weight, n.slices[1].weight) for n in near} >= {(0.2, 0.2), (0.4, 0.4), (0.3, 0.3)}


def test_research_setup_passes_with_next_open(cfg):
    market = engine.build_market(cfg, load_snapshot(HERE / "data" / "prices.csv.gz"))
    checks = gate.run(cfg, market, "mix_30_30_40", "spy", engine.Rules.from_config(cfg, execution="next_open"))
    assert [c.passed for c in checks] == [True] * 4, checks


def test_the_real_config_passes_the_gate():
    # Milestone 1 closed on this result. Filling in the trade cost, tax rate and start size
    # (milestone 3's entry condition) re-runs it here; a failure means don't trade.
    real = config.load(HERE.parent / "bot" / "config.toml")
    px = load_snapshot(HERE / "data" / "prices.csv.gz", HERE / "data" / "eur.csv.gz")
    market = engine.build_market(real, px)
    checks = gate.run(real, market, real.follow, "spy", engine.Rules.from_config(real), "1999-01-04")
    assert [c.passed for c in checks] == [True] * 4, checks
