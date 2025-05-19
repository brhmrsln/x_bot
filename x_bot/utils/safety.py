"""
Generic retry / validation helpers used across the bot.
"""

from __future__ import annotations
import backoff
import pandas as pd
from binance.error import ClientError

# ---------- REST retry wrapper -------------------------------------------

@backoff.on_exception(
    backoff.expo,
    (ClientError, OSError, ValueError),
    max_time=60,         # toplam 60 sn dene
    max_tries=5,         # en fazla 5 tekrar
    jitter=None,
)
def fetch_klines_safe(client, symbol: str, interval: str, limit: int):
    """
    Wraps client.klines() with exponential back-off.
    Raises ValueError if API returns empty list.
    """
    raw = client.klines(symbol=symbol, interval=interval, limit=limit)
    if not raw:
        raise ValueError("Empty klines")
    return raw


# ---------- dataframe integrity -------------------------------------------

def validate_df(df: pd.DataFrame, min_rows: int = 30) -> bool:
    """
    Quick sanity-check before feeding data into a strategy.
    Returns True = looks usable, False = skip cycle.
    """
    if df is None or df.empty:
        return False
    if len(df) < min_rows:
        return False
    if df["close"].isna().any():
        return False
    return True

def build_dataframe(raw_klines) -> pd.DataFrame:
    """
    Convert Binance /klines REST response (list[list]) → Pandas DataFrame
    and cast numeric columns to float.
    """
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base", "taker_quote", "ignore"
    ]
    df = pd.DataFrame(raw_klines, columns=cols)

    # Cast numeric strings to float for TA calculations
    numeric = ["open", "high", "low", "close", "volume"]
    df[numeric] = df[numeric].astype(float)

    return df

