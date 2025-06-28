# trading_bot/core/base_strategy.py

from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    def __init__(self, params: dict):
        self.params = params
        self.validate_parameters()

    @abstractmethod
    def get_required_parameters(self):
        """
        Stratejinin ihtiyaç duyduğu parametrelerin bir haritasını döndürmelidir.
        Bu metodun @staticmethod olması beklenir.
        """
        pass

    def validate_parameters(self):
        """Gerekli tüm parametrelerin self.params içinde olup olmadığını kontrol eder."""
        required = self.get_required_parameters()
        missing = [key for key in required.keys() if key not in self.params]
        if missing:
            raise ValueError(f"Missing strategy parameters: {missing}")

    # generate_signal metodu stratejiye özel olduğu için burada sadece abstract olarak kalabilir.
    # Ancak mevcut yapıda trading_engine içinde çağrıldığı için burada olmasına gerek yok.