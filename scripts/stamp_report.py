#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告生成时间盖章器 —— 给 A股深度研究报告盖上 / 刷新「精确到秒」的生成时间戳。

一次 stamp = 报告落盘那一刻。**幂等**：已有戳就地刷新，缺失的自动补上。
只改时间戳文本，不碰正文、不碰结构、不碰行号锚点。

戳统一格式：YYYY-MM-DD HH:MM:SS（本地时区，24 小时制）。

四个位置全部覆盖：
  1. <title>                  ：… ｜ 生成于 YYYY-MM-DD HH:MM:SS
  2. <h1><small> 副标题末尾    ：… ｜ 生成于 YYYY-MM-DD HH:MM:SS
  3. <footer>                 ：报告生成时间：YYYY-MM-DD HH:MM:SS（本地时间）
  4. 顶部注释块                 ：· 报告生成时间：YYYY-MM-DD HH:MM:SS

用法:
    python3 stamp_report.py <report.html>                     # 当前本地时间盖章
    python3 stamp_report.py <report.html> --at "2026-09-15 09:05:32"
    python3 stamp_report.py <report.html> --check             # 只校验，不改文件
    python3 stamp_report.py <report.html> --rename            # 盖章 + 文件名时间同步
    python3 stamp_report.py <report.html> --dry-run           # 预览改动不落盘

退出码: 正常 0；--check 发现未盖章/精度不足 1；参数错误 2。

注意：`数据截至 YYYY-MM-DD 收盘` 这类**数据时点**不是生成时间，本脚本只认
「生成于 / 报告生成时间」两个锚点，不会误改数据时点。
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

TS_RE = r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
RE_ANCHOR_GEN = re.compile(r"(生成于\s*)" + TS_RE)
RE_ANCHOR_FOOT = re.compile(r"(报告生成时间[:：]\s*)" + TS_RE)
RE_TS = re.compile(TS_RE)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
RE_H1 = re.compile(r"<h1[\s>].*?</h1>", re.S)
RE_FOOTER = re.compile(r"</footer>")
RE_COMMENT = re.compile(r"<!--.*?-->", re.S)


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp(text, ts):
    """返回 (新文本, 命中报告 dict)。"""
    hits = {"副标题/正文生成于": 0, "报告生成时间行": 0, "title 补写": 0, "小标题补写": 0, "页脚补写": 0, "注释块补写": 0}

    hits["副标题/正文生成于"] = len(RE_ANCHOR_GEN.findall(text))
    text = RE_ANCHOR_GEN.sub(lambda m: m.group(1) + ts, text)

    hits["报告生成时间行"] = len(RE_ANCHOR_FOOT.findall(text))
    text = RE_ANCHOR_FOOT.sub(lambda m: m.group(1) + ts, text)

    # 1) <title>：缺「生成于」就补
    m = RE_TITLE.search(text)
    if m and "生成于" not in m.group(1):
        new = m.group(1).strip() + " ｜ 生成于 " + ts
        text = text[:m.start(1)] + new + text[m.end(1):]
        hits["title 补写"] = 1

    # 2) <h1> 里的 <small> 副标题：缺「生成于」就补
    m = RE_H1.search(text)
    if m and "生成于" not in m.group(0):
        block = m.group(0)
        if "</small>" in block:
            block = block.replace("</small>", " ｜ 生成于 " + ts + "</small>", 1)
        elif "</h1>" in block:
            block = block.replace("</h1>", "<small>生成于 " + ts + "</small></h1>", 1)
        text = text[:m.start()] + block + text[m.end():]
        hits["小标题补写"] = 1

    # 3) footer：缺「报告生成时间」就补
    m = RE_FOOTER.search(text)
    if m:
        block = RE_FOOTER.search(text).group(0)
        head = text[:m.start()]
        # 只在 footer 段（最后一个 <footer> 之后）判断
        seg_start = head.rfind("<footer")
        seg = text[seg_start:m.start()] if seg_start >= 0 else ""
        if "报告生成时间" not in seg:
            text = text[:m.start()] + "<br>  报告生成时间：" + ts + "（本地时间）\n" + text[m.start():]
            hits["页脚补写"] = 1

    # 4) 顶部注释块：缺「报告生成时间」就在块尾补一行（注释块是文档头，便于 grep 存档时间）
    m = RE_COMMENT.search(text)
    if m and "报告生成时间" not in m.group(0):
        inner = m.group(0)[4:-3].rstrip() + "\n  · 报告生成时间：" + ts + "\n"
        text = text[:m.start()] + "<!--" + inner + "-->" + text[m.end():]
        hits["注释块补写"] = 1

    return text, hits


def check(text):
    """已盖章且精确到秒 → True。"""
    for m in RE_ANCHOR_GEN.finditer(text):
        if re.search(r"\d{2}:\d{2}:\d{2}", m.group(0)):
            return True
    for m in RE_ANCHOR_FOOT.finditer(text):
        if re.search(r"\d{2}:\d{2}:\d{2}", m.group(0)):
            return True
    return False


def rename_with_ts(path: Path, ts, dry_run=False):
    """文件名时间同步：xxx_20260915(_091732)?.html → xxx_20260915_091732.html"""
    d, t = ts.split(" ")
    compact = d.replace("-", "") + "_" + t.replace(":", "")
    stem, ext = path.stem, path.suffix
    m = re.match(r"^(.*)_(\d{8})(?:_\d{6})?$", stem)
    new_stem = "%s_%s_%s" % (m.group(1), m.group(2), t.replace(":", "")) if m else "%s_%s" % (stem, compact)
    new_path = path.with_name(new_stem + ext)
    if new_path == path:
        return path, False
    if not dry_run:
        path.rename(new_path)
    return new_path, True


def main():
    ap = argparse.ArgumentParser(add_help=True, description="给研报盖「精确到秒」的生成时间戳（幂等）")
    ap.add_argument("report", help="报告 HTML 路径")
    ap.add_argument("--at", default=None, help='指定时间戳，如 "2026-09-15 09:05:32"；缺省=当前本地时间')
    ap.add_argument("--check", action="store_true", help="只校验是否已盖精确到秒的戳（不改文件）")
    ap.add_argument("--rename", action="store_true", help="同时把文件名时间同步为 YYYYMMDD_HHMMSS")
    ap.add_argument("--dry-run", action="store_true", help="预览，不落盘")
    args = ap.parse_args()

    p = Path(args.report)
    if not p.exists():
        sys.exit("❌ 未找到报告：%s" % p)
    text = p.read_text(encoding="utf-8")

    if args.check:
        ok = check(text)
        print(("✅ 已盖精确到秒的生成时间戳" if ok else "❌ 未找到精确到秒的生成时间戳（跑 stamp_report.py 盖章）") + "：%s" % p.name)
        sys.exit(0 if ok else 1)

    ts = args.at or now_ts()
    new_text, hits = stamp(text, ts)

    changed = new_text != text
    if not args.dry_run and changed:
        p.write_text(new_text, encoding="utf-8")

    label = "（预览，未落盘）" if args.dry_run else ""
    print("🕒 生成时间戳 %s%s → %s" % (ts, label, p.name))
    for k, v in hits.items():
        print("   · %-14s 命中 %d 处" % (k, v))

    out = p
    if args.rename:
        out, renamed = rename_with_ts(p, ts, dry_run=args.dry_run)
        if renamed:
            print("   · 文件名%s → %s" % ("将改为" if args.dry_run else "已改为", out.name))

    if not changed and not args.rename:
        print("   · 内容已是该时间戳，无改动")


if __name__ == "__main__":
    main()
