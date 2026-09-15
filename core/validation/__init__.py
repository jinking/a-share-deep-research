# -*- coding: utf-8 -*-
"""Executor 与 Validator 共用的验证逻辑（只检查，不修改产物）。"""

from __future__ import annotations

from .codes import CODES, EVIDENCE_CODES, severity_of
from .evidence_validator import validate_evidence, validate_evidence_store
from .manifest_validator import detect_manifest_version, validate_manifest_v3
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
    "severity_of",
    "validate_evidence",
    "validate_evidence_store",
    "detect_manifest_version",
    "validate_manifest_v3",
    "TIME_FIELDS",
    "TIME_FIELD_LABELS",
    "TimeModel",
    "build_time_model",
    "has_malformed_time_field",
    "validate_time_model",
]
