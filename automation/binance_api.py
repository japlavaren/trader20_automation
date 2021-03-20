import math
from collections import namedtuple
from decimal import Decimal
from typing import Dict, List, Optional

from binance.client import Client

from automation.functions import parse_decimal
from automation.order import Order

Precision = namedtuple('Precision', 'quantity, price')


class BinanceApi:
    STOP_PRICE_CORRECTION = Decimal(0.5) / 100  # 0.5%

    def __init__(self, client: Client) -> None:
        self._client: Client = client
        self.__precisions: Dict[str, Precision] = {}

    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        precision = self.get_precision(symbol)
        info = self._client.order_market_buy(
            symbol=self._normalize_symbol(symbol),
            quoteOrderQty=self._round(amount, precision.price),
        )
        order = Order.from_dict(info, quantity_key='executedQty')
        order.price = parse_decimal(info['cummulativeQuoteQty']) / order.quantity  # price is zero in original response
        assert order.status == Order.STATUS_FILLED

        return order

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Order:
        quantity = amount / price
        precision = self.get_precision(symbol)
        info = self._client.order_limit_buy(
            symbol=self._normalize_symbol(symbol),
            price=self._round(price, precision.price),
            quantity=self._round(quantity, precision.quantity),
        )
        quantity_key = 'executedQty' if info['status'] == Order.STATUS_FILLED else 'origQty'
        order = Order.from_dict(info, quantity_key)
        assert order.status in (Order.STATUS_NEW, Order.STATUS_FILLED)

        return order

    def market_sell(self, symbol: str, total_quantity: Decimal) -> Order:
        info = self._client.order_market_sell(
            symbol=self._normalize_symbol(symbol),
            quantity=total_quantity,
        )
        order = Order.from_dict(info, quantity_key='executedQty')
        # price is zero in original response
        order.price = parse_decimal(info['cummulativeQuoteQty']) / order.quantity
        assert order.status == Order.STATUS_FILLED

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        precision = self.get_precision(symbol)
        quantities = self._get_target_quantities(quantity, len(targets), precision)
        stop_price = stop_loss * (1 + self.STOP_PRICE_CORRECTION)

        for price, quantity in zip(targets, quantities):
            info = self._client.order_oco_sell(
                symbol=self._normalize_symbol(symbol),
                quantity=quantity,
                price=self._round(price, precision.price),
                stopPrice=self._round(stop_price, precision.price),
                stopLimitPrice=self._round(stop_loss, precision.price),
                stopLimitTimeInForce=Client.TIME_IN_FORCE_FOK,
            )
            assert info['listStatusType'] == 'EXEC_STARTED'

    def get_last_buy_order(self, symbol: str) -> Optional[Order]:
        api_orders = self._client.get_all_orders(symbol=self._normalize_symbol(symbol))
        api_orders.sort(key=lambda o: o['updateTime'], reverse=True)

        for api_order in api_orders:
            if api_order['side'] == Order.SIDE_BUY and api_order['status'] == Order.STATUS_FILLED:
                order = Order.from_dict(api_order, quantity_key='executedQty')
                # price is zero in original response
                order.price = parse_decimal(api_order['cummulativeQuoteQty']) / order.quantity

                return order
        else:
            return None

    def get_oco_sell_orders(self, symbol: str) -> List[List[Order]]:
        all_orders = [Order.from_dict(info, 'origQty')
                      for info in self._client.get_open_orders(symbol=self._normalize_symbol(symbol))]
        all_orders.sort(key=lambda o: o.type)
        grouped: Dict[int, List[Order]] = {}

        for order in all_orders:
            if self._is_oco_sell_order(order):
                assert order.order_list_id is not None
                grouped.setdefault(order.order_list_id, []).append(order)

        oco_orders = list(grouped.values())

        for orders in oco_orders:
            assert len(orders) == 2
            assert orders[0].type == Order.TYPE_LIMIT_MAKER
            assert orders[1].type == Order.TYPE_STOP_LOSS_LIMIT

        return oco_orders

    @staticmethod
    def _is_oco_sell_order(order: Order) -> bool:
        return (order.side == Order.SIDE_SELL and order.status == Order.STATUS_NEW and order.order_list_id is not None
                and order.type in (Client.ORDER_TYPE_LIMIT_MAKER, Client.ORDER_TYPE_STOP_LOSS_LIMIT))

    def cancel_order(self, symbol: str, order_id: int) -> None:
        info = self._client.cancel_order(symbol=self._normalize_symbol(symbol), orderId=order_id)
        assert info['listStatusType'] == 'ALL_DONE'

    def get_precision(self, symbol: str) -> Precision:
        if symbol not in self.__precisions:
            info = self._client.get_symbol_info(symbol=self._normalize_symbol(symbol))
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

        return round(num, precision)

    @staticmethod
    def _normalize_symbol(symbol):
        return symbol.replace('/', '')
