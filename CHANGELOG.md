# Changelog

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
