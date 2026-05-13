"""ExtractionRouter — confidence-gated strategy escalation for US financial docs.

Strategies:
  A (fast_text): PyMuPDF block extraction — $0.0001/page
  B (layout_aware): pdfplumber tables + fitz text — $0.001/page
  C (vision_model): Claude Haiku vision — $0.01/page

Automatically escalates A→B→C when confidence falls below threshold.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

from src.ingestion.models import (
    DocumentProfile,
    ExtractionMetrics,
    ExtractionStrategy,
    ExtractedDocument,
    LDU,
    LedgerEntry,
    Provenance,
)

logger = logging.getLogger(__name__)


def _extract_fast_text(profile: DocumentProfile, pdf_path: Path) -> list[LDU]:
    doc = fitz.open(str(pdf_path))
    ldus: list[LDU] = []
    for page_num in range(len(doc)):
        blocks = doc[page_num].get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:
                continue
            text = " ".join(
                span["text"] for line in block.get("lines", []) for span in line.get("spans", [])
            ).strip()
            if not text:
                continue
            bbox = block.get("bbox", [0, 0, 0, 0])
            ldus.append(LDU(
                ldu_id=str(uuid.uuid4()),
                ldu_type="text",
                content=text,
                confidence=0.92,
                provenance=Provenance(
                    document_id=profile.document_id, filename=profile.filename,
                    page_number=page_num + 1, bounding_box=list(bbox),
                    content_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
                    extraction_strategy="fast_text", confidence=0.92,
                ),
            ))
    doc.close()
    return ldus


def _extract_layout_aware(profile: DocumentProfile, pdf_path: Path) -> list[LDU]:
    ldus: list[LDU] = []
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed — falling back to fast_text")
        return _extract_fast_text(profile, pdf_path)

    doc_fitz = fitz.open(str(pdf_path))
    with pdfplumber.open(str(pdf_path)) as doc_p:
        for page_num, (pp, pf) in enumerate(zip(doc_p.pages, doc_fitz)):
            # Tables
            tables = pp.extract_tables()
            table_bboxes: list[list[float]] = []
            for table in tables:
                if not table:
                    continue
                rows = [" | ".join(str(c) for c in row if c) for row in table]
                table_text = "\n".join(rows)
                ch = hashlib.sha256(table_text.encode()).hexdigest()[:16]
                bbox = list(pp.bbox)
                table_bboxes.append(bbox)
                ldus.append(LDU(
                    ldu_id=str(uuid.uuid4()), ldu_type="table",
                    content=table_text, confidence=0.88,
                    provenance=Provenance(
                        document_id=profile.document_id, filename=profile.filename,
                        page_number=page_num + 1, bounding_box=bbox,
                        content_hash=ch, extraction_strategy="layout_aware", confidence=0.88,
                    ),
                ))
            # Non-table text
            blocks = pf.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:
                    continue
                text = " ".join(
                    span["text"] for line in block.get("lines", []) for span in line.get("spans", [])
                ).strip()
                if not text:
                    continue
                bbox = list(block.get("bbox", [0, 0, 0, 0]))
                if any(
                    bbox[0] < r[2] and bbox[2] > r[0] and bbox[1] < r[3] and bbox[3] > r[1]
                    for r in table_bboxes
                ):
                    continue
                ldus.append(LDU(
                    ldu_id=str(uuid.uuid4()), ldu_type="text",
                    content=text, confidence=0.90,
                    provenance=Provenance(
                        document_id=profile.document_id, filename=profile.filename,
                        page_number=page_num + 1, bounding_box=bbox,
                        content_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
                        extraction_strategy="layout_aware", confidence=0.90,
                    ),
                ))
    doc_fitz.close()
    return ldus


def _extract_vision(profile: DocumentProfile, pdf_path: Path) -> list[LDU]:
    from src.config import settings
    if not settings.anthropic_api_key:
        logger.warning("No ANTHROPIC_API_KEY — falling back to fast_text")
        return _extract_fast_text(profile, pdf_path)
    try:
        import anthropic
        import base64
    except ImportError:
        return _extract_fast_text(profile, pdf_path)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    doc = fitz.open(str(pdf_path))
    ldus: list[LDU] = []
    for page_num in range(len(doc)):
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = doc[page_num].get_pixmap(matrix=mat)
        img_b64 = base64.standard_b64encode(pix.tobytes("png")).decode()
        prompt = (
            "Extract all text, tables, amounts, dates, and vendor names from this US financial document page. "
            "For tables, use pipe-separated format. Include every number exactly as shown. Output only extracted content."
        )
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=2000,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                    {"type": "text", "text": prompt},
                ]}],
            )
            text = resp.content[0].text.strip()
        except Exception as e:
            logger.error("VLM failed page %d: %s", page_num + 1, e)
            text = doc[page_num].get_text("text").strip()
        if text:
            ldus.append(LDU(
                ldu_id=str(uuid.uuid4()), ldu_type="text",
                content=text, confidence=0.82,
                provenance=Provenance(
                    document_id=profile.document_id, filename=profile.filename,
                    page_number=page_num + 1,
                    content_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
                    extraction_strategy="vision_model", confidence=0.82,
                ),
            ))
    doc.close()
    return ldus


STRATEGY_FN = {
    ExtractionStrategy.STRATEGY_A: _extract_fast_text,
    ExtractionStrategy.STRATEGY_B: _extract_layout_aware,
    ExtractionStrategy.STRATEGY_C: _extract_vision,
}
STRATEGY_COST = {
    ExtractionStrategy.STRATEGY_A: 0.0001,
    ExtractionStrategy.STRATEGY_B: 0.001,
    ExtractionStrategy.STRATEGY_C: 0.01,
}
ESCALATION_CHAIN = [ExtractionStrategy.STRATEGY_A, ExtractionStrategy.STRATEGY_B, ExtractionStrategy.STRATEGY_C]


class ExtractionRouter:
    def __init__(self, confidence_threshold: float = 0.70, max_cost_usd: float = 5.0) -> None:
        self.confidence_threshold = confidence_threshold
        self.max_cost_usd = max_cost_usd

    def extract(self, profile: DocumentProfile, pdf_path: str | Path) -> ExtractedDocument:
        pdf_path = Path(pdf_path)
        start = time.time()
        strategy = ExtractionStrategy(profile.recommended_strategy)
        ldus = STRATEGY_FN[strategy](profile, pdf_path)
        avg_conf = _avg_conf(ldus)
        total_cost = STRATEGY_COST[strategy] * profile.page_count
        escalations = 0
        errors: list[str] = []

        idx = ESCALATION_CHAIN.index(strategy)
        while avg_conf < self.confidence_threshold and idx < len(ESCALATION_CHAIN) - 1:
            nxt = ESCALATION_CHAIN[idx + 1]
            add_cost = STRATEGY_COST[nxt] * profile.page_count
            if total_cost + add_cost > self.max_cost_usd:
                errors.append(f"Cost budget exceeded at confidence {avg_conf:.3f}")
                break
            logger.info("Escalating %s → %s (conf=%.3f)", strategy.value, nxt.value, avg_conf)
            try:
                new_ldus = STRATEGY_FN[nxt](profile, pdf_path)
                new_conf = _avg_conf(new_ldus)
                if new_conf > avg_conf:
                    ldus, avg_conf, strategy = new_ldus, new_conf, nxt
                    total_cost += add_cost
                    escalations += 1
                else:
                    break
            except Exception as e:
                errors.append(f"Escalation to {nxt.value} failed: {e}")
                break
            idx += 1

        needs_review = avg_conf < self.confidence_threshold
        if needs_review:
            errors.append(f"Final confidence {avg_conf:.3f} < threshold. Flagged for review.")

        elapsed = round(time.time() - start, 2)
        return ExtractedDocument(
            profile=profile,
            ldus=ldus,
            metrics=ExtractionMetrics(
                extraction_time_seconds=elapsed, strategy_used=strategy.value,
                escalation_count=escalations, total_cost_usd=round(total_cost, 6),
                average_confidence=round(avg_conf, 4),
                low_confidence_count=sum(1 for l in ldus if l.confidence < 0.60),
            ),
            ledger_entry=LedgerEntry(
                document_id=profile.document_id, filename=profile.filename,
                strategy_selected=strategy.value, confidence_score=round(avg_conf, 4),
                cost_estimate_usd=round(total_cost, 6), ldu_count=len(ldus),
                table_count=sum(1 for l in ldus if l.ldu_type == "table"),
                escalated=escalations > 0, errors=errors, needs_human_review=needs_review,
            ),
        )


def _avg_conf(ldus: list[LDU]) -> float:
    return sum(l.confidence for l in ldus) / len(ldus) if ldus else 0.0
