import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from automation.message.buy_message import BuyMessage
from automation.message.unknown_message import UnknownMessage
from automation.parser.parser import Parser


class BuyMessageParser(Parser):
    _NUM = r'\d+(?:\.\d*)?'
    _TARGET = fr'(?:target|take profit)[: ]({_NUM})'

    @classmethod
    def parse(cls, content: str, parent_content: Optional[str]) -> BuyMessage:
        normalized = cls._normalize(content)
        buy = cls._parse_buy(normalized)
        symbol = cls._parse_symbol(normalized)
        targets = cls._parse_targets(normalized)
        stop_loss = cls._parse_stop_loss(normalized, targets)

        return BuyMessage(content, parent_content, symbol, buy['type'], buy['price'], targets, stop_loss)

    @classmethod
    def _parse_buy(cls, normalized: str) -> Dict[str, Any]:
        market_match = re.search(r'vstup[: ].*market', normalized)

        if market_match is not None:
            return dict(type=BuyMessage.BUY_MARKET, price=None)

        limit_match = re.search(fr'vstup[: ]({cls._NUM})', normalized)

        if limit_match is not None:
            return dict(type=BuyMessage.BUY_LIMIT, price=Decimal(limit_match.group(1)))

        limit_match2 = re.search(fr'limitny (?:vstup|prikaz)[: ]({cls._NUM})', normalized)

        if limit_match2 is not None:
            return dict(type=BuyMessage.BUY_LIMIT, price=Decimal(limit_match2.group(1)))

        raise UnknownMessage()

    @classmethod
    def _parse_targets(cls, normalized: str) -> List[Decimal]:
        targets = [Decimal(price) for price in re.findall(cls._TARGET, normalized)]
        assert len(targets) != 0, 'No targets found'

        return targets

    @classmethod
    def _parse_stop_loss(cls, normalized: str, targets: List[Decimal]) -> Decimal:
        stop_lass_match = re.search(fr'stop ?loss[: ]({cls._NUM})', normalized)

        if stop_lass_match is not None:
            return Decimal(stop_lass_match.group(1))

        target_match = re.search(fr'{cls._TARGET}/-{cls._NUM} ?%', normalized)

        if target_match:
            stop_loss = Decimal(target_match.group(1))
            targets.remove(stop_loss)
            assert len(targets) != 0

            return stop_loss

        raise UnknownMessage()
