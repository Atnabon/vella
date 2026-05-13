"""TriageAgent — classifies US financial documents and produces DocumentProfiles.

Classifies: invoices, bank statements, tax forms (W-2, 1099, 1040),
receipts, purchase orders, payroll docs, financial statements.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from src.ingestion.models import (
    DocType,
    DocumentProfile,
    ExtractionStrategy,
    LayoutComplexity,
    OriginType,
)

logger = logging.getLogger(__name__)


# ── Document Type Classification ────────────────────────────────────────────

DOC_TYPE_KEYWORDS: dict[DocType, list[str]] = {
    DocType.INVOICE: [
        "invoice", "inv #", "invoice number", "bill to", "ship to",
        "amount due", "total due", "payment terms", "net 30", "net 60",
        "remit to", "subtotal", "sales tax",
    ],
    DocType.BANK_STATEMENT: [
        "bank statement", "account statement", "beginning balance",
        "ending balance", "deposits", "withdrawals", "account number",
        "routing number", "checking", "savings",
    ],
    DocType.TAX_FORM: [
        "form 1040", "schedule c", "form 941", "form 940",
        "estimated tax", "internal revenue service", "IRS",
        "taxpayer identification", "EIN", "social security",
    ],
    DocType.RECEIPT: [
        "receipt", "transaction receipt", "payment received",
        "thank you for your purchase", "card ending in",
    ],
    DocType.PURCHASE_ORDER: [
        "purchase order", "PO #", "PO number", "ordered by",
        "delivery date", "ship date", "unit price", "qty",
    ],
    DocType.W2: [
        "form w-2", "wage and tax statement", "w-2",
        "employer identification", "federal income tax withheld",
        "social security wages", "medicare wages",
    ],
    DocType.FORM_1099: [
        "form 1099", "1099-misc", "1099-nec", "1099-int", "1099-div",
        "nonemployee compensation", "miscellaneous income",
    ],
    DocType.PAYROLL: [
        "pay stub", "payroll", "gross pay", "net pay",
        "deductions", "federal withholding", "state withholding",
        "FICA", "401k", "health insurance",
    ],
    DocType.FINANCIAL_STATEMENT: [
        "balance sheet", "income statement", "profit and loss",
        "statement of cash flows", "retained earnings",
        "total assets", "total liabilities", "stockholders equity",
    ],
    DocType.CONTRACT: [
        "agreement", "contract", "terms and conditions",
        "hereby agree", "effective date", "termination",
        "governing law", "jurisdiction",
    ],
}

DOC_TYPE_FILENAME_PATTERNS: dict[DocType, list[str]] = {
    DocType.INVOICE: ["invoice", "inv", "bill"],
    DocType.BANK_STATEMENT: ["statement", "bank"],
    DocType.TAX_FORM: ["tax", "1040", "941", "940"],
    DocType.RECEIPT: ["receipt", "rcpt"],
    DocType.PURCHASE_ORDER: ["po", "purchase_order"],
    DocType.W2: ["w2", "w-2"],
    DocType.FORM_1099: ["1099"],
    DocType.PAYROLL: ["payroll", "paystub", "pay_stub"],
    DocType.FINANCIAL_STATEMENT: ["financial", "balance_sheet", "p&l", "pnl"],
    DocType.CONTRACT: ["contract", "agreement"],
}


def classify_doc_type(sample_text: str, filename: str) -> DocType:
    """Classify a US financial document by keyword scoring."""
    text_lower = sample_text.lower()
    filename_lower = filename.lower()
    scores: dict[DocType, int] = {dt: 0 for dt in DOC_TYPE_KEYWORDS}

    for dt, keywords in DOC_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                scores[dt] += 1

    for dt, patterns in DOC_TYPE_FILENAME_PATTERNS.items():
        for pat in patterns:
            if pat.lower() in filename_lower:
                scores[dt] += 3

    max_score = max(scores.values())
    if max_score == 0:
        return DocType.UNKNOWN
    return max(scores, key=scores.get)


# ── Triage Agent ────────────────────────────────────────────────────────────

TABLE_KEYWORDS = ["table", "total", "amount", "subtotal", "%", "sum", "qty", "quantity", "unit price"]


class TriageAgent:
    """Analyses a PDF and produces a DocumentProfile.

    Fast (< 2s for 200 pages), cheap (no LLM), deterministic.
    """

    SCANNED_TEXT_THRESHOLD: int = 50
    SCANNED_RATIO_THRESHOLD: float = 0.5
    MIXED_RATIO_LOWER: float = 0.1
    TABLE_KEYWORD_THRESHOLD: int = 3
    COMPLEX_TABLE_THRESHOLD: int = 5

    def profile_document(self, pdf_path: str | Path) -> DocumentProfile:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info("Triaging: %s", pdf_path.name)
        file_hash = _compute_file_hash(pdf_path)
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)

        origin_type, scanned_ratio = self._detect_origin_type(doc)
        layout_complexity, has_tables, has_images = self._assess_layout(doc)
        sample_text = self._extract_sample_text(doc)
        doc_type = classify_doc_type(sample_text, pdf_path.name)
        strategy, rationale, cost = self._select_strategy(
            origin_type, layout_complexity, doc_type, page_count, has_tables
        )
        doc.close()

        return DocumentProfile(
            document_id=_make_document_id(pdf_path.stem),
            filename=pdf_path.name,
            file_hash=file_hash,
            file_path=str(pdf_path),
            doc_type=doc_type,
            origin_type=origin_type,
            layout_complexity=layout_complexity,
            page_count=page_count,
            has_tables=has_tables,
            has_images=has_images,
            scanned_page_ratio=round(scanned_ratio, 3),
            recommended_strategy=strategy,
            strategy_rationale=rationale,
            estimated_cost_usd=cost,
        )

    def _detect_origin_type(self, doc: fitz.Document) -> tuple[OriginType, float]:
        scanned = 0
        indices = _sample_indices(len(doc), 20)
        for idx in indices:
            if len(doc[idx].get_text("text").strip()) < self.SCANNED_TEXT_THRESHOLD:
                scanned += 1
        ratio = scanned / len(indices) if indices else 0.0
        if ratio >= self.SCANNED_RATIO_THRESHOLD:
            return OriginType.SCANNED_IMAGE, ratio
        elif ratio >= self.MIXED_RATIO_LOWER:
            return OriginType.MIXED, ratio
        return OriginType.NATIVE_DIGITAL, ratio

    def _assess_layout(self, doc: fitz.Document) -> tuple[LayoutComplexity, bool, bool]:
        has_tables = False
        has_images = False
        table_count = 0
        multi_col = 0
        indices = _sample_indices(len(doc), 15)

        for idx in indices:
            page = doc[idx]
            if page.get_images(full=True):
                has_images = True
            text = page.get_text("text")
            kw_hits = sum(1 for kw in TABLE_KEYWORDS if kw.lower() in text.lower())
            if kw_hits >= self.TABLE_KEYWORD_THRESHOLD:
                has_tables = True
                table_count += 1
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            if blocks and "blocks" in blocks:
                x_pos = {round(b["bbox"][0] / 50) * 50 for b in blocks["blocks"] if b.get("type") == 0}
                if len(x_pos) > 2:
                    multi_col += 1

        mc_ratio = multi_col / len(indices) if indices else 0
        if table_count >= self.COMPLEX_TABLE_THRESHOLD or (mc_ratio > 0.3 and has_tables):
            return LayoutComplexity.COMPLEX, has_tables, has_images
        elif has_tables or mc_ratio > 0.2 or has_images:
            return LayoutComplexity.MODERATE, has_tables, has_images
        return LayoutComplexity.SIMPLE, has_tables, has_images

    def _extract_sample_text(self, doc: fitz.Document, max_chars: int = 5000) -> str:
        texts, total = [], 0
        for i in range(min(10, len(doc))):
            t = doc[i].get_text("text")
            texts.append(t)
            total += len(t)
            if total >= max_chars:
                break
        return "\n".join(texts)[:max_chars]

    def _select_strategy(
        self,
        origin: OriginType,
        complexity: LayoutComplexity,
        doc_type: DocType,
        page_count: int,
        has_tables: bool,
    ) -> tuple[ExtractionStrategy, str, float]:
        costs = {
            ExtractionStrategy.STRATEGY_A: 0.0001,
            ExtractionStrategy.STRATEGY_B: 0.001,
            ExtractionStrategy.STRATEGY_C: 0.01,
        }
        # Invoices and financial statements always benefit from layout-aware
        table_heavy = doc_type in (
            DocType.INVOICE, DocType.BANK_STATEMENT, DocType.FINANCIAL_STATEMENT,
            DocType.TAX_FORM, DocType.W2, DocType.FORM_1099,
        )
        if origin == OriginType.SCANNED_IMAGE:
            s = ExtractionStrategy.STRATEGY_C
            r = "Scanned — VLM extraction required."
        elif origin == OriginType.MIXED:
            s = ExtractionStrategy.STRATEGY_B
            r = "Mixed — layout-aware with per-page VLM escalation."
        elif complexity == LayoutComplexity.COMPLEX or (has_tables and table_heavy):
            s = ExtractionStrategy.STRATEGY_B
            r = f"{doc_type} with tables — layout-aware for numerical accuracy."
        else:
            s = ExtractionStrategy.STRATEGY_A
            r = "Simple native digital — fast text extraction."
        return s, r, round(costs[s] * page_count, 4)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_document_id(stem: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", stem.lower()).strip("_")


def _sample_indices(total: int, max_samples: int = 20) -> list[int]:
    if total <= max_samples:
        return list(range(total))
    step = total / max_samples
    return [int(i * step) for i in range(max_samples)]
