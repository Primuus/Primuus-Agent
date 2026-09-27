# 节点 M：跨任务记忆受控对照

## 条件与结果

同一个临时 Git 仓库从 `color.py = unknown` 开始。先运行任务 A：实现 `Widget color rule: green`，修改隔离副本并通过项目检查，从这次 Trace 自动保存一条修复记忆；原仓库仍保持初始状态。随后写入三条仅关于 `db.py` 的较新项目记录。任务 B 为 `Fix widget color.py`，检查命令同为 `grep -q '^green$' color.py`。

受控模型只读取传入的 Context：看到准确的颜色规则时写入 `green`，否则写入 `red`，然后给出最终回复。三种模式使用相同模型、代码基线、任务、检查、四轮预算和冻结的记忆库，各重复两次。比较期间关闭记忆写入。

| 模式 | 通过 | 平均轮数 | 平均工具调用 | 平均 Token |
|---|---:|---:|---:|---:|
| 关闭 | 0/2 | 3 | 1 | 36 |
| 最近摘要 | 0/2 | 3 | 1 | 36 |
| 任务检索 | 2/2 | 2 | 1 | 26 |

最近摘要只纳入三条较新的 `db.py` 记录；任务检索找到了任务 A 的已检查修复。该实验检验了跨任务提取、记忆选择、上下文注入、项目检查和汇总链路，**不衡量真实模型的泛化收益**。真实模型重复对照可用 README 中的 `compare-memory` 命令运行，需在环境中提供模型密钥。

## 复现

在工程根目录运行以下临时代码；仓库、数据库与原始会话产物在运行结束后自动清理。要保留原始产物，可将 `TemporaryDirectory` 换为自选的运行目录。

```bash
python3 - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from subprocess import run
from time import sleep
import json

from coding_agent.contracts import ModelResponse, ToolCall
from coding_agent.eval.memory_compare import compare_memory
from coding_agent.session.app import RepositorySession
from coding_agent.session.memory import MemoryStore

class WarmupModel:
    model_id = 'controlled-warmup-model-v1'

    def __init__(self):
        self.wrote = False

    def generate(self, messages, tools):
        if not self.wrote:
            self.wrote = True
            return ModelResponse(tool_calls=(ToolCall('write', 'write_file',
                {'path': 'color.py', 'content': 'green\n'}),))
        return ModelResponse(final_message='Widget color rule: green')

class ContextModel:
    model_id = 'controlled-context-model-v1'

    def __init__(self):
        self.wrote = False

    def generate(self, messages, tools):
        if not self.wrote:
            self.wrote = True
            remembered = any('Widget color rule: green' in str(message.get('content'))
                             for message in messages)
            value = 'green\n' if remembered else 'red\n'
            return ModelResponse(
                tool_calls=(ToolCall('write', 'write_file',
                                     {'path': 'color.py', 'content': value}),),
                input_tokens=12, output_tokens=4,
            )
        return ModelResponse(final_message='Done', input_tokens=8, output_tokens=2)

with TemporaryDirectory() as temp:
    root = Path(temp)
    repo = root / 'repo'
    repo.mkdir()
    (repo / 'color.py').write_text('unknown\n')
    run(['git', '-C', str(repo), 'init', '-q'], check=True)
    run(['git', '-C', str(repo), 'add', '.'], check=True)
    run(['git', '-C', str(repo), '-c', 'user.name=Test',
         '-c', 'user.email=test@example.com', 'commit', '-qm', 'init'], check=True)

    config = json.loads(Path('config/default.json').read_text())
    config['memory_dir'] = str(root / 'memory')
    config['memory']['mode'] = 'summary'
    config['max_steps'] = 4
    prior = RepositorySession.create(
        repo, root / 'sessions', WarmupModel(), config, 'auto',
    )
    prior_result = prior.run('Implement Widget color rule: green',
                             ["grep -q '^green$' color.py"])
    assert prior_result['stop_reason'] == 'completed'

    store = MemoryStore(root / 'memory')
    repository = str(repo.resolve())
    assert any(entry.kind == 'fix' for entry in store.list(repository))
    for index in range(3):
        sleep(0.002)
        store.add(repository, 'project', f'Unrelated database note {index}', ['db.py'],
                  {'kind': 'manual', 'ref': f'db-spec-{index}'})

    report = compare_memory(
        repo, 'Fix widget color.py', ["grep -q '^green$' color.py"],
        config, ContextModel, root / 'sessions', root / 'comparison', 2,
    )
    print(json.dumps(report['aggregates'], indent=2))
PY
```
