# Latent Persona Seismograph V2：正式研究协议

Protocol ID：`LPS-V2-20260824`
版本：`2.0-preparation`
状态：正式协议；G0 `PASS`，G1–G8 open；尚未开始 V2 pilot，尚无 V2 实验结果
权威设计来源：[`deep-research-report.md`](../deep-research-report.md) 与 [`重启项目的细节.md`](../重启项目的细节.md)
执行解释：[`docs/restart_v2_amendment.md`](restart_v2_amendment.md)

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

## 2. 研究单位与术语

- **Main turn**：一条正式 user message + 一条 assistant response；system/persona 初始化不计入。
- **Full trajectory**：25 个 main turns。
- **Persona condition**：一个冻结的行为型 persona 及其 system-prompt operationalization。
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

### 3.2 Primary personas

来源为 Anthropic Model-Written Evals，固定四个 behavioral persona conditions：

- `risk-averse`；
- `risk-seeking`；
- `stands-its-ground`；
- `agreeableness`。

它们是四个独立预注册条件，不宣称构成两对完美心理学反义轴。每个 persona 的 source item IDs、system-prompt 转换规则和 persona-opposing pressure family 在 `G1/G2` 冻结。

PersonaGym 仅用于 pipeline 冻结后的 external cross-persona evaluation；它不参与 V2 主模型开发、校准或 primary test。

### 3.3 Topics

主研究固定 30 个 public topic anchors：

\[
24\text{ MMLU-Pro anchors}+6\text{ Anthropic sycophancy/opinion anchors}.
\]

24 个 MMLU-Pro anchors 覆盖 12 个预先选择领域，每域 2 个；6 个观点 topics 由 philosophy、NLP 和 politics 各 2 个构成。公开问题只提供 topic/scenario anchor；正确答案不是 Drift label。

所有 item IDs 和 25-turn scenario conversion templates 在生成前冻结。按 topic 划分：

| Split | Topics | 用途 |
|---|---:|---|
| Development | 15 | 特征/模型开发、候选比较、pilot、power simulation |
| Calibration | 5 | region threshold、warning threshold、probability calibration |
| Untouched Test | 10 | 所有方法冻结后的一次性 confirmatory evaluation |

6 个 pilot topics 是 15 个 Development topics 中预先标记的子集，不进入 Calibration 或 Untouched Test。

Topic ID 是 split、provenance 和 cluster unit，不是可泛化 predictor。模型不得使用 untouched topic 的 categorical ID；需要 topic conditioning 时，只能使用在 outcomes 前冻结、与 Drift labels 无关的 topic features/embedding。Public-data license/terms、feature extractor/revision 和 feature-freeze manifest 属于 `G1`；具体模型编码与 regularization 属于 `G6`。

### 3.4 Pressure schedules

每个 persona × pressure family 建立 L0–L5，每级约 8 个意图等价 templates。独立 raters 在看不到模型 Drift outcome 的情况下完成 0–100 intensity ratings 与 pairwise ordering；ordinal/Rasch calibration、接受标准和 prompt rewrite rule 在 `G4` 冻结。

候选 gradual schedules 为 `restart_v2_amendment.md` 定义的 \(S_{-2},\ldots,S_{+2}\)，首 5 turns 永远为 L0 neutral baseline。Pilot 为每个 model × persona 选择有左右邻居且位于 transition band 的 \(S^*\)。Main 使用：

\[
S^*_{-1},\quad S^*,\quad S^*_{+1}.
\]

这里下标表示 schedule-grid neighbor；每条记录仍保存实际的 \(L_{1:25}\)。

## 4. 样本设计

### 4.1 Dose-finding pilot

\[
3\text{ models}\times4\text{ personas}\times6\text{ development topics}
\times4\text{ seeds}\times5\text{ schedules}=1{,}440
\]

即 36,000 target-model turns。Pilot 仅用于：

- protocol/hook sanity checks；
- 为每个 model × persona 寻找 aggregate \(0.2<P(Drift)<0.8\) 的 transition schedules；
- 检查 topic-stratified within-cell positivity/overlap，确认 Stable/Drift 不只是由少数 topics 或 topic-separable outcomes 造成；
- 估计 event rate、topic/trajectory cluster variance、runtime 和 storage；
- 运行 simulation-based power check。

Pilot 不产生 confirmatory claim。Aggregate 0.2–0.8 只是必要条件，不是充分条件；topic-stratified positivity/overlap 的量化接受标准在看到 pilot outcomes 前由 `G5` decision rule 冻结。若没有 eligible \(S^*\) 或 within-cell support 不足，执行 `G5` 中的停止/扩展规则。

### 4.2 Main full trajectories

\[
3\times4\times30\times8\times3=8{,}640
\]

即 base plan 为 216,000 target-model turns。每个 model × persona × schedule cell 有 240 trajectories。`8 seeds` 是初始冻结值；只有 `G6` 预先规定的 simulation rule 判定 power 不足时，才能在 main generation 开始前统一扩展为 10 seeds，并重算全部 totals。

### 4.3 Randomized prefix forks

在 main 保持 8 seeds 且 `G7` eligibility 全部满足的 base plan 中，每个 model × persona 选择 50 个 eligible、尚未 Drift 的 post-response prefixes：Turn 10 和 Turn 15 各 25 个，共 600 root prefixes。每个 prefix 包含已完成的 \(A_t\)，并随机生成：

\[
4\text{ doses}\times4\text{ continuation seeds}=16
\]

个 H=5 continuation，base-plan target 共 9,600 short trajectories、48,000 turns。Primary arms 为 \(d\in\{0,1,2,3\}\)，且必须满足无 clipping 的上界资格规则。

若任一 model × persona × fork-turn stratum 无法取得目标数量的 eligible prefixes，立即停止并提交 amendment；禁止跨 stratum 借用/复制 prefix、改 fork turn、降低 dose、clipping 或替代 arms 来凑到 600/9,600。

Fork arms 共享 root prefix，因此统计单位不是 9,600 个彼此独立的 trajectories；估计和 bootstrap 必须保留 root-prefix cluster。

### 4.4 计划总量

在 main=8 seeds 且 G7 eligibility 满足时，base-plan target-model generation 约为：

\[
36{,}000+216{,}000+48{,}000=300{,}000\text{ turns}.
\]

300,000 不是无条件 realized sample size。若 G6 触发 10 seeds、G7 shortfall 或正式 amendment，必须重新计算并报告 planned/realized totals。这也不包括 pressure calibration raters、behavior judges、Persona Vector extraction/validation、PersonaGym external evaluation、失败重跑和 full-attention audit；资源表必须分别核算这些项目。

## 5. 生成和采集协议

### 5.1 Reproducibility unit

每条 trajectory 在运行前获得不可变 ID，其最小生成键为：

```text
protocol_version
model_id + model_revision + tokenizer_revision
persona_id + persona_prompt_version
topic_id + scenario_version + split
pressure_family + schedule_id + L_1:25
prompt_template_ids_1:25
generation_seed + sampling_config
```

模型输出、prompt、token IDs、stop reason、runtime、software/hardware provenance 和异常状态全部 append-only 记录。失败重跑生成新的 attempt ID，不覆盖原 attempt。

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

- 每个 persona 的 positive/negative behavioral anchors；
- probe/measurement 的时点和内容；
- judge models/raters、temperature、repeats 和 aggregation；
- drift score threshold；
- “sustained”需要连续多少次/多长窗口；
- onset 对离散 checkpoint 的精确映射与 interval censoring rule；
- disagreement/adjudication、blind IDs 和 reliability acceptance criteria。

不允许以 topic 正确性、pressure level、activation projection 或 Persona Vector score直接定义 Drift。用于 Drift 判定的文本不得同时作为 pre-response latent predictor 的未来信息。

到 Turn 25 未发生 Drift 的 trajectory 在行为学汇总中记为 `Stable-through-end`；在 survival analysis 中则记为 Turn 25 administrative right censoring。它不等价于“25 轮以后永远 Stable”。任何跨过 Turn 25 的 observational horizon 如何纳入、截短或排除，必须在 `G6` 冻结，不能把未知 future outcome 自动编码成 non-event。

## 7. Persona representation

Persona Vector 的提取数据必须与 30 个 main topics、pressure templates 和 test outcomes分离。`G2` 冻结：

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

第一版采用 ridge/low-order autoregression；\(c\) 至少包括 model、persona、pressure family、absolute pressure history 和 turn。若加入 topic information，只允许使用 `G1` 冻结的 outcome-blind topic features/embedding；categorical topic ID 不得作为 predictor。具体编码、regularization grid 和 feature dimension 在 `G6` 冻结，并只在 Development topics 比较。Topic 仍是 split 和 cluster unit。

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

复杂 GP、HMM、flow 或 trajectory encoder 不替代简单 baseline；只有 `G6` 预注册为扩展后才可报告为 confirmatory family。

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

### 8.6 Uncertainty and dependence

Turns 不作为 iid observations。分析必须保留以下依赖：同一 trajectory 内的 turns、同一 topic 内的 seeds、同一 root prefix 的 intervention forks。具体采用 hierarchical model、cluster bootstrap 或二者组合；resampling unit 和 strata 在 `G6/G7` 冻结。

## 9. Randomized causal Robust Radius

### 9.1 Assignment

Fork cut-off 是完成 \(A_t\) 之后的 \(t^+\)。只有在 through-turn-t 行为测量尚未满足 Drift，且未来 baseline levels 可容纳全部 \(d=0,1,2,3\) 时，包含 \(A_t\) 的 prefix 才 eligible。Prefix selection 按 model × persona × fork turn 预先分层随机抽取；四个 dose arms 与 continuation seeds 的 assignment 由独立 seed manifest 生成。

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

由于单 prefix 每 arm 只有 4 continuations，primary causal effect 的聚合层级、monotonicity assumption、partial pooling 和个体化 Radius 的证据等级在 `G7` 冻结。未经该 gate，不宣称单 prefix 的经验 0/4…4/4 比例是精确因果风险。\(R_{t^-}^{obs,(H)}\) 与 \(R_{t^+}^{fork,(H)}(d)\) 的信息集、窗口和干预含义均不同，二者不得拼接为同一个 risk endpoint。

## 10. Execution stages and stopping rules

| Stage | 输入 | 必须产出 | Stop / go |
|---|---|---|---|
| 0. Archive & provenance | 旧项目 + 三份设计材料 | 三个 source checksums、Git tag、read-only artifact archive manifest verification | `G0` **PASS** |
| 1. Static public design | public datasets | data license/terms、persona/topic/split manifests、scenario templates、topic-feature contract | `G1` |
| 2. Measurement design | persona definitions | vectors protocol、judge rubric、onset rules | `G2` |
| 3. Instrumentation smoke | 3 target models | model license/access、frozen revisions、hook validation、10-trajectory benchmark | `G3` |
| 4. Pressure calibration | L0–L5 candidates | calibrated template bank | `G4` |
| 5. Dose pilot | 1,440 trajectories | S* decisions、topic-stratified within-cell positivity/overlap、variance/runtime/storage | `G5` |
| 6. Analysis/power lock | pilot summaries only | two-clock estimands、trajectory-max calibration、Turn-25 horizon rule、signed analysis manifest、power result | `G6` |
| 7. Main study | 8,640 trajectories | frozen Development/Calibration/Test artifacts | test opened once |
| 8. Intervention | eligible post-response main prefixes | eligibility/shortfall decision、randomized fork results | `G7` before outcomes |
| 9. External evaluation | frozen pipeline | PersonaGym study | `G8` |

通用 stopping rules：

- label reliability 未达到 `G2` 标准：停止生成或重做 rubric，不调 activation model弥补；
- hook/logit equivalence失败：停止对应模型；
- transition band 不存在：停止该 cell或走预注册 pressure-template扩展；
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
- 未运行 1,440 条 V2 pilot；
- 未生成 8,640 条 V2 main trajectories；
- 未运行 randomized intervention；
- 未得到 V2 Region、Margin、hazard 或 Robust Radius 结果；
- 未形成任何 V2 confirmatory conclusion。

历史 Gate A/B/C 和 OLMo 结果可以在背景中引用，但必须明确标记为 V1 historical exploratory evidence。
