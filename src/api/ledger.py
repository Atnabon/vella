"""Audit ledger, review queue, and hash-chain verification endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.db import get_pool
from src.ledger.store import EventStore

router = APIRouter(prefix="/ledger", tags=["ledger"])


async def _deps():
    pool = await get_pool()
    store = EventStore(pool)
    return pool, store


# ── Event streams ──────────────────────────────────────────────────────────────

@router.get("/streams")
async def list_streams(
    org_id: str | None = None, limit: int = 50, offset: int = 0, deps=Depends(_deps),
) -> dict[str, Any]:
    pool, _ = deps
    conds, params = [], []
    if org_id:
        conds.append(f"stream_id LIKE ${len(params)+1}"); params.append(f"%-{org_id}%")
    where = "WHERE " + " AND ".join(conds) if conds else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT stream_id, aggregate_type, current_version, created_at FROM event_streams {where} ORDER BY created_at DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM event_streams {where}", *params)
    return {"total": total, "streams": [dict(r) for r in rows]}


@router.get("/streams/{stream_id}/events")
async def get_stream_events(stream_id: str, deps=Depends(_deps)) -> dict[str, Any]:
    _, store = deps
    events = await store.load_stream(stream_id)
    if not events:
        raise HTTPException(404, detail=f"Stream '{stream_id}' not found")
    return {
        "stream_id": stream_id,
        "event_count": len(events),
        "events": [
            {
                "position": e.stream_position,
                "type": e.event_type,
                "payload": e.payload,
                "recorded_at": e.recorded_at.isoformat(),
                "global_position": e.global_position,
            }
            for e in events
        ],
    }


@router.get("/streams/{stream_id}/verify")
async def verify_chain(stream_id: str, deps=Depends(_deps)) -> dict[str, Any]:
    """Verify the hash chain integrity of an event stream."""
    _, store = deps
    result = await store.verify_chain(stream_id)
    if not result:
        raise HTTPException(404, detail=f"Stream '{stream_id}' not found")
    return result


# ── Audit packages ─────────────────────────────────────────────────────────────

@router.post("/audit-package")
async def generate_audit_package(
    org_id: str, stream_id: str, deps=Depends(_deps),
) -> dict[str, Any]:
    """Generate a self-contained audit examination package."""
    from src.agents.audit_agent import AuditPrepAgent

    pool, store = deps
    agent = AuditPrepAgent(pool, store)
    result = await agent.generate_package(org_id, stream_id)
    if "error" in result:
        raise HTTPException(404, detail=result["error"])
    return result


@router.get("/audit-streams")
async def list_audit_streams(org_id: str, deps=Depends(_deps)) -> dict[str, Any]:
    from src.agents.audit_agent import AuditPrepAgent

    pool, store = deps
    agent = AuditPrepAgent(pool, store)
    streams = await agent.list_streams(org_id)
    return {"org_id": org_id, "streams": streams}


# ── Review queue ───────────────────────────────────────────────────────────────

@router.get("/review-queue")
async def list_review_queue(
    org_id: str | None = None,
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
    deps=Depends(_deps),
) -> dict[str, Any]:
    pool, _ = deps
    conds, params = [f"status=${len([])+1}"], [status]
    if org_id:
        conds.append(f"org_id=${len(params)+1}"); params.append(org_id)
    where = "WHERE " + " AND ".join(conds)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM review_queue {where} ORDER BY sla_deadline ASC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM review_queue {where}", *params)
    return {"total": total, "items": [dict(r) for r in rows]}


class ReviewDecisionRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    reviewer_id: str
    notes: str | None = None


@router.post("/review-queue/{item_id}/decide")
async def decide_review(
    item_id: str, req: ReviewDecisionRequest, deps=Depends(_deps),
) -> dict[str, Any]:
    """Approve or reject a queued review item."""
    from src.ledger.events import HumanReviewCompleted

    pool, store = deps
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(400, detail="decision must be 'approved' or 'rejected'")

    async with pool.acquire() as conn:
        item = await conn.fetchrow("SELECT * FROM review_queue WHERE id=$1", int(item_id))
        if not item:
            raise HTTPException(404, detail="Review item not found")
        await conn.execute(
            "UPDATE review_queue SET status=$1, reviewed_at=NOW(), reviewer_notes=$2 WHERE id=$3",
            req.decision, req.notes, int(item_id),
        )

    # Record event in the appropriate stream
    item_dict = dict(item)
    payload = item_dict.get("payload") or {}
    doc_id = payload.get("document_id") or payload.get("invoice_id", "unknown")
    stream_id = f"{item_dict['review_type'].split('_')[0]}-{item_dict['org_id']}-{doc_id}"
    version = await store.stream_version(stream_id)
    event = HumanReviewCompleted.create(
        org_id=item_dict["org_id"], review_id=str(item_id),
        decision=req.decision, reviewer_id=req.reviewer_id,
    )
    try:
        await store.append(stream_id, [event], version)
    except Exception:
        pass  # stream may not exist if item is orphaned

    return {"item_id": item_id, "decision": req.decision, "status": "updated"}


# ── Global event feed ──────────────────────────────────────────────────────────

@router.get("/events")
async def global_event_feed(
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    deps=Depends(_deps),
) -> dict[str, Any]:
    pool, _ = deps
    conds, params = [], []
    if event_type:
        conds.append(f"event_type=${len(params)+1}"); params.append(event_type)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT event_id, stream_id, event_type, recorded_at, global_position FROM events {where} ORDER BY global_position DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM events {where}", *params)
    return {"total": total, "events": [dict(r) for r in rows]}
