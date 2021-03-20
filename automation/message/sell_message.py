from typing import Optional

from automation.message.message import Message


class SellMessage(Message):
    SELL_MARKET = 'market'

    def __init__(self, content: str, parent_content: Optional[str], symbol: str, sell_type: str) -> None:
        super().__init__(content, parent_content, symbol)
        self.sell_type: str = sell_type
