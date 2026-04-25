import os
from dotenv import load_dotenv

load_dotenv()

# Messaging backend selection: "telegram" or "discord"
MESSAGING_BACKEND = os.getenv("MESSAGING_BACKEND", "telegram").lower()

# Backend-specific tokens (only the chosen one is required at runtime)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_COMMAND_PREFIX = os.getenv("DISCORD_COMMAND_PREFIX", "!")

TRIGGER_PATTERN = os.getenv("TRIGGER_PATTERN", "@jarvis")
KIRO_AGENT = os.getenv("KIRO_AGENT", "JARVIS")
CONTAINER_IMAGE = os.getenv("CONTAINER_IMAGE", "kiro-claw-agent:latest")
CONTAINER_TIMEOUT = int(os.getenv("CONTAINER_TIMEOUT", "300"))
BRAIN_DIR = os.getenv("BRAIN_DIR", "")
EXTRA_HOSTS = os.getenv("EXTRA_HOSTS", "")
PROJECTS = os.getenv("PROJECTS", "")

OWNER_USER_ID = os.getenv("OWNER_USER_ID", "").strip()
DEFAULT_EVENT_CHAT_ID = os.getenv("DEFAULT_EVENT_CHAT_ID", "").strip()
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL", "http://homeassistant.local:8123").rstrip("/")

# MCP secrets — passed as env vars to container, never written to files
MCP_SECRETS: dict[str, str] = {
    k: v for k, v in os.environ.items() if k.startswith("MCP_")
}

# chat / channel IDs are kept as strings so Discord snowflakes and Telegram ints both fit.
ALLOWED_CHAT_IDS: set[str] = {
    x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
}


def require_backend_token() -> str:
    """Validate and return the token for the selected backend."""
    if MESSAGING_BACKEND == "telegram":
        if not TELEGRAM_BOT_TOKEN:
            raise RuntimeError("MESSAGING_BACKEND=telegram but TELEGRAM_BOT_TOKEN is not set")
        return TELEGRAM_BOT_TOKEN
    if MESSAGING_BACKEND == "discord":
        if not DISCORD_BOT_TOKEN:
            raise RuntimeError("MESSAGING_BACKEND=discord but DISCORD_BOT_TOKEN is not set")
        return DISCORD_BOT_TOKEN
    raise RuntimeError(f"Unknown MESSAGING_BACKEND: {MESSAGING_BACKEND!r} (expected 'telegram' or 'discord')")
