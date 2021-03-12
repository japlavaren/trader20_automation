from decimal import Decimal

from automation.binance_api import BinanceApi
from automation.logger import Logger
from automation.message_parser import BuyMessage, MessageParser, UnknownMessage


class BombermanCoins:
    def __init__(self, trade_amount: Decimal, api: BinanceApi, logger: Logger) -> None:
        self._trade_amount: Decimal = trade_amount
        self._api: BinanceApi = api
        self._logger: Logger = logger

    def process(self, content: str) -> None:
        message = MessageParser.parse(content)

        if message.buy_type == BuyMessage.BUY_MARKET:
            self._process_market_buy(message)
        elif message.buy_type == BuyMessage.BUY_LIMIT:
            self._process_limit_buy(message)
        else:
            raise UnknownMessage()

    def _process_market_buy(self, message: BuyMessage) -> None:
        quantity, buy_price = self._api.market_buy(message.symbol, self._trade_amount)
        all_params = self._api.oco_sell(message.symbol, message.targets, quantity, message.stop_loss)

        subject = f'{message.symbol} market bought qty {quantity:.3f}, price {buy_price:.3f}'
        msg = '\n'.join(', '.join(part for part in [
            f'OCO price {params["price"]:.2f}',
            f'stop {params["stopPrice"]:.2f}' if 'stopPrice' in params else None,
            f'limit {params["stopLimitPrice"]:.2f}' if 'stopLimitPrice' in params else None,
        ] if part is not None) for params in all_params)

        self._logger.log(subject, message.content + '\n\n' + subject + '\n' + msg)

    def _process_limit_buy(self, message: BuyMessage) -> None:
        assert message.buy_price is not None
        self._api.limit_buy(message.symbol, message.buy_price, self._trade_amount)

        msg = f'{message.symbol} limit buy created, price {message.buy_price:.3f}'
        self._logger.log(msg, message.content + '\n\n' + msg)
