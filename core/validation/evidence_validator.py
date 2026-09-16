#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence Validator（v3.0 §8）。

职责单一：检查 Evidence Store 与 manifest 的证据绑定关系，输出 P0/P1/P2 结论。
禁止：自动补 Claim、自动改证据等级、自动修正内容、写回任何产物（§19.2）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..evidence.hasher import sha256_file
from ..evidence.independence import describe_groups, group_documents, shared_upstream_hint
from ..evidence.locator import describe_locator, validate_locator
from ..issue import Issue
from ..models.base import clean_str, parse_date
from ..models.claim import PRIMARY_REQUIRED_LEVELS, STRICT_MATERIALITIES, Claim
from ..models.document import SourceDocument
from ..models.evidence import EvidenceLink
from ..models.research_state import ResearchState
from .codes import severity_of
from .time_model import TimeModel, build_time_model

__all__ = ["Emit", "validate_evidence", "validate_evidence_store"]

Emit = Callable[..., None]

# 「事实」可以建立在什么之上：事实本身，或已确认级（一手来源支撑）
FACT_BASIS_LEVELS = frozenset({"fact"}) | PRIMARY_REQUIRED_LEVELS

# 不得被标为 supported 的「未确认」等级（v3.0.1 §8）。
# 注意不含 management_statement —— 管理层口径是**已披露**的信息，不是「未确认」。
UNCONFIRMED_LEVELS = frozenset({"assumption", "unconfirmed"})

# 仅用于「文档缺失时」判断是否一手来源（缺失必然不是），不参与任何写入。
_MISSING_DOC = SourceDocument(
    document_id="DOC_missing", source_type="media", title="(missing)", retrieved_at="1970-01-01"
)


def _emit(emit: Emit, severity: str, code: str, message: str, detail: str = "") -> None:
    emit(severity, code, message, detail)


def _emit_issue(emit: Emit, issue: Issue) -> None:
    _emit(emit, issue.severity, issue.code, issue.message, issue.detail)


def _check_documents(
    state: ResearchState,
    *,
    emit: Emit,
    base_dir: Optional[Path],
    time_model: "TimeModel",
) -> None:
    for doc in state.documents.values():
        # 1) 可追溯入口
        if not doc.has_source:
            _emit(
                emit,
                severity_of("EVIDENCE_NO_SOURCE"),
                "EVIDENCE_NO_SOURCE",
                f"Document 既无 url 也无 local_path: {doc.document_id}",
                doc.describe(),
            )

        # 2) 原始版本是否被替换
        if doc.local_path:
            path = Path(doc.local_path)
            if base_dir is not None and not path.is_absolute():
                path = Path(base_dir) / path
            if doc.sha256:
                if not path.is_file():
                    _emit(
                        emit,
                        severity_of("EVIDENCE_HASH_UNVERIFIED"),
                        "EVIDENCE_HASH_UNVERIFIED",
                        f"登记了 sha256 但本地文件缺失，无法证明未被替换: {doc.document_id}",
                        f"local_path={doc.local_path}；解析路径={path}",
                    )
                else:
                    actual = sha256_file(path)
                    if actual.lower() != str(doc.sha256).strip().lower():
                        _emit(
                            emit,
                            severity_of("EVIDENCE_HASH_MISMATCH"),
                            "EVIDENCE_HASH_MISMATCH",
                            f"Document 本地文件 hash 与登记值不同: {doc.document_id}",
                            f"登记={doc.sha256}；实际={actual}；文件={path}",
                        )
            else:
                _emit(
                    emit,
                    severity_of("EVIDENCE_HASH_UNVERIFIED"),
                    "EVIDENCE_HASH_UNVERIFIED",
                    f"Document 未登记 sha256，无法校验原始版本: {doc.document_id}",
                    f"local_path={doc.local_path}",
                )
        elif doc.url:
            _emit(
                emit,
                severity_of("EVIDENCE_HASH_UNVERIFIED"),
                "EVIDENCE_HASH_UNVERIFIED",
                f"Document 仅有 URL 无本地副本，无法校验原始版本: {doc.document_id}",
                doc.url,
            )

        # 3) 时间一致性：证据发布时间不得晚于研究信息截止时点
        #    v3.0.2 §12：双方都有时刻 → datetime 比较；证据只写到日 → 退化为 day-level。
        #    禁止拿 00:00 冒充未知的发布时间，那会凭空制造时点结论。
        cutoff = time_model.info_cutoff
        cutoff_dt = time_model.as_of
        pub_dt = doc.published_datetime
        late = False
        if cutoff is not None:
            if pub_dt is not None and cutoff_dt is not None:
                late = pub_dt > cutoff_dt
            else:
                pub_day = doc.published_date
                late = pub_day is not None and pub_day > cutoff
        if late:
            # 新时间模型报 SOURCE_DATE_AFTER_AS_OF；旧模型保留原错误码，行为不变
            if time_model.is_new_model:
                code = "SOURCE_DATE_AFTER_AS_OF"
                detail = (
                    f"published_at={doc.published_at}；"
                    f"as_of={time_model.raw.get('as_of')}"
                )
            else:
                code = "SOURCE_DATE_AFTER_RESEARCH_DATE"
                detail = (
                    f"published_at={doc.published_at}；"
                    f"research_date={time_model.raw.get('research_date')}"
                )
            _emit(
                emit,
                severity_of(code),
                code,
                f"证据发布时间晚于研究截止时点: {doc.document_id}",
                detail,
            )


def _claim_level_policy(
    state: ResearchState,
    claim: Claim,
    links: List[EvidenceLink],
    *,
    emit: Emit,
) -> None:
    docs = [state.documents.get(l.document_id) for l in links]
    docs = [d for d in docs if d is not None]

    # 确认级：必须有一手来源
    if claim.level in PRIMARY_REQUIRED_LEVELS and claim.materiality in STRICT_MATERIALITIES:
        if not any(d.is_primary for d in docs):
            _emit(
                emit,
                severity_of("EVIDENCE_PRIMARY_REQUIRED"),
                "EVIDENCE_PRIMARY_REQUIRED",
                f"确认级 Claim 缺少一手来源: {claim.claim_id}",
                f"level={claim.level}；现有来源={[d.source_type for d in docs] or '无'}",
            )

    # 已确认订单/收入/量产等：必须存在 direct 证据
    if claim.requires_direct:
        direct = [l for l in links if l.support_type == "direct"]
        direct_primary = [
            l
            for l in direct
            if (state.documents.get(l.document_id) or _MISSING_DOC).is_primary
        ]
        if not direct:
            _emit(
                emit,
                severity_of("EVIDENCE_DIRECT_REQUIRED"),
                "EVIDENCE_DIRECT_REQUIRED",
                f"{claim.level} 必须有 support_type=direct 的证据: {claim.claim_id}",
                f"现有 support_type={[l.support_type for l in links] or '无'}",
            )
        elif not direct_primary:
            source_types = [
                state.documents[l.document_id].source_type
                if l.document_id in state.documents
                else "文档缺失"
                for l in direct
            ]
            _emit(
                emit,
                severity_of("EVIDENCE_DIRECT_REQUIRED"),
                "EVIDENCE_DIRECT_REQUIRED",
                f"{claim.level} 的 direct 证据不来自一手来源: {claim.claim_id}",
                f"direct 证据来源={source_types}",
            )

    # critical 额外要求：定位 + 可审查摘录
    if claim.materiality == "critical":
        if not any(l.has_locator for l in links):
            _emit(
                emit,
                severity_of("EVIDENCE_LOCATOR_MISSING"),
                "EVIDENCE_LOCATOR_MISSING",
                f"critical Claim 的证据没有任何定位: {claim.claim_id}",
                f"evidence={[l.evidence_id for l in links]}；需要 page/section/paragraph/table 至少一种",
            )
        if not any(clean_str(l.evidence_text) for l in links):
            _emit(
                emit,
                severity_of("EVIDENCE_TEXT_MISSING"),
                "EVIDENCE_TEXT_MISSING",
                f"critical Claim 缺少可供人工审查的证据摘录: {claim.claim_id}",
                "evidence_text 为必填（原文摘录，便于人工复核）",
            )

        # 摘录「跳过了校验」不等于「已经验证过」（v3.0.2 §9）。
        # 未声明状态同样按未验证处理 —— 否则「什么都不写」就成了最省事的通过方式。
        with_text = [l for l in links if clean_str(l.evidence_text)]
        unverified = [l for l in with_text if not l.excerpt_is_verified]
        if unverified:
            _emit(
                emit,
                severity_of("EVIDENCE_EXCERPT_UNVERIFIED"),
                "EVIDENCE_EXCERPT_UNVERIFIED",
                f"critical Claim 的摘录未经验证，不能作为可复核证据: {claim.claim_id}",
                "未验证="
                + str([f"{l.evidence_id}({l.excerpt_verification_status or '未声明'})" for l in unverified])
                + "；请用 excerpt_verification_status=verified 声明（并给出 method/source），"
                "或补齐可比对的文本层后重新执行摘录校验",
            )

    # 定位越界 / 章节不存在
    for link in links:
        doc = state.documents.get(link.document_id)
        problems = validate_locator(link, doc)
        hard = [p for p in problems if not p.startswith("page / section")]
        if hard:
            _emit(
                emit,
                severity_of("EVIDENCE_LOCATOR_INVALID"),
                "EVIDENCE_LOCATOR_INVALID",
                f"证据定位非法: {link.evidence_id}",
                f"{describe_locator(link)}；问题={hard}",
            )


def _check_independence(
    state: ResearchState, claim: Claim, links: List[EvidenceLink], *, emit: Emit
) -> None:
    if not claim.requires_two_sources:
        return
    docs = [d for d in (state.documents.get(l.document_id) for l in links) if d is not None]
    # 传全量文档表：声明了 upstream_document_id 的 Document 要沿上游合并，
    # 否则「westock-data + 公司公告」会被错当成两个独立来源（v3.0.2 §8）。
    groups = group_documents(docs, state.documents)
    if len(groups) >= 2:
        return
    detail = describe_groups(groups)
    hint = shared_upstream_hint(groups)
    _emit(
        emit,
        severity_of("EVIDENCE_SOURCE_NOT_INDEPENDENT"),
        "EVIDENCE_SOURCE_NOT_INDEPENDENT",
        f"需要双源确认的 Claim 不满足独立性: {claim.claim_id}",
        f"独立来源数={len(groups)}；{detail}" + (f"；{hint}" if hint else ""),
    )


def _check_claim_basis(state: ResearchState, claim: Claim, *, emit: Emit) -> None:
    """Claim 的「依据」是否成立（v3.0.1 §8 / §9）。

    两条结构性规则，都不涉及语义理解：

    - `basis_claim_ids` 必须指向真实存在的 Claim（否则依据是空的）；
    - `fact` 级的结论不能建立在 `inference` / `assumption` / `unconfirmed` 之上，
      因为那等于把「推导」当「事实」用。推导链本身可以叠推导，
      只有 fact 这一层要求依据足够硬。
    """
    basis = [clean_str(c) for c in (claim.basis_claim_ids or []) if clean_str(c)]
    if not basis:
        return

    unknown = [cid for cid in basis if cid not in state.claims]
    if unknown:
        _emit(
            emit,
            severity_of("CLAIM_BASIS_UNKNOWN"),
            "CLAIM_BASIS_UNKNOWN",
            f"Claim 的依据指向了不存在的 Claim: {claim.claim_id}",
            f"basis_claim_ids={unknown}；claims.jsonl 中无此 claim_id",
        )

    if claim.level != "fact":
        return

    weak = [
        f"{cid}({state.claims[cid].level})"
        for cid in basis
        if cid in state.claims and state.claims[cid].level not in FACT_BASIS_LEVELS
    ]
    if weak:
        _emit(
            emit,
            severity_of("CLAIM_BASIS_LEVEL_INVALID"),
            "CLAIM_BASIS_LEVEL_INVALID",
            f"fact Claim 依赖了未确认的推导: {claim.claim_id}",
            f"依据={weak}；事实级只能建立在事实/确认级之上，"
            "否则应把本 Claim 降级为 inference",
        )


def _check_claims(state: ResearchState, *, emit: Emit) -> None:
    for claim in state.claims.values():
        links = state.links_of(claim.claim_id)
        alive = [l for l in links if l.document_id in state.documents]

        if claim.materiality in STRICT_MATERIALITIES and not links:
            _emit(
                emit,
                severity_of("EVIDENCE_CLAIM_ORPHAN"),
                "EVIDENCE_CLAIM_ORPHAN",
                f"{claim.materiality} Claim 没有任何证据绑定: {claim.claim_id}",
                claim.describe(),
            )

        if claim.status == "supported" and not alive:
            _emit(
                emit,
                severity_of("EVIDENCE_SUPPORT_BROKEN"),
                "EVIDENCE_SUPPORT_BROKEN",
                f"Claim 标记为 supported 但支持证据全部失效: {claim.claim_id}",
                f"links={[l.evidence_id for l in links]}；有效链接={len(alive)}",
            )

        # 未确认的东西不能被标成 supported —— 否则「等级」就成了装饰（§8）
        if (
            claim.level in UNCONFIRMED_LEVELS
            and claim.status == "supported"
            and claim.materiality in STRICT_MATERIALITIES
        ):
            _emit(
                emit,
                severity_of("CLAIM_UNCONFIRMED_SUPPORTED"),
                "CLAIM_UNCONFIRMED_SUPPORTED",
                f"未确认等级的 Claim 不能标为 supported: {claim.claim_id}",
                f"level={claim.level}；materiality={claim.materiality}；"
                "请改为 status=pending，或补齐口径后升级等级",
            )

        _check_claim_basis(state, claim, emit=emit)
        _claim_level_policy(state, claim, links, emit=emit)
        _check_independence(state, claim, links, emit=emit)


def _check_candidates(state: ResearchState, *, emit: Emit) -> None:
    """线索层检查（v3.0.1 §5）。

    线索本身不参与证据校验的通过口径；这里只拦住一种误用：
    把自己标成 `promoted` 却没有对应正式 Document —— 那等于用状态冒充证据。
    """
    for candidate in state.candidates.values():
        if candidate.status != "promoted":
            continue
        doc_id = clean_str(candidate.promoted_document_id)
        if not doc_id or doc_id not in state.documents:
            _emit(
                emit,
                severity_of("CANDIDATE_PROMOTED_WITHOUT_DOCUMENT"),
                "CANDIDATE_PROMOTED_WITHOUT_DOCUMENT",
                f"线索标为 promoted 但没有正式 Document: {candidate.candidate_id}",
                f"promoted_document_id={candidate.promoted_document_id or '(空)'}；"
                "promoted 只是跟进状态，证据仍只认 Document + EvidenceLink",
            )


def _check_manifest_refs(
    state: ResearchState, manifest: Dict[str, Any], *, emit: Emit
) -> None:
    refs = manifest.get("evidence_refs")
    if refs is None:
        _emit(
            emit,
            severity_of("EVIDENCE_REFS_EMPTY"),
            "EVIDENCE_REFS_EMPTY",
            "v3 manifest 未声明 evidence_refs（关键 Claim 引用）",
            "请在 manifest 中登记 claim_id + importance",
        )
        return
    if not isinstance(refs, list) or not refs:
        _emit(
            emit,
            severity_of("EVIDENCE_REFS_EMPTY"),
            "EVIDENCE_REFS_EMPTY",
            "v3 manifest 的 evidence_refs 为空",
            f"当前值={refs!r}",
        )
        return

    for i, ref in enumerate(refs, start=1):
        if not isinstance(ref, dict):
            _emit(
                emit,
                severity_of("MANIFEST_EVIDENCE_REFS_FORMAT"),
                "MANIFEST_EVIDENCE_REFS_FORMAT",
                f"evidence_refs 第 {i} 项不是对象",
                repr(ref)[:120],
            )
            continue
        claim_id = clean_str(ref.get("claim_id"))
        importance = clean_str(ref.get("importance"))
        if not claim_id:
            _emit(
                emit,
                severity_of("MANIFEST_EVIDENCE_REFS_FORMAT"),
                "MANIFEST_EVIDENCE_REFS_FORMAT",
                f"evidence_refs 第 {i} 项缺少 claim_id",
                repr(ref)[:120],
            )
            continue
        claim = state.claims.get(claim_id)
        if claim is None:
            if claim_id in state.candidates:
                _emit(
                    emit,
                    severity_of("CANDIDATE_USED_AS_EVIDENCE"),
                    "CANDIDATE_USED_AS_EVIDENCE",
                    f"manifest 引用了线索（Candidate）而不是 Claim: {claim_id}",
                    f"evidence_refs[{i}]；线索 ≠ 证据，"
                    "必须先经正式 Document + EvidenceLink 升级为 Claim",
                )
            else:
                _emit(
                    emit,
                    severity_of("EVIDENCE_REF_UNKNOWN"),
                    "EVIDENCE_REF_UNKNOWN",
                    f"manifest 引用了不存在的 Claim: {claim_id}",
                    f"evidence_refs[{i}]；claims.jsonl 中无此 claim_id",
                )
            continue
        if importance and importance != claim.materiality:
            _emit(
                emit,
                severity_of("EVIDENCE_IMPORTANCE_MISMATCH"),
                "EVIDENCE_IMPORTANCE_MISMATCH",
                f"manifest importance 与 Claim materiality 不一致: {claim_id}",
                f"manifest={importance}；claims.jsonl={claim.materiality}",
            )


def _resolve_time_model(
    *,
    state: ResearchState,
    manifest: Optional[Dict[str, Any]],
    as_of: Optional[str] = None,
    market_data_as_of: Optional[str] = None,
    generated_at: Optional[str] = None,
    research_date=None,
) -> TimeModel:
    """决定「证据时效」用哪个时点。

    优先级（后者覆盖前者）：state 字段 → manifest.meta → 显式参数。
    `research_date` 只作为旧模型的回退，新模型一律以 `as_of` 为准。
    """
    meta: Dict[str, Any] = {}
    for key in ("as_of", "market_data_as_of", "generated_at"):
        value = getattr(state, key, None)
        if value:
            meta[key] = value
    meta.update((manifest or {}).get("meta") or {})
    if research_date is not None:
        meta["research_date"] = research_date
    if as_of is not None:
        meta["as_of"] = as_of
    if market_data_as_of is not None:
        meta["market_data_as_of"] = market_data_as_of
    if generated_at is not None:
        meta["generated_at"] = generated_at
    return build_time_model(meta)


def validate_evidence(
    state: ResearchState,
    *,
    emit: Emit,
    manifest: Optional[Dict[str, Any]] = None,
    research_date: Optional[str] = None,
    as_of: Optional[str] = None,
    market_data_as_of: Optional[str] = None,
    generated_at: Optional[str] = None,
    strict: bool = True,
    store_issues: Iterable[Issue] = (),
    documents_base_dir: Optional[str] = None,
) -> Dict[str, int]:
    """校验一个研究的 Evidence 层。

    strict=False 时只做引用完整性（v2 兼容模式），语义校验降级为一条 P2 说明。
    """
    summary: Dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}

    def counting_emit(severity: str, code: str, message: str, detail: str = "") -> None:
        summary[severity] = summary.get(severity, 0) + 1
        emit(severity, code, message, detail)

    for issue in list(store_issues):
        _emit(counting_emit, issue.severity, issue.code, issue.message, issue.detail)
    for issue in state.check_integrity():
        _emit(counting_emit, issue.severity, issue.code, issue.message, issue.detail)

    if not strict:
        _emit(
            counting_emit,
            severity_of("EVIDENCE_STORE_SKIPPED"),
            "EVIDENCE_STORE_SKIPPED",
            "兼容模式：只完成 Evidence Store 引用完整性检查，未执行证据真实性/等级校验",
            "v2 manifest 不承载 Evidence 绑定关系；如需完整校验请迁移到 manifest_version=3",
        )
        return summary

    base_dir = Path(documents_base_dir) if documents_base_dir else None

    if research_date is None:
        research_date = state.research_date
    if research_date is None and manifest:
        research_date = clean_str((manifest.get("meta") or {}).get("research_date"))
    if isinstance(research_date, str):
        research_date = parse_date(research_date)

    time_model = _resolve_time_model(
        state=state,
        manifest=manifest,
        as_of=as_of,
        market_data_as_of=market_data_as_of,
        generated_at=generated_at,
        research_date=research_date,
    )

    _check_documents(state, emit=counting_emit, base_dir=base_dir, time_model=time_model)
    _check_claims(state, emit=counting_emit)
    _check_candidates(state, emit=counting_emit)
    if manifest:
        _check_manifest_refs(state, manifest, emit=counting_emit)

    _emit(
        counting_emit,
        "INFO",
        "EVIDENCE_SUMMARY",
        "Evidence 校验完成",
        f"candidates={len(state.candidates)}；documents={len(state.documents)}；"
        f"claims={len(state.claims)}；links={len(state.links)}",
    )
    return summary


def validate_evidence_store(
    state: ResearchState,
    *,
    emit: Emit,
    research_date: Optional[str] = None,
    as_of: Optional[str] = None,
    market_data_as_of: Optional[str] = None,
    generated_at: Optional[str] = None,
    documents_base_dir: Optional[str] = None,
    store_issues: Iterable[Issue] = (),
) -> Dict[str, int]:
    """只校验 Evidence Store 本身（不需要 manifest / 报告）。"""
    return validate_evidence(
        state,
        emit=emit,
        manifest=None,
        research_date=research_date,
        as_of=as_of,
        market_data_as_of=market_data_as_of,
        generated_at=generated_at,
        strict=True,
        store_issues=store_issues,
        documents_base_dir=documents_base_dir,
    )
