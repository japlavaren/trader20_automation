from abc import ABC, abstractmethod
from collections import namedtuple
from decimal import Decimal
from typing import List, Optional

from binance.client import Client

from automation.order import Order

Precision = namedtuple('Precision', 'quantity, price')


class Api(ABC):
    _STOP_PRICE_CORRECTION = Decimal(0.5) / 100  # 0.5%

    def __init__(self, client: Client) -> None:
        self._client: Client = client

    @abstractmethod
    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        pass

    @abstractmethod
    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Order:
        pass

    @abstractmethod
    def market_sell(self, symbol: str, total_quantity: Decimal) -> Order:
        pass

    @abstractmethod
    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        pass

    @abstractmethod
    def get_oco_sell_orders(self, symbol: str) -> List[List[Order]]:
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: int) -> None:
        pass

    @abstractmethod
    def get_precision(self, symbol: str) -> Precision:
        pass

    @abstractmethod
    def get_last_buy_order(self, symbol: str) -> Optional[Order]:
        pass

    @classmethod
    def _get_target_quantities(cls, total_quantity: Decimal, targets_count: int, precision: Precision) -> List[Decimal]:
        assert targets_count != 0
        trade_quantity = cls._round(total_quantity / targets_count, precision.quantity)
        quantities = [trade_quantity for _ in range(targets_count)]
        quantities[-1] = total_quantity - sum(quantities[:-1])

        return quantities

    @staticmethod
    def _round(num: Decimal, precision: int) -> Decimal:
        assert isinstance(num, Decimal)

        return round(num, precision)

    @staticmethod
    def _normalize_symbol(symbol):
        return symbol.replace('/', '')
