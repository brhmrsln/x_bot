# trading_bot/core/base_strategy.py
from abc import ABC, abstractmethod
import logging

class BaseStrategy(ABC):
    def __init__(self, client, strategy_params=None):
        self.client = client
        self.params = strategy_params or {}
        self.logger = logging.getLogger("trading_bot")
        self.validate_parameters()
        
    def validate_parameters(self):
        """Validates required strategy parameters"""
        required_params = self.get_required_parameters()
        missing = [p for p in required_params if p not in self.params]
        if missing:
            self.logger.error(f"Missing required parameters: {', '.join(missing)}")
            raise ValueError(f"Missing strategy parameters: {missing}")

    @abstractmethod
    def get_required_parameters(self):
        """Returns list of required parameter names"""
        return []
    
    @abstractmethod
    def generate_signal(self, symbol):
        """Generates trading signal for given symbol"""
        pass