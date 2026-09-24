# 第一阶段数据与模块契约

本文固定节点 A 的接口约定。Python 数据结构位于 [`coding_agent/contracts.py`](../coding_agent/contracts.py)；任务示例位于 [`tasks/task_001/`](../tasks/task_001/)。节点 B～G 将按此约定实现运行逻辑。

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
- Harness 读取元数据和说明，将 `repo/` 的副本放入 Agent 容器 `/workspace`。Agent 只能接触任务说明和该副本；验证器不得挂载到 Agent 容器。后续节点 E 应由 Harness 在独立的验证环境中，针对工作区快照运行验证器。
- 任务基线应验证失败；存在正确修复时应验证通过。这样成功率才反映 Agent 的工作。

## 2. 模型如何交付动作

`ModelBackend.generate(messages, tools)` 未来应返回一个标准化的 `ModelResponse`。一次模型回复**恰好**包含一个工具调用，或一个最终回复；模型服务自己的响应格式由后端适配器转换。

工具调用示例：

```json
{
  "tool_call": {
    "call_id": "call_001",
    "name": "read_file",
    "arguments": {"path": "calculator.py"}
  },
  "final_message": null,
  "input_tokens": 120,
  "output_tokens": 18
}
```

最终回复示例：

```json
{
  "tool_call": null,
  "final_message": "I have applied the fix.",
  "input_tokens": 205,
  "output_tokens": 10
}
```

- `call_id` 标识一次调用，供工具结果与 Trace 对应；后端没有提供时由适配器生成。
- 只支持 `read_file`、`write_file`、`run_shell`。参数分别为 `{ "path": string }`、`{ "path": string, "content": string }`、`{ "command": string }`。缺失、多余或类型错误的参数均无效。
- 没有动作、同时有工具调用和最终回复、或最终回复为空，视为无效模型动作，终止原因记为 `invalid_model_action`。
- 工具名或参数无效时，Harness 不执行该调用，而是生成 `ToolResult(status="error")` 反馈模型；该轮仍计入步数和失败工具调用次数。
- 最终回复只表示模型决定结束；**成功必须由 Verifier 判定**。

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

Harness 在工具动作后调用任务 Verifier，并在模型最终回复时再次确认结果。Verifier 在独立环境中读取 Agent 工作区的快照；其代码与执行入口由 Harness 控制，Agent 无法修改。验证通过时 `success=true`，`stop_reason="verified"`。模型最终回复而验证未通过时，结果为 `final_unverified`。

其余终止原因：

| `stop_reason` | 含义 |
|---|---|
| `max_steps` | 达到模型轮次上限 |
| `timeout` | 整个任务超过时间限制 |
| `invalid_model_action` | 模型回复无法归一化为一个动作 |
| `model_error` | 模型服务持续不可用或返回错误 |
| `tool_error` | 工具基础设施出现无法继续的错误 |
| `verifier_error` | 验证器自身无法完成检查 |

一般的无效工具参数和命令失败会作为 Observation 反馈模型，并不直接使用 `tool_error` 终止。第一阶段只要求这种基本错误处理；更复杂的恢复策略留到后续阶段。

## 5. 结果保存在哪里

每次运行使用唯一 `run_id`，产物保存为：

```text
runs/<run_id>/
├── trace.jsonl   按执行顺序记录模型动作、工具结果、验证结果和错误
└── result.json   单次运行摘要
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
  "tokens": 3200,
  "latency_seconds": 93.4,
  "trace_path": "runs/example_run_001/trace.jsonl"
}
```

- `steps` 是模型回复轮数，`tool_calls` 是尝试分发的工具调用次数。
- `failed_tool_calls` 统计无效工具调用、工具错误、工具超时和非零命令退出码。
- `retries` 统计基础设施层面的额外尝试；未进行重试时为 `0`。后续 Failure Recovery 的策略重试需另行定义，避免混淆。
- `tokens` 是可获得的输入与输出 token 之和；模型服务未提供用量时为 `null`，不能用 `0` 代替。
- `latency_seconds` 是从任务启动到清理完成的总耗时。
- `trace.jsonl` 每行是一个带 `run_id`、`step`、`event_type`、`timestamp` 和事件数据的 JSON 对象；节点 F 将固定具体事件类型及汇总实现。

## 6. 默认配置

[`config/default.json`](../config/default.json) 放步数、超时、容器资源、结果目录等初始值。`model.backend` 和 `model.name` 目前为 `null`，表示尚未选择与接入服务。密钥不写入任务包、配置文件或 Trace；模型接入时从运行环境读取。
