"""
Trader
======

• Opens one isolated 10× USDT-M futures position at a time
• Calculates quantity from account equity (default 100 USDT × 10× = 1 000 USDT notional)
• Places **reduce-only** TAKE_PROFIT_MARKET (+2 USDT) & STOP_MARKET (-5 USDT)
  orders immediately after entry
• Monitors unrealised PnL every loop; if ±threshold is hit,
  closes position with a market order (extra safety)
• Logs each closed trade to ``trade_results.csv`` and prints running total
• Enforces a *cool-down* period after exit before a new entry

Dependencies:  `rich`, `decimal`, `x_bot.utils.result_log`
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Literal
from math import floor

from binance.error import ClientError
from binance.um_futures import UMFutures
from rich import print

from x_bot.utils.result_log import log_trade

Side = Literal["BUY", "SELL"]        # long / short
PRICE_PREC = Decimal("0.1")          # BTCUSDT min tick


class Trader:
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        client: UMFutures,
        symbol: str,
        notional_usd: float,
        leverage: int = 10,
        tp_usd: float = 2.0,
        sl_usd: float = 5.0,
        cooldown: int = 30,
        step_size: Decimal = Decimal("0.0001"),   
        price_tick: Decimal = Decimal("0.1"),
    ):
        self.client = client
        self.symbol = symbol.upper()
        self.leverage = leverage
        self.notional = notional_usd
        self.tp_usd = tp_usd
        self.sl_usd = sl_usd
        self.cooldown = cooldown
        self.step = step_size
        self.tick = price_tick

        # runtime state
        self.position_side: Side | None = None
        self.entry_price: float | None = None
        self.qty: float | None = None
        self.last_exit_ts: float = 0.0

        self._configure_isolated()

    # ---------- one-time account setup -------------------------------- #
    def _configure_isolated(self) -> None:
        try:
            self.client.change_margin_type(symbol=self.symbol, marginType="ISOLATED")
        except ClientError as exc:
            if exc.error_code != -4046:  # already isolated
                raise
        self.client.change_leverage(symbol=self.symbol, leverage=self.leverage)
        print(f"[green]✓[/] Isolated {self.leverage}× set for {self.symbol}")

    # ---------- helpers ----------------------------------------------- #
    def _market_qty(self, price: float) -> float:
        """
        Qty = floor( (notional*leverage/price) / step ) * step
        Ensures qty % step == 0
        """
        raw_qty = (self.notional * self.leverage) / price
        steps   = floor(Decimal(raw_qty) / self.step)
        qty     = (steps * self.step).normalize()
        if qty <= 0:
            print("[red]Qty ≤ 0 — increase --notional or lower leverage[/]")
        return float(qty)

    def _get_unrealised(self) -> float:
        """
        Compute PnL = (markPrice − entryPrice) × qty × direction
        • direction = +1 for long, −1 for short
        """
        if self.entry_price is None or self.qty is None:
            return 0.0

        # mark price (≈ last price) — no auth needed
        mark = float(self.client.ticker_price(self.symbol)["price"])
        direction = 1 if self.position_side == "BUY" else -1
        pnl = (mark - self.entry_price) * self.qty * direction
        return pnl

    def _cancel_protective_orders(self) -> None:
        """
        Cancel any remaining TP/SL orders left after manual close.
        Works with both old (`open_orders`) and new (`get_open_orders`)
        connector method names.
        """
        # -------- 1 ▸ hangi metot mevcut? -------------------------------
        if hasattr(self.client, "open_orders"):
            fetch_orders = lambda: self.client.open_orders(symbol=self.symbol)
        elif hasattr(self.client, "get_open_orders"):
            fetch_orders = lambda: self.client.get_open_orders(symbol=self.symbol)
        else:
            print("[yellow]No open-orders method on client[/]")
            return

        # -------- 2 ▸ listeyi çek & iptal et ---------------------------
        try:
            for order in fetch_orders():
                # koruyucu emirlerimiz either:
                #   • type == TAKE_PROFIT_MARKET / STOP_MARKET
                #   • veya reduceOnly/closePosition true  (API sürümüne göre değişir)
                if order["type"] in ("TAKE_PROFIT_MARKET", "STOP_MARKET") \
                   or order.get("closePosition") == "true":
                    self.client.cancel_order(symbol=self.symbol,
                                             orderId=order["orderId"])
        except ClientError as exc:
            # çoğu durumda "Unknown order sent." => zaten iptal/çalışmış demek
            print(f"[yellow]Cancel warn:[/] {exc}")

    def _round_price(self, p: float) -> float:
        """Round price to nearest valid tickSize."""
        steps = Decimal(p) / self.tick
        return float((steps.quantize(0) * self.tick).normalize())

    # ---------- public API -------------------------------------------- #
    # 1) ENTRY
    # ------------------------------------------------------------------ #
    def try_open(self, side: Side, price_hint: float) -> None:
        """
        Open a new isolated 10× position **only if**
          • no other position is active, and
          • the cooldown period has elapsed.
        """
        # ---- çakışma & cooldown kontrolü ---------------------------------
        if self.position_side or (time.time() - self.last_exit_ts) < self.cooldown:
            return  # already in a trade or still cooling down

        # ---- 1) Piyasa öncesi son fiyat ----------------------------------
        last_price = float(self.client.ticker_price(self.symbol)["price"])

        # ---- 2) Adet (qty) hesapla ---------------------------------------
        qty = self._market_qty(last_price)
        if qty <= 0:
            print("[red]Qty ≤ 0 — increase --notional or lower leverage[/]")
            return
        print(f"[grey]Placing MARKET {side} qty {qty} (price ~ {last_price})[/]")

        # ---- 3) MARKET emri ----------------------------------------------
        try:
            order = self.client.new_order(
                symbol=self.symbol,
                side=side,
                type="MARKET",
                quantity=qty,
            )
        except ClientError as exc:
            print(f"[red]Open failed:[/] {exc}")
            return

        self.position_side = side
        self.qty = qty
        self.entry_price = float(order["avgPrice"]) or last_price
        print(f"[cyan]{side}[/] opened @ {self.entry_price:.2f}  qty {qty}")

        self.skip_first_pnl = True 
        self._place_protective_orders(side)


    # 2) RISK / EXIT WATCH
    def manage_position(self) -> None:
        """
        Check PnL once per main loop; skip very first check so protective
        orders can settle.
        """
        if not self.position_side:
            return

        if getattr(self, "skip_first_pnl", False):
            # koruyucu TP/SL emirleri yerleşene kadar bekle
            self.skip_first_pnl = False
            return

        pnl = self._get_unrealised()
        print(f"Unrealised PnL: {pnl:+.2f}", end="\r") 
        if pnl >= self.tp_usd or pnl <= -self.sl_usd:
            self._close_position(pnl)

    # ---------- internal ---------------------------------------------- #
    def _place_protective_orders(self, side: Side) -> None:
        """
        Create reduce-only TP (+2 USDT) & SL (-5 USDT) market orders.
        Auto-cancels one another (Binance engine handles).
        """
        if self.entry_price is None or self.qty is None:
            return

        tp_price = self._round_price(self.entry_price + self.tp_usd)
        sl_price = self._round_price(self.entry_price - self.sl_usd)

        if side == "SELL":                     # short
            tp_price, sl_price = sl_price, tp_price

        opp_side = "SELL" if side == "BUY" else "BUY"
        try:
            # --- Take-Profit
            self.client.new_order(
                symbol=self.symbol,
                side=opp_side,
                type="TAKE_PROFIT_MARKET",
                stopPrice=float(tp_price),
                closePosition="true",
            )
            # --- Stop-Loss
            self.client.new_order(
                symbol=self.symbol,
                side=opp_side,
                type="STOP_MARKET",
                stopPrice=float(sl_price),
                closePosition="true",
            )
            print(f"[green]Protective orders[/] TP {tp_price}  SL {sl_price}")
        except ClientError as exc:
            print(f"[red]Protective order error:[/] {exc}")

    def _close_position(self, pnl_estimate: float) -> None:
        """Closes with market order, logs result, cancels leftover orders."""
        if not self.qty or not self.position_side:
            return
        opp = "SELL" if self.position_side == "BUY" else "BUY"
        try:
            self.client.new_order(
                symbol=self.symbol,
                side=opp,
                type="MARKET",
                quantity=self.qty,
                reduceOnly="true",
            )
            self._cancel_protective_orders()
            emoji = "💰" if pnl_estimate > 0 else "💥"
            print(f"{emoji} Closed ~{pnl_estimate:+.2f} USDT")

            # Log trade
            log_trade(
                pnl_estimate,
                self.position_side,
                self.entry_price,
                float(self.client.ticker_price(self.symbol)["price"]),
            )
        except ClientError as exc:
            print(f"[red]Close failed:[/] {exc}")
            return

        # reset state
        self.position_side = None
        self.entry_price = None
        self.qty = None
        self.last_exit_ts = time.time()
