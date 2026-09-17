#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键收尾链（v3.0.3 报告交付 SOP 的自动化）：

    stamp_claim_fingerprints --write
      → stamp_report --rename（文件名定格 _YYYYMMDD_HHMMSS）
      → 由文件名派生 meta.generated_at 回填 manifest（不手填）
      → validate_report 完整模式
      → validate_report --claim-only
      → validate_evidence --fail-on P0,P1,P2

任何一步失败立即停止，退出码 1；全过打印总耗时。

用法：
    python3 scripts/finish_report.py <report.html> \
        --manifest <research_dir/research_manifest.json> \
        --evidence-dir <research_dir/evidence>

validation 输出到 manifest 所在目录的 validation/ 与 validation/claim_only/。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable


def run(step: str, cmd: list) -> int:
    print(f"\n── {step} ──")
    print("$ " + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"❌ {step} 失败（exit {r.returncode}），链条停止")
    return r.returncode


def derive_generated_at(stem: str) -> str:
    """报告文件名 _YYYYMMDD_HHMMSS → ISO8601+08:00（不手填，唯一事实源是文件名）。"""
    m = re.search(r"_(\d{8})_(\d{6})$", stem)
    if not m:
        raise SystemExit(f"❌ 文件名缺少 _YYYYMMDD_HHMMSS 后缀：{stem}")
    dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(
        tzinfo=timezone(timedelta(hours=8))
    )
    return dt.isoformat(timespec="seconds")


def main() -> int:
    ap = argparse.ArgumentParser(description="盖章 → 回填 → 三路验收 一键收尾")
    ap.add_argument("report", help="报告 HTML（未盖章或已盖指纹均可，指纹步骤幂等）")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--skip-claim-only", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    report = Path(args.report).resolve()
    manifest = Path(args.manifest).resolve()
    evidence = Path(args.evidence_dir).resolve()
    if not report.is_file():
        raise SystemExit(f"❌ 报告不存在：{report}")
    if not manifest.is_file():
        raise SystemExit(f"❌ manifest 不存在：{manifest}")

    val_dir = manifest.parent / "validation"

    # 守卫：报告文件名已带 _YYYYMMDD_HHMMSS 且与 manifest.generated_at 一致
    # → 视为已盖章，跳过①②③（重跑 = 纯验收，时间戳不漂移）
    m_done = re.search(r"_(\d{8})_(\d{6})$", report.stem)
    if m_done:
        existing = json.loads(manifest.read_text(encoding="utf-8")).get("meta", {}).get("generated_at")
        if existing == derive_generated_at(report.stem):
            final_report = report
            print(f"📌 报告已盖章（{report.name}），跳过盖章/回填，直接验收")
            if run("④ validate_report 完整模式", [PY, str(SCRIPTS / "validate_report.py"),
                  str(final_report), "--manifest", str(manifest), "--evidence-dir", str(evidence),
                  "--out", str(val_dir)]):
                return 1
            if not args.skip_claim_only:
                if run("⑤ validate_report --claim-only", [PY, str(SCRIPTS / "validate_report.py"),
                      str(final_report), "--manifest", str(manifest), "--evidence-dir", str(evidence),
                      "--claim-only", "--out", str(val_dir / "claim_only")]):
                    return 1
            if run("⑥ validate_evidence --fail-on P0,P1,P2", [PY, str(SCRIPTS / "validate_evidence.py"),
                  str(evidence), "--fail-on", "P0,P1,P2"]):
                return 1
            print("\n" + "═" * 62)
            print(f"🎉 纯验收全绿，总耗时 {time.time() - t0:.0f}s")
            return 0

    # ① 指纹盖章
    if run("① Claim 指纹盖章", [PY, str(SCRIPTS / "stamp_claim_fingerprints.py"),
          str(report), "--evidence-dir", str(evidence), "--write"]):
        return 1

    # ② 时间戳盖章 + 重命名
    if run("② 精确到秒时间戳盖章 + 重命名", [PY, str(SCRIPTS / "stamp_report.py"),
          str(report), "--rename"]):
        return 1
    # 从原文件名 stem 前缀定位新文件（rename 规则：prefix_YYYYMMDD_HHMMSS.html）
    m = re.match(r"^(.*?)_(\d{8})(?:_\d{6})?$", report.stem)
    prefix = m.group(1) if m else report.stem
    cands = sorted(report.parent.glob(f"{prefix}_*.html"))
    if not cands:
        raise SystemExit(f"❌ 重命名后找不到报告：{prefix}_*.html")
    final_report = cands[-1]
    print(f"📌 最终报告：{final_report.name}")

    # ③ 文件名派生 generated_at 回填 manifest
    generated_at = derive_generated_at(final_report.stem)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    old = data.get("meta", {}).get("generated_at")
    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["generated_at"] = generated_at
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n── ③ generated_at 回填 manifest ──\n{old} → {generated_at}")

    # ④ 完整验收
    if run("④ validate_report 完整模式", [PY, str(SCRIPTS / "validate_report.py"),
          str(final_report), "--manifest", str(manifest), "--evidence-dir", str(evidence),
          "--out", str(val_dir)]):
        return 1

    # ⑤ claim-only 跨产物验收
    if not args.skip_claim_only:
        if run("⑤ validate_report --claim-only", [PY, str(SCRIPTS / "validate_report.py"),
              str(final_report), "--manifest", str(manifest), "--evidence-dir", str(evidence),
              "--claim-only", "--out", str(val_dir / "claim_only")]):
            return 1

    # ⑥ 证据层独立验收
    if run("⑥ validate_evidence --fail-on P0,P1,P2", [PY, str(SCRIPTS / "validate_evidence.py"),
          str(evidence), "--fail-on", "P0,P1,P2"]):
        return 1

    print("\n" + "═" * 62)
    print(f"🎉 收尾链全绿，总耗时 {time.time() - t0:.0f}s")
    print(f"   报告：{final_report.name}")
    print(f"   generated_at：{generated_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
