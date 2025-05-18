"""
Strategy module – contains a simple EMA-crossover + RSI filter example.
You can subclass `BaseStrategy` for additional ideas later.
"""

from __future__ import annotations
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator


class Signal:
    LONG  = "long"
    SHORT = "short"
    FLAT  = None


class BaseStrategy:
    """All strategies must implement `generate_signal(candles_df)`."""
    def generate_signal(self, candles: pd.DataFrame) -> str | None:
        raise NotImplementedError


class EMACrossStrategy(BaseStrategy):
    """
    9/21 EMA crossover with RSI(14) confirmation:
        • Go LONG  when EMA-9 crosses above EMA-21 and RSI < 70
        • Go SHORT when EMA-9 crosses below EMA-21 and RSI > 30
        • Do nothing otherwise
    """

    def __init__(self, fast: int = 9, slow: int = 21, rsi_period: int = 14):
        self.fast = fast
        self.slow = slow
        self.rsi_period = rsi_period

    # --- public -----------------------------------------------------------

    def generate_signal(self, candles: pd.DataFrame) -> str | None:
        if candles.empty:
            return Signal.FLAT

        close = candles["close"]

        ema_fast = EMAIndicator(close, window=self.fast).ema_indicator()
        ema_slow = EMAIndicator(close, window=self.slow).ema_indicator()
        rsi      = RSIIndicator(close, window=self.rsi_period).rsi()

        # Latest values
        fast_now, slow_now, rsi_now = ema_fast.iat[-1], ema_slow.iat[-1], rsi.iat[-1]

        if fast_now > slow_now and rsi_now < 70:
            return Signal.LONG
        if fast_now < slow_now and rsi_now > 30:
            return Signal.SHORT
        return Signal.FLAT

