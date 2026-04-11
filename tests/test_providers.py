"""Tests for the provider registry."""

import os

from monet.providers import (
    AVAILABLE_PROVIDERS,
    DEFAULT_PROVIDER,
    NVIDIA_API_BASE,
    Provider,
    provider_by_name,
)


class TestProvider:
    def test_fields(self):
        p = Provider("test", "TestLabel", "openai/test", "TEST_KEY")
        assert p.model == "test"
        assert p.label == "TestLabel"
        assert p.api_model == "openai/test"
        assert p.api_key_env == "TEST_KEY"
        assert p.fallback_api_key_env == ""
        assert p.api_base == ""

    def test_resolve_api_key_primary(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        p = Provider("m", "L", "openai/m", "MY_KEY")
        assert p.resolve_api_key() == "secret123"

    def test_resolve_api_key_fallback(self, monkeypatch):
        monkeypatch.delenv("PRIMARY_KEY", raising=False)
        monkeypatch.setenv("FALLBACK_KEY", "fallback_val")
        p = Provider("m", "L", "openai/m", "PRIMARY_KEY", "FALLBACK_KEY")
        assert p.resolve_api_key() == "fallback_val"

    def test_resolve_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("NOPE_KEY", raising=False)
        p = Provider("m", "L", "openai/m", "NOPE_KEY")
        assert p.resolve_api_key() == ""

    def test_resolve_api_key_primary_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("PRI", "primary_val")
        monkeypatch.setenv("FAL", "fallback_val")
        p = Provider("m", "L", "openai/m", "PRI", "FAL")
        assert p.resolve_api_key() == "primary_val"


class TestAvailableProviders:
    def test_not_empty(self):
        assert len(AVAILABLE_PROVIDERS) > 0

    def test_unique_names(self):
        names = [p.model for p in AVAILABLE_PROVIDERS]
        assert len(names) == len(set(names))

    def test_default_is_first(self):
        assert DEFAULT_PROVIDER is AVAILABLE_PROVIDERS[0]

    def test_all_have_api_model(self):
        for p in AVAILABLE_PROVIDERS:
            assert p.api_model, f"{p.model} has empty api_model"

    def test_all_have_api_key_env(self):
        for p in AVAILABLE_PROVIDERS:
            assert p.api_key_env, f"{p.model} has empty api_key_env"

    def test_nvidia_providers_have_api_base(self):
        for p in AVAILABLE_PROVIDERS:
            if p.label == "NVIDIA NIM":
                assert p.api_base == NVIDIA_API_BASE
                assert p.fallback_api_key_env == "OPENAI_API_KEY"

    def test_anthropic_providers(self):
        anthropic = [p for p in AVAILABLE_PROVIDERS if p.label == "Anthropic"]
        assert len(anthropic) >= 3
        for p in anthropic:
            assert p.api_model.startswith("anthropic/")
            assert p.api_key_env == "ANTHROPIC_API_KEY"

    def test_openai_providers(self):
        openai = [p for p in AVAILABLE_PROVIDERS if p.label == "OpenAI"]
        assert len(openai) >= 4
        for p in openai:
            assert p.api_model.startswith("openai/")
            assert p.api_key_env == "OPENAI_API_KEY"


class TestProviderByName:
    def test_found(self):
        p = provider_by_name("claude-haiku-4-5")
        assert p is not None
        assert p.label == "Anthropic"

    def test_not_found(self):
        assert provider_by_name("nonexistent") is None

    def test_all_findable(self):
        for p in AVAILABLE_PROVIDERS:
            assert provider_by_name(p.model) is p
