# 节点 R：同仓库连续任务记忆对照数据

此目录保存 2026-09-29 在 `python-humanize/humanize` 上进行的五题连续任务对照。任务和修复前后提交见[任务清单](../../../tasks/memory_real/humanize-series.json)；运行参数见[配置](../../../config/real-recovery-2026-09-29.json)。模型使用 `deepseek-flash`，服务商将该别名标为 DeepSeek-V4.1-Flash；运行前后 `/models` 检查见 [api_model_checks.json](api_model_checks.json)。

每题都在相同的本地仓库提交上分别运行 `off`、`summary`、`retrieve`。每轮结束后统一应用上游代码变更，使三组下一题的起点相同；各组记忆独立积累。Agent 可见仓库只包含当前及以前的代码提交，不含未来上游修复提交。第一次尝试曾因完整上游 Git 历史泄露未来修复而被废弃；隔离重跑中生成接口一度返回 HTTP 402，之后从第二题续跑。14 条零步服务失败已排除，详见[审计结果](audit.json)。

[报告数据](report.json)包含 15 次主对照和 2 次错误记忆探针。每条记录的 `published_artifact_dir` 指向本目录下的会话配置、Trace、最终补丁、项目检查结果和独立验证结果。`artifact_dir` 是本机原始运行位置，仅作来源记录。所有五题的隐藏验证均在基线失败、在对应上游修复后通过；代码补丁与会话终态的核对也记录在审计文件中。

主对照每题每模式仅一次。`success` 指最终工作区通过独立隐藏验证；`normal_completions` 另计 Agent 正常结束且验证通过的次数。探索指标从 Trace 推导，具体口径见[阶段结论](../../completed/节点R-持续记忆真实对照实施记录.md)。
