# Changelog

## v3.0.0-alpha — Evidence Layer（可审计证据链）

从「能生成深度研究报告」升级为「能生产可审计的投资研究资产」。核心动作是把 **Document → Claim → Evidence** 三层对象落到代码与磁盘，并让 Validator 能独立检查「这份证据是不是真的」。

### 新增
- `core/models/`：`SourceDocument` / `Claim` / `EvidenceLink` / `ResearchState`（三层对象模型 + 聚合与完整性检查）。
- `core/evidence/`：`store.py`（JSONL 证据库读写）、`hasher.py`（sha256 与稳定 `document_id`）、`locator.py`（定位校验）、`independence.py`（来源独立性）。
- `core/validation/`：`evidence_validator.py`（证据校验规则）、`manifest_validator.py`（v2/v3 结构校验与版本识别）、`codes.py`（固定错误码目录）。
- `core/normalize.py`：股票代码归一化（`002897 → sz002897`），无法判断时 **raise 而非 silent failure**。
- `schemas/`：`document` / `claim` / `evidence_link` / `research_manifest.v3` 四份 JSON Schema。
- `scripts/build_evidence.py`：`init` / `register`（自动算 sha256）/ `verify`（复核是否被替换）/ `validate` / `show`。
- `scripts/validate_evidence.py`：Evidence Store 独立验收（不需要报告与 manifest）。
- `scripts/migrate_manifest_v2_to_v3.py`：v2 → v3 迁移，产物一律标记 `needs_verification`。
- `tests/`：pytest 用例（模型/Store/归一化/证据错误码/来源独立性/manifest v3/迁移/Schema/存量数学与结构/端到端 CLI）；**当前 157 个全部通过**。
- `.github/workflows/test.yml`：CI 跑 `pytest` + 存量样板回归；v3 样板存在时追加 Evidence 验收。
- `references/证据对象规范.md`：三层对象、ID 规范、等级与重要度、定位与独立性要求、错误码表、工作流。

### 变更
- `scripts/validate_report.py`：新增 `--evidence-dir` 与 `--strict-evidence`；v3 manifest 未提供 Evidence Store 直接报 `EVIDENCE_STORE_MISSING`（P1）；验收报告新增 Evidence 层汇总。**v2 产物行为完全不变**。
- Validator 版本号 → `2.0.0`。

### 新增校验能力（P0）
`EVIDENCE_DOC_MISSING`（引用不存在的文档）、`EVIDENCE_HASH_MISMATCH`（本地文件被替换）、`EVIDENCE_PRIMARY_REQUIRED`（确认级结论缺一手来源）、`EVIDENCE_DIRECT_REQUIRED`（已确认订单/收入/量产无 direct 证据）。
### 新增校验能力（P1）
`EVIDENCE_LOCATOR_MISSING` / `EVIDENCE_LOCATOR_INVALID` / `EVIDENCE_TEXT_MISSING` / `EVIDENCE_SOURCE_NOT_INDEPENDENT` / `EVIDENCE_NO_SOURCE` / `EVIDENCE_CLAIM_MISSING` / `EVIDENCE_CLAIM_ORPHAN` / `EVIDENCE_SUPPORT_BROKEN` / `EVIDENCE_DUPLICATE_ID` / `EVIDENCE_MODEL_INVALID` / `EVIDENCE_PARSE` / `EVIDENCE_REF_UNKNOWN` / `EVIDENCE_REFS_EMPTY` / `SOURCE_DATE_AFTER_RESEARCH_DATE` / `EVIDENCE_STORE_MISSING` / `MANIFEST_VERSION_UNSUPPORTED` / `MANIFEST_V3_STRUCTURE`。

### 兼容性
- v2 manifest 仍可读取，Evidence 校验自动降级为「引用完整性 + 一条 P2 说明」；
- 存量样板（意华股份 002897）在改版后重跑仍为 `PASS / P0=0 / P1=0`。

### Sprint 4a：意华股份 Golden Sample —— 迁移与证据绑定
- `examples/意华股份002897_样板/` 新增：`research_manifest.v3.json`、`evidence/`（12 Claims / 8 Documents / 15 Links）、`evidence/raw/`（4 份本地原件）、`evidence/attach_plan.json`、`待补原始资料清单.md`。
- 本地能拿到原件的一律做实：`E006`（2026-09-14 收盘 71.39、前收 64.90）绑 `kline.txt`；`E009`（10 派 5.000 元 / 9694 万）绑 `dividend.txt`；`E010`（意华控股 38.28%）绑 `shareholder.txt`；另用 `profile.txt` 提供股本以复算市值。
- 严格模式 P1 由 **19 → 15**，`E006` 的定位与摘录缺口已消除。
- **仍未 PASS**：`E001/E002/E004/E005/E007` 五条 critical Claim 依赖 2026 半年报 PDF 与互动易原文（本地只有到 2025 年报的结构化财务数据），另有 4 份 Document 缺来源地址、1 处日期矛盾（`research_date=2026-09-14` vs 机构预期 `2026-09-15`）。逐条列在 `待补原始资料清单.md`，**未做任何"让它变绿"的修饰**。

### Sprint 5：确定性逻辑下沉
- `scripts/fetch_stock.py`：
  - 入口统一调 `core/normalize.py`；无法判断市场时**报错并以退出码 2 结束**（原先是静默兜底继续跑，三大报表与 K 线全空却只留一行提示）；
  - 新增 `validate_kline_text()`（行数 / 日期 / 收盘价三项校验，纯函数）与 `fetch_kline_with_fallback()`（主源 → 校验 → npm 直取 → 再校验 → 失败标 `DATA_KLINE_UNAVAILABLE`）；
  - `main()` 改为 `sys.exit(main())`，退出码语义生效。
- `SKILL.md`：删除「代码前缀判断」与「K 线手工回退」两段操作性说明；`build_kline.py` 用法与列序警告保留。

### 新增脚本与测试
- `scripts/attach_local_evidence.py`：把本地原件绑到已登记的 Document 上并补 locator / 原文摘录。**两阶段原子执行**（任一条校验失败则整体不落盘），带**防脑补硬闸**——文本类原件的 `evidence_text` 必须是该文件的真实子串，否则拒绝。
- 测试新增：`tests/test_attach_local_evidence.py`（9）、`tests/test_fetch_stock_deterministic.py`（10）、`tests/integration/test_golden_sample_pipeline.py`（2）。**全量 157 用例通过**。

### 修复
- `validate_report.py`：v3 manifest 不再误报 `EVIDENCE_EMPTY`——该检查针对 v2 的 `evidence[]`，v3 证据完整性由 `evidence_validator` 负责。


## v2.4 — PDF 导出（无头浏览器）

新增可选的 PDF 交付格式。**核心坑**：ECharts 图表是运行时画在 canvas 上的，纯排版引擎（weasyprint / wkhtmltopdf）不执行 JS，导出来是空白框——必须用真浏览器。

### 新增
- `scripts/html_to_pdf.py`：HTML 研报 → PDF。自动探测引擎并按可靠性降级：`chrome-headless-shell`（Playwright 缓存内的纯无头二进制）→ Chrome/Edge → Playwright。`--out` / `--format` / `--landscape` / `--margin` / `--header-footer` / `--chrome-no-sandbox` / `--quiet`。
- 打印样式（`@page` 尺寸页边距 + 防跨页断裂）**只注入临时副本**，源 HTML 零改动；导出后校验页数与内嵌图像数，ECharts 报告 0 图即判失败。

### 变更
- `SKILL.md`：§8 新增「可选交付：PDF 版」小节与命令；新增**硬规则 K**「PDF 版必须走无头浏览器，且导出后校验图表」；文件导航补 `html_to_pdf.py`。
- `README.md`：新增「PDF 导出」一节。

### 实测（2026-09-15）
- 东材科技 601208：28 页 / 55 内嵌图 / 4.25 MB。
- 药明康德 603259：25 页 / 4.07 MB（打印 CSS 修正后页数由 34 降至 25，第 1 页留白消失）。

### 踩坑记录（重要）
- **`Chrome.app --headless=new` 在无 GUI 会话的进程上下文（自动化/agent shell）里会静默卡死在启动阶段**，无任何报错，反复重试只会堆积孤儿进程。定位过程排除了网络、CDN、缓存、参数、报告复杂度。改用 `chrome-headless-shell` 后 7.7 秒出稿。
- **打印 CSS 不要给 `.card` / `.fs-card` 这类可能高于一页的大容器加 `break-inside:avoid`**：整卡会被推到下一页，前一页大片留白（药明康德首版页数虚高至 34 页即此因）。只对图表、表格行、图片、KPI 小格等原子块防断裂。

## v2.3.1 — 首个完整个案回填（药明康德 603259）

以药明康德（603259.SH）端到端实战，把两个踩坑点固化为文档。

### 变更
- `SKILL.md` §2：新增「日 K 线取数回退」——core 源 kline 取空（`raw/kline.txt` 仅几十字节、`ok=false`）时，改用 `npx -y westock-data-clawhub@1.0.4 kline <代码> --period day --limit 62` 直取，剔除当日未收盘行后 `build_kline.py --days 60 --out kline.js`。
- `SKILL.md` §8：新增「克隆模板后必查三处占位残留」——`<script>` 内嵌示例标的 K 线价（`kDates`/`kValues`）与饼图 `【业务A】` 占位必须整体替换、`<title>`/注释块占位必须改写、首屏 CSS 勿重复注入。

### 实测
- 药明康德 603259 报告：四处生成时间戳统一 `2026-09-15 09:40:08`（`--check` 通过），Validator **PASS（P0=0 P1=0 P2=0 INFO=5）**。

## v2.3 — 生成时间精确到秒

报告落盘时间从「只到日期」升级为「精确到秒」，并由脚本盖章，禁止人工填写。

### 新增
- `scripts/stamp_report.py`：生成时间盖章器（幂等）。`--check` 校验、`--rename` 同步文件名、`--at` 指定时间戳、`--dry-run` 预览。

### 变更
- `SKILL.md`：§8 首屏 header 要求副标题含 `｜ 生成于 YYYY-MM-DD HH:MM:SS`；新增硬规则 J「交付物必须带精确到秒的生成时间」；文件导航补 `stamp_report.py`。
- `assets/报告模板.html`：`title` / `h1 small` / `footer` / 注释块四处时间占位改为 `YYYY-MM-DD HH:MM:SS`；文件名规范改为 `<公司简称><代码>_深度研究_YYYYMMDD_HHMMSS.html`。
- `scripts/apply_firstscreen.py`：副标题自动追加 `｜ 生成于 <秒级时间戳>`（支持 spec.generated_at 覆盖），并在输出末尾提示跑盖章脚本。
- `references/HTML输出规范.md`：新增 §2.5「生成时间与文件名（精确到秒，强制）」；§5 交付清单补盖章步骤。
- `references/版本对比方法.md`、`references/样板案例-意华股份.md`：命名与引用同步到秒级。

### 实测
- 意华股份 002897 报告盖章后 `--check` 通过，Validator 仍为 PASS（P0=0/P1=0/P2=0）。

## v2.2 — 独立产物验收

新增 `Research Artifact Validator`，把“生成研究报告”和“验收研究报告”拆成两个阶段。

### 新增
- `scripts/validate_report.py`
- `assets/research_manifest.template.json`
- `references/产物验收规则.md`

### 强制规则
- 悲观/中性/乐观必须完整覆盖连续未来3年。
- 正式研究必须生成 `research_manifest.json`。
- 盈利预测、估值、SOTP 同年中性利润必须对账一致。
- EPS×股本、现价×股本、可直接复算的估值公式必须一致。
- 确认级订单/量产结论必须由一手来源支撑。
- 只有 Validator 返回 PASS 才能标记研究完成。

### 实测
- 旧版意华股份报告：report-only 成功识别“仅2个预测年度”。
- 模拟顺络电子模型冲突：成功识别“2027E 总利润15.5亿 vs SOTP分部17.5亿”。
- 模拟证据越级：成功识别“券商研报被标成已确认订单”。
- 空白 manifest 模板：成功拒绝占位值通过。
