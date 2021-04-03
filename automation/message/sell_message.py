from typing import Optional

from automation.message.message import Message


class SellMessage(Message):
    TYPE = 'sell'
    SELL_MARKET = 'market'

    def __init__(self, content: str, parent_content: Optional[str], symbol: str, sell_type: str) -> None:
        super().__init__(self.TYPE, content, parent_content)
        self.symbol: str = symbol
        self.sell_type: str = sell_type

    @staticmethod
    def from_dict(values: dict) -> 'SellMessage':
        return SellMessage(values['content'], values['parentContent'], values['symbol'], values['sell_type'])
