# Topic 设计讨论整理

> 起始位置：从助手回复“我建议优化一下 Topic 设计，但不是因为 MMLU-Pro 有 14 类就机械地必须全用……”开始。  
> 说明：仅整理用户与助手的可见对话内容，不包含系统消息、开发者消息、工具调用或内部推理。

---

## Assistant

我建议**优化一下 Topic 设计，但不是因为 MMLU-Pro 有 14 类就机械地必须全用**。现在 Persona 设计已经从 4 个孤立 Persona 往“Behavioral Family → Persona Trait → Prompt Variant”升级了，Topic 这一侧也最好变得更规范，否则以后 reviewer 很容易问“为什么偏偏只选这 12 类”。

我目前更推荐一个很清楚的版本：

\[
\boxed{
28\text{ MMLU-Pro anchors}
+
6\text{ Anthropic opinion anchors}
=
34\text{ Topics}
}
\]

其中：

\[
\boxed{
14\text{ MMLU-Pro categories}\times2
=
28
}
\]

再加：

\[
\boxed{
2\text{ Philosophy}
+
2\text{ NLP}
+
2\text{ Politics}
=
6
}
\]

这样有一个很明显的优点：**不用解释“14 个类别为什么删掉 2 个”**。

### 为什么我现在更倾向 34，而不是原来的 30？

原方案：

\[
12\times2+6=30
\]

本身没什么错误。

但 reviewer 可能自然追问：

> MMLU-Pro 有 14 个类别，你们为什么只选 12 个？  
> 被排除的两个类别是不是因为表现不好？  
> 是在实验前排除，还是看过结果以后排除？

当然这些都可以通过预注册回答，但既然：

\[
30\rightarrow34
\]

只增加 4 个 Topic，计算量增加大约：

\[
\frac{34-30}{30}\approx13.3\%
\]

我觉得没必要为了省这 4 个 Topic 增加解释成本。

因此如果每个类别都能找到合适的题，我更喜欢：

> **MMLU-Pro 14 个官方类别全部覆盖，每类固定选 2 个。**

### 但有一个非常重要的前提

不能为了“14 类全覆盖”硬塞不适合 Persona Drift 的题。

比如 MMLU-Pro 中假设有这种纯计算题：

> 求某积分的值。

它虽然是一个合法 Math item，但是对于：

- risk-averse
- risk-seeking
- agreeableness

这些 Persona 来说，很难自然表现人格。

一个风险规避模型和风险偏好模型面对：

\[
\int x^2dx
\]

理论上都应该算出同一个答案。

你如果硬设计 pressure：

> “请更冒险地算这个积分。”

就很奇怪。

所以应该先制定一个 **Topic Suitability Screen（主题适配筛选标准）**。

每个候选 MMLU-Pro item 在不知道 Drift 结果之前，先判断：

1. 能不能自然扩展成 25-turn conversation；
2. 是否允许 Persona trait 产生行为表达；
3. 是否可以自然施加反 Persona pressure；
4. 是否不会把 Persona Drift 和“答错知识题”混为一谈；
5. 是否不存在明显 safety/policy confound；
6. 是否能够在 25 轮中保持同一个核心主题，而不是为了凑轮数不断胡乱添加内容。

只有满足这些标准的 item 才进入候选池。

### 所以不是“每个 category 随机抽两道题”

而是：

```text
MMLU-Pro 某 Category
        │
        ↓
所有候选 items
        │
        ↓
Topic suitability screen
        │
        ├── 不适合 → 排除
        │
        └── 适合
              │
              ↓
       按预先规定规则选择 2 个
```

例如 Economics 里可能有 500 道题。

我们不是先跑模型看哪两道 Drift 最漂亮，而是在**完全不知道 Drift outcome 的情况下**，按照场景适配标准选出两道。

这才不会形成 cherry-picking（挑结果）。

### 为什么还要保留 6 个 Anthropic opinion topics？

即使 MMLU-Pro 全部 14 类都覆盖，我仍然建议保留这 6 个。

因为它们不是为了“再增加三个领域”。

它们提供的是**不同类型的实验场景**。

MMLU-Pro：

\[
\boxed{\text{task / reasoning anchor}}
\]

典型形式：

> 有一个相对客观的问题，模型先形成判断，然后我们开始施压。

Anthropic Sycophancy：

\[
\boxed{\text{opinion / social-influence anchor}}
\]

典型形式：

> 用户本身已经明确表达立场，再看模型会不会迎合。

所以 6 个 Anthropic topics 是在增加：

\[
\boxed{\text{interaction-type diversity}}
\]

而不只是：

\[
\text{domain diversity}
\]

这个区别非常重要。

### 那 34 个怎么 split？

如果改成 34，我建议：

\[
\boxed{
16\text{ Development}
+
6\text{ Calibration}
+
12\text{ Untouched Test}
=
34
}
\]

其中：

\[
\boxed{
6\text{ Pilot Topics}
\subset
16\text{ Development}
}
\]

结构就是：

```text
34 Topics
│
├── Development: 16
│   ├── Pilot: 6
│   └── Main Development: 10
│
├── Calibration: 6
│
└── Untouched Test: 12
```

我比较喜欢把 untouched test 从原来的 10 增加到 12，因为最终论文最重要的是：

> 方法在完全没参与开发的新 Topic 上还能不能工作。

### 但 split 不能简单随机

还应该做 **stratified topic split（分层划分）**。

因为假如不控制，可能出现：

```text
Development：
几乎全是 MMLU-Pro

Test：
大量 Anthropic Opinion
```

那么 Test performance 下降时，你不知道是：

> 新 Topic 导致的，

还是：

> task type 完全变了导致的。

所以三个 split 最好都保持：

- MMLU-Pro anchors；
- Anthropic opinion anchors；

都有代表。

例如 6 个 Anthropic：

- Development：3
- Calibration：1
- Test：2

或者类似的预注册比例。

MMLU-Pro 的 category 也尽量分散。

### 还有一个比“30 还是 34”更重要的问题

现在你的 Persona 结构可能最终发展成：

\[
4\text{ Families}
\times6\text{ Traits}
=
24\text{ Persona traits}
\]

如果这样，**Topic 没必要也无限扩张**。

因为实验规模是乘法：

\[
\text{Persona}
\times
\text{Prompt}
\times
\text{Topic}
\times
\text{Seed}
\times
\text{Model}
\times
\text{Pressure}.
\]

所以我不会建议：

> Persona 已经 24 个了，Topic 再上 80 个。

那没有必要。

我现在认为比较好的平衡点反而就是：

\[
\boxed{24\text{ Persona traits}}
\]

配：

\[
\boxed{34\text{ Topics}}
\]

配：

\[
\boxed{3\text{ Models}}
\]

然后把重点放到**层级化泛化设计**上，而不是纯粹堆数量。

### 所以如果现在让我替你定，我会这样改

原来：

\[
24\text{ MMLU-Pro from 12 categories}
+
6\text{ Opinion}
=
30
\]

我会改成：

\[
\boxed{
28\text{ MMLU-Pro from all 14 categories}
+
6\text{ Anthropic opinion}
=
34
}
\]

但加一个前提：

> **每个 MMLU-Pro category 都必须能找到至少两个通过预注册 Topic Suitability Screen 的 items。**

如果某一个 category，例如纯 Math，确实找不到适合自然扩展成 Persona-sensitive 25-turn scenario 的题，那么**不要为了“14 类齐全”硬塞进去**。这时候宁愿事先按筛选规则把该 category 标记为 unsuitable，并透明报告。

---

## User

你觉得现在topic就选择之前的方案，还是需要再优化一下呢，因为你说有14类

---

## Assistant

我现在反而有一个和刚才**不完全一样**的想法，而且我觉得比我前面说的 "34 个 Topic（14×2+6）" 更合理。

我的结论是：

> **Topic 不应该围绕 MMLU-Pro 的 category 来设计，而应该围绕"Scenario Type（场景类型）"来设计。**

我解释一下为什么。

### 为什么我改变了一点想法？

前面我们已经把 Persona 升级成了：

```text
Behavioral Family
        ↓
Persona Trait
        ↓
Prompt Variant
```

那么 Topic 如果还是：

```text
Biology
Business
Chemistry
Physics
...
```

其实两个层级不匹配。

因为：

**Persona 决定的是行为。**

而：

**MMLU-Pro category 决定的是知识领域。**

真正影响 Persona 是否能够表达的，不是：

> 这是 Biology 还是 Law。

而是：

> **这个场景是否允许 Persona 发挥。**

### 举个最简单的例子

例如：

#### Topic A

MMLU-Pro

```text
Physics

Which equation is correct?
```

这是 Physics。

但是：

```text
risk-averse
```

怎么体现？

几乎体现不了。

因为：

> 正确答案就是正确答案。

风险偏好和风险规避都应该答一样。

#### Topic B

MMLU-Pro

```text
Economics

Should a company choose Strategy A or B
under uncertain market conditions?
```

同样来自 MMLU-Pro。

但是：

```text
risk-averse
```

天然就可以表达。

因为：

> A 风险低。

> B 风险高。

所以：

两个都是：

```text
MMLU-Pro
```

但是：

第二个远比第一个适合作为 Persona 实验。

所以：

\[
\boxed{
\text{Scenario suitability}
>
\text{Category coverage}
}
\]

### 所以14类不是最重要的

我现在觉得：

**14 categories 应该只是 Candidate Pool（候选池）。**

例如：

```text
14 Categories

↓

所有题目

↓

Scenario Suitability Screen

↓

最终 Topic
```

而不是：

```text
14 Categories

↓

每类固定2个
```

因为：

有的类别可能找到：

20 个特别好的 Topic。

有的类别：

一个都找不到。

例如：

```text
Math
```

很多题都是：

```text
算数。

证明。

积分。
```

很难做：

```text
agreeableness

risk preference
```

但是：

```text
Business
Economics
Law
Health
Psychology
```

天然适合。

### 那我现在会怎么设计？

其实我现在更喜欢：

#### 第一层：

不是：

```text
MMLU Categories
```

而是：

```text
Scenario Types
```

例如：

```text
Evidence-based reasoning

Decision under uncertainty

Multi-stakeholder trade-off

Opinion

Negotiation

Planning
```

你会发现：

这些：

才真正对应：

Persona。

例如：

```text
Risk Preference
```

最适合：

```text
Decision under uncertainty
```

例如：

```text
Should we invest?

Should we take treatment A or B?

Should we evacuate?
```

而不是：

```text
Which molecule has valence 4?
```

```text
Stands-its-ground
```

最适合：

```text
Evidence

Opinion

Social pressure
```

例如：

```text
Everybody disagrees.

Experts disagree.

User insists.
```

```text
Agreeableness
```

更适合：

```text
Negotiation

Conflict

Team discussion
```

而不是：

```text
Math
```

所以：

我觉得：

Topic 其实也应该升级成：

```text
Scenario Family

↓

Topic
```

而不是：

```text
Category

↓

Topic
```

### 所以我的最终建议变成了

我不会再建议：

```text
14 categories ×2
```

了。

我会建议：

#### Step 1

MMLU-Pro

14 categories

只是：

```text
Candidate Pool
```

#### Step 2

建立：

```text
Topic Suitability Screen
```

例如：

每道题打分：

##### A

能不能扩展成：

25 turns？

##### B

能不能自然施加：

Pressure？

##### C

能不能体现：

Persona？

##### D

有没有：

Ground Truth？

##### E

是否存在：

Multi-turn discussion potential？

只有：

```text
ABCDE

全部通过
```

才进入：

Candidate。

#### Step 3

最后得到：

例如：

```text
36 Topics
```

但是：

不是：

```text
14×2
```

而是：

```text
12 Shared Core Topics
```

所有 Persona 都跑。

例如：

```text
6 Evidence-based

6 Opinion
```

再加：

```text
24 Family-specific Topics
```

例如：

每个 Behavioral Family：

```text
6 Topics
```

```text
Risk Family

↓

6 Decision-under-uncertainty Topics
```

```text
Agreeableness

↓

6 Negotiation Topics
```

```text
Stands-its-ground

↓

6 Evidence / Opinion Topics
```

等等。

这样：

Topic 和 Persona 是配套的。

### 我觉得这是目前整个项目最大的优化点之一

老实说，我现在甚至觉得：

**相比于 "14 类还是 12 类"，这个问题已经不重要了。**

真正重要的是：

> **Topic 应该围绕 Behavioral Expression 来设计，而不是围绕学科分类来设计。**

因为 reviewer 最终不会关心：

> 你是不是覆盖了 14 个学科。

他真正关心的是：

> **你的实验是不是让 Persona 有机会表现出来。**

### 所以，如果现在让我拍板

我会**放弃**：

> **14 类全部覆盖**。

改成：

> **14 类全部作为候选池（Candidate Pool），最终通过预注册的 Topic Suitability Screen 选择能够自然支持 Persona 表达的 Topics。**

然后把 Topic 组织成：

```text
Scenario Family
        │
        ├── Shared Core Topics
        │
        └── Family-specific Topics
```

我认为，这比：

> **14×2=28，再加6=34**

更符合你整个项目已经升级后的实验哲学。

事实上，我觉得这和我们刚刚讨论出来的 **Behavioral Family → Persona Trait → Prompt Variant** 是完全一致的。现在数据集的两边都变成了**层级化设计**：

```text
Behavioral Side

Behavioral Family
        ↓
Persona Trait
        ↓
Prompt Variant
```

对应：

```text
Scenario Side

Scenario Family
        ↓
Topic
        ↓
Scenario Template
```

我认为这是目前整个项目最协调、也最容易向 reviewer 讲清楚的一套设计。

---

## User

那具体怎么实施，选择多少呢

---

## Assistant

我认真想了一下，我现在会**推翻我前面一半的建议**。

我之前最大的错误是还在围绕 **MMLU-Pro category** 思考。

其实，如果你的目标是：

> **研究 Persona Stability，而不是 Benchmark Coverage。**

那么 Topic 的设计原则应该是：

> **Scenario First，Category Second。**

也就是说：

\[
\boxed{
\text{Scenario Suitability}
>
\text{MMLU-Pro Category Coverage}
}
\]

### 我现在会怎么真正实施？

我建议分 **G1、G2、G3** 三步。

### G1：先确定 Persona

**不要先选 Topic。**

因为：

Topic 是为 Persona 服务的。

不是反过来。

例如最终 Persona Family 假设是：

```text
Risk Preference

Social Independence

Interpersonal Style

Decision Style
```

这四个。

那么：

每个 Family 都需要不同的：

```text
Pressure

Scenario

Conversation
```

所以：

**Persona 必须先冻结。**

否则 Topic 永远不知道怎么设计。

### G2：先设计 Scenario Family

这是我觉得目前整个项目最缺的一层。

不是：

```text
Biology

Math

Economics
```

而是：

```text
Scenario Family
```

例如：

#### Scenario Family 1

Decision under uncertainty

例如：

```text
是否投资？

是否采用治疗方案？

是否撤离？
```

天然对应：

```text
Risk Preference
```

#### Scenario Family 2

Evidence disagreement

例如：

```text
专家意见冲突

证据冲突

新的证据出现
```

天然对应：

```text
Stands-its-ground
```

#### Scenario Family 3

Social pressure

例如：

```text
大家都不同意你

我是专家

我是你导师

全网都认为……
```

仍然主要对应：

```text
Stands-its-ground
```

#### Scenario Family 4

Negotiation

例如：

```text
团队讨论

利益冲突

合作

妥协
```

天然对应：

```text
Agreeableness
```

#### Scenario Family 5

Preference conflict

例如：

```text
客户要求

老板要求

朋友要求
```

也是：

```text
Agreeableness
```

所以：

现在 Topic 就不是：

```text
Physics

Law

History
```

而是：

```text
Scenario Family

↓

Topic
```

### G3：最后才选 Public Anchor

这里才开始用：

```text
MMLU-Pro

Anthropic
```

但是：

它们只是：

```text
Candidate Pool
```

例如：

```text
所有 MMLU-Pro

↓

筛选

↓

有没有适合

Decision under uncertainty？

↓

有

↓

Candidate
```

而不是：

```text
Physics

↓

必须选两个。
```

### 我真正推荐的 Topic 数量

现在我会重新设计。

#### Shared Core

**12**

所有 Persona 都跑。

组成：

```text
6

Evidence-based

+

6

Opinion
```

其中：

```text
Evidence

主要来自：

MMLU-Pro
```

```text
Opinion

主要来自：

Anthropic
```

为什么只有：

```text
12
```

因为：

这是：

```text
Cross-family

Benchmark
```

所有 Persona 都必须跑。

不能太多。

#### Family-specific

每个 Family：

```text
6
```

例如：

```text
Risk

↓

6
```

```text
Independence

↓

6
```

```text
Agreeableness

↓

6
```

```text
Decision Style

↓

6
```

所以：

```text
24
```

于是：

```text
12

+

24

=

36
```

这就是我之前说：

```text
36 Topics
```

真正的来源。

不是：

```text
14×2+6
```

而是：

```text
Shared

+

Family-specific
```

### 每个 Family 的 6 怎么来？

我会这样设计。

例如：

```text
Risk Preference
```

不是：

6 个随机 Topic。

而是：

#### Subtype A

Medical decision

两个。

例如：

```text
治疗方案

疫苗

药物
```

#### Subtype B

Financial decision

两个。

例如：

```text
投资

保险
```

#### Subtype C

Engineering / Planning

两个。

例如：

```text
是否采用新方案

是否上线
```

所以：

```text
2

+

2

+

2

=

6
```

这比：

```text
随机6个
```

好多了。

对于：

```text
Stands-its-ground
```

例如：

```text
Authority pressure

×

2
```

```text
Consensus pressure

×

2
```

```text
Repeated persuasion

×

2
```

又是：

```text
6
```

### 那 MMLU-Pro 怎么选？

这里我觉得应该建立一个：

## Topic Suitability Screen

不是：

```text
Physics

一定要两个。
```

而是：

每一个 Candidate：

打分。

例如：

| 指标 | 分值 |
|------|------|
| 能否扩展25轮 | 0–2 |
| 是否允许Persona表达 | 0–2 |
| 是否容易施压 | 0–2 |
| 是否有Ground Truth或稳定立场 | 0–2 |
| 是否不会引入Safety Confound | 0–2 |

总分：

```text
10
```

例如：

```text
>=8
```

进入：

Candidate Pool。

否则：

淘汰。

所以：

14 Categories

↓

只是：

```text
Candidate Pool
```

不是：

Quota。

### Split 我也建议改

现在：

```text
18

6

12
```

我仍然保留。

但是：

变成：

```text
Shared

6

↓

Development
```

```text
Shared

2

↓

Calibration
```

```text
Shared

4

↓

Test
```

每个 Family：

```text
6 Topics
```

分：

```text
3

1

2
```

所以：

```text
Family

↓

Development

3
```

```text
Calibration

1
```

```text
Test

2
```

四个 Family：

```text
12

4

8
```

最终：

```text
18

6

12
```

### Pilot 怎么选？

我会改。

不是：

随机：

```text
6 Topics
```

而是：

```text
2 Shared

+

每个 Family

1 个
```

所以：

```text
2

+

4

=

6
```

这样：

Pilot 已经覆盖：

所有 Scenario Family。

非常漂亮。

### 这是我现在真正会拍板的版本

| 模块 | 最终建议 |
|------|----------|
| Persona | 4 Behavioral Families → 24 Persona Traits |
| Shared Core Topics | **12** |
| Family-specific Topics | **24（6/Family）** |
| 总 Topics | **36** |
| Topic 来源 | **14 个 MMLU-Pro category 全部作为 Candidate Pool，不做固定配额；Anthropic opinion 作为 Shared Core 的 opinion 部分** |
| Topic Selection | **Topic Suitability Screen，不按学科平均抽样** |
| Split | **18 / 6 / 12** |
| Pilot | **6（2 Shared + 每个 Family 1 个）** |

### 我为什么现在最认可这个版本？

因为它和我们刚刚确定的 **Persona 三层结构** 是完全对称的：

```text
Behavior Side

Behavioral Family
        ↓
Persona Trait
        ↓
Prompt Variant
```

对应：

```text
Scenario Side

Scenario Family
        ↓
Topic
        ↓
Scenario Template
```

两边都是**三层结构**。

整个项目一下子从：

> **"几个 Persona + 几个 Topic"**

升级成了：

> **"Behavior × Scenario 的层级化 Benchmark"**。

我认为，这是目前整个项目最值得保留、也最有机会成为论文亮点的实验设计。

---

## User

从下面这段话所在的位置开始的所有对话，整理成一个md格式文件返回给我：

我建议**优化一下 Topic 设计，但不是因为 MMLU-Pro 有 14 类就机械地必须全用**。现在 Persona 设计已经从 4 个孤立 Persona 往“Behavioral Family → Persona Trait → Prompt Variant”升级了，Topic 这一侧也最好变得更规范，否则以后 reviewer 很容易问“为什么偏偏只选这 12 类”。
