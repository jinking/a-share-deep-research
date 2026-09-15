#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research_manifest v2 / v3 结构校验（v3.0 §7、§16）。

注意：本模块只做「清单结构与引用声明」的检查；
0–16 章、三情景×三年、EPS×股本 等数学一致性仍由 scripts/validate_report.py 负责。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..models.base import clean_str
from ..models.claim import MATERIALITIES
from .codes import severity_of

__all__ = ["SUPPORTED_VERSIONS", "detect_manifest_version", "validate_manifest_v3"]

SUPPORTED_VERSIONS = (2, 3)
REQUIRED_V3_BLOCKS = ("meta", "forecast", "valuation", "final")

Emit = Callable[..., None]


def detect_manifest_version(data: Dict[str, Any]) -> int:
    if not isinstance(data, dict):
        return 2
    raw = data.get("manifest_version")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return -1
    return 3 if "evidence_refs" in data else 2


def validate_manifest_v3(
    data: Dict[str, Any], *, emit: Emit, version: Optional[int] = None
) -> None:
    version = detect_manifest_version(data) if version is None else version

    if version not in SUPPORTED_VERSIONS:
        emit(
            severity_of("MANIFEST_VERSION_UNSUPPORTED"),
            "MANIFEST_VERSION_UNSUPPORTED",
            f"不支持的 manifest_version: {version}",
            f"当前支持 {list(SUPPORTED_VERSIONS)}；v2 走兼容模式，v3 执行完整 Evidence Validation",
        )
        return

    if version < 3:
        emit(
            "INFO",
            "MANIFEST_V2_COMPAT",
            "v2 manifest：Evidence Verification 降级为兼容检查",
            "建议迁移：python scripts/migrate_manifest_v2_to_v3.py old_manifest.json --out research_manifest.v3.json",
        )
        return

    missing = [b for b in REQUIRED_V3_BLOCKS if not data.get(b)]
    if missing:
        emit(
            severity_of("MANIFEST_V3_STRUCTURE"),
            "MANIFEST_V3_STRUCTURE",
            "v3 manifest 缺少必需区块",
            f"缺少: {missing}；必需: {list(REQUIRED_V3_BLOCKS)}",
        )

    meta = data.get("meta") or {}
    if not clean_str(meta.get("research_date")):
        emit(
            severity_of("MANIFEST_V3_STRUCTURE"),
            "MANIFEST_V3_STRUCTURE",
            "v3 manifest 缺少 meta.research_date",
            "缺该字段将无法执行「证据发布时间不得晚于研究日期」校验",
        )

    refs = data.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        emit(
            severity_of("EVIDENCE_REFS_EMPTY"),
            "EVIDENCE_REFS_EMPTY",
            "v3 manifest 必须声明 evidence_refs（关键 Claim 引用）",
            f"当前值={refs!r}",
        )
        return

    seen = set()
    for i, ref in enumerate(refs, start=1):
        if not isinstance(ref, dict):
            emit(
                severity_of("MANIFEST_EVIDENCE_REFS_FORMAT"),
                "MANIFEST_EVIDENCE_REFS_FORMAT",
                f"evidence_refs 第 {i} 项不是对象",
                repr(ref)[:120],
            )
            continue
        claim_id = clean_str(ref.get("claim_id"))
        importance = clean_str(ref.get("importance"))
        if not claim_id:
            emit(
                severity_of("MANIFEST_EVIDENCE_REFS_FORMAT"),
                "MANIFEST_EVIDENCE_REFS_FORMAT",
                f"evidence_refs 第 {i} 项缺少 claim_id",
                repr(ref)[:120],
            )
        elif claim_id in seen:
            emit(
                severity_of("MANIFEST_EVIDENCE_REFS_FORMAT"),
                "MANIFEST_EVIDENCE_REFS_FORMAT",
                f"evidence_refs 中 claim_id 重复: {claim_id}",
                "同一 Claim 只应在 evidence_refs 中出现一次",
            )
        else:
            seen.add(claim_id)
        if importance and importance not in MATERIALITIES:
            emit(
                severity_of("MANIFEST_EVIDENCE_REFS_FORMAT"),
                "MANIFEST_EVIDENCE_REFS_FORMAT",
                f"evidence_refs 第 {i} 项 importance 非法: {importance!r}",
                f"允许值: {list(MATERIALITIES)}",
            )
