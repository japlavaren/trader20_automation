from decimal import Decimal
from typing import Dict, Optional

from automation.binance_api import BinanceApi
from automation.logger import Logger
from automation.parser.message_parser import BuyMessage, MessageParser, UnknownMessage
from automation.parser.sell_message_parser import SellMessage


class BombermanCoins:
    def __init__(self, spot_trade_amounts: Dict[str, Decimal], api: BinanceApi, logger: Logger) -> None:
        self._spot_trade_amounts: Dict[str, Decimal] = spot_trade_amounts
        self._api: BinanceApi = api
        self._logger: Logger = logger

    def process(self, content: str, parent_content: Optional[str]) -> None:
        message = MessageParser.parse(content, parent_content)

        if isinstance(message, BuyMessage):
            return self._spot_buy(message)
        elif isinstance(message, SellMessage):
            return self._spot_sell(message)

        raise UnknownMessage()

    def _spot_buy(self, message: BuyMessage) -> None:
        amount = self._spot_trade_amounts.get(message.currency, Decimal(0))

        if amount == Decimal(0):
            msg = f'SKIPPING spot {message.symbol}'
            self._logger.log(msg, message.content)
            return

        if message.buy_type == BuyMessage.BUY_MARKET:
            return self._spot_market_buy(message, amount)
        elif message.buy_type == BuyMessage.BUY_LIMIT:
            return self._spot_limit_buy(message, amount)

        raise UnknownMessage()

    def _spot_market_buy(self, message: BuyMessage, amount: Decimal) -> None:
        quantity, price = self._api.market_buy(message.symbol, amount)
        self._api.oco_sell(message.symbol, message.targets, quantity, message.stop_loss)
        self._logger.log_message(message.content, [
            f'Spot market bought {message.symbol}',
            f'price: {price:.3f}',
            'TP: ' + ', '.join(f'{tp:,3f}' for tp in message.targets),
            f'SL: {message.stop_loss:,3f}',
        ])

    def _spot_limit_buy(self, message: BuyMessage, amount: Decimal) -> None:
        assert message.buy_price is not None
        self._api.limit_buy(message.symbol, message.buy_price, amount)
        self._logger.log_message(message.content, [
            f'Spot limit buy order {message.symbol}',
            f'price: {message.buy_price:.3f}',
        ])

    def _spot_sell(self, message: SellMessage) -> None:
        if message.sell_type == SellMessage.SELL_MARKET:
            return self._spot_market_sell(message)

        raise UnknownMessage()

    def _spot_market_sell(self, message: SellMessage) -> None:
        orders = self._api.get_oco_orders(message.symbol)
        assert len(orders) != 0, 'None OCO sell orders found'
        total_quantity = Decimal(0)

        for order_id, quantity in orders:
            self._api.cancel_order(message.symbol, order_id)
            total_quantity += quantity

        price = self._api.market_sell(message.symbol, total_quantity)
        self._logger.log_message(message.content, [
            f'Spot market sold {message.symbol}',
            f'price: {price:.3f}',
        ])
