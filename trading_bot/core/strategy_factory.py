# trading_bot/core/strategy_factory.py
import logging
from .mean_reversion_strategy import MeanReversionStrategy

logger = logging.getLogger("trading_bot")

class StrategyFactory:
    STRATEGIES = {
        "mean_reversion": MeanReversionStrategy
    }

    @staticmethod
    def create_strategy(strategy_name, client, strategy_params):
        strategy_class = StrategyFactory.STRATEGIES.get(strategy_name)
        if not strategy_class:
            logger.error(f"Unknown strategy: {strategy_name}")
            raise ValueError(f"Invalid strategy name: {strategy_name}")
        return strategy_class(client, strategy_params)