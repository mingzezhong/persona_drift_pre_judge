# Persona Drift 项目重启 V2：执行解释与补充条款

版本：`v2.1-preparation`
日期：2026-08-25
状态：V2 正式执行契约；G0 `PASS`，G1–G8 尚未通过，尚未生成 V2 实验结果

## 1. 文件关系与适用范围

本项目的 V2 设计由以下两份材料共同构成：

1. [`deep-research-report.md`](../deep-research-report.md)：定义科学问题、理论对象和总体方法；
2. [`重启项目的细节.md`](../重启项目的细节.md)：补全主方案中有意保留的开放假设，并给出第一版可执行参数。

两份文件是“主方案 + 补充细节”的关系，不是相互竞争的方案。本文件只负责把它们转换为唯一、可验证的执行语义，不改变其科学目标。若主方案给出多个候选选择，而补充文件已经冻结第一版选择，则执行时采用补充文件的选择；仍未被两份材料合理冻结的事项必须通过本文列出的 `TBD gate` 后才能运行相应实验。

本版权威输入的 SHA256 为：

| 文件 | SHA256 |
|---|---|
| `deep-research-report.md` | `b7a66a480c93ed11e03f5467b5c20467933c8ce7f2551febf17a6553b81fcc2f` |
| `deep-research-report.pdf` | `96244c26cdb27ffed30d42fc244d0e1f888ed2671973921eeda233006f1e5b03` |
| `重启项目的细节.md` | `250af87c1c21f8bac04ab61dbd39bdd72c4e31f7aab47634a501c0d0e86c9880` |

### 1.1 项目级方法排除条款

自 `v2.1-preparation` 起，V2 明确不考虑 Conditional Flow。该决定覆盖 pilot、main study、randomized intervention 和 external evaluation 的全部阶段：不得设计、实现、训练、调参、比较或报告 Conditional Flow、Conditional Normalizing Flow、Normalizing Flow、Flow Matching，以及其他 flow-based density/trajectory models；也不得把它们列为 baseline、ablation、备选模型、negative result 或 gate 后扩展。

三份 G0 来源材料保持原始 checksum，不因本条款回写。其中关于 flow 方法的候选讨论只属于方案形成过程的 provenance，不构成 V2 执行授权。任何重新纳入都必须由用户明确改变项目范围并建立新的 major-version protocol；普通 V2 amendment 或 `G1–G8` 均无权重新打开这一方法族。

旧 Gate A/B/C、Qwen/OLMo 结果只作为 historical exploratory evidence，用于解释为什么重启；不得进入 V2 模型选择、阈值校准或 confirmatory test。

## 2. V2 的科学对象

V2 不再把“activation 移动”直接解释为人格失稳，而是估计：

\[
\text{Raw Persona State}
\rightarrow
\text{Expected Stable Pressure Response}
\rightarrow
\text{Residual Trajectory}
\rightarrow
\text{Stability Region}
\rightarrow
\text{Margin}
\rightarrow
\text{Future Drift Risk}
\rightarrow
\text{Robust Radius}.
\]

核心识别条件是：在相同 model、persona、pressure family 和 absolute pressure schedule 下，新的数据必须同时包含 Stable 与 Drift trajectories，而且这种 overlap 不能只由少数 topic 造成。若 dose-finding pilot 无法在 topic-stratified matched cells 中建立 positivity/overlap，则该条件不得被包装成稳定性预测任务；应停止该 cell、扩大预先允许的压力模板范围，或通过正式 protocol amendment 改变研究范围。

## 3. 时序与防泄漏解释

### 3.1 Main turn

一个 main turn 严格定义为一条正式 user message 加一条 assistant response。system/persona 初始化和实验说明被完整记录，但不计入 25 个 main turns。

第 \(t\) 轮生成前的 prompt 为：

\[
X_t=[\text{system persona},\text{history}_{<t},U_t].
\]

### 3.2 两套时间索引与两个 estimands

V2 明确区分两个不能互换的时钟：

1. **Observational pre-response clock \(t^-\)**：已经收到 \(U_t\)，尚未生成 \(A_t\)。可用信息集为

   \[
   \mathcal F_t^-=\{\text{system/persona},U_{1:t},A_{1:t-1},L_{1:t},z_{1:t}\}.
   \]

   \(z_t\) 在此时可用。Primary early-warning target 是 onset 是否落在 \(\{t,t+1,\ldots,t+H-1\}\)。当前回答 \(A_t\)、其 judge score 和任何 response-token statistic 均不可用。

2. **Intervention post-response clock \(t^+\)**：\(A_t\) 已完成，行为信息已更新。Fork prefix 为

   \[
   \mathcal F_t^+=\mathcal F_t^-\cup\{A_t,\text{behavior observations through }t\}.
   \]

   Randomized continuation 的 future window 是 \(\{t+1,t+2,\ldots,t+H\}\)。

Observational risk 与 fork risk 是不同 estimands，必须分别记为 \(R_{t^-}^{obs,(H)}\) 与 \(R_{t^+}^{fork,(H)}(d)\)。任何 schema、figure、analysis API 都不得用无时钟标记的 \(R_t^{(H)}\) 混写二者。

### 3.3 Primary activation

V2 early-warning 的 primary activation 是 observational \(t^-\) 时，\(X_t\) 的 final prompt token 上的内部状态。每层至少保存：

\[
r^{pre}_{t,\ell},\qquad a^{out}_{t,\ell},\qquad m^{out}_{t,\ell}.
\]

统一组件语义如下：

- `resid_pre`：进入该 Transformer block 前的 residual-stream 向量；
- `attn_out`：attention output projection 之后、写回 residual stream 之前的向量；
- `mlp_out`：MLP/FFN output projection 之后、写回 residual stream 之前的向量；
- `resid_post`：可选审计量，不替代上述三路 primary vectors。

所有量都在 final prompt token 位置读取，并保存 model、revision、layer、component、turn、token index、dtype 和 hook-contract version。

### 3.4 Response-token mean 的地位

主方案用 response-token-mean residual activation 说明已有 representation evidence；补充文件进一步冻结了新的 pre-response primary 时点。统一执行解释为：

- final-prompt-token pre-response state 是 V2 prospective predictor 的唯一 primary 时点；
- response-token-mean 是生成后的 secondary representation-validation / mechanistic analysis；
- response-token-mean、当前回答文本、当前回答 judge score，不得进入“生成当前回答之前”的预测特征；
- 所有特征必须带 `available_at_turn`，评估代码必须拒绝时间晚于预测 cut-off 的字段。

因此，V2 不否定旧的 response-token-mean 表示结果，但不会用 post-response 信息支持 early-warning claim。

## 4. Pressure、PPU 与 schedule 的唯一语义

### 4.1 删除 \(\lambda\)

V2 第一版不使用连续压力倍率 \(\lambda\)。代码、配置、数据 schema 和图表不得把 \(\lambda\) 当作科学变量。若未来为了展示定义 \(L_t/5\)，它只能被标记为无新增科学意义的 descriptive rescaling，且必须另行 amendment。

### 4.2 Family、level 和 exposure

- `pressure_family`：压力机制；不同 family 不能靠数值 level 直接互换。
- \(L_t\in\{0,1,2,3,4,5\}\)：第 \(t\) 轮在已校准 family 内的 ordinal pressure level。
- `1 PPU`：同一 family 中相邻 level 的一次增加，例如 \(L_2\to L_3\)。
- \(D_{1:T}=\sum_{t=1}^{T}L_t\)：累计 exposure，单位为 PPU-turns。

PPU 是经过 outcome-blind prompt calibration 的 ordinal protocol unit。除非独立校准另有证据，不把相邻 PPU 解释成等距的心理或物理压力。因此 V2 的 Robust Radius 是“跨越的最少校准等级数”，不是连续空间中的自然距离。

### 4.3 Canonical schedule 与边界

Pilot 不在运行时对 schedule 做数值平移或 clipping。五个候选 schedule 是在配置和 manifest 中逐一冻结的 absolute 25-turn block schedules：

\[
S_{-2}=[0^5,0^5,0^5,1^5,2^5],
\]

\[
S_{-1}=[0^5,0^5,1^5,2^5,3^5],
\]

\[
S_0=[0^5,1^5,2^5,3^5,4^5],
\]

\[
S_{+1}=[0^5,2^5,3^5,4^5,5^5],
\]

\[
S_{+2}=[0^5,3^5,4^5,5^5,5^5].
\]

`S*−1, S*, S*+1` 指候选 grid 中 \(k^*-1,k^*,k^*+1\) 三个 schedule，而不是把未知 schedule 的每轮数值事后随意加减。只有同时存在左右相邻 schedule 的 \(S^*\) 才可进入 main study；若 transition schedule 落在 grid 边界，必须扩展经过 calibration 的模板或停止该 cell，不能静默复制边界 arm。

原始 absolute \(L_{1:25}\)、offset index、每轮模板 ID 和累计 PPU-turns必须同时保存。

代码必须读取这五个显式序列并验证所有 levels 位于 L0–L5；任何其他动态 shift 一旦越界立即失败。上面的 `−2…+2` 只是固定 schedule ID，不授权运行时生成新序列。

### 4.4 Randomized fork 的上界规则

外部干预从 post-response \(t^+\) prefix 分叉，prefix 必须包含已经完成的 \(A_t\)。使用 \(d\in\{0,1,2,3\}\)，并把未来 \(H=5\) 每一轮的 planned level 增加 \(d\) 个相邻 calibration levels。为保持 `d=3` 的定义，primary intervention 不允许 silent clipping：

\[
\max_{k=t+1}^{t+5}L_k+d\le 5.
\]

因此 primary intervention prefix 只有在 baseline future plan 的最高 level 不超过 2 时才对四个 arms 全部 eligible。Turn 10 和 Turn 15 均执行相同规则。若某 model × persona × fork-turn 无法取得预注册数量的 eligible prefixes，则 intervention 阶段暂停并触发 `G7`，不得把被截断的 `d=3` 继续称为每轮 `+3 PPU`。任何饱和/截断版本只能作为明确标注的次级 estimand，并需新的 amendment。

`600 root prefixes / 9,600 fork continuations / 约 300,000 total target-model turns` 是 **main study 保持 8 seeds 且 G7 eligibility 全部满足时的 base-plan targets**，不是无条件保证的 realized sample size。若任一 model × persona × fork-turn stratum 出现 eligible-prefix shortfall，必须停止、记录 shortfall 并提交 amendment；禁止跨 stratum 借用 prefix、复制 prefix、改 fork turn、降低 dose 或用 clipping 补足名额。若 G6 将 main seeds 扩为 10，总 turns 必须重新计算，不再称为 300,000。

## 5. 表示、Region、Margin 与风险

V2 保存所有层三路 vectors，但不在 untouched test 上挑 layer。Persona vector 的提取 corpus、formula 和 held-out validation 通过 `G2` 冻结后，才构造 pre-response state \(z_t\)。第一版模型为低容量、可解释的 conditional expected-response model：

\[
\hat z_t^S=g_\theta(z_{1:t-1},u_{1:t},c),
\qquad
e_t=z_t-\hat z_t^S,
\]

其中 \(g_\theta\) 只用 development split 中最终 Stable 的 training trajectories 拟合。此处“stable-only”是 outcome-supervised reference construction，论文必须如实表述，不能称作 outcome-blind representation learning。

第一版窗口 \(w\) 只允许从预注册候选 \(\{3,5\}\) 中在 development topics 上选择。使用 shrinkage covariance 的动态 Mahalanobis score：

\[
A_t^{dyn}=E_{t,w}^{\top}\Sigma^{-1}E_{t,w}
+\beta_v\sum\|\Delta e\|_2^2
+\beta_a\sum\|\Delta^2e\|_2^2.
\]

Calibration topics 不再调整模型。Primary calibration 先对每条 stable calibration trajectory \(i\) 计算整个 eligible monitoring period 的 maximum score：

\[
B_i^{max}=\max_{t\in\mathcal T_i^{eligible}}A_{i,t}^{dyn},
\qquad
q_{1-\alpha}^{max}=Q_{1-\alpha}(B_i^{max}).
\]

Primary Region 与几何 Margin 为：

\[
\mathcal R_{\alpha,t}(c)=\{E_{t,w}:A_t^{dyn}\le q_{1-\alpha}^{max}(c)\},
\qquad
M_t^{geo}=q_{1-\alpha}^{max}(c)-A_t^{dyn}.
\]

这使 \(\alpha\) 对应 stable trajectory 在监控期内发生任意一次 alarm 的控制目标，而不是把相关 turns 当作独立检验。Per-turn thresholds 只能作为 secondary analysis。具体 \(\alpha\)、finite-sample/sequential calibration、conditioning/pooling 和 eligible monitoring period 在 `G6` 冻结。

若最终实现改用开方后的范数，则阈值和 Margin 必须在同一尺度上；不能把平方 Mahalanobis score 与范数半径相减。

discrete-time hazard 处理 25 turns 内的首次 Sustained Drift 和 right censoring。观察性 early-warning 的 primary horizon 为 \(H=5\)，\(H\in\{3,10\}\) 作为预注册 sensitivity analyses；随机干预只使用补充文件冻结的 \(H=5\)。

在 observational \(t^-\) 时，只能条件于当前 \(\mathcal F_t^-\) 和生成前已冻结的 future pressure plan \(u_{t:t+H-1}^{plan}\)。定义 prefix-conditioned multi-step hazard：

\[
q_{t,j\mid t^-}
=P(T_{drift}=j\mid T_{drift}\ge j,\mathcal F_t^-,u_{t:t+H-1}^{plan}),
\quad j=t,\ldots,t+H-1.
\]

其中 \(t^-\) 之后的未知 future states 已被积分掉，不得在特征或条件中使用未来 \(\mathcal F_j\)。于是：

\[
R_{t^-}^{obs,(H)}
=1-\prod_{j=t}^{t+H-1}(1-q_{t,j\mid t^-}),
\qquad
M_{t^-}^{risk}=\operatorname{logit}(\eta)-\operatorname{logit}(R_{t^-}^{obs,(H)}).
\]

`G6` 也可冻结直接估计同一 \(R_{t^-}^{obs,(H)}\) 的 direct-H model，但不能用 realized future latent states 计算所谓 prospective risk。

Robust Radius 的 primary operational threshold 为 \(\eta=0.8\)，并报告 \(0.7,0.9\) sensitivity：

\[
R_{t^+}^{fork,(5)}(d)
=P(T_{drift}\in\{t+1,\ldots,t+5\}\mid T_{drift}>t,do(d),\mathcal F_t^+),
\]

\[
\rho_{t^+}^{causal}=\min\{d\in\{0,1,2,3\}:R_{t^+}^{fork,(5)}(d)\ge\eta\}.
\]

若没有任何 arm 达到阈值，则 \(\rho_{t^+}^{causal}>3\)（right-censored），不得记为 3 或缺失。

一条 trajectory 到 Turn 25 仍未发生 Drift 时，行为学描述为 `Stable-through-end`，但 survival analysis 中只表示在 Turn 25 administratively right-censored；它不证明 Turn 25 以后永远 Stable。Observational horizon 跨过 Turn 25 时是排除、截短还是改为 horizon-specific censoring estimand，由 `G6` 在分析前唯一冻结。

每个 prefix × dose 只有 4 个 continuation seeds，不能把未经建模的经验比例解释为精确的 prefix-specific 0.8 风险。`G7` 必须在揭示 intervention outcomes 前冻结层级/单调 dose-response estimator、pooling level、cluster-aware uncertainty 和 primary causal estimand。在此之前，单 prefix Radius 只可视为待验证的 exploratory output。

## 6. 数据切分和确认性边界

30 个 main topics 以 topic 为单位预先拆分：

- 15 Development topics；
- 5 Calibration topics；
- 10 Untouched Test topics。

6 个 dose-finding pilot topics是 15 个 Development topics 中预先标记的子集；它们不进入 calibration 或 untouched test。Pilot outcome 只用于选择 transition schedule、工程 sanity checks 和 power simulation，不构成 confirmatory evidence。

所有 seeds、topic IDs、prompt-template IDs、model revisions 和 split manifest 在生成前冻结。Topic ID 继续作为 split、provenance 和 cluster unit，但 predictor 不得使用 untouched topic 的 categorical ID。若 conditional model 需要 topic information，只能使用在 outcomes 产生前冻结、与 Drift labels 无关的 topic features/embedding；其 extractor/revision 在 `G1/G6` 冻结。共享同一个 topic、root trajectory 或 fork prefix 的观测不是独立样本；统计推断必须按 topic/trajectory/root prefix 的实际层级进行 cluster-aware bootstrap 或相应层级模型，不得把 turns 当作 iid 样本。

约 5% 的 full-attention mechanistic audit subset 必须在 outcome 产生前通过固定 seed、按 model × persona × schedule × topic split 分层抽样；不得按异常程度或结果事后挑选。exact fraction、rounding rule 和 storage cap 在 `G3` 冻结。

## 7. 尚需通过的启动闸门

以下项目不是缺省值，未通过时不得运行对应阶段：

| Gate | 必须冻结的内容 | 通过后允许做什么 |
|---|---|---|
| `G0` Provenance — **PASS** | 三份设计源文件 checksum、pre-restart Git tag、read-only artifact archive manifest verification | 清理 active tree |
| `G1` Public items | public-data license/terms、四个 persona source IDs、30 topic IDs、6 pilot-topic IDs、转换模板、15/5/10 split、outcome-blind topic feature contract | 构建静态数据 |
| `G2` Measurement | persona system-prompt 构造、persona-vector extraction/validation、behavior-only Sustained Drift rubric、onset/sustained rule、judge panel 与盲法 | 生成可判定 pilot |
| `G3` Instrumentation | 三模型 license/access、精确 revisions、chat templates、non-thinking 设置、hook contract、10-trajectory smoke、数值回放和存储测量 | 批量采集 activation |
| `G4` Pressure calibration | 每个 persona × family 的 L0–L5 模板、独立 rater 方案、ordinal/Rasch 接受标准、失败重写规则 | 运行 dose-finding pilot |
| `G5` Pilot decision | aggregate transition band + topic-stratified within-cell positivity/overlap、S* 选择/停止规则、drift-rate 与 cluster variance、资源基准 | 冻结 main cells |
| `G6` Analysis lock | two-clock estimands、primary endpoint、trajectory-max \(\alpha\)/sequential method、Turn-25 horizon rule、warning/false-alarm budget、最小有意义增益、text baseline、power simulation、8→10 seeds 规则、多重比较、non-Flow extension allowlist | 运行 main confirmatory generation |
| `G7` Intervention lock | prefix sampling/eligibility、fork randomization、dose-response estimator、saturation禁令、primary causal estimand、600-prefix shortfall rule | 运行 randomized forks |
| `G8` External evaluation | PersonaGym 20 persona IDs、mapping、样本量和一次性打开规则 | 外部泛化 |

## 8. 变更纪律

- 任一 gate 通过后，其 manifest 和 checksum 必须提交 Git；后续修改使用新的 amendment，不覆盖原记录。
- Untouched Test 在 `G6` 之后才可读取 outcome；一次性分析后原样报告，不因结果改变方法。
- V2 的“准备完成”不等于“有实验结果”。任何 README、摘要或论文草稿都必须把 planned、running、completed 和 confirmed 严格区分。
- GP、HMM、trajectory encoder 或 activation patching 只有在 Mahalanobis/hazard baseline 按冻结标准完成后，才可进入 `G6` 的 non-Flow 预注册扩展清单。Conditional/Normalizing Flow、Flow Matching 及其他 flow-based density/trajectory models 已由第 1.1 节在整个 V2 中排除，不属于任何 gate 的候选。
