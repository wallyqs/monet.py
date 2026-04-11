"""Model providers — static registry of supported LLM configurations."""

import os
from dataclasses import dataclass

NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"


@dataclass
class Provider:
    """Describes how to reach a specific model via LiteLLM / dspy.LM."""

    model: str  # display name used in /model selector
    label: str  # provider label ("Anthropic", "OpenAI", "NVIDIA NIM")
    api_model: (
        str  # LiteLLM model identifier (e.g. "anthropic/claude-haiku-4-5-20251001")
    )
    api_key_env: str  # env var holding the API key
    fallback_api_key_env: str = ""  # fallback env var
    api_base: str = ""  # custom endpoint (empty = provider default)

    def resolve_api_key(self) -> str:
        """Return the API key, trying primary then fallback env var."""
        key = os.environ.get(self.api_key_env, "")
        if not key and self.fallback_api_key_env:
            key = os.environ.get(self.fallback_api_key_env, "")
        return key


AVAILABLE_PROVIDERS: list[Provider] = [
    # Anthropic
    Provider(
        "claude-haiku-4-5",
        "Anthropic",
        "anthropic/claude-haiku-4-5-20251001",
        "ANTHROPIC_API_KEY",
    ),
    Provider(
        "claude-sonnet-4",
        "Anthropic",
        "anthropic/claude-sonnet-4-20250514",
        "ANTHROPIC_API_KEY",
    ),
    Provider(
        "claude-opus-4",
        "Anthropic",
        "anthropic/claude-opus-4-20250514",
        "ANTHROPIC_API_KEY",
    ),
    # OpenAI
    Provider("gpt-4o", "OpenAI", "openai/gpt-4o", "OPENAI_API_KEY"),
    Provider("gpt-4o-mini", "OpenAI", "openai/gpt-4o-mini", "OPENAI_API_KEY"),
    Provider("o3", "OpenAI", "openai/o3", "OPENAI_API_KEY"),
    Provider("o4-mini", "OpenAI", "openai/o4-mini", "OPENAI_API_KEY"),
    # NVIDIA NIM (OpenAI-compatible endpoint)
    # LiteLLM strips the first "openai/" as a routing prefix — the remainder is
    # sent as the model name in the request body.  NVIDIA NIM expects the full
    # organisation-qualified name (e.g. "openai/gpt-oss-20b"), so models whose
    # NVIDIA identifier already starts with "openai/" need a double prefix.
    Provider(
        "gpt-oss-20b",
        "NVIDIA NIM",
        "openai/openai/gpt-oss-20b",
        "NVIDIA_API_KEY",
        "OPENAI_API_KEY",
        NVIDIA_API_BASE,
    ),
    Provider(
        "gpt-oss-120b",
        "NVIDIA NIM",
        "openai/openai/gpt-oss-120b",
        "NVIDIA_API_KEY",
        "OPENAI_API_KEY",
        NVIDIA_API_BASE,
    ),
    Provider(
        "qwen3-coder-480b",
        "NVIDIA NIM",
        "openai/qwen/qwen3-coder-480b-a35b-instruct",
        "NVIDIA_API_KEY",
        "OPENAI_API_KEY",
        NVIDIA_API_BASE,
    ),
    Provider(
        "kimi-k2.5",
        "NVIDIA NIM",
        "openai/moonshotai/kimi-k2.5",
        "NVIDIA_API_KEY",
        "OPENAI_API_KEY",
        NVIDIA_API_BASE,
    ),
]

DEFAULT_PROVIDER = AVAILABLE_PROVIDERS[0]  # claude-haiku-4-5


def provider_by_name(name: str) -> Provider | None:
    """Look up a provider by its display name."""
    for p in AVAILABLE_PROVIDERS:
        if p.model == name:
            return p
    return None
