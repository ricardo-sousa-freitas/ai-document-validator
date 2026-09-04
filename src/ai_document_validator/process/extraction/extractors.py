"""Document extraction interfaces and implementations."""

import io
import json
import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Any, NamedTuple

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ai_document_validator.clients.azure_llm_client import AzureLLMClient, LLMCompletion
from ai_document_validator.common.constants import (
    CONFIDENCE_FALLBACK,
    CONFIDENCE_HIGH,
    CONFIDENCE_MISSING,
    CONFIDENCE_SECONDARY,
)
from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.config_loader_prompts import ConfigLoaderPrompts
from ai_document_validator.config.config_types import (
    ExtractionResult,
    FieldConfidence,
    InvoiceFieldsExtracted,
)

logger = setup_logger(__name__)


class UnsupportedDocumentError(ValueError):
    """Raised when a document is valid but unsupported by the extraction path."""


class FieldEvidence(NamedTuple):
    """Evidence metadata for one regex-extracted field."""

    pattern_index: int
    candidate_count: int


class Extractor(ABC):
    """Abstract base class for document extractors."""

    @abstractmethod
    def extract(self, content: str | bytes, metadata: dict[str, Any] | None = None) -> ExtractionResult:
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
                # Explicit labels are the strongest evidence.
                r"(?im)^\s*(?:supplier|vendor|company|from)\s*:\s*([^\n]+)",
                # The first non-empty header line is a weaker regex signal.
                r"(?im)\A(?:[ \t]*\r?\n)*[ \t]*(?!invoice\b|factura\b|credit note\b|commercial invoice\b)"
                r"([A-Za-z][A-Za-z0-9 &.,'/-]{2,})[ \t]*(?:\r?\n|$)",
                r"(?im)^\s*invoice[ \t]+from[ \t]+([^\n]+)",
                r"(?im)^\s*from[ \t]+([^\n]+)",
            ],
            "invoice_number": [
                # Dedicated invoice-number labels are the strongest evidence.
                r"(?im)^\s*(?:invoice[ \t]+(?:number|no\.?|#)|"
                r"numero[ \t]+de[ \t]+factura|reference|ref|no\.?\b|#)"
                r"[ \t]*[:#]?[ \t]*([A-Z0-9][A-Z0-9_/-]*)",
                # Embedded number labels are weaker but still explicit.
                r"(?im)^.*?\binvoice[ \t]+no\.?[ \t]*([A-Z0-9][A-Z0-9_/-]*)\s*$",
                # Generic invoice and number fallbacks are least specific.
                r"(?im)^\s*invoice\s+([A-Z0-9][A-Z0-9_/-]*)\s*$",
                r"(?im)^.*?\b(?:no\.?\b|#)\s*([A-Z0-9][A-Z0-9_/-]*)\s*$",
            ],
            "invoice_date": [
                # ISO dates are unambiguous and receive the highest tier.
                r"(?im)^\s*(?:date|invoice date|inv date|issued|fecha)\s*:\s*(\d{4}-\d{2}-\d{2})",
                # Labeled localized dates are the next strongest tier.
                r"(?im)^\s*(?:date|invoice date|inv date|issued|fecha)\s*:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                # Long-form dates require more parsing assumptions.
                r"(?im)^\s*(?:date|invoice date|inv date|issued)\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            ],
            "total_amount": [
                # Specific total labels are preferred over generic amount labels.
                r"(?im)^.*(?:total\s+amount|total\s+due|importe\s+total)"
                r"\s*:?\s*(?:[A-Z]{3}\s+)?(-?[0-9][0-9.,\s]*)"
                r"\s*(?:[A-Z]{3})?\s*$",
                # A plain total label is less specific.
                r"(?im)^\s*total\s*:\s*(?:[A-Z]{3}\s+)?(-?[0-9][0-9.,\s]*)\s*(?:[A-Z]{3})?\s*$",
                # Generic amount/sum labels are fallback evidence.
                r"(?im)^\s*(?:amount|sum)\s*:\s*(-?[0-9][0-9.,\s]*)\s*(?:[A-Z]{3})?\s*$",
            ],
            "currency": [
                # Explicit currency labels are strongest.
                r"(?im)^\s*(?:currency|curr|cur|moneda)\s*:\s*([A-Z]{3})\s*$",
                # Currency on a total line is contextual evidence.
                r"(?im)^.*(?:total\s+amount|total\s+due|importe\s+total|total)\s*:\s*.*\b(EUR|GBP|USD)\b",
                # A standalone currency code is the broadest fallback.
                r"\b(EUR|GBP|USD)\b",
            ],
            "tax_id": [
                # Explicit tax labels are the only accepted evidence.
                r"(?im)^\s*(?:tax id|federal tax id|vat id|vat|tax number|"
                r"tax no|tin|cif|nif|btw|tva|ust-idnr\.?|vat reg no)"
                r"\s*:\s*([A-Z0-9][A-Z0-9 /-]*)",
            ],
        }

    def extract(self, content: str | bytes, metadata: dict[str, Any] | None = None) -> ExtractionResult:
        """Extract fields using heuristic regex patterns.

        Args:
            content: Document text content.
            metadata: Optional metadata.

        Returns:
            ExtractionResult with extracted fields and confidence scores.
        """
        if isinstance(content, bytes):
            raise TypeError("TextExtractor requires text content, not PDF bytes")

        logger.info("Starting text extraction: characters=%d", len(content))
        fields, evidence = self._extract_fields(content)
        confidence = self._compute_confidence(fields, evidence)
        evidence_snippet = content[:200] if content else None
        extracted_field_count = sum(value is not None for value in fields)
        logger.info("Completed text extraction: extracted_fields=%d", extracted_field_count)

        return ExtractionResult(
            fields=fields,
            confidence=confidence,
            evidence_snippet=evidence_snippet,
            page_hint=1,
            model_id="heuristic_v1",
            latency_ms=5.0,
        )

    def _extract_fields(self, content: str) -> tuple[InvoiceFieldsExtracted, dict[str, FieldEvidence]]:
        """Extract individual fields using regex patterns."""
        extracted_values: dict[str, str | None] = {
            "supplier_name": None,
            "invoice_number": None,
            "invoice_date": None,
            "total_amount": None,
            "currency": None,
            "tax_id": None,
        }
        evidence: dict[str, FieldEvidence] = {}
        for field_name in extracted_values:
            value, field_evidence = self._extract_field_with_evidence(content, field_name)
            extracted_values[field_name] = value
            evidence[field_name] = field_evidence

        fields = InvoiceFieldsExtracted(
            supplier_name=extracted_values["supplier_name"],
            invoice_number=extracted_values["invoice_number"],
            invoice_date=self._parse_invoice_date(extracted_values["invoice_date"]),
            total_amount=self._parse_number(extracted_values["total_amount"]),
            currency=extracted_values["currency"],
            tax_id=self._normalize_tax_id(extracted_values["tax_id"]),
        )
        return fields, evidence

    def _parse_invoice_date(self, invoice_date_str: str | None) -> date | None:
        """Parse invoice date strings from common formats."""
        if not invoice_date_str:
            return None

        try:
            if len(invoice_date_str) == 10 and invoice_date_str[4] == "-":
                return date.fromisoformat(invoice_date_str)

            for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y"):
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

        return self._parse_number(total_amount_str)

    @staticmethod
    def _parse_number(number_string: str | None) -> float | None:
        """Parse common US and European monetary separators."""
        if not number_string:
            return None

        cleaned = number_string.replace(" ", "").strip()
        if not cleaned:
            return None

        try:
            if "," in cleaned and "." in cleaned:
                cleaned = (
                    cleaned.replace(".", "") if cleaned.rfind(",") > cleaned.rfind(".") else cleaned.replace(",", "")
                )
                cleaned = cleaned.replace(",", ".")
            elif "," in cleaned:
                decimal_part = cleaned.rsplit(",", maxsplit=1)[-1]
                cleaned = cleaned.replace(",", ".") if len(decimal_part) == 2 else cleaned.replace(",", "")
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _normalize_tax_id(tax_id: str | None) -> str | None:
        """Normalize tax identifiers that contain presentation spaces."""
        return re.sub(r"\s+", "", tax_id) if tax_id else None

    def _extract_field_with_evidence(self, content: str, field_name: str) -> tuple[str | None, FieldEvidence]:
        """Extract a single field using regex patterns.

        Args:
            content: Document text content.
            field_name: Name of the field to extract.

        Returns:
            Extracted field value or None.
        """
        patterns = self.patterns.get(field_name, [])
        matches_by_pattern = [list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)) for pattern in patterns]
        candidate_values = {match.group(1).strip().casefold() for matches in matches_by_pattern for match in matches}
        candidate_count = len(candidate_values)
        if field_name == "total_amount":
            candidate_count = max(candidate_count, self._count_amount_candidates(content))
        for pattern_index, matches in enumerate(matches_by_pattern):
            if matches:
                return matches[0].group(1).strip(), FieldEvidence(pattern_index, candidate_count)
        return None, FieldEvidence(-1, 0)

    @staticmethod
    def _count_amount_candidates(content: str) -> int:
        """Count labeled monetary candidates used to assess amount ambiguity."""
        candidate_pattern = (
            r"(?im)^\s*.*(?:subtotal|net\s+total|total\s+amount|total\s+due|importe\s+total|total|amount|sum)"
            r"\s*:?\s*(?:[A-Z]{3}\s+)?-?[0-9][0-9.,\s]*"
        )
        return len(re.findall(candidate_pattern, content))

    def _extract_field(self, content: str, field_name: str) -> str | None:
        """Extract a field value without exposing its evidence metadata."""
        value, _ = self._extract_field_with_evidence(content, field_name)
        return value

    def _compute_confidence(
        self, fields: InvoiceFieldsExtracted, evidence: dict[str, FieldEvidence]
    ) -> FieldConfidence:
        """Compute confidence scores for each field.

        Confidence scoring:
        - CONFIDENCE_HIGH (0.9): Field is present
        - CONFIDENCE_MISSING (0.0): Field is None

        Args:
            fields: Extracted fields.

        Returns:
            FieldConfidence with scores for each field.
        """

        def score(field_name: str, value: Any) -> float:
            """Score one value from its winning regex tier and ambiguity."""
            if value is None or value == "":
                return CONFIDENCE_MISSING
            field_evidence = evidence[field_name]
            if field_evidence.pattern_index < 0:
                return CONFIDENCE_FALLBACK
            tier_score = [CONFIDENCE_HIGH, CONFIDENCE_SECONDARY, CONFIDENCE_FALLBACK][
                min(field_evidence.pattern_index, 2)
            ]
            if field_evidence.candidate_count >= 3:
                return min(tier_score, CONFIDENCE_FALLBACK)
            if field_evidence.candidate_count == 2:
                return min(tier_score, CONFIDENCE_SECONDARY)
            return tier_score

        return FieldConfidence(
            supplier_name=score("supplier_name", fields.supplier_name),
            invoice_number=score("invoice_number", fields.invoice_number),
            invoice_date=score("invoice_date", fields.invoice_date),
            total_amount=score("total_amount", fields.total_amount),
            currency=score("currency", fields.currency),
            tax_id=score("tax_id", fields.tax_id),
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
            text, page_count = self._load_text(content)
            result = self.text_extractor.extract(text, metadata)
            logger.info("Completed PDF extraction: pages=%d", page_count)
            return result
        except UnsupportedDocumentError:
            logger.warning("PDF extraction unsupported: no text layer")
            raise
        except (OSError, PdfReadError, ValueError) as exc:
            logger.exception(
                "PDF extraction failed",
                extra={"source_type": "pdf", "input_kind": "path" if isinstance(content, str) else "bytes"},
            )
            raise ValueError("Failed to extract PDF document") from exc

    def extract_text(self, content: str | bytes) -> str:
        """Extract the PDF text used by downstream fallback processing.

        Args:
            content: PDF file path or PDF bytes.

        Returns:
            Concatenated text from all PDF pages.

        Raises:
            UnsupportedDocumentError: If the PDF has no extractable text.
            ValueError: If the PDF cannot be read.
        """
        try:
            text, _ = self._load_text(content)
            return text
        except UnsupportedDocumentError:
            logger.warning("PDF text extraction unsupported: no text layer")
            raise
        except (OSError, PdfReadError, ValueError) as exc:
            logger.exception(
                "PDF text extraction failed",
                extra={"source_type": "pdf", "input_kind": "path" if isinstance(content, str) else "bytes"},
            )
            raise ValueError("Failed to extract PDF document") from exc

    def _load_text(self, content: str | bytes) -> tuple[str, int]:
        """Load and validate PDF text while retaining the page count."""
        logger.info(
            "Starting PDF extraction: input_kind=%s",
            "path" if isinstance(content, str) else "bytes",
        )
        if isinstance(content, str):
            pdf_file = Path(content)
            with open(pdf_file, "rb") as file_handle:
                pdf_reader = self.pdf_reader(file_handle)
                text = self._extract_text_from_pdf(pdf_reader)
        else:
            pdf_reader = self.pdf_reader(io.BytesIO(content))
            text = self._extract_text_from_pdf(pdf_reader)

        if not text.strip():
            raise UnsupportedDocumentError("PDF contains no extractable text")
        return text, len(pdf_reader.pages)

    def _extract_text_from_pdf(self, pdf_reader) -> str:  # type: ignore
        """Extract text from PDF reader.

        Args:
            pdf_reader: pypdf PdfReader instance.

        Returns:
            Concatenated text from all pages.
        """
        text = ""
        for page in pdf_reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text


class LLMExtractor(Extractor):
    """Extract invoice fields with an optional Azure OpenAI fallback."""

    def __init__(
        self,
        llm_client: AzureLLMClient | None = None,
        prompt_loader: ConfigLoaderPrompts | None = None,
    ) -> None:
        """Initialize the Azure client and invoice extraction prompts."""
        self.llm_client = llm_client or AzureLLMClient()
        self.prompt_loader = prompt_loader or ConfigLoaderPrompts()

    def extract(self, content: str | bytes, metadata: dict[str, Any] | None = None) -> ExtractionResult:
        """Extract fields by requesting structured JSON from the configured LLM.

        Args:
            content: Text extracted from a document.
            metadata: Optional document metadata.

        Returns:
            Structured extraction result with LLM provider metadata.

        Raises:
            TypeError: If binary PDF content is supplied instead of extracted text.
            ValueError: If the LLM response is not valid invoice JSON.
        """
        if isinstance(content, bytes):
            raise TypeError("LLMExtractor requires document text, not PDF bytes")

        prompts = self.prompt_loader.prompts
        completion = self.llm_client.extract_invoice(
            prompts.system_prompt,
            prompts.extraction_prompt.format(document_text=content),
        )
        fields = self._parse_fields(completion)
        logger.info("LLM extraction completed: model_id=%s", completion.model_id)
        return ExtractionResult(
            fields=fields,
            confidence=self._llm_confidence(fields),
            evidence_snippet=content[:200] if content else None,
            page_hint=metadata.get("page_hint") if metadata else None,
            model_id=completion.model_id,
            latency_ms=completion.latency_ms,
        )

    def _parse_fields(self, completion: LLMCompletion) -> InvoiceFieldsExtracted:
        """Parse and validate the required invoice fields from an LLM JSON response."""
        try:
            data: dict[str, Any] = json.loads(completion.content)
            invoice_date_value = data.get("invoice_date")
            total_amount_value = data.get("total_amount")
            return InvoiceFieldsExtracted(
                supplier_name=self._optional_string(data.get("supplier_name")),
                invoice_number=self._optional_string(data.get("invoice_number")),
                invoice_date=date.fromisoformat(invoice_date_value) if invoice_date_value else None,
                total_amount=float(total_amount_value) if total_amount_value is not None else None,
                currency=self._optional_string(data.get("currency")),
                tax_id=self._optional_string(data.get("tax_id")),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("LLM response does not match the invoice field schema") from exc

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Convert JSON string values while preserving nulls."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("LLM invoice fields must be strings or null")
        return value

    @staticmethod
    def _llm_confidence(fields: InvoiceFieldsExtracted) -> FieldConfidence:
        """Assign high evidence confidence to fields returned in structured LLM JSON."""
        # Future work: replace presence-based constants with calibrated confidence from the LLM or provider metadata.
        return FieldConfidence(
            supplier_name=CONFIDENCE_HIGH if fields.supplier_name else CONFIDENCE_MISSING,
            invoice_number=CONFIDENCE_HIGH if fields.invoice_number else CONFIDENCE_MISSING,
            invoice_date=CONFIDENCE_HIGH if fields.invoice_date else CONFIDENCE_MISSING,
            total_amount=CONFIDENCE_HIGH if fields.total_amount is not None else CONFIDENCE_MISSING,
            currency=CONFIDENCE_HIGH if fields.currency else CONFIDENCE_MISSING,
            tax_id=CONFIDENCE_HIGH if fields.tax_id else CONFIDENCE_MISSING,
        )
