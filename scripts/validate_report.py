#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股个股深度研究产物独立检查器（Research Artifact Validator）

目标：在研究报告生成后，以独立于生成过程的规则做验收，避免“每一段都合理，组合起来却冲突”。

推荐用法（严格模式，正式产物必须这样跑）：
    python3 scripts/validate_report.py report.html \
      --manifest research_manifest.json \
      --out validation

只检查旧报告结构（无法完成数学/证据强校验）：
    python3 scripts/validate_report.py old_report.html --report-only --out validation

退出码：
    0 = PASS（允许交付）
    1 = FAIL（存在 P0/P1 错误，不允许标记研究完成）
    2 = 参数/文件错误
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VERSION = "1.0.0"
SCENARIO_ALIASES = {
    "bear": "悲观", "pessimistic": "悲观", "悲观": "悲观",
    "base": "中性", "neutral": "中性", "中性": "中性",
    "bull": "乐观", "optimistic": "乐观", "乐观": "乐观",
}
PRIMARY_SOURCE_TYPES = {
    "annual_report", "interim_report", "quarterly_report",
    "company_announcement", "exchange_filing", "company_ir",
    "customer_announcement", "government", "official_database",
}
CONFIRMED_LEVEL_KEYWORDS = (
    "已确认收入", "已确认订单", "已定点", "已量产", "已批量交付", "批量供货"
)
ALLOWED_STATUS = {"研究池", "观察", "试仓", "加仓", "持有", "降仓", "回避"}


@dataclass
class Finding:
    severity: str   # P0 / P1 / P2 / INFO
    code: str
    message: str
    detail: str = ""


def fail(findings: List[Finding], severity: str, code: str, message: str, detail: str = ""):
    findings.append(Finding(severity, code, message, detail))


def close(a: Optional[float], b: Optional[float], rel: float = 0.03, abs_tol: float = 0.02) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b), 1e-9))


def num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace(",", "").replace("％", "%").strip()
        s = s.replace("亿元", "").replace("亿", "").replace("元", "")
        if s.endswith("%"):
            s = s[:-1]
        return float(s)
    except Exception:
        return None


def strip_html_to_text(raw: str) -> str:
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"</?(?:h1|h2|h3|h4|p|li|tr|td|th|div|section|br)\b[^>]*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{2,}", "\n", raw)
    return raw.strip()


def report_text(path: Path) -> Tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm"} or "<html" in raw[:1000].lower():
        return raw, strip_html_to_text(raw)
    return raw, raw


def extract_chapters(raw: str, text: str) -> List[int]:
    nums = set()
    # HTML: <h2> ... 10 ... </h2>，允许内部 span
    for m in re.finditer(r"<h2\b[^>]*>(.*?)</h2>", raw, flags=re.I | re.S):
        t = strip_html_to_text(m.group(1))
        mm = re.search(r"(?:^|\s)(1[0-6]|[0-9])(?:\s|[.、：:]|$)", t)
        if mm:
            nums.add(int(mm.group(1)))
    # Markdown / 纯文本
    for m in re.finditer(r"(?m)^\s*#{1,4}\s*(1[0-6]|[0-9])(?:[.、：:]|\s)", text):
        nums.add(int(m.group(1)))
    return sorted(nums)


def extract_forecast_years(text: str) -> List[int]:
    return sorted({int(x) for x in re.findall(r"\b(20\d{2})E\b", text)})


def count_tracker_rows(raw: str, text: str) -> Optional[int]:
    # HTML：找到含“季度跟踪”的 h2/h3 后，取紧随其后的第一个 table
    if "<table" in raw.lower():
        # 优先找明确的“季度跟踪表”小标题，避免把同章节前面的催化剂表误认为跟踪表。
        patterns = [
            r"<h3\b[^>]*>.*?季度跟踪表.*?</h3>.*?<table\b[^>]*>(.*?)</table>",
            r"<h3\b[^>]*>.*?季度跟踪.*?</h3>.*?<table\b[^>]*>(.*?)</table>",
            r"<h2\b[^>]*>.*?季度跟踪.*?</h2>.*?<table\b[^>]*>(.*?)</table>",
        ]
        for pat in patterns:
            m = re.search(pat, raw, flags=re.I | re.S)
            if m:
                body = m.group(1)
                rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, flags=re.I | re.S)
                data_rows = [r for r in rows if "<td" in r.lower()]
                return len(data_rows)
    # Markdown 粗略：季度跟踪之后到下一章节，统计表格数据行
    m = re.search(r"季度跟踪.*?(?=\n##\s|\Z)", text, flags=re.S)
    if m:
        lines = [ln for ln in m.group(0).splitlines() if ln.strip().startswith("|")]
        if len(lines) >= 2:
            return max(0, len(lines) - 2)
    return None


def validate_report_structure(path: Path, raw: str, text: str, findings: List[Finding], strict_manifest_expected: bool):
    chapters = extract_chapters(raw, text)
    missing = [i for i in range(17) if i not in chapters]
    if missing:
        fail(findings, "P0", "STRUCT_CHAPTERS", "16章/0–16结构不完整", f"缺少章节: {missing}; 已识别: {chapters}")
    else:
        fail(findings, "INFO", "STRUCT_CHAPTERS", "0–16章结构完整")

    labels = ["事实", "管理层", "推断", "假设", "无法确认"]
    absent = [x for x in labels if x not in text]
    if absent:
        fail(findings, "P1", "EVIDENCE_LABELS", "证据标签体系未完整出现在报告中", f"缺少: {absent}")
    else:
        fail(findings, "INFO", "EVIDENCE_LABELS", "证据标签体系存在")

    years = extract_forecast_years(text)
    has_scenarios = all(x in text for x in ("悲观", "中性", "乐观"))
    if not has_scenarios:
        fail(findings, "P0", "FORECAST_SCENARIOS", "三情景不完整", "必须同时出现悲观/中性/乐观")
    if len(years) < 3:
        fail(findings, "P0", "FORECAST_YEARS", "盈利预测未覆盖至少3个预测年度", f"识别到预测年度: {years}")
    else:
        fail(findings, "INFO", "FORECAST_YEARS", f"识别到至少3个预测年度: {years[:5]}")

    tracker_rows = count_tracker_rows(raw, text)
    if tracker_rows is None:
        fail(findings, "P1", "TRACKER_ROWS", "未能识别季度跟踪表", "建议保留明确的‘季度跟踪表’标题和标准表格")
    elif not (10 <= tracker_rows <= 15):
        fail(findings, "P1", "TRACKER_ROWS", "季度跟踪指标数量不在10–15项", f"识别到 {tracker_rows} 项")
    else:
        fail(findings, "INFO", "TRACKER_ROWS", f"季度跟踪指标数量合格: {tracker_rows}")

    required_phrases = ["当前价格隐含", "证伪", "条件树"]
    for phrase in required_phrases:
        if phrase not in text:
            fail(findings, "P1", "REQUIRED_ANALYSIS", f"缺少关键分析模块：{phrase}")

    if strict_manifest_expected:
        fail(findings, "INFO", "STRICT_MODE", "严格模式：将继续校验结构化 manifest")
    else:
        fail(findings, "P2", "REPORT_ONLY", "当前为 report-only，只能做结构/文本检查，不能证明数学与证据一致性")


def normalize_scenarios(forecast: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for k, v in (forecast or {}).items():
        nk = SCENARIO_ALIASES.get(str(k).strip().lower(), SCENARIO_ALIASES.get(str(k).strip()))
        if nk:
            out[nk] = v if isinstance(v, list) else []
    return out


def validate_manifest(data: Dict[str, Any], findings: List[Finding]):
    meta = data.get("meta") or {}
    forecast = normalize_scenarios(data.get("forecast") or {})

    # A. 三情景 × 三年：必须完全对齐
    for s in ("悲观", "中性", "乐观"):
        if s not in forecast:
            fail(findings, "P0", "MANIFEST_SCENARIO", f"manifest 缺少{s}情景")
            continue
        years = [int(x.get("year")) for x in forecast[s] if isinstance(x, dict) and str(x.get("year", "")).isdigit()]
        if len(years) != 3 or len(set(years)) != 3:
            fail(findings, "P0", "MANIFEST_3X3", f"{s}情景必须恰好包含3个预测年度", f"当前: {years}")
    if all(s in forecast for s in ("悲观", "中性", "乐观")):
        year_sets = [{int(x.get("year")) for x in forecast[s] if str(x.get("year", "")).isdigit()} for s in ("悲观", "中性", "乐观")]
        if not (year_sets[0] == year_sets[1] == year_sets[2]):
            fail(findings, "P0", "MANIFEST_YEAR_ALIGN", "三情景预测年度不一致", str(year_sets))
        elif len(year_sets[0]) == 3:
            ys = sorted(year_sets[0])
            if not (ys[1] == ys[0] + 1 and ys[2] == ys[1] + 1):
                fail(findings, "P1", "MANIFEST_YEAR_CONTIG", "预测3年不是连续年度", str(ys))

    required_forecast_fields = ("revenue_billion", "net_profit_billion", "eps")
    numeric_values = []
    for sname, rows in forecast.items():
        for r in rows:
            y = r.get("year")
            for field in required_forecast_fields:
                v = num(r.get(field))
                if v is None:
                    fail(findings, "P0", "FORECAST_FIELD", f"{sname}{y} 缺少可计算字段 {field}")
                else:
                    numeric_values.append(abs(v))
    if numeric_values and max(numeric_values) == 0:
        fail(findings, "P0", "FORECAST_PLACEHOLDER", "盈利预测仍为全0占位值，不能通过正式验收")

    # B. EPS × 股本 = 归母净利润
    shares_b = num(meta.get("shares_billion"))
    price_meta = num(meta.get("current_price"))
    cap_meta = num(meta.get("market_cap_billion"))
    if shares_b is None or shares_b <= 0:
        fail(findings, "P0", "META_SHARES", "manifest.meta 缺少有效 shares_billion（必须>0）")
    if price_meta is None or price_meta <= 0:
        fail(findings, "P0", "META_PRICE", "manifest.meta 缺少有效 current_price（必须>0）")
    if cap_meta is None or cap_meta <= 0:
        fail(findings, "P0", "META_MARKET_CAP", "manifest.meta 缺少有效 market_cap_billion（必须>0）")

    if shares_b is not None and shares_b > 0:
        for s, rows in forecast.items():
            for r in rows:
                y = r.get("year")
                eps, np = num(r.get("eps")), num(r.get("net_profit_billion"))
                if eps is not None and np is not None:
                    calc = eps * shares_b
                    if not close(calc, np, rel=0.025, abs_tol=0.03):
                        fail(findings, "P0", "MATH_EPS", f"{s}{y} EPS×股本 与归母净利润不一致", f"EPS {eps} × 股本 {shares_b} = {calc:.3f}亿，但归母={np}亿")

        if price_meta is not None and cap_meta is not None:
            calc_cap = price_meta * shares_b
            if not close(calc_cap, cap_meta, rel=0.02, abs_tol=0.1):
                fail(findings, "P0", "MATH_MARKET_CAP", "现价×股本 与总市值不一致", f"计算={calc_cap:.2f}亿，manifest={cap_meta:.2f}亿")

    # C. 估值必须和中性预测使用同一口径。支持 PE/PB/PS/DDM/DCF/SOTP 等。
    valuation = data.get("valuation") or {}
    if not valuation:
        fail(findings, "P1", "VALUATION_EMPTY", "manifest 缺少 valuation 估值对账块")
    else:
        ty = valuation.get("target_year")
        method = str(valuation.get("method") or valuation.get("primary_method") or ("PE" if valuation.get("pe") is not None else "")).upper()
        metric = str(valuation.get("linked_metric") or ("net_profit_billion" if valuation.get("base_net_profit_billion") is not None else ""))
        linked = num(valuation.get("linked_value"))
        if linked is None and valuation.get("base_net_profit_billion") is not None:
            linked = num(valuation.get("base_net_profit_billion"))
        multiple = num(valuation.get("multiple"))
        if multiple is None and valuation.get("pe") is not None:
            multiple = num(valuation.get("pe"))
        equity = num(valuation.get("equity_value_billion"))
        px = num(valuation.get("price_per_share"))

        base_row = next((r for r in forecast.get("中性", []) if r.get("year") == ty), None) if ty is not None else None
        if ty is None:
            fail(findings, "P1", "VAL_TARGET_YEAR", "valuation 缺少 target_year")
        elif base_row is None:
            fail(findings, "P0", "VAL_FORECAST_LINK", "估值目标年无法映射到中性盈利预测", f"target_year={ty}")
        elif linked is not None and metric in {"net_profit_billion", "revenue_billion"}:
            fc_val = num(base_row.get(metric))
            if fc_val is not None and not close(linked, fc_val, rel=0.015, abs_tol=0.03):
                fail(findings, "P0", "VAL_METRIC_MISMATCH", "估值使用的链接指标与盈利预测不一致", f"metric={metric}; 估值={linked}; 预测={fc_val}")

        # 对 PE/PB/PS 这类“权益指标×倍数=权益价值”的方法做直接数学校验。
        if method in {"PE", "PB", "PS"} and linked is not None and multiple is not None and equity is not None:
            calc = linked * multiple
            if not close(calc, equity, rel=0.02, abs_tol=0.2):
                fail(findings, "P0", "MATH_VALUATION", f"{method}估值数学不一致", f"链接值 {linked} × 倍数 {multiple} = {calc:.2f}亿，但估值={equity}亿")
        if equity is not None and shares_b is not None and shares_b > 0 and px is not None:
            calc_px = equity / shares_b
            if not close(calc_px, px, rel=0.02, abs_tol=0.2):
                fail(findings, "P0", "MATH_TARGET_PRICE", "估值市值÷股本 与目标价不一致", f"计算={calc_px:.2f}元，目标价={px}元")

    # D. SOTP 分部相加 + 与公司总利润对账
    sotp = data.get("sotp") or {}
    if sotp:
        parts = sotp.get("parts") or []
        part_values = [num(p.get("equity_value_billion")) for p in parts if isinstance(p, dict)]
        part_values = [x for x in part_values if x is not None]
        total_equity = num(sotp.get("total_equity_value_billion"))
        if part_values and total_equity is not None:
            calc = sum(part_values)
            if not close(calc, total_equity, rel=0.015, abs_tol=0.2):
                fail(findings, "P0", "SOTP_VALUE_SUM", "SOTP 分部估值之和与总估值不一致", f"分部和={calc:.2f}亿，总估值={total_equity:.2f}亿")

        profit_parts = []
        for p in parts:
            if not isinstance(p, dict) or p.get("include_in_profit_reconciliation", True) is False:
                continue
            v = num(p.get("net_profit_billion"))
            if v is not None:
                profit_parts.append((p.get("name", "未命名"), v))
        reconciled = num(sotp.get("reconciled_total_net_profit_billion"))
        if profit_parts and reconciled is not None:
            calc = sum(v for _, v in profit_parts)
            if not close(calc, reconciled, rel=0.02, abs_tol=0.05):
                fail(findings, "P0", "SOTP_PROFIT_SUM", "SOTP 分部利润之和与声明的公司利润不一致", f"分部={profit_parts}; 合计={calc:.2f}亿; 声明={reconciled:.2f}亿")

        ty = sotp.get("target_year")
        if ty is not None and reconciled is not None:
            row = next((r for r in forecast.get("中性", []) if r.get("year") == ty), None)
            if row:
                fc_np = num(row.get("net_profit_billion"))
                if fc_np is not None and not close(fc_np, reconciled, rel=0.02, abs_tol=0.05):
                    fail(findings, "P0", "SOTP_FORECAST_MISMATCH", "SOTP 对账利润与同年中性盈利预测不一致", f"SOTP={reconciled}亿，预测={fc_np}亿")

    # E. 证据层级：确认级结论必须有一手源
    evidence = data.get("evidence") or []
    if not evidence:
        fail(findings, "P1", "EVIDENCE_EMPTY", "manifest 未提供 evidence 证据清单")
    for i, ev in enumerate(evidence):
        if not isinstance(ev, dict):
            fail(findings, "P1", "EVIDENCE_FORMAT", f"第{i+1}条 evidence 格式错误")
            continue
        level = str(ev.get("level", ""))
        source_type = str(ev.get("source_type", "")).strip()
        src_title = str(ev.get("source_title", "")).strip()
        src_date = str(ev.get("source_date", "")).strip()
        src_ref = str(ev.get("source_ref", "")).strip()
        if not all([level, source_type, src_title, src_date, src_ref]):
            fail(findings, "P1", "EVIDENCE_FIELDS", f"证据条目字段不完整: {ev.get('claim_id', i+1)}", "level/source_type/source_title/source_date/source_ref 为必填")
        if any(k in level for k in CONFIRMED_LEVEL_KEYWORDS) and source_type not in PRIMARY_SOURCE_TYPES:
            fail(findings, "P0", "EVIDENCE_UPGRADE", f"确认级证据被低等级来源错误升级: {ev.get('claim_id', i+1)}", f"level={level}; source_type={source_type}; claim={ev.get('claim','')}")

    # F. 季度跟踪必须 10–15项
    tracking = data.get("quarterly_tracking") or []
    if not (10 <= len(tracking) <= 15):
        fail(findings, "P1", "TRACKING_COUNT", "manifest 季度跟踪指标必须10–15项", f"当前={len(tracking)}")
    for item in tracking:
        if isinstance(item, dict) and not item.get("invalidation_or_signal"):
            fail(findings, "P2", "TRACKING_SIGNAL", f"跟踪指标缺少逻辑触发阈值: {item.get('indicator','未命名')}")

    # G. 最终状态与证伪条件
    final = data.get("final") or {}
    status = final.get("status")
    if status not in ALLOWED_STATUS:
        fail(findings, "P1", "FINAL_STATUS", "最终状态不在允许集合", f"当前={status}")
    invalid = final.get("core_invalidation") or []
    if not (3 <= len(invalid) <= 7):
        fail(findings, "P1", "FINAL_INVALIDATION", "核心证伪条件建议3–7个", f"当前={len(invalid)}")


def summarize(findings: List[Finding]) -> Dict[str, int]:
    out = {"P0": 0, "P1": 0, "P2": 0, "INFO": 0}
    for f in findings:
        out[f.severity] = out.get(f.severity, 0) + 1
    return out


def write_outputs(outdir: Path, report: Path, manifest: Optional[Path], findings: List[Finding]):
    outdir.mkdir(parents=True, exist_ok=True)
    stats = summarize(findings)
    passed = stats.get("P0", 0) == 0 and stats.get("P1", 0) == 0
    payload = {
        "validator_version": VERSION,
        "report": str(report),
        "manifest": str(manifest) if manifest else None,
        "status": "PASS" if passed else "FAIL",
        "summary": stats,
        "findings": [asdict(x) for x in findings],
    }
    (outdir / "validation_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# A股个股深度研究 · 产物验收报告",
        "",
        f"- Validator: v{VERSION}",
        f"- 研究报告: `{report}`",
        f"- Manifest: `{manifest if manifest else '无（report-only）'}`",
        f"- **最终状态: {'PASS' if passed else 'FAIL'}**",
        f"- P0: {stats.get('P0',0)} ｜ P1: {stats.get('P1',0)} ｜ P2: {stats.get('P2',0)} ｜ INFO: {stats.get('INFO',0)}",
        "",
        "## 验收结果",
        "",
        "| 等级 | 代码 | 结果 | 详情 |",
        "|---|---|---|---|",
    ]
    for f in findings:
        msg = f.message.replace("|", "\\|")
        detail = (f.detail or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {f.severity} | `{f.code}` | {msg} | {detail} |")
    lines += [
        "",
        "## 判定规则",
        "",
        "- **P0**：硬错误。数学冲突、三情景/三年缺失、确认级证据误标等；禁止交付。",
        "- **P1**：重要缺陷。核心模块不完整、跟踪指标不足等；严格模式下禁止交付。",
        "- **P2**：改进项。不会单独阻断交付，但必须在下一版修复。",
        "- **INFO**：通过项或说明。",
    ]
    (outdir / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    return passed, payload


def main():
    ap = argparse.ArgumentParser(description="A股个股深度研究产物独立检查器")
    ap.add_argument("report", help="研究报告（HTML / Markdown）")
    ap.add_argument("--manifest", help="结构化 research_manifest.json（正式研究强制）")
    ap.add_argument("--report-only", action="store_true", help="只检查旧报告文本；不能证明模型数学/证据一致性")
    ap.add_argument("--out", default="validation", help="验收报告输出目录，默认 validation")
    args = ap.parse_args()

    report = Path(args.report)
    if not report.exists():
        print(f"❌ 报告不存在: {report}")
        return 2

    manifest_path = Path(args.manifest) if args.manifest else None
    if not args.report_only and manifest_path is None:
        print("❌ 正式验收必须提供 --manifest；旧报告临时检查请显式加 --report-only")
        return 2
    if manifest_path is not None and not manifest_path.exists():
        print(f"❌ manifest 不存在: {manifest_path}")
        return 2

    findings: List[Finding] = []
    raw, text = report_text(report)
    validate_report_structure(report, raw, text, findings, strict_manifest_expected=not args.report_only)

    if manifest_path is not None:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            fail(findings, "P0", "MANIFEST_PARSE", "manifest JSON 无法解析", str(e))
            data = {}
        if data:
            validate_manifest(data, findings)

    passed, payload = write_outputs(Path(args.out), report, manifest_path, findings)
    stats = payload["summary"]
    print("=" * 72)
    print(f"Research Artifact Validator v{VERSION}")
    print(f"状态: {'✅ PASS' if passed else '❌ FAIL'}")
    print(f"P0={stats.get('P0',0)}  P1={stats.get('P1',0)}  P2={stats.get('P2',0)}  INFO={stats.get('INFO',0)}")
    for f in findings:
        if f.severity in {"P0", "P1"}:
            print(f"  [{f.severity}] {f.code}: {f.message}" + (f" | {f.detail}" if f.detail else ""))
    print(f"验收报告: {Path(args.out) / 'validation_report.md'}")
    print("=" * 72)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
