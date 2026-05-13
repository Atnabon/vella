"""Tax estimation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.db import get_pool
from src.ledger.store import EventStore

router = APIRouter(prefix="/tax", tags=["tax"])


async def _deps():
    pool = await get_pool()
    store = EventStore(pool)
    return pool, store


class TaxEstimateRequest(BaseModel):
    org_id: str
    tax_year: int = 2026
    quarter: int | None = None  # 1-4, or None for annual
    entity_type: str = "llc"    # sole_prop | llc | s_corp | c_corp
    state: str = "default"
    filing_status: str = "single"


@router.post("/estimate")
async def compute_tax_estimate(
    req: TaxEstimateRequest, deps=Depends(_deps),
) -> dict[str, Any]:
    """Compute quarterly or annual tax estimate from booked invoices."""
    from src.agents.tax_agent import TaxPrepAgent

    pool, store = deps
    agent = TaxPrepAgent(pool, store)
    try:
        result = await agent.compute_estimate(
            org_id=req.org_id,
            tax_year=req.tax_year,
            quarter=req.quarter,
            entity_type=req.entity_type,
            state=req.state,
            filing_status=req.filing_status,
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Tax estimation failed: {e}")
    return result


@router.get("/estimates")
async def list_tax_estimates(
    org_id: str | None = None,
    tax_year: int | None = None,
    limit: int = 20,
    offset: int = 0,
    deps=Depends(_deps),
) -> dict[str, Any]:
    pool, _ = deps
    conds, params = [], []
    if org_id:
        conds.append(f"org_id=${len(params)+1}"); params.append(org_id)
    if tax_year:
        conds.append(f"tax_year=${len(params)+1}"); params.append(tax_year)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM tax_estimates {where} ORDER BY computed_at DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tax_estimates {where}", *params)
    return {"total": total, "estimates": [dict(r) for r in rows]}


@router.get("/estimates/{org_id}/{tax_year}")
async def get_annual_summary(
    org_id: str, tax_year: int, deps=Depends(_deps),
) -> dict[str, Any]:
    """Return all quarterly estimates plus annual for a given year."""
    pool, _ = deps
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tax_estimates WHERE org_id=$1 AND tax_year=$2 ORDER BY quarter NULLS LAST",
            org_id, tax_year,
        )
    if not rows:
        raise HTTPException(404, detail="No tax estimates found for this year")
    estimates = [dict(r) for r in rows]
    total_tax = sum(e["total_estimated_tax"] for e in estimates if e["quarter"] is not None)
    return {
        "org_id": org_id,
        "tax_year": tax_year,
        "estimates": estimates,
        "total_quarterly_tax": round(total_tax, 2),
    }
