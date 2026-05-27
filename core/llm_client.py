"""Provider detection and client construction for LLM calls.

Priority: Anthropic (if anthropic.api_key / ANTHROPIC_API_KEY is set) → OpenAI-compatible.
"""
import os
from typing import Optional
from core.config import cfg
from core.log import logger

try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def get_anthropic_api_key() -> str:
    return str(cfg.get("anthropic.api_key", None, silent=True) or os.getenv("ANTHROPIC_API_KEY", "") or "")


def get_anthropic_model(override: Optional[str] = None) -> str:
    return str(
        override
        or cfg.get("anthropic.model", None, silent=True)
        or os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
        or "claude-opus-4-7"
    )


def get_openai_api_key() -> str:
    return str(cfg.get("openai.api_key", None, silent=True) or os.getenv("OPENAI_API_KEY", "") or "")


def get_openai_base_url() -> str:
    raw = str(
        cfg.get("openai.base_url", None, silent=True)
        or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        or "https://api.openai.com/v1"
    )
    return raw if raw.endswith("/") else raw + "/"


def get_openai_model(override: Optional[str] = None) -> str:
    return str(
        override
        or cfg.get("openai.model", None, silent=True)
        or os.getenv("OPENAI_MODEL", "gpt-4o")
        or "gpt-4o"
    )


def build_anthropic_client() -> Optional["AsyncAnthropic"]:
    """Return AsyncAnthropic if anthropic.api_key / ANTHROPIC_API_KEY is set, else None."""
    if not ANTHROPIC_AVAILABLE:
        return None
    key = get_anthropic_api_key()
    if key:
        return AsyncAnthropic(api_key=key)
    return None


def build_openai_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> Optional["AsyncOpenAI"]:
    """Return AsyncOpenAI if an API key is available, else None."""
    if not OPENAI_AVAILABLE:
        return None
    key = api_key or get_openai_api_key()
    url = base_url or get_openai_base_url()
    if key:
        return AsyncOpenAI(api_key=key, base_url=url)
    return None
