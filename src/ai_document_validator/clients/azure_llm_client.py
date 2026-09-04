"""Optional Azure OpenAI client for invoice extraction fallback."""

import os
import time
from importlib import import_module
from typing import Any, NamedTuple

from dotenv import load_dotenv

from ai_document_validator.common.logging_config import setup_logger

load_dotenv(override=True)

logger = setup_logger(__name__)


class LLMCompletion(NamedTuple):
    """Raw LLM response and safe provider metadata."""

    content: str
    model_id: str
    latency_ms: float


class LLMUnavailableError(RuntimeError):
    """Raised when optional Azure LLM fallback cannot be used."""


class AzureLLMClient:
    """Lazily invoke a configured Azure OpenAI deployment."""

    def __init__(self) -> None:
        """Initialize without requiring Azure dependencies."""
        self._client: Any | None = None

    def extract_invoice(self, system_prompt: str, extraction_prompt: str) -> LLMCompletion:
        """Request structured invoice extraction from Azure OpenAI.

        Args:
            system_prompt: System instruction defining the JSON contract.
            extraction_prompt: User prompt containing invoice text.

        Returns:
            Raw completion content and provider metadata.

        Raises:
            LLMUnavailableError: If Azure settings, SDK, or provider access are unavailable.
        """
        client, model_id = self._get_client()
        try:
            started_at = time.perf_counter()
            completion = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": extraction_prompt},
                ],
                response_format={"type": "json_object"},
            )
            response_content = completion.choices[0].message.content
            if not response_content:
                raise LLMUnavailableError("Azure OpenAI returned an empty response")
            return LLMCompletion(response_content, model_id, (time.perf_counter() - started_at) * 1000)
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            logger.error("Azure LLM response was invalid: error_type=%s", type(exc).__name__)
            raise LLMUnavailableError("Azure OpenAI returned an invalid response") from exc

    def _get_client(self) -> tuple[Any, str]:
        """Create the Azure SDK client only when fallback is invoked."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not all((endpoint, api_key, api_version, deployment)):
            raise LLMUnavailableError("Azure OpenAI fallback is not configured")
        assert endpoint is not None
        assert api_key is not None
        assert api_version is not None
        assert deployment is not None

        if self._client is None:
            try:
                azure_openai = import_module("openai").AzureOpenAI

                self._client = azure_openai(
                    azure_endpoint=endpoint,
                    api_key=api_key,
                    api_version=api_version,
                )
            except ImportError as exc:
                raise LLMUnavailableError("Install the optional azure dependency group to enable fallback") from exc
        assert self._client is not None
        return self._client, deployment
