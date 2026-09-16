#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EvidenceLink：Claim → Document 的带定位证据链接（v3.0 §5.3）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .base import EvidenceModelError, as_jsonable, clean_str

__all__ = [
    "SUPPORT_TYPES",
    "LOCATOR_FIELDS",
    "EXCERPT_VERIFICATION_STATUSES",
    "EXCERPT_VERIFICATION_METHODS",
    "EvidenceLink",
]

SUPPORT_TYPES = ("direct", "partial", "contradict", "context")

# 定位字段：至少命中一种
LOCATOR_FIELDS = ("page", "section", "paragraph", "table")

# 摘录验证状态（v3.0.2 §9）：显式声明，禁止用「跳过校验」冒充「已校验」
EXCERPT_VERIFICATION_STATUSES = ("verified", "unverified", "not_applicable")

# 验证手段：verified 必须说明是怎么验的
EXCERPT_VERIFICATION_METHODS = ("direct_text", "text_layer", "manual", "ocr")


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
    # 以下为 v3.0.2 §9 摘录验证状态
    excerpt_verification_status: Optional[str] = None
    excerpt_verification_method: Optional[str] = None
    excerpt_verification_source: Optional[str] = None

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

    @property
    def excerpt_is_verified(self) -> bool:
        """摘录是否已被显式验证过（None 视为「未声明」＝未验证）。"""
        return self.excerpt_verification_status == "verified"

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

        status = clean_str(self.excerpt_verification_status)
        method = clean_str(self.excerpt_verification_method)
        if status and status not in EXCERPT_VERIFICATION_STATUSES:
            raise EvidenceModelError(
                f"{self.evidence_id}: excerpt_verification_status 非法 {status!r}；"
                f"允许值: {list(EXCERPT_VERIFICATION_STATUSES)}"
            )
        if method and method not in EXCERPT_VERIFICATION_METHODS:
            raise EvidenceModelError(
                f"{self.evidence_id}: excerpt_verification_method 非法 {method!r}；"
                f"允许值: {list(EXCERPT_VERIFICATION_METHODS)}"
            )
        # 「已验证」必须说明是怎么验的；反过来，声明了手段就必须给出结论。
        if status == "verified" and not method:
            raise EvidenceModelError(
                f"{self.evidence_id}: 摘录标记为 verified 但未声明 excerpt_verification_method"
            )
        if method and not status:
            raise EvidenceModelError(
                f"{self.evidence_id}: 声明了 excerpt_verification_method 但未给出 "
                "excerpt_verification_status"
            )

    def describe(self) -> str:
        from ..evidence.locator import describe_locator

        return (
            f"{self.evidence_id} -> {self.claim_id} @ {self.document_id} "
            f"[{self.support_type}] {describe_locator(self)}"
        )
