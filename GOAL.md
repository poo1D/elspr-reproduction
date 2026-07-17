# GOAL：复现 ELSPR 论文

## 1. 项目目标

在一个可独立运行、可审计、可扩展的 Python 仓库中复现论文 **ELSPR: Evaluator LLM Training Data Self-Purification on Non-Transitive Preferences via Tournament Graph Reconstruction** 的核心方法与主要实验链路。

项目必须优先完成“方法复现”，再进行“小规模实验复现”，最后才尝试“论文数字级复现”。不得为了匹配论文表格而硬编码结果，也不得把缺失的实验细节当作已知事实。

最终系统应支持以下端到端流程：

1. 读取同一问题下由多个 LLM 生成的回答；
2. 对每一对回答进行双顺序 pairwise judging；
3. 将偏好关系构造成 tournament graph；
4. 使用 SCC 分析计算非传递率；
5. 计算论文定义的归一化二维有向图结构熵；
6. 按全局入度重构 SCC，得到 tie-aware acyclic preference structure；
7. 将原始偏好数据划分为 `cleaned` 与 `discarded`；
8. 分别在 `raw`、`cleaned` 和等量 `random` 数据上进行 LoRA 微调；
9. 比较模型的非传递率、结构熵、人类一致性和下游判别能力；
10. 自动生成可复现实验报告。

### 1.1 开源仓库交付目标

本项目不仅要在本地完成，还必须在实现过程中持续同步到用户的公开 GitHub 仓库。默认仓库配置为：

```text
GITHUB_OWNER=poo1D
GITHUB_REPO=elspr-reproduction
GITHUB_REPO_FULL_NAME=poo1D/elspr-reproduction
GITHUB_SSH_URL=git@github.com:poo1D/elspr-reproduction.git
```

若用户后来提供其他仓库地址，只修改仓库配置，不改变本文定义的 Git 工作流。

仓库初始化要求：

- 仓库必须为 public；
- 默认分支为 `main`；
- 若远程仓库尚不存在，且本机 `gh auth status` 通过，可执行：

```bash
gh repo create poo1D/elspr-reproduction \
  --public \
  --description "Reproduction of ELSPR: graph-based self-purification for evaluator LLM preference data" \
  --source . \
  --remote origin
```

- 若仓库已存在，则验证并设置远程地址：

```bash
git remote -v
git remote add origin git@github.com:poo1D/elspr-reproduction.git  # 仅在 origin 不存在时
git remote set-url origin git@github.com:poo1D/elspr-reproduction.git
```

- 首次公开提交至少包含 `README.md`、`GOAL.md`、`LICENSE`、`.gitignore`、`.env.example`、`PROGRESS.md` 和基础项目结构；
- 默认使用 MIT License；
- 禁止把 API key、`.env`、私有数据、完整模型权重、checkpoint、缓存和大体积运行产物提交到 GitHub。

---

## 2. 复现层级

### Level 1：算法级复现，必须完成

不依赖大规模 API 或 GPU，完整实现并验证：

- 双顺序偏好聚合；
- tournament graph 构建；
- Tarjan SCC 分析；
- 非传递率 `rho_non_trans`；
- 二维结构熵 `H2` 与归一化结构熵 `tau`；
- SCC 内基于全局入度的图重构；
- `cleaned/discarded` 数据过滤；
- 合成样例、单元测试和可视化。

### Level 2：小规模实证复现，必须完成

选择一个 AlpacaEval 子集和少量回答模型，建议：

- 50–200 个问题；
- 5–8 个 response models；
- 每个无序回答对进行两次顺序交换判断；
- 至少训练一组 `raw`、`cleaned`、`random` LoRA 模型；
- 在未参与训练的问题或 response models 上评估。

Level 2 的目标是验证论文结论的方向：

- `cleaned` 模型的 `rho_non_trans` 低于 `raw`；
- `cleaned` 模型的 `tau_avg` 低于 `raw`；
- `random` 不能稳定达到 `cleaned` 的改进；
- cleaned 数据通常保留 raw 数据的大部分，而不是只保留极少样本。

不得要求小规模实验精确复现论文中的 13.8% 和 0.088 改进。

### Level 3：完整论文复现，可选

在补齐论文附录、补充材料、模型列表、prompt 模板、数据切分和训练配置后，复现：

- AlpacaEval 的 5 个数据集；
- 14 个训练 response models 和 7 个测试 response models；
- Qwen2.5-Max teacher；
- Qwen2.5-7B-Instruct，LoRA rank 8，3 epochs，learning rate `1e-4`，batch size 16；
- Llama-3.1-8B-Instruct 消融；
- MT-Bench、2.5k 人工标签、Self-BLEU、人类标注实验；
- 论文 Tables 1–7 和主要图表。

当前 PDF 未包含完整附录和补充代码，因此 Level 3 在缺少这些资产时只能标记为 `blocked`，不能声称完成精确复现。

---

## 3. 核心数据格式

所有中间数据使用 JSONL，字段必须稳定、可追溯。

### `responses.jsonl`

```json
{
  "question_id": "q_0001",
  "dataset": "helpful_base",
  "instruction": "...",
  "model_id": "model_a",
  "response": "...",
  "generation_config": {},
  "source": "alpacaeval"
}
```

### `judgments.jsonl`

每一条记录表示一个有顺序的比较。

```json
{
  "question_id": "q_0001",
  "left_model": "model_a",
  "right_model": "model_b",
  "left_response": "...",
  "right_response": "...",
  "verdict": "left_win",
  "normalized_left_outcome": "win",
  "judge_model": "qwen2.5-max",
  "prompt_template_id": "cot_v1",
  "raw_output": "...",
  "status": "ok",
  "created_at": "..."
}
```

允许的标准化结果：`win`、`lose`、`tie`、`invalid`。

### `pair_relations.jsonl`

聚合两个顺序后的无序回答对关系。

```json
{
  "question_id": "q_0001",
  "model_a": "model_a",
  "model_b": "model_b",
  "j_ab": "win",
  "j_ba": "lose",
  "relation": "a_over_b"
}
```

关系允许：`a_over_b`、`b_over_a`、`tie`。

---

## 4. 图构建规则

边方向必须严格遵循论文：**边从较差回答指向较好回答**，因此节点入度表示其胜出次数。

对回答 `a_j` 和 `a_k`：

- 若 `J(a_j, a_k)=win` 且 `J(a_k, a_j)=lose`，添加 `v_k -> v_j`；
- 若 `J(a_j, a_k)=lose` 且 `J(a_k, a_j)=win`，添加 `v_j -> v_k`；
- 其他情况添加双向边 `v_j <-> v_k`，表示 tie 或位置偏差导致的不稳定关系。

实现要求：

- 使用 `networkx.DiGraph` 或自研等价结构；
- 双向 tie 使用两条有向边表示；
- 每个问题应形成完整 tournament relation；
- 若某个回答对缺少一个顺序或解析失败，默认将该问题标记为 `incomplete`，不静默补值；
- 报告中必须统计 incomplete questions 和 invalid judgments。

---

## 5. 非传递率

使用 Tarjan 算法求 SCC。

一个 SCC 被视为 non-transitive，当且仅当：

1. SCC 大小大于 2；
2. SCC 内至少存在一对节点不是双向 tie。

全局非传递率实现为：

```text
rho_non_trans =
    所有问题中属于 non-transitive SCC 的节点数之和
    / 所有问题的节点数之和
```

注意：论文公式符号存在歧义，但正文明确描述分子是 non-transitive SCC 中的节点总数，因此实现必须对 SCC 大小求和，而不是只统计 SCC 个数。

---

## 6. 二维有向图结构熵

对每个图 `G=(V,E)`：

- `d_in(v)`：节点入度；
- `vol(SCC_j) = sum(d_in(v) for v in SCC_j)`；
- `vol(G) = sum(d_in(v) for v in V) = |E|`；
- `g_j`：从 SCC 外部进入 `SCC_j` 的边数，但排除“singleton SCC 到 singleton SCC”的边；
- 保留 singleton 与 multi-node SCC 之间的边，以及不同 multi-node SCC 之间的边。

实现论文公式：

```text
H2(G) =
  - sum_j [g_j / vol(G) * log2(vol(SCC_j) / vol(G))]
  - sum_j [vol(SCC_j) / vol(G)
           * sum_{v in SCC_j}
             d_in(v) / vol(SCC_j)
             * log2(d_in(v) / vol(SCC_j))]

 tau(G) = H2(G) / log2(|V|)
```

数值约定：

- `0 * log(0) = 0`；
- `|V| <= 1` 时 `tau = 0`；
- `vol(G) = 0` 时 `tau = 0`；
- `vol(SCC_j) = 0` 时该 SCC 的对应项为 0；
- 默认不强行 clip 到 `[0,1]`，若超界应记录 warning，以便发现公式理解或数据构建问题。

数据集指标：

```text
tau_avg = mean(tau(G_i))
```

---

## 7. SCC 重构与数据过滤

对原图中每个 SCC：

1. 记录每个节点在原图中的全局入度 `global_in_degree`；
2. 删除 SCC 内所有原始边；
3. 对 SCC 内任意节点对 `(v_i, v_j)`：
   - 若 `in_i > in_j`，添加 `v_j -> v_i`；
   - 若 `in_i < in_j`，添加 `v_i -> v_j`；
   - 若 `in_i == in_j`，添加双向边；
4. SCC 之间的原始边保持不变。

严格来说，含双向 tie 的结果不是普通 DiGraph 意义下的 DAG。实现中应把双向 tie 节点视为等价类；收缩 tie 等价类后，quotient graph 必须是 DAG。

由重构图得到每个有序回答对的目标标签：

- `b -> a` 且不存在 `a -> b`：`J(a,b)=win`；
- `a -> b` 且不存在 `b -> a`：`J(a,b)=lose`；
- 同时存在两个方向：`J(a,b)=tie`。

过滤规则：

- 原始判断与重构目标一致：进入 `cleaned`；
- 不一致：进入 `discarded`；
- 默认不重新标注原始样本；
- 若原始 judge 只允许 win/lose，而重构结果为 tie，则两条有序判断均进入 `discarded`；
- 任何“重标注”实验必须作为额外消融，不能混入论文主复现。

---

## 8. 训练实验

至少生成三套训练集：

- `raw`：全部合法原始训练数据；
- `cleaned`：ELSPR 过滤后数据；
- `random`：从 raw 中按 cleaned 的样本数量随机采样，固定 seed。

训练实现要求：

- Hugging Face Transformers + PEFT；
- LoRA 参数全部配置化；
- 默认论文参数：rank 8、3 epochs、learning rate `1e-4`、batch size 16；
- 明确记录 batch size 是 per-device 还是 global；
- 保存训练配置、随机种子、Git commit、依赖版本、GPU 信息和数据 hash；
- 支持断点续训；
- 不在代码中硬编码 Qwen 路径或 API key；
- exact prompt 未知时，模板必须放在 `configs/prompts/` 中并在报告中标为 deviation。

---

## 9. 评估

### 必做指标

- `rho_non_trans`；
- `tau_avg`；
- cleaned/raw/random 数据量；
- 每个问题 SCC 数量、最大 SCC 大小、tie ratio；
- 不同训练集模型在 unseen questions 上的指标差异。

### 建议指标

- 与 AlpacaEval 人工标签的一致率；
- Spearman rank correlation；
- MT-Bench adjusted win rate：

```text
r_adj = (wins + 0.5 * ties) / (wins + losses + ties)
```

- 多个被评模型 adjusted win rate 的标准差；
- non-transitive 与 transitive response pairs 的 Self-BLEU；
- bootstrap confidence interval。

所有评估必须输出逐问题明细和聚合结果，不能只输出最终均值。

---

## 10. CLI

仓库提供统一 CLI：

```bash
elspr prepare-data --config configs/data.yaml
elspr judge --config configs/judge.yaml --resume
elspr build-graphs --judgments artifacts/judgments.jsonl
elspr analyze --graphs artifacts/graphs/
elspr filter --graphs artifacts/graphs/ --judgments artifacts/judgments.jsonl
elspr train --variant raw --config configs/train_qwen.yaml
elspr train --variant cleaned --config configs/train_qwen.yaml
elspr train --variant random --config configs/train_qwen.yaml
elspr evaluate --config configs/eval.yaml
elspr report --run-dir runs/<run_id>
```

`judge` 必须支持：

- dry-run 估算请求数和 token 数；
- 本地缓存；
- 限速与重试；
- 幂等执行；
- 失败恢复；
- 原始输出永久保留。

---

## 11. 推荐仓库结构

```text
elspr-reproduction/
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
│       └── ci.yml
├── .env.example
├── .gitignore
├── CHANGELOG.md
├── LICENSE
├── PROGRESS.md
├── README.md
├── REPRODUCIBILITY.md
├── GOAL.md
├── pyproject.toml
├── configs/
│   ├── data.yaml
│   ├── judge.yaml
│   ├── train_qwen.yaml
│   ├── eval.yaml
│   └── prompts/
├── src/elspr/
│   ├── cli.py
│   ├── schemas.py
│   ├── data/
│   ├── judging/
│   ├── graph/
│   │   ├── build.py
│   │   ├── scc.py
│   │   ├── entropy.py
│   │   └── reconstruct.py
│   ├── filtering/
│   ├── training/
│   ├── evaluation/
│   └── reporting/
├── tests/
│   ├── test_pair_aggregation.py
│   ├── test_scc_metrics.py
│   ├── test_entropy.py
│   ├── test_reconstruction.py
│   └── test_end_to_end_toy.py
├── scripts/
├── artifacts/
├── runs/
└── reports/
```

---

## 12. Git 阶段跟进与公开同步

### 12.1 分支策略

采用“每个复现层级一个长期功能分支、每个实现阶段一个原子提交”的方式：

```text
main
├── repro/level-1
├── repro/level-2
└── repro/level-3
```

规则：

- `main` 只保存已经达到某个 Level 完成标准的稳定版本；
- Level 1 开发使用 `repro/level-1`；
- Level 2 开发使用 `repro/level-2`，从完成 Level 1 后的 `main` 创建；
- Level 3 同理；
- 每个 Level 开始时创建一个 Draft Pull Request；
- 每完成一个阶段，在本地测试通过后立即 commit，并 push 到对应远程分支；
- 不把整个 Level 压缩成一个 commit；公开仓库必须能够看到真实、连续的开发轨迹；
- 禁止对已经 push 的阶段提交执行 rebase、`commit --amend` 或 force push；需要修复时追加新的 `fix:` commit；
- 未经用户明确指示，不自动 merge Pull Request，也不直接向 `main` 推送开发代码。

初始化示例：

```bash
git checkout -b repro/level-1
git push -u origin repro/level-1

gh pr create \
  --base main \
  --head repro/level-1 \
  --draft \
  --title "repro: implement ELSPR Level 1" \
  --body-file .github/PULL_REQUEST_LEVEL_1.md
```

### 12.2 阶段提交协议

每个阶段必须执行完整闭环：

1. 仅完成当前阶段规定的工作，不混入无关重构；
2. 运行对应单元测试、静态检查和最小端到端检查；
3. 更新 `PROGRESS.md`，写明阶段状态、结果、已知偏差和下一步；
4. 更新必要的 `README.md`、`REPRODUCIBILITY.md` 或 `CHANGELOG.md`；
5. 检查 diff 和敏感信息；
6. 创建原子 commit；
7. push 到当前远程分支；
8. 确认远程 commit SHA 可见后再进入下一阶段。

标准命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
git status --short
git diff --check
git diff --cached --stat
git commit -m "<type>: <stage result>"
git push origin HEAD
```

每次 push 后记录：

```bash
git rev-parse HEAD
```

并把 commit SHA 写入 `PROGRESS.md` 对应阶段。不得预先伪造 SHA；只有 push 成功后才能填写。

### 12.3 Level 1 必须公开的阶段提交

| 阶段 | 主要交付 | 建议 commit message | push 前最低验证 |
|---|---|---|---|
| 0 | 仓库骨架、许可证、配置、CI、文档 | `chore: bootstrap reproducible ELSPR project` | 安装成功，空测试框架通过 |
| 1 | JSONL schema 与双顺序聚合 | `feat: implement pairwise judgment aggregation` | 聚合与位置偏差测试通过 |
| 2 | tournament graph 构建 | `feat: build tie-aware tournament graphs` | 边方向与完整性测试通过 |
| 3 | Tarjan SCC 与非传递率 | `feat: add SCC non-transitivity analysis` | Case A–D 中 SCC 指标通过 |
| 4 | `H2`、`tau`、`tau_avg` | `feat: implement directed structural entropy` | 零值、线性、循环、全 tie 测试通过 |
| 5 | SCC 重构与 quotient DAG | `feat: reconstruct SCC preference structure` | 重构排序和 DAG 校验通过 |
| 6 | cleaned/discarded 过滤 | `feat: filter non-transitive preference data` | 守恒与标签一致性测试通过 |
| 7 | 完整 toy test suite | `test: cover ELSPR toy graphs and edge cases` | 五类必测案例全部通过 |
| 8 | CLI 与 toy pipeline | `feat: expose end-to-end reproduction CLI` | 一条命令完成 toy pipeline |
| 9 | Level 1 报告与复现说明 | `docs: publish ELSPR level-1 reproduction report` | 全量 CI 通过，报告可追溯 |

如果某阶段第一次实现没有通过验证，不得提交“看似完成”的 commit。可以先继续本地修复；只有阶段达到最低验证要求后再提交。阶段提交后若 CI 失败，必须追加 `fix:` commit 并再次 push，不能改写历史。

### 12.4 `PROGRESS.md` 规范

`PROGRESS.md` 必须是公开进度总表，而不是流水账。至少包含：

```markdown
# Reproduction Progress

| Stage | Status | Branch | Commit | Tests | Main result | Deviations |
|---|---|---|---|---|---|---|
| 0. Bootstrap | done | repro/level-1 | <sha> | passed | repo initialized | none |
| 1. Pair aggregation | in_progress | repro/level-1 | — | partial | — | — |
```

状态只允许：

- `not_started`
- `in_progress`
- `blocked`
- `done`

每完成一个阶段，同时追加简短阶段记录：

```markdown
## Stage 3 — SCC analysis

- Completed: 2026-xx-xx
- Commit: `<full sha>`
- Tests: `uv run pytest tests/test_scc_metrics.py`
- Result: ...
- Paper assumptions/deviations: ...
- Next: ...
```

禁止把“计划完成”标为 `done`。因 API、GPU、论文附录或数据缺失而无法继续时，标为 `blocked` 并写清证据。

### 12.5 GitHub Actions

`.github/workflows/ci.yml` 至少在以下事件触发：

```yaml
on:
  push:
  pull_request:
```

CI 至少执行：

- Python 3.11 环境安装；
- `uv sync --frozen`；
- `ruff check`；
- `ruff format --check`；
- `pytest`；
- toy pipeline smoke test；
- 检查代码中不存在明显密钥模式；
- 检查 Git 跟踪文件中不存在超大模型或运行产物。

阶段只有在本地验证和 GitHub Actions 都通过后，才能在 `PROGRESS.md` 中最终标记为 `done`。

### 12.6 开源仓库安全边界

必须加入并遵守 `.gitignore`，至少忽略：

```gitignore
.env
.env.*
!.env.example
__pycache__/
.pytest_cache/
.ruff_cache/
.venv/
cache/
artifacts/raw/
artifacts/cache/
runs/**/checkpoints/
*.safetensors
*.bin
*.pt
*.pth
wandb/
```

额外要求：

- `.env.example` 只能放变量名和占位符；
- commit 前检查 `git diff --cached`；
- 不提交 Qwen API key、Hugging Face token、W&B key 或云平台凭据；
- 不提交许可证不允许再发布的数据；
- 大型公开数据只保存下载脚本、版本号、URL、checksum 和处理 manifest；
- 模型 checkpoint 放在外部模型仓库或 release artifact 中，Git 仓库只保存引用和 hash；
- 单文件超过 50 MB 时默认停止提交并说明原因；不得通过 Git LFS 绕过这一检查，除非用户明确批准；
- 任何密钥一旦进入 commit，即使随后删除，也必须视为泄露并立即停止 push，报告给用户处理。

### 12.7 Level 发布与版本标签

每个 Level 完成后：

1. 更新 `CHANGELOG.md`、`README.md` 和 `PROGRESS.md`；
2. 将 Draft PR 标记为 Ready for Review；
3. 等待用户确认后 merge 到 `main`；
4. merge 后创建 annotated tag：

```bash
git checkout main
git pull --ff-only origin main
git tag -a v0.1.0-level1 -m "ELSPR Level 1 algorithm reproduction"
git push origin v0.1.0-level1
```

建议版本：

- Level 1：`v0.1.0-level1`
- Level 2：`v0.2.0-level2`
- Level 3：`v1.0.0`

Release notes 必须列出：已完成内容、运行命令、指标、已知差异、环境、数据版本和对应 commit。

---

## 13. 必须通过的单元测试

### Case A：严格线性偏好

`A > B > C`，图中边为 `B->A, C->B, C->A`。

预期：

- 所有 SCC 为 singleton；
- `rho_non_trans = 0`；
- `tau = 0`。

### Case B：三节点循环

`A > B, B > C, C > A`。

预期：

- 一个大小为 3 的 SCC；
- `rho_non_trans = 1`；
- 三节点入度均匀时 `tau = 1`；
- 按入度重构后得到三者 tie；
- 若原始数据无 tie 标签，则这些二元判断进入 discarded。

### Case C：全部 tie

三对节点均双向。

预期：

- 一个大小为 3 的 SCC；
- 因所有节点对均为双向，`rho_non_trans = 0`；
- `tau = 1`。

### Case D：位置偏差

`J(A,B)=win` 且 `J(B,A)=win`。

预期：

- 聚合关系为 tie；
- 图中添加 `A->B` 和 `B->A`。

### Case E：重构正确性

构造包含外部节点且 SCC 内全局入度不同的图。

预期：

- 重构顺序与原始全局入度排序一致；
- 收缩 tie 等价类后图为 DAG；
- cleaned 与 discarded 数量之和等于合法 raw 数量。

---

## 14. 完成标准

项目只有同时满足以下条件才算完成 Level 1：

- 所有核心公式均有独立实现和测试；
- `pytest` 全部通过；
- toy example 可以一条命令跑通；
- 输出 raw graph、SCC、重构 graph、cleaned/discarded 文件；
- README 解释边方向、tie、SCC、熵公式和零值处理；
- 对论文中的歧义有 `REPRODUCIBILITY.md` 记录；
- 不存在硬编码论文结果。

Level 2 完成标准：

- 至少一组真实数据从准备到报告端到端跑通；
- raw、cleaned、random 三个训练变体可复现；
- 在 unseen evaluation set 上输出 `rho_non_trans` 与 `tau_avg`；
- 报告说明是否支持论文结论方向；
- API 花费、GPU 时长和失败样本均有记录。

Level 3 完成标准：

- 补齐论文缺失资产；
- 复现 Tables 1–7；
- 每个数字都可追溯到具体 run、config、checkpoint 和数据 hash；
- 对无法复现的差异给出证据化分析，而不是猜测。

---

## 15. 实现约束

- Python 3.11+；
- 使用 `uv` 或等价方式锁定依赖；
- 全部公共函数提供类型标注；
- 使用结构化日志；
- API key 只从环境变量读取；
- 原始数据只读，派生数据写入带 hash 的 run directory；
- 所有随机过程固定 seed；
- 每个实验保存完整 provenance；
- 优先写纯函数和单元测试，不把核心逻辑埋在 notebook；
- notebook 只用于探索和图表展示；
- 对缺失论文细节明确标注 `assumption` 或 `deviation`。

---

## 16. 第一阶段执行顺序

1. 初始化仓库、schema、配置系统和测试框架；
2. 实现 pairwise 双顺序聚合；
3. 实现 graph builder；
4. 实现 SCC 与 `rho_non_trans`；
5. 实现 `H2`、`tau`、`tau_avg`；
6. 实现 SCC 重构与 quotient DAG 校验；
7. 实现 cleaned/discarded 过滤；
8. 完成五类 toy tests；
9. 完成 CLI 和端到端 toy pipeline；
10. 再接入 AlpacaEval、judge API、LoRA 和真实评估。

实现过程中，每完成一个阶段都必须先运行测试、更新 `PROGRESS.md`、创建原子 commit 并 push 到 `repro/level-1`，确认远程提交和 CI 状态后再进入下一阶段。

执行代理不得只在全部开发结束后一次性上传；阶段性 Git 历史本身就是本项目的必需交付物。若远程认证失败、仓库不存在且无法创建、分支保护阻止 push 或 CI 无权限运行，应立即把当前阶段标为 `blocked`，保留本地 commit，并向用户报告准确命令输出，不得假装已上传。
