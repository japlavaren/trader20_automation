from typing import Optional

from automation.message.message import Message


class UnknownMessage(Message):
    TYPE = 'unknown'

    def __init__(self, channel: str, content: str, parent_content: Optional[str]) -> None:
        super().__init__(channel, self.TYPE, content, parent_content)

    @staticmethod
    def from_dict(values: dict) -> 'UnknownMessage':
        return UnknownMessage(values['channel'], values['content'], values['parentContent'])
