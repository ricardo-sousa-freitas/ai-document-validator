"""Select document extractors and run file-based extraction."""

from pathlib import Path
from typing import Any

from ai_document_validator.common.logging_config import setup_logger
from ai_document_validator.config.config_types import ExtractionResult
from ai_document_validator.process.extraction.extractors import Extractor, PDFExtractor, TextExtractor

logger = setup_logger(__name__)

_TEXT_EXTENSIONS = {".txt", ".text"}
_PDF_CONTENT_TYPE = "application/pdf"
_TEXT_CONTENT_TYPES = {"text/plain", "text/*"}


def select_extractor(
    source_name: str | Path | None = None,
    content_type: str | None = None,
) -> Extractor:
    """Select an extractor from an explicit content type or source extension.

    Args:
        source_name: Filename or path used when content type is unavailable.
        content_type: MIME type supplied by the caller.

    Returns:
        A configured extractor for the document format.

    Raises:
        ValueError: If the format is unsupported or ambiguous.
    """
    if content_type:
        normalized_content_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        if normalized_content_type == _PDF_CONTENT_TYPE:
            logger.info("Selected PDF extractor from content type")
            return PDFExtractor()
        if normalized_content_type in _TEXT_CONTENT_TYPES or normalized_content_type.startswith("text/"):
            logger.info("Selected text extractor from content type")
            return TextExtractor()
        raise ValueError(f"Unsupported document content type: {content_type}")

    if source_name is not None:
        suffix = Path(source_name).suffix.lower()
        if suffix == ".pdf":
            logger.info("Selected PDF extractor from source extension: %s", suffix)
            return PDFExtractor()
        if suffix in _TEXT_EXTENSIONS:
            logger.info("Selected text extractor from source extension: %s", suffix)
            return TextExtractor()
        raise ValueError(f"Unsupported document extension: {suffix or '<none>'}")

    return TextExtractor()


def extract_document_file(
    file_path: str | Path,
    content_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExtractionResult:
    """Extract a document from a file selected by MIME type or extension.

    Args:
        file_path: Path to a PDF or plain-text document.
        content_type: Optional MIME type, which takes precedence over extension.
        metadata: Optional metadata passed to the selected extractor.

    Returns:
        Structured extraction result.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the document format is unsupported or extraction fails.
    """
    path = Path(file_path)
    logger.info("Starting document extraction: source_type=%s", path.suffix.lower() or "unknown")
    extractor = select_extractor(path, content_type)
    if isinstance(extractor, PDFExtractor):
        result = extractor.extract(str(path), metadata)
    else:
        content = path.read_text(encoding="utf-8")
        result = extractor.extract(content, metadata)

    logger.info("Completed document extraction: source_type=%s", path.suffix.lower() or "unknown")
    return result
