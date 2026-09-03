"""Golden set evaluation harness for quality metrics."""

from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.config_types import RuleConfig
from ai_document_validator.process.extraction.extractors import FixtureExtractor
from ai_document_validator.process.rules.evaluator import RulesEvaluator

logger = setup_logger(__name__)


class EvaluationCase(NamedTuple):
    """Single test case with expected labels."""

    case_id: str
    expected_verdict: str
    expected_fields: dict[str, Any]


class EvaluationMetrics(NamedTuple):
    """Aggregated evaluation metrics."""

    total_cases: int
    passed_cases: int
    failed_cases: int
    verdict_agreement_rate: float
    field_exact_match_rates: dict[str, float]
    failures: list[dict[str, Any]]


class EvaluationState(NamedTuple):
    """Mutable accumulators used while evaluating golden cases."""

    verdict_matches: int
    failures: list[dict[str, Any]]
    field_matches_per_field: dict[str, list[bool]]


class GoldenSetEvaluator:
    """Evaluates extraction and verdict against golden test set."""

    def __init__(self, fixture_dir: str | Path) -> None:
        """Initialize with fixture directory.

        Args:
            fixture_dir: Path to directory containing fixture YAML files.
        """
        self.fixture_dir = Path(fixture_dir)
        self.extractor = FixtureExtractor(fixture_dir)
        self.evaluator = RulesEvaluator()
        self.test_cases: list[EvaluationCase] = []
        self._load_golden_set()

    def _load_golden_set(self) -> None:
        """Load golden test cases from fixtures."""
        for case_id, fixture in self.extractor.fixtures.items():
            expected_verdict = fixture.get("expected_verdict", "PASS")
            expected_fields = fixture.get("fields", {})
            self.test_cases.append(
                EvaluationCase(
                    case_id=case_id,
                    expected_verdict=expected_verdict,
                    expected_fields=expected_fields,
                )
            )
        logger.info(f"Loaded {len(self.test_cases)} golden test cases")

    def evaluate_all(self, config: RuleConfig | None = None) -> EvaluationMetrics:
        """Evaluate all test cases."""
        config = config or self._default_config()
        evaluation_state = EvaluationState(
            verdict_matches=0,
            failures=[],
            field_matches_per_field={
                "supplier_name": [],
                "invoice_number": [],
                "invoice_date": [],
                "total_amount": [],
                "currency": [],
                "tax_id": [],
            },
        )

        for case in self.test_cases:
            evaluation_state = self._evaluate_case(case, config, evaluation_state)

        total = len(self.test_cases)
        passed = evaluation_state.verdict_matches
        failed = total - passed
        field_exact_match_rates = {
            field_name: (sum(matches) / len(matches)) if matches else 0.0
            for field_name, matches in evaluation_state.field_matches_per_field.items()
        }

        return EvaluationMetrics(
            total_cases=total,
            passed_cases=passed,
            failed_cases=failed,
            verdict_agreement_rate=passed / total if total > 0 else 0.0,
            field_exact_match_rates=field_exact_match_rates,
            failures=evaluation_state.failures,
        )

    @staticmethod
    def _default_config() -> RuleConfig:
        """Build the default config used for golden-set evaluation."""
        return RuleConfig(
            document_type="SUPPLIER_INVOICE",
            max_age_days=90,
            allowed_currencies=["EUR", "GBP"],
            required_fields=None,
        )

    def _evaluate_case(
        self,
        case: EvaluationCase,
        config: RuleConfig,
        evaluation_state: EvaluationState,
    ) -> EvaluationState:
        """Evaluate one golden-case and accumulate its results."""
        extraction = self.extractor.extract("", metadata={"fixture_id": case.case_id})
        verdict = self.evaluator.evaluate(extraction, config)

        if verdict.status == case.expected_verdict:
            verdict_matches = evaluation_state.verdict_matches + 1
        else:
            verdict_matches = evaluation_state.verdict_matches
            evaluation_state.failures.append(self._verdict_failure(case, verdict))

        for field_name, matches_list in evaluation_state.field_matches_per_field.items():
            expected_value = self._normalize_expected_value(case.expected_fields.get(field_name))
            actual_value = getattr(extraction.fields, field_name, None)
            matches = expected_value == actual_value
            matches_list.append(matches)
            if not matches:
                evaluation_state.failures.append(
                    {
                        "case_id": case.case_id,
                        "type": "field_mismatch",
                        "field": field_name,
                        "expected": str(expected_value),
                        "actual": str(actual_value),
                    }
                )

        return EvaluationState(
            verdict_matches=verdict_matches,
            failures=evaluation_state.failures,
            field_matches_per_field=evaluation_state.field_matches_per_field,
        )

    @staticmethod
    def _normalize_expected_value(expected_value: Any) -> Any:
        """Normalize comparison values for field matching."""
        if expected_value is None or not isinstance(expected_value, str):
            return expected_value

        try:
            return date.fromisoformat(expected_value)
        except (TypeError, ValueError):
            return expected_value

    @staticmethod
    def _verdict_failure(case: EvaluationCase, verdict: Any) -> dict[str, Any]:
        """Build a failure payload for a verdict mismatch."""
        return {
            "case_id": case.case_id,
            "type": "verdict_mismatch",
            "expected": case.expected_verdict,
            "actual": verdict.status,
            "rule_results": [
                {
                    "rule_id": rr.rule_id,
                    "passed": rr.passed,
                    "message": rr.message,
                }
                for rr in verdict.rule_results
            ],
        }

    @staticmethod
    def print_metrics(metrics: EvaluationMetrics) -> None:
        """Print evaluation metrics in human-readable format.

        Args:
            metrics: EvaluationMetrics to print.
        """
        print("\n" + "=" * 80)
        print("EVALUATION HARNESS RESULTS")
        print("=" * 80)

        print("\nVERDICT LEVEL:")
        print(f"  Total cases: {metrics.total_cases}")
        print(f"  Passed: {metrics.passed_cases}")
        print(f"  Failed: {metrics.failed_cases}")
        print(f"  Agreement rate: {metrics.verdict_agreement_rate:.1%}")

        print("\nFIELD LEVEL (exact-match rate):")
        for field, rate in sorted(metrics.field_exact_match_rates.items()):
            status = "ok" if rate == 1.0 else "missing" if rate == 0.0 else "~"
            print(f"  {status} {field}: {rate:.1%}")

        if metrics.failures:
            print(f"\nFAILURES ({len(metrics.failures)} issues):")
            print("-" * 80)
            for failure in metrics.failures:
                print(f"\n  Case: {failure['case_id']}")
                print(f"  Type: {failure['type']}")
                if failure["type"] == "field_mismatch":
                    print(f"  Field: {failure['field']}")
                    print(f"    Expected: {failure['expected']}")
                    print(f"    Actual: {failure['actual']}")
                elif failure["type"] == "verdict_mismatch":
                    print(f"  Expected verdict: {failure['expected']}")
                    print(f"  Actual verdict: {failure['actual']}")
                    print("  Rule results:")
                    for rule in failure.get("rule_results", []):
                        status = "pass" if rule["passed"] else "fail"
                        print(f"    {status} {rule['rule_id']}: {rule['message']}")
        else:
            print("\nAll tests passed!")

        print("\n" + "=" * 80)
