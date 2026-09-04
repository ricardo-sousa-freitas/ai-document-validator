"""CLI entry point for evaluation harness."""

import argparse
import sys
from pathlib import Path

from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.eval.golden_set import DocumentGoldenSetEvaluator

logger = setup_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the canonical or legacy evaluation harness.

    Args:
        argv: Optional command-line arguments, primarily for tests.

    Returns:
        Exit code (0 for success, 1 for failures).
    """
    parser = argparse.ArgumentParser(description="Evaluate invoice extraction and validation quality.")
    parser.add_argument(
        "--expected-file",
        type=Path,
        default=Path(__file__).parent.parent.parent.parent / "fixtures" / "expected.yaml",
        help="Canonical expected.yaml path.",
    )
    args = parser.parse_args(argv)

    try:
        if not args.expected_file.exists():
            logger.error("Expected file not found: %s", args.expected_file)
            return 1
        document_evaluator = DocumentGoldenSetEvaluator(args.expected_file)
        metrics = document_evaluator.evaluate_all()
    except (OSError, ValueError, KeyError) as exc:
        logger.exception("Evaluation failed: %s", type(exc).__name__)
        return 1

    DocumentGoldenSetEvaluator.print_metrics(metrics)

    # Exit with appropriate code
    if metrics.failed_cases > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
