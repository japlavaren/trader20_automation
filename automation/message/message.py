from abc import ABC, abstractmethod
from typing import Optional


class Message(ABC):
    def __init__(self, typ: str, content: str, parent_content: Optional[str]) -> None:
        self.type: str = typ
        self.content: str = content
        self.parent_content: Optional[str] = parent_content

    @staticmethod
    @abstractmethod
    def from_dict(values: dict) -> 'Message':
        pass
