#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_report 模板 —— HTML 报告生成器骨架（0-16 章 + 首屏四件套 + 三图）。

用法：复制为 /tmp/build_<code>_report.py，替换 TODO。**照抄华电/风华版结构再改内容**。

坑位提醒：
1. 章节 0-16 缺一即 P0：模板 assets/报告模板.md 只列到 §15，
   §16「本次研究结论发生变化的条件」必须自补。
2. 正文必须含字面标签【推断】【无法确认】各至少一处（P1）；
   必含字面短语「当前价格隐含」「证伪」「条件树」；「季度跟踪」四个字只能出现在
   跟踪表标题（正文提前出现会被 validator 的贪心正则错配）。
3. Claim 锚点由 claims.jsonl 注入：A(cid, text) 生成
   <span data-claim-id=...>，全部 claim 至少各 1 个锚点，否则 REPORT_CRITICAL_CLAIM_MISSING。
4. 生成后必做：① 抽内联 <script> 跑 node --check；② DOM/echarts 桩冒烟
   （_harness_template.js），断言 setOption 次数与数据点数。已两次踩到内联 JS 语法错。
5. 最终交付走 finish_report.py（盖章→回填→三路验收一条命令）。
"""

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
SKILL = Path.home() / "WorkBuddy/A股助手/.workbuddy/skills/a-share-stock-deep-research"
TPL = SKILL / "assets" / "报告模板.html"          # 统一版式唯一来源
KLINES = BASE.parent / "kline.js"                 # build_kline.py 产物
OUT = BASE.parent / "XX股份000000_深度研究.html"  # TODO（不含时间戳后缀，盖章时自动加）


def load_claims():
    return [json.loads(l) for l in open(BASE / "evidence" / "claims.jsonl", encoding="utf-8")]


def A(cid, text):
    """Claim 锚点：data-claim-id 由 stamp_claim_fingerprints 补指纹。"""
    return f'<span class="claim-anchor" data-claim-id="{cid}">{text}</span>'


def build_head():
    html = TPL.read_text(encoding="utf-8")
    return html[: html.index("<body")] # head + 样式


BODY = """
<!-- TODO: 照抄华电版 0-16 章结构，以下为章节骨架与必查项 -->
<h1>XX股份（000000）深度研究</h1>
<div class="fs-header">…</div><div class="fs-profile">…</div>
<div class="fs-verdict">…</div><div id="kline" class="fs-chart">…</div>

<h2>1. 核心结论</h2>
<p>{A("C_XXX", "核心结论绑定 claim")}…当前价格隐含…</p>
<h2>4. 财务</h2><p>…【推断】…</p>
<h2>7. 风险</h2><p>…证伪条件…条件树…【无法确认】…</p>
<!-- ⚠ 「季度跟踪」四字只能出现在下面这个跟踪表标题里 -->
<h2>13. 季度跟踪</h2>
<table><thead><tr><th>指标</th><th>现值</th><th>证伪/信号</th></tr></thead>
<tbody><!-- TODO: 与 manifest.quarterly_tracking 逐条一致 --></tbody></table>
<h2>14. 结论与操作建议</h2><p>…</p>
<h2>15. 最终投资研究卡</h2><table>…</table>
<h2>16. 本次研究结论发生变化的条件</h2><p>…</p>
<script>
// TODO: 照抄华电版三图初始化（K线60根/饼图/双轴柱），数据由本脚本注入
</script>
"""


def main():
    claims = load_claims()
    body = BODY
    # TODO: 注入 kline.js 数据、财务表、图表数据（照抄华电版替换函数）
    html = build_head() + "<body>" + body + "</body></html>"
    # 自检 1：0-16 章齐全
    found = sorted(int(m.group(1)) for m in re.finditer(r"<h2>\s*(\d+)\.", html))
    assert found == list(range(17)), f"章节缺失：{set(range(17)) - set(found)}"
    # 自检 2：每个 claim 至少 1 个锚点
    missing = [c["claim_id"] for c in claims
               if f'data-claim-id="{c["claim_id"]}"' not in html]
    assert not missing, f"缺锚点 Claim: {missing}"
    # 自检 3：字面标签
    for token in ["当前价格隐含", "证伪", "条件树", "【推断】", "【无法确认】"]:
        assert token in html, f"缺字面标签：{token}"
    OUT.write_text(html, encoding="utf-8")
    print(f"✅ {OUT.name}（{len(html)//1024}KB，锚点 {html.count('data-claim-id')}）")
    print("→ 下一步：node --check 内联 JS + harness 冒烟 + finish_report.py")


if __name__ == "__main__":
    main()
