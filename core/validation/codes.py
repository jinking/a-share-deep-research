#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误码目录（v3.0 §16）。

要求：稳定、可测试、可搜索、不可随意改名；格式固定为「领域_问题」。
禁止使用 ERROR001 这类无语义编号。
"""

from __future__ import annotations

from typing import Dict

__all__ = [
    "EVIDENCE_CODES",
    "MANIFEST_V3_CODES",
    "REPORT_CLAIM_CODES",
    "CODES",
    "severity_of",
    "is_known_code",
]

EVIDENCE_CODES: Dict[str, str] = {
    # ---- P0：硬错误，禁止交付 ----
    "EVIDENCE_DOC_MISSING": "P0",          # Claim 指向不存在的 Document
    "EVIDENCE_HASH_MISMATCH": "P0",        # 本地文件 hash 与登记值不同（证据被替换）
    "EVIDENCE_PRIMARY_REQUIRED": "P0",     # 确认级 Claim 无允许的一手来源
    "EVIDENCE_DIRECT_REQUIRED": "P0",      # 已确认订单/收入/量产 等却无 direct 证据
    # ---- P1：重要缺陷，严格模式下禁止交付 ----
    "EVIDENCE_LOCATOR_MISSING": "P1",      # critical Claim 无 page/section/paragraph/table
    "EVIDENCE_LOCATOR_INVALID": "P1",      # 定位越界或指向文档未登记的章节
    "EVIDENCE_TEXT_MISSING": "P1",         # critical Claim 缺少可供人工审查的证据摘录
    "EVIDENCE_SOURCE_NOT_INDEPENDENT": "P1",   # 所谓「双源」实为同一上游转载
    "EVIDENCE_NO_SOURCE": "P1",            # Document 既无 url 也无 local_path
    "EVIDENCE_CLAIM_MISSING": "P1",        # Evidence 引用了不存在的 Claim
    "EVIDENCE_CLAIM_ORPHAN": "P1",         # critical/major Claim 完全没有证据绑定
    "EVIDENCE_SUPPORT_BROKEN": "P1",       # status=supported 但支持证据全部失效
    "EVIDENCE_DUPLICATE_ID": "P1",         # document_id / claim_id / evidence_id 重复
    "EVIDENCE_MODEL_INVALID": "P1",        # 模型字段非法（source_type、level 等）
    "EVIDENCE_PARSE": "P1",                # JSONL 解析失败
    "EVIDENCE_REF_UNKNOWN": "P1",          # manifest.evidence_refs 指向不存在的 Claim
    "EVIDENCE_REFS_EMPTY": "P1",           # v3 manifest 未声明任何关键 Claim
    "SOURCE_DATE_AFTER_RESEARCH_DATE": "P1",   # 【旧时间模型】证据发布时间晚于 research_date
    "SOURCE_DATE_AFTER_AS_OF": "P1",       # 证据发布时间晚于 as_of（v3.0.1 §4）
    "MARKET_DATA_AFTER_GENERATED_AT": "P1",    # 行情数据时点晚于报告生成时点（v3.0.1 §4）
    "GENERATED_AT_MISMATCH": "P1",         # manifest.generated_at 与报告内时间戳/文件名不一致
    "EVIDENCE_STORE_MISSING": "P1",        # v3 manifest 但未提供 Evidence Store
    "MANIFEST_VERSION_UNSUPPORTED": "P1",  # manifest_version 不在支持范围
    "MANIFEST_V3_STRUCTURE": "P1",         # v3 manifest 结构不完整
    "CLAIM_BASIS_UNKNOWN": "P1",           # basis_claim_ids 指向不存在的 Claim（v3.0.1 §9）
    "CLAIM_BASIS_LEVEL_INVALID": "P1",     # fact Claim 建立在不确认的推导之上（v3.0.1 §8）
    "CLAIM_UNCONFIRMED_SUPPORTED": "P1",   # 未确认等级却被标成 critical-supported（v3.0.1 §8）
    "CANDIDATE_USED_AS_EVIDENCE": "P0",    # 把 EvidenceCandidate 当成正式证据使用（v3.0.1 §9）
    "EVIDENCE_EXCERPT_VERIFICATION_MISMATCH": "P0",  # 摘录验证状态与重算结果不符（v3.0.3 §5）
    "CANDIDATE_PROMOTED_WITHOUT_DOCUMENT": "P1",  # Candidate 标为 promoted 但没有正式 Document
    "EVIDENCE_UPSTREAM_UNKNOWN": "P1",     # 上游引用无法解析到真实原件（不存在 / 成环）（v3.0.3 §7）
    "MANIFEST_STRICT_CLAIM_MISSING": "P1", # scope=report 的 critical/major Claim 未进 manifest（v3.0.3 §8）
    "EVIDENCE_EXCERPT_UNVERIFIED": "P1",   # critical Claim 的摘录未经验证（v3.0.2 §9）
    "TIME_MODEL_INCOMPLETE": "P1",         # 正式 v3 时间模型缺字段（v3.0.2 §11）
    # ---- P2：改进项，不单独阻断交付 ----
    "EVIDENCE_HASH_UNVERIFIED": "P2",      # 无法校验原始版本（无本地文件 / 无 hash）
    "EVIDENCE_IMPORTANCE_MISMATCH": "P2",  # manifest importance 与 Claim materiality 不一致
    "EVIDENCE_STORE_SKIPPED": "P2",        # v2 兼容模式：只做引用完整性，不做证据校验
    "TIME_MODEL_LEGACY": "P2",             # 旧时间模型：只有 research_date，没有 as_of
}

# 跨产物一致性（报告 ↔ Claim Ledger ↔ manifest.evidence_refs，v3.0.2 §6）
REPORT_CLAIM_CODES: Dict[str, str] = {
    # ---- P0：报告与 Ledger 直接冲突，禁止交付 ----
    "REPORT_CLAIM_UNKNOWN": "P0",           # 报告引用了不存在的 Claim
    "REPORT_PENDING_CLAIM_ASSERTED": "P0",  # status=pending 的 Claim 被当成确定性事实
    "REPORT_CLAIM_LEVEL_MISMATCH": "P0",    # 报告声明的 level 与 Ledger 不一致
    "REPORT_UNCONFIRMED_AS_FACT": "P0",     # 未确认等级被写成 fact / confirmed_*
    # v3.0.3 §4：level/status 全对、但报告复述的是**上一版** Claim。
    # 「锚点没声明 fingerprint」也归此类——没有版本可比，同样不能放行。
    "REPORT_CLAIM_REVISION_MISMATCH": "P0",
    # ---- P1：重要缺陷，严格模式下禁止交付 ----
    "REPORT_CLAIM_STATUS_MISMATCH": "P1",   # 报告声明的 status 与 Ledger 不一致
    "REPORT_CRITICAL_CLAIM_MISSING": "P1",  # critical Claim 在报告中没有任何落点
}

MANIFEST_V3_CODES: Dict[str, str] = {
    "MANIFEST_VERSION_UNSUPPORTED": "P1",
    "MANIFEST_V3_STRUCTURE": "P1",
    "MANIFEST_EVIDENCE_REFS_FORMAT": "P1",
    "EVIDENCE_REFS_EMPTY": "P1",
    "SOURCE_DATE_AFTER_AS_OF": "P1",
    "MARKET_DATA_AFTER_GENERATED_AT": "P1",
    "GENERATED_AT_MISMATCH": "P1",
    "CLAIM_BASIS_UNKNOWN": "P1",
    "CLAIM_BASIS_LEVEL_INVALID": "P1",
    "CLAIM_UNCONFIRMED_SUPPORTED": "P1",
    "CANDIDATE_USED_AS_EVIDENCE": "P0",
    "EVIDENCE_EXCERPT_VERIFICATION_MISMATCH": "P0",
    "CANDIDATE_PROMOTED_WITHOUT_DOCUMENT": "P1",
    "EVIDENCE_UPSTREAM_UNKNOWN": "P1",
    "MANIFEST_STRICT_CLAIM_MISSING": "P1",
    "EVIDENCE_EXCERPT_UNVERIFIED": "P1",
    "TIME_MODEL_INCOMPLETE": "P1",
    "TIME_MODEL_LEGACY": "P2",
}

# 全部错误码（证据层 + manifest 层 + 跨产物层）
CODES: Dict[str, str] = {**EVIDENCE_CODES, **MANIFEST_V3_CODES, **REPORT_CLAIM_CODES}


def severity_of(code: str, default: str = "P1") -> str:
    return CODES.get(code, default)


def is_known_code(code: str) -> bool:
    return code in CODES
