> 工程入口：实验运行与目录规范见
> [`docs/experiment_runbook.md`](docs/experiment_runbook.md)，冻结的试点设计见
> [`docs/research_spec.md`](docs/research_spec.md)。

> 当前状态（2026-08-18）：Gate B 与 scoped Gate A 已通过。预注册的 Gate C
> 新数据确认已完成，但完整解离判据失败（4/6 项通过）。冻结联合模型相对同前缀
> TF-IDF 的 AUPRC 增量为 -0.0120，trajectory-bootstrap 95% CI
> [-0.0369, 0.0160]，低于预设最小有用增量 0.05；同时独立轴压力下出现
> 16/60 输出漂移，而且逐 judge 结果对量表严重度敏感。因此当前不支持成功的
> latent early-warning detector，也不启动 intervention。随后完成的 anchored
> three-judge measurement v1 在 20 个独立 validation anchors 上通过全部 5 项
> 门槛，并将 Qwen 开发数据中的独立轴压力漂移重测为 2/60；该结果仅属于测量开发，
> 但已按冻结规则授权进入 untouched 跨模型复现。因 CETUS 无法访问 gated Llama
> 权重，且尚未生成任何跨模型结果，目标已按技术修订改为公开 ungated 的 OLMo-2-7B。
> OLMo 专用 persona vectors 已通过冻结重编码阶段。原始整轴生成作业
> `52719`--`52720` 在只检查吞吐量和记录数后，因预计超过四小时队列限制而停止；
> partial 文件与日志已归档且不进入分析。执行修订 v2 将同一冻结设计拆成 6 个
> axis-topic 分区；验证 `52822` 与六个生成作业 `52823`--`52828` 均成功，
> 共生成 240 条轨迹、6000 个主回合和 1440 个 probe。但合并作业 `52829`
> 按冻结规则拒绝继续：3104/7440（41.72%）回复触及 128-token 上限，超过 10%
> 门槛，且截断率随条件明显不均衡。三个 judge 与最终分析均未运行，因此该轮没有
> 合格的跨模型科学结论。现已冻结只读取 token-QC 的 256/384 长度试点，并提交
> 首次验证链 `53128`--`53135` 因 CPU 节点低占用挂起而在生成前取消；
> 替代验证 `53145` 已以 5 项新增测试和精确配置校验、exit 0 通过，GPU 分区
> `53146`--`53151` 与自动汇总 `53152` 已进入队列。试点使用独立种子
> 601--602，正式重跑预留 701--710。
> 执行修订见
> [`docs/cross_model_replication_olmo_v1_execution_amendment.md`](docs/cross_model_replication_olmo_v1_execution_amendment.md)
> 与
> [`docs/cross_model_replication_olmo_v1_submission_addendum.md`](docs/cross_model_replication_olmo_v1_submission_addendum.md)，
> judge GPU 修订见
> [`docs/cross_model_replication_olmo_v1_judge_gpu_addendum.md`](docs/cross_model_replication_olmo_v1_judge_gpu_addendum.md)。
> 长度试点见
> [`docs/olmo_generation_length_pilot_v1_preregistration.md`](docs/olmo_generation_length_pilot_v1_preregistration.md)。
> 确认结果见
> [`docs/gate_c_dissociation_confirmation_v1_results.md`](docs/gate_c_dissociation_confirmation_v1_results.md)，
> 测量结果见
> [`docs/persona_measurement_development_v1_results.md`](docs/persona_measurement_development_v1_results.md)，
> 后续论文与实验路线见
> [`docs/paper_strategy_after_dissociation_confirmation_v1.md`](docs/paper_strategy_after_dissociation_confirmation_v1.md)。

下面整理成一份**完整研究构想文档版本**。我保留了之前方案的核心思想，并结合刚刚阅读的 BILLY / Persona Vector 工作进行了调整，使逻辑更完整，适合作为 Notion 研究 proposal、和导师讨论的初稿。

---

# Latent Persona Seismograph

## 基于内部激活状态的 LLM Agent Persona Drift 早期预测与干预

---

# 1. 研究背景

随着大型语言模型（Large Language Models, LLMs）逐渐从单轮问答系统发展为能够长期运行、自主决策和多智能体协作的 agent，persona（人格/角色设定）成为构建可信 AI agent 的重要组成部分。

在实际应用中，LLM agent 通常会通过 system prompt 被赋予不同的 persona，例如：

* 一个谨慎、保守、重视安全的医疗助手；
* 一个独立、开放、鼓励探索的创新顾问；
* 一个具有特定价值观和行为模式的社会模拟 agent。

这些 persona 不仅影响模型的语言风格，也会影响：

* 决策偏好；
* 信息筛选方式；
* 与其他 agent 的互动模式；
* 长期任务执行行为。

然而，一个重要问题是：

> LLM agent 被赋予的 persona 是否能够在长期交互过程中保持稳定？

---

## 1.1 Persona Drift 问题

已有研究已经发现，在持续多轮 multi-agent interaction 中，LLM agent 的 persona 并不一定保持稳定。

例如，在已有 Persona Drift 研究中，作者利用 Schwartz value theory 和 PVQ-21 构建 persona，并在多个 dialogue checkpoint 测量 agent 的 measured value profile。

实验发现：

* group interaction 相比 dyadic interaction 会产生更明显的 value profile drift；
* agent 的 measured value profile 会随着持续交互发生变化；
* drift 会受到 interaction topology、topic、model scale 和 initial persona quadrant 的影响。

该研究定义的 persona drift 是：

> 在固定测量接口下，agent measured value profile 随时间发生变化。

而不是直接证明模型具有类似人类的真实 latent value。

当前研究证明了：

> persona drift 是一个真实存在且具有结构性的现象。

但是，它主要解决的是：

* drift 是否发生；
* drift 发生多少；
* 哪些因素导致 drift 更明显。

而没有解决：

> 能否在 persona 真正发生变化之前，提前预测它即将发生变化？

---

# 2. 研究动机

## 2.1 现有方法存在滞后性

目前检测 persona stability 的方法主要依赖：

### 方法 1：输出行为检测

例如：

* 判断回复是否符合 persona；
* 使用 LLM judge 评估 persona consistency；
* 判断是否出现 unsafe behavior。

问题：

这些方法只能观察到已经产生的行为变化。

即：

模型已经偏离 persona 后，才被发现。

---

### 方法 2：周期性心理测量

例如：

* PVQ-21；
* personality questionnaire；
* value probing。

这种方法可以更加结构化地测量 persona，但是存在两个问题：

第一：

成本较高。

如果每轮对话都执行完整问卷，会显著增加推理成本。

第二：

可能影响模型行为。

已有 Persona Drift 工作中特别强调：

PVQ probing 必须与 dialogue generation 分离，不能把 probing 结果加入后续 conversation history，否则测量过程本身可能影响 agent 状态。

因此：

> 问卷适合作为 offline evaluation，而不适合作为实时 monitoring mechanism。

---

# 2.2 核心假设

我们的核心假设：

> Persona drift 在输出行为变化之前，可能已经在模型内部 activation space 中出现。

也就是说：

当前：

[
\text{Latent Persona Change}
\rightarrow
\text{Behavior Change}
]

如果能够捕获 latent change：

那么：

[
t_{latent}<t_{behavior}
]

我们可以在 agent 输出异常之前进行预测和干预。

---

# 3. 相关启发：Persona Vector 与 Activation Steering

近期 activation engineering 工作表明：

模型内部 activation space 中存在能够表示 persona、trait 和 behavior 的方向。

例如 BILLY 工作提出：

> persona 可以表示为 activation space 中的方向 vector。

作者通过 contrastive activation 方法提取 persona vector：

[
v_P^{(l)}
=========

E(a^{+})-E(a^{-})
]

其中：

* (a^{+})：体现某 persona 的回答 activation；
* (a^{-})：普通回答 activation。

得到的 vector 表示：

> 模型从普通状态转向该 persona 时，activation 的变化方向。

随后，BILLY 将多个 persona vectors 融合：

[
v_{merged}
==========

\frac{1}{N}\sum_i v_i
]

并在 inference 时：

[
a_{steered}
===========

a_{original}
+
\alpha v_{merged}
]

直接修改 activation，使单个模型产生多 persona 行为。

这说明：

> Persona 不只是 prompt 中的文本描述，而可以在模型内部 representation space 中被定位、测量和控制。

因此，我们进一步提出：

如果 persona 可以被表示，那么 persona drift 也应该可以通过内部 representation 的变化提前发现。

---

# 4. 研究目标

本文希望解决三个问题：

---

## RQ1

### Persona drift 是否会在 activation space 中提前出现？

即：

模型输出仍然保持 persona consistency 时，

内部 activation 是否已经开始偏离？

---

## RQ2

### 能否利用 activation 预测未来 persona drift？

给定当前 turn 的内部状态：

预测：

未来 H 轮是否发生：

* value profile drift；
* quadrant transition；
* persona inconsistency；
* unsafe behavior。

---

## RQ3

### 提前发现后，是否可以阻止 persona degradation？

即：

是否可以通过 activation-level intervention：

在行为变化之前修正 agent 状态？

---

# 5. 方法框架

提出：

# Latent Persona Seismograph

整体框架：

```
Multi-agent Dialogue

        ↓

Pre-decoding Activation Extraction

        ↓

Persona Representation Learning

        ↓

Latent Persona Stability Measurement

        ↓

Future Drift Prediction

        ↓

Early Intervention
```

---

# 6. 方法一：Pre-decoding Activation Monitoring

## 核心思想

不观察模型已经生成的回复。

而是在生成回复之前读取模型内部状态。

对于第 t 轮：

提取：

[
h_t^{pre}
]

其中：

* t 表示当前 dialogue turn；
* h 表示模型 hidden state / residual stream。

重点分析：

* middle layers；
* residual stream；
* final prompt token activation；
* attention pattern。

原因：

输出可能仍然正常，但是内部状态可能已经发生偏移。

---

# 7. 方法二：学习 Persona Activation Space

直接分析 hidden state 会受到很多因素影响：

例如：

* topic；
* conversation history；
* instruction；
* wording。

因此需要学习 persona-specific representation。

---

## 7.1 Contrastive Persona Extraction

构造两类样本：

### Persona-aligned responses

例如：

```
You are a cautious medical advisor.
```

生成：

体现谨慎、安全倾向的回答。

得到：

[
D^+
]

---

### Neutral responses

普通 assistant：

[
D^-
]

---

然后计算：

[
v_p
===

## mean(h(D^+))

mean(h(D^-))
]

得到 persona vector。

例如：

* cautious vector；
* altruistic vector；
* independent vector；
* conservative vector。

---

# 8. 方法三：Latent Persona Stability Region

对于每个 persona：

构建稳定 activation region：

[
B_p
]

表示：

> 当 agent 保持该 persona 时，activation 通常所在区域。

例如：

```
          Other Persona Region


               |
               |
Persona Stable Region -------- Unsafe Region
```

---

然后计算：

当前状态：

[
z_t
]

距离：

[
B_p
]

的变化。

---

# 9. 方法四：Latent Persona Margin

定义：

[
m_t
===

## d(z_t,B_{other})

d(z_t,B_p)
]

含义：

如果：

[
m_t \uparrow
]

说明：

当前状态更加接近原 persona。

如果：

[
m_t \downarrow
]

说明：

正在靠近边界。

---

相比简单 distance：

这个方法更合理。

因为 persona degradation 不一定表现为：

“离开所有 cluster”。

它可能是：

从 persona A：

↓

逐渐进入 persona B。

例如：

谨慎医疗助手：

↓

逐渐变成：

效率优先、不考虑风险的助手。

两者都可能是正常 cluster。

---

# 10. 方法五：Latent Persona Robust Radius

进一步定义：

## Persona Stability Margin

[
\rho_t
]

表示：

当前状态距离 persona boundary 的距离。

直观理解：

不是问：

> 当前是否已经坏？

而是：

> 当前距离坏掉还有多远？

如果：

[
\rho_t
]

持续下降：

说明：

persona stability 正在降低。

即：

early-warning signal。

---

# 11. 方法六：Future Drift Prediction

训练 temporal prediction model：

[
P(Y_t^H=1|x_t)
]

预测：

未来 H 轮是否发生 drift。

输入：

包括：

* persona projection；
* persona margin；
* robust radius；
* radius decreasing speed；
* activation trajectory；
* social pressure feature。

标签：

来自 offline PVQ measurement。

已有 Persona Drift 工作已经定义：

* L2 drift；
* AUC-L2 drift；
* quadrant transition；

这些可以作为 drift label。

---

# 12. 方法七：Social Influence Modeling

Multi-agent 场景中：

persona drift 往往来自其他 agent 的影响。

已有研究发现：

1v3 和 4Q group interaction 比 2-agent interaction 更容易产生 drift。

因此加入：

social pressure signal。

定义：

[
p_t
===

\sum_j w_j(z_j-z_0)
]

表示其他 agent 对 target persona 的影响。

计算：

[
cos(\Delta z_t,p_t)
]

如果越来越接近：

说明：

agent 正在沿着群体方向变化。

---

# 13. Intervention

当风险较低：

不干预。

当风险升高：

进行：

## 轻量干预

* persona reminder；
* self-check；
* micro probing。

## 强干预

* activation steering；
* persona vector correction；
* context pruning；
* human review。

---

# 14. 实验设计

## Dataset

构建：

# PreDriftBench

基于已有 Persona Drift framework。

已有工作提供：

* persona construction；
* Schwartz value space；
* PVQ measurement；
* multi-agent topology；
* drift metrics。

扩展：

记录：

* 每轮 activation；
* 每轮 latent persona state；
* future drift label。

---

# 15. 实验问题

## Experiment 1

### Activation 是否早于 output drift？

比较：

* activation warning time；
* output drift time；
* PVQ drift time。

指标：

* lead time。

---

## Experiment 2

### Latent monitor 是否优于 output monitor？

Baseline：

* output embedding；
* LLM judge；
* PVQ periodic probing。

指标：

* AUROC；
* AUPRC；
* false alarm；
* detection delay。

---

## Experiment 3

### Early intervention 是否有效？

比较：

1. 无干预；
2. 定期 persona reinforcement；
3. drift 后干预；
4. latent warning 后干预。

评价：

* drift reduction；
* unsafe behavior reduction；
* intervention cost。

---

# 16. 主要贡献

## Contribution 1

提出新的问题：

> Pre-drift forecasting of LLM persona degradation。

从事后检测推进到提前预测。

---

## Contribution 2

提出 activation-based persona stability monitor。

利用：

* persona vector；
* latent margin；
* robust radius；

衡量 persona stability。

---

## Contribution 3

提出低成本 AI safety intervention framework。

不需要每轮 questionnaire。

只在 latent risk 升高时进行干预。

---

# 17. 与已有 Persona Drift 工作区别

已有工作：

回答：

> Persona drift 是否发生？

方法：

PVQ-21 measurement。

---

本文：

回答：

> Persona drift 发生之前，内部是否已经出现信号？

方法：

activation monitoring + forecasting + intervention。

两者关系：

第一篇：

证明问题存在。

第二篇：

解决如何提前防止问题。

---

# 一句话总结

**我们提出 Latent Persona Seismograph，通过分析 LLM 在生成回复前的内部 activation，学习 persona representation space，并利用 latent stability margin 和 robust radius，在输出行为变化之前预测 persona drift，从而实现低成本、提前的 persona safety monitoring 和 intervention。**
