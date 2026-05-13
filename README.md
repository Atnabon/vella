# Vella Ops

**Autonomous Finance Operations.**

Vella Ops is an AI-agent backend that processes invoices, reconciles accounts, prepares tax filings, and handles compliance — with full audit trails and human-in-the-loop governance.

---

## What it does

| Capability | Detail |
|---|---|
| Invoice processing | Extract, validate, and route invoices from PDFs and images |
| Reconciliation | Match transactions across bank feeds and accounting ledgers |
| Tax preparation | Compute tax positions and generate filing-ready summaries |
| Audit trail | Immutable ledger of every agent action and state transition |
| HITL governance | Confidence-gated auto-approval with escalation queues |
| Integrations | QuickBooks (accounting sync), Plaid (bank feed ingestion) |

---

## Architecture

```
vella-ops/
├── src/
│   ├── ingestion/       # Document triage, extraction pipeline, models
│   ├── agents/          # Invoice agent, reconciliation agent, tax agent, audit agent
│   ├── governance/      # HITL gate — auto-approve / escalate logic
│   ├── verification/    # Dialectical verification of extracted claims
│   ├── ledger/          # Immutable event store
│   ├── integrations/    # QuickBooks, Plaid connectors
│   ├── api/             # FastAPI routers (documents, invoices, reconciliation, tax, ledger)
│   ├── config.py        # Settings via pydantic-settings
│   └── db.py            # asyncpg connection pool
├── migrations/          # SQL migrations
├── data/                # Uploads, processed docs, ChromaDB
├── tests/
├── main.py              # App entry point
├── Dockerfile
└── docker-compose.yml
```

---

## Quickstart

### 1. Environment

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and DATABASE_URL at minimum
```

### 2. Run with Docker

```bash
docker compose up --build
```

### 3. Run locally

```bash
pip install -e ".[dev]"
uvicorn main:app --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/documents/upload` | Upload a financial document |
| `GET` | `/api/v1/documents/{id}` | Get document status and extracted data |
| `POST` | `/api/v1/invoices/process` | Process and validate an invoice |
| `GET` | `/api/v1/invoices/{id}` | Get invoice processing result |
| `POST` | `/api/v1/reconciliation/run` | Run account reconciliation |
| `GET` | `/api/v1/reconciliation/{id}` | Get reconciliation result |
| `POST` | `/api/v1/tax/prepare` | Generate tax filing summary |
| `GET` | `/api/v1/tax/{id}` | Get tax preparation result |
| `GET` | `/api/v1/ledger/events` | Query the audit ledger |
| `GET` | `/health` | Health check |

---

## Configuration

Key environment variables (see `.env.example` for full list):

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Claude API key (required) |
| `OPENAI_API_KEY` | OpenAI key for VLM extraction (optional) |
| `HITL_AUTO_APPROVE_THRESHOLD` | Confidence above which decisions auto-approve (default `0.90`) |
| `HITL_ESCALATION_THRESHOLD` | Confidence below which a human review is triggered (default `0.70`) |
| `QUICKBOOKS_CLIENT_ID` | QuickBooks OAuth client ID |
| `QUICKBOOKS_CLIENT_SECRET` | QuickBooks OAuth client secret |
| `PLAID_CLIENT_ID` | Plaid API client ID |
| `PLAID_SECRET` | Plaid API secret |
| `PLAID_ENV` | Plaid environment (`sandbox`, `development`, `production`) |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
black --check src/

# Type check
mypy src/
```

---

## Stack

- **Runtime**: Python 3.12, FastAPI, uvicorn
- **Database**: PostgreSQL (asyncpg)
- **Vector store**: ChromaDB
- **LLMs**: Anthropic Claude, OpenAI
- **PDF**: PyMuPDF, pdfplumber
- **Integrations**: QuickBooks API, Plaid API
