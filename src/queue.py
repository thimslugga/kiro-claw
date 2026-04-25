"""Per-chat async queue — serialises container invocations per chat."""

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

log = logging.getLogger(__name__)

RunnerFn = Callable[[str, str], Awaitable[str]]


class ChatQueue:
    def __init__(self, runner: RunnerFn):
        self._runner = runner
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def submit(self, prompt: str, chat_id) -> str:
        cid = str(chat_id)
        async with self._locks[cid]:
            return await self._runner(prompt, cid)
