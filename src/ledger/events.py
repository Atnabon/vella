"""FYTO Ops domain events — finance operations lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OptimisticConcurrencyError(Exception):
    def __init__(self, stream_id: str, expected: int, actual: int) -> None:
        self.stream_id, self.expected_version, self.actual_version = stream_id, expected, actual
        super().__init__(f"OCC conflict '{stream_id}': expected={expected}, actual={actual}")


class StreamNotFoundError(Exception):
    def __init__(self, stream_id: str) -> None:
        self.stream_id = stream_id
        super().__init__(f"Stream '{stream_id}' not found")


class BaseEvent(BaseModel):
    event_type: str
    event_version: int = 1
    payload: dict[str, Any]


class StoredEvent(BaseModel):
    event_id: uuid.UUID
    stream_id: str
    stream_position: int
    global_position: int
    event_type: str
    event_version: int
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime


# ── Invoice Events ────────────────────────────────────────────────────────────

class InvoiceUploaded(BaseEvent):
    event_type: str = "InvoiceUploaded"

    @classmethod
    def create(cls, org_id: str, document_id: str, filename: str) -> "InvoiceUploaded":
        return cls(payload={"org_id": org_id, "document_id": document_id, "filename": filename,
                            "uploaded_at": datetime.utcnow().isoformat()})


class InvoiceParsed(BaseEvent):
    event_type: str = "InvoiceParsed"

    @classmethod
    def create(cls, org_id: str, document_id: str, vendor: str, invoice_number: str,
               total_amount: float, confidence: float) -> "InvoiceParsed":
        return cls(payload={"org_id": org_id, "document_id": document_id, "vendor_name": vendor,
                            "invoice_number": invoice_number, "total_amount": total_amount,
                            "confidence": confidence, "parsed_at": datetime.utcnow().isoformat()})


class InvoicePOMatched(BaseEvent):
    event_type: str = "InvoicePOMatched"

    @classmethod
    def create(cls, org_id: str, invoice_id: str, po_number: str, match_confidence: float) -> "InvoicePOMatched":
        return cls(payload={"org_id": org_id, "invoice_id": invoice_id, "po_number": po_number,
                            "match_confidence": match_confidence, "matched_at": datetime.utcnow().isoformat()})


class InvoiceBooked(BaseEvent):
    event_type: str = "InvoiceBooked"

    @classmethod
    def create(cls, org_id: str, invoice_id: str, gl_account: str, booked_by: str) -> "InvoiceBooked":
        return cls(payload={"org_id": org_id, "invoice_id": invoice_id, "gl_account": gl_account,
                            "booked_by": booked_by, "booked_at": datetime.utcnow().isoformat()})


class InvoiceFlaggedForReview(BaseEvent):
    event_type: str = "InvoiceFlaggedForReview"

    @classmethod
    def create(cls, org_id: str, invoice_id: str, reason: str, confidence: float) -> "InvoiceFlaggedForReview":
        return cls(payload={"org_id": org_id, "invoice_id": invoice_id, "reason": reason,
                            "confidence": confidence, "flagged_at": datetime.utcnow().isoformat()})


# ── Reconciliation Events ────────────────────────────────────────────────────

class ReconciliationStarted(BaseEvent):
    event_type: str = "ReconciliationStarted"

    @classmethod
    def create(cls, org_id: str, account_name: str, period_start: str, period_end: str) -> "ReconciliationStarted":
        return cls(payload={"org_id": org_id, "account_name": account_name,
                            "period_start": period_start, "period_end": period_end,
                            "started_at": datetime.utcnow().isoformat()})


class TransactionMatched(BaseEvent):
    event_type: str = "TransactionMatched"

    @classmethod
    def create(cls, org_id: str, txn_id: str, invoice_id: str | None, confidence: float) -> "TransactionMatched":
        return cls(payload={"org_id": org_id, "txn_id": txn_id, "invoice_id": invoice_id,
                            "confidence": confidence, "matched_at": datetime.utcnow().isoformat()})


class DiscrepancyDetected(BaseEvent):
    event_type: str = "DiscrepancyDetected"

    @classmethod
    def create(cls, org_id: str, account_name: str, difference: float, description: str) -> "DiscrepancyDetected":
        return cls(payload={"org_id": org_id, "account_name": account_name,
                            "difference": difference, "description": description,
                            "detected_at": datetime.utcnow().isoformat()})


class ReconciliationCompleted(BaseEvent):
    event_type: str = "ReconciliationCompleted"

    @classmethod
    def create(cls, org_id: str, account_name: str, matched: int, unmatched: int,
               difference: float) -> "ReconciliationCompleted":
        return cls(payload={"org_id": org_id, "account_name": account_name,
                            "matched_count": matched, "unmatched_count": unmatched,
                            "difference": difference, "completed_at": datetime.utcnow().isoformat()})


# ── Tax Events ────────────────────────────────────────────────────────────────

class TaxEstimateComputed(BaseEvent):
    event_type: str = "TaxEstimateComputed"

    @classmethod
    def create(cls, org_id: str, tax_year: int, quarter: int | None,
               gross_revenue: float, total_expenses: float, taxable_income: float,
               total_tax: float) -> "TaxEstimateComputed":
        return cls(payload={"org_id": org_id, "tax_year": tax_year, "quarter": quarter,
                            "gross_revenue": gross_revenue, "total_expenses": total_expenses,
                            "taxable_income": taxable_income, "total_estimated_tax": total_tax,
                            "computed_at": datetime.utcnow().isoformat()})


class TaxDocumentCollected(BaseEvent):
    event_type: str = "TaxDocumentCollected"

    @classmethod
    def create(cls, org_id: str, tax_year: int, doc_type: str, document_id: str) -> "TaxDocumentCollected":
        return cls(payload={"org_id": org_id, "tax_year": tax_year, "doc_type": doc_type,
                            "document_id": document_id, "collected_at": datetime.utcnow().isoformat()})


# ── Audit Events ──────────────────────────────────────────────────────────────

class AuditPackageGenerated(BaseEvent):
    event_type: str = "AuditPackageGenerated"

    @classmethod
    def create(cls, org_id: str, package_id: str, events_included: int,
               final_hash: str) -> "AuditPackageGenerated":
        return cls(payload={"org_id": org_id, "package_id": package_id,
                            "events_included": events_included, "final_hash": final_hash,
                            "generated_at": datetime.utcnow().isoformat()})


class HumanReviewRequested(BaseEvent):
    event_type: str = "HumanReviewRequested"

    @classmethod
    def create(cls, review_type: str, entity_id: str, reason: str, confidence: float) -> "HumanReviewRequested":
        return cls(payload={"review_type": review_type, "entity_id": entity_id,
                            "reason": reason, "confidence": confidence,
                            "requested_at": datetime.utcnow().isoformat()})


class HumanReviewCompleted(BaseEvent):
    event_type: str = "HumanReviewCompleted"

    @classmethod
    def create(cls, review_id: str, reviewer_id: str, decision: str, note: str | None = None) -> "HumanReviewCompleted":
        return cls(payload={"review_id": review_id, "reviewer_id": reviewer_id,
                            "decision": decision, "note": note,
                            "completed_at": datetime.utcnow().isoformat()})


EVENT_REGISTRY: dict[str, type[BaseEvent]] = {
    "InvoiceUploaded": InvoiceUploaded,
    "InvoiceParsed": InvoiceParsed,
    "InvoicePOMatched": InvoicePOMatched,
    "InvoiceBooked": InvoiceBooked,
    "InvoiceFlaggedForReview": InvoiceFlaggedForReview,
    "ReconciliationStarted": ReconciliationStarted,
    "TransactionMatched": TransactionMatched,
    "DiscrepancyDetected": DiscrepancyDetected,
    "ReconciliationCompleted": ReconciliationCompleted,
    "TaxEstimateComputed": TaxEstimateComputed,
    "TaxDocumentCollected": TaxDocumentCollected,
    "AuditPackageGenerated": AuditPackageGenerated,
    "HumanReviewRequested": HumanReviewRequested,
    "HumanReviewCompleted": HumanReviewCompleted,
}
