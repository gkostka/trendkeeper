import io
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

from bot.config import FX, RATES, Config

RESEARCH_TICKERS = ["SPY", "QQQ", "^NDX", "^IRX", "SSO", "QLD", "VFITX"]
UCITS_TICKERS = ["DBPG.DE", "LQQ.PA", "SXRM.DE"]
ECB = "https://data-api.ecb.europa.eu/service/data/{}?format=csvdata&startPeriod={}"
NASDAQ = "https://api.nasdaq.com/api/quote/{}/historical?assetclass=etf&fromdate={}&limit=10"
ECB_SERIES = {"EURUSD": "EXR/D.USD.EUR.SP00.A", "^DFR": "FM/D.U2.EUR.4F.KR.DFR.LEV"}


def download(tickers, start="1990-01-01", end=None) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(tickers, start=start, end=end or date.today().isoformat(), auto_adjust=True, progress=False)
    close = raw["Close"].add_suffix(".close")
    open_ = raw["Open"].add_suffix(".open")
    return pd.concat([close, open_], axis=1).sort_index(axis=1)


def download_ecb(names=tuple(ECB_SERIES), start="1999-01-01", end=None) -> pd.DataFrame:
    """EUR/USD (USD per euro, ECB 14:15 CET fixing) and the ECB deposit rate in %, both daily from 1999."""
    end, out = end or date.today().isoformat(), {}
    for name in names:
        with urllib.request.urlopen(ECB.format(ECB_SERIES[name], start), timeout=60) as f:
            raw = pd.read_csv(io.StringIO(f.read().decode()), usecols=["TIME_PERIOD", "OBS_VALUE"])
        s = raw.set_index(pd.to_datetime(raw.TIME_PERIOD)).OBS_VALUE.astype(float)
        out[f"{name}.close"] = s[s.index < end]
    return pd.DataFrame(out)


def needed(cfg: Config) -> set[str]:
    """Every price, rate and FX series the config's instruments read."""
    out = set()
    for i in cfg.instruments.values():
        if i.rate:
            out.add(RATES[i.rate])
            continue
        out |= {i.id} | ({i.backfill} if i.backfill else set()) | ({RATES[i.financing]} if i.tracks else set())
        if i.currency != cfg.base_currency:
            out.add(FX.get((i.currency, cfg.base_currency)) or FX[(cfg.base_currency, i.currency)])
    return out


def fetch(cfg: Config, start: str) -> pd.DataFrame:
    """Prices from `start` on: Yahoo for funds, indexes and ^IRX; the ECB for EUR/USD and its deposit rate."""
    want = needed(cfg)
    ecb = [s for s in want if s in ECB_SERIES]
    parts = [download(sorted(want - set(ecb)), start=start)]
    if ecb:
        parts.append(download_ecb(ecb, start=start))
    return pd.concat(parts, axis=1, sort=True)


def second_close(ticker: str) -> tuple[pd.Timestamp, float]:
    """The latest close from Nasdaq's public quote API, a second free source to cross-check Yahoo's.
    (Stooq, the plan's first choice, now puts its CSV behind a browser check.)"""
    since = f"{pd.Timestamp.today() - pd.Timedelta(days=14):%Y-%m-%d}"
    req = urllib.request.Request(NASDAQ.format(ticker, since),
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as f:
        row = json.load(f)["data"]["tradesTable"]["rows"][0]
    return pd.Timestamp(pd.to_datetime(row["date"], format="%m/%d/%Y")), float(row["close"].replace(",", ""))


def save_snapshot(prices: pd.DataFrame, path: Path) -> None:
    prices.to_csv(path, float_format="%.6g")


def load_snapshot(*paths: Path) -> pd.DataFrame:
    return pd.concat([pd.read_csv(p, index_col=0, parse_dates=True) for p in paths], axis=1, sort=True)


if __name__ == "__main__":
    data = Path(__file__).resolve().parent.parent / "tests" / "data"
    data.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "research"
    if which == "research":
        out, prices = data / "prices.csv.gz", download(RESEARCH_TICKERS)
    else:
        out, prices = data / "eur.csv.gz", pd.concat([download(UCITS_TICKERS), download_ecb()], axis=1, sort=True)
    save_snapshot(prices, out)
    print(out, out.stat().st_size)
