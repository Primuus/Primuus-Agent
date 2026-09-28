# 转向 Software Engineering Agent 前的阶段目标

> 项目：Primuus-Agent  
> 当前定位：Long-Horizon Coding Agent / Repository-Level Coding Agent  
> 阶段目标：在正式扩展到 Software Engineering Agent（SEA）之前，先完成真实任务验证、实验体系建立和现有能力收敛，使后续 SEA 扩展建立在稳定、可测量、可复现的基础上。

---

# 1. 当前阶段定位

Primuus-Agent 当前已经具备较完整的 Coding Agent Runtime：

```text
Model Adapter
+
Session Runner
+
Repository Workspace
+
Docker Sandbox
+
Repository Tools
+
Permission
+
Pause / Resume
+
Snapshot / Restore
+
Context Compression
+
Failure Recovery
+
Persistent Memory
+
Hooks / MCP
+
Parallel Task
+
Verifier
+
Evaluation
+
CI Entry
```

目前已经基本完成：

```text
Tool-Calling Agent
        ↓
Coding Agent Baseline
        ↓
Repository-Level Coding Agent
        ↓
Long-Horizon Coding Agent Runtime
```

因此，转向 SEA 前的主要问题已经不是：

```text
还能增加什么 Agent 功能？
```

而是：

```text
现有能力在真实软件工程任务中是否有效？
```

---

# 2. 转向 SEA 前的核心目标

正式进入 SEA 阶段前，需要回答以下四个问题。

## 2.1 Agent 是否能处理真实 Repository Task

当前已有 `task_001 ~ task_012` 可以继续作为回归任务，但还需要增加真实仓库任务。

需要验证：

```text
Repository Understanding
Code Search
Multi-file Modification
Build / Test
Debug
Long-Horizon Execution
```

是否在真实代码仓库中能够稳定运行。

---

## 2.2 当前 Baseline 到底有多强

需要得到一个真实模型、真实仓库、重复运行后的基础结果。

也就是确定：

```text
不使用 Recovery
不使用 Persistent Memory
不使用 Parallel
```

时，当前 Agent 的基础能力。

这个 Baseline 是后续所有实验的参照组。

---

## 2.3 Recovery 和 Memory 是否真的有效

目前 Recovery 和 Persistent Memory 已经实现。

下一步不应优先继续增加功能，而应验证：

```text
Recovery 是否提高真实任务成功率？

Memory 是否降低重复探索和上下文浪费？

这些收益是否值得它们带来的 Token / 时间成本？
```

---

## 2.4 是否已经具备进入 SEA 的工程基础

进入 SEA 前，需要确保以下基础已经稳定：

```text
Session
Workspace
Tool
Permission
Trace
Verifier
Evaluation
Recovery
Memory
```

使后续加入：

```text
Issue
PR
CI Feedback
Code Review
```

时，不需要重新设计底层 Runtime。

---

# 3. 阶段 N：真实 Repository Benchmark

## 3.1 目标

建立第一批真实 Repository Task。

现有小任务保留用于：

```text
Regression Test
```

新的任务用于：

```text
Real Repository Evaluation
```

---

## 3.2 第一批规模

建议：

```text
3 ～ 5 个 Repository
10 个左右真实任务
```

第一轮不需要追求大规模。

重点是：

```text
任务真实
验证明确
能够重复运行
```

---

## 3.3 任务类型

第一批优先选择：

```text
Bug Fix

Multi-file Bug Fix

Small Feature

Configuration Error

Dependency Problem

Build Failure

Test Failure

CLI Behavior Bug

API Behavior Bug
```

避免一开始就选择需要几十个文件修改的大型任务。

---

## 3.4 每个任务的基本要求

每个任务至少包含：

```text
task_id

repository

base_commit

task_description

setup_command

test_command / build_command

verifier

difficulty
```

要求：

```text
初始版本验证失败

存在可确认的正确结果

Agent 看不到参考 Patch

每次运行都从同一个 Commit 开始

Verifier 独立于 Agent
```

---

## 3.5 推荐难度分层

### Easy

```text
1 ～ 2 个主要文件
错误位置相对明确
一个测试入口
```

### Medium

```text
3 ～ 5 个相关文件
需要搜索和定位
需要运行多个检查
```

### Long-Horizon

```text
需要多阶段操作
可能出现失败与重试
需要跨文件理解
上下文明显增长
```

---

## 3.6 阶段 N 验收

完成标准：

```text
✓ 至少 10 个真实 Repository Task

✓ 所有任务固定 base commit

✓ 初始状态均无法通过最终验证

✓ 每个任务都有独立 Verifier

✓ 任务能够自动重建执行环境

✓ 可以接入当前 Evaluation

✓ 原始 Repository 不被 Agent 修改
```

---

# 4. 阶段 O：真实模型 Baseline

## 4.1 目标

建立当前 Agent 的真实能力基线。

Baseline 配置：

```text
Recovery = OFF

Memory = OFF

Parallel = OFF
```

保留：

```text
Session Runner

Repository Tools

Sandbox

Verifier

Evaluation
```

---

## 4.2 实验控制

以下条件必须固定：

```text
Model

Model Version

Repository Commit

Task Version

Tool Set

Max Steps

Token Budget

Timeout

Sandbox

Network Policy
```

每个任务至少重复：

```text
3 次
```

条件允许时：

```text
5 次
```

---

## 4.3 基础指标

记录：

```text
Success Rate

Steps

Tool Calls

Failed Tool Calls

Tokens

Latency

Human Intervention

Stop Reason
```

同时保留：

```text
trace.jsonl

diff.patch

result.json

config.json
```

---

## 4.4 阶段 O 验收

```text
✓ 所有真实任务使用真实模型运行

✓ 每个任务至少重复 3 次

✓ 保存完整 Trace

✓ 保存最终 Diff

✓ 保存检查结果

✓ 生成 Baseline 汇总报告
```

---

# 5. 阶段 P：Failure Taxonomy

## 5.1 目标

不只统计“成功 / 失败”，而是明确：

```text
Agent 为什么失败？
```

后续研究方向必须从真实失败中产生。

---

## 5.2 初始失败分类

建议使用：

```text
Repository Understanding Failure

Code Search Failure

Wrong File Selection

Incorrect Edit

Tool Misuse

Build Failure

Test Failure

Test Result Misinterpretation

Repeated Action

Context Loss

Premature Finish

Verification Failure

Budget Exhaustion

Model Service Failure

Environment Failure
```

---

## 5.3 每个失败案例记录

至少记录：

```text
Task ID

Run ID

Failure Category

Critical Step

Relevant Trace

Final Diff

Observed Cause

Potential Recovery Point
```

---

## 5.4 最终输出

得到类似：

```text
总失败：24

Repository Understanding    6
Incorrect Edit              5
Test Failure Recovery       4
Repeated Action             3
Context Loss                3
Premature Finish            2
Environment Failure         1
```

这样才能确定下一阶段真正应该优化什么。

---

## 5.5 阶段 P 验收

```text
✓ 所有 Baseline 失败案例完成分类

✓ 每类失败有代表性 Trace

✓ 能定位至少一个主要失败模式

✓ 后续实验能够针对该失败模式展开
```

---

# 6. 阶段 Q：Recovery 真实对照实验

## 6.1 目标

验证当前 Failure Recovery 机制在真实 Repository Task 上是否有效。

不是继续加入 Recovery 功能。

而是比较：

```text
Recovery OFF
        vs
Recovery ON
```

---

## 6.2 保持一致的条件

```text
Model

Task

Repository Commit

Token Budget

Max Steps

Tool Set

Environment
```

唯一变量：

```text
Recovery
```

---

## 6.3 重点指标

比较：

```text
Success Rate

Recovery Rate

Steps

Tool Calls

Tokens

Latency

Repeated Actions

Human Intervention
```

同时记录：

```text
Recovery 成功案例

Recovery 失败案例

Recovery 增加的成本
```

---

## 6.4 重点问题

需要回答：

```text
Recovery 是否提高成功率？

它主要解决哪类失败？

哪些失败它无法解决？

是否出现过度 Retry？

是否显著增加 Token？

是否显著增加延迟？
```

---

## 6.5 阶段 Q 验收

```text
✓ Recovery ON/OFF 成对实验完成

✓ 每个任务重复运行

✓ 有成功率与成本对比

✓ 有代表性恢复轨迹

✓ 能说明 Recovery 的适用边界
```

---

# 7. 阶段 R：Persistent Memory 真实对照实验

## 7.1 目标

验证 Persistent Memory 是否能帮助同一个 Repository 上的连续任务。

Memory 的目标不只是：

```text
记住聊天内容
```

而是减少：

```text
重复 Repository Exploration
```

---

## 7.2 实验场景

选择同一个 Repository：

```text
Repository A

Task 1
Task 2
Task 3
Task 4
Task 5
```

任务之间共享部分工程知识：

```text
Build Command

Test Command

Repository Structure

Coding Convention

Known Failure Pattern

Previously Solved Issue
```

---

## 7.3 对照模式

比较：

```text
Memory OFF

Summary Memory

Retrieved Memory
```

---

## 7.4 指标

除了常规指标：

```text
Success Rate

Steps

Tool Calls

Tokens

Latency
```

增加：

```text
Repeated Exploration

Repository Discovery Commands

Repeated File Reads

Time To First Useful Edit
```

重点观察：

> Memory 是否让 Agent 更快进入有效工作状态。

---

## 7.5 Memory Pollution

额外加入少量：

```text
Stale Memory

Wrong Memory

Conflicting Memory
```

观察 Agent 是否被错误历史信息影响。

第一轮只需要记录现象，不急于设计复杂 Memory Validation。

---

## 7.6 阶段 R 验收

```text
✓ 同一 Repository 上完成连续任务实验

✓ 三种 Memory Mode 完成对照

✓ 记录重复探索指标

✓ 记录 Memory 带来的收益和成本

✓ 至少验证一个错误 / 过期 Memory 场景
```

---

# 8. 阶段 S：当前 Runtime 工程收敛

真实实验过程中同步检查现有工程结构。

这一阶段不是大规模重构，而是：

```text
为进入 SEA 做必要的工程整理
```

---

## 8.1 重点检查

当前核心模块：

```text
coding_agent/session/

coding_agent/tools/

coding_agent/eval/

coding_agent/models/

coding_agent/sandbox/
```

需要确认边界清晰。

重点关注：

```text
Session Runner 是否保持单一职责

RepositorySession 是否过度膨胀

CLI 是否承担过多业务逻辑

Evaluation 是否能复用同一 Runner

Tool 是否统一经过权限与事件接口

Memory / MCP / Hooks 是否保持可选扩展
```

---

## 8.2 当前不要求进行的工作

暂时不需要：

```text
大规模目录重构

更换整个架构

引入复杂框架

为了抽象而抽象
```

只有当后续 Issue / PR / CI 接入明显让：

```text
session/app.py

__main__.py
```

继续膨胀时，再拆分 Application Service。

---

## 8.3 阶段 S 验收

```text
✓ Runtime 主循环稳定

✓ 普通仓库会话和 Evaluation 共用执行内核

✓ 新实验不需要修改 Runner 核心流程

✓ Trace / Result Schema 稳定

✓ 现有回归任务全部通过
```

---

# 9. SEA 转向前最终验收

只有以下目标基本完成后，再正式进入 SEA Workflow。

---

## 9.1 Engineering Baseline

```text
✓ Agent 能在真实 Repository 上工作

✓ 能处理跨文件任务

✓ 能运行真实 Test / Build

✓ 能输出稳定 Diff

✓ 能保留完整 Session Trace
```

---

## 9.2 Evaluation Baseline

```text
✓ 至少约 10 个真实 Repository Task

✓ 每个任务有固定 Commit

✓ 有独立 Verifier

✓ 真实模型重复运行

✓ 有 Baseline 成功率

✓ 有 Failure Taxonomy
```

---

## 9.3 Reliability Evidence

```text
✓ Recovery ON/OFF 有真实对照

✓ Memory 不同模式有真实对照

✓ 能说明收益

✓ 能说明成本

✓ 能说明失败边界
```

---

## 9.4 Runtime Stability

```text
✓ Session 可持久化

✓ Pause / Resume 稳定

✓ Snapshot / Restore 稳定

✓ Permission 稳定

✓ Sandbox 稳定

✓ Event Journal 稳定

✓ Evaluation 可复现
```

---

# 10. 完成这些目标后再进入 SEA

完成上述阶段后，项目正式进入：

```text
Software Engineering Agent
```

此时才开始加入：

```text
Issue
 ↓
Planning
 ↓
Repository Modification
 ↓
Test / Build
 ↓
PR Artifact
 ↓
CI Feedback
 ↓
Revision
 ↓
Review Feedback
```

也就是：

```text
Coding Task Agent
        ↓
Repository Agent
        ↓
Reliable Long-Horizon Agent
        ↓
Software Engineering Agent
```

---

# 11. 当前执行顺序

推荐严格按以下顺序：

```text
N. 真实 Repository Benchmark

        ↓

O. 真实模型 Baseline

        ↓

P. Failure Taxonomy

        ↓

Q. Recovery Ablation

        ↓

R. Memory Ablation

        ↓

S. Runtime 工程收敛

        ↓

SEA
```

其中：

```text
N + O + P
```

优先级最高。

因为在真实 Baseline 和 Failure Taxonomy 出来之前，不应该继续凭感觉决定下一个研究功能。

---

# 12. 当前最近的任务

下一步直接执行：

```text
选择 3 ～ 5 个小型真实 Repository
        ↓
构建约 10 个真实 Repository Task
        ↓
固定 Commit 和 Verifier
        ↓
关闭 Recovery / Memory
        ↓
真实模型重复运行
        ↓
得到 Baseline
        ↓
整理 Failure Taxonomy
```

完成这一轮后，再决定 Recovery 和 Memory 实验的具体任务集。

---

# 13. 转向 SEA 前的研究问题

这一阶段可以统一围绕：

> **当前 Long-Horizon Coding Agent 在真实 Repository 任务中为什么失败，以及 Harness 中的 Recovery、Memory 和 Context 机制能否提高其可靠性？**

这也是后续向 SEA 扩展时最重要的基础问题。

SEA 阶段关注的是：

```text
完整软件工程 Workflow
```

而 SEA 前这一阶段关注的是：

```text
让 Coding Agent 在真实 Repository 中先稳定地工作，并证明哪些机制真的有效。
```
