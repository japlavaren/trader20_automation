import json
from typing import List


class SymbolWatcher:
    def __init__(self, file_path: str) -> None:
        self._file_path: str = file_path
        self.symbols: List[str] = self._load()

    def add_symbol(self, symbol: str) -> None:
        if symbol not in self.symbols:
            self.symbols.append(symbol)
            self._save()

    def remove(self, symbol: str) -> None:
        if symbol in self.symbols:
            self.symbols.remove(symbol)
            self._save()

    def _save(self) -> None:
        with open(self._file_path, 'w') as h:
            json.dump(self.symbols, h)

    def _load(self) -> List[str]:
        try:
            with open(self._file_path) as h:
                return json.load(h)
        except IOError:
            return []
