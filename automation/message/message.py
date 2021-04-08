from abc import ABC, abstractmethod
from typing import Optional


class Message(ABC):
    CHANNEL_COIN = 'coin'
    CHANNEL_MIDTERM = 'midterm'
    CHANNEL_OTHER = 'other'

    def __init__(self, channel: str, typ: str, content: str, parent_content: Optional[str]) -> None:
        self.channel: str = channel
        self.type: str = typ
        self.content: str = content
        self.parent_content: Optional[str] = parent_content

    @staticmethod
    @abstractmethod
    def from_dict(values: dict) -> 'Message':
        pass
