# Primuus-Agent

Primuus-Agent 是一个面向 Git 仓库的 **Long-Horizon Coding Agent** 研究原型。它通过模型与文件、终端工具协作，完成代码阅读、问题定位、修改和项目检查，并保存任务计划、执行轨迹与补丁，支持长任务暂停后继续执行。

目前提供命令行单任务执行、交互会话、隔离并行任务和评测入口。运行结果包含可审阅的代码差异、检查结果及资源消耗，便于日常开发使用和 Agent 行为研究。

## 现有功能

| 功能 | 能力 |
|---|---|
| 仓库编码 | 文件列表、按目录与文件模式搜索、分段读取、文件写入、精确替换、Shell 执行及 Git 状态与差异查看 |
| 隔离工作区 | 从目标仓库的 Git 提交创建独立副本，内置文件与终端工具在 Docker 中执行，容器默认关闭网络 |
| 长任务会话 | 计划初始化、编辑前行动回顾、项目检查后的进度回顾、当前子问题与下一动作、上下文压缩与工作笔记续接、历史输出按需读取、预算收尾、会话持久化、暂停与续跑 |
| 检查与快照 | 代码变更后执行配置检查，显式读取或重新运行检查、复用当前通过结果；支持 Git 快照与恢复 |
| 有限失败恢复 | 部分模型服务错误与只读工具超时重试、重复失败动作拦截、失败反馈及工作区回退 |
| 模型适配 | 支持具备工具调用能力的 OpenAI 兼容 Chat Completions 服务，以及 Anthropic Messages API |
| 项目扩展 | 加载 `AGENTS.md`、项目 Skills、工具执行前后的 Hooks 和可选 MCP 工具 |
| 仓库记忆 | 项目知识、历史失败及有效修复记录；支持摘要注入、相关记录检索与修订历史 |
| 并行任务 | 独立会话并发执行、修改范围约束、补丁整合、冲突记录与整合检查 |
| 评测与 CI | 独立 Verifier、批量评测、可续跑的重复基线、恢复与记忆对照，以及 CI 产物导出 |

## 快速开始

需要 Python 3.10 或更新版本、Git，以及可访问的 Docker 服务。基础 Python 包没有第三方运行依赖；运行 Agent 命令时请位于本项目根目录。

### 1. 获取项目并准备镜像

```bash
git clone https://github.com/Primuus/Primuus-Agent.git
cd Primuus-Agent
docker build -t coding-agent-sandbox:local -f coding_agent/sandbox/Dockerfile .
```

默认镜像包含 Python、Git 和 pytest。目标项目需要的其他依赖应准备在自定义镜像中，通过 `--image <镜像名>` 选择；文件工具需要镜像提供 Python 和 Git。容器需要联网时可显式使用 `--network`。

### 2. 配置模型凭据

默认配置使用模型名 `deepseek-flash`，服务地址为 `https://api.deepseek.com`：

```bash
export DEEPSEEK_API_KEY='<你的密钥>'
```

凭据从运行环境读取，不写入项目配置或会话产物。模型名、服务地址和凭据变量可通过 `--model`、`--base-url`、`--api-key-env` 覆盖。

### 3. 执行仓库任务

```bash
python3 -m coding_agent exec /path/to/repository \
  --task '修复 CSV 导出中的编码问题' \
  --check 'python3 -m pytest -q' \
  --check 'git diff --check'
```

将仓库路径和检查命令替换为目标项目的实际值。`--check` 可以重复传入，适用于测试、构建或其他验收命令；`git diff --check` 只检查补丁的空白格式。

会话基于目标仓库当前 `HEAD` 创建独立工作区，未提交改动不会自动带入。修改产物保存在会话目录中，供审阅和应用到目标仓库。

## 仓库会话

### 单次执行与交互模式

```bash
# 单次无交互执行
python3 -m coding_agent exec /path/to/repository --task '修复配置读取错误'

# 连续交互，使用项目检查
python3 -m coding_agent chat /path/to/repository --check 'python3 -m pytest -q'
```

`exec` 默认使用 `auto` 权限，`chat` 默认使用 `ask`。可通过 `--approval-mode` 选择：

| 模式 | 行为 |
|---|---|
| `auto` | 允许会话工具执行 |
| `ask` | 写文件、运行 Shell 等操作先询问 |
| `read-only` | 拒绝写入类工具，包括 Shell 工具 |

显式配置的 `--check` 命令作为项目验收在容器内执行。检查在代码产生新补丁后触发，最终回复时确认当前补丁的检查结果；失败输出会反馈给模型。结果与补丁摘要关联，续跑保留最近一批完整结果；补丁变化后需要重新检查。项目检查通过后，模型仍需完成最终回复。

模型可用 `run_checks` 获取配置检查；同一次运行中会复用相同补丁的已通过结果，`force=true` 明确重新执行。普通 Shell 和 Hook 的 Shell 调用使缓存失效，最终验证使用同一缓存。复现脚本与配置检查应分开执行。

`--recovery-mode on|off` 控制自动恢复。开启时，对可重试错误进行有限重试，拦截重复失败动作，并在失败的写入、构建或测试操作后按恢复策略回到快照。重试、恢复与人工介入均记录在执行轨迹中。

### 暂停、续跑与快照

运行中按 `Ctrl+C` 可暂停。使用命令输出中的 `session_id` 查看、续跑或恢复快照：

```bash
python3 -m coding_agent inspect <session_id>
python3 -m coding_agent pause <session_id>
python3 -m coding_agent resume <session_id>
python3 -m coding_agent resume <session_id> --task '继续修复另一个问题'
python3 -m coding_agent resume <session_id> --interactive
python3 -m coding_agent snapshot <session_id>
python3 -m coding_agent restore <session_id> --snapshot <commit>
```

若中断发生在工具调用内部，先查看工作区与补丁，再使用 `resume <session_id> --resolve-pending` 确认继续。该参数用于确认已检查未决操作，不会重放该工具调用。

交互模式支持 `/status`、`/diff`、`/plan`、`/snapshots`、`/restore <commit>`、`/pause` 和 `/exit`。模型可维护里程碑计划；上下文过长时压缩旧消息，并保留摘要、近期消息和计划。

### 会话产物

默认位置为 `~/.local/state/primuus-agent/sessions/<session_id>/`，可通过 `--sessions-dir` 修改：

```text
<session_id>/
├── workspace/       隔离 Git 工作区
├── session.json     会话配置与元数据
├── trace.jsonl      持续写入的执行事件
├── diff.patch       相对初始提交的补丁
├── status.txt       工作区 Git 状态
└── result.json      终止原因、计划、检查结果及资源统计
```

`result.json` 包含实际修改文件、计划是否完成、步数、工具调用、Token、重试、恢复、人工介入及耗时。`checks_current` 表示检查结果是否对应当前补丁；是否通过需查看各项检查的状态与退出码。配置检查与任务行为验证分别记录。

## 模型与运行配置

运行参数默认来自 [config/default.json](config/default.json)，可用 `--config <文件>` 指定其他配置。

| 配置项 | 默认值 |
|---|---|
| 模型后端 / 模型名 | `openai_compatible` / `deepseek-flash` |
| 服务地址 | `https://api.deepseek.com` |
| 轮数预算 | 普通仓库会话 80，评测任务 20 |
| 累计 Token 上限 | 默认不限制（`max_tokens: null`） |
| 编辑前行动回顾 | 无补丁且已有目标源码证据时，在已用 40,000 Token 后触发一次，更新下一动作 |
| 单次输出上限 | 8,192 Token，可用 `--max-output-tokens` 调整 |
| 默认 DeepSeek 推理强度 | 工具调用 `low`；计划初始化、行动和进度回顾、最终答复 `none` |
| 单次任务 / 工具超时 | 600 秒 / 30 秒 |
| 上下文压缩阈值 | 24,000 字符，优先保留近期 8 条消息 |
| 工具输出上下文上限 | 每个输出字段 4,000 字符；最新一轮分段源码读取保留原始输出，Trace 保留工具返回的完整结果 |
| 自动恢复 / 仓库记忆 | 开启 / 关闭 |
| 容器 CPU / 内存 / 网络 | 1 核 / 512 MB / 关闭 |

上下文压缩保留完整的工具调用组和最新任务要求；当近期消息仍然过长时继续压缩较早的调用组。最新一组调用及其推理字段保持完整，因此单组过长时仍可能超过字符阈值。支持的模型推理字段会随会话记录保存并回传。

发给模型的工具结果保留状态、输出、错误和退出码；完整输出、调用标识及耗时保存在 Trace。长输出预览提供 `output_ref`，模型可通过 `read_tool_output` 按调用编号与行范围查看原结果。摘要保留实际改动文件、操作、命令结果和源码引用；模型假设与意图单独标注。历史源码输出属于快照，文件变化后需重新读取当前源码。

`--max-steps` 可覆盖轮数预算。请求前按消息大小及最近实际用量估算输入成本，仓库会话单独预留精简最终说明的输入与最多 1,024 输出 Token。工作输出额度按剩余预算缩减；不足以支持下一轮工作或达到轮数限制时，使用无工具请求报告修改、检查与未完成工作。没有当前通过检查的补丁时仍记录预算或步数停止。输入估算不能视为精确计费上限，单次请求仍可能出现偏差。

工作阶段按会话权限保持工具可用。使用三分之一预算后会提醒推进修改，连续三次相同读取返回相同内容时提醒补充证据或选择下一动作。调度层只执行本次请求提供的工具。编辑后自动返回项目检查结果；只读操作复用当前补丁的通过结果，Shell 操作使检查缓存失效。已有计划仍有待办项时，最终回复记录为 `final_unverified`。

OpenAI 兼容后端支持 `model.reasoning_effort` 配置和 `--reasoning-effort none|low|high|max`，无工具的最终答复可单独设置 `model.final_reasoning_effort`。默认 DeepSeek 工具调用使用 `low`，最终答复使用 `none`；更换模型或服务地址时，需显式配置所选服务支持的推理强度。

其他模型服务可按以下方式使用：

```bash
# 兼容 Chat Completions 和工具调用的服务
python3 -m coding_agent exec /path/to/repository --task '修复配置读取错误' \
  --backend openai_compatible --model '<模型 ID>' \
  --base-url 'https://your-provider.example/v1' --api-key-env MODEL_API_KEY

# Anthropic Messages API，凭据从 ANTHROPIC_API_KEY 读取
python3 -m coding_agent exec /path/to/repository --task '修复配置读取错误' \
  --backend anthropic --model '<模型 ID>'
```

运行前在环境中设置对应的凭据变量。默认兼容后端读取 `DEEPSEEK_API_KEY`，未设置时可使用 `OPENAI_API_KEY`。

## 项目指令与工具扩展

新仓库会话默认加载根目录的 `AGENTS.md`。可以通过 `--instruction-file <相对路径>` 增加项目指令，通过 `--skill <名称>` 加载 `.primuus/skills/<名称>/SKILL.md`。指令内容与来源摘要写入会话记录，续跑使用保存的内容。

### Hooks

使用 `--hooks-file <JSON 文件>` 配置工具执行前后的 Shell 命令：

```json
{
  "before_tool": ["git diff --check"],
  "after_tool": []
}
```

Hook 在容器工作区执行，遵守工具权限模式。前置 Hook 失败会阻止该工具调用，后置 Hook 失败会反馈为工具错误；命令与结果记录在 Trace 中。

### MCP

MCP 为可选依赖，先执行 `python3 -m pip install '.[mcp]'`，再使用 `--mcp-config <JSON 文件>` 配置 stdio 服务：

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

服务工具以 `mcp__project__lookup` 等名称注册。未列入 `read_only_tools` 的工具按写入操作管理。MCP 服务在宿主机启动，以隔离 Git 副本为工作目录，按 `env_from` 传入环境变量；应配置可信服务。工具发现、调用和权限决定均保存到 Trace。

## 仓库记忆

记忆按源仓库存储在仓库外的 SQLite 数据库中，支持 `project`、`failure`、`fix` 三类记录。每条记录带有来源、仓库提交、适用路径和修订历史。

```bash
python3 -m coding_agent memory-add /path/to/repository --kind project \
  --text '导出文件采用 UTF-8 编码' --source 'docs/export.md' --scope 'exporter.py'
python3 -m coding_agent memory-list /path/to/repository
python3 -m coding_agent memory-update /path/to/repository \
  --memory-id <记忆 ID> --text '导出文件采用 UTF-8 BOM' --source 'issue-42'
python3 -m coding_agent memory-history /path/to/repository --memory-id <记忆 ID>
python3 -m coding_agent memory-remove /path/to/repository --memory-id <记忆 ID>
```

新会话通过 `--memory-mode off|summary|retrieve` 选择模式，默认 `off`。`summary` 加入最近记录；`retrieve` 按任务关键词与适用路径检索，默认最多加入 3 条、2,500 字符。选择结果与来源记录在 Trace 中。

开启记忆后，会话可记录历史失败和通过检查的项目检查命令；有效修复仅在任务正常完成、当前补丁通过项目检查且存在代码变更时保存。记忆内容加入模型上下文，仍需结合当前仓库验证。

默认数据库为 `~/.local/state/primuus-agent/memory/memory.sqlite3`，可用 `--memory-dir` 调整位置。项目指令、Skills、Hooks、MCP 和记忆设置在创建会话时配置，续跑沿用保存的设置。

## 并行任务与补丁整合

`parallel` 按 JSON 清单执行独立子任务。每项任务定义 ID、指令、允许修改的相对路径及检查命令，另行指定整合检查：

```json
{
  "tasks": [
    {"id": "api", "instruction": "修复 API 分页", "paths": ["src/api.py"], "checks": ["python3 -m pytest -q tests/test_api.py"]},
    {"id": "export", "instruction": "修复导出格式", "paths": ["src/export.py"], "checks": ["python3 -m pytest -q tests/test_export.py"]}
  ],
  "integration_checks": ["python3 -m pytest -q"]
}
```

将上述清单保存为 `tasks.json` 并按目标项目调整路径与检查命令：

```bash
python3 -m coding_agent parallel /path/to/repository \
  --tasks-file tasks.json --workers 2 --output-dir runs/parallel-review
```

子任务从同一提交创建各自的 Git 副本和容器，分别导出交接信息、Trace、结果和补丁。成功任务的补丁按清单顺序应用到另一份整合工作区，再执行整合检查。范围外修改、冲突和整合结果写入 `report.json`；输出目录应为空，有依赖的任务应分批执行。

## 评测能力

项目内置三类评测资源：

| 路径 | 内容 |
|---|---|
| `tasks/task_001` ～ `tasks/task_012` | 12 个小型修复与跨文件开发任务 |
| `tasks/real/real_001` ～ `tasks/real/real_010` | 来自 3 个开源仓库、固定源提交的 10 个真实任务 |
| `tasks/memory_real/humanize-series.json` | 用于跨任务记忆研究的 5 个连续任务 |

任务包由 Harness 加载，独立 Verifier 在模型执行环境之外验证结果。评测保存 Trace、补丁、验证结果和配置，可分析成功率、失败类别、步数、Token 与恢复行为。

```bash
# 单任务与批量评测，产物默认写入 runs/
python3 -m coding_agent run tasks/task_001
python3 -m coding_agent batch tasks

# 固定条件的真实任务重复基线，支持使用相同参数续跑
docker build -t coding-agent-real-benchmark:20260928 -f tasks/real/Dockerfile .
python3 -m coding_agent baseline tasks/real --config config/real-benchmark.json \
  --repeats 3 --output-dir runs/real-baseline

# 相同任务与预算下的恢复开关对照，支持续跑
python3 -m coding_agent compare-recovery tasks/real --config config/real-benchmark.json \
  --repeats 3 --output-dir runs/recovery-comparison
```

`compare` 提供批量恢复对照；`compare-memory` 对普通仓库任务重复比较关闭记忆、摘要和检索三种模式；`compare-memory-series` 使用连续任务清单评估跨任务记忆。对照入口保留各次运行的配置、检查、轨迹和补丁。

## CI 使用

`ci` 提供无交互入口和固定产物目录：

```bash
python3 -m coding_agent ci /path/to/repository \
  --task '修复配置读取错误' --check 'python3 -m pytest -q' \
  --output-dir /path/to/agent-artifacts
```

产物包括 `summary.json`、`result.json`、`trace.jsonl`、`diff.patch` 和 `status.txt`。只有任务正常完成且配置的检查通过时返回退出码 0；`ci` 不接受 `ask` 权限模式。

项目提供可手动触发的 [GitHub Actions 工作流](.github/workflows/agent-ci.yml)，从仓库 Secret `DEEPSEEK_API_KEY` 读取凭据，执行任务并上传补丁与运行产物供审阅。

## 项目结构

```text
coding_agent/
├── __main__.py      命令行入口
├── contracts.py     共享数据契约
├── models/          模型服务适配
├── session/         会话、上下文、恢复、记忆与并行执行
├── tools/           文件、终端与 Git 工具
├── sandbox/         Docker 环境与默认镜像
├── harness/         评测任务加载
├── verifier/        独立验证器
└── eval/            评测与对照运行
config/              运行配置
tasks/               评测任务及固定仓库副本
experiments/         实验数据与运行产物
docs/                相关文档
```
