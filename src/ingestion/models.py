"""Ingestion models — document profiles, LDUs, extraction results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OriginType(str, Enum):
    NATIVE_DIGITAL = "native_digital"
    SCANNED_IMAGE = "scanned_image"
    MIXED = "mixed"


class LayoutComplexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class DocType(str, Enum):
    """US financial document classification."""
    INVOICE = "invoice"
    BANK_STATEMENT = "bank_statement"
    TAX_FORM = "tax_form"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    W2 = "w2"
    FORM_1099 = "1099"
    PAYROLL = "payroll"
    FINANCIAL_STATEMENT = "financial_statement"
    CONTRACT = "contract"
    UNKNOWN = "unknown"


class ExtractionStrategy(str, Enum):
    STRATEGY_A = "fast_text"
    STRATEGY_B = "layout_aware"
    STRATEGY_C = "vision_model"


class DocumentProfile(BaseModel):
    document_id: str
    filename: str
    file_hash: str
    file_path: str = ""
    doc_type: DocType = DocType.UNKNOWN
    origin_type: OriginType
    layout_complexity: LayoutComplexity
    page_count: int = Field(ge=1)
    language: str = "en"
    has_tables: bool = False
    has_images: bool = False
    scanned_page_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    recommended_strategy: ExtractionStrategy
    strategy_rationale: str = ""
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    profiled_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class Provenance(BaseModel):
    """Full chain of custody for an extracted datapoint."""
    document_id: str
    filename: str
    page_number: int
    bounding_box: list[float] | None = None
    section: str = ""
    content_hash: str = ""
    extraction_strategy: str = ""
    confidence: float = 1.0
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class LDU(BaseModel):
    """Least Discardable Unit — atomic extraction with provenance."""
    ldu_id: str = ""
    ldu_type: str = "text"  # text|table|header|line_item|amount|date
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionMetrics(BaseModel):
    extraction_time_seconds: float
    strategy_used: str
    escalation_count: int = 0
    total_cost_usd: float = 0.0
    average_confidence: float = 0.0
    low_confidence_count: int = 0


class LedgerEntry(BaseModel):
    document_id: str
    filename: str
    strategy_selected: str
    confidence_score: float
    cost_estimate_usd: float
    ldu_count: int
    table_count: int = 0
    escalated: bool = False
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    errors: list[str] = Field(default_factory=list)
    needs_human_review: bool = False


class ExtractedDocument(BaseModel):
    profile: DocumentProfile
    ldus: list[LDU]
    metrics: ExtractionMetrics
    ledger_entry: LedgerEntry
