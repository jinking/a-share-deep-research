# A股个股深度研究 Skill

> **WorkBuddy 专用**。一套可验证、可复现、可持续更新的 A 股个股研究流程：
> 产业趋势 → 公司卡位 → 真实需求/订单 → 财务兑现 → 业务拆分 → 盈利预测（三情景×连续三年） → 估值 → 市场验证 → 仓位条件 → 持续证伪 → **独立产物验收**。

## 数据源：三源协同

取数由 `scripts/fetch_stock.py` 统一编排，自动探测、**任一不可用都不中断研究**：

| 分组 | 数据源 | 覆盖 | 可用条件 |
|---|---|---|---|
| **core** | `westock-npm` | 公司简况、三大报表近 30 期、日 K 线、技术指标、股东结构、分红、资金/两融 | Node ≥ 18（`npx` 即用，零配置） |
| **enhanced** | `westock-cli` | 新闻、券商研报、公司公告、资金流向 | 已装 Go CLI（见下） |
| **search** | `neodata` | 最新财报、主营构成、供应链关系、业绩会纪要、机构一致预期、风险事件 | WorkBuddy 凭证有效 |

三源互补关系：**core 提供精确可复现的数值序列**，**enhanced 补资讯面**，**neodata 补最难结构化的语义信息**（财报全文、分业务、供应链、业绩会、一致预期）。

## 目录

```text
a-share-stock-deep-research/
├── SKILL.md                      # 主流程（0~8 步；报告正文 0~16 章）
├── CHANGELOG.md
├── README.md
├── providers/                    # 数据源 provider 层
│   ├── __init__.py               #   注册表 + 分组选择
│   ├── base.py                   #   接口：Provider / SearchProvider / 任务表
│   ├── westock_npm.py            #   core：npm 包
│   ├── westock_cli.py            #   enhanced：Go CLI
│   └── neodata.py                #   search：平台检索 + 凭证管理
├── core/                         # v3.0 核心包（不依赖 scripts/providers，可独立单测）
│   ├── normalize.py              #   股票代码归一化（无法判断时 raise，不静默兜底）
│   ├── issue.py                  #   验收问题的中性载体
│   ├── models/                   #   SourceDocument / Claim / EvidenceLink / ResearchState
│   ├── evidence/                 #   store（JSONL 证据库）/ hasher / locator / independence
│   └── validation/               #   evidence_validator / manifest_validator / codes（错误码目录）
├── schemas/                      # document / claim / evidence_link / research_manifest.v3
├── tests/                        # pytest 回归（validator / providers / evidence / integration）
├── scripts/
│   ├── fetch_stock.py            #   三源协同取数 + 搜索清单
│   ├── cross_validate.py         #   搜索值与结构化值交叉验证
│   ├── validate_report.py        #   独立产物验收器（结构/数学/模型口径/证据层级）
│   ├── build_evidence.py         #   v3.0 证据库构建与自检（init/register/verify/validate/show）
│   ├── attach_local_evidence.py  #   v3.0 绑定本地原件 + 补定位/摘录（防脑补硬闸）
│   ├── validate_evidence.py      #   v3.0 证据库独立验收（不需要报告与 manifest）
│   ├── migrate_manifest_v2_to_v3.py  # v2 → v3 迁移（产物标记 needs_verification）
│   ├── build_kline.py            #   raw/kline.txt → 研报内联 JS 数组
│   ├── apply_firstscreen.py      #   注入「V1 版式首屏」
│   ├── stamp_report.py           #   生成时间盖章（精确到秒，幂等）
│   ├── html_to_pdf.py            #   HTML 研报 → PDF（无头浏览器，引擎自动降级）
│   └── install_westock_cli.sh    #   安装 Go CLI 到技能私有目录
├── references/                   # 研究 SOP、证据规则、证据对象规范、估值适配、HTML 规范、产物验收规则、案例
├── assets/                       # 报告模板（.md 内容结构 + .html 统一版式）+ manifest 模板
├── examples/                     # 示例产物：意华股份成品报告 + 样板（manifest + 验收结果）
├── .github/workflows/test.yml    # CI：pytest + 存量样板回归（+ v3 证据验收）
└── tools/bin/                    # 私有二进制（安装后生成，可随时删除；不入库，见 .gitignore）
```

> `tools/bin/` 下的 `westock` 二进制（8.6MB）不纳入版本控制，克隆后按下方「增强源安装」执行一次即可。

## 使用

直接对 WorkBuddy 说：

```text
深度研究：意华股份 002897
按A股个股深度研究SOP研究：紫光股份 000938
更新一下立讯精密这只股票的季度研究结论
```

## 取数

```bash
# 一条命令跑完三源
python3 scripts/fetch_stock.py sz002897 --name 意华股份

# 查看已注册数据源
python3 scripts/fetch_stock.py --list-providers

# 指定 core 数据源
python3 scripts/fetch_stock.py sz002897 --name 意华股份 --provider westock-npm
```

产出：`raw/*.txt`、`01_历史财务.csv`、`02_资产负债关键项.csv`、`03_现金流.csv`、`04_技术指标.csv`、`05_股东结构.md`、`06_检索结果.md`、`待搜索清单.txt`、`取数元信息.json`。

## 增强源（Go CLI）安装

```bash
bash scripts/install_westock_cli.sh
```

从腾讯官方源 `stockbuddy.qq.com` 下载并做 SHA256 校验，**只装到技能私有目录** `tools/bin/`，不改系统 PATH、不需要 sudo。若系统 PATH 中已有 `westock`，则优先使用系统版本。未安装时增强任务自动跳过。

## neodata 凭证

凭证由 WorkBuddy 平台下发，本地缓存 12 小时。失效时：

```bash
python3 providers/neodata.py --status                     # 查看状态
# 调用 WorkBuddy 的 connect_cloud_service 工具取得凭证后：
python3 providers/neodata.py --save-token "<凭证>"          # 写入缓存
```

> ⚠️ 凭证只写本机 600 权限文件，禁止回显或写入报告。

## 交叉验证

```bash
python3 scripts/cross_validate.py research_sz002897 --json checks.json
```

```json
{
  "2025年营业收入(亿)": 64.01,
  "2025年归母净利润(亿)": 3.18
}
```

## 产物验收（正式研究强制）

报告与 `research_manifest.json` 完成后，必须运行独立校验器。**只有返回 PASS 才能标记「研究完成」**：

```bash
python3 scripts/validate_report.py report.html \
  --manifest research_manifest.json \
  --out validation
```

| 退出码 | 含义 |
|---|---|
| `0` | PASS，允许交付 |
| `1` | FAIL，存在 P0/P1 错误，禁止交付 |
| `2` | 参数 / 文件错误 |

**校验内容**

- 0–16 章完整性、证据标签体系、关键分析模块（当前价格隐含预期 / 证伪 / 条件树）
- 三情景 × **连续3年**（三个情景都必须覆盖完整三年）
- 数学一致性：`EPS×股本=归母`、`现价×股本=市值`、`PE/PB/PS 链接值×倍数=权益价值`、`权益价值÷股本=目标价`
- 口径一致性：盈利预测 / 估值 / SOTP 必须使用**同一年度的同一套中性利润**
- SOTP 分部估值之和 = 总估值；分部利润之和 = 声明利润
- **确认级结论必须有一手来源**（公司公告/财报、交易所、IR、客户公告、政府）；券商研报、媒体、自媒体不可升级为「已确认」
- 季度跟踪 10–15 项、最终状态在允许集合内、证伪条件 3–7 个

旧报告没有 manifest 时只能做结构体检：

```bash
python3 scripts/validate_report.py old_report.html --report-only --out validation
```

> `--report-only` 的通过**不视为正式验收通过**。详细等级与阻断规则见 `references/产物验收规则.md`。

## 证据层：Document → Claim → Evidence（v3.0）

v2 的 `evidence[]` 只是一段描述，Validator 无法判断「这份文档是否真实存在、第 12 页是否真写了这句话、所谓双源是否其实同源」。v3.0 把证据变成**可机器校验的对象**：

```text
Research Conclusion → Claim → EvidenceLink → SourceDocument → page/section/paragraph → 原文
```

```text
research_sz002897/
└── evidence/
    ├── documents.jsonl        # DOC_<指纹前8位>，含 source_type / source_group / sha256
    ├── claims.jsonl           # C_FIN_REV_2026H1 这类语义稳定 ID
    ├── evidence_links.jsonl   # 定位 + 原文摘录 + support_type
    └── raw/                   # 原始证据文件
```

```bash
# 建库 / 登记原始文档（自动复制进 raw/ 并算 sha256）
python3 scripts/build_evidence.py init     research_sz002897/evidence
python3 scripts/build_evidence.py register research_sz002897/evidence \
  --file ~/Downloads/2026H1.pdf --type interim_report \
  --title "意华股份2026年半年度报告" --published-at 2026-08-25 \
  --url "https://www.cninfo.com.cn/..." --group CNINFO_002897_2026H1 --pages 168

# 复核证据是否被事后替换 / 只校验证据库
python3 scripts/build_evidence.py verify research_sz002897/evidence
python3 scripts/validate_evidence.py     research_sz002897/evidence

# 把本地已有原件绑到已登记的 Document 上，并补 locator + 原文摘录
# 两阶段原子执行；文本类原件的 evidence_text 必须是文件真实子串，否则整体拒绝
python3 scripts/attach_local_evidence.py research_sz002897/evidence --plan attach_plan.json
python3 scripts/attach_local_evidence.py research_sz002897/evidence --plan attach_plan.json --dry-run

# v3 正式验收（报告 + v3 manifest + 证据库）
python3 scripts/validate_report.py report.html \
  --manifest research_manifest.v3.json \
  --evidence-dir research_sz002897/evidence \
  --out validation

# v2 → v3 迁移（产物一律标记 needs_verification，绝不自动宣称「已验证」）
python3 scripts/migrate_manifest_v2_to_v3.py research_manifest.json \
  --out research_manifest.v3.json --evidence-dir research_sz002897/evidence --critical E001,E007
```

v3 新增的 P0 拦截：`EVIDENCE_DOC_MISSING`（文档不存在）、`EVIDENCE_HASH_MISMATCH`（文件被替换）、`EVIDENCE_PRIMARY_REQUIRED`（确认级缺一手来源）、`EVIDENCE_DIRECT_REQUIRED`（已确认订单/收入/量产无 direct 证据）。
完整错误码、等级与 materiality 规则、来源独立性判定见 **`references/证据对象规范.md`**；Schema 见 `schemas/`。

**兼容性**：v2 manifest 继续可用，证据校验自动降级为「引用完整性 + 一条 P2 说明」。

**迁移后的典型形态**：`migrate_manifest_v2_to_v3.py` 只做结构化搬运，产物必然带 `EVIDENCE_NO_SOURCE`
（Document 既无 url 也无 local_path）以及 critical Claim 的 `EVIDENCE_LOCATOR_MISSING` / `EVIDENCE_TEXT_MISSING`。
这是**预期中间态，不是故障**——接着用 `attach_local_evidence.py` 把手上已有的原件绑上去；
绑不上的就构成了「待补原始资料清单」。示例见 `examples/意华股份002897_样板/待补原始资料清单.md`。

开发与测试：

```bash
pip install -r requirements-dev.txt
pytest -q          # 157 个用例：模型/Store/归一化/证据错误码/独立性/manifest v3/迁移/Schema/绑定原件/确定性取数/端到端
```

## 生成时间与文件名（精确到秒）

每份报告落盘后统一盖章——**生成时间精确到秒**（`YYYY-MM-DD HH:MM:SS`，本地时区），出现在
`title` / `h1 small` 副标题 / `footer` / 顶部注释块四处，且**四处必须一致**。**不要手写时间**
（手写必然停在日期精度或写错），一律由脚本读系统时钟写入：

```bash
# 盖章并同步文件名（_YYYYMMDD_HHMMSS）
python3 scripts/stamp_report.py 意华股份002897_深度研究_20260915.html --rename

# 交付前校验：退出码 1 = 未精确到秒，视为未完成
python3 scripts/stamp_report.py 意华股份002897_深度研究_20260915_090532.html --check
```

文件名规范：`<公司简称><代码>_深度研究_YYYYMMDD_HHMMSS.html`——同日多版并存时一眼看出先后。

> 脚本只认「生成于 / 报告生成时间」两个锚点，**不会误改** `数据截至 2026-09-14 收盘` 这类**数据时点**；
> 数据时点与生成时间是两个概念，不得混为一谈。

## PDF 导出（可选交付）

HTML 定稿后如需 PDF，用 `scripts/html_to_pdf.py`：

```bash
# 同名 .pdf（A4 纵向）
python3 scripts/html_to_pdf.py 东材科技601208_深度研究_20260915_182214.html

# 指定路径 / 纸张 / 方向
python3 scripts/html_to_pdf.py <report.html> --out <out.pdf> --format A3 --landscape
```

**为什么必须用浏览器**：报告里的日 K、饼图、双轴图都是 ECharts **运行时画在 canvas 上**的，
weasyprint / wkhtmltopdf 这类纯排版引擎**不执行 JavaScript**，导出来只有空白框。

引擎优先级（`--engine auto`，失败自动降级）：

| 顺序 | 引擎 | 说明 |
|---|---|---|
| 1 | `shell` | Playwright 缓存里的 **`chrome-headless-shell`**——纯无头二进制，**无 GUI 外壳，最可靠** |
| 2 | `chrome` | 本机 Chrome / Edge 无头打印（有正常 GUI 会话时可用） |
| 3 | `playwright` | Python 版 Playwright（可等图表就绪，需自行安装） |

> ⚠️ **优先 `shell`，不要依赖 `Chrome.app --headless`**：Chrome.app 的无头模式仍挂在 GUI 应用外壳上，
> 在无 GUI 会话的进程上下文（自动化脚本 / agent shell）里会**静默卡死在启动阶段**、无任何报错。
> 实测同机 `Chrome.app` 反复挂死，换 `chrome-headless-shell` 后 7.7 秒出稿。

脚本会把打印样式（`@page` 尺寸页边距 + 防跨页断裂）注入**临时副本**，源 HTML 一个字不改；
导出后自动校验页数与内嵌图像数——**引用了 ECharts 却 0 张内嵌图 = 导出失败**。

## 扩展新数据源

写一个 `Provider`（结构化）或 `SearchProvider`（检索）子类，在 `providers/__init__.py` 的 `REGISTRY` 里登记即可，主流程无需改动。
