import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from automation.parser.common import normalize, parse_symbol, UnknownMessage


class BuyMessage:
    BUY_MARKET = 'market'
    BUY_LIMIT = 'limit'

    def __init__(self, content: str, symbol: str, currency: str, buy_type: str, buy_price: Optional[Decimal],
                 targets: List[Decimal], stop_loss: Decimal) -> None:
        self.content: str = content
        self.symbol: str = symbol
        self.currency: str = currency
        self.buy_type: str = buy_type
        self.buy_price: Optional[Decimal] = buy_price
        self.targets: List[Decimal] = targets
        self.stop_loss: Decimal = stop_loss


class BuyMessageParser:
    @classmethod
    def parse(cls, content: str, parent_content: Optional[str]) -> BuyMessage:
        normalized = normalize(content)
        buy = cls._parse_buy(normalized)
        symbol, currency = parse_symbol(normalized)

        return BuyMessage(
            content=content,
            symbol=symbol,
            currency=currency,
            buy_type=buy['type'],
            buy_price=buy['price'],
            targets=cls._parse_targets(normalized),
            stop_loss=cls._parse_stop_loss(normalized)
        )

    @classmethod
    def _parse_buy(cls, normalized: str) -> Dict[str, Any]:
        market_match = re.search(r'vstup[^a-z].+market', normalized)

        if market_match is not None:
            return dict(type=BuyMessage.BUY_MARKET, price=None)

        limit_match = re.search(r'vstup: (\d+(?:\.\d*)?)', normalized)

        if limit_match is not None:
            return dict(type=BuyMessage.BUY_LIMIT, price=Decimal(limit_match.group(1)))

        limit_match2 = re.search(r'limitny (?:vstup|prikaz): (\d+(?:\.\d*)?)', normalized)

        if limit_match2 is not None:
            return dict(type=BuyMessage.BUY_LIMIT, price=Decimal(limit_match2.group(1)))

        raise UnknownMessage()

    @classmethod
    def _parse_targets(cls, normalized: str) -> List[Decimal]:
        targets = [Decimal(price) for price in re.findall(r'(?:target|take profit): (\d+(?:\.\d*)?)', normalized)]
        assert len(targets) != 0, 'No targets found'

        return targets

    @classmethod
    def _parse_stop_loss(cls, normalized: str) -> Decimal:
        match = re.search(r'stop ?loss: (\d+(?:\.\d*)?)', normalized)
        assert match is not None, 'Stop loss not found'

        return Decimal(match.group(1))
