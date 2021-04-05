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
        self.__symbol_infos: Dict[str, SymbolInfo] = {}

    @property
    def leverage(self) -> int:
        assert self._leverage is not None
        leverage, self._leverage = self._leverage, None  # reset after use

        return leverage

    @leverage.setter
    def leverage(self, leverage: int):
        self._leverage = leverage

    def is_futures_symbol(self, symbol: str) -> bool:
        return symbol in self._symbol_infos.keys()

    def market_buy(self, symbol: str, amount: Decimal) -> Order:
        self._check_is_empty(symbol)
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
        assert order.status == Order.STATUS_FILLED, f'Got {order.status} status'

        return order

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> Order:
        self._check_is_empty(symbol)
        self._set_futures_settings(symbol, self.leverage)
        buy_price, buy_quantity = self._get_limit_buy_price_and_quantity(symbol, price, amount)
        info = self._client.futures_create_order(
            side=Order.SIDE_BUY,
            type=Order.TYPE_LIMIT,
            symbol=symbol,
            price=buy_price,
            quantity=buy_quantity,
            timeInForce=Client.TIME_IN_FORCE_GTC,
        )
        order = Order.from_dict(info, quantity_key='origQty', futures=True)
        assert order.status == Order.STATUS_NEW, f'Got {order.status} status'

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
        assert order.status == Order.STATUS_FILLED, f'Got {order.status} status'

        return order

    def oco_sell(self, symbol: str, quantity: Decimal, targets: List[Decimal], stop_loss: Decimal) -> None:
        self._stop_market_sell(symbol, stop_loss)
        quantities = self._get_target_quantities(symbol, quantity, len(targets))

        for price, quantity in zip(targets, quantities):
            self._limit_sell(symbol, quantity, price)

    def get_open_position_quantity(self, symbol: str) -> Decimal:
        info = self._client.futures_position_information(symbol=symbol)
        assert len(info) == 1

        return parse_decimal(info[0]['positionAmt'])

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        return self._symbol_infos[symbol]

    def get_sell_order_pnl(self, sell_order: Order) -> Optional[Decimal]:
        assert sell_order.side == Order.SIDE_SELL
        assert sell_order.status == Order.STATUS_FILLED
        trades = self._client.futures_account_trades(symbol=sell_order.symbol)
        pln = [parse_decimal(info['realizedPnl']) for info in trades
               if info['orderId'] == sell_order.order_id]

        return pln[0] if len(pln) != 0 else None

    def _stop_market_sell(self, symbol: str, stop_loss: Decimal) -> None:
        _, stop_loss_price = self._get_stop_loss_prices(symbol, stop_loss)
        info = self._client.futures_create_order(
            side=Order.SIDE_SELL,
            type=Order.TYPE_STOP_MARKET,
            symbol=symbol,
            stopPrice=stop_loss_price,
            closePosition=True,
            timeInForce='GTE_GTC',
        )
        assert info['status'] == Order.STATUS_NEW, f'Got {info["status"]} status'

    def _limit_sell(self, symbol: str, quantity: Decimal, price: Decimal) -> None:
        info = self._client.futures_create_order(
            side=Order.SIDE_SELL,
            type=Order.TYPE_LIMIT,
            symbol=symbol,
            price=price,
            quantity=quantity,
            reduceOnly=True,
            timeInForce=Client.TIME_IN_FORCE_GTC,
        )
        assert info['status'] == Order.STATUS_NEW, f'Got {info["status"]} status'

    def _check_is_empty(self, symbol: str) -> None:
        positions = self._client.futures_position_information(symbol=symbol)
        assert len(positions) == 1
        assert parse_decimal(positions[0]['positionAmt']) == Decimal(0), f'{symbol} has open future position'
        assert len(self._client.futures_get_open_orders(symbol=symbol)) == 0, f'{symbol} has open future order'

    def _set_futures_settings(self, symbol: str, leverage: int) -> None:
        try:
            self._client.futures_change_margin_type(symbol=symbol, marginType=self._margin_type)
        except BinanceAPIException as e:
            if e.code != self._NO_NEED_TO_CHANGE_MARGIN:
                raise

        self._client.futures_change_leverage(symbol=symbol, leverage=leverage)

    @property
    def _symbol_infos(self) -> Dict[str, SymbolInfo]:
        if len(self.__symbol_infos) == 0:
            all_info = self._client.futures_exchange_info()

            for info in all_info['symbols']:
                symbol = info['symbol']
                min_notional = [parse_decimal(f['notional']) for f in info['filters']
                                if f['filterType'] == 'MIN_NOTIONAL'][0]
                self.__symbol_infos[symbol] = SymbolInfo(int(info['quantityPrecision']),
                                                         int(info['pricePrecision']),
                                                         min_notional)

        return self.__symbol_infos
