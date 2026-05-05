# SWE-Bench Lite

这套脚本用于在 MT-Agent 上跑 `SWE-bench/SWE-bench_Lite`。

## 目录

- [prefetch.sh](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/prefetch.sh)
  预拉取 Lite 所需 repo 和 commit
- [predict.sh](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/predict.sh)
  生成 predictions
- [eval.sh](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/eval.sh)
  调用官方 harness 评测
- [generate_predictions.py](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/generate_predictions.py)
  prediction 主入口

输出默认放在：

- [predictions](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/predictions)
- [evaluations](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/evaluations)

## 环境

在项目根目录准备：

```bash
uv sync
```

如果缺 `datasets`：

```bash
uv add datasets
```

模型配置依赖这些环境变量：

```bash
export LLM_API_KEY="..."
export LLM_BASE_URL="..."
export MODEL_NAME="..."
```

建议配置 Hugging Face 缓存：

```bash
export HF_HOME="/disk/yangchen/.cache/huggingface"
export HF_DATASETS_CACHE="/disk/yangchen/.cache/huggingface/datasets"
```

## 流程

### 1. 预拉取 repo

```bash
bash benchmark/SWE-Bench-Lite/prefetch.sh
```

### 2. 生成 predictions

```bash
bash benchmark/SWE-Bench-Lite/predict.sh
```

默认使用离线 repo：

- repo 根目录：`.swebench/repos`
- predictions：`benchmark/SWE-Bench-Lite/predictions/mt-agent-lite.jsonl`

### 3. 运行评测

```bash
bash benchmark/SWE-Bench-Lite/eval.sh
```

`eval.sh` 会调用官方 `SWE-bench` harness。评测阶段需要 Docker。

## 常改变量

在脚本顶部一般只需要改这些：

- `LIMIT`
- `INSTANCE_IDS`
- `MODEL_NAME_OR_PATH`
- `OUTPUT_PATH`
- `PREDICTIONS_PATH`
- `RUN_ID`

### 单题

在 `predict.sh` 里设置：

```bash
LIMIT=0
INSTANCE_IDS=("sympy__sympy-20590")
```

### 全量

在 `predict.sh` 里设置：

```bash
LIMIT=0
INSTANCE_IDS=()
```

## 结果查看

预测结果：

- [predictions/deepseek-v4-flash.mt-agent.jsonl](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/predictions/deepseek-v4-flash.mt-agent.jsonl)

评测结果：

- [evaluations/deepseek-v4-flash.mt-agent.json](/Users/chenclay/Documents/code/projects/MT-Agent/benchmark/SWE-Bench-Lite/evaluations/deepseek-v4-flash.mt-agent.json)

官方评测日志一般在 `SWE-bench` 仓库里的：

- `logs/run_evaluation/`
- `logs/build_images/`

## 说明

- prediction 阶段直接在宿主机跑
- evaluation 阶段由官方 harness 自动调用 Docker
- `predict.sh` 默认开启 `resume`
