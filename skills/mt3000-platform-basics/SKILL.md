---
name: mt3000-platform-basics
description: Provides MT-3000 platform background, compute-memory model, and optimization constraints. Use when analyzing MT-3000 kernels, deciding AM/SM optimization boundaries, or reasoning about memory hierarchy and data movement.
---

# MT-3000 Platform Basics

## Quick Start

当任务涉及 MT-3000 代码优化时，先明确三件事：

1. 计算模式是标量主导还是向量主导。
2. 数据访问是连续块、局部复用还是随机访问。
3. 当前瓶颈更偏计算还是访存。

## 优化决策基线

- AM 路径：优先处理可按 SIMD 批量推进的循环。
- SM 路径：优先处理 DDR 访存密集且具有局部性的代码段。
- 混合路径：对不能稳定向量化的部分保留标量实现。

## 使用建议

- 先做任务划分（线程范围）再做缓存/向量优化。
- 优先减少不必要的数据搬运与重复加载。
- 所有优化都应以可编译、可测试为第一目标。

## Additional Resources

- 详细平台与访存层级说明见 [reference.md](reference.md)。

