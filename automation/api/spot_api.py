import math
from decimal import Decimal
from typing import Dict, List, Optional

from binance.client import Client

from automation.api.api import Api, Precision
from automation.functions import parse_decimal, precision_round
from automation.order import Order


class SpotApi(Api):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._precisions: Dict[str, Precision] = {}

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

    def market_sell(self, symbol: str, quantity: Decimal) -> Order:
        info = self._client.order_market_sell(
            symbol=symbol,
            quantity=quantity,
        )
        order = Order.from_dict(info, quantity_key='executedQty')
        assert order.status == Order.STATUS_FILLED

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        precision = self._get_precision(symbol)
        stop_price = precision_round(stop_loss * (1 + self._STOP_PRICE_CORRECTION), precision.price)
        stop_limit_price = precision_round(stop_loss, precision.price)

        for price, quantity in zip(targets, self._get_target_quantities(quantity, len(targets), precision)):
            info = self._client.order_oco_sell(
                symbol=symbol,
                quantity=quantity,
                price=price,
                stopPrice=stop_price,
                stopLimitPrice=stop_limit_price,
                stopLimitTimeInForce=Client.TIME_IN_FORCE_FOK,
            )
            assert info['listStatusType'] == 'EXEC_STARTED'

    def get_spot_last_buy_order(self, symbol: str) -> Optional[Order]:
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
        all_orders = [Order.from_dict(info, quantity_key='origQty')
                      for info in self._client.get_open_orders(symbol=symbol)]
        all_orders.sort(key=lambda o: o.type)
        grouped_filtered: Dict[int, List[Order]] = {}

        for order in all_orders:
            if self._is_oco_sell_order(order):
                assert order.order_list_id is not None
                grouped_filtered.setdefault(order.order_list_id, []).append(order)

        oco_orders = list(grouped_filtered.values())

        for orders in oco_orders:
            assert len(orders) == 2
            assert orders[0].type == Order.TYPE_LIMIT_MAKER
            assert orders[1].type == Order.TYPE_STOP_LOSS_LIMIT

        return oco_orders

    def cancel_order(self, symbol: str, order_id: int) -> None:
        info = self._client.cancel_order(symbol=symbol, orderId=order_id)
        assert info['listStatusType'] == 'ALL_DONE'

    @staticmethod
    def _is_oco_sell_order(order: Order) -> bool:
        return (order.side == Order.SIDE_SELL and order.status == Order.STATUS_NEW
                and order.type in (Client.ORDER_TYPE_LIMIT_MAKER, Client.ORDER_TYPE_STOP_LOSS_LIMIT))

    def _get_precision(self, symbol: str) -> Precision:
        if symbol not in self._precisions:
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
            self._precisions[symbol] = Precision(quantity, price)

        return self._precisions[symbol]
