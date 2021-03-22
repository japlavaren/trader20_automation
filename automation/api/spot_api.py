import math
from decimal import Decimal
from time import sleep
from typing import Dict, List, Optional, Tuple

from binance.client import Client

from automation.api.api import Api, SymbolInfo
from automation.functions import parse_decimal
from automation.order import Order


class SpotApi(Api):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._symbol_infos: Dict[str, SymbolInfo] = {}

    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        info = self._client.order_market_buy(
            symbol=symbol,
            quoteOrderQty=amount,
        )

        if info['status'] != Order.STATUS_FILLED:
            sleep(1)
            info = self._client.get_order(symbol=info['symbol'], orderId=info['orderId'])

        # price is zero in original response
        price = parse_decimal(info['cummulativeQuoteQty']) / parse_decimal(info['executedQty'])
        order = Order.from_dict(info, price=price, quantity_key='executedQty')
        assert order.status == Order.STATUS_FILLED, f'Got {order.status}'

        return order

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Order:
        symbol_info = self.get_symbol_info(symbol)
        quantity = self._round(amount / price, symbol_info.quantity_precision)
        info = self._client.order_limit_buy(
            symbol=symbol,
            price=price,
            quantity=quantity,
        )
        order = Order.from_dict(info, quantity_key='origQty')
        assert order.status == Order.STATUS_NEW, f'Got {order.status}'

        return order

    def market_sell(self, symbol: str, quantity: Decimal) -> Order:
        info = self._client.order_market_sell(
            symbol=symbol,
            quantity=quantity,
        )

        if info['status'] != Order.STATUS_FILLED:
            sleep(1)
            info = self._client.get_order(symbol=info['symbol'], orderId=info['orderId'])

        # price is zero in original response
        price = parse_decimal(info['cummulativeQuoteQty']) / parse_decimal(info['executedQty'])
        order = Order.from_dict(info, price=price, quantity_key='executedQty')
        assert order.status == Order.STATUS_FILLED, f'Got {order.status}'

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        symbol_info = self.get_symbol_info(symbol)
        stop_price = self._round(stop_loss * (1 + self._STOP_PRICE_CORRECTION), symbol_info.price_precision)
        quantities = self._get_target_quantities(quantity, len(targets), symbol_info.quantity_precision)

        for price, quantity in zip(targets, quantities):
            info = self._client.order_oco_sell(
                symbol=symbol,
                quantity=quantity,
                price=price,
                stopPrice=stop_price,
                stopLimitPrice=stop_loss,
                stopLimitTimeInForce=Client.TIME_IN_FORCE_FOK,
            )
            assert info['listStatusType'] == 'EXEC_STARTED', f'Got {info["listStatusType"]}'

    def get_oco_sell_orders(self, symbol: str) -> List[Tuple[Order, Order]]:
        all_orders = [Order.from_dict(info, quantity_key='origQty')
                      for info in self._client.get_open_orders(symbol=symbol)
                      if info['side'] == Order.SIDE_SELL and info['status'] == Order.STATUS_NEW
                      and info['type'] in (Order.TYPE_LIMIT_MAKER, Order.TYPE_STOP_LOSS_LIMIT)]
        all_orders.sort(key=lambda o: o.type)
        grouped: Dict[int, List[Order]] = {}

        for order in all_orders:
            if order.order_list_id is not None:
                grouped.setdefault(order.order_list_id, []).append(order)

        oco_orders = []

        for orders in grouped.values():
            if len(orders) == 2:
                limit_maker, stop_loss_limit = orders
                assert limit_maker.type == Order.TYPE_LIMIT_MAKER, f'Got {limit_maker.type}'
                assert stop_loss_limit.type == Order.TYPE_STOP_LOSS_LIMIT, f'Got {stop_loss_limit.type}'
                oco_orders.append((limit_maker, stop_loss_limit))

        return oco_orders

    def cancel_order(self, symbol: str, order_id: int) -> None:
        info = self._client.cancel_order(symbol=symbol, orderId=order_id)
        assert info['listStatusType'] == 'ALL_DONE', f'Got {info["listStatusType"]}'

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        if symbol not in self._symbol_infos:
            info = self._client.get_symbol_info(symbol=symbol)
            quantity_precision, price_precision, min_notional = None, None, None

            def parse(key: str) -> int:
                return int(round(-math.log(Decimal(f[key]), 10), 0))

            for f in info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    quantity_precision = parse('stepSize')
                elif f['filterType'] == 'PRICE_FILTER':
                    price_precision = parse('tickSize')
                elif f['filterType'] == 'MIN_NOTIONAL':
                    min_notional = parse_decimal(f['minNotional'])

            assert quantity_precision is not None and price_precision is not None and min_notional is not None
            self._symbol_infos[symbol] = SymbolInfo(quantity_precision, price_precision, min_notional)

        return self._symbol_infos[symbol]

    def get_sell_order_pnl(self, sell_order: Order) -> Optional[Decimal]:
        assert sell_order.side == Order.SIDE_SELL
        assert sell_order.status == Order.STATUS_FILLED
        buy_order = self._get_last_buy_order(sell_order.symbol)

        # sell quantity can not be bigger than buy quantity
        if buy_order is not None and sell_order.quantity <= buy_order.quantity:
            return (sell_order.price - buy_order.price) * sell_order.quantity
        else:
            return None

    def _get_last_buy_order(self, symbol: str) -> Optional[Order]:
        api_orders = self._client.get_all_orders(symbol=symbol)
        api_orders.sort(key=lambda o: o['updateTime'], reverse=True)

        for info in api_orders:
            if info['side'] == Order.SIDE_BUY and info['status'] == Order.STATUS_FILLED:
                # price is zero in original response
                price = parse_decimal(info['cummulativeQuoteQty']) / parse_decimal(info['executedQty'])

                return Order.from_dict(info, price=price, quantity_key='executedQty')
        else:
            return None
