---
name: hthreads-kernel-programming
description: Captures hthreads kernel programming patterns for MT-3000, including thread partitioning, kernel structure, and device-side constraints. Use when generating or reviewing __global__ kernels and task partition logic.
---

# Hthreads Kernel Programming

## Quick Start

生成或改写 `__global__` 核函数时，固定遵循：

1. 获取线程信息：`get_thread_id()` / `get_group_size()`。
2. 计算任务区间：`start/end`。
3. 仅处理本线程负责的数据范围。
4. 末尾处理边界，防止越界。

## 核心约束

- 优先无副作用循环；避免线程间写冲突。
- 代码应可在设备端直接编译通过。
- 不引入与目标环境不兼容的头文件或 API。

## Additional Resources

- 常用接口与任务划分模板见 [reference.md](reference.md)。

