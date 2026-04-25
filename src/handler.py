"""Platform-agnostic message handling.

Wires a `MessagingAdapter` to the rest of the system: stores messages, parses
trigger patterns, drives the per-chat lock, streams container output back to
the user, and dispatches `/ping` / `/chatid` / `/tasks` / `/cancel`.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

from .config import (
    ALLOWED_CHAT_IDS,
    DEFAULT_EVENT_CHAT_ID,
    OWNER_USER_ID,
    TRIGGER_PATTERN,
)
from .db import delete_task, get_tasks_for_chat, store_message
from .messaging import Command, IncomingMessage, MessagingAdapter
from .runner import stream_from_container

log = logging.getLogger(__name__)

DRAFT_INTERVAL = 1.0  # min seconds between live edits


def _split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def is_allowed(chat_id: str) -> bool:
    return not ALLOWED_CHAT_IDS or chat_id in ALLOWED_CHAT_IDS


def _trigger_strip(text: str, is_private: bool) -> str | None:
    """Return the prompt body if the bot should respond, else None."""
    if is_private:
        return text
    pattern = re.escape(TRIGGER_PATTERN)
    match = re.match(rf"^{pattern}\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


class MessageHandler:
    """Owns the full receive→reply pipeline. Wired into an adapter."""

    def __init__(self, adapter: MessagingAdapter):
        self.adapter = adapter
        self._max = adapter.MAX_MESSAGE_LENGTH

    # ---- public callbacks given to the adapter --------------------------

    async def on_command(self, cmd: Command, msg: IncomingMessage) -> None:
        if not is_allowed(msg.chat_id):
            log.info("Rejected command %s from chat %s", cmd.name, msg.chat_id)
            return

        if cmd.name == "ping":
            await self.adapter.send_text(msg.chat_id, "JARVIS online, Sir.")
            return

        if cmd.name == "chatid":
            await self.adapter.send_text(msg.chat_id, f"Chat ID: `{msg.chat_id}`")
            return

        if cmd.name == "tasks":
            tasks = get_tasks_for_chat(msg.chat_id)
            if not tasks:
                await self.adapter.send_text(msg.chat_id, "No active tasks.")
                return
            lines = [
                f"• `{t['id']}` [{t['schedule_type']}] — {t['prompt'][:60]}\n  Next: {t['next_run']}"
                for t in tasks
            ]
            await self.adapter.send_text(msg.chat_id, "\n".join(lines))
            return

        if cmd.name == "cancel":
            task_id = cmd.args.strip()
            if not task_id:
                await self.adapter.send_text(msg.chat_id, "Usage: /cancel <task_id>")
                return
            ok = delete_task(task_id)
            text = f"Task `{task_id}` {'cancelled.' if ok else 'not found.'}"
            await self.adapter.send_text(msg.chat_id, text)
            return

        log.debug("Ignoring unknown command: %s", cmd.name)

    async def on_message(self, msg: IncomingMessage) -> None:
        if not is_allowed(msg.chat_id):
            log.info("Rejected message from chat %s", msg.chat_id)
            return

        text = msg.text or ""

        # In groups, observe everyone but only reply to the configured owner.
        if msg.is_group:
            store_message(msg.chat_id, msg.sender_name, msg.sender_id, text, msg.timestamp)
            if OWNER_USER_ID and msg.sender_id != OWNER_USER_ID:
                log.info("[GROUP OBSERVE] %s: %s", msg.sender_name, text[:200])
                return
            if not OWNER_USER_ID:
                # No owner configured → never reply in groups, just observe.
                log.info("[GROUP OBSERVE — no OWNER_USER_ID set] %s: %s", msg.sender_name, text[:200])
                return

        if not text:
            return

        prompt = _trigger_strip(text, msg.is_private)
        if not prompt:
            return

        if not msg.is_group:
            store_message(msg.chat_id, msg.sender_name, msg.sender_id, text, msg.timestamp)

        full_prompt = f"[Chat from {msg.sender_name}]: {prompt}"
        log.info("Processing message from %s in chat %s", msg.sender_name, msg.chat_id)

        await self._stream_reply(msg.chat_id, full_prompt, allow_live_edit=msg.is_private)

    # ---- streaming reply -------------------------------------------------

    async def _stream_reply(self, chat_id: str, prompt: str, *, allow_live_edit: bool) -> None:
        typing_active = True

        async def _typing_loop():
            while typing_active:
                await self.adapter.send_typing(chat_id)
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(_typing_loop())

        accumulated = ""
        live_msg_id: str | None = None
        last_edit = 0.0

        try:
            async for line in stream_from_container(prompt, chat_id):
                accumulated = (accumulated + "\n" + line).strip() if accumulated else line
                if not allow_live_edit:
                    continue
                now = time.monotonic()
                if now - last_edit < DRAFT_INTERVAL:
                    continue
                preview = accumulated[-self._max :]
                try:
                    if live_msg_id is None:
                        live_msg_id = await self.adapter.send_text(chat_id, preview)
                    else:
                        await self.adapter.edit_text(chat_id, live_msg_id, preview)
                    last_edit = now
                except Exception as e:
                    log.debug("Live update failed: %s", e)
        finally:
            typing_active = False
            typing_task.cancel()

        if not accumulated:
            accumulated = "No response from container."

        chunks = _split_message(accumulated, self._max)

        if live_msg_id is not None and chunks:
            # Replace the live preview with the final first chunk.
            try:
                await self.adapter.edit_text(chat_id, live_msg_id, chunks[0])
            except Exception:
                await self.adapter.send_text(chat_id, chunks[0])
            for extra in chunks[1:]:
                await self.adapter.send_text(chat_id, extra)
        else:
            for chunk in chunks:
                await self.adapter.send_text(chat_id, chunk)

        store_message(
            chat_id,
            "JARVIS",
            "0",
            accumulated,
            datetime.now(timezone.utc).isoformat(),
            is_bot=True,
        )


# ---- send-fn factories used by scheduler / IPC / events ------------------


def make_send_fn(adapter: MessagingAdapter):
    """Return an async (chat_id, text) callback that splits long messages."""
    limit = adapter.MAX_MESSAGE_LENGTH

    async def send_fn(chat_id, text: str):
        cid = str(chat_id)
        for chunk in _split_message(text, limit):
            try:
                await adapter.send_text(cid, chunk)
            except Exception as e:
                log.error("send_fn failed for %s: %s", cid, e)

    return send_fn


def make_send_photo_fn(adapter: MessagingAdapter):
    async def send_photo_fn(chat_id, photo_path: str, caption: str = ""):
        try:
            await adapter.send_photo(str(chat_id), photo_path, caption)
        except Exception as e:
            log.error("send_photo_fn failed for %s: %s", chat_id, e)

    return send_photo_fn


def event_default_chat_id() -> str:
    """Chat id used by the event processor when an event has no explicit target."""
    return DEFAULT_EVENT_CHAT_ID
