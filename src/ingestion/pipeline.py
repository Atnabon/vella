"""Document ingestion pipeline — triage → extract → classify → persist."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg

from src.config import settings
from src.ingestion.extractor import ExtractionRouter
from src.ingestion.models import ExtractedDocument
from src.ingestion.triage import TriageAgent

logger = logging.getLogger(__name__)

_triage = TriageAgent()
_router = ExtractionRouter(
    confidence_threshold=settings.confidence_escalation_threshold,
    max_cost_usd=settings.max_cost_per_document_usd,
)


async def ingest_document(
    pdf_path: str | Path,
    pool: asyncpg.Pool,
    org_id: str | None = None,
) -> ExtractedDocument:
    pdf_path = Path(pdf_path)

    logger.info("Pipeline: triaging %s", pdf_path.name)
    profile = _triage.profile_document(pdf_path)

    logger.info("Pipeline: extracting %s (strategy=%s, type=%s)",
                pdf_path.name, profile.recommended_strategy, profile.doc_type)
    result = _router.extract(profile, pdf_path)

    await _persist_document(result, pool, org_id)

    logger.info(
        "Pipeline complete: %s | type=%s | LDUs=%d | conf=%.3f | cost=$%.6f%s",
        pdf_path.name, profile.doc_type, result.metrics.ldu_count,
        result.metrics.average_confidence, result.metrics.total_cost_usd,
        " [REVIEW]" if result.ledger_entry.needs_human_review else "",
    )
    return result


async def _persist_document(
    result: ExtractedDocument,
    pool: asyncpg.Pool,
    org_id: str | None,
) -> None:
    p = result.profile
    le = result.ledger_entry
    status = "review" if le.needs_human_review else "extracted"

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO documents (
                document_id, filename, file_hash, file_path, doc_type,
                origin_type, layout_complexity, page_count, language, has_tables,
                recommended_strategy, strategy_rationale, estimated_cost_usd,
                status, confidence_score, needs_human_review, extraction_cost_usd,
                org_id, processed_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,NOW())
            ON CONFLICT (file_hash) DO UPDATE SET
                status = EXCLUDED.status,
                confidence_score = EXCLUDED.confidence_score,
                needs_human_review = EXCLUDED.needs_human_review,
                extraction_cost_usd = EXCLUDED.extraction_cost_usd,
                processed_at = NOW()
            """,
            p.document_id, p.filename, p.file_hash, p.file_path, p.doc_type,
            p.origin_type, p.layout_complexity, p.page_count, p.language, p.has_tables,
            p.recommended_strategy, p.strategy_rationale, p.estimated_cost_usd,
            status, le.confidence_score, le.needs_human_review, le.cost_estimate_usd,
            org_id,
        )

        if le.needs_human_review:
            deadline = datetime.utcnow() + timedelta(hours=settings.hitl_review_sla_hours)
            await conn.execute(
                """
                INSERT INTO review_queue (
                    org_id, document_id, review_type, reason,
                    confidence_score, payload, sla_deadline
                )
                VALUES ($1, $2, 'document_extraction', $3, $4, $5, $6)
                """,
                org_id, p.document_id,
                f"Confidence {le.confidence_score:.3f} below threshold",
                le.confidence_score,
                json.dumps({"errors": le.errors, "strategy": le.strategy_selected}),
                deadline,
            )
