from abc import ABC, abstractmethod
from collections import namedtuple
from decimal import Decimal
from typing import List, Optional

from binance.client import Client

from automation.functions import parse_decimal
from automation.order import Order

SymbolInfo = namedtuple('SymbolInfo', 'quantity_precision, price_precision, min_notional')


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
    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        pass

    @abstractmethod
    def get_last_buy_order(self, symbol: str) -> Optional[Order]:
        pass

    def get_current_price(self, symbol: str) -> Decimal:
        info = self._client.get_symbol_ticker(symbol=symbol)

        return parse_decimal(info['price'])

    def check_min_notional(self, symbol: str, buy_price: Optional[Decimal], trade_amount: Decimal, targets_count: int,
                           stop_loss: Decimal) -> None:
        if buy_price is None:
            buy_price = self.get_current_price(symbol)

        target_quantity = trade_amount / buy_price / targets_count
        stop_loss_amount = target_quantity * stop_loss

        assert stop_loss_amount > self.get_symbol_info(symbol).min_notional, 'Trade amount is too small for stop loss'

    @classmethod
    def _get_target_quantities(cls, total_quantity: Decimal, targets_count: int, quantity_precision: int,
                               ) -> List[Decimal]:
        assert targets_count != 0
        trade_quantity = cls._round(total_quantity / targets_count, quantity_precision)
        quantities = [trade_quantity for _ in range(targets_count)]
        quantities[-1] = total_quantity - sum(quantities[:-1])

        return quantities

    @staticmethod
    def _round(num: Decimal, precision: int) -> Decimal:
        assert isinstance(num, Decimal)

        return round(num, precision)
