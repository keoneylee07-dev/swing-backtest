"""
The 25-ticker liquid universe used for the pooled backtest.

All 25 were listed and trading well before 2019-01-01, and all clear the
harness liquidity floor (>$10, >2M avg volume) on unadjusted 2019 prices.
Mega-cap tech, semis, banks, energy and staples -- deliberately mixed, so
the pooled result is not just one sector's regime.
"""

TICKERS = [
    # mega-cap tech / internet
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "DIS",
    # semis
    "NVDA", "AMD", "INTC", "MU", "QCOM", "CSCO",
    # autos / industrials
    "TSLA", "BA",
    # financials
    "JPM", "BAC", "WFC", "C",
    # energy
    "XOM", "CVX",
    # healthcare / staples / telecom
    "PFE", "KO", "WMT", "T",
]

assert len(TICKERS) == len(set(TICKERS)) == 25
