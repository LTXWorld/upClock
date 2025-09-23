"""通知服务抽象基类。"""

from __future__ import annotations

import abc


class Notifier(abc.ABC):
    """通知接口，未来支持不同平台实现。"""

    @abc.abstractmethod
    async def send(self, title: str, message: str) -> None:
        """发送通知。"""

        raise NotImplementedError
