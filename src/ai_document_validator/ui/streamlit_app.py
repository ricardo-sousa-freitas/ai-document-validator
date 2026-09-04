"""Streamlit interface for invoice validation."""

from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st
from pydantic import ValidationError

from ai_document_validator.common.constants import DocumentType, VerdictStatusValues
from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.validation import RuleConfigModel
from ai_document_validator.process.extraction.extractors import LLMExtractor, PDFExtractor, UnsupportedDocumentError
from ai_document_validator.process.extraction.hybrid import HybridExtractionResult, HybridExtractor
from ai_document_validator.process.extraction.selector import select_extractor
from ai_document_validator.process.rules.evaluator import RulesEvaluator

logger = setup_logger(__name__)

_UPLOAD_TYPES = ["pdf", "txt"]
_DEFAULT_MAX_AGE_DAYS = 90
_DEFAULT_ALLOWED_CURRENCIES = "EUR, GBP"
_DEFAULT_CONFIDENCE_THRESHOLD = 0.60


def _build_rule_config(
    max_age_days: int,
    allowed_currencies: str,
    review_confidence_threshold: float,
) -> RuleConfigModel:
    """Build a validated rule config from sidebar inputs."""
    currencies = [currency.strip() for currency in allowed_currencies.split(",") if currency.strip()]
    return RuleConfigModel(
        document_type=DocumentType.SUPPLIER_INVOICE,
        max_age_days=max_age_days,
        allowed_currencies=currencies or None,
        required_fields=["supplier_name", "invoice_number", "invoice_date", "total_amount"],
        review_confidence_threshold=review_confidence_threshold,
    )


def _extract_uploaded_document(uploaded_file: Any, config: RuleConfigModel) -> HybridExtractionResult:
    """Extract fields from a Streamlit-uploaded text or PDF document."""
    extractor = select_extractor(uploaded_file.name, uploaded_file.type or None)
    content = uploaded_file.getvalue()
    metadata = {"source_name": uploaded_file.name}
    if not isinstance(extractor, PDFExtractor):
        content = content.decode("utf-8")
    hybrid_extractor = HybridExtractor(
        heuristic_extractor=extractor,
        required_fields=config.required_fields or [],
        confidence_threshold=config.review_confidence_threshold or 0.0,
        fallback_extractor=LLMExtractor(),
    )
    return hybrid_extractor.extract(content, metadata)


def _render_verdict(status: str) -> None:
    """Render the validation status with an appropriate Streamlit indicator."""
    if status == VerdictStatusValues.PASS:
        st.success(status)
    elif status == VerdictStatusValues.REVIEW:
        st.warning(status)
    else:
        st.error(status)


def _render_results(uploaded_file: Any, config: RuleConfigModel) -> None:
    """Extract, validate, and render a document result."""
    hybrid_result = _extract_uploaded_document(uploaded_file, config)
    extraction = hybrid_result.extraction
    verdict = RulesEvaluator().evaluate(extraction, config.to_rule_config())
    logger.info("Streamlit validation completed: status=%s", verdict.status)

    _render_verdict(verdict.status)
    if hybrid_result.fallback_required:
        st.info("LLM fallback is recommended but unavailable: " + ", ".join(hybrid_result.fallback_reasons))
    left_column, right_column = st.columns(2)
    with left_column:
        st.subheader("Extracted Fields")
        st.json(extraction.fields._asdict())
    with right_column:
        st.subheader("Field Confidence")
        st.json(extraction.confidence._asdict())

    st.subheader("Rule Results")
    st.dataframe(
        [result._asdict() for result in verdict.rule_results],
        hide_index=True,
        use_container_width=True,
    )
    if extraction.evidence_snippet:
        with st.expander("Evidence Preview"):
            st.code(extraction.evidence_snippet, language="text")


def main() -> None:
    """Run the Streamlit invoice validation interface."""
    st.set_page_config(page_title="Invoice Validator", page_icon="IV", layout="wide")
    st.title("Invoice Validator")

    with st.sidebar:
        st.header("Rule Configuration")
        max_age_days = st.number_input("Maximum Invoice Age (days)", min_value=0, value=_DEFAULT_MAX_AGE_DAYS)
        allowed_currencies = st.text_input("Allowed Currencies", value=_DEFAULT_ALLOWED_CURRENCIES)
        review_confidence_threshold = st.slider(
            "Review Confidence Threshold",
            min_value=0.0,
            max_value=1.0,
            value=_DEFAULT_CONFIDENCE_THRESHOLD,
            step=0.05,
        )
        reference_date = st.date_input("Reference Date", value=date.today())

    uploaded_file = st.file_uploader("Upload an invoice", type=_UPLOAD_TYPES)
    if uploaded_file is None:
        return

    if st.button("Validate Invoice", type="primary", use_container_width=True):
        try:
            config = _build_rule_config(max_age_days, allowed_currencies, review_confidence_threshold).model_copy(
                update={"reference_date": reference_date}
            )
            with st.spinner("Validating document..."):
                _render_results(uploaded_file, config)
        except UnsupportedDocumentError as exc:
            logger.warning("Streamlit document unsupported: source_name=%s", uploaded_file.name)
            st.warning(f"UNSUPPORTED_DOCUMENT: {exc}")
        except (UnicodeDecodeError, ValidationError, ValueError) as exc:
            logger.exception("Streamlit validation failed: error_type=%s", type(exc).__name__)
            st.error(str(exc))


if __name__ == "__main__":
    main()
