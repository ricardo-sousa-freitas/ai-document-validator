"""HTTP API for document extraction and validation."""

from __future__ import annotations

import base64
import binascii
import time
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.config_types import ExtractionResult, Verdict
from ai_document_validator.config.validation import RuleConfigModel
from ai_document_validator.process.extraction.extractors import PDFExtractor, TextExtractor, UnsupportedDocumentError
from ai_document_validator.process.extraction.selector import select_extractor
from ai_document_validator.process.rules.evaluator import RulesEvaluator

logger = setup_logger(__name__)


class ValidateRequest(BaseModel):
    """JSON document payload accepted by the validation endpoints."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1)
    content: str | None = None
    content_base64: str | None = None
    content_type: str | None = None
    config: RuleConfigModel

    @model_validator(mode="after")
    def validate_content(self) -> "ValidateRequest":
        """Require exactly one document representation."""
        if (self.content is None) == (self.content_base64 is None):
            raise ValueError("Provide exactly one of content or content_base64")
        if self.content_base64 is not None:
            try:
                base64.b64decode(self.content_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("content_base64 must contain valid base64") from exc
        return self


class ExtractedFieldsResponse(BaseModel):
    """Serialized extracted invoice fields."""

    supplier_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    total_amount: float | None
    currency: str | None
    tax_id: str | None


class FieldConfidenceResponse(BaseModel):
    """Serialized per-field extraction confidence."""

    supplier_name: float
    invoice_number: float
    invoice_date: float
    total_amount: float
    currency: float
    tax_id: float


class RuleResultResponse(BaseModel):
    """Serialized rule evaluation result."""

    rule_id: str
    passed: bool
    message: str


class ExtractionResponse(BaseModel):
    """API extraction response."""

    fields: ExtractedFieldsResponse
    confidence: FieldConfidenceResponse
    evidence_snippet: str | None
    page_hint: int | None
    model_id: str | None
    latency_ms: float | None


class ValidationResponse(ExtractionResponse):
    """API validation response containing the final verdict."""

    status: str
    rule_results: list[RuleResultResponse]
    total_tokens: int | None


class UnsupportedDocumentResponse(BaseModel):
    """Response for a document the configured extractor cannot process."""

    status: str = "UNSUPPORTED_DOCUMENT"
    detail: str


app = FastAPI(title="AI Document Validator", version="0.1.0")


def _decode_request_content(request: ValidateRequest) -> str | bytes:
    """Decode the request's text or base64 document content."""
    if request.content is not None:
        return request.content
    assert request.content_base64 is not None
    return base64.b64decode(request.content_base64)


def _extract(request: ValidateRequest) -> ExtractionResult:
    """Select an extractor and extract the request document."""
    content = _decode_request_content(request)
    extractor = select_extractor(request.source_name, request.content_type)
    metadata: dict[str, Any] = {"source_name": request.source_name}
    if isinstance(extractor, PDFExtractor):
        if not isinstance(content, bytes):
            raise ValueError("PDF documents must use content_base64")
        return extractor.extract(content, metadata)
    if not isinstance(content, str):
        raise ValueError("Text documents must use content")
    return TextExtractor().extract(content, metadata)


def _extraction_response(extraction: ExtractionResult) -> ExtractionResponse:
    """Map the internal extraction result to an API response."""
    return ExtractionResponse(
        fields=ExtractedFieldsResponse(**extraction.fields._asdict()),
        confidence=FieldConfidenceResponse(**extraction.confidence._asdict()),
        evidence_snippet=extraction.evidence_snippet,
        page_hint=extraction.page_hint,
        model_id=extraction.model_id,
        latency_ms=extraction.latency_ms,
    )


def _validation_response(verdict: Verdict, extraction: ExtractionResult) -> ValidationResponse:
    """Map the internal verdict to an API response."""
    response = _extraction_response(extraction)
    return ValidationResponse(
        **response.model_dump(),
        status=verdict.status,
        rule_results=[RuleResultResponse(**result._asdict()) for result in verdict.rule_results],
        total_tokens=verdict.total_tokens,
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Return the service liveness status."""
    return {"status": "ok"}


@app.post("/v1/extract", response_model=ExtractionResponse | UnsupportedDocumentResponse)
def extract_document(request: ValidateRequest) -> ExtractionResponse | UnsupportedDocumentResponse:
    """Extract invoice fields from text or a base64-encoded PDF."""
    started_at = time.perf_counter()
    try:
        response = _extraction_response(_extract(request))
        logger.info("Document extraction request completed: source_type=%s", request.source_name)
        return response
    except UnsupportedDocumentError as exc:
        logger.warning("Document extraction unsupported: source_type=%s", request.source_name)
        return UnsupportedDocumentResponse(detail=str(exc))
    except (OSError, TypeError, ValueError) as exc:
        logger.exception("Document extraction request failed: error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        logger.info("Document extraction request latency_ms=%.2f", (time.perf_counter() - started_at) * 1000)


@app.post("/v1/validate", response_model=ValidationResponse | UnsupportedDocumentResponse)
def validate_document(request: ValidateRequest) -> ValidationResponse | UnsupportedDocumentResponse:
    """Extract and validate an invoice document against its rule config."""
    started_at = time.perf_counter()
    try:
        extraction = _extract(request)
        verdict = RulesEvaluator().evaluate(extraction, request.config.to_rule_config())
        logger.info("Document validation request completed: status=%s", verdict.status)
        return _validation_response(verdict, extraction)
    except UnsupportedDocumentError as exc:
        logger.warning("Document validation unsupported: source_type=%s", request.source_name)
        return UnsupportedDocumentResponse(detail=str(exc))
    except (OSError, TypeError, ValueError) as exc:
        logger.exception("Document validation request failed: error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        logger.info("Document validation request latency_ms=%.2f", (time.perf_counter() - started_at) * 1000)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_document_validator.api:app", host="0.0.0.0", port=8000)
