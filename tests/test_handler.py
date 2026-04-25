"""Tests for the platform-agnostic MessageHandler.

DB isolation is handled by `tests/conftest.py::isolated_db_path`.
"""

from unittest.mock import AsyncMock

import pytest

from src import config
from src.handler import MessageHandler, _split_message
from src.messaging import Command, IncomingMessage


@pytest.fixture
def adapter():
    a = AsyncMock()
    a.MAX_MESSAGE_LENGTH = 2000
    return a


@pytest.fixture
def open_acl():
    """Allow all chat IDs for the duration of the test."""
    old = config.ALLOWED_CHAT_IDS
    config.ALLOWED_CHAT_IDS = set()
    # handler caches no copy, but `is_allowed` reads it lazily — verify:
    import src.handler as h
    h.ALLOWED_CHAT_IDS = set()
    yield
    config.ALLOWED_CHAT_IDS = old
    h.ALLOWED_CHAT_IDS = old


def _msg(**overrides) -> IncomingMessage:
    base = dict(
        chat_id="100",
        sender_id="42",
        sender_name="Alice",
        text="hello",
        is_private=True,
        is_group=False,
        timestamp="2026-04-25T00:00:00+00:00",
    )
    base.update(overrides)
    return IncomingMessage(**base)


# ---- _split_message --------------------------------------------------------

def test_split_short():
    assert _split_message("hi", limit=100) == ["hi"]


def test_split_long():
    text = "a" * 250
    chunks = _split_message(text, limit=100)
    assert len(chunks) == 3
    assert "".join(chunks) == text
    assert all(len(c) <= 100 for c in chunks)


# ---- commands --------------------------------------------------------------

@pytest.mark.asyncio
async def test_ping_command(adapter, open_acl):
    h = MessageHandler(adapter)
    await h.on_command(Command(name="ping", args=""), _msg())
    adapter.send_text.assert_awaited_once()
    args, _ = adapter.send_text.await_args
    assert args[0] == "100"
    assert "JARVIS" in args[1]


@pytest.mark.asyncio
async def test_chatid_command(adapter, open_acl):
    h = MessageHandler(adapter)
    await h.on_command(Command(name="chatid", args=""), _msg(chat_id="999"))
    adapter.send_text.assert_awaited_once()
    args, _ = adapter.send_text.await_args
    assert "999" in args[1]


@pytest.mark.asyncio
async def test_tasks_command_empty(adapter, open_acl):
    h = MessageHandler(adapter)
    await h.on_command(Command(name="tasks", args=""), _msg())
    adapter.send_text.assert_awaited_once()
    _, args, _ = (None, *adapter.send_text.await_args)
    assert "No active tasks" in adapter.send_text.await_args.args[1]


@pytest.mark.asyncio
async def test_cancel_command_missing_arg(adapter, open_acl):
    h = MessageHandler(adapter)
    await h.on_command(Command(name="cancel", args=""), _msg())
    adapter.send_text.assert_awaited_once()
    assert "Usage" in adapter.send_text.await_args.args[1]


@pytest.mark.asyncio
async def test_command_blocked_by_acl(adapter):
    """Non-allowlisted chats get no reply at all."""
    import src.handler as h
    old = h.ALLOWED_CHAT_IDS
    h.ALLOWED_CHAT_IDS = {"999"}
    try:
        handler = MessageHandler(adapter)
        await handler.on_command(Command(name="ping", args=""), _msg(chat_id="100"))
        adapter.send_text.assert_not_called()
    finally:
        h.ALLOWED_CHAT_IDS = old


@pytest.mark.asyncio
async def test_unknown_command_silent(adapter, open_acl):
    h = MessageHandler(adapter)
    await h.on_command(Command(name="banana", args=""), _msg())
    adapter.send_text.assert_not_called()


# ---- group routing ---------------------------------------------------------

@pytest.mark.asyncio
async def test_group_observes_non_owner_silently(adapter, open_acl, monkeypatch):
    """In a group, messages from non-owners are stored but never replied to."""
    import src.handler as h
    monkeypatch.setattr(h, "OWNER_USER_ID", "owner-id-7")
    handler = MessageHandler(adapter)

    msg = _msg(chat_id="g1", sender_id="someone-else", sender_name="Bob",
               text="@jarvis hello", is_private=False, is_group=True)
    await handler.on_message(msg)
    adapter.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_group_no_owner_configured_never_replies(adapter, open_acl, monkeypatch):
    """Without OWNER_USER_ID set, the bot must not reply in groups (safety default)."""
    import src.handler as h
    monkeypatch.setattr(h, "OWNER_USER_ID", "")
    handler = MessageHandler(adapter)

    msg = _msg(chat_id="g1", sender_id="anyone", sender_name="Bob",
               text="@jarvis hello", is_private=False, is_group=True)
    await handler.on_message(msg)
    adapter.send_text.assert_not_called()
