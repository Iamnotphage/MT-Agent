---
name: sm-cache-optimization-templates
description: Provides SM cache optimization strategy selection and templates for CACHEd, CACHEs, and CACHEb. Use when optimizing scalar kernels with on-chip cache or when choosing cache strategy by memory access pattern.
---

# SM Cache Optimization Templates

## Quick Start

标量缓存优化按以下规则：

1. 连续区间读改写：优先 `CACHEb`。
2. 局部性强、单路复用：优先 `CACHEs`。
3. 访问随机、冲突较多：优先 `CACHEd`。

## 核心约束

- 先 `INIT`，再 `RD/WT`，结束必须 `FLUSH` 或 `INVALID`。
- 写回场景必须 `FLUSH`，只读可 `INVALID`。
- 函数名建议后缀：`_sca_qwen`。

## Additional Resources

- 三种缓存策略接口说明与模板片段见 [reference.md](reference.md)。

