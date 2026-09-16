# 报告 Claim 绑定规范（v3.0.2 / v3.0.3）

> **一句话**：报告里凡是「会被拿去做决策」的结论，都要锚回 Claim Ledger 里的 Claim；
> 一旦锚定，就是一次**声明**——声明的等级、状态与**版本**都必须与 Ledger 一致。

## 1. 为什么需要它

v3.0 / v3.0.1 让证据库变得可信：`Document → Claim → EvidenceLink` 三层都能被机器校验，
原件带 SHA256、定位可核、摘录可复核。但最终**交付给人的是报告**，而报告与证据库之间
原本没有任何可校验的连接。

真实的翻车案例（v3.0.2 §2）：

| 证据层已经这么做了 | 报告却还是这么写 |
|---|---|
| E007 从「送样阶段」纠正为「在研 / 实质性开发阶段」 | 「仍处送样阶段」（引互动易转述） |
| C_PE_TTM_20260914 降级为 `unconfirmed` / `pending` | KPI 卡里 `PE（TTM）53.83×` 当事实展示 |
| E008 降级为 `third_party_consensus` / `pending` | 「一致预期 4.22 亿元」当已验证事实 |

证据库自己全绿，交付物却是错的。这个缺口就是本规范要堵的东西。

## 2. 语法

### 2.1 HTML

```html
<span
  data-claim-id="E007"
  data-claim-level="management_statement"
  data-claim-status="supported"
  data-claim-fingerprint="6e31ab49f0028c17">
  224G 产品仍处于在研阶段
</span>
```

| 属性 | 必填 | 说明 |
|---|---|---|
| `data-claim-id` | ✅ | 必须存在于 `claims.jsonl` |
| `data-claim-level` | 建议 | 必须与 Ledger 的 `level` 一致 |
| `data-claim-status` | 建议 | 必须与 Ledger 的 `status` 一致 |
| `data-claim-fingerprint` | ✅（v3.0.3） | 必须与**当前** Claim 的指纹一致；不得手写，由脚本抄入 |

- 标签不限，`<span>` / `<td>` / `<div>` / `<li>` 都可以；嵌套同名标签会正确配对。
- 属性顺序无关；单引号 / 双引号 / 无引号都支持。
- 只写 `data-claim-level` 而漏了 `data-claim-id` 也会被解析出来，并报 `REPORT_CLAIM_UNKNOWN`。
- 指纹大小写敏感：`AB…` 与 `ab…` 不是同一个值，不做宽容匹配。

### 2.2 Markdown

```markdown
<!-- claim:E007 level=management_statement status=supported fingerprint=6e31ab49f0028c17 -->
224G 产品仍处于在研阶段。
```

- 锚点独占一行时，关联文本取**下一个非空行**。
- 锚点与文本同行时（`PE(TTM) <!-- claim:... --> 约 53.8×`），取同行前后内容。
- 同一个 Claim 可以在报告里出现多次，每一处都要各自声明正确。

### 2.3 Claim 指纹（v3.0.3 §4）

```text
claim_fingerprint = sha256(canonical_json({
    claim_id, claim(空白归一化), level, status
}))[:16]
```

- 由 `scripts/stamp_claim_fingerprints.py` 从 Ledger **现算**后抄进报告，**不得手写**。
- **不是**持久化字段：`claims.jsonl` 里不存它，每次由 `Claim.claim_fingerprint` 现算，
  避免出现「本体改了、副本没改」的第二份真值。
- **不做** `hash(报告可见文本) == hash(claim.claim)`：报告允许对 Claim 做人类可读改写
  （「营业收入 28.63 亿元」写成「营收 28.63 亿」是正常的）。本版本只保证
  「报告锚点对应当前 Claim 版本」，不保证逐字复述。
- `category` / `materiality` **不参与**指纹：报告锚点不声明这两者，
  把它们算进去会让「补了个分类」这种无关变更把报告误判为过期。

## 3. 核心语义：锚定即声明

未显式声明 `level` / `status` 的锚点，按 **`fact` / `supported`** 解读。

这不是苛求，而是唯一能拦住旧报告的写法：旧报告的锚点不会有 `level` / `status`，
若「缺省 = 不检查」，那「Claim 被降级后旧报告必须 FAIL」这条要求就永远触发不了。

**推论**：不确定等级的结论，要么如实声明它的等级，要么干脆不锚。
不要为了「有个锚点」而写上 `fact`。

同一条逻辑在 v3.0.3 推到**版本**这一层：没声明 `fingerprint` 的锚点，同样不能放行。

```text
「缺省 = 不检查」= 给了一条「把属性删掉」的绕过路径。
```

所以：漏写指纹 → P0 `REPORT_CLAIM_REVISION_MISMATCH`。与 level / status 不同——那两者
缺省有明确读法（`fact` / `supported`），而「版本」缺省没有任何合理读法：锚点无法对应到
任何一版 Claim，读者也无从判断它说的是哪一版。

## 4. 校验规则与错误码

| 错误码 | 等级 | 触发条件 |
|---|---|---|
| `REPORT_CLAIM_UNKNOWN` | **P0** | 报告引用了 `claims.jsonl` 里不存在的 Claim；或锚点缺 `claim_id` |
| `REPORT_CLAIM_REVISION_MISMATCH` | **P0** | 锚点未声明 `fingerprint`，或声明的指纹 ≠ 当前 Claim 的指纹（v3.0.3 §4） |
| `REPORT_PENDING_CLAIM_ASSERTED` | **P0** | Ledger `status=pending`，报告却按肯定式（`supported` / `partially_supported`，或缺省）陈述 |
| `REPORT_UNCONFIRMED_AS_FACT` | **P0** | Ledger `level ∈ {assumption, unconfirmed, third_party_consensus}`，报告却声明为 `fact` / `confirmed_*` |
| `REPORT_CLAIM_LEVEL_MISMATCH` | **P0** | 报告声明的 `level` 与 Ledger 不一致（上一条之外的所有情况） |
| `REPORT_CLAIM_STATUS_MISMATCH` | **P1** | 报告声明的 `status` 与 Ledger 不一致 |
| `REPORT_CRITICAL_CLAIM_MISSING` | **P1** | `manifest.evidence_refs` 里 `importance=critical` 的 Claim，报告中没有任何落点 |

约定：

- `REPORT_UNCONFIRMED_AS_FACT` 与 `REPORT_CLAIM_LEVEL_MISMATCH` 互斥——前者命中时不再报后者。
- `REPORT_PENDING_CLAIM_ASSERTED` 命中时不再报同一锚点的 `REPORT_CLAIM_STATUS_MISMATCH`。
- **指纹检查先于 level / status**：版本都不对，谈等级没有意义。但命中版本失配**不抑制**
  level / status 的检查——多条问题各自独立，不互相掩盖。
- `claim_id` 不存在时**只**报 `REPORT_CLAIM_UNKNOWN`：没有当前版本可比，
  再报指纹失配会误导排查方向。
- 「非法 level / status 值」不另立错误码：畸形值与 Ledger 必然对不上，
  一定会被 MISMATCH / UNKNOWN 抓到。错误码要稳定，不为每种畸形长一个新码。
- 同理，`REPORT_CLAIM_REVISION_MISMATCH` 一个码覆盖「缺指纹」与「指纹不符」两种形态：
  它们对读者的含义是同一句话——「这处结论无法被证明对应当前版本」。
- 本层**只做显式 metadata 一致性**，第一版不做语气/语义判断，不引入 LLM（§6）。

## 5. 强制范围

不要求报告每一句都锚。必须锚的是：

```
影响预测
影响估值
影响风险
影响最终状态
影响证伪条件
关键财务事实
关键订单 / 客户 / 量产状态
```

此外，`manifest.evidence_refs` 中 `importance=critical` 的 Claim **必须在报告里有至少一个落点**。

## 6. 命令

```bash
# 0) 给报告里的 Claim 锚点盖版本指纹（幂等；缺省只预览，--check 只校验）
python3 scripts/stamp_claim_fingerprints.py report.html \
  --evidence-dir research_sz002897/evidence --write

# 全链路（结构 + 数学 + 证据 + 跨产物一致性）
python3 scripts/validate_report.py report.html \
  --manifest research_manifest.v3.json \
  --evidence-dir research_sz002897/evidence \
  --out validation

# 只跑跨产物一致性（CI Gate 4）
python3 scripts/validate_report.py report.html \
  --manifest research_manifest.v3.json \
  --evidence-dir research_sz002897/evidence \
  --claim-only --out validation
```

`--claim-only` 不检查章节结构、数学与证据绑定，只对照「报告锚点 ↔ Claim Ledger ↔
manifest.evidence_refs」——便于在改动报告文案时快速定位漂移。

盖章脚本只负责把版本指纹抄对，**盖章通过 ≠ 报告合格**：真正的判定仍然在 Validator。

## 7. 反例（必须 FAIL 的写法）

```html
<!-- ① pending 的 Claim 当事实说 -->
<span data-claim-id="C_PE_TTM_20260914">PE(TTM) 53.83×</span>
<!-- ② 未确认等级伪装成事实 -->
<span data-claim-id="E008" data-claim-level="fact" data-claim-status="pending">一致预期 4.22 亿元</span>
<!-- ③ inference 写成 fact -->
<span data-claim-id="C_MKT_CAP_20260914" data-claim-level="fact">总市值 138.40 亿元</span>
<!-- ④ 引用了不存在的 Claim -->
<span data-claim-id="E999">...</span>
<!-- ⑤ 漏写版本指纹（旧报告形态） -->
<span data-claim-id="E007" data-claim-level="management_statement" data-claim-status="supported">在研</span>
<!-- ⑥ 指纹停留在上一版：Claim 正文已被改写，这三项却全对 -->
<span data-claim-id="E007" data-claim-level="management_statement" data-claim-status="supported"
      data-claim-fingerprint="6e31ab49f0028c17">仍处于在研阶段</span>
```

⑤ 与 ⑥ 都是 `REPORT_CLAIM_REVISION_MISMATCH`（P0）。⑥ 是最隐蔽的一种：
`claim_id` / `level` / `status` 全部对得上，报告却仍然在陈述**已经被推翻的结论**——
这正是 v3.0.3 §4 存在的唯一理由。

正例见 `examples/意华股份002897_深度研究_20260915_090532.html`；
对应的负样本（保留旧结论、必须被拦住）见 `examples/invalid/意华股份002897_旧结论漂移样板/`。
