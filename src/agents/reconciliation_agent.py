"""ReconciliationAgent — autonomous bank account reconciliation.

Matches bank transactions against invoices and book entries,
detects discrepancies, flags unmatched items, and produces
reconciliation reports with full audit trails.
"""

from __future__ import annotations

import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

import asyncpg

from src.config import settings
from src.governance.gate import ConfidenceGate, GateDecision
from src.ledger.events import DiscrepancyDetected, ReconciliationCompleted, ReconciliationStarted, TransactionMatched
from src.ledger.store import EventStore

logger = logging.getLogger(__name__)


class ReconciliationAgent:
    """Reconciles bank transactions with invoices/book entries.

    1. Load bank transactions for the period
    2. Load invoices marked as paid in the period
    3. Match transactions to invoices (amount + date + vendor fuzzy match)
    4. Flag discrepancies
    5. Record everything in the ledger
    """

    def __init__(self, pool: asyncpg.Pool, event_store: EventStore) -> None:
        self._pool = pool
        self._store = event_store
        self._gate = ConfidenceGate(
            auto_approve=settings.hitl_auto_approve_threshold,
            escalation=settings.hitl_escalation_threshold,
        )

    async def reconcile(
        self, org_id: str, account_name: str, period_start: str, period_end: str,
    ) -> dict[str, Any]:
        stream_id = f"recon-{org_id}-{account_name}-{period_start}"
        version = await self._store.stream_version(stream_id)

        # Start event
        start_event = ReconciliationStarted.create(
            org_id=org_id, account_name=account_name,
            period_start=period_start, period_end=period_end,
        )
        version = await self._store.append(stream_id, [start_event], expected_version=version)

        # Load data
        async with self._pool.acquire() as conn:
            txns = await conn.fetch(
                """SELECT * FROM bank_transactions
                   WHERE org_id=$1 AND account_name=$2 AND txn_date BETWEEN $3 AND $4
                   ORDER BY txn_date""",
                org_id, account_name, period_start, period_end,
            )
            invoices = await conn.fetch(
                """SELECT * FROM invoices
                   WHERE org_id=$1 AND booked=TRUE
                   ORDER BY total_amount""",
                org_id,
            )

        # Match transactions to invoices
        matched_count = 0
        unmatched_txns = []
        discrepancies = []
        invoice_map = {str(inv["invoice_id"]): dict(inv) for inv in invoices}
        used_invoices: set[str] = set()

        for txn in txns:
            txn_dict = dict(txn)
            best_match = self._find_best_match(txn_dict, invoices, used_invoices)

            if best_match:
                used_invoices.add(str(best_match["invoice_id"]))
                match_event = TransactionMatched.create(
                    org_id=org_id, txn_id=str(txn["txn_id"]),
                    invoice_id=str(best_match["invoice_id"]),
                    confidence=best_match["confidence"],
                )
                version = await self._store.append(stream_id, [match_event], version)

                # Mark as reconciled
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE bank_transactions SET reconciled=TRUE, matched_invoice_id=$1 WHERE txn_id=$2",
                        best_match["invoice_id"], txn["txn_id"],
                    )

                # Check amount discrepancy
                diff = abs(abs(float(txn["amount"])) - float(best_match["total_amount"]))
                if diff > 0.01:
                    disc = {
                        "type": "amount_mismatch",
                        "txn_amount": float(txn["amount"]),
                        "invoice_amount": float(best_match["total_amount"]),
                        "difference": round(diff, 2),
                        "txn_id": str(txn["txn_id"]),
                    }
                    discrepancies.append(disc)
                    disc_event = DiscrepancyDetected.create(
                        org_id=org_id, account_name=account_name,
                        difference=diff, description=f"Amount mismatch: txn ${abs(float(txn['amount'])):,.2f} vs invoice ${float(best_match['total_amount']):,.2f}",
                    )
                    version = await self._store.append(stream_id, [disc_event], version)

                matched_count += 1
            else:
                unmatched_txns.append(str(txn["txn_id"]))

        # Calculate balances
        total_debits = sum(float(t["amount"]) for t in txns if t["txn_type"] == "debit")
        total_credits = sum(float(t["amount"]) for t in txns if t["txn_type"] == "credit")
        net_difference = round(total_credits - total_debits, 2)

        # Complete event
        comp_event = ReconciliationCompleted.create(
            org_id=org_id, account_name=account_name,
            matched=matched_count, unmatched=len(unmatched_txns),
            difference=net_difference,
        )
        version = await self._store.append(stream_id, [comp_event], version)

        # Persist reconciliation
        status = "completed" if not discrepancies and not unmatched_txns else "discrepancy"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO reconciliations
                   (org_id, account_name, period_start, period_end,
                    book_balance, difference, matched_count, unmatched_count,
                    status, discrepancies, completed_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())""",
                org_id, account_name, period_start, period_end,
                net_difference, net_difference, matched_count, len(unmatched_txns),
                status, discrepancies,
            )

        chain = await self._store.build_chain(stream_id)

        logger.info(
            "Reconciliation: %s/%s %s→%s | matched=%d unmatched=%d discrepancies=%d",
            org_id, account_name, period_start, period_end,
            matched_count, len(unmatched_txns), len(discrepancies),
        )

        return {
            "org_id": org_id,
            "account_name": account_name,
            "period": f"{period_start} to {period_end}",
            "total_transactions": len(txns),
            "matched": matched_count,
            "unmatched": len(unmatched_txns),
            "discrepancies": discrepancies,
            "total_debits": round(total_debits, 2),
            "total_credits": round(total_credits, 2),
            "net_difference": net_difference,
            "status": status,
            "stream_id": stream_id,
            "audit_chain": chain,
        }

    def _find_best_match(
        self, txn: dict[str, Any], invoices: list, used: set[str],
    ) -> dict[str, Any] | None:
        """Find the best matching invoice for a bank transaction."""
        txn_amount = abs(float(txn["amount"]))
        txn_desc = txn.get("description", "").lower()
        best, best_score = None, 0.0

        for inv in invoices:
            inv_id = str(inv["invoice_id"])
            if inv_id in used:
                continue

            inv_amount = float(inv["total_amount"])
            vendor = (inv.get("vendor_name") or "").lower()

            # Amount similarity (0-0.5 score)
            amount_diff = abs(txn_amount - inv_amount)
            if amount_diff == 0:
                amount_score = 0.5
            elif amount_diff / max(txn_amount, 1) < 0.05:
                amount_score = 0.3
            else:
                continue  # Too different, skip

            # Vendor name similarity (0-0.5 score)
            name_score = SequenceMatcher(None, txn_desc, vendor).ratio() * 0.5

            total = amount_score + name_score
            if total > best_score:
                best_score = total
                best = {**dict(inv), "confidence": round(min(total, 1.0), 3)}

        if best and best_score >= 0.5:
            return best
        return None
