import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from bot.config import FX, RATES, Config, Instrument, Strategy

CALENDAR_DAY_SERIES = {"^DFR", "EURUSD"}
# A day a fund moves this much more or less than its model can't be explained by the European close
# coming 4.5 hours early (2x of SPY's worst intraday swing is well inside it): it's a split or a bad print.
MAX_GAP = 0.20


@dataclass(frozen=True)
class Market:
    """Everything the engine reads, as arrays aligned on `dates`; row i uses prices up to dates[i] only."""

    dates: pd.DatetimeIndex
    close_r: dict[str, np.ndarray]
    open_r: dict[str, np.ndarray]
    price: dict[str, np.ndarray]
    scale: dict[str, np.ndarray]
    starts: dict[str, pd.Timestamp]
    priced: frozenset[str]
    foreign: frozenset[str]
    repaired: dict[str, tuple[pd.Timestamp, ...]]
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
    fx_cost: float = 0.0
    fx_min: float = 0.0

    @classmethod
    def from_config(cls, cfg: Config, **overrides) -> "Rules":
        cash = cfg.instruments[cfg.cash]
        return replace(cls(execution=cfg.execution, cost=cfg.trade_cost, min_trade=cfg.min_trade,
                           whole_shares=cfg.whole_shares, cash_spread=cash.spread, cash_free=cash.free,
                           cash_full_rate_nav=cash.full_rate_nav, fx_cost=cfg.fx_cost, fx_min=cfg.fx_min), **overrides)


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
    close = px.filter(like=".close").rename(columns=lambda c: c[: -len(".close")])
    # Trading days come from market prices; rate and FX series list every calendar day.
    traded = close.drop(columns=[c for c in close if c in CALENDAR_DAY_SERIES]).notna().any(axis=1)
    close = close.ffill()[traded]
    open_ = px.filter(like=".open").rename(columns=lambda c: c[: -len(".open")])
    keep = close.index >= start
    close, open_ = close[keep], open_.reindex(close.index[keep])
    def rate(name):
        return (close[RATES[name]] / 100 / 252).shift(1).fillna(0)

    def per_unit(frm, to) -> pd.Series:
        """Value of one unit of `frm` in `to`, each day."""
        if frm == to:
            return pd.Series(1.0, close.index)
        return 1 / close[FX[(frm, to)]] if (frm, to) in FX else close[FX[(to, frm)]]

    def convert(r, frm, to):
        rate = per_unit(frm, to)
        return (1 + r) * rate / rate.shift(1) - 1

    def ccy(name):
        return cfg.instruments[name].currency if name in cfg.instruments else "USD"

    returns: dict[str, tuple[pd.Series, pd.Series]] = {}
    repaired: dict[str, tuple[pd.Timestamp, ...]] = {}

    def own(name):
        c = close[name]
        prev = c.shift(1)
        r = (c / prev - 1).where(prev.notna())
        # An open equal to the close, or of zero, means Yahoo has no open that day. Treating it as a trade
        # at the close is the cautious choice: it can only make next_open look worse, never better.
        o = open_[name] / prev - 1 if name in open_ else r
        op = open_.get(name, c)
        o = o.where(op.notna() & (op != c) & (op > 0), r)
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
            fin = rate(inst.financing)
            sr = inst.leverage * ur - (inst.leverage - 1) * fin - inst.cost / 252
            so = inst.leverage * uo
            # fx = "converted": the fund applies its leverage in the tracked currency, then converts.
            sr, so = convert(sr, ccy(inst.tracks), inst.currency), convert(so, ccy(inst.tracks), inst.currency)
            bad = r.notna() & sr.notna() & ((r - sr).abs() > MAX_GAP)
            # The next day goes too: it carries the catch-up of a late US move, or the second half of a bad print.
            bad = bad | bad.shift(1, fill_value=False)
            if bad.any():
                repaired[name] = tuple(r.index[bad])
            r, o = r.where(r.notna() & ~bad, sr), o.where(r.notna() & ~bad, so)
        returns[name] = (r, o)
        return r, o

    signals = {sl.signal for s in cfg.strategies.values() for sl in s.slices if sl.rule == "trend"}
    levels = {name: (1 + series(name)[0]).cumprod() for name in signals}

    funds = {sl.fund for s in cfg.strategies.values() for sl in s.slices}
    base = cfg.base_currency
    close_r = {f: convert(series(f)[0], ccy(f), base) for f in funds}
    starts = {f: r.first_valid_index() for f, r in close_r.items()}
    close_r = {f: r.fillna(0) for f, r in close_r.items()}
    open_r = {f: convert(series(f)[1], ccy(f), base).fillna(0) for f in funds}
    price, scale = {}, {}
    for f in funds:
        index = (1 + close_r[f]).cumprod()
        scale[f] = np.ones(len(index))
        if f in close:
            # Anchored at the listing price, not today's: from listing on, shares cost what they really did,
            # and no price depends on later data.
            to_base = per_unit(ccy(f), base)
            first = (close[f].notna() & to_base.notna()).idxmax()
            index = index * close[f][first] * to_base[first] / index[first]
            # Repaired days (splits, bad prints) leave `index` off the quote; `scale` takes it back to the quote.
            quote = (close[f] * to_base).where(~close.index.isin(repaired.get(f, ())))
            scale[f] = (quote / index).ffill().fillna(1.0).to_numpy()
        price[f] = index.to_numpy()
    return Market(
        dates=close.index,
        close_r={f: r.to_numpy() for f, r in close_r.items()},
        open_r={f: r.to_numpy() for f, r in open_r.items()},
        price=price,
        scale=scale,
        starts=starts,
        priced=frozenset(f for f in funds if f in close),
        foreign=frozenset(f for f in funds if ccy(f) != base),
        repaired=repaired,
        cash=rate(cfg.instruments[cfg.cash].rate).to_numpy(),
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


def _trade(s: SliceState, amount: float, price: float, rules: Rules, tax_rate: float, carry: float,
           foreign: bool = False, available: float = math.inf, quote: float | None = None):
    """Trades `amount` of the slice's fund at `price`; a buy spends no more than `available` cash, fees included.
    Whole shares are counted at `quote`, the price on the exchange, which can differ from the engine's `price`."""
    fx_rate, fx_min = (rules.fx_cost, rules.fx_min) if foreign else (0.0, 0.0)
    if amount > 0:
        amount = min(amount, (available - fx_min) / (1 + rules.cost + fx_rate))
        if amount <= 0:
            return s, 0.0, 0.0, carry
    shares = amount / price
    if amount < 0 and -amount >= s.fund * (1 - 1e-9):
        shares = -s.shares
    elif rules.whole_shares:
        quote = quote or price
        shares = math.trunc(amount / quote) * quote / price
    if shares == 0:
        return s, 0.0, 0.0, carry
    executed = shares * price
    fee = abs(executed) * (rules.cost + fx_rate) + fx_min
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
    if cash <= 0:
        return 0.0
    rate = max(bench - rules.cash_spread / 252, 0.0)
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
            p = market.price[sl.fund][i]
            slices[k] = _trade(slices[k], slices[k].cash, p, replace(rules, cost=0.0), 0.0, 0.0,
                               available=slices[k].cash, quote=p * market.scale[sl.fund][i])[0]
    return replace(state, slices=tuple(slices))


def step(strategy: Strategy, state: State, market: Market, day, rules: Rules):
    """The strategy's state and trades after the close of `day`, from yesterday's state and data up to `day` only."""
    i = market.pos(day)
    day = market.dates[i]
    trades: list[Trade] = []
    slices = list(state.slices)
    funds = [sl.fund for sl in strategy.slices]
    carry, paid = state.loss_carry, state.tax_paid

    def trade(k, amount, price, j, when, at, reason):
        nonlocal carry, paid
        f = funds[k]
        # Cash moves between slices freely, so a buy can use any slice's cash, but never more than there is.
        available = sum(s.cash for s in slices)
        s, executed, tax, carry = _trade(slices[k], amount, price, rules, strategy.tax_rate, carry,
                                         f in market.foreign, available, price * market.scale[f][j])
        if executed:
            paid += tax
            trades.append(Trade(when, f, executed, at, reason, tax))
        slices[k] = s

    def fill_signals(price, j, when, at):
        for k, s in enumerate(slices):
            if s.pending is not None:
                trade(k, s.pending * s.value - s.fund, price(k), j, when, at, "signal")
                slices[k] = replace(slices[k], held=s.pending, pending=None)

    def rebalance(price, j, when, at):
        total = sum(s.value for s in slices)
        slices[:] = [replace(s, cash=s.cash + sl.weight * total - s.value) for sl, s in zip(strategy.slices, slices)]
        amounts = [s.held * s.value - s.fund for s in slices]
        # Sells first, so the buys can spend what they free.
        for k in sorted(range(len(slices)), key=amounts.__getitem__):
            amount = min(amounts[k], sum(s.cash for s in slices))
            if abs(amount) > 1e-12 and abs(amount) >= rules.min_trade * total:
                trade(k, amount, price(k), j, when, at, "rebalance")

    new_month = strategy.rebalance == "monthly" and day.month != state.day.month
    r = [market.close_r[f][i] for f in funds]
    o = [market.open_r[f][i] for f in funds]

    def close_price(k):
        return market.price[funds[k]][i]

    def open_price(k):
        return close_price(k) * (1 + o[k]) / (1 + r[k])

    # Decided after yesterday's close, traded when the execution rule allows: same_close at yesterday's close,
    # next_open at today's open, next_close at today's close.
    if rules.execution == "same_close" and new_month:
        rebalance(lambda k: market.price[funds[k]][i - 1], i - 1, state.day, "close")
    c = _cash_rate(market.cash[i], sum(s.cash for s in slices), state.value, rules)
    slices[:] = [replace(s, cash=s.cash * (1 + c)) for s in slices]
    if rules.execution == "next_open":
        slices[:] = [replace(s, fund=s.fund * (1 + o[k])) for k, s in enumerate(slices)]
        fill_signals(open_price, i, day, "open")
        if new_month:
            rebalance(open_price, i, day, "open")
        slices[:] = [replace(s, fund=s.fund * (1 + r[k]) / (1 + o[k])) for k, s in enumerate(slices)]
    else:
        slices[:] = [replace(s, fund=s.fund * (1 + r[k])) for k, s in enumerate(slices)]
        if rules.execution == "next_close":
            fill_signals(close_price, i, day, "close")
            if new_month:
                rebalance(close_price, i, day, "close")

    for k, sl in enumerate(strategy.slices):
        if sl.rule == "trend":
            s = slices[k]
            frac = market.above(sl.signal, sl.windows, sl.buffer)[i]
            if frac != (s.held if s.pending is None else s.pending):
                if rules.execution == "same_close":
                    trade(k, frac * s.value - s.fund, close_price(k), i, day, "close", "signal")
                    slices[k] = replace(slices[k], held=frac)
                else:
                    slices[k] = replace(s, pending=frac)

    return State(day=day, slices=tuple(slices), loss_carry=carry, tax_paid=paid), trades


def after_tax_value(strategy: Strategy, state: State, market: Market, rules: Rules) -> float:
    """What the strategy would be worth if every position were sold at today's close, fees and tax paid."""
    fees = sum(s.fund * rules.cost + ((s.fund * rules.fx_cost + rules.fx_min) if sl.fund in market.foreign else 0.0)
               for sl, s in zip(strategy.slices, state.slices) if s.lots)
    gain = sum(s.fund - sum(lot.cost for lot in s.lots) for s in state.slices) - fees
    tax, _ = _tax(gain, state.loss_carry, strategy.tax_rate)
    return state.value - fees - tax


def backtest(strategy: Strategy, market: Market, rules: Rules, start=None, end=None, value=1.0, liquidate=True):
    """Daily values over [start, end). With `liquidate`, the last value is after selling everything and paying tax,
    so a buy-and-hold that never sells is compared on the same footing as a strategy that trades."""
    if rules.whole_shares and (missing := {sl.fund for sl in strategy.slices} - market.priced):
        raise ValueError(f"whole shares need real prices for {sorted(missing)}")
    dates = market.dates
    starts = {sl.fund: market.starts[sl.fund] for sl in strategy.slices}
    if None in starts.values():
        raise ValueError(f"no data for {sorted(f for f, d in starts.items() if d is None)}")
    # By default, start on the last day before every fund has a return, the first day all of them have a price.
    start = start or dates[market.pos(max(starts.values())) - 1]
    dates = dates[(dates >= start) & (dates < (end or dates[-1] + pd.Timedelta(days=1)))]
    if late := {f: f"{d:%Y-%m-%d}" for f, d in starts.items() if d > dates[min(1, len(dates) - 1)]}:
        raise ValueError(f"no data at the start {dates[0]:%Y-%m-%d} for {late}")
    state = start_state(strategy, market, dates[0], value, rules)
    values, trades = [state.value], []
    for day in dates[1:]:
        state, t = step(strategy, state, market, day, rules)
        values.append(state.value)
        trades += t
    if liquidate:
        values[-1] = after_tax_value(strategy, state, market, rules)
    return pd.Series(values, index=dates, name=strategy.id), trades, state


def stats(values: pd.Series, start, end) -> dict:
    """Annual return over calendar years and worst drop over [start, end), from the close before `start`."""
    before = values[values.index < start]
    v = values[(values.index >= start) & (values.index < end)]
    first = before.index[-1] if len(before) else v.index[0]
    eq = v / values[first]
    years = (v.index[-1] - first).days / 365.25
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1, "max_dd": (eq / eq.cummax() - 1).min()}
