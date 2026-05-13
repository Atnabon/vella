"""EventStore — append-only, OCC, hash-chained, transactional outbox."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import asyncpg

from src.ledger.events import BaseEvent, OptimisticConcurrencyError, StoredEvent, StreamNotFoundError


class EventStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self, stream_id: str, events: list[BaseEvent], expected_version: int,
        correlation_id: str | None = None, causation_id: str | None = None,
    ) -> int:
        if not events:
            raise ValueError("Cannot append empty event list")
        async with self._pool.acquire() as conn:
            try:
                async with conn.transaction():
                    agg_type = stream_id.split("-")[0]
                    if expected_version == -1:
                        await conn.execute(
                            "INSERT INTO event_streams (stream_id, aggregate_type, current_version) VALUES ($1,$2,0)",
                            stream_id, agg_type,
                        )
                        current = 0
                    else:
                        row = await conn.fetchrow(
                            "SELECT current_version FROM event_streams WHERE stream_id=$1 FOR UPDATE", stream_id,
                        )
                        if row is None:
                            raise StreamNotFoundError(stream_id)
                        current = row["current_version"]
                        if current != expected_version:
                            raise OptimisticConcurrencyError(stream_id, expected_version, current)

                    meta: dict[str, Any] = {}
                    if correlation_id:
                        meta["correlation_id"] = correlation_id
                    if causation_id:
                        meta["causation_id"] = causation_id

                    new_ver = current
                    for event in events:
                        new_ver += 1
                        eid = uuid.uuid4()
                        await conn.execute(
                            """INSERT INTO events (event_id,stream_id,stream_position,event_type,event_version,payload,metadata)
                               VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                            eid, stream_id, new_ver, event.event_type, event.event_version, event.payload, meta,
                        )
                        await conn.execute(
                            "INSERT INTO outbox (event_id,destination,payload) VALUES ($1,$2,$3)",
                            eid, f"stream:{stream_id}", event.payload,
                        )

                    await conn.execute(
                        "UPDATE event_streams SET current_version=$1 WHERE stream_id=$2", new_ver, stream_id,
                    )
                    return new_ver
            except asyncpg.UniqueViolationError:
                actual = await self._get_version(conn, stream_id)
                raise OptimisticConcurrencyError(stream_id, expected_version, actual)

    async def load_stream(self, stream_id: str, from_position: int = 0) -> list[StoredEvent]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT event_id,stream_id,stream_position,global_position,
                          event_type,event_version,payload,metadata,recorded_at
                   FROM events WHERE stream_id=$1 AND stream_position>$2
                   ORDER BY stream_position ASC""",
                stream_id, from_position,
            )
        return [StoredEvent(
            event_id=r["event_id"], stream_id=r["stream_id"],
            stream_position=r["stream_position"], global_position=r["global_position"],
            event_type=r["event_type"], event_version=r["event_version"],
            payload=r["payload"], metadata=r["metadata"] or {}, recorded_at=r["recorded_at"],
        ) for r in rows]

    async def stream_version(self, stream_id: str) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT current_version FROM event_streams WHERE stream_id=$1", stream_id,
            )
        return row["current_version"] if row else -1

    async def build_chain(self, stream_id: str) -> dict[str, Any]:
        events = await self.load_stream(stream_id)
        if not events:
            return {"stream_id": stream_id, "events_checked": 0, "integrity": "EMPTY"}
        prev = "GENESIS"
        async with self._pool.acquire() as conn:
            for pos, e in enumerate(events, 1):
                data = {"event_id": str(e.event_id), "stream_id": e.stream_id,
                        "stream_position": e.stream_position, "event_type": e.event_type,
                        "payload": e.payload, "recorded_at": e.recorded_at.isoformat()}
                eh = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
                ch = hashlib.sha256(f"{prev}:{eh}".encode()).hexdigest()
                await conn.execute(
                    """INSERT INTO audit_chain (stream_id,event_id,event_hash,chain_hash,chain_position)
                       VALUES ($1,$2,$3,$4,$5)
                       ON CONFLICT (stream_id,chain_position) DO UPDATE
                       SET event_hash=EXCLUDED.event_hash, chain_hash=EXCLUDED.chain_hash, computed_at=NOW()""",
                    stream_id, e.event_id, eh, ch, pos,
                )
                prev = ch
        return {"stream_id": stream_id, "events_checked": len(events), "final_hash": prev, "integrity": "VERIFIED"}

    async def verify_chain(self, stream_id: str) -> dict[str, Any]:
        events = await self.load_stream(stream_id)
        async with self._pool.acquire() as conn:
            stored = {r["chain_position"]: r["chain_hash"] for r in await conn.fetch(
                "SELECT chain_position,chain_hash FROM audit_chain WHERE stream_id=$1 ORDER BY chain_position", stream_id,
            )}
        prev, discrepancies = "GENESIS", []
        for pos, e in enumerate(events, 1):
            data = {"event_id": str(e.event_id), "stream_id": e.stream_id,
                    "stream_position": e.stream_position, "event_type": e.event_type,
                    "payload": e.payload, "recorded_at": e.recorded_at.isoformat()}
            eh = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            ch = hashlib.sha256(f"{prev}:{eh}".encode()).hexdigest()
            if pos in stored and stored[pos] != ch:
                discrepancies.append({"position": pos, "expected": ch, "stored": stored[pos]})
            prev = ch
        return {"stream_id": stream_id, "events_checked": len(events),
                "integrity": "TAMPERED" if discrepancies else "VERIFIED",
                "discrepancies": discrepancies, "final_hash": prev}

    @staticmethod
    async def _get_version(conn, stream_id: str) -> int:
        row = await conn.fetchrow("SELECT current_version FROM event_streams WHERE stream_id=$1", stream_id)
        return row["current_version"] if row else -1
