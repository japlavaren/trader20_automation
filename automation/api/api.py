from abc import ABC, abstractmethod
from collections import namedtuple
from decimal import Decimal
from typing import List, Optional, Tuple

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
    def get_sell_order_pnl(self, sell_order: Order) -> Optional[Decimal]:
        pass

    def get_current_price(self, symbol: str) -> Decimal:
        info = self._client.get_symbol_ticker(symbol=symbol)

        return parse_decimal(info['price'])

    def check_min_notional(self, symbol: str, buy_price: Decimal, amount: Decimal,
                           targets: List[Decimal], stop_loss: Decimal, futures: bool) -> None:
        target_amounts, stop_loss_amount = self.get_buy_order_amounts(symbol, amount, buy_price, targets, stop_loss,
                                                                      futures)
        min_notional = self.get_symbol_info(symbol).min_notional

        for target_amount in target_amounts:
            assert target_amount > min_notional, 'Trade amount is too small for target'

        assert stop_loss_amount > min_notional, 'Trade amount is too small for stop loss'

    def get_buy_order_amounts(self, symbol: str, amount: Decimal, buy_price: Decimal, targets: List[Decimal],
                              stop_loss: Decimal, futures: bool) -> Tuple[List[Decimal], Decimal]:
        symbol_info = self.get_symbol_info(symbol)
        total_quantity = self._round(amount / buy_price, symbol_info.quantity_precision)
        target_quantities = self._get_target_quantities(total_quantity, len(targets), symbol_info.quantity_precision)
        target_amounts = [self._round(target * quantity, symbol_info.price_precision)
                          for target, quantity in zip(targets, target_quantities)]

        if futures:
            # for futures there is one stop order which close all position
            stop_loss_amount = self._round(total_quantity * stop_loss, symbol_info.price_precision)
        else:
            # for spot there is stop OCO order for every target
            stop_loss_amount = min([self._round(stop_loss * quantity, symbol_info.price_precision)
                                    for quantity in target_quantities])

        return target_amounts, stop_loss_amount

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
