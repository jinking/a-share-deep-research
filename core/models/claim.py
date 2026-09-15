#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim：可追溯研究结论（v3.0 §5.2）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import EvidenceModelError, as_jsonable, clean_str

__all__ = [
    "CLAIM_CATEGORIES",
    "CLAIM_LEVELS",
    "MATERIALITIES",
    "CLAIM_STATUSES",
    "PRIMARY_REQUIRED_LEVELS",
    "DIRECT_REQUIRED_LEVELS",
    "STRICT_MATERIALITIES",
    "Claim",
    "is_semantic_claim_id",
]

CLAIM_CATEGORIES = (
    "financial",
    "order",
    "customer",
    "industry",
    "valuation",
    "governance",
    "risk",
    "market",
    "other",
)

CLAIM_LEVELS = (
    # 未升级为确认级的等级
    "fact",
    "management_statement",
    "inference",
    "assumption",
    "unconfirmed",
    "third_party_consensus",
    # 确认级（需一手来源，部分还需 direct 支持）
    "confirmed_revenue",
    "confirmed_order",
    "design_win",
    "mass_production",
    "batch_delivery",
)

# 确认级 Claim：至少需要一个一手来源 Document
PRIMARY_REQUIRED_LEVELS = frozenset(
    {
        "confirmed_revenue",
        "confirmed_order",
        "design_win",
        "mass_production",
        "batch_delivery",
    }
)

# 其中必须存在 support_type = direct 的证据（v3.0 §5.3）
DIRECT_REQUIRED_LEVELS = frozenset(
    {
        "confirmed_revenue",
        "confirmed_order",
        "mass_production",
        "batch_delivery",
    }
)

MATERIALITIES = ("critical", "major", "normal")
# 只有 critical / major 进入严格 Evidence Validation
STRICT_MATERIALITIES = frozenset({"critical", "major"})

CLAIM_STATUSES = (
    "supported",
    "partially_supported",
    "unsupported",
    "pending",
    "contradicted",
)

# v2 中文等级 -> v3 等级（迁移用）
V2_LEVEL_ALIASES = {
    "事实": "fact",
    "管理层口径": "management_statement",
    "管理层表述": "management_statement",
    "推断": "inference",
    "假设": "assumption",
    "无法确认": "unconfirmed",
    "第三方一致预期": "third_party_consensus",
    "已确认收入": "confirmed_revenue",
    "已确认订单": "confirmed_order",
    "已定点": "design_win",
    "已量产": "mass_production",
    "已批量交付": "batch_delivery",
}

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SEMANTIC_HINT_RE = re.compile(r"_[A-Z]")


def is_semantic_claim_id(claim_id: str) -> bool:
    """推荐使用语义稳定 ID（如 C_FIN_REV_2026H1），而不是 C001。

    这里只做「更像语义 ID」的弱判断，用于给出提示，不作为硬校验。
    """
    text = str(claim_id or "")
    if not _ID_RE.match(text):
        return False
    return bool(_SEMANTIC_HINT_RE.search(text)) and not re.fullmatch(r"[A-Za-z]+\d+", text)


@dataclass
class Claim:
    claim_id: str
    claim: str
    category: str = "other"
    level: str = "fact"
    materiality: str = "normal"
    status: str = "pending"
    # 需要双源确认时置 True；validator 会检查来源独立性
    requires_two_sources: bool = False
    # v3.1 Forecast Lineage 预留：假设型 Claim 可声明其依据的事实 Claim
    basis_claim_ids: List[str] = field(default_factory=list)
    migration_status: Optional[str] = None
    note: Optional[str] = None

    # ---- 派生属性 ----

    @property
    def is_confirmed_level(self) -> bool:
        return self.level in PRIMARY_REQUIRED_LEVELS

    @property
    def needs_strict_validation(self) -> bool:
        return self.materiality in STRICT_MATERIALITIES

    @property
    def requires_direct(self) -> bool:
        return self.level in DIRECT_REQUIRED_LEVELS

    # ---- 序列化 ----

    def to_dict(self) -> Dict[str, Any]:
        return as_jsonable(dict(self.__dict__))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Claim":
        if not isinstance(data, dict):
            raise EvidenceModelError("Claim 必须是 JSON 对象")
        allowed = set(cls.__dataclass_fields__)
        kwargs = {k: v for k, v in data.items() if k in allowed}
        basis = kwargs.get("basis_claim_ids")
        if isinstance(basis, str):
            kwargs["basis_claim_ids"] = [basis]
        elif basis is None:
            kwargs["basis_claim_ids"] = []
        return cls(**kwargs)

    # ---- 校验 ----

    def validate(self) -> None:
        if not clean_str(self.claim_id):
            raise EvidenceModelError("claim_id 不能为空")
        if not _ID_RE.match(self.claim_id):
            raise EvidenceModelError(
                f"claim_id 必须是字母开头的标识符（[A-Za-z][A-Za-z0-9_]*）: {self.claim_id!r}"
            )
        if not clean_str(self.claim):
            raise EvidenceModelError(f"{self.claim_id}: claim 文本不能为空")
        if self.category not in CLAIM_CATEGORIES:
            raise EvidenceModelError(
                f"{self.claim_id}: category 非法 {self.category!r}；允许值: {list(CLAIM_CATEGORIES)}"
            )
        if self.level not in CLAIM_LEVELS:
            raise EvidenceModelError(
                f"{self.claim_id}: level 非法 {self.level!r}；允许值: {list(CLAIM_LEVELS)}"
            )
        if self.materiality not in MATERIALITIES:
            raise EvidenceModelError(
                f"{self.claim_id}: materiality 非法 {self.materiality!r}；允许值: {list(MATERIALITIES)}"
            )
        if self.status not in CLAIM_STATUSES:
            raise EvidenceModelError(
                f"{self.claim_id}: status 非法 {self.status!r}；允许值: {list(CLAIM_STATUSES)}"
            )

    def describe(self) -> str:
        return f"{self.claim_id} [{self.category}/{self.level}/{self.materiality}] {self.claim}"
