import math
from collections import namedtuple
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from binance.client import Client

Precision = namedtuple('Precision', 'quantity, price')


class BinanceApi:
    STOP_PRICE_CORRECTION = Decimal(0.5) / 100  # 0.5%

    def __init__(self, client: Client) -> None:
        self._client: Client = client
        self.__precisions: Dict[str, Precision] = {}

    def market_buy(self, symbol: str, amount: Decimal) -> Tuple[Decimal, Decimal]:
        precision = self._get_precision(symbol)
        info = self._client.order_market_buy(
            symbol=symbol,
            quoteOrderQty=self._round(amount, precision.price),
        )
        assert info['status'] == 'FILLED', f'Got {info["status"]} status'
        quantity = Decimal(info['executedQty'])
        price = Decimal(info['cummulativeQuoteQty']) / quantity

        return quantity, price

    def market_sell(self, symbol: str, quantity: Decimal) -> Decimal:
        precision = self._get_precision(symbol)
        info = self._client.order_market_sell(
            symbol=symbol,
            quantity=self._round(quantity, precision.quantity),
        )
        assert info['status'] == 'FILLED', f'Got {info["status"]} status'
        total_price = Decimal(info['cummulativeQuoteQty'])
        price = total_price / Decimal(info['executedQty'])

        return price

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> None:
        quantity = amount / price
        precision = self._get_precision(symbol)
        info = self._client.order_limit_buy(
            symbol=symbol,
            price=self._round(price, precision.price),
            quantity=self._round(quantity, precision.quantity),
        )
        assert info['status'] in ('FILLED', 'NEW'), f'Got {info["status"]} status'

    def oco_sell(self, symbol: str, targets: List[Decimal], total_quantity: Decimal, stop_loss: Decimal) -> None:
        precision = self._get_precision(symbol)
        quantities = self._get_target_quantities(total_quantity, len(targets), precision)
        stop_price = stop_loss * (1 + self.STOP_PRICE_CORRECTION)

        for price, quantity in zip(targets, quantities):
            info = self._client.order_oco_sell(
                symbol=symbol,
                quantity=quantity,
                price=self._round(price, precision.price),
                stopPrice=self._round(stop_price, precision.price),
                stopLimitPrice=self._round(stop_loss, precision.price),
                stopLimitTimeInForce='FOK',
            )
            assert info['listStatusType'] == 'EXEC_STARTED'

    def get_oco_orders(self, symbol: str) -> List[Tuple[int, Decimal]]:
        all_orders = self._client.get_open_orders(symbol=symbol)
        sorted(all_orders, key=lambda o: o['type'])
        grouped_orders: Dict[int, List[Dict[str, Any]]] = {}
        oco_orders = []

        for order in all_orders:
            grouped_orders.setdefault(order['orderListId'], []).append(order)

        for orders in grouped_orders.values():
            if len(orders) == 2 and orders[0]['type'] == 'STOP_LOSS_LIMIT' and orders[1]['type'] == 'LIMIT_MAKER':
                oco_orders.append((orders[0]['orderId'], Decimal(orders[0]['origQty'])))

        return oco_orders

    def cancel_order(self, symbol: str, order_id: int) -> None:
        info = self._client.cancel_order(symbol=symbol, orderId=order_id)
        assert info['listStatusType'] == 'ALL_DONE'

    def _get_precision(self, symbol: str) -> Precision:
        if symbol not in self.__precisions:
            info = self._client.get_symbol_info(symbol)
            quantity, price = None, None

            def parse(key: str) -> int:
                return int(round(-math.log(Decimal(f[key]), 10), 0))

            for f in info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    quantity = parse('stepSize')
                elif f['filterType'] == 'PRICE_FILTER':
                    price = parse('tickSize')

            assert quantity is not None, 'Unknown quantity precision'
            assert price is not None, 'Unknown price precision'
            self.__precisions[symbol] = Precision(quantity, price)

        return self.__precisions[symbol]

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

        return Decimal(round(num, precision))
