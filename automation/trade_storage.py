import pickle
from typing import List

from automation.trade import Trade


class TradeStorage:
    def __init__(self, file_path: str) -> None:
        self._file_path: str = file_path
        self._trades: List[Trade] = self._load_trades()

    def get_trades_by_symbol(self, symbol: str) -> List[Trade]:
        return [trade for trade in self._trades if trade.buy_order.symbol == symbol]

    def add_trade(self, trade: Trade) -> None:
        if trade not in self._trades:
            self._trades.append(trade)

        self.save()

    def remove_trade(self, trade: Trade) -> None:
        self._trades.remove(trade)
        self.save()

    def save(self) -> None:
        with open(self._file_path, 'wb') as h:
            pickle.dump(self._trades, h)

    def _load_trades(self) -> List[Trade]:
        try:
            with open(self._file_path, 'rb') as h:
                return pickle.load(h)
        except IOError:
            return []
