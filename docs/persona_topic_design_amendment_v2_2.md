# Latent Persona Seismograph V2.2：Persona–Topic 设计修订

Amendment ID：`LPS-V2.2-PERSONA-TOPIC-20260825`
版本：`2.2-preparation`
日期：2026-08-25
状态：正式范围修订；仅完成设计记录，`G1–G8` 仍为 open，尚无 V2.2 实验结果

## 1. 来源、效力与状态词

本修订记录用户在 Persona/Topic 讨论中明确认可的设计方向，并将尚未获得足够依据的执行项继续留在 gate 内。讨论记录为 [`persona和topic的讨论.md`](../persona和topic的讨论.md)，其 SHA256 为：

```text
c6cb50d4f039d77b347a145c3b0408fd04a526bf123f586986775d2f75eb47bf
```

该讨论文件是 V2.2 的决策 provenance，不替换三份 G0 权威来源，也不把讨论中的每一条助手建议自动提升为用户决定。本修订只采用以下两种状态描述讨论产生的新设计：

- **ENDORSED DIRECTION**：用户明确认可的研究方向，可以据此开展 outcome-free 准备工作；除非同时标为 frozen，否则不等于 exact executable value。
- **OPEN**：尚未冻结，不能使用默认值、示例、近义词或临时生成内容代替；必须在指定 gate 形成 manifest、审查证据和 checksum 后才能用于 outcome-bearing run。

本修订取代 V2.1 中把四个孤立 Persona 当作完整 primary sampling frame 的部分，也取代所有由该 Flat-4 假设推导的样本量目标。V2.1 的两时钟、pre-response activation、L0–L5/PPU、absolute schedules、Region/hazard、干预边界和全 V2 排除 Flow 方法等条款继续有效。

## 2. Persona 设计

### 2.1 ENDORSED DIRECTION

Persona 实验对象采用层级化定义：

```text
Behavioral Family
└── Persona Trait
    ├── Prompt Variant
    └── Evaluation Items
```

以下方向已被认可：

1. 研究覆盖多个 behavioral families，而不是用四个孤立 traits 代表全部 Persona 空间。
2. 规划目标是 4 个 families、每个 family 4–6 个真正可区分的 traits，即 16–24 个 true persona traits；这是候选招募与审查方向，不是已冻结的可运行数量。
3. 同一 JSONL 中的多个 evaluation items 仍属于一个 trait 的测量题库，不能重复计数为多个 Persona。
4. 同一 trait 的多个 system-prompt variants 是多个 prompt conditions，不能重复计数为多个独立 Persona traits。
5. 泛化评价分三层：未见 prompt wording、同一 family 内未见 trait、以及完整未见 behavioral family。
6. 至少保留同一 family 内的未见 traits，并保留一个完整未见 family；Development、Calibration 与 untouched evaluation 的具体分配必须在生成前冻结。
7. Persona 覆盖优先增加真正独立的 traits；不得为了达到目标数量而把近义标签、prompt 改写或 evaluation items 当作独立 traits。

### 2.2 RETIRED：Flat-4 primary design

V2.1 使用的以下 Flat-4 列表不再构成完整的 primary confirmatory sampling frame：

- `risk-averse`；
- `risk-seeking`；
- `stands-its-ground`；
- `agreeableness`。

这些名称只能作为等待公开语料审计的候选 traits。V2.2 不保证它们最终全部入选，也不允许在未通过 `G1/G2` 时把它们直接写入运行 manifest。

### 2.3 OPEN — `G1` Persona sampling frame

以下内容全部保持 OPEN：

- 四个 behavioral families 的精确定义、名称和边界；
- 每个 family 最终纳入 4、5 还是 6 个 traits，以及最终总 trait 数；
- 每个 trait 的公开 source file、immutable item IDs、上游 revision、license/terms 和下载文件 checksum；
- 判断两个候选是否为独立 traits、近义重复或同一 trait prompt variants 的审查 rubric；
- family 内方向/侧别及其是否具有可比较的反向 pressure；
- family、trait 在 Development、Calibration、within-family untouched 和 unseen-family evaluation 中的分配；
- eligibility shortfall、family 不平衡或合格 traits 少于规划目标时的停止与 amendment 规则。

候选筛选必须在任何 Drift outcome 产生前进行，并至少检查：行为可操作性、可定义相反 pressure、与 safety policy 的可分离性、足够的高质量 evaluation items、family 内实质区分度和跨 family 覆盖。若公开语料不能支持规划目标，必须报告 shortfall 并修改设计；不得用近义词补足数量。

### 2.4 OPEN — `G2` operationalization 与测量

以下内容全部保持 OPEN：

- 每个 trait 的定义文本和 system prompts；
- prompt variants 的数量、文本、长度/结构匹配规则和 unseen-wording assignment；
- item bank 中 definition、Persona Vector extraction 和完全 held-out validation 的分割比例及 immutable IDs；
- prompt 构造者/生成器、版本、seed、盲审和重写规则；
- held-out behavioral validation、trait distinguishability、judge rubric、onset 和 Sustained Drift 标准；
- Persona Vector 的 paired prompts、公式、层/组件选择和 validation threshold。

用于定义或修改 prompt 的 item、用于表示提取的 item、以及最终 held-out validation item 必须按冻结 manifest 分离。25-turn main topics、pressure templates 和 main outcomes 也不得充当 Persona prompt 开发或 Persona Vector validation 数据。

### 2.5 Predictor 的 cold-start 边界

`behavioral_family_id`、`persona_trait_id` 和 `persona_prompt_variant_id` 是 provenance、split、assignment 和统计分层字段，不因此自动成为 predictor features。对 unseen wording、within-family unseen trait 和 unseen family 的 primary evaluation：

1. predictor 不得使用 categorical family/trait/variant ID、one-hot 编码或由这些 ID 学得的 lookup embedding；
2. 只能使用 `G1/G2` 在任何 trajectory outcome 产生前冻结的 outcome-blind trait/family descriptors、由分离 items 提取的 Persona Vector，或预注册的 cold-start encoder；
3. cold-start encoder 的 inputs、training corpus、revision、parameters 和 freeze checksum 必须于 `G2/G6` 锁定，不得读取 held-out trait/family 的 Drift、activation 或 judge outcomes；
4. 任何使用 categorical IDs 的 seen-only diagnostic 都必须独立标记，不得用来支持 unseen-trait 或 unseen-family claim。

Prompt variant 的 wording 文本若被编码，也必须遵守 frozen observed/unseen-wording assignment；不得在评价时为 held-out wording 新建结果导向的映射。

## 3. Topic 设计

### 3.1 RETAINED V2 CONTRACT

讨论没有形成把 30 topics 改为 36 或 40 的用户决定，因此 V2.2 保留：

- 30 个 public topic anchors；
- 24 个 MMLU-Pro anchors + 6 个 Anthropic sycophancy/opinion anchors；
- 15 Development / 5 Calibration / 10 Untouched Test；
- 6 个 pilot topics，且它们是 Development 的预先指定子集；
- 25 个 main turns，前 5 turns 为 L0 neutral baseline；
- Topic 是 outer split、provenance 和 cluster unit。

讨论中的 `36 topics / 18-6-12`、`40 topics` 及 `36 = 30 general + 6 opinion` 仅为未采纳建议，不属于 V2.2 执行契约。任何更改 topic 总数、来源比例或 split 数量都需要新的明确 amendment。

### 3.2 OPEN — `G1` exact topic corpus

以下内容全部保持 OPEN：

- 12 个 MMLU-Pro categories 的精确名单及每类 2 个 immutable item IDs；
- Anthropic philosophy、NLP、politics 三个 source pools 各 2 个 immutable item IDs；
- 两个上游数据源的 canonical URL、license/terms、revision、retrieval date 和文件 checksum；
- 30 个 transformed topic IDs、15/5/10 assignment 和 6 个 pilot IDs；
- source/category-stratified split 算法、seed 和平衡诊断；
- outcome-blind topic suitability rubric、审查者、排除理由与 inter-rater rule；
- 每个 anchor 的 deterministic 25-turn scenario conversion、模板版本和输出 checksum；
- Anthropic biography/user-stance 字段的标准化、剥离或 source-specific baseline/estimand 处理；
- outcome-blind topic feature/embedding extractor、revision、维度和 freeze manifest。

MMLU-Pro 有其自身 categories，而 Anthropic 的 philosophy/NLP/politics 是不同 source/task strata；它们不能被描述为与 MMLU-Pro 完全互斥的额外语义 domains。特别是 philosophy 存在直接语义重叠，NLP/politics 也可能与其他 MMLU-Pro categories 相关。

### 3.3 Outcome-blind topic suitability

Topic 筛选只能读取公开 source text、source metadata 和预注册 rubric，不得读取任何 candidate topic 上的 Drift、activation、warning、judge 或 transition-band outcome。Rubric 至少要求：

1. 内容完整且可确定性转换为 25-turn interaction；
2. 在不改变事实正确性的前提下，允许预注册 Persona families 有行为表达空间；
3. 不依赖安全违规、拒答或政策冲突制造表面 Drift；
4. 不把 MMLU-Pro 正确答案直接当作 Drift label；
5. 不把某个模型/Persona 的试跑表现作为保留或剔除依据。

任何 outcome-bearing run 后替换 topic、split 或 pilot ID 都必须停止相应阶段并提交 amendment；不得用“场景不合适”作为静默替换理由。

### 3.4 Scenario、pressure 与 source confounding

公开 item 只提供 Topic Anchor。每个 25-turn scenario 必须把内容推进与压力操纵分离：

```text
actual user turn = frozen topic move + frozen pressure template at L_t
```

Topic scenario 保存 content-only `topic_move` 与显式 `pressure_slot`；不得把某一 Persona 的反向 pressure 永久写入 topic template。所有 Persona/model/seed/schedule 版本仍继承同一个 topic split。

Anthropic sycophancy items 原生 biography 或用户预表态已经包含 social influence。`G1/G4` 必须在运行前唯一冻结以下其中一种可审计处理：

- 以确定性转换剥离或标准化原生 stance，使 L0 与其他 source strata 可比较；或
- 保留原生 stance，但建立独立 source-specific baseline、pressure interpretation 和交互 estimand。

在该选择未冻结前，Anthropic opinion anchors 不得进入 outcome-bearing pilot。不得把原生 stance 造成的压力与后来叠加的 L0–L5 剂量混合解释。

### 3.5 Topic leakage boundary

同一个 `topic_id` 下的所有 Persona、trait、prompt variant、model、seed、schedule、trajectory 和 fork 必须属于同一个 outer split。Untouched topic 的 categorical ID 不得作为 predictor；需要 topic conditioning 时，只能使用 outcome 前冻结的 topic features/embedding。若论文声称 category-level unseen generalization，必须另行预注册完整 category holdout；当前 10 个 Untouched topics 只保证 exact-topic holdout。

## 4. RETIRED 样本量与重算要求

以下 V2.1 数字均由 Flat-4 Persona 假设推导，现为 **RETIRED PLANNING FIGURES**，不是 V2.2 targets，更不是实验结果：

| V2.1 figure | 旧用途 | V2.2 状态 |
|---:|---|---|
| 1,440 full trajectories / 36,000 turns | dose-finding pilot | RETIRED；待 Persona frame 和 pilot assignment 冻结后重算 |
| 8,640 full trajectories / 216,000 turns | main study | RETIRED；待 power 与层级化 Persona design 冻结后重算 |
| 600 root prefixes / 9,600 forks / 48,000 turns | randomized intervention | RETIRED；待 active strata 与 G7 eligibility 冻结后重算 |
| 约 300,000 target-model turns | 8-seed base-plan 合计 | RETIRED；不得继续用于预算、排队或完成度汇报 |

V2.1 的 pilot 4 seeds、main 8 seeds、候选 `8→10`，以及 fork 每 arm 4 continuation seeds 也只属于 **V2.1 candidate history**。V2.2 的 pilot/main/fork seeds 必须按 phase 依据 power/精度、cluster variance、event rate 和资源 benchmark 分别冻结；不得把 4、8 或 10 作为 fallback default。

V2.2 保留 3 个 target models、30 topics、25 main turns、L0–L5 和既有 absolute pilot schedules；但 trajectory 数、每层级 seeds、Persona/prompt sampling matrix、fork-prefix quotas、总 turns、storage 和 walltime 均为 OPEN。

对 $\phi\in\{\mathrm{pilot},\mathrm{main},\mathrm{fork}\}$，`G1/G2/G6/G7` 按职责冻结一份 phase-specific row-wise assignment manifest $X_{\phi}$。每个 non-seed row 必须显式含 trait × prompt-variant pair，以及该 phase 所需的 model/topic/schedule 或 root/fork-turn/dose 字段。定义：

$$
A^{(\phi)}_{\tau v}=\lvert X_{\phi}(\tau,v)\rvert,
\qquad
N_{\phi}=\sum_{x\in X_{\phi}}s_{\phi}(x),
$$

其中 $s_{\phi}(x)$ 是该行在对应 gate 待冻结的 generation/continuation seed 数。只有逐行 seed 数一致时，才可写成 $N_{\phi}=s_{\phi}\sum_{\tau,v}A^{(\phi)}_{\tau v}$。$A$ 必须计入每次 prompt-variant exposure；不得只计 trait 数，不得使用未验证的平均 `K_variant`，也不得将 robustness-only/unseen-wording rows 排除在资源总量之外。

重算必须：

1. 使用 `G1/G2` 最终 eligible family/trait/prompt manifests；
2. 明确哪些层级进入完整 crossed design，哪些采用预注册 balanced design；
3. 保持 Topic outer split 和 cluster dependence；
4. 使用 pilot variance/event rate 进行 `G6` power simulation；
5. 在任何 outcome-bearing bulk run 或 GPU 资源申请前形成带版本的 sample-size manifest。

### 4.1 统计嵌套、依赖与 claim boundary

观测主干是：

```text
behavioral family → persona trait → prompt variant → trajectory → turn
```

Topic 与 Persona 层级交叉；同一 topic 下的不同 model/trait/variant/seed/schedule trajectories 不是独立样本。干预另有 `root trajectory/prefix → dose arm → fork continuation` 嵌套，同一 root 下的 doses/continuations 必须绑定处理。

Primary uncertainty 契约为：

- observational evaluation 以 topic 为 outer cluster/resampling unit，在 source/category strata 内重抽整个 topic block，不拆分其内 trajectories/turns；
- trajectory-max calibration 以 trajectory 为 score unit，topic 依赖在不确定性评估中继续保留；
- randomized intervention 以 root prefix 为 randomization 和主 dependence unit，重抽时携带该 root 的所有 dose arms 与 continuations，并以 topic 作 outer block/层级效应。

具体 estimator、small-cluster correction、strata 与有限样本区间在 `G6/G7` 冻结，但不得把 turn、seed、variant 或 fork continuation 当作 iid 重复。

规划仅有 4 个 behavioral families，因此 family 是有限、预注册的 fixed claim strata，不是用于估计无限 family population variance 的 4 个 iid clusters。完整 held-out family 的结果只能表述为对该预注册 family 的 cold-start transfer；若要声称对新 behavioral families 的总体泛化，必须在新 amendment 中增加 family-level sampling frame 和足够的 family units。

## 5. Gate 影响与停止规则

- `G0` 的三份权威来源 checksum、Git tag 和只读旧档案验证仍为 PASS；本讨论文件是新增 V2.2 provenance，不追溯改写 G0。
- `G1` 必须同时冻结 Persona sampling frame 与 exact 30-topic corpus，不能只完成其中一侧。
- `G2` 必须冻结 trait/prompt/item-role 层级和行为测量，Flat-4 prompt 不得作为默认实现。
- `G3/G4` 可进行不含 outcome 的 instrumentation 与 pressure calibration 准备，但不得借此筛选“容易出结果”的 traits/topics。
- 旧的 1,440-trajectory pilot 不再自动获得授权；新的 pilot sample-size manifest 未通过前不得批量生成。
- `G5/G6/G7` 的 transition、power 和 intervention 规则必须使用重算后的 strata/targets。

若 exact traits、prompt variants、source items、licenses/revisions、topic IDs、templates、split 或样本量仍为 OPEN，代码必须 fail closed；不得从 V2.1 config、README 示例或讨论文字中补默认值。

## 6. 当前结论边界

V2.2 仍处于准备阶段。本修订只改变设计和执行边界，没有生成任何新 trajectory、activation、behavior label、Region、Margin、hazard、Robust Radius 或确认性结论。
