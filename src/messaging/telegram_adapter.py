"""Telegram backend for the messaging adapter."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .adapter import Command, IncomingMessage, OnCommand, OnMessage

log = logging.getLogger(__name__)

_KNOWN_COMMANDS = ("ping", "chatid", "tasks", "cancel")


class TelegramAdapter:
    MAX_MESSAGE_LENGTH = 4096

    def __init__(self, token: str):
        self._token = token
        self._app: Application | None = None
        self._on_message: OnMessage | None = None
        self._on_command: OnCommand | None = None

    # ---- lifecycle -------------------------------------------------------

    async def start(self, on_message: OnMessage, on_command: OnCommand) -> None:
        self._on_message = on_message
        self._on_command = on_command
        self._app = Application.builder().token(self._token).build()

        for cmd in _KNOWN_COMMANDS:
            self._app.add_handler(CommandHandler(cmd, self._handle_command))
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.CAPTION) & ~filters.COMMAND,
                self._handle_message,
            )
        )

        log.info("Telegram adapter starting (polling)")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        # Block forever — caller decides when to cancel.
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self._app is None:
            return
        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            if self._app.running:
                await self._app.stop()
            await self._app.shutdown()
        except Exception as e:
            log.warning("Telegram shutdown error: %s", e)
        finally:
            self._app = None

    # ---- send primitives -------------------------------------------------

    async def send_text(self, chat_id: str, text: str) -> str:
        msg = await self._bot.send_message(int(chat_id), text, parse_mode="Markdown")
        return str(msg.message_id)

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        try:
            await self._bot.edit_message_text(
                text,
                chat_id=int(chat_id),
                message_id=int(message_id),
                parse_mode="Markdown",
            )
        except Exception as e:
            # Edits routinely fail on "message is not modified" — not worth surfacing.
            log.debug("Telegram edit failed: %s", e)

    async def send_photo(self, chat_id: str, photo_path: str, caption: str = "") -> None:
        with open(photo_path, "rb") as f:
            await self._bot.send_photo(int(chat_id), photo=f, caption=caption or None)

    async def send_typing(self, chat_id: str) -> None:
        try:
            await self._bot.send_chat_action(int(chat_id), "typing")
        except Exception:
            pass

    # ---- internals -------------------------------------------------------

    @property
    def _bot(self):
        assert self._app is not None, "TelegramAdapter.start() not called"
        return self._app.bot

    async def _handle_command(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        if not msg or not msg.text:
            return
        body = msg.text.lstrip("/")
        name, _, args = body.partition(" ")
        # Strip @botname suffix Telegram appends in groups.
        name = name.split("@", 1)[0].lower()
        incoming = self._to_incoming(update, msg)
        if self._on_command:
            await self._on_command(Command(name=name, args=args.strip()), incoming)

    async def _handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        if not msg:
            return
        incoming = self._to_incoming(update, msg)
        if self._on_message:
            await self._on_message(incoming)

    @staticmethod
    def _to_incoming(update: Update, msg) -> IncomingMessage:
        chat = update.effective_chat
        user = msg.from_user
        text = msg.text or msg.caption or ""
        return IncomingMessage(
            chat_id=str(chat.id),
            sender_id=str(user.id) if user else "0",
            sender_name=(user.first_name if user else "Unknown") or "Unknown",
            text=text,
            is_private=chat.type == "private",
            is_group=chat.type in ("group", "supergroup"),
            timestamp=msg.date.isoformat() if msg.date else "",
        )
