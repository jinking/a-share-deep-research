# -*- coding: utf-8 -*-
"""报告 Claim 锚点解析器测试（v3.0.2 §5 / §15-A）。

12 个用例，覆盖 HTML / Markdown 两种语法，以及各种畸形锚点——
畸形锚点必须**被解析出来**（哪怕 claim_id 为空、level 非法），
因为「裁决」属于 validator，「解析」只负责别漏东西。
"""

from __future__ import annotations

from core.report import parse_html_claims, parse_markdown_claims, parse_report_claims, visible_text


# ---------------------------------------------------------------- A1 HTML 正常


def test_html_single_claim():
    raw = """
    <p>公司新品进展：</p>
    <span data-claim-id="E007"
          data-claim-level="management_statement"
          data-claim-status="supported">224G 产品仍处于在研阶段</span>
    <p>后续跟踪。</p>
    """
    refs = parse_html_claims(raw)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.claim_id == "E007"
    assert ref.declared_level == "management_statement"
    assert ref.declared_status == "supported"
    assert ref.text == "224G 产品仍处于在研阶段"
    assert ref.syntax == "html"
    assert ref.location


def test_html_multiple_claims():
    raw = """
    <div>
      <span data-claim-id="E001">营收 28.63 亿元</span>
      <span data-claim-id="E002" data-claim-level="fact">连接器 8.22 亿元</span>
      <span data-claim-id="E007" data-claim-status="supported">224G 在研</span>
    </div>
    """
    refs = parse_html_claims(raw)
    assert [r.claim_id for r in refs] == ["E001", "E002", "E007"]
    assert refs[0].text == "营收 28.63 亿元"


# ---------------------------------------------------------------- A3 重复 Claim


def test_repeated_claim_is_kept_twice():
    """同一 Claim 在报告里出现多次是允许的（§15-B「同一 Claim 多处出现允许」），
    解析器必须把每一处都返回，而不是去重。"""
    raw = """
    <p><span data-claim-id="E007">在研</span></p>
    <p>风险章节再次提及：<span data-claim-id="E007">仍处研发阶段</span></p>
    """
    refs = parse_html_claims(raw)
    assert len(refs) == 2
    assert {r.claim_id for r in refs} == {"E007"}
    assert refs[0].location != refs[1].location


# ---------------------------------------------------------------- A4 空 Claim


def test_html_missing_claim_id_is_parsed_not_dropped():
    refs = parse_html_claims('<span data-claim-level="fact">没有 id 的锚点</span>')
    assert len(refs) == 1
    assert refs[0].claim_id == ""


def test_html_empty_claim_id_value():
    refs = parse_html_claims('<span data-claim-id="">空值</span>')
    assert len(refs) == 1
    assert refs[0].claim_id == ""


# ------------------------------------------------------------ A5/A6 非法枚举


def test_html_invalid_level_and_status_are_preserved_verbatim():
    raw = '<span data-claim-id="E001" data-claim-level="facts" data-claim-status="OK">x</span>'
    ref = parse_html_claims(raw)[0]
    assert ref.declared_level == "facts"
    assert ref.declared_status == "OK"


# ---------------------------------------------------------------- A7 嵌套标签


def test_html_nested_same_tag():
    raw = """
    <span data-claim-id="E001">营收 <span class="num">28.63</span> 亿元，<b>同比 -5.97%</b></span>
    """
    refs = parse_html_claims(raw)
    assert len(refs) == 1
    assert refs[0].text == "营收 28.63 亿元，同比 -5.97%"


def test_html_attribute_order_does_not_matter():
    raw = '<span class="tag" data-claim-status="supported" data-claim-id="E009" data-claim-level="fact">分红</span>'
    ref = parse_html_claims(raw)[0]
    assert ref.claim_id == "E009"
    assert ref.declared_level == "fact"
    assert ref.declared_status == "supported"


# ---------------------------------------------------------------- A8 表格 Claim


def test_html_table_cell_claim():
    raw = """
    <table><tr><td>液冷产品</td>
    <td><span data-claim-id="E007" data-claim-level="management_statement">在研 / 已进入实质性开发阶段</span></td>
    <td>无量产时间表</td></tr></table>
    """
    refs = parse_html_claims(raw)
    assert len(refs) == 1
    assert refs[0].text == "在研 / 已进入实质性开发阶段"


# -------------------------------------------------------------- A9 callout Claim


def test_html_callout_claim_with_single_quotes():
    raw = "<div class='callout'><p><span data-claim-id='C_PE_TTM_20260914' data-claim-level='unconfirmed' data-claim-status='pending'>第三方口径约 53.8×</span></p></div>"
    refs = parse_html_claims(raw)
    assert len(refs) == 1
    assert refs[0].claim_id == "C_PE_TTM_20260914"
    assert refs[0].text == "第三方口径约 53.8×"


# ------------------------------------------------------ A10 多个 Claim 同一块


def test_html_multiple_claims_in_one_block():
    raw = """
    <p>
      <span data-claim-id="E001">营收 28.63 亿元</span> /
      <span data-claim-id="E004" data-claim-level="fact">经营现金流 2.70 亿元</span>
    </p>
    """
    refs = parse_html_claims(raw)
    assert [r.claim_id for r in refs] == ["E001", "E004"]
    assert refs[1].text == "经营现金流 2.70 亿元"


# ----------------------------------------------------------- A2 Markdown 正常


def test_markdown_standard_syntax():
    md = """## 1. 核心结论

<!-- claim:E007 level=management_statement status=supported -->
224G 产品仍处于在研阶段。

下一段。
"""
    refs = parse_markdown_claims(md)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.claim_id == "E007"
    assert ref.declared_level == "management_statement"
    assert ref.declared_status == "supported"
    assert ref.text == "224G 产品仍处于在研阶段。"
    assert ref.syntax == "markdown"
    assert ref.location == "line 3"


def test_markdown_inline_comment():
    md = "PE(TTM) <!-- claim:C_PE_TTM_20260914 level=unconfirmed status=pending --> 约 53.8×\n"
    ref = parse_markdown_claims(md)[0]
    assert ref.claim_id == "C_PE_TTM_20260914"
    assert ref.text == "PE(TTM) 约 53.8×"


def test_markdown_without_level_status():
    md = "<!-- claim:E001 -->\n2026H1 营业收入 28.63 亿元。\n"
    ref = parse_markdown_claims(md)[0]
    assert ref.claim_id == "E001"
    assert ref.declared_level is None
    assert ref.declared_status is None
    assert ref.text == "2026H1 营业收入 28.63 亿元。"


# ------------------------------------------------------------ A11 连续块


def test_markdown_consecutive_blocks():
    md = """<!-- claim:E001 -->
2026H1 营业收入 28.63 亿元。

<!-- claim:E004 level=fact -->
2026H1 经营现金流 2.70 亿元。
"""
    refs = parse_markdown_claims(md)
    assert [r.claim_id for r in refs] == ["E001", "E004"]
    assert refs[0].text == "2026H1 营业收入 28.63 亿元。"
    assert refs[1].text == "2026H1 经营现金流 2.70 亿元。"


# ------------------------------------------------------------ A12 无 Claim 报告


def test_report_without_any_claim_returns_empty():
    html = "<html><body><h2>1. 核心结论</h2><p>纯文字，没有锚点。</p></body></html>"
    assert parse_report_claims(html) == []
    assert parse_report_claims("# 标题\n\n正文。\n") == []


def test_plain_html_comment_is_not_a_claim():
    raw = "<html><!-- 普通注释：不是锚点 --><p>x</p></html>"
    assert parse_html_claims(raw) == []
    assert parse_markdown_claims(raw) == []


# ------------------------------------------------------------ 统一入口


def test_unified_entry_merges_both_syntaxes():
    raw = (
        '<span data-claim-id="E001">营收</span>\n'
        "<!-- claim:E004 level=fact -->\n经营现金流。\n"
    )
    refs = parse_report_claims(raw)
    assert [r.claim_id for r in refs] == ["E001", "E004"]


def test_visible_text_unescapes_and_collapses():
    assert visible_text("<b>营收</b>&nbsp;28.63&nbsp;亿元\n  (同比 -5.97%)") == "营收 28.63 亿元 (同比 -5.97%)"


def test_self_closing_and_void_elements_do_not_break_scanning():
    raw = '<img src="x.png"><span data-claim-id="E001">甲</span>'
    refs = parse_html_claims(raw)
    assert len(refs) == 1
    assert refs[0].text == "甲"
