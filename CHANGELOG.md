# Changelog

## v3.0.2 — Cross-Artifact Consistency（把可信的证据层延伸到最终交付物）

v3.0 / v3.0.1 把证据库做成了可校验对象：`Document → Claim → EvidenceLink` 三层都能被机器验，
原件带 SHA256、定位可核、摘录可复核。但**最终交付给人的是报告**，而报告与证据库之间
原本没有任何可校验的连接 —— 于是出现这类翻车：

| 证据层已经这么做了 | 报告却还是这么写 |
|---|---|
| E007 从「送样阶段」纠正为「在研 / 实质性开发阶段」 | 「仍处送样阶段」（引互动易转述） |
| `C_PE_TTM_20260914` 降级为 `unconfirmed` / `pending` | KPI 卡里 `PE（TTM）53.83×` 当事实展示 |
| E008 降级为 `third_party_consensus` / `pending` | 「一致预期 4.22 亿元」当已验证事实 |

**证据库自己全绿，交付物却是错的。** 本版把这个缺口堵上，并顺手焊死四个会让证据链
「看起来在验、其实没验」的松口。

### 新增：跨产物一致性（报告 ↔ Claim Ledger ↔ `manifest.evidence_refs`）

- `core/report/`（`models.py` / `claim_parser.py`）：从最终报告里解析结论锚点。
  HTML 走 `data-claim-id` / `data-claim-level` / `data-claim-status`（标签不限、属性顺序无关、
  嵌套同名标签正确配对）；Markdown 走 `<!-- claim:ID level=... status=... -->`（独占一行取下一非空行，同行取前后文）。
- `core/validation/report_claim_validator.py`：只做**显式 metadata 一致性**，
  第一版不引入 LLM、不做语气判断。
- **核心语义：锚定即声明。** 未显式声明 `level` / `status` 的锚点按 `fact` / `supported` 解读
  （`DEFAULT_ASSERTED_LEVEL` / `DEFAULT_ASSERTED_STATUS`）。这不是苛求，而是唯一能拦住旧报告的写法：
  旧报告的锚点不会有 `level` / `status`，若「缺省 = 不检查」，「Claim 被降级后旧报告必须 FAIL」就永远触发不了。
- 新错误码 6 个：P0 `REPORT_CLAIM_UNKNOWN` / `REPORT_PENDING_CLAIM_ASSERTED` /
  `REPORT_UNCONFIRMED_AS_FACT` / `REPORT_CLAIM_LEVEL_MISMATCH`；
  P1 `REPORT_CLAIM_STATUS_MISMATCH` / `REPORT_CRITICAL_CLAIM_MISSING`。
  `UNCONFIRMED_AS_FACT` 与 `LEVEL_MISMATCH` 互斥；非法 level / status 值不另立错误码
  （畸形值必然对不上 Ledger，一定会被 MISMATCH / UNKNOWN 抓到）。
- `scripts/validate_report.py` 新增 `--claim-only`：只对锚点与 Ledger，跳过结构与数学，便于改文案时快速定位漂移。
- 规范文档 `references/报告Claim绑定规范.md`（含语法、强制范围、反例）。
- **负 Golden Sample**：`examples/invalid/意华股份002897_旧结论漂移样板/` ——
  保留旧结论的报告，**必须 FAIL**，用来做反向验收（正样本过 ≠ 闸门有效）。

### 变更：Provider ≠ Source（§8）

`westock-data` / `neodata` 这类取数服务是 **Provider**，不是 **Source**。
搬运交易所公告不产生一手性，但把它们登记成 `official_database` 就能凭空获得「一手来源」资格，
单独支撑确认级 Claim —— `EVIDENCE_PRIMARY_REQUIRED` 直接形同虚设。

- `core/models/provenance.py`：`DATA_VENDOR_PROVIDERS` 白名单 + `normalize_provider()`
  （剥括号后缀，如 `westock-data(kline)`）+ `default_source_type_for()`。
- `SourceDocument` 新增 `provider` / `upstream_source_type` / `upstream_document_id`
  与派生属性 `is_data_vendor` / `has_declared_upstream`。
  **硬规则**：`is_data_vendor` 且 `source_type` 是一手来源 且 未声明 `upstream_*` → 拒绝。
- `source_type` 新增枚举 `data_vendor` / `third_party_database`（均非一手来源）。
- 独立性合并：`independence_key` 沿 `upstream_document_id` **多级传递**，
  「westock-data(kline) + 公司公告」算**一个**来源，不再被错当成两个独立来源。
- 样板纠正：`examples/意华股份002897_样板/` 4 份 westock 文档与 manifest 里的 E006
  由 `official_database` 改为 `data_vendor` + `provider="westock-data"`。

### 新增：摘录验证状态（§9）

此前只要求 critical Claim 有 `evidence_text`，却不区分「摘录确实来自原文」与
「没法比对所以跳过了」。PDF 跳过子串校验，于是**「跳过」被当成了「通过」**。

- `EvidenceLink` 新增 `excerpt_verification_status`（`verified` / `unverified` / `not_applicable`）、
  `_method`（`direct_text` / `text_layer` / `manual` / `ocr`）、`_source`。
  `verified` 必须声明手段；只写一半（有 method 无 status）同样拒绝。
- **未声明状态 = 未验证**。critical Claim 的 `unverified` 摘录 → P1 `EVIDENCE_EXCERPT_UNVERIFIED`。
- `core/evidence/excerpt.py`：`resolve_verification_source()`（PDF → 同名 `.textlayer.txt` 用 `text_layer`；
  纯文本用 `direct_text`；否则无法比对）+ `stamp_excerpt_verification()` **唯一写入通道**。
- `core/evidence/verbatim.py` 拆成两个函数：`excerpt_in_file()` **严格**
  （非文本 / 缺失 / 空 → False，禁止「跳过 = 通过」）给验证路径；
  `text_supports_excerpt()` 保留原「跳过」语义给 attach 路径，不破坏既有行为。
- `scripts/verify_excerpts.py`：独立重算入口，`--write` 才写回。状态**只由机器比对产生**，不允许手工填 `verified`。
- 样板：23 条链接经真实比对写回 `verified`（17 条对官方文本层逐页核对、6 条对文本原件子串校验）。

### 变更：原子落盘（§10）

`save()` 逐个文件直接覆盖，中途失败留下**半新半旧**的证据库 —— `documents.jsonl` 已更新、
`raw/` 还是旧的，hash 与内容对不上，正好是最危险的状态。

- `EvidenceStore.save_atomic()`：内存算完目标内容 → 逐个写 `.tmp` + `fsync` →
  原文件 rename 为 `.bak` → `.tmp` `os.replace` 成正式文件 → 任一步失败用 `.bak` 回滚。
- `EvidenceStore.add_raw_file()`：经 `raw/.staging/` 暂存并**复核落地副本 sha256**
  与源文件一致，才 `os.replace` 进 `raw/`；失败只删临时文件，`raw/` 保持原样。

### 变更：正式 v3 时间模型必须完整（§11）

v3.0.1 允许三个时间字段「都可缺省」，结果是可以只写一部分：写了 `as_of` 却漏 `market_data_as_of`，
时效校验悄悄退化而验收照样 PASS。

- 一旦声明 `as_of` 即视为采用新时间模型，**三个时点缺一不可**，否则 P1 `TIME_MODEL_INCOMPLETE`。
- 三缺 + 有 `research_date` → 兼容路径 P2 `TIME_MODEL_LEGACY`（**不要声明 `as_of`**）；
  三缺且连 `research_date` 都没有 → P1 `MANIFEST_V3_STRUCTURE`。

### 变更：`published_at` 支持 datetime 精度（§12）

- 允许 `YYYY-MM-DDTHH:MM:SS+08:00`；只写到日时 `published_datetime` 返回 `None`，
  时效校验退化为 **day-level 比较**；**禁止**拿 `00:00` 冒充真实时刻。
- 双方都有时刻 → 按 datetime 比较，能抓到「同一日内但晚于 `as_of`」这种 day-level 看不见的倒挂。
- `schemas/document.schema.json` 的 `published_at` pattern 同步放开。

### 修复：`load()` 幂等（§13）

`EvidenceStore.load()` 原先只清 `issues`，`links` 是 list —— 重复调用会把同一份 JSONL
读第二遍而**静默翻倍**。现每次 load 都清空 `candidates` / `documents` / `claims` / `links` 再重建。

### 变更：CI 收敛为四闸门（阻断式）

| 闸门 | 内容 | 断言 |
|---|---|---|
| 1 | `pytest -q` | 363 个用例全绿 |
| 2 | v2 manifest 存量样板回归 | 行为零变化（仍 PASS） |
| 3a | `validate_evidence.py --fail-on P0,P1,P2` | 证据库 P0=P1=P2=0 |
| 3b | 报告 + v3 manifest + 证据库三段串联 | P0=P1=0，且**跨产物 summary 归零** |
| 4a | `--claim-only` 正样本 | PASS |
| 4b | 负 Golden Sample | **必须 FAIL**，且命中 4 类预期错误码，否则视为闸门失效 |
| 4c | `pytest tests/integration/test_report_drift.py` | 故障注入（Claim 降级后旧报告必须 FAIL）真的被抓住 |

闸门 4 由三部分组成（正样本过 / 负样本挂 / 故障注入被抓），单靠「正样本 PASS」证明不了闸门有效 ——
这正是「先写失败测试，再实现」在 CI 层的落地。

### 测试

- 全量 **363 个用例通过**（v3.0.1 基线 271 → 新增 92）。
- 新增用例：`test_cross_artifact.py` 19、`test_claim_parser.py` 20、
  `test_provenance.py` 13、`test_store_atomic_and_time.py` 13、
  `test_excerpt_verification.py` 12、`test_report_drift.py` 9，
  以及 `test_schemas.py` 4 个 schema 一致性、`test_end_to_end.py` 2 个端到端。
- 本地四道闸门实测：Gate3a `P0=P1=P2=0`；Gate3b `P0=P1=0` 且跨产物 0；
  Gate4a PASS；Gate4b `rc=1` 命中 `REPORT_UNCONFIRMED_AS_FACT` /
  `REPORT_PENDING_CLAIM_ASSERTED` / `REPORT_CLAIM_LEVEL_MISMATCH` / `REPORT_CRITICAL_CLAIM_MISSING`。

## v3.0.1 — 证据链收口（线索层 / 时间模型 / 摄入通道 / 严格样板）

v3.0 把证据变成了可校验对象，但留下四个后果严重的松口：**线索可以直接冒充证据**、
**一个 `research_date` 分不清信息时点与行情时点**、**从线索到证据没有唯一通道**、
**Golden Sample 长期停在「故意不完整」**。v3.0.1 逐个焊死，并把样板做到严格 PASS。

### 新增：线索层（线索 ≠ 证据）

- `core/models/candidate.py`：`EvidenceCandidate`（`CAN_<指纹前8位>`），状态机 `new / reviewed / promoted / rejected / duplicate`。
- `candidates.jsonl`：线索独立落盘，**不参与任何证据校验的通过口径**。
  它不能承担 `EVIDENCE_PRIMARY_REQUIRED` / `EVIDENCE_DIRECT_REQUIRED`，不能提供 critical Claim 的 locator 与摘录，
  也不计入正式来源独立性。`status=promoted` 本身同样不构成证据。
- 新错误码：P0 `CANDIDATE_USED_AS_EVIDENCE`（把线索当 Claim/Document 引用）、P1 `CANDIDATE_PROMOTED_WITHOUT_DOCUMENT`。
- `scripts/build_evidence.py` 新增子命令 `add-candidate` / `candidates`。

### 新增：摄入通道（线索 → 证据的唯一入口）

- `scripts/promote_evidence_candidate.py`：候选 → 确认原始来源 → 保存原件 → register Document（自动算 sha256）
  → 绑定 `source_group` → 生成 EvidenceLink（补 locator）→ 抽取 `evidence_text` → `status=promoted`。
  两阶段原子执行（任一条不通过则整体不落盘，落盘阶段异常回滚内存状态）。
- `core/evidence/verbatim.py`：摘录真伪的**唯一实现**。`text_supports_excerpt()` 做子串校验（防脑补硬闸），
  `extract_verbatim()` 支持「给锚点、机器剪摘录」——把「需要被信任」换成「只需要被复核」。
  `attach_local_evidence.py` 与 `promote_evidence_candidate.py` 共用同一份逻辑，不再各写一套。
- 硬规则（代码化）：无 url 且无 local_file → 拒绝；文本原件摘录必须真实子串；promote 永不写 `claims.jsonl`
  （Claim 能否 `supported` 只由 Document + EvidenceLink 决定）；重复 promote 到同一 Document 幂等放行，改指向明确拒绝。

### 新增：时间模型（v3.0.1 §4）

- `core/validation/time_model.py`：`as_of`（信息截止）/ `market_data_as_of`（行情截止）/ `generated_at`（报告生成）
  取代语义模糊的 `research_date`。
- 新错误码：P1 `SOURCE_DATE_AFTER_AS_OF` / `MARKET_DATA_AFTER_GENERATED_AT` / `GENERATED_AT_MISMATCH`，P2 `TIME_MODEL_LEGACY`。
- 旧 v3（只有 `research_date`）继续可读，报一条 P2，不阻断迁移；v2 manifest 行为零变化。
- `validate_report.py` 新增报告层时间一致性：`generated_at` 必须与文件名 `<YYYYMMDD_HHMMSS>` 及报告内「生成于 …」四处一致。

### 新增：Claim 依据与未确认等级纪律

- `Claim.basis_claim_ids`：结论可以显式声明自己建立在哪些 Claim 之上。
- 新错误码：P1 `CLAIM_BASIS_UNKNOWN`（依据指向不存在的 Claim）、`CLAIM_BASIS_LEVEL_INVALID`
  （`fact` 不能建立在 `inference` / `assumption` / `unconfirmed` 之上）、`CLAIM_UNCONFIRMED_SUPPORTED`
  （`unconfirmed` / `assumption` 不得标成 critical-supported）。`management_statement` 是**已披露**信息，不算未确认。

### 变更：Golden Sample 收紧为严格 PASS

`examples/意华股份002897_样板/` 从「故意不完整」转为**严格 PASS 样本**（P0=P1=P2=0）：

- **补齐官方原件并按唯一通道摄入**：3 份巨潮 PDF —— 2026 年半年度报告（163 页，sha256 `6c8c441a…`）、
  2025 年年度权益分派实施公告（3 页）、关于部分限制性股票回购注销完成的公告（6 页）；4 份本地取数（kline / dividend / shareholder / profile）。
- **混合 Claim 拆分**：原 E006 拆为 `C_MKT_CLOSE_20260914`（行情事实）/ `C_MKT_CAP_20260914`（推导，声明依据）/
  `C_PE_TTM_20260914`（口径未定，`pending`，不绑证据）；E005 拆出 `C_FIN_FX_LOSS_2026H1`；
  E009 拆出 `C_DIVIDEND_TOTAL_2025`（推导）；E011 拆出 `C_RELATED_PURCHASE_TOTAL_2026H1`（推导）；
  新增 `C_SHARE_CAPITAL_20260630` / `C_SHARE_CAPITAL_20260910`。
- **口径更正**：E007 原写作「送样阶段」，出处是深交所互动易问答的转述；本次复核**未能取得公司回复的官方原文**
  （互动易详情接口不可读），按「不得脑补」改用半年报原文口径「在研 / 已进入实质性开发阶段」，
  该问询本身转入 Candidate 留痕。
- **降级而非掩饰**：E008（机构一致预期）无官方原件，出处是 neodata 聚合摘要 → 删除其 Document 与证据绑定，
  Claim 降级为 `pending`，线索留在 Candidate 层。
- 结果：**7 Documents / 19 Claims / 23 EvidenceLinks / 10 Candidates，23 条摘录全部命中原文**（17 条对官方文本层逐页核对、6 条对文本原件子串校验）。
- **样例文件整理**：`evidence/attach_plan.json` 已删除——它引用的是拆分前的 `E006`，dry-run 直接报「引用了不存在的 Claim」，留着就是陷阱；
  其职责已由覆盖全部 23 条链接的 `evidence/promote_plan.json` 取代。原《待补原始资料清单.md》改写为《原始资料补齐记录.md》。

### 变更：CI 收敛为阻断式三闸门

- Gate 1 `pytest -q`；Gate 2 存量 v2 样板回归；Gate 3a `validate_evidence.py`；Gate 3b 报告 + manifest + 证据库三段串联。
- Gate 3a 把 **P2 一起纳入阻断**：按既定口径「文件在但摘要不符」= P0 `EVIDENCE_HASH_MISMATCH`，
  而「登记了 hash 但原件没随仓库提交」= P2 `EVIDENCE_HASH_UNVERIFIED`，两者刻意分开、不可混改等级。
  若只挡 P0/P1，**删掉一个证据原件构建仍会通过**——实测确认，故由闸门补齐这一刀。
- 时间模型参数从 manifest 读出后透传给验收器，避免 CI 里出现第二份 `as_of` 而与 manifest 漂移。

### 测试

- 全量 **271 个用例通过**（v3.0 基线 163 → 新增 `test_candidate_promotion` 27、`test_claim_basis` 17、
  `test_finish_rules` 17、`test_time_model`、`test_manifest_v3`、`test_report_time`、`test_candidate_rules` 等）。

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
- `tests/`：pytest 用例（模型/Store/归一化/证据错误码/来源独立性/manifest v3/迁移/Schema/存量数学与结构/端到端 CLI）；**当前 163 个全部通过**。
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
- 测试新增：`tests/test_attach_local_evidence.py`（9）、`tests/test_fetch_stock_deterministic.py`（10）、`tests/integration/test_golden_sample_pipeline.py`（2）、`tests/integration/test_validate_evidence_cli.py`（6）。**全量 163 用例通过**。

### 修复
- `validate_report.py`：v3 manifest 不再误报 `EVIDENCE_EMPTY`——该检查针对 v2 的 `evidence[]`，v3 证据完整性由 `evidence_validator` 负责。
- `.gitignore`：`raw/` 收窄为 `research_*/raw/`。原先的裸 `raw/` 会把 `examples/**/evidence/raw/` 一并排除——证据原件不入库，他人克隆后登记过 hash 的文件全部取不到（P2），证据链在别人机器上直接断裂。

### 修正（首次推送后）
- `scripts/validate_evidence.py` 新增 `--fail-on LEVELS`：默认 `P0,P1`（行为与之前完全一致），允许调用方声明「哪些等级才算失败」。
- CI 的 v3 验收改为断言**「已提交的证据原件必须真实可校验」**（P0=0 且 P2=0），而不是「样板必须 PASS」：意华样板是**故意不完整**的 Golden Sample，P1 是已归档的待补缺口，断言它完整等于断言一件假事。P0 / P2 仍会拦住构建，「证据原件没被提交」这类事故照样能被抓住。
- 新增 `tests/integration/test_validate_evidence_cli.py`（6 例）：固定默认阻断等级、样板放宽语义、非法取值返回 2、以及「文件缺失=P2 / 文件被替换=P0」不可混淆。


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
