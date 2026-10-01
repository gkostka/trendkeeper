import numpy as np
import pandas as pd
import yfinance as yf

START, END = "2010-05-01", "2026-10-01"
FUNDS = {  # ticker: (underlying, currency of the listing)
    "SSO": ("SPY", "USD"), "QLD": ("QQQ", "USD"),
    "XS2D.L": ("SPY", "USD"), "XS2L.MI": ("SPY", "EUR"),
    "CL2.MI": ("SPY", "EUR"), "LQQ.PA": ("QQQ", "EUR"),
}
raw = yf.download(list(FUNDS) + ["SPY", "QQQ", "^IRX", "EURUSD=X"], start="2010-01-01", end=END,
                  auto_adjust=True, progress=False)["Close"]
us = raw.index[raw["SPY"].notna()]
cash = (raw["^IRX"].reindex(us).ffill() / 100 / 252).shift(1).fillna(0)
fx = raw["EURUSD=X"].reindex(us).ffill()  # USD per EUR, sampled at US dates


def model_usd(under):
    """Plain daily-reset 2x: no fees, financing the extra 1x at the T-bill rate."""
    r = raw[under].reindex(us).pct_change()
    return (1 + 2 * r - cash).cumprod()


def month_end(s):
    return s.dropna().resample("ME").last()


def clean(s, max_move=0.4):
    """Splits show up as one-day moves of ~+100% or ~-99%; drop those days' returns."""
    r = s.dropna().pct_change()
    r[r.abs() > max_move] = 0.0
    return (1 + r.fillna(0)).cumprod(), int((s.dropna().pct_change().abs() > max_move).sum())


rows = []
for tkr, (under, ccy) in FUNDS.items():
    level, fixed = clean(raw[tkr])
    m_usd = model_usd(under)
    candidates = {"2x in USD": m_usd}
    if ccy == "EUR":
        candidates = {"2x in USD, then converted to EUR": m_usd / fx}
        idx_eur = (raw[under].reindex(us) / fx).pct_change()
        # ponytail: financed at the USD T-bill rate for lack of a free EUR rate series; only the tracking error is used to tell the two apart

        candidates["2x of the index measured in EUR (FX leveraged)"] = (1 + 2 * idx_eur - cash).cumprod()
    real_m = month_end(level)
    real_m = real_m[(real_m.index >= START) & (real_m.index < END)]
    for name, m in candidates.items():
        mm = month_end(m).reindex(real_m.index)
        rr, mr = real_m.pct_change().dropna(), mm.pct_change().dropna()
        yrs = (real_m.index[-1] - real_m.index[0]).days / 365.25
        gap = (mm.iloc[-1] / mm.iloc[0]) ** (1 / yrs) - (real_m.iloc[-1] / real_m.iloc[0]) ** (1 / yrs)
        rows.append({"fund": tkr, "model": name, "glitch_days_fixed": fixed,
                     "monthly_tracking_err": (rr - mr).std() * np.sqrt(12),
                     "fund_cagr": (real_m.iloc[-1] / real_m.iloc[0]) ** (1 / yrs) - 1, "cost_vs_model": gap})

res = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(res.round(4).to_string(index=False))
assert res.groupby("fund").monthly_tracking_err.min().max() < 0.1, "some fund fits no model; check the data"

# CL2 applies 2x to the EUR-converted index, so its borrowing is in EUR: refit with the ECB deposit rate.
ecb = pd.read_csv("ecb_dfr.csv", usecols=["TIME_PERIOD", "OBS_VALUE"], parse_dates=["TIME_PERIOD"]).set_index("TIME_PERIOD")["OBS_VALUE"]
cash_eur = (ecb.reindex(us, method="ffill") / 100 / 252).shift(1).fillna(0)
idx_eur = (raw["SPY"].reindex(us) / fx).pct_change()
m_eur = month_end((1 + 2 * idx_eur - cash_eur).cumprod())
lvl, _ = clean(raw["CL2.MI"])
real_m = month_end(lvl)
real_m = real_m[(real_m.index >= START) & (real_m.index < END)]
mm = m_eur.reindex(real_m.index)
yrs = (real_m.index[-1] - real_m.index[0]).days / 365.25
print(f"\navg USD T-bill {cash.mean() * 252:.4f}, avg ECB deposit rate {cash_eur.mean() * 252:.4f}")
print(f"CL2 vs 2x EUR index financed at ECB rate: cost {(mm.iloc[-1] / mm.iloc[0]) ** (1 / yrs) - (real_m.iloc[-1] / real_m.iloc[0]) ** (1 / yrs):.4f}/yr")
