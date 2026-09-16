# -*- coding: utf-8 -*-
"""Executor 与 Validator 共用的验证逻辑（只检查，不修改产物）。"""

from __future__ import annotations

from .codes import CODES, EVIDENCE_CODES, REPORT_CLAIM_CODES, severity_of
from .evidence_validator import validate_evidence, validate_evidence_store
from .manifest_validator import detect_manifest_version, validate_manifest_v3
from .report_claim_validator import (
    ASSERTIVE_STATUSES,
    CONFIRMED_FACT_LEVELS,
    UNCONFIRMED_FAMILY,
    critical_claims_of,
    validate_report_claims,
)
from .time_model import (
    TIME_FIELDS,
    TIME_FIELD_LABELS,
    TimeModel,
    build_time_model,
    has_malformed_time_field,
    validate_time_model,
)

__all__ = [
    "CODES",
    "EVIDENCE_CODES",
    "REPORT_CLAIM_CODES",
    "severity_of",
    "validate_evidence",
    "validate_evidence_store",
    "validate_report_claims",
    "critical_claims_of",
    "UNCONFIRMED_FAMILY",
    "CONFIRMED_FACT_LEVELS",
    "ASSERTIVE_STATUSES",
    "detect_manifest_version",
    "validate_manifest_v3",
    "TIME_FIELDS",
    "TIME_FIELD_LABELS",
    "TimeModel",
    "build_time_model",
    "has_malformed_time_field",
    "validate_time_model",
]
