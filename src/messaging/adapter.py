"""Platform-agnostic messaging interface.

Adapters translate between a concrete chat platform (Telegram, Discord, ...)
and the rest of kiro-claw, which only deals in `IncomingMessage` / `Command`
plus four primitive send operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, runtime_checkable


@dataclass
class IncomingMessage:
    """A message received from any chat platform."""

    chat_id: str            # channel / chat identifier (always str)
    sender_id: str          # author identifier (always str)
    sender_name: str
    text: str               # message body or photo caption ("" if neither)
    is_private: bool        # DM / private chat
    is_group: bool          # group chat / guild channel
    timestamp: str          # ISO-8601


@dataclass
class Command:
    """A parsed command invocation, e.g. `/ping` or `!cancel task-abc123`."""

    name: str               # without leading slash/prefix, lowercase
    args: str               # everything after the command, trimmed


OnMessage = Callable[[IncomingMessage], Awaitable[None]]
OnCommand = Callable[[Command, IncomingMessage], Awaitable[None]]


@runtime_checkable
class MessagingAdapter(Protocol):
    """The contract every chat backend must satisfy."""

    # Hard upper bound for a single message on this platform.
    MAX_MESSAGE_LENGTH: int

    async def start(self, on_message: OnMessage, on_command: OnCommand) -> None:
        """Connect to the platform and dispatch incoming events.

        Must run until cancelled. Implementations decide whether they spawn
        their own background loop or run inline.
        """

    async def stop(self) -> None:
        """Disconnect cleanly."""

    async def send_text(self, chat_id: str, text: str) -> str:
        """Send a text message; return the platform-specific message id (str)."""

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        """Replace the body of a previously-sent message."""

    async def send_photo(self, chat_id: str, photo_path: str, caption: str = "") -> None:
        """Upload an image with an optional caption."""

    async def send_typing(self, chat_id: str) -> None:
        """Show a transient 'typing' / 'is uploading' indicator."""
