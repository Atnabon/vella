-- vella Ops — Autonomous Finance Operations
-- Schema: event store + finance domain tables

-- ── Event Store ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS event_streams (
    stream_id        TEXT PRIMARY KEY,
    aggregate_type   TEXT NOT NULL,
    current_version  INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at      TIMESTAMPTZ,
    metadata         JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS events (
    event_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id        TEXT NOT NULL REFERENCES event_streams(stream_id),
    stream_position  INTEGER NOT NULL,
    global_position  BIGSERIAL,
    event_type       TEXT NOT NULL,
    event_version    INTEGER NOT NULL DEFAULT 1,
    payload          JSONB NOT NULL,
    metadata         JSONB NOT NULL DEFAULT '{}',
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(stream_id, stream_position)
);

CREATE INDEX IF NOT EXISTS idx_events_stream ON events(stream_id);
CREATE INDEX IF NOT EXISTS idx_events_global ON events(global_position);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_recorded ON events(recorded_at);

CREATE TABLE IF NOT EXISTS outbox (
    id           BIGSERIAL PRIMARY KEY,
    event_id     UUID NOT NULL REFERENCES events(event_id),
    destination  TEXT NOT NULL,
    payload      JSONB NOT NULL,
    published    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished ON outbox(published) WHERE NOT published;

-- ── Audit Hash Chain ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_chain (
    chain_id         BIGSERIAL PRIMARY KEY,
    stream_id        TEXT NOT NULL,
    event_id         UUID NOT NULL REFERENCES events(event_id),
    event_hash       TEXT NOT NULL,
    chain_hash       TEXT NOT NULL,
    chain_position   INTEGER NOT NULL,
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(stream_id, chain_position)
);

CREATE INDEX IF NOT EXISTS idx_audit_chain_stream ON audit_chain(stream_id);

-- ── Document Registry ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS documents (
    document_id      TEXT PRIMARY KEY,
    filename         TEXT NOT NULL,
    file_hash        TEXT NOT NULL UNIQUE,
    file_path        TEXT NOT NULL,
    doc_type         TEXT NOT NULL DEFAULT 'unknown',  -- invoice|bank_statement|tax_form|receipt|po|w2|1099|other
    origin_type      TEXT NOT NULL,                    -- native_digital|scanned_image|mixed
    layout_complexity TEXT NOT NULL,
    page_count       INTEGER NOT NULL,
    language         TEXT NOT NULL DEFAULT 'en',
    has_tables       BOOLEAN NOT NULL DEFAULT FALSE,
    recommended_strategy TEXT NOT NULL,
    strategy_rationale TEXT,
    estimated_cost_usd FLOAT NOT NULL DEFAULT 0.0,
    status           TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|extracted|matched|booked|review|failed
    confidence_score FLOAT,
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    extraction_cost_usd FLOAT,
    org_id           TEXT,
    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_org ON documents(org_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);

-- ── Organizations ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organizations (
    org_id           TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    plan             TEXT NOT NULL DEFAULT 'starter',  -- starter|business|enterprise
    quickbooks_realm_id TEXT,
    plaid_access_token TEXT,
    settings         JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Invoices ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           TEXT NOT NULL REFERENCES organizations(org_id),
    document_id      TEXT REFERENCES documents(document_id),
    vendor_name      TEXT NOT NULL,
    invoice_number   TEXT,
    invoice_date     DATE,
    due_date         DATE,
    total_amount     NUMERIC(14, 2) NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'USD',
    line_items       JSONB NOT NULL DEFAULT '[]',
    po_number        TEXT,
    po_matched       BOOLEAN NOT NULL DEFAULT FALSE,
    payment_status   TEXT NOT NULL DEFAULT 'unpaid',  -- unpaid|partial|paid|overdue
    gl_account       TEXT,
    booked           BOOLEAN NOT NULL DEFAULT FALSE,
    confidence_score FLOAT NOT NULL DEFAULT 1.0,
    provenance       JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_org ON invoices(org_id);
CREATE INDEX IF NOT EXISTS idx_invoices_vendor ON invoices(vendor_name);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(payment_status);
CREATE INDEX IF NOT EXISTS idx_invoices_due ON invoices(due_date) WHERE payment_status = 'unpaid';

-- ── Bank Transactions ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bank_transactions (
    txn_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           TEXT NOT NULL REFERENCES organizations(org_id),
    account_name     TEXT NOT NULL,
    account_last4    TEXT,
    txn_date         DATE NOT NULL,
    description      TEXT NOT NULL,
    amount           NUMERIC(14, 2) NOT NULL,
    txn_type         TEXT NOT NULL,  -- debit|credit
    category         TEXT,
    matched_invoice_id UUID REFERENCES invoices(invoice_id),
    reconciled       BOOLEAN NOT NULL DEFAULT FALSE,
    source           TEXT NOT NULL DEFAULT 'manual',  -- plaid|csv|manual
    imported_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bank_txn_org ON bank_transactions(org_id);
CREATE INDEX IF NOT EXISTS idx_bank_txn_reconciled ON bank_transactions(reconciled) WHERE NOT reconciled;
CREATE INDEX IF NOT EXISTS idx_bank_txn_date ON bank_transactions(txn_date);

-- ── Reconciliation ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reconciliations (
    recon_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           TEXT NOT NULL REFERENCES organizations(org_id),
    account_name     TEXT NOT NULL,
    period_start     DATE NOT NULL,
    period_end       DATE NOT NULL,
    opening_balance  NUMERIC(14, 2) NOT NULL DEFAULT 0,
    closing_balance  NUMERIC(14, 2) NOT NULL DEFAULT 0,
    book_balance     NUMERIC(14, 2) NOT NULL DEFAULT 0,
    difference       NUMERIC(14, 2) NOT NULL DEFAULT 0,
    matched_count    INTEGER NOT NULL DEFAULT 0,
    unmatched_count  INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'pending',  -- pending|in_progress|completed|discrepancy
    discrepancies    JSONB NOT NULL DEFAULT '[]',
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recon_org ON reconciliations(org_id);
CREATE INDEX IF NOT EXISTS idx_recon_status ON reconciliations(status);

-- ── Tax Estimates ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tax_estimates (
    estimate_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           TEXT NOT NULL REFERENCES organizations(org_id),
    tax_year         INTEGER NOT NULL,
    quarter          INTEGER,  -- 1-4, NULL for annual
    entity_type      TEXT NOT NULL DEFAULT 'llc',  -- sole_prop|llc|s_corp|c_corp|partnership
    gross_revenue    NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_expenses   NUMERIC(14, 2) NOT NULL DEFAULT 0,
    taxable_income   NUMERIC(14, 2) NOT NULL DEFAULT 0,
    federal_tax      NUMERIC(14, 2) NOT NULL DEFAULT 0,
    state_tax        NUMERIC(14, 2) NOT NULL DEFAULT 0,
    self_employment_tax NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_estimated_tax NUMERIC(14, 2) NOT NULL DEFAULT 0,
    deductions       JSONB NOT NULL DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'draft',  -- draft|computed|reviewed|filed
    computed_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tax_org ON tax_estimates(org_id);
CREATE INDEX IF NOT EXISTS idx_tax_year ON tax_estimates(tax_year);

-- ── Human Review Queue ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS review_queue (
    review_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           TEXT,
    document_id      TEXT REFERENCES documents(document_id),
    stream_id        TEXT,
    review_type      TEXT NOT NULL,  -- invoice_extraction|reconciliation_discrepancy|tax_review|po_match
    reason           TEXT NOT NULL,
    confidence_score FLOAT,
    payload          JSONB NOT NULL DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'pending',  -- pending|in_review|approved|rejected
    assigned_to      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at      TIMESTAMPTZ,
    resolved_by      TEXT,
    resolution_note  TEXT,
    sla_deadline     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_deadline ON review_queue(sla_deadline) WHERE status = 'pending';
