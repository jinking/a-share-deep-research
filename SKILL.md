---
name: a-share-stock-deep-research
description: A股个股深度研究技能。用于“深度研究/分析某只A股”“按SOP研究某标的”“公司投资逻辑/基本面/估值/风险是什么”“季度更新某只股票研究”等任务。默认执行：识别公司类型→建立证据账本→结构化取数→搜索最新一手资料→交叉验证→16章研究→三情景×三年盈利预测与估值→生成 research_manifest.json→独立产物验收→市场验证→风险证伪→季度跟踪。适用于成长、周期、红利/公用事业、金融、多业务控股等A股公司；不得仅凭概念、股价涨跌或单一数据源下结论。
---

# A股个股深度研究

## 目标

把“产业叙事”转成一套可验证、可复现、可持续更新的个股研究流程：

**产业趋势 → 公司卡位 → 真实需求/订单 → 财务兑现 → 核心业务拆分 → 盈利预测 → 估值 → 市场验证 → 仓位条件 → 持续证伪**

核心不是给股票背书，而是回答四件事：
1. 公司为什么可能创造超额收益？
2. 这个逻辑有没有被真实订单和财务兑现？
3. 当前价格已经隐含了多少预期？
4. 什么数据出现时，当前结论必须被推翻？

---

## 触发方式

用户可直接说：
- “深度研究：股票名称/代码”
- “按A股个股深度研究SOP研究：股票名称/代码”
- “这家公司投资逻辑、估值和风险是什么？”
- “更新一下这只股票的季度研究结论”

默认执行完整研究；若用户明确只要某一部分，则只执行对应模块，但仍遵守证据规则。

---

## 运行环境（WorkBuddy 专用）

本技能为 **WorkBuddy 专用**，位于项目级目录 `.workbuddy/skills/a-share-stock-deep-research/`，取数依赖三项平台能力：

1. **结构化行情/财务** —— 公开 npm 包 `westock-data-clawhub`（`npx` 即用，需 Node ≥ 18）
2. **资讯面** —— 腾讯官方 Go CLI `westock`（首次需 `bash scripts/install_westock_cli.sh`）
3. **语义检索** —— WorkBuddy 平台金融数据服务 `neodata`（凭证由平台下发）

> 本技能可能**不会出现在宿主的可用技能清单中**（清单为会话启动时的快照）。
> 因此：接到「深度研究某只A股」类任务时，**先确认本技能是否已被加载**；若宿主未自动加载，**手动读取 `SKILL.md` 与 `references/` 后按本流程执行**，不要因为清单里没有就直接裸答。

代价对比：多读 5 个文件 ≈ 几十秒；漏掉技能 ≈ 整个研究失去证据分层与交叉验证，结论可信度下降一个档次。

---

## 总流程（严格按序）

### 0. 识别标的与研究类型

先确认：公司名称、代码、上市板块、主营业务、当前报告期。

然后识别公司类型，选择估值/财务重点：
- **成长/科技制造**：增长兑现、研发、份额、PE/PEG/SOTP
- **周期/资源**：产品价格、成本曲线、产能周期、标准化利润、PB/PE/EV-EBITDA
- **红利/公用事业**：现金流、资本开支、负债、股息可持续性、DCF/DDM/PE
- **金融**：ROE、资产质量、净息差/手续费、资本充足率、PB-ROE
- **多业务/控股型**：核心子公司拆分、SOTP、少数股东权益与资本配置

若无法明确分类，用“混合模式”，不要强行套单一估值框架。

### 1. 建立证据账本

研究过程中维护关键结论的证据状态：

| 标签 | 含义 |
|---|---|
| `【事实】` | 公告、财报、交易所文件等可核验事实 |
| `【管理层口径】` | 公司/管理层表述，不等于已兑现 |
| `【推断】` | 基于事实做出的逻辑推理 |
| `【假设】` | 盈利预测和估值模型输入 |
| `【无法确认】` | 当前取不到或无法交叉确认 |

关键数字同时记录：**数值、口径、报告期/时点、来源、发布时间、是否交叉验证**。

**线索 ≠ 证据（v3.0.1 起）**。研究过程中最先出现的东西——搜索结果、neodata 摘要、券商转述、媒体转述——
是**线索**，不是证据。线索先落成 `EvidenceCandidate`（`CAN_` 前缀），拿到原件、登记 Document、
算出 SHA256、补上定位与原文摘录之后才能升格为证据。线索不能承担确认级结论、不能提供 critical Claim
的定位与摘录、也不计入来源独立性。升级的唯一通道是 `scripts/promote_evidence_candidate.py`，**不要手写 Document 绕过去**。

**时间要分清三个时点**：`as_of`（信息截止）/ `market_data_as_of`（行情截止）/ `generated_at`（报告生成）。
证据的 `published_at` 不得晚于 `as_of`；行情不得晚于报告生成时间。

### 2. 多源取数（三源协同，一条命令跑完）

```bash
python3 scripts/fetch_stock.py <代码> --name <名称> [--out <输出目录>]
```

> `<代码>` 可传 `sz002897` / `002897` / `002897.SZ` 等任意常见形式——由 `core/normalize.py`
> 统一归一化，并据此决定输出目录（`research_sz002897`）。
> **无法判断所属市场时脚本直接报错退出（退出码 2），不再静默兜底**——
> 过去"把纯数字当成无前缀代码继续跑、三大报表与 K 线全取空却只留一行提示"的行为已移除。

脚本自动探测并协同三个数据源，**任一不可用都不中断研究**：

| 分组 | 数据源 | 取到什么 | 可用条件 |
|---|---|---|---|
| **core** | `westock-npm` | 公司简况、三大报表近 30 期、日 K 线、技术指标、股东结构、分红、资金/两融 | Node ≥ 18（`npx` 即用） |
| **enhanced** | `westock-cli` | 新闻、券商研报、公司公告、资金流向 | 已装 Go CLI（`bash scripts/install_westock_cli.sh`） |
| **search** | `neodata` | 最新财报、主营构成、供应链关系、业绩会纪要、机构一致预期、风险事件 | WorkBuddy 凭证有效 |

输出：`raw/*.txt`（各源原始返回）、`01~05` 结构化 CSV/MD、`06_检索结果.md`（neodata 汇总，若可用）、`待搜索清单.txt`、`取数元信息.json`。

**日 K 线**：`fetch_stock.py` 第⑤步已内置「主源校验 → 不达标自动 fallback（npm 直取）→ 再校验」，
彻底失败时会在 `取数元信息.json` 写入 `DATA_KLINE_UNAVAILABLE`。
**这一步不需要任何手工干预**，也不要用 `npx` 自己去补。

拿到 `raw/kline.txt` 后本地构建图表数组：

```bash
python3 scripts/build_kline.py --days 60 --out kline.js
```

> ⚠️ `build_kline.py` 要读**当前目录**下的 `raw/kline.txt`，所以必须在 `research_<代码>/` 里执行；
> 此时 `scripts/...` 的相对路径已失效，**改用技能目录的绝对路径**：
> `python3 /path/to/.workbuddy/skills/a-share-stock-deep-research/scripts/build_kline.py . --days 60 --out kline.js`。
>
> ⚠️ `raw/kline.txt` 的列序是 `date | open | last | high | low | volume | amount | exchange`——
> **`last`（第 4 列）才是收盘价**，第 3 列是开盘价。用 `awk -F'|' '{print $3}'` 取"收盘价"会拿到开盘价。

**neodata 凭证刷新**（仅当 `python3 providers/neodata.py --status` 显示缺失/过期时）：

1. 调用 WorkBuddy 的 `connect_cloud_service` 工具取得凭证；
2. `python3 providers/neodata.py --save-token "<凭证>"` 写入本机缓存（12 小时有效）；
3. 重跑取数。

> ⚠️ 凭证只写本机 600 权限文件，**禁止回显、禁止写进报告**。

**注意：结构化数据不是事实的唯一来源。** 数据源不可用或最新报告期滞后时流程不得终止，立即进入搜索回退路径。

### 3. 搜索最新一手资料（不可跳过）

neodata 若可用，已自动覆盖下列第 1、2、4、6 项（见 `06_检索结果.md`），但仍需用一手资料**核实并补足**：
1. 最新一期季报/中报/年报及公告日期
2. 分业务收入、毛利率、产品结构
3. 扣非与利润质量归因
4. 核心子公司/并购标的经营
5. 客户、订单、定点、送样、在研的真实状态
6. 股权质押、减持、解禁、股权变化
7. 行业景气、技术路线、价格、政策、客户资本开支
8. 竞争对手与市场份额变化
9. 近期重大资本开支、产能和融资
10. 影响未来6–18个月的催化剂与风险事件

搜索和来源规则见 `references/搜索与证据规则.md`。

### 4. 交叉验证

对会直接影响投资结论的数字进行双源验证。可运行：

```bash
python3 scripts/cross_validate.py <研究目录> --json checks.json
```

判定：
- 双源一致 → 提升可信度
- 不一致 → 查口径/时点/单位，不得自行取平均
- 数据库缺失 → 以更高等级的一手来源为准
- 只有单一低等级来源 → 标记 `【无法确认】` 或低可信度

**不能因为“两个网页写得一样”就视为真正交叉验证；若二者都转引同一原始新闻，仍算单一源。**

### 5. 按16章研究框架建模

完整框架见 `references/研究SOP.md`。必须完成：
- 核心争议与预期差量化
- 公司业务地图
- 客户/订单真实性分层
- 近5年+最新一期财务质量
- 核心业务/子公司单独拆分
- 悲观/中性/乐观三情景 × **连续3年**预测（三个情景都必须覆盖完整三年，不允许“第一年三情景、后两年只有中性”）
- 与公司类型匹配的估值
- 当前价格隐含预期
- 市场验证与交易条件树
- 风险等级与3–5个证伪指标
- 未来6–18个月催化剂
- 季度跟踪表（10–15 项）

### 6. 生成机器可审计 Manifest

完整研究除人读报告外，必须同步生成 `research_manifest.json`，骨架用 `assets/research_manifest.template.json`。

Manifest 只记录**会影响结论的关键结构化数据**：
- 当前价、总股本、总市值
- 悲观/中性/乐观 × **连续3年**预测（每年含营收、归母、EPS）
- 估值使用的目标年利润、倍数、合理市值/股价
- SOTP 分部利润与分部价值（如适用；未盈利的期权业务须置 `include_in_profit_reconciliation=false`）
- 关键证据及其层级、来源类型、日期、定位
- 10–15 个季度跟踪指标（每项须有 `invalidation_or_signal`）
- 最终状态与核心证伪条件（3–7 个）

**禁止只生成报告、不生成 manifest。** Manifest 是 Validator 做跨章节数学/口径对账的权威输入。

### 7. 独立产物验收（不可跳过）

报告与 manifest 完成后必须运行：

```bash
python3 scripts/validate_report.py <report.html或report.md> \
  --manifest <research_manifest.json> \
  --out <validation目录>
```

Validator 与研究生成过程职责分离，检查：
1. 0–16 章是否完整；
2. 三情景 × 连续3年是否完整；
3. `EPS×股本`、`现价×股本`、`PE/PB/PS 估值`、`估值得市值÷股本=目标价` 等数学是否一致；
4. 盈利预测、估值、SOTP 是否使用同一年度、同一套中性利润口径；
5. SOTP 分部利润/估值能否对回公司总值；
6. “已确认订单/已量产/已批量交付”等确认级结论是否有一手来源（公司公告/财报、交易所、IR、客户公告、政府；**券商研报、媒体、自媒体不可升级为确认级**）；
7. 季度跟踪是否保持 10–15 个关键指标；
8. 最终状态与证伪条件是否完整。

**退出码 0 = PASS，只有 PASS 才能向用户标记「研究完成」。** 验收等级与阻断规则见 `references/产物验收规则.md`。

#### v3：证据层校验（manifest_version = 3）

当 manifest 为 v3（`"manifest_version": 3`）时，**必须**同时提交 Evidence Store，否则报 `EVIDENCE_STORE_MISSING`：

```bash
python3 scripts/validate_report.py <report.html> \
  --manifest <research_manifest.v3.json> \
  --evidence-dir <research_xxx/evidence> \
  --out <validation目录>
```

新增检查项（完整错误码见 `references/证据对象规范.md`）：

9. Claim 指向的 Document 是否真实存在（`EVIDENCE_DOC_MISSING`，P0）；
10. 证据文件 hash 是否与登记值一致——**证据是否被事后替换**（`EVIDENCE_HASH_MISMATCH`，P0）；
11. 确认级结论是否由允许的一手来源支撑、是否存在 `direct` 证据（`EVIDENCE_PRIMARY_REQUIRED` / `EVIDENCE_DIRECT_REQUIRED`，P0）；
12. 是否把**线索**（Candidate）当成正式证据引用（`CANDIDATE_USED_AS_EVIDENCE`，P0）；
13. critical Claim 是否有定位、是否有原文摘录（`EVIDENCE_LOCATOR_MISSING` / `EVIDENCE_TEXT_MISSING`，P1）；
14. 所谓「双源」是否真正独立（同 `source_group` 的转载只算一个来源，`EVIDENCE_SOURCE_NOT_INDEPENDENT`，P1）；
15. 证据发布时间是否晚于 `as_of`（`SOURCE_DATE_AFTER_AS_OF`，P1）；行情是否晚于 `generated_at`（`MARKET_DATA_AFTER_GENERATED_AT`，P1）；
16. `generated_at` 是否与报告文件名 `<YYYYMMDD_HHMMSS>` 及报告内「生成于 …」一致（`GENERATED_AT_MISMATCH`，P1）；
17. `basis_claim_ids` 是否指向真实存在的 Claim（`CLAIM_BASIS_UNKNOWN`，P1）；`fact` 是否建立在未确认的推导之上（`CLAIM_BASIS_LEVEL_INVALID`，P1）；
18. `unconfirmed` / `assumption` 等级的 Claim 是否被标成 critical-supported（`CLAIM_UNCONFIRMED_SUPPORTED`，P1）；
19. **跨产物一致性（v3.0.2）**：报告里的锚点声明是否与 Claim Ledger 一致（`REPORT_*`，P0/P1，见下方规则 N）；
20. **摘录验证状态（v3.0.2）**：critical Claim 的摘录是否真的验证过，而非「没法比对所以跳过」（`EVIDENCE_EXCERPT_UNVERIFIED`，P1）；
21. **时间模型完整性（v3.0.2）**：正式 v3 是否同时给出 `as_of` / `market_data_as_of` / `generated_at`（`TIME_MODEL_INCOMPLETE`，P1）；
22. **Provider ≠ Source（v3.0.2）**：取数服务商是否被错当成一手来源（provider 白名单见 `core/models/provenance.py`）。

只跑跨产物一致性（改报告文案时最快定位漂移）：

```bash
python3 scripts/validate_report.py <report.html> \
  --manifest <research_manifest.v3.json> \
  --evidence-dir <research_xxx/evidence> \
  --claim-only --out <validation目录>
```

**线索 → 证据（唯一通道）**：

```bash
# a) 先把搜索/摘要阶段的线索登记下来（线索 ≠ 证据，不参与验收通过口径）
python3 scripts/build_evidence.py add-candidate <research_xxx/evidence> \
  --url "<原件地址>" --type interim_report --title "<文档标题>" --provider cninfo
python3 scripts/build_evidence.py candidates <research_xxx/evidence>

# b) 拿到原件后 promote：确认来源 → 存原件 → 算 SHA256 → 绑 source_group → 补 locator → 抽原文摘录
python3 scripts/promote_evidence_candidate.py <research_xxx/evidence> --plan promote_plan.json --dry-run
python3 scripts/promote_evidence_candidate.py <research_xxx/evidence> --plan promote_plan.json
```

`promote_plan.json` 的 `links[]` 二选一：手写 `evidence_text`（会被子串校验），或只给
`excerpt_anchor` + `excerpt_tail` **让脚本从原文里剪**——后者不需要被信任，只需要被复核。
PDF 等二进制原件跳过硬闸（第一版不做 OCR），此时请把**官方文本层**一起留存并单独比对，
并把摘录状态如实写为 `unverified`——**「跳过校验」不等于「已验证」**。落盘后脚本会自动重算摘录验证状态。

```bash
# 独立重算摘录验证状态（先报告，确认无误再加 --write）
python3 scripts/verify_excerpts.py <research_xxx/evidence>
python3 scripts/verify_excerpts.py <research_xxx/evidence> --write
```

证据库自身的构建与自检：

```bash
python3 scripts/build_evidence.py init     <research_xxx/evidence>
python3 scripts/build_evidence.py register <research_xxx/evidence> --file <原始文件> --type interim_report --title "..." --url "..." --group <同一上游标识>
python3 scripts/build_evidence.py verify   <research_xxx/evidence>   # 检查原件是否被事后替换
python3 scripts/validate_evidence.py       <research_xxx/evidence>
```

> **纪律**：Validator 只检查、不修改产物；`evidence_text` 必须是原文摘录，不得改写或脑补；
> promote **永不写** `claims.jsonl`——Claim 能否 `supported` 只由 Document + EvidenceLink 决定；
> 不得通过放宽规则或删数据让校验变绿。

若返回 FAIL：
- 按 `validation/validation_report.md` 的 P0/P1 逐项修正报告或 manifest；
- **不得通过删数据、放宽证据等级规则或放宽容差来“绕过”错误**；
- 修正后重跑 Validator，直到 PASS。

旧报告若无 manifest，只允许 `--report-only` 做结构体检；**report-only 通过不能视为正式验收通过**。

### 8. 输出研究报告

**内容结构**按 `assets/报告模板.md`（0–16 章）。
**版式**一律套用 `assets/报告模板.html`（复制该文件再填充），**不得从空白另起配色或另设 CSS 变量**——否则同一技能产出的报告会版式不统一（历史上已发生：两份同技能报告品牌主色、章节编号格式、标题层级各不相同）。该模板的视觉设计基准为京泉华 V1 研报。

**首屏为强制项**（参考 V1 版式，放在正文 0 章之前，**顺序不可调换**）：

1. `header`：kicker 标签 + 大标题 + 副标题（含「数据截至 YYYY-MM-DD 收盘 ｜ 生成于 YYYY-MM-DD HH:MM:SS」，**生成时间精确到秒**）。
2. **公司简介**（`.fs-intro`）：一段话讲清「这是一家什么公司」——一句话定位 → 成立/上市 → 主营与产品线 → 规模（营收/员工/市值）→ 行业位置 → 核心看点及当前兑现度。**只写可核验的事实，查不到的不写**（市占率、"唯一/第一" 无一手出处一律不写）；与核心结论分工明确：简介回答"它是什么"，结论回答"该不该买"。
3. **首屏结论卡**：左侧一段话核心结论 + 研究状态 pill；右侧**报告日真实行情**（收盘价、涨跌幅、总市值、开/高/低/成交额/换手）；下方 8 个 KPI；卡底数据来源。
4. **近 3 个月日 K 线卡**：`raw/kline.txt`（60 个交易日）→ candlestick + MA5/MA10/MA20 + 成交量副图，**A 股口径红涨绿跌**。

首屏所有数字**必须取自当日真实行情与本报告自身结论**，不得杜撰或沿用其它标的的数据。
已有报告补首屏，直接跑 `scripts/apply_firstscreen.py`（详见下方文件导航），只改开头、正文不动。「一句话本质 / 一句话投资逻辑」属正文 §2，**不占首屏**。

**报告生成时间必须精确到秒（强制项）**：格式 `YYYY-MM-DD HH:MM:SS`（本地时区），四处必须一致 —— `title` / `h1 small` 副标题 / `footer` / 顶部注释块。**不要手写时间**（手写必然停留在日期精度或写错）；报告落盘后统一跑盖章脚本，由脚本取系统时钟写入，幂等可重跑：

```bash
python3 scripts/stamp_report.py <report.html>              # 当前本地时间盖章
python3 scripts/stamp_report.py <report.html> --rename     # 同时把文件名时间同步为 _YYYYMMDD_HHMMSS
python3 scripts/stamp_report.py <report.html> --check      # 交付前校验：是否已精确到秒
```

**文件名同样精确到秒**：`<公司简称><代码>_深度研究_YYYYMMDD_HHMMSS.html`（例：`意华股份002897_深度研究_20260915_090532.html`），便于同日多版并存、一眼定位版本先后。`--check` 退出码非 0 一律视为未交付完成。

**可选交付：PDF 版（`scripts/html_to_pdf.py`）** —— HTML 定稿后如需 PDF，用**无头浏览器**导出。**禁止用 weasyprint / wkhtmltopdf 等纯排版引擎**：它们不执行 JavaScript，拿不到 ECharts 画在 canvas 上的图表，导出来只会是空白框。

```bash
python3 scripts/html_to_pdf.py <report.html>                             # 同名 .pdf，A4 纵向
python3 scripts/html_to_pdf.py <report.html> --out <out.pdf>             # 指定路径
python3 scripts/html_to_pdf.py <report.html> --format A3 --landscape    # 换纸张/方向
```

引擎优先级（`--engine auto`，失败自动降级）：**`chrome-headless-shell`（Playwright 缓存内的纯无头二进制，最可靠）→ Chrome/Edge → Playwright**。
> ⚠️ 首选 shell 而非 Chrome.app 的原因（2026-09-15 实测）：Chrome.app 的 `--headless=new` 仍挂在 GUI 应用外壳上，在**无 GUI 会话**的进程上下文（自动化脚本 / agent shell）里会**卡死在启动阶段**，表现为静默挂起、无任何报错。`chrome-headless-shell` 专为无头编译，不受影响。

打印样式（`@page` 尺寸页边距 + 防跨页断裂）注入**临时副本**，源 HTML 一个字不改。导出后自动校验页数与内嵌图像数：**报告引用了 ECharts 却 0 张内嵌图 = 导出失败**（常见是转换时无网络拉不到 CDN，或 JS 没跑起来）。

**首屏两条硬规则**（2026-09-14 踩坑后固化，细节见 `references/HTML输出规范.md` §2.2）：

- **两列用 Grid 不用 `flex-wrap`**：`.fs-top{display:grid;grid-template-columns:minmax(0,1fr) auto}`，价格块 `.fs-quote{text-align:right;justify-self:end}`；否则「结论段 760px + 价格块 ≈314px」超宽时会把**价格块换行挤到左侧**。
- **配色只准引用令牌、不准硬编码**：`var(--brand,var(--blue,…))` / `var(--up,var(--red,…))` / `var(--down,var(--green,…))` / `var(--ink…)`；涨跌类名 `.r`/`.g` 必须成对存在（**只写 HTML 不写 CSS 变体 = 价格不显红绿**）。K 线同理，运行时读 `--up/--down`。
- **首屏 CSS 单一来源 = `scripts/apply_firstscreen.py` 的 `CSS` 常量**；改完样式必须 `--sync-template` 刷进 `assets/报告模板.html`，交付前 `--check-template` 验脱钩。

- 输出默认 **HTML 研报**：浅底深字研报风、首屏结论先行、趋势/占比/分布类数据用 ECharts、关系拓扑用 SVG/CSS，章节与模板 0–16 章一一对应。
- **长报告不要一次 `Write` 写完**（约 80 KB / 5.6 万字符会被输出上限截断）——用「复制模板 → 分块 `Edit` 填首屏与 §0–§5 → §6 起到 `<script>` 一次性写临时文件 → Python 按边界拼接」，详见 `references/HTML输出规范.md` §2.4。
- **克隆模板后必查三处占位残留**：① `<script>` 区块内嵌的**示例标的 K 线价（`kDates`/`kValues`）与饼图 `【业务A】` 类占位**——必须整体替换为真实 `research_*/kline.js` 与最新业务结构，**不能只改标题**；② `<title>` 与顶部注释块占位（保留会把 `【】` 残留进交付件，被判「占位符未清」）；③ 首屏 CSS 若模板已含则勿重复注入。填充后跑规范 §4 质检（`node --check` + K 线逐字节比对 + 占位符扫描）。
- 样式规则与质检清单见 `references/HTML输出规范.md`；**组件类名、章节编号、红涨绿跌、首屏令牌回退链均为锁定项**。
- HTML 交付前**必须**对内联 JS 做语法自检（`node --check`），报错改到通过为止——一处括号失配会导致整页图表全废。
- 交付前另做三项文本自检（规范 §4）：**日 K 内嵌数据与 `research_*/kline.js` 逐字节比对**、**中日汉字混入扫描**（如「証実」）、**同指标跨章口径一致性**。
- 仅在用户明确要求纯文本 / Markdown 时才改用 `.md` 输出。

开头先给“核心结论 + 最关键争议 + 当前研究状态”，正文再展开。最终状态只能是条件判断：

**研究池 / 观察 / 试仓 / 加仓 / 持有 / 降仓 / 回避**

不要输出脱离条件的“无脑买入/卖出”。

---

## 研究硬规则

### A. 先产业，再公司，再财务，再估值，最后才看交易

不得从股价涨跌反推基本面；不得因为“AI/机器人/算力/新能源”等概念映射就直接判定公司受益。

### B. 最新报告期优先于历史数据库

历史数据用结构化源提高效率；最新财报和重大公告必须用一手资料校正时效性。

### C. 订单状态必须分层

严格区分：
- 已确认收入
- 已确认订单/定点
- 管理层口径
- 在研/送样/小试
- 市场预期/传闻

不可跨层级表达。

### D. 利润必须检查“质量”

至少核查：营收、归母、扣非、毛利率、净利率、ROE、经营现金流、应收、存货、有息负债、资产负债率、资本开支、研发费用，以及一次性收益/汇兑/并表/费用率等因素。

现金流为负时必须拆单季度和回款，不允许只看累计值就定性经营恶化。

### E. 盈利预测必须自建「三情景 × 连续三年」

不直接照抄券商一致预期。悲观/中性/乐观三个情景必须**全部覆盖连续未来3年**，不允许“第一年三情景、后两年只有中性”的缩水版本。每个关键假设都标注 `【假设】`，并说明依据和最敏感的2–3个变量。

### F. 估值必须匹配公司类型

不要对所有公司机械套PE。具体适配见 `references/估值与公司类型适配.md`。

### G. 结论必须可证伪

至少给3–5个长期跟踪指标，并明确“出现什么变化时，当前投资逻辑失效”。

### H. 关键结论必须尽量量化

不要只写“市场担心竞争加剧”；尽量回答竞争变化将影响多少收入、利润率、EPS或合理估值。

### I. 交付前必须通过独立验收

正式研究必须生成 `research_manifest.json`，并通过 `scripts/validate_report.py` 的严格模式（PASS）。
Validator 与生成过程**职责分离，不允许自我放行**；P0/P1 未清零不得标记「研究完成」。

### J. 交付物必须带精确到秒的生成时间

每份报告（HTML 及可选 md）落盘后，用 `scripts/stamp_report.py` 盖章：生成时间 `YYYY-MM-DD HH:MM:SS`，出现在 `title` / 副标题 / `footer` / 注释块四处，且文件名带 `_YYYYMMDD_HHMMSS`。
**只到日期的「生成于 2026-09-15」视为不合格**；时间戳一律由脚本读系统时钟写入，**禁止人工填**。

### K. PDF 版必须走无头浏览器，且导出后校验图表

需要 PDF 时用 `scripts/html_to_pdf.py`，**不得改用 weasyprint / wkhtmltopdf 等纯排版引擎**——它们不执行 JS，ECharts 的 canvas 图表拿不到，只会输出空白框。
引擎优先 `chrome-headless-shell`（纯无头二进制），**不要依赖 Chrome.app 的 `--headless`**：它在无 GUI 会话的进程上下文里会静默卡死。
PDF 产出的**最低合格线 = 内嵌图像数 > 0**（报告含 ECharts 时）；否则视为交付失败，不得交付。

### L. 线索 ≠ 证据：结论必须能顺着链路走回原文

任何一条进入正文的关键结论，都要能顺着 **Claim → EvidenceLink → Document → 原件里的那一段** 走回来。
走不回来的，只能写成 `【推断】` / `【假设】` / `【无法确认】`，**不能伪装成事实**。

- 搜索结果、neodata 摘要、券商转述、媒体转述 = **线索**，先落 `EvidenceCandidate`，**不得直接当证据**；
- 拿到原件后走唯一通道 `scripts/promote_evidence_candidate.py` 升格，**不得手写 Document 绕过**；
- `evidence_text` 必须是原件的真实摘录（`extract_verbatim` 能「给锚点、机器剪」，优先用它）；
- 拿不到一手原文时**宁可降级、宁可留空**：把 Claim 改成 `pending` / 降级等级，或整条撤回。
  **不允许**为了报告好看而保留一个出处不可考的「事实」；
- 对方是 PDF 等二进制、又没有官方文本层可比对时，如实记录「本摘录未经机器复核」（`unverified`），不要假装它经过了。
- **Provider ≠ Source**：`westock-data` / `neodata` 这类取数服务是搬运方，不是来源，默认 `data_vendor`。
  不要把它们的本地文件当成一手来源去支撑「已确认」级结论。

### M. 时点必须分清：信息截止 ≠ 行情截止 ≠ 报告生成

`as_of` / `market_data_as_of` / `generated_at` 三者各管一段。证据 `published_at` 不得晚于 `as_of`；
行情不得晚于 `generated_at`；`generated_at` 必须与报告文件名及报告内「生成于 …」一致。
**不得**用一个 `research_date` 含糊覆盖三种含义——那正是「证据晚于研究时点却查不出来」的根源。

正式 v3 一旦声明 `as_of`，**三个时点缺一不可**（缺一个就是 `TIME_MODEL_INCOMPLETE`），
不要只写一部分让时效校验悄悄退化。`published_at` 尽量写到秒级，
只写到「日」时校验会退化为 day-level——不要拿 `00:00` 冒充真实时刻。

### N. 报告锚定即声明：Claim 降级后，报告不得继续保留旧确定性表述

报告里的关键结论写成**锚点**（HTML `data-claim-id` / `data-claim-level` / `data-claim-status`；
Markdown `<!-- claim:ID level=... status=... -->`），锚点上的 `level` / `status`
**必须与 Claim Ledger 一致**。

```html
<span data-claim-id="C_PE_TTM_20260914" data-claim-level="unconfirmed" data-claim-status="pending">
  PE（TTM）约 53.8×（口径未定，仅作参考）
</span>
```

- **未声明 `level` / `status` 的锚点按 `fact` / `supported` 解读**（锚定即声明）。
  不确定等级的结论，要么如实声明等级，要么干脆不锚——**不要为了「有个锚点」而写上 `fact`**。
- 必须锚的是：影响**预测 / 估值 / 风险 / 最终状态 / 证伪条件**的结论，以及关键财务事实与订单/客户/量产状态；
  `manifest.evidence_refs` 中 `importance=critical` 的 Claim **必须在报告里有至少一个落点**。
- 不要求每句话都锚；也**不允许**为「形式完整」给所有文字建 Claim。
- 语法、强制范围与反例见 `references/报告Claim绑定规范.md`；
  负样本 `examples/invalid/意华股份002897_旧结论漂移样板/` **必须 FAIL**——那是这条规则的守卫。

---

## 文件导航

| 文件 | 用途 |
|---|---|
| `references/研究SOP.md` | 完整16章研究方法（含 §17 产物验收） |
| `references/搜索与证据规则.md` | 一手资料优先级、必搜清单、证据账本 |
| `references/估值与公司类型适配.md` | 不同类型A股公司的建模/估值选择 |
| `references/产物验收规则.md` | **P0/P1/P2 验收规则与阻断条件**（Validator 判定标准） |
| `references/证据对象规范.md` | **v3.0.2 证据对象规范**：三层对象 + 线索层、ID 规范、错误码表、定位与独立性、Provider ≠ Source、摘录验证状态、原子落盘、时间模型 |
| `references/报告Claim绑定规范.md` | **v3.0.2 报告锚点规范**：锚点语法（HTML/Markdown）、「锚定即声明」、强制范围、跨产物错误码、反例 |
| `references/样板案例-意华股份.md` | **首个通过独立验收（PASS）的完整产物**：三情景×三年建模逻辑、manifest 写法、6 个已踩坑位 |
| `references/实战案例-立讯精密.md` | 双路取数、现金流归因、质押遗漏等复盘 |
| `references/版本对比方法.md` | 同一标的多版研报对照（保留旧版 + SOP 版 + 7 章对比页） |
| `references/HTML输出规范.md` | HTML 版式锁定项、图表细则、交付前 JS 自检清单 |
| `assets/报告模板.md` | 最终报告的**内容结构**（0–16 章） |
| `assets/报告模板.html` | 最终报告的**统一版式**（唯一版式来源，复制后填充） |
| `assets/research_manifest.template.json` | **机器可审计研究清单模板**（Validator 的权威输入） |
| `scripts/fetch_stock.py` | **三源协同取数**（core/enhanced/search）+ 搜索清单生成 |
| `providers/` | 数据源 provider 层：`base.py` 接口 + `westock_npm.py` / `westock_cli.py` / `neodata.py`；新增源只需写子类并注册 |
| `providers/neodata.py` | neodata 检索源与凭证管理（`--status` / `--query` / `--save-token`） |
| `scripts/validate_report.py` | **独立产物验收器**（结构/数学/模型口径/证据层级/跨产物一致性；`--claim-only` 只跑跨产物） |
| `scripts/verify_excerpts.py` | 重算 Evidence Store 的摘录验证状态（`--write` 才写回，状态只由机器比对产生） |
| `scripts/install_westock_cli.sh` | 安装腾讯官方 Go CLI 到技能私有目录 `tools/bin/`（不改系统 PATH、无需 sudo） |
| `scripts/cross_validate.py` | 搜索值与结构化值交叉验证 |
| `scripts/validate_report.py` | **独立产物验收器**：结构、数学、模型口径一致性、证据层级（`--manifest` 严格模式 / `--report-only` 体检） |
| `scripts/build_evidence.py` | v3 证据库构建与自检：`init` / `register` / `verify` / `validate` / `show` / `add-candidate` / `candidates` |
| `scripts/promote_evidence_candidate.py` | **线索 → 证据唯一通道**：两阶段原子执行，自动算 SHA256、补定位、抽原文摘录 |
| `scripts/attach_local_evidence.py` | 把本地原件绑到已登记的 Document 上并补 locator / 摘录（防脑补硬闸） |
| `scripts/validate_evidence.py` | v3 证据库独立验收（不需要报告与 manifest），支持 `--fail-on LEVELS` |
| `scripts/build_kline.py` | `raw/kline.txt` → 研报内联 JS 数组（日 K，升序重排 + 统计校验） |
| `scripts/apply_firstscreen.py` | 给已有报告注入「V1 版式首屏」（真实行情 + 近 3 个月日 K 线），正文不动；副标题自动带秒级生成时间 |
| `scripts/stamp_report.py` | **生成时间盖章器**：四处时间戳统一刷新为 `YYYY-MM-DD HH:MM:SS`，幂等；`--check` 校验、`--rename` 同步文件名 |
| `scripts/html_to_pdf.py` | **HTML 研报 → PDF**（可选交付）：无头浏览器打印，引擎 `chrome-headless-shell` → Chrome/Edge → Playwright 自动降级；打印样式只注入临时副本；导出后校验页数/内嵌图像数 |

