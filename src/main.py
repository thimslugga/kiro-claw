"""Kiro-Claw entry point — wires the messaging adapter to all background loops."""

import asyncio
import logging

from aiohttp import web

from .config import (
    DISCORD_COMMAND_PREFIX,
    MESSAGING_BACKEND,
    require_backend_token,
)
from .events import event_processor_loop
from .handler import MessageHandler, make_send_fn, make_send_photo_fn
from .ipc import ipc_loop
from .messaging import build_adapter
from .scheduler import scheduler_loop
from .webhook import WEBHOOK_PORT, create_webhook_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


async def _run():
    token = require_backend_token()
    adapter = build_adapter(MESSAGING_BACKEND, token, command_prefix=DISCORD_COMMAND_PREFIX)
    handler = MessageHandler(adapter)

    send_fn = make_send_fn(adapter)
    send_photo_fn = make_send_photo_fn(adapter)

    # Webhook server (event ingestion)
    webhook_app = create_webhook_app()
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    log.info("Webhook server on port %d", WEBHOOK_PORT)

    background = [
        asyncio.create_task(scheduler_loop(send_fn), name="scheduler"),
        asyncio.create_task(ipc_loop(send_fn, send_photo_fn), name="ipc"),
        asyncio.create_task(event_processor_loop(send_fn), name="events"),
    ]
    log.info("Scheduler, IPC, event processor started")

    log.info("Kiro-Claw starting — JARVIS bridge online (backend=%s)", MESSAGING_BACKEND)
    try:
        await adapter.start(handler.on_message, handler.on_command)
    finally:
        for t in background:
            t.cancel()
        await runner.cleanup()
        await adapter.stop()


def main():
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        log.info("Interrupted, shutting down")


if __name__ == "__main__":
    main()
