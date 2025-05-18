#!/usr/bin/env python3
"""
Main entry: fetch recent klines every X seconds, compute signal, and route to Trader.
"""

from __future__ import annotations
import argparse
import json
import pathlib
import time
from datetime import datetime, timezone

import pandas as pd
from binance.um_futures import UMFutures
from rich import print, box
from rich.console import Console
from rich.table import Table

from x_bot.strategy import EMACrossStrategy, Signal
from x_bot.trader   import Trader

_KLINE_INTERVAL = "1m"     # Binance interval: 1s,1m,3m,5m,15m,1h...
_HISTORY_LIMIT  = 200      # number of candles to keep


def load_keys(path: str | pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fetch_klines(client: UMFutures, symbol: str, limit: int = _HISTORY_LIMIT) -> pd.DataFrame:
    raw = client.klines(symbol=symbol, interval=_KLINE_INTERVAL, limit=limit)
    df  = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"
    ])
    # Convert numeric types
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].astype(float)
    return df


def pretty_print(df: pd.DataFrame, symbol: str) -> None:
    last = df.iloc[-1]
    table = Table(title=f"{symbol} – {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}",
                  box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Open"), table.add_column("High"), table.add_column("Low"), table.add_column("Close")
    table.add_row(*(f"{last[col]:,.2f}" for col in ["open", "high", "low", "close"]))
    Console().print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="x_bot – minimal Binance Futures bot")
    parser.add_argument("--keys",  default="keys.json", help="Path to key file")
    parser.add_argument("--symbol",default="BTCUSDT",   help="Futures trading pair")
    parser.add_argument("--mode",  choices=["live", "test"], help="Override mode in keys.json")
    parser.add_argument("--qty",   type=float, default=0.001, help="Order size in base asset")
    parser.add_argument("--loop",  type=int, default=30,  help="Seconds between cycles")
    args = parser.parse_args()

    creds = load_keys(args.keys)
    mode  = args.mode or creds.get("mode", "test")

    base_url = "https://fapi.binance.com" if mode == "live" \
               else "https://testnet.binancefuture.com"

    client = UMFutures(creds["key"], creds["secret"], base_url=base_url)

    strategy = EMACrossStrategy()
    trader   = Trader(client, symbol=args.symbol, leverage=2)

    print(f"[bold cyan]x_bot[/] launched in [green]{mode.upper()}[/] mode — symbol {args.symbol}")

    while True:
        candles = fetch_klines(client, args.symbol)
        pretty_print(candles.tail(1), args.symbol)

        signal = strategy.generate_signal(candles)
        if signal == Signal.LONG:
            trader.submit_order("BUY", args.qty)
        elif signal == Signal.SHORT:
            trader.submit_order("SELL", args.qty)

        time.sleep(args.loop)


if __name__ == "__main__":
    #main()
    print("test");

