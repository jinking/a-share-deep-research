#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_manifest 模板 —— research_manifest.json v3 生成器骨架（含数学自检）。

用法：复制为 /tmp/build_<code>_manifest.py，替换 TODO。
调用：python build_<code>_manifest.py "2026-09-17T10:20:14+08:00"
      （generated_at 由 finish_report.py 自动回填，这里的参数仅首版占位）

坑位提醒：
- manifest_version 必须是**整数 3**（写 "3.0" 判 -1 → 全链 FAIL）。
- meta 三时点 as_of / market_data_as_of / generated_at 缺一 = P1 TIME_MODEL_INCOMPLETE；
  走兼容路径就别声明 as_of。
- quarterly_tracking 每项只允许 indicator / current / invalidation_or_signal 三个 key。
- 长中文 note 避免 % 格式串（% 转义坑两次），一律 f-string。
- critical/major Claim（scope=report）必须全部出现在 evidence_refs。
"""

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "research_manifest.json"  # TODO: 改绝对路径

# ── 标的参数（TODO 全替换）──
CODE, NAME = "sh000000", "XX股份"
PRICE, SHARES_B = 10.00, 500.0            # 现价、总股本（亿股）
CAP = round(PRICE * SHARES_B, 2)          # 市值（亿）

SCENARIOS = {
    "neutral": {"label": "中性", "np_2027e_billion": 10.0, "pe": 25,
                "note": "TODO: 目标年净利与倍数的依据"},
    "bull":    {"label": "乐观", "np_2027e_billion": 12.0, "pe": 30, "note": "TODO"},
    "bear":    {"label": "悲观", "np_2027e_billion": 8.0,  "pe": 20, "note": "TODO"},
}


def target_price(np_b, pe):
    return round(np_b * 1e8 * pe / (SHARES_B * 1e8), 2)


def main():
    generated_at = sys.argv[1] if len(sys.argv) > 1 else "2026-01-01T00:00:00+08:00"
    # ── 数学自检：目标价必须能被净利×倍数复算出来 ──
    for k, s in SCENARIOS.items():
        tp = target_price(s["np_2027e_billion"], s["pe"])
        assert abs(tp * SHARES_B / s["pe"] - s["np_2027e_billion"]) < 0.02, k
        s["target_price"] = tp
        print(f"  {s['label']}: {s['np_2027e_billion']}亿 × {s['pe']}× = {tp} 元")

    manifest = {
        "manifest_version": 3,               # 整数！
        "meta": {
            "code": CODE, "name": NAME,
            "as_of": generated_at, "market_data_as_of": generated_at,
            "generated_at": generated_at,
            "current_price": PRICE, "shares_billion": SHARES_B,
            "market_cap_billion": CAP, "currency": "CNY",
        },
        "forecast": {  # TODO: 三情景×连续三年（2026E/2027E/2028E）
            "years": [2026, 2027, 2028],
            "scenarios": {
                k: {"years": [
                    {"year": y, "revenue_billion": 0.0, "net_profit_billion": 0.0, "eps": 0.0}
                    for y in [2026, 2027, 2028]]} for k in SCENARIOS
            },
        },
        "scenarios": {k: {"target_price": s["target_price"], "pe": s["pe"],
                          "np_2027e_billion": s["np_2027e_billion"], "note": s["note"]}
                      for k, s in SCENARIOS.items()},
        "valuation": {
            "method": "PE", "target_year": 2027,
            "implied_pe_at_current": round(CAP / (SCENARIOS["neutral"]["np_2027e_billion"]), 1),
        },
        "quarterly_tracking": [  # TODO: 8-14 项；字段名只允许这三个
            {"indicator": "TODO 跟踪指标", "current": "TODO 现值",
             "invalidation_or_signal": "TODO 证伪/信号条件"},
        ],
        "evidence_refs": [],  # TODO: critical+major（scope=report）的 claim_id 全列表
        "final": {
            "status": "回避",  # TODO
            "reason": f"TODO：三情景目标价 vs 现价（中性 {SCENARIOS['neutral']['target_price']}）",
        },
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"✅ {OUT}（version={manifest['manifest_version']}）")


if __name__ == "__main__":
    main()
