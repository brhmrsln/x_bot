# trading_bot/core/strategy_factory.py

from trading_bot.core.simple_ema_crossover_strategy import SimpleEmaCrossoverStrategy # BU SATIRI EKLE

def StrategyFactory(strategy_name: str):
    """
    Verilen strateji ismine göre ilgili strateji SINIFINI döndürür.
    """
    if strategy_name == "simple_ema_crossover": # BU İKİ SATIRI EKLE
        return SimpleEmaCrossoverStrategy
    else:
        raise ValueError(f"Bilinmeyen strateji: '{strategy_name}'. Lütfen .env dosyasını kontrol edin.")