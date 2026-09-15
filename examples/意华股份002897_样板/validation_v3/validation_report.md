# A股个股深度研究 · 产物验收报告

- Validator: v2.0.0
- 研究报告: `examples/意华股份002897_深度研究_20260915_090532.html`
- Manifest: `examples/意华股份002897_样板/research_manifest.v3.json`
- Evidence Store: `examples/意华股份002897_样板/evidence`
- **最终状态: FAIL**
- P0: 0 ｜ P1: 15 ｜ P2: 0 ｜ INFO: 6
- Evidence 层: P0=0 ｜ P1=15 ｜ P2=0

## 验收结果

| 等级 | 代码 | 结果 | 详情 |
|---|---|---|---|
| INFO | `STRUCT_CHAPTERS` | 0–16章结构完整 |  |
| INFO | `EVIDENCE_LABELS` | 证据标签体系存在 |  |
| INFO | `FORECAST_YEARS` | 识别到至少3个预测年度: [2026, 2027, 2028] |  |
| INFO | `TRACKER_ROWS` | 季度跟踪指标数量合格: 12 |  |
| INFO | `STRICT_MODE` | 严格模式：将继续校验结构化 manifest |  |
| P1 | `EVIDENCE_NO_SOURCE` | Document 既无 url 也无 local_path: DOC_6121db64 | DOC_6121db64 \| interim_report \| 意华股份 2026 年半年度报告（未经审计） \| (2026-08-25) |
| P1 | `EVIDENCE_NO_SOURCE` | Document 既无 url 也无 local_path: DOC_d7e5798b | DOC_d7e5798b \| company_ir \| 深圳证券交易所互动易公司回复 \| (2026-09-14) |
| P1 | `EVIDENCE_NO_SOURCE` | Document 既无 url 也无 local_path: DOC_3ae8c988 | DOC_3ae8c988 \| broker_report \| neodata 汇总机构评级与盈利预测 \| (2026-09-15) |
| P1 | `SOURCE_DATE_AFTER_RESEARCH_DATE` | 证据发布时间晚于研究日期: DOC_3ae8c988 | published_at=2026-09-15；research_date=2026-09-14 |
| P1 | `EVIDENCE_NO_SOURCE` | Document 既无 url 也无 local_path: DOC_fae6a760 | DOC_fae6a760 \| company_announcement \| 意华股份 2025 年年度权益分派实施公告 \| (2026-05-29) |
| P1 | `EVIDENCE_LOCATOR_MISSING` | critical Claim 的证据没有任何定位: E001 | evidence=['EV_E001_01']；需要 page/section/paragraph/table 至少一种 |
| P1 | `EVIDENCE_TEXT_MISSING` | critical Claim 缺少可供人工审查的证据摘录: E001 | evidence_text 为必填（原文摘录，便于人工复核） |
| P1 | `EVIDENCE_LOCATOR_MISSING` | critical Claim 的证据没有任何定位: E002 | evidence=['EV_E002_01']；需要 page/section/paragraph/table 至少一种 |
| P1 | `EVIDENCE_TEXT_MISSING` | critical Claim 缺少可供人工审查的证据摘录: E002 | evidence_text 为必填（原文摘录，便于人工复核） |
| P1 | `EVIDENCE_LOCATOR_MISSING` | critical Claim 的证据没有任何定位: E004 | evidence=['EV_E004_01']；需要 page/section/paragraph/table 至少一种 |
| P1 | `EVIDENCE_TEXT_MISSING` | critical Claim 缺少可供人工审查的证据摘录: E004 | evidence_text 为必填（原文摘录，便于人工复核） |
| P1 | `EVIDENCE_LOCATOR_MISSING` | critical Claim 的证据没有任何定位: E005 | evidence=['EV_E005_01']；需要 page/section/paragraph/table 至少一种 |
| P1 | `EVIDENCE_TEXT_MISSING` | critical Claim 缺少可供人工审查的证据摘录: E005 | evidence_text 为必填（原文摘录，便于人工复核） |
| P1 | `EVIDENCE_LOCATOR_MISSING` | critical Claim 的证据没有任何定位: E007 | evidence=['EV_E007_01']；需要 page/section/paragraph/table 至少一种 |
| P1 | `EVIDENCE_TEXT_MISSING` | critical Claim 缺少可供人工审查的证据摘录: E007 | evidence_text 为必填（原文摘录，便于人工复核） |
| INFO | `EVIDENCE_SUMMARY` | Evidence 校验完成 | documents=8；claims=12；links=15 |

## 判定规则

- **P0**：硬错误。数学冲突、三情景/三年缺失、确认级证据误标等；禁止交付。
- **P1**：重要缺陷。核心模块不完整、跟踪指标不足等；严格模式下禁止交付。
- **P2**：改进项。不会单独阻断交付，但必须在下一版修复。
- **INFO**：通过项或说明。