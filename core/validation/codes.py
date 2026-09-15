#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误码目录（v3.0 §16）。

要求：稳定、可测试、可搜索、不可随意改名；格式固定为「领域_问题」。
禁止使用 ERROR001 这类无语义编号。
"""

from __future__ import annotations

from typing import Dict

__all__ = ["EVIDENCE_CODES", "MANIFEST_V3_CODES", "CODES", "severity_of", "is_known_code"]

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
    "SOURCE_DATE_AFTER_RESEARCH_DATE": "P1",   # 证据发布时间晚于研究日期
    "EVIDENCE_STORE_MISSING": "P1",        # v3 manifest 但未提供 Evidence Store
    "MANIFEST_VERSION_UNSUPPORTED": "P1",  # manifest_version 不在支持范围
    "MANIFEST_V3_STRUCTURE": "P1",         # v3 manifest 结构不完整
    # ---- P2：改进项，不单独阻断交付 ----
    "EVIDENCE_HASH_UNVERIFIED": "P2",      # 无法校验原始版本（无本地文件 / 无 hash）
    "EVIDENCE_IMPORTANCE_MISMATCH": "P2",  # manifest importance 与 Claim materiality 不一致
    "EVIDENCE_STORE_SKIPPED": "P2",        # v2 兼容模式：只做引用完整性，不做证据校验
}

MANIFEST_V3_CODES: Dict[str, str] = {
    "MANIFEST_VERSION_UNSUPPORTED": "P1",
    "MANIFEST_V3_STRUCTURE": "P1",
    "MANIFEST_EVIDENCE_REFS_FORMAT": "P1",
    "EVIDENCE_REFS_EMPTY": "P1",
}

CODES: Dict[str, str] = {**EVIDENCE_CODES, **MANIFEST_V3_CODES}


def severity_of(code: str, default: str = "P1") -> str:
    return CODES.get(code, default)


def is_known_code(code: str) -> bool:
    return code in CODES
