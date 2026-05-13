"""Invoice processing endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.db import get_pool
from src.ledger.store import EventStore

router = APIRouter(prefix="/invoices", tags=["invoices"])


async def _deps():
    pool = await get_pool()
    store = EventStore(pool)
    return pool, store


class ProcessInvoiceRequest(BaseModel):
    org_id: str
    document_id: str


@router.post("/process")
async def process_invoice(
    req: ProcessInvoiceRequest,
    deps=Depends(_deps),
) -> dict[str, Any]:
    """Trigger invoice processing pipeline for an uploaded document."""
    from src.agents.invoice_agent import InvoiceProcessorAgent

    pool, store = deps

    # Load LDUs from the documents table
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM documents WHERE document_id=$1 AND org_id=$2",
            req.document_id, req.org_id,
        )
    if not row:
        raise HTTPException(404, detail="Document not found")

    doc = dict(row)
    ldus = doc.get("ldus") or []

    agent = InvoiceProcessorAgent(pool, store)
    try:
        result = await agent.process_invoice(req.org_id, req.document_id, ldus)
    except Exception as e:
        raise HTTPException(500, detail=f"Processing failed: {e}")

    return result


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str, deps=Depends(_deps)) -> dict[str, Any]:
    pool, _ = deps
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM invoices WHERE invoice_id=$1", invoice_id)
    if not row:
        raise HTTPException(404, detail="Invoice not found")
    return dict(row)


@router.get("/")
async def list_invoices(
    org_id: str | None = None,
    status: str | None = None,
    booked: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    deps=Depends(_deps),
) -> dict[str, Any]:
    pool, _ = deps
    conds, params = [], []
    if org_id:
        conds.append(f"org_id=${len(params)+1}"); params.append(org_id)
    if status:
        conds.append(f"payment_status=${len(params)+1}"); params.append(status)
    if booked is not None:
        conds.append(f"booked=${len(params)+1}"); params.append(booked)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM invoices {where} ORDER BY created_at DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM invoices {where}", *params)
    return {"total": total, "invoices": [dict(r) for r in rows]}


class BookInvoiceRequest(BaseModel):
    gl_account: str | None = None
    booked_by: str = "human"


@router.post("/{invoice_id}/book")
async def book_invoice(
    invoice_id: str, req: BookInvoiceRequest, deps=Depends(_deps),
) -> dict[str, Any]:
    """Manually book an invoice (after human review)."""
    from src.ledger.events import InvoiceBooked

    pool, store = deps
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM invoices WHERE invoice_id=$1", invoice_id)
        if not row:
            raise HTTPException(404, detail="Invoice not found")

        gl_account = req.gl_account or row["gl_account"] or "6900-General"
        await conn.execute(
            "UPDATE invoices SET booked=TRUE, gl_account=$1 WHERE invoice_id=$2",
            gl_account, invoice_id,
        )
        await conn.execute(
            "UPDATE review_queue SET status='approved', reviewed_at=NOW() WHERE payload->>'invoice_id'=$1",
            invoice_id,
        )

    inv = dict(row)
    stream_id = f"invoice-{inv['org_id']}-{inv['document_id']}"
    version = await store.stream_version(stream_id)
    event = InvoiceBooked.create(
        org_id=inv["org_id"], invoice_id=invoice_id,
        gl_account=gl_account, booked_by=req.booked_by,
    )
    await store.append(stream_id, [event], version)

    return {"invoice_id": invoice_id, "status": "booked", "gl_account": gl_account}
