# trading_bot/exchange/binance_client.py
import logging
from binance.um_futures import UMFutures  # For USDT-M Futures (USDⓈ-M Futures)
import time # For sleep

# Attempt to import settings and logger setup function from the project structure
try:
    from trading_bot.config import settings
    from trading_bot.utils.logger_config import setup_logger
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_script_dir, '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.insert(0, project_root_dir)
    from trading_bot.config import settings
    from trading_bot.utils.logger_config import setup_logger

logger = logging.getLogger("trading_bot")

class BinanceFuturesClient:
    def __init__(self):
        logger.info(f"Initializing BinanceFuturesClient for {settings.TRADING_MODE} mode...")
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.base_url = settings.BINANCE_FUTURES_BASE_URL
        self.exchange_info_cache = None 

        is_api_key_placeholder = (not self.api_key or 
                                  self.api_key.startswith("YOUR_") or 
                                  "aaaaa" in self.api_key.lower() or 
                                  "bbbbb" in self.api_key.lower())
        
        is_api_secret_placeholder = (not self.api_secret or 
                                     self.api_secret.startswith("YOUR_") or 
                                     "aaaaa" in self.api_secret.lower() or
                                     "bbbbb" in self.api_secret.lower())

        if is_api_key_placeholder:
            msg = "Binance API Key is not set correctly or is a placeholder in .env / settings.py."
            logger.critical(msg)
            raise ValueError(msg)
        if is_api_secret_placeholder:
            msg = "Binance API Secret is not set correctly or is a placeholder in .env / settings.py."
            logger.critical(msg)
            raise ValueError(msg)
            
        logger.debug(f"API Key (first 5 chars): {str(self.api_key)[:5]}, Using Base URL: {self.base_url}")
        
        try:
            self.client = UMFutures(key=self.api_key, secret=self.api_secret, base_url=self.base_url)
            logger.debug("UMFutures client instance created.")
        except Exception as e:
            logger.critical(f"Failed to create UMFutures client instance: {e}", exc_info=True)
            raise 

        self._test_connectivity()
        self._get_exchange_info() 

    def _test_connectivity(self):
        logger.info("Testing connectivity to Binance Futures API...")
        try:
            self.client.ping()
            logger.info("Successfully connected to Binance Futures API (ping successful).")
        except Exception as e:
            logger.error(f"Connectivity test failed: Error pinging Binance Futures API: {e}", exc_info=True)
            raise 

    def _get_exchange_info(self):
        if not self.exchange_info_cache: 
            logger.info("Fetching exchange information...")
            try:
                self.exchange_info_cache = self.client.exchange_info()
                logger.info("Successfully fetched and cached exchange information.")
            except Exception as e:
                logger.error(f"Error fetching exchange information: {e}", exc_info=True)
                self.exchange_info_cache = None 
                raise 
        return self.exchange_info_cache

    def _get_symbol_info(self, symbol):
        exchange_info = self._get_exchange_info()
        if not exchange_info:
            raise ConnectionError("Could not get exchange information. Client may be misconfigured or network issues.")
        for item in exchange_info['symbols']:
            if item['symbol'] == symbol.upper():
                return item
        logger.error(f"Symbol information for {symbol} not found in exchange info.")
        raise ValueError(f"Symbol information for {symbol} not found.")

    def _get_filter_value(self, symbol_info, filter_type, filter_key):
        for f_filter in symbol_info.get('filters', []):
            if f_filter.get('filterType') == filter_type:
                return f_filter.get(filter_key)
        return None

    def _format_quantity(self, symbol, quantity):
        try:
            symbol_info = self._get_symbol_info(symbol)
            step_size_str = self._get_filter_value(symbol_info, 'LOT_SIZE', 'stepSize')
            min_qty_str = self._get_filter_value(symbol_info, 'LOT_SIZE', 'minQty')

            if not step_size_str or not min_qty_str:
                logger.warning(f"Step size or Min Qty not found for {symbol}, using raw quantity {quantity} formatted to a reasonable default precision.")
                return float(f"{float(quantity):.8f}") # Genel bir formatlama

            step_size = float(step_size_str)
            min_qty = float(min_qty_str)
            
            # Calculate precision from step_size (e.g., "0.001" -> 3)
            if '.' in step_size_str:
                # Virgülden sonraki sıfır olmayan son basamağa kadar olan kısım hassasiyeti verir
                precision = len(step_size_str.split('.')[1].rstrip('0'))
            else: 
                precision = 0 # Tam sayı ise hassasiyet 0

            # Miktarı step_size'ın en yakın katına (aşağıya) yuvarla ve string olarak formatla
            # Örnek: quantity=0.00954, step_size=0.001 -> floor(0.00954/0.001)*0.001 = floor(9.54)*0.001 = 9*0.001 = 0.009
            if step_size > 0:
                # Ensure quantity is a multiple of step_size, by truncating towards zero
                # (value / step) * step -> then format to precision
                num_steps = int(float(quantity) / step_size) # Kaç tane step_size içerdiği (tam sayı kısmı)
                formatted_quantity_val = num_steps * step_size
            else: # step_size 0 ise (olmamalı ama)
                formatted_quantity_val = float(quantity)

            # Python'un float hassasiyet sorunlarından kaçınmak için string formatlama
            formatted_quantity_str = f"{formatted_quantity_val:.{precision}f}"
            formatted_quantity = float(formatted_quantity_str)

            logger.debug(f"Formatting quantity for {symbol}: original={quantity}, minQty={min_qty}, stepSize={step_size_str} (numeric: {step_size}), precision={precision}, pre-minQty-check-formatted={formatted_quantity}")

            # Eğer formatlanmış miktar min_qty'den küçükse ve orijinal miktar 0'dan büyükse
            if formatted_quantity < min_qty and quantity > 0: # quantity > 0 kontrolü önemli
                logger.warning(f"Formatted quantity {formatted_quantity} for {symbol} is less than minQty {min_qty}. Adjusting to minQty.")
                # Bu durumda API hatası almamak için min_qty'ye eşitlemek bir seçenek olabilir,
                # ancak bu istenen pozisyon büyüklüğünü değiştirir.
                # Ya da hata fırlatıp pozisyon büyüklüğünün artırılmasını istemek daha doğru olabilir.
                # Şimdilik, eğer orijinal miktar min_qty'den büyük veya eşitse ve formatlama min_qty'nin altına düşürdüyse,
                # bu bir sorun. Eğer orijinal miktar zaten min_qty'den küçükse, sipariş zaten geçmemeli.
                # Bu mantık, siparişin minimumları karşılamasını sağlamalı.
                # If original quantity was intended to be at least min_qty, but formatting made it smaller (e.g. 0.001 becomes 0.0)
                # this logic below is not perfect.
                # The core idea is that the final quantity sent to API must be >= min_qty AND a multiple of step_size.

                # If the calculated quantity (after being made a multiple of stepSize) is still less than minQty,
                # but the *original intended quantity based on USDT value was trying to be something*,
                # it means the position_size_usdt is too small for even minQty.
                # The `ValueError` for `formatted_quantity <= 0` in `place_market_order` should catch if it becomes 0.
                # If it's >0 but < min_qty, Binance will reject with a "LOT_SIZE" filter error.
                # We rely on that Binance error for now if formatted_quantity is >0 but < min_qty.
                pass # Let Binance reject if it's > 0 but < min_qty after formatting.

            return formatted_quantity
        except Exception as e:
            logger.error(f"Error in _format_quantity for {symbol} ({quantity}): {e}", exc_info=True)
            return float(f"{float(quantity):.8f}") # Fallback to a generic formatting
        
    def _format_price(self, symbol, price):
        try:
            symbol_info = self._get_symbol_info(symbol)
            tick_size_str = self._get_filter_value(symbol_info, 'PRICE_FILTER', 'tickSize')

            if not tick_size_str:
                logger.warning(f"Tick size not found for {symbol}, using default price formatting (8 decimals).")
                return float(f"{float(price):.8f}")

            tick_size = float(tick_size_str)
            if '.' in tick_size_str:
                precision = len(tick_size_str.split('.')[1].rstrip('0'))
            else:
                precision = 0
            
            formatted_price = (round(float(price) / tick_size)) * tick_size
            formatted_price = float(f"{formatted_price:.{precision}f}")

            logger.debug(f"Formatting price for {symbol}: original={price}, tickSize={tick_size_str}, precision={precision}, formatted={formatted_price}")
            return formatted_price
        except Exception as e:
            logger.error(f"Error formatting price for {symbol} ({price}): {e}", exc_info=True)
            return float(price)

    def set_leverage(self, symbol, leverage):
        logger.info(f"Attempting to set leverage for {symbol.upper()} to {leverage}x...")
        try:
            response = self.client.change_leverage(symbol=symbol.upper(), leverage=leverage, recvWindow=5000)
            logger.info(f"Leverage for {symbol.upper()} set to {leverage}x. Response: {response}")
            return response
        except Exception as e:
            logger.error(f"Failed to set leverage for {symbol.upper()} to {leverage}x: {e}", exc_info=True)
            if hasattr(e, 'error_code') and e.error_code == -4048: 
                logger.warning(f"Leverage for {symbol.upper()} was already {leverage}x or not modified.")
                return {"status": "Leverage not modified", "code": e.error_code, "msg": e.error_message}
            raise 

    def get_ticker_price(self, symbol):
        logger.debug(f"Fetching ticker price for {symbol.upper()}...")
        try:
            ticker_info = self.client.ticker_price(symbol=symbol.upper())
            price = float(ticker_info['price'])
            logger.info(f"Current ticker price for {symbol.upper()}: {price}")
            return price
        except Exception as e:
            logger.error(f"Error fetching ticker price for {symbol.upper()}: {e}", exc_info=True)
            return None

    def place_market_order(self, symbol, side, quantity): # Sadece quantity alır
        logger.info(f"Attempting to place MARKET order for {symbol.upper()}: Side={side}, Quantity(base)={quantity}")
        
        # Miktarı formatla (Bu _format_quantity metodunun en son iyileştirilmiş hali olmalı)
        formatted_quantity = self._format_quantity(symbol, quantity) 
        if formatted_quantity <= 0: 
            msg = f"Formatted quantity {formatted_quantity} is zero or less for symbol {symbol}. Cannot place order. Original quantity was {quantity}."
            logger.error(msg)
            raise ValueError(msg)
            
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'type': 'MARKET',
            'quantity': formatted_quantity, # Formatlanmış miktarı kullan
            'newOrderRespType': 'RESULT'
        }
        logger.info(f"Placing order with explicitly calculated and formatted quantity: {formatted_quantity} for {symbol.upper()}")
        logger.debug(f"Parameters being sent to Binance API for new_order: {params}")
        try:
            order = self.client.new_order(**params)
            logger.info(f"MARKET order placed successfully for {symbol.upper()}. Response: {order}")
            return order
        except Exception as e:
            logger.error(f"Failed to place MARKET order (using calculated quantity) for {symbol.upper()}: {e}", exc_info=True)
            raise
    
    def place_take_profit_market_order(self, symbol, side, quantity, stop_price, reduce_only=True):
        """
        Places a TAKE_PROFIT_MARKET order.
        Typically used for taking profit on an existing position.
        :param side: "BUY" (for take-profit on short) or "SELL" (for take-profit on long)
        :param stop_price: The price at which the market order (to take profit) will be triggered.
        :param reduce_only: If True, this order will only reduce an existing position.
        """
        formatted_quantity = self._format_quantity(symbol, quantity)
        if formatted_quantity <= 0:
            msg = f"Formatted quantity {formatted_quantity} for take-profit order is zero or less. Cannot place order."
            logger.error(msg)
            raise ValueError(msg)
            
        # stop_price for TAKE_PROFIT_MARKET is the trigger price for profit taking
        formatted_trigger_price = self._format_price(symbol, stop_price) 
        
        logger.info(f"Attempting to place TAKE_PROFIT_MARKET order: {side} {formatted_quantity} {symbol.upper()} at triggerPrice {formatted_trigger_price}, reduceOnly={reduce_only}...")
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'type': 'TAKE_PROFIT_MARKET',
            'quantity': formatted_quantity,
            'stopPrice': formatted_trigger_price, # For TAKE_PROFIT_MARKET, stopPrice acts as the trigger price
            'reduceOnly': str(reduce_only).lower(),
            'newOrderRespType': 'RESULT'
        }
        logger.debug(f"Parameters for TAKE_PROFIT_MARKET order: {params}")
        try:
            order = self.client.new_order(**params)
            logger.info(f"TAKE_PROFIT_MARKET order placed successfully for {symbol.upper()}. Response: {order}")
            return order
        except Exception as e:
            logger.error(f"Failed to place TAKE_PROFIT_MARKET order for {symbol.upper()} at triggerPrice {formatted_trigger_price}: {e}", exc_info=True)
            raise 


    def place_stop_market_order(self, symbol, side, quantity, stop_price, reduce_only=True):
        formatted_quantity = self._format_quantity(symbol, quantity)
        if formatted_quantity <= 0:
            msg = f"Formatted quantity {formatted_quantity} for stop order is zero or less. Cannot place stop order."
            logger.error(msg)
            raise ValueError(msg)
            
        formatted_stop_price = self._format_price(symbol, stop_price)
        
        logger.info(f"Attempting to place STOP_MARKET order: {side} {formatted_quantity} {symbol.upper()} at stopPrice {formatted_stop_price}, reduceOnly={reduce_only}...")
        params = {
            'symbol': symbol.upper(),
            'side': side.upper(),
            'type': 'STOP_MARKET',
            'quantity': formatted_quantity,
            'stopPrice': formatted_stop_price,
            'reduceOnly': str(reduce_only).lower(),
            'newOrderRespType': 'RESULT'
        }
        logger.debug(f"Parameters for STOP_MARKET order: {params}")
        try:
            order = self.client.new_order(**params)
            logger.info(f"STOP_MARKET order placed successfully for {symbol.upper()}. Response: {order}")
            return order
        except Exception as e:
            logger.error(f"Failed to place STOP_MARKET order for {symbol.upper()} at stopPrice {formatted_stop_price}: {e}", exc_info=True)
            raise # Re-raise
    
    def open_position_market_with_sl_tp(self, symbol, order_side, position_size_usdt, stop_loss_price, take_profit_price):
        """
        Opens a new position with a MARKET order using calculated base asset quantity,
        and immediately places both a STOP_MARKET order for stop-loss 
        and a TAKE_PROFIT_MARKET order for take-profit.

        :param symbol: Trading symbol, e.g., "BTCUSDT"
        :param order_side: "BUY" (for LONG) or "SELL" (for SHORT)
        :param position_size_usdt: Desired nominal size of the position in USDT.
        :param stop_loss_price: The absolute price for the stop-loss order.
        :param take_profit_price: The absolute price for the take-profit order.
        :return: Tuple (entry_order_response, stop_loss_order_response, take_profit_order_response)
                 Returns None for any order that failed or if the entry order fails.
        """
        logger.info(f"Attempting to open {order_side.upper()} position for {symbol.upper()} (target nominal size: {position_size_usdt} USDT) "
                    f"with SL at {stop_loss_price} and TP at {take_profit_price}.")
        
        entry_order_response = None
        stop_loss_order_response = None
        take_profit_order_response = None

        # 1. Get current price to calculate base asset quantity
        current_price = self.get_ticker_price(symbol)
        if not current_price or current_price <= 0:
            logger.error(f"Could not fetch valid current price for {symbol.upper()} (got: {current_price}). Cannot calculate quantity for entry order.")
            return entry_order_response, stop_loss_order_response, take_profit_order_response # Return Nones

        # Calculate quantity in base asset
        quantity_in_base_asset = position_size_usdt / current_price
        logger.info(f"Calculated base asset quantity for {position_size_usdt} USDT entry at price {current_price} for {symbol.upper()}: {quantity_in_base_asset}")
        # Note: _format_quantity will be called inside place_market_order

        # 2. Place the MARKET order to open the position
        try:
            # Call the version of place_market_order that only accepts 'quantity'
            entry_order_response = self.place_market_order(
                symbol=symbol, 
                side=order_side, 
                quantity=quantity_in_base_asset 
            )
        except ValueError as ve: 
            # Catches ValueErrors from _format_quantity or pre-API checks in place_market_order
            logger.error(f"ValueError during market entry placement step: {ve}", exc_info=False) 
            return entry_order_response, stop_loss_order_response, take_profit_order_response
        except Exception as e: 
            # Catches other exceptions (e.g., Binance API errors re-raised by place_market_order)
            logger.error(f"Unexpected exception during market entry placement step: {e}", exc_info=True)
            return entry_order_response, stop_loss_order_response, take_profit_order_response

        if not entry_order_response or 'orderId' not in entry_order_response:
            logger.error(f"Market entry order for {order_side.upper()} {symbol.upper()} FAILED or did not return an orderId. Response: {entry_order_response}")
            return entry_order_response, stop_loss_order_response, take_profit_order_response

        # Market orders with RESULT response type should contain executedQty
        executed_qty_str = entry_order_response.get('executedQty')
        # Ensure status is FILLED as well, though for MARKET orders with RESULT it usually is.
        order_status = entry_order_response.get('status')

        if order_status != 'FILLED' or not executed_qty_str or float(executed_qty_str) == 0:
            logger.error(f"Market entry order {entry_order_response.get('orderId')} for {symbol.upper()} status is '{order_status}' "
                         f"or executedQty is missing/zero ({executed_qty_str}). Cannot place SL/TP. Response: {entry_order_response}")
            return entry_order_response, stop_loss_order_response, take_profit_order_response
        
        executed_quantity = float(executed_qty_str)
        logger.info(f"Market entry order {entry_order_response.get('orderId')} for {symbol.upper()} FILLED. "
                    f"Executed Quantity: {executed_quantity}. Avg Price: {entry_order_response.get('avgPrice')}")

        # Determine side for SL and TP orders (opposite of entry order side)
        sl_tp_side = "SELL" if order_side.upper() == "BUY" else "BUY"
        
        # 3. Place the STOP_MARKET order for stop-loss
        try:
            stop_loss_order_response = self.place_stop_market_order(
                symbol=symbol, 
                side=sl_tp_side, 
                quantity=executed_quantity, 
                stop_price=stop_loss_price, 
                reduce_only=True
            )
        except Exception as e:
            # place_stop_market_order should log the detailed error and re-raise
            logger.error(f"Exception during stop-loss placement (entry order {entry_order_response.get('orderId')} was successful): {e}", exc_info=True) 
            # Continue to try placing TP order even if SL fails
        
        if not stop_loss_order_response or 'orderId' not in stop_loss_order_response:
            logger.warning(f"Market entry {entry_order_response.get('orderId')} placed, but FAILED to place stop-loss or SL orderId missing. SL Response: {stop_loss_order_response}")
        else:
            logger.info(f"Stop-loss order {stop_loss_order_response.get('orderId')} successfully placed for entry {entry_order_response.get('orderId')}.")

        # 4. Place the TAKE_PROFIT_MARKET order
        try:
            take_profit_order_response = self.place_take_profit_market_order(
                symbol=symbol,
                side=sl_tp_side,
                quantity=executed_quantity,
                stop_price=take_profit_price, 
                reduce_only=True
            )
        except Exception as e:
            logger.error(f"Exception during take-profit placement (entry order {entry_order_response.get('orderId')} was successful): {e}", exc_info=True)

        if not take_profit_order_response or 'orderId' not in take_profit_order_response:
            logger.warning(f"Market entry {entry_order_response.get('orderId')} placed, but FAILED to place take-profit or TP orderId missing. TP Response: {take_profit_order_response}")
        else:
            logger.info(f"Take-profit order {take_profit_order_response.get('orderId')} successfully placed for entry {entry_order_response.get('orderId')}.")

        return entry_order_response, stop_loss_order_response, take_profit_order_response
    

    def get_position_info(self, symbol):
        """Fetches current position information for a specific symbol."""
        logger.debug(f"Fetching position risk information for {symbol.upper()}...")
        positions_risk_data = None
        try:
            # Try with "get_position_risk" first
            if hasattr(self.client, "get_position_risk"):
                logger.debug("Attempting to use self.client.get_position_risk()")
                positions_risk_data = self.client.get_position_risk(symbol=symbol.upper(), recvWindow=5000)
            # If "get_position_risk" doesn't exist, try "position_risk" (as we did before, which failed)
            # This is just to be thorough, but the AttributeError previously suggested "position_risk" is not there.
            elif hasattr(self.client, "position_risk"): # This branch likely won't be hit if previous error was consistent
                logger.debug("Attempting to use self.client.position_risk() as a fallback")
                positions_risk_data = self.client.position_risk(symbol=symbol.upper(), recvWindow=5000)
            else:
                logger.error("'UMFutures' object has no attribute like 'position_risk' or 'get_position_risk'. Falling back to account info.")
                # Fallback to account() if specific position_risk methods are not found
                return self._get_position_info_from_account(symbol) # Call a helper for account-based positions

            logger.debug(f"Raw position_risk/get_position_risk API response for {symbol.upper()}: {positions_risk_data}")

            if not positions_risk_data:
                logger.info(f"No position risk data returned by API for {symbol.upper()}.")
                return [] 
            
            active_positions = []
            for pos in positions_risk_data:
                if float(pos.get('positionAmt', 0)) != 0:
                    logger.info(f"ACTIVE Position (from position_risk) for {symbol.upper()}: "
                                f"Side={'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'}, "
                                f"Amount={pos['positionAmt']}, EntryPrice={pos.get('entryPrice', 'N/A')}, "
                                f"MarkPrice={pos.get('markPrice', 'N/A')}, UnPnl={pos.get('unRealizedProfit', 'N/A')}, "
                                f"Leverage={pos.get('leverage', 'N/A')}")
                    active_positions.append(pos)
                else:
                    logger.debug(f"No active position amount for {symbol.upper()} in this position_risk entry (Amt: {pos.get('positionAmt', 0)}). Leverage set: {pos.get('leverage')}.")
            
            if not active_positions:
                logger.info(f"No active open position currently found for {symbol.upper()} via position_risk/get_position_risk.")
            
            return active_positions 

        except AttributeError as ae:
            logger.error(f"AttributeError while trying to fetch position risk for {symbol.upper()}: {ae}. Neither 'position_risk' nor 'get_position_risk' seems to exist or work.", exc_info=False)
            logger.info("Falling back to fetching position info from general account details (less detailed).")
            return self._get_position_info_from_account(symbol) # Call helper for account-based positions
        except Exception as e:
            logger.error(f"Generic error fetching position risk information for {symbol.upper()}: {e}", exc_info=True)
            return None # Indicate a more general error

    def _get_position_info_from_account(self, symbol):
        """
        Fallback method to get position information from the general account endpoint.
        This typically has less detail (e.g., may lack entryPrice directly for the position).
        """
        logger.debug(f"Fetching account information to find position for symbol: {symbol.upper()} (fallback method)...")
        try:
            account_info = self.client.account(recvWindow=5000) 
            # logger.debug(f"Raw account API response (fallback): {account_info}") # Can be very verbose

            if not account_info or 'positions' not in account_info:
                logger.warning(f"No 'positions' key found in account information response (fallback).")
                return []

            all_positions = account_info['positions']
            active_positions_for_symbol = []

            for pos in all_positions:
                if pos.get('symbol') == symbol.upper() and float(pos.get('positionAmt', 0)) != 0:
                    logger.info(f"ACTIVE Position (from account fallback) for {symbol.upper()}: "
                                f"Side={'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'}, "
                                f"Amount={pos['positionAmt']}, "
                                f"UnPnl={pos.get('unRealizedProfit', 'N/A')}, "
                                f"Leverage={pos.get('leverage', 'N/A')}, "
                                f"Notional={pos.get('notional', 'N/A')}") # entryPrice is typically not here
                    active_positions_for_symbol.append(pos)
            
            if not active_positions_for_symbol:
                logger.info(f"No active open position currently found for {symbol.upper()} in account details (fallback).")
            
            return active_positions_for_symbol
        except Exception as e:
            logger.error(f"Error fetching account/position information (fallback) for {symbol.upper()}: {e}", exc_info=True)
            return None
    
    def get_all_orders_for_symbol(self, symbol, limit=100): # Limit for recent orders
        """
        Fetches all orders (open, filled, cancelled, etc.) for a specific symbol.
        We can then filter for 'NEW' status to find open orders.
        """
        logger.debug(f"Fetching all orders for {symbol.upper()} (limit: {limit})...")
        try:
            # Assuming the library method is named get_all_orders and requires symbol
            # The actual method name might vary slightly depending on the exact library fork/version
            if hasattr(self.client, "get_all_orders"):
                all_orders = self.client.get_all_orders(symbol=symbol.upper(), limit=limit, recvWindow=5000)
            elif hasattr(self.client, "all_orders"): # Another common naming
                 all_orders = self.client.all_orders(symbol=symbol.upper(), limit=limit, recvWindow=5000)
            else:
                logger.error("Could not find a method like 'get_all_orders' or 'all_orders' on the client object.")
                return None

            if all_orders:
                logger.info(f"Found {len(all_orders)} total order(s) for {symbol.upper()} (last {limit}):")
                new_orders_count = 0
                for order in all_orders:
                    if order.get('status') == 'NEW':
                        new_orders_count += 1
                        logger.info(f"  OPEN Order (from all_orders): OrderID: {order['orderId']}, Type: {order['type']}, "
                                    f"Side: {order['side']}, Price: {order['price']}, StopPrice: {order.get('stopPrice','N/A')}, "
                                    f"Qty: {order['origQty']}, Status: {order['status']}")
                    # You can log other statuses too for debugging if needed
                    # else:
                    #    logger.debug(f"  Order (from all_orders): OrderID: {order['orderId']}, Status: {order['status']}")
                if new_orders_count == 0:
                    logger.info(f"No 'NEW' (open) orders found for {symbol.upper()} among the last {limit} orders.")

            else:
                logger.info(f"No orders found at all for {symbol.upper()} (last {limit}).")
            return all_orders
        except Exception as e:
            logger.error(f"Error fetching all orders for {symbol.upper()}: {e}", exc_info=True)
            return None


    def cancel_all_open_orders(self, symbol):
        logger.info(f"Attempting to cancel all open orders for {symbol.upper()}...")
        try:
            response = self.client.cancel_open_orders(symbol=symbol.upper(), recvWindow=5000)
            logger.info(f"Cancel all open orders response for {symbol.upper()}: {response}")
            if isinstance(response, list): 
                 logger.info(f"Successfully sent cancel all orders request. {len(response)} orders potentially cancelled.")
            return response
        except Exception as e:
            logger.error(f"Error cancelling all open orders for {symbol.upper()}: {e}", exc_info=True)
            if hasattr(e, 'error_code') and e.error_code == -2011: 
                logger.info(f"No open orders found for {symbol.upper()} to cancel (or specific order IDs were not found if used).")
                return {"status": "No open orders or error -2011"}
            return None
        

    def query_order(self, symbol, order_id=None, orig_client_order_id=None):
        """
        Queries a specific order by its orderId or origClientOrderId.
        One of order_id or orig_client_order_id must be provided.
        """
        if not order_id and not orig_client_order_id:
            msg = "Either order_id or orig_client_order_id must be provided to query an order."
            logger.error(msg)
            raise ValueError(msg)

        params = {
            'symbol': symbol.upper(),
            'recvWindow': 5000
        }
        if order_id:
            params['orderId'] = order_id
            logger.debug(f"Querying order for {symbol.upper()} by orderId: {order_id}")
        elif orig_client_order_id:
            params['origClientOrderId'] = orig_client_order_id
            logger.debug(f"Querying order for {symbol.upper()} by origClientOrderId: {orig_client_order_id}")
        
        try:
            order_info = self.client.query_order(**params)
            logger.info(f"Successfully queried order for {symbol.upper()}. Response: {order_info}")
            return order_info
        except Exception as e:
            logger.error(f"Error querying order for {symbol.upper()} (ID: {order_id or orig_client_order_id}): {e}", exc_info=True)
            return None
        
    def get_historical_klines(self, symbol, interval, limit=100, start_time=None, end_time=None):
        """
        Fetches historical klines (candlestick data) for a symbol.

        :param symbol: Trading symbol (e.g., "BTCUSDT")
        :param interval: Kline interval (e.g., "1m", "5m", "15m", "1h", "4h", "1d")
        :param limit: Number of klines to retrieve (default 100, max usually 1000 or 1500 by Binance).
        :param start_time: Optional. Timestamp in ms to get klines from (inclusive).
        :param end_time: Optional. Timestamp in ms to get klines until (inclusive).
        :return: List of kline data, or None if an error occurs.
                 Each kline is a list: [
                     open_time, open_price, high_price, low_price, close_price,
                     volume, close_time, quote_asset_volume, number_of_trades,
                     taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore
                 ]
                 All price/volume related fields are strings.
        """
        logger.debug(f"Fetching historical klines for {symbol.upper()} with interval {interval}, limit {limit}...")
        params = {
            'symbol': symbol.upper(),
            'interval': interval,
            'limit': limit
        }
        if start_time is not None: # Ensure None is not passed if not provided
            params['startTime'] = start_time
        if end_time is not None: # Ensure None is not passed if not provided
            params['endTime'] = end_time
        
        # Log parameters without None values for clarity if they were not provided
        active_params_log = {k: v for k, v in params.items() if v is not None}
        logger.debug(f"Parameters for klines API: {active_params_log}")
        
        try:
            # The UMFutures klines method directly returns the list of klines
            klines_data = self.client.klines(**params)
            if klines_data:
                logger.info(f"Successfully fetched {len(klines_data)} klines for {symbol.upper()} (interval: {interval}, limit: {limit}).")
                # logger.debug(f"Sample kline data (first kline): {klines_data[0]}")
            else:
                logger.info(f"No kline data returned for {symbol.upper()} (interval: {interval}, limit: {limit}) with params: {active_params_log}.")
            return klines_data
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol.upper()} interval {interval}: {e}", exc_info=True)
            return None
        
    def get_all_tickers_24hr(self):
        """
        Fetches 24-hour price change statistics for all available symbols
        using the ticker_24hr_price_change method.

        :return: List of ticker data dictionaries, or None if an error occurs.
        """
        method_name_to_use = "ticker_24hr_price_change"
        logger.debug(f"Fetching 24hr ticker statistics for ALL symbols using client.{method_name_to_use}(symbol=None)...")
        
        try:
            # Doğrudan ticker_24hr_price_change metodunu çağırıyoruz.
            # symbol=None argümanı, kütüphanenin tüm semboller için veri getirmesini sağlamalıdır.
            tickers_data = self.client.ticker_24hr_price_change(symbol=None) 
            
            if tickers_data:
                # API bazen boş liste yerine None döndürebilir veya tam tersi, bu yüzden her iki durumu da kontrol etmek iyidir.
                if isinstance(tickers_data, list):
                    logger.info(f"Successfully fetched 24hr ticker data for {len(tickers_data)} symbols using {method_name_to_use}.")
                    # logger.debug(f"Sample ticker data (first symbol): {tickers_data[0] if tickers_data else 'No data'}")
                else:
                    # Bu durum, API'nin beklenmedik bir formatta yanıt verdiğini gösterebilir.
                    logger.warning(f"Data received from {method_name_to_use} is not a list (type: {type(tickers_data)}). Data: {tickers_data}")
                    # Beklenmedik bir yanıt türü ise None döndürmek daha güvenli olabilir.
                    # Ancak kütüphane genellikle ya liste ya da hata döndürür. Şimdilik bu log yeterli.
            else:
                # None veya boş liste durumu
                logger.warning(f"No 24hr ticker data returned by {method_name_to_use} (received {type(tickers_data)}).")
            return tickers_data
        except AttributeError: # Eğer metot hala bulunamazsa bu hata yakalanır
            logger.error(f"AttributeError: Method '{method_name_to_use}' not found on client object (type: {type(self.client)}). "
                         "Please verify the method name in your installed library version.", exc_info=True)
            return None
        except Exception as e: # Diğer olası API veya ağ hataları için
            logger.error(f"Error fetching 24hr ticker data using {method_name_to_use}: {e}", exc_info=True)
            return None
            
if __name__ == '__main__':
    standalone_logger = setup_logger(name="trading_bot") 
    standalone_logger.info("--- Testing BinanceFuturesClient Standalone with Order Placement (SL & TP) ---")
    standalone_logger.info(f"Using settings for: {settings.TRADING_MODE} mode (loaded via settings.py).")
    standalone_logger.info("Ensure .env TRADING_MODE='TESTNET', and API keys are correct and NOT placeholders.")

    test_symbol = "BTCUSDT" 
    leverage_to_set = 10
    position_size_usdt_to_open = 1000 # Nominal position size in USDT
    order_side_to_open = "BUY"       # Open a LONG position

    try:
        client = BinanceFuturesClient() 
        standalone_logger.info("BinanceFuturesClient initialized.")

        standalone_logger.info(f"--- Step 0: Cancelling any existing open orders for {test_symbol} ---")
        client.cancel_all_open_orders(symbol=test_symbol)
        time.sleep(1)

        standalone_logger.info(f"--- Step 1: Setting leverage for {test_symbol} to {leverage_to_set}x ---")
        client.set_leverage(symbol=test_symbol, leverage=leverage_to_set)
        time.sleep(1) 

        standalone_logger.info(f"--- Step 2: Determining Stop-Loss & Take-Profit Prices for {test_symbol} ---")
        current_price = client.get_ticker_price(test_symbol)
        if not current_price:
            raise Exception(f"Could not get current price for {test_symbol} to set SL/TP.")

        if order_side_to_open == "BUY": # LONG
            stop_loss_trigger_price = current_price * 0.99 # Example: 1% below current price
            take_profit_trigger_price = current_price * 1.02 # Example: 2% above current price
        else: # SHORT
            stop_loss_trigger_price = current_price * 1.01 # Example: 1% above current price
            take_profit_trigger_price = current_price * 0.98 # Example: 2% below current price
        
        stop_loss_trigger_price = client._format_price(test_symbol, stop_loss_trigger_price)
        take_profit_trigger_price = client._format_price(test_symbol, take_profit_trigger_price)
        standalone_logger.info(f"Current Price: {current_price}. Calculated SL: {stop_loss_trigger_price}, TP: {take_profit_trigger_price}")

        standalone_logger.info(f"--- Step 3: Opening {order_side_to_open} position for {test_symbol} ({position_size_usdt_to_open} USDT size) with SL at {stop_loss_trigger_price} and TP at {take_profit_trigger_price} ---")
        entry_order, stop_order, tp_order = client.open_position_market_with_sl_tp( # Renamed function
            symbol=test_symbol,
            order_side=order_side_to_open,
            position_size_usdt=position_size_usdt_to_open,
            stop_loss_price=stop_loss_trigger_price,
            take_profit_price=take_profit_trigger_price # Added TP price
        )

        log_order_details = lambda ord_resp, ord_name: standalone_logger.info(f"{ord_name} Response: {ord_resp}") if ord_resp and isinstance(ord_resp, dict) and ord_resp.get('orderId') else standalone_logger.warning(f"{ord_name} FAILED or no proper response: {ord_resp}")
        
        log_order_details(entry_order, "Entry Order")
        log_order_details(stop_order, "Stop-Loss Order")
        log_order_details(tp_order, "Take-Profit Order") # Log TP order

        if entry_order and entry_order.get('status') == 'FILLED': 
            standalone_logger.info("--- Step 4: Fetching Position Information (waiting a few seconds for update) ---")
            time.sleep(5) 
            positions = client.get_position_info(test_symbol) # Assuming get_position_info is working now
            if positions: 
                for pos_info in positions: 
                    standalone_logger.info(f"Position Details: {pos_info}")
            elif positions == []: 
                 standalone_logger.info(f"No active position found for {test_symbol} after order placement.")
            else: 
                standalone_logger.warning(f"Could not retrieve position info for {test_symbol}, or an error occurred during fetch.")
        else:
            standalone_logger.warning(f"Skipping position info check as entry order was not confirmed as FILLED or failed. Entry order: {entry_order}")
        
        standalone_logger.info(f"--- Step 5: Fetching ALL Orders for {test_symbol} (and filtering for NEW) ---")
        try:
            all_orders_list = client.get_all_orders_for_symbol(test_symbol, limit=10) # Get last 10 orders
            # The method itself now logs the 'NEW' orders found.
            # You can add further processing here if needed.
            if all_orders_list is not None:
                standalone_logger.info(f"get_all_orders_for_symbol call completed for {test_symbol}.")
            else:
                standalone_logger.warning(f"get_all_orders_for_symbol call returned None for {test_symbol}.")

        except Exception as e_all_orders:
            standalone_logger.error(f"Error explicitly caught during get_all_orders_for_symbol call in __main__: {type(e_all_orders).__name__} - {e_all_orders}")


        standalone_logger.info(f"--- Step 6: Fetching Historical Klines for {test_symbol} ---")
        klines = client.get_historical_klines(symbol=test_symbol, interval="5m", limit=5)
        if klines:
            standalone_logger.info(f"Fetched last {len(klines)} klines (5m interval):")
            for kline in klines:
                # Kline format: [open_time, open, high, low, close, volume, close_time, ...]
                # Convert open_time to readable format (timestamp is in ms)
                import datetime
                open_time_readable = datetime.datetime.fromtimestamp(kline[0]/1000).strftime('%Y-%m-%d %H:%M:%S')
                standalone_logger.info(f"  Time: {open_time_readable}, Open: {kline[1]}, High: {kline[2]}, Low: {kline[3]}, Close: {kline[4]}, Volume: {kline[5]}")
        else:
            standalone_logger.warning(f"Could not fetch klines for {test_symbol}.")
            
    except ValueError as ve: # For config errors or formatting issues
        standalone_logger.critical(f"CONFIGURATION or VALUE ERROR: {ve}", exc_info=True) # Show traceback for ValueErrors too
    except Exception as e:
        standalone_logger.critical(f"An UNEXPECTED ERROR occurred during standalone test: {e}", exc_info=True)
    finally:
        logging.shutdown()