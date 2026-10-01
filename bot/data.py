import io
import sys
import urllib.request
from pathlib import Path

import pandas as pd

RESEARCH_TICKERS = ["SPY", "QQQ", "^NDX", "^IRX", "SSO", "QLD", "VFITX"]
UCITS_TICKERS = ["DBPG.DE", "LQQ.PA", "SXRM.DE"]
ECB = "https://data-api.ecb.europa.eu/service/data/{}?format=csvdata&startPeriod=1999-01-01"
ECB_SERIES = {"EURUSD": "EXR/D.USD.EUR.SP00.A", "^DFR": "FM/D.U2.EUR.4F.KR.DFR.LEV"}


def download(tickers, start="1990-01-01", end="2026-10-01") -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    close = raw["Close"].add_suffix(".close")
    open_ = raw["Open"].add_suffix(".open")
    return pd.concat([close, open_], axis=1).sort_index(axis=1)


def download_ecb(end="2026-10-01") -> pd.DataFrame:
    """EUR/USD (USD per euro, ECB 14:15 CET fixing) and the ECB deposit rate in %, both daily from 1999."""
    out = {}
    for name, key in ECB_SERIES.items():
        with urllib.request.urlopen(ECB.format(key), timeout=60) as f:
            raw = pd.read_csv(io.StringIO(f.read().decode()), usecols=["TIME_PERIOD", "OBS_VALUE"])
        s = raw.set_index(pd.to_datetime(raw.TIME_PERIOD)).OBS_VALUE.astype(float)
        out[f"{name}.close"] = s[s.index < end]
    return pd.DataFrame(out)


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
