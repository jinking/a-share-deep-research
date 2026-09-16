#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨产物一致性校验（v3.0.2 §6）：报告 ↔ Claim Ledger ↔ manifest.evidence_refs。

为什么需要它：v3.0/v3.0.1 让「证据库」变得可信，但最终交付给人的报告与证据库之间
**没有可校验的连接**。于是出现了 v3.0.2 §2 的真实案例——Ledger 已把「送样阶段」
纠正为「在研」、已把 PE(TTM) 降级为 unconfirmed/pending，HTML 却照旧把这些当事实写。

本模块只做**显式 metadata 一致性**，第一版不做语气/语义判断（§6 末段）：

    REPORT_CLAIM_UNKNOWN             P0  报告引用了不存在的 Claim
    REPORT_PENDING_CLAIM_ASSERTED    P0  pending 的 Claim 被当成确定性事实
    REPORT_CLAIM_LEVEL_MISMATCH      P0  报告声明的 level 与 Ledger 不一致
    REPORT_UNCONFIRMED_AS_FACT       P0  未确认等级被写成 fact / confirmed_*
    REPORT_CLAIM_STATUS_MISMATCH     P1  报告声明的 status 与 Ledger 不一致
    REPORT_CRITICAL_CLAIM_MISSING    P1  critical Claim 在报告里没有落点

「缺 claim_id / level 写成非法值」这两类畸形锚点不另立错误码，复用上表中的
MISMATCH / UNKNOWN —— 错误码要稳定，不能为每个畸形形态长一个新码。畸形锚点与
Ledger 必然对不上，因此一定会被这两条抓到（详见 references/报告Claim绑定规范.md）。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from ..models.claim import PRIMARY_REQUIRED_LEVELS, Claim
from ..report.models import ReportClaimRef
from .codes import severity_of

__all__ = [
    "UNCONFIRMED_FAMILY",
    "CONFIRMED_FACT_LEVELS",
    "ASSERTIVE_STATUSES",
    "validate_report_claims",
    "critical_claims_of",
]

Emit = Callable[..., None]

# 「未确认」家族：这些等级不存在「已确认」的读法，一旦被写成事实即冲突
UNCONFIRMED_FAMILY = frozenset({"assumption", "unconfirmed", "third_party_consensus"})

# 报告若这样声明，等于在说「这是事实/已确认」
CONFIRMED_FACT_LEVELS = frozenset({"fact"}) | PRIMARY_REQUIRED_LEVELS

# 「肯定式」状态：把它们用在非 supported 的 Claim 上就是过度声明
ASSERTIVE_STATUSES = frozenset({"supported", "partially_supported"})


def critical_claims_of(evidence_refs: Optional[Iterable[Mapping[str, Any]]]) -> List[str]:
    """从 manifest.evidence_refs 里取出所有 importance=critical 的 claim_id（保序去重）。"""
    out: List[str] = []
    for ref in evidence_refs or []:
        if not isinstance(ref, Mapping):
            continue
        if str(ref.get("importance") or "").strip() != "critical":
            continue
        claim_id = str(ref.get("claim_id") or "").strip()
        if claim_id and claim_id not in out:
            out.append(claim_id)
    return out


def validate_report_claims(
    refs: Sequence[ReportClaimRef],
    *,
    claims: Mapping[str, Claim],
    evidence_refs: Optional[Iterable[Mapping[str, Any]]] = None,
    emit: Emit,
) -> Dict[str, int]:
    """校验报告中的 Claim 锚点与 Claim Ledger 是否一致。

    返回与其它校验层同构的 `{"P0": n, "P1": n, "P2": n}` 统计。
    """
    summary: Dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}

    def report(severity: str, code: str, message: str, detail: str = "") -> None:
        summary[severity] = summary.get(severity, 0) + 1
        emit(severity, code, message, detail)

    anchored: List[str] = []

    for ref in refs:
        claim_id = (ref.claim_id or "").strip()
        if not claim_id or claim_id not in claims:
            report(
                severity_of("REPORT_CLAIM_UNKNOWN"),
                "REPORT_CLAIM_UNKNOWN",
                f"报告引用了不存在的 Claim: {claim_id or '(缺 claim_id)'}",
                f"{ref.location}；{ref.syntax}；锚点文本={ref.text[:60]!r}；"
                "claims.jsonl 中无此 claim_id（锚点缺 claim_id 也归此类）",
            )
            continue

        claim = claims[claim_id]
        if claim_id not in anchored:
            anchored.append(claim_id)

        # ---- level ----
        declared_level = ref.effective_level
        if claim.level in UNCONFIRMED_FAMILY and declared_level in CONFIRMED_FACT_LEVELS:
            report(
                severity_of("REPORT_UNCONFIRMED_AS_FACT"),
                "REPORT_UNCONFIRMED_AS_FACT",
                f"未确认的 Claim 在报告里被写成了事实: {claim_id}",
                f"{ref.location}；Ledger level={claim.level}；报告声明={declared_level}"
                + ("（锚点未声明 level，按缺省『事实』解读）" if not ref.declared_level else ""),
            )
        elif declared_level != claim.level:
            report(
                severity_of("REPORT_CLAIM_LEVEL_MISMATCH"),
                "REPORT_CLAIM_LEVEL_MISMATCH",
                f"报告声明的证据等级与 Claim Ledger 不一致: {claim_id}",
                f"{ref.location}；Ledger level={claim.level}；报告声明={declared_level}",
            )

        # ---- status ----
        # 先看「有没有过度声明」：非 supported 的 Claim 被当成肯定式结论
        if claim.status != "supported" and ref.effective_status in ASSERTIVE_STATUSES:
            if claim.status == "pending":
                report(
                    severity_of("REPORT_PENDING_CLAIM_ASSERTED"),
                    "REPORT_PENDING_CLAIM_ASSERTED",
                    f"pending 的 Claim 在报告里被当成确定性事实: {claim_id}",
                    f"{ref.location}；Ledger status=pending；报告声明={ref.effective_status}"
                    + (
                        "（锚点未声明 status，按缺省『supported』解读）"
                        if not ref.declared_status
                        else ""
                    )
                    + "；请改为显式声明 status=pending，或补齐证据后升级 Claim",
                )
            else:
                report(
                    severity_of("REPORT_CLAIM_STATUS_MISMATCH"),
                    "REPORT_CLAIM_STATUS_MISMATCH",
                    f"报告声明的状态与 Claim Ledger 不一致: {claim_id}",
                    f"{ref.location}；Ledger status={claim.status}；报告声明={ref.effective_status}",
                )
            continue

        if ref.effective_status != claim.status:
            report(
                severity_of("REPORT_CLAIM_STATUS_MISMATCH"),
                "REPORT_CLAIM_STATUS_MISMATCH",
                f"报告声明的状态与 Claim Ledger 不一致: {claim_id}",
                f"{ref.location}；Ledger status={claim.status}；报告声明={ref.effective_status}",
            )

    # ---- critical Claim 必须至少有一个落点 ----
    for claim_id in critical_claims_of(evidence_refs):
        if claim_id in anchored:
            continue
        claim = claims.get(claim_id)
        report(
            severity_of("REPORT_CRITICAL_CLAIM_MISSING"),
            "REPORT_CRITICAL_CLAIM_MISSING",
            f"critical Claim 在报告里没有任何落点: {claim_id}",
            f"manifest.evidence_refs importance=critical；"
            f"Claim={'存在' if claim is not None else '不存在'}；"
            "请用 data-claim-id / <!-- claim:... --> 把结论锚回 Claim",
        )

    return summary
