# Latent Persona Seismograph V2：正式研究协议

Protocol ID：`LPS-V2-20260824`
版本：`2.3-preparation`
修订日期：2026-08-25
状态：正式协议；G0 `PASS`，G1–G8 open；Persona 层级与 Scenario-first Topic 骨架已修订，exact assets 与新版样本量仍 OPEN；尚无 V2.3 实验结果
权威设计来源：[`deep-research-report.md`](../deep-research-report.md) 与 [`重启项目的细节.md`](../重启项目的细节.md)
执行解释：[`docs/restart_v2_amendment.md`](restart_v2_amendment.md)；Persona 范围由 [`persona_topic_design_amendment_v2_2.md`](persona_topic_design_amendment_v2_2.md) 修订；Topic 范围由 [`topic_design_amendment_v2_3.md`](topic_design_amendment_v2_3.md) 修订，讨论 provenance 分别为 [`persona和topic的讨论.md`](../persona和topic的讨论.md) 与 [`topic的优化.md`](../topic的优化.md)

## 1. 研究目标

本研究检验：在给定 model、persona、topic、pressure family 和 pressure history 后，生成回答前的内部状态轨迹是否会在外显 Sustained Persona Drift 之前，偏离仍能保持人格稳定的正常压力响应轨迹。

本研究不把 pressure-induced activation movement 本身视为 drift evidence。科学目标按以下链路组织：

\[
\text{Expected Stable Trajectory}
\rightarrow
\text{Pressure-residual Trajectory}
\rightarrow
\text{Conditional Stability Region}
\rightarrow
\text{Persona Margin}
\rightarrow
\text{Future Drift Risk}
\rightarrow
\text{Causal Robust Radius}.
\]

### 1.1 Primary questions

1. 在 matched condition 内，future-Drift trajectory 是否比 Stable trajectory 更早偏离 conditional expected stable trajectory？
2. 这种 residual trajectory signal 是否在同-prefix text baseline 之外提供预注册的增量预测价值？
3. 在 randomized prefix-fork experiment 中，额外 calibrated pressure 是否单调提高未来 5 turns 的 Sustained Drift risk？
4. 最少需要多少额外、随机分配的 pressure levels，才能使风险达到预注册 operational threshold？

### 1.2 Confirmatory hypotheses

具体效应阈值在 `G6 Analysis lock` 通过前标记为 `TBD`，不得事后根据 untouched test 结果填写。

- `H1 — Residual specificity`：相对于 raw activation/projection，observational \(t^-\) 的 pressure-residual trajectory score 在相同 model × persona × family × absolute schedule 内更好地区分 onset 是否落入 \(\{t,\ldots,t+4\}\)。
- `H2 — Incremental warning`：latent trajectory features 相比同-prefix text baseline 达到预注册的最小有意义增益，同时不突破 false-alarm budget。
- `H3 — Lead time`：在 Sustained Drift onset 之前，几何 Margin 呈预注册方向变化，并达到预注册的 trajectory-level detection/lead-time 标准。
- `H4 — Dose response`：随机分配的未来 pressure dose 对 post-response fork risk \(R_{t^+}^{fork,(5)}(d)\) 产生预注册方向的 dose-response effect。

### 1.3 项目范围排除

V2 不采用 Conditional Flow。Pilot、main study、randomized intervention 和 external evaluation 均不得设计、实现、训练、调参、比较或报告 Conditional Flow、Conditional Normalizing Flow、Normalizing Flow、Flow Matching，以及其他 flow-based density/trajectory models。它们不属于 baseline、comparator、ablation、备选模型或 confirmatory/exploratory extension。

权威来源材料中的相关候选讨论按 G0 checksum 原样保留，只记录方案形成过程，不产生执行授权。任何重新纳入都需要用户明确改变项目范围并建立新的 major-version protocol；`G6` 或其他 V2 gate 不能重新开放该方法族。

## 2. 研究单位与术语

- **Main turn**：一条正式 user message + 一条 assistant response；system/persona 初始化不计入。
- **Full trajectory**：25 个 main turns。
- **Behavioral family**：包含多个可区分 Persona traits 的上位行为域。
- **Persona trait**：具有独立构念、公开来源题库和行为验证的 Persona 单位；主要 Persona 计数以 trait 为准。
- **Prompt variant**：同一 trait 的结构匹配 system-prompt 表述；是嵌套条件，不是新 Persona。
- **Evaluation item**：公开 trait 题库中的单条测量题；不是 Persona，也不得与 prompt variant 混计。
- **Persona generalization role**：seen-trait observed wording、unseen wording、within-family unseen trait 或 unseen behavioral family；它与 Topic split 正交。
- **Scenario role**：解释一个场景如何支持行为表达的概念名；它不是 machine-readable manifest field。
- **`topic_scope`**：唯一的机器字段，取 `shared_core` 或 `family_specific`；不得使用 `topic_role` 别名。
- **Phase assignment manifest \(X_{\phi}\)**：pilot、main 或 fork 的逐行 non-seed design cells；每行显式记录 trait × prompt variant 及所有 phase-specific 交叉因子。
- **Pressure family**：反 persona 压力机制。
- **Pressure level \(L_t\)**：同一 family 内经独立、outcome-blind 校准的 L0–L5 ordinal level。
- **PPU**：同一 family 内相邻 level 增加一级。
- **PPU-turn**：某一 level 在一轮中的 exposure；累计量为 \(\sum_t L_t\)。
- **Stable / Sustained Drift**：仅由冻结的行为测量协议判定，不读取 activation。
- **Drift onset \(T_i\)**：第一次满足 Sustained Drift rule 的时间；精确定义由 `G2` 冻结。
- **Eligible turn**：预测 cut-off 时尚未满足 Drift onset，且该 horizon 的标签/删失处理符合分析规则的 turn。
- **Observational \(t^-\)**：收到 \(U_t\) 之后、生成 \(A_t\) 之前；\(z_t\) 可用，预测窗口为 \(\{t,\ldots,t+H-1\}\)。
- **Fork \(t^+\)**：完成 \(A_t\) 并更新行为信息之后；fork prefix 包含 \(A_t\)，干预窗口为 \(\{t+1,\ldots,t+H\}\)。

两套时钟对应不同 estimands。所有数据表、函数和图必须使用 `t_minus/obs` 或 `t_plus/fork` 显式命名，禁止用无时钟标记的 \(R_t\) 混写。

## 3. 固定实验因子

### 3.1 Models

第一版固定三个 open-weight instruction models：

1. Qwen3-8B，固定 non-thinking mode；
2. Llama-3.1-8B-Instruct；
3. Gemma-3-12B-it。

精确 repository ID、revision hash、tokenizer revision、chat template、generation parameters 和模型许可/access 状态由 `G3` 冻结。任一模型无法访问或无法满足 hook contract 时不得静默替换；需停止对应阶段并提交 amendment。

### 3.2 Hierarchical Persona sampling frame

V2.2 采用：

```text
Behavioral Family → Persona Trait → Prompt Variant → Evaluation Item
```

用户认可的规划方向为 4 个 behavioral families、每类 4–6 个真正独立 traits（总计 16–24）。这是一项 **ENDORSED DIRECTION**，不是 exact frozen catalog。Prompt variants 与 evaluation items 都不能重复计数为 Persona。

三种泛化必须分开报告：

1. 同一 trait 的 unseen prompt wording；
2. 已见 family 内的 unseen trait；
3. 一个完整 unseen behavioral family。

`risk-averse`、`risk-seeking`、`stands-its-ground` 和 `agreeableness` 目前只是 seed trait candidates，不再是完整的 Flat-4 primary frame。`G1` 必须冻结 exact Persona family/trait catalog、sampling frame，以及公开 source/revision/license/item IDs；`G2` 必须冻结 fully held-out family，以及 trait/variant/wording generalization assignments、prompt variants、item-role split、held-out validation 与 Persona Vector protocol。无法达到规划范围时必须报告 shortfall 和 amendment，不能用近义标签、prompt 改写或 items 补数。

PersonaGym 仍仅用于 pipeline 冻结后的 external evaluation。

### 3.3 Scenario-first Topics

V2.3 主研究采用 36 个 public topic anchors：

| Scenario role（概念） | 结构 | Development | Calibration | Untouched Test | Total |
|---|---|---:|---:|---:|---:|
| Shared core | 6 evidence-based + 6 opinion | 6 | 2 | 4 | 12 |
| Family-specific | 每个 behavioral family 6 个 | 12（每 family 3） | 4（每 family 1） | 8（每 family 2） | 24 |
| **Total** | 12 shared + 24 family-specific | **18** | **6** | **12** | **36** |

G1 冻结 6 个 Development pilot topic assets：2 个 shared core + 每个 behavioral family 1 个 family-specific。六个 assets 全部可用于 outcome-free scenario/instrumentation QA，但 held-out-family asset 不得产生或揭示 target-model behavior、judge、activation 等 outcomes。G2 冻结 fully held-out family 后，G5 outcome-bearing dose-finding 只允许三个 Development families，使用 2 shared + 每个 Development family 1 specific，即 5 个 logical topic assets；第六个 held-out-family specific asset 不进入 `X_pilot`。

本设计遵守 **Scenario first, category second**。MMLU-Pro 的 14 个 categories 只构成候选搜索池，不设每类 quota，也不要求最终全部覆盖；Shared evidence anchors 主要从该池筛选。Anthropic sycophancy/opinion items 构成 Shared opinion candidate pool。Public item只提供 anchor，正确答案不是 Drift label。

Shared topics 对各纳入 families 使用相同 content-only scenario，支持 matched-topic cross-family comparison。Family-specific topic 只对其 `eligible_behavioral_family_id` 有效，只支持对应 family 内的 trait、wording 与 trajectory claim；不同 families 的不同 family-specific topics 不能合并成 matched cross-family ranking。

`G1` 必须冻结 exact four-family mapping、scenario families/subtypes、36 个 immutable source/transformed IDs、`topic_scope`、source revision/license/file hash、25 个 pairwise-unique move hashes、single content-canonicalization version、globally unique content root、exact 18/6/12 topic IDs、exact 6 pilot-asset IDs、`split_algorithm_version`、`split_seed`、`balance_diagnostics_sha256`、`topic_split_plan_manifest_sha256`、`assignment_outcome_blind=true` 和全部排除理由；这些 exact IDs 必须在 `G1 PASS` 前完成冻结。讨论中的具体 family names、medical/financial/engineering 等 subtypes 和题目示例均不是 frozen assets。

Topic Suitability Screen 必须 outcome-blind。讨论中的五项指标（25-turn extensibility、Persona expression、pressure compatibility、ground truth/stable stance、safety-confound separation）、每项 0–2 和总分至少 8，只是 **CANDIDATE**。Exact rubric、scale、threshold、rater count/qualification、blind review、aggregation、reliability、ties、adjudication 和 shortfall/replacement rules 必须在读取任何 candidate outcome 前由 `G1` 唯一冻结。

Topic split 与 Persona generalization role 是两条同时生效的访问轴。G1 冻结 Persona family/trait catalog 与 sampling frame；在 Topic 资产侧，G1 冻结 `topic_scope × behavioral_family` eligibility、exact topic split/pilot IDs 和静态双轴 access-policy logic。G2 冻结 fully held-out family 与 trait/variant/wording generalization assignments。每个 outcome phase 前另行签名 `X_phi` exposure manifest；G6 冻结 confirmatory exposure/analysis rule 与 `X_main`。Untouched Topic outcomes 或 held-out wording/trait/family outcomes均不得进入 Development/Calibration。Shared Untouched topics 提供 unseen-family primary cold-start test；held-out-family specific Untouched topics 只能作为 Persona + Scenario joint-transfer diagnostic，必须分开报告。

每个 anchor 确定性转换成 25 个 content-only topic moves。每轮输入严格分离为：

```text
actual_user_turn_t = topic_move_t + pressure_template_t(L_t)
```

每个 Topic 保存 `topic_move_ids` 和 turn-aligned `topic_move_sha256s`；后者必须恰有 25 个 pairwise-unique content hashes。全库固定 `topic_content_canonicalization_version=restart-v2.3-topic-move-root-v1`：canonical bytes 为该 ASCII header 加换行，随后按 turn 1–25 拼接 `NN:<64-lowercase-hex>` 行，行间单个换行、末尾无额外换行。`topic_content_root_sha256` 是该 UTF-8 payload 的 SHA256，必须在 36 topics 中 globally unique，且不得混入 `topic_id`、source ID、`topic_scope` 或 split。相同 root 出现在多个 IDs/partitions 时 fail closed；cross-topic move overlap 与 near-duplicate scenario 另做 outcome-blind audit。

每条 trajectory 另存 25 个独立 `pressure_template_ids`、absolute `L_1:25`、`turn_composition_version`、`composed_user_turn_sha256s` 和 `pre_response_full_prompt_sha256s`；三个 tuples 均按 turn 1–25 对齐。Topic move 不包含 level、反-Persona 指令或 outcome 预判，也不随 Persona/model/seed/schedule 改写。

Anthropic items 的原生 biography/user stance 必须预先选择确定性剥离/标准化，或独立 source-specific baseline/estimand；否则不得进入 outcome-bearing pilot。Topic ID 是 split、provenance 和 outer cluster unit，不是 predictor feature。需要 Topic conditioning 时，只能使用 outcomes 前冻结的 topic features/embedding；具体模型编码与 regularization 由 `G6` 冻结。

### 3.4 Pressure schedules

每个 active persona trait × pressure family 建立 L0–L5，每级约 8 个意图等价 templates。独立 raters 在看不到模型 Drift outcome 的情况下完成 0–100 intensity ratings 与 pairwise ordering；ordinal/Rasch calibration、接受标准和 prompt rewrite rule 在 `G4` 冻结。

候选 gradual schedules 为 `restart_v2_amendment.md` 定义的 \(S_{-2},\ldots,S_{+2}\)，首 5 turns 永远为 L0 neutral baseline。Pilot 为每个 model × active trait 选择有左右邻居且位于 transition band 的 \(S^*\)。Main 使用：

\[
S^*_{-1},\quad S^*,\quad S^*_{+1}.
\]

这里下标表示 schedule-grid neighbor；每条记录仍保存实际的 \(L_{1:25}\)。

Held-out family 不运行 outcome-bearing dose-finding，也不得用其 outcomes 选择 `S^*`。它只可使用 G4 independent-rater、outcome-blind L0–L5 calibration，以及在任何 held-out outcome 揭封前于 G6 冻结的 cross-Development-family schedule-transfer/fallback rule。该 rule 必须签名 inputs、aggregation、ties/shortfall 和左右邻居可行性；若无法给出可执行 schedule，则停止 held-out-family evaluation，不得看 outcome 后调整 dose。

## 4. 样本设计（V2.3 待重算）

V2.1 基于四个 Flat-4 Persona 推导出的 `1,440` pilot trajectories、`8,640` main trajectories、`600` prefixes、`9,600` fork continuations 和约 `300,000` target-model turns 全部是 **RETIRED PLANNING FIGURES**。它们不能继续作为 V2.3 target、GPU 申请或完成度分母。

V2.3 以以下非 Persona 因子作为规划输入：3 models、36 main topics（12 shared + 24 family-specific）、6 Development pilot assets但仅5个G5 outcome-bearing logical assets、25 main turns、5 candidate pilot schedules、3 main schedule arms，以及 fork 的 4 randomized doses。新的总量必须从 frozen manifests 计算，而不是从 README 常数读取。

V2.1 使用过的 pilot 4 seeds、main 8 seeds、候选 `8→10` 和 fork 每 arm 4 continuation seeds 都是 **historical candidate values**，不是 V2.3 defaults。三个 phase 的 seed 数均为 OPEN，必须根据该 phase 的 power/精度目标、层级方差、event rate 和 runtime/storage benchmark 在对应 gate 独立冻结。

### 4.1 G1/G2 后的重算输入

重算前必须唯一确定：

- exact family/trait catalog 与每个 trait 的 generalization role；
- 哪些 traits 进入 pilot、Development、Calibration 和一次性 untouched evaluation；
- 36 个 topic slots 的 `topic_scope`、eligible family 与 split，以及后续 phase-specific Topic × Persona exposure assignments；
- prompt variants 是完整因子、平衡抽样因子还是 robustness subset；
- pressure calibration 是 trait-level、pole-level 或 family-level；
- intervention prefix quota 的分层单位；
- 两卡 runtime、storage 与 checkpoint/resume benchmark。

计划公式只从已签名的逐行 assignment manifests 计算。G1 冻结 Persona family/trait catalog 与 sampling frame，以及静态 Topic/eligibility/split contract；G2 冻结 fully held-out family 与 trait/variant/wording generalization assignments；`X_pilot`、`X_main`、`X_fork` 分别必须在对应 outcome phase 前签名，且 G6 冻结 analysis/confirmatory exposure rules。对 \(\phi\in\{\mathrm{pilot},\mathrm{main},\mathrm{fork}\}\)，令 \(X_{\phi}\) 是该 phase 的 non-seed design rows；pilot/main 行至少包含 model、topic_id、topic_scope、topic_split、eligible family、trait、prompt variant、Persona holdout role 和 schedule，fork 行至少包含 root prefix、fork turn、trait、prompt variant 和 dose。定义 trait × variant 计数矩阵：

\[
A^{(\phi)}_{\tau v}=\lvert X_{\phi}(\tau,v)\rvert.
\]

若 \(s_{\phi}(x)\) 是 row \(x\) 在对应 gate 冻结的 generation/continuation seed 数，则：

\[
N_{\phi}=\sum_{x\in X_{\phi}}s_{\phi}(x)
=\sum_{\tau,v}\sum_{x\in X_{\phi}(\tau,v)}s_{\phi}(x).
\]

只有当该 phase 的 seed 数对所有 rows 一致时，才可简化为 \(N_{\phi}=s_{\phi}\sum_{\tau,v}A^{(\phi)}_{\tau v}\)。每个 observed/unseen-wording/robustness-only prompt-variant exposure 都必须成为 \(X_{\phi}\) 的显式 row；不得仅按 trait 计数，也不得使用未验证的平均 `K_variant` 乘数。若使用 balanced incomplete design，必须保存完整 assignment matrix、inclusion probability、cell weights 和每个 variant 的 exposure diagnostics。

### 4.2 Pilot 与 power

六个预先指定的 Development pilot assets 全部用于 outcome-free scenario/instrumentation QA。G5 outcome-bearing dose pilot 仅使用 5 个 logical assets（2 shared + 三个 Development families 各 1 specific）；held-out-family specific asset 不进入 `X_pilot`，不产生 behavior/activation outcome。只有 G1/G2/G3/G4、新版 sample-size manifest、signed `X_pilot` 和停止规则全部通过后才能启动。Dose pilot 不产生 confirmatory claim。

Pilot seed rule 与 signed `X_pilot` 在任何 pilot outcome 前冻结；main seed rule、trait × variant assignment 与主效应 power 均须依据 pilot 的 event rate 和 family/trait/topic cluster variance在 `G6` 预注册；fork continuation seed rule 在揭示任何 fork outcome 前于 `G7` 冻结。V2.1 的 4/8/10 只可作为 power simulation 的候选情景，不得被自动选为运行值。

### 4.3 Randomized forks

Turn 10/15、5-turn horizon、`d in {0,1,2,3}`、no-clipping 和全部 arms feasible 的资格规则继续有效；但旧的 50 prefixes per Flat-4 persona、600 roots 和 9,600 continuations 不再有效。`G7` 必须使用最终 active trait strata 重算 quotas、shortfall rule 和总 turns。

在新版计数通过前，所有 outcome-bearing bulk run 必须 fail closed。

## 5. 生成和采集协议

### 5.1 Reproducibility unit

每条 trajectory 在运行前获得不可变 ID，其最小生成键为：

```text
protocol_version
model_id + model_revision + tokenizer_revision
behavioral_family_id + persona_trait_id + persona_prompt_variant_id + persona_catalog_sha256
topic_id + topic_scope + topic_split + eligible_behavioral_family_id
split_algorithm_version + split_seed + assignment_outcome_blind=true
balance_diagnostics_sha256 + topic_split_plan_manifest_sha256
scenario_version + scenario_sha256
topic_content_canonicalization_version=restart-v2.3-topic-move-root-v1
topic_move_ids + topic_move_sha256s + topic_content_root_sha256
pressure_family + schedule_id + L_1:25
pressure_template_ids_1:25
turn_composition_version + composed_user_turn_sha256s
pre_response_full_prompt_sha256s
generation_seed + sampling_config
```

`topic_move_sha256s` 必须恰有 25 个 pairwise-unique hashes。`topic_content_root_sha256` 使用 `restart-v2.3-topic-move-root-v1`：header 加换行后按 turn 1–25 拼接 `NN:<hash>`，行间单个换行、末尾无额外换行，然后对完整 UTF-8 payload 做 SHA256。Root 必须在 36 topics 中 globally unique；duplicate、跨 split 重用或 canonical replay mismatch 都在生成前 fail closed。

其中 `turn_composition_version` 唯一标识将 frozen `topic_move_t` 与 `pressure_template_t(L_t)` 组成实际 `U_t` 的确定性规则。Tuple `composed_user_turn_sha256s` 中的单-turn `composed_user_turn_sha256` 是组成后、进入 chat history 前的实际 user-turn UTF-8 bytes 的 SHA256；tuple `pre_response_full_prompt_sha256s` 中的单-turn `pre_response_full_prompt_sha256` 是 observational `t^-` 实际送入 tokenizer 的完整 chat-template-rendered prompt UTF-8 bytes 的 SHA256。两组 tuple 都必须严格包含 25 项、与 turn 1–25 对齐；不能只保存最后一轮、滚动摘要或未组合的 template hash。

模型输出、完整 prompt、token IDs、stop reason、runtime、software/hardware provenance 和异常状态全部 append-only 记录。组成版本、composed-turn hash、full-prompt hash 或 token replay 任一不一致时必须 fail closed，不得采集正式 activation。失败重跑生成新的 attempt ID，不覆盖原 attempt。

### 5.2 Pre-response activations

在每个 main turn 的 observational \(t^-\)（收到 \(U_t\)、尚未生成 \(A_t\)）对 full prompt 做一次可复现 forward pass，在 final prompt token 保存所有 layers 的：

- `resid_pre`；
- `attn_out`；
- `mlp_out`；
- attention summaries：entropy、persona/system-span mass、current-pressure-span mass、top-k mass。

约 5% stratified mechanistic subset 保存完整 attention patterns。选择必须在 outcomes 前完成。Primary activation corpus 使用明确的低精度存储格式；计算 dtype、保存 dtype、shape、checksum 和 component semantics 均进入 manifest。

### 5.3 Hook validation

每个模型批量运行前至少通过：

1. layer count、hidden size 和 component shape 检查；
2. final prompt token index 与 chat-template tokenization 检查；
3. hooks enabled/disabled 时 logits 数值一致性检查；
4. components 写回关系的抽样 reconstruction/consistency check；
5. 10-trajectory smoke 的 runtime、峰值显存、bytes/trajectory 和 round-trip read test；
6. 25-turn context 不截断 system persona/current pressure span 的检查。

任何模型不满足统一语义时不得用“近似同名 tensor”继续批量运行。

## 6. 行为测量与标签

Sustained Drift label 必须 behavior-only：judge 看不到 activation、Region score、模型条件的预测结果和 intervention risk estimate。`G2` 在 pilot 前冻结：

- 每个 persona trait 的 positive/negative behavioral anchors；
- probe/measurement 的时点和内容；
- judge models/raters、temperature、repeats 和 aggregation；
- drift score threshold；
- “sustained”需要连续多少次/多长窗口；
- onset 对离散 checkpoint 的精确映射与 interval censoring rule；
- disagreement/adjudication、blind IDs 和 reliability acceptance criteria。

不允许以 topic 正确性、pressure level、activation projection 或 Persona Vector score直接定义 Drift。用于 Drift 判定的文本不得同时作为 pre-response latent predictor 的未来信息。

到 Turn 25 未发生 Drift 的 trajectory 在行为学汇总中记为 `Stable-through-end`；在 survival analysis 中则记为 Turn 25 administrative right censoring。它不等价于“25 轮以后永远 Stable”。任何跨过 Turn 25 的 observational horizon 如何纳入、截短或排除，必须在 `G6` 冻结，不能把未知 future outcome 自动编码成 non-event。

## 7. Persona representation

Persona Vector 的提取数据必须与 36 个 main topics、pressure templates 和 test outcomes分离。`G2` 冻结：

- positive/negative paired prompts 的来源、数量和 split；
- vector formula、token aggregation 和 normalization；
- 每模型/每 persona 是独立 vector 还是共享映射；
- held-out representation-validation criteria；
- all-layer feature reduction 和 layer-selection procedure。

V2 primary predictor使用 pre-response representations。Response-token-mean projections仅为 secondary representation validation，不进入当前 turn 的 prospective feature set。

## 8. Statistical analysis plan

### 8.1 Expected stable response

只用 Development split 中最终 Stable 的 training trajectories 拟合低容量 conditional model：

\[
\hat z_t^S=g_\theta(z_{1:t-1},u_{1:t},c),
\qquad e_t=z_t-\hat z_t^S.
\]

第一版采用 ridge/low-order autoregression；\(c\) 至少包括 model、可用的 Persona representation、pressure family、absolute pressure history 和 turn。Family/trait/variant 的 categorical IDs 只用于 provenance、split 和 strata；在 unseen wording、within-family unseen trait 或 unseen-family primary evaluation 中，不得作为 predictor，也不得通过 lookup embedding 间接输入。

泛化评价的 Persona conditioning 只能来自 `G1/G2` 在 outcome 前冻结的 outcome-blind family/trait descriptors、由完全分离 items 提取的 Persona Vector，或预注册 cold-start encoder。该 encoder 的 inputs、training corpus、revision、parameters 和 checksum 在 `G2/G6` 冻结，且不得读取 held-out trait/family 的 Drift、activation 或 judge outcomes。使用 categorical Persona IDs 的 seen-only diagnostic 必须单独标记，不得支持 unseen claim。

若加入 topic information，只允许使用 `G1` 冻结的 outcome-blind topic features/embedding；categorical topic ID 不得作为 predictor。具体编码、regularization grid 和 feature dimension 在 `G6` 冻结，并只在 Development topics 比较。Topic 仍是 split 和 cluster unit。

### 8.2 Stability Region 与 Margin

对 \(w\in\{3,5\}\) 的 residual window 构造 shrinkage-Mahalanobis dynamic score：

\[
A_t^{dyn}=E_{t,w}^{\top}\Sigma^{-1}E_{t,w}
+\beta_v\sum\|\Delta e\|^2
+\beta_a\sum\|\Delta^2e\|^2.
\]

Development 学习 \(g_\theta,\Sigma,\beta_v,\beta_a,w\)。Calibration stable trajectories 不再调整这些模型参数。Primary calibration 对每条 stable calibration trajectory 计算：

\[
B_i^{max}=\max_{t\in\mathcal T_i^{eligible}}A_{i,t}^{dyn},
\qquad q_{1-\alpha}^{max}=Q_{1-\alpha}(B_i^{max}).
\]

Primary Region 与 Margin 为：

\[
\mathcal R_{\alpha,t}(c)=\{E:A_t^{dyn}\le q_{1-\alpha}^{max}(c)\},
\qquad
M_t^{geo}=q_{1-\alpha}^{max}(c)-A_t^{dyn}.
\]

Primary \(\alpha\) 控制的是 stable trajectory 在整个 eligible monitoring period 内出现任意一次 alarm 的概率目标；不得把相关 turns 当作独立 tests。Per-turn threshold 只能作为 secondary analysis。具体 \(\alpha\)、finite-sample/sequential calibration、eligible period 和 pooling/hierarchical rule 必须在 `G6` 冻结；不得看到 test 后合并条件。

### 8.3 Discrete-time hazard

以首次 Sustained Drift 为 event。Observational prediction row 位于 pre-response \(t^-\)：已经收到 \(U_t\)，尚未生成 \(A_t\)，只条件于当前 \(\mathcal F_t^-\) 和生成前已冻结的 future pressure plan \(u_{t:t+H-1}^{plan}\)。其 target window 是 \(\{t,\ldots,t+H-1\}\)。定义从同一个 prefix 出发的 multi-step hazards：

\[
q_{t,j\mid t^-}
=P(T_{drift}=j\mid T_{drift}\ge j,\mathcal F_t^-,u_{t:t+H-1}^{plan}),
\quad j=t,\ldots,t+H-1,
\]

\[
R_{t^-}^{obs,(H)}
=1-\prod_{j=t}^{t+H-1}(1-q_{t,j\mid t^-}).
\]

所有 \(t^-\) 之后的未知 latent/text states 均被积分掉；不得用未来 \(\mathcal F_j\) 计算这些 hazards。`G6` 也可以选择直接估计相同 target 的 direct-H risk，但必须在 outcomes/test 之前冻结。Primary horizon 为 H=5；H=3、10 是 sensitivity analyses。所有数据行由程序化 feature-availability audit 生成，禁止 \(A_t\)、当前回答 judge score、未来 probes、未来 states、最终 outcome summary 和 full-trajectory statistics 泄漏。

Turn 25 无 event 的 trajectory 在 survival analysis 中 administratively right-censored。对于 \(t+H-1>25\) 的 observational rows，是排除、截短还是使用 horizon-specific censoring estimand，由 `G6` 唯一冻结；不得把 Turn 25 之后未知的 outcome 编码成 non-event。

### 8.4 Required comparators

Untouched Test 至少比较：

1. condition/pressure-only base-rate model；
2. same-availability \(t^-\) text-only baseline（只到 \(U_t\)，不含 \(A_t\)）；
3. raw persona-projection baseline；
4. raw multi-layer activation baseline；
5. conditional residual trajectory model；
6. text + residual trajectory model。

GP、HMM 或 trajectory encoder 不替代简单 baseline；只有进入 `G6` 预注册的 non-Flow allowlist 后才可报告为扩展。Conditional/Normalizing Flow、Flow Matching 及其他 flow-based density/trajectory models 不作为 baseline、comparator、ablation 或 extension。

### 8.5 Primary reporting set

- turn-level AUROC、AUPRC；
- Brier score 和 calibration curve；
- false alarms / 100 eligible stable turns；
- trajectory-level detection rate；
- lead-time distribution及 median；
- event-aligned Margin at T−10、T−5、T−3、T−1；
- matched-condition and resistant-condition specificity；
- text baseline 之上的增量效果及 cluster-aware uncertainty；
- model/persona/topic heterogeneity。

Primary metric、最小有意义增益、false-alarm budget、warning threshold、\(\alpha\)、confidence level 和多重比较 family由 `G6` 冻结。目前均为 `TBD`，不得从 test performance 反推。

### 8.6 Uncertainty, nesting and claim boundary

观测层级的嵌套主干是：

```text
behavioral family → persona trait → prompt variant → trajectory → turn
```

Shared Topic 与这一主干交叉；family-specific Topic 只在 eligible family 内交叉。共享同一 topic 的 model/trait/variant/seed/schedule trajectories 相关；seeds 是 trajectory replicates 而不是新 trait 或无条件 iid 单位。干预数据另有 `root trajectory/prefix → dose arm → fork continuation` 嵌套。同一 root 下的 forks 共享历史，不能装作独立 roots。

Primary uncertainty 计算必须遵守：

1. observational Development/Calibration/Test 以 **topic** 为 outer cluster/resampling unit，在预注册 topic_scope/source/scenario strata 内重抽整个 topic block，保留该 topic 下全部 Persona 层级、trajectories 和 turns；
2. Region 的 primary alarm calibration 使用 trajectory-level maxima，不将 turns 当 iid calibration samples；评估 calibration uncertainty 时仍保留 topic blocks；
3. randomized fork 以 **root prefix** 为 randomization/dependence unit，重抽一个 root 时同时携带其所有 dose arms 与 continuations，并使用 topic 作 outer block/层级效应；
4. turns、seeds、prompt variants 和 fork continuations 均不得被当作 iid replicates 以缩小标准误。

Estimator、topic_scope/source/scenario strata、small-cluster correction 与有限样本区间在 `G6/G7` 冻结，但不能改变上述 primary units。规划中只有 4 个 behavioral families，因此 family 作为有限的 fixed claim strata，不作为 4 个 iid clusters 来估计“所有可能 Persona families”的 population variance。一个 fully unseen family 只支持对该预注册 family 的 cold-start transfer claim，不支持无界的新-family population generalization。Trait 级 claim 也条件于 `G1` 冻结的 sampling frame 和 inclusion rule。Shared-topic cross-family claim 与 family-specific within-family claim 必须分开估计和报告；held-out family-specific topic 只支持 Persona + Scenario 联合迁移诊断。

## 9. Randomized causal Robust Radius

### 9.1 Assignment

Fork cut-off 是完成 \(A_t\) 之后的 \(t^+\)。只有在 through-turn-t 行为测量尚未满足 Drift，且未来 baseline levels 可容纳全部 \(d=0,1,2,3\) 时，包含 \(A_t\) 的 prefix 才 eligible。Prefix selection 按 model × behavioral family × active trait × prompt variant × topic × fork turn 的预注册 strata/配额抽取；四个 dose arms 与 OPEN 的 continuation-seed count 在任何 fork outcome 前由独立 assignment/seed manifests 冻结。

### 9.2 Estimands

H=5 下：

\[
R_{t^+}^{fork,(5)}(d)
=P(T_{drift}\in\{t+1,\ldots,t+5\}\mid T_{drift}>t,do(d),\mathcal F_t^+),
\]

\[
\rho_{t^+}^{causal}=\min\{d\in\{0,1,2,3\}:R_{t^+}^{fork,(5)}(d)\ge\eta\}.
\]

\(\eta=0.8\) 为 primary operational threshold，0.7 和 0.9 为 sensitivity。若 d≤3 都未达到阈值，Radius 报告为 `>3 PPU`。

单 prefix 每 arm 的 continuation count 是 `G7` 依据精度/power 和资源证据待冻结的变量 \(s_{\mathrm{fork}}(x)\)。Primary causal effect 的聚合层级、monotonicity assumption、partial pooling 和个体化 Radius 的证据等级也在 `G7` 冻结。未经该 gate，任何单 prefix 的小样本经验比例都不得被宣称为精确因果风险。\(R_{t^-}^{obs,(H)}\) 与 \(R_{t^+}^{fork,(H)}(d)\) 的信息集、窗口和干预含义均不同，二者不得拼接为同一个 risk endpoint。

## 10. Execution stages and stopping rules

| Stage | 输入 | 必须产出 | Stop / go |
|---|---|---|---|
| 0. Archive & provenance | 旧项目 + 三份设计材料 | 三个 source checksums、Git tag、read-only artifact archive manifest verification | `G0` **PASS** |
| 1. Static public design | public datasets | Persona family/trait catalog 与 sampling frame、public item/provenance manifests、36-topic `topic_scope`/source/content-root manifests、exact 18/6/12 IDs、exact 6 pilot-asset IDs、split provenance fields/plan hash、`topic_scope × family` eligibility、静态双轴 access policy、25-turn templates、suitability/topic-feature contracts | `G1` |
| 2. Measurement design | persona definitions | fully held-out family 与 trait/variant/wording generalization assignments、vectors protocol、judge rubric、onset rules | `G2` |
| 3. Instrumentation smoke | 3 target models + 6 pilot assets | 六个 assets 的 outcome-free QA、model license/access、frozen revisions、hook validation、benchmark；held-out-family Persona 不产生 outcome | `G3` |
| 4. Pressure calibration | L0–L5 candidates | calibrated template bank | `G4` |
| 5. Dose pilot | signed `X_pilot`：5 logical topic assets × 3 Development families only | S* decisions、topic-stratified within-cell positivity/overlap、variance/runtime/storage；held-out family 无 outcome | `G5` |
| 6. Analysis/power lock | Development-family pilot summaries only | two-clock estimands、trajectory-max calibration、Turn-25 rule、confirmatory exposure rule、signed `X_main`、heldout-family schedule-transfer/fallback、power、non-Flow allowlist | `G6` |
| 7. Main study | signed `X_main` only | frozen Development/Calibration/Test artifacts；shared untouched 是 heldout-family primary cold-start，family-specific untouched 是 joint transfer | test opened once |
| 8. Intervention | eligible prefixes + signed `X_fork` | eligibility/shortfall decision、randomized fork results | `G7` before outcomes |
| 9. External evaluation | frozen pipeline | PersonaGym study | `G8` |

通用 stopping rules：

- label reliability 未达到 `G2` 标准：停止生成或重做 rubric，不调 activation model弥补；
- hook/logit equivalence失败：停止对应模型；
- transition band 不存在：停止该 cell或走预注册 pressure-template扩展；
- held-out family 的 schedule-transfer/fallback rule 无法给出可执行且有左右邻居的 schedule：停止该 family evaluation，不查看 outcome、不事后调 dose；
- aggregate transition band 存在但 topic-stratified positivity/overlap 不足：停止该 cell，不用 aggregate rate 掩盖 topic separation；
- 存储/runtime 超过 `G3/G5` cap：先调整工程格式或样本设计 amendment，不丢字段后继续；
- G7 eligible prefixes 少于任一预注册 stratum target：停止并 amendment，不 clipping、不跨 stratum 替代、不凑数；
- main generation 开始后不得因 interim performance 改特征、阈值、seed 数或 test split；
- untouched test 不用于 debug；工程错误需通过 blind integrity audit 确认后整批重跑并保留失败 provenance。

## 11. Reproducibility deliverables

每个 gate 至少提交：

- machine-readable config；
- input/output schema version；
- frozen IDs/seeds manifest；
- SHA256 checksums；
- environment/model revision manifest；
- validation report；
- exact command or scheduler job spec；
- failure ledger；
- 不含 secret 的 Git commit。

Raw generations、activations、licensed model weights 和 credentials 不进入 Git。Git 只同步代码、small manifests、aggregate results、protocol amendments 和可复现命令。

## 12. 当前状态

截至本协议日期，G0 已通过：三份设计源文件 checksums、pre-restart Git tag 和 read-only artifact archive manifest 已验证。以下内容均尚未发生：

- 未完成 G1–G8；
- 未运行任何 V2.3 dose-finding pilot；
- 未生成任何 V2.3 main trajectories；
- 未运行 randomized intervention；
- 未得到 V2 Region、Margin、hazard 或 Robust Radius 结果；
- 未形成任何 V2 confirmatory conclusion。

历史 Gate A/B/C 和 OLMo 结果可以在背景中引用，但必须明确标记为 V1 historical exploratory evidence。
