from pathlib import Path

import pandas as pd
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
    checks = gate.run(real, market, real.follow[0], "spy", engine.Rules.from_config(real), "1999-01-04")
    assert [c.passed for c in checks] == [True] * 4, checks


def test_stress_shows_what_the_trend_filter_and_bonds_add():
    from bot import stress
    real = config.load(HERE.parent / "bot" / "config.toml")
    px = load_snapshot(HERE / "data" / "prices.csv.gz", HERE / "data" / "eur.csv.gz")
    market = engine.build_market(real, px)
    rows = dict(stress.run(real, market, real.follow[0], "spy", engine.Rules.from_config(real), "1999-01-04"))
    strategy = rows[real.strategies[real.follow[0]].name]
    assert rows["always invested"]["max_dd"] < strategy["max_dd"] - 0.3
    assert rows["held funds as cash"]["cagr"] < strategy["cagr"]
    assert rows["after 20% tax"]["cagr"] < strategy["cagr"]
    assert stress.crash_day(real, real.strategies[real.follow[0]]) == pytest.approx(-0.24)
    assert stress.longest_underwater(pd.Series([1.0, 0.5, 0.9, 1.1], pd.to_datetime(
        ["2000-01-01", "2001-01-01", "2002-01-01", "2003-01-01"]))) == pytest.approx(3 * 365 / 365.25, abs=0.01)
