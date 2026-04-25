"""Adapter-contract + factory tests for the messaging layer."""

import pytest

from src.messaging import (
    Command,
    IncomingMessage,
    MessagingAdapter,
    build_adapter,
)
from src.messaging.discord_adapter import DiscordAdapter
from src.messaging.telegram_adapter import TelegramAdapter


def test_build_adapter_telegram():
    adapter = build_adapter("telegram", "fake-token")
    assert isinstance(adapter, TelegramAdapter)
    assert adapter.MAX_MESSAGE_LENGTH == 4096


def test_build_adapter_discord():
    adapter = build_adapter("discord", "fake-token")
    assert isinstance(adapter, DiscordAdapter)
    assert adapter.MAX_MESSAGE_LENGTH == 2000


def test_build_adapter_unknown():
    with pytest.raises(ValueError):
        build_adapter("matrix", "x")


@pytest.mark.parametrize(
    "adapter",
    [
        TelegramAdapter(token="fake"),
        DiscordAdapter(token="fake"),
    ],
)
def test_adapter_satisfies_protocol(adapter):
    """Both backends must satisfy the runtime-checkable Protocol."""
    assert isinstance(adapter, MessagingAdapter)


def test_incoming_message_construction():
    im = IncomingMessage(
        chat_id="42",
        sender_id="7",
        sender_name="Alice",
        text="hi",
        is_private=True,
        is_group=False,
        timestamp="2026-04-25T00:00:00+00:00",
    )
    assert im.chat_id == "42"
    assert im.is_private is True


def test_command_construction():
    c = Command(name="cancel", args="task-abc")
    assert c.name == "cancel"
    assert c.args == "task-abc"
