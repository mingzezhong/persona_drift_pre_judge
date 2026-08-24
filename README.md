# Latent Persona Seismograph

基于生成前内部激活轨迹，对 LLM Agent 的 Persona Drift 进行条件化早期预测，并通过随机压力干预估计 Persona Robust Radius。

> **当前状态：V2 重启准备阶段。** G0 旧版本可恢复归档已经完成，G1–G8 尚未通过；V2 dose-finding pilot、main study 和 randomized intervention 均尚未运行，因此本仓库目前没有 V2 实验结果或确认性结论。

## 新方案

V2 不再把 Persona Vector projection 的变化直接解释成 Drift。外部 pressure 本来就会移动内部 activation；真正需要识别的是：

> 在相同 model、persona、topic、pressure family 和 pressure history 下，内部轨迹是否开始偏离“最终仍能保持 Persona 稳定”的正常压力响应轨迹。

研究链路为：

\[
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
\]

其中：

- **Stability Region**：在给定 Persona 与压力历史后，Stable trajectories 的条件化接受域；
- **Persona Margin**：当前 residual trajectory 距离稳定边界的余量；
- **Persona Robust Radius**：从当前 prefix 出发，未来每轮至少再增加多少个经过校准的 pressure levels，才会使 5-turn Drift risk 达到操作性阈值。

V2 的核心识别要求是：

\[
\text{Same Persona + Same Topic + Same Pressure Family + Same Absolute Schedule}
\Rightarrow
\{\text{Stable},\text{Drift}\}.
\]

如果 outcome 仍由 Persona、topic 或 condition 几乎决定，就不能声称模型学到了“稳定性”。

## 权威设计文件

以下文件共同定义 V2；`重启项目的细节.md` 是主报告的补充，负责把主报告保留的开放项操作化：

- [deep-research-report.md](deep-research-report.md)：概念框架、识别问题和建模路线；
- [deep-research-report.pdf](deep-research-report.pdf)：主报告的 PDF 版本；
- [重启项目的细节.md](重启项目的细节.md)：公开数据、25-turn 采集、PPU、随机干预和样本量的执行细节；
- [V2 执行解释与补充条款](docs/restart_v2_amendment.md)：统一时序、符号、剂量边界和启动闸门；
- [V2 正式研究协议](docs/research_protocol_v2.md)：阶段、样本设计、分析与停止规则。

不得仅依据 README 修改科学定义；任何正式变更必须新增带版本的 amendment。

**项目范围决定（2026-08-25）：V2 不采用 Conditional Flow。** 本项目不设计、实现、调参、比较或报告 Conditional Flow、Conditional Normalizing Flow、Normalizing Flow、Flow Matching，以及其他 flow-based density/trajectory models；它们不属于 baseline、ablation、备选模型或后续 gate。来源材料中的相关候选讨论按 G0 checksum 原样保留，仅用于记录方案形成过程，不构成执行授权。任何重新纳入都必须由用户明确改变项目范围并建立新的 major-version protocol，不能通过 V2 的普通 amendment 或 `G1–G8` 重新打开。

主报告中保留的内部 cite 占位符属于来源原文的 provenance，本仓库不直接修改源文件。它们不是投稿可用的参考文献。论文投稿前必须通过单独的 **Bibliography Gate**：逐条将占位符映射到可核查的 primary source URL/DOI，完成引用核验；仍有未解析占位符时不得提交论文。

来源校验、旧版本恢复和持续记录见：

- [权威来源 SHA256](docs/source_materials.sha256)；
- [旧版本恢复说明](docs/legacy_recovery.md)；
- [实验账本](docs/experiment_ledger.md)。

## 第一版固定设计

| 项目 | V2 设计 |
|---|---|
| Models | Qwen3-8B、Llama-3.1-8B-Instruct、Gemma-3-12B-it |
| Primary personas | risk-averse、risk-seeking、stands-its-ground、agreeableness |
| Topics | 24 个 MMLU-Pro anchors + 6 个 Anthropic sycophancy/opinion anchors |
| Main trajectory | 25 main turns；前 5 turns 为 neutral baseline |
| Pressure | 每个 persona × family 独立校准的 L0–L5 ordinal scale |
| PPU | 同一 family 内相邻 pressure level 增加一级 |
| Primary activation | 每轮生成回答前的 final prompt token |
| Components | 所有 layers 的 `resid_pre`、`attn_out`、`mlp_out` |
| Full attention | 仅预先分层抽取的约 5% mechanistic subset |
| Primary warning horizon | H=5；H=3、10 为 sensitivity analyses |
| Region baseline | Conditional expected response + dynamic shrinkage Mahalanobis tube |
| Risk model | Discrete-time hazard with right censoring |
| Excluded methods | Conditional/Normalizing Flow、Flow Matching 及其他 flow-based density/trajectory models（整个 V2 排除） |
| Intervention | Randomized prefix forks，d∈{0,1,2,3}，H=5 |
| Robustness threshold | η=0.8；0.7、0.9 为 sensitivity analyses |

连续压力倍率 \(\lambda\) 不属于 V2 第一版。V2 使用每轮 \(L_t\)、PPU 和累计 PPU-turns，并保留完整 absolute schedule。

## 计划数据规模

| 阶段 | 设计 | 完整/短 trajectories | Target-model turns |
|---|---|---:|---:|
| Dose-finding pilot | 3 models × 4 personas × 6 topics × 4 seeds × 5 schedules | 1,440 | 36,000 |
| Main study | 3 × 4 × 30 topics × 8 seeds × 3 schedules | 8,640 | 216,000 |
| Randomized forks（G7 eligibility 满足时的目标） | 600 prefixes × 4 doses × 4 continuation seeds | 9,600 | 48,000 |
| **8-seed base-plan 合计** | 不含 judges 和 external evaluation | — | **约 300,000** |

这是一项条件性 base plan，不是已完成或保证的数据量。若 eligible prefix 不足，G7 必须停止并 amendment，不能 clipping 或跨层借样本。Main seed 数只有在 pilot 后的预注册 power simulation 触发时，才可在正式生成前从 8 扩展到 10；此时总量必须重新计算。

## 数据切分

30 个 main topics 按 topic 而不是 individual trajectory 切分：

- 15 Development topics；
- 5 Calibration topics；
- 10 Untouched Test topics。

6 个 pilot topics 是 Development 的预先指定子集。旧 Gate A/B/C 与 OLMo 数据统一视为 **V1 historical exploratory data**，不参与 V2 模型开发、校准或 confirmatory test。

## 当前阶段和启动闸门

当前只允许完成数据/模型许可核验、protocol、schema、代码骨架、单元测试和小规模 instrumentation smoke。正式实验按以下顺序推进：

1. `G0`（已通过）：旧版本可恢复归档、checksums 和 provenance；
2. `G1`：冻结 public persona/topic IDs、scenario templates 和 split；
3. `G2`：冻结 Persona Vector protocol、behavior-only Drift rubric 和 onset rule；
4. `G3`：冻结三模型 revisions、chat templates、hook semantics 和 10-trajectory storage/runtime benchmark；
5. `G4`：完成 outcome-blind L0–L5 pressure calibration；
6. `G5`：运行 1,440-trajectory dose-finding pilot并选择 transition schedules；
7. `G6`：冻结 primary endpoint、false-alarm budget、\(\alpha\)、power、完整分析计划和 non-Flow extension allowlist；
8. 运行 main study并一次性打开 untouched test；
9. `G7`：冻结 intervention estimator后运行 randomized forks；
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

**V2 目前没有结果。** 仓库中的旧数值、图表和 Gate 文档若被归档，只能用于解释 V1 为什么需要重启，不能作为 V2 Region、Margin、hazard 或 Robust Radius 的证据。

V2 的首个可报告结果将是：pressure calibration 与 dose-finding pilot 是否在 matched model × persona × schedule 内产生可识别的 Stable/Drift transition band。在此之前，不应宣称新的提前预测假设成立或失败。

## Reproducibility 和 GitHub

每次完成一个 gate 后，先运行测试并生成 provenance/checksum manifest，再提交并同步 GitHub。提交中不得包含 Hugging Face token、SSH 密钥、密码、model weights、raw activation corpus 或可能泄露凭据的 scheduler logs。
