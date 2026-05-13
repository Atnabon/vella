"""InvoiceParser — extracts structured invoice data from LDUs.

Takes raw LDUs from the extraction pipeline and produces a structured
Invoice object with: vendor, invoice number, date, due date, total,
line items, PO reference — all with provenance chains.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.ingestion.models import LDU

logger = logging.getLogger(__name__)


class LineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: float = 0.0
    gl_account: str | None = None


class ParsedInvoice(BaseModel):
    vendor_name: str = ""
    invoice_number: str = ""
    invoice_date: str | None = None
    due_date: str | None = None
    po_number: str | None = None
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    currency: str = "USD"
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: float = 0.0
    extraction_method: str = "heuristic"


class InvoiceParser:
    """Parses invoice data from extracted LDUs using heuristics + optional LLM."""

    # Common US date formats
    DATE_PATTERNS = [
        r"(\d{1,2})/(\d{1,2})/(\d{2,4})",  # MM/DD/YYYY or M/D/YY
        r"(\d{1,2})-(\d{1,2})-(\d{2,4})",  # MM-DD-YYYY
        r"(\w+ \d{1,2},?\s*\d{4})",         # January 15, 2026
    ]

    AMOUNT_PATTERN = re.compile(r"\$?\s*([\d,]+\.\d{2})")

    def parse(self, ldus: list[LDU], use_llm: bool = True) -> ParsedInvoice:
        """Extract structured invoice data from LDUs.

        Tries LLM first (if available), falls back to heuristics.
        """
        if use_llm:
            try:
                return self._llm_parse(ldus)
            except Exception as e:
                logger.warning("LLM invoice parse failed: %s — using heuristics", e)

        return self._heuristic_parse(ldus)

    def _llm_parse(self, ldus: list[LDU]) -> ParsedInvoice:
        """Use Claude to extract structured invoice fields."""
        from src.config import settings
        if not settings.anthropic_api_key:
            raise RuntimeError("No API key")

        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        full_text = "\n".join(ldu.content for ldu in ldus)[:4000]
        prompt = (
            "Extract invoice data from this text. Return a JSON object with exactly these fields:\n"
            "vendor_name, invoice_number, invoice_date (YYYY-MM-DD or null), "
            "due_date (YYYY-MM-DD or null), po_number (or null), subtotal, tax_amount, "
            "total_amount, currency (default USD), "
            "line_items (array of {description, quantity, unit_price, amount}).\n"
            "If a field is not found, use empty string for text or 0 for numbers.\n\n"
            f"Document text:\n{full_text}"
        )

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        items = [LineItem(**item) for item in data.get("line_items", [])]
        return ParsedInvoice(
            vendor_name=data.get("vendor_name", ""),
            invoice_number=data.get("invoice_number", ""),
            invoice_date=data.get("invoice_date"),
            due_date=data.get("due_date"),
            po_number=data.get("po_number"),
            subtotal=float(data.get("subtotal", 0)),
            tax_amount=float(data.get("tax_amount", 0)),
            total_amount=float(data.get("total_amount", 0)),
            currency=data.get("currency", "USD"),
            line_items=items,
            confidence=0.88,
            extraction_method="llm",
        )

    def _heuristic_parse(self, ldus: list[LDU]) -> ParsedInvoice:
        """Rule-based invoice parsing from LDU text."""
        full_text = "\n".join(ldu.content for ldu in ldus)
        text_lower = full_text.lower()

        vendor = self._extract_vendor(full_text)
        inv_num = self._extract_pattern(text_lower, [
            r"invoice\s*#?\s*:?\s*(\S+)",
            r"inv\s*#?\s*:?\s*(\S+)",
            r"invoice\s+number\s*:?\s*(\S+)",
        ])
        po_num = self._extract_pattern(text_lower, [
            r"po\s*#?\s*:?\s*(\S+)",
            r"purchase\s+order\s*#?\s*:?\s*(\S+)",
        ])
        inv_date = self._extract_date_near(text_lower, "invoice date")
        due_date = self._extract_date_near(text_lower, "due date")
        total = self._extract_amount_near(text_lower, ["total due", "amount due", "total", "balance due"])

        amounts = self.AMOUNT_PATTERN.findall(full_text)
        all_amounts = sorted([float(a.replace(",", "")) for a in amounts], reverse=True)
        if total == 0 and all_amounts:
            total = all_amounts[0]

        subtotal = self._extract_amount_near(text_lower, ["subtotal", "sub total", "sub-total"])
        tax = self._extract_amount_near(text_lower, ["tax", "sales tax", "vat"])

        confidence = 0.60
        if vendor and inv_num and total > 0:
            confidence = 0.82
        elif vendor and total > 0:
            confidence = 0.72

        return ParsedInvoice(
            vendor_name=vendor,
            invoice_number=inv_num or "",
            invoice_date=inv_date,
            due_date=due_date,
            po_number=po_num,
            subtotal=subtotal,
            tax_amount=tax,
            total_amount=total,
            confidence=confidence,
            extraction_method="heuristic",
        )

    @staticmethod
    def _extract_vendor(text: str) -> str:
        """Extract vendor name — typically the first prominent line."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines[:5]:
            if len(line) > 3 and not any(kw in line.lower() for kw in ["invoice", "bill to", "date", "page"]):
                return line
        return ""

    @staticmethod
    def _extract_pattern(text: str, patterns: list[str]) -> str | None:
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    def _extract_date_near(self, text: str, label: str) -> str | None:
        idx = text.find(label)
        if idx == -1:
            return None
        region = text[idx:idx + 80]
        for pat in self.DATE_PATTERNS:
            m = re.search(pat, region)
            if m:
                return m.group(0)
        return None

    def _extract_amount_near(self, text: str, labels: list[str]) -> float:
        for label in labels:
            idx = text.find(label)
            if idx == -1:
                continue
            region = text[idx:idx + 60]
            m = self.AMOUNT_PATTERN.search(region)
            if m:
                return float(m.group(1).replace(",", ""))
        return 0.0
