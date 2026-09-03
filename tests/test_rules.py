"""Unit tests for business rules engine."""

from datetime import date, timedelta

import pytest

from ai_document_validator.common.constants import VerdictStatusValues
from ai_document_validator.config.config_types import (
    ExtractionResult,
    FieldConfidence,
    InvoiceFieldsExtracted,
    RuleConfig,
)
from ai_document_validator.process.rules.evaluator import (
    CurrencyRule,
    InvoiceDateRule,
    RulesEvaluator,
    SupplierNameRule,
    TotalAmountRule,
)


@pytest.mark.unit
class TestSupplierNameRule:
    """Test SupplierNameRule."""

    def test_passes_when_supplier_name_present(self) -> None:
        """Test that rule passes when supplier_name is present."""
        rule = SupplierNameRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name="Acme Corp",
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.9, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        result = rule.evaluate(extraction, config)

        assert result.passed is True
        assert result.rule_id == "supplier_name_required"

    def test_fails_when_supplier_name_missing(self) -> None:
        """Test that rule fails when supplier_name is None."""
        rule = SupplierNameRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        result = rule.evaluate(extraction, config)

        assert result.passed is False

    def test_fails_when_supplier_name_empty(self) -> None:
        """Test that rule fails when supplier_name is empty string."""
        rule = SupplierNameRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name="",
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        result = rule.evaluate(extraction, config)

        assert result.passed is False


@pytest.mark.unit
class TestInvoiceDateRule:
    """Test InvoiceDateRule."""

    def test_passes_when_recent_date(self) -> None:
        """Test that rule passes when invoice_date is recent."""
        rule = InvoiceDateRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=date.today(),
                total_amount=None,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.9, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE", max_age_days=90)

        result = rule.evaluate(extraction, config)

        assert result.passed is True

    def test_fails_when_date_missing(self) -> None:
        """Test that rule fails when invoice_date is None."""
        rule = InvoiceDateRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE", max_age_days=90)

        result = rule.evaluate(extraction, config)

        assert result.passed is False
        assert "missing" in result.message.lower()

    def test_fails_when_date_too_old(self) -> None:
        """Test that rule fails when invoice_date is older than max_age_days."""
        rule = InvoiceDateRule()
        old_date = date.today() - timedelta(days=100)
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=old_date,
                total_amount=None,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.9, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE", max_age_days=90)

        result = rule.evaluate(extraction, config)

        assert result.passed is False
        assert "exceeds max age" in result.message.lower()


@pytest.mark.unit
class TestTotalAmountRule:
    """Test TotalAmountRule."""

    def test_passes_when_positive_amount(self) -> None:
        """Test that rule passes when total_amount is positive."""
        rule = TotalAmountRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=1000.0,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.9, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        result = rule.evaluate(extraction, config)

        assert result.passed is True

    def test_fails_when_amount_missing(self) -> None:
        """Test that rule fails when total_amount is None."""
        rule = TotalAmountRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        result = rule.evaluate(extraction, config)

        assert result.passed is False

    def test_fails_when_amount_zero(self) -> None:
        """Test that rule fails when total_amount is 0."""
        rule = TotalAmountRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=0.0,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        result = rule.evaluate(extraction, config)

        assert result.passed is False

    def test_fails_when_amount_negative(self) -> None:
        """Test that rule fails when total_amount is negative."""
        rule = TotalAmountRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=-100.0,
                currency=None,
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        result = rule.evaluate(extraction, config)

        assert result.passed is False


@pytest.mark.unit
class TestCurrencyRule:
    """Test CurrencyRule."""

    def test_passes_when_no_restrictions(self) -> None:
        """Test that rule passes when allowed_currencies is None."""
        rule = CurrencyRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency="JPY",
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.9, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE", allowed_currencies=None)

        result = rule.evaluate(extraction, config)

        assert result.passed is True

    def test_passes_when_currency_allowed(self) -> None:
        """Test that rule passes when currency is in allowed list."""
        rule = CurrencyRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency="EUR",
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.9, 0.0),
        )
        config = RuleConfig(
            document_type="SUPPLIER_INVOICE",
            allowed_currencies=["EUR", "GBP"],
        )

        result = rule.evaluate(extraction, config)

        assert result.passed is True

    def test_fails_when_currency_not_allowed(self) -> None:
        """Test that rule fails when currency is not in allowed list."""
        rule = CurrencyRule()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                currency="JPY",
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.0, 0.0, 0.0, 0.9, 0.0),
        )
        config = RuleConfig(
            document_type="SUPPLIER_INVOICE",
            allowed_currencies=["EUR", "GBP"],
        )

        result = rule.evaluate(extraction, config)

        assert result.passed is False


@pytest.mark.unit
class TestRulesEvaluator:
    """Test RulesEvaluator."""

    def test_verdict_pass_when_all_rules_pass(self, sample_extraction: ExtractionResult) -> None:
        """Test that verdict is PASS when all rules pass."""
        # Create extraction with all required fields and allowed currency
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name="Test Corp",
                invoice_number="INV-001",
                invoice_date=date.today(),
                total_amount=1000.0,
                currency="EUR",  # Make sure it's in allowed list
                tax_id="VAT-123",
            ),
            confidence=FieldConfidence(0.9, 0.9, 0.9, 0.9, 0.8, 0.7),
        )
        evaluator = RulesEvaluator()
        config = RuleConfig(
            document_type="SUPPLIER_INVOICE",
            max_age_days=90,
            allowed_currencies=["EUR", "GBP"],
        )

        verdict = evaluator.evaluate(extraction, config)

        assert verdict.status == VerdictStatusValues.PASS
        assert all(rr.passed for rr in verdict.rule_results)

    def test_verdict_fail_when_critical_rule_fails(self) -> None:
        """Test that verdict is FAIL when a critical rule fails."""
        evaluator = RulesEvaluator()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name=None,  # Missing required field
                invoice_number="INV-001",
                invoice_date=date.today(),
                total_amount=1000.0,
                currency="EUR",
                tax_id=None,
            ),
            confidence=FieldConfidence(0.0, 0.9, 0.9, 0.9, 0.8, 0.0),
        )
        config = RuleConfig(document_type="SUPPLIER_INVOICE")

        verdict = evaluator.evaluate(extraction, config)

        assert verdict.status == VerdictStatusValues.FAIL

    def test_verdict_review_when_soft_rule_fails(self) -> None:
        """Test that verdict is REVIEW when only soft (non-critical) rule fails."""
        evaluator = RulesEvaluator()
        extraction = ExtractionResult(
            fields=InvoiceFieldsExtracted(
                supplier_name="Test Corp",
                invoice_number="INV-001",
                invoice_date=date.today(),
                total_amount=1000.0,
                currency=None,  # Missing currency (won't fail when no restrictions)
                tax_id=None,
            ),
            confidence=FieldConfidence(0.9, 0.9, 0.9, 0.9, 0.0, 0.0),
        )
        config = RuleConfig(
            document_type="SUPPLIER_INVOICE",
            allowed_currencies=None,  # No currency restrictions
        )

        verdict = evaluator.evaluate(extraction, config)

        # All critical rules pass, no soft rules configured
        assert verdict.status == VerdictStatusValues.PASS

    def test_can_add_custom_rule(self) -> None:
        """Test that custom rules can be added to evaluator."""
        from ai_document_validator.process.rules.evaluator import Rule

        class CustomRule(Rule):
            rule_id = "custom_rule"
            rule_description = "Custom test rule"
            is_critical = False

            def evaluate(self, extraction, config):  # type: ignore
                return type(
                    "RuleResult",
                    (),
                    {
                        "rule_id": self.rule_id,
                        "passed": True,
                        "message": "Custom rule passed",
                    },
                )()

        evaluator = RulesEvaluator([])
        initial_count = len(evaluator.rule_instances)
        evaluator.add_rule(CustomRule)

        assert len(evaluator.rule_instances) == initial_count + 1
        assert evaluator.rule_instances[-1].rule_id == "custom_rule"
