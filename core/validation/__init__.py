# -*- coding: utf-8 -*-
"""Executor 与 Validator 共用的验证逻辑（只检查，不修改产物）。"""

from __future__ import annotations

from .codes import CODES, EVIDENCE_CODES, severity_of
from .evidence_validator import validate_evidence, validate_evidence_store
from .manifest_validator import detect_manifest_version, validate_manifest_v3

__all__ = [
    "CODES",
    "EVIDENCE_CODES",
    "severity_of",
    "validate_evidence",
    "validate_evidence_store",
    "detect_manifest_version",
    "validate_manifest_v3",
]
