import re
from decimal import Decimal
from typing import List, Optional, Tuple

from unidecode import unidecode


class BuyMessage:
    BUY_MARKET = 'market'
    BUY_LIMIT = 'limit'

    def __init__(self, content: str, symbol: str, buy_type: str, buy_price: Optional[Decimal], targets: List[Decimal],
                 stop_loss: Decimal) -> None:
        self.content: str = content
        self.symbol: str = symbol
        self.buy_type: str = buy_type
        self.buy_price: Optional[Decimal] = buy_price
        self.targets: List[Decimal] = targets
        self.stop_loss: Decimal = stop_loss


class UnknownMessage(Exception):
    pass


class MessageParser:
    @classmethod
    def parse(cls, original_msg: str) -> BuyMessage:
        msg = cls._normalize(original_msg)
        buy_type, buy_price = cls._parse_buy(msg)

        return BuyMessage(
            content=msg,
            symbol=cls._parse_symbol(msg),
            buy_type=buy_type,
            buy_price=buy_price,
            targets=cls._parse_targets(msg),
            stop_loss=cls._parse_stop_loss(msg)
        )

    @classmethod
    def _parse_symbol(cls, msg: str) -> str:
        match = re.search(r'([\da-z]+/(?:usdt?|btc))', msg)
        assert match is not None
        symbol = match.group(1).replace('/', '').upper()

        if 'USD' in symbol and 'USDT' not in symbol:
            symbol = symbol.replace('USD', 'USDT')

        return symbol

    @classmethod
    def _parse_buy(cls, msg: str) -> Tuple[str, Optional[Decimal]]:
        if 'vstup:' in msg:
            return BuyMessage.BUY_MARKET, None

        limit_match = re.search(r'limitny (?:vstup|prikaz): (\d+(?:\.\d*)?)', msg)

        if limit_match is not None:
            return BuyMessage.BUY_LIMIT, Decimal(limit_match.group(1))

        raise UnknownMessage()

    @classmethod
    def _parse_targets(cls, msg: str) -> List[Decimal]:
        targets = [Decimal(price) for price in re.findall(r'(?:target|take profit): (\d+(?:\.\d*)?)', msg)]
        assert len(targets) != 0, 'No targets found'

        return targets

    @classmethod
    def _parse_stop_loss(cls, msg: str) -> Decimal:
        match = re.search(r'stop ?loss: (\d+(?:\.\d*)?)', msg)
        assert match is not None

        return Decimal(match.group(1))

    @staticmethod
    def _normalize(msg: str) -> str:
        msg = unidecode(msg).lower()
        msg = re.sub(r'\s*:\s*', ': ', msg)
        msg = re.sub(r'\s*/\s*', '/', msg)

        return msg
