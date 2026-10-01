from pathlib import Path

import pandas as pd

RESEARCH_TICKERS = ["SPY", "QQQ", "^NDX", "^IRX", "SSO", "QLD", "VFITX"]


def download(tickers, start="1990-01-01", end="2026-10-01") -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    close = raw["Close"].add_suffix(".close")
    open_ = raw["Open"].add_suffix(".open")
    return pd.concat([close, open_], axis=1).sort_index(axis=1)


def save_snapshot(prices: pd.DataFrame, path: Path) -> None:
    prices.to_csv(path, float_format="%.6g")


def load_snapshot(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0, parse_dates=True)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "tests" / "data" / "prices.csv.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    save_snapshot(download(RESEARCH_TICKERS), out)
    print(out, out.stat().st_size)
