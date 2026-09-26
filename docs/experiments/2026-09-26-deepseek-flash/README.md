# DeepSeek V4.1 Flash：第一阶段任务集实验

运行日期：2026-09-26（UTC）。代码版本：[`05cde0e`](https://github.com/Primuus/Primuus-Agent/commit/05cde0ea38f2fdef5f25ee9dab38d9ee92b191a7)。模型 ID：`deepseek-flash`；服务地址：`https://api.deepseek.com`。

## 实验条件

- 任务集：`tasks/task_001`～`tasks/task_010`；每个任务从原始仓库开始，各运行一次，按顺序执行。
- 运行限制：每题最多 20 步、600 秒；工具超时 30 秒，Verifier 超时 60 秒。
- Sandbox：`coding-agent-sandbox:local`；每个任务独立容器，1 CPU、512 MB 内存、关闭网络。
- 成功判据：独立 Verifier 在任务工作区快照上通过；模型最终回复本身不计为成功。
- 配置详情和任务摘要保存在各题的 `config.json`；每一步的模型动作、工具观察和验证结果保存在 `trace.jsonl`。

## 结果

10 个任务全部通过，成功率 **10/10**。每题平均 **3.8 步**、**4.5 次工具调用**、**5.4569 秒**；总计 **35,517 tokens**。汇总原始文件：[batch-20260926T082513.json](../../../experiments/2026-09-26-deepseek-flash/batch-20260926T082513.json)。

| 任务结果 | 验证 | 步数 | 工具调用 | 失败工具调用 | Tokens | 耗时（秒） | 执行轨迹 |
|---|---|---:|---:|---:|---:|---:|---|
| [task_001](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082419-task_001-8efe74c0/result.json) | 通过 | 2 | 3 | 0 | 1457 | 2.852 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082419-task_001-8efe74c0/trace.jsonl) |
| [task_002](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082421-task_002-54e18bf8/result.json) | 通过 | 3 | 3 | 0 | 2727 | 6.230 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082421-task_002-54e18bf8/trace.jsonl) |
| [task_003](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082428-task_003-7d8a9607/result.json) | 通过 | 4 | 6 | 2 | 3795 | 4.858 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082428-task_003-7d8a9607/trace.jsonl) |
| [task_004](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082433-task_004-0b2d7e7d/result.json) | 通过 | 5 | 6 | 2 | 5061 | 6.056 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082433-task_004-0b2d7e7d/trace.jsonl) |
| [task_005](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082439-task_005-33c08298/result.json) | 通过 | 5 | 5 | 2 | 4884 | 7.426 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082439-task_005-33c08298/trace.jsonl) |
| [task_006](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082446-task_006-4761423b/result.json) | 通过 | 5 | 5 | 2 | 4701 | 6.028 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082446-task_006-4761423b/trace.jsonl) |
| [task_007](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082452-task_007-6b275b58/result.json) | 通过 | 3 | 4 | 0 | 2614 | 4.222 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082452-task_007-6b275b58/trace.jsonl) |
| [task_008](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082456-task_008-c3ecbce8/result.json) | 通过 | 3 | 3 | 1 | 2324 | 4.333 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082456-task_008-c3ecbce8/trace.jsonl) |
| [task_009](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082501-task_009-1fa5ec5c/result.json) | 通过 | 4 | 4 | 1 | 3970 | 7.146 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082501-task_009-1fa5ec5c/trace.jsonl) |
| [task_010](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082508-task_010-1948cdae/result.json) | 通过 | 4 | 6 | 2 | 3984 | 5.418 | [Trace](../../../experiments/2026-09-26-deepseek-flash/records/20260926T082508-task_010-1948cdae/trace.jsonl) |

“失败工具调用”包括工具状态非 `completed` 或 shell 命令退出码非零；因此探索性命令失败也会计入，但不等于任务失败。所有任务的终止原因为 `verified`。

这是 10 个专为第一阶段构建的小型任务，每题只运行一次。该结果用于证明任务、模型、工具、隔离环境、验证器和评测链路已经连通，不代表在其他任务或重复采样下的成功率。仓库内另有预设修复动作的集成检查；其 10/10 结果与本次真实模型实验分开记录。

## 复现

按[项目 README](../../../README.md) 构建镜像并设置运行时 `DEEPSEEK_API_KEY`，然后运行：

```bash
python3 -m coding_agent batch tasks
```

运行记录默认保存在本地 `runs/`。仓库根目录的 `experiments/2026-09-26-deepseek-flash/` 保存了上述一次真实运行的原始结果副本；各题 `result.json` 内的 `trace_path` 仍为运行时的 `runs/<run_id>/trace.jsonl`，在实验产物目录中可按对应 `records/<run_id>/trace.jsonl` 查阅。
