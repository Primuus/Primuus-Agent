# Long-Horizon Coding Agent

本仓库用于实现一个可运行、可验证、可评测的 Coding / Terminal Agent。

当前已完成[第一阶段执行方案](docs/Long-Horizon-Coding-Agent-Phase-1-Execution-Plan.md)中的节点 A 与 B：任务契约和确定性 Agent Loop。Docker Sandbox 与真实模型将在后续节点接入。

## 目前的文件

```text
coding_agent/       Python 包及共享数据契约
coding_agent/harness/ 任务加载、状态、上下文与 Agent Loop
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
