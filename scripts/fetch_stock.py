#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOP 取数工具 —— WorkBuddy 专用版（三源协同）

用法:
    python3 fetch_stock.py <股票代码> [--name 股票名] [--out 输出目录] [--provider 名称]

示例:
    python3 fetch_stock.py sz002897 --name 意华股份
    python3 fetch_stock.py sz002897 --name 意华股份 --out research_sz002897

数据源（自动探测，任一不可用均不中断研究）:
    core     westock-npm  → 结构化数值：行情/K线/三大表/技术指标/股东/分红/资金两融
    enhanced westock-cli  → 资讯面：新闻/研报/公告/资金流向（需先安装 Go CLI）
    search   neodata      → 语义检索：财报全文/主营构成/供应链/业绩会/一致预期/风险
                            凭证失效时，由 Agent 调 connect_cloud_service 取回凭证后执行
                            `python3 providers/neodata.py --save-token "<凭证>"` 刷新

输出:
    <outdir>/raw/*.txt            各数据源原始返回
    <outdir>/01_历史财务.csv       近 8 年财务序列（含同比）
    <outdir>/02_资产负债关键项.csv
    <outdir>/03_现金流.csv
    <outdir>/04_技术指标.csv
    <outdir>/05_股东结构.md
    <outdir>/06_检索结果.md        neodata 语义召回（若可用）
    <outdir>/待搜索清单.txt        结构化盲区，必须搜索补齐
    <outdir>/取数元信息.json       数据源状态与质量提示

设计原则（来自实测复盘）:
    1. 结构化源强项：多期结构化财务、技术指标、股东结构、资金流向 → 自动取
    2. 结构化源盲区：最新一期财报（入库滞后约 1 个季度）、分业务、订单、管理层口径
       → neodata 检索 + 一手资料搜索双侧补齐
    3. 多源交叉验证关键数字，避免单一数据源幻觉
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 允许从任意工作目录直接运行本脚本：把技能根加入模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.normalize import StockCodeError, normalize_stock_code  # noqa: E402
from providers import first_for, list_providers  # noqa: E402
from providers.base import SEARCH_TASKS, TASK_SPECS  # noqa: E402

TIMEOUT = 120


# ---------------------------------------------------------------- 工具函数
def parse_md_table(text):
    """把返回的 markdown 表格解析成 (header, list[dict])"""
    lines = [l.rstrip() for l in text.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return [], []
    header = [h.strip() for h in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return header, rows


def num(v, default=0.0):
    """安全转数字"""
    if v is None:
        return default
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def plain_code(code: str) -> str:
    c = (code or "").lower().strip()
    for p in ("sh", "sz", "bj", "hk", "us", "t", "ks", "kq", "fu", "fx", "pt"):
        if c.startswith(p) and c[len(p):].isdigit():
            return c[len(p):]
    return c


# ---------------------------------------------------------------- K 线取数与回退
# 原先「主源取空 → npx 直取 → 校验 → build_kline」是写在 SKILL.md 里由 Agent 手工执行的；
# v3.0 §11.2 起这些确定性步骤由程序负责，Skill 不再指导人工修复。
KLINE_MIN_ROWS = 40
KLINE_FALLBACK_PKG = "westock-data-clawhub@1.0.4"
KLINE_RAW_NAME = "kline.txt"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_kline_text(text, *, min_rows: int = KLINE_MIN_ROWS):
    """校验 K 线文本是否可用（v3.0 §11.2）。纯函数，可离线测试。

    返回 (ok, rows, reason)：
        ok     —— 是否满足最低可用标准
        rows   —— 解析出的 [{'date', 'close'}] 列表
        reason —— 人类可读的判定说明

    规则：有效数据行 >= min_rows；日期形如 YYYY-MM-DD；收盘价为正数。
    单行非法会被跳过并计入 reason，但不单独判整体失败。
    """
    _, raw_rows = parse_md_table(text or "")
    rows = []
    bad_date = bad_close = 0
    for r in raw_rows:
        date = str(r.get("date") or "").strip()
        close = str(r.get("last") or "").strip()
        if not _DATE_RE.match(date):
            bad_date += 1
            continue
        try:
            value = float(close)
        except (TypeError, ValueError):
            bad_close += 1
            continue
        if value <= 0:
            bad_close += 1
            continue
        rows.append({"date": date, "close": value})

    if len(rows) < min_rows:
        return False, rows, f"有效行数 {len(rows)} < 最低要求 {min_rows}"
    if bad_date or bad_close:
        return True, rows, f"可用，跳过 {bad_date} 行日期非法 / {bad_close} 行收盘价非法"
    return True, rows, "OK"


def _run_kline_fallback(code: str, *, limit: int = 62, timeout: int = TIMEOUT) -> str:
    """用 npm 包直取日 K（等价于原先 SKILL.md 里的手工命令）。"""
    cmd = ["npx", "-y", KLINE_FALLBACK_PKG, "kline", code, "--period", "day", "--limit", str(limit)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  ⚠️  fallback 取数命令无法执行: {exc}")
        return ""
    return proc.stdout or ""


def fetch_kline_with_fallback(code, outdir, *, min_rows: int = KLINE_MIN_ROWS, runner=None):
    """取日 K：先校验主源产物，不达标则 fallback 直取并再次校验。

    返回 (ok, note, row_count)。失败时调用方应把 DATA_KLINE_UNAVAILABLE 写进元信息。
    """
    raw_dir = Path(outdir) / "raw"
    path = raw_dir / KLINE_RAW_NAME

    def read():
        return path.read_text(encoding="utf-8") if path.exists() else ""

    ok, rows, why = validate_kline_text(read(), min_rows=min_rows)
    if ok:
        return True, f"主源可用（{len(rows)} 行；{why}）", len(rows)

    print(f"  ⚠️  主源 K 线不达标：{why} → 启动 fallback（npx {KLINE_FALLBACK_PKG}）")
    text = (runner or _run_kline_fallback)(code, limit=max(min_rows + 2, 62))
    if not text:
        return False, f"主源不达标（{why}），fallback 未返回数据", 0

    ok2, rows2, why2 = validate_kline_text(text, min_rows=min_rows)
    if not ok2:
        return False, f"fallback 仍不达标：{why2}", len(rows2)

    raw_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True, f"fallback 成功（{len(rows2)} 行；{why2}）", len(rows2)


# ---------------------------------------------------------------- 数据源探测
def probe_sources(preferred=""):
    """探测三组数据源，返回 (core, enhanced, search) 三个 provider 或 None。"""
    print("=" * 70)
    print("【第①步】数据源探测")
    print("=" * 70)
    for name, desc, groups in list_providers():
        print(f"  · {name:<12} [{groups}]  {desc}")
    print()

    core = first_for("core", preferred)
    enhanced = first_for("enhanced")
    search = first_for("search")

    def _line(label, p):
        if p is not None:
            print(f"  ✅ {label:<9} {p.name}")
        else:
            print(f"  ⚪ {label:<9} 不可用（已跳过）")

    _line("core", core)
    _line("enhanced", enhanced)
    _line("search", search)
    print()

    if core is None and not preferred:
        print("  ❌ 结构化主源不可用：仍将生成搜索清单，改为纯一手资料检索路径")
    elif core is None:
        print(f"  ❌ 指定的数据源 '{preferred}' 不可用或未注册")
    return core, enhanced, search


# ---------------------------------------------------------------- 取数
def _fetch_group(provider, group, code, name, outdir, label):
    """按分组取数并落盘，返回 {task: 结果摘要}。"""
    raw = Path(outdir) / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    tasks = [t for t, spec in TASK_SPECS.items() if spec[2] == group]
    if group == "search":
        tasks = list(SEARCH_TASKS)

    print("=" * 70)
    print(f"【{label}】{provider.name} — {name}({code})")
    print("=" * 70)

    out = {}
    for task in tasks:
        r = provider.fetch(task, code, name=name, timeout=TIMEOUT)
        if group == "search":
            desc = SEARCH_TASKS[task][0]
            good = r.ok and r.has_content
        else:
            desc = TASK_SPECS[task][0]
            good = r.ok and r.has_table
        status = "✅" if good else "⚠️"
        (raw / f"{task}.txt").write_text(r.text or "", encoding="utf-8")
        out[task] = {"ok": good, "desc": desc, "len": len(r.text or "")}
        print(f"  {status} {desc:<18} ({len(r.text or ''):>6} 字符)")
    print()
    return out


# ---------------------------------------------------------------- 数据整理
def build_dataset(code, name, outdir):
    """把原始数据整理成结构化 CSV + 汇总"""
    import csv

    outdir = Path(outdir)
    raw = outdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    # ---- 历史财务序列
    bs, is_, cf = [], [], []
    if (raw / "finance_is.txt").exists():
        _, is_ = parse_md_table((raw / "finance_is.txt").read_text(encoding="utf-8"))
    if (raw / "finance_bs.txt").exists():
        _, bs = parse_md_table((raw / "finance_bs.txt").read_text(encoding="utf-8"))
    if (raw / "finance_cf.txt").exists():
        _, cf = parse_md_table((raw / "finance_cf.txt").read_text(encoding="utf-8"))

    annual = []
    for r in is_:
        d = r.get("EndDate") or r.get("_date", "")
        if d.endswith("12-31"):
            rev = num(r.get("OperatingRevenue"))
            npp = num(r.get("NPParentCompanyOwners"))
            annual.append({
                "年份": d[:4],
                "营业收入(亿)": round(rev / 1e8, 2),
                "归母净利润(亿)": round(npp / 1e8, 2),
                "EPS": r.get("BasicEPS"),
                "研发费用(亿)": round(num(r.get("RAndD")) / 1e8, 2),
            })
    annual.sort(key=lambda x: x["年份"])

    for i in range(1, len(annual)):
        p, c = annual[i - 1], annual[i]
        if p["营业收入(亿)"]:
            c["营收同比%"] = round((c["营业收入(亿)"] / p["营业收入(亿)"] - 1) * 100, 2)
        if p["归母净利润(亿)"]:
            c["归母同比%"] = round((c["归母净利润(亿)"] / p["归母净利润(亿)"] - 1) * 100, 2)

    if annual:
        keys = ["年份", "营业收入(亿)", "营收同比%", "归母净利润(亿)", "归母同比%", "EPS", "研发费用(亿)"]
        with open(outdir / "01_历史财务.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(annual)

    if bs:
        latest = sorted(bs, key=lambda x: x.get("EndDate") or x.get("_date", ""))[-1]
        bs_items = [
            ("资产总计", "TotalAssets"), ("负债合计", "TotalLiability"),
            ("货币资金", "CashEquivalents"), ("应收账款", "BillAccReceivable"),
            ("存货", "Inventories"), ("固定资产", "TotalFixedAsset"),
            ("商誉", "GoodWill"), ("短期借款", "ShortTermLoan"),
            ("长期借款", "LongtermLoan"), ("有息负债", "InterestBearDebt"),
            ("应付账款", "NotAccountsPayable"), ("归母权益", "SEWithoutMI"),
            ("流动负债", "TotalCurrentLiability"), ("流动资产", "TotalCurrentAssets"),
        ]
        with open(outdir / "02_资产负债关键项.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["科目", "金额(亿元)", "报告期"])
            for label, key in bs_items:
                v = num(latest.get(key))
                w.writerow([label, round(v / 1e8, 2) if v else "", latest.get("EndDate") or latest.get("_date")])

    if cf:
        latest_cf = sorted(cf, key=lambda x: x.get("EndDate", ""))[-1]
        with open(outdir / "03_现金流.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["科目", "金额(亿元)", "报告期"])
            for label, key in [
                ("经营活动现金流净额", "NetOperateCashFlow"),
                ("投资活动现金流净额", "NetInvestCashFlow"),
                ("筹资活动现金流净额", "NetFinanceCashFlow"),
                ("自由现金流(FCFF)", "FCFF"),
                ("销售收款现金", "GoodsSaleServiceRenderCash"),
            ]:
                v = num(latest_cf.get(key))
                w.writerow([label, round(v / 1e8, 2) if v else "", latest_cf.get("EndDate")])

    if (raw / "technical.txt").exists():
        _, tech = parse_md_table((raw / "technical.txt").read_text(encoding="utf-8"))
        if tech:
            t = tech[0]
            with open(outdir / "04_技术指标.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["指标", "数值"])
                for k, v in t.items():
                    if k not in ("code", "name", "date"):
                        w.writerow([k, v])

    sh_file = raw / "shareholder.txt"
    if sh_file.exists():
        (outdir / "05_股东结构.md").write_text(sh_file.read_text(encoding="utf-8"), encoding="utf-8")

    return annual, bs, cf


def build_search_digest(outdir):
    """把 neodata 各检索任务结果汇总成 06_检索结果.md"""
    outdir = Path(outdir)
    raw = outdir / "raw"
    chunks = []
    for task, (desc, _tpl) in SEARCH_TASKS.items():
        f = raw / f"{task}.txt"
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8").strip()
        if not text:
            continue
        chunks.append(f"## {desc}\n\n{text}\n")
    if chunks:
        (outdir / "06_检索结果.md").write_text(
            "# neodata 语义检索结果\n\n> 来源：WorkBuddy 平台金融数据服务（neodata）\n\n"
            + "\n".join(chunks),
            encoding="utf-8",
        )
    return len(chunks)


# ---------------------------------------------------------------- 搜索清单
SEARCH_CHECKLIST = """
======================================================================
【第③步】搜索侧补充清单（结构化盲区，需一手资料搜索确认）
======================================================================

⚠️ 关键提醒：结构化源的财务数据入库滞后（通常落后约 1 个季度）。
   例如 2026-09-14 时，最新年报可能只到 2025-12-31，而 2026H1 已披露。
   → 必须确认最新一期财报，否则会漏掉核心争议。
   （若 neodata 可用，见 06_检索结果.md，已自动检索其中若干项）

必搜清单（优先级从高到低）：
  □ 1. 最新一期财报（季报/中报）      → 营收/归母/扣非/毛利率/净利率/ROE/经营现金流
  □ 2. 分业务收入拆分                 → 各板块收入、占比、增速、毛利率
  □ 3. 利润质量归因                   → 汇兑损益、一次性收益、费用率变化
  □ 4. 业绩预告/管理层指引            → 下一期指引区间
  □ 5. 核心子公司/并购标的经营情况    → 单独收入、利润、市场份额
  □ 6. 客户端验证                     → 大客户订单、份额、客户资本开支
  □ 7. 新业务真实订单                 → 已确认订单 vs 在研/送样 vs 市场预期
  □ 8. 行业景气与政策                 → 上下游价格、行业增速、政策变化
  □ 9. 股权质押/解禁                  → 需查中登公司数据
  □ 10. 竞争格局                      → 主要对手对比、份额变化
  □ 11. 券商观点                      → 一致预期、目标价（低优先级，不得当事实）
  □ 12. 股价异动/催化剂               → 近期事件、板块相对强弱

搜索关键词模板：
  "{name} {code_plain} 最新 财报 营收 归母 扣非"
  "{name} 分业务 收入 拆分 增速"
  "{name} 汇兑损失 财务费用 一次性"
  "{name} 质押 股东 减持 解禁"
  "{name} 订单 客户 定点 产能"
"""


# ---------------------------------------------------------------- 质量校验
def quality_checks(annual, bs, cf, code):
    """对取到的数据做自动化质量校验，输出提示"""
    print("=" * 70)
    print("【第④步】数据质量自动校验")
    print("=" * 70)
    warns = []

    if annual:
        latest = annual[-1]
        if len(annual) >= 5:
            print(f"  ✅ 历史财务序列长度: {len(annual)}年（≥5年，满足SOP要求）")
        else:
            print(f"  ⚠️  历史财务序列仅 {len(annual)}年（SOP要求≥5年）")
            warns.append("历史财务不足5年")

        y = int(latest["年份"])
        gap = datetime.now().year - y
        if gap <= 1:
            print(f"  ⚠️  结构化源最新年报为 {y}年，距今{gap}年 → **必须确认最新一期财报**")
            warns.append(f"最新财报仅到{y}年，需搜索补充")
        else:
            print(f"  🔴 结构化源数据严重滞后（最新{y}年，距今{gap}年）→ 必须搜索补充")
            warns.append(f"数据滞后{gap}年")

        if latest.get("营收同比%") is not None and latest.get("归母同比%") is not None:
            rev_g, npp_g = latest["营收同比%"], latest["归母同比%"]
            d = rev_g - npp_g
            if d > 15:
                print(f"  🔴 营收增速({rev_g}%) 远超 归母增速({npp_g}%)，差{d:.1f}pct → 重点关注利润质量")
                warns.append("利润增速显著落后收入")
            elif d > 5:
                print(f"  ⚠️  营收增速快于归母 {d:.1f}pct，需关注")
            elif d < -15:
                print(f"  ⚠️  归母增速({npp_g}%) 远超 营收增速({rev_g}%)，差{-d:.1f}pct → 核查是否低基数/非经常性损益驱动")
                warns.append("利润增速远超收入，需核查驱动因素")
            else:
                print(f"  ✅ 营收与归母增速匹配（差{d:.1f}pct）")

        if len(annual) >= 2 and annual[-1].get("研发费用(亿)"):
            r0, r1 = annual[-2].get("研发费用(亿)") or 0, annual[-1]["研发费用(亿)"]
            if r0:
                g = (r1 / r0 - 1) * 100
                print(f"  ℹ️  研发费用同比 {g:+.1f}%")

    if bs:
        latest_bs = sorted(bs, key=lambda x: x.get("EndDate") or x.get("_date", ""))[-1]
        ta = num(latest_bs.get("TotalAssets"))
        tl = num(latest_bs.get("TotalLiability"))
        if ta:
            ratio = tl / ta * 100
            flag = "🔴" if ratio > 70 else ("⚠️ " if ratio > 65 else "✅")
            print(f"  {flag} 资产负债率 {ratio:.2f}%")
            if ratio > 70:
                warns.append(f"资产负债率{ratio:.1f}%偏高")
        gw = num(latest_bs.get("GoodWill"))
        if ta and gw:
            gp = gw / ta * 100
            flag = "⚠️ " if gp > 10 else "✅"
            print(f"  {flag} 商誉/总资产 {gp:.2f}%（绝对额{gw/1e8:.2f}亿）")

    if cf:
        latest_cf = sorted(cf, key=lambda x: x.get("EndDate", ""))[-1]
        nocf = num(latest_cf.get("NetOperateCashFlow"))
        print(f"  {'⚠️ ' if nocf < 0 else '✅'} 经营现金流净额 {nocf/1e8:,.2f}亿")

    if warns:
        print()
        print("  📋 校验提示汇总：")
        for w in warns:
            print(f"     - {w}")
    return warns


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="SOP 三源协同取数工具（WorkBuddy 专用）")
    ap.add_argument("code", nargs="?", help="股票代码，如 sz002475 / sh600487")
    ap.add_argument("--name", default="", help="股票名称（用于检索与搜索清单）")
    ap.add_argument("--out", default="", help="输出目录，默认 ./research_<code>")
    ap.add_argument("--provider", default="", help="指定 core 数据源（默认自动探测）")
    ap.add_argument("--list-providers", action="store_true", help="列出已注册数据源后退出")
    args = ap.parse_args()

    if args.list_providers:
        for name, desc, groups in list_providers():
            print(f"  {name:<12} [{groups}]  {desc}")
        return

    if not args.code:
        ap.error("需要提供股票代码（或用 --list-providers 查看数据源）")

    # 代码归一化：由 core/normalize.py 统一判断市场，不再静默兜底（v3.0 §11.1）
    try:
        code = normalize_stock_code(args.code)
    except StockCodeError as exc:
        print()
        print(f"❌ 无法判断股票代码所属市场: {args.code!r}")
        print(f"   {exc}")
        print("   支持形式: sz002897 / 002897 / 002897.SZ / SZ002897 / 600584 / bj430047")
        print("   规则: 60/68→sh，00/30→sz，4/8/92→bj；其余一律报错，不做猜测。")
        return 2

    name = args.name or code
    outdir = Path(args.out) if args.out else Path(f"research_{code}")
    outdir.mkdir(parents=True, exist_ok=True)

    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + f"  SOP 三源协同取数  |  {name} ({code})".ljust(66) + "║")
    print("║" + f"  时间: {datetime.now():%Y-%m-%d %H:%M:%S}".ljust(66) + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    # ① 探测三源
    core, enhanced, search = probe_sources(args.provider)

    if core is None and enhanced is None and search is None:
        (outdir / "待搜索清单.txt").write_text(
            SEARCH_CHECKLIST.format(name=name, code_plain=plain_code(code)), encoding="utf-8")
        (outdir / "取数元信息.json").write_text(json.dumps({
            "code": code, "name": name,
            "fetch_time": datetime.now().isoformat(),
            "sources": {"core": None, "enhanced": None, "search": None},
            "mode": "search_fallback",
            "note": "全部数据源不可用；请使用一手资料搜索，并用至少两个独立来源交叉核验",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("⚠️ 未探测到任何可用数据源，已切换为纯搜索模式。")
        print(f"✅ 已生成搜索清单: {(outdir / '待搜索清单.txt').resolve()}")
        return

    # ② 分源取数
    core_res = _fetch_group(core, "core", code, name, outdir, "第②步 a · 结构化") if core else {}
    enh_res = _fetch_group(enhanced, "enhanced", code, name, outdir, "第②步 b · 资讯增强") if enhanced else {}
    srch_res = _fetch_group(search, "search", code, name, outdir, "第②步 c · 语义检索") if search else {}

    # ③ 整理
    print("=" * 70)
    print("【第③步】数据整理")
    print("=" * 70)
    annual, bs, cf = build_dataset(code, name, outdir)
    print(f"  ✅ 历史财务序列: {len(annual)} 个年度")
    print(f"  ✅ 资产负债表:   {len(bs)} 期")
    print(f"  ✅ 现金流量表:   {len(cf)} 期")
    n_search = build_search_digest(outdir)
    if n_search:
        print(f"  ✅ 语义检索汇总: {n_search} 组 → 06_检索结果.md")
    print(f"  ✅ 输出目录:     {outdir.resolve()}")

    if annual:
        latest = annual[-1]
        print(f"\n  📌 结构化源最新年报: {latest['年份']}年 "
              f"营收{latest['营业收入(亿)']}亿 / 归母{latest['归母净利润(亿)']}亿")
        if len(annual) >= 2:
            print(f"     历史序列: {annual[0]['年份']} ~ {annual[-1]['年份']}（{len(annual)}年）")

    # ④ 质量校验
    warns = quality_checks(annual, bs, cf, code)

    # ⑤ K 线校验与自动回退（确定性逻辑，v3.0 §11.2 起不再交给 Agent 手工处理）
    print()
    print("=" * 70)
    print("【第⑤步】K 线校验与回退")
    print("=" * 70)
    kline_ok, kline_note, _ = fetch_kline_with_fallback(code, outdir)
    print(f"  {'✅' if kline_ok else '❌'} {kline_note}")
    if not kline_ok:
        warns.append("DATA_KLINE_UNAVAILABLE")

    core_missing = [
        core_res[t]["desc"]
        for t, spec in TASK_SPECS.items()
        if spec[2] == "core" and spec[1] and t in core_res and not core_res[t]["ok"]
    ]
    if core_missing:
        print()
        print(f"  ⚠️  关键结构化数据缺失: {'、'.join(core_missing)} → 请用一手资料搜索补齐")

    # 元信息 + 搜索清单
    (outdir / "待搜索清单.txt").write_text(
        SEARCH_CHECKLIST.format(name=name, code_plain=plain_code(code)), encoding="utf-8")
    (outdir / "取数元信息.json").write_text(json.dumps({
        "code": code, "name": name,
        "fetch_time": datetime.now().isoformat(),
        "sources": {
            "core": core.name if core else None,
            "enhanced": enhanced.name if enhanced else None,
            "search": search.name if search else None,
        },
        "annual_years": len(annual),
        "quality_warnings": warns,
        "tasks": {
            "core": core_res, "enhanced": enh_res, "search": srch_res,
        },
        "note": "结构化数据入库滞后，最新一期财报必须搜索补充",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(SEARCH_CHECKLIST.format(name=name, code_plain=plain_code(code)))
    print("=" * 70)
    print(f"✅ 取数完成，结果在: {outdir.resolve()}")
    print("   下一步: 按「待搜索清单」用 WebSearch 补充，再交叉验证关键数字")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
