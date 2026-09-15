#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SourceDocument：证据来源文档（v3.0 §5.1）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .base import EvidenceModelError, as_jsonable, clean_str, is_sha256_hex, parse_date

__all__ = ["SOURCE_TYPES", "PRIMARY_SOURCE_TYPES", "SourceDocument"]

# 一手来源：可用于支撑确认级 Claim
PRIMARY_SOURCE_TYPES = frozenset(
    {
        "annual_report",
        "interim_report",
        "quarterly_report",
        "company_announcement",
        "exchange_filing",
        "company_ir",
        "customer_announcement",
        "government",
        "official_database",
    }
)

# 全部允许的来源类型
SOURCE_TYPES = frozenset(
    set(PRIMARY_SOURCE_TYPES)
    | {
        "broker_report",
        "media",
        "social_media",
        "data_vendor",
        "third_party_database",
    }
)


@dataclass
class SourceDocument:
    """证据来源文档。

    document_id 由内容/链接指纹生成（见 core.evidence.hasher.make_document_id），
    不使用简单递增 ID 作为全局唯一标识。
    """

    document_id: str
    source_type: str
    title: str
    retrieved_at: str
    issuer: Optional[str] = None
    published_at: Optional[str] = None
    url: Optional[str] = None
    local_path: Optional[str] = None
    sha256: Optional[str] = None
    source_group: Optional[str] = None
    # 以下为 v3.0 扩展字段（可选），用于定位与迁移状态记录
    page_count: Optional[int] = None
    sections: list = field(default_factory=list)
    migration_status: Optional[str] = None
    note: Optional[str] = None

    # ---- 派生属性 ----

    @property
    def is_primary(self) -> bool:
        return self.source_type in PRIMARY_SOURCE_TYPES

    @property
    def independence_key(self) -> str:
        """来源独立性判断键：同一上游转载共享同一个 source_group。"""
        return self.source_group or self.document_id

    @property
    def has_source(self) -> bool:
        """是否至少有一个可追溯入口（URL 或本地文件）。"""
        return bool(self.url or self.local_path)

    @property
    def published_date(self):
        return parse_date(self.published_at)

    # ---- 序列化 ----

    def to_dict(self) -> Dict[str, Any]:
        return as_jsonable(dict(self.__dict__))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceDocument":
        if not isinstance(data, dict):
            raise EvidenceModelError("SourceDocument 必须是 JSON 对象")
        allowed = set(cls.__dataclass_fields__)
        kwargs = {k: v for k, v in data.items() if k in allowed}
        return cls(**kwargs)

    # ---- 校验 ----

    def validate(self) -> None:
        """结构性校验：失败即 raise，不做静默修补。"""
        if not clean_str(self.document_id):
            raise EvidenceModelError("document_id 不能为空")
        if not self.document_id.startswith("DOC_"):
            raise EvidenceModelError(f"document_id 需以 DOC_ 开头: {self.document_id!r}")
        if self.source_type not in SOURCE_TYPES:
            raise EvidenceModelError(
                f"source_type 非法: {self.source_type!r}；允许值: {sorted(SOURCE_TYPES)}"
            )
        if not clean_str(self.title):
            raise EvidenceModelError("title 不能为空")
        if not clean_str(self.retrieved_at):
            raise EvidenceModelError("retrieved_at 不能为空")
        if self.sha256 is not None and not is_sha256_hex(self.sha256):
            raise EvidenceModelError(f"sha256 不是 64 位十六进制: {self.sha256!r}")
        if self.published_at is not None and self.published_date is None:
            raise EvidenceModelError(f"published_at 无法解析为日期: {self.published_at!r}")
        if self.page_count is not None and int(self.page_count) <= 0:
            raise EvidenceModelError(f"page_count 必须为正整数: {self.page_count!r}")

    def describe(self) -> str:
        bits = [f"{self.document_id}", self.source_type, self.title]
        if self.published_at:
            bits.append(f"({self.published_at})")
        return " | ".join(str(b) for b in bits)
