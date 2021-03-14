import math
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, List, Tuple

from binance.client import Client


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
