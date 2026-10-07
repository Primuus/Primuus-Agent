# Runtime 流程与上下文优化

## 范围与依据

在 S 阶段继续收敛 Runtime，按用户确认的方案分步实现并提交。第三轮跨文件任务在接口和工具均无报错时仍未尝试编辑；预算停止时也未产生最终说明。目标为有效补丁推进、准确收尾与减少重复输入，收益以真实任务验证为准。

参考 OpenCode `ecc4916` 的 [工具输出保存](https://github.com/anomalyco/opencode/blob/ecc4916b5a9608c30e6dd58a67f2137b594407ca/packages/opencode/src/tool/truncate.ts)、[历史清理](https://github.com/anomalyco/opencode/blob/ecc4916b5a9608c30e6dd58a67f2137b594407ca/packages/opencode/src/session/compaction.ts)、[任务摘要](https://github.com/anomalyco/opencode/blob/ecc4916b5a9608c30e6dd58a67f2137b594407ca/packages/core/src/session/compaction.ts)，以及 [Aider 仓库地图](https://aider.chat/docs/repomap.html)。这些是机制参考，不是本工程成功率或成本保证。

## 执行顺序

1. 工具调度、独立收尾预算与检查缓存。
2. 范围搜索、任务证据与编辑上下文、普通说明文本保存。
3. 旧输出清理、长输出按需读取、持续保留任务状态。
4. 完成说明与有限验证。

真实验证第一批只执行 intword 和 boltons 跨文件各一次；两题通过后，第二批执行 intcomma、packaging 和跨文件各一次。关键任务未通过先修复，累计两题失败停止扩展。固定模型、任务基准、Docker 和预算；中断样本单列。临时脚本与工作区用完删除，记录保留在 experiments/。

## 第一步实施

- 删除调查预算触发的工具缩减，保留已有三分之一预算的进度提醒。
- 工作请求预留的是精简最终说明的实际输入估计与最多 1,024 输出 Token，不再预留完整工作请求。
- 剩余预算或步数不足时生成无工具的最终说明；没有当前通过检查的补丁时，停止原因仍为 token_budget 或 max_steps，不将说明生成等同于任务通过。
- 最终上下文包含原任务、观察到的操作、计划和当前检查，避免携带大量源码与历史推理。
- 只读调用保留已通过检查缓存；Shell 调用可能改变环境，因此仍使该缓存失效。

定向验证包含预算与工具分支、真实 Docker 会话的编辑—读取—结束流程，以及日志重建。结果见 [focused-step-1.json](../experiments/2026-10-07-runtime-workflow/focused-step-1.json)。缓存验证的临时检查使用 python -B，防止导入产生缓存文件改变补丁。生产代码不依赖临时脚本。

## 第二步实施

- search_text 可限定仓库内文件或目录，并按文件名或相对路径 glob 过滤；query 仍为字面搜索，保留原调用形式。
- 计划可记录 files、hypothesis、next_action；这些是模型计划和假设，不能当作已验证事实。简单任务不要求额外计划调用。
- OpenAI 兼容与 Anthropic 适配器保存工具调用同时返回的普通说明文字，日志重建也保留它；DeepSeek 已有 reasoning_content 原样保留。旧日志缺少新字段时仍可重建。
- 三次相同读取返回相同结果时提供进度提醒，建议补充缺失证据、复现或编辑；不禁止正常工具调用。

定向验证覆盖适配器消息保留与重建、Docker 范围搜索和扩展计划持久化、重复读取提醒。结果见 [focused-step-2.json](../experiments/2026-10-07-runtime-workflow/focused-step-2.json)。只使用临时工作区和内联验证，没有新增永久测试脚本。
