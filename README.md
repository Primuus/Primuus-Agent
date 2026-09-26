# Long-Horizon Coding Agent

本仓库用于实现一个可运行、可验证、可评测的 Coding / Terminal Agent。

当前已完成[第一阶段执行方案](docs/Long-Horizon-Coding-Agent-Phase-1-Execution-Plan.md)中的节点 A～C、E、F，并建立了 10 个任务。OpenAI 兼容模型后端已实现；实际模型服务联通和真实模型评测仍待完成。

## 目前的文件

```text
coding_agent/       Python 包及共享数据契约
coding_agent/harness/ 任务加载、状态、上下文与 Agent Loop
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

预期退出码为非零。未来的 Agent 应修复 `calculator.py`，使同一验证器返回零退出码。

Docker 工具使用前构建本地镜像：

```bash
docker build -t coding-agent-sandbox:local -f coding_agent/sandbox/Dockerfile .
```

## 运行任务

接入支持 Chat Completions 工具调用的模型服务后，在运行环境中设置 `OPENAI_MODEL`、`OPENAI_API_KEY`（无密钥的本地服务可不设）和可选的 `OPENAI_BASE_URL`。密钥不会写入仓库或运行结果。

```bash
python3 -m coding_agent run tasks/task_001
python3 -m coding_agent batch tasks
```

每次运行的 `trace.jsonl`、`result.json` 和 `config.json` 保存在 `runs/<run_id>/`；批量汇总保存为 `runs/batch-<时间戳>.json`。`runs/` 已加入 `.gitignore`。

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

每个任务都包含 `task.md`、初始 `repo/` 和仅供 Harness 调用的 `verifier.py`。10 个任务均已确认初始版本验证失败、临时修复版本验证通过。用预设修复动作运行整条批量链路时，10 个任务全部通过，平均每任务 1 步、1 次工具调用；这只用于检查系统集成，**不是模型性能实验结果**。检查使用的临时文件已清理，任务 Verifier 属于评测数据并保留。
