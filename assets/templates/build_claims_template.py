#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_claims 模板 —— 新标的 claims.jsonl 生成器骨架。

用法：复制本文件为 /tmp/build_<code>_claims.py，把 TODO 处替换为新标的数据。
纪律：**照抄结构，不要凭记忆重写**（华电凭记忆重写 evidence 结构 → 8 次修复多花 6 分钟）。

坑位提醒：
- category 是封闭枚举：financial/order/customer/industry/valuation/governance/risk/market/other
  自造值（segment/technology/...）会被 validate() **静默丢弃**，claims.jsonl 缺行且无报错。
- 落盘后必须复核行数（Edit/写盘偶发不落地）。
"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent          # evidence/ 目录
# TODO: 改为 research_<code>/evidence 的绝对路径

COMPANY = "XX股份"                               # TODO
CODE = "000000"                                  # TODO


def C(claim_id, claim, level, materiality, category, *, scope="report", status="supported"):
    """level: fact|inference；materiality: critical|major|normal；
    status: supported|unconfirmed——推断类 Claim 用 status='unconfirmed' + level='inference'。"""
    return {
        "claim_id": claim_id, "claim": claim, "level": level,
        "materiality": materiality, "category": category,
        "scope": scope, "status": status, "company": COMPANY, "code": CODE,
    }


CLAIMS = [
    # ── critical（确认级：必须一手来源 + direct 链接 + 摘录 verified）──
    C("C_FIN_H1_REV", "2026H1 营收 XX.XX 亿元（同比 +X.XX%）", "fact", "critical", "financial"),
    C("C_FIN_H1_NP",  "2026H1 归母净利润 XX.XX 亿元（同比 +X.XX%）", "fact", "critical", "financial"),
    # ── major（只强制绑定；scope=report 必须进 manifest.evidence_refs）──
    C("C_VAL_PE_TTM", "现价对应 PE(TTM) 约 XX 倍", "fact", "major", "valuation"),
    # ── 推断类 ──
    C("C_FIN_Q2_INFER", "2026Q2 单季归母约 X.X 亿元（同比约 +XX%）——由 H1 减 Q1 推算",
      "inference", "major", "financial", status="unconfirmed"),
    # TODO: 按 SOP 结构补齐 40-55 条（财务/订单/行业/估值/治理/风险/市场）

    C("C_VAL_TARGET_2027E", "中性情景 2027E 目标价 XX.XX 元", "inference", "critical", "valuation",
      status="unconfirmed"),
]


def main():
    out = BASE / "claims.jsonl"
    lines = [json.dumps(c, ensure_ascii=False) for c in CLAIMS]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 落盘复核（写盘偶发不落地，必须复核）
    n = len(out.read_text(encoding="utf-8").strip().splitlines())
    assert n == len(CLAIMS), f"落盘行数 {n} != 期望 {len(CLAIMS)}"
    print(f"✅ claims.jsonl：{n} 条（critical={sum(1 for c in CLAIMS if c['materiality']=='critical')}）")


if __name__ == "__main__":
    main()
