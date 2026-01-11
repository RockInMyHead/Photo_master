from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional
import threading

@dataclass(frozen=True)
class CacheKey:
    path: str
    mtime: float
    size: int

class PreviewCache:
    def __init__(self, max_items: int = 256):
        self.max_items = max_items
        self._lock = threading.Lock()
        self._cache: "OrderedDict[CacheKey, bytes]" = OrderedDict()

    def get(self, key: CacheKey) -> Optional[bytes]:
        with self._lock:
            v = self._cache.get(key)
            if v is None:
                return None
            self._cache.move_to_end(key)
            return v

    def put(self, key: CacheKey, value: bytes) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_items:
                self._cache.popitem(last=False)
