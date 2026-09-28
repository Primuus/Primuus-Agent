# 节点 N：真实仓库任务集

## 结果

建立了 `tasks/real/real_001`～`real_010`，从 humanize、packaging、boltons 三个开源仓库的真实修复提交中取出修复前的源码。难度分布为 Easy 3 题、Medium 5 题、Long-Horizon 2 题。任务覆盖列表输入、数字格式化、标签生成、需求和标记解析、统计直方图、JSONL、流对象及集合操作。

这一步只建立任务与验证环境。真实模型成功率属于阶段 O，不从参考修复或脚本化接入检查中推断。

## 任务来源

| 任务 | 仓库 | 基线提交 | 原始修复提交 | 难度 | 目标 |
| --- | --- | --- | --- | --- | --- |
| `real_001` | [humanize](https://github.com/python-humanize/humanize) | `bada0f88b4d1` | `ffdf407fdfe1` | Easy | `natural_list` 接受一般迭代器 |
| `real_002` | humanize | `f971127ce7e7` | `ca892b368a53` | Medium | `intword` 大数进位 |
| `real_003` | humanize | `14965a74953e` | `984526c02448` | Easy | `intcomma` 超大整数 |
| `real_004` | [packaging](https://github.com/pypa/packaging) | `b09745046152` | `4e79787a31c9` | Medium | 空平台集合的标签生成 |
| `real_005` | packaging | `0bfc3cea4f9f` | `189a76d54d64` | Medium | 拒绝末尾换行的需求与标记 |
| `real_006` | packaging | `2497782b2bb0` | `5b583e309996` | Medium | 保留标记值中的引号语义 |
| `real_007` | [boltons](https://github.com/mahmoud/boltons) | `805c803ca71d` | `1cdc0e9d36f3` | Easy | 零四分位距直方图 |
| `real_008` | boltons | `435774ef8b10` | `f1034b07ddf7` | Medium | JSONL 文件尾与反向相对定位 |
| `real_009` | boltons | `961dcff3f42e` | `4e5faa3d7e40` | Long-Horizon | spooled 流写入与多字节文本定位 |
| `real_010` | boltons | `efff866a3b66` | `e00c10a80952` | Long-Horizon | 跨模块修复列表边界与批量集合删除 |

每题的 `task.json` 保存完整仓库 URL、40 位 `base_commit`、参考修复提交、描述、难度、环境检查命令、项目检查命令与源码归档 SHA-256。`repo/` 是指定基线提交的 `git archive` 快照，评测运行直接从它复制独立工作区，不依赖远端仓库当前分支，也不会修改原始仓库。humanize 源码包在构建时由 `hatch-vcs` 生成 `_version.py`；三个任务包仅额外放入对应的 `4.16.0` 版本文件，路径和内容记在 `generated_setup_files`，其余文件与基线归档逐字节一致。

Agent 只接收 `task.md` 和 `repo/` 副本。`task.json` 中的参考提交与任务包外的 `verifier.py` 不进入 Agent 容器；容器默认断网，源码快照不带 Git 历史，避免从后续提交读取修复。Verifier 在另一容器中检查工作区快照。各题保留原项目测试作为工作区的一部分；私有 Verifier 才是成功判定依据。

## 环境与评测接入

构建任务镜像：

```bash
docker build -t coding-agent-sandbox:local coding_agent/sandbox
docker build -f tasks/real/Dockerfile -t coding-agent-real-benchmark:20260928 tasks/real
```

真实任务镜像在已有沙箱镜像上增加固定版本的 `pretend`，供 packaging 的项目测试使用。本次校准使用镜像 ID `sha256:4217cbc4df372b696f659c9f25d32dccbc52b4c33ddb8e8c2008c0aa8ae1f163`；实验跨机器重建时应记录实际镜像 ID。任务运行配置位于 [`config/real-benchmark.json`](../../config/real-benchmark.json)：恢复关闭、记忆关闭、容器断网，真实模型默认仍为 DeepSeek `deepseek-flash`。阶段 O 应固定并记录所用镜像 ID 与模型版本，再重复运行。

沿用现有 Evaluation 入口：

```bash
python3 -m coding_agent batch tasks/real --config config/real-benchmark.json
```

任务目录仍使用 v1 任务包契约。一次脚本化接入检查通过 `run_task` 对 `real_003` 写入参考修复，并得到 `verified`；该检查仅证明任务可以走同一 Runner、工具和独立 Verifier，不是模型实验。

## 验收记录

逐题校准结果保存在 [`validation.json`](../../experiments/2026-09-28-real-benchmark/validation.json)：

| 检查 | 结果 |
| --- | --- |
| 任务数与来源仓库数 | 10 题、3 个仓库 |
| 固定基线与源码归档 SHA-256 | 10/10 匹配 |
| 基线独立 Verifier | 10/10 失败，均因目标行为 |
| 应用对应上游修复后的 Verifier | 10/10 通过 |
| 环境检查命令 | 10/10 通过 |
| 修复前原项目检查命令 | 10/10 通过 |
| 同一 Evaluation 接入 | `real_003` 脚本化修复通过 |

校准时参考补丁只应用于临时副本，随后删除。任务包内不含补丁，原始仓库与基线快照均未被修改。阶段 N 的验收已完成；下一步按新计划进入阶段 O，使用真实模型在这 10 题上重复运行基线。
