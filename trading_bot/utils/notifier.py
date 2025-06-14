# trading_bot/utils/notifier.py
import requests
import logging
from trading_bot.config import settings

logger = logging.getLogger("trading_bot")

def send_telegram_message(message: str):
    """Sends a message to the configured Telegram chat."""
    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not bot_token or not chat_id:
        logger.debug("Telegram BOT_TOKEN or CHAT_ID not configured. Skipping notification.")
        return False

    # Using MarkdownV2 for better formatting. Note that some characters must be escaped.
    # Characters that must be escaped: _ * [ ] ( ) ~ ` > # + - = | { } . !
    # We will create a helper function for this if complex messages are needed.
    # For now, we will send simple messages.
    # A more robust implementation would use a Telegram library or handle formatting better.
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status() # Raises an exception for bad status codes (4xx or 5xx)
        logger.debug(f"Successfully sent Telegram message: {message}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}", exc_info=False) # exc_info=False to keep log clean
        return False