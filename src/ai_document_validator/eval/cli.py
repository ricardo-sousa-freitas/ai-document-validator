"""CLI entry point for evaluation harness."""

import sys
from pathlib import Path

from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.config_types import RuleConfig
from ai_document_validator.eval.golden_set import GoldenSetEvaluator

logger = setup_logger(__name__)


def main() -> int:
    """Run evaluation harness on golden set.

    Returns:
        Exit code (0 for success, 1 for failures).
    """
    # Find fixtures directory
    fixture_dir = Path(__file__).parent.parent.parent.parent / "fixtures"

    if not fixture_dir.exists():
        logger.error(f"Fixtures directory not found: {fixture_dir}")
        return 1

    logger.info(f"Loading golden test set from: {fixture_dir}")

    # Initialize evaluator
    evaluator = GoldenSetEvaluator(fixture_dir)

    # Define evaluation config
    config = RuleConfig(
        document_type="SUPPLIER_INVOICE",
        max_age_days=90,
        allowed_currencies=["EUR", "GBP"],
        required_fields=None,
    )

    logger.info("Running evaluation with config:")
    logger.info(f"  max_age_days={config.max_age_days}")
    logger.info(f"  allowed_currencies={config.allowed_currencies}")

    # Run evaluation
    metrics = evaluator.evaluate_all(config)

    # Print results
    GoldenSetEvaluator.print_metrics(metrics)

    # Exit with appropriate code
    if metrics.failed_cases > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
