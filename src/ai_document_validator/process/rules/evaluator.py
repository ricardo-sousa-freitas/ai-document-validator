"""Business rules engine for document validation."""

from abc import ABC, abstractmethod
from datetime import date, timedelta

from ai_document_validator.common.constants import VerdictStatusValues
from ai_document_validator.config.config_types import (
    ExtractionResult,
    RuleConfig,
    RuleResult,
    Verdict,
)


class Rule(ABC):
    """Abstract base class for validation rules."""

    rule_id: str = "base_rule"
    rule_description: str = "Base rule (not implemented)"
    is_critical: bool = False  # If True, failure triggers FAIL; else triggers REVIEW

    @abstractmethod
    def evaluate(self, extraction: ExtractionResult, config: RuleConfig) -> RuleResult:
        """Evaluate the rule against extraction result.

        Args:
            extraction: ExtractionResult with extracted fields and confidence.
            config: RuleConfig with rule parameters.

        Returns:
            RuleResult indicating pass/fail and message.
        """
        raise NotImplementedError


class SupplierNameRule(Rule):
    """Rule: supplier_name must be present and non-empty."""

    rule_id = "supplier_name_required"
    rule_description = "Supplier name must be present and non-empty"
    is_critical = True

    def evaluate(self, extraction: ExtractionResult, config: RuleConfig) -> RuleResult:
        """Check that supplier_name is present.

        Args:
            extraction: ExtractionResult to validate.
            config: RuleConfig (unused).

        Returns:
            RuleResult with pass/fail.
        """
        passed = extraction.fields.supplier_name is not None and extraction.fields.supplier_name.strip() != ""
        message = "Supplier name is present" if passed else "Supplier name is missing or empty"
        return RuleResult(rule_id=self.rule_id, passed=passed, message=message)


class InvoiceDateRule(Rule):
    """Rule: invoice_date must be present and not older than max_age_days."""

    rule_id = "invoice_date_valid"
    rule_description = "Invoice date must be present and within max age"
    is_critical = True

    def evaluate(self, extraction: ExtractionResult, config: RuleConfig) -> RuleResult:
        """Check that invoice_date is present and recent.

        Args:
            extraction: ExtractionResult to validate.
            config: RuleConfig with max_age_days parameter.

        Returns:
            RuleResult with pass/fail.
        """
        if extraction.fields.invoice_date is None:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                message="Invoice date is missing",
            )

        # Check age
        max_age = timedelta(days=config.max_age_days)
        invoice_date = extraction.fields.invoice_date
        age = date.today() - invoice_date

        if age > max_age:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                message=f"Invoice date {invoice_date} exceeds max age of {config.max_age_days} days "
                f"(age: {age.days} days)",
            )

        return RuleResult(
            rule_id=self.rule_id,
            passed=True,
            message=f"Invoice date {invoice_date} is within max age",
        )


class TotalAmountRule(Rule):
    """Rule: total_amount must be present and greater than 0."""

    rule_id = "total_amount_valid"
    rule_description = "Total amount must be present and greater than 0"
    is_critical = True

    def evaluate(self, extraction: ExtractionResult, config: RuleConfig) -> RuleResult:
        """Check that total_amount is present and positive.

        Args:
            extraction: ExtractionResult to validate.
            config: RuleConfig (unused).

        Returns:
            RuleResult with pass/fail.
        """
        if extraction.fields.total_amount is None:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                message="Total amount is missing",
            )

        if extraction.fields.total_amount <= 0:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                message=f"Total amount {extraction.fields.total_amount} must be greater than 0",
            )

        return RuleResult(
            rule_id=self.rule_id,
            passed=True,
            message=f"Total amount {extraction.fields.total_amount} is valid",
        )


class CurrencyRule(Rule):
    """Rule: if allowed_currencies is configured, currency must be in the list."""

    rule_id = "currency_allowed"
    rule_description = "Currency must be in allowed list (if configured)"
    is_critical = True  # Critical: currency restriction must be honored

    def evaluate(self, extraction: ExtractionResult, config: RuleConfig) -> RuleResult:
        """Check that currency is in allowed list.

        Args:
            extraction: ExtractionResult to validate.
            config: RuleConfig with allowed_currencies parameter.

        Returns:
            RuleResult with pass/fail.
        """
        if not config.allowed_currencies:
            # No currency restrictions
            return RuleResult(
                rule_id=self.rule_id,
                passed=True,
                message="No currency restrictions configured",
            )

        if extraction.fields.currency is None:
            # Currency not detected but is restricted
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                message="Currency not detected but restrictions are in place",
            )

        if extraction.fields.currency not in config.allowed_currencies:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                message=f"Currency {extraction.fields.currency} not in allowed list " f"{config.allowed_currencies}",
            )

        return RuleResult(
            rule_id=self.rule_id,
            passed=True,
            message=f"Currency {extraction.fields.currency} is allowed",
        )


class RulesEvaluator:
    """Orchestrates rule evaluation and produces a Verdict."""

    DEFAULT_RULES: list[type[Rule]] = [
        SupplierNameRule,
        InvoiceDateRule,
        TotalAmountRule,
        CurrencyRule,
    ]

    def __init__(self, rules: list[type[Rule]] | None = None) -> None:
        """Initialize evaluator with rule classes.

        Args:
            rules: List of Rule subclasses to evaluate. Defaults to DEFAULT_RULES.
        """
        self.rules = rules or self.DEFAULT_RULES
        self.rule_instances = [rule_class() for rule_class in self.rules]

    def evaluate(self, extraction: ExtractionResult, config: RuleConfig) -> Verdict:
        """Evaluate all rules and return a Verdict.

        Args:
            extraction: ExtractionResult with extracted fields.
            config: RuleConfig with rule parameters.

        Returns:
            Verdict with status (PASS/FAIL/REVIEW) and rule results.
        """
        rule_results: list[RuleResult] = []
        critical_failures = False
        soft_failures = False

        for rule in self.rule_instances:
            result = rule.evaluate(extraction, config)
            rule_results.append(result)

            if not result.passed:
                if rule.is_critical:
                    critical_failures = True
                else:
                    soft_failures = True

        # Determine overall verdict status
        if critical_failures:
            status = VerdictStatusValues.FAIL
        elif soft_failures:
            status = VerdictStatusValues.REVIEW
        else:
            status = VerdictStatusValues.PASS

        return Verdict(
            status=status,
            rule_results=rule_results,
            extracted_fields=extraction.fields,
            field_confidence=extraction.confidence,
            model_id=extraction.model_id,
            latency_ms=extraction.latency_ms,
            total_tokens=None,
        )

    def add_rule(self, rule_class: type[Rule]) -> None:
        """Add a new rule to the evaluator.

        Args:
            rule_class: Rule subclass to add.
        """
        if rule_class not in self.rules:
            self.rules.append(rule_class)
            self.rule_instances.append(rule_class())
