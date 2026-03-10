---
name: am-vectorization-templates
description: Provides MT-3000 AM vectorization interfaces and transformation templates. Use when converting scalar kernels to vector kernels, selecting vector templates, or fixing AM vectorization compile issues.
---

# AM Vectorization Templates

## Quick Start

进行 AM 向量化时，按固定流水线执行：

1. 线程任务划分。
2. 向量常量初始化（如 `one_vec`）。
3. `vector_load` 搬运到向量缓冲。
4. 使用向量算子计算。
5. `vector_store` 写回。
6. 尾部标量处理。

## 最小输出约束

- 函数名建议后缀：`_vec_qwen`。
- 无法向量化段允许保留标量逻辑。
- 结果必须是完整可编译 C 代码。

## Additional Resources

- 向量接口与通用模板摘要见 [reference.md](reference.md)。

