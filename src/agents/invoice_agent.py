"""InvoiceProcessorAgent — end-to-end invoice processing pipeline.

Upload → Extract → Parse → PO Match → Governance → Book → Ledger
Processes invoices in parallel batches with confidence-gated approval.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

import asyncpg

from src.config import settings
from src.governance.gate import ConfidenceGate, GateDecision
from src.ingestion.invoice_parser import InvoiceParser, ParsedInvoice
from src.ingestion.models import LDU
from src.ledger.events import InvoiceBooked, InvoiceFlaggedForReview, InvoiceParsed, InvoicePOMatched
from src.ledger.store import EventStore

logger = logging.getLogger(__name__)


class InvoiceProcessorAgent:
    """Autonomous invoice processing: extract → parse → match PO → book.

    Low-confidence or high-amount invoices are routed to human review.
    Every action is recorded in the event-sourced ledger.
    """

    def __init__(self, pool: asyncpg.Pool, event_store: EventStore) -> None:
        self._pool = pool
        self._store = event_store
        self._gate = ConfidenceGate(
            auto_approve=settings.hitl_auto_approve_threshold,
            escalation=settings.hitl_escalation_threshold,
        )
        self._parser = InvoiceParser()

    async def process_invoice(
        self, org_id: str, document_id: str, ldus: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Full invoice processing pipeline.

        Returns structured result with invoice data, PO match status, and booking decision.
        """
        stream_id = f"invoice-{org_id}-{document_id}"
        version = await self._store.stream_version(stream_id)

        # 1. Parse invoice from LDUs
        ldu_objs = [LDU(**ldu) if isinstance(ldu, dict) else ldu for ldu in ldus]
        parsed = self._parser.parse(ldu_objs)

        # Record parse event
        parse_event = InvoiceParsed.create(
            org_id=org_id, document_id=document_id,
            vendor=parsed.vendor_name, invoice_number=parsed.invoice_number,
            total_amount=parsed.total_amount, confidence=parsed.confidence,
        )
        version = await self._store.append(stream_id, [parse_event], version)

        # 2. PO matching
        po_match = None
        if parsed.po_number:
            po_match = await self._match_po(org_id, parsed.po_number, parsed.total_amount)
            if po_match:
                match_event = InvoicePOMatched.create(
                    org_id=org_id, invoice_id=document_id,
                    po_number=parsed.po_number, match_confidence=po_match["confidence"],
                )
                version = await self._store.append(stream_id, [match_event], version)

        # 3. Governance gate
        gate_result = self._gate.evaluate(
            confidence=parsed.confidence,
            payload={
                "vendor_name": parsed.vendor_name,
                "total_amount": parsed.total_amount,
                "invoice_number": parsed.invoice_number,
            },
            context=f"invoice:{parsed.vendor_name}:{parsed.total_amount}",
        )

        # 4. Decision
        invoice_id = str(uuid.uuid4())
        if gate_result.decision == GateDecision.AUTO_APPROVE:
            # Auto-book
            gl_account = self._suggest_gl_account(parsed)
            await self._persist_invoice(org_id, document_id, invoice_id, parsed, gl_account, booked=True)
            book_event = InvoiceBooked.create(
                org_id=org_id, invoice_id=invoice_id,
                gl_account=gl_account, booked_by="invoice-agent",
            )
            version = await self._store.append(stream_id, [book_event], version)
            decision = "booked"
        else:
            # Flag for review
            reason = gate_result.reason
            if gate_result.amount_anomaly:
                reason = f"Unusual amount ${parsed.total_amount:,.2f} — {reason}"
            await self._persist_invoice(org_id, document_id, invoice_id, parsed, booked=False)
            flag_event = InvoiceFlaggedForReview.create(
                org_id=org_id, invoice_id=invoice_id,
                reason=reason, confidence=parsed.confidence,
            )
            version = await self._store.append(stream_id, [flag_event], version)
            await self._queue_review(org_id, invoice_id, reason, parsed.confidence)
            decision = "review"

        # Build chain
        chain = await self._store.build_chain(stream_id)

        return {
            "invoice_id": invoice_id,
            "vendor_name": parsed.vendor_name,
            "invoice_number": parsed.invoice_number,
            "total_amount": parsed.total_amount,
            "currency": parsed.currency,
            "invoice_date": parsed.invoice_date,
            "due_date": parsed.due_date,
            "po_number": parsed.po_number,
            "po_matched": po_match is not None,
            "line_items": [li.model_dump() for li in parsed.line_items],
            "confidence": parsed.confidence,
            "decision": decision,
            "stream_id": stream_id,
            "audit_chain": chain,
        }

    async def _match_po(self, org_id: str, po_number: str, amount: float) -> dict[str, Any] | None:
        """Match invoice PO number against purchase orders in the system."""
        # In production: query PO table or QuickBooks. Here: simple lookup.
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM invoices WHERE org_id=$1 AND po_number=$2 AND booked=TRUE LIMIT 1",
                org_id, po_number,
            )
        if row:
            return {"po_number": po_number, "matched": True, "confidence": 0.92}
        return None

    def _suggest_gl_account(self, parsed: ParsedInvoice) -> str:
        """Suggest GL account based on vendor and line items."""
        vendor_lower = parsed.vendor_name.lower()
        if any(kw in vendor_lower for kw in ["aws", "google cloud", "azure", "hosting", "server"]):
            return "6200-Technology"
        if any(kw in vendor_lower for kw in ["rent", "lease", "property"]):
            return "6100-Rent"
        if any(kw in vendor_lower for kw in ["insurance"]):
            return "6400-Insurance"
        if any(kw in vendor_lower for kw in ["legal", "law", "attorney"]):
            return "6500-Legal"
        if any(kw in vendor_lower for kw in ["office", "supplies", "staples"]):
            return "6300-Office"
        return "6900-General"

    async def _persist_invoice(
        self, org_id: str, document_id: str, invoice_id: str,
        parsed: ParsedInvoice, gl_account: str | None = None, booked: bool = False,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO invoices
                   (invoice_id, org_id, document_id, vendor_name, invoice_number,
                    invoice_date, due_date, total_amount, currency, line_items,
                    po_number, gl_account, booked, confidence_score, provenance)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)""",
                uuid.UUID(invoice_id), org_id, document_id,
                parsed.vendor_name, parsed.invoice_number,
                None, None,  # date parsing in production
                parsed.total_amount, parsed.currency,
                json.dumps([li.model_dump() for li in parsed.line_items]),
                parsed.po_number, gl_account, booked, parsed.confidence,
                json.dumps({"extraction_method": parsed.extraction_method}),
            )

    async def _queue_review(self, org_id: str, invoice_id: str, reason: str, confidence: float) -> None:
        deadline = datetime.utcnow() + timedelta(hours=settings.hitl_review_sla_hours)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO review_queue (org_id, review_type, reason, confidence_score, payload, sla_deadline)
                   VALUES ($1, 'invoice_extraction', $2, $3, $4, $5)""",
                org_id, reason, confidence, json.dumps({"invoice_id": invoice_id}), deadline,
            )
