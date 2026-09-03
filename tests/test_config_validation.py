"""Tests for external rule configuration validation."""

import pytest
from pydantic import ValidationError

from ai_document_validator.config.validation import RuleConfigModel


@pytest.mark.unit
class TestRuleConfigModel:
    """Test strict validation of external rule configuration."""

    def test_converts_valid_config_to_internal_type(self) -> None:
        """Convert valid external config and normalize currency codes."""
        config = RuleConfigModel(
            document_type="SUPPLIER_INVOICE",
            max_age_days=90,
            allowed_currencies=["eur", "GBP"],
        )

        internal_config = config.to_rule_config()

        assert internal_config.allowed_currencies == ["EUR", "GBP"]

    def test_rejects_unknown_keys(self) -> None:
        """Reject misspelled or unsupported configuration keys."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            RuleConfigModel(document_type="SUPPLIER_INVOICE", unknown_key=True)

    @pytest.mark.parametrize("max_age_days", [-1, -100])
    def test_rejects_negative_max_age(self, max_age_days: int) -> None:
        """Reject invalid invoice age limits."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            RuleConfigModel(document_type="SUPPLIER_INVOICE", max_age_days=max_age_days)

    def test_rejects_empty_document_type(self) -> None:
        """Reject an empty document type."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            RuleConfigModel(document_type="")

    def test_rejects_invalid_currency_codes(self) -> None:
        """Reject malformed currency codes."""
        with pytest.raises(ValidationError, match="three-letter alphabetic codes"):
            RuleConfigModel(document_type="SUPPLIER_INVOICE", allowed_currencies=["EURO"])

    def test_validates_reference_date_and_confidence_threshold(self) -> None:
        """Parse deterministic evaluation settings at the external boundary."""
        config = RuleConfigModel(
            document_type="SUPPLIER_INVOICE",
            reference_date="2026-09-03",
            review_confidence_threshold=0.6,
        )

        assert config.reference_date is not None
        assert config.reference_date.isoformat() == "2026-09-03"
        assert config.review_confidence_threshold == 0.6

    def test_rejects_confidence_threshold_outside_range(self) -> None:
        """Reject confidence thresholds outside the unit interval."""
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            RuleConfigModel(document_type="SUPPLIER_INVOICE", review_confidence_threshold=1.1)
