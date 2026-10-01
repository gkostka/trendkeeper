import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from bot.config import RATES, Config, Instrument, Strategy


@dataclass(frozen=True)
class Market:
    """Everything the engine reads, as arrays aligned on `dates`; row i uses prices up to dates[i] only."""

    dates: pd.DatetimeIndex
    close_r: dict[str, np.ndarray]
    open_r: dict[str, np.ndarray]
    price: dict[str, np.ndarray]
    priced: frozenset[str]
    cash: np.ndarray
    levels: dict[str, pd.Series]
    _above: dict = field(default_factory=dict, repr=False, compare=False)

    def pos(self, day) -> int:
        return self.dates.get_loc(pd.Timestamp(day))

    def above(self, signal: str, windows: tuple[int, ...], buffer: float) -> np.ndarray:
        """Share of `windows` averages the signal closes above, each day; computed once, causal by construction."""
        key = (signal, windows, buffer)
        if key not in self._above:
            lv = self.levels[signal]
            self._above[key] = (sum(_above(lv, w, buffer) for w in windows) / len(windows)).to_numpy()
        return self._above[key]


@dataclass(frozen=True)
class Rules:
    execution: str = "same_close"
    cost: float = 0.0005
    min_trade: float = 0.0
    whole_shares: bool = False
    cash_spread: float = 0.0
    cash_free: float = 0.0
    cash_full_rate_nav: float = 0.0

    @classmethod
    def from_config(cls, cfg: Config, **overrides) -> "Rules":
        cash = cfg.instruments[cfg.cash]
        return replace(cls(execution=cfg.execution, cost=cfg.trade_cost, min_trade=cfg.min_trade,
                           whole_shares=cfg.whole_shares, cash_spread=cash.spread, cash_free=cash.free,
                           cash_full_rate_nav=cash.full_rate_nav), **overrides)


@dataclass(frozen=True)
class Lot:
    shares: float
    cost: float


@dataclass(frozen=True)
class SliceState:
    fund: float
    cash: float
    held: float
    lots: tuple[Lot, ...] = ()
    pending: float | None = None

    @property
    def value(self) -> float:
        return self.fund + self.cash

    @property
    def shares(self) -> float:
        return sum(lot.shares for lot in self.lots)


@dataclass(frozen=True)
class State:
    day: pd.Timestamp
    slices: tuple[SliceState, ...]
    loss_carry: float = 0.0
    tax_paid: float = 0.0

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
    tax: float = 0.0


def _above(lv: pd.Series, window: int, buffer: float) -> pd.Series:
    ma = lv.rolling(window).mean()
    if not buffer:
        return (lv > ma).astype(float)
    # Enter above the average, leave only once below it by `buffer`: in between, keep yesterday's call.
    s = pd.Series(np.where(lv > ma, 1.0, np.where(lv < ma * (1 - buffer), 0.0, np.nan)), index=lv.index)
    return s.where(ma.notna(), 0.0).ffill().fillna(0.0)


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

    signals = {sl.signal for s in cfg.strategies.values() for sl in s.slices if sl.rule == "trend"}
    levels = {name: (1 + series(name)[0]).cumprod() for name in signals}

    funds = {sl.fund for s in cfg.strategies.values() for sl in s.slices}
    close_r = {f: series(f)[0].fillna(0) for f in funds}
    price = {}
    for f in funds:
        index = (1 + close_r[f]).cumprod()
        if f in close:
            # Anchored at the listing price, not today's: from listing on, shares cost what they really did,
            # and no price depends on later data.
            first = close[f].first_valid_index()
            index = index * close[f][first] / index[first]
        price[f] = index.to_numpy()
    return Market(
        dates=close.index,
        close_r={f: r.to_numpy() for f, r in close_r.items()},
        open_r={f: series(f)[1].fillna(0).to_numpy() for f in funds},
        price=price,
        priced=frozenset(f for f in funds if f in close),
        cash=rates[cfg.instruments[cfg.cash].rate].to_numpy(),
        levels=levels,
    )


def _tax(gain: float, carry: float, rate: float) -> tuple[float, float]:
    """Tax on a realized gain, offset first by losses carried forward; returns (tax, new carry)."""
    net = gain - carry
    return (rate * net, 0.0) if net > 0 else (0.0, -net)


def _sell_lots(lots: tuple[Lot, ...], shares: float) -> tuple[tuple[Lot, ...], float]:
    """Removes `shares` first-in-first-out; returns the remaining lots and the cost basis sold."""
    left, basis, out = shares, 0.0, []
    for lot in lots:
        take = min(lot.shares, left)
        if take > 0:
            basis += lot.cost * take / lot.shares
            left -= take
        if lot.shares - take > 1e-12:
            out.append(Lot(lot.shares - take, lot.cost * (lot.shares - take) / lot.shares))
    return tuple(out), basis


def _trade(s: SliceState, amount: float, price: float, rules: Rules, tax_rate: float, carry: float):
    shares = amount / price
    if amount < 0 and -amount >= s.fund * (1 - 1e-9):
        shares = -s.shares
    elif rules.whole_shares:
        shares = math.trunc(shares)
    if shares == 0:
        return s, 0.0, 0.0, carry
    executed = shares * price
    fee = abs(executed) * rules.cost
    tax = 0.0
    if shares > 0:
        lots = s.lots + (Lot(shares, executed + fee),)
    else:
        lots, basis = _sell_lots(s.lots, -shares)
        tax, carry = _tax(-executed - fee - basis, carry, tax_rate)
    fund = s.fund + executed if lots else 0.0
    return replace(s, fund=fund, cash=s.cash - executed - fee - tax, lots=lots), executed, tax, carry


def _cash_rate(bench: float, cash: float, nav: float, rules: Rules) -> float:
    """IBKR-style daily rate on all cash: benchmark minus spread, nothing on the first `free`, scaled for small accounts."""
    rate = max(bench - rules.cash_spread / 252, 0.0)
    if cash <= 0:
        return rate
    paid_share = max(cash - rules.cash_free, 0.0) / cash
    scale = min(1.0, nav / rules.cash_full_rate_nav) if rules.cash_full_rate_nav else 1.0
    return rate * paid_share * scale


def start_state(strategy: Strategy, market: Market, day, value: float, rules: Rules) -> State:
    i = market.pos(day)
    state = State(day=market.dates[i], slices=tuple(
        SliceState(fund=0.0, cash=sl.weight * value, held=1.0 if sl.rule == "hold" else 0.0) for sl in strategy.slices))
    slices = list(state.slices)
    for k, sl in enumerate(strategy.slices):
        if sl.rule == "hold":
            slices[k] = _trade(slices[k], slices[k].cash, market.price[sl.fund][i], replace(rules, cost=0.0), 0.0, 0.0)[0]
    return replace(state, slices=tuple(slices))


def step(strategy: Strategy, state: State, market: Market, day, rules: Rules):
    """The strategy's state and trades after the close of `day`, from yesterday's state and data up to `day` only."""
    i = market.pos(day)
    day = market.dates[i]
    trades: list[Trade] = []
    slices = list(state.slices)
    carry, paid = state.loss_carry, state.tax_paid

    def trade(k, s, amount, price, when, at, reason):
        nonlocal carry, paid
        s, executed, tax, carry = _trade(s, amount, price, rules, strategy.tax_rate, carry)
        if executed:
            paid += tax
            trades.append(Trade(when, strategy.slices[k].fund, executed, at, reason, tax))
        return s

    if strategy.rebalance == "monthly" and day.month != state.day.month:
        total = state.value
        # Cash moves between slices freely; only the fund part of each slice is traded.
        slices = [replace(s, cash=s.cash + sl.weight * total - s.value) for sl, s in zip(strategy.slices, slices)]
        for k, (sl, s) in enumerate(zip(strategy.slices, slices)):
            amount = s.held * s.value - s.fund
            if abs(amount) > 1e-12 and abs(amount) >= rules.min_trade * total:
                slices[k] = trade(k, s, amount, market.price[sl.fund][i - 1], state.day, "close", "rebalance")

    nav = sum(s.value for s in slices)
    c = _cash_rate(market.cash[i], sum(s.cash for s in slices), nav, rules)
    for k, (sl, s) in enumerate(zip(strategy.slices, slices)):
        r, o, p = market.close_r[sl.fund][i], market.open_r[sl.fund][i], market.price[sl.fund][i]
        if rules.execution == "next_open" and s.pending is not None:
            s = replace(s, fund=s.fund * (1 + o))
            s = replace(trade(k, s, s.pending * s.value - s.fund, p * (1 + o) / (1 + r), day, "open", "signal"),
                        held=s.pending, pending=None)
            s = replace(s, fund=s.fund * (1 + r) / (1 + o), cash=s.cash * (1 + c))
        else:
            s = replace(s, fund=s.fund * (1 + r), cash=s.cash * (1 + c))
            if rules.execution == "next_close" and s.pending is not None:
                s = replace(trade(k, s, s.pending * s.value - s.fund, p, day, "close", "signal"),
                            held=s.pending, pending=None)

        if sl.rule == "trend":
            frac = market.above(sl.signal, sl.windows, sl.buffer)[i]
            if frac != (s.held if s.pending is None else s.pending):
                if rules.execution == "same_close":
                    s = replace(trade(k, s, frac * s.value - s.fund, p, day, "close", "signal"), held=frac)
                else:
                    s = replace(s, pending=frac)
        slices[k] = s

    return State(day=day, slices=tuple(slices), loss_carry=carry, tax_paid=paid), trades


def after_tax_value(strategy: Strategy, state: State) -> float:
    """What the strategy would be worth if every position were sold at today's close and the tax paid."""
    gain = sum(s.fund - sum(lot.cost for lot in s.lots) for s in state.slices)
    tax, _ = _tax(gain, state.loss_carry, strategy.tax_rate)
    return state.value - tax


def backtest(strategy: Strategy, market: Market, rules: Rules, start=None, end=None, value=1.0, liquidate=True):
    """Daily values over [start, end). With `liquidate`, the last value is after selling everything and paying tax,
    so a buy-and-hold that never sells is compared on the same footing as a strategy that trades."""
    if rules.whole_shares and (missing := {sl.fund for sl in strategy.slices} - market.priced):
        raise ValueError(f"whole shares need real prices for {sorted(missing)}")
    dates = market.dates
    dates = dates[(dates >= (start or dates[0])) & (dates < (end or dates[-1] + pd.Timedelta(days=1)))]
    state = start_state(strategy, market, dates[0], value, rules)
    values, trades = [state.value], []
    for day in dates[1:]:
        state, t = step(strategy, state, market, day, rules)
        values.append(state.value)
        trades += t
    if liquidate:
        values[-1] = after_tax_value(strategy, state)
    return pd.Series(values, index=dates, name=strategy.id), trades, state


def stats(values: pd.Series, start, end) -> dict:
    """Annual return and worst drop over [start, end), from the close before `start`, 252 days a year."""
    before = values[values.index < start]
    v = values[(values.index >= start) & (values.index < end)]
    eq = v / (before.iloc[-1] if len(before) else v.iloc[0])
    return {"cagr": eq.iloc[-1] ** (252 / len(eq)) - 1, "max_dd": (eq / eq.cummax() - 1).min()}
