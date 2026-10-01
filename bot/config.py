import tomllib
from dataclasses import dataclass, field
from pathlib import Path

EXECUTIONS = ("same_close", "next_open", "next_close")
RATES = {"tbill": "^IRX", "ecb_dfr": "^DFR"}
FX = {("USD", "EUR"): "EURUSD"}  # column holds units of the first currency per one of the second


@dataclass(frozen=True)
class Instrument:
    id: str
    currency: str = "USD"
    tracks: str | None = None
    leverage: float = 1.0
    cost: float = 0.0
    financing: str = "tbill"
    backfill: str | None = None
    rate: str | None = None
    spread: float = 0.0
    free: float = 0.0
    full_rate_nav: float = 0.0
    fx: str = "converted"


@dataclass(frozen=True)
class Slice:
    weight: float
    fund: str
    rule: str
    signal: str | None = None
    windows: tuple[int, ...] = ()
    buffer: float = 0.0


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    slices: tuple[Slice, ...]
    tax_rate: float
    rebalance: str | None = None
    benchmark: bool = False


@dataclass(frozen=True)
class Config:
    instruments: dict[str, Instrument]
    strategies: dict[str, Strategy]
    cash: str
    base_currency: str = "USD"
    execution: str = "same_close"
    trade_cost: float = 0.0005
    min_trade: float = 0.0
    whole_shares: bool = False
    start_value: float = 1.0
    fx_cost: float = 0.0
    fx_min: float = 0.0
    extra: dict = field(default_factory=dict)


class ConfigError(ValueError):
    pass


def load(source: str | Path) -> Config:
    text = Path(source).read_text() if isinstance(source, Path) else source
    raw = tomllib.loads(text)
    instruments = {k: Instrument(id=k, **v) for k, v in raw.pop("instrument", {}).items()}
    strategies = {}
    for s in raw.pop("strategy", []):
        slices = tuple(Slice(**{**sl, "windows": tuple(sl.get("windows", ()))}) for sl in s.pop("slice"))
        if "tax_rate" not in s:
            raise ConfigError(f"strategy {s['id']}: tax_rate is required")
        strategies[s["id"]] = Strategy(slices=slices, **s)
    if "cash" not in raw:
        raise ConfigError("cash is required: the instrument whose rate uninvested money earns")
    known = ("cash", "base_currency", "execution", "trade_cost", "min_trade", "whole_shares", "start_value",
             "fx_cost", "fx_min")
    cfg = Config(instruments=instruments, strategies=strategies,
                 **{k: raw.pop(k) for k in known if k in raw}, extra=raw)
    check(cfg)
    return cfg


def check(cfg: Config) -> None:
    if cfg.execution not in EXECUTIONS:
        raise ConfigError(f"execution must be one of {EXECUTIONS}, not {cfg.execution!r}")
    cash = cfg.instruments.get(cfg.cash)
    if cash is None or cash.rate is None:
        raise ConfigError(f"cash instrument {cfg.cash!r} must be listed and have a rate")
    for name in [cash.rate] + [i.financing for i in cfg.instruments.values() if i.tracks]:
        if name not in RATES:
            raise ConfigError(f"unknown rate {name!r}; known: {sorted(RATES)}")
    pairs = {frozenset(k) for k in FX}
    for i in cfg.instruments.values():
        if i.fx != "converted":
            raise ConfigError(f"instrument {i.id}: only fx = 'converted' is supported")
        tracked = cfg.instruments[i.tracks].currency if i.tracks in cfg.instruments else i.currency
        for other in (cfg.base_currency, tracked):
            if other != i.currency and frozenset((i.currency, other)) not in pairs:
                raise ConfigError(f"instrument {i.id}: no exchange rate between {i.currency} and {other}")
        for ref in (i.tracks, i.backfill):
            if ref and ref not in cfg.instruments and not ref.startswith("^"):
                raise ConfigError(f"instrument {i.id}: unknown instrument {ref!r}")
    for s in cfg.strategies.values():
        if abs(sum(sl.weight for sl in s.slices) - 1) > 1e-9:
            raise ConfigError(f"strategy {s.id}: slice weights must add up to 1")
        if not 0 <= s.tax_rate < 1:
            raise ConfigError(f"strategy {s.id}: tax_rate must be between 0 and 1")
        for sl in s.slices:
            if sl.fund not in cfg.instruments:
                raise ConfigError(f"strategy {s.id}: fund {sl.fund!r} is not an instrument")
            if sl.rule == "trend":
                if sl.signal not in cfg.instruments or not sl.windows or min(sl.windows) < 1:
                    raise ConfigError(f"strategy {s.id}: trend slice on {sl.fund} needs a signal instrument and windows")
                if not 0 <= sl.buffer < 0.2:
                    raise ConfigError(f"strategy {s.id}: buffer must be between 0 and 0.2")
            elif sl.rule != "hold":
                raise ConfigError(f"strategy {s.id}: rule must be 'hold' or 'trend', not {sl.rule!r}")
