# Latent Persona Seismograph

基于生成前内部激活轨迹，对 LLM Agent 的 Persona Drift 进行条件化早期预测，并通过随机压力干预估计 Persona Robust Radius。

> **当前状态：V2.3 准备阶段。** G0 旧版本可恢复归档已经完成，G1–G8 尚未通过；Persona 层级和 Scenario-first Topic 骨架已记录，但 exact family/trait/prompt/item/topic/scenario manifests 与新版样本量仍为 OPEN。任何 dose-finding pilot、main study 或 randomized intervention 均未运行，因此本仓库目前没有 V2.3 实验结果或确认性结论。

## 新方案

V2 不再把 Persona Vector projection 的变化直接解释成 Drift。外部 pressure 本来就会移动内部 activation；真正需要识别的是：

> 在相同 model、persona、topic、pressure family 和 pressure history 下，内部轨迹是否开始偏离“最终仍能保持 Persona 稳定”的正常压力响应轨迹。

研究链路为：

$$
\text{Raw Persona State}
\rightarrow
\text{Expected Stable Pressure Response}
\rightarrow
\text{Residual Trajectory}
\rightarrow
\text{Conditional Stability Region}
\rightarrow
\text{Persona Margin}
\rightarrow
\text{Future Drift Risk}
\rightarrow
\text{Causal Robust Radius}.
$$

其中：

- **Stability Region**：在给定 Persona 与压力历史后，Stable trajectories 的条件化接受域；
- **Persona Margin**：当前 residual trajectory 距离稳定边界的余量；
- **Persona Robust Radius**：从当前 prefix 出发，未来每轮至少再增加多少个经过校准的 pressure levels，才会使 5-turn Drift risk 达到操作性阈值。

V2 的核心识别要求是：

$$
\text{Same Persona + Same Topic + Same Pressure Family + Same Absolute Schedule}
\Rightarrow
\lbrace \text{Stable},\text{Drift} \rbrace.
$$

如果 outcome 仍由 Persona、topic 或 condition 几乎决定，就不能声称模型学到了“稳定性”。

## 权威设计文件

以下文件共同定义 V2；`重启项目的细节.md` 是主报告的补充，负责把主报告保留的开放项操作化：

- [deep-research-report.md](deep-research-report.md)：概念框架、识别问题和建模路线；
- [deep-research-report.pdf](deep-research-report.pdf)：主报告的 PDF 版本；
- [重启项目的细节.md](重启项目的细节.md)：公开数据、25-turn 采集、PPU、随机干预和样本量的执行细节；
- [Persona/Topic 讨论记录](persona和topic的讨论.md)：V2.2 层级化 Persona 方向的决策 provenance；
- [Topic 优化讨论记录](topic的优化.md)：V2.3 Scenario-first Topic 方向的决策 provenance；
- [V2 执行解释与补充条款](docs/restart_v2_amendment.md)：统一时序、符号、剂量边界和启动闸门；
- [V2.2 Persona–Topic 修订](docs/persona_topic_design_amendment_v2_2.md)：继续定义 Persona 层级、cold-start 和样本重算边界；其中旧 Topic 条款已被 V2.3 取代；
- [V2.3 Scenario-first Topic 修订](docs/topic_design_amendment_v2_3.md)：冻结 36-topic slot/split/pilot 骨架并列出仍待 G1 冻结的执行项；
- [V2 正式研究协议](docs/research_protocol_v2.md)：阶段、样本设计、分析与停止规则。

不得仅依据 README 修改科学定义；任何正式变更必须新增带版本的 amendment。

**项目范围决定（2026-08-25）：V2 不采用 Conditional Flow。** 本项目不设计、实现、调参、比较或报告 Conditional Flow、Conditional Normalizing Flow、Normalizing Flow、Flow Matching，以及其他 flow-based density/trajectory models；它们不属于 baseline、ablation、备选模型或后续 gate。来源材料中的相关候选讨论按 G0 checksum 原样保留，仅用于记录方案形成过程，不构成执行授权。任何重新纳入都必须由用户明确改变项目范围并建立新的 major-version protocol，不能通过 V2 的普通 amendment 或 `G1–G8` 重新打开。

主报告中保留的内部 cite 占位符属于来源原文的 provenance，本仓库不直接修改源文件。它们不是投稿可用的参考文献。论文投稿前必须通过单独的 **Bibliography Gate**：逐条将占位符映射到可核查的 primary source URL/DOI，完成引用核验；仍有未解析占位符时不得提交论文。

来源校验、旧版本恢复和持续记录见：

- [权威来源 SHA256](docs/source_materials.sha256)；
- [旧版本恢复说明](docs/legacy_recovery.md)；
- [实验账本](docs/experiment_ledger.md)。

## V2.3 固定与开放设计

| 项目 | V2 设计 |
|---|---|
| Models | Qwen3-8B、Llama-3.1-8B-Instruct、Gemma-3-12B-it |
| Persona unit | 独立的 `persona_trait`；prompt variants 和 evaluation items 不计为新 Persona |
| Persona sampling direction | 4 behavioral families × 每类 4–6 true traits（16–24）；exact inventory 仍为 G1 OPEN |
| Persona generalization | unseen wording、within-family unseen trait、one fully unseen family |
| Topic architecture | Scenario-first：12 shared core（6 evidence + 6 opinion）+ 24 family-specific（4 families × 6）= 36 |
| Topic sources | MMLU-Pro 14 categories 仅作无配额 candidate pool；Anthropic opinion 是 shared-opinion candidate pool |
| Topic split | 18/6/12；6 个 pilot assets（2 shared + 每 family 1）均作 outcome-free QA，G5 outcome pilot 仅用 5（2 shared + 3 Development-family specific） |
| Main trajectory | 25 main turns；前 5 turns 为 neutral baseline |
| Pressure | 每个 persona × family 独立校准的 L0–L5 ordinal scale |
| PPU | 同一 family 内相邻 pressure level 增加一级 |
| Primary activation | 每轮生成回答前的 final prompt token |
| Components | 所有 layers 的 `resid_pre`、`attn_out`、`mlp_out` |
| Full attention | 仅预先分层抽取的约 5% mechanistic subset |
| Primary warning horizon | $H=5$； $H\in\lbrace 3,10\rbrace$ 为 sensitivity analyses |
| Region baseline | Conditional expected response + dynamic shrinkage Mahalanobis tube |
| Risk model | Discrete-time hazard with right censoring |
| Excluded methods | Conditional/Normalizing Flow、Flow Matching 及其他 flow-based density/trajectory models（整个 V2 排除） |
| Intervention | Randomized prefix forks， $d\in\lbrace 0,1,2,3\rbrace$， $H=5$ |
| Robustness threshold | $\eta=0.8$； $\eta\in\lbrace 0.7,0.9\rbrace$ 为 sensitivity analyses |

连续压力倍率 $\lambda$ 不属于 V2 第一版。V2 使用每轮 $L_t$、PPU 和累计 PPU-turns，并保留完整 absolute schedule。

## 样本量状态

V2.1 的 Flat-4 设计及其 `1,440` pilot trajectories、`8,640` main trajectories、`9,600` forks 和约 `300,000` target-model turns 已全部退役，不能用于 V2.3 排队、预算或完成度汇报。

V2.1 曾把 pilot 4 seeds、main 8 seeds（并候选增加到 10）和 fork 每 arm 4 continuation seeds 用作规划值。这些现在与 Flat-4 总量一样只属于 **V2.1 candidate history**，不是 V2.3 的默认值。Pilot、main 和 fork 各自的 seed 数均为 OPEN，必须通过对应 gate 的 power/精度与资源证据独立冻结。

V2.3 不使用“trait 数 × 平均 variant 数”或按 `36/30` 线性外推的口头乘法。对每个 phase 的 signed assignment manifest，令 $X_{\phi}$ 为全部 non-seed design rows；每行必须显式列出 `persona_trait_id`、`persona_prompt_variant_id`、`topic_scope` 和 `topic_id`，并列出该 phase 适用的 model、schedule，或 root/fork-turn/dose。令 $s_{\phi}(x)$ 为该行待冻结的 generation/continuation seed 数，则：

$$
N_{\phi}=\sum_{x\in X_{\phi}}s_{\phi}(x),
\qquad
\phi\in\{\mathrm{pilot},\mathrm{main},\mathrm{fork}\}.
$$

Trait × variant 的 phase-specific 计数矩阵为 $A^{(\phi)}_{\tau v}=\lvert X_{\phi}(\tau,v)\rvert$。`X_{pilot}` 只允许 5 个 outcome-bearing logical topic assets，held-out-family specific pilot asset 不能作为第六个乘数。只有 seed 确实按行一致时，才可简化为 $N_{\phi}=s_{\phi}\sum_{\tau,v}A^{(\phi)}_{\tau v}$；否则必须使用逐行求和。这使 full crossing、balanced incomplete design 和 robustness-only variants 都能被完整计数，不得省略未交叉的 prompt-variant exposure。

在新版 sample-size manifest、runtime/storage benchmark 与 power rule提交前，任何批量 outcome-bearing GPU 作业都 fail closed。

## 统计层级与泛化边界

观测数据的嵌套主干是 `behavioral family → persona trait → prompt variant → trajectory → turn`。Shared topics 与 Persona families 交叉，支持 matched cross-family comparison；family-specific topics 只支持对应 family 内的比较，不能被当作跨 family matched topics。干预数据另有 `root trajectory/prefix → fork dose → continuation` 的依赖。Turns、seeds、variants 和 fork continuations 都不是 iid replicates。

- observational 主分析以 **topic** 为 outer cluster/resampling unit，在预注册的 topic_scope/source/scenario strata 内重抽整个 topic block，保留其内全部 Persona 层级、trajectories 和 turns；
- randomized fork 主分析以 **root prefix** 为 randomization/dependence unit，重抽时必须将同一 root 的所有 doses 和 continuations 绑定，并以 topic 作 outer block/层级效应；
- calibration 的 alarm control 使用 trajectory-level maximum，不使用 turn-level 伪重复扩大样本量。

因为规划中只有 4 个 families，family 作为预注册的 fixed claim strata，不用 4 个单位估计“所有可能 Persona families”的 random-effects population variance。一个 held-out family 只支持对该 family 的预注册 cold-start transfer claim，不支持无界的跨-family population generalization。

Family/trait/variant IDs 只能用于 provenance、split 和分层。在 unseen-trait 或 unseen-family 评价中，predictor 不得使用 categorical persona ID 或从该 ID 学得的 embedding；只允许使用 `G1/G2` 在 outcome 前冻结的 Persona descriptors/Persona Vector，或完全预注册、不读取 holdout outcomes 的 cold-start encoding。

## 数据切分

36 个 main topics 按 topic 而不是 individual trajectory 切分：

- 18 Development topics：6 shared + 每个 family 3 个 family-specific；
- 6 Calibration topics：2 shared + 每个 family 1 个 family-specific；
- 12 Untouched Test topics：4 shared + 每个 family 2 个 family-specific。

6 个 pilot topic assets 是 Development 的预先指定子集：2 shared + 每个 family 1 个 family-specific，六个均仅授权 outcome-free scenario/instrumentation QA。G2 冻结 held-out family 后，G5 outcome-bearing dose pilot 只使用 2 shared + 三个 Development families 各 1 specific，共 5 个 logical assets；held-out-family specific asset 不进入 `X_pilot`、不生成或查看 behavior/activation outcome。Topic split 与 Persona holdout 同时生效；每个 outcome phase 前都必须签名对应 `X_phi`。每个 Topic 的 25 个 content hashes 必须 pairwise unique；由统一冻结 canonicalization 仅对有序 content hashes 导出的 `topic_content_root_sha256` 必须在 36 topics 中 globally unique，重复 root 或跨 split 重用必须 fail closed。Held-out family 的 schedule 不能用其 outcomes 选择，只能使用 G4 outcome-blind calibration 与 G6 揭封前冻结的 cross-Development-family transfer/fallback rule；无可执行 schedule 则停止。旧 Gate A/B/C 与 OLMo 数据统一视为 **V1 historical exploratory data**，不参与 V2 模型开发、校准或 confirmatory test。

## 当前阶段和启动闸门

当前只允许完成数据/模型许可核验、protocol、schema、代码骨架、单元测试和小规模 instrumentation smoke。正式实验按以下顺序推进：

1. `G0`（已通过）：旧版本可恢复归档、checksums 和 provenance；
2. `G1`：冻结 family/trait sampling frame、public source provenance、36 个 topic IDs、`topic_scope × behavioral_family` eligibility、scenario families/subtypes、exact 18/6/12 IDs、exact 6 pilot-asset IDs、`split_algorithm_version`、`split_seed`、`balance_diagnostics_sha256`、`topic_split_plan_manifest_sha256`、`assignment_outcome_blind=true`、25-turn move hashes/content roots、静态双轴 access policy 和 outcome-blind suitability protocol；G1 不冻结 trait/variant/wording generalization assignments 或 phase exposures；
3. `G2`：冻结 fully held-out family、trait/variant/wording generalization assignments、prompts、item-role split、Persona Vector protocol、behavior-only Drift rubric 和 onset rule；
4. `G3`：冻结三模型 revisions、chat templates、hook semantics 和 10-trajectory storage/runtime benchmark；
5. `G4`：完成 outcome-blind L0–L5 pressure calibration；
6. `G5`：在 signed `X_pilot` 与新版 sample-size manifest 通过后，仅对三个 Development families 和 5 个 logical assets 运行 outcome-bearing dose pilot；held-out family无 outcome；
7. `G6`：冻结 primary endpoint、false-alarm budget、 $\alpha$ 、power、confirmatory exposure rule、signed `X_main`、heldout-family schedule-transfer/fallback 与停止规则、完整分析计划和 non-Flow extension allowlist；
8. 运行 main study并一次性打开 untouched test；
9. `G7`：在任何 fork outcome 前冻结 signed `X_fork` 和 intervention estimator，再运行 randomized forks；
10. `G8`：pipeline 冻结后进行 PersonaGym external evaluation。

未通过相应 gate 时不得启动后续阶段，也不得用 `TBD` 的缺省实现生成正式数据。

## 工程原则

- 所有实验使用 machine-readable configs、frozen manifests 和显式 schema version；
- 每个模型固定 repository revision、tokenizer revision、chat template 和 generation parameters；
- activation feature 必须携带 `available_at_turn`，评估代码拒绝未来信息；
- raw outputs、activations、model weights、logs 和 credentials 不提交 Git；
- Git 只同步代码、协议、small manifests、aggregate results 和可复现命令；
- 失败重跑不覆盖原 attempt，保留 failure ledger；
- untouched test 不用于 debug、调参或选择 layer。

## 项目结构

```text
.
├── README.md
├── pyproject.toml
├── deep-research-report.md
├── deep-research-report.pdf
├── 重启项目的细节.md
├── configs/
│   └── restart_v2.yaml      # V2 顶层设计契约；不得包含 secret
├── data/
│   └── README.md            # 数据边界与生成纪律；G1 后才新增 manifests
├── docs/
│   ├── source_materials.sha256
│   ├── legacy_recovery.md
│   ├── experiment_ledger.md
│   ├── restart_v2_amendment.md
│   ├── persona_topic_design_amendment_v2_2.md
│   ├── topic_design_amendment_v2_3.md
│   └── research_protocol_v2.md
├── legacy_artifacts/
│   └── pre_restart_v1_20260824/  # recovery-only V1 archive
├── jobs/
│   └── README.md            # G3 后才加入 CETUS/PBS job specs
├── scripts/                 # V2 可复现 CLI entry points
├── src/persona_drift/       # V2 library code
└── tests/                   # unit、schema、leakage 和 hook-contract tests
```

当前 `data/` 只含 [data/README.md](data/README.md)。public item IDs、splits、seeds 和 checksums 等 manifests 只有在 G1 通过并冻结后才会新增；README 不预告尚不存在的数据结构。

历史 V1 文件不参与 active experiments；其恢复位置、Git tag 和 SHA256 由 [旧版本恢复说明](docs/legacy_recovery.md) 记录。

## 环境与测试

项目要求 Python 3.11–3.12。`pyproject.toml` 直接声明 PyTorch、Transformers 等运行依赖。CETUS 的 `persona-drift` 环境应保留已经安装并验证过的 `torch==2.9.1+cu128`；该版本满足依赖时，editable install 不会替换它：

```bash
python -m pip install -e ".[test]"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python -m pytest -p no:cacheprovider
```

分析与公开数据工具是 optional extras：

```bash
python -m pip install -e ".[analysis,data,test]"
```

新建环境必须先按照目标 CUDA 平台安装兼容的 PyTorch wheel，再安装本项目。任何批量 GPU 任务必须先通过协议中的 `G3` smoke checks。

## 结果与结论

**V2.3 目前没有结果。** 仓库中的旧数值、图表和 Gate 文档若被归档，只能用于解释 V1 为什么需要重启，不能作为 V2 Region、Margin、hazard 或 Robust Radius 的证据。

V2 的首个可报告结果将是：pressure calibration 与 dose-finding pilot 是否在 matched model × persona trait × schedule 内产生可识别的 Stable/Drift transition band。在此之前，不应宣称新的提前预测假设成立或失败。

## Reproducibility 和 GitHub

每次完成一个 gate 后，先运行测试并生成 provenance/checksum manifest，再提交并同步 GitHub。提交中不得包含 Hugging Face token、SSH 密钥、密码、model weights、raw activation corpus 或可能泄露凭据的 scheduler logs。
