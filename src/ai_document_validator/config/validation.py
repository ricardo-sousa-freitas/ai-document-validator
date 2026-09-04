"""Validated external configuration models."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_document_validator.config.config_types import RuleConfig


class RuleConfigModel(BaseModel):
    """Validate rule configuration received at an external boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_type: str = Field(min_length=1)
    max_age_days: int = Field(default=90, ge=0)
    allowed_currencies: list[str] | None = None
    required_fields: list[str] | None = None
    reference_date: date | None = None
    review_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("allowed_currencies")
    @classmethod
    def validate_currencies(cls, currencies: list[str] | None) -> list[str] | None:
        """Require non-empty three-letter currency codes."""
        if currencies is None:
            return None
        if not currencies or any(len(currency) != 3 or not currency.isalpha() for currency in currencies):
            raise ValueError("allowed_currencies must contain three-letter alphabetic codes")
        return [currency.upper() for currency in currencies]

    @field_validator("required_fields")
    @classmethod
    def validate_required_fields(cls, fields: list[str] | None) -> list[str] | None:
        """Reject empty required-field names."""
        if fields is not None and (not fields or any(not field for field in fields)):
            raise ValueError("required_fields must contain non-empty field names")
        return fields

    def to_rule_config(self) -> RuleConfig:
        """Convert validated external data to the internal rule configuration."""
        return RuleConfig(
            document_type=self.document_type,
            max_age_days=self.max_age_days,
            allowed_currencies=self.allowed_currencies,
            required_fields=self.required_fields,
            reference_date=self.reference_date,
            review_confidence_threshold=self.review_confidence_threshold,
        )
