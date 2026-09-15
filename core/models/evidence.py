#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EvidenceLink：Claim → Document 的带定位证据链接（v3.0 §5.3）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .base import EvidenceModelError, as_jsonable, clean_str

__all__ = ["SUPPORT_TYPES", "EvidenceLink"]

SUPPORT_TYPES = ("direct", "partial", "contradict", "context")

# 定位字段：至少命中一种
LOCATOR_FIELDS = ("page", "section", "paragraph", "table")


@dataclass
class EvidenceLink:
    evidence_id: str
    claim_id: str
    document_id: str
    support_type: str = "direct"
    confidence: float = 1.0
    page: Optional[int] = None
    section: Optional[str] = None
    paragraph: Optional[str] = None
    table: Optional[str] = None
    evidence_text: Optional[str] = None
    migration_status: Optional[str] = None
    note: Optional[str] = None

    # ---- 派生属性 ----

    @property
    def locators(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "section": clean_str(self.section),
            "paragraph": clean_str(self.paragraph),
            "table": clean_str(self.table),
        }

    @property
    def has_locator(self) -> bool:
        return any(v is not None for v in self.locators.values())

    @property
    def is_direct(self) -> bool:
        return self.support_type == "direct"

    # ---- 序列化 ----

    def to_dict(self) -> Dict[str, Any]:
        return as_jsonable(dict(self.__dict__))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceLink":
        if not isinstance(data, dict):
            raise EvidenceModelError("EvidenceLink 必须是 JSON 对象")
        allowed = set(cls.__dataclass_fields__)
        kwargs = {k: v for k, v in data.items() if k in allowed}
        return cls(**kwargs)

    # ---- 校验 ----

    def validate(self) -> None:
        for name in ("evidence_id", "claim_id", "document_id"):
            if not clean_str(getattr(self, name)):
                raise EvidenceModelError(f"EvidenceLink.{name} 不能为空（{self.evidence_id or '未命名'}）")
        if self.support_type not in SUPPORT_TYPES:
            raise EvidenceModelError(
                f"{self.evidence_id}: support_type 非法 {self.support_type!r}；允许值: {list(SUPPORT_TYPES)}"
            )
        if self.page is not None:
            try:
                page = int(self.page)
            except (TypeError, ValueError):
                raise EvidenceModelError(f"{self.evidence_id}: page 必须是整数，当前 {self.page!r}")
            if page <= 0:
                raise EvidenceModelError(f"{self.evidence_id}: page 必须为正整数，当前 {page}")
        if self.confidence is not None:
            try:
                conf = float(self.confidence)
            except (TypeError, ValueError):
                raise EvidenceModelError(f"{self.evidence_id}: confidence 必须是 0–1 之间的数值")
            if not (0.0 <= conf <= 1.0):
                raise EvidenceModelError(f"{self.evidence_id}: confidence 超出 [0,1]: {conf}")

    def describe(self) -> str:
        from ..evidence.locator import describe_locator

        return (
            f"{self.evidence_id} -> {self.claim_id} @ {self.document_id} "
            f"[{self.support_type}] {describe_locator(self)}"
        )
