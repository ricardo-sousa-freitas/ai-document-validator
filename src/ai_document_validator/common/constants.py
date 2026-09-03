"""Shared domain constants."""


# Document types
class DocumentType:
    """Supported document types."""

    SUPPLIER_INVOICE = "SUPPLIER_INVOICE"


# Invoice field names
class InvoiceFieldNames:
    """Supplier invoice field identifiers."""

    SUPPLIER_NAME = "supplier_name"
    INVOICE_NUMBER = "invoice_number"
    INVOICE_DATE = "invoice_date"
    TOTAL_AMOUNT = "total_amount"
    CURRENCY = "currency"
    TAX_ID = "tax_id"

    @classmethod
    def all_fields(cls) -> list[str]:
        """Return all field names."""
        return [
            cls.SUPPLIER_NAME,
            cls.INVOICE_NUMBER,
            cls.INVOICE_DATE,
            cls.TOTAL_AMOUNT,
            cls.CURRENCY,
            cls.TAX_ID,
        ]


# Verdict statuses
class VerdictStatusValues:
    """Verdict status constants."""

    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"

    @classmethod
    def all_statuses(cls) -> list[str]:
        """Return all status values."""
        return [cls.PASS, cls.FAIL, cls.REVIEW]


# Confidence thresholds
CONFIDENCE_HIGH = 0.9  # Direct match
CONFIDENCE_MEDIUM = 0.7  # Regex/heuristic match
CONFIDENCE_LOW = 0.5  # Partial match
CONFIDENCE_MISSING = 0.0  # Field not found

# Default max age for invoices (days)
DEFAULT_MAX_INVOICE_AGE_DAYS = 90
