#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交叉验证工具 —— 融合取数流程的第⑤步

用法:
    # 方式1: 交互式（推荐，把搜索到的数字粘进来）
    python3 cross_validate.py research_sz002475

    # 方式2: 用 JSON 文件批量验证
    python3 cross_validate.py research_sz002475 --json my_checks.json

my_checks.json 格式:
{
  "2025年营业收入(亿)": 3323.44,
  "2025年归母净利润(亿)": 166.00,
  "2026H1营业收入(亿)": 1745.04
}

作用:
    把「搜索侧」拿到的数字与「技能侧」已落盘的数据比对，
    自动标记一致 / 不一致 / 技能侧缺失（需以搜索为准）。

为什么需要这一步（来自立讯精密实测教训）:
    单一数据源会出现幻觉。技能侧与搜索侧交叉验证后，
    14项关键指标全部一致 → 数据可信度从"中"提升到"极高"。
    同时能发现技能侧的缺失项（如2026H1、股权质押）。
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path


def load_skill_data(outdir):
    """加载技能侧数据，构建 {指标名: 数值} 字典"""
    outdir = Path(outdir)
    data = {}

    # 历史财务
    f = outdir / "01_历史财务.csv"
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                y = row["年份"]
                rev = row.get("营业收入(亿)")
                npp = row.get("归母净利润(亿)")
                rd = row.get("研发费用(亿)")
                data[f"{y}年营业收入(亿)"] = rev
                data[f"{y}年归母净利润(亿)"] = npp
                data[f"{y}年研发费用(亿)"] = rd
                # 常见别名，提升匹配命中率
                if rev not in (None, ""):
                    data[f"{y}年营收(亿)"] = rev
                    data[f"{y}年收入(亿)"] = rev
                    data[f"{y}年营业总收入(亿)"] = rev
                if npp not in (None, ""):
                    data[f"{y}年归母(亿)"] = npp
                    data[f"{y}年归母净利(亿)"] = npp
                    data[f"{y}年净利润(亿)"] = npp
                if rd not in (None, ""):
                    data[f"{y}年研发(亿)"] = rd

    # 资产负债
    f = outdir / "02_资产负债关键项.csv"
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                period = row.get("报告期", "")
                y = period[:4] if period else ""
                data[f"{row['科目']}(亿)"] = row.get("金额(亿元)")
                if y:
                    data[f"{y}年{row['科目']}(亿)"] = row.get("金额(亿元)")

    # 现金流
    f = outdir / "03_现金流.csv"
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                period = row.get("报告期", "")
                y = period[:4] if period else ""
                data[f"{row['科目']}(亿)"] = row.get("金额(亿元)")
                if y:
                    data[f"{y}年{row['科目']}(亿)"] = row.get("金额(亿元)")

    return {k: v for k, v in data.items() if v not in (None, "", "0")}


def to_num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def fuzzy_find(skill_data, key):
    """模糊匹配指标名（去除空格/括号差异）"""
    norm = lambda s: re.sub(r"[\s（）()]", "", str(s))
    target = norm(key)
    # 1) 精确
    if key in skill_data:
        return key, skill_data[key]
    # 2) 归一化后完全相同
    for k, v in skill_data.items():
        if norm(k) == target:
            return k, v
    # 3) 同一年份+同一指标语义（如"2025年营收"→"2025年营业收入"）
    #    要求年份和数字/量词都对齐，避免"营收"错配到"营业收入同比"
    year_m = re.search(r"(20\d{2})", target)
    if year_m:
        year = year_m.group(1)
        cands = []
        for k, v in skill_data.items():
            nk = norm(k)
            if not nk.startswith(year):
                continue
            # 指标主体部分（去掉年份前缀）
            kt, tt = nk[len(year):], target[len(year):]
            # 只在"单位/括号"等价时视为同一指标，禁止"同比"类衍生指标混入
            if ("同比" in kt) != ("同比" in tt):
                continue
            if kt == tt or (kt.startswith(tt) and len(kt) - len(tt) <= 2):
                cands.append((k, v))
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            # 多个候选取最短的（最贴近原指标）
            cands.sort(key=lambda x: len(norm(x[0])))
            return cands[0]
    return None, None


def validate(outdir, checks, tol=0.02):
    """执行交叉验证"""
    skill_data = load_skill_data(outdir)

    print("=" * 74)
    print("【交叉验证】搜索侧 vs 技能侧")
    print("=" * 74)
    print(f"技能侧已加载 {len(skill_data)} 个指标\n")
    print(f"{'指标':<30} {'搜索值':>12} {'技能值':>12}  {'结论'}")
    print("-" * 74)

    stats = {"一致": 0, "不一致": 0, "技能侧缺失": 0}
    rows = []

    for key, val in checks.items():
        s_num = to_num(val)
        sk_key, sk_val = fuzzy_find(skill_data, key)
        sk_num = to_num(sk_val)

        if sk_num is None:
            concl = "🔵 技能侧缺失→以搜索为准"
            stats["技能侧缺失"] += 1
            sk_disp = "—"
        else:
            # 相对误差
            if s_num is not None and sk_num != 0:
                diff = abs(s_num - sk_num) / max(abs(sk_num), 1e-9)
                if diff <= tol:
                    concl = f"✅ 一致 (差{diff*100:.2f}%)"
                    stats["一致"] += 1
                else:
                    concl = f"🔴 **不一致 (差{diff*100:.1f}%)**"
                    stats["不一致"] += 1
            else:
                concl = "⚠️ 无法比对"
            sk_disp = f"{sk_num:,.2f}"

        s_disp = f"{s_num:,.2f}" if s_num is not None else str(val)
        print(f"{key:<30} {s_disp:>12} {sk_disp:>12}  {concl}")
        rows.append([key, s_disp, sk_disp, concl])

    print("-" * 74)
    print(f"汇总: 一致 {stats['一致']} | 不一致 {stats['不一致']} | 技能侧缺失 {stats['技能侧缺失']}")
    if stats["不一致"]:
        print()
        print("⚠️  存在不一致项，需人工复核数据源（可能是口径差异或时点差异）")
    return stats, rows


def main():
    ap = argparse.ArgumentParser(description="交叉验证工具")
    ap.add_argument("outdir", nargs="?", help="取数输出目录（含01_历史财务.csv 等）")
    ap.add_argument("--json", help="JSON 文件，包含待验证指标")
    ap.add_argument("--tol", type=float, default=0.02, help="允许相对误差，默认0.02（即2%%）")
    args = ap.parse_args()

    if not args.outdir:
        print("❌ 缺少输出目录参数。用法: python3 cross_validate.py <取数输出目录> [--json checks.json]")
        sys.exit(1)

    outdir = Path(args.outdir)
    if not outdir.exists():
        print(f"❌ 目录不存在: {outdir}")
        sys.exit(1)

    if args.json:
        checks = json.loads(Path(args.json).read_text(encoding="utf-8"))
    else:
        # 交互式输入
        print("请输入搜索侧拿到的指标（格式：指标名=数值），空行结束：")
        print('示例: 2025年营业收入(亿)=3323.44')
        print("-" * 50)
        checks = {}
        while True:
            try:
                line = input().strip()
            except EOFError:
                break
            if not line:
                break
            if "=" in line:
                k, v = line.split("=", 1)
                checks[k.strip()] = v.strip()
        if not checks:
            print("未输入任何指标，退出。")
            sys.exit(0)

    stats, rows = validate(outdir, checks, args.tol)

    # 落盘
    out_file = outdir / "06_交叉验证结果.csv"
    with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["指标", "搜索值", "技能值", "结论"])
        w.writerows(rows)
    print(f"\n✅ 验证结果已保存: {out_file}")


if __name__ == "__main__":
    main()
