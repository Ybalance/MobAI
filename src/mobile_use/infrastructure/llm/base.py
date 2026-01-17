"""Base LLM provider interface and common types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LLMProviderType(Enum):
    """Supported LLM provider types."""
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"
    LOCAL = "local"


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""
    provider: LLMProviderType
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout: int = 30
    retry_attempts: int = 3
    extra_params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("Temperature must be between 0 and 2")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("Max tokens must be positive")


@dataclass
class LLMMessage:
    """A message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str
    images: list[bytes] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "role": self.role,
            "content": self.content
        }


@dataclass
class LLMResponse:
    """Response from LLM provider."""
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    raw_response: Any = None

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self.usage.get("total_tokens", 0)

    @property
    def prompt_tokens(self) -> int:
        """Get prompt tokens used."""
        return self.usage.get("prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        """Get completion tokens used."""
        return self.usage.get("completion_tokens", 0)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All LLM providers must implement this interface to ensure
    consistent behavior across different AI services.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider (e.g., validate API key)."""
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any
    ) -> str:
        """Generate text from a prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text content
        """
        pass

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        **kwargs: Any
    ) -> LLMResponse:
        """Send a chat conversation.

        Args:
            messages: List of conversation messages
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def analyze_image(
        self,
        image: bytes,
        prompt: str,
        **kwargs: Any
    ) -> str:
        """Analyze an image with a prompt.

        Args:
            image: Image bytes
            prompt: Analysis prompt
            **kwargs: Additional provider-specific parameters

        Returns:
            Analysis result text
        """
        pass

    async def generate_with_retry(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any
    ) -> str:
        """Generate with automatic retry on failure."""
        import asyncio

        last_error: Exception | None = None
        for attempt in range(self.config.retry_attempts):
            try:
                return await self.generate(prompt, system_prompt, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        raise last_error or Exception("Generation failed")

    @property
    def is_initialized(self) -> bool:
        """Check if provider is initialized."""
        return self._initialized

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return self.config.provider.value

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self.config.model
