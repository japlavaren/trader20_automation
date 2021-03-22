from decimal import Decimal
from typing import List, Optional

from automation.message.message import Message


class BuyMessage(Message):
    BUY_MARKET = 'market'
    BUY_LIMIT = 'limit'

    def __init__(self, content: str, parent_content: Optional[str], symbol: str, buy_type: str,
                 buy_price: Optional[Decimal], targets: List[Decimal], stop_loss: Decimal) -> None:
        super().__init__(content, parent_content, symbol)
        assert len(targets) != 0

        for target in targets:
            assert target > stop_loss, f'Target {target} is smaller than stop loss {stop_loss}'

        self.buy_type: str = buy_type
        self.buy_price: Optional[Decimal] = buy_price
        self.targets: List[Decimal] = targets
        self.stop_loss: Decimal = stop_loss
