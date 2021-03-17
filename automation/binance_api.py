import math
from collections import namedtuple
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from binance.client import Client

from automation.trade import Order, Trade

Precision = namedtuple('Precision', 'quantity, price')


class BinanceApi:
    STOP_PRICE_CORRECTION = Decimal(0.5) / 100  # 0.5%

    def __init__(self, client: Client) -> None:
        self._client: Client = client
        self.__precisions: Dict[str, Precision] = {}

    def market_buy(self, symbol: str, amount: Decimal) -> Trade:
        precision = self._get_precision(symbol)
        info = self._client.order_market_buy(
            symbol=symbol,
            quoteOrderQty=self._round(amount, precision.price),
        )
        assert info['status'] == Client.ORDER_STATUS_FILLED, f'Got {info["status"]} status'
        bought_quantity = self._parse_decimal(info['executedQty'])
        bought_amount = self._parse_decimal(info['cummulativeQuoteQty'])
        buy_price = self._round(bought_amount / bought_quantity, precision.price)

        return Trade(Order(info['symbol'], info['side'], info['type'], info['status'], info['orderId'],
                           bought_quantity, buy_price))

    def market_sell(self, symbol: str, quantity: Decimal) -> Decimal:
        precision = self._get_precision(symbol)
        info = self._client.order_market_sell(
            symbol=symbol,
            quantity=self._round(quantity, precision.quantity),
        )
        assert info['status'] == Client.ORDER_STATUS_FILLED, f'Got {info["status"]} status'
        sold_amount = self._parse_decimal(info['cummulativeQuoteQty'])
        sold_quantity = self._parse_decimal(info['executedQty'])
        sell_price = self._round(sold_amount / sold_quantity, precision.price)

        return sell_price

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Trade:
        quantity = amount / price
        precision = self._get_precision(symbol)
        info = self._client.order_limit_buy(
            symbol=symbol,
            price=self._round(price, precision.price),
            quantity=self._round(quantity, precision.quantity),
        )

        return Trade(Order(info['symbol'], info['side'], info['type'], info['status'], info['orderId'],
                           quantity=self._parse_decimal(info['origQty']), price=self._parse_decimal(info['price'])))

    def oco_sell(self, trade: Trade, targets: List[Decimal], stop_loss: Decimal) -> None:
        buy_order = trade.buy_order
        assert buy_order.status == Order.STATUS_FILLED
        precision = self._get_precision(buy_order.symbol)
        quantities = self._get_target_quantities(buy_order.quantity, len(targets), precision)
        stop_price = stop_loss * (1 + self.STOP_PRICE_CORRECTION)

        for price, quantity in zip(targets, quantities):
            oco_info = self._client.order_oco_sell(
                symbol=buy_order.symbol,
                quantity=quantity,
                price=self._round(price, precision.price),
                stopPrice=self._round(stop_price, precision.price),
                stopLimitPrice=self._round(stop_loss, precision.price),
                stopLimitTimeInForce=Client.TIME_IN_FORCE_FOK,
            )
            assert oco_info['listStatusType'] == 'EXEC_STARTED'

            for info in oco_info['orderReports']:
                stop_price_value = self._parse_decimal(info['stopPrice']) if 'stopPrice' in info else None
                trade.add_sell_order(Order(info['symbol'], info['side'], info['type'], info['status'], info['orderId'],
                                           self._parse_decimal(info['origQty']), self._parse_decimal(info['price']),
                                           stop_price_value))

    def get_oco_orders(self, symbol: str) -> List[Tuple[Order, Order]]:
        all_orders = self._client.get_open_orders(symbol=symbol)
        all_orders.sort(key=lambda o: o['type'])
        grouped_orders: Dict[int, List[Dict[str, Any]]] = {}
        oco_orders = []

        for order in all_orders:
            grouped_orders.setdefault(order['orderListId'], []).append(order)

        oco_order_types = Client.ORDER_TYPE_LIMIT_MAKER, Client.ORDER_TYPE_STOP_LOSS_LIMIT

        for orders in grouped_orders.values():
            if len(orders) == 2 and (orders[0]['type'], orders[1]['type']) == oco_order_types:
                first, second = orders[0], orders[1]
                limit_maker = Order(first['symbol'], first['side'], first['type'], first['status'], first['orderId'],
                                    quantity=self._parse_decimal(first['origQty']),
                                    price=self._parse_decimal(first['price']))
                stop_loss_limit = Order(second['symbol'], second['side'], second['type'], second['status'],
                                        second['orderId'],
                                        quantity=self._parse_decimal(second['origQty']),
                                        price=self._parse_decimal(second['price']),
                                        stop_price=self._parse_decimal(second['stopPrice']))
                oco_orders.append((limit_maker, stop_loss_limit))

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

        return round(num, precision)

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        if '.' in value:
            value = value.rstrip('0')

        return Decimal(value)
