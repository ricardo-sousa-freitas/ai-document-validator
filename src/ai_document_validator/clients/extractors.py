"""Document extraction interfaces and implementations."""

import io
import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from pypdf import PdfReader

from ai_document_validator.common.constants import CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_MISSING
from ai_document_validator.config.config_types import (
    ExtractionResult,
    FieldConfidence,
    InvoiceFieldsExtracted,
)


class Extractor(ABC):
    """Abstract base class for document extractors."""

    @abstractmethod
    def extract(self, content: str, metadata: dict[str, Any] | None = None) -> ExtractionResult:
        """Extract structured fields from document content.

        Args:
            content: Document text content.
            metadata: Optional metadata (e.g., page hints, file name).

        Returns:
            ExtractionResult with fields and confidence scores.
        """
        raise NotImplementedError


class TextExtractor(Extractor):
    """Heuristic-based text extractor using regex patterns."""

    def __init__(self) -> None:
        """Initialize regex patterns for invoice field extraction."""
        # Regex patterns for field detection
        self.patterns = {
            "supplier_name": [
                r"(?:supplier|vendor|company|from)[\s:]+([^\n]+?)(?:\n|$)",
                r"^([A-Z][A-Za-z\s&,.]+?)(?:\n|$)",
            ],
            "invoice_number": [
                r"(?:invoice|inv|reference|ref|no\.?|#)[\s:]+([A-Z0-9-/]+)",
                r"INV-?(\d+)",
            ],
            "invoice_date": [
                r"(?:date|invoice date|inv date|issued)[\s:]+(\d{4}-\d{2}-\d{2})",
                r"(?:date|invoice date)[\s:]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            ],
            "total_amount": [
                r"(?:total|amount|sum|grand total)[\s:]+([0-9]+(?:[.,][0-9]{2})?)",
            ],
            "currency": [
                r"(?:currency|curr|cur|in\s+)([A-Z]{3})",
                r"([A-Z]{3})[\s]?([0-9]+(?:[.,][0-9]{2})?)",
            ],
            "tax_id": [
                r"(?:tax id|vat|tax number|tax no|tin)[\s:]+([A-Z0-9-/]+)",
            ],
        }

    def extract(self, content: str, metadata: dict[str, Any] | None = None) -> ExtractionResult:
        """Extract fields using heuristic regex patterns.

        Args:
            content: Document text content.
            metadata: Optional metadata.

        Returns:
            ExtractionResult with extracted fields and confidence scores.
        """
        fields = self._extract_fields(content)
        confidence = self._compute_confidence(fields)
        evidence_snippet = content[:200] if content else None

        return ExtractionResult(
            fields=fields,
            confidence=confidence,
            evidence_snippet=evidence_snippet,
            page_hint=1,
            model_id="heuristic_v1",
            latency_ms=5.0,
        )

    def _extract_fields(self, content: str) -> InvoiceFieldsExtracted:
        """Extract individual fields using regex patterns."""
        supplier_name = self._extract_field(content, "supplier_name")
        invoice_number = self._extract_field(content, "invoice_number")
        invoice_date_str = self._extract_field(content, "invoice_date")
        total_amount_str = self._extract_field(content, "total_amount")
        currency = self._extract_field(content, "currency")
        tax_id = self._extract_field(content, "tax_id")

        invoice_date = self._parse_invoice_date(invoice_date_str)
        total_amount = self._parse_total_amount(total_amount_str)

        return InvoiceFieldsExtracted(
            supplier_name=supplier_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            total_amount=total_amount,
            currency=currency,
            tax_id=tax_id,
        )

    def _parse_invoice_date(self, invoice_date_str: str | None) -> date | None:
        """Parse invoice date strings from common formats."""
        if not invoice_date_str:
            return None

        try:
            if len(invoice_date_str) == 10 and invoice_date_str[4] == "-":
                return date.fromisoformat(invoice_date_str)

            for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(invoice_date_str, fmt).date()
                except ValueError:
                    continue
        except (ValueError, AttributeError):
            return None

        return None

    def _parse_total_amount(self, total_amount_str: str | None) -> float | None:
        """Parse monetary strings into floats."""
        if not total_amount_str:
            return None

        try:
            cleaned = total_amount_str.replace(",", ".").replace(" ", "")
            return float(cleaned)
        except ValueError:
            return None

    def _extract_field(self, content: str, field_name: str) -> str | None:
        """Extract a single field using regex patterns.

        Args:
            content: Document text content.
            field_name: Name of the field to extract.

        Returns:
            Extracted field value or None.
        """
        patterns = self.patterns.get(field_name, [])
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    def _compute_confidence(self, fields: InvoiceFieldsExtracted) -> FieldConfidence:
        """Compute confidence scores for each field.

        Confidence scoring:
        - CONFIDENCE_HIGH (0.9): Field is present
        - CONFIDENCE_MISSING (0.0): Field is None

        Args:
            fields: Extracted fields.

        Returns:
            FieldConfidence with scores for each field.
        """
        return FieldConfidence(
            supplier_name=CONFIDENCE_HIGH if fields.supplier_name else CONFIDENCE_MISSING,
            invoice_number=CONFIDENCE_HIGH if fields.invoice_number else CONFIDENCE_MISSING,
            invoice_date=CONFIDENCE_HIGH if fields.invoice_date else CONFIDENCE_MISSING,
            total_amount=CONFIDENCE_HIGH if fields.total_amount is not None else CONFIDENCE_MISSING,
            currency=CONFIDENCE_MEDIUM if fields.currency else CONFIDENCE_MISSING,  # Often harder to detect
            tax_id=CONFIDENCE_MEDIUM if fields.tax_id else CONFIDENCE_MISSING,  # Optional field
        )


class FixtureExtractor(Extractor):
    """Loads extraction results from pre-defined fixtures (YAML/JSON)."""

    def __init__(self, fixture_dir: str | Path) -> None:
        """Initialize with path to fixture directory.

        Args:
            fixture_dir: Path to directory containing fixture YAML files.
        """
        self.fixture_dir = Path(fixture_dir)
        self.fixtures: dict[str, dict[str, Any]] = {}
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """Load all fixture files from the directory."""
        if not self.fixture_dir.exists():
            return

        for yaml_file in self.fixture_dir.glob("*.yaml"):
            with open(yaml_file, encoding="utf-8") as f:
                fixtures_in_file: dict[str, Any] = yaml.safe_load(f) or {}
                self.fixtures.update(fixtures_in_file)

    def extract(self, content: str, metadata: dict[str, Any] | None = None) -> ExtractionResult:
        """Extract from fixture data.

        Args:
            content: Document identifier or content (used to find matching fixture).
            metadata: Optional metadata containing fixture_id.

        Returns:
            ExtractionResult from fixture data.
        """
        fixture_id = metadata.get("fixture_id") if metadata else None
        if not fixture_id:
            fixture_id = content[:50] if content else "default"

        fixture = self.fixtures.get(fixture_id)
        if not fixture:
            # Fallback: create empty result
            return ExtractionResult(
                fields=InvoiceFieldsExtracted(
                    supplier_name=None,
                    invoice_number=None,
                    invoice_date=None,
                    total_amount=None,
                    currency=None,
                    tax_id=None,
                ),
                confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                model_id="fixture_v1",
                latency_ms=0.0,
            )

        # Parse fixture data
        fields_data = fixture.get("fields", {})
        invoice_date_str = fields_data.get("invoice_date")
        invoice_date: date | None = None
        if invoice_date_str:
            try:
                invoice_date = date.fromisoformat(invoice_date_str)
            except (ValueError, TypeError):
                invoice_date = None

        fields = InvoiceFieldsExtracted(
            supplier_name=fields_data.get("supplier_name"),
            invoice_number=fields_data.get("invoice_number"),
            invoice_date=invoice_date,
            total_amount=fields_data.get("total_amount"),
            currency=fields_data.get("currency"),
            tax_id=fields_data.get("tax_id"),
        )

        confidence_data = fixture.get("confidence", {})
        confidence = FieldConfidence(
            supplier_name=float(confidence_data.get("supplier_name", 0.9)),
            invoice_number=float(confidence_data.get("invoice_number", 0.9)),
            invoice_date=float(confidence_data.get("invoice_date", 0.9)),
            total_amount=float(confidence_data.get("total_amount", 0.9)),
            currency=float(confidence_data.get("currency", 0.7)),
            tax_id=float(confidence_data.get("tax_id", 0.7)),
        )

        return ExtractionResult(
            fields=fields,
            confidence=confidence,
            evidence_snippet=fixture.get("evidence_snippet"),
            page_hint=fixture.get("page_hint", 1),
            model_id="fixture_v1",
            latency_ms=0.0,
        )


class PDFExtractor(Extractor):
    """Extracts text from PDF files and applies heuristic extraction."""

    def __init__(self) -> None:
        """Initialize PDF extractor with text extractor."""

        self.pdf_reader = PdfReader
        self.text_extractor = TextExtractor()

    def extract(self, content: str | bytes, metadata: dict[str, Any] | None = None) -> ExtractionResult:
        """Extract text from PDF and apply heuristic extraction.

        Args:
            content: PDF file path (str) or PDF bytes.
            metadata: Optional metadata.

        Returns:
            ExtractionResult with extracted fields from PDF text.
        """
        try:
            # Read PDF
            if isinstance(content, str):
                pdf_file = Path(content)
                with open(pdf_file, "rb") as f:
                    pdf_reader = self.pdf_reader(f)
                    text = self._extract_text_from_pdf(pdf_reader)
            else:
                pdf_reader = self.pdf_reader(io.BytesIO(content))
                text = self._extract_text_from_pdf(pdf_reader)

            # Apply text extraction
            return self.text_extractor.extract(text, metadata)
        except Exception as e:
            raise ValueError(f"Failed to extract PDF: {e}") from e

    def _extract_text_from_pdf(self, pdf_reader) -> str:  # type: ignore
        """Extract text from PDF reader.

        Args:
            pdf_reader: pypdf PdfReader instance.

        Returns:
            Concatenated text from all pages.
        """
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
