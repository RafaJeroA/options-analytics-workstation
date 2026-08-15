from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    value: Any


class TTLCache:
    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._values: dict[tuple[Any, ...], _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple[Any, ...]) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._values.pop(key, None)
                return None
            return entry.value

    def set(self, key: tuple[Any, ...], value: Any) -> None:
        with self._lock:
            self._values[key] = _CacheEntry(
                expires_at=time.monotonic() + self.ttl_seconds,
                value=value,
            )

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


class KeyedLockPool:
    def __init__(self) -> None:
        self._locks: dict[tuple[Any, ...], threading.Lock] = {}
        self._lock = threading.Lock()

    @contextmanager
    def hold(self, key: tuple[Any, ...]) -> Iterator[None]:
        with self._lock:
            target = self._locks.setdefault(key, threading.Lock())
        target.acquire()
        try:
            yield
        finally:
            target.release()
