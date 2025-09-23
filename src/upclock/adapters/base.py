"""信号采集适配器基类。"""

from __future__ import annotations

import abc
import datetime as dt
from typing import Dict, Union

from upclock.core.signal_buffer import SignalBuffer, SignalRecord


class InputAdapter(abc.ABC):
    """所有传感器适配器的抽象基类。"""

    def __init__(self, buffer: SignalBuffer) -> None:
        self._buffer = buffer

    @abc.abstractmethod
    async def start(self) -> None:
        """启动采集循环。"""

    def publish(self, values: Dict[str, Union[float, str]]) -> None:
        """向缓冲区追加转换后的指标。"""

        record = SignalRecord(timestamp=dt.datetime.utcnow(), values=values)
        self._buffer.append(record)
