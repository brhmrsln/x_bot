"""
Trader module – wraps Binance Futures client calls + basic risk management.
"""

from __future__ import annotations
from binance.um_futures import UMFutures
from rich import print


class Trader:
    def __init__(self, client: UMFutures, symbol: str, leverage: int = 2):
        self.client  = client
        self.symbol  = symbol.upper()
        self.leverage = leverage
        self._set_leverage()

    # ---------------------------------------------------------------------

    def _set_leverage(self) -> None:
        try:
            self.client.change_leverage(symbol=self.symbol, leverage=self.leverage)
            print(f"[bold green]✓[/] Leverage set to {self.leverage} × for {self.symbol}")
        except Exception as exc:  # noqa: BLE001
            print(f"[red]Leverage change failed:[/] {exc}")

    # ---------------------------------------------------------------------

    def submit_order(self, side: str, quantity: float) -> None:
        """
        side  -> "BUY"  or "SELL"
        quantity is **base asset** amount, NOT quote (e.g. BTC, not USDT)
        """
        try:
            order = self.client.new_order(
                symbol=self.symbol,
                side=side.upper(),
                type="MARKET",
                quantity=quantity,
            )
            print(f"[yellow]{side}[/] market order filled – id: {order['orderId']}")
        except Exception as exc:  # noqa: BLE001
            print(f"[red]Order failed:[/] {exc}")

