"""Tests for heuristic-first hybrid extraction decisions."""

from pathlib import Path
from typing import Any

import pytest

from ai_document_validator.config.config_types import ExtractionResult
from ai_document_validator.process.extraction.extractors import Extractor, PDFExtractor, TextExtractor
from ai_document_validator.process.extraction.hybrid import HybridExtractor


class RecordingFallbackExtractor(Extractor):
    """Fallback test double that records the content passed to it."""

    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.received_content: str | bytes | None = None

    def extract(self, content: str | bytes, metadata: dict[str, Any] | None = None) -> ExtractionResult:
        """Record fallback input and return a prepared extraction result."""
        self.received_content = content
        return self.result


@pytest.mark.unit
class TestHybridExtractor:
    """Test LLM fallback decisions without invoking an LLM."""

    def test_skips_fallback_for_complete_high_confidence_document(self) -> None:
        """Do not request fallback when required fields are strong heuristic matches."""
        extractor = HybridExtractor(
            heuristic_extractor=TextExtractor(),
            required_fields=["supplier_name", "invoice_number", "invoice_date", "total_amount"],
            confidence_threshold=0.6,
        )

        result = extractor.extract(
            "Supplier: Example Corp\n" "Invoice Number: INV-1\n" "Date: 2026-09-01\n" "Total Amount: 100.00 EUR\n"
        )

        assert result.fallback_required is False
        assert result.fallback_reasons == []

    def test_requests_fallback_for_missing_required_field(self) -> None:
        """Request fallback when a required field is not extracted."""
        extractor = HybridExtractor(
            heuristic_extractor=TextExtractor(),
            required_fields=["supplier_name", "invoice_number"],
            confidence_threshold=0.6,
        )

        result = extractor.extract("Supplier: Example Corp\n")

        assert result.fallback_required is True
        assert result.fallback_reasons == ["missing_required_field:invoice_number"]

    def test_requests_fallback_for_low_confidence_field(self) -> None:
        """Request fallback when a required field uses a weak regex tier."""
        extractor = HybridExtractor(
            heuristic_extractor=TextExtractor(),
            required_fields=["total_amount"],
            confidence_threshold=0.6,
        )

        result = extractor.extract("Supplier: Example Corp\nAmount: 100.00\n")

        assert result.fallback_required is True
        assert result.fallback_reasons == ["low_confidence_field:total_amount"]

    def test_passes_extracted_pdf_text_to_fallback(self) -> None:
        """Convert PDF bytes to text before invoking the fallback extractor."""
        pdf_path = Path(__file__).parent.parent / "fixtures" / "documents" / "inv_001_clean_eur.pdf"
        pdf_bytes = pdf_path.read_bytes()
        heuristic_extractor = PDFExtractor()
        fallback_extractor = RecordingFallbackExtractor(heuristic_extractor.extract(pdf_bytes))
        hybrid_extractor = HybridExtractor(
            heuristic_extractor=heuristic_extractor,
            required_fields=["field_not_in_invoice_schema"],
            confidence_threshold=0.6,
            fallback_extractor=fallback_extractor,
        )

        result = hybrid_extractor.extract(pdf_bytes)

        assert result.fallback_used is True
        assert isinstance(fallback_extractor.received_content, str)
        assert "NORDWIND" in fallback_extractor.received_content
