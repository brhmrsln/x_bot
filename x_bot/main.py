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
from decimal import Decimal
from math import floor

import pandas as pd
from binance.um_futures import UMFutures
from rich import print, box
from rich.console import Console
from rich.table import Table

from x_bot.utils.safety import fetch_klines_safe, validate_df, build_dataframe

from x_bot.strategy import EMACrossStrategy, Signal
from x_bot.trader import Trader, Side

_KLINE_INTERVAL = "1m"     # Binance interval: 1s,1m,3m,5m,15m,1h...
_HISTORY_LIMIT  = 200      # number of candles to keep


def load_keys(path: str | pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fetch_klines(client, symbol: str) -> pd.DataFrame | None:
    """
    Wrapped version with retry + validation.
    Returns DataFrame or None if unusable.
    """
    try:
        raw = fetch_klines_safe(client, symbol, _KLINE_INTERVAL, _HISTORY_LIMIT)
        df = build_dataframe(raw)          # eski numeric-cast satırlarını taşı
        return df if validate_df(df) else None
    except Exception as exc:               # ClientError / ValueError / OSError
        print(f"[red]Kline fetch failed:[/] {exc}")
        return None
    
def get_equity_usd(client, asset="USDT") -> float:
    for row in client.balance():
        if row["asset"] == asset:
            return float(row["availableBalance"])
    return 0.0


def _symbol_filters(client, symbol: str) -> dict:
    """Return the filter dicts for the given symbol."""
    info = client.exchange_info()              # no args
    for s in info["symbols"]:
        if s["symbol"] == symbol.upper():
            return {f["filterType"]: f for f in s["filters"]}
    raise ValueError(f"{symbol} not found in exchangeInfo")

def lot_step(client, symbol: str) -> Decimal:
    return Decimal(_symbol_filters(client, symbol)["LOT_SIZE"]["stepSize"])

def price_tick(client, symbol: str) -> Decimal:
    return Decimal(_symbol_filters(client, symbol)["PRICE_FILTER"]["tickSize"])

def print_futures_balances(client):
    rows = client.balance()
    print("\n[bold]Futures wallet balances[/]")
    for row in rows:
        asset = row["asset"]
        avail = float(row["availableBalance"])
        wallet = float(row["balance"])
        upnl   = float(row["crossUnPnl"])
        if avail or wallet or upnl:
            print(f"{asset:>5s}   avail={avail:.4f}   wallet={wallet:.4f}   upnl={upnl:.4f}")

def pretty_print(df: pd.DataFrame, symbol: str) -> None:
    last = df.iloc[-1]
    table = Table(title=f"{symbol} – {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}",
                  box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Open"), table.add_column("High"), table.add_column("Low"), table.add_column("Close")
    table.add_row(*(f"{last[col]:,.2f}" for col in ["open", "high", "low", "close"]))
    Console().print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="x_bot – minimal Binance Futures bot")
    parser.add_argument("--keys",  default="keys_test.json", help="Path to key file")
    parser.add_argument("--symbol",default="BTCUSDT",   help="Futures trading pair")
    parser.add_argument("--mode",  choices=["live", "test"], help="Override mode in keys_test.json")
    parser.add_argument("--qty",   type=float, default=0.001, help="Order size in base asset")
    parser.add_argument("--loop",  type=int, default=30,  help="Seconds between cycles")
    parser.add_argument("--notional", type=float, default=100, help="USDT amount per trade before leverage (default 100)")
    args = parser.parse_args()

    creds = load_keys(args.keys)
    mode  = args.mode or creds.get("mode", "test")

    base_url = "https://fapi.binance.com" if mode == "live" \
               else "https://testnet.binancefuture.com"

    client = UMFutures(creds["key"], creds["secret"], base_url=base_url)

    STEP_SIZE  = lot_step(client, args.symbol)
    PRICE_TICK = price_tick(client, args.symbol)
    print(f"[bold]Exchange precision[/]  stepSize={STEP_SIZE}  tickSize={PRICE_TICK}")

    srv_ms = client.time()["serverTime"]
    skew = abs(srv_ms - int(time.time() * 1000))
    if skew > 1_000:
        print(f"[yellow]⚠ Clock skew {skew} ms — enable NTP![/]")

    print_futures_balances(client)

    equity = get_equity_usd(client)
    print(f"Account equity: {equity:.2f} USDT")

    strategy = EMACrossStrategy()
    trader = Trader(client,
                    symbol=args.symbol,
                    notional_usd=args.notional, 
                    leverage=10,
                    tp_usd=2.0,
                    sl_usd=5.0,
                    cooldown=30,
                    step_size=STEP_SIZE,       
                    price_tick=PRICE_TICK)
    
    print(f"[bold cyan]x_bot[/] launched in [green]{mode.upper()}[/] mode — symbol {args.symbol}")


    while True:
        candles = fetch_klines(client, args.symbol)
        if candles is None:
            time.sleep(args.loop)
            continue

        pretty_print(candles.tail(1), args.symbol)

        # --- ENTRY -----------------------------------------------------------
        signal = strategy.generate_signal(candles)
        if signal == Signal.LONG:
            trader.try_open("BUY", candles["close"].iat[-1])
        elif signal == Signal.SHORT:
            trader.try_open("SELL", candles["close"].iat[-1])

        # --- EXIT  -----------------------------------------------------------
        trader.manage_position()

        time.sleep(args.loop)

if __name__ == "__main__":
    main()
    #print("test")

