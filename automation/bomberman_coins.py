from decimal import Decimal
from typing import Dict, Optional

from automation.binance_api import BinanceApi
from automation.logger import Logger
from automation.parser.message_parser import BuyMessage, MessageParser, UnknownMessage
from automation.parser.sell_message_parser import SellMessage
from automation.trade import Order
from automation.trade_storage import TradeStorage


class BombermanCoins:
    def __init__(self, spot_trade_amounts: Dict[str, Decimal], api: BinanceApi, logger: Logger,
                 trade_storage: TradeStorage) -> None:
        self._spot_trade_amounts: Dict[str, Decimal] = spot_trade_amounts
        self._api: BinanceApi = api
        self._logger: Logger = logger
        self._storage: TradeStorage = trade_storage

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
            trade = self._api.market_buy(message.symbol, amount)
            self._storage.add_trade(trade)
        elif message.buy_type == BuyMessage.BUY_LIMIT:
            assert message.buy_price is not None
            trade = self._api.limit_buy(message.symbol, message.buy_price, amount)
            self._storage.add_trade(trade)
        else:
            raise UnknownMessage()

        buy_order = trade.buy_order
        status = buy_order.status

        if status == Order.STATUS_NEW:
            self._logger.log_message(message.content, [
                f'Spot limit buy order {message.symbol}',
                f'price: {message.buy_price}',
            ])
        elif status == Order.STATUS_FILLED:
            self._api.oco_sell(trade, message.targets, message.stop_loss)
            self._storage.add_trade(trade)

            self._logger.log_message(message.content, [
                f'Spot market bought {message.symbol}',
                f'price: {buy_order.price}',
                'TP: ' + ', '.join(str(o.price) for o in trade.get_orders_by_type(Order.TYPE_LIMIT_MAKER)),
                f'SL: {trade.get_orders_by_type(Order.TYPE_STOP_LOSS_LIMIT)[0].price}',
            ])
        else:
            raise Exception(f'Unknown order status {status}')

    def _spot_sell(self, message: SellMessage) -> None:
        if message.sell_type == SellMessage.SELL_MARKET:
            return self._spot_market_sell(message)

        raise UnknownMessage()

    def _spot_market_sell(self, message: SellMessage) -> None:
        symbol = message.symbol
        oco_orders = self._api.get_oco_orders(symbol)
        assert len(oco_orders) != 0, 'None OCO sell orders found'
        total_quantity = Decimal(0)

        # cancel all oco orders
        for order, _ in oco_orders:
            self._api.cancel_order(symbol, order.order_id)
            total_quantity += order.quantity

        price = self._api.market_sell(symbol, total_quantity)
        parts = [
            f'Spot market sold {symbol}',
            f'price: {price}',
        ]
        trades = self._storage.get_trades_by_symbol(symbol)

        # add statistics if there is just one buy trade
        if len(trades) == 1:
            buy_price = trades[0].buy_order.price
            diff = price - buy_price
            parts.append(f'profit: {diff / buy_price * 100:.2f}%')
            parts.append(f'gain: {diff * total_quantity:.2f} {message.currency}')

        self._logger.log_message(message.content, parts)

        for trade in trades:
            self._storage.remove_trade(trade)
