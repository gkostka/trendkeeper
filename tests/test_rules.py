from dataclasses import replace

import pandas as pd
from pathlib import Path

import pytest

from bot import config, engine
from bot.data import load_snapshot
from bot.engine import Lot, Rules

HERE = Path(__file__).parent

# A strategy on funds with real prices, so whole shares can be bought.
PRICED = """
[instrument.SSO]
tracks = "SPY"
leverage = 2
cost = 0.0182

[[strategy]]
id = "sso_mix"
name = "60% SSO trend, 40% SPY"
rebalance = "monthly"
tax_rate = 0.0

  [[strategy.slice]]
  weight = 0.60
  fund = "SSO"
  rule = "trend"
  signal = "SPY"
  windows = [200, 250, 300]

  [[strategy.slice]]
  weight = 0.40
  fund = "SPY"
  rule = "hold"
"""


@pytest.fixture(scope="module")
def cfg():
    return config.load((HERE / "research.toml").read_text() + PRICED)


@pytest.fixture(scope="module")
def market(cfg):
    return engine.build_market(cfg, load_snapshot(HERE / "data" / "prices.csv.gz"))


def run(cfg, market, sid, start="2007-01-01", value=20_000.0, **rules):
    return engine.backtest(cfg.strategies[sid], market, Rules.from_config(cfg, **rules), start=start, value=value)


def test_tax_offsets_losses_carried_forward():
    assert engine._tax(100.0, 0.0, 0.25) == (25.0, 0.0)
    assert engine._tax(-40.0, 0.0, 0.25) == (0.0, 40.0)
    assert engine._tax(100.0, 40.0, 0.25) == (15.0, 0.0)
    assert engine._tax(30.0, 40.0, 0.25) == (0.0, 10.0)


def test_lots_sell_first_in_first_out():
    lots, basis = engine._sell_lots((Lot(10, 100.0), Lot(10, 300.0)), 15)
    assert basis == pytest.approx(100 + 150)
    assert lots == (Lot(5, 150.0),)


def test_cash_interest_follows_ibkr_terms():
    r = Rules(cash_spread=0.005, cash_free=10_000, cash_full_rate_nav=100_000)
    bench = 0.04 / 252
    assert engine._cash_rate(bench, 5_000, 200_000, r) == 0.0
    full = engine._cash_rate(bench, 20_000, 200_000, r)
    assert full == pytest.approx((0.04 - 0.005) / 252 * 0.5)
    assert engine._cash_rate(bench, 20_000, 50_000, r) == pytest.approx(full * 0.5)


def test_whole_shares_buy_only_whole_shares(cfg, market):
    values, trades, state = run(cfg, market, "sso_mix", whole_shares=True)
    assert trades and all(lot.shares == int(lot.shares) for s in state.slices for lot in s.lots)
    fractional = run(cfg, market, "sso_mix")[0]
    assert values.iloc[-1] == pytest.approx(fractional.iloc[-1], rel=0.01)


def test_whole_shares_need_real_prices(cfg, market):
    with pytest.raises(ValueError, match="real prices"):
        run(cfg, market, "mix_30_30_40", whole_shares=True)


def test_min_trade_skips_small_rebalances(cfg, market):
    values, trades, _ = run(cfg, market, "sso_mix", min_trade=0.02)
    rebalances = [t for t in trades if t.reason == "rebalance"]
    assert rebalances and all(abs(t.amount) >= 0.02 * values[t.day] * 0.999 for t in rebalances)
    all_small = [t for t in run(cfg, market, "sso_mix")[1] if t.reason == "rebalance"]
    assert len(rebalances) < len(all_small)


def test_buy_and_hold_pays_tax_on_the_gain_when_valued_at_the_end(cfg, market):
    spy = replace(cfg.strategies["spy"], tax_rate=0.25)
    values, _, state = engine.backtest(spy, market, Rules.from_config(cfg), start="2007-01-01", value=20_000.0)
    assert values.iloc[-1] == pytest.approx(state.value - 0.25 * (state.value - 20_000.0))


def test_trading_strategy_pays_tax_as_it_goes(cfg, market):
    taxed = replace(cfg.strategies["mix_30_30_40"], tax_rate=0.25)
    rules = Rules.from_config(cfg)
    v0 = engine.backtest(cfg.strategies["mix_30_30_40"], market, rules)[0]
    v1, trades, state = engine.backtest(taxed, market, rules)
    assert state.tax_paid > 0 and any(t.tax > 0 for t in trades)
    assert v1.iloc[-1] < v0.iloc[-1]


def test_buffer_cuts_quick_reversals(cfg):
    buffered = (HERE / "research.toml").read_text().replace(
        "windows = [200, 250, 300]\n", "windows = [200, 250, 300]\n  buffer = 0.02\n")
    px = load_snapshot(HERE / "data" / "prices.csv.gz")
    signal_trades = []
    for c in (cfg, config.load(buffered)):
        m = engine.build_market(c, px)
        _, trades, _ = engine.backtest(c.strategies["mix_30_30_40"], m, Rules.from_config(c))
        signal_trades.append(sum(t.reason == "signal" for t in trades))
    assert signal_trades[1] < signal_trades[0] * 0.8


@pytest.fixture(scope="module")
def eur():
    from bot.config import load
    cfg = load(HERE.parent / "bot" / "config.toml")
    px = load_snapshot(HERE / "data" / "prices.csv.gz", HERE / "data" / "eur.csv.gz")
    return cfg, px, engine.build_market(cfg, px)


def test_usd_funds_are_valued_in_euros(eur):
    cfg, px, market = eur
    d = market.dates
    sel = (d > "1999-01-04") & (d <= "2026-09-29")
    growth = (1 + market.close_r["SPY"][sel]).prod()
    spy, fx = px["SPY.close"].ffill(), px["EURUSD.close"].ffill()
    a, b = d[sel][0] - pd.Timedelta(days=1), d[sel][-1]
    want = (spy.asof(b) / fx.asof(b)) / (spy.asof(d[d <= a][-1]) / fx.asof(d[d <= a][-1]))
    assert growth == pytest.approx(want, rel=1e-9)


def test_splits_and_bad_prints_are_repaired_and_reported(eur):
    _, _, market = eur
    assert pd.Timestamp("2015-01-02") in market.repaired["LQQ.PA"]
    assert abs(market.close_r["LQQ.PA"]).max() < 0.5 and abs(market.close_r["DBPG.DE"]).max() < 0.5


def test_calibrated_cost_makes_the_model_grow_like_the_fund():
    from bot.calibrate import measured_cost
    extra = '\n[instrument.SSO]\ntracks = "SPY"\nleverage = 2\n'
    cfg = config.load((HERE / "research.toml").read_text() + extra)
    px = load_snapshot(HERE / "data" / "prices.csv.gz")
    cost = measured_cost(cfg, px, "SSO")
    assert cost == pytest.approx(0.0156, abs=5e-4)
