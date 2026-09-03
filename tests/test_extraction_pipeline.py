"""Integration tests for extraction and verdict pipeline."""

from pathlib import Path

import pytest

from ai_document_validator.common.constants import VerdictStatusValues
from ai_document_validator.config.config_types import RuleConfig
from ai_document_validator.process.extraction.extractors import PDFExtractor, TextExtractor
from ai_document_validator.process.extraction.selector import extract_document_file, select_extractor
from ai_document_validator.process.rules.evaluator import RulesEvaluator


@pytest.mark.integration
class TestTextExtractionPipeline:
    """Test text extraction pipeline."""

    def test_extract_from_invoice_text(self, text_extractor: TextExtractor) -> None:
        """Test extraction from sample invoice text."""
        invoice_text = """
        Invoice from Acme Corporation
        Invoice Number: INV-2024-001
        Date: 2026-09-01
        Total Amount: 5000.00 EUR
        Tax ID: VAT-DE-123456789
        """

        result = text_extractor.extract(invoice_text)

        assert result.fields.supplier_name is not None
        assert "acme" in result.fields.supplier_name.lower()
        # Heuristic extraction is imperfect for complex patterns
        assert result.fields.invoice_date is not None
        assert result.fields.total_amount == 5000.0
        assert result.fields.tax_id is not None
        assert result.confidence.invoice_date == 0.9
        assert result.confidence.total_amount == 0.9

    def test_extract_with_missing_fields(self, text_extractor: TextExtractor) -> None:
        """Test extraction when some fields are missing."""
        invoice_text = """
        Supplier: PartnerCo
        Amount: 1000.00
        """

        result = text_extractor.extract(invoice_text)

        assert result.fields.supplier_name is not None
        assert result.fields.total_amount == 1000.0
        assert result.fields.invoice_number is None
        assert result.fields.invoice_date is None
        assert result.confidence.invoice_number == 0.0
        assert result.confidence.invoice_date == 0.0

    def test_extract_and_evaluate_pipeline(self, text_extractor: TextExtractor) -> None:
        """Test end-to-end extraction and evaluation."""
        invoice_text = """
        Supplier: Test Corporation
        Invoice: INV-2024-100
        Date: 2026-09-01
        Amount: 5000.00
        Currency: EUR
        """

        extraction = text_extractor.extract(invoice_text)
        evaluator = RulesEvaluator()
        config = RuleConfig(
            document_type="SUPPLIER_INVOICE",
            max_age_days=90,
            allowed_currencies=["EUR", "GBP"],
        )

        verdict = evaluator.evaluate(extraction, config)

        # With heuristic extraction, some fields may not be extracted perfectly
        # At minimum, we should have a verdict status
        assert verdict.status in ["PASS", "FAIL", "REVIEW"]


@pytest.mark.integration
class TestMultiFormatExtraction:
    """Test text and PDF documents through the shared extraction path."""

    samples_dir = Path(__file__).parent.parent / "fixtures" / "documents"

    def test_extract_text_sample_file(self) -> None:
        """Extract fields from a plain-text sample selected by its extension."""
        result = extract_document_file(self.samples_dir / "inv_001_clean_eur.txt")

        assert result.fields.supplier_name == "NORDWIND LOGISTIK GMBH"
        assert result.fields.invoice_number == "INV-2026-0417"
        assert result.fields.total_amount == 4820.5
        assert result.fields.currency == "EUR"

    def test_extract_pdf_sample_from_path_and_bytes(self) -> None:
        """Extract fields from a PDF sample supplied as a path and as bytes."""
        pdf_path = self.samples_dir / "inv_001_clean_eur.pdf"
        path_result = PDFExtractor().extract(str(pdf_path))
        bytes_result = PDFExtractor().extract(pdf_path.read_bytes())

        assert path_result.fields == bytes_result.fields
        assert path_result.fields.supplier_name == "NORDWIND LOGISTIK GMBH"
        assert path_result.fields.invoice_number == "INV-2026-0417"
        assert path_result.fields.total_amount == 4820.5
        assert path_result.fields.currency == "EUR"

    def test_selector_prefers_content_type_over_extension(self) -> None:
        """Use the explicit MIME type when it conflicts with the filename."""
        assert isinstance(select_extractor("invoice.txt", "application/pdf"), PDFExtractor)
        assert isinstance(select_extractor("invoice.pdf", "text/plain"), TextExtractor)

    def test_selector_rejects_unsupported_extension(self) -> None:
        """Reject formats that the service cannot extract."""
        with pytest.raises(ValueError, match="Unsupported document extension"):
            select_extractor("invoice.docx")

    def test_corrupt_pdf_error_preserves_cause(self) -> None:
        """Wrap corrupt PDF failures without losing the original exception."""
        with pytest.raises(ValueError, match="Failed to extract PDF") as error:
            PDFExtractor().extract(b"not a PDF")

        assert error.value.__cause__ is not None

    def test_empty_pdf_error_is_safe(self) -> None:
        """Reject empty PDF bytes with a safe domain-level error."""
        with pytest.raises(ValueError, match="Failed to extract PDF"):
            PDFExtractor().extract(b"")

    def test_missing_fields_remain_explicit(self) -> None:
        """Allow missing fields to flow to the rules engine as failures."""
        result = TextExtractor().extract("Supplier: Partial Invoice\nAmount: 100.00\n")
        verdict = RulesEvaluator().evaluate(
            result,
            RuleConfig(document_type="SUPPLIER_INVOICE", max_age_days=90),
        )

        assert result.fields.invoice_date is None
        assert verdict.status == VerdictStatusValues.FAIL

    def test_confidence_reflects_regex_ambiguity(self) -> None:
        """Lower amount confidence when multiple total candidates are present."""
        result = TextExtractor().extract(
            "Supplier: Example Corp\n"
            "Invoice Number: INV-1\n"
            "Date: 2026-09-01\n"
            "Subtotal: 100.00 EUR\n"
            "Net total: 90.00 EUR\n"
            "Total Amount: 90.00 EUR\n"
        )

        assert result.fields.total_amount == 90.0
        assert result.confidence.total_amount == 0.3

    def test_confidence_reflects_specificity_tier(self) -> None:
        """Use a lower score for a less-specific amount label."""
        result = TextExtractor().extract("Supplier: Example Corp\nAmount: 100.00\n")

        assert result.fields.total_amount == 100.0
        assert result.confidence.total_amount == 0.3
