"""Integration tests for the HTTP API."""

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_document_validator.api import app


@pytest.mark.integration
class TestApi:
    """Test HTTP extraction and validation endpoints."""

    client = TestClient(app)
    samples_dir = Path(__file__).parent.parent / "fixtures" / "documents"

    def _text_payload(self) -> dict[str, object]:
        """Build a valid text validation request."""
        return {
            "source_name": "invoice.txt",
            "content": "Supplier: Example Corp\nInvoice Number: INV-1\nDate: 2026-09-01\nAmount: 100.00\nCurrency: EUR",
            "config": {
                "document_type": "SUPPLIER_INVOICE",
                "allowed_currencies": ["EUR"],
            },
        }

    def test_health(self) -> None:
        """Return a liveness response."""
        response = self.client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_validate_text_document(self) -> None:
        """Extract and validate a text document."""
        response = self.client.post("/v1/validate", json=self._text_payload())

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "PASS"
        assert body["fields"]["supplier_name"] == "Example Corp"
        assert body["fields"]["total_amount"] == 100.0
        assert body["rule_results"]

    def test_extract_pdf_document(self) -> None:
        """Extract a base64-encoded PDF document."""
        pdf_bytes = (self.samples_dir / "inv_001_clean_eur.pdf").read_bytes()
        payload = {
            "source_name": "inv_001_clean_eur.pdf",
            "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "config": {"document_type": "SUPPLIER_INVOICE"},
        }

        response = self.client.post("/v1/extract", json=payload)

        assert response.status_code == 200
        assert response.json()["fields"]["invoice_number"] == "INV-2026-0417"

    def test_rejects_unknown_config_key(self) -> None:
        """Reject unknown rule configuration keys at request validation."""
        payload = self._text_payload()
        payload["config"] = {"document_type": "SUPPLIER_INVOICE", "unexpected": True}

        response = self.client.post("/v1/validate", json=payload)

        assert response.status_code == 422
        assert "extra_forbidden" in response.text

    def test_rejects_multiple_content_representations(self) -> None:
        """Require exactly one document representation."""
        payload = self._text_payload()
        payload["content_base64"] = base64.b64encode(b"duplicate").decode("ascii")

        response = self.client.post("/v1/extract", json=payload)

        assert response.status_code == 422
        assert "exactly one" in response.text

    def test_returns_safe_error_for_corrupt_pdf(self) -> None:
        """Return a client error without exposing document internals."""
        payload = {
            "source_name": "corrupt.pdf",
            "content_base64": base64.b64encode(b"not a PDF").decode("ascii"),
            "config": {"document_type": "SUPPLIER_INVOICE"},
        }

        response = self.client.post("/v1/validate", json=payload)

        assert response.status_code == 400
        assert response.json()["detail"] == "Failed to extract PDF document"
        assert "not a PDF" not in response.text

    def test_returns_unsupported_status_for_scanned_pdf(self) -> None:
        """Return a structured outcome for a PDF with no text layer."""
        pdf_bytes = (self.samples_dir / "inv_012_scanned_no_text.pdf").read_bytes()
        payload = {
            "source_name": "inv_012_scanned_no_text.pdf",
            "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "config": {"document_type": "SUPPLIER_INVOICE"},
        }

        response = self.client.post("/v1/validate", json=payload)

        assert response.status_code == 200
        assert response.json()["status"] == "UNSUPPORTED_DOCUMENT"
