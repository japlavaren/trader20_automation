from decimal import Decimal
from typing import Optional

from automation.binance_api import BinanceApi
from automation.logger import Logger
from automation.parser.message_parser import BuyMessage, MessageParser, UnknownMessage
from automation.parser.sell_message_parser import SellMessage


class BombermanCoins:
    def __init__(self, trade_amount: Decimal, api: BinanceApi, logger: Logger) -> None:
        self._trade_amount: Decimal = trade_amount
        self._api: BinanceApi = api
        self._logger: Logger = logger

    def process(self, content: str, parent_content: Optional[str]) -> None:
        message = MessageParser.parse(content, parent_content)

        if isinstance(message, BuyMessage):
            if message.buy_type == BuyMessage.BUY_MARKET:
                self._process_market_buy(message)
                return
            elif message.buy_type == BuyMessage.BUY_LIMIT:
                self._process_limit_buy(message)
                return
        elif isinstance(message, SellMessage):
            if message.sell_type == SellMessage.SELL_MARKET:
                self._process_market_sell(message)
                return

        raise UnknownMessage()

    def _process_market_buy(self, message: BuyMessage) -> None:
        quantity, buy_price = self._api.market_buy(message.symbol, self._trade_amount)
        all_params = self._api.oco_sell(message.symbol, message.targets, quantity, message.stop_loss)

        subject = f'{message.symbol} market bought qty {quantity:.3f}, price {buy_price:.3f}'
        msg = '\n'.join(', '.join(part for part in [
            f'OCO sell order price {params["price"]:.2f}',
            f'stop {params["stopPrice"]:.2f}' if 'stopPrice' in params else None,
            f'limit {params["stopLimitPrice"]:.2f}' if 'stopLimitPrice' in params else None,
        ] if part is not None) for params in all_params)

        self._logger.log(subject, message.content + '\n\n' + subject + '\n' + msg)

    def _process_limit_buy(self, message: BuyMessage) -> None:
        assert message.buy_price is not None
        self._api.limit_buy(message.symbol, message.buy_price, self._trade_amount)

        subject = f'{message.symbol} limit buy created, price {message.buy_price:.3f}'
        self._logger.log(subject, message.content + '\n\n' + subject)

    def _process_market_sell(self, message: SellMessage) -> None:
        order_id, quantity = self._api.get_oco_order(message.symbol)
        self._api.cancel_order(message.symbol, order_id)
        sell_price = self._api.market_sell(message.symbol, quantity)

        subject = f'{message.symbol} market sold qty {quantity:.3f}, price {sell_price:.3f}'
        self._logger.log(subject, message.content + '\n\n' + subject)
