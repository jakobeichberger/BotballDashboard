"""Small asyncio helpers shared by modules."""

import asyncio
import weakref
from types import TracebackType


class ProcessSemaphore:
    """A module-level ``asyncio.Semaphore`` that works under any event loop.

    An ``asyncio.Semaphore`` belongs to the loop it first waits on; one
    created at import time breaks as soon as a second loop uses it (Celery
    runs each task under its own loop, the test suite one loop per test).
    This keeps one semaphore per running loop, all with the same limit.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
            weakref.WeakKeyDictionary()
        )

    def _current(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        semaphore = self._by_loop.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.limit)
            self._by_loop[loop] = semaphore
        return semaphore

    async def __aenter__(self) -> None:
        await self._current().acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._current().release()
