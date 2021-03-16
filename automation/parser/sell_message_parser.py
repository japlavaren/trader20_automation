from typing import Optional, Tuple

from automation.parser.common import normalize, parse_symbol, UnknownMessage


class SellMessage:
    SELL_MARKET = 'market'

    def __init__(self, content: str, symbol: str, currency: str, sell_type: str) -> None:
        self.content: str = content
        self.symbol: str = symbol
        self.currency: str = currency
        self.sell_type: str = sell_type


class SellMessageParser:
    @classmethod
    def parse(cls, content: str, parent_content: Optional[str]) -> SellMessage:
        normalized = normalize(content)
        parent_normalized = normalize(parent_content) if parent_content is not None else None
        cls._check_is_sell(normalized)
        symbol, currency = cls._parse_symbol(normalized, parent_normalized)

        return SellMessage(
            content=content,
            symbol=symbol,
            currency=currency,
            sell_type=SellMessage.SELL_MARKET,
        )

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

    @staticmethod
    def _parse_symbol(normalized: str, parent_normalized: Optional[str]) -> Tuple[str, str]:
        try:
            return parse_symbol(normalized)
        except AssertionError:
            if parent_normalized is None:
                raise
            else:
                return parse_symbol(parent_normalized)
