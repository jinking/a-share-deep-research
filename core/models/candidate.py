#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EvidenceCandidate：线索（v3.0.1 §5）。

核心纪律（§5「核心规则」）：

    线索 ≠ 证据

`EvidenceCandidate` 只表达「有人看见过这么一条线索」——搜索结果、neodata 摘要、
券商转述、媒体转述都属于这一层。它**不能**：

    - 满足 EVIDENCE_PRIMARY_REQUIRED（不是一手来源）
    - 满足 EVIDENCE_DIRECT_REQUIRED（没有直接支持关系）
    - 提供 critical Claim 的 locator
    - 提供 critical Claim 的 evidence_text
    - 参与正式 independent source count

要变成正式证据，必须走 §6 的摄入流程：拿到原件 → register Document → 算 SHA256
→ 生成 EvidenceLink → 补 locator 与原文摘录 → 才能把 status 置为 promoted。
promoted 之后**仍然**必须有正式 Document——status 本身不构成证据。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import EvidenceModelError, as_jsonable, clean_str, parse_datetime
from .document import SOURCE_TYPES

__all__ = [
    "CANDIDATE_ID_PREFIX",
    "CANDIDATE_STATUSES",
    "TERMINAL_CANDIDATE_STATUSES",
    "EvidenceCandidate",
    "is_candidate_id",
    "make_candidate_id",
]

CANDIDATE_ID_PREFIX = "CAN_"

# new → 刚发现；reviewed → 人工看过；promoted → 已成正式证据
# rejected → 判定不可用；duplicate → 与既有线索重复
CANDIDATE_STATUSES = ("new", "reviewed", "promoted", "rejected", "duplicate")

# 终态：不再需要跟进
TERMINAL_CANDIDATE_STATUSES = frozenset({"promoted", "rejected", "duplicate"})


def is_candidate_id(value: Any) -> bool:
    """Candidate ID 前缀约定：CAN_。用于拦截「把线索当证据」的误用。"""
    return str(value or "").startswith(CANDIDATE_ID_PREFIX)


@dataclass
class EvidenceCandidate:
    candidate_id: str
    source_type: str
    title: str
    discovered_at: str
    status: str = "new"
    # 该线索想支持的 Claim；可能一开始还不确定属于哪个 Claim，故可空
    claim_id: Optional[str] = None
    url: Optional[str] = None
    snippet: Optional[str] = None
    provider: Optional[str] = None
    # 上游出处提示：用于判断「两个线索是否同源」（如都转载自同一家媒体）
    upstream_hint: Optional[str] = None
    # promote 成功后回填的正式 Document；status=promoted 时必须有值。
    # 「promoted」本身不构成证据——真正的证据仍只认 Document + EvidenceLink。
    promoted_document_id: Optional[str] = None
    note: Optional[str] = None

    # ---- 派生属性 ----

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_CANDIDATE_STATUSES

    @property
    def has_source(self) -> bool:
        """线索级「有出处」：仅表示可点开看看，不等于可校验。"""
        return bool(self.url)

    # ---- 序列化 ----

    def to_dict(self) -> Dict[str, Any]:
        return as_jsonable(dict(self.__dict__))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceCandidate":
        if not isinstance(data, dict):
            raise EvidenceModelError("EvidenceCandidate 必须是 JSON 对象")
        allowed = set(cls.__dataclass_fields__)
        kwargs = {k: v for k, v in data.items() if k in allowed}
        return cls(**kwargs)

    # ---- 校验 ----

    def validate(self) -> None:
        """结构性校验：失败即 raise，不做静默修补。"""
        if not clean_str(self.candidate_id):
            raise EvidenceModelError("candidate_id 不能为空")
        if not self.candidate_id.startswith(CANDIDATE_ID_PREFIX):
            raise EvidenceModelError(
                f"candidate_id 需以 {CANDIDATE_ID_PREFIX} 开头: {self.candidate_id!r}"
            )
        if self.source_type not in SOURCE_TYPES:
            raise EvidenceModelError(
                f"source_type 非法: {self.source_type!r}；允许值: {sorted(SOURCE_TYPES)}"
            )
        if not clean_str(self.title):
            raise EvidenceModelError(f"{self.candidate_id}: title 不能为空")
        if not clean_str(self.discovered_at):
            raise EvidenceModelError(f"{self.candidate_id}: discovered_at 不能为空")
        if parse_datetime(self.discovered_at) is None:
            raise EvidenceModelError(
                f"{self.candidate_id}: discovered_at 无法解析为时间: {self.discovered_at!r}"
            )
        if self.status not in CANDIDATE_STATUSES:
            raise EvidenceModelError(
                f"{self.candidate_id}: status 非法 {self.status!r}；允许值: {list(CANDIDATE_STATUSES)}"
            )

    def describe(self) -> str:
        bits = [self.candidate_id, self.status, self.source_type, self.title]
        if self.provider:
            bits.append(f"via {self.provider}")
        return " | ".join(str(b) for b in bits)


# 便于调用方构造稳定 ID（与 make_document_id 同一套指纹思路）
def make_candidate_id(
    *,
    url: Optional[str] = None,
    title: Optional[str] = None,
    discovered_at: Optional[str] = None,
    provider: Optional[str] = None,
) -> str:
    """生成 CAN_<hash前8位>。优先用 url，其次 provider+discovered_at+title。"""
    from ..evidence.hasher import sha256_text

    base = clean_str(url)
    if not base:
        parts = [
            clean_str(provider) or "",
            clean_str(discovered_at) or "",
            clean_str(title) or "",
        ]
        if not any(parts):
            raise ValueError("无法生成 candidate_id：url / provider / discovered_at / title 全部为空")
        base = "|".join(parts)
    return CANDIDATE_ID_PREFIX + sha256_text(base)[:8]
