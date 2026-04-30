# SWE-bench 使用说明

这份说明覆盖 MT-Agent 对接 SWE-bench Lite 的完整流程：

1. 准备环境
2. 预拉取 Lite 需要的仓库和 commit
3. 生成 predictions
4. 在 SWE-bench 官方 harness 里评测
5. 查看结果

## 目录约定

下面的例子默认你在服务器上使用这两个目录：

- `MT-Agent`: `${HOME}/projects/MT-Agent`
- `SWE-bench`: `${HOME}/projects/SWE-bench`

如果你的实际目录不同，修改对应 shell 脚本顶部变量即可。

## 一、环境准备

### 1. MT-Agent 环境

进入 MT-Agent 项目目录：

```bash
cd ~/projects/MT-Agent
```

安装依赖：

```bash
uv sync
```

如果你还没有 `datasets`，补上：

```bash
uv add datasets
```

### 2. Hugging Face 缓存

建议把缓存放到大磁盘目录，例如：

```bash
export HF_HOME="~/.cache/huggingface"
export HF_DATASETS_CACHE="~/.cache/huggingface/datasets"
export TRANSFORMERS_CACHE="~/.cache/huggingface"
export XDG_CACHE_HOME="~/.cache"
mkdir -p ~/.cache/huggingface/datasets
```

### 3. LLM 环境变量

MT-Agent 需要你自己的模型配置，例如：

```bash
export LLM_API_KEY="your_api_key"
export LLM_BASE_URL="your_base_url"
export MODEL_NAME="deepseek-v4-pro"
```

## 二、脚本说明

当前脚本有三类：

- `scripts/swebench-lite-prefetch.sh`
  预拉取 Lite 用到的仓库和 base commit
- `scripts/swebench-lite-predic.sh`
  生成 `predictions.jsonl`
- `scripts/swebench-lite-eval.sh`
  调用 SWE-bench 官方 harness 跑评测

核心 Python 入口：

- `scripts/swebench_generate_predictions.py`

## 三、prediction 和 evaluation 的关系

整个流程分两段：

### 1. prediction 阶段

这一步由 MT-Agent 完成，负责：

- 读取数据集中的 instance
- 进入对应仓库
- reset 到该 instance 的 `base_commit`
- 让 Agent 改代码
- 导出 `git diff --binary`
- 写成 `predictions.jsonl`

这一步不依赖 SWE-bench 官方 Docker harness。

### 2. evaluation 阶段

这一步由 SWE-bench 官方 harness 完成，负责：

- 读取 `predictions.jsonl`
- 启动 Docker 容器
- 应用 patch
- 跑测试
- 统计 `resolved / unresolved / errors`

所以当前建议是：

- prediction：直接在宿主机跑
- evaluation：在 `SWE-bench` 仓库里跑官方 harness

## 四、先预拉取 repo

为了避免批量跑的时候因为网络中断而失败，先执行预拉取脚本：

```bash
cd ~/projects/MT-Agent
bash scripts/swebench-lite-prefetch.sh
```

这个脚本会做这些事情：

1. 读取 `SWE-bench/SWE-bench_Lite` 的 `test` split
2. 找出涉及到的 repo
3. clone 到 `.swebench/repos`
4. fetch 对应 commit
5. 检查每个 instance 的 `base_commit` 是否已经在本地

脚本默认会预拉取整个 Lite `test` 集合。

如果你只想先拉少量样例，可以修改：

- `LIMIT`
- `INSTANCE_IDS`

位置在：

- [swebench-lite-prefetch.sh](/Users/chenclay/Documents/code/projects/MT-Agent/scripts/swebench-lite-prefetch.sh)

## 五、生成 predictions

预拉取完成后，执行 prediction：

```bash
cd ~/projects/MT-Agent
bash scripts/swebench-lite-predic.sh
```

这个 shell 会调用：

```bash
uv run python scripts/swebench_generate_predictions.py ...
```

默认行为：

- 使用 `SWE-bench/SWE-bench_Lite`
- 使用 `test` split
- repo 根目录是 `.swebench/repos`
- `OFFLINE_REPOS=1`

`OFFLINE_REPOS=1` 的含义：

- 只使用本地 repo
- 不再主动 clone / fetch
- 如果本地缺 repo 或缺 commit，会直接报错

这正好和预拉取脚本配套使用。

### 单题示例

如果你只跑一个 instance，例如 `sympy__sympy-20590`，把脚本里的：

```bash
INSTANCE_IDS=()
```

改成：

```bash
INSTANCE_IDS=("sympy__sympy-20590")
```

然后执行：

```bash
bash scripts/swebench-lite-predic.sh
```

### 多题示例

如果你想小批量跑 10 题，可以设置：

```bash
LIMIT=10
INSTANCE_IDS=()
```

然后执行：

```bash
bash scripts/swebench-lite-predic.sh
```

### 输出文件

prediction 结束后，默认输出：

```bash
predictions/mt-agent-lite.jsonl
```

文件里每一行对应一个实例，主要包含：

- `instance_id`
- `model_name_or_path`
- `model_patch`

## 六、运行官方评测

进入 SWE-bench 仓库：

```bash
cd ~/projects/SWE-bench
```

执行：

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name SWE-bench/SWE-bench_Lite \
  --predictions_path /home/yangchen/projects/MT-Agent/predictions/mt-agent-lite.jsonl \
  --max_workers 1 \
  --run_id mt-agent-lite
```

或者直接使用封装好的 shell：

```bash
cd ~/projects/MT-Agent
bash scripts/swebench-lite-eval.sh
```

这个脚本会切到 `${HOME}/projects/SWE-bench`，然后调用官方 harness。

### 这里的 Docker 是什么作用

`run_evaluation` 会自动调用 Docker。

它会在容器里：

- 准备测试环境
- 应用 patch
- 跑测试
- 生成结果

你只需要保证运行 harness 的机器上 Docker 可用。

## 七、如何看结果

评测结束后，终端里通常会看到：

```text
Instances resolved: X
Instances unresolved: Y
Instances with errors: Z
```

其中最关键的是：

- `resolved`
- `resolution rate = resolved / submitted`

还会生成几个结果和日志目录：

### 1. 汇总报告

当前目录下会出现类似文件：

```bash
deepseek-reasoner.mt-agent-lite.json
```

这个文件名通常由：

- `MODEL_NAME`
- `run_id`

组合而成。

### 2. 评测结果目录

一般在 SWE-bench 仓库下面：

```bash
evaluation_results/
```

### 3. 运行日志目录

一般在：

```bash
logs/run_evaluation/
logs/build_images/
```

用途分别是：

- `run_evaluation`：每个实例的评测过程日志
- `build_images`：Docker 镜像构建日志

## 八、常见用法

### 1. 先全量预拉取，再跑单题

```bash
cd ~/projects/MT-Agent
bash scripts/swebench-lite-prefetch.sh
```

然后把 `scripts/swebench-lite-predic.sh` 里的：

```bash
INSTANCE_IDS=("sympy__sympy-20590")
LIMIT=10
```

调整成：

```bash
INSTANCE_IDS=("sympy__sympy-20590")
LIMIT=0
```

再执行：

```bash
bash scripts/swebench-lite-predic.sh
bash scripts/swebench-lite-eval.sh
```

### 2. 跑一个小批量基线

把 `scripts/swebench-lite-predic.sh` 里的：

```bash
INSTANCE_IDS=()
LIMIT=10
```

保留，然后执行：

```bash
bash scripts/swebench-lite-predic.sh
bash scripts/swebench-lite-eval.sh
```

## 九、当前设计的要点

当前脚本设计有两个重点：

1. repo 拉取和 prediction 解耦
2. prediction 默认离线使用本地 repo

这样做的好处是：

- 批跑更稳定
- 网络问题影响更小
- 失败点更容易定位

## 十、相关文件

- [swebench_generate_predictions.py](/Users/chenclay/Documents/code/projects/MT-Agent/scripts/swebench_generate_predictions.py)
- [swebench-lite-prefetch.sh](/Users/chenclay/Documents/code/projects/MT-Agent/scripts/swebench-lite-prefetch.sh)
- [swebench-lite-predic.sh](/Users/chenclay/Documents/code/projects/MT-Agent/scripts/swebench-lite-predic.sh)
- [swebench-lite-eval.sh](/Users/chenclay/Documents/code/projects/MT-Agent/scripts/swebench-lite-eval.sh)
