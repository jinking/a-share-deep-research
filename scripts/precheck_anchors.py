#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""锚点预检（promote 之前跑）：把 promote_plan.json 里的每条摘录用
与 promote 重算**完全相同**的口径（NFKC + 去空白 → 子串命中）提前验一遍。

动机（2026-09-17 三标的实测）：PDF 文本层换行断词（「领\\n先」「600\\n万千瓦」）
是写生成器→promote 失败循环的最大时间黑洞（金盘 5 次、风华 5 次、华电 8 次修复）。
本脚本在 promote 之前一条命令暴露全部问题，并给出断词诊断。

用法：
    python3 scripts/precheck_anchors.py <evidence_dir>            # 全量输出
    python3 scripts/precheck_anchors.py <evidence_dir> --quiet    # 只报 FAIL/WARN

evidence_dir 下必须有 promote_plan.json（由 build_evidence 生成器产出）。
local_file 相对 evidence_dir 解析；.pdf → 同名 .textlayer.txt；纯文本后缀直接比对；
无 local_file（纯 URL 的 vendor 线索）→ SKIP。

退出码：0 = 全部 PASS/SKIP/WARN；1 = 存在 FAIL；2 = 参数/文件错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.evidence.verbatim import normalize_for_match  # noqa: E402  唯一口径，禁止本地重写

PAGE_RE = re.compile(r"<<<PAGE (\d+)>>>")


def resolve_source(evidence_dir: Path, local_file: str):
    """document.local_file → 可比对文本路径；拿不到返回 None。"""
    p = Path(local_file)
    if not p.is_absolute():
        p = evidence_dir / p
    if p.suffix.lower() == ".pdf":
        tl = p.with_name(p.name[: -len(".pdf")] + ".textlayer.txt")
        return tl if tl.is_file() else None
    if p.is_file() and p.suffix.lower() in (
        ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".html", ".htm"
    ):
        return p
    return None


PAGE_STRIP_RE = re.compile(r"<<<PAGE \d+>>>")


def check_excerpt(needle: str, raw: str):
    """与 promote 重算同口径的匹配：逐页 → 全文（含页标记，与 promote 字节级一致）。

    返回 (hit_page|None, cross_page: bool)。cross_page=True 表示只有全文匹配命中
    （摘录跨页或含页标记），page 字段不核对。
    """
    hits = list(PAGE_RE.finditer(raw))
    if hits:
        for i, m in enumerate(hits):
            start = m.end()
            end = hits[i + 1].start() if i + 1 < len(hits) else len(raw)
            if needle in normalize_for_match(raw[start:end]):
                return int(m.group(1)), False
        if needle in normalize_for_match(raw):
            return None, True  # 全文命中：与 promote 同口径
        return None, False
    if needle in normalize_for_match(raw):
        return 0, False
    return None, False


def longest_prefix_hit(needle: str, hay: str) -> int:
    """needle 在 hay 中能命中的最长前缀长度（二分）。"""
    lo, hi, best = 0, len(needle), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if mid == 0:
            lo = mid + 1
            continue
        if needle[:mid] in hay:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def diagnose(needle: str, raw_text: str) -> str:
    """断词诊断：最长前缀断点前后的原文形态。"""
    whole = normalize_for_match(PAGE_STRIP_RE.sub("", raw_text))
    n = longest_prefix_hit(needle, whole)
    if n <= 0:
        return "摘录开头就不在原文中 —— 锚点选错了段落"
    if n >= len(needle):
        return ""
    tail_needle = needle[n : n + 30]
    ctx_at = whole.find(needle[max(0, n - 20) : n]) if n >= 20 else -1
    show_from = max(0, ctx_at) if ctx_at >= 0 else max(0, n - 20)
    ctx = whole[show_from : show_from + 60]
    return f"前 {n} 字符可命中，断点附近原文：…{ctx}…；摘录接续：{tail_needle}…"


def main() -> int:
    ap = argparse.ArgumentParser(description="promote 前的摘录/锚点批量预检")
    ap.add_argument("evidence_dir", help="含 promote_plan.json 的证据目录")
    ap.add_argument("--quiet", action="store_true", help="只输出 FAIL/WARN 行")
    args = ap.parse_args()

    evidence_dir = Path(args.evidence_dir)
    plan_file = evidence_dir / "promote_plan.json"
    if not plan_file.is_file():
        print(f"❌ 找不到 {plan_file}")
        return 2
    plan = json.loads(plan_file.read_text(encoding="utf-8"))

    t0 = time.time()
    n_pass = n_fail = n_warn = n_skip = 0
    lines = []

    for promo in plan.get("promotions", []):
        doc = promo.get("document", {})
        title = doc.get("title", "?")
        lf = doc.get("local_file")
        cand = promo.get("candidate_id", "?")
        src = resolve_source(evidence_dir, lf) if lf else None

        if lf is None:
            n_skip += len(promo.get("links", []))
            if not args.quiet:
                lines.append(f"· SKIP  {cand}（纯 URL vendor，无本地原件可比）")
            continue
        if src is None:
            for lk in promo.get("links", []):
                n_fail += 1
                lines.append(f"✗ FAIL  {cand}｜{lk.get('claim_id')}：找不到可比对文本（{lf} 及其 textlayer 均缺失）")
            continue

        raw = src.read_text(encoding="utf-8")

        for lk in promo.get("links", []):
            cid = lk.get("claim_id", "?")
            excerpt = lk.get("evidence_text") or ""
            needle = normalize_for_match(excerpt)
            if not needle:
                n_fail += 1
                lines.append(f"✗ FAIL  {cand}｜{cid}：evidence_text 为空")
                continue

            hit_page, cross_page = check_excerpt(needle, raw)

            if hit_page is None and not cross_page:
                n_fail += 1
                why = diagnose(needle, raw)
                lines.append(f"✗ FAIL  {cand}｜{cid}：摘录未命中原文（{src.name}）{('—— ' + why) if why else ''}")
                continue

            n_pass += 1
            if cross_page:
                lines.append(f"· CROSS {cand}｜{cid}：摘录跨页边界，全文命中（page 不核对）")
                n_skip += 1
                n_pass -= 1
            elif hit_page and hit_page != int(lk.get("page") or -1):
                n_warn += 1
                lines.append(
                    f"⚠ WARN  {cand}｜{cid}：page 写的 {lk.get('page')}，实际命中第 {hit_page} 页"
                )
            sections = doc.get("sections") or []
            sec = lk.get("section")
            if sections and sec and sec not in sections:
                n_warn += 1
                lines.append(f"⚠ WARN  {cand}｜{cid}：section「{sec}」不在文档登记 sections 里（{sections}）")

    dt = time.time() - t0
    if not args.quiet:
        print("\n".join(lines))
    else:
        print("\n".join(l for l in lines if not l.startswith("·")))
    print("─" * 62)
    print(f"PASS {n_pass} / FAIL {n_fail} / WARN {n_warn} / SKIP {n_skip}  （{dt:.1f}s）")
    if n_fail:
        print("❌ 存在 FAIL —— 先修生成器锚点，再 promote（省掉整轮失败循环）")
        return 1
    print("✅ 预检通过，可以 promote")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
