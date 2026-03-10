# MT-AutoOptimize

## 项目介绍

`MT-AutoOptimize` 是一个面向 MT-3000 平台的自动代码优化工具，参考 `mt-vectorizer-tool` 重构而来。  
工具提供两类优化能力：

- AM 向量化优化（生成 `_vec_qwen` 风格代码）
- SM 标量缓存优化（生成 `_sca_qwen` 风格代码）

整体流程为：**分析源码 -> 生成优化代码 -> 编译测试 -> 输出结果**。

## 环境搭建与激活

1. 创建环境：

```bash
/thfs3/home/xjtu_cx/miniconda3/bin/conda env create -f environment.yml
```

2. 激活环境：

```bash
source /thfs3/home/xjtu_cx/miniconda3/bin/activate mt-autooptimize
```

3. 准备配置文件：

```bash
cp config.example.json config.json
```

配置中包含两组 LLM：

- `analyze_llm`：用于源码分析
- `code_llm`：用于优化代码生成

## 项目结构

```text
MT-AutoOptimize/
├── main.py                     # 项目主入口
├── config.example.json         # 配置模板
├── environment.yml             # conda 环境
├── input/                      # 输入目录（如 test.dev.c / compile-entry.dev.c）
├── output/
│   ├── code/                   # 优化后代码输出（kernel_generated.h）
│   └── reports/                # 编译测试与流程报告
├── core/
│   ├── analyzer.py             # 源码分析
│   ├── optimizer.py            # 优化代码生成
│   ├── compiler.py             # MT-3000 编译测试封装
│   ├── pipeline.py             # 核心流程编排
│   └── config.py               # 配置加载
├── prompts/                    # Prompt 模板
├── scripts/
│   └── compile_test.py         # 独立编译测试脚本
└── skills/                     # Skill 与资源
```

## 使用方法

### 1) 一键主流程（推荐）

```bash
python3 main.py \
  -i input/test.dev.c \
  --mode auto
```

常用参数：

- `--mode auto|am|sm`：自动选择或强制优化模式
- `--compile-entry`：编译入口文件（默认 `output/code/compile-entry.dev.c`）
- `--output-dir output`：输出目录（默认 `output`）
- `--config config.json`：配置文件路径

### 2) 仅做编译测试

```bash
python3 scripts/compile_test.py -i output/code/compile-entry.dev.c
```

报告命名规则：

- `output/reports/compile_test_YYYYMMDD_HHMMSS.log`

## 输出说明

- 优化代码输出到：`output/code/kernel_generated.h`
- 报告输出到：`output/reports/`

