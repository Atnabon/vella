"""AuditPrepAgent — generates self-contained audit-ready packages.

Collects evidence across the event ledger, verifies hash chain integrity,
produces a regulatory examination package that auditors can independently verify.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

from src.ledger.events import AuditPackageGenerated
from src.ledger.store import EventStore

logger = logging.getLogger(__name__)


class AuditPrepAgent:
    """Produces auditor-ready packages with independently verifiable audit trails."""

    def __init__(self, pool: asyncpg.Pool, event_store: EventStore) -> None:
        self._pool = pool
        self._store = event_store

    async def generate_package(
        self, org_id: str, stream_id: str,
    ) -> dict[str, Any]:
        """Generate a self-contained audit examination package.

        The package includes:
        - Full event history with payloads
        - Hash chain verification result
        - Lifecycle narrative
        - Source document provenance links
        - Summary statistics
        """
        events = await self._store.load_stream(stream_id)
        if not events:
            return {"error": f"Stream '{stream_id}' not found or empty"}

        # Verify integrity
        chain = await self._store.verify_chain(stream_id)

        # Build narrative
        narrative = []
        for e in events:
            ts = e.recorded_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            summary = _summarize(e.payload)
            narrative.append(f"[{ts}] {e.event_type}: {summary}")

        # Compute stats
        event_types: dict[str, int] = {}
        for e in events:
            event_types[e.event_type] = event_types.get(e.event_type, 0) + 1

        # Source documents referenced
        doc_refs = set()
        for e in events:
            for key in ("document_id", "source_document_id"):
                if key in e.payload:
                    doc_refs.add(e.payload[key])

        # Linked invoices
        invoice_refs = set()
        for e in events:
            for key in ("invoice_id", "matched_invoice_id"):
                if key in e.payload and e.payload[key]:
                    invoice_refs.add(str(e.payload[key]))

        # Amounts mentioned
        amounts = []
        for e in events:
            for key in ("total_amount", "amount", "difference", "total_estimated_tax"):
                if key in e.payload and isinstance(e.payload[key], (int, float)):
                    amounts.append({"event": e.event_type, "field": key, "value": e.payload[key]})

        package_id = f"PKG-{stream_id}-{events[-1].global_position}"

        # Record audit package generation
        gen_stream = f"audit-{org_id}"
        gen_version = await self._store.stream_version(gen_stream)
        gen_event = AuditPackageGenerated.create(
            org_id=org_id, package_id=package_id,
            events_included=len(events), final_hash=chain.get("final_hash", ""),
        )
        await self._store.append(gen_stream, [gen_event], gen_version)

        return {
            "package_id": package_id,
            "stream_id": stream_id,
            "org_id": org_id,
            "generated_at": datetime.utcnow().isoformat(),
            "event_count": len(events),
            "event_types": event_types,
            "hash_chain": {
                "integrity": chain.get("integrity"),
                "events_checked": chain.get("events_checked"),
                "final_hash": chain.get("final_hash"),
                "discrepancies": chain.get("discrepancies", []),
            },
            "lifecycle_narrative": "\n".join(narrative),
            "source_documents": list(doc_refs),
            "linked_invoices": list(invoice_refs),
            "amounts": amounts,
            "events": [
                {
                    "position": e.stream_position,
                    "type": e.event_type,
                    "payload": e.payload,
                    "recorded_at": e.recorded_at.isoformat(),
                }
                for e in events
            ],
        }

    async def list_streams(self, org_id: str) -> list[dict[str, Any]]:
        """List all event streams for an organization."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT stream_id, aggregate_type, current_version, created_at
                   FROM event_streams
                   WHERE stream_id LIKE $1
                   ORDER BY created_at DESC""",
                f"%-{org_id}%",
            )
        return [dict(r) for r in rows]


def _summarize(payload: dict[str, Any]) -> str:
    """One-line summary of an event payload."""
    keys = ["vendor_name", "invoice_number", "total_amount", "account_name",
            "confidence", "decision", "difference", "matched_count", "total_estimated_tax"]
    parts = []
    for k in keys:
        if k in payload:
            v = payload[k]
            if isinstance(v, float):
                parts.append(f"{k}={v:,.2f}")
            else:
                parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else str(payload)[:120]
