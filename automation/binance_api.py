import math
import time
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, List, Tuple

from binance.client import Client
from binance.exceptions import BinanceAPIException


class BinanceApi:
    STOP_PRICE_CORRECTION = Decimal(0.5) / 100  # 0.5%

    def __init__(self, client: Client) -> None:
        self._client: Client = client

    def market_buy(self, symbol: str, amount: Decimal) -> Tuple[Decimal, Decimal]:
        assert 'USDT' in symbol, 'Only USDT pairs are suported'
        precision = self._get_precisions(symbol)
        amount_rounded = round(amount, precision['price'])
        info = self._client.order_market_buy(symbol=symbol, quoteOrderQty=amount_rounded)
        assert info['status'] == 'FILLED', f'Got {info["status"]} status'
        quantity = Decimal(info['executedQty'])
        price = Decimal(info['cummulativeQuoteQty']) / quantity

        return quantity, price

    def market_sell(self, symbol: str, quantity: Decimal) -> Decimal:
        precision = self._get_precisions(symbol)
        quantity_rounded = round(quantity, precision['quantity'])
        info = self._client.order_market_sell(symbol=symbol, quantity=quantity_rounded)
        assert info['status'] == 'FILLED', f'Got {info["status"]} status'
        total_price = Decimal(info['cummulativeQuoteQty'])
        price = total_price / Decimal(info['executedQty'])

        return price

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> None:
        assert 'USDT' in symbol, 'Only USDT pairs are suported'
        precision = self._get_precisions(symbol)
        price_rounded = round(price, precision['price'])
        quantity_rounded = round(amount / price, precision['quantity'])
        info = self._client.order_limit_buy(symbol=symbol, price=price_rounded, quantity=quantity_rounded)
        assert info['status'] in ('FILLED', 'NEW'), f'Got {info["status"]} status'

    def market_futures_buy(self, symbol: str, amount: Decimal, leverage: str,
                           margin_type: str, targets: List[Decimal], sl: Decimal):
        assert 'USDT' in symbol, 'Only USDT pairs are suported'

        try:
            self._client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
        except BinanceAPIException as e:
            if e.code != -4046:
                raise

        self._client.futures_change_leverage(symbol=symbol, leverage=leverage)
        ex_info = self._get_futures_exinfo(symbol)
        if not ex_info:
            raise ValueError("Symbol not available on Futures")

        price = float(self._get_symbol_price(symbol))
        quantity = round(amount / price, ex_info["quantityPrecision"])

        self._client.futures_create_order(
            side="BUY",
            symbol=symbol,
            type="MARKET",
            quantity=quantity,
            timestamp=int(time.time() * 1000)
        )

        # TP SL
        quantity_precision = ex_info["quantityPrecision"]
        price_precision = ex_info["pricePrecision"]
        tp_quantity = round(quantity / len(targets), quantity_precision)
        sl_price = round(sl, price_precision)
        '''
        for t in targets:
            self._client.futures_create_order(
                side="SELL",
                symbol=symbol,
                type="TAKE_PROFIT",
                quantity=tp_quantity,
                price=round(t, price_precision),
                stopPrice=sl_price,
                timeInForce="GTC",
            )
        '''
        for t in targets:
            self._client.futures_create_order(
                side="SELL",
                symbol=symbol,
                type="TAKE_PROFIT_MARKET",
                quantity=tp_quantity,
                stopPrice=round(t, price_precision),
                timeInForce="GTC",
            )

        # SL
        self._client.futures_create_order(
            side="SELL",
            symbol=symbol,
            type="STOP_MARKET",
            quantity=quantity,
            stopPrice=round(sl_price, price_precision),
            timeInForce="GTC",
        )

    def limit_futures_buy(self, symbol: str, price: Decimal, amount: Decimal,
                          leverage: str, margin_type: str, targets: List[Decimal], sl: Decimal):
        assert 'USDT' in symbol, 'Only USDT pairs are suported'

        try:
            self._client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
        except BinanceAPIException as e:
            if e.code != -4046:
                raise

        self._client.futures_change_leverage(symbol=symbol, leverage=leverage)
        ex_info = self._get_futures_exinfo(symbol)
        if not ex_info:
            raise ValueError("Symbol not available on Futures")

        quantity = round(amount / price, ex_info["quantityPrecision"])

        self._client.futures_create_order(
            side="BUY",
            symbol=symbol,
            type="LIMIT",
            price=price,
            quantity=quantity,
            timeInForce="GTC",
            timestamp=int(time.time() * 1000)
        )

        # TP SL
        quantity_precision = ex_info["quantityPrecision"]
        price_precision = ex_info["pricePrecision"]
        tp_quantity = round(quantity / len(targets), quantity_precision)
        sl_price = round(sl, price_precision)

        for t in targets:
            self._client.futures_create_order(
                side="SELL",
                symbol=symbol,
                type="TAKE_PROFIT_MARKET",
                quantity=tp_quantity,
                stopPrice=round(t, price_precision),
                timeInForce="GTC",
            )
        # SL
        self._client.futures_create_order(
            side="SELL",
            symbol=symbol,
            type="STOP_MARKET",
            quantity=quantity,
            stopPrice=round(sl_price, price_precision),
            timeInForce="GTC",
        )

    def oco_sell(self, symbol: str, targets: List[Decimal], total_quantity: Decimal, stop_loss: Decimal,
                 ) -> List[Dict[str, Any]]:
        # split total quantity to equal parts per each trade
        precision = self._get_precisions(symbol)
        trade_quantity = round(total_quantity / len(targets), precision['quantity'])
        quantities = [trade_quantity for _ in range(len(targets))]
        quantities[-1] = round(total_quantity - sum(quantities[:-1]), precision['quantity'])
        stop_loss_rounded = round(stop_loss, precision['price'])
        all_params = []

        for price, quantity in zip(targets, quantities):
            price_rounded = round(price, precision['price'])
            stop_price_rounded = round(stop_loss * (1 + self.STOP_PRICE_CORRECTION), precision['price'])
            params = dict(symbol=symbol, quantity=quantity, price=price_rounded, stopPrice=stop_price_rounded,
                          stopLimitPrice=stop_loss_rounded, stopLimitTimeInForce='FOK')
            info = self._client.order_oco_sell(**params)
            assert info['listStatusType'] == 'EXEC_STARTED'
            all_params.append(params)

        return all_params

    def get_oco_orders(self, symbol: str) -> List[Tuple[int, Decimal]]:
        all_orders = self._client.get_open_orders(symbol=symbol)
        sorted(all_orders, key=lambda o: o['type'])
        grouped_orders = {}
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

    def _get_futures_exinfo(self, symbol):
        exinfo = self._client.futures_exchange_info()
        symbol_info = None
        for i in exinfo["symbols"]:
            if i["symbol"] == symbol:
                symbol_info = i
                break

        return symbol_info

    def _get_symbol_price(self, symbol):
        return self._client.get_symbol_ticker(symbol=symbol)["price"]

    @lru_cache
    def _get_precisions(self, symbol: str) -> Dict[str, int]:
        info = self._client.get_symbol_info(symbol)
        precision = {}

        def parse(key: str) -> int:
            return int(round(-math.log(Decimal(f[key]), 10), 0))

        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                precision['quantity'] = parse('stepSize')
            elif f['filterType'] == 'PRICE_FILTER':
                precision['price'] = parse('tickSize')

        assert precision['quantity'] is not None, 'Unknown quantity precission'
        assert precision['price'] is not None, 'Unknown price precission'

        return precision
