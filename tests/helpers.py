# -*- coding: utf-8 -*-
"""测试公共构件：构造「合法产物」与「定向破坏」的辅助函数。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceStore, sha256_file
from core.issue import Issue
from core.models import (
    Claim,
    EvidenceCandidate,
    EvidenceLink,
    ResearchState,
    SourceDocument,
    make_candidate_id,
)
from core.validation import validate_evidence

RESEARCH_DATE = "2026-09-14"
AS_OF = "2026-09-15T09:00:00+08:00"
MARKET_AS_OF = "2026-09-14T15:00:00+08:00"
GENERATED_AT = "2026-09-15T09:05:32+08:00"


# --------------------------------------------------------------------------- #
# Evidence 侧构件
# --------------------------------------------------------------------------- #


def make_document(document_id: str = "DOC_h1report", **overrides) -> SourceDocument:
    data: Dict[str, Any] = {
        "document_id": document_id,
        "source_type": "interim_report",
        "title": "意华股份2026年半年度报告",
        "issuer": "意华股份",
        "published_at": "2026-08-25",
        "retrieved_at": "2026-09-15T10:30:00+08:00",
        "url": "https://www.cninfo.com.cn/002897/2026H1.pdf",
        "local_path": None,
        "sha256": None,
        "source_group": "CNINFO_002897_2026H1",
        "page_count": 168,
        "sections": ["主要会计数据", "主营业务分行业情况"],
    }
    data.update(overrides)
    return SourceDocument(**data)


def make_claim(claim_id: str = "C_FIN_REV_2026H1", **overrides) -> Claim:
    data: Dict[str, Any] = {
        "claim_id": claim_id,
        "claim": "2026H1 营业收入 28.63 亿元（同比 -5.97%）",
        "category": "financial",
        "level": "fact",
        "materiality": "critical",
        "status": "supported",
    }
    data.update(overrides)
    return Claim(**data)


def make_link(claim_id: str = "C_FIN_REV_2026H1", document_id: str = "DOC_h1report", **overrides) -> EvidenceLink:
    data: Dict[str, Any] = {
        "evidence_id": f"EV_{claim_id}_01",
        "claim_id": claim_id,
        "document_id": document_id,
        "page": 12,
        "section": "主要会计数据",
        "evidence_text": "营业收入 2,863,000,000 元，同比下降 5.97%",
        "support_type": "direct",
        "confidence": 1.0,
    }
    data.update(overrides)
    return EvidenceLink(**data)


def make_candidate(candidate_id: str = "CAN_test0001", **overrides) -> EvidenceCandidate:
    data: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "source_type": "media",
        "title": "财联社：意华股份高速连接器进展",
        "discovered_at": "2026-09-14T20:10:00+08:00",
        "status": "new",
        "claim_id": None,
        "url": "https://www.cls.cn/detail/123",
        "snippet": "媒体口径，非公司披露",
        "provider": "neodata",
        "upstream_hint": "CLS_20260915_001",
        "promoted_document_id": None,
        "note": None,
    }
    data.update(overrides)
    return EvidenceCandidate(**data)


def base_state() -> ResearchState:
    """一个完全合法的研究证据状态：不产生任何 P0/P1。"""
    state = ResearchState(research_date=RESEARCH_DATE)
    state.add_document(make_document())
    state.add_document(
        make_document(
            "DOC_aichip_ir",
            source_type="company_ir",
            title="深交所互动易公司回复",
            published_at="2026-09-14",
            url="https://irm.cninfo.com.cn/002897/qa",
            source_group="SZSE_IR_002897",
            page_count=None,
            sections=["投资者互动"],
        )
    )
    state.add_document(
        make_document(
            "DOC_cls_media",
            source_type="media",
            title="财联社：意华股份高速连接器进展",
            published_at="2026-09-14",
            url="https://www.cls.cn/detail/123",
            source_group="CLS_20260915_001",
            page_count=None,
            sections=None,
        )
    )
    state.add_claim(make_claim())
    state.add_claim(
        make_claim(
            "C_ORDER_224G_STATUS",
            claim="液冷 CAGE 与 224G 高速连接器处于送样阶段，尚未批量供货",
            category="order",
            level="management_statement",
            materiality="major",
            status="supported",
        )
    )
    state.add_claim(
        make_claim(
            "C_VAL_CONSENSUS",
            claim="机构一致预期 2026E 归母 4.22 亿元",
            category="valuation",
            level="third_party_consensus",
            materiality="normal",
            status="supported",
        )
    )
    state.add_link(make_link())
    state.add_link(
        make_link(
            "C_ORDER_224G_STATUS",
            "DOC_aichip_ir",
            page=None,
            section="投资者互动",
            evidence_text="相关产品目前处于送样阶段",
        )
    )
    state.add_link(
        make_link(
            "C_VAL_CONSENSUS",
            "DOC_cls_media",
            page=None,
            section="正文",
            evidence_text="9 家机构一致预期归母 4.22 亿元",
            support_type="context",
        )
    )
    return state


def collect(state: ResearchState, **kwargs) -> List[Issue]:
    """跑一遍 Evidence Validator，返回全部 Issue。"""
    bucket: List[Issue] = []
    kwargs.setdefault("research_date", RESEARCH_DATE)
    validate_evidence(state, emit=lambda s, c, m, d="": bucket.append(Issue(s, c, m, d)), **kwargs)
    return bucket


def codes(state: ResearchState, **kwargs) -> List[str]:
    return [i.code for i in collect(state, **kwargs)]


def severities(state: ResearchState, **kwargs) -> Dict[str, int]:
    out = {"P0": 0, "P1": 0, "P2": 0}
    for issue in collect(state, **kwargs):
        out[issue.severity] = out.get(issue.severity, 0) + 1
    return out


def with_override(state: ResearchState, **kwargs) -> ResearchState:
    """深拷贝后替换字段，避免用例之间互相污染。"""
    clone = copy.deepcopy(state)
    for key, value in kwargs.items():
        setattr(clone, key, value)
    return clone


# --------------------------------------------------------------------------- #
# Manifest 侧构件（v2，数学自洽）
# --------------------------------------------------------------------------- #


def valid_manifest() -> Dict[str, Any]:
    return {
        "meta": {
            "company": "测试公司",
            "code": "002897.SZ",
            "research_date": RESEARCH_DATE,
            "current_price": 71.39,
            "shares_billion": 1.9386,
            "market_cap_billion": 138.40,
        },
        "forecast": {
            "悲观": [
                {"year": 2026, "revenue_billion": 60.0, "net_profit_billion": 2.80, "eps": 1.44},
                {"year": 2027, "revenue_billion": 62.0, "net_profit_billion": 3.30, "eps": 1.70},
                {"year": 2028, "revenue_billion": 63.0, "net_profit_billion": 3.55, "eps": 1.83},
            ],
            "中性": [
                {"year": 2026, "revenue_billion": 65.0, "net_profit_billion": 3.20, "eps": 1.65},
                {"year": 2027, "revenue_billion": 76.0, "net_profit_billion": 4.60, "eps": 2.37},
                {"year": 2028, "revenue_billion": 86.0, "net_profit_billion": 5.80, "eps": 2.99},
            ],
            "乐观": [
                {"year": 2026, "revenue_billion": 72.0, "net_profit_billion": 4.20, "eps": 2.17},
                {"year": 2027, "revenue_billion": 87.0, "net_profit_billion": 6.20, "eps": 3.20},
                {"year": 2028, "revenue_billion": 103.0, "net_profit_billion": 8.00, "eps": 4.13},
            ],
        },
        "valuation": {
            "method": "PE",
            "target_year": 2026,
            "linked_metric": "net_profit_billion",
            "linked_value": 3.20,
            "multiple": 35,
            "equity_value_billion": 112.0,
            "price_per_share": 57.8,
        },
        "sotp": {
            "target_year": 2026,
            "parts": [
                {"name": "主业", "net_profit_billion": 3.20, "multiple": 35, "equity_value_billion": 112.0,
                 "include_in_profit_reconciliation": True},
                {"name": "期权业务", "net_profit_billion": None, "multiple": None, "equity_value_billion": 0.0,
                 "include_in_profit_reconciliation": False},
            ],
            "reconciled_total_net_profit_billion": 3.20,
            "total_equity_value_billion": 112.0,
        },
        "evidence": [
            {
                "claim_id": "E001",
                "claim": "示例：2026H1 营业收入 28.63 亿元",
                "level": "事实",
                "source_type": "interim_report",
                "source_title": "测试公司 2026 年半年度报告",
                "source_date": "2026-08-25",
                "source_ref": "半年报·主要会计数据",
            }
        ],
        "quarterly_tracking": [
            {"indicator": f"指标{i}", "latest": "", "invalidation_or_signal": "阈值"}
            for i in range(1, 11)
        ],
        "final": {
            "status": "观察",
            "core_invalidation": ["证伪1", "证伪2", "证伪3"],
        },
    }


def valid_manifest_v3() -> Dict[str, Any]:
    data = valid_manifest()
    data["manifest_version"] = 3
    data["evidence_refs"] = [
        {"claim_id": "C_FIN_REV_2026H1", "importance": "critical"},
        {"claim_id": "C_ORDER_224G_STATUS", "importance": "major"},
    ]
    return data


def v3_state() -> ResearchState:
    """与 valid_manifest_v3.evidence_refs 对齐、且完全合法的证据状态。"""
    state = ResearchState(research_date=RESEARCH_DATE)
    state.add_document(make_document())
    state.add_document(
        make_document(
            "DOC_aichip_ir",
            source_type="company_ir",
            title="深交所互动易公司回复",
            published_at="2026-09-14",
            url="https://irm.cninfo.com.cn/002897/qa",
            source_group="SZSE_IR_002897",
            page_count=None,
            sections=["投资者互动"],
        )
    )
    state.add_claim(make_claim())
    state.add_claim(
        make_claim(
            "C_ORDER_224G_STATUS",
            claim="液冷 CAGE 与 224G 高速连接器处于送样阶段",
            category="order",
            level="management_statement",
            materiality="major",
        )
    )
    state.add_link(make_link())
    state.add_link(
        make_link(
            "C_ORDER_224G_STATUS",
            "DOC_aichip_ir",
            page=None,
            section="投资者互动",
            evidence_text="相关产品目前处于送样阶段",
        )
    )
    return state


def run_legacy_manifest_validator(data: Dict[str, Any]) -> List[str]:
    """直接调用 validate_report.py 内的数学/结构校验，返回错误码列表。"""
    module = legacy_module()

    findings: List[Any] = []
    module.validate_manifest(copy.deepcopy(data), findings)
    return [f.code for f in findings if f.severity in {"P0", "P1"}]


def legacy_module():
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("legacy_validator", root / "scripts" / "validate_report.py")
    module = importlib.util.module_from_spec(spec)
    # dataclass 装饰器会通过 sys.modules 反查模块命名空间，必须先注册
    sys.modules["legacy_validator"] = module
    spec.loader.exec_module(module)
    return module


def write_store(tmp_path, *, with_files: bool = True, **document_overrides) -> EvidenceStore:
    """在磁盘上建一个真实可读的 Evidence Store（含原始文件与正确 hash）。"""
    store = EvidenceStore.init(tmp_path / "evidence")
    raw = store.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    if with_files:
        (raw / "2026H1.txt").write_text("营业收入 2,863,000,000 元", encoding="utf-8")
    doc = store.register_document(
        source_type="interim_report",
        title="测试公司 2026 年半年度报告",
        issuer="测试公司",
        published_at="2026-08-25",
        url="https://www.cninfo.com.cn/002897/2026H1.pdf",
        local_path="raw/2026H1.txt" if with_files else None,
        source_group="CNINFO_002897_2026H1",
        page_count=168,
        **document_overrides,
    )
    store.add_claim(make_claim())
    store.add_link(
        make_link(document_id=doc.document_id),
    )
    store.save()
    return store


def json_roundtrip(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# 报告侧构件（用于验证 0–16 章等结构规则）
# --------------------------------------------------------------------------- #


def minimal_report_html(
    *,
    chapters=None,
    scenarios=("悲观", "中性", "乐观"),
    years=(2026, 2027, 2028),
    tracker_rows: int = 12,
    phrases=("当前价格隐含", "证伪", "条件树"),
    labels=("事实", "管理层", "推断", "假设", "无法确认"),
) -> str:
    chapters = list(range(17)) if chapters is None else list(chapters)
    parts = ["<html><body>"]
    for n in chapters:
        parts.append(f"<h2>{n} 第{n}章</h2><p>正文</p>")
    parts.append("<p>" + " ".join(scenarios) + "情景</p>")
    parts.append("<p>" + " ".join(f"{y}E" for y in years) + "</p>")
    parts.append("<h3>季度跟踪表</h3><table>")
    for i in range(tracker_rows):
        parts.append(f"<tr><td>指标{i+1}</td><td>值</td><td>阈值</td></tr>")
    parts.append("</table>")
    parts.append("<p>" + " ".join(phrases) + "</p>")
    parts.append("<p>" + " ".join(labels) + "</p>")
    parts.append("</body></html>")
    return "".join(parts)


def report_error_codes(tmp_path, html: str) -> List[str]:
    """对一段 HTML 跑 report 结构检查，返回 P0/P1 错误码。"""
    module = legacy_module()
    path = Path(tmp_path) / "report.html"
    path.write_text(html, encoding="utf-8")
    raw, text = module.report_text(path)
    findings: List[Any] = []
    module.validate_report_structure(path, raw, text, findings, strict_manifest_expected=True)
    return [f.code for f in findings if f.severity in {"P0", "P1"}]

