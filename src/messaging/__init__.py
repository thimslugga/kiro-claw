"""Messaging adapters — platform-agnostic interface for chat backends."""

from .adapter import (
    MessagingAdapter,
    IncomingMessage,
    Command,
    OnMessage,
    OnCommand,
)

__all__ = [
    "MessagingAdapter",
    "IncomingMessage",
    "Command",
    "OnMessage",
    "OnCommand",
    "build_adapter",
]


def build_adapter(backend: str, token: str, *, command_prefix: str = "!") -> MessagingAdapter:
    """Factory — returns the adapter for the configured backend."""
    backend = backend.lower()
    if backend == "telegram":
        from .telegram_adapter import TelegramAdapter
        return TelegramAdapter(token=token)
    if backend == "discord":
        from .discord_adapter import DiscordAdapter
        return DiscordAdapter(token=token, command_prefix=command_prefix)
    raise ValueError(f"Unknown messaging backend: {backend!r}")
