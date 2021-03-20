from abc import ABC
from typing import Optional


class Message(ABC):
    def __init__(self, content: str, parent_content: Optional[str], symbol: str) -> None:
        self.content: str = content
        self.parent_content: Optional[str] = parent_content
        self.symbol: str = symbol
