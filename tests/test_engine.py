from pathlib import Path

import pandas as pd
import pytest

from bot import config, engine
from bot.data import load_snapshot
from tests import reference as ref

HERE = Path(__file__).parent
START, END = "1994-01-01", "2026-10-01"


@pytest.fixture(scope="module")
def px():
    return load_snapshot(HERE / "data" / "prices.csv.gz")


@pytest.fixture(scope="module")
def cfg():
    return config.load(HERE / "research.toml")


@pytest.fixture(scope="module")
def market(cfg, px):
    return engine.build_market(cfg, px)


def run(cfg, market, sid, execution="same_close", **rules):
    r = engine.Rules.from_config(cfg, execution=execution, **rules)
    values, trades, _ = engine.backtest(cfg.strategies[sid], market, r)
    return engine.stats(values, START, END), values, trades


def test_reference_matches_the_research_docs(px):
    r, drag, d = ref.mix_30_30_40(px)
    mix, spy, qqq = ref.stats(r), ref.stats(d["underlying"]["SPY"]), ref.stats(d["underlying"]["QQQ"])
    assert round(mix["cagr"], 3) == 0.134 and round(mix["max_dd"], 2) == -0.30
    assert round(spy["cagr"], 3) == 0.109 and round(spy["max_dd"], 2) == -0.55
    assert round(qqq["cagr"], 3) == 0.147 and round(qqq["max_dd"], 2) == -0.83


def test_fund_costs_in_config_match_the_measured_drag(px, cfg):
    _, drag, _ = ref.mix_30_30_40(px)
    assert cfg.instruments["2xSPY"].cost == pytest.approx(drag["SSO"], abs=5e-4)
    assert cfg.instruments["2xQQQ"].cost == pytest.approx(drag["QLD"], abs=5e-4)


def test_engine_reproduces_the_reference(px, cfg, market):
    # The engine lets positions drift between trades and charges rebalance trades, where the research
    # reset each slice every day for free; the gap this leaves must stay small.
    r, _, _ = ref.mix_30_30_40(px)
    want = ref.stats(r)
    got, _, _ = run(cfg, market, "mix_30_30_40")
    assert got["cagr"] == pytest.approx(want["cagr"], abs=0.001)
    assert got["max_dd"] == pytest.approx(want["max_dd"], abs=0.005)


def test_buy_and_hold_is_the_fund_itself(px, cfg, market):
    _, values, trades = run(cfg, market, "spy")
    spy = px["SPY.close"].dropna()
    days = values.index[values.index >= spy.index[0]]
    growth = values[days] / values[days[0]]
    assert not trades
    # The last value is after selling, so it is net of one trade cost.
    assert growth.iloc[-1] == pytest.approx(spy[days[-1]] / spy[days[0]] * (1 - cfg.trade_cost), rel=1e-9)


def state_at(cfg, market, execution, cut):
    strategy = cfg.strategies["mix_30_30_40"]
    rules = engine.Rules.from_config(cfg, execution=execution)
    state = engine.start_state(strategy, market, market.dates[0], 1.0, rules)
    for day in market.dates[1:][market.dates[1:] <= cut]:
        state, _ = engine.step(strategy, state, market, day, rules)
    return state


@pytest.mark.parametrize("execution", ["same_close", "next_open", "next_close"])
def test_no_look_ahead(cfg, px, execution):
    # The whole state, pending orders included: a next-day order decided with tomorrow's data
    # would not show in the portfolio value until after the cut.
    cut = pd.Timestamp("2015-12-31")
    full = state_at(cfg, engine.build_market(cfg, px), execution, cut)
    part = state_at(cfg, engine.build_market(cfg, px[px.index <= cut]), execution, cut)
    assert full == part


def test_trades_follow_execution_timing(cfg, market):
    for execution, at in [("same_close", "close"), ("next_close", "close"), ("next_open", "open")]:
        _, _, trades = run(cfg, market, "mix_30_30_40", execution)
        signal = [t for t in trades if t.reason == "signal"]
        assert signal and all(t.at == at for t in signal)


def test_next_day_trades_one_day_after_the_signal(cfg, market):
    _, _, same = run(cfg, market, "mix_30_30_40", "same_close")
    _, _, nxt = run(cfg, market, "mix_30_30_40", "next_open")
    first_same = next(t.day for t in same if t.reason == "signal")
    first_next = next(t.day for t in nxt if t.reason == "signal")
    assert market.pos(first_next) == market.pos(first_same) + 1


def test_config_rejects_bad_strategies():
    base = (HERE / "research.toml").read_text()
    with pytest.raises(config.ConfigError, match="tax_rate"):
        config.loads(base.replace('tax_rate = 0.0\n\n  [[strategy.slice]]\n  weight = 1.0\n  fund = "SPY"',
                                 '\n  [[strategy.slice]]\n  weight = 1.0\n  fund = "SPY"'))
    with pytest.raises(config.ConfigError, match="add up to 1"):
        config.loads(base.replace("weight = 0.40", "weight = 0.50"))
    with pytest.raises(config.ConfigError, match="not an instrument"):
        config.loads(base.replace('fund = "VFITX"', 'fund = "IEF"'))
    with pytest.raises(config.ConfigError, match="execution"):
        config.loads(base.replace('execution = "same_close"', 'execution = "tomorrow"'))
    with pytest.raises(config.ConfigError, match="unknown settings"):
        config.loads(base.replace("trade_cost =", "trade_costs ="))
    with pytest.raises(config.ConfigError, match="follow"):
        config.loads('follow = "mix_30_30"\n' + base)
    with pytest.raises(config.ConfigError, match="used twice"):
        config.loads(base + base[base.index("[[strategy]]"):])
    with pytest.raises(config.ConfigError, match="instrument SPY"):
        config.loads(base.replace("[instrument.SPY]\n", "[instrument.SPY]\nlevrage = 2\n"))
