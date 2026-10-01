import tomllib
from dataclasses import dataclass, field
from pathlib import Path

EXECUTIONS = ("same_close", "next_open", "next_close")
RATES = {"tbill": "^IRX"}


@dataclass(frozen=True)
class Instrument:
    id: str
    currency: str = "USD"
    tracks: str | None = None
    leverage: float = 1.0
    cost: float = 0.0
    financing: str = "tbill"
    backfill: str | None = None


@dataclass(frozen=True)
class Slice:
    weight: float
    fund: str
    rule: str
    signal: str | None = None
    windows: tuple[int, ...] = ()


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
    execution: str = "same_close"
    trade_cost: float = 0.0005
    cash_rate: str = "tbill"
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
    cfg = Config(
        instruments=instruments,
        strategies=strategies,
        execution=raw.pop("execution", "same_close"),
        trade_cost=raw.pop("trade_cost", 0.0005),
        cash_rate=raw.pop("cash_rate", "tbill"),
        extra=raw,
    )
    check(cfg)
    return cfg


def check(cfg: Config) -> None:
    if cfg.execution not in EXECUTIONS:
        raise ConfigError(f"execution must be one of {EXECUTIONS}, not {cfg.execution!r}")
    for name in [cfg.cash_rate] + [i.financing for i in cfg.instruments.values() if i.tracks]:
        if name not in RATES:
            raise ConfigError(f"unknown rate {name!r}; known: {sorted(RATES)}")
    for i in cfg.instruments.values():
        for ref in (i.tracks, i.backfill):
            if ref and ref not in cfg.instruments and not ref.startswith("^"):
                raise ConfigError(f"instrument {i.id}: unknown instrument {ref!r}")
    for s in cfg.strategies.values():
        if abs(sum(sl.weight for sl in s.slices) - 1) > 1e-9:
            raise ConfigError(f"strategy {s.id}: slice weights must add up to 1")
        for sl in s.slices:
            if sl.fund not in cfg.instruments:
                raise ConfigError(f"strategy {s.id}: fund {sl.fund!r} is not an instrument")
            if sl.rule == "trend":
                if sl.signal not in cfg.instruments or not sl.windows or min(sl.windows) < 1:
                    raise ConfigError(f"strategy {s.id}: trend slice on {sl.fund} needs a signal instrument and windows")
            elif sl.rule != "hold":
                raise ConfigError(f"strategy {s.id}: rule must be 'hold' or 'trend', not {sl.rule!r}")
