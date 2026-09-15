#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ResearchState：一次研究的证据对象全集（v3.0 §4）。

它只做「聚合 + 完整性检查」，不做内容判断；所有校验结论以 Issue 形式返回，
由 Validator 决定如何呈现，绝不修改产物（§19.2）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..issue import Issue
from .claim import STRICT_MATERIALITIES, Claim
from .document import SourceDocument
from .evidence import EvidenceLink

__all__ = ["ResearchState"]


@dataclass
class ResearchState:
    documents: Dict[str, SourceDocument] = field(default_factory=dict)
    claims: Dict[str, Claim] = field(default_factory=dict)
    links: List[EvidenceLink] = field(default_factory=list)
    research_date: Optional[str] = None
    manifest: Dict[str, Any] = field(default_factory=dict)

    # ---- 装配 ----

    def add_document(self, doc: SourceDocument) -> SourceDocument:
        self.documents[doc.document_id] = doc
        return doc

    def add_claim(self, claim: Claim) -> Claim:
        self.claims[claim.claim_id] = claim
        return claim

    def add_link(self, link: EvidenceLink) -> EvidenceLink:
        self.links.append(link)
        return link

    # ---- 查询 ----

    def links_of(self, claim_id: str) -> List[EvidenceLink]:
        return [l for l in self.links if l.claim_id == claim_id]

    def document_of(self, link: EvidenceLink) -> Optional[SourceDocument]:
        return self.documents.get(link.document_id)

    def documents_of(self, claim_id: str) -> List[SourceDocument]:
        out: List[SourceDocument] = []
        for link in self.links_of(claim_id):
            doc = self.document_of(link)
            if doc is not None and doc not in out:
                out.append(doc)
        return out

    def independent_source_count(self, claim_id: str) -> int:
        """独立来源数量：同 source_group 的转载只算一个来源。"""
        keys = {d.independence_key for d in self.documents_of(claim_id)}
        return len(keys)

    def source_groups_of(self, claim_id: str) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for doc in self.documents_of(claim_id):
            groups.setdefault(doc.independence_key, []).append(doc.document_id)
        return groups

    def dangling_links(self) -> List[EvidenceLink]:
        return [l for l in self.links if l.document_id not in self.documents]

    def links_missing_claims(self) -> List[EvidenceLink]:
        return [l for l in self.links if l.claim_id not in self.claims]

    def referenced_document_ids(self) -> Iterable[str]:
        return {l.document_id for l in self.links}

    # ---- 完整性检查（结构层面，不含语义判断） ----

    def check_integrity(self) -> List[Issue]:
        issues: List[Issue] = []

        for link in self.links_missing_claims():
            issues.append(
                Issue(
                    "P1",
                    "EVIDENCE_CLAIM_MISSING",
                    f"证据引用了不存在的 Claim: {link.evidence_id}",
                    f"claim_id={link.claim_id}；请检查 claims.jsonl 是否缺该 Claim",
                )
            )

        for link in self.dangling_links():
            claim = self.claims.get(link.claim_id)
            strict = claim is None or claim.materiality in STRICT_MATERIALITIES
            issues.append(
                Issue(
                    "P0" if strict else "P1",
                    "EVIDENCE_DOC_MISSING",
                    f"证据指向不存在的 Document: {link.evidence_id}",
                    f"document_id={link.document_id}；claim={link.claim_id}",
                )
            )

        # 文档 / Claim 的重复 ID 在 store 读取阶段即被识别（见 core/evidence/store.py），
        # 这里只负责 evidence_id 的重复检测。
        seen_evidence: Dict[str, int] = {}
        for link in self.links:
            seen_evidence[link.evidence_id] = seen_evidence.get(link.evidence_id, 0) + 1
        for ev_id, count in seen_evidence.items():
            if count > 1:
                issues.append(
                    Issue(
                        "P1",
                        "EVIDENCE_DUPLICATE_ID",
                        f"evidence_id 重复出现 {count} 次: {ev_id}",
                        "evidence_id 必须全局唯一",
                    )
                )

        return issues

    # ---- 方便测试与调试 ----

    def summary(self) -> Dict[str, int]:
        return {
            "documents": len(self.documents),
            "claims": len(self.claims),
            "links": len(self.links),
            "critical_claims": sum(
                1 for c in self.claims.values() if c.materiality in STRICT_MATERIALITIES
            ),
        }
