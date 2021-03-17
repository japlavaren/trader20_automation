from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from automation.binance_api import BinanceApi
from automation.logger import Logger
from automation.parser.message_parser import BuyMessage, MessageParser, UnknownMessage
from automation.parser.sell_message_parser import SellMessage
from automation.trade import Order, Trade
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

    def process_changes(self):
        for symbol in self._storage.symbols:
            for trade, api_order in self._get_changed_trades(symbol):
                if api_order.side == Order.SIDE_BUY:
                    self._process_changed_buy_trade(trade, api_order)

    def _spot_buy(self, message: BuyMessage) -> None:
        amount = self._spot_trade_amounts.get(message.currency, Decimal(0))

        if amount == Decimal(0):
            msg = f'SKIPPING spot {message.symbol}'
            self._logger.log(msg, message.content)
            return

        if message.buy_type == BuyMessage.BUY_MARKET:
            buy_order = self._api.market_buy(message.symbol, amount)
        elif message.buy_type == BuyMessage.BUY_LIMIT:
            assert message.buy_price is not None
            buy_order = self._api.limit_buy(message.symbol, message.buy_price, amount)
        else:
            raise UnknownMessage()

        trade = Trade(buy_order, message.targets, message.stop_loss, message.content)
        self._storage.save_trade(trade)
        status = buy_order.status

        if status == Order.STATUS_NEW:
            self._logger.log_message(trade.message_content, [
                f'Spot limit buy order {buy_order.symbol}',
                f'price: {buy_order.price}',
            ])
        elif status == Order.STATUS_FILLED:
            self._api.oco_sell(trade)
            self._storage.save_trade(trade)

            self._logger.log_message(trade.message_content, [
                f'Spot market bought {buy_order.symbol}',
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

        sell_order = self._api.market_sell(symbol, total_quantity)
        sell_price = sell_order.price
        parts = [
            f'Spot market sold {symbol}',
            f'price: {sell_price}',
        ]
        trades = self._storage.get_trades_by_symbol(symbol)

        # add statistics if there is just one buy trade
        if len(trades) == 1:
            buy_price = trades[0].buy_order.price
            diff = sell_price - buy_price
            parts.append(f'profit: {diff / buy_price * 100:.2f}%')
            parts.append(f'gain: {diff * total_quantity}')

        self._logger.log_message(message.content, parts)

        for trade in trades:
            self._storage.remove_trade(trade)

    def _process_changed_buy_trade(self, trade: Trade, api_order: Order) -> None:
        if api_order.status == Order.STATUS_CANCELED:
            self._storage.remove_trade(trade)
        elif trade.buy_order.status == Order.STATUS_NEW and api_order.status == Order.STATUS_FILLED:  # limit bought
            self._api.oco_sell(trade)
            self._storage.save_trade(trade)
            buy_order = trade.buy_order

            self._logger.log_message(trade.message_content, [
                f'Spot limit bought {buy_order.symbol}',
                f'price: {buy_order.price}',
                'TP: ' + ', '.join(str(o.price) for o in trade.get_orders_by_type(Order.TYPE_LIMIT_MAKER)),
                f'SL: {trade.get_orders_by_type(Order.TYPE_STOP_LOSS_LIMIT)[0].price}',
            ])

    def _get_changed_trades(self, symbol: str) -> List[Tuple[Trade, Order]]:
        trades = self._storage.get_trades_by_symbol(symbol)
        api_orders = self._api.get_orders(symbol)
        changed_trades: List[Tuple[Trade, Order]] = []

        for trade in trades:
            order_ids = set(order.order_id for order in trade.orders)

            for api_order in api_orders:
                if api_order.order_id in order_ids:
                    for order in trade.orders:
                        if order.order_id == api_order.order_id and order.status != api_order.status:
                            changed_trades.append((trade, api_order))

        return changed_trades
