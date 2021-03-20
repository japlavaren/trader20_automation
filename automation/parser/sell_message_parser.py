from typing import Optional

from automation.message.sell_message import SellMessage
from automation.message.unknown_message import UnknownMessage
from automation.parser.parser import Parser


class SellMessageParser(Parser):
    @classmethod
    def parse(cls, content: str, parent_content: Optional[str]) -> SellMessage:
        normalized = cls._normalize(content)
        parent_normalized = cls._normalize(parent_content) if parent_content is not None else None
        cls._check_is_sell(normalized)
        symbol = cls._parse_message_symbol(normalized, parent_normalized)

        return SellMessage(content, parent_content, symbol, sell_type=SellMessage.SELL_MARKET)

    @staticmethod
    def _check_is_sell(normalized: str) -> None:
        # must contain stop word but can not contain saving word
        for stop in ('uzavrite', 'ukoncite', 'predajte', 'skoncite'):
            if stop in normalized:
                if 'zvysok' in normalized or 'polovicu' in normalized:
                    raise UnknownMessage()
                else:
                    return  # is valid sell message

        raise UnknownMessage()

    @classmethod
    def _parse_message_symbol(cls, normalized: str, parent_normalized: Optional[str]) -> str:
        try:
            return cls._parse_symbol(normalized)
        except AssertionError:
            if parent_normalized is None:
                raise
            else:
                return cls._parse_symbol(parent_normalized)
