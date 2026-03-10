---
name: compile-test-feedback-loop
description: Defines compile-test-feedback loops for MT-3000 kernel generation, including retry polling, error extraction, and report output. Use when validating generated AM/SM code with compiler diagnostics and iterative fixes.
---

# Compile Test Feedback Loop

## Quick Start

对 LLM 生成代码执行统一闭环：

1. 写入目标头文件（如 `kernel_vec.h` / `kernel_sca.h`）。
2. 调用 MT-3000 编译链（compile -> link -> makedat）。
3. 解析 stderr，提取可执行错误反馈。
4. 回灌模型并重试，直到成功或达到上限。

## 轮询策略

- 默认重试次数：3~5。
- 每轮保留：模型输出摘要、编译阶段、错误摘要、耗时。
- 同一错误重复出现可提前退出并标记人工介入。

## Additional Resources

- 编译步骤、错误抽取和报告字段建议见 [reference.md](reference.md)。

