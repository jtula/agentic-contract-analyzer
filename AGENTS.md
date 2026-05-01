# AGENTS.md — Contract Risk Analyzer

> **Reference guide for AI agents (Codex, Claude, Cursor, Copilot, etc.)**
> This file describes the architecture, conventions, and rules of the project so that any agent can contribute correctly without breaking the system.

---

## OpenSpec

OpenSpec is a **spec-driven development (SDD) framework** for AI coding assistants. It ensures human and AI align on requirements before implementation, keeping specs organized in a dedicated `openspec/` directory.

### When to Use OpenSpec

Use OpenSpec when starting new features, significant refactors, or any change that needs structured planning. The workflow is iterative: explore ideas, create proposals, implement, verify, and archive.

### Key Commands

| Command         | When to Use                                                     |
| --------------- | --------------------------------------------------------------- |
| `/opsx-explore` | Think through a problem before committing to implementation     |
| `/opsx-propose` | Start a new change - creates proposal, specs, design, and tasks |
| `/opsx-apply`   | Implement tasks from an existing change proposal                |
| `/opsx-verify`  | After implementation, verify that the change meets the specs    |
| `/opsx-archive` | Once verified, archive the change for future reference          |

### Workflow Overview

```
1. Explore  →  2. Propose  →  3. Implement  →  4. Verify  →  5. Archive
   /opsx-       /opsx-         /opsx-          /opsx-         /opsx-
   explore       propose        apply            verify          archive
```

### Relevant Skills

| Skill                   | Purpose                                                    |
| ----------------------- | ---------------------------------------------------------- |
| `openspec-propose`      | Create all artifacts (proposal, design, tasks) in one step |
| `openspec-apply-change` | Implement tasks from an existing change proposal           |

For all available commands and skills, see `.opencode/skills/<skill-name>/SKILL.md`

## Available Skills

Skills provide detailed guidance for specific tasks. Activate them as needed.

| Skill                 | Description                                                                      | When to Activate                                                                       |
| --------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `q-python-code`       | Clean Architecture + Polylith code generation with dependency injection patterns | When creating new features, components, adapters, or any Python code in the repository |
| `q-python-code-style` | Pre-commit, linting and formatting enforcement                                   | After making code changes, before committing                                           |
| `q-python-unit-tests` | Essential unit testing guidelines (no high coverage required)                    | When writing tests for new or existing code                                            |
| `q-migrations`        | Alembic migration generation from SQLAlchemy models                              | When modifying `impl_repository_postgres/models.py`                                    |
| `q-issue-generator`   | Generate structured GitHub issues from brief ideas or requirements               | When user wants to create issues from ideas                                            |

Location: `skills/<skill-name>/SKILL.md`

## 1. Project Overview

**Contract Risk Analyzer** is a multi-agent system based on **LangGraph** that analyzes legal contracts in PDF format and identifies risks, ambiguities, and problematic clauses. It exposes an API using **FastAPI** with SSE streaming and is deployed on **AWS** (Lambda + DynamoDB + S3 + API Gateway).

```
contract-risk-analyzer/
├── src/
│   ├── graph/          # LangGraph StateGraph (system core)
│   ├── nodes/          # Each agent as a pure function
│   ├── models/         # Pydantic v2 models (inputs/outputs for each node)
│   ├── services/       # AWS integrations (S3, DynamoDB) and LLM
│   ├── api/            # FastAPI + SSE streaming
│   └── utils/          # Retry decorator, logger
├── tests/
│   ├── unit/           # Isolated node tests
│   └── integration/    # Full graph tests with mock LLM
├── infrastructure/
│   ├── terraform/      # IaC for AWS
│   └── docker-compose.yml
└── docs/
```

---

## 2. Stack and Versions

| Tool           | Minimum Version | Notes                                                   |
| -------------- | --------------- | ------------------------------------------------------- |
| Python         | 3.11+           | Mandatory. Do not use 3.9 or 3.10                       |
| LangGraph      | 0.2+            | Main orchestrator. DO NOT use LangChain as orchestrator |
| LangChain      | 0.3+            | Only for loaders, embeddings, and LLM integrations      |
| FastAPI        | 0.111+          | Backend + SSE streaming                                 |
| Pydantic       | v2 (2.x)        | All models use `model_config`, not `class Config`       |
| boto3          | 1.34+           | AWS SDK                                                 |
| PyMuPDF (fitz) | 1.24+           | PDF text extraction                                     |
| pytest         | 8.x             | Testing. Use `pytest-asyncio` for async tests           |
| Docker         | 24+             | Local dev with LocalStack                               |

---

## 3. LangGraph Graph Architecture

### 3.1 GraphState

The shared state between all nodes is defined in `src/graph/state.py` as a `TypedDict`. **Never pass data between nodes outside the state.**

```python
# src/graph/state.py — campos del GraphState
class GraphState(TypedDict):
    # Input
    document_id: str
    s3_path: str
    document_text: str

    # Outputs por nodo
    extractor_output: ExtractorOutput | None
    summary_output: SummaryOutput | None
    risk_analysis_output: RiskAnalysisOutput | None
    validation_output: ValidationOutput | None

    # Control de flujo
    global_confidence: float
    needs_human_review: bool
    human_feedback: str | None
    current_node: str
    errors: list[str]
    retry_count: int

    # Metadata
    created_at: str
    updated_at: str
```

### 3.2 Graph Nodes

Each node is a **pure function** with this exact signature:

```python
def node_name(state: GraphState) -> dict:
    """Descripción del nodo."""
    ...
    return {"campo_actualizado": valor}   # Solo los campos que modifica
```

**Golden rule:** nodes only return the fields of the state they modify. LangGraph merges automatically.

| Node               | File                        | Description                                                 |
| ------------------ | --------------------------- | ----------------------------------------------------------- |
| `extractor`        | `nodes/extractor.py`        | Extracts text from PDF and segments sections                |
| `summarizer`       | `nodes/summarizer.py`       | Summarizes each section with LLM + structured output        |
| `risk_analyzer`    | `nodes/risk_analyzer.py`    | Detects risks with severity and confidence per clause       |
| `validator`        | `nodes/validator.py`        | Crosses outputs and calculates global confidence            |
| `hitl_gate`        | `nodes/hitl_gate.py`        | Decides whether to pause for human review                   |
| `report_generator` | `nodes/report_generator.py` | Generates final report in JSON + Markdown and uploads to S3 |

### 3.3 Edges y Routing

```
extractor
    │
    ├──► summarizer  ─┐
    │                  ├──► validator ──► hitl_gate ──► report_generator
    └──► risk_analyzer ┘
         (paralelo con Send())
```

Conditional routing logic is **only** in `src/graph/edges.py`. Do not put routing `if/else` inside nodes.

```python
# src/graph/edges.py — ejemplo de routing en hitl_gate
def route_after_validation(state: GraphState) -> str:
    if state["needs_human_review"]:
        return "hitl_gate"       # Pausa para revisión humana
    return "report_generator"    # Continúa automáticamente
```

---

## 4. Code Conventions

### 4.1 Type Hints — Mandatory Everywhere

```python
# ✅ CORRECTO
def analyze_risk(state: GraphState) -> dict[str, RiskAnalysisOutput]:
    ...

# ❌ INCORRECTO — sin type hints
def analyze_risk(state):
    ...
```

### 4.2 Pydantic v2 — Structured Outputs

Todos los outputs de nodos tienen su Pydantic model en `src/models/`. Usa siempre `model_config` de Pydantic v2:

```python
# src/models/risk.py
from pydantic import BaseModel, Field
from enum import Enum

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class RiskItem(BaseModel):
    model_config = {"frozen": True}   # ✅ Pydantic v2

    description: str = Field(..., min_length=10)
    severity: Severity
    confidence: float = Field(..., ge=0.0, le=1.0)
    clause_reference: str
    recommendation: str

class RiskAnalysisOutput(BaseModel):
    risks: list[RiskItem]
    total_risks: int
    highest_severity: Severity
    analysis_timestamp: str
```

**Never use `class Config` from Pydantic v1.**

### 4.3 Retry Decorator

Cualquier llamada externa (LLM, S3, DynamoDB) **debe** usar el decorator `@with_retry`:

```python
# Uso correcto
from src.utils.retry import with_retry

@with_retry(max_retries=3, backoff_factor=2.0)
async def call_llm(prompt: str) -> str:
    ...
```

The decorator is in `src/utils/retry.py` and handles:

- `max_retries=3` by default
- Exponential backoff: `wait = backoff_factor ** attempt`
- Logging of each failed attempt
- Re-raise of the original exception after exhausting attempts

### 4.4 Logging

Usa el logger centralizado, **nunca `print()`**:

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)

logger.info("node_started", node="extractor", document_id=state["document_id"])
logger.error("node_failed", node="extractor", error=str(e), retry_count=state["retry_count"])
```

The logger emits structured JSON. Required fields in each log: `node`, `document_id`.

### 4.5 Docstrings

Todas las funciones y clases públicas llevan docstring en formato Google:

```python
def extract_sections(text: str) -> dict[str, str]:
    """Segmenta el texto del contrato en secciones identificadas.

    Args:
        text: Texto completo extraído del PDF.

    Returns:
        Diccionario con nombre de sección como clave y contenido como valor.

    Raises:
        ExtractionError: Si el texto no tiene estructura reconocible.
    """
```

---

## 5. Nodes — Implementation Guide

### 5.1 EXTRACTOR NODE (`nodes/extractor.py`)

**Responsibility:** extract clean text from the PDF and segment it into sections.

- Use **PyMuPDF** (`fitz`), not pdfplumber (faster and more accurate)
- Read the PDF from S3 using `services/s3_service.py`
- Identify sections heuristically: PARTES, OBJETO, CLÁUSULAS, PENALIZACIONES, FECHAS
- If no sections are found → return the full text without segmentation (do not fail)
- Update `state["current_node"] = "extractor"`

**Output model:** `ExtractorOutput` with fields `sections`, `raw_text`, `page_count`, `extraction_confidence`.

### 5.2 SUMMARIZER NODE (`nodes/summarizer.py`)

**Responsibility:** summarize each section with LLM in structured format.

- Call the LLM via `services/llm_service.py` (never directly)
- Force structured output with `.with_structured_output(SummaryOutput)`
- Process sections in parallel with `asyncio.gather()` if more than 3
- Temperature: `0.1` (maximum determinism for legal analysis)

**Output model:** `SummaryOutput` with `section_summaries: list[SectionSummary]`, `executive_summary`, `key_parties`, `contract_duration`.

### 5.3 RISK ANALYZER NODE (`nodes/risk_analyzer.py`)

**Responsibility:** detect legal, financial, and ambiguity risks.

- Analyze each clause individually
- Assign `severity: LOW | MEDIUM | HIGH | CRITICAL`
- Assign `confidence: float` (0.0–1.0) per risk
- Mandatory risk categories to detect:
  - `FINANCIAL`: penalties, fines, hidden payments
  - `LEGAL`: ambiguities, abusive clauses, jurisdiction
  - `TEMPORAL`: critical dates, short deadlines, automatic renewals
  - `COMPLIANCE`: GDPR, data protection, sector regulations

**Output model:** `RiskAnalysisOutput`.

### 5.4 VALIDATOR NODE (`nodes/validator.py`)

**Responsibility:** verify consistency between Summarizer and Risk Analyzer.

- Cross references: each risk must have a real clause in the text
- If a risk has no textual support → mark as `unverified=True`
- Calculate `global_confidence` as weighted average:
  ```
  global_confidence = (summary_confidence * 0.3) + (avg_risk_confidence * 0.7)
  ```
- If `global_confidence < 0.75` or there are `CRITICAL` risks → `needs_human_review = True`

### 5.5 HITL GATE (`nodes/hitl_gate.py`)

**Responsibility:** pause the graph for human review when necessary.

- Implement with `interrupt()` from LangGraph:

  ```python
  from langgraph.types import interrupt, Command

  def hitl_gate(state: GraphState):
      if state["needs_human_review"]:
          feedback = interrupt({
              "reason": "Low confidence or critical risks detected",
              "current_risks": state["risk_analysis_output"].model_dump(),
              "confidence": state["global_confidence"]
          })
          return {"human_feedback": feedback, "current_node": "hitl_gate"}
      return {"current_node": "hitl_gate"}
  ```

- The endpoint `POST /analyze/{run_id}/resume` resumes the graph with `Command(resume=feedback)`

### 5.6 REPORT GENERATOR (`nodes/report_generator.py`)

**Responsibility:** generate and persist the final report.

- Generates two formats:
  - `report.json`: complete structured output
  - `report.md`: human-readable Markdown
- Uploads both to S3 at `s3://bucket/reports/{document_id}/`
- Includes in the report: `model_used`, `total_tokens`, `processing_time_ms`, `langsmith_trace_url`

---

## 6. FastAPI API

### 6.1 Endpoints

| Method | Path                       | Description                                    |
| ------ | -------------------------- | ---------------------------------------------- |
| POST   | `/analyze`                 | Starts analysis. Returns `run_id` + SSE stream |
| GET    | `/runs/{run_id}`           | Current run state (from DynamoDB)              |
| POST   | `/analyze/{run_id}/resume` | Resumes a paused graph (HITL)                  |
| GET    | `/health`                  | Health check                                   |

### 6.2 Streaming SSE

The `/analyze` endpoint returns a `StreamingResponse` with `media_type="text/event-stream"`.

Each event has this format:

```
data: {"event": "node_completed", "node": "extractor", "status": "success", "output": {...}, "timestamp": "2024-01-01T00:00:00Z"}

data: {"event": "node_completed", "node": "risk_analyzer", "status": "success", "output": {...}}

data: {"event": "human_review_required", "run_id": "abc123", "reason": "critical_risk_detected"}

data: {"event": "analysis_completed", "report_url": "s3://...", "run_id": "abc123"}
```

### 6.3 API Rules

- **Do not use `<form>` HTML** in any frontend component (if any)
- All endpoints have explicit `response_model` with Pydantic
- Errors follow the format:
  ```json
  {
    "error": "node_failed",
    "node": "extractor",
    "detail": "...",
    "run_id": "abc123"
  }
  ```

---

## 7. AWS Services

### 7.1 S3 Service (`services/s3_service.py`)

```python
# Available operations
upload_document(file_bytes: bytes, document_id: str) -> str          # Returns s3_path
download_document(s3_path: str) -> bytes
upload_report(report_json: dict, report_md: str, document_id: str)  # Uploads both formats
```

### 7.2 DynamoDB Service (`services/dynamo_service.py`)

- Table: `contract-analyzer-runs`
- Partition key: `run_id` (str)
- Used as **LangGraph checkpointer** via `DynamoDBSaver`
- **Do not store contract data in DynamoDB**, only metadata and graph state

### 7.3 LLM Service (`services/llm_service.py`)

- Wrapper over the LLM client (OpenAI or Bedrock depending on `LLM_PROVIDER` env var)
- Always logs: `model`, `prompt_tokens`, `completion_tokens`, `latency_ms`
- LangSmith tracing enabled via env vars (not configured in code)
- Never instantiate the LLM client directly in nodes; always use this service

---

## 8. Environment Variables

Copy `.env.example` to `.env` for local development. **Never commit `.env`**.

```bash

# LLM
LLM_PROVIDER=openai                    # openai | bedrock
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# AWS (use LocalStack for local development)
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566  # Only for local LocalStack
S3_BUCKET_NAME=contract-analyzer-docs
DYNAMODB_TABLE_NAME=contract-analyzer-runs

# LangSmith (Observability)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=contract-risk-analyzer

# App
LOG_LEVEL=INFO
CONFIDENCE_THRESHOLD=0.75              # Threshold for HITL
MAX_FILE_SIZE_MB=10
```

---

## 9. Testing

### 9.1 Test Structure

```
tests/
├── unit/
│   ├── nodes/
│   │   ├── test_extractor.py
│   │   ├── test_summarizer.py
│   │   ├── test_risk_analyzer.py
│   │   ├── test_validator.py
│   │   └── test_report_generator.py
│   ├── services/
│   │   └── test_llm_service.py
│   └── utils/
│       └── test_retry.py
└── integration/
    ├── test_full_graph.py             # Grafo completo con mock LLM
    └── test_hitl_flow.py              # Test del flujo de HITL
```

### 9.2 Testing Conventions

```python

# ✅ Each node is tested in isolation with minimal state
def test_extractor_node_extracts_sections():
    state = GraphState(
        document_id="test-123",
        s3_path="s3://bucket/test.pdf",
        document_text=SAMPLE_CONTRACT_TEXT,
        # ... rest as None
    )
    result = extractor_node(state)
    assert result["extractor_output"].sections is not None
    assert result["extractor_output"].extraction_confidence > 0.5

# ✅ Mock LLM in all unit tests
@patch("src.services.llm_service.LLMService.call")
def test_summarizer_node(mock_llm):
    mock_llm.return_value = SummaryOutput(...)
    ...

# ✅ Integration tests use fixtures of anonymized real contracts
# Store in tests/fixtures/sample_contracts/
```

### 9.3 Commands

```bash
make test              # Todos los tests
make test-unit         # Solo unitarios
make test-integration  # Solo integración
make test-cov          # Con coverage report (mínimo 80%)
```

---

## 10. Graceful Degradation

If a node fails after retries, the system **must not cascade fail**. Rules:

1. The failed node logs the error in `state["errors"]`
2. Returns the output field as `None`
3. The next node checks if it has what it needs:
   ```python
   if state["extractor_output"] is None:
       logger.warning("extractor_failed_using_raw_text", ...)
       # Continues with raw text instead of sections
   ```
4. The `validator_node` detects partial outputs and lowers `global_confidence` proportionally
5. The final report includes the `"errors"` section with what failed

---

## 11. Rules That CANNOT Be Broken

These rules are inviolable. If an agent breaks them, the PR must be rejected:

1. **Do not use CrewAI or AutoGen.** The orchestrator is pure LangGraph.
2. **Do not use LangChain as orchestrator.** Only for loaders, embeddings, and LLM wrappers.
3. **Do not instantiate the LLM client directly in a node.** Always via `LLMService`.
4. **Do not use `print()`.** Always use `logger.info()` or appropriate level.
5. **Do not commit `.env`, credentials, or API keys.**
6. **Do not modify `GraphState` without updating integration tests.**
7. **Do not add routing logic inside nodes.** Only in `graph/edges.py`.
8. **Do not use Pydantic v1 (`class Config`).** Always `model_config` from v2.
9. **Every new node must have its unit test.** No exceptions.
10. **Do not hardcode S3 bucket or DynamoDB table names.** Always from env vars.

---

## 12. How to Run Locally

```bash

# 1. Clone and set up environment
git clone https://github.com/your-user/contract-risk-analyzer
cd contract-risk-analyzer
cp .env.example .env           # Edit with your API keys

# 2. Start local infrastructure (LocalStack simulates AWS)
make up                        # docker-compose up -d

# 3. Create local AWS resources (S3 bucket + DynamoDB table)
make setup-local-aws

# 4. Run the API
make run                       # uvicorn src.api.main:app --reload

# 5. Test with a sample contract
curl -X POST http://localhost:8000/analyze \
    -F "file=@tests/fixtures/sample_contract.pdf" \
    -H "Accept: text/event-stream"
```

---

## 13. Contribution Workflow for Agents

When an AI agent works in this repository, it must follow this order:

1. **Read this file (`AGENTS.md`) completely** before writing code
2. **Read `src/graph/state.py`** to understand the shared state
3. **Read the affected node** before modifying it
4. **Run the unit tests for the node** before proposing changes:
   ```bash
   pytest tests/unit/nodes/test_{node}.py -v
   ```
5. **Verify that the full graph still works:**
   ```bash
   make test-integration
   ```
6. **Do not modify public interfaces** (GraphState, node signatures) without consensus

---

_Last updated: generated for the Contract Risk Analyzer project — LangGraph + AWS Portfolio Project_
