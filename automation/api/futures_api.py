from decimal import Decimal
from time import sleep
from typing import Dict, List, Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException

from automation.api.api import Api, SymbolInfo
from automation.functions import parse_decimal
from automation.order import Order


class FuturesApi(Api):
    MARGIN_TYPE_ISOLATED = 'ISOLATED'
    MARGIN_TYPE_CROSS = 'CROSS'

    _NO_NEED_TO_CHANGE_MARGIN = -4046

    def __init__(self, margin_type: str, *args, **kwargs) -> None:
        assert margin_type in (self.MARGIN_TYPE_ISOLATED, self.MARGIN_TYPE_CROSS)
        super().__init__(*args, **kwargs)
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
        self._load_symbol_infos()

        return symbol in self._symbol_infos.keys()

    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        self._set_futures_settings(symbol, self.leverage)
        symbol_info = self.get_symbol_info(symbol)
        price = self.get_current_price(symbol)
        quantity = self._round(amount / price, symbol_info.quantity_precision)
        info = self._client.futures_create_order(
            side=Order.SIDE_BUY,
            type=Order.TYPE_MARKET,
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
        self._set_futures_settings(symbol, self.leverage)
        symbol_info = self.get_symbol_info(symbol)
        quantity = self._round(amount / price, symbol_info.quantity_precision)
        info = self._client.futures_create_order(
            side=Order.SIDE_BUY,
            type=Order.TYPE_LIMIT,
            symbol=symbol,
            price=price,
            quantity=quantity,
            timeInForce=Client.TIME_IN_FORCE_GTC,
        )
        order = Order.from_dict(info, quantity_key='origQty', futures=True)
        assert order.status == Order.STATUS_NEW

        return order

    def market_sell(self, symbol: str, quantity: Decimal) -> Order:
        info = self._client.futures_create_order(
            side=Order.SIDE_SELL,
            type=Order.TYPE_MARKET,
            symbol=symbol,
            quantity=quantity,
            reduceOnly=True,
        )

        if info['status'] != Order.STATUS_FILLED:
            sleep(1)
            info = self._client.futures_get_order(symbol=info['symbol'], orderId=info['orderId'])

        order = Order.from_dict(info, quantity_key='executedQty', price_key='avgPrice', futures=True)
        assert order.status == Order.STATUS_FILLED

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        symbol_info = self.get_symbol_info(symbol)
        self._stop_market(symbol, stop_loss)
        quantities = self._get_target_quantities(quantity, len(targets), symbol_info.quantity_precision)

        for price, quantity in zip(targets, quantities):
            self._limit(symbol, quantity, price)

    def _stop_market(self, symbol: str, stop_loss: Decimal) -> None:
        info = self._client.futures_create_order(
            side=Order.SIDE_SELL,
            type=Order.TYPE_STOP_MARKET,
            symbol=symbol,
            stopPrice=stop_loss,
            closePosition=True,
            timeInForce='GTE_GTC',
        )
        assert info['status'] == Order.STATUS_NEW

    def _limit(self, symbol: str, quantity: Decimal, price: Decimal) -> None:
        info = self._client.futures_create_order(
            side=Order.SIDE_SELL,
            type=Order.TYPE_LIMIT,
            symbol=symbol,
            price=price,
            quantity=quantity,
            reduceOnly=True,
            timeInForce=Client.TIME_IN_FORCE_GTC,
        )
        assert info['status'] == Order.STATUS_NEW

    def get_last_buy_order(self, symbol: str) -> Optional[Order]:
        api_orders = self._client.futures_get_all_orders(symbol=symbol)
        api_orders.sort(key=lambda o: o['updateTime'], reverse=True)

        for info in api_orders:
            if info['side'] == Order.SIDE_BUY and info['status'] == Order.STATUS_FILLED:
                return Order.from_dict(info, quantity_key='executedQty', price_key='avgPrice', futures=True)
        else:
            return None

    def get_position_quantity(self, symbol: str) -> Decimal:
        info = self._client.futures_position_information(symbol=symbol)
        assert len(info) == 1

        return parse_decimal(info[0]['positionAmt'])

    def get_available_balance(self, currency: str) -> Decimal:
        # client futures_account_balance() is pointing to v1 and we need v2 call
        uri = self._client._create_futures_api_uri('balance').replace('v1', 'v2')
        info = self._client._request('get', uri, signed=True, data={})
        balances = [parse_decimal(balance['availableBalance']) for balance in info if balance['asset'] == currency]
        assert len(balances) == 1

        return balances[0]

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self._load_symbol_infos()

        return self._symbol_infos[symbol]

    def has_open_position(self, symbol: str) -> bool:
        open_positions = self._client.futures_position_information(symbol=symbol)
        # there is always one position with zero values
        assert len(open_positions) == 1
        position_amount = parse_decimal(open_positions[0]['positionAmt'])

        return position_amount != Decimal(0)

    def _set_futures_settings(self, symbol: str, leverage: int) -> None:
        try:
            self._client.futures_change_margin_type(symbol=symbol, marginType=self._margin_type)
        except BinanceAPIException as e:
            if e.code != self._NO_NEED_TO_CHANGE_MARGIN:
                raise

        self._client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def _load_symbol_infos(self) -> None:
        if len(self._symbol_infos) == 0:
            all_info = self._client.futures_exchange_info()

            for info in all_info['symbols']:
                symbol = info['symbol']
                min_notional = [parse_decimal(f['notional']) for f in info['filters']
                                if f['filterType'] == 'MIN_NOTIONAL'][0]
                self._symbol_infos[symbol] = SymbolInfo(int(info['quantityPrecision']),
                                                        int(info['pricePrecision']),
                                                        min_notional)
