from decimal import Decimal
from time import sleep
from typing import Dict, List, Optional
from uuid import uuid4

from binance.client import Client
from binance.exceptions import BinanceAPIException

from automation.api.api import Api, SymbolInfo
from automation.functions import parse_decimal
from automation.order import Order


class FuturesApi(Api):
    MARGIN_TYPE_ISOLATED = 'ISOLATED'
    MARGIN_TYPE_CROSS = 'CROSS'

    _OCO_STOP_MARKET = 'OCO-SM'
    _OCO_TAKE_PROFIT_MARKET = 'OCO-TPM'

    _NO_NEED_TO_CHANGE_MARGIN = -4046

    def __init__(self, margin_type: str, client: Client) -> None:
        assert margin_type in (self.MARGIN_TYPE_ISOLATED, self.MARGIN_TYPE_CROSS)
        super().__init__(client)
        self._margin_type: str = margin_type
        self._leverage: Optional[int] = None
        self._symbol_infos: Dict[str, SymbolInfo] = {}

    @property
    def leverage(self) -> int:
        assert self._leverage is not None
        leverage, self._leverage = self._leverage, None  # reset after use

        return leverage

    @leverage.setter
    def leverage(self, leverage: int):
        self._leverage = leverage

    def is_futures(self, symbol: str) -> bool:
        if len(self._symbol_infos) == 0:
            info = self._client.futures_exchange_info()

            for symbol_info in info['symbols']:
                min_notional = [parse_decimal(f['notional']) for f in symbol_info['filters']
                                if f['filterType'] == 'MIN_NOTIONAL'][0]
                self._symbol_infos[symbol_info['symbol']] = SymbolInfo(int(symbol_info['quantityPrecision']),
                                                                       int(symbol_info['pricePrecision']),
                                                                       min_notional)

        return symbol in self._symbol_infos.keys()

    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        self._check_has_orders(symbol)
        self._set_futures_settings(symbol, self.leverage)
        symbol_info = self.get_symbol_info(symbol)
        price = self.get_current_price(symbol)
        quantity = self._round(amount / price, symbol_info.quantity_precision)
        info = self._client.futures_create_order(
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            symbol=symbol,
            quantity=quantity,
        )

        if info['status'] != Order.STATUS_FILLED:
            sleep(1)
            info = self._client.futures_get_order(symbol=info['symbol'], orderId=info['orderId'])

        order = Order.from_dict(info, quantity_key='executedQty', price_key='avgPrice', futures=True)
        assert order.status == Order.STATUS_FILLED

        return order

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Order:
        self._check_has_orders(symbol)
        self._set_futures_settings(symbol, self.leverage)
        symbol_info = self.get_symbol_info(symbol)
        quantity = self._round(amount / price, symbol_info.quantity_precision)
        info = self._client.futures_create_order(
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_LIMIT,
            symbol=symbol,
            price=price,
            quantity=quantity,
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
        )

        if info['status'] != Order.STATUS_FILLED:
            sleep(1)
            info = self._client.futures_get_order(symbol=info['symbol'], orderId=info['orderId'])

        order = Order.from_dict(info, quantity_key='executedQty', price_key='avgPrice', futures=True)
        assert order.status == Order.STATUS_FILLED

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        symbol_info = self.get_symbol_info(symbol)
        quantities = self._get_target_quantities(quantity, len(targets), symbol_info.quantity_precision)

        for price, quantity in zip(targets, quantities):
            identifier = uuid4().hex[:20]
            self._stop(identifier, symbol, quantity, stop_loss)
            self._take_profit(identifier, symbol, quantity, price)

    def _stop(self, identifier: str, symbol: str, quantity: Decimal, stop_loss: Decimal) -> None:
        symbol_info = self.get_symbol_info(symbol)
        stop_price = self._round(stop_loss * (1 + self._STOP_PRICE_CORRECTION), symbol_info.price_precision)  # +0.5%
        info = self._client.futures_create_order(
            newClientOrderId=f'{self._OCO_STOP_MARKET}-{identifier}',
            side=Client.SIDE_SELL,
            type=Order.TYPE_STOP,
            symbol=symbol,
            quantity=quantity,
            stopPrice=stop_price,
            price=stop_loss,
        )
        assert info['status'] == Order.STATUS_NEW

    def _take_profit(self, identifier: str, symbol: str, quantity: Decimal, price: Decimal) -> None:
        symbol_info = self.get_symbol_info(symbol)
        stop_price = self._round(price / (1 + self._STOP_PRICE_CORRECTION), symbol_info.price_precision)  # -0.5%
        info = self._client.futures_create_order(
            newClientOrderId=f'{self._OCO_TAKE_PROFIT_MARKET}-{identifier}',
            side=Client.SIDE_SELL,
            type=Order.TYPE_TAKE_PROFIT,
            symbol=symbol,
            quantity=quantity,
            stopPrice=stop_price,
            price=price,
        )
        assert info['status'] == Order.STATUS_NEW

    def get_oco_sell_orders(self, symbol: str) -> List[List[Order]]:
        all_orders = [Order.from_dict(info, quantity_key='origQty', price_key='stopPrice', futures=True)
                      for info in self._client.futures_get_open_orders(symbol=symbol)]
        all_orders.sort(key=lambda o: o.type, reverse=True)
        grouped_filtered: Dict[str, List[Order]] = {}

        for order in all_orders:
            if self._is_oco_sell_order(order):
                key = order.client_order_id.replace(self._OCO_TAKE_PROFIT_MARKET, '').replace(self._OCO_STOP_MARKET, '')
                grouped_filtered.setdefault(key, []).append(order)

        oco_orders = list(grouped_filtered.values())
        oco_types = [Order.TYPE_TAKE_PROFIT_MARKET, Order.TYPE_STOP_MARKET]

        for orders in oco_orders:
            assert [order.type for order in orders] == oco_types

        return oco_orders

    def cancel_oco_orders(self, symbol, client_order_id: str) -> None:
        all_orders = [Order.from_dict(info, quantity_key='origQty', price_key='stopPrice', futures=True)
                      for info in self._client.futures_get_open_orders(symbol=symbol)]
        identifier = client_order_id.replace(self._OCO_TAKE_PROFIT_MARKET, '').replace(self._OCO_STOP_MARKET, '')

        for order in all_orders:
            if order.client_order_id.endswith(identifier):
                self.cancel_order(order.symbol, order.order_id)

    def cancel_order(self, symbol: str, order_id: int) -> None:
        info = self._client.futures_cancel_order(symbol=symbol, orderId=order_id)
        assert info['status'] == Order.STATUS_CANCELED

    def get_last_buy_order(self, symbol: str) -> Optional[Order]:
        api_orders = self._client.futures_get_all_orders(symbol=symbol)
        api_orders.sort(key=lambda o: o['updateTime'], reverse=True)

        for api_order in api_orders:
            if api_order['side'] == Order.SIDE_BUY and api_order['status'] == Order.STATUS_FILLED:
                return Order.from_dict(api_order, quantity_key='executedQty', price_key='avgPrice', futures=True)
        else:
            return None

    def get_available_balance(self, currency: str) -> Decimal:
        # client futures_account_balance() is pointing to v1 and we need v2 call
        uri = self._client._create_futures_api_uri('balance').replace('v1', 'v2')
        info = self._client._request('get', uri, signed=True, data={})
        balances = [parse_decimal(balance['availableBalance']) for balance in info if balance['asset'] == currency]
        assert len(balances) == 1

        return balances[0]

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        return self._symbol_infos[symbol]

    @classmethod
    def _is_oco_sell_order(cls, order: Order) -> bool:
        return (order.side == Order.SIDE_SELL and order.status == Order.STATUS_NEW
                and order.type in (Order.TYPE_TAKE_PROFIT_MARKET, Order.TYPE_STOP_MARKET)
                and (order.client_order_id.startswith(cls._OCO_TAKE_PROFIT_MARKET)
                     or order.client_order_id.startswith(cls._OCO_STOP_MARKET)))

    def _check_has_orders(self, symbol: str) -> None:
        open_orders = self._client.futures_get_open_orders(symbol=symbol)
        assert len(open_orders) == 0, f'{symbol} has open future order'
        assert self._has_none_open_position(symbol), f'{symbol} has open future position'

    def _set_futures_settings(self, symbol: str, leverage: int) -> None:
        try:
            self._client.futures_change_margin_type(symbol=symbol, marginType=self._margin_type)
        except BinanceAPIException as e:
            if e.code != self._NO_NEED_TO_CHANGE_MARGIN:
                raise

        self._client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def _has_none_open_position(self, symbol: str) -> bool:
        open_positions = self._client.futures_position_information(symbol=symbol)

        # there can be always one open position with zero positionAmt and notional even if there is no position open
        return (len(open_positions) == 0 or (len(open_positions) == 1 and open_positions[0]['positionAmt'] == '0.0'
                                             and open_positions[0]['notional'] == '0'))
