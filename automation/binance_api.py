import math
from collections import namedtuple
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from binance.client import Client

from automation.functions import parse_decimal, precision_round
from automation.order import Order

Precision = namedtuple('Precision', 'quantity, price')


class BinanceApi:
    STOP_PRICE_CORRECTION = Decimal(0.5) / 100  # 0.5%

    def __init__(self, client: Client) -> None:
        self._client: Client = client
        self.__precisions: Dict[str, Precision] = {}

    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        precision = self._get_precision(symbol)
        info = self._client.order_market_buy(
            symbol=symbol,
            quoteOrderQty=precision_round(amount, precision.price),
        )
        order = Order.from_dict(info, quantity_key='executedQty')
        order.price = parse_decimal(info['cummulativeQuoteQty']) / order.quantity  # price is zero in original response
        assert order.status == Order.STATUS_FILLED

        return order

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Order:
        quantity = amount / price
        precision = self._get_precision(symbol)
        info = self._client.order_limit_buy(
            symbol=symbol,
            price=precision_round(price, precision.price),
            quantity=precision_round(quantity, precision.quantity),
        )
        quantity_key = 'executedQty' if info['status'] == Order.STATUS_FILLED else 'origQty'
        order = Order.from_dict(info, quantity_key)
        assert order.status in (Order.STATUS_NEW, Order.STATUS_FILLED)

        return order

    def market_sell(self, symbol: str, total_quantity: Decimal) -> Order:
        precision = self._get_precision(symbol)
        info = self._client.order_market_sell(
            symbol=symbol,
            quantity=precision_round(total_quantity, precision.quantity),
        )
        order = Order.from_dict(info, quantity_key='executedQty')
        assert order.status == Order.STATUS_FILLED

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        precision = self._get_precision(symbol)
        quantities = self._get_target_quantities(quantity, len(targets), precision)
        stop_price = stop_loss * (1 + self.STOP_PRICE_CORRECTION)

        for price, quantity in zip(targets, quantities):
            info = self._client.order_oco_sell(
                symbol=symbol,
                quantity=quantity,
                price=precision_round(price, precision.price),
                stopPrice=precision_round(stop_price, precision.price),
                stopLimitPrice=precision_round(stop_loss, precision.price),
                stopLimitTimeInForce=Client.TIME_IN_FORCE_FOK,
            )
            assert info['listStatusType'] == 'EXEC_STARTED'

    def get_last_buy_order(self, symbol: str) -> Optional[Order]:
        api_orders = self._client.get_all_orders(symbol=symbol)
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
        all_orders = [Order.from_dict(info, 'origQty') for info in self._client.get_open_orders(symbol=symbol)]
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

    @staticmethod
    def _get_target_quantities(total_quantity: Decimal, targets_count: int, precision: Precision) -> List[Decimal]:
        assert targets_count != 0
        trade_quantity = precision_round(total_quantity / targets_count, precision.quantity)
        quantities = [trade_quantity for _ in range(targets_count)]
        quantities[-1] = total_quantity - sum(quantities[:-1])

        return quantities
