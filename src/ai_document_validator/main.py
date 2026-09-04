"""Application entry point."""

import sys

from ai_document_validator.common.logging_config import setup_logger

logger = setup_logger(__name__)


def main() -> None:
    """Main entry point for the application."""
    logger.info("AI Document Validator started")
    logger.info("Use the evaluation harness: python -m ai_document_validator.eval")
    sys.exit(0)


if __name__ == "__main__":
    main()
