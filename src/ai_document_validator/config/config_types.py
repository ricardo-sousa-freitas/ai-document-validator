"""Type definitions for configuration and domain objects."""

from datetime import date
from typing import NamedTuple


class InvoiceFieldsExtracted(NamedTuple):
    """Extracted fields from a supplier invoice."""

    supplier_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    total_amount: float | None
    currency: str | None
    tax_id: str | None


class FieldConfidence(NamedTuple):
    """Confidence score for each extracted field."""

    supplier_name: float
    invoice_number: float
    invoice_date: float
    total_amount: float
    currency: float
    tax_id: float


class ExtractionResult(NamedTuple):
    """Result of document extraction."""

    fields: InvoiceFieldsExtracted
    confidence: FieldConfidence
    evidence_snippet: str | None = None
    page_hint: int | None = None
    model_id: str | None = None
    latency_ms: float | None = None


class RuleConfig(NamedTuple):
    """Configuration for rule evaluation."""

    document_type: str
    max_age_days: int = 90
    allowed_currencies: list[str] | None = None
    required_fields: list[str] | None = None


class RuleResult(NamedTuple):
    """Result of a single rule evaluation."""

    rule_id: str
    passed: bool
    message: str


class VerdictStatus(str):
    """Verdict status enumeration."""

    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class Verdict(NamedTuple):
    """Final validation verdict."""

    status: str  # VerdictStatus.PASS | VerdictStatus.FAIL | VerdictStatus.REVIEW
    rule_results: list[RuleResult]
    extracted_fields: InvoiceFieldsExtracted
    field_confidence: FieldConfidence
    model_id: str | None = None
    latency_ms: float | None = None
    total_tokens: int | None = None
