from typing import Optional

from automation.message.unknown_message import UnknownMessage
from automation.parser.buy_message_parser import BuyMessageParser
from automation.message.message import Message
from automation.parser.sell_message_parser import SellMessageParser


class MessageParser:
    @classmethod
    def parse(cls, content: str, parent_content: Optional[str]) -> Message:
        for parser in (BuyMessageParser, SellMessageParser):
            try:
                # "Type[object]" has no attribute "parse"
                return parser.parse(content, parent_content)  # type: ignore
            except UnknownMessage:
                pass
        else:
            raise UnknownMessage()
