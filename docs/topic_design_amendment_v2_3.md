# Latent Persona Seismograph V2.3：Scenario-first Topic 设计修订

Amendment ID：`LPS-V2.3-TOPIC-20260825`
版本：`2.3-preparation`
日期：2026-08-25
状态：正式 Topic 范围修订；仅冻结设计骨架，`G1–G8` 仍为 open，尚无 V2.3 实验结果

## 1. 来源、效力与状态

本修订依据 [`topic的优化.md`](../topic的优化.md) 中最新形成的 Scenario-first 方案。原始讨论文件的 SHA256 为：

```text
1e403671cadfada1eacfe7675ff27e89d1e3e98b4bf7363f67c9c789a7382380
```

本修订取代 [`persona_topic_design_amendment_v2_2.md`](persona_topic_design_amendment_v2_2.md) 第 3 节的 30-topic、按 MMLU-Pro category 配额和 15/5/10 split；V2.2 的 Persona 层级、cold-start、样本量重算、Flow 排除和其他非 Topic 条款继续有效。

本文使用三种状态：

- **ADOPTED CONTRACT**：已经采用的设计结构；除非经过后续 amendment，不得回退到旧的 30-topic/category-quota 方案。
- **CANDIDATE**：可在 `G1` 盲于任何 outcome 的前提下评估，但不是冻结默认值。
- **OPEN**：尚无可执行值；必须由指定 gate 生成 manifest、审查记录和 checksum，不能用讨论示例或临时内容代替。

讨论中的医学决策、金融决策、工程规划、authority pressure、consensus pressure、repeated persuasion，以及五项 0–2 分和总分至少 8 分，均为设计示例或候选操作化，不是冻结的 scenario subtype、题目、评分表或阈值。

## 2. ADOPTED CONTRACT：Scenario first, category second

Topic 设计以 Persona 可观察的行为表达场景为首要单位：

```text
Scenario side
Scenario role → Scenario family/subtype → Topic anchor → 25-turn scenario

Behavior side
Behavioral family → Persona trait → Prompt variant
```

`Scenario role` 只是在科学叙述中解释场景如何支持行为表达的**概念名**，不是 manifest 字段。所有 machine-readable assignment、split、schema 和统计 strata 统一使用 `topic_scope`，其 frozen values 为 `shared_core` 与 `family_specific`；不得再创建 `topic_role` 别名。

MMLU-Pro 的 14 个官方 categories 只定义候选搜索池，不形成每类固定配额，也不要求最终 14 类全部出现。Topic 是否入选由 outcome-blind scenario suitability 决定，而不是由学科覆盖率或候选 topic 上的模型表现决定。

V2.3 固定 36 个 Topic slots：

| Scenario role（概念） | 结构 | 数量 | 可支持的主张 |
|---|---|---:|---|
| Shared core | 6 evidence-based + 6 opinion | 12 | 同一 shared topic 上的 cross-family 比较与泛化 |
| Family-specific | 4 behavioral families × 每 family 6 | 24 | 只支持对应 family 内的 trait/wording/trajectory 比较 |
| Total | 12 + 24 | 36 | 不把 family-specific topic 当作跨 family matched topic |

Shared evidence anchors 主要从 MMLU-Pro 的 14-category candidate pool 搜索；Shared opinion anchors 从 Anthropic sycophancy/opinion pool 搜索。来源角色不是自动 license 或 suitability 通过：每个最终 anchor 仍需在 `G1` 冻结 immutable item ID、revision、license/terms、file hash 和 deterministic transformation。

Family-specific 的“每 family 6”是 slot architecture。四个 family 的精确名称、边界以及每个 family 的 scenario families/subtypes 仍随 V2.2 Persona `G1` 保持 OPEN；必须先完成 Persona sampling-frame 审计，再填写这些 slots。如果最终合格 Persona frame 无法支持四个 families 或某 family 无法提供六个合格 scenarios，必须报告 shortfall 并提交 amendment，不能用近义 trait、低分 Topic 或复制场景凑数。

## 3. ADOPTED CONTRACT：split、pilot assets 与 outcome access

36 个 topics 按 immutable `topic_id` 分配，并以 `topic_scope` 记录 `shared_core`/`family_specific` scope：

| topic_scope | Development | Calibration | Untouched Test | Total |
|---|---:|---:|---:|---:|
| Shared core | 6 | 2 | 4 | 12 |
| Family-specific：每 family | 3 | 1 | 2 | 6 |
| Family-specific：4 families | 12 | 4 | 8 | 24 |
| **Total** | **18** | **6** | **12** | **36** |

G1 冻结 6 个 Development **pilot topic assets**：

```text
2 shared core + 每个 behavioral family 1 个 family-specific = 6 assets
```

六个 assets 均可用于 outcome-free scenario/instrumentation QA，例如 schema、hash、composition、render/tokenization 和 neutral fixture checks；这不等于六个 assets 均可进入 outcome-bearing dose-finding。QA 不得对 held-out-family Persona 生成或查看 target-model behavior、judge label、activation 或其他 outcome。

G2 冻结一个 fully held-out family 后，G5 outcome-bearing dose-finding 只允许三个 Development families，并使用：

```text
2 shared core + 每个 Development family 1 个 family-specific = 5 logical topic assets
```

Held-out-family 的 family-specific pilot asset 继续只作 outcome-free QA，不进入 `X_pilot`，不产生或揭示 behavior/activation outcome。样本公式中的 pilot phase 指这 5 个 outcome-bearing logical assets，不能用 6 作乘数。

G5 不得用 held-out-family outcomes 选择其 `S^*`。Held-out family 只可使用 G4 independent-rater、outcome-blind L0–L5 calibration，以及在任何 held-out outcome 揭封前冻结的 cross-Development-family schedule-transfer/fallback rule。该 rule 的 inputs、aggregation、tie/shortfall 和左右邻居可行性必须在 G6 签名；若它不能给出可执行 schedule，则停止 held-out-family evaluation，不得查看其 outcome 后调 dose 或重新选 schedule。

G1 PASS 前必须冻结 exact 36 topic IDs、18/6/12 assignment 和 exact 6 pilot-asset IDs，并保存 `split_algorithm_version`、`split_seed`、`balance_diagnostics_sha256`、`topic_split_plan_manifest_sha256` 与 `assignment_outcome_blind=true`。Pilot asset 不能进入 Calibration 或 Untouched Test。任何 outcome-bearing run 后替换 `topic_id`、`topic_scope`、`topic_split` 或 pilot-asset assignment，都必须停止对应阶段并提交 amendment。

## 4. Shared 与 family-specific 的 claim boundary

Shared core topics 对所有纳入运行的 behavioral families 使用同一 content-only scenario，因此才可支持 matched-topic cross-family comparison。其 exact trait × prompt-variant exposure matrix仍由 phase-specific assignment manifest 冻结；“shared”不自动意味着每个 prompt variant 完全交叉。

Family-specific topic 只对其 `eligible_behavioral_family_id` 有效。它可支持：

- 同一 family 内 seen/unseen wording 比较；
- 同一 family 内 seen/unseen trait 比较；
- 该 family 内压力响应与 trajectory heterogeneity；
- 在预注册双重 holdout 下，对新 family-specific scenario 的联合迁移诊断。

它不能单独支持：

- 不同 families 在同一 Topic 上的 matched comparison；
- 把 family-specific topic 效应解释为 family 主效应；
- 把四组不同 scenarios 合并后声称无条件 cross-family ranking。

Primary uncertainty 仍以 topic 为 outer cluster。`G6` 必须在 topic_scope、source 与冻结的 scenario strata 中规定 resampling/partial-pooling 方法，并对 shared 与 family-specific claims 分开报告。

## 5. Topic × Persona 双重 holdout 与 gate 时序

Topic split 和 Persona generalization split 是两条同时生效的访问轴，不是可以互相替代的单一标签。

G1 只冻结静态 Topic 资产与 access-policy contract：

```text
topic_id
topic_scope
topic_split
topic_content_canonicalization_version
topic_content_root_sha256
eligible_behavioral_family_id (nullable only for shared_core)
split_algorithm_version
split_seed
balance_diagnostics_sha256
topic_split_plan_manifest_sha256
assignment_outcome_blind=true
```

其中必须包括 `topic_scope × behavioral_family` eligibility、exact 18/6/12 topic IDs、exact 6 pilot-asset IDs 和双轴 policy 的逻辑；G1 不冻结 trait/variant/wording generalization assignments，也不冻结任何 outcome-phase exposure rows。

G2 冻结 fully held-out family 及 trait/variant/wording generalization assignments。每个 outcome-bearing phase 开始前，必须另行签名对应 `X_phi` exposure manifest，把已冻结 Topic manifest 与 Persona holdout manifest绑定，并至少携带 `behavioral_family_id`、`persona_trait_id`、`persona_prompt_variant_id`、`persona_generalization_role`、phase 和全部 phase-specific 因子。G5 前冻结 `X_pilot`，且只含 5 个获准的 Development logical topic assets；G6 冻结 confirmatory exposure/analysis rule 与 `X_main`；G7 在任何 fork outcome 前冻结 `X_fork`。

一个 exposure row 只有同时满足 Topic 轴、Persona 轴和相应 signed `X_phi` 才能生成、拟合、校准或评估。至少遵守：

1. Untouched Test topic 的任何 outcome 不进入 Development、Calibration、模型选择或阈值选择。
2. Unseen wording、unseen trait 或 unseen family 的 outcome 不得越过其 Persona holdout 边界。
3. Outcome-free 的公开 source text 可在 G1 用于审计和 scenario 构建，但这不授权读取其后生成的 held-out outcomes。
4. 每条 trajectory/fork 继承唯一 topic split；同一 topic 的 model、persona、seed、schedule 和 fork 不得跨 partition。
5. Predictor 不得用 held-out categorical topic/family/trait/variant ID 或 lookup embedding；只能使用 gate 前冻结的 outcome-blind descriptors/features。
6. Held-out-family pilot asset 只允许 outcome-free QA，不得进入任何 outcome-bearing `X_pilot`。

对 fully unseen family，Shared Untouched topics 提供 primary matched cross-family cold-start test；该 family 的 family-specific Untouched topics只支持更加严格的 Persona + Scenario joint-transfer diagnostic。二者必须分开报告，不能把联合迁移失败归因于 Persona 或 Topic 的单一轴。

## 6. Outcome-blind Topic Suitability Screen

采用 suitability screening 原则，但讨论中的具体量表仍是 **CANDIDATE**，不是 frozen rule。候选五项为：

1. 能否自然、确定性地扩展为 25 个 content-only turns；
2. 是否允许 Persona trait 产生可区分的行为表达；
3. 是否能自然施加反-Persona pressure；
4. 是否具有 ground truth 或可冻结的稳定立场，而不把知识题答错当作 Drift；
5. 是否不依赖 safety/policy confound。

每项 `0–2` 和总分 `>=8` 仅作为 `G1` 待检验的候选方案。`G1` 必须在读取任何 Drift、activation、warning、judge 或 transition-band outcome 前唯一冻结：

- rubric 的 exact criteria、anchors 和 exclusion reasons；
- 评分尺度、缺失项处理和 eligibility threshold；
- rater 数量、资格、训练材料、盲法与独立性；
- aggregation、inter-rater reliability、disagreement/adjudication；
- ties、边界分数、category/source shortfall 和 replacement rule；
- audit log、review versions、candidate universe 与所有排除理由。

不得先在候选 Topic 上运行目标模型，再用“25 轮不自然”“不容易 Drift”或“结果不理想”作为筛选理由。MMLU-Pro 14 categories 无 quota；某 category 可以贡献多个或零个 anchors。

## 7. 25-turn scenario 与 pressure 分离

每个最终 Topic 都必须冻结一组 25 个 content-only `topic_move`：它们只推进同一个核心场景，不包含 pressure level、反-Persona 指令或 outcome 预判。每条 trajectory 另外保存 25 个 `pressure_template_id`，实际 user turn 由二者组合：

```text
actual_user_turn_t = topic_move_t + pressure_template_t(L_t)
```

至少保存：

- 25 个 `topic_move_ids` 和按 turn 对齐的 `topic_move_sha256s`；
- `topic_content_canonicalization_version=restart-v2.3-topic-move-root-v1`；
- 按下述 canonical rule 导出的 `topic_content_root_sha256`；
- scenario template/version/hash；
- 25 个独立的 `pressure_template_ids` 与 absolute `L_1:25`；
- `turn_composition_version`、`composed_user_turn_sha256s` 与 `pre_response_full_prompt_sha256s`，后三个 tuples 均按 turn 1–25 对齐。

每个 `topic_move_sha256` 是 deterministic transformed content-only move 的 exact UTF-8 bytes 的 SHA256。`topic_move_sha256s` 必须恰有 25 项且 pairwise unique。第一版 root canonical bytes 精确为：ASCII header `restart-v2.3-topic-move-root-v1\n`，随后按 turn 1–25 拼接 `NN:<64-lowercase-hex>` 行，行间单个 `\n`，末尾无额外换行；`topic_content_root_sha256` 是该完整 UTF-8 payload 的 SHA256。

同一 canonicalization version 下，`topic_content_root_sha256` 必须在全部 36 topics 中 globally unique。Root payload 不能包含 `topic_id`、source item ID、`topic_scope` 或 split 等可通过重命名改变的身份字段。相同 root 不得分配多个 topic IDs，也不得跨 split；否则它们是同一 content cluster，G1 必须 fail closed。Cross-topic move-hash overlap 和 near-duplicate scenario 另需 outcome-blind overlap report 与冻结 adjudication rule，不能用轻微改写复制 scenario 来凑足 36 个 clusters。

Topic move 不因 Persona/model/seed/schedule 改写。Family-specific 只决定该 Topic 的 eligible family，不授权把反-Persona pressure写入 content layer。讨论中的所有示例场景和 25-turn 文案都不是 frozen assets。

Anthropic opinion anchor 的原生 biography/user stance 仍需在 `G1/G4` 前唯一选择确定性剥离/标准化，或 source-specific baseline/estimand；在选择和 checksum 未冻结前不得进入 outcome-bearing pilot。

## 8. Gate-specific OPEN 清单与停止规则

V2.3 的 36/18-6-12/6-pilot-asset slot architecture 已采用。以下内容是 **G1 PASS blockers**：

- exact four family names/boundaries 和 24 family-specific slots 的 eligibility mapping；
- Shared evidence/opinion 和各 family-specific scenario family/subtype 的定义；
- 14-category MMLU-Pro candidate universe、Anthropic pool 和全部 source revisions/licenses/file hashes；
- 36 个 immutable source item IDs、transformed topic IDs、`topic_scope` 和 anchor-to-slot mapping；
- suitability rubric 的 exact scale/threshold/raters/aggregation/ties/reliability；
- 25-turn topic moves、pairwise-unique move hashes、frozen canonical root rule、globally unique content roots、scenario templates 和 reviewer procedure；
- exact 18/6/12 IDs、exact 6 pilot-asset IDs、`split_algorithm_version`、`split_seed`、`balance_diagnostics_sha256`、`topic_split_plan_manifest_sha256` 和 `assignment_outcome_blind=true`；
- `topic_scope × behavioral_family` eligibility 与静态双轴 access-policy logic；
- Anthropic native stance policy、topic feature contract 和 freeze manifest；
- exact/near-duplicate content overlap report、shortfall、duplicate anchor/root、insufficient subtype 和 post-freeze correction rules。

上述 G1 blockers 任一为空时，G1 不得通过；代码必须 fail closed。V2.1/V2.2 的 30-topic IDs、示例、默认评分阈值或旧 split 不得作为 fallback。

以下是后续 gate/phase blockers，不反向计入 G1 PASS：

- G2：fully held-out family、trait/variant/wording generalization assignments、prompt/item-role 和 measurement manifests；
- 每个 outcome phase 前：signed `X_phi` exposure manifest；其中 `X_pilot` 仅允许 5 个 Development logical topic assets；
- G6：confirmatory exposure/analysis rule、`X_main`、heldout-family schedule-transfer/fallback rule 及 failure-to-transfer stop rule；
- G7：`X_fork`、fork eligibility/randomization 和 intervention estimand。

任一后续 blocker 为空，只阻止对应 phase；不得伪称它已在 G1 冻结，也不得以临时默认值继续。

## 9. 保持不变的项目边界

- Persona 继续遵守 V2.2：4 families × 每类 4–6 true traits 是 16–24 的规划方向，不把 exact trait 数冻结为 24。
- 25 main turns、前 5 turns L0、L0–L5/PPU、两套时钟、pre-response activation、Region/Margin/hazard 和 randomized forks 保持不变。
- V2 整体继续排除 Conditional/Normalizing Flow、Flow Matching 及所有 flow-based density/trajectory models。
- 所有旧 Flat-4 样本量继续退役；36-topic 结构变更后必须从 signed phase manifests 重算资源与 power，不能只按 `36/30` 线性外推。
- 本修订没有生成任何 trajectory、activation、label 或实验结果，也没有通过 `G1`。
