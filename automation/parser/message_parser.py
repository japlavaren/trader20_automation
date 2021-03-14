from typing import Optional, Union

from automation.parser.buy_message_parser import BuyMessage, BuyMessageParser
from automation.parser.common import UnknownMessage
from automation.parser.sell_message_parser import SellMessage, SellMessageParser


class MessageParser:
    @classmethod
    def parse(cls, content: str, parent_content: Optional[str]) -> Union[BuyMessage, SellMessage]:
        for parser in (BuyMessageParser, SellMessageParser):
            try:
                # "Type[object]" has no attribute "parse"
                return parser.parse(content, parent_content)  # type: ignore
            except UnknownMessage:
                pass
        else:
            raise UnknownMessage()
