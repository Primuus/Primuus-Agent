# 节点 O：真实模型基线

## 实验条件

2026-09-28 使用真实模型运行节点 N 的 10 个真实仓库任务，每题重复 3 次，共 30 次。运行期间使用代码提交 `b1cdd11514a3bc5dcc7a662efa274d6bdc4a36e9`；完整配置、任务摘要和顺序保存在[实验清单](../../experiments/2026-09-28-real-baseline/manifest.json)。没有人工介入单次运行。

| 项目 | 固定值 |
| --- | --- |
| 模型 | DeepSeek `deepseek-flash`；运行前后 `/models` 均返回 `DeepSeek-V4.1-Flash`，见[版本检查](../../experiments/2026-09-28-real-baseline/api_model_checks.json) |
| 恢复、记忆、并行 | 均关闭；不启用技能、Hook 或 MCP 工具 |
| 仓库与任务 | `tasks/real/real_001`～`real_010`；各题固定源码快照和任务摘要见清单 |
| 工具集 | 固定代码提交中的 Session Runner、Repository Tools、Sandbox、Verifier 和 Evaluation |
| 预算 | 最多 80 步、120,000 Token；上下文字符预算 60,000 |
| 超时 | 任务 1,800 秒、工具 60 秒、Verifier 30 秒 |
| 沙箱 | 镜像 ID `sha256:4217cbc4df372b696f659c9f25d32dccbc52b4c33ddb8e8c2008c0aa8ae1f163`，1 CPU、512 MiB、容器断网 |

实验采用[固定配置](../../config/real-baseline-2026-09-28.json)，按重复次数和任务编号顺序执行。模型密钥仅通过运行时环境提供，实验文件中没有密钥。模型服务由宿主机访问；任务容器断网。

## 基线结果

总体成功率 **11/30 = 36.7%**。成功由独立 Verifier 的最终结果判定。终止原因分别为 `verified` 11 次、`token_budget` 15 次、`model_error` 4 次。4 次模型服务错误的 Trace 都记录了响应截断；恢复关闭，所以该次运行随即结束。

| 任务 | 成功次数 / 3 | 其他终止原因 |
| --- | ---: | --- |
| `real_001` | 3 | — |
| `real_002` | 0 | Token 预算 3 |
| `real_003` | 0 | Token 预算 3 |
| `real_004` | 3 | — |
| `real_005` | 0 | Token 预算 2、模型服务错误 1 |
| `real_006` | 0 | Token 预算 2、模型服务错误 1 |
| `real_007` | 3 | — |
| `real_008` | 2 | 模型服务错误 1 |
| `real_009` | 0 | Token 预算 2、模型服务错误 1 |
| `real_010` | 0 | Token 预算 3 |

| 指标 | 30 次运行的结果 |
| --- | ---: |
| 平均步数 | 8.70 |
| 平均工具调用次数 | 12.20 |
| 平均失败工具调用次数 | 2.53 |
| 平均耗时 | 36.17 秒 |
| 人工介入 | 0 次 |
| 有 Token 记录的运行 | 26/30 |
| 已记录 Token 合计 | 2,678,594 |
| 已记录运行的平均 Token | 103,022.85 |

4 次 `model_error` 的最终 `tokens` 字段为空，所以不能计算全部 30 次的平均 Token；已记录合计也不是实验的真实总消耗。Token 预算在每轮模型调用前检查，单轮结束后累计值可以超过 120,000。以上是 10 题、每题 3 次的基线观察值，不能外推为其他任务集或模型版本的成功率。模型版本由运行前后服务端查询确认，但 `deepseek-flash` 是服务端别名，清单没有不可变的服务端权重修订号。

## 产物与核验

[完整汇总](../../experiments/2026-09-28-real-baseline/report.json)保存每次的成功状态、步数、工具调用、失败调用、Token、耗时、人工介入和终止原因。`records/<run_id>/` 下各有 `trace.jsonl`、`diff.patch`、`verification.json`、`result.json` 和 `config.json`，共 150 个核心文件。30 次 Trace 均以 `task_finished` 结束；结果与最终独立检查一致；每份补丁都能对对应任务基线执行 `git apply --check`。

正式运行时的补丁导出包含测试产生的 Python 缓存文件，并对新增文件保留了工作区路径。运行结束后仅规范化 30 份 `diff.patch`：移除缓存差异、改为仓库相对路径；原始与规范化后的 SHA-256、移除数量及可应用性见[产物规范化记录](../../experiments/2026-09-28-real-baseline/artifact_normalization.json)。Trace、Verifier 结果、运行配置和统计结果没有改动。后续运行的补丁导出逻辑已在提交 `df4a820` 修复；本次基线统计仍对应上述运行代码提交。

节点 O 的验收项已完成。失败原因的细分和恢复策略的对照实验留待后续阶段。
