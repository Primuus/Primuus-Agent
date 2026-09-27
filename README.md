# Long-Horizon Coding Agent

本仓库用于实现一个可运行、可验证、可评测的 Coding / Terminal Agent。

已完成[第一阶段执行方案](docs/Long-Horizon-Coding-Agent-Phase-1-Execution-Plan.md)中的节点 A～G，建立了 10 个任务。默认模型服务为 DeepSeek V4.1 Flash；真实模型批量运行 10 个任务，均由独立 Verifier 判定通过。运行条件、逐题结果和完整 Trace 见[实验记录](docs/experiments/2026-09-26-deepseek-flash/README.md)。

后续开发按[总体方案](docs/方案.md)的节点 H～M 推进。节点 H～K 已完成：评测与普通仓库会话共用同一 Session Runner，普通仓库会话支持持久记录、续跑和有限的失败恢复。节点 K 的受控故障注入结果见[实验记录](docs/experiments/2026-09-27-recovery-controlled/README.md)。

## 目前的文件

```text
coding_agent/       Python 包及共享数据契约
coding_agent/harness/ 评测任务加载
coding_agent/session/ 通用会话状态、上下文与 Agent Loop
coding_agent/sandbox/ Docker 任务环境及镜像定义
coding_agent/tools/   文件与终端工具
coding_agent/verifier/ 独立容器验证器
coding_agent/eval/   Trace 与批量评测
config/default.json 初始运行配置
docs/contracts.md   任务、动作、工具结果、运行结果约定
tasks/task_001/     最小示例任务：说明、初始仓库、独立验证器
```

任务包的读取方式、验证规则和结果位置见[契约文档](docs/contracts.md)。

## 检查示例任务

示例任务的初始代码故意有错。在项目根目录执行：

```bash
cd tasks/task_001/repo
python3 ../verifier.py
```

预期退出码为非零。Agent 的任务是修复 `calculator.py`，使同一验证器返回零退出码。

Docker 工具使用前构建本地镜像：

```bash
docker build -t coding-agent-sandbox:local -f coding_agent/sandbox/Dockerfile .
```

## 运行任务

默认使用 DeepSeek 的 `deepseek-flash` 与 `https://api.deepseek.com`。在运行环境中设置 `DEEPSEEK_API_KEY` 后即可执行；密钥不会写入仓库或运行结果。若使用其他兼容 Chat Completions 工具调用的服务，可通过 `--model` 和 `--base-url` 覆盖默认值，并使用 `OPENAI_API_KEY`。

模型适配还支持 Anthropic Messages API。指定 `--backend anthropic --model <模型 ID>`，并在运行环境设置 `ANTHROPIC_API_KEY`；其他兼容服务可用 `--api-key-env <变量名>` 指定凭据来源。配置和会话记录只保存变量名，不保存密钥值。

```bash
python3 -m coding_agent run tasks/task_001
python3 -m coding_agent batch tasks
python3 -m coding_agent compare tasks --repeats 3
```

每次运行的 `trace.jsonl`、`result.json` 和 `config.json` 保存在 `runs/<run_id>/`；批量汇总保存为 `runs/batch-<时间戳>.json`。`compare` 对同一任务分别运行关闭和开启恢复的版本，保存成对结果、成功率、恢复率、步数、Token、耗时和人工介入。真实模型结果有随机性，应重复运行并结合单次 Trace 分析。`runs/` 已加入 `.gitignore`。

## 在普通仓库中工作

从本项目目录运行以下命令，仓库路径指向要修改的 Git 仓库：

```bash
python3 -m coding_agent exec /path/to/repository --task '修复登录流程中的错误' --check 'git diff --check'
python3 -m coding_agent chat /path/to/repository
python3 -m coding_agent chat /path/to/repository --skill cleanup
```

`exec` 是单次无交互运行，默认允许在隔离工作区内执行工具；`chat` 是可连续提问的交互会话，写文件和运行 Shell 时默认询问。可用 `--approval-mode auto|ask|read-only` 指定策略，`--max-steps` 调整模型轮数，`--recovery-mode on|off` 切换恢复策略。默认镜像包含 Python 和 Git；其他语言项目可用 `--image` 选择已准备好的镜像，镜像仍需包含 Python 和 Git 供文件工具使用。确需容器联网时显式加 `--network`。交互会话中可用 `/status`、`/diff`、`/exit`。

每次会话从目标仓库当前 `HEAD` 创建独立 Git 副本，原仓库及其未提交改动不会被修改。工作区、`session.json`、`diff.patch`、`status.txt`、`trace.jsonl` 和 `result.json` 默认保存在 `~/.local/state/primuus-agent/sessions/<session_id>/`；可用 `--sessions-dir` 修改位置。`--check` 指定的项目检查在模型给出最终回复后执行，检查失败时将结果交给模型进行有限次修复；检查命令保存在会话中供续跑使用。最终仍未通过时，`exec` 返回非零退出码。

默认恢复策略只对可重试的模型服务错误和只读工具超时自动重试；相同的失败动作会被拦截，并提示模型检查原因、选择其他动作。写文件、构建或测试失败时，隔离工作区可回到操作前快照。恢复动作、失败类别、重试和人工介入计数都写入会话事件与结果。运行 `--recovery-mode off` 可取得无自动恢复的基线。

创建普通仓库会话时，根目录的 `AGENTS.md` 会作为项目指令加入模型上下文。`--instruction-file <相对路径>` 可再加入项目文件；`--skill <名称>` 会读取工作区中的 `.primuus/skills/<名称>/SKILL.md`。这些来源的内容与摘要记录在会话事件中，续跑时保持一致。

可用 `--hooks-file <JSON 文件>` 显式启用 `before_tool` 和 `after_tool` Shell Hooks。例如文件内容为 `{"before_tool": ["git diff --check"], "after_tool": []}`。Hook 在隔离工作区运行，遵守当前权限模式，并把命令、结果写入 Trace。前置 Hook 失败会阻止对应工具调用；后置 Hook 失败会作为本次工具错误反馈。会话续跑沿用创建时保存的 Hook 配置。

MCP 工具为可选扩展。先安装 `python3 -m pip install '.[mcp]'`，再通过 `--mcp-config <JSON 文件>` 为新会话配置受信任的 stdio 服务，例如：

```json
{
  "servers": [{
    "name": "project",
    "command": "python3",
    "args": ["/path/to/server.py"],
    "env_from": ["PROJECT_TOKEN"],
    "read_only_tools": ["lookup"]
  }]
}
```

服务工具会以 `mcp__project__lookup` 等名称提供给模型；未列入 `read_only_tools` 的工具按写入操作管理，在 `ask` 模式询问、在 `read-only` 模式拒绝。服务命令在 Agent 宿主机上以隔离 Git 副本为工作目录运行，只有 `env_from` 列出的环境变量会额外传给服务；只配置你信任的服务。工具发现、调用和权限决定写入会话 Trace，续跑沿用创建时的配置。未配置 MCP 时不需要安装可选依赖。

会话事件在操作过程中持续写入 `trace.jsonl`。运行中按 `Ctrl+C` 可暂停；空闲时也可用命令标记暂停。记下输出中的 `session_id` 后，可查看并续跑：

```bash
python3 -m coding_agent inspect <session_id>
python3 -m coding_agent pause <session_id>
python3 -m coding_agent resume <session_id> --task '继续完成剩余工作'
python3 -m coding_agent resume <session_id> --interactive
python3 -m coding_agent snapshot <session_id>
python3 -m coding_agent restore <session_id> --snapshot <commit>
```

恢复未完成的任务时可省略 `--task`。若中断恰好落在一个工具调用内部，该操作的结果可能无法确定；先查看会话工作区和 diff，再用 `resume <session_id> --resolve-pending` 确认继续。系统不会自动重放这次工具调用。交互模式还提供 `/plan`、`/snapshots`、`/restore <commit>` 和 `/pause`。复杂任务可由模型维护里程碑计划；上下文过长时，旧对话被压缩为摘要，近期消息和计划保留。会话总轮数和 Token 上限由配置控制。

## 任务集

| 任务 | 内容 |
|---|---|
| `task_001` | 修复加法函数 |
| `task_002` | 修复名称标准化 |
| `task_003` | 修复本地模块导入 |
| `task_004` | 修复 JSON 配置类型 |
| `task_005` | 补全缺失函数 |
| `task_006` | 修复按 ID 查询的 API |
| `task_007` | 根据错误日志修复除零问题 |
| `task_008` | 修复命令行输出格式 |
| `task_009` | 修复键值配置解析 |
| `task_010` | 修复依赖当前目录的文件读取 |
| `task_011` | 跨模块修复带分页的问题搜索 |
| `task_012` | 跨模块实现配置驱动的 CSV 导出 |

每个任务都包含 `task.md`、初始 `repo/` 和仅供 Harness 调用的 `verifier.py`。12 个任务均已确认初始版本验证失败、参考修复版本验证通过。最初 10 个任务用预设修复动作运行整条批量链路时全部通过，平均每任务 1 步、1 次工具调用；这只用于检查系统集成，**不是模型性能实验结果**。检查使用的临时文件已清理，任务 Verifier 属于评测数据并保留。

真实模型的首轮基线实验对每个任务运行一次，结果为 10/10 通过，平均每任务 3.8 步、4.5 次工具调用、5.4569 秒。该结果仅对应这 10 个小型任务和这一次运行；原始结果及 Trace 已保存在[实验记录](docs/experiments/2026-09-26-deepseek-flash/README.md)。
