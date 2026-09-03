"""Shared pytest fixtures and configuration."""

from datetime import date

import pytest

from ai_document_validator.config.config_types import (
    ExtractionResult,
    FieldConfidence,
    InvoiceFieldsExtracted,
    RuleConfig,
)
from ai_document_validator.process.extraction.extractors import TextExtractor


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    """Sample extraction result for testing."""
    return ExtractionResult(
        fields=InvoiceFieldsExtracted(
            supplier_name="Test Corp",
            invoice_number="INV-001",
            invoice_date=date(2024, 9, 1),
            total_amount=1000.0,
            currency="EUR",
            tax_id="VAT-123",
        ),
        confidence=FieldConfidence(0.9, 0.9, 0.9, 0.9, 0.8, 0.7),
        evidence_snippet="Test invoice",
        page_hint=1,
        model_id="test_v1",
        latency_ms=5.0,
    )


@pytest.fixture
def sample_rule_config() -> RuleConfig:
    """Sample rule configuration for testing."""
    return RuleConfig(
        document_type="SUPPLIER_INVOICE",
        max_age_days=90,
        allowed_currencies=["EUR", "GBP", "USD"],
        required_fields=None,
    )


@pytest.fixture
def text_extractor() -> TextExtractor:
    """TextExtractor instance for testing."""
    return TextExtractor()
