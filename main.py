"""vella Ops — FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.documents import router as documents_router
from src.api.invoices import router as invoices_router
from src.api.ledger import router as ledger_router
from src.api.reconciliation import router as reconciliation_router
from src.api.tax import router as tax_router
from src.db import close_pool, get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="vella Ops API",
    description="Autonomous finance operations — invoice processing, reconciliation, tax prep, audit.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(documents_router, prefix=PREFIX)
app.include_router(invoices_router, prefix=PREFIX)
app.include_router(reconciliation_router, prefix=PREFIX)
app.include_router(tax_router, prefix=PREFIX)
app.include_router(ledger_router, prefix=PREFIX)


@app.on_event("startup")
async def startup() -> None:
    await get_pool()
    logger.info("vella Ops API started")


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_pool()
    logger.info("vella Ops API stopped")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "vella-ops"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "vella Ops", "docs": "/docs"}
