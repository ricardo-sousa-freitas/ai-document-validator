# AI Document Validator

A production-shaped document validation service for B2B compliance platforms. Extracts structured fields from supplier invoices and evaluates business rules to produce a trusted validation verdict.

**Status**: MVP (core extraction + rules + evaluation harness) ✓  
**Language**: Python 3.12+  
**API Framework**: FastAPI

---

## Quick Start

### 1. Install Dependencies

```bash
# Using uv (recommended)
uv sync --all-groups

# Or using pip
pip install -e ".[dev]"
```

### 2. Run Evaluation Harness

Validate the canonical document-pair golden set:

```bash
python -m ai_document_validator.eval
```

**Output**:
- Verdict-level agreement rate (expected vs actual)
- Field-level exact-match rates per field
- Detailed failure report with rule explanations

### 3. Run Unit & Integration Tests

```bash
pytest tests/ -v                          # All tests
pytest tests/ -v -m unit                  # Unit tests only
pytest tests/ -v -m integration           # Integration tests only
pytest tests/ --cov --cov-report=html     # With coverage (opens HTML report)
```

### 4. Code Quality Checks

```bash
# Type checking (strict mode)
mypy src/ --config-file pyproject.toml

# Formatting & linting
black src/ tests/
isort src/ tests/
flake8 src/ tests/ --max-line-length 120 --max-complexity 10
pylint src/ --rcfile=.pylintrc
vulture src/ --min-confidence 100
```

---

## Architecture Overview

### Layered Package Structure

```
src/ai_document_validator/
├── __init__.py                 # Package entry point
├── main.py                     # CLI entry point
│
├── common/                     # Shared utilities
│   ├── logging_config.py      # Centralized logger setup
│   ├── constants.py           # Field names, statuses, confidence thresholds
│   └── __init__.py
│
├── config/                     # Configuration & type definitions
│   ├── config_types.py        # NamedTuple types (InvoiceFields, Verdict, etc.)
│   └── __init__.py
│
├── clients/                    # External service clients
│   ├── extractors.py          # Extractor implementations (Text, Fixture, PDF)
│   └── __init__.py
│
├── process/                    # Core domain logic
│   ├── extraction/
│   │   └── __init__.py
│   ├── rules/
│   │   ├── evaluator.py       # Rule base class, concrete rules, RulesEvaluator
│   │   └── __init__.py
│   └── __init__.py
│
├── eval/                       # Evaluation harness
│   ├── __main__.py            # Module entry point (python -m)
│   ├── cli.py                 # CLI runner
│   ├── golden_set.py          # Golden set loader & metrics
│   └── __init__.py
│
├── api.py                      # FastAPI endpoints
│
├── ui/                         # Streamlit user interface (future)
│   └── __init__.py
│
└── workflow/                   # Orchestration (future multi-step flows)
    └── __init__.py

fixtures/
├── expected.yaml              # Hand-maintained expected outputs
└── documents/                 # Real text/PDF golden inputs

tests/
├── __init__.py
├── conftest.py               # Shared pytest fixtures
├── test_rules.py             # Unit tests for rules engine
└── test_extraction_pipeline.py  # Integration tests
```

### Data Flow

```
Document (text/PDF/fixture)
    ↓
[Extraction Layer]
  • TextExtractor (heuristic regex)
  • PDFExtractor (PyPDF2 + TextExtractor)
  • Document-pair golden evaluator (real text/PDF inputs)
    ↓
ExtractionResult
  • InvoiceFieldsExtracted (supplier_name, invoice_number, invoice_date, total_amount, currency, tax_id)
  • FieldConfidence (per-field confidence scores)
  • Evidence snippet & page hint
    ↓
[Rules Engine]
  • SupplierNameRule (required, non-empty)
  • InvoiceDateRule (present, not older than max_age_days)
  • TotalAmountRule (present, > 0)
  • CurrencyRule (in allowed list, if configured)
    ↓
Verdict
  • Status: PASS | FAIL | REVIEW
  • Rule results (per-rule pass/fail + message)
  • Extracted fields & confidence
  • Metadata (model ID, latency, token usage)
```

### Confidence Scoring Strategy

**Heuristic approach** (regex + pattern matching):

Confidence describes extraction evidence quality, not a calibrated probability of correctness. The extractor records
the winning regex tier and the number of candidate matches for each field:

- `0.9 (HIGH)`: Most-specific regex tier with one candidate
- `0.6 (SECONDARY)`: Less-specific regex tier, or two candidates requiring disambiguation
- `0.3 (FALLBACK)`: Weak regex tier, or three or more candidates requiring heuristic selection
- `0.0 (MISSING)`: Field is absent or cannot be parsed

For example, a single `Total Amount` match receives high confidence, while a totals table containing `Subtotal`,
`Net total`, and `Total Amount` is marked low-confidence even when the selected amount is correct. PDF extraction uses
the same field scoring after converting the PDF text layer. Fixture extraction preserves the confidence values supplied
by its hand-maintained fixture.

When LLM integration is added, confidence will use embedding similarity or LLM confidence scores while reusing the same Verdict structure.

### Rule Evaluation Logic

**Critical rules** (failure → FAIL verdict):
- `SupplierNameRule` — supplier_name required
- `InvoiceDatePresentRule` — date required
- `InvoiceDateWithinMaxAgeRule` — date must not be too old
- `TotalAmountRule` — amount required and > 0
- `CurrencyRule` — currency must be in allowed list (when allowed_currencies is configured)

**Soft rules** (failure → REVIEW verdict):
- `ConfidenceThresholdRule` — present required fields must meet `review_confidence_threshold`

**Verdict Logic**:
- **PASS**: All rules pass
- **FAIL**: Any critical rule fails
- **REVIEW**: No critical rule fails, but a soft rule fails

---

## Golden Test Set

18 document/expected-output cases in `fixtures/expected.yaml`:

| Fixture | Supplier | Status | Reason |
|---------|----------|--------|--------|
| `invoice_001` | Acme Corporation | PASS | All fields present, recent, EUR allowed |
| `invoice_002` | TechSupply Ltd | PASS | All fields present, recent, GBP allowed |
| `invoice_003` | Global Industries | FAIL | Currency USD not in [EUR, GBP] |
| `invoice_004_missing_date` | PartnerCo | FAIL | Missing required invoice_date |
| `invoice_005_zero_amount` | ZeroCost Supplier | FAIL | Amount is 0 (must be > 0) |
| `invoice_006_wrong_currency` | JPYSupplier | FAIL | Currency JPY not in [EUR, GBP] |

**Running evaluation harness:**

```bash
python -m ai_document_validator.eval
```

**Expected output**:
```
================================================================================
EVALUATION HARNESS RESULTS
================================================================================

VERDICT LEVEL:
  Total cases: 6
  Passed: 2
  Failed: 4
  Agreement rate: 100.0%

FIELD LEVEL (exact-match rate):
  ✓ supplier_name: 100.0%
  ✓ invoice_number: 100.0%
  ✓ invoice_date: 83.3%
  ✓ total_amount: 100.0%
  ✓ currency: 83.3%
  ~ tax_id: 50.0%

FAILURES (0 issues):
✓ All tests passed!

================================================================================
```

---

## Design Trade-offs & Decisions

### 1. Extraction: Heuristic vs LLM

**Current**: Heuristic (regex + pattern matching)

**Why**: 
- Fast (<10ms vs 500ms-2s for LLM)
- Deterministic and testable
- No API keys or cost per document
- Reviewers can run without credentials

**When to use LLM**:
- Free-form invoice layouts (not structured/templated)
- Need semantic understanding (e.g., "invoice total" vs "line item total")
- Cost per document is acceptable (<0.01 USD)
- Latency tolerance is >500ms

**Migration path**: Extract a `confidence` score for each field. When LLM is added, replace heuristic confidence with LLM embedding similarity or model confidence. Verdict structure remains unchanged.

### 2. Fixtures vs Real OCR

**Current**: YAML fixtures (no PDF processing)

**Why**:
- Reproducible and version-controllable
- Reviewers don't need OCR libraries or PDF credentials
- Allows testing logic without document processing

**Fallback**: TextExtractor + PDFExtractor classes are implemented and functional; switch to real PDFs by changing `EXTRACTION_MODE` environment variable.

### 3. Rules Engine Design

**Current**: Abstract `Rule` class with concrete subclasses

**Why**:
- Extensible: add new rules without modifying existing code
- Testable: each rule is unit-testable in isolation
- Configurable: rule parameters (max_age_days, allowed_currencies) are config-driven

**Example**: Adding a new rule (e.g., InvoiceNumberFormatRule):

```python
class InvoiceNumberFormatRule(Rule):
    rule_id = "invoice_number_format"
    is_critical = True

    def evaluate(self, extraction, config):
        # Custom validation logic
        return RuleResult(...)

# Add to evaluator
evaluator.add_rule(InvoiceNumberFormatRule)
```

### 4. Type Safety

**Current**: All public functions fully annotated; mypy strict mode

**Why**:
- Catch errors at type-check time (before runtime)
- Self-documenting code (signatures are contracts)
- NamedTuple for config reduces dict-related runtime errors

---

## Cost, Latency & Monitoring (Production Notes)

### Estimated Per-Document Cost & Latency

| Component | Latency | Cost |
|-----------|---------|------|
| Heuristic extraction | 5-10ms | $0.00 |
| LLM extraction (GPT-4o) | 500-1000ms | $0.001-0.01 |
| Rules evaluation | 1-2ms | $0.00 |
| **Total (heuristic)** | **10ms** | **$0.00** |
| **Total (LLM)** | **600ms** | **$0.002** |

### What to Monitor in Production

1. **Quality metrics**:
   - Verdict agreement rate (vs human review, if available)
   - Field extraction accuracy per field
   - Confidence score distribution (are confidence scores calibrated?)

2. **Performance metrics**:
   - End-to-end latency (p50, p95, p99)
   - Rule evaluation time per rule
   - Extraction time by document type

3. **Cost metrics** (if using LLM):
   - Total tokens per document
   - Cost per document
   - Token efficiency (fields extracted per token spent)

4. **Drift detection**:
   - Is verdict distribution shifting? (e.g., more FAILs over time)
   - Is confidence distribution changing?
   - Are rule failure rates increasing?

5. **Observability**:
   - Log extraction confidence per field
   - Log rule evaluation results (which rules fail most often?)
   - Log evidence snippets for failed verdicts (for debugging)
   - Use structured JSON logging with request ID, timestamp, document type

---

## API Usage

The API accepts JSON requests. Plain text is sent in `content`; PDF bytes are sent as base64 in
`content_base64`. `source_name` determines the format unless an explicit `content_type` is supplied.
PDFs with no extractable text layer return `UNSUPPORTED_DOCUMENT`; corrupted PDFs return a safe `400` error.

```bash
# Start server
uv run python -m ai_document_validator.api

# POST /v1/validate (plain text)
curl -X POST http://localhost:8000/v1/validate \
  -H "Content-Type: application/json" \
  -d '{"source_name":"invoice.txt","content":"Supplier: Acme Corp\\nInvoice Number: INV-1\\nDate: 2026-09-01\\nAmount: 100.00\\nCurrency: EUR","config":{"document_type":"SUPPLIER_INVOICE","allowed_currencies":["EUR"]}}'

# POST /v1/extract (base64 PDF)
curl -X POST http://localhost:8000/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"source_name":"invoice.pdf","content_base64":"<base64-pdf>","config":{"document_type":"SUPPLIER_INVOICE"}}'

# GET /health
curl http://localhost:8000/health
```

## Streamlit Interface

Run the local document-validation interface:

```bash
uv run streamlit run src/ai_document_validator/ui/streamlit_app.py
```

Upload a `.txt` or `.pdf` invoice, set the date and currency rules, and inspect the extracted fields,
confidence values, evidence preview, and rule verdicts.

**Response** (example):

```json
{
  "status": "PASS",
  "fields": {
    "supplier_name": "Acme Corp",
    "invoice_number": "INV-2024-001",
    "invoice_date": "2024-09-01",
    "total_amount": 5000.0,
    "currency": "EUR",
    "tax_id": "VAT-DE-123456789"
  },
  "confidence": {
    "supplier_name": 0.95,
    "invoice_number": 0.95,
    "invoice_date": 0.95,
    "total_amount": 0.95,
    "currency": 0.90,
    "tax_id": 0.85
  },
  "rule_results": [
    {
      "rule_id": "supplier_name_required",
      "passed": true,
      "message": "Supplier name is present"
    },
    // ... other rules
  ],
  "model_id": "heuristic_v1",
  "latency_ms": 8.5,
  "total_tokens": null
}
```

---

## What's Next (With More Time)

### Phase 2: HTTP API
- [x] FastAPI endpoints for `/v1/validate`, `/v1/extract`, `/health`
- [x] Base64 JSON document input and strict Pydantic config validation
- [x] OpenAPI schema generated from the request/response models
- [ ] Structured JSON logging with request ID and verdict

### Phase 3: LLM Integration
- [ ] Abstract extraction interface (heuristic | LLM via factory)
- [ ] OpenAI GPT-4o integration for complex layouts
- [ ] Anthropic Claude as alternative provider
- [ ] LLM confidence scores + token tracking
- [ ] Cost per document metrics

### Phase 4: Multi-Document Support
- [ ] Support SUPPLIER_INVOICE, PURCHASE_ORDER, SHIPPING_LABEL, etc.
- [ ] Dynamic field schemas per document type
- [ ] Document-type-aware confidence thresholds

### Phase 5: Production Hardening
- [ ] PDF OCR (Azure Form Recognizer, AWS Textract)
- [ ] Async document processing with task queues
- [ ] Result caching + duplicate detection
- [ ] Audit trail (who reviewed, when, why overridden)
- [ ] Model versioning + A/B testing

### Phase 6: Observability
- [ ] Prometheus metrics (verdict rate, latency, cost)
- [ ] Structured logging (OpenTelemetry traces)
- [ ] Drift monitoring (alert on quality degradation)
- [ ] Debug dashboard (sample verdicts, failure analysis)

---

## Dependencies

See `pyproject.toml`:

**Runtime**:
- `fastapi` - Web framework (Phase 2)
- `pydantic` - Data validation & settings
- `pypdf` - PDF text extraction
- `pyyaml` - YAML fixture parsing
- `python-dotenv` - Environment configuration
- `uvicorn` - ASGI server (Phase 2)

**Dev**:
- `pytest`, `pytest-cov` - Testing
- `black`, `isort` - Code formatting
- `flake8`, `pylint`, `mypy` - Linting & type checking
- `vulture` - Dead code detection
- `ruff` - Fast Python linter

---

## Contributing

1. **Branch**: `feature/name` or `fix/issue-name`
2. **Tests**: All changes must include unit tests (`@pytest.mark.unit`)
3. **Type checking**: `mypy src/ --strict` must pass
4. **Formatting**: Run `black src/`, `isort src/`
5. **Linting**: Run `flake8`, `pylint`
6. **Commit**: Include descriptive message + context

---

## License

[Add your license here]

---

## Support

For questions or issues:
1. Check the golden set evaluation output (run `python -m ai_document_validator.eval`)
2. Review test cases (`tests/test_rules.py`, `tests/test_extraction_pipeline.py`)
3. Check document examples in `fixtures/documents/` and expected outputs in `fixtures/expected.yaml`
4. See `AI_USAGE.md` for AI tool usage and design decisions
