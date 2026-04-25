"""Discord backend for the messaging adapter."""

from __future__ import annotations

import logging

import discord

from .adapter import Command, IncomingMessage, OnCommand, OnMessage

log = logging.getLogger(__name__)


class DiscordAdapter:
    # Discord caps a regular message at 2000 chars.
    MAX_MESSAGE_LENGTH = 2000

    def __init__(self, token: str, command_prefix: str = "!"):
        self._token = token
        self._prefix = command_prefix

        intents = discord.Intents.default()
        intents.message_content = True   # required to read message bodies
        intents.guilds = True
        intents.dm_messages = True
        intents.guild_messages = True

        self._client = discord.Client(intents=intents)
        self._on_message: OnMessage | None = None
        self._on_command: OnCommand | None = None

        # discord.py looks up event handlers by function __name__, so we
        # register thin wrappers under the canonical names.
        @self._client.event
        async def on_ready():  # noqa: N802 — discord.py event name
            await self._handle_ready()

        @self._client.event
        async def on_message(msg: discord.Message):  # noqa: N802 — discord.py event name
            await self._handle_message(msg)

    # ---- lifecycle -------------------------------------------------------

    async def start(self, on_message: OnMessage, on_command: OnCommand) -> None:
        self._on_message = on_message
        self._on_command = on_command
        log.info("Discord adapter starting")
        await self._client.start(self._token)

    async def stop(self) -> None:
        if not self._client.is_closed():
            await self._client.close()

    # ---- send primitives -------------------------------------------------

    async def send_text(self, chat_id: str, text: str) -> str:
        ch = await self._channel(chat_id)
        m = await ch.send(content=text)
        return str(m.id)

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        ch = await self._channel(chat_id)
        try:
            m = await ch.fetch_message(int(message_id))
            await m.edit(content=text)
        except discord.NotFound:
            log.debug("Discord edit_text: message %s vanished", message_id)
        except discord.HTTPException as e:
            log.debug("Discord edit failed: %s", e)

    async def send_photo(self, chat_id: str, photo_path: str, caption: str = "") -> None:
        ch = await self._channel(chat_id)
        await ch.send(content=caption or None, file=discord.File(photo_path))

    async def send_typing(self, chat_id: str) -> None:
        try:
            ch = await self._channel(chat_id)
            # `typing()` is an async context manager. Entering once shows the
            # indicator for ~10s; the orchestrator calls us periodically, which
            # keeps it alive.
            async with ch.typing():
                pass
        except Exception:
            pass

    # ---- internals -------------------------------------------------------

    async def _channel(self, chat_id: str):
        cid = int(chat_id)
        ch = self._client.get_channel(cid)
        if ch is None:
            ch = await self._client.fetch_channel(cid)
        return ch

    async def _handle_ready(self):
        user = self._client.user
        log.info("Discord connected as %s (id=%s)", user, user.id if user else "?")

    async def _handle_message(self, msg: discord.Message):
        # Ignore self / other bots so the bot can't recursively trigger itself.
        if msg.author.bot or (self._client.user and msg.author.id == self._client.user.id):
            return

        incoming = self._to_incoming(msg)
        body = msg.content.strip()

        if body.startswith(self._prefix):
            tail = body[len(self._prefix):]
            name, _, args = tail.partition(" ")
            if name and self._on_command:
                await self._on_command(Command(name=name.lower(), args=args.strip()), incoming)
            return

        if self._on_message:
            await self._on_message(incoming)

    @staticmethod
    def _to_incoming(msg: discord.Message) -> IncomingMessage:
        is_dm = isinstance(msg.channel, (discord.DMChannel, discord.GroupChannel))
        return IncomingMessage(
            chat_id=str(msg.channel.id),
            sender_id=str(msg.author.id),
            sender_name=getattr(msg.author, "display_name", None) or msg.author.name,
            text=msg.content,
            is_private=is_dm,
            is_group=msg.guild is not None,
            timestamp=msg.created_at.isoformat() if msg.created_at else "",
        )
