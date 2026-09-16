#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告 Claim 指纹盖章器 —— 给报告里的 Claim 锚点盖上 / 刷新「版本指纹」。

v3.0.3 §4 起，报告锚点不仅要声明 claim_id / level / status，还要声明
`claim_fingerprint` —— 否则「Claim 正文被改写、level 与 status 都没变」这类
**结论漂移**无法被机器发现。

指纹**不由人手填写**：它从 Evidence Store 的 Claim Ledger 现算（sha256 前 16 位）。
本脚本只做「把真值抄进报告」这一件机械动作，幂等：

  · 缺 `data-claim-fingerprint`  → 补上
  · 有但与当前 Ledger 不符        → 就地刷新
  · 已一致                       → 不动

两种锚点语法都支持：HTML 的 `data-claim-fingerprint="…"` 与 Markdown 的
`<!-- claim:ID level=… fingerprint=… -->`。

用法:
    python3 stamp_claim_fingerprints.py <report> --evidence-dir <dir>            # 预览
    python3 stamp_claim_fingerprints.py <report> --evidence-dir <dir> --write    # 落盘
    python3 stamp_claim_fingerprints.py <report> --evidence-dir <dir> --check    # 只校验

退出码: 正常 0；--check 发现缺失/过期 1；参数错误 2。

注意：本脚本**不校验** Claim 与报告的语义是否一致，只负责把版本指纹抄对。
真正的判定仍然由 `scripts/validate_report.py` 完成——盖章通过 ≠ 报告合格。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.evidence import EvidenceStore, EvidenceStoreError  # noqa: E402

TAG_RE = re.compile(r"<[A-Za-z][A-Za-z0-9:_-]*\b[^>]*>", re.S)
ATTR_ID_RE = re.compile(r'(data-claim-id\s*=\s*"([^"]*)")')
ATTR_FP_RE = re.compile(r'data-claim-fingerprint\s*=\s*"([^"]*)"')
MD_RE = re.compile(r"<!--\s*claim\s*:([^>]*?)-->", re.I | re.S)
MD_FP_RE = re.compile(r"(fingerprint\s*=\s*)([^\s=]+)", re.I)


def load_fingerprints(evidence_dir: Path) -> dict:
    """从 Claim Ledger 现算每个 Claim 的指纹（唯一真值来源）。"""
    store = EvidenceStore.open(evidence_dir)
    return {cid: claim.claim_fingerprint for cid, claim in store.claims.items()}


def _fix_html(text: str, fps: dict, stats: dict) -> str:
    def repl(m: re.Match) -> str:
        tag = m.group(0)
        id_m = ATTR_ID_RE.search(tag)
        if not id_m:
            return tag
        cid = id_m.group(2).strip()
        want = fps.get(cid)
        if want is None:
            stats["unknown"].append(cid)
            return tag
        stats["anchors"] += 1
        cur = ATTR_FP_RE.search(tag)
        if cur:
            if cur.group(1) == want:
                stats["ok"] += 1
                return tag
            stats["refreshed"] += 1
            return tag[: cur.start(1)] + want + tag[cur.end(1):]
        stats["added"] += 1
        return tag[: id_m.end(1)] + f' data-claim-fingerprint="{want}"' + tag[id_m.end(1):]

    return TAG_RE.sub(repl, text)


def _fix_markdown(text: str, fps: dict, stats: dict) -> str:
    def repl(m: re.Match) -> str:
        body = m.group(1).strip()
        if not body:
            return m.group(0)
        cid = body.split(None, 1)[0].strip()
        want = fps.get(cid)
        if want is None:
            if cid:
                stats["unknown"].append(cid)
            return m.group(0)
        stats["anchors"] += 1
        cur = MD_FP_RE.search(body)
        if cur:
            if cur.group(2) == want:
                stats["ok"] += 1
                return m.group(0)
            stats["refreshed"] += 1
            new_body = body[: cur.start(2)] + want + body[cur.end(2):]
        else:
            stats["added"] += 1
            new_body = f"{body} fingerprint={want}"
        return "<!-- claim:" + new_body + " -->"

    return MD_RE.sub(repl, text)


def stamp(text: str, fps: dict) -> tuple:
    stats = {"anchors": 0, "added": 0, "refreshed": 0, "ok": 0, "unknown": []}
    text = _fix_html(text, fps, stats)
    text = _fix_markdown(text, fps, stats)
    stats["unknown"] = sorted(set(stats["unknown"]))
    return text, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="给报告 Claim 锚点盖「版本指纹」（幂等）")
    ap.add_argument("report", help="报告文件（HTML / Markdown）")
    ap.add_argument("--evidence-dir", dest="evidence_dir", required=True, help="Evidence Store 目录（指纹真值来源）")
    ap.add_argument("--write", action="store_true", help="写回文件（缺省只预览）")
    ap.add_argument("--check", action="store_true", help="只校验：全部锚点指纹都与 Ledger 一致才返回 0")
    args = ap.parse_args()

    report = Path(args.report)
    if not report.is_file():
        print(f"❌ 未找到报告：{report}")
        return 2
    ev = Path(args.evidence_dir)
    if not ev.is_dir():
        print(f"❌ 未找到 Evidence Store：{ev}")
        return 2

    try:
        fps = load_fingerprints(ev)
    except EvidenceStoreError as exc:
        print(f"❌ Evidence Store 无法读取：{exc}")
        return 2

    text = report.read_text(encoding="utf-8")
    new_text, stats = stamp(text, fps)

    if stats["anchors"] == 0:
        print(f"⚠️  报告里没有可盖章的 Claim 锚点：{report.name}")
        if stats["unknown"]:
            print(f"   · Ledger 中不存在的 claim_id：{', '.join(stats['unknown'])}")
        return 0 if not args.check else 1

    changed = new_text != text
    stale = stats["added"] + stats["refreshed"]

    if args.check:
        if stale == 0:
            print(f"✅ 全部 {stats['anchors']} 处锚点指纹与 Ledger 一致：{report.name}")
            return 0
        print(
            f"❌ 锚点指纹缺失或过期：{report.name}"
            f"（缺失 {stats['added']} 处、过期 {stats['refreshed']} 处，共 {stats['anchors']} 处）"
        )
        print("   跑 `stamp_claim_fingerprints.py … --write` 重新盖章")
        return 1

    if args.write and changed:
        report.write_text(new_text, encoding="utf-8")

    label = "" if args.write else "（预览，未落盘）"
    print(f"🔖 Claim 指纹盖章{label} → {report.name}")
    print(f"   · 锚点总数      {stats['anchors']} 处")
    print(f"   · 新增指纹      {stats['added']} 处")
    print(f"   · 刷新过期指纹  {stats['refreshed']} 处")
    print(f"   · 已一致        {stats['ok']} 处")
    if stats["unknown"]:
        print(f"   · ⚠️ Ledger 中不存在的 claim_id：{', '.join(stats['unknown'])}")
    if not changed:
        print("   · 内容无改动")
    return 0


if __name__ == "__main__":
    sys.exit(main())
