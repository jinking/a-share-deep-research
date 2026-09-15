#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日K线数据转换器 —— 把 fetch_stock.py 产出的 raw/kline.txt 转成研报 HTML 内联 JS 数组。

用法:
    python3 build_kline.py <研究目录|kline.txt>            # 打印 JS 片段
    python3 build_kline.py <研究目录> --out kline.js       # 写入文件
    python3 build_kline.py <研究目录> --days 60            # 只取最近 N 个交易日（默认全部）

输出:
    var kDates=[...];                       // 'YYYY-MM-DD' 升序
    var kRaw=[[开,收,低,高,量],...];          // 与 ECharts candlestick 兼容的顺序
    另附一行统计，便于交叉验证（区间涨跌幅 / 区间高低点）。

说明:
    raw/kline.txt 由 westock-data `kline --period day --limit 60` 产出，日期为降序；
    本脚本自动翻转成升序，并把 [open,last,high,low] 重排为 [open,last,low,high]。
    列含义：date open last(收) high low volume amount exchange
"""

import argparse
import re
import sys
from pathlib import Path


def parse_kline(text: str):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7 or not re.match(r"^\d{4}-\d{2}-\d{2}$", cells[0]):
            continue
        try:
            d = cells[0]
            o, c_, h, l = float(cells[1]), float(cells[2]), float(cells[3]), float(cells[4])
            v = int(float(cells[5]))
        except ValueError:
            continue
        rows.append((d, o, c_, h, l, v))
    # 按日期升序
    rows.sort(key=lambda r: r[0])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="研究目录（内含 raw/kline.txt）或 kline.txt 路径")
    ap.add_argument("--days", type=int, default=0, help="只取最近 N 个交易日（0=全部）")
    ap.add_argument("--out", default="", help="输出文件路径（默认打印到 stdout）")
    args = ap.parse_args()

    p = Path(args.path)
    kf = p / "raw" / "kline.txt" if p.is_dir() else p
    if not kf.exists():
        sys.exit(f"❌ 找不到 {kf}")

    rows = parse_kline(kf.read_text(encoding="utf-8"))
    if not rows:
        sys.exit("❌ kline.txt 未解析出数据")
    if args.days and args.days < len(rows):
        rows = rows[-args.days:]

    dates = "[" + ",".join("'%s'" % r[0] for r in rows) + "]"
    raw = "[" + ",".join("[%.2f,%.2f,%.2f,%.2f,%d]" % (r[1], r[2], r[4], r[3], r[5]) for r in rows) + "]"

    first, last = rows[0], rows[-1]
    chg = (last[2] / first[1] - 1) * 100
    hi = max(r[3] for r in rows)
    lo = min(r[4] for r in rows)

    out = []
    out.append("/* 近 %d 个交易日日K：%s ~ %s（来源 raw/kline.txt） */" % (len(rows), first[0], last[0]))
    out.append("var kDates=%s;" % dates)
    out.append("var kRaw=%s;  /* [开,收,低,高,量] */" % raw)
    out.append("/* 统计校验：区间 %+.2f%% ｜ 区间最高 %.2f ｜ 区间最低 %.2f ｜ 报告日收盘 %.2f */"
               % (chg, hi, lo, last[2]))
    text = "\n".join(out)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"✅ 已写入 {args.out}")
    else:
        print(text)
    print(f"# 交易日 {len(rows)} ｜ 区间 {first[0]}~{last[0]} ｜ 涨跌 {chg:+.2f}% ｜ 高 {hi:.2f} 低 {lo:.2f} 收盘 {last[2]:.2f}")


if __name__ == "__main__":
    main()
