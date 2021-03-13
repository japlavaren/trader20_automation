import math
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from binance.client import Client


class BinanceApi:
    STOP_PRICE_CORRECTION = Decimal(0.5) / 100  # 0.5%

    def __init__(self, client: Client) -> None:
        self._client: Client = client

    def market_buy(self, symbol: str, amount: Decimal) -> Tuple[Decimal, Decimal]:
        assert 'USDT' in symbol, 'Only USDT pairs are suported'
        info = self._client.order_market_buy(symbol=symbol, quoteOrderQty=amount)
        quantity = Decimal(info['executedQty'])
        price = Decimal(info['cummulativeQuoteQty']) / quantity

        return quantity, price

    def limit_buy(self, symbol: str, price: Decimal, amount: Decimal) -> None:
        assert 'USDT' in symbol, 'Only USDT pairs are suported'
        quantity_precision, price_precision = self._get_precisions(symbol)
        quantity = round(amount / price, quantity_precision)
        self._client.order_limit_buy(symbol=symbol, price=price, quantity=quantity)

    def oco_sell(self, symbol: str, targets: List[Decimal], total_quantity: Decimal, stop_loss: Decimal,
                 ) -> List[Dict[str, Any]]:
        # split total quantity to equal parts per each trade
        quantity_precision, price_precision = self._get_precisions(symbol)
        trade_quantity = round(total_quantity / len(targets), quantity_precision)
        quantities = [trade_quantity for _ in range(len(targets))]
        quantities[-1] = round(total_quantity - sum(quantities[:-1]), quantity_precision)
        all_params = []

        for price, quantity in zip(targets, quantities):
            stop_price = round(stop_loss * (1 + self.STOP_PRICE_CORRECTION), price_precision)
            params = dict(symbol=symbol, quantity=quantity, price=price, stopPrice=stop_price, stopLimitPrice=stop_loss,
                          stopLimitTimeInForce='FOK')
            self._client.order_oco_sell(**params)
            all_params.append(params)

        return all_params

    def _get_precisions(self, symbol: str) -> Tuple[int, int]:
        info = self._client.get_symbol_info(symbol)
        quantity_precision, price_precision = None, None

        def parse(key: str) -> int:
            return int(round(-math.log(Decimal(f[key]), 10), 0))

        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                quantity_precision = parse('stepSize')
            elif f['filterType'] == 'PRICE_FILTER':
                price_precision = parse('tickSize')

        assert quantity_precision is not None
        assert price_precision is not None

        return quantity_precision, price_precision
