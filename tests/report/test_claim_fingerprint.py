# -*- coding: utf-8 -*-
"""Claim 指纹与版本漂移（v3.0.3 §4 / §12-A）。

v3.0.2 的锚点只声明 claim_id / level / status，于是还留着一条缝：三者全对，
但**结论正文已经被改写**。这组用例就是钉死这条缝。

「旧报告」在这里指：锚点没有 fingerprint 属性。它的语义是「无法对应到任何
Claim 版本」——按「锚定即声明」的同一逻辑，缺省不能等于放行，否则
「把 fingerprint 删掉」就是新的绕过路径。
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.models import Claim
from core.models.fingerprint import (
    CLAIM_FINGERPRINT_LENGTH,
    claim_fingerprint,
    claim_fingerprint_of,
    is_valid_fingerprint,
    normalize_claim_text,
)
from core.report import ReportClaimRef
from core.report.claim_parser import parse_html_claims, parse_markdown_claims
from core.validation import validate_report_claims


# --------------------------------------------------------------------- 构件


def make_claim(**overrides) -> Claim:
    data: Dict[str, Any] = {
        "claim_id": "E007",
        "claim": "液冷 / 224G 处于在研阶段",
        "category": "order",
        "level": "management_statement",
        "materiality": "critical",
        "status": "supported",
    }
    data.update(overrides)
    return Claim(**data)


def claims_of(claim: Claim) -> Dict[str, Claim]:
    return {claim.claim_id: claim}


def ref(claim: Claim, *, fingerprint: Any = "__auto__", **kw) -> ReportClaimRef:
    """构造一个锚点；默认带上**当前**版本的正确指纹。"""
    if fingerprint == "__auto__":
        fingerprint = claim_fingerprint(claim)
    kw.setdefault("text", claim.claim)
    kw.setdefault("location", "<span#1>")
    kw.setdefault("declared_level", claim.level)
    kw.setdefault("declared_status", claim.status)
    return ReportClaimRef(claim_id=claim.claim_id, declared_fingerprint=fingerprint, **kw)


def run(refs: List[ReportClaimRef], claim: Claim) -> List[Any]:
    out: List[Any] = []
    validate_report_claims(
        refs,
        claims=claims_of(claim),
        evidence_refs=None,
        emit=lambda s, c, m, d="": out.append((s, c, m, d)),
    )
    return out


def codes(refs: List[ReportClaimRef], claim: Claim) -> List[str]:
    return [c for _, c, _, _ in run(refs, claim)]


# ------------------------------------------------- 1. 指纹本身的确定性


def test_same_claim_same_fingerprint():
    a = make_claim()
    b = make_claim()
    assert claim_fingerprint(a) == claim_fingerprint(b)


def test_claim_text_changed_changes_fingerprint():
    before = claim_fingerprint(make_claim())
    after = claim_fingerprint(make_claim(claim="液冷 / 224G 已进入量产阶段"))
    assert before != after


def test_level_changed_changes_fingerprint():
    assert claim_fingerprint(make_claim()) != claim_fingerprint(make_claim(level="fact"))


def test_status_changed_changes_fingerprint():
    assert claim_fingerprint(make_claim()) != claim_fingerprint(make_claim(status="pending"))


def test_fingerprint_is_short_lowercase_hex():
    value = claim_fingerprint(make_claim())
    assert len(value) == CLAIM_FINGERPRINT_LENGTH
    assert is_valid_fingerprint(value)
    assert value == value.lower()


def test_fingerprint_is_stable_across_process_states():
    """同一组字段必须每次都算出同一个值（不能掺入时间/随机/PYTHONHASHSEED）。"""
    args = ("E007", "液冷 / 224G 处于在研阶段", "management_statement", "supported")
    assert claim_fingerprint_of(*args) == claim_fingerprint_of(*args)


# ------------------------------------------------- 2. 归一化的边界


def test_whitespace_normalization_is_stable():
    """排版差异不该改变指纹：全角空格 / 连续空格 / 换行 / 制表符。

    注意只在**原文本来就有空白**的位置替换空白形态——把换行插进
    「处于在研」中间等于改了词边界，那属于内容变更。
    """
    a = make_claim(claim="液冷 / 224G 处于在研阶段")
    b = make_claim(claim="  液冷 \t/  \u3000 224G \n 处于在研阶段  ")
    assert normalize_claim_text(b.claim) == normalize_claim_text(a.claim)
    assert claim_fingerprint(a) == claim_fingerprint(b)


def test_normalization_does_not_touch_content():
    """归一化只收敛排版：标点、大小写、词序都算内容，不能被抹平。"""
    assert normalize_claim_text("PE(TTM) 53.83x") != normalize_claim_text("PE(TTM) 53.83X")
    assert normalize_claim_text("在研阶段") != normalize_claim_text("在研")
    assert normalize_claim_text("A、B") != normalize_claim_text("A.B")


def test_category_and_materiality_do_not_affect_fingerprint():
    """报告锚点不声明分类与重要性，它们的变更不该把报告判为过期。"""
    base = make_claim()
    moved = make_claim(category="industry", materiality="normal")
    assert claim_fingerprint(base) == claim_fingerprint(moved)


# ------------------------------------------------- 3. HTML 锚点


def test_html_correct_fingerprint_parses_and_passes():
    claim = make_claim()
    fp = claim_fingerprint(claim)
    html = (
        f'<span data-claim-id="E007" data-claim-level="management_statement" '
        f'data-claim-status="supported" data-claim-fingerprint="{fp}">液冷 / 224G 处于在研阶段</span>'
    )
    refs = parse_html_claims(html)
    assert len(refs) == 1
    assert refs[0].declared_fingerprint == fp
    assert run(refs, claim) == []


def test_html_stale_fingerprint_fails():
    """**本版本的核心故障注入**：只改 Claim 正文，id / level / status 全不变。"""
    old = make_claim()
    new = make_claim(claim="液冷 / 224G 已进入量产阶段")
    html = (
        f'<span data-claim-id="E007" data-claim-level="management_statement" '
        f'data-claim-status="supported" data-claim-fingerprint="{claim_fingerprint(old)}">'
        f"液冷 / 224G 处于在研阶段</span>"
    )
    refs = parse_html_claims(html)
    assert codes(refs, new) == ["REPORT_CLAIM_REVISION_MISMATCH"]


def test_html_missing_fingerprint_fails():
    """旧报告（没有 fingerprint 属性）必须 FAIL —— 否则「删掉指纹」就是绕过路径。"""
    claim = make_claim()
    html = (
        '<span data-claim-id="E007" data-claim-level="management_statement" '
        'data-claim-status="supported">液冷 / 224G 处于在研阶段</span>'
    )
    refs = parse_html_claims(html)
    assert refs[0].declared_fingerprint is None
    assert codes(refs, claim) == ["REPORT_CLAIM_REVISION_MISMATCH"]


def test_html_uppercase_fingerprint_is_not_silently_accepted():
    """大小写敏感：`AB` 与 `ab` 是不同的字符串，不做宽容匹配。"""
    claim = make_claim()
    refs = parse_html_claims(
        f'<span data-claim-id="E007" data-claim-level="management_statement" '
        f'data-claim-status="supported" data-claim-fingerprint="{claim_fingerprint(claim).upper()}">x</span>'
    )
    assert codes(refs, claim) == ["REPORT_CLAIM_REVISION_MISMATCH"]


# ------------------------------------------------- 4. Markdown 锚点


def test_markdown_correct_fingerprint_parses_and_passes():
    claim = make_claim()
    fp = claim_fingerprint(claim)
    md = f"<!-- claim:E007 level=management_statement status=supported fingerprint={fp} -->\n液冷 / 224G 处于在研阶段。\n"
    refs = parse_markdown_claims(md)
    assert len(refs) == 1
    assert refs[0].declared_fingerprint == fp
    assert run(refs, claim) == []


def test_markdown_stale_fingerprint_fails():
    old = make_claim()
    new = make_claim(claim="液冷 / 224G 已进入量产阶段")
    md = (
        f"<!-- claim:E007 level=management_statement status=supported "
        f"fingerprint={claim_fingerprint(old)} -->\n液冷 / 224G 处于在研阶段。\n"
    )
    assert codes(parse_markdown_claims(md), new) == ["REPORT_CLAIM_REVISION_MISMATCH"]


def test_markdown_missing_fingerprint_fails():
    md = "<!-- claim:E007 level=management_statement status=supported -->\n液冷 / 224G 处于在研阶段。\n"
    assert codes(parse_markdown_claims(md), make_claim()) == ["REPORT_CLAIM_REVISION_MISMATCH"]


# ------------------------------------------------- 5. 指纹漂移不掩盖别的错


def test_revision_mismatch_coexists_with_level_mismatch():
    """指纹与等级可各自独立漂移，两条都要报——不能因为命中一条就吞掉另一条。"""
    claim = make_claim()
    refs = [
        ReportClaimRef(
            claim_id="E007",
            declared_level="fact",               # 与 Ledger 不符
            declared_status="supported",
            declared_fingerprint=claim_fingerprint(claim),
        )
    ]
    out = codes(refs, claim)
    assert "REPORT_CLAIM_LEVEL_MISMATCH" in out
    assert "REPORT_CLAIM_REVISION_MISMATCH" not in out  # 指纹是对的，不该误报


def test_revision_mismatch_reported_for_unknown_claim_only_as_unknown():
    """claim_id 都不存在时只报 UNKNOWN——没有当前版本可比，报 REVISION 会误导。"""
    refs = [ReportClaimRef(claim_id="E999", declared_fingerprint="0" * 16)]
    assert codes(refs, make_claim()) == ["REPORT_CLAIM_UNKNOWN"]
