"""Document upload and query endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.config import settings
from src.db import get_pool
from src.ingestion.pipeline import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])

async def _pool():
    return await get_pool()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...), org_id: str | None = None, pool=Depends(_pool),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, detail="Only PDF files supported")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe = f"{uuid.uuid4().hex}_{file.filename.replace(' ', '_')}"
    path = upload_dir / safe

    async with aiofiles.open(path, "wb") as f:
        await f.write(await file.read())

    try:
        result = await ingest_document(path, pool, org_id=org_id)
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(500, detail=f"Ingestion failed: {e}")

    return {
        "document_id": result.profile.document_id,
        "filename": result.profile.filename,
        "doc_type": result.profile.doc_type,
        "pages": result.profile.page_count,
        "strategy_used": result.metrics.strategy_used,
        "ldu_count": result.metrics.ldu_count,
        "confidence": result.metrics.average_confidence,
        "cost_usd": result.metrics.total_cost_usd,
        "needs_human_review": result.ledger_entry.needs_human_review,
        "status": "review" if result.ledger_entry.needs_human_review else "extracted",
    }


@router.get("/{document_id}")
async def get_document(document_id: str, pool=Depends(_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM documents WHERE document_id=$1", document_id)
    if not row:
        raise HTTPException(404, detail="Document not found")
    return dict(row)


@router.get("/")
async def list_documents(
    status: str | None = None, doc_type: str | None = None,
    org_id: str | None = None, limit: int = 50, offset: int = 0, pool=Depends(_pool),
) -> dict[str, Any]:
    conds, params = [], []
    if status:
        conds.append(f"status=${len(params)+1}"); params.append(status)
    if doc_type:
        conds.append(f"doc_type=${len(params)+1}"); params.append(doc_type)
    if org_id:
        conds.append(f"org_id=${len(params)+1}"); params.append(org_id)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM documents {where} ORDER BY uploaded_at DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM documents {where}", *params)
    return {"total": total, "documents": [dict(r) for r in rows]}
