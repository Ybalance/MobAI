"""LLM provider factory."""

from mobile_use.infrastructure.llm.base import (
    BaseLLMProvider,
    LLMConfig,
    LLMProviderType,
)
from mobile_use.infrastructure.llm.openai_provider import OpenAIProvider


class LLMFactory:
    """Factory for creating LLM provider instances.

    This factory provides a centralized way to create LLM providers
    based on configuration, supporting multiple provider types.
    """

    _providers: dict[LLMProviderType, type[BaseLLMProvider]] = {
        LLMProviderType.OPENAI: OpenAIProvider,
    }

    @classmethod
    def create(cls, config: LLMConfig) -> BaseLLMProvider:
        """Create an LLM provider from configuration.

        Args:
            config: LLM configuration

        Returns:
            Configured LLM provider instance

        Raises:
            ValueError: If provider type is not supported
        """
        provider_class = cls._providers.get(config.provider)
        if not provider_class:
            raise ValueError(
                f"Unsupported LLM provider: {config.provider.value}. "
                f"Supported providers: {[p.value for p in cls._providers.keys()]}"
            )
        return provider_class(config)

    @classmethod
    def create_from_dict(cls, config_dict: dict) -> BaseLLMProvider:
        """Create an LLM provider from a dictionary configuration.

        Args:
            config_dict: Dictionary with provider configuration

        Returns:
            Configured LLM provider instance
        """
        provider_type = LLMProviderType(config_dict.get("provider", "openai"))
        config = LLMConfig(
            provider=provider_type,
            model=config_dict.get("model", "gpt-4"),
            api_key=config_dict.get("api_key"),
            base_url=config_dict.get("base_url"),
            temperature=config_dict.get("temperature", 0.7),
            max_tokens=config_dict.get("max_tokens"),
            timeout=config_dict.get("timeout", 30),
            retry_attempts=config_dict.get("retry_attempts", 3),
            extra_params=config_dict.get("extra_params", {})
        )
        return cls.create(config)

    @classmethod
    def register_provider(
        cls,
        provider_type: LLMProviderType,
        provider_class: type[BaseLLMProvider]
    ) -> None:
        """Register a new provider type.

        Args:
            provider_type: Provider type enum value
            provider_class: Provider class to register
        """
        cls._providers[provider_type] = provider_class

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        """Get list of supported provider names."""
        return [p.value for p in cls._providers.keys()]
