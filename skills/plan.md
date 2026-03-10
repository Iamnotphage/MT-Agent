# MT-AutoOptimize 开发计划

## 1. 目标

将 `mt-vectorizer-tool` 重构为基于 Skill 的自动优化工具，覆盖两类核心能力：

- AM 向量化优化（vector API 驱动）
- SM 标量缓存优化（CACHEd/CACHEs/CACHEb）

并建立统一的配置、安全、编译测试与结果展示流程。

## 2. 环境与基础配置

### 2.1 Python 环境

- conda 环境名：`mt-autooptimize`
- Python 版本：`3.10`
- 依赖管理：项目根目录 `environment.yml`

### 2.2 配置与密钥管理

- 配置来源优先级：环境变量 > 配置文件默认值
- 推荐配置键：
  - 编译器: `mt3000_root`
  - 固定脚本: `report_path`, `keep_artifacts`
- 编译测试链路不依赖 LLM API。

## 3. Skill 设计与目录结构

采用低耦合模块化设计，每个知识域一个 Skill：

```text
skills/
├── plan.md
├── mt3000-platform-basics/
│   ├── SKILL.md
│   └── reference.md
├── hthreads-kernel-programming/
│   ├── SKILL.md
│   └── reference.md
├── am-vectorization-templates/
│   ├── SKILL.md
│   └── reference.md
├── sm-cache-optimization-templates/
│   ├── SKILL.md
│   └── reference.md
└── compile-test-feedback-loop/
    ├── SKILL.md
    └── reference.md
```

### 3.1 Skill 内容映射

- `mt3000-platform-basics`：MT-3000 背景、执行模型、访存层级、优化边界。
- `hthreads-kernel-programming`：`get_thread_id/get_group_size`、任务划分、设备端约束。
- `am-vectorization-templates`：向量接口、模板选择、尾部处理。
- `sm-cache-optimization-templates`：CACHEd/CACHEs/CACHEb 策略选择与调用规范。
- `compile-test-feedback-loop`：编译校验、错误回灌重试、结果汇总输出。

## 4. 代码架构（低耦合）

建议拆分如下模块（后续实现阶段按此落地）：

- `core/pipeline.py`：统一流程编排（读取输入 -> 固定脚本编译测试 -> 汇总结果）
- `core/compiler.py`：MT3000 编译封装（复用现有 `mt3000_compiler` 思路）
- `core/config.py`：配置加载与校验（环境变量 + 配置文件）
- `skills_loader/`：Skill 元数据读取与按需加载
- `reporting/`：编译/测试结果展示（终端与 Markdown）

## 5. 固定编译测试策略

针对“输入代码 -> 编译检查 -> 结果落盘”流程，采用固定脚本机制：

- 入口脚本：`scripts/compile_test.py`
- 固定执行三阶段：`compile -> link -> makedat`
- 记录每阶段 `stdout/stderr/returncode`
- 输出结构化报告到 `reports/latest_compile_test.json`

## 6. 编译/测试结果展示

统一生成两类结果：

- 控制台摘要：每轮是否成功、失败阶段（compile/link/makedat）、核心报错
- 工件文件：
  - `reports/latest_run.md`：本次执行摘要
  - `reports/history/<timestamp>.json`：结构化历史记录

建议报告字段：

- 输入文件、优化类型（AM/SM）
- 选用模板与策略
- 固定脚本执行状态
- 编译步骤输出（stdout/stderr 摘要）
- 生成代码输出路径

## 7. 里程碑

### M1（已完成）

- Skill 目录骨架建立
- 关键背景知识封装为独立 Skill 文档
- 本开发计划输出为 `skills/plan.md`

### M2（实现阶段）

- 重构主程序为模块化目录
- 打通 AM/SM 两条流程的统一入口
- 接入配置中心与环境变量注入

### M3（质量阶段）

- 增加最小可行测试（配置加载、Prompt 构建、编译结果解析）
- 增加报告生成与历史归档
- 文档完善（使用说明、常见问题、错误排查）

## 8. 风险与应对

- 编译环境不可用：在启动前执行编译器路径与二进制检查。
- 编译结果不稳定：通过固定脚本、统一环境变量与结构化报告定位问题。
- 配置泄露风险：禁止提交真实密钥，使用环境变量与 `.example` 配置。

