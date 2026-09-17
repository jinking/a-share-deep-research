#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_evidence 模板 —— promote_plan.json + candidates.jsonl 生成器骨架。

用法：复制为 /tmp/build_<code>_evidence.py，替换 TODO。**整段复制华电/风华版再改内容**。

坑位提醒（全部实测咬过人）：
1. plan 结构固定为 {"promotions":[{candidate_id, document{...}, links[]}]}，自造 {"documents":[...]} 被拒。
2. Document.source_type 封闭枚举：annual_report/interim_report/quarterly_report/
   company_announcement/company_ir/data_vendor/exchange_filing/broker_report。
   分红/减值/解禁/发电量/异动 → company_announcement；IR 记录表 → company_ir；行情 → data_vendor。
3. plan 里**禁止**出现 claim_status / excerpt_verification_*（升格状态只由机器重算）。
4. local_file 相对 evidence/ 目录解析：vendor 文本放 raw/ 下写 "raw/kline.txt"；
   若报解析不到，试 "../raw/kline.txt"（版本差异）。page_count 必须正整数（vendor 文本写 1）。
5. 链接的 section 必须精确等于 document.sections 登记的章节名。
6. 先跑 precheck_anchors.py（promote 前预检），全 PASS 再 promote。
7. candidates 必须先用 build_evidence.py add-candidate CLI 注册（见 main）。
"""

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent   # evidence/
SKILL = Path.home() / "WorkBuddy/A股助手/.workbuddy/skills/a-share-stock-deep-research"
RETRIEVED = "2026-09-17T00:00:00+08:00"  # TODO: 取数时间


def D(cand, doc_id, source_type, title, issuer, published_at, local_file, source_group,
      page_count, sections, links, *, url=None, vendor=False, note=""):
    return {"cand": cand, "doc_id": doc_id, "source_type": source_type, "title": title,
            "issuer": issuer, "published_at": published_at, "local_file": local_file,
            "source_group": source_group, "page_count": page_count, "sections": sections,
            "links": links, "url": url, "vendor": vendor, "note": note}


def L(doc_key, claim_id, section, start, end, note, support="direct", vendor=False):
    """摘录 = 机器从文本层按 start/end 锚点裁剪，**人手不碰字符**。
    start/end 必须事先在对应 textlayer 里 grep 验证过（换行断词是最大敌人）。"""
    return (doc_key, claim_id, section, start, end, note, support, vendor)


DOCS = [
    # TODO: 逐文档照抄华电版 D(...) 结构改内容；每条 L() 的 start/end 先批量预检
    D("CAN_XXXX_2026H1", "DOC_XXXX_2026H1", "interim_report", "XX公司 2026 年半年度报告",
      "XX公司", "2026-08-27", "raw/2026半年报.pdf", "SSE_XXXX_2026H1",
      200, ["主要财务数据"],
      [
          L("h1", "C_FIN_H1_REV", "主要财务数据", "营业收入", "同比增减",
            "营收一手摘录"),
      ],
      url="https://pdf.dfcfw.com/pdf/H2_AN..._1.pdf"),
    # vendor 示例：
    # D("CAN_WESTOCK_KLINE_XXXX", "DOC_WESTOCK_KLINE", "data_vendor",
    #   "westock-data 日K线", "westock-data", RETRIEVED, "../raw/kline.txt",
    #   "WESTOCK_KLINE", 1, [], [...], vendor=True),
]


def npage(doc_key, vendor=False):
    """pdf 页数 = textlayer 页标记数；vendor 文本直接写 1，不走本函数。"""
    tl = BASE / "raw" / f"{doc_key}.textlayer.txt"  # TODO: 按实际文件名解析
    return sum(1 for ln in tl.read_text(encoding="utf-8").splitlines() if "<<<PAGE " in ln)


def build_links(d):
    """L 元组 → promote 所需的 link 字典；摘录由脚本从 textlayer 机械裁剪。"""
    out = []
    for item in d["links"]:
        doc_key, cid, sec, start, end, note, support, vendor = item
        if vendor:
            src = (BASE.parent / d["local_file"].lstrip("./")) if d["local_file"].startswith("..") \
                else BASE / d["local_file"]
        else:
            src = BASE / d["local_file"].replace(".pdf", ".textlayer.txt")
        lines = src.read_text(encoding="utf-8").splitlines()
        # 页码 = start 锚点之前的页标记数（子串计数！list.count 是整行相等，必错）
        pg = sum(1 for ln in lines[: next(i for i, l in enumerate(lines) if start in l)]
                 if "<<<PAGE " in ln) + 1
        i0 = next(i for i, l in enumerate(lines) if start in l)
        i1 = next(i for i, l in enumerate(lines) if end in l)
        evidence_text = "\n".join(lines[i0 : i1 + 1])
        out.append({"claim_id": cid, "page": pg, "section": sec,
                    "evidence_text": evidence_text, "support_type": support, "note": note})
    return out


def main():
    promos, nlink = [], 0
    for d in DOCS:
        doc = {k: v for k, v in d.items() if k not in ("cand", "links", "vendor")}
        doc["note"] = d.get("note") or f"{d['title']}，摘录取自官方文本层，可复核"
        ls = build_links(d)
        nlink += len(ls)
        promos.append({"candidate_id": d["cand"], "document": doc, "links": ls})
    plan = {
        "note": "线索摄入计划（v3.0.3）。local_file 相对本文件所在目录（evidence/）解析；"
                "不写 claim_status、不写 excerpt_verification_*；全部 evidence_text "
                "由构建脚本从官方文本层机器裁剪，promote 再重算比对。",
        "promotions": promos,
    }
    (BASE / "promote_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ promote_plan.json：{len(promos)} documents / {nlink} links")

    # candidates.jsonl：必须走 add-candidate CLI（线索层注册）
    cand_file = BASE / "candidates.jsonl"
    if cand_file.exists():
        cand_file.unlink()
    for d in DOCS:
        cmd = [sys.executable, str(SKILL / "scripts" / "build_evidence.py"), "add-candidate",
               str(BASE), "--type", d["source_type"], "--title", d["title"],
               "--provider", ("westock-data" if d["vendor"] else "dfcfw_mirror"),
               "--upstream", d["source_group"], "--snippet", (d.get("note") or d["title"])[:120],
               "--id", d["cand"], "--status", "reviewed", "--discovered-at", RETRIEVED]
        if d.get("url"):
            cmd += ["--url", d["url"]]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, f"{d['cand']}: {r.stdout} {r.stderr}"
    n = len(cand_file.read_text(encoding="utf-8").strip().splitlines())
    print(f"✅ candidates.jsonl：{n} 条")

    # 引用完整性断言：链接引用的 Claim 必须全部存在
    ids = {json.loads(l)["claim_id"] for l in open(BASE / "claims.jsonl", encoding="utf-8")}
    missing = {ls["claim_id"] for p in promos for ls in p["links"]} - ids
    assert not missing, f"引用了不存在的 Claim: {sorted(missing)}"
    print("✅ 全部链接引用的 Claim 均存在")


if __name__ == "__main__":
    main()
