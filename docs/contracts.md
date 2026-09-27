# 第一阶段数据与模块契约

本文记录当前评测任务与会话接口。Python 数据结构位于 [`coding_agent/contracts.py`](../coding_agent/contracts.py)；任务示例位于 [`tasks/task_001/`](../tasks/task_001/)。

## 1. 任务如何加载

每个任务是 `tasks/<task_id>/` 下的一个独立目录：

```text
tasks/task_001/
├── task.json       元数据，仅 Harness 读取
├── task.md         提供给 Agent 的任务说明
├── repo/           每次运行都从这里复制初始代码
└── verifier.py     Harness 控制的验证器，不放进 Agent 工作区
```

`task.json` 的第 1 版格式：

```json
{
  "schema_version": 1,
  "task_id": "task_001",
  "title": "Fix the addition function",
  "tags": ["python", "bugfix"],
  "verifier": {
    "kind": "python_script",
    "entrypoint": "verifier.py"
  }
}
```

- `schema_version` 固定为 `1`；不认识的版本应拒绝加载。
- `task_id` 必须与目录名一致，在任务集中唯一。
- `task.md` 和 `repo/` 必须存在；`repo/` 是 Agent 唯一可修改的任务内容。
- 目前只约定 `python_script` 验证器；`entrypoint` 是相对任务目录的文件名，必须留在任务目录内。
- Harness 读取元数据和说明，将 `repo/` 的副本放入 Agent 容器 `/workspace`。Agent 只能接触任务说明和该副本；验证器在独立的容器中针对工作区快照运行，不挂载到 Agent 容器。
- 任务基线应验证失败；存在正确修复时应验证通过。这样成功率才反映 Agent 的工作。

## 2. 模型如何交付动作

`ModelBackend.generate(messages, tools)` 返回一个标准化的 `ModelResponse`。一次模型回复包含一个或多个工具调用，或一个最终回复；模型服务自己的响应格式由后端适配器转换。

工具调用示例：

```json
{
  "tool_calls": [{
    "call_id": "call_001",
    "name": "read_file",
    "arguments": {"path": "calculator.py"}
  }],
  "final_message": null,
  "input_tokens": 120,
  "output_tokens": 18
}
```

最终回复示例：

```json
{
  "tool_calls": [],
  "final_message": "I have applied the fix.",
  "input_tokens": 205,
  "output_tokens": 10
}
```

- `call_id` 标识一次调用，供工具结果与 Trace 对应；后端没有提供时由适配器生成。
- 第一阶段评测只暴露 `read_file`、`write_file`、`run_shell`。参数分别为 `{ "path": string }`、`{ "path": string, "content": string }`、`{ "command": string }`。普通仓库会话还提供文件发现、文本搜索、分段读取、精确编辑、Git 状态与差异、计划更新。缺失、多余或类型错误的参数均无效。
- 没有动作、同时有工具调用和最终回复、或最终回复为空，视为无效模型动作，终止原因记为 `invalid_model_action`。
- 同轮多个工具调用按返回顺序执行，全部结果一起加入下一轮 Context；该轮仅进行一次 Verifier 检查。
- 工具名或参数无效时，Harness 不执行该调用，而是生成 `ToolResult(status="error")` 反馈模型；该轮仍计入步数和失败工具调用次数。
- 最终回复只表示模型决定结束；评测任务的**成功必须由 Verifier 判定**。开启恢复时，最终验证失败可以触发有次数上限的再修复。

## 3. 工具如何返回结果

三个工具共享 `ToolResult` 格式：

```json
{
  "call_id": "call_001",
  "name": "run_shell",
  "status": "completed",
  "output": "2 passed",
  "error": null,
  "exit_code": 0,
  "duration_ms": 125
}
```

- `status` 为 `completed`、`error` 或 `timeout`。`completed` 表示工具执行结束；对 `run_shell`，退出码非零仍属于 `completed`，退出码单独反映命令成败。
- `output` 放读取内容、写入确认或命令标准输出；`error` 放工具错误或命令标准错误。没有相关内容时分别用空字符串和 `null`。
- `exit_code` 仅对已经结束的 `run_shell` 命令有值；其他情况为 `null`。
- `duration_ms` 为工具耗时，单位毫秒。
- 文件路径相对 `/workspace`。绝对路径、`..` 越界和符号链接越界必须被拒绝；节点 C 的容器配置还应限制 `run_shell` 的可写区域为任务工作区。工具超时及不可执行命令要转化成可记录的结果，不让 Agent Loop 无说明地崩溃。
- 每个工具调用返回一个结果；Harness 将其作为 Observation 送入下一轮 Context。

## 4. 成功如何判断、何时停止

Harness 在工具动作后调用任务 Verifier，并在模型最终回复时再次确认结果。Verifier 在独立环境中读取 Agent 工作区的快照；其代码与执行入口由 Harness 控制，Agent 无法修改。验证通过时 `success=true`，`stop_reason="verified"`。最终验证未通过时，可按恢复预算继续一轮；仍未通过时为 `final_unverified`。普通仓库会话在最终回复后执行保存的项目检查，检查通过时为 `completed`。

其余终止原因：

| `stop_reason` | 含义 |
|---|---|
| `completed` | 普通仓库会话收到模型最终回复，指定的项目检查通过 |
| `paused` | 普通仓库会话暂停，可从事件记录恢复 |
| `token_budget` | 会话达到 Token 预算 |
| `max_steps` | 达到模型轮次上限 |
| `timeout` | 整个任务超过时间限制 |
| `invalid_model_action` | 模型回复无法归一化为一个动作 |
| `model_error` | 模型服务持续不可用或返回错误 |
| `tool_error` | 工具基础设施出现无法继续的错误 |
| `verifier_error` | 验证器自身无法完成检查 |
| `recovery_exhausted` | 重复失败动作达到拦截上限 |

一般的无效工具参数和命令失败会作为 Observation 反馈模型，并不直接使用 `tool_error` 终止。节点 K 将模型服务、工具、命令、构建、测试和最终验证失败分别写入 `failure_detected` 事件；可重试的模型错误与只读工具超时有次数上限。重复失败动作会被拦截，写入、构建和测试失败可触发操作前快照回退。独立 Verifier 的内部输出不会反馈给模型；用户指定项目检查的输出可用于修复。

## 5. 结果保存在哪里

每次运行使用唯一 `run_id`，产物保存为：

```text
runs/<run_id>/
├── trace.jsonl   按执行顺序记录模型动作、工具结果、验证结果和错误
├── result.json   单次运行摘要
└── config.json   本次配置和任务内容摘要
```

`result.json` 使用 `RunResult` 字段：

```json
{
  "run_id": "example_run_001",
  "task_id": "task_001",
  "model_id": "example-model",
  "success": false,
  "stop_reason": "max_steps",
  "steps": 20,
  "tool_calls": 18,
  "failed_tool_calls": 2,
  "retries": 0,
  "recoveries": 0,
  "manual_interventions": 0,
  "failure_counts": {"test": 1},
  "tokens": 3200,
  "latency_seconds": 93.4,
  "trace_path": "runs/example_run_001/trace.jsonl"
}
```

- `steps` 是模型回复轮数，`tool_calls` 是尝试分发的工具调用次数。
- `failed_tool_calls` 统计无效工具调用、工具错误、工具超时和非零命令退出码。
- `retries` 统计模型、只读工具和最终验证的额外尝试；`recoveries` 统计重试、替代动作与快照回退事件；`manual_interventions` 统计会话中确认中断工具、权限询问和手动回退。`failure_counts` 按失败类别汇总事件。
- `tokens` 是可获得的输入与输出 token 之和；模型服务未提供用量时为 `null`，不能用 `0` 代替。
- `latency_seconds` 是从任务启动到清理完成的总耗时。
- `trace.jsonl` 每行是一个带 `run_id`、`step`、`event_type`、`timestamp` 和事件数据的 JSON 对象。
- 评测 Trace 包含 `user_message`、`model_action`、`tool_started`、`tool_result`、`verification_result`、`failure_detected`、`recovery_action` 和 `task_finished`。普通仓库会话还会记录计划、快照、上下文压缩、项目检查及其命令集、人工介入与恢复事件。`config.json` 记录不含密钥的运行参数与任务文件 SHA-256 摘要。`compare` 对同一任务成对运行关闭和开启恢复的版本，分别保存单次 Trace 与汇总 JSON。
- 普通仓库会话从隔离副本读取项目指令与显式选择的技能，写入 `context_source_added` 事件，记录相对路径、内容与 SHA-256 摘要。续跑从事件恢复这些来源；模型密钥只从命名的环境变量读取。
- 显式启用的 `before_tool`、`after_tool` Hook 使用相同的命令权限入口，分别产生 `hook_started` 和 `hook_result` 事件。Hook 失败会反映在关联的工具结果中；未启用 Hooks 时不改变工具行为。
- 普通仓库会话可显式配置 MCP stdio 服务。发现的工具以 `mcp__<服务名>__<工具名>` 暴露给模型，`mcp_tools_registered` 记录工具名；调用沿用 `tool_started`、`tool_result` 与权限事件。服务配置随会话保存，环境变量仅保存名称；未声明为只读的 MCP 工具按写操作审批。MCP 服务在宿主机执行，外部系统的副作用不属于 Git 快照，遇到未完成调用时仍需人工检查后确认续跑。
- `ci` 与 `exec` 共用普通仓库会话及 Trace。`ci --output-dir` 将 `result.json`、`trace.jsonl`、`diff.patch`、`status.txt` 复制到指定目录，并生成 `summary.json`，字段为 `success`、`session_id`、`stop_reason`、`checks` 和 `artifacts`。成功退出码为 0，未完成或项目检查失败为 1；失败时仍保留可生成的会话产物。
- 跨任务记忆位于仓库外的 SQLite 文件中，按原仓库绝对路径隔离。每条记录包含 `memory_id`、`kind`（`project`、`failure`、`fix`）、内容、相对路径适用范围、来源、修订号与启停状态。新增、修订和停用都保留版本快照；手工来源记录来源引用及当时的原仓库提交。
- 普通仓库会话的记忆模式为 `off`、`summary` 或 `retrieve`。启动和续跑时选择的记录由 `memory_context_set` 事件保存快照，Context 标注记忆 ID、修订号、适用路径和来源；`result.json` 列出本次选择的 ID。`memory_stored` 记录从当前会话提取的失败或经过项目检查的修复。检索只读取同一原仓库的有效记录；停用条目不会进入新上下文。
- `compare-memory` 固定原仓库基线、任务、检查、模型和预算，先复制记忆数据库，然后用 `off`、`summary`、`retrieve` 各运行指定次数。比较期间关闭记忆写入；`report.json` 汇总成功率、轮数、工具调用、Token、耗时与选择的记忆 ID，每次运行仍保留独立会话配置、Trace、结果和补丁。

## 6. 默认配置

[`config/default.json`](../config/default.json) 放步数、超时、容器资源、结果目录等初始值。当前默认服务为 DeepSeek，模型 ID 为 `deepseek-flash`，基础地址为 `https://api.deepseek.com`。密钥不写入任务包、配置文件或 Trace；运行时从 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 读取。
