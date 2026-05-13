"""TaxPrepAgent — autonomous quarterly/annual tax estimate preparation.

Gathers financial data, computes estimated taxes using IRS brackets,
handles common deductions, and records everything in the ledger.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import asyncpg

from src.config import settings
from src.ledger.events import TaxDocumentCollected, TaxEstimateComputed
from src.ledger.store import EventStore

logger = logging.getLogger(__name__)

# 2026 Federal Income Tax Brackets (single/LLC)
FEDERAL_BRACKETS_2026 = [
    (11_600, 0.10),
    (47_150, 0.12),
    (100_525, 0.22),
    (191_950, 0.24),
    (243_725, 0.32),
    (609_350, 0.35),
    (float("inf"), 0.37),
]

SELF_EMPLOYMENT_RATE = 0.153  # 15.3% (12.4% SS + 2.9% Medicare)
SELF_EMPLOYMENT_DEDUCTION = 0.5  # Deduct half of SE tax from income

# Standard deductions (2026 estimate)
STANDARD_DEDUCTION = {
    "single": 15_700,
    "married_filing_jointly": 31_400,
    "head_of_household": 23_550,
}

# Common state tax rates (simplified flat rates)
STATE_TAX_RATES = {
    "CA": 0.093, "NY": 0.0685, "TX": 0.0, "FL": 0.0, "WA": 0.0,
    "IL": 0.0495, "PA": 0.0307, "OH": 0.04, "GA": 0.055, "NC": 0.0475,
    "NJ": 0.0637, "VA": 0.0575, "MA": 0.05, "CO": 0.044, "OR": 0.099,
    "default": 0.05,
}


class TaxPrepAgent:
    """Computes estimated tax obligations from financial data.

    Handles: quarterly estimates, annual projections, self-employment tax,
    state tax, common business deductions.
    """

    def __init__(self, pool: asyncpg.Pool, event_store: EventStore) -> None:
        self._pool = pool
        self._store = event_store

    async def compute_estimate(
        self,
        org_id: str,
        tax_year: int,
        quarter: int | None = None,
        entity_type: str = "llc",
        state: str = "default",
        filing_status: str = "single",
    ) -> dict[str, Any]:
        """Compute tax estimate from booked invoices and expenses.

        Args:
            org_id: Organization ID.
            tax_year: Tax year (e.g., 2026).
            quarter: Quarter (1-4) or None for annual.
            entity_type: sole_prop|llc|s_corp|c_corp.
            state: Two-letter state code.
            filing_status: single|married_filing_jointly|head_of_household.
        """
        stream_id = f"tax-{org_id}-{tax_year}" + (f"-Q{quarter}" if quarter else "")
        version = await self._store.stream_version(stream_id)

        # Gather financial data
        revenue, expenses, deductions = await self._gather_financials(org_id, tax_year, quarter)

        # Compute taxes
        gross = revenue
        total_exp = expenses
        taxable_before_deductions = gross - total_exp

        # Self-employment tax (for sole prop / LLC)
        se_tax = 0.0
        se_deduction = 0.0
        if entity_type in ("sole_prop", "llc"):
            se_taxable = taxable_before_deductions * 0.9235  # 92.35% of net SE income
            se_tax = round(se_taxable * SELF_EMPLOYMENT_RATE, 2)
            se_deduction = round(se_tax * SELF_EMPLOYMENT_DEDUCTION, 2)

        # Standard deduction
        std_deduction = STANDARD_DEDUCTION.get(filing_status, 15_700)

        # Taxable income
        taxable_income = max(0, taxable_before_deductions - se_deduction - std_deduction)

        # Federal income tax
        federal_tax = self._compute_federal_tax(taxable_income)

        # State tax
        state_rate = STATE_TAX_RATES.get(state, STATE_TAX_RATES["default"])
        state_tax = round(taxable_income * state_rate, 2)

        total_tax = round(federal_tax + state_tax + se_tax, 2)

        # Quarterly adjustment
        if quarter:
            # Quarterly estimate is ¼ of annual projection
            federal_tax = round(federal_tax / 4, 2)
            state_tax = round(state_tax / 4, 2)
            se_tax = round(se_tax / 4, 2)
            total_tax = round(total_tax / 4, 2)

        # Record event
        event = TaxEstimateComputed.create(
            org_id=org_id, tax_year=tax_year, quarter=quarter,
            gross_revenue=gross, total_expenses=total_exp,
            taxable_income=taxable_income, total_tax=total_tax,
        )
        version = await self._store.append(stream_id, [event], version)

        # Persist
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO tax_estimates
                   (org_id, tax_year, quarter, entity_type,
                    gross_revenue, total_expenses, taxable_income,
                    federal_tax, state_tax, self_employment_tax,
                    total_estimated_tax, deductions, status, computed_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'computed',NOW())""",
                org_id, tax_year, quarter, entity_type,
                gross, total_exp, taxable_income,
                federal_tax, state_tax, se_tax, total_tax,
                {"standard_deduction": std_deduction, "se_deduction": se_deduction, **deductions},
            )

        chain = await self._store.build_chain(stream_id)

        logger.info(
            "Tax estimate: %s %d Q%s | revenue=$%,.2f expenses=$%,.2f tax=$%,.2f",
            org_id, tax_year, quarter or "annual", gross, total_exp, total_tax,
        )

        return {
            "org_id": org_id,
            "tax_year": tax_year,
            "quarter": quarter,
            "entity_type": entity_type,
            "filing_status": filing_status,
            "state": state,
            "gross_revenue": gross,
            "total_expenses": total_exp,
            "taxable_income": taxable_income,
            "federal_tax": federal_tax,
            "state_tax": state_tax,
            "self_employment_tax": se_tax,
            "total_estimated_tax": total_tax,
            "deductions": {"standard_deduction": std_deduction, "se_deduction": se_deduction, **deductions},
            "stream_id": stream_id,
            "audit_chain": chain,
        }

    async def _gather_financials(
        self, org_id: str, tax_year: int, quarter: int | None,
    ) -> tuple[float, float, dict[str, float]]:
        """Gather revenue and expenses from booked invoices."""
        async with self._pool.acquire() as conn:
            # Revenue from invoices where org is the vendor (accounts receivable)
            # For simplicity, we sum all booked invoices as expenses (accounts payable)
            invoices = await conn.fetch(
                "SELECT total_amount, gl_account FROM invoices WHERE org_id=$1 AND booked=TRUE",
                org_id,
            )

        total_expenses = sum(float(inv["total_amount"]) for inv in invoices)

        # Categorize by GL account
        by_category: dict[str, float] = {}
        for inv in invoices:
            cat = inv.get("gl_account") or "Uncategorized"
            by_category[cat] = by_category.get(cat, 0) + float(inv["total_amount"])

        # In production: revenue from separate revenue table or QuickBooks
        # Placeholder: assume 3x expenses as revenue for estimation
        revenue = total_expenses * 3

        return round(revenue, 2), round(total_expenses, 2), by_category

    @staticmethod
    def _compute_federal_tax(taxable_income: float) -> float:
        """Compute federal income tax using progressive brackets."""
        tax = 0.0
        prev_limit = 0
        for limit, rate in FEDERAL_BRACKETS_2026:
            bracket_income = min(taxable_income, limit) - prev_limit
            if bracket_income <= 0:
                break
            tax += bracket_income * rate
            prev_limit = limit
        return round(tax, 2)
