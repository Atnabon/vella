"""Bank reconciliation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.db import get_pool
from src.ledger.store import EventStore

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


async def _deps():
    pool = await get_pool()
    store = EventStore(pool)
    return pool, store


class ReconcileRequest(BaseModel):
    org_id: str
    account_name: str
    period_start: str  # YYYY-MM-DD
    period_end: str    # YYYY-MM-DD


@router.post("/run")
async def run_reconciliation(
    req: ReconcileRequest, deps=Depends(_deps),
) -> dict[str, Any]:
    """Run bank reconciliation for an account and period."""
    from src.agents.reconciliation_agent import ReconciliationAgent

    pool, store = deps
    agent = ReconciliationAgent(pool, store)
    try:
        result = await agent.reconcile(
            req.org_id, req.account_name, req.period_start, req.period_end,
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Reconciliation failed: {e}")
    return result


@router.get("/")
async def list_reconciliations(
    org_id: str | None = None,
    account_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    deps=Depends(_deps),
) -> dict[str, Any]:
    pool, _ = deps
    conds, params = [], []
    if org_id:
        conds.append(f"org_id=${len(params)+1}"); params.append(org_id)
    if account_name:
        conds.append(f"account_name=${len(params)+1}"); params.append(account_name)
    if status:
        conds.append(f"status=${len(params)+1}"); params.append(status)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM reconciliations {where} ORDER BY completed_at DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM reconciliations {where}", *params)
    return {"total": total, "reconciliations": [dict(r) for r in rows]}


class UploadTransactionRequest(BaseModel):
    org_id: str
    account_name: str
    transactions: list[dict[str, Any]]  # [{txn_date, description, amount, txn_type}]


@router.post("/transactions/upload")
async def upload_transactions(
    req: UploadTransactionRequest, deps=Depends(_deps),
) -> dict[str, Any]:
    """Bulk-upload bank transactions (CSV import / Plaid webhook payload)."""
    pool, _ = deps
    inserted = 0
    async with pool.acquire() as conn:
        for txn in req.transactions:
            await conn.execute(
                """INSERT INTO bank_transactions
                   (org_id, account_name, txn_date, description, amount, txn_type, source)
                   VALUES ($1,$2,$3,$4,$5,$6,'manual')
                   ON CONFLICT DO NOTHING""",
                req.org_id, req.account_name,
                txn["txn_date"], txn.get("description", ""),
                float(txn["amount"]), txn.get("txn_type", "debit"),
            )
            inserted += 1
    return {"inserted": inserted, "account_name": req.account_name}


@router.get("/transactions")
async def list_transactions(
    org_id: str | None = None,
    account_name: str | None = None,
    reconciled: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    deps=Depends(_deps),
) -> dict[str, Any]:
    pool, _ = deps
    conds, params = [], []
    if org_id:
        conds.append(f"org_id=${len(params)+1}"); params.append(org_id)
    if account_name:
        conds.append(f"account_name=${len(params)+1}"); params.append(account_name)
    if reconciled is not None:
        conds.append(f"reconciled=${len(params)+1}"); params.append(reconciled)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM bank_transactions {where} ORDER BY txn_date DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM bank_transactions {where}", *params)
    return {"total": total, "transactions": [dict(r) for r in rows]}
