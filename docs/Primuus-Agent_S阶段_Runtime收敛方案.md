# Primuus-Agent：S 阶段 Runtime 收敛方案

> 项目：Primuus-Agent  
> 当前定位：Long-Horizon Coding Agent / Repository-Level Coding Agent  
> 当前阶段：S — Runtime Convergence  
> 目标：完成 Long-Horizon Runtime 的工程收敛，为后续 Software Engineering Agent（SEA）阶段提供稳定底座。

---

# 1. 当前项目进度

当前整体阶段已经推进到：

```text
N. Real Repository Benchmark        ✅ 完成
        ↓
O. Real Model Baseline              ✅ 完成
        ↓
P. Failure Taxonomy                 ✅ 完成
        ↓
Q. Recovery OFF / ON Ablation       ✅ 完成
        ↓
R. Persistent Memory Ablation       ✅ 完成
        ↓
S. Runtime Convergence              🔄 当前阶段
        ↓
SEA Workflow                        ⏳ 尚未进入
```

目前 S 阶段已经完成或基本具备：

```text
Requirement-level Planning
Action Review
Progress Review
Context Compression
Continuation Notes
Source Snapshot
Tool Evidence
Behavior Evidence
Project Check Cache
Final Check Refresh
Plan Handoff
Pause / Resume
Snapshot / Restore
Failure Recovery
Trace Replay
```

因此，当前问题已经不是继续增加更多 Agent 功能，而是：

> **已有机制是否能够在真实跨文件 Long-Horizon Coding Task 中形成稳定闭环。**

---

# 2. S 阶段当前真正存在的问题

## 2.1 Plan State 与 Agent 实际工作状态存在漂移

当前 Runtime 使用显式 Plan：

```text
Requirement A -> in_progress
Requirement B -> pending
Requirement C -> pending
```

理论上 Agent 应始终围绕当前 `in_progress` Requirement 工作。

但真实跨文件任务中出现过：

```text
Plan:
Requirement A = 当前任务

Agent:
调查 A
  ↓
修改 A
  ↓
开始读取 Requirement B 对应文件
  ↓
实际上已经开始处理 B

但 Plan 仍然：
Requirement A = in_progress
```

这会导致：

```text
Action Review
Progress Review
Context Filtering
Evidence Selection
Next Action
```

全部仍然围绕旧 Requirement。

核心问题：

> **Execution State 与 Explicit Plan State 没有完全同步。**

---

## 2.2 “调查 → 编辑”已有改善，但“子问题 → 下一子问题”尚未稳定

早期主要失败模式为：

```text
Search
 ↓
Read
 ↓
Probe
 ↓
Read
 ↓
继续调查
 ↓
Token Budget Exhaustion
 ↓
没有 Patch
```

目前 Runtime 已经能更积极地产生真实 Edit。

但新的瓶颈变成：

```text
Requirement A
 ↓
调查
 ↓
编辑
 ↓
行为验证
 ↓
部分满足要求
 ↓
无法稳定确认 A 已完成
 ↓
不能干净切换 Requirement B
```

因此现在需要解决的不是单纯的：

```text
Make Edit Earlier
```

而是：

```text
Local Progress
    ↓
Requirement Completion
    ↓
Plan Handoff
    ↓
Global Task Progress
```

---

## 2.3 Completion Judgment 仍需彻底收敛

已有真实实验证明：

```text
Existing Tests Pass
        ≠
User Requirement Satisfied
```

因此不能使用：

```text
pytest passed
```

作为唯一完成条件。

当前 Completion 应依赖：

```text
Requirement Completed
        +
Valid Behavior Evidence
        +
Current Patch Checks Passed
        +
Evidence / Check 与当前 Patch 一致
```

实际运行中还出现过以下问题：

- 旧失败证据覆盖新成功证据；
- Shell 行为证据对应旧 Patch；
- Restore 后仍保留旧 Evidence；
- 最后一次 Shell 使项目检查失效；
- Final Report 漏掉已通过的新 Evidence；
- 测试脚本自身错误被误认为目标代码缺陷。

因此真正需要保证的是：

> **Evidence 属于哪个 Requirement、哪个 Patch、哪个时间点，以及它当前是否仍有效。**

---

## 2.4 Context Continuity 已具备，但任务总成本仍然较高

当前已经具备：

```text
Context Compression
Working Notes
Source Snapshots
read_tool_output
Active Requirement Filtering
```

局部上下文已经可以明显减少重复内容。

但真实跨文件任务仍然出现过：

```text
80 rounds
500k+ Input Tokens
最终仍未完成
```

这说明问题已经不主要是：

```text
单次 Context 太长
```

而是：

```text
无效工作轮数过多
×
每轮 Context 重复输入
=
巨大累计 Token
```

因此后续不应继续只依靠：

```text
24000 chars
 ↓
20000 chars
 ↓
16000 chars
```

来解决成本问题。

真正需要减少的是：

> **无效 Search / Read / Probe / Re-check 的轮数。**

---

## 2.5 存在针对单个跨文件任务过拟合 Runtime 的风险

当前 S 阶段大量优化来自同一个跨文件 Long-Horizon Task。

流程长期是：

```text
运行 real_010
 ↓
发现 Failure
 ↓
修改 Runtime
 ↓
重新运行 real_010
 ↓
发现另一个 Failure
 ↓
继续修改 Runtime
```

这种方式在早期非常有价值，但如果持续下去，可能导致：

```text
Runtime
    ↓
非常适合 real_010

但不一定：
    ↓
泛化到其他 Long-Horizon Repository Task
```

因此 S 后期必须进入：

```text
Runtime Freeze
        ↓
Independent Validation
```

不能继续无限针对单一任务调机制。

---

## 2.6 最新 Runtime 修正仍缺少最终 Live Validation

当前最新机制已经包括：

```text
Requirement-level Action Review
Plan Handoff
Behavior Evidence
Final Check Refresh
Active Requirement Context Filtering
Recent Shell Evidence
Patch Timing
Rollback Evidence Invalidation
```

其中很多已经通过：

```text
Trace Replay
Controlled Scenario
Focused Validation
```

但真正重要的验收仍然是：

```text
完整真实模型
+
真实 Repository
+
真实跨文件 Task
+
Hidden Verifier
```

因此当前最重要的下一步不是继续增加机制，而是：

> **冻结当前 Runtime，重新执行真实跨文件任务。**

---

# 3. S 阶段应该收敛为四个 Runtime Invariant

后续不要继续按照无限增加 `S4.x` 功能的方式推进。

建议把 S 阶段最终收敛为四个明确的不变量。

---

# 4. Invariant A：Requirement State Consistency

目标：

```text
Agent 当前主要工作的 Requirement
=
Plan 中 in_progress Requirement
```

如果当前：

```text
Requirement A = in_progress
Requirement B = pending
```

但 Agent 开始：

```text
read B.py
edit B.py
run behavior check for B
```

Runtime 应主动发现：

```text
Plan Drift
```

并触发：

```text
Plan Handoff Review
```

要求先判断：

```text
A 是否已经完成？

是：
A -> completed
B -> in_progress

否：
回到 A

或者：
重新明确 A 的 Next Action
```

不能允许：

```text
模型实际工作在 B
Runtime 仍认为当前任务是 A
```

## 验收条件

```text
✓ 一个 Requirement 同时只有一个 in_progress
✓ 切换 pending Requirement 前显式更新 Plan
✓ Action Review 始终针对实际当前 Requirement
✓ Context Filtering 与当前 Requirement 一致
```

---

# 5. Invariant B：Evidence Validity

每个 Requirement 完成时，必须存在真实行为证据：

```text
Requirement
    ↓
Behavior Evidence
    ↓
Tool Call ID
    ↓
Command / Output / Exit Code
    ↓
Patch State
```

例如：

```text
Requirement A
evidence = shell-call-52
```

并记录：

```text
shell-call-52
exit_code = 0
source_patch = abc123
after_latest_edit = true
after_latest_restore = true
```

## Evidence 失效条件

如果之后发生：

```text
edit_file()
write_file()
restore()
rollback()
```

并影响该 Requirement 对应源码，则旧 Evidence 必须：

```text
stale / invalid
```

不能继续作为完成依据。

## 验收条件

```text
✓ completed Requirement 必须存在有效 Evidence
✓ Evidence 晚于相关源码最后修改
✓ Restore 后旧 Evidence 自动失效
✓ Rollback 后 Evidence 状态与 Workspace 同步
✓ Final Report 不引用失效 Evidence 作为当前事实
```

---

# 6. Invariant C：Completion Correctness

任务只有满足：

```text
All Requirements Completed
        &&
Each Requirement Has Valid Evidence
        &&
Current Patch Checks Passed
        &&
Checks Correspond To Current Patch
```

才允许：

```text
completed
```

以下情况都不能算完成：

```text
LLM 说 Done
```

```text
Existing Tests Passed
```

```text
历史 Patch 上 Checks Passed
```

```text
Plan 仍有 pending / in_progress
```

```text
Behavior Evidence 已 stale
```

对应终态应是：

```text
final_unverified
max_steps
token_budget
model_error
...
```

而不是伪造完成。

---

# 7. Invariant D：Context Continuity

Context Compression 前后必须保留：

```text
Current Requirement
Hypothesis
Next Action
Relevant Source Evidence
Current Patch
Relevant Behavior Evidence
Current Project Check State
```

但完成的旧 Requirement 不应继续长期携带：

```text
大量源码
长 Shell Output
旧失败
重复搜索结果
旧推理
```

理想结构：

```text
Completed Requirement A
    ↓
保留：
简短状态
Evidence Reference

Current Requirement B
    ↓
保留：
源码证据
Hypothesis
Next Action
Behavior Evidence
最新 Tool Result
```

目标不是：

```text
保存更多上下文
```

而是：

> **只保存继续完成当前任务所需要的上下文。**

---

# 8. 接下来应该如何执行

## Step 1：冻结当前 Runtime

以当前最新 Runtime 为候选版本。

暂时停止：

```text
新 Planning 架构
新 Memory
新 Recovery
新 MCP
新 Tool
Multi-Agent
Issue / PR
CI Feedback Agent
```

只验证现有闭环。

---

## Step 2：重新执行 real_010 一次

保持固定：

```text
Repository Commit
Task
Hidden Verifier
Model
Docker Image
Tool Set
Runtime Config
```

重点记录：

```text
Plan initialization

Requirement A first investigation

Requirement A first edit

Requirement A behavior evidence

Requirement A completed

Plan handoff A -> B

Requirement B first investigation

Requirement B first edit

Requirement B behavior evidence

Requirement B completed

All plan complete

Final project check refresh

Final response
```

理想 Trace：

```text
Plan A
 ↓
Investigate A
 ↓
Edit A
 ↓
Behavior A Pass
 ↓
A Completed
 ↓
Plan Handoff

Plan B
 ↓
Investigate B
 ↓
Edit B
 ↓
Behavior B Pass
 ↓
B Completed
 ↓
All Plan Complete
 ↓
Current Patch Checks
 ↓
Final
```

---

# 9. 如果 real_010 再失败，如何判断是否继续修改 Runtime

非常重要：

> **并不是所有失败都需要继续修改 Runner。**

## 属于 Runtime Failure

以下情况需要继续修：

```text
Plan 与实际工作漂移
Context Compression 丢失当前 Requirement
Evidence 使用旧 Patch
Restore 后旧 Evidence 仍有效
Current Checks 错误复用
Plan 未完成却 completed
Final Report 与 Trace 事实不一致
```

## 属于 Model Capability Failure

以下情况通常不应该继续修改 Runtime：

```text
模型理解代码错误
模型选择错误算法
模型修改逻辑有 Bug
Hidden Verifier 发现算法本身不正确
模型在正确工具与正确状态下作出错误决策
```

S 阶段目标不是：

```text
让 DeepSeek 在所有 Benchmark 上 100% 通过
```

而是：

```text
保证 Runtime 的执行状态机正确、可恢复、可验证、可收尾
```

---

# 10. Step 3：real_010 通过后进行独立 Long-Horizon 验证

不能只在 real_010 上宣布成功。

建议使用：

```text
real_009
```

作为第二个 Long-Horizon Task。

目的不是要求与 real_010 完全相同的执行路径，而是验证：

```text
Requirement State
Evidence
Completion
Context Continuity
```

这些 Runtime Invariant 能在不同 Repository Structure 下继续成立。

---

# 11. Step 4：构建 Deterministic Runtime Regression Suite

真实 LLM 运行成本高、随机性强。

S 最终工程验收应该大量依赖确定性测试。

建议使用：

```text
Fake Model
Mock Response
Recorded Trace Replay
Temporary Git Repository
Controlled Docker Scenario
```

覆盖以下场景：

```text
Plan initialization

Plan handoff

Action review

Progress review

Patch change -> Evidence stale

Restore -> Evidence stale

Rollback -> Evidence stale

Shell -> Project checks stale

All plan complete -> refresh checks

Plan incomplete -> final_unverified

Behavior evidence missing -> cannot complete

Context compaction

Pause / Resume

Pending tool interruption

Snapshot / Restore

Event replay

Final report evidence reconstruction
```

目标：

```text
Runtime Contract Regression
=
100% deterministic pass
```

---

# 12. Token Budget 的最终处理方式

不建议现在直接重新使用固定：

```text
max_tokens = 120000
```

逼真实跨文件任务通过。

因为这会重新混合两个不同问题：

```text
Runtime Correctness
```

和：

```text
Runtime Efficiency
```

正确顺序：

## Phase 1：Correctness Run

```text
max_steps = 80
max_tokens = null
```

先确保：

```text
Requirement
 ↓
Evidence
 ↓
Handoff
 ↓
Completion
```

完整跑通。

得到一次真实成功成本：

```text
Successful Runtime Cost = X
```

## Phase 2：Bounded Run

根据真实成功 Trace 设置：

```text
Budget ≈ X + 20% ~ 30% Margin
```

重新执行一次。

这样 Budget 来自：

```text
成功运行证据
```

而不是人为猜一个数字。

---

# 13. S 阶段最终验收标准

## 13.1 Runtime 工程验收

```text
✓ SessionRunner 主循环稳定
✓ RepositorySession 与 Evaluation 共用执行内核
✓ Pause / Resume 正确
✓ Snapshot / Restore 正确
✓ Pending Tool 恢复正确
✓ Trace Replay 正确
✓ Result Schema 稳定
✓ Deterministic Regression 全通过
```

---

## 13.2 Long-Horizon 执行验收

最低要求：

```text
✓ 至少 1 个真实跨文件 Long-Horizon Task 完整成功

✓ Requirement 按顺序推进

✓ 至少发生 1 次真实 Plan Handoff

✓ 每个 completed Requirement 有有效 Behavior Evidence

✓ 最终 Project Checks 对应当前 Patch

✓ Hidden Verifier 通过

✓ 无人工介入
```

更推荐：

```text
real_010
至少获得 1 个干净成功样本

+

real_009
至少获得 1 个独立成功样本
```

如果预算允许，可进一步：

```text
real_010 × 2~3
至少 2 次成功
```

---

## 13.3 成本验收

不再设置：

```text
Token 必须下降 30%
```

这种缺乏依据的硬指标。

更合理的是：

```text
✓ 不存在长时间无进展探索循环

✓ Requirement 切换后旧 Context 大幅退出

✓ 成功运行得到明确总成本

✓ 能据成功 Trace 建立合理 Token Budget

✓ 在该 Budget 下至少完成一次有界复测
```

---

# 14. S 阶段停止条件

S 阶段不应等到：

```text
10 / 10 Benchmark 全通过
```

才结束。

那已经是在优化：

```text
Benchmark Score
```

而不是：

```text
Runtime Convergence
```

S 应结束在：

```text
Runtime State Machine 正确
        +
Requirement Continuity 正确
        +
Plan Handoff 稳定
        +
Evidence 与 Patch 一致
        +
Completion Judgment 正确
        +
真实跨文件任务证明该链路能够工作
```

此后如果某个任务失败原因是：

```text
LLM 写错算法
```

应该记录为：

```text
Model Capability Failure
```

而不是继续无限修改 Runtime。

---

# 15. 推荐最终执行顺序

```text
Freeze 当前 Runtime
        ↓
real_010 Live Run × 1
        ↓
检查 Runtime Invariant

如果出现 Runtime Failure
        ↓
只修对应 Invariant
        ↓
重新 real_010

如果 real_010 完整通过
        ↓
Freeze Runtime API / Trace Schema
        ↓
real_009 Independent Validation
        ↓
Deterministic Regression Suite
        ↓
得到 Successful Runtime Cost
        ↓
设置合理 Bounded Budget
        ↓
Bounded Run × 1
        ↓
S 阶段完成
        ↓
进入 SEA
```

---

# 16. 进入 SEA 前的最终项目状态

S 阶段完成后，Primuus-Agent 应达到：

```text
Tool-Calling Agent
        ↓
Repository-Level Coding Agent
        ↓
Long-Horizon Coding Agent
        ↓
Reliable Requirement-Level Runtime
```

然后再进入：

```text
Software Engineering Agent
```

增加：

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
Code Review Feedback
```

---

# 17. 当前最重要的原则

当前阶段不再以：

```text
还能加入什么功能？
```

作为主要问题。

而应该改成：

```text
现有 Runtime 是否已经形成：

Requirement
    ↓
Evidence
    ↓
Edit
    ↓
Verification
    ↓
Plan Handoff
    ↓
Completion

这一稳定闭环？
```

只有这个闭环在真实跨文件任务中得到验证，S 阶段才算真正收敛。
