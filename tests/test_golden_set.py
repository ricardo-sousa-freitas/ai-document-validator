"""Tests for canonical document-pair golden-set evaluation."""

from pathlib import Path

import pytest

from ai_document_validator.eval.golden_set import DocumentGoldenSetEvaluator


@pytest.mark.integration
class TestDocumentGoldenSetEvaluator:
    """Test evaluation against real documents and hand-maintained outputs."""

    expected_file = Path(__file__).parent.parent / "fixtures" / "expected.yaml"

    def test_loads_all_document_pair_cases(self) -> None:
        """Load all canonical cases and their pinned configuration."""
        evaluator = DocumentGoldenSetEvaluator(self.expected_file)

        assert len(evaluator.test_cases) == 18
        assert evaluator.config.reference_date is not None
        assert evaluator.config.reference_date.isoformat() == "2026-09-03"

    def test_evaluates_real_documents(self) -> None:
        """Run extraction and rules over every canonical document."""
        metrics = DocumentGoldenSetEvaluator(self.expected_file).evaluate_all()

        assert metrics.total_cases == 18
        assert metrics.verdict_agreement_rate >= 0.8
        assert metrics.field_exact_match_rates["total_amount"] >= 0.8
        assert any(failure["type"] == "field_mismatch" for failure in metrics.failures)

    def test_reports_textless_pdf_as_expected_status(self) -> None:
        """Keep scanned PDF processing distinct from missing extracted fields."""
        evaluator = DocumentGoldenSetEvaluator(self.expected_file)
        scanned_case = next(case for case in evaluator.test_cases if case.case_id == "inv_012_scanned_no_text")

        assert scanned_case.expected_extraction_status == "UNSUPPORTED_DOCUMENT"
        assert scanned_case.expected_fields is None
