# HTML 输出规范（A股深度研究统一版式 · 基准 = 京泉华 V1 研报）

> **唯一版式来源 = `assets/报告模板.html`。** 本文件是它的使用说明与质检清单。
> 产出 HTML 研报时**必须**复制模板文件再填充，**不得从空白另起配色或另设 CSS 变量**。
>
> **设计基准**：`京泉华002885_深度研究_20260914.html`（V1）。视觉语言以它为准 —— 蓝色强调、
> 卡片 + 三色 callout、产业链链条盒子、图/表切换、中文序数之外的 0–16 章骨架。
>
> 定这条硬规则的原因：历史上同一技能先后产出的报告，因每次即兴写 CSS，品牌主色、章节编号、
> 标题层级各不相同（实测两份同技能报告品牌色 `#1b3a63` vs `#2b4acb`、章节号带点 vs 不带点、
> 最大层级 h3 vs h4）。从此以模板为准。

---

## 1. 锁定项（禁止改动）

| 项 | 锁定值 |
|---|---|
| CSS 令牌 | **每份报告自带一套**（正文主题由该报告自己的 `:root` 决定，数值不必横向统一）。但**首屏组件只准引用令牌、不准硬编码色值**：深字 `var(--ink/--ink2/--ink3)`、线 `var(--line)`、底 `var(--bg/--card)`、蓝 `var(--brand,var(--blue,…))`、涨 `var(--up,var(--red,…))`、跌 `var(--down,var(--green,…))` |
| 涨跌语义 | **A股口径：红涨绿跌**；首屏与图表一律取 `--up`/`--down`（缺则回退 `--red`/`--green`）。首屏类名固定 `.r`（涨/正）／`.g`（跌/负）／无（中性） |
| 组件类名 | 正文：`header.top .kicker h1 small h2(.n) .card .grid(.g4/.g3/.g2) .kpi(.lb/.vl/.sub) .tag(.r/.g/.b/.a/.p) .note .callout(.blue/.red) .chart .chart-wrap .switch .chain/.chain-row/.layer/.boxes/.box(.hi/.dim) .src .lead .num-big`<br>首屏（`scripts/apply_firstscreen.py` 产出，与模板一致）：`.fs-head .fs-kicker .fs-intro(.fs-lb) .fs-card .fs-top .fs-concl .fs-pill .fs-quote .fs-big .fs-chg .fs-mc .fs-ohlc .fs-kpis .fs-kpi(.lb/.vl/.sub) .fs-lbl .fs-lbl2 .fs-src .fs-chart` |
| 章节骨架 | 编号固定 **0–16**（h2 带 `<span class="n">编号</span>`），与 `assets/报告模板.md` 一一对应 |
| 证据标签 | `事实=.tag.g`、`管理层口径=.tag.a`、`推断=.tag.b`、`假设=.tag.p`、`无法确认=.tag` |
| 引库 | ECharts 5，CDN 放 `<head>` |
| 图表配色 | 主序列 `#9db2d0`（蓝灰）／净利或重点序列 `--red`／毛利率 `--amber`／占比饼图 主色 `--red` + 蓝灰梯度 |

## 2. 版式要点

- **浅底深字研报风**，`max-width:1080px` 居中；`header.top` 用蓝色 `.kicker` 标签 + 大标题 + 灰色副标题。
- **首屏结论先行**：紧跟头部一张「公司简介」块 + 一张 `.fs-card`（左"核心结论"一段话 + 右大号收盘价/市值），下接 `.fs-kpis` 两行 KPI。
- **「一句话本质 / 一句话投资逻辑」不放在首屏**——它属于正文 §2，首屏只放「公司简介 + 核心结论 + 日 K」三块，避免同一判断重复三次。
- 章节：`h2` 蓝色左边条 + 编号；正文用 `.card` 承载；多栏用 `.grid.g2/.g3`。
- 关系拓扑（产业链/股权/传导链）用 `.chain` 链条盒子，**当前环节用 `.box.hi`**（红框高亮），其余 `.box.dim`。
- 表格：数值列右对齐、表头浅灰底、`tbody tr:hover` 高亮；**重点行**（如本公司）加 `style="background:#fffaf9;"`。

### 2.1 首屏（强制项，放在正文 0 章之前）

参考京泉华 V1 版式，**四件套缺一不可**（顺序不可调换）：

1. **`header`**：`.fs-kicker` 标签 + `h1` 大标题 + `h1 small` 副标题（含「数据截至 YYYY-MM-DD 收盘 ｜ 生成于 YYYY-MM-DD HH:MM:SS」——**生成时间精确到秒**，见 §2.5）。
2. **公司简介**（`.fs-intro`，蓝边浅底块）：一段话讲清「**这是一家什么公司**」——`<b>一句话定位</b>` → 成立年份 / 上市时间与板块 → 主营与产品线 → 规模（营收 / 员工 / 市值）→ 行业位置 → 核心看点及其当前兑现度。
   - **只写可核验的事实**（工商信息、年报、公司官网、公告）。查不到的不写，**宁缺勿猜**——市占率、「唯一」「第一」这类表述若无一手出处，一律不写。
   - 允许 `<b></b>` 加粗（其余标签会被 `esc()` 转义）；长度控制在 150–260 字。
   - 与「核心结论」的分工：**简介回答"它是什么"，结论回答"该不该买"**，两者不得互相抄。
3. **首屏结论卡**（`.fs-card`）：左侧「— 核心结论 —」一段话 + 研究状态 pill；右侧**报告日真实行情**——收盘价（大号）、涨跌幅、总市值、开/高/低/成交额/换手；下方 `.fs-kpis` **8 个 KPI**；卡底数据来源。
4. **近 3 个月日 K 线卡**（`.fs-card`）：`raw/kline.txt`（60 个交易日）→ ECharts candlestick + MA5/MA10/MA20 + 成交量副图；**红涨绿跌**（`color`/`borderColor` 用 `--red`（涨），`color0`/`borderColor0` 用 `--green`（跌））。

**数据来源纪律**：首屏所有数字**必须取自当日真实行情与本报告自身结论**，严禁杜撰或沿用其它标的的数据。
行情字段与 `raw/kline.txt` 的最后一行必须自洽（收盘价、开高低、成交量一致）。
`<` 等符号必须转义（如 `<5%` → `&lt;5%`），否则会被解析成标签、破坏版面。

**给已有报告补首屏**：跑 `scripts/apply_firstscreen.py <report.html> <spec.json>`——只替换开头（删掉旧 header / 旧结论块、插入新首屏、追加日 K 脚本），**正文 0–16 章一律不动**；带哨兵，可安全重复运行。spec 各字段见脚本头注释（`intro` / `conclusion` / `quote` / `kpis` / `source` / `kline_dir`……）。

### 2.2 首屏两条硬规则（踩过坑，别再犯）

**规则一：两列布局必须是 Grid，不能用 flex + `flex-wrap:wrap`。**

```css
.fs-top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:start}
.fs-quote{text-align:right;justify-self:end}
@media(max-width:860px){.fs-top{grid-template-columns:1fr}.fs-quote{text-align:left;justify-self:start}}
```

原因：`flex-wrap` 会在「结论段 `max-width:760px` + 价格块内容宽（`.fs-ohlc` 那行约 314px）+ gap」超过卡片内宽时
**把价格块换行挤到左侧**——用户看到的就是"最新收盘价跑到左边去了"。Grid 在结构上不可能换行，价格块恒在右列。

**规则二：首屏配色一律继承宿主报告令牌，禁止硬编码。**

```css
color:var(--ink,#1a1d24)                                    /* 深字 → 与正文同色 */
color:var(--brand,var(--blue,#2563c9))                      /* 蓝 → 该报告的品牌色 */
color:var(--up,var(--red,#d5342b))                          /* 涨 → 该报告的涨色 */
background:color-mix(in srgb,var(--brand,var(--blue,#2563c9)) 12%,#fff)   /* 浅底由品牌色派生 */
```

- 回退链要写成 `var(--报告令牌, var(--V1令牌, #兜底色))`：三套样板令牌名不同——京泉华 SOP 版与顺络电子都用 `--brand/--up/--down`（**值不同**），V1 用 `--blue/--red/--green`。
- 浅底先写静态色（`background:#e8effb;`）、再写 `color-mix(...)` 覆盖：不支持 `color-mix` 的浏览器自然落到静态色。
- **图表/K 线同理**：用 `fsPick(['--up','--red'],'#d5342b')` 从 `document.documentElement` 读令牌，缺令牌才回退，否则会出现「图一套色、正文一套色」。
- 涨跌色只在 `.r`/`.g` 有定义时才生效——**新增组件时，先确认 `.r`/`.g` 变体都写了**。

> **为什么定这两条（2026-09-14 实测）**：首屏首次落地时把 V1 色值写死，且**模板与生成器脚本各改各的**
> （模板有 `.fs-big.r/.g`、脚本没有）→ 同一技能产出的两份报告，首屏价格**既不跟正文同色、又完全不显红绿**
> （对截图做像素采样：价格区红色像素 **0 个**）；同时 flex 换行把价格块挤到左侧（实测右边缘 CSS 353px，
> 而卡片右边应在 1038px）。

### 2.3 首屏 CSS 的单一来源与防脱钩

**首屏 CSS 的唯一来源 = `scripts/apply_firstscreen.py` 里的 `CSS` 常量。**
`assets/报告模板.html` 里的同名区块是**同步产物**（区块用 `/* FS-CSS:BEGIN */ … /* FS-CSS:END */` 标记）。

```bash
python3 scripts/apply_firstscreen.py --sync-template    # 把脚本的 CSS 刷进模板
python3 scripts/apply_firstscreen.py --check-template   # 校验是否脱钩（不一致退出码 1）
```

**改了首屏样式后必须跑一次 `--sync-template`，并在交付前跑 `--check-template`。**
历史上"模板与脚本脱钩"正是首屏配色不一致的直接原因。

### 2.4 长报告的生成方式（防截断）

**不要试图用一次 `Write` 写出整份报告**——一份完整 17 章研报在 80 KB 量级（约 5.6 万字符），
单次工具调用输出会**被截断**（2026-09-14 意华股份 002897 实测踩到）。

推荐流程（意华那一版就是这么出来的，一次成功）：

1. `cp assets/报告模板.html "<公司><代码>_深度研究_<YYYYMMDD_HHMMSS>.html"` —— 先拿骨架（文件名时间见 §2.5）。
2. 用 `Edit` 逐块把 **首屏 + §0–§5** 填进这个文件（分段小、不易出错）。
3. **§6–§16 + footer + 内联 `<script>` 一次性写到 `/tmp/<code>_tail.html`**（`Write` 写临时文件不受报告体量影响）。
4. 用一个小 Python 脚本**按边界精确拼接**：

```python
s = Path(report).read_text("utf-8")
a = s.find('<h2><span class="n">6</span>')      # 起始边界（用 HTML 注释标记更稳）
b = s.rfind("</script>") + len("</script>")     # 结束边界
Path(report).write_text(s[:a] + Path(tail).read_text("utf-8") + s[b:], "utf-8")
```

5. 拼完立刻校验字符数增量与「残留占位符 `【】` 数」。

**边界锚点建议**：模板给每章都留了 `<!-- ============ N. 章节名 ============ -->` 注释，
拼接时优先用注释锚点而不是中文标题，避免标题里改了一个字就找不到位置。

### 2.5 生成时间与文件名（精确到秒，强制）

**只到日期不算数**（`生成于 2026-09-15` ✗）——每份报告的生成时间必须精确到秒：`YYYY-MM-DD HH:MM:SS`（本地时区）。

四处必须一致：

| 位置 | 形态 |
|---|---|
| `<title>` | `… A股个股深度研究 ｜ 生成于 2026-09-15 09:05:32` |
| `h1 small` 副标题末尾 | `… ｜ 数据截至 2026-09-14 收盘 ｜ 生成于 2026-09-15 09:05:32` |
| `<footer>` | `· 报告生成时间：2026-09-15 09:05:32（本地时间）` |
| 顶部注释块 | `· 报告生成时间：2026-09-15 09:05:32` |

**不要手写时间**——手写必然停在日期精度或写错。报告落盘后统一跑盖章脚本（读系统时钟，幂等可重跑）：

```bash
python3 scripts/stamp_report.py <report.html>              # 盖/刷新时间戳
python3 scripts/stamp_report.py <report.html> --rename     # 顺手把文件名时间同步为 _YYYYMMDD_HHMMSS
python3 scripts/stamp_report.py <report.html> --check      # 交付前校验（退出码 1 = 不合格）
```

**文件名同样精确到秒**：`<公司简称><代码>_深度研究_YYYYMMDD_HHMMSS.html`
（例：`意华股份002897_深度研究_20260915_090532.html`）。同日多版并存时一眼看出先后。

> 脚本只认「生成于 / 报告生成时间」两个锚点，**不会误改** `数据截至 2026-09-14 收盘` 这类**数据时点**——
> 数据时点与生成时间是两个概念，不得混为一谈。

## 3. 图表分工与质量

- **有数值轴的趋势/对比/占比/分布 → ECharts**；查阅型/多维对照 → 表格。
- **图/表可切换**：数字密集块用 `.chart-wrap > .switch` + `.hidden` 表格，默认看图、一键切表查精确值。
- **双轴注意量级差**：营收（数十亿）vs 净利（数亿）量级差大，用双轴或小序列改折线，勿共用一轴。
- **空值不入图**：无数据区间不要硬塞占位，x 轴从有数据处起。
- 取数尽量多取一个完整周期（算 8 个季度同比就取 12 个季度），消除前段空值、避免手算同比出错。

## 4. 交付前必做质检（最高优先级）

HTML 里手写的内联 `<script>`（尤其 ECharts `option`）**极易括号/引号失配**——一处失配整块
`SyntaxError`，该页**所有图表全废**（不是一个图空）。所以交付前必须：

```bash
# 抽出内联 script → 语法校验；通过则静默，报错精确定位行列
node --check /tmp/_check.js

# 首屏 CSS 单一来源防脱钩（不一致则退出码 1）
python3 scripts/apply_firstscreen.py --check-template
```

- 报错 → 改到通过为止，再交付。
- 无 node 时用 `python3` 等替代；实在无工具就人工数括号配平，重点查 `=>({...})` 与多层 `series:[{...}]`。
- **不要把"生成了 HTML"当作完成——图表能渲染才算完成。**
- **首屏自检三问**：① 价格/涨跌幅有没有 `.r`/`.g`（有没有颜色）？② 价格块是不是钉在卡片**右侧**（不是被换行挤到左侧）？③ 首屏蓝/红/灰是不是和正文**同一套色**（跟正文里的强调色并排比一眼）？

**①' 日 K 数据必须逐字节比对（禁止只靠肉眼核对）**：报告内嵌的 `kDates` / `kRaw`
要与 `scripts/build_kline.py` 产出的 `research_<code>/kline.js` 做**去除空白后的字符串全等比对**：

```python
norm = lambda x: re.sub(r"\s+", "", x)
assert norm(re.search(r"var kRaw=\[(.*?)\];", report, re.S).group(1)) \
     == norm(re.search(r"var kRaw=\[(.*?)\];", kline_js, re.S).group(1))
```

60 天 × 5 个字段共 300 个数字，手抄一遍必错一次——`kRaw` 错一个数字图就假了，且**肉眼看不出来**。

**①'' 交付前全文字符扫描（两类最容易漏的错）**：

- **中日汉字混入**：`証実`（应为"证实"）、`経営`、`総額`、`決算`、`円` 等日文用字，多发生在快速手写长文时。
  扫描办法：对 `["証","実","経","営","総","価","円","の"]` 逐个 `count`，非零就逐处人工确认。
- **同指标跨章口径不一致**：同一个数（如净现比、毛利率、增速）在首屏 / 正文 / 表格里写了两个值。
  扫描办法：抽 5–8 个高频指标名（净现比、PE、毛利率、经营现金流）做全文 `finditer`，把上下文并排看一眼，
  不一致就统一到一个口径并注明算法。

高发错误形态：`data:arr.map(s=>({...}))` 少一个 `)`、字符串 `formatter:'{b}: {c}%'` 跨行断裂、
`series:[{...}}, {...}]` 多一个 `}`、`legend.data` 里混入游离裸值。

## 5. 交付

- 文件名：`<公司简称><代码>_深度研究_<YYYYMMDD_HHMMSS>.html`（**精确到秒**，见 §2.5）；重做版加 `_SOP版`；对比页加 `_两版研报对比`。
- 落盘后跑 `python3 scripts/stamp_report.py <report.html> --rename` 盖生成时间戳并同步文件名，交付前 `--check` 必须返回 0。
- 产出后用 `present_files` 打开预览给用户。
- 结尾 footer 必须含数据来源口径 + 免责声明 + **报告生成时间（精确到秒）**（模板已内置，替换占位即可）。
