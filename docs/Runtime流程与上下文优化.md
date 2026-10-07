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

## 第三步实施

- 工具结果不再在 DockerTools 中按 20,000 字符截断，完整结果进入 Trace。模型侧仍按上下文阈值保留预览。
- 预览提供 output_ref；read_tool_output 按调用编号与行范围读取原结果，包括 stderr。该只读工具由共享 Runner 处理，普通仓库会话和评测均可使用；引用只属于当前会话。
- 最新分段源码和最新按范围读取的结果在首次提供给模型前保持完整。更早结果可被清理，通过 Trace 引用找回。
- 摘要记录当前实际改动文件、成功操作、命令与失败、源码位置及调用编号。计划中的目标文件优先保留；模型普通说明明确标为未验证意图。
- 工作区补丁元数据写入日志并可重建；回滚后重新观察当前补丁。最终说明使用事实摘要，不携带源码正文。

一次 Docker 综合验证覆盖超过 20,000 字符的完整输出、压缩后中间内容读取、新鲜源码编辑以及持久化重建。结果见 [focused-step-3.json](../experiments/2026-10-07-runtime-workflow/focused-step-3.json)。没有引入额外模型摘要调用；实际成本收益留待真实验证。

## 第四步实施与验证准备

- 结果增加实际 changed_paths 和 plan_complete，便于对照任务、补丁与检查。
- 最终回复及续跑不会将未完成计划标为 completed；预算说明仍与成功完成分别记录。
- 工作提示要求按原需求进行最小行为复现或验证，检查通过不能替代需求实现证据。独立隐藏 Verifier 继续留在 Agent 工作区之外。
- README 同步现有能力与运行方式，移除已经取消的预算工具关闭说明。

未完成计划的定向验证见 [focused-step-4.json](../experiments/2026-10-07-runtime-workflow/focused-step-4.json)。真实任务验证尚未执行，S 阶段仍未整体验收。

## 第一批真实验证

真实运行版本为 `b17b0fb`，沿用第三轮的模型、固定源码树、镜像、上下文和预算。两题均为无宿主中断样本，没有接口故障。结果为 **0/2 通过**，达到两题失败的停止规则，不执行第二批三次回归；未执行任务不计为失败。

| 任务 | 停止原因 | 输入 Token | 总 Token | 有效源码修改 | 独立验证 / 重建 |
| --- | --- | ---: | ---: | --- | --- |
| intword | token_budget | 85,794 | 98,565 | 无 | 失败 / 一致 |
| boltons 跨文件 | token_budget | 90,708 | 93,465 | 无 | 失败 / 一致 |

两题均在第 14 轮生成精简最终说明，明确没有修改。intword 有一次导入命令失败，模型未使用已经提供的 PYTHONPATH 环境；曾手动执行现有 240 项测试并通过，但未产生补丁，所以没有触发当前补丁的自动检查。独立任务验证仍失败。跨文件执行 16 次工具调用，没有工具错误。

两题均未调用 update_plan 或 read_tool_output。intword 出现长时间的数值边界调查；跨文件存在整文件和大范围分段读取交替重复。连续相同读取提醒没有触发，因为重复读取之间穿插了其他调用或改变了范围。能力已提供，但这轮没有证明模型会有效使用它们。

预算说明与日志重建得到真实验证；探索到编辑、跨文件能力与整体输入成本仍未验收。没有成功样本可用于宣称成本收益，也没有进入下一阶段。

原始证据见 [report.json](../experiments/2026-10-07-runtime-workflow/real/report.json) 和 [analysis.json](../experiments/2026-10-07-runtime-workflow/real/analysis.json)。会话配置、完整 Trace、补丁、独立验证和逐请求指标保存在 real/records/。隐藏验证代码仅在独立容器通过 stdin 执行，没有进入 Agent 上下文或工作区。

## 真实验证后的两处修正

1. intword 最终上下文只保存最近两条命令，遗漏较早执行的 240 项测试。现在单独保留匹配配置检查的历史 Shell 调用及输出，与当前补丁的自动检查分别记录。用已有 Trace 重建验证，未调用模型；原始最终回复保留作为失败证据。见 [final-evidence-correction.json](../experiments/2026-10-07-runtime-workflow/final-evidence-correction.json)。
2. 工作请求不能容纳最大 8,192 输出 Token 时，原收尾判断提前切换最终说明。现在先按剩余预算分配工作输出，在不足一轮最低输出额度时才收尾。重建两题停止前状态，仍可分别分配 2,196 和 7,478 工作输出 Token，同时保留最终说明预算。见 [budget-allocation-correction.json](../experiments/2026-10-07-runtime-workflow/budget-allocation-correction.json)。

这两处修正只做既有日志重放，没有重新执行真实任务；不能据此推断 intword 或跨文件已经通过。本轮仍判失败。

临时驱动、源码副本、会话工作区和容器已删除，没有永久新增验证脚本或工程依赖。凭据未写入文件，检查结果见 [cleanup-report.json](../experiments/2026-10-07-runtime-workflow/cleanup-report.json)。
