from decimal import Decimal
from time import time
from typing import Dict, List, Optional, Set
from uuid import uuid4

from binance.client import Client
from binance.exceptions import BinanceAPIException

from automation.api.api import Api, Precision
from automation.functions import parse_decimal, precision_round
from automation.order import Order


class FuturesApi(Api):
    MARGIN_TYPE_ISOLATED = 'ISOLATED'
    MARGIN_TYPE_CROSS = 'CROSS'

    _NO_NEED_TO_CHANGE_MARGIN = -4046

    def __init__(self, margin_type: str, client: Client) -> None:
        assert margin_type in (self.MARGIN_TYPE_ISOLATED, self.MARGIN_TYPE_CROSS)
        super().__init__(client)
        self._margin_type: str = margin_type
        self._leverage: Optional[int] = None
        self._precisions: Dict[str, Precision] = {}
        self._futures_symbols: Set[str] = set()

    @property
    def leverage(self) -> int:
        assert self._leverage is not None
        leverage, self._leverage = self._leverage, None  # reset after use

        return leverage

    @leverage.setter
    def leverage(self, leverage: int):
        self.leverage = leverage

    @property
    def futures_symbols(self) -> Set[str]:
        if len(self._futures_symbols) == 0:
            info = self._client.futures_exchange_info()

            for symbol_info in info['symbols']:
                symbol = symbol_info['symbol']
                self._futures_symbols.add(symbol)
                self._precisions[symbol] = Precision(int(symbol_info['quantityPrecision']),
                                                     int(symbol_info['pricePrecision']))

        return self._futures_symbols

    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        self._set_futures_settings(symbol, self.leverage)
        precision = self._get_precision(symbol)
        price = self._get_current_price(symbol)
        quantity = precision_round(amount / price, precision.quantity)
        info = self._client.futures_create_order(
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            symbol=symbol,
            quantity=quantity,
            timestamp=self._timestamp,
        )
        order = Order.from_dict(info, quantity_key='executedQty', futures=True)
        a = 1  # TODO check price is not zero
        assert order.status == Order.STATUS_FILLED

        return order

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Order:
        self._set_futures_settings(symbol, self.leverage)
        precision = self._get_precision(symbol)
        quantity = precision_round(amount / price, precision.quantity)
        info = self._client.futures_create_order(
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_LIMIT,
            symbol=symbol,
            price=price,
            quantity=quantity,
            timestamp=self._timestamp,
            timeInForce=Client.TIME_IN_FORCE_GTC,
        )
        quantity_key = 'executedQty' if info['status'] == Order.STATUS_FILLED else 'origQty'
        order = Order.from_dict(info, quantity_key, futures=True)
        assert order.status in (Order.STATUS_NEW, Order.STATUS_FILLED)

        return order

    def market_sell(self, symbol: str, quantity: Decimal) -> Order:
        info = self._client.futures_create_order(
            side=Client.SIDE_SELL,
            type=Client.ORDER_TYPE_MARKET,
            symbol=symbol,
            quantity=quantity,
            timestamp=self._timestamp,
        )
        order = Order.from_dict(info, quantity_key='executedQty', futures=True)
        a = 1  # TODO check price is not zero
        assert order.status == Order.STATUS_FILLED

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        precision = self._get_precision(symbol)
        stop_price = precision_round(stop_loss, precision.price)

        for price, quantity in zip(targets, self._get_target_quantities(quantity, len(targets), precision)):
            client_order_id = uuid4().hex
            self._stop_market(client_order_id, symbol, quantity, stop_price)
            self._take_profit_market(client_order_id, symbol, quantity, price)

    def _stop_market(self, client_order_id: str, symbol: str, quantity: Decimal, stop_price: Decimal) -> None:
        info = self._client.futures_create_order(
            newClientOrderId=client_order_id,
            side=Client.SIDE_SELL,
            type='STOP_MARKET',
            symbol=symbol,
            quantity=quantity,
            stopPrice=stop_price,
        )
        a = 1  # TODO assert state

    def _take_profit_market(self, client_order_id: str, symbol: str, quantity: Decimal, price: Decimal) -> None:
        info = self._client.futures_create_order(
            newClientOrderId=client_order_id,
            side=Client.SIDE_SELL,
            type='TAKE_PROFIT_MARKET',
            symbol=symbol,
            quantity=quantity,
            stopPrice=price,
        )
        a = 1  # TODO assert state

    def get_oco_sell_orders(self, symbol: str) -> List[List[Order]]:
        raise NotImplementedError()
        # o = self._client.futures_get_open_orders(symbol=symbol)
        # a=1

    def cancel_order(self, symbol: str, order_id: int) -> None:
        raise NotImplementedError()

    @property
    def _timestamp(self) -> int:
        return int(time() * 1000)

    def _set_futures_settings(self, symbol: str, leverage: int) -> None:
        try:
            self._client.futures_change_margin_type(symbol=symbol, marginType=self._margin_type)
        except BinanceAPIException as e:
            if e.code != self._NO_NEED_TO_CHANGE_MARGIN:
                raise

        self._client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def _get_current_price(self, symbol: str) -> Decimal:
        info = self._client.get_symbol_ticker(symbol=symbol)

        return parse_decimal(info['price'])

    def _get_precision(self, symbol: str) -> Precision:
        if len(self._precisions) == 0:
            _ = self.futures_symbols  # load symbols and precisions

        return self._precisions[symbol]
