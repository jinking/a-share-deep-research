# A股个股深度研究 · 产物验收报告

- Validator: v2.2.0
- 研究报告: `examples/意华股份002897_深度研究_20260915_090532.html`
- Manifest: `examples/意华股份002897_样板/research_manifest.v3.json`
- Evidence Store: `examples/意华股份002897_样板/evidence`
- **最终状态: PASS**
- P0: 0 ｜ P1: 0 ｜ P2: 0 ｜ INFO: 7
- Evidence 层: P0=0 ｜ P1=0 ｜ P2=0
- 跨产物一致性（报告 ↔ Claim Ledger）: P0=0 ｜ P1=0

## 验收结果

| 等级 | 代码 | 结果 | 详情 |
|---|---|---|---|
| INFO | `STRUCT_CHAPTERS` | 0–16章结构完整 |  |
| INFO | `EVIDENCE_LABELS` | 证据标签体系存在 |  |
| INFO | `FORECAST_YEARS` | 识别到至少3个预测年度: [2026, 2027, 2028] |  |
| INFO | `TRACKER_ROWS` | 季度跟踪指标数量合格: 12 |  |
| INFO | `STRICT_MODE` | 严格模式：将继续校验结构化 manifest |  |
| INFO | `EVIDENCE_SUMMARY` | Evidence 校验完成 | candidates=10；documents=7；claims=19；links=23 |
| INFO | `REPORT_CLAIM_SUMMARY` | 报告 Claim 锚点 19 处，已与 Claim Ledger 对照 | P0=0 P1=0；落点 Claim=['C_FIN_FX_LOSS_2026H1', 'C_MKT_CAP_20260914', 'C_MKT_CLOSE_20260914', 'C_PE_TTM_20260914', 'C_SHARE_CAPITAL_20260910', 'E001', 'E002', 'E004', 'E005', 'E007', 'E008'] |

## 判定规则

- **P0**：硬错误。数学冲突、三情景/三年缺失、确认级证据误标等；禁止交付。
- **P1**：重要缺陷。核心模块不完整、跟踪指标不足等；严格模式下禁止交付。
- **P2**：改进项。不会单独阻断交付，但必须在下一版修复。
- **INFO**：通过项或说明。