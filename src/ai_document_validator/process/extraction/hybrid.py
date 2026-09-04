"""Heuristic-first extraction with an explicit LLM fallback decision."""

from typing import Any, NamedTuple

from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.config_types import ExtractionResult
from ai_document_validator.process.extraction.extractors import Extractor, PDFExtractor

logger = setup_logger(__name__)


class HybridExtractionResult(NamedTuple):
    """Heuristic extraction and the decision whether an LLM fallback is needed."""

    extraction: ExtractionResult
    fallback_required: bool
    fallback_reasons: list[str]
    fallback_used: bool = False


class HybridExtractor:
    """Run a heuristic extractor before requesting an optional LLM fallback."""

    def __init__(
        self,
        heuristic_extractor: Extractor,
        required_fields: list[str],
        confidence_threshold: float,
        fallback_extractor: Extractor | None = None,
    ) -> None:
        """Initialize hybrid fallback criteria.

        Args:
            heuristic_extractor: Deterministic extractor used first for every document.
            required_fields: Fields required before skipping an LLM fallback.
            confidence_threshold: Minimum acceptable confidence for present required fields.
            fallback_extractor: Optional LLM extractor used when the heuristic result is insufficient.
        """
        self.heuristic_extractor = heuristic_extractor
        self.required_fields = required_fields
        self.confidence_threshold = confidence_threshold
        self.fallback_extractor = fallback_extractor

    def extract(self, content: str | bytes, metadata: dict[str, Any] | None = None) -> HybridExtractionResult:
        """Extract heuristically and calculate whether LLM fallback is required.

        Args:
            content: Text content or PDF bytes accepted by the heuristic extractor.
            metadata: Optional document metadata.

        Returns:
            Heuristic or LLM extraction plus the fallback decision.
        """
        extraction = self.heuristic_extractor.extract(content, metadata)
        fallback_reasons = self._fallback_reasons(extraction)
        fallback_required = bool(fallback_reasons)
        fallback_used = False

        fallback_content: str | bytes = content
        if (
            fallback_required
            and self.fallback_extractor is not None
            and isinstance(content, bytes)
            and isinstance(self.heuristic_extractor, PDFExtractor)
        ):
            fallback_content = self.heuristic_extractor.extract_text(content)

        if fallback_required and self.fallback_extractor is not None and isinstance(fallback_content, str):
            try:
                extraction = self.fallback_extractor.extract(fallback_content, metadata)
                fallback_used = True
            except (RuntimeError, TypeError, ValueError) as exc:
                fallback_reasons.append(f"fallback_unavailable:{type(exc).__name__}")

        logger.info(
            "Hybrid extraction completed: fallback_required=%s fallback_used=%s reason_count=%d",
            fallback_required,
            fallback_used,
            len(fallback_reasons),
        )
        return HybridExtractionResult(extraction, fallback_required, fallback_reasons, fallback_used)

    def _fallback_reasons(self, extraction: ExtractionResult) -> list[str]:
        """Build reasons for escalating a heuristic result to an LLM provider."""
        reasons: list[str] = []
        for field_name in self.required_fields:
            field_value = getattr(extraction.fields, field_name, None)
            if field_value is None or field_value == "":
                reasons.append(f"missing_required_field:{field_name}")
                continue

            confidence = getattr(extraction.confidence, field_name, 0.0)
            if confidence < self.confidence_threshold:
                reasons.append(f"low_confidence_field:{field_name}")
        return reasons
