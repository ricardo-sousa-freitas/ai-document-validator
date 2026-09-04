"""Golden set evaluation harness for quality metrics."""

from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

import yaml

from ai_document_validator.common.constants import InvoiceFieldNames
from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.config_types import RuleConfig
from ai_document_validator.config.validation import RuleConfigModel
from ai_document_validator.process.extraction.selector import extract_document_file
from ai_document_validator.process.rules.evaluator import RulesEvaluator

logger = setup_logger(__name__)


class EvaluationMetrics(NamedTuple):
    """Aggregated evaluation metrics."""

    total_cases: int
    passed_cases: int
    failed_cases: int
    verdict_agreement_rate: float
    field_exact_match_rates: dict[str, float]
    failures: list[dict[str, Any]]


class DocumentEvaluationCase(NamedTuple):
    """Golden case backed by a real document and hand-maintained output."""

    case_id: str
    document: str
    expected_fields: dict[str, Any] | None
    expected_verdict: str
    expected_extraction_status: str | None
    expected_failed_rules: list[str]


class DocumentEvaluationState(NamedTuple):
    """Accumulators used during document-pair evaluation."""

    verdict_matches: int
    failures: list[dict[str, Any]]
    field_matches: dict[str, list[bool]]


class DocumentGoldenSetEvaluator:
    """Evaluate extraction and rules against real document/expected-output pairs."""

    def __init__(self, expected_file: str | Path, config_file: str | Path | None = None) -> None:
        """Load document-pair expectations and a separate evaluation config."""
        self.expected_file = Path(expected_file)
        self.document_dir = self.expected_file.parent / "documents"
        self.test_cases: list[DocumentEvaluationCase] = []
        self.config = self._load_expected_file(config_file)
        self.evaluator = RulesEvaluator()

    def _load_expected_file(self, config_file: str | Path | None) -> RuleConfig:
        """Load cases and the validated evaluation config."""
        with self.expected_file.open(encoding="utf-8") as file_handle:
            data: dict[str, Any] = yaml.safe_load(file_handle) or {}

        self.test_cases = [
            DocumentEvaluationCase(
                case_id=case["id"],
                document=case["document"],
                expected_fields=case.get("expected_fields"),
                expected_verdict=case["expected_verdict"],
                expected_extraction_status=case.get("expected_extraction_status"),
                expected_failed_rules=case.get("expected_failed_rules", []),
            )
            for case in data.get("cases", [])
        ]
        selected_config = (
            Path(config_file)
            if config_file
            else Path(__file__).parent.parent / "config" / "rule_validation_config.yaml"
        )
        with selected_config.open(encoding="utf-8") as file_handle:
            config_data: dict[str, Any] = yaml.safe_load(file_handle) or {}
        config = RuleConfigModel.model_validate(config_data).to_rule_config()
        logger.info("Loaded canonical evaluation: cases=%d", len(self.test_cases))
        return config

    def evaluate_all(self) -> EvaluationMetrics:
        """Evaluate all canonical document-pair cases."""
        logger.info("Starting canonical golden evaluation: cases=%d", len(self.test_cases))
        field_names = tuple(InvoiceFieldNames.all_fields())
        state = DocumentEvaluationState(
            verdict_matches=0,
            failures=[],
            field_matches={field_name: [] for field_name in field_names},
        )

        for case in self.test_cases:
            state = self._evaluate_document_case(case, state)

        total = len(self.test_cases)
        metrics = EvaluationMetrics(
            total_cases=total,
            passed_cases=state.verdict_matches,
            failed_cases=total - state.verdict_matches,
            verdict_agreement_rate=state.verdict_matches / total if total else 0.0,
            field_exact_match_rates={
                field: sum(matches) / len(matches) if matches else 0.0 for field, matches in state.field_matches.items()
            },
            failures=state.failures,
        )
        logger.info(
            "Completed canonical golden evaluation: agreement=%.1f%% failures=%d",
            metrics.verdict_agreement_rate * 100,
            len(metrics.failures),
        )
        return metrics

    def _evaluate_document_case(
        self,
        case: DocumentEvaluationCase,
        state: DocumentEvaluationState,
    ) -> DocumentEvaluationState:
        """Evaluate one document-pair case and update accumulators."""
        document_path = self.document_dir / case.document
        if case.expected_extraction_status:
            try:
                extract_document_file(document_path)
            except ValueError:
                return state._replace(verdict_matches=state.verdict_matches + int(case.expected_verdict == "REVIEW"))
            state.failures.append({"case_id": case.case_id, "type": "extraction_status_mismatch"})
            return state

        extraction = extract_document_file(document_path)
        verdict = self.evaluator.evaluate(extraction, self.config)
        if verdict.status == case.expected_verdict:
            state = state._replace(verdict_matches=state.verdict_matches + 1)
        else:
            state.failures.append(
                {
                    "case_id": case.case_id,
                    "type": "verdict_mismatch",
                    "expected": case.expected_verdict,
                    "actual": verdict.status,
                }
            )

        actual_failed_rules = [result.rule_id for result in verdict.rule_results if not result.passed]
        if actual_failed_rules != case.expected_failed_rules:
            state.failures.append(
                {
                    "case_id": case.case_id,
                    "type": "failed_rules_mismatch",
                    "expected": case.expected_failed_rules,
                    "actual": actual_failed_rules,
                }
            )

        for field_name, matches in state.field_matches.items():
            expected_value = self._normalize_expected_value((case.expected_fields or {}).get(field_name))
            actual_value = getattr(extraction.fields, field_name)
            matches.append(expected_value == actual_value)
            if expected_value != actual_value:
                state.failures.append(
                    {
                        "case_id": case.case_id,
                        "type": "field_mismatch",
                        "field": field_name,
                        "expected": str(expected_value),
                        "actual": str(actual_value),
                    }
                )
        return state

    @staticmethod
    def _normalize_expected_value(expected_value: Any) -> Any:
        """Normalize ISO date strings before field comparison."""
        if expected_value is None or not isinstance(expected_value, str):
            return expected_value
        try:
            return date.fromisoformat(expected_value)
        except ValueError:
            return expected_value

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
