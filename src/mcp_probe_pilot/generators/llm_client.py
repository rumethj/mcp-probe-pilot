"""LLM client abstraction for test generation.

This module provides a unified interface for interacting with LLM providers
(OpenAI and Anthropic) for generating test scenarios and ground truth.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel

from ..config import LLMConfig


class LLMResponse(BaseModel):
    """Response from an LLM completion request.

    Attributes:
        content: The generated text content.
        model: The model used for generation.
        usage: Token usage information if available.
    """

    content: str
    model: str
    usage: Optional[dict[str, int]] = None


class LLMClientError(Exception):
    """Exception raised when LLM client operations fail."""

    pass


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.

    Provides a unified interface for different LLM providers.
    """

    def __init__(self, config: LLMConfig):
        """Initialize the LLM client.

        Args:
            config: LLM configuration settings.
        """
        self.config = config
        self._api_key: Optional[str] = None

    @property
    def api_key(self) -> str:
        """Get the API key, caching it after first retrieval."""
        if self._api_key is None:
            self._api_key = self.config.get_api_key()
        return self._api_key

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """Generate a completion from the LLM.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for context.

        Returns:
            LLMResponse containing the generated content.

        Raises:
            LLMClientError: If the generation fails.
        """
        pass

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate a JSON response from the LLM.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for context.

        Returns:
            Parsed JSON dictionary from the response.

        Raises:
            LLMClientError: If generation or JSON parsing fails.
        """
        response = await self.generate(prompt, system_prompt)
        try:
            # Try to extract JSON from the response
            content = response.content.strip()

            # Handle markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            return json.loads(content.strip())
        except json.JSONDecodeError as e:
            raise LLMClientError(f"Failed to parse JSON from LLM response: {e}") from e


class OpenAIClient(BaseLLMClient):
    """OpenAI API client implementation."""

    def __init__(self, config: LLMConfig):
        """Initialize the OpenAI client.

        Args:
            config: LLM configuration settings.
        """
        super().__init__(config)
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        """Get the OpenAI client, initializing lazily."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError as e:
                raise LLMClientError(
                    "OpenAI package not installed. Install with: pip install openai"
                ) from e
        return self._client

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """Generate a completion using OpenAI.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for context.

        Returns:
            LLMResponse containing the generated content.

        Raises:
            LLMClientError: If the generation fails.
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self.client.chat.completions.create(
                model=self.config.get_model(),
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            content = response.choices[0].message.content or ""
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return LLMResponse(
                content=content,
                model=response.model,
                usage=usage,
            )

        except Exception as e:
            raise LLMClientError(f"OpenAI generation failed: {e}") from e


class AnthropicClient(BaseLLMClient):
    """Anthropic API client implementation."""

    def __init__(self, config: LLMConfig):
        """Initialize the Anthropic client.

        Args:
            config: LLM configuration settings.
        """
        super().__init__(config)
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        """Get the Anthropic client, initializing lazily."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(api_key=self.api_key)
            except ImportError as e:
                raise LLMClientError(
                    "Anthropic package not installed. Install with: pip install anthropic"
                ) from e
        return self._client

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """Generate a completion using Anthropic.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for context.

        Returns:
            LLMResponse containing the generated content.

        Raises:
            LLMClientError: If the generation fails.
        """
        try:
            kwargs: dict[str, Any] = {
                "model": self.config.get_model(),
                "max_tokens": self.config.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            # Anthropic uses top_p instead of temperature in some cases
            # but does support temperature
            if self.config.temperature > 0:
                kwargs["temperature"] = self.config.temperature

            response = await self.client.messages.create(**kwargs)

            content = ""
            if response.content:
                content = response.content[0].text

            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                }

            return LLMResponse(
                content=content,
                model=response.model,
                usage=usage,
            )

        except Exception as e:
            raise LLMClientError(f"Anthropic generation failed: {e}") from e


class GeminiClient(BaseLLMClient):
    """Google Gemini API client implementation using the new google-genai package."""

    def __init__(self, config: LLMConfig):
        """Initialize the Gemini client.

        Args:
            config: LLM configuration settings.
        """
        super().__init__(config)
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        """Get the Gemini client, initializing lazily."""
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except ImportError as e:
                raise LLMClientError(
                    "Google GenAI package not installed. "
                    "Install with: pip install google-genai"
                ) from e
        return self._client

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """Generate a completion using Gemini.

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system prompt for context.

        Returns:
            LLMResponse containing the generated content.

        Raises:
            LLMClientError: If the generation fails.
        """
        try:
            from google.genai import types

            # Build contents with system instruction support
            contents = prompt
            
            # Configure generation settings
            config = types.GenerateContentConfig(
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
                system_instruction=system_prompt if system_prompt else None,
            )

            # Generate response asynchronously using the aio interface
            response = await self.client.aio.models.generate_content(
                model=self.config.get_model(),
                contents=contents,
                config=config,
            )

            content = ""
            if response.text:
                content = response.text

            # Extract usage metadata
            usage = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "completion_tokens": response.usage_metadata.candidates_token_count,
                    "total_tokens": response.usage_metadata.total_token_count,
                }

            return LLMResponse(
                content=content,
                model=self.config.get_model(),
                usage=usage,
            )

        except Exception as e:
            raise LLMClientError(f"Gemini generation failed: {e}") from e


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """Factory function to create the appropriate LLM client.

    Args:
        config: LLM configuration settings.

    Returns:
        An instance of the appropriate LLM client.

    Raises:
        ValueError: If the provider is not supported.
    """
    if config.provider == "openai":
        return OpenAIClient(config)
    elif config.provider == "anthropic":
        return AnthropicClient(config)
    elif config.provider == "gemini":
        return GeminiClient(config)
    else:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")


class MockLLMClient(BaseLLMClient):
    """Mock LLM client for testing purposes.

    This client returns pre-configured responses without making actual API calls.
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        responses: Optional[list[str]] = None,
    ):
        """Initialize the mock LLM client.

        Args:
            config: Optional LLM configuration (uses defaults if not provided).
            responses: List of responses to return in order. If exhausted,
                the last response is repeated.
        """
        if config is None:
            config = LLMConfig(provider="openai", model="mock-model")
        super().__init__(config)
        self.responses = responses or ["Mock response"]
        self.call_count = 0
        self.call_history: list[dict[str, Any]] = []

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """Return a mock response.

        Args:
            prompt: The user prompt (recorded for testing).
            system_prompt: Optional system prompt (recorded for testing).

        Returns:
            LLMResponse with mock content.
        """
        self.call_history.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "call_number": self.call_count,
        })

        # Get the response at the current index, or the last one if exhausted
        response_index = min(self.call_count, len(self.responses) - 1)
        content = self.responses[response_index]

        self.call_count += 1

        return LLMResponse(
            content=content,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    def reset(self) -> None:
        """Reset the mock client state."""
        self.call_count = 0
        self.call_history = []

    def set_responses(self, responses: list[str]) -> None:
        """Set the responses to return.

        Args:
            responses: List of responses to return in order.
        """
        self.responses = responses
        self.reset()
