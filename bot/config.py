import os
import tomllib
from dataclasses import dataclass, field, fields
from datetime import date
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


CHANNELS = ("slack", "email")
DEFAULT = Path(__file__).resolve().parent / "config.toml"


def path() -> Path:
    """The config file: TK_CONFIG if set, else bot/config.toml."""
    return Path(os.environ.get("TK_CONFIG", DEFAULT))


def data_dir(cfg: "Config") -> Path:
    """Where the database, status and personal files live: TK_DATA_DIR if set, else the config's data_dir."""
    return Path(os.environ.get("TK_DATA_DIR", cfg.data_dir))


@dataclass(frozen=True)
class Notify:
    alerts: tuple[str, ...] = ()
    daily: tuple[str, ...] = ()
    weekly: tuple[str, ...] = ()
    email_to: str | None = None


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
    follow: str | None = None
    start: date | None = None
    data_dir: str = "/var/lib/trendkeeper"
    xetra_holidays: tuple[date, ...] = ()
    notify: Notify = field(default_factory=Notify)


class ConfigError(ValueError):
    pass


def load(path: str | Path) -> Config:
    return loads(Path(path).read_text())


def _make(cls, where: str, **kw):
    try:
        return cls(**kw)
    except TypeError as e:
        raise ConfigError(f"{where}: {e}") from None


def loads(text: str) -> Config:
    raw = tomllib.loads(text)
    instruments = {k: _make(Instrument, f"instrument {k}", id=k, **v) for k, v in raw.pop("instrument", {}).items()}
    strategies = {}
    for s in raw.pop("strategy", []):
        if s["id"] in strategies:
            raise ConfigError(f"strategy {s['id']}: id used twice")
        if "tax_rate" not in s:
            raise ConfigError(f"strategy {s['id']}: tax_rate is required")
        slices = tuple(_make(Slice, f"strategy {s['id']}", **{**sl, "windows": tuple(sl.get("windows", ()))})
                       for sl in s.pop("slice"))
        strategies[s["id"]] = _make(Strategy, f"strategy {s['id']}", slices=slices, **s)
    if "cash" not in raw:
        raise ConfigError("cash is required: the instrument whose rate uninvested money earns")
    if "notify" in raw:
        n = raw.pop("notify")
        raw["notify"] = _make(Notify, "notify", **{k: tuple(v) if isinstance(v, list) else v for k, v in n.items()})
    if "xetra_holidays" in raw:
        raw["xetra_holidays"] = tuple(raw["xetra_holidays"])
    known = {f.name for f in fields(Config)} - {"instruments", "strategies"}
    if unknown := sorted(set(raw) - known):
        raise ConfigError(f"unknown settings {unknown}; known: {sorted(known)}")
    cfg = Config(instruments=instruments, strategies=strategies, **raw)
    check(cfg)
    return cfg


def check(cfg: Config) -> None:
    if cfg.execution not in EXECUTIONS:
        raise ConfigError(f"execution must be one of {EXECUTIONS}, not {cfg.execution!r}")
    if cfg.follow is not None and cfg.follow not in cfg.strategies:
        raise ConfigError(f"follow: no strategy {cfg.follow!r}")
    n = cfg.notify
    for kind in ("alerts", "daily", "weekly"):
        if bad := sorted(set(getattr(n, kind)) - set(CHANNELS)):
            raise ConfigError(f"notify.{kind}: unknown channels {bad}; known: {list(CHANNELS)}")
    if "email" in n.alerts + n.daily + n.weekly and not n.email_to:
        raise ConfigError("notify: email is used but email_to is not set")
    cash = cfg.instruments.get(cfg.cash)
    if cash is None or cash.rate is None:
        raise ConfigError(f"cash instrument {cfg.cash!r} must be listed and have a rate")
    for name in [cash.rate] + [i.financing for i in cfg.instruments.values() if i.tracks]:
        if name not in RATES:
            raise ConfigError(f"unknown rate {name!r}; known: {sorted(RATES)}")
    pairs = {frozenset(k) for k in FX}
    for i in cfg.instruments.values():
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
