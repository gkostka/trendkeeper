from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from bot.config import RATES, Config, Instrument, Strategy


@dataclass(frozen=True)
class Market:
    """Everything the engine reads, as arrays aligned on `dates`; row i uses prices up to dates[i] only."""

    dates: pd.DatetimeIndex
    close_r: dict[str, np.ndarray]
    open_r: dict[str, np.ndarray]
    cash: np.ndarray
    above: dict[tuple[str, tuple[int, ...]], np.ndarray]

    def pos(self, day) -> int:
        return self.dates.get_loc(pd.Timestamp(day))


@dataclass(frozen=True)
class SliceState:
    fund: float
    cash: float
    held: float
    pending: float | None = None

    @property
    def value(self) -> float:
        return self.fund + self.cash


@dataclass(frozen=True)
class State:
    day: pd.Timestamp
    slices: tuple[SliceState, ...]

    @property
    def value(self) -> float:
        return sum(s.value for s in self.slices)


@dataclass(frozen=True)
class Trade:
    day: pd.Timestamp
    fund: str
    amount: float
    at: str
    reason: str


def build_market(cfg: Config, px: pd.DataFrame, start="1992-01-01") -> Market:
    close = px.filter(like=".close").rename(columns=lambda c: c[: -len(".close")]).ffill()
    open_ = px.filter(like=".open").rename(columns=lambda c: c[: -len(".open")])
    keep = close.index >= start
    close, open_ = close[keep], open_.reindex(close.index[keep])
    rates = {name: (close[col] / 100 / 252).shift(1).fillna(0) for name, col in RATES.items()}

    returns: dict[str, tuple[pd.Series, pd.Series]] = {}

    def own(name):
        c = close[name]
        prev = c.shift(1)
        r = (c / prev - 1).where(prev.notna())
        # An open equal to the close means Yahoo has no open that day. Treating it as a trade at
        # the close is the cautious choice: it can only make next_open look worse, never better.
        o = open_[name] / prev - 1 if name in open_ else r
        o = o.where(open_.get(name, c).notna() & (open_.get(name, c) != c), r)
        return r, o

    def series(name) -> tuple[pd.Series, pd.Series]:
        if name in returns:
            return returns[name]
        inst = cfg.instruments.get(name, Instrument(id=name))
        r, o = own(name) if name in close else (pd.Series(np.nan, close.index), pd.Series(np.nan, close.index))
        if inst.backfill:
            # Index opens before the fund listed only repeat the previous close, so use none of them.
            br = series(inst.backfill)[0]
            r, o = r.where(r.notna(), br), o.where(r.notna(), br)
        if inst.tracks:
            ur, uo = series(inst.tracks)
            fin = rates[inst.financing]
            sr = inst.leverage * ur - (inst.leverage - 1) * fin - inst.cost / 252
            so = inst.leverage * uo
            r, o = r.where(r.notna(), sr), o.where(r.notna(), so)
        returns[name] = (r, o)
        return r, o

    above = {}
    for s in cfg.strategies.values():
        for sl in s.slices:
            if sl.rule == "trend":
                lv = (1 + series(sl.signal)[0]).cumprod()
                above[(sl.signal, sl.windows)] = (
                    sum((lv > lv.rolling(w).mean()).astype(float) for w in sl.windows) / len(sl.windows)
                ).to_numpy()
    funds = {sl.fund for s in cfg.strategies.values() for sl in s.slices}
    return Market(
        dates=close.index,
        close_r={f: series(f)[0].fillna(0).to_numpy() for f in funds},
        open_r={f: series(f)[1].fillna(0).to_numpy() for f in funds},
        cash=rates[cfg.cash_rate].to_numpy(),
        above=above,
    )


def start_state(strategy: Strategy, market: Market, day, value=1.0) -> State:
    slices = tuple(
        SliceState(fund=sl.weight * value if sl.rule == "hold" else 0.0,
                   cash=0.0 if sl.rule == "hold" else sl.weight * value,
                   held=1.0 if sl.rule == "hold" else 0.0)
        for sl in strategy.slices)
    return State(day=pd.Timestamp(day), slices=slices)


def _trade_to(s: SliceState, frac: float, cost: float) -> tuple[SliceState, float]:
    amount = frac * s.value - s.fund
    value = s.value - abs(amount) * cost
    return replace(s, fund=frac * value, cash=(1 - frac) * value, held=frac, pending=None), amount


def step(strategy: Strategy, state: State, market: Market, day, execution: str, cost: float):
    """The strategy's state and trades after the close of `day`, from yesterday's state and data up to `day` only."""
    i = market.pos(day)
    day = market.dates[i]
    trades: list[Trade] = []
    slices = list(state.slices)

    if strategy.rebalance == "monthly" and day.month != state.day.month:
        total = state.value
        for k, (sl, s) in enumerate(zip(strategy.slices, slices)):
            target = sl.weight * total
            amount = s.held * target - s.fund
            if abs(amount) > 1e-12:
                trades.append(Trade(state.day, sl.fund, amount, "close", "rebalance"))
            value = target - abs(amount) * cost
            slices[k] = replace(s, fund=s.held * value, cash=(1 - s.held) * value)

    for k, (sl, s) in enumerate(zip(strategy.slices, slices)):
        r, o, c = market.close_r[sl.fund][i], market.open_r[sl.fund][i], market.cash[i]
        if execution == "next_open" and s.pending is not None:
            s = replace(s, fund=s.fund * (1 + o))
            s, amount = _trade_to(s, s.pending, cost)
            trades.append(Trade(day, sl.fund, amount, "open", "signal"))
            s = replace(s, fund=s.fund * (1 + r) / (1 + o), cash=s.cash * (1 + c))
        else:
            s = replace(s, fund=s.fund * (1 + r), cash=s.cash * (1 + c))
            if execution == "next_close" and s.pending is not None:
                s, amount = _trade_to(s, s.pending, cost)
                trades.append(Trade(day, sl.fund, amount, "close", "signal"))

        if sl.rule == "trend":
            frac = market.above[(sl.signal, sl.windows)][i]
            if frac != (s.held if s.pending is None else s.pending):
                if execution == "same_close":
                    s, amount = _trade_to(s, frac, cost)
                    trades.append(Trade(day, sl.fund, amount, "close", "signal"))
                else:
                    s = replace(s, pending=frac)
        slices[k] = s

    return State(day=day, slices=tuple(slices)), trades


def backtest(strategy: Strategy, market: Market, execution: str, cost: float, start=None, end=None):
    dates = market.dates
    dates = dates[(dates >= (start or dates[0])) & (dates < (end or dates[-1] + pd.Timedelta(days=1)))]
    state = start_state(strategy, market, dates[0])
    values, trades = [state.value], []
    for day in dates[1:]:
        state, t = step(strategy, state, market, day, execution, cost)
        values.append(state.value)
        trades += t
    return pd.Series(values, index=dates, name=strategy.id), trades


def stats(values: pd.Series, start, end) -> dict:
    """Annual return and worst drop over [start, end), from the close before `start`, 252 days a year."""
    before = values[values.index < start]
    v = values[(values.index >= start) & (values.index < end)]
    eq = v / (before.iloc[-1] if len(before) else v.iloc[0])
    return {"cagr": eq.iloc[-1] ** (252 / len(eq)) - 1, "max_dd": (eq / eq.cummax() - 1).min()}
