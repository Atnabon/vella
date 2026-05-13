"""ConfidenceGate — governs all agent decisions.

Three-tier: auto-approve / queue for review / reject.
Also runs data contract validation on every agent I/O boundary.
"""

from __future__ import annotations

import hashlib
import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GateDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    QUEUE_FOR_REVIEW = "queue_for_review"
    REJECT = "reject"


@dataclass
class GateResult:
    decision: GateDecision
    confidence: float
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    contract_violations: list[str] = field(default_factory=list)
    amount_anomaly: bool = False


class ConfidenceGate:
    def __init__(self, auto_approve: float = 0.90, escalation: float = 0.70) -> None:
        self.auto_approve_threshold = auto_approve
        self.escalation_threshold = escalation
        self._amount_history: list[float] = []
        self._confidence_history: list[float] = []

    def evaluate(self, confidence: float, payload: dict[str, Any], context: str = "") -> GateResult:
        violations = self._validate_contract(confidence, payload)
        amount_anomaly = self._check_amount_anomaly(payload)

        if violations:
            return GateResult(GateDecision.REJECT, confidence,
                              f"Contract violations: {'; '.join(violations)}",
                              payload, violations, amount_anomaly)

        if amount_anomaly:
            return GateResult(GateDecision.QUEUE_FOR_REVIEW, confidence,
                              "Unusual amount detected — queuing for review",
                              payload, amount_anomaly=True)

        self._confidence_history.append(confidence)

        if confidence >= self.auto_approve_threshold:
            return GateResult(GateDecision.AUTO_APPROVE, confidence,
                              f"Confidence {confidence:.3f} >= {self.auto_approve_threshold}", payload)
        elif confidence >= self.escalation_threshold:
            return GateResult(GateDecision.QUEUE_FOR_REVIEW, confidence,
                              f"Confidence {confidence:.3f} in review band", payload)
        else:
            return GateResult(GateDecision.REJECT, confidence,
                              f"Confidence {confidence:.3f} < {self.escalation_threshold}", payload)

    def _check_amount_anomaly(self, payload: dict[str, Any]) -> bool:
        """Flag unusual amounts via Z-score detection."""
        amount = payload.get("total_amount") or payload.get("amount")
        if amount is None or not isinstance(amount, (int, float)):
            return False
        self._amount_history.append(amount)
        if len(self._amount_history) < 10:
            return False
        mean = statistics.mean(self._amount_history[:-1])
        stdev = statistics.stdev(self._amount_history[:-1])
        if stdev == 0:
            return False
        z = abs(amount - mean) / stdev
        return z > 3.0

    @staticmethod
    def _validate_contract(confidence: float, payload: dict[str, Any]) -> list[str]:
        violations = []
        if not isinstance(confidence, (int, float)):
            violations.append(f"confidence must be numeric, got {type(confidence).__name__}")
        elif not (0.0 <= confidence <= 1.0):
            violations.append(f"confidence={confidence} out of [0.0, 1.0]")
        if not isinstance(payload, dict):
            violations.append(f"payload must be dict, got {type(payload).__name__}")
            return violations
        # Amount validation
        for key in ("total_amount", "amount", "subtotal"):
            val = payload.get(key)
            if val is not None:
                if not isinstance(val, (int, float)):
                    violations.append(f"{key} must be numeric")
                elif val < 0:
                    violations.append(f"{key}={val} cannot be negative")
        return violations

    @staticmethod
    def provenance_hash(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
