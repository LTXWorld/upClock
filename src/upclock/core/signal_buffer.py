"""负责缓存并聚合来自各传感器的信号。"""

from __future__ import annotations

import collections
import datetime as dt
import threading
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, Iterator, List, Union


@dataclass
class SignalRecord:
    """单条信号记录。"""

    timestamp: dt.datetime
    values: Dict[str, Union[float, str]]


class SignalBuffer:
    """环形缓冲区，支持多线程追加与快照。"""

    def __init__(self, maxlen: int = 600) -> None:
        self._records: Deque[SignalRecord] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, record: SignalRecord) -> None:
        """追加新信号。"""

        with self._lock:
            self._records.append(record)

    def iter_recent_metrics(self) -> Iterator[Dict[str, Union[float, str]]]:
        """遍历当前缓存的所有指标。"""

        with self._lock:
            snapshot = list(self._records)
        return (record.values for record in snapshot)

    def snapshot(self) -> List[SignalRecord]:
        """返回当前记录的浅拷贝。"""

        with self._lock:
            return list(self._records)
