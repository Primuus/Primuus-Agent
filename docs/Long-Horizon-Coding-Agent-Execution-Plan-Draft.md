# Long-Horizon Coding Agent 项目执行方案（初稿）

> 目标：先实现一个可运行、可评测、可扩展的 Coding / Terminal Agent 原型，用于 Hackathon、科研实习作品集和后续研究。当前阶段不追求功能很广，而是先完成 **Agent Loop + Harness + Sandbox + Verifier + Evaluation** 的最小闭环。

---

## 1. 项目定位

项目暂定方向：

```text
Long-Horizon Coding / Terminal Agent
```

核心问题：

> 如何让一个基于 LLM 的 Coding Agent 在真实代码仓库和终端环境中，经过多步操作后仍然能够稳定完成任务？

第一阶段重点：

```text
Agent Loop
+ Harness
+ Terminal / File Tools
+ Docker Sandbox
+ Verifier
+ Evaluation
```

后续扩展：

```text
Persistent Memory
Failure Recovery
Context Management
Skill Learning
Evolving Agent
```

---

## 2. 整体系统结构

```text
                    User Task
                        │
                        ▼
                ┌──────────────┐
                │    Harness   │
                └──────┬───────┘
                       │
                Build Context
                       │
                       ▼
                ┌──────────────┐
                │     LLM      │
                │ API / Local  │
                └──────┬───────┘
                       │
                    Action
                       │
              ┌────────┼─────────┐
              │        │         │
          read_file  write_file  run_shell
              │        │         │
              └────────┼─────────┘
                       │
                       ▼
                ┌──────────────┐
                │   Sandbox    │
                │ Docker / VM  │
                └──────┬───────┘
                       │
                 Observation
                       │
                       ▼
                  Update State
                       │
                       ▼
                   Verifier
                 ┌────┴────┐
                 │         │
               Fail      Pass
                 │         │
           Retry/Replan    │
                 │         ▼
                 └──────> Finish
                           │
                           ▼
                      Evaluation
```

核心分工：

```text
LLM        = 决定下一步做什么
Harness    = 管理整个执行过程
Tools      = 执行具体动作
Sandbox    = 提供隔离执行环境
Verifier   = 判断任务是否完成
Evaluation = 评价整个 Agent 系统表现
```

---

## 3. 第一阶段：跑通最小闭环

第一版只实现三个 Tool：

```text
read_file(path)
write_file(path, content)
run_shell(command)
```

模型负责：

```text
选择 Tool
生成参数
读取 Observation
决定下一步
决定何时结束
```

Harness 负责：

```text
调用模型
解析 Tool Call
执行 Tool
维护 State
组织 Context
限制最大步数
记录 Trace
```

第一阶段暂时不加入复杂 Planner、Multi-Agent 和长期 Memory。

---

## 4. 模型接入

第一阶段直接使用现成模型 API：

```text
Agent
 ↓
Model Adapter
 ↓
OpenAI / Anthropic / Gemini / Local Endpoint
```

建议统一封装：

```python
class ModelBackend:
    def generate(self, messages, tools):
        ...
```

这样后续更换模型时不需要修改 Agent 主逻辑。

---

## 5. Agent Loop

最小 Loop：

```python
while step < max_steps:
    context = build_context(state)
    action = model.generate(context, tools)
    observation = execute(action)
    state.update(action, observation)

    if verifier.check():
        break
```

每轮流程：

```text
State
 ↓
Build Context
 ↓
Model
 ↓
Action
 ↓
Tool
 ↓
Observation
 ↓
Update State
 ↓
Verifier
```

---

## 6. Harness

Harness 是当前项目最重要的工程模块。

建议目录：

```text
harness/
├── runner.py
├── state.py
├── context.py
├── trace.py
├── retry.py
└── limits.py
```

负责：

```text
Task 初始化
Context 构建
Model 调用
Tool 调度
State 管理
Error Handling
Retry
Timeout
Stop Condition
Trace
```

---

## 7. Sandbox

第一阶段建议使用 Docker：

```text
Host
 │
 │ Agent Harness
 ▼
Docker Sandbox
├── repository
├── Python
├── Git
├── pytest
└── terminal
```

基本限制：

```text
只能访问 workspace
限制运行时间
限制 CPU / Memory
默认不挂载宿主机敏感目录
```

后续再考虑 Network Policy、Secret Isolation、MicroVM。

---

## 8. Verifier

Coding Agent 尽量选择自动可验证任务。

可用：

```text
pytest
build
compiler
linter
output checker
```

例如：

```python
class PytestVerifier:
    def check(self):
        result = run("pytest -q")
        return result.returncode == 0
```

原则：

> 不能只让 Agent 自己判断“我觉得已经修好了”。

---

## 9. Evaluation

从第一版就记录：

```text
success
steps
tool_calls
failed_tool_calls
retries
tokens
latency
```

例如：

```json
{
  "task_id": "task_001",
  "success": true,
  "steps": 14,
  "tool_calls": 18,
  "retries": 2,
  "latency": 93.4
}
```

最终统计：

| Metric | Value |
|---|---:|
| Success Rate | 62% |
| Avg Steps | 18.4 |
| Avg Tool Calls | 23.1 |
| Recovery Rate | 55% |
| Avg Latency | 120s |

---

## 10. Task 设计

第一阶段准备 10～20 个任务，后续扩展到 30～50 个。

建议类型：

```text
修复 Python failing test
修复配置错误
修改 JSON / YAML
修复 import error
分析日志
修复 dependency 问题
补充缺失函数
修复简单 API bug
```

每个任务：

```text
tasks/
└── task_001/
    ├── task.md
    ├── repo/
    └── verifier.py
```

---

## 11. 推荐项目结构

```text
coding-agent/
│
├── agent/
│   ├── agent.py
│   └── prompts.py
├── models/
│   ├── base.py
│   └── api_backend.py
├── harness/
│   ├── runner.py
│   ├── state.py
│   ├── context.py
│   ├── retry.py
│   └── trace.py
├── tools/
│   ├── read_file.py
│   ├── write_file.py
│   └── shell.py
├── sandbox/
│   ├── docker.py
│   └── Dockerfile
├── verifier/
│   ├── base.py
│   └── pytest_verifier.py
├── eval/
│   ├── evaluator.py
│   ├── metrics.py
│   └── results/
├── tasks/
├── config/
│   └── default.yaml
└── README.md
```

---

## 12. 第一版完整运行流程

```text
1. 加载 task.md
2. 创建 Docker Sandbox
3. 将目标 repository 放入 Sandbox
4. 初始化 Agent State
5. Harness 构建 Context
6. 调用 LLM API
7. LLM 返回 Tool Call
8. Harness 执行 Tool
9. 返回 Observation
10. 更新 State / Trace
11. Verifier 检查
12. 未通过 → 回到步骤 5
13. 通过 → 结束任务
14. Evaluation 保存结果
15. 销毁 Sandbox
```

---

## 13. 第二阶段：Failure Recovery

基础闭环跑通后，第一个适合深入的研究点：

```text
Failure-Aware Harness
```

研究问题：

> Agent 在 Tool 失败、命令失败、测试失败和重复行动时，怎样更有效恢复？

加入：

```text
Error Classification
Retry Policy
Rollback
Repeated Action Detection
Alternative Action
```

实验：

```text
Baseline Agent
vs
+ Failure Recovery
```

比较：

```text
Success Rate
Recovery Rate
Steps
Cost
```

---

## 14. 第三阶段：Persistent Memory

可以继续增加：

```text
Persistent Memory
```

保存：

```text
Project Knowledge
Past Failures
Successful Fixes
Common Commands
Repository Structure
```

流程：

```text
Task 1
 ↓
Trajectory
 ↓
Extract Memory
 ↓
Persistent Store

Task 2
 ↓
Retrieve Relevant Memory
 ↓
Context
 ↓
Agent
```

可比较：

```text
No Memory
Raw History Memory
Summarized Memory
Retrieved Episodic Memory
```

---

## 15. 当前阶段暂时不做

为了控制范围，先不做：

```text
Multi-Agent
A2A
复杂 MCP
GUI Agent
Web Agent
强化学习
Self-Evolving
自动 Skill 生成
复杂长期 Memory
```

这些作为后续扩展。

---

## 16. 建议时间安排

### Week 1

```text
LLM API
Tool Calling
Agent Loop
```

目标：Agent 可以调用 `read_file` / `run_shell`。

### Week 2

```text
write_file
Docker Sandbox
State
Trace
```

目标：Agent 可以在 Docker 中修改简单项目。

### Week 3

```text
Verifier
Task Dataset
Evaluation
```

目标：能批量跑 10 个任务并统计成功率。

### Week 4

```text
Failure Analysis
Recovery
README
Demo
```

目标：形成一个可以展示的完整 Coding Agent 项目。

---

## 17. 第一阶段最小成果

```text
✓ 一个自己实现的 Agent Loop
✓ 三个基础 Tool
✓ Docker Sandbox
✓ 自动 Verifier
✓ 10～20 个 Coding Tasks
✓ Trace
✓ Evaluation Script
✓ 实验结果
✓ README
```

这可以同时作为：

```text
Hackathon Project
+
科研实习作品集
+
后续 Agent Research Baseline
```

---

## 18. 核心原则

整个项目尽量坚持：

```text
Small
Measurable
Reproducible
Extensible
```

即：

> 先完成一个“小而完整、可量化”的 Coding Agent 系统，再从 Harness、Memory、Evaluation 或 Evolving Agent 中选择一个点深入。
